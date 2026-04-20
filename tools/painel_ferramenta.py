from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class PainelFerramentaBasico(QFrame):
    """Painel auxiliar padrão para ferramentas sem UI própria."""

    def __init__(self, titulo: str, descricao: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PainelFerramentaBasico")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setFixedWidth(280)
        self._margem_canvas = 12
        self._drag_offset_local: QPoint | None = None

        self.setStyleSheet(
            """
            QFrame#PainelFerramentaBasico {
                background: #f5f7fa;
                border: 1px solid #c8d2dc;
                border-radius: 10px;
                color: #16202a;
            }
            QLabel#titulo {
                color: #0f4f86;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#descricao {
                color: #4c5d6f;
                font-size: 11px;
            }
            QLabel#status {
                background: #ffffff;
                border: 1px solid #d6dee6;
                border-radius: 6px;
                padding: 6px;
                color: #1f2d3a;
                font-size: 11px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        cabecalho = QHBoxLayout()
        cabecalho.setContentsMargins(0, 0, 0, 0)
        titulo_lbl = QLabel(titulo)
        titulo_lbl.setObjectName("titulo")
        cabecalho.addWidget(titulo_lbl, 1)
        layout.addLayout(cabecalho)

        descricao_lbl = QLabel(descricao)
        descricao_lbl.setObjectName("descricao")
        descricao_lbl.setWordWrap(True)
        layout.addWidget(descricao_lbl)

        self.status_lbl = QLabel("Ferramenta pronta.")
        self.status_lbl.setObjectName("status")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        layout.addWidget(self.status_lbl)

    def atualizar_status(self, texto: str):
        self.status_lbl.setText(texto)

    def _retangulo_util_canvas(self) -> QRect:
        parent = self.parentWidget()
        if parent is None:
            return QRect(0, 0, max(self.width(), 1), max(self.height(), 1))
        return parent.rect().adjusted(self._margem_canvas, self._margem_canvas, -self._margem_canvas, -self._margem_canvas)

    def _ajustar_para_canvas(self, pos: QPoint) -> QPoint:
        area = self._retangulo_util_canvas()
        largura_util = max(0, area.width() - self.width())
        altura_util = max(0, area.height() - self.height())
        x = area.left() + max(0, min(pos.x() - area.left(), largura_util))
        y = area.top() + max(0, min(pos.y() - area.top(), altura_util))
        return QPoint(x, y)

    def reposicionar_no_canto_superior_direito(self):
        parent = self.parentWidget()
        if parent is not None and hasattr(parent, "calcular_posicao_painel_auxiliar"):
            destino = parent.calcular_posicao_painel_auxiliar(self.width(), self.height(), abaixo_coordenadas=True)
            self.move(self._ajustar_para_canvas(destino))
            return
        self.move(self._ajustar_para_canvas(QPoint(10_000, 0)))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.position().y() <= 56:
            self._drag_offset_local = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset_local is not None and event.buttons() & Qt.LeftButton:
            destino = self.pos() + event.position().toPoint() - self._drag_offset_local
            self.move(self._ajustar_para_canvas(destino))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._drag_offset_local is not None:
            self._drag_offset_local = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
