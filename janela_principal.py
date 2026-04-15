from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QMainWindow,
    QPushButton,
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
        self.titulo = titulo
        self.grande = grande
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setText(titulo)
        self.setIcon(self._criar_icone())
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

    def _criar_icone(self):
        lado = 28 if self.grande else 22
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


class BackstagePanel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BackstagePanel")
        self.setFixedWidth(520)
        self.hide()
        self._recentes: list[str] = []

        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(28)
        sombra.setOffset(4, 4)
        sombra.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(sombra)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        menu_esquerdo = QFrame()
        menu_esquerdo.setFixedWidth(180)
        menu_esquerdo.setStyleSheet("background: #f3f3f3; border-right: 1px solid #d8dde3;")
        menu_layout = QVBoxLayout(menu_esquerdo)
        menu_layout.setContentsMargins(0, 10, 0, 10)
        menu_layout.setSpacing(2)

        titulo = QLabel("ARQUIVO")
        titulo.setStyleSheet("color: #104f90; font-size: 18px; font-weight: 800; padding: 8px 14px 14px 16px;")
        menu_layout.addWidget(titulo)

        self.botoes: dict[str, QPushButton] = {}
        itens = [
            "Novo",
            "Abrir",
            "Fechar",
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
            botao.setMinimumHeight(34)
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

        cab = QLabel("Documentos Recentes")
        cab.setStyleSheet("font-size: 19px; font-weight: 700; color: #1e1e1e;")
        direito.addWidget(cab)

        self.lista_recentes = QListWidget()
        self.lista_recentes.setStyleSheet(
            "QListWidget { border: none; font-size: 14px; color: #1f1f1f; background: white; }"
        )
        self.lista_recentes.setSelectionMode(QListWidget.NoSelection)
        direito.addWidget(self.lista_recentes)

        self.lbl_vazio = QLabel("Nenhum documento recente.")
        self.lbl_vazio.setStyleSheet("font-size: 13px; color: #676767;")
        direito.addWidget(self.lbl_vazio)
        self._atualizar_recentes()
        direito.addStretch(1)

        raiz.addWidget(menu_esquerdo)
        raiz.addWidget(painel_direito)

        self.setStyleSheet(
            """
            QFrame#BackstagePanel { background: white; border: 1px solid #cfd6df; border-radius: 0px; }
            """
        )

    def _atualizar_recentes(self):
        self.lista_recentes.clear()
        for i, caminho in enumerate(self._recentes, start=1):
            self.lista_recentes.addItem(QListWidgetItem(f"{i}  {caminho}"))
        vazio = len(self._recentes) == 0
        self.lbl_vazio.setVisible(vazio)
        self.lista_recentes.setVisible(not vazio)

    def adicionar_recente(self, caminho: str):
        nome = caminho.split("/")[-1].split("\\")[-1]
        if nome in self._recentes:
            self._recentes.remove(nome)
        self._recentes.insert(0, nome)
        self._recentes = self._recentes[:12]
        self._atualizar_recentes()


class GuimmaStudioMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GUIMMA STUDIO")
        self.resize(1550, 920)
        self._configurar_interface()

    def _configurar_interface(self):
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        topo = self._criar_topo()
        raiz.addWidget(topo)
        raiz.addWidget(self._criar_area_documento())
        raiz.addWidget(self._criar_status())

        self.setStyleSheet(
            """
            QMainWindow { background: #e9edf2; }
            QWidget#TopHeader { background: #efefef; border-bottom: 1px solid #cfd6df; }
            QWidget#RibbonHost { background: #efefef; border-bottom: 1px solid #d8dce3; }
            QTabBar::tab {
                background: transparent;
                color: #101010;
                padding: 4px 10px;
                margin: 0 1px;
                border: none;
                font-size: 10px;
            }
            QTabBar::tab:selected {
                background: #0f7cb5;
                color: #ffffff;
                border: 1px solid #0b6898;
            }
            QTabBar::tab:hover { background: #dcecf7; }
            """
        )

    def _criar_topo(self):
        topo = QWidget()
        topo.setObjectName("TopHeader")
        layout = QVBoxLayout(topo)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        barra_superior = QWidget()
        sup = QHBoxLayout(barra_superior)
        sup.setContentsMargins(6, 2, 6, 2)
        sup.setSpacing(6)

        self.botao_arquivo = QPushButton("ARQUIVO")
        self.botao_arquivo.setCursor(Qt.PointingHandCursor)
        self.botao_arquivo.setFixedSize(84, 24)
        self.botao_arquivo.clicked.connect(self._alternar_backstage)
        self.botao_arquivo.setStyleSheet(
            """
            QPushButton {
                background: #0078b5;
                color: white;
                border: 1px solid #026da2;
                border-radius: 2px;
                font-size: 10px;
                font-weight: 700;
            }
            QPushButton:hover { background: #0682c2; }
            QPushButton:pressed { background: #016595; }
            """
        )
        sup.addWidget(self.botao_arquivo, 0, Qt.AlignLeft)

        titulo = QLabel("GUIMMA STUDIO")
        titulo.setStyleSheet("font-size: 13px; font-weight: 700; color: #202020;")
        sup.addWidget(titulo)
        sup.addStretch(1)
        sup.addWidget(QLabel("VISÃO • OPÇÕES • JANELAS"))
        layout.addWidget(barra_superior)
        self.barra_superior = barra_superior

        host = QWidget()
        host.setObjectName("RibbonHost")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        self.tabbar = RibbonTabBar()
        self.paginas = QStackedWidget()
        self.tabbar.currentChanged.connect(self.paginas.setCurrentIndex)
        self.tabbar.currentChanged.connect(lambda _: self.backstage.hide() if hasattr(self, "backstage") else None)

        abas = self._dados_abas()
        for nome, grupos in abas.items():
            self.tabbar.addTab(nome)
            self.paginas.addWidget(RibbonPage(grupos))
        self.tabbar.setCurrentIndex(0)
        self.paginas.setCurrentIndex(0)

        host_layout.addWidget(self.tabbar)
        host_layout.addWidget(self.paginas)
        layout.addWidget(host)

        self.backstage = BackstagePanel(self)
        self.backstage.botoes["Abrir"].clicked.connect(self._abrir_documento_real)
        self.backstage.move(0, self._topo_backstage())
        self.backstage.raise_()

        return topo

    # noinspection PyPep8Naming
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "backstage"):
            y = self._topo_backstage()
            self.backstage.setFixedHeight(max(220, self.height() - y - 28))
            self.backstage.move(0, y)

    def _alternar_backstage(self):
        self.tabbar.setCurrentIndex(0)
        self.backstage.setVisible(not self.backstage.isVisible())
        if self.backstage.isVisible():
            self.backstage.raise_()

    # noinspection PyPep8Naming
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.backstage.isVisible() and event.position().x() > self.backstage.width():
            self.backstage.hide()

    def _topo_backstage(self) -> int:
        return self.barra_superior.height() + self.tabbar.height()

    def _abrir_documento_real(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir documento",
            "",
            "Arquivos de molde (*.adsx *.dxf *.plt);;Todos os arquivos (*.*)",
        )
        if caminho:
            self.backstage.adicionar_recente(caminho)

    @staticmethod
    def _dados_abas():
        return {
            "Arquivo": [
                ("Arquivo", ["Novo", "Abrir"], ["Fechar", "Salvar", "Salvar como", "Imprimir"]),
            ],
            "Início": [
                ("Desenho", ["Cor", "Selecionar"], ["Colar", "Excluir", "Recortar", "Copiar"]),
                ("Restauração", ["Selecionar moldes"], ["Ponto de restauração", "Restaurar", "Restaura cópia", "Abrir software"]),
                ("3D", ["Abrir"], []),
            ],
            "Construção": [
                ("Retas", ["Reta", "Retângulo"], ["Por ângulo", "Estender reta", "Estender duas retas", "Estender até elemento"]),
                ("Curvas", ["Curva", "Espiral e curvas"], ["Dividir curva", "Cadastrar curva", "Pré-definida", "Editar pontos de curva"]),
                ("Pontos", ["Por coordenada", "Por interseção"], ["No centro do arco", "No perímetro", "Por distância"]),
                ("Arcos", ["Por raio"], []),
            ],
            "Produção": [
                ("Definir moldes", ["Criar molde", "Digitalizar"], ["Sentido do fio", "Encolhimento", "Linha simetria", "Bainha"]),
                ("Costura", ["Remover costura", "Trocar costura/linha"], ["Converter em costura"]),
                ("Pregas e pences", ["Pregas", "Pence no contorno"], ["Pence interna", "Fechar pence", "Transferir pence"]),
                ("Cortar e unir", ["Múltiplas pences"], ["Cortar", "Unir", "Remover região"]),
            ],
            "Marcações": [
                ("Piques", ["Inserir", "Remover pique"], ["Múltiplos", "Alinhar", "Substituir", "Alterar piques"]),
                ("Linhas auxiliares", ["Inserir ou remover"], []),
                ("Estampa digital", ["Corrida", "Localizada"], []),
            ],
            "Graduação": [
                ("Graduar", ["Tabela", "Mouse"], ["Tangente", "Regras", "Criar regra", "Remover graduação"]),
                ("Manipular graduação", ["Unir", "Agrupar"], ["Deduzir", "Copiar graduação", "Ajustar", "Graduar curva"]),
            ],
            "Manipulação": [
                ("Redefinir", ["Manipular pontos", "Mover"], ["Mover ponto", "Redefinir perímetro", "Dividir elementos", "Girar"]),
                ("Cerca", ["Definir cerca"], ["Mover cerca"]),
                ("Manipular molde", ["Inserir ponto", "Excluir ponto"], ["Transformar em elementos", "Alinhar", "Copiar ou trocar elemento", "Arredondar ou chanfrar"]),
            ],
            "Conferência": [
                ("Conferir perímetro", ["Conferir", "Conferir múltiplos"], ["Contro. curvas", "Cota perímetro", "Perímetro", "Comparar perímetros"]),
                ("Distância", ["Cota distância"], ["Horizontal/Vertical", "Ângulo", "Raio", "Comparar distância"]),
            ],
            "Modelo": [
                ("Informações", ["Propriedades", "Tecidos"], ["Autor", "Informações dos moldes", "Variantes"]),
                ("Operações", ["Relacionamento piques", "Imagens"], ["Localizar modelos", "Substituir", "Editar"]),
                ("Medida/Grupos", ["Criar"], []),
            ],
            "Usuário 1": [
                ("Ferramentas", ["Retângulo", "Curva"], ["Editar pontos de curva", "Por coordenada", "Inserir texto", "Extrair molde"]),
                ("Operações", ["Cortar", "Unir"], ["Inserir pique", "Tabela", "Modificar"]),
                ("Conferência", ["Conferir", "Perímetro"], ["Distância", "Comparar distância"]),
            ],
        }

    @staticmethod
    def _criar_area_documento():
        area = QWidget()
        area.setStyleSheet("background: #f2f3f5;")
        layout = QVBoxLayout(area)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        quadro = QFrame()
        quadro.setStyleSheet("background: #000000; border: 1px solid #9da5b1; border-radius: 0px;")
        ql = QVBoxLayout(quadro)
        ql.setContentsMargins(2, 2, 2, 2)
        ql.setSpacing(2)

        faixa = QFrame()
        faixa.setFixedHeight(24)
        faixa.setStyleSheet("background: #f4f4f4; border: 1px solid #d7dbe1; border-radius: 0px;")
        fl = QHBoxLayout(faixa)
        fl.setContentsMargins(10, 0, 10, 0)
        fl.addWidget(QLabel("ENCOMENDA 3 (3) NOVO TEC.adsx    ✕     GIL 130 2.adsx    ✕     GIL 144.adsx"))
        fl.addStretch(1)
        fl.addWidget(QLabel("100%"))
        ql.addWidget(faixa)

        regua_superior = QFrame()
        regua_superior.setFixedHeight(22)
        regua_superior.setStyleSheet("background: #f6f7f9; border: 1px solid #c8ced8; color: #3b3b3b;")
        rl_top = QHBoxLayout(regua_superior)
        rl_top.setContentsMargins(4, 0, 4, 0)
        rl_top.addWidget(QLabel("0      10      20      30      40      50      60      70      80      90      100"))
        rl_top.addStretch(1)
        ql.addWidget(regua_superior)

        corpo_canvas = QHBoxLayout()
        corpo_canvas.setSpacing(2)

        regua_lateral = QFrame()
        regua_lateral.setFixedWidth(22)
        regua_lateral.setStyleSheet("background: #f6f7f9; border: 1px solid #c8ced8; color: #3b3b3b;")
        rl_left = QVBoxLayout(regua_lateral)
        rl_left.setContentsMargins(2, 4, 2, 4)
        rl_left.addWidget(QLabel("0"))
        rl_left.addWidget(QLabel("10"))
        rl_left.addWidget(QLabel("20"))
        rl_left.addWidget(QLabel("30"))
        rl_left.addStretch(1)
        corpo_canvas.addWidget(regua_lateral)

        tela = QLabel("ÁREA CANVAS")
        tela.setAlignment(Qt.AlignCenter)
        tela.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tela.setMinimumHeight(620)
        tela.setStyleSheet(
            "background: #000000; border: 1px solid #a8aeb8; color: #4b4b4b; font-size: 16px; font-weight: 700;"
        )
        corpo_canvas.addWidget(tela, 1)
        ql.addLayout(corpo_canvas, 1)

        layout.addWidget(quadro)
        return area

    @staticmethod
    def _criar_status():
        barra = QFrame()
        barra.setFixedHeight(28)
        barra.setStyleSheet("background: #e7ebf1; border-top: 1px solid #cfd6df;")
        l = QHBoxLayout(barra)
        l.setContentsMargins(10, 0, 10, 0)
        l.addWidget(QLabel("Pronto"))
        l.addStretch(1)
        l.addWidget(QLabel("Snap Ativo"))
        l.addSpacing(12)
        l.addWidget(QLabel("Escala 100%"))
        return barra


def executar_app() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    janela = GuimmaStudioMainWindow()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(executar_app())
