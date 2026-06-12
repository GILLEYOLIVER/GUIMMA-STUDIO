from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "remover_graduacao"
    nome = "Remover Graduacao"
    descricao_painel = "Remove toda a graduação do molde indicado."

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._status(canvas, "Remover graduação: clique no molde para limpar toda a graduação.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            canvas.set_ferramenta_ativa("selecionar")
            self._status(canvas, "Remover graduação finalizado. Voltando para Selecionar.")
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position()) if hasattr(canvas, "_ponto_com_snap") else QPointF(event.position())
        molde_idx = self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            self._status(canvas, "Remover graduação: clique sobre um molde.")
            event.accept()
            return True
        molde = canvas.cena.elementos[molde_idx]
        removidas = self._remover_graduacao_molde(molde)
        canvas._selecionados = {molde_idx}
        if removidas:
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
            elif hasattr(canvas, "elementos_alterados"):
                canvas.elementos_alterados.emit()
            self._status(canvas, "Graduação removida do molde.")
        else:
            self._status(canvas, "O molde indicado não possui graduação para remover.")
        canvas.update()
        event.accept()
        return True

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        for idx, el in enumerate(canvas.cena.elementos):
            if isinstance(el, dict) and el.get("molde") and self._ponto_dentro_bbox(el, pos):
                return idx
        return None

    @staticmethod
    def _remover_graduacao_molde(molde: dict) -> bool:
        if not isinstance(molde, dict):
            return False
        chaves = [chave for chave in molde.keys() if str(chave).startswith("graduacao_")]
        if not chaves:
            return False
        for chave in chaves:
            molde.pop(chave, None)
        return True

    @staticmethod
    def _ponto_dentro_bbox(molde: dict, pos: QPointF) -> bool:
        pontos = molde.get("pontos") or []
        coords = []
        for item in pontos:
            try:
                x, y = item[0], item[1]
                coords.append((float(x), float(y)))
            except Exception:
                continue
        if not coords:
            return False
        xs = [x for x, _y in coords]
        ys = [y for _x, y in coords]
        return min(xs) <= pos.x() <= max(xs) and min(ys) <= pos.y() <= max(ys)

    def _status(self, canvas, texto: str):
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
