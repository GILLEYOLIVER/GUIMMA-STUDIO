from __future__ import annotations

from math import floor, log10

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from canvas.visualizacao import VisualizacaoCanvas
from canvas.cena import CenaDocumento


class ReguaWidget(QWidget):
    def __init__(self, horizontal: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.horizontal = horizontal
        self.zoom = 1.0
        self.origem_x = 0.0
        self.origem_y = 0.0
        if horizontal:
            self.setFixedHeight(20)
        else:
            self.setFixedWidth(28)

    def atualizar_viewport(self, zoom: float, origem_x: float, origem_y: float):
        self.zoom = max(0.1, zoom)
        self.origem_x = origem_x
        self.origem_y = origem_y
        self.update()

    def atualizar_zoom(self, zoom: float):
        self.atualizar_viewport(zoom, self.origem_x, self.origem_y)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f2f2f2"))
        painter.setPen(QPen(QColor("#222222"), 1))

        pixel_step = max(25, int(40 * self.zoom))
        passo_unidade = self._passo_principal()
        if self.horizontal:
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            for x in range(0, self.width(), 5):
                if x % pixel_step == 0:
                    painter.drawLine(x, self.height() - 12, x, self.height())
                elif x % max(1, pixel_step // 2) == 0:
                    painter.drawLine(x, self.height() - 8, x, self.height())
                else:
                    painter.drawLine(x, self.height() - 4, x, self.height())
            inicio = self.origem_x
            fim = self.origem_x + (self.width() / max(self.zoom, 0.001))
            valor = floor(inicio / passo_unidade) * passo_unidade
            while valor <= fim + passo_unidade:
                px = int((valor - self.origem_x) * self.zoom)
                if 0 <= px <= self.width():
                    painter.drawLine(px, self.height() - 12, px, self.height())
                    painter.drawText(px + 2, 9, self._formatar_valor(valor, passo_unidade))
                valor += passo_unidade
        else:
            painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
            for y in range(0, self.height(), 5):
                if y % pixel_step == 0:
                    painter.drawLine(self.width() - 12, y, self.width(), y)
                elif y % max(1, pixel_step // 2) == 0:
                    painter.drawLine(self.width() - 8, y, self.width(), y)
                else:
                    painter.drawLine(self.width() - 4, y, self.width(), y)
            inicio = self.origem_y
            fim = self.origem_y + (self.height() / max(self.zoom, 0.001))
            valor = floor(inicio / passo_unidade) * passo_unidade
            while valor <= fim + passo_unidade:
                py = int((valor - self.origem_y) * self.zoom)
                if 0 <= py <= self.height():
                    painter.drawLine(self.width() - 12, py, self.width(), py)
                    painter.save()
                    painter.translate(9, py + 2)
                    painter.rotate(-90)
                    painter.drawText(0, 0, self._formatar_valor(valor, passo_unidade))
                    painter.restore()
                valor += passo_unidade

    def _passo_principal(self) -> float:
        alvo_px = 85.0
        bruto = max(alvo_px / max(self.zoom, 0.001), 1e-6)
        base = 10 ** floor(log10(bruto))
        for mult in (1, 2, 5, 10):
            passo = base * mult
            if passo >= bruto:
                return passo
        return base * 10

    def _formatar_valor(self, valor: float, passo: float) -> str:
        if passo >= 1:
            return f"{valor:.0f}"
        dec = max(0, min(6, int(abs(floor(log10(passo))))))
        return f"{valor:.{dec}f}"


class AreaDocumentoWidget(QWidget):
    zoom_changed = Signal(float)

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.regua_h = ReguaWidget(horizontal=True)
        self.regua_v = ReguaWidget(horizontal=False)
        self.canto = QLabel("cm")
        self.canto.setAlignment(Qt.AlignCenter)
        self.canto.setStyleSheet("background:#f8f8f8; border-right:1px solid #cdd6df; border-bottom:1px solid #cdd6df; font-size:10px;")

        self.canvas = VisualizacaoCanvas(cena)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)

        layout.addWidget(self.canto, 0, 0)
        layout.addWidget(self.regua_h, 0, 1)
        layout.addWidget(self.regua_v, 1, 0)
        layout.addWidget(self.canvas, 1, 1)

    def _on_zoom_changed(self, zoom: float):
        self.regua_h.atualizar_viewport(zoom, self.canvas.origem_cena.x(), self.canvas.origem_cena.y())
        self.regua_v.atualizar_viewport(zoom, self.canvas.origem_cena.x(), self.canvas.origem_cena.y())
        self.zoom_changed.emit(zoom)
