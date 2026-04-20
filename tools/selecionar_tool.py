from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "selecionar"
    nome = "Selecionar"
    descricao_painel = "Selecione elementos com clique, caixa de seleção e ciclo com botão direito."

    def __init__(self):
        super().__init__()
        self._inicio_caixa: QPointF | None = None
        self._fim_caixa: QPointF | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self.set_status("Clique para selecionar. Arraste para seleção por área. RMB cicla sobrepostos.")

    def on_mouse_press(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if event.button() == Qt.RightButton:
            if canvas._selecionar_proximo_em_ponto(pos):
                self.set_status("Elemento alternado com botão direito.")
                event.accept()
                return True
            return False
        if event.button() != Qt.LeftButton:
            return False

        indices = canvas._indices_elementos_em_ponto(pos)
        if indices:
            selecionado = indices[0]
            if event.modifiers() & Qt.ShiftModifier:
                if selecionado in canvas._selecionados:
                    canvas._selecionados.remove(selecionado)
                else:
                    canvas._selecionados.add(selecionado)
            else:
                canvas._selecionados = {selecionado}
            self._inicio_caixa = None
            self._fim_caixa = None
            self.set_status(f"{len(canvas._selecionados)} elemento(s) selecionado(s).")
            canvas.update()
            event.accept()
            return True

        if not (event.modifiers() & Qt.ShiftModifier):
            canvas._selecionados.clear()
        self._inicio_caixa = pos
        self._fim_caixa = pos
        self.set_status("Arraste para selecionar por área.")
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._inicio_caixa is None:
            return False
        self._fim_caixa = canvas._ponto_com_snap(event.position())
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton or self._inicio_caixa is None or self._fim_caixa is None:
            return False
        x1 = min(self._inicio_caixa.x(), self._fim_caixa.x())
        y1 = min(self._inicio_caixa.y(), self._fim_caixa.y())
        x2 = max(self._inicio_caixa.x(), self._fim_caixa.x())
        y2 = max(self._inicio_caixa.y(), self._fim_caixa.y())

        if sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) > (4.0 / max(canvas.zoom, 0.001)):
            selecionados_area: set[int] = set()
            for idx, el in enumerate(canvas.cena.elementos):
                if el.get("tipo") == "polyline":
                    pontos = [QPointF(float(px), float(py)) for px, py in el.get("pontos", [])]
                elif el.get("tipo") == "bezier_quadratica":
                    p0 = QPointF(*el["p0"])
                    p1 = QPointF(*el["p1"])
                    p2 = QPointF(*el["p2"])
                    pontos = canvas._amostrar_bezier_quadratica(p0, p1, p2, segmentos=24)
                else:
                    pontos = []
                if any(x1 <= p.x() <= x2 and y1 <= p.y() <= y2 for p in pontos):
                    selecionados_area.add(idx)
            if event.modifiers() & Qt.ShiftModifier:
                canvas._selecionados |= selecionados_area
            else:
                canvas._selecionados = selecionados_area
            self.set_status(f"Seleção por área: {len(canvas._selecionados)} elemento(s).")

        self._inicio_caixa = None
        self._fim_caixa = None
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._inicio_caixa is None or self._fim_caixa is None:
            return
        p1 = canvas._cena_para_tela(self._inicio_caixa)
        p2 = canvas._cena_para_tela(self._fim_caixa)
        x = min(p1.x(), p2.x())
        y = min(p1.y(), p2.y())
        w = abs(p2.x() - p1.x())
        h = abs(p2.y() - p1.y())
        painter.setPen(QPen(QColor("#33c1ff"), 1, Qt.DashLine))
        painter.setBrush(QColor(40, 160, 255, 40))
        painter.drawRect(int(x), int(y), int(w), int(h))
