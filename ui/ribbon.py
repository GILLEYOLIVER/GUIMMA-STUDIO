from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap, QIcon
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
        return QSize(max(size.width() + 16, 92), 26)


class RibbonButton(QToolButton):
    acionada = Signal(str)

    def __init__(self, ferramenta: ToolDef, parent: QWidget | None = None):
        super().__init__(parent)
        self.ferramenta = ferramenta
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setText(ferramenta.title)
        self.setIcon(_carregar_icone(ferramenta.icon))
        self.setIconSize(QSize(20, 20))
        self.setMinimumSize(64, 54)
        self.clicked.connect(lambda: self.acionada.emit(self.ferramenta.tool_id))
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


class RibbonGroup(QFrame):
    tool_selected = Signal(str)

    def __init__(self, titulo: str, tools: list[ToolDef], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self.setFixedHeight(102)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 4, 6, 2)
        raiz.setSpacing(2)

        corpo = QHBoxLayout()
        corpo.setSpacing(4)
        raiz.addLayout(corpo)

        for tool in tools:
            botao = RibbonButton(tool)
            botao.acionada.connect(self.tool_selected.emit)
            corpo.addWidget(botao)

        corpo.addStretch(1)

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

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tabs, self._tools = carregar_mapa_ribbon()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setStyleSheet("background:#ffffff; color:#111;")

        self.tabbar = RibbonTabBar()
        self.paginas = QStackedWidget()
        self.tabbar.currentChanged.connect(self.paginas.setCurrentIndex)

        for tab in self._tabs:
            self.tabbar.addTab(tab.title)
            grupos: list[tuple[str, list[ToolDef]]] = []
            for group in tab.groups:
                grupos.append((group.title, [self._tools[tid] for tid in group.tools]))
            pagina = RibbonPage(grupos)
            pagina.tool_selected.connect(self.tool_selected.emit)
            self.paginas.addWidget(pagina)

        layout.addWidget(self.tabbar)
        layout.addWidget(self.paginas)

    def tool_def(self, tool_id: str) -> ToolDef | None:
        return self._tools.get(tool_id)


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
