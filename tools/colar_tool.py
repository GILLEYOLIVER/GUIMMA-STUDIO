from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

try:
    from PySide6.QtCore import QTimer
except Exception:  # pragma: no cover - fallback apenas para ambientes sem Qt
    QTimer = None

from tools.tool_base import FerramentaBase

try:
    from tools.movimento_utils import mover_elemento_por_delta, mover_valor_estruturado_por_delta
except Exception:  # pragma: no cover
    mover_elemento_por_delta = None
    mover_valor_estruturado_por_delta = None


class Ferramenta(FerramentaBase):
    id_ferramenta = "colar"
    nome = "Colar"
    usa_painel_auxiliar = False
    descricao_painel = "Cola a cópia interna no canvas e volta para Selecionar."

    DESLOCAMENTO_BASE_CM = 2.0

    def on_activate(self, canvas):
        total = self._colar(canvas)
        if total > 0:
            self._status(canvas, f"Colado: {total} elemento(s).")
        else:
            self._status(canvas, "Colar: não existe cópia na memória. Use Copiar primeiro.")
        self._voltar_para_selecionar(canvas)

    def on_mouse_press(self, canvas, event) -> bool:
        total = self._colar(canvas)
        if total > 0:
            self._status(canvas, f"Colado: {total} elemento(s).")
        else:
            self._status(canvas, "Colar: não existe cópia na memória. Use Copiar primeiro.")
        self._voltar_para_selecionar(canvas)
        try:
            event.accept()
        except Exception:
            pass
        return True

    def _colar(self, canvas) -> int:
        if canvas is None or not hasattr(canvas, "cena"):
            return 0

        elementos = self._ler_buffer(canvas)
        if not elementos:
            return 0

        offset_n = int(getattr(canvas, "_offset_colagem", 0) or 0) + 1
        canvas._offset_colagem = offset_n
        dx = self.DESLOCAMENTO_BASE_CM * offset_n
        dy = self.DESLOCAMENTO_BASE_CM * offset_n

        novos = deepcopy(elementos)
        self._renovar_ids_e_vinculos(novos)

        for el in novos:
            self._mover_elemento_completo(el, dx, dy)

        inicio = len(canvas.cena.elementos)
        canvas.cena.elementos.extend(novos)
        indices_novos = list(range(inicio, inicio + len(novos)))
        canvas._selecionados = set(indices_novos)

        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        if hasattr(canvas, "elementos_alterados"):
            try:
                canvas.elementos_alterados.emit()
            except Exception:
                pass
        if hasattr(canvas, "update"):
            canvas.update()
        return len(novos)

    def _ler_buffer(self, canvas) -> list[dict]:
        if hasattr(canvas, "obter_buffer_copia"):
            buffer = canvas.obter_buffer_copia()
        else:
            buffer = getattr(canvas, "_buffer_copia", None)
        if not buffer:
            return []

        if isinstance(buffer, dict) and isinstance(buffer.get("elementos"), list):
            return [deepcopy(el) for el in buffer.get("elementos", []) if isinstance(el, dict)]

        if isinstance(buffer, list):
            return [deepcopy(el) for el in buffer if isinstance(el, dict)]

        if isinstance(buffer, dict):
            return [deepcopy(buffer)]

        return []

    def _renovar_ids_e_vinculos(self, elementos: list[dict]) -> None:
        """Cria novos IDs para a cópia e mantém costuras presas ao molde copiado."""
        mapa_molde: dict[str, str] = {}

        for el in elementos:
            mid = self._molde_id(el)
            if mid and (el.get("molde") or el.get("costura_de_molde_id") or el.get("molde_linha_vinculada")):
                mapa_molde.setdefault(mid, str(uuid4()))

            costura_mid = str(el.get("costura_de_molde_id") or "").strip()
            if costura_mid:
                mapa_molde.setdefault(costura_mid, str(uuid4()))

        for el in elementos:
            id_antigo = str(el.get("id") or "").strip()
            if id_antigo:
                el["id"] = str(uuid4())

            mid_antigo = self._molde_id(el)
            if mid_antigo:
                el["molde_id"] = mapa_molde.get(mid_antigo, str(uuid4()) if el.get("molde") else mid_antigo)

            costura_mid = str(el.get("costura_de_molde_id") or "").strip()
            if costura_mid:
                novo_mid = mapa_molde.get(costura_mid, costura_mid)
                el["costura_de_molde_id"] = novo_mid
                el["molde_id"] = novo_mid
                el["molde_linha_vinculada"] = True
                el["parte_do_molde"] = True

            if bool(el.get("molde_linha_vinculada")):
                mid = str(el.get("molde_id") or "").strip()
                if mid in mapa_molde:
                    el["molde_id"] = mapa_molde[mid]
                el["parte_do_molde"] = True

            metadados = el.get("metadados")
            if isinstance(metadados, dict):
                if "id" in metadados:
                    metadados["id"] = str(uuid4())
                if "molde_id" in metadados and str(metadados.get("molde_id") or "").strip() in mapa_molde:
                    metadados["molde_id"] = mapa_molde[str(metadados.get("molde_id")).strip()]
                if "costura_de_molde_id" in metadados and str(metadados.get("costura_de_molde_id") or "").strip() in mapa_molde:
                    metadados["costura_de_molde_id"] = mapa_molde[str(metadados.get("costura_de_molde_id")).strip()]

    def _mover_elemento_completo(self, elemento: dict, dx: float, dy: float) -> None:
        """Move a cópia sem deixar pontos auxiliares, dobra ou costura para trás."""
        if mover_elemento_por_delta is not None:
            try:
                mover_elemento_por_delta(elemento, dx, dy)
            except Exception:
                pass
        else:
            self._mover_topo_basico(elemento, dx, dy)

        # mover_elemento_por_delta cobre os pontos principais. Estes campos
        # abaixo podem guardar pontos aninhados usados por dobra/restauração.
        for chave in (
            "estado_dobra",
            "contornos_dobra_original",
            "dobra_eixo",
            "ponto_restauracao",
            "pontos_restauracao",
            "restauracao",
        ):
            if chave in elemento:
                elemento[chave] = self._mover_valor_recursivo(elemento.get(chave), dx, dy)

    def _mover_topo_basico(self, elemento: dict, dx: float, dy: float) -> None:
        for chave in (
            "pontos",
            "controle_cantos",
            "controle_auxiliares",
            "marcacoes_no_perimetro",
            "distancias_no_perimetro",
            "marcacoes_perimetro",
            "pontos_controle_principais",
            "pontos_auxiliares",
            "piques_config",
            "graduacao_tabela",
            "graduacao_pontos",
        ):
            if chave in elemento:
                if mover_valor_estruturado_por_delta is not None and chave in {
                    "piques_config",
                    "graduacao_tabela",
                    "graduacao_pontos",
                }:
                    elemento[chave] = mover_valor_estruturado_por_delta(elemento.get(chave), dx, dy)
                else:
                    elemento[chave] = self._mover_valor_recursivo(elemento.get(chave), dx, dy)

        for chave in (
            "p0",
            "p1",
            "p2",
            "pos",
            "ponto_texto",
            "ponto_texto_nome",
            "ponto_texto_descricao",
            "ponto_texto_observacoes",
            "nome_posicao",
            "nome_centro",
            "fio_origem",
            "fio_fim",
            "seta_origem",
            "seta_fim",
        ):
            if chave in elemento:
                elemento[chave] = self._mover_valor_recursivo(elemento.get(chave), dx, dy)

    def _mover_valor_recursivo(self, valor, dx: float, dy: float):
        if isinstance(valor, dict):
            movido = dict(valor)
            if "x" in movido and "y" in movido and self._numero(movido.get("x")) and self._numero(movido.get("y")):
                movido["x"] = float(movido["x"]) + dx
                movido["y"] = float(movido["y"]) + dy
                return movido
            for chave, item in list(movido.items()):
                if self._chave_com_pontos(chave):
                    movido[chave] = self._mover_valor_recursivo(item, dx, dy)
            return movido

        if isinstance(valor, list):
            if len(valor) >= 2 and self._numero(valor[0]) and self._numero(valor[1]):
                return [float(valor[0]) + dx, float(valor[1]) + dy, *valor[2:]]
            return [self._mover_valor_recursivo(item, dx, dy) for item in valor]

        if isinstance(valor, tuple):
            if len(valor) >= 2 and self._numero(valor[0]) and self._numero(valor[1]):
                return (float(valor[0]) + dx, float(valor[1]) + dy, *valor[2:])
            return tuple(self._mover_valor_recursivo(item, dx, dy) for item in valor)

        return valor

    @staticmethod
    def _chave_com_pontos(chave: object) -> bool:
        txt = str(chave or "").lower()
        return any(
            termo in txt
            for termo in (
                "ponto",
                "pontos",
                "contorno",
                "controle",
                "marcacao",
                "marcação",
                "dobra",
                "eixo",
                "segmento",
                "segmentos",
                "pique",
                "piques",
                "origem",
                "fim",
                "posicao",
                "posição",
                "seta",
                "fio",
            )
        )

    @staticmethod
    def _molde_id(elemento: dict) -> str:
        return str(elemento.get("molde_id") or elemento.get("id") or "").strip()

    @staticmethod
    def _numero(valor) -> bool:
        try:
            float(valor)
            return True
        except Exception:
            return False

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

    def _voltar_para_selecionar(self, canvas) -> None:
        def aplicar():
            try:
                if hasattr(canvas, "ferramenta_padrao_solicitada"):
                    canvas.ferramenta_padrao_solicitada.emit("selecionar")
                elif hasattr(canvas, "set_ferramenta_ativa"):
                    canvas.set_ferramenta_ativa("selecionar")
            except Exception:
                pass

        if QTimer is not None:
            QTimer.singleShot(0, aplicar)
        else:
            aplicar()
