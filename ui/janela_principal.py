from __future__ import annotations

from importlib import import_module
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from canvas.cena import CenaDocumento
from canvas.workspace import AreaDocumentoWidget
from config import EXTENSAO_PROJETO
from core.projeto import Projeto
from formats.gs_project import GSProjectIO
from ui.backstage_arquivo import BackstageArquivoPanel
from ui.ribbon import RibbonWidget


class GuimmaStudioMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.projeto_atual = Projeto()
        self._arquivo_atual: Path | None = None
        self.setWindowTitle("GUIMMA STUDIO")
        self.resize(1700, 980)
        self._configurar_interface()

    def _configurar_interface(self):
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        raiz.addWidget(self._criar_topo())
        raiz.addWidget(self._criar_area_documento(), 1)
        raiz.addWidget(self._criar_status())

        self.setStyleSheet(
            """
            QMainWindow { background: #eef2f6; }
            QTabBar::tab {
                background: #f6f7f9;
                color: #101010;
                border: 1px solid #d7dde5;
                padding: 6px 18px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0b5f9e;
                border-bottom: 2px solid #0b8dd1;
            }
            QTabBar::tab:hover { background: #ecf4fb; }
            """
        )

    def _criar_topo(self) -> QWidget:
        topo = QWidget()
        layout = QVBoxLayout(topo)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        barra_superior = QWidget()
        sup = QHBoxLayout(barra_superior)
        sup.setContentsMargins(6, 2, 6, 1)
        sup.setSpacing(6)

        self.botao_arquivo = QPushButton("ARQUIVO")
        self.botao_arquivo.setCursor(Qt.PointingHandCursor)
        self.botao_arquivo.setFixedSize(100, 28)
        self.botao_arquivo.clicked.connect(self._alternar_backstage)
        self.botao_arquivo.setStyleSheet("background:#0b7fb8;color:white;font-weight:700;")
        sup.addWidget(self.botao_arquivo, 0, Qt.AlignLeft)

        sup.addStretch(1)
        sup.addWidget(QLabel("VISÃO • OPÇÕES • JANELAS"))
        layout.addWidget(barra_superior)
        self.barra_superior = barra_superior

        self.ribbon = RibbonWidget()
        self.ribbon.tabbar.currentChanged.connect(lambda _: self.backstage.hide())
        self.ribbon.tool_selected.connect(self._abrir_pagina_ferramenta)
        layout.addWidget(self.ribbon)

        self.backstage = BackstageArquivoPanel(self)
        self.backstage.botoes["Novo"].clicked.connect(self._novo_projeto)
        self.backstage.botoes["Abrir"].clicked.connect(self._abrir_projeto)
        self.backstage.botoes["Salvar"].clicked.connect(self._salvar_projeto)
        self.backstage.botoes["Salvar como"].clicked.connect(self._salvar_projeto_como)

        return topo

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        y = self._topo_backstage()
        self.backstage.setFixedHeight(max(220, self.height() - y - 28))
        self.backstage.move(0, y)

    def _alternar_backstage(self):
        self.backstage.setVisible(not self.backstage.isVisible())
        if self.backstage.isVisible():
            self.backstage.raise_()

    def mousePressEvent(self, event):  # noqa: N802
        super().mousePressEvent(event)
        if self.backstage.isVisible() and event.position().x() > self.backstage.width():
            self.backstage.hide()

    def _topo_backstage(self) -> int:
        return self.barra_superior.height() + self.ribbon.tabbar.height()

    def _abrir_pagina_ferramenta(self, tool_id: str):
        tool_def = self.ribbon.tool_def(tool_id)
        if not tool_def:
            self.lbl_status.setText(f"Ferramenta não encontrada: {tool_id}")
            return

        module_name = tool_def.module.replace("/", ".").replace(".py", "")
        try:
            module = import_module(module_name)
            tool_cls = getattr(module, tool_def.class_name)
            tool = tool_cls()
            msg = tool.ativar()
            self.lbl_status.setText(msg)
        except Exception as exc:  # pragma: no cover - fallback de carregamento
            self.lbl_status.setText(f"Falha ao abrir {tool_def.title}: {exc}")

    def _novo_projeto(self):
        self.projeto_atual = Projeto()
        self._arquivo_atual = None
        self._atualizar_titulo()
        self.backstage.hide()

    def _abrir_projeto(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Abrir projeto", "", f"Projeto GUIMMA (*{EXTENSAO_PROJETO});;Todos (*.*)")
        if caminho:
            self.projeto_atual = GSProjectIO.abrir(caminho)
            self._arquivo_atual = Path(caminho)
            self.backstage.adicionar_recente(caminho)
            self._atualizar_titulo()
            self.backstage.hide()

    def _salvar_projeto(self):
        if self._arquivo_atual is None:
            self._salvar_projeto_como()
            return
        GSProjectIO.salvar(self.projeto_atual, self._arquivo_atual)
        self.backstage.adicionar_recente(str(self._arquivo_atual))
        self._atualizar_titulo()

    def _salvar_projeto_como(self):
        caminho, _ = QFileDialog.getSaveFileName(self, "Salvar projeto", f"novo_projeto{EXTENSAO_PROJETO}", f"Projeto GUIMMA (*{EXTENSAO_PROJETO})")
        if caminho:
            destino = Path(caminho)
            if destino.suffix.lower() != EXTENSAO_PROJETO:
                destino = destino.with_suffix(EXTENSAO_PROJETO)
            GSProjectIO.salvar(self.projeto_atual, destino)
            self._arquivo_atual = destino
            self.backstage.adicionar_recente(str(destino))
            self._atualizar_titulo()
            self.backstage.hide()

    def _atualizar_titulo(self):
        sufixo = self._arquivo_atual.name if self._arquivo_atual else "sem arquivo"
        self.setWindowTitle(f"GUIMMA STUDIO — {self.projeto_atual.nome} ({sufixo})")

    def _criar_area_documento(self) -> QWidget:
        area = QWidget()
        area.setStyleSheet("background: #eceff3;")
        layout = QVBoxLayout(area)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        faixa = QFrame()
        faixa.setFixedHeight(28)
        faixa.setStyleSheet("background: #f9f9f9; border: 1px solid #d7dbe1;")
        fl = QHBoxLayout(faixa)
        fl.setContentsMargins(10, 0, 10, 0)
        fl.addWidget(QLabel("ENCOMENDA 3  (3) NOVO TEC.adsx"))
        fl.addStretch(1)

        self.lbl_zoom = QLabel("100%")
        fl.addWidget(self.lbl_zoom)
        layout.addWidget(faixa)

        self.area_documento = AreaDocumentoWidget(CenaDocumento())
        self.area_documento.zoom_changed.connect(lambda z: self.lbl_zoom.setText(f"{int(z * 100)}%"))
        layout.addWidget(self.area_documento, 1)
        return area

    def _criar_status(self) -> QFrame:
        barra = QFrame()
        barra.setFixedHeight(28)
        barra.setStyleSheet("background: #0b88b6; border-top: 1px solid #0a7aa2; color: white;")
        l = QHBoxLayout(barra)
        l.setContentsMargins(10, 0, 10, 0)
        self.lbl_status = QLabel("Pronto")
        l.addWidget(self.lbl_status)
        l.addStretch(1)
        l.addWidget(QLabel("Snap ativo"))
        l.addSpacing(12)
        l.addWidget(QLabel("Escala 100%"))
        return barra
