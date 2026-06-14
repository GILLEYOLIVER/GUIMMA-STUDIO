from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QPointF, Qt

from tools.colar_tool import Ferramenta as FerramentaColar
from tools.copiar_tool import Ferramenta as FerramentaCopiar
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "copiar_ou_trocar_elemento"
    nome = "Copiar ou trocar elemento"
    usa_painel_auxiliar = False
    descricao_painel = "Copia a seleção ou substitui o elemento clicado pela cópia atual."

    def __init__(self):
        super().__init__()
        self._copiador = FerramentaCopiar()
        self._colador = FerramentaColar()

    def on_activate(self, canvas) -> None:
        total = 0
        if self._indices_selecionados(canvas):
            total = self._copiador._copiar_selecao(canvas)
        if total > 0:
            self._status(canvas, f"Copiado: {total} elemento(s). Clique em outro elemento para trocar ou use Colar em outra aba.")
            return
        if self._tem_buffer(canvas):
            self._status(canvas, "Clique no elemento que deseja trocar pela cópia atual. Direito finaliza.")
        else:
            self._status(canvas, "Selecione ou clique em um elemento para copiar. Depois clique em outro para trocar.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._finalizar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = self._posicao_cena(canvas, event)
        idx = self._indice_elemento_em_ponto(canvas, pos)
        if idx is None:
            self._status(canvas, "Nenhum elemento encontrado no clique.")
            event.accept()
            return True

        if self._tem_buffer(canvas):
            if self._trocar_elemento(canvas, idx):
                self._status(canvas, "Elemento trocado pela cópia atual.")
            else:
                self._status(canvas, "Não foi possível trocar o elemento clicado.")
            event.accept()
            return True

        self._selecionar(canvas, idx)
        total = self._copiador._copiar_selecao(canvas)
        if total > 0:
            self._status(canvas, f"Copiado: {total} elemento(s). Clique no destino para trocar.")
        else:
            self._status(canvas, "Não foi possível copiar o elemento clicado.")
        event.accept()
        return True

    def _trocar_elemento(self, canvas, idx_alvo: int) -> bool:
        if canvas is None or not hasattr(canvas, "cena"):
            return False
        elementos_canvas = list(getattr(canvas.cena, "elementos", []) or [])
        if not (0 <= idx_alvo < len(elementos_canvas)):
            return False

        novos = self._colador._ler_buffer(canvas)
        if not novos:
            return False
        novos = deepcopy(novos)
        self._colador._renovar_ids_e_vinculos(novos)

        indices_alvo = self._indices_alvo_com_vinculos(canvas, idx_alvo)
        if not indices_alvo:
            return False
        destino = [deepcopy(elementos_canvas[idx]) for idx in indices_alvo if 0 <= idx < len(elementos_canvas)]
        dx, dy = self._delta_centralizar(novos, destino)
        for el in novos:
            self._colador._mover_elemento_completo(el, dx, dy)

        inserir_em = min(indices_alvo)
        substituidos = set(indices_alvo)
        elementos_finais: list[dict] = []
        inseriu = False
        for idx, el in enumerate(elementos_canvas):
            if idx == inserir_em:
                elementos_finais.extend(novos)
                inseriu = True
            if idx not in substituidos:
                elementos_finais.append(el)
        if not inseriu:
            elementos_finais.extend(novos)
            inserir_em = len(elementos_finais) - len(novos)

        canvas.cena.elementos = elementos_finais
        canvas._selecionados = set(range(inserir_em, inserir_em + len(novos)))
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        if hasattr(canvas, "elementos_alterados"):
            try:
                canvas.elementos_alterados.emit()
            except Exception:
                pass
        if hasattr(canvas, "update"):
            canvas.update()
        return True

    def _indices_alvo_com_vinculos(self, canvas, idx_alvo: int) -> list[int]:
        indices = {int(idx_alvo)}
        elementos = list(getattr(canvas.cena, "elementos", []) or [])
        if not (0 <= idx_alvo < len(elementos)):
            return []
        alvo = elementos[idx_alvo]
        if isinstance(alvo, dict) and alvo.get("molde") and hasattr(canvas, "_indices_costuras_vinculadas"):
            try:
                indices.update(int(i) for i in canvas._indices_costuras_vinculadas(idx_alvo))
            except Exception:
                pass
        molde_id = self._copiador._molde_id(alvo) if isinstance(alvo, dict) else ""
        if molde_id and isinstance(alvo, dict) and alvo.get("molde"):
            for idx, outro in enumerate(elementos):
                if idx in indices or not isinstance(outro, dict):
                    continue
                if self._copiador._linha_vinculada_ao_molde(outro, molde_id):
                    indices.add(idx)
        return sorted(i for i in indices if 0 <= i < len(elementos))

    def _delta_centralizar(self, origem: list[dict], destino: list[dict]) -> tuple[float, float]:
        bbox_origem = self._copiador._bbox_elementos(origem)
        bbox_destino = self._copiador._bbox_elementos(destino)
        if bbox_origem is None or bbox_destino is None:
            return 0.0, 0.0
        ox = (bbox_origem[0] + bbox_origem[2]) / 2.0
        oy = (bbox_origem[1] + bbox_origem[3]) / 2.0
        dx = (bbox_destino[0] + bbox_destino[2]) / 2.0
        dy = (bbox_destino[1] + bbox_destino[3]) / 2.0
        return dx - ox, dy - oy

    def _indice_elemento_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indices_elementos_em_ponto"):
            try:
                indices = list(canvas._indices_elementos_em_ponto(pos) or [])
                if indices:
                    return int(indices[0])
            except Exception:
                pass
        if hasattr(canvas, "_indice_molde_em_ponto"):
            try:
                idx = canvas._indice_molde_em_ponto(pos)
                if idx is not None:
                    return int(idx)
            except Exception:
                pass
        return None

    def _posicao_cena(self, canvas, event) -> QPointF:
        try:
            return QPointF(canvas._ponto_com_snap(event.position()))
        except Exception:
            if hasattr(canvas, "_tela_para_cena"):
                return QPointF(canvas._tela_para_cena(event.position()))
            return QPointF(event.position())

    def _indices_selecionados(self, canvas) -> list[int]:
        if canvas is None or not hasattr(canvas, "cena"):
            return []
        elementos = list(getattr(canvas.cena, "elementos", []) or [])
        indices = sorted(int(i) for i in (getattr(canvas, "_selecionados", set()) or set()))
        return [idx for idx in indices if 0 <= idx < len(elementos)]

    def _selecionar(self, canvas, idx: int) -> None:
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(idx)}
        if hasattr(canvas, "update"):
            canvas.update()

    def _tem_buffer(self, canvas) -> bool:
        try:
            if hasattr(canvas, "obter_buffer_copia"):
                return bool(canvas.obter_buffer_copia())
            return bool(getattr(canvas, "_buffer_copia", None))
        except Exception:
            return False

    def _finalizar(self, canvas) -> None:
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        elif hasattr(canvas, "ferramenta_padrao_solicitada"):
            try:
                canvas.ferramenta_padrao_solicitada.emit("selecionar")
            except Exception:
                pass
        if hasattr(canvas, "update"):
            canvas.update()
        self._status(canvas, "Ferramenta Copiar ou trocar elemento finalizada.")

    def _status(self, canvas, texto: str) -> None:
        try:
            if getattr(canvas, "lbl_status", None) is not None:
                canvas.lbl_status.setText(texto)
                return
        except Exception:
            pass
        try:
            self.set_status(texto)
        except Exception:
            pass
