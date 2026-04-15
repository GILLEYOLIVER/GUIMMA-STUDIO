from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from canvas.cena import CenaDocumento


class VisualizacaoCanvas(QWidget):
    zoom_changed = Signal(float)

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.cena = cena
        self.zoom = 1.0
        self._base_size = QSize(cena.largura, cena.altura)
        self.setFixedSize(self._base_size)
        self.setStyleSheet("background: #050505; border: 1px solid #b7c0cc;")

    def set_zoom(self, zoom: float):
        self.zoom = max(0.2, min(zoom, 6.0))
        self.setFixedSize(int(self._base_size.width() * self.zoom), int(self._base_size.height() * self.zoom))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            fator = 1.1 if delta > 0 else 0.9
            self.set_zoom(self.zoom * fator)
            event.accept()
            return
        super().wheelEvent(event)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.cena.grid_ativo:
            painter.setPen(QPen(QColor("#1a1a1a"), 1))
            passo = max(8, int(24 * self.zoom))
            for x in range(0, self.width(), passo):
                painter.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), passo):
                painter.drawLine(0, y, self.width(), y)

        painter.setPen(QPen(QColor("#e5e5e5"), 2))
        painter.drawRect(120, 100, max(80, self.width() // 2), max(60, self.height() // 3))

        painter.setPen(QPen(QColor("#f0d000"), 2))
        painter.drawRect(self.width() // 2 + 180, self.height() // 2, 280, 210)

        painter.setPen(QPen(QColor("#8a8a8a"), 1))
        painter.drawText(self.rect(), Qt.AlignCenter, "Canvas técnico com zoom (Ctrl+Scroll)")
