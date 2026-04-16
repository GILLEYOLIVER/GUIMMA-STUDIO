from __future__ import annotations

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
        if horizontal:
            self.setFixedHeight(20)
        else:
            self.setFixedWidth(28)

    def atualizar_zoom(self, zoom: float):
        self.zoom = max(0.1, zoom)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f2f2f2"))
        painter.setPen(QPen(QColor("#222222"), 1))

        pixel_step = max(25, int(40 * self.zoom))
        if self.horizontal:
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            for x in range(0, self.width(), 5):
                if x % pixel_step == 0:
                    painter.drawLine(x, self.height() - 12, x, self.height())
                    painter.drawText(x + 2, 9, str(int(x / max(self.zoom, 0.001))))
                elif x % max(1, pixel_step // 2) == 0:
                    painter.drawLine(x, self.height() - 8, x, self.height())
                else:
                    painter.drawLine(x, self.height() - 4, x, self.height())
        else:
            painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
            for y in range(0, self.height(), 5):
                if y % pixel_step == 0:
                    painter.drawLine(self.width() - 12, y, self.width(), y)
                    painter.save()
                    painter.translate(9, y + 2)
                    painter.rotate(-90)
                    painter.drawText(0, 0, str(int(y / max(self.zoom, 0.001))))
                    painter.restore()
                elif y % max(1, pixel_step // 2) == 0:
                    painter.drawLine(self.width() - 8, y, self.width(), y)
                else:
                    painter.drawLine(self.width() - 4, y, self.width(), y)


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
        self.regua_h.atualizar_zoom(zoom)
        self.regua_v.atualizar_zoom(zoom)
        self.zoom_changed.emit(zoom)
