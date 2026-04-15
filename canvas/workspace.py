from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QWidget

from canvas.visualizacao import VisualizacaoCanvas
from canvas.cena import CenaDocumento


class ScrollAreaSemWheel(QScrollArea):
    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        # Rolagem vertical/horizontal somente pelas barras, conforme solicitado.
        event.ignore()


class ReguaWidget(QWidget):
    def __init__(self, horizontal: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.horizontal = horizontal
        self.offset = 0
        self.zoom = 1.0
        if horizontal:
            self.setFixedHeight(20)
        else:
            self.setFixedWidth(28)

    def atualizar(self, offset: int, zoom: float):
        self.offset = offset
        self.zoom = max(0.1, zoom)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f8f8f8"))
        painter.setPen(QPen(QColor("#9aa6b2"), 1))

        pixel_step = max(20, int(50 * self.zoom))
        if self.horizontal:
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            for x in range(0, self.width(), 5):
                world_x = x + self.offset
                if world_x % pixel_step == 0:
                    painter.drawLine(x, self.height() - 10, x, self.height())
                    painter.drawText(x + 2, 10, str(int(world_x / max(self.zoom, 0.001))))
                elif world_x % max(1, pixel_step // 2) == 0:
                    painter.drawLine(x, self.height() - 6, x, self.height())
        else:
            painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
            for y in range(0, self.height(), 5):
                world_y = y + self.offset
                if world_y % pixel_step == 0:
                    painter.drawLine(self.width() - 10, y, self.width(), y)
                    painter.save()
                    painter.translate(10, y + 2)
                    painter.rotate(-90)
                    painter.drawText(0, 0, str(int(world_y / max(self.zoom, 0.001))))
                    painter.restore()
                elif world_y % max(1, pixel_step // 2) == 0:
                    painter.drawLine(self.width() - 6, y, self.width(), y)


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

        self.scroll = ScrollAreaSemWheel()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.scroll.horizontalScrollBar().valueChanged.connect(self._sync_reguas)
        self.scroll.verticalScrollBar().valueChanged.connect(self._sync_reguas)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)

        layout.addWidget(self.canto, 0, 0)
        layout.addWidget(self.regua_h, 0, 1)
        layout.addWidget(self.regua_v, 1, 0)
        layout.addWidget(self.scroll, 1, 1)

        self._sync_reguas()

    def _on_zoom_changed(self, zoom: float):
        self.zoom_changed.emit(zoom)
        self._sync_reguas()

    def _sync_reguas(self):
        self.regua_h.atualizar(self.scroll.horizontalScrollBar().value(), self.canvas.zoom)
        self.regua_v.atualizar(self.scroll.verticalScrollBar().value(), self.canvas.zoom)
