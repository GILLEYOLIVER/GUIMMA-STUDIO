from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import ICONS_DIR


@dataclass(slots=True)
class ToolDef:
    tool_id: str
    title: str
    module: str
    class_name: str
    icon: str


@dataclass(slots=True)
class GroupDef:
    title: str
    tools: list[str]


@dataclass(slots=True)
class TabDef:
    tab_id: str
    title: str
    groups: list[GroupDef]


class RibbonTabBar(QTabBar):
    def tabSizeHint(self, index):  # noqa: N802
        size = super().tabSizeHint(index)
        return QSize(max(size.width() + 8, 56), 26)


class RibbonButton(QToolButton):
    acionada = Signal(str)

    def __init__(self, ferramenta: ToolDef, compacto: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.ferramenta = ferramenta
        self.setCursor(Qt.PointingHandCursor)
        self.setText(ferramenta.title)
        self.setIcon(_carregar_icone(ferramenta.icon))
        self.clicked.connect(lambda: self.acionada.emit(self.ferramenta.tool_id))

        if compacto:
            self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.setIconSize(QSize(14, 14))
            self.setFixedSize(132, 22)
            self.setStyleSheet(
                """
                QToolButton {
                    text-align: left;
                    background: transparent;
                    border: 1px solid transparent;
                    color: #1e1e1e;
                    font-size: 10px;
                    padding: 0 2px;
                }
                QToolButton:hover { background: #f5f8fd; border: 1px solid #cddbf0; }
                QToolButton:pressed { background: #e6eefb; border: 1px solid #9cb7df; }
                """
            )
            return

        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(20, 20))
        self.setMinimumSize(64, 54)
        self.setStyleSheet(
            """
            QToolButton {
                background: #ffffff;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #1e1e1e;
                font-size: 10px;
                padding: 3px;
            }
            QToolButton:hover { background: #f5f8fd; border: 1px solid #cddbf0; }
            QToolButton:pressed { background: #e6eefb; border: 1px solid #9cb7df; }
            """
        )


class ColorControlWidget(QFrame):
    estilo_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ColorControlWidget")
        self._cor = "#ff5a00"
        self._estilo = "solid"
        self._espessura = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(2)

        self.btn_cor = QPushButton()
        self.btn_cor.setFixedSize(30, 30)
        self.btn_cor.setCursor(Qt.PointingHandCursor)
        self.btn_cor.clicked.connect(self._selecionar_cor)
        topo.addWidget(self.btn_cor)

        coluna_setas = QVBoxLayout()
        coluna_setas.setContentsMargins(0, 0, 0, 0)
        coluna_setas.setSpacing(2)

        self.cmb_estilo = QComboBox()
        self.cmb_estilo.setFixedSize(18, 14)
        self.cmb_estilo.addItem("", "solid")
        self.cmb_estilo.addItem("", "dash")
        self.cmb_estilo.addItem("", "dot")
        self.cmb_estilo.currentIndexChanged.connect(self._on_estilo_changed)
        coluna_setas.addWidget(self.cmb_estilo)

        self.cmb_espessura = QComboBox()
        self.cmb_espessura.setFixedSize(18, 14)
        for valor in (1, 2, 3, 4, 5, 6):
            self.cmb_espessura.addItem("", float(valor))
        self.cmb_espessura.currentIndexChanged.connect(self._on_espessura_changed)
        coluna_setas.addWidget(self.cmb_espessura)

        topo.addLayout(coluna_setas)
        layout.addLayout(topo)

        lbl = QLabel("Cor")
        lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lbl.setStyleSheet("font-size: 9px; color:#1e1e1e; padding-left:2px;")
        layout.addWidget(lbl)
        self.setFixedSize(56, 58)
        self.setStyleSheet(
            """
            QFrame#ColorControlWidget { background:#ffffff; border:1px solid transparent; }
            QComboBox { border:1px solid #d1d7de; background:#f8fafc; padding:0; }
            QComboBox::drop-down { border:none; width:16px; }
            QComboBox::down-arrow { image: none; border-left:4px solid transparent; border-right:4px solid transparent; border-top:5px solid #2f4f6f; margin-right:2px; }
            """
        )
        self._atualizar_preview_cor()

    def _on_estilo_changed(self):
        self._estilo = str(self.cmb_estilo.currentData() or "solid")
        self.estilo_changed.emit(self.valor())

    def _on_espessura_changed(self):
        self._espessura = float(self.cmb_espessura.currentData() or 1.0)
        self.estilo_changed.emit(self.valor())

    def _selecionar_cor(self):
        cor = QColorDialog.getColor(QColor(self._cor), self, "Selecionar cor da linha")
        if not cor.isValid():
            return
        self._cor = cor.name()
        self._atualizar_preview_cor()
        self.estilo_changed.emit(self.valor())

    def _atualizar_preview_cor(self):
        self.btn_cor.setStyleSheet(
            f"QPushButton {{ background:{self._cor}; border:1px solid #6b7480; }} QPushButton:hover {{ border:1px solid #1f5f99; }}"
        )

    def valor(self) -> dict:
        return {"cor": self._cor, "estilo": self._estilo, "espessura": self._espessura}


