from __future__ import annotations

import json
from math import sin
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QIcon, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidgetAction,
    QWidget,
)

from config import ICONS_DIR
from core.line_styles import LINE_STYLES, dash_pattern_for_line, is_geometric_line_style, pen_style_for_line


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
        return QSize(max(size.width() + 12, 66), 30)


class RibbonButton(QToolButton):
    acionada = Signal(str)

    def __init__(self, ferramenta: ToolDef, compacto: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.ferramenta = ferramenta
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setText(ferramenta.title)
        self.setIcon(_carregar_icone(ferramenta.icon))
        self.setProperty("tool_id", ferramenta.tool_id)
        self.clicked.connect(lambda: self.acionada.emit(self.ferramenta.tool_id))

        if compacto:
            self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.setIconSize(QSize(18, 18))
            self.setFixedSize(112, 26)
            self.setStyleSheet(
                """
                QToolButton {
                    text-align: left;
                    background: transparent;
                    border: 1px solid transparent;
                    color: #1e1e1e;
                    font-size: 12px;
                    padding: 0 4px;
                }
                QToolButton:hover { background: #f5f8fd; border: 1px solid #cddbf0; }
                QToolButton:pressed { background: #e6eefb; border: 1px solid #9cb7df; }
                QToolButton:checked { background: #e7f1ff; border: 1px solid #8cb3df; color:#0f4f86; }
                """
            )
            return

        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(26, 26))
        self.setMinimumSize(78, 66)
        self.setStyleSheet(
            """
            QToolButton {
                background: #ffffff;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #1e1e1e;
                font-size: 12px;
                padding: 3px;
            }
            QToolButton:hover { background: #f5f8fd; border: 1px solid #cddbf0; }
            QToolButton:pressed { background: #e6eefb; border: 1px solid #9cb7df; }
            QToolButton:checked { background: #e7f1ff; border: 1px solid #8cb3df; color:#0f4f86; }
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
        self._amplitude = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(2)

        self.btn_cor = QPushButton()
        self.btn_cor.setFixedSize(34, 34)
        self.btn_cor.setCursor(Qt.PointingHandCursor)
        self.btn_cor.setToolTip("Selecionar cor da linha")
        self.btn_cor.clicked.connect(self._selecionar_cor)
        topo.addWidget(self.btn_cor)

        coluna_setas = QVBoxLayout()
        coluna_setas.setContentsMargins(0, 0, 0, 0)
        coluna_setas.setSpacing(2)

        self.btn_estilo = QToolButton()
        self.btn_estilo.setText("Estilo")
        self.btn_estilo.setCursor(Qt.PointingHandCursor)
        self.btn_estilo.setFixedSize(62, 16)
        self.btn_estilo.setToolTip("Estilo da linha")
        self.btn_estilo.clicked.connect(self._abrir_menu_estilo)
        coluna_setas.addWidget(self.btn_estilo)

        self.btn_espessura = QToolButton()
        self.btn_espessura.setText("Espess.")
        self.btn_espessura.setCursor(Qt.PointingHandCursor)
        self.btn_espessura.setFixedSize(62, 16)
        self.btn_espessura.setToolTip("Espessura da linha")
        self.btn_espessura.clicked.connect(self._abrir_menu_espessura)
        coluna_setas.addWidget(self.btn_espessura)

        self.btn_amplitude = QToolButton()
        self.btn_amplitude.setText("Amplitude")
        self.btn_amplitude.setCursor(Qt.PointingHandCursor)
        self.btn_amplitude.setFixedSize(62, 16)
        self.btn_amplitude.setToolTip("Altura da onda/zig-zag")
        self.btn_amplitude.clicked.connect(self._abrir_menu_amplitude)
        coluna_setas.addWidget(self.btn_amplitude)

        topo.addLayout(coluna_setas)
        layout.addLayout(topo)

        lbl = QLabel("Cor")
        lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lbl.setStyleSheet("font-size: 11px; color:#1e1e1e; padding-left:2px;")
        layout.addWidget(lbl)
        self.setFixedSize(122, 72)
        self.setStyleSheet(
            """
            QFrame#ColorControlWidget { background:#ffffff; border:1px solid transparent; }
            QToolButton { border:1px solid #d1d7de; background:#f8fafc; color:#2f4f6f; font-size:10px; }
            QToolButton:hover { background:#eef5fd; }
            """
        )
        self._menu_estilo = QMenu(self)
        for estilo_id, titulo in LINE_STYLES:
            self._adicionar_acao_estilo(estilo_id, titulo)
        self._menu_espessura = QMenu(self)
        for valor in (1, 2, 3, 4, 5, 6):
            self._adicionar_acao_menu(
                self._menu_espessura,
                self._icone_espessura(float(valor)),
                f"Espessura {valor}",
                lambda _=False, v=valor: self._selecionar_espessura(float(v)),
            )
        self._menu_amplitude = QMenu(self)
        amplitudes = [
            (0.5, "Amplitude baixa"),
            (1.0, "Amplitude normal"),
            (1.5, "Amplitude alta"),
            (2.0, "Amplitude muito alta"),
        ]
        for valor, rotulo in amplitudes:
            self._adicionar_acao_menu(
                self._menu_amplitude,
                self._icone_estilo("wave_soft", amplitude=valor),
                rotulo,
                lambda _=False, v=valor: self._selecionar_amplitude(float(v)),
            )
        self._atualizar_preview_cor()

    def _abrir_menu_estilo(self):
        self._menu_estilo.exec(self.btn_estilo.mapToGlobal(self.btn_estilo.rect().bottomLeft()))

    def _abrir_menu_espessura(self):
        self._menu_espessura.exec(self.btn_espessura.mapToGlobal(self.btn_espessura.rect().bottomLeft()))

    def _abrir_menu_amplitude(self):
        self._menu_amplitude.exec(self.btn_amplitude.mapToGlobal(self.btn_amplitude.rect().bottomLeft()))

    def _selecionar_estilo(self, estilo: str):
        self._estilo = estilo
        self.estilo_changed.emit(self.valor())

    def _selecionar_espessura(self, espessura: float):
        self._espessura = espessura
        self.estilo_changed.emit(self.valor())

    def _selecionar_amplitude(self, amplitude: float):
        self._amplitude = max(0.2, float(amplitude))
        self.estilo_changed.emit(self.valor())

    def _adicionar_acao_estilo(self, estilo: str, titulo: str):
        self._adicionar_acao_menu(
            self._menu_estilo,
            self._icone_estilo(estilo),
            titulo,
            lambda _=False, e=estilo: self._selecionar_estilo(e),
        )

    def _adicionar_acao_menu(self, menu: QMenu, icone: QPixmap, texto: str, callback):
        acao = QWidgetAction(menu)
        botao = QPushButton(texto)
        botao.setIcon(QIcon(icone))
        botao.setIconSize(icone.size())
        botao.setCursor(Qt.PointingHandCursor)
        botao.setStyleSheet(
            """
            QPushButton {
                text-align: left;
                border: none;
                padding: 3px 10px 3px 6px;
                color: #1b1b1b;
                background: transparent;
            }
            QPushButton:hover { background: #e8f1fb; }
            """
        )
        botao.clicked.connect(lambda: (callback(), menu.close()))
        acao.setDefaultWidget(botao)
        menu.addAction(acao)

    def _icone_estilo(self, estilo: str, amplitude: float | None = None) -> QPixmap:
        pix = QPixmap(132, 20)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor("#111111"), 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            amp_scale = max(0.2, float(amplitude if amplitude is not None else self._amplitude))
            if is_geometric_line_style(estilo):
                path = QPainterPath()
                path.moveTo(6, 10)
                if estilo.startswith("zigzag"):
                    amp = (2.0 if estilo == "zigzag_soft" else 4.0) * amp_scale
                    passo = 10.0 if estilo == "zigzag_soft" else 12.0
                    x = 6.0
                    sentido = 1.0
                    while x < 126.0:
                        x = min(126.0, x + passo)
                        path.lineTo(x, 10 + (amp * sentido))
                        sentido *= -1.0
                    path.lineTo(126, 10)
                elif estilo.startswith("wave"):
                    amp = (2.0 if estilo == "wave_soft" else 4.0) * amp_scale
                    passo = 12.0 if estilo == "wave_soft" else 14.0
                    for i in range(1, 48):
                        t = i / 47.0
                        x = 6.0 + (120.0 * t)
                        y = 10.0 + (amp * sin((2.0 * 3.14159265359 * (x - 6.0)) / passo))
                        path.lineTo(x, y)
                else:
                    amp = (3.0 if estilo == "half_moon" else 2.6) * amp_scale
                    passo = 16.0 if estilo == "half_moon" else 18.0
                    if estilo == "half_moon":
                        ciclos = max(1, round(120.0 / passo))
                        passo = 120.0 / ciclos
                    x = 6.0
                    while x < 126.0:
                        restante = 126.0 - x
                        if restante < (passo * 0.7):
                            path.lineTo(126.0, 10.0)
                            break
                        raio = passo / 2.0
                        centro_x = x + raio
                        inicio = x
                        fim = min(126.0, x + passo)
                        subamostras = 10
                        for i in range(subamostras + 1):
                            t = i / subamostras
                            px = inicio + ((fim - inicio) * t)
                            theta = 3.14159265359 * t
                            py = 10.0 - (amp * sin(theta))
                            path.lineTo(px, py)
                        if estilo != "half_moon":
                            gap = 7.0 if estilo == "dash_half_moon" else 4.0
                            path.moveTo(min(126.0, fim + gap), 10.0)
                            x = fim + gap
                        else:
                            x = fim
                painter.drawPath(path)
            else:
                pen.setStyle(pen_style_for_line(estilo))
                padrao = dash_pattern_for_line(estilo)
                if padrao:
                    pen.setDashPattern(padrao)
                painter.setPen(pen)
                painter.drawLine(6, 10, 126, 10)
        finally:
            painter.end()
        return pix

    def _icone_espessura(self, espessura: float) -> QPixmap:
        pix = QPixmap(90, 16)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        try:
            pen = QPen(QColor("#111111"), espessura)
            pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.drawLine(4, 8, 86, 8)
        finally:
            painter.end()
        return pix

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
        return {"cor": self._cor, "estilo": self._estilo, "espessura": self._espessura, "amplitude": self._amplitude}


class RibbonGroup(QFrame):
    tool_selected = Signal(str)
    estilo_changed = Signal(dict)

    def __init__(self, titulo: str, tools: list[ToolDef], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self.setFixedHeight(92)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 4, 6, 0)
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
        rodape.setFixedHeight(12)
        rodape.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        rodape.setStyleSheet("color: #505050; font-size: 8px; border-top: 1px solid #d9d9d9; padding-top: 0px;")
        raiz.addWidget(rodape)

        self.setStyleSheet("QFrame#RibbonGroup { background: #ffffff; border-right: 1px solid #dddddd; }")


class RibbonPage(QWidget):
    tool_selected = Signal(str)

    def __init__(self, grupos: list[tuple[str, list[ToolDef]]], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 1, 5, 1)
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
            pagina.tool_selected.connect(self._on_tool_selected)
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
                font-size: 13px;
                padding: 6px 12px;
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

    def _on_tool_selected(self, tool_id: str):
        self.set_active_tool(tool_id)
        self.tool_selected.emit(tool_id)

    def set_active_tool(self, tool_id: str):
        for botao in self.findChildren(RibbonButton):
            botao.blockSignals(True)
            botao.setChecked(bool(botao.property("tool_id") == tool_id))
            botao.blockSignals(False)

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
        groups_data = tab["groups"]
        if tab.get("id") == "inicio":
            groups_data = _normalizar_grupos_inicio(groups_data)
        groups = [GroupDef(title=g["title"], tools=g["tools"]) for g in groups_data]
        tabs.append(TabDef(tab_id=tab["id"], title=tab["title"], groups=groups))
    return tabs, tools


def _normalizar_grupos_inicio(groups: list[dict]) -> list[dict]:
    grupos_por_titulo = {g.get("title"): list(g.get("tools", [])) for g in groups}
    desenho = [tid for tid in grupos_por_titulo.get("Desenho", []) if tid != "colar"]
    if not desenho:
        desenho = ["cor", "selecionar"]

    editar_base = [tid for tid in ("colar", "recortar", "copiar", "excluir") if tid in groups_tools_flat(groups)]
    editar_existentes = [tid for tid in grupos_por_titulo.get("Editar", []) if tid not in editar_base]
    editar = editar_base + editar_existentes

    saida: list[dict] = []
    for g in groups:
        titulo = g.get("title")
        if titulo == "Desenho":
            saida.append({"title": "Desenho", "tools": desenho})
        elif titulo == "Editar":
            saida.append({"title": "Editar", "tools": editar})
        else:
            saida.append(g)
    return saida


def groups_tools_flat(groups: list[dict]) -> set[str]:
    resultado: set[str] = set()
    for g in groups:
        resultado.update(g.get("tools", []))
    return resultado


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
