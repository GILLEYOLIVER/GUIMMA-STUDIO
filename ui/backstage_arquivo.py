from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BackstageArquivoPanel(QFrame):
    arquivo_recente_clicado = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BackstagePanel")
        self.setFixedWidth(520)
        self.hide()
        self._recentes: list[str] = []
        self._settings = QSettings("GUIMMA", "GUIMMA STUDIO")

        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(28)
        sombra.setOffset(4, 4)
        sombra.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(sombra)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        menu_esquerdo = QFrame()
        menu_esquerdo.setFixedWidth(190)
        menu_esquerdo.setStyleSheet("background: #f3f3f3; border-right: 1px solid #d8dde3;")
        menu_layout = QVBoxLayout(menu_esquerdo)
        menu_layout.setContentsMargins(0, 10, 0, 10)
        menu_layout.setSpacing(1)

        titulo = QLabel("ARQUIVO")
        titulo.setStyleSheet("color: #104f90; font-size: 18px; font-weight: 800; padding: 8px 14px 14px 16px;")
        menu_layout.addWidget(titulo)

        self.botoes: dict[str, QPushButton] = {}
        itens = [
            "Novo",
            "Abrir",
            "Salvar",
            "Salvar como",
            "Modelo ▸",
            "Importar ▸",
            "Exportar ▸",
            "Plotar",
            "Imprimir",
            "Configurações ▸",
            "Ajuda",
        ]
        for item in itens:
            botao = QPushButton(item)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setMinimumHeight(30)
            botao.setMaximumHeight(30)
            botao.setStyleSheet(
                """
                QPushButton {
                    text-align: left;
                    padding-left: 16px;
                    color: #1d1d1d;
                    border: none;
                    background: transparent;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: #d9ebf7;
                }
                """
            )
            menu_layout.addWidget(botao)
            self.botoes[item] = botao
        menu_layout.addStretch(1)

        painel_direito = QFrame()
        painel_direito.setStyleSheet("background: #ffffff;")
        direito = QVBoxLayout(painel_direito)
        direito.setContentsMargins(18, 18, 18, 18)
        direito.setSpacing(12)

        cab = QLabel("Arquivos Recentes")
        cab.setStyleSheet("font-size: 19px; font-weight: 700; color: #1e1e1e;")
        direito.addWidget(cab)

        self.lista_recentes = QListWidget()
        self.lista_recentes.setMouseTracking(True)
        self.lista_recentes.setStyleSheet(
            """
            QListWidget {
                border: none;
                font-size: 14px;
                color: #1f1f1f;
                background: white;
            }
            QListWidget::item {
                padding: 5px 8px;
                border-left: 2px solid transparent;
            }
            QListWidget::item:hover {
                background: #f3f8ff;
                border-left: 2px solid #2ea3f2;
            }
            QListWidget::item:selected {
                background: #eef6ff;
                border-left: 2px solid #1f9bf0;
                color: #0f3c66;
            }
            """
        )
        self.lista_recentes.setSelectionMode(QListWidget.SingleSelection)
        self.lista_recentes.itemClicked.connect(self._ao_clicar_recente)
        direito.addWidget(self.lista_recentes)

        self.lbl_vazio = QLabel("Nenhum arquivo recente.")
        self.lbl_vazio.setStyleSheet("font-size: 13px; color: #676767;")
        direito.addWidget(self.lbl_vazio)

        self._carregar_recentes_persistidos()
        self._atualizar_recentes()
        direito.addStretch(1)

        raiz.addWidget(menu_esquerdo)
        raiz.addWidget(painel_direito)

        self.setStyleSheet("QFrame#BackstagePanel { background: white; border: 1px solid #cfd6df; }")

    def _atualizar_recentes(self):
        self.lista_recentes.clear()
        for i, caminho in enumerate(self._recentes, start=1):
            item = QListWidgetItem(f"{i}  {caminho}")
            item.setData(Qt.UserRole, caminho)
            self.lista_recentes.addItem(item)
        vazio = len(self._recentes) == 0
        self.lbl_vazio.setVisible(vazio)
        self.lista_recentes.setVisible(not vazio)

    def adicionar_recente(self, caminho: str):
        if caminho in self._recentes:
            self._recentes.remove(caminho)
        self._recentes.insert(0, caminho)
        self._recentes = self._recentes[:12]
        self._persistir_recentes()
        self._atualizar_recentes()

    def _ao_clicar_recente(self, item: QListWidgetItem):
        caminho = item.data(Qt.UserRole)
        if caminho:
            self.arquivo_recente_clicado.emit(caminho)

    def _carregar_recentes_persistidos(self):
        recentes = self._settings.value("recent_files", [], list)
        if isinstance(recentes, list):
            self._recentes = [str(c) for c in recentes][:12]

    def _persistir_recentes(self):
        self._settings.setValue("recent_files", self._recentes[:12])
