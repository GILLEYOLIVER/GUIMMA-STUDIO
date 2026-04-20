from __future__ import annotations

from math import atan2, degrees, sqrt

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class PainelCoordenadas(QFrame):
    desfazer_ponto = Signal()
    aplicar = Signal(dict)
    alternado = Signal(bool)
    posicao_alterada = Signal(int, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PainelCoordenadas")
        self.setFixedSize(300, 120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(4)

        titulo = QLabel("(cm) Coordenadas")
        titulo.setStyleSheet("font-size: 10px; color: #7c7c7c;")
        topo.addWidget(titulo, 1)
        btn_fechar = QPushButton("✕")
        btn_fechar.setFixedSize(16, 16)
        btn_fechar.clicked.connect(lambda: self._alternar_visibilidade(False))
        topo.addWidget(btn_fechar, 0, Qt.AlignRight)
        layout.addLayout(topo)

        grade = QGridLayout()
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setHorizontalSpacing(6)
        grade.setVerticalSpacing(2)
        self.dx_input = QLineEdit()
        self.dy_input = QLineEdit()
        self.a_input = QLineEdit()
        self.d_input = QLineEdit()
        for field in (self.dx_input, self.dy_input, self.a_input, self.d_input):
            field.setFixedHeight(20)
            field.setStyleSheet("background:#f2f2f2; border:1px solid #a2a2a2;")
        self.dx_preview = QLabel("0")
        self.dy_preview = QLabel("0")
        self.a_preview = QLabel("0°")
        self.d_preview = QLabel("0")
        for lbl in (self.dx_preview, self.dy_preview, self.a_preview, self.d_preview):
            lbl.setStyleSheet("font-size:10px; color:#7c7c7c;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grade.addWidget(QLabel("Dx:"), 0, 0)
        grade.addWidget(self.dx_input, 0, 1)
        grade.addWidget(self.dx_preview, 0, 2)
        grade.addWidget(QLabel("Ângulo:"), 0, 3)
        grade.addWidget(self.a_input, 0, 4)
        grade.addWidget(self.a_preview, 0, 5)
        grade.addWidget(QLabel("Dy:"), 1, 0)
        grade.addWidget(self.dy_input, 1, 1)
        grade.addWidget(self.dy_preview, 1, 2)
        grade.addWidget(QLabel("Distância:"), 1, 3)
        grade.addWidget(self.d_input, 1, 4)
        grade.addWidget(self.d_preview, 1, 5)
        layout.addLayout(grade)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        botao_desfazer = QPushButton("Desfaz ponto")
        botao_desfazer.setFixedHeight(22)
        botao_desfazer.clicked.connect(self.desfazer_ponto.emit)
        row.addWidget(botao_desfazer)
        botao_limpar = QPushButton("Limpar")
        botao_limpar.setFixedHeight(22)
        botao_limpar.clicked.connect(self._limpar)
        row.addWidget(botao_limpar)
        botao_aplicar = QPushButton("Aplicar")
        botao_aplicar.setFixedHeight(22)
        botao_aplicar.clicked.connect(self._emitir_aplicar)
        row.addWidget(botao_aplicar)
        layout.addLayout(row)
        self._offset_arraste: QPointF | None = None

        self.setStyleSheet(
            """
            QFrame#PainelCoordenadas {
                background: #ebebeb;
                border: 1px solid #9a9a9a;
                border-radius: 8px;
                color: #1f1f1f;
            }
            QPushButton {
                background: #f6f6f6;
                border: 1px solid #9b9b9b;
                font-size: 10px;
                font-weight: 600;
                color: #111111;
            }
            QPushButton:hover { background: #ffffff; }
            QLabel { color: #1f1f1f; }
            QLineEdit { color: #1a1a1a; selection-background-color: #0b8dd1; }
            """
        )

    def _alternar_visibilidade(self, visivel: bool):
        if visivel:
            self.show()
        else:
            self.hide()
        self.alternado.emit(visivel)

    def definir_visivel(self, visivel: bool):
        self._alternar_visibilidade(visivel)

    def _limpar(self):
        for field in (self.dx_input, self.dy_input, self.a_input, self.d_input):
            field.clear()

    def _parse(self, txt: str) -> float | None:
        txt = txt.strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            return None

    def _emitir_aplicar(self):
        self.aplicar.emit(
            {
                "dx": self._parse(self.dx_input.text()),
                "dy": self._parse(self.dy_input.text()),
                "a": self._parse(self.a_input.text()),
                "d": self._parse(self.d_input.text()),
            }
        )

    def atualizar_preview(self, origem: QPointF | None, destino: QPointF | None):
        if not origem or not destino:
            self.dx_preview.setText("0")
            self.dy_preview.setText("0")
            self.a_preview.setText("0°")
            self.d_preview.setText("0")
            return
        dx = destino.x() - origem.x()
        dy = destino.y() - origem.y()
        ang = degrees(atan2(-dy, dx)) % 360.0
        dist = sqrt(dx * dx + dy * dy)
        self.dx_preview.setText(f"{dx:.2f}")
        self.dy_preview.setText(f"{dy:.2f}")
        self.a_preview.setText(f"{ang:.0f}°")
        self.d_preview.setText(f"{dist:.2f}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._offset_arraste = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._offset_arraste is not None and event.buttons() & Qt.LeftButton:
            destino = self.mapToParent(event.position().toPoint() - self._offset_arraste.toPoint())
            self.move(destino)
            self.posicao_alterada.emit(self.x(), self.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._offset_arraste = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
