from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from canvas.cena import CenaDocumento


class VisualizacaoCanvas(QWidget):
    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.cena = cena
        self.zoom = 1.0
        self.setMinimumHeight(500)
        self.setStyleSheet("background: #fdfdfd; border: 1px solid #b7c0cc;")

    # noinspection PyPep8Naming
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.cena.grid_ativo:
            painter.setPen(QPen(QColor("#e9edf3"), 1))
            passo = 24
            for x in range(0, self.width(), passo):
                painter.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), passo):
                painter.drawLine(0, y, self.width(), y)

        painter.setPen(QPen(QColor("#98a4b4"), 2))
        painter.drawRect(40, 40, max(40, self.width() - 80), max(40, self.height() - 80))

        painter.setPen(QPen(QColor("#5c6776"), 1))
        painter.drawText(self.rect(), Qt.AlignCenter, "Área de trabalho técnica")
