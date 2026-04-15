from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QWheelEvent
from PySide6.QtWidgets import QWidget

from canvas.cena import CenaDocumento


class VisualizacaoCanvas(QWidget):
    """Canvas de fundo infinito (visualmente sem limites) e sem elementos desenhados."""

    zoom_changed = Signal(float)

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.cena = cena
        self.zoom = 1.0
        self.setMinimumSize(100, 100)
        self.setAutoFillBackground(False)

    def set_zoom(self, zoom: float):
        self.zoom = max(0.2, min(zoom, 8.0))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        delta = event.angleDelta().y()
        fator = 1.1 if delta > 0 else 0.9
        self.set_zoom(self.zoom * fator)
        event.accept()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