class RibbonGroup(QFrame):
    tool_selected = Signal(str)
    estilo_changed = Signal(dict)

    def __init__(self, titulo: str, tools: list[ToolDef], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self.setFixedHeight(102)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 4, 6, 2)
        raiz.setSpacing(2)

        if len(tools) > 3:
            corpo = QGridLayout()
            corpo.setHorizontalSpacing(4)
            corpo.setVerticalSpacing(1)
            for index, tool in enumerate(tools):
                botao = RibbonButton(tool, compacto=True)
                botao.acionada.connect(self.tool_selected.emit)
                linha = index % 3
                coluna = index // 3
                corpo.addWidget(botao, linha, coluna)
            if len(tools) < 6:
                for linha in range(len(tools), 3):
                    spacer = QWidget()
                    spacer.setFixedSize(132, 22)
                    corpo.addWidget(spacer, linha, 0)
        else:
            corpo = QHBoxLayout()
            corpo.setSpacing(4)
            for tool in tools:
                if tool.tool_id == "cor":
                    controle_cor = ColorControlWidget()
                    controle_cor.estilo_changed.connect(self.estilo_changed.emit)
                    corpo.addWidget(controle_cor)
                else:
                    botao = RibbonButton(tool)
                    botao.acionada.connect(self.tool_selected.emit)
                    corpo.addWidget(botao)
            corpo.addStretch(1)

        raiz.addLayout(corpo)

        rodape = QLabel(titulo)
        rodape.setAlignment(Qt.AlignCenter)
        rodape.setStyleSheet("color: #505050; font-size: 9px; border-top: 1px solid #d9d9d9; padding-top: 2px;")
        raiz.addWidget(rodape)

        self.setStyleSheet("QFrame#RibbonGroup { background: #ffffff; border-right: 1px solid #dddddd; }")


class RibbonPage(QWidget):
    tool_selected = Signal(str)

    def __init__(self, grupos: list[tuple[str, list[ToolDef]]], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(0)
        for titulo, tools in grupos:
            group = RibbonGroup(titulo, tools)
            group.tool_selected.connect(self.tool_selected.emit)
            layout.addWidget(group)
        espaco = QWidget()
        espaco.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(espaco)


class RibbonWidget(QWidget):
    tool_selected = Signal(str)
    estilo_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None, include_tabbar: bool = True):
        super().__init__(parent)
        self._tabs, self._tools = carregar_mapa_ribbon()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setStyleSheet("background:#ffffff; color:#111;")

        self.tabbar = RibbonTabBar()
        self.paginas = QStackedWidget()
        self.tabbar.currentChanged.connect(self.paginas.setCurrentIndex)
        self.tabbar.currentChanged.connect(self._atualizar_destaque_aba)

        for tab in self._tabs:
            self.tabbar.addTab(tab.title)
            grupos: list[tuple[str, list[ToolDef]]] = []
            for group in tab.groups:
                grupos.append((group.title, [self._tools[tid] for tid in group.tools]))
            pagina = RibbonPage(grupos)
            pagina.tool_selected.connect(self.tool_selected.emit)
            for grupo in pagina.findChildren(RibbonGroup):
                grupo.estilo_changed.connect(self.estilo_changed.emit)
            self.paginas.addWidget(pagina)

        if include_tabbar:
            layout.addWidget(self.tabbar)
        layout.addWidget(self.paginas)
        self.tabbar.setStyleSheet(
            """
            QTabBar::tab {
                background: #f3f5f8;
                color: #1e2a36;
                border: 1px solid #d4dbe4;
                padding: 6px 10px;
            }
            QTabBar::tab:selected {
                background: #e8f2fc;
                color: #0f4f86;
                border-bottom: 2px solid #2f9fe8;
            }
            QTabBar::tab:hover { background: #edf5ff; }
            """
        )
        self._atualizar_destaque_aba(self.tabbar.currentIndex())

    def tool_def(self, tool_id: str) -> ToolDef | None:
        return self._tools.get(tool_id)

    def _atualizar_destaque_aba(self, index: int):
        for i in range(self.paginas.count()):
            pagina = self.paginas.widget(i)
            if i == index:
                pagina.setStyleSheet("background: #eaf4ff; border-top: 1px solid #c7ddf3;")
            else:
                pagina.setStyleSheet("background: #ffffff; border-top: 1px solid #dfe4ea;")


def carregar_mapa_ribbon() -> tuple[list[TabDef], dict[str, ToolDef]]:
    map_path = Path(__file__).with_name("tool_pages_map.json")
    dados = json.loads(map_path.read_text(encoding="utf-8"))

    tools = {
        tool_id: ToolDef(
            tool_id=tool_id,
            title=tool_data["title"],
            module=tool_data["module"],
            class_name=tool_data["class"],
            icon=tool_data.get("icon", ""),
        )
        for tool_id, tool_data in dados["tools"].items()
    }

    tabs: list[TabDef] = []
    for tab in dados["tabs"]:
        groups = [GroupDef(title=g["title"], tools=g["tools"]) for g in tab["groups"]]
        tabs.append(TabDef(tab_id=tab["id"], title=tab["title"], groups=groups))
    return tabs, tools


def _carregar_icone(icon_name: str) -> QIcon:
    if icon_name:
        icon_path = ICONS_DIR / icon_name
        if icon_path.exists():
            return QIcon(str(icon_path))

    pix = QPixmap(20, 20)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#4a7fc1"))
    painter.drawRoundedRect(1, 1, 18, 18, 4, 4)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(5, 5, 10, 10, 2, 2)
    painter.end()
    return QIcon(pix)
