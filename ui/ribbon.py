from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class RibbonTabBar(QTabBar):
    # noinspection PyPep8Naming
    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        return QSize(max(size.width() + 16, 92), 26)


class RibbonButton(QToolButton):
    def __init__(self, titulo: str, grande: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setText(titulo)
        self.setIcon(self._criar_icone(grande))
        self.setIconSize(QSize(20, 20) if grande else QSize(16, 16))
        self.setMinimumSize(64, 52 if grande else 40)
        self.setStyleSheet(
            """
            QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #1e1e1e;
                font-size: 10px;
                padding: 3px;
            }
            QToolButton:hover {
                background: #f5f8fd;
                border: 1px solid #cddbf0;
            }
            QToolButton:pressed {
                background: #e6eefb;
                border: 1px solid #9cb7df;
            }
            """
        )

    @staticmethod
    def _criar_icone(grande: bool):
        lado = 28 if grande else 22
        pix = QPixmap(lado, lado)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4a7fc1"))
        painter.drawRoundedRect(2, 2, lado - 4, lado - 4, 5, 5)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(6, 6, lado - 12, lado - 12, 3, 3)
        painter.end()
        return pix


class RibbonGroup(QFrame):
    def __init__(self, titulo: str, grandes: list[str], pequenos: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self.setFixedHeight(102)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 4, 6, 2)
        raiz.setSpacing(2)

        corpo = QHBoxLayout()
        corpo.setSpacing(4)
        raiz.addLayout(corpo)

        for texto in grandes:
            corpo.addWidget(RibbonButton(texto, grande=True))

        if pequenos:
            grade_wrap = QWidget()
            grade = QVBoxLayout(grade_wrap)
            grade.setContentsMargins(0, 0, 0, 0)
            grade.setSpacing(4)

            linha = None
            for i, texto in enumerate(pequenos):
                if i % 2 == 0:
                    linha = QHBoxLayout()
                    linha.setSpacing(2)
                    grade.addLayout(linha)
                linha.addWidget(RibbonButton(texto, grande=False))
            corpo.addWidget(grade_wrap)

        corpo.addStretch(1)

        rodape = QLabel(titulo)
        rodape.setAlignment(Qt.AlignCenter)
        rodape.setStyleSheet(
            "color: #505050; font-size: 9px; border-top: 1px solid #d9d9d9; padding-top: 2px;"
        )
        raiz.addWidget(rodape)

        self.setStyleSheet(
            """
            QFrame#RibbonGroup {
                background: transparent;
                border-right: 1px solid #dddddd;
            }
            """
        )


class RibbonPage(QWidget):
    def __init__(self, grupos: list[tuple[str, list[str], list[str]]], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(0)
        for titulo, grandes, pequenos in grupos:
            layout.addWidget(RibbonGroup(titulo, grandes, pequenos))
        espaco = QWidget()
        espaco.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(espaco)


class RibbonWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabbar = RibbonTabBar()
        self.paginas = QStackedWidget()
        self.tabbar.currentChanged.connect(self.paginas.setCurrentIndex)

        for nome, grupos in dados_abas().items():
            self.tabbar.addTab(nome)
            self.paginas.addWidget(RibbonPage(grupos))

        layout.addWidget(self.tabbar)
        layout.addWidget(self.paginas)


def dados_abas() -> dict[str, list[tuple[str, list[str], list[str]]]]:
    return {
        "Início": [
            ("Projeto", ["Novo", "Abrir"], ["Salvar", "Salvar como", "Importar", "Exportar"]),
            ("Edição", ["Selecionar", "Mover"], ["Copiar", "Recortar", "Colar", "Excluir"]),
        ],
        "Produção": [
            ("Moldes", ["Criar molde", "Digitalizar"], ["Linha simetria", "Bainha", "Costura", "Fio"]),
        ],
        "Marcação": [
            ("Piques", ["Inserir", "Remover"], ["Alinhar", "Substituir", "Múltiplos", "Editar"]),
        ],
        "Graduação": [
            ("Regras", ["Tabela", "Regra"], ["Aplicar", "Remover", "Copiar", "Ajustar"]),
        ],
        "Manipulação": [
            ("Geometria", ["Ponto", "Linha"], ["Curva", "Arco", "Dividir", "Unir"]),
        ],
        "Conferência": [
            ("Medições", ["Perímetro", "Distância"], ["Ângulo", "Raio", "Comparar", "Relatório"]),
        ],
        "Modelo": [
            ("Dados", ["Propriedades", "Tecidos"], ["Autor", "Variantes", "Imagens", "Biblioteca"]),
        ],
    }
