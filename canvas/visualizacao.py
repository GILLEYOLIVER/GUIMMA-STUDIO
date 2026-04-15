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
        self.setStyleSheet("background: #000000; border: 1px solid #2e2e2e;")

    def set_zoom(self, zoom: float):
        self.zoom = max(0.2, min(zoom, 6.0))
        self.setFixedSize(int(self._base_size.width() * self.zoom), int(self._base_size.height() * self.zoom))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        # Zoom direto no scroll do mouse (sem Ctrl), conforme solicitado.
        delta = event.angleDelta().y()
        fator = 1.1 if delta > 0 else 0.9
        self.set_zoom(self.zoom * fator)
        event.accept()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Canvas deve ficar apenas negro (sem quadriculado).
        painter.fillRect(self.rect(), QColor("#000000"))

        painter.setPen(QPen(QColor("#f0f0f0"), 2))
        painter.drawRect(120, 100, max(80, self.width() // 2), max(60, self.height() // 3))

        painter.setPen(QPen(QColor("#f0d000"), 2))
        painter.drawRect(self.width() // 2 + 180, self.height() // 2, 280, 210)

        painter.setPen(QPen(QColor("#8a8a8a"), 1))
        painter.drawText(self.rect(), Qt.AlignCenter, "Canvas técnico")
