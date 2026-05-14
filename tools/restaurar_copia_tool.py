from __future__ import annotations

from copy import deepcopy
from time import monotonic

from PySide6.QtWidgets import QMessageBox

from tools.tool_base import FerramentaBase


_STORE_ATTR = "_guimma_pontos_restauracao_moldes"
_LAST_ATTR = "_guimma_ultimo_ponto_restauracao"
_RUNNING_ATTR = "_guimma_restaurar_copia_em_execucao"
_LAST_DONE_ATTR = "_guimma_restaurar_copia_ultimo_fim"


class Ferramenta(FerramentaBase):
    id_ferramenta = "restaurar_copia"
    nome = "Restaurar"
    descricao_painel = "Restaura um ponto de restauração substituindo o molde atual ou criando uma cópia restaurada."

    def ativar(self):
        return "Use Restaurar para substituir o molde atual ou restaurar como cópia."

    def on_activate(self, canvas):
        if self._deve_ignorar_chamada_duplicada(canvas):
            return None
        setattr(canvas, _RUNNING_ATTR, True)
        try:
            self._executar(canvas)
        finally:
            setattr(canvas, _RUNNING_ATTR, False)
            setattr(canvas, _LAST_DONE_ATTR, monotonic())
        return None

    def _executar(self, canvas):
        store = getattr(canvas, _STORE_ATTR, None)
        if not isinstance(store, dict) or not store:
            self._status(canvas, "Nenhum ponto de restauração foi criado para este documento.")
            return

        selecionados = self._indices_moldes_selecionados(canvas)
        if not selecionados:
            self._avisar_indique_molde(canvas)
            return

        snapshots = self._snapshots_para_restaurar(canvas, store, selecionados)
        if not snapshots:
            self._status(canvas, "O molde selecionado não possui ponto de restauração. Crie o ponto primeiro.")
            return

        escolha = self._perguntar_modo(canvas, len(snapshots), True)
        if escolha == "cancelar":
            self._status(canvas, "Restauração cancelada.")
            return
        if escolha == "substituir":
            self._substituir_moldes(canvas, snapshots)
            return
        if escolha == "copia":
            self._restaurar_como_copia(canvas, snapshots)
            return

    def _deve_ignorar_chamada_duplicada(self, canvas) -> bool:
        try:
            if bool(getattr(canvas, _RUNNING_ATTR, False)):
                return True
            ultimo = float(getattr(canvas, _LAST_DONE_ATTR, 0.0) or 0.0)
            return (monotonic() - ultimo) < 0.75
        except Exception:
            return False

    def _indices_moldes_selecionados(self, canvas) -> list[int]:
        elementos = list(getattr(getattr(canvas, "cena", None), "elementos", []) or [])
        selecionados = getattr(canvas, "_selecionados", set()) or set()
        indices = []
        try:
            candidatos = sorted(int(i) for i in selecionados)
        except Exception:
            candidatos = []
        for idx in candidatos:
            if 0 <= idx < len(elementos):
                el = elementos[idx]
                if isinstance(el, dict) and el.get("molde"):
                    indices.append(idx)
        return indices

    def _snapshots_para_restaurar(self, canvas, store: dict, selecionados: list[int]) -> list[tuple[int | None, dict]]:
        snapshots: list[tuple[int | None, dict]] = []
        for idx in selecionados:
            dados = store.get(int(idx))
            if isinstance(dados, dict) and isinstance(dados.get("snapshot"), dict):
                snapshots.append((int(idx), self._copiar_elemento_limpo(canvas, dados["snapshot"])))
        return snapshots

    def _avisar_indique_molde(self, canvas):
        mensagem = "Indique o molde ou elemento que deseja restaurar."
        self._status(canvas, mensagem)
        parent = None
        try:
            parent = canvas.window() if hasattr(canvas, "window") else None
        except Exception:
            parent = None
        try:
            QMessageBox.information(parent, "Restaurar", mensagem)
        except Exception:
            pass

    def _perguntar_modo(self, canvas, quantidade: int, tem_selecao: bool) -> str:
        parent = None
        try:
            parent = canvas.window() if hasattr(canvas, "window") else None
        except Exception:
            parent = None

        caixa = QMessageBox(parent)
        caixa.setIcon(QMessageBox.Question)
        caixa.setWindowTitle("Restaurar ponto de restauração")
        if quantidade == 1:
            caixa.setText("Como deseja restaurar este ponto de restauração?")
        else:
            caixa.setText(f"Como deseja restaurar estes {quantidade} pontos de restauração?")
        caixa.setInformativeText(
            "Substituir troca o molde selecionado pela versão salva.\n"
            "Restaurar cópia mantém o molde atual e cria uma nova cópia restaurada."
        )
        btn_substituir = caixa.addButton("Substituir", QMessageBox.AcceptRole)
        btn_copia = caixa.addButton("Restaurar cópia", QMessageBox.ActionRole)
        btn_cancelar = caixa.addButton("Cancelar", QMessageBox.RejectRole)
        if not tem_selecao:
            btn_substituir.setEnabled(False)
            caixa.setInformativeText(
                "Restaurar cópia cria uma nova cópia restaurada.\n"
                "Para substituir, selecione o molde que possui ponto de restauração."
            )
        caixa.setDefaultButton(btn_copia if not tem_selecao else btn_substituir)
        caixa.exec()
        clicado = caixa.clickedButton()
        if clicado is btn_substituir and btn_substituir.isEnabled():
            return "substituir"
        if clicado is btn_copia:
            return "copia"
        if clicado is btn_cancelar:
            return "cancelar"
        return "cancelar"

    def _substituir_moldes(self, canvas, snapshots: list[tuple[int | None, dict]]):
        elementos = getattr(getattr(canvas, "cena", None), "elementos", None)
        if not isinstance(elementos, list):
            self._status(canvas, "Não foi possível acessar os elementos do canvas.")
            return

        substituidos: list[int] = []
        for idx, snapshot in snapshots:
            if idx is None or not (0 <= idx < len(elementos)):
                continue
            elementos[int(idx)] = self._copiar_elemento_limpo(canvas, snapshot)
            substituidos.append(int(idx))

        if not substituidos:
            self._status(canvas, "Nenhum molde selecionado pôde ser substituído.")
            return

        try:
            canvas._selecionados = set(substituidos)
        except Exception:
            pass
        self._finalizar_alteracao(canvas)
        if len(substituidos) == 1:
            self._status(canvas, "Molde substituído pelo ponto de restauração.")
        else:
            self._status(canvas, f"{len(substituidos)} moldes substituídos pelos pontos de restauração.")

    def _restaurar_como_copia(self, canvas, snapshots: list[tuple[int | None, dict]]):
        elementos = getattr(getattr(canvas, "cena", None), "elementos", None)
        if not isinstance(elementos, list):
            self._status(canvas, "Não foi possível acessar os elementos do canvas.")
            return

        novos_indices: list[int] = []
        for _idx_original, snapshot in snapshots:
            novo = self._copiar_elemento_limpo(canvas, snapshot)
            nome = str(novo.get("nome_molde") or novo.get("nome") or "Molde").strip()
            if nome and not nome.lower().endswith("cópia restaurada"):
                novo["nome_molde"] = f"{nome} - cópia restaurada"
            elementos.append(novo)
            novos_indices.append(len(elementos) - 1)

        if not novos_indices:
            self._status(canvas, "Nenhuma cópia pôde ser restaurada.")
            return

        try:
            canvas._selecionados = set(novos_indices)
        except Exception:
            pass
        self._finalizar_alteracao(canvas)
        if len(novos_indices) == 1:
            self._status(canvas, "Cópia restaurada criada a partir do ponto de restauração.")
        else:
            self._status(canvas, f"{len(novos_indices)} cópias restauradas criadas.")

    def _finalizar_alteracao(self, canvas):
        try:
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
            elif hasattr(canvas, "elementos_alterados"):
                canvas.elementos_alterados.emit()
        except Exception:
            pass
        try:
            if hasattr(canvas, "update"):
                canvas.update()
        except Exception:
            pass

    def _copiar_elemento_limpo(self, canvas, elemento: dict) -> dict:
        try:
            if hasattr(canvas, "_elemento_serializavel"):
                return canvas._elemento_serializavel(elemento)
        except Exception:
            pass
        return deepcopy(elemento)

    def _status(self, canvas, mensagem: str):
        try:
            self.set_status(mensagem)
            return
        except Exception:
            pass
        try:
            janela = canvas.window() if hasattr(canvas, "window") else None
            lbl = getattr(janela, "lbl_status", None) if janela is not None else None
            if lbl is not None and hasattr(lbl, "setText"):
                lbl.setText(mensagem)
                return
        except Exception:
            pass
        try:
            lbl = getattr(canvas, "lbl_status", None)
            if lbl is not None and hasattr(lbl, "setText"):
                lbl.setText(mensagem)
        except Exception:
            pass
