from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from tools.tool_base import FerramentaBase


@dataclass(slots=True)
class MoldeRef:
    indice: int
    nome: str
    dados: dict


class PreviewMoldeWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._molde: dict | None = None
        self.setMinimumHeight(270)
        self._zoom = 1.0

    def set_molde(self, molde: dict | None):
        self._molde = molde
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#000000"))

        if not self._molde or self._molde.get("tipo") != "polyline":
            painter.setPen(QPen(QColor("#8a8a8a"), 1))
            painter.drawText(self.rect(), Qt.AlignCenter, "Nenhum molde selecionado")
            return

        pontos_raw = self._molde.get("pontos", [])
        pontos = [QPointF(float(x), float(y)) for x, y in pontos_raw]
        if len(pontos) < 2:
            return

        base = pontos[:-1] if len(pontos) >= 3 and pontos[0] == pontos[-1] else pontos
        if not base:
            return

        xs = [p.x() for p in base]
        ys = [p.y() for p in base]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura = max(1.0, max_x - min_x)
        altura = max(1.0, max_y - min_y)

        margem = 26.0
        area_w = max(1.0, self.width() - (margem * 2.0))
        area_h = max(1.0, self.height() - (margem * 2.0))
        escala = min(area_w / largura, area_h / altura)

        offset_x = (self.width() - (largura * escala)) / 2.0
        offset_y = (self.height() - (altura * escala)) / 2.0

        def mapear(pt: QPointF) -> QPointF:
            return QPointF(
                offset_x + ((pt.x() - min_x) * escala),
                offset_y + ((pt.y() - min_y) * escala),
            )

        pen = QPen(QColor("#ffffff"), 1.0)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        path = QPainterPath(mapear(base[0]))
        for pt in base[1:]:
            path.lineTo(mapear(pt))
        if len(base) >= 3:
            path.closeSubpath()

        if bool(self._molde.get("visual_preencher", False)):
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(str(self._molde.get("cor") or "#58dfe3")))
            painter.drawPath(path)
            painter.restore()
            painter.setPen(pen)

        painter.drawPath(path)

        self._desenhar_fio(painter, base, mapear)
        self._desenhar_textos(painter, base, mapear, min_y, max_y)
        self._desenhar_controles(painter, mapear)

    def _desenhar_fio(self, painter: QPainter, base: list[QPointF], mapear):
        if not self._molde.get("mostrar_fio", True):
            return
        fio_origem = self._molde.get("fio_origem")
        fio_fim = self._molde.get("fio_fim")
        xs = [p.x() for p in base]
        ys = [p.y() for p in base]
        if fio_origem and fio_fim:
            p1 = mapear(QPointF(float(fio_origem[0]), float(fio_origem[1])))
            p2 = mapear(QPointF(float(fio_fim[0]), float(fio_fim[1])))
        else:
            margem = (max(xs) - min(xs)) * 0.18
            y_fio = min(ys) + ((max(ys) - min(ys)) * 0.58)
            p1 = mapear(QPointF(min(xs) + margem, y_fio))
            p2 = mapear(QPointF(max(xs) - margem, y_fio))

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-6:
            return
        ux = dx / comp
        uy = dy / comp
        nx = -uy
        ny = ux
        recuo = min(16.0, max(7.0, comp * 0.045))
        a = QPointF(p1.x() + (ux * recuo), p1.y() + (uy * recuo))
        b = QPointF(p2.x() - (ux * recuo), p2.y() - (uy * recuo))
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.drawLine(a, b)
        self._desenhar_ponta(painter, p1, QPointF(-ux, -uy), QPointF(nx, ny), 9.0, 2.8)
        self._desenhar_ponta(painter, p2, QPointF(ux, uy), QPointF(nx, ny), 9.0, 2.8)

    def _desenhar_ponta(self, painter: QPainter, ponta: QPointF, direcao: QPointF, normal: QPointF, comprimento: float, meia: float):
        base = QPointF(ponta.x() - (direcao.x() * comprimento), ponta.y() - (direcao.y() * comprimento))
        e = QPointF(base.x() + (normal.x() * meia), base.y() + (normal.y() * meia))
        d = QPointF(base.x() - (normal.x() * meia), base.y() - (normal.y() * meia))
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        path = QPainterPath()
        path.moveTo(ponta)
        path.lineTo(e)
        path.lineTo(d)
        path.closeSubpath()
        painter.drawPath(path)
        painter.restore()

    def _desenhar_textos(self, painter: QPainter, base: list[QPointF], mapear, min_y: float, max_y: float):
        cx = sum(p.x() for p in base) / len(base)
        cy = sum(p.y() for p in base) / len(base)
        painter.setPen(QPen(QColor("#ffffff"), 1.0))

        fonte = QFont(painter.font())
        fonte.setPointSize(9)
        painter.setFont(fonte)

        if self._molde.get("mostrar_nome", True):
            nome = str(self._molde.get("nome_molde") or "")
            if nome:
                pos = mapear(QPointF(cx, cy + ((max_y - min_y) * 0.02)))
                painter.drawText(int(pos.x() - 16), int(pos.y() - 6), 60, 20, Qt.AlignLeft, nome)

        if self._molde.get("visual_descricao", False):
            descricao = str(self._molde.get("descricao") or "Descrição")
            pos = mapear(QPointF(cx, cy + ((max_y - min_y) * 0.18)))
            painter.drawText(int(pos.x() - 40), int(pos.y()), 120, 18, Qt.AlignCenter, descricao)

        if self._molde.get("visual_quantidade", False):
            qtd = str(self._molde.get("qtd_modelo", 1) or 1)
            sufixo = " ( Par)" if self._molde.get("par", False) else ""
            pos = mapear(QPointF(cx, cy + ((max_y - min_y) * 0.22)))
            painter.drawText(int(pos.x() - 50), int(pos.y() + 16), 140, 18, Qt.AlignCenter, f"Quantidade {qtd}{sufixo}")

    def _desenhar_controles(self, painter: QPainter, mapear):
        if not self._molde.get("mostrar_controles", True):
            return
        pontos = [QPointF(float(x), float(y)) for x, y in self._molde.get("controle_cantos", [])]
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        for i, pt in enumerate(pontos, start=1):
            tela = mapear(pt)
            painter.drawRect(int(tela.x() - 3), int(tela.y() - 3), 6, 6)
            if self._molde.get("mostrar_numeros", False):
                painter.drawText(int(tela.x() + 4), int(tela.y() - 6), str(i))


class PropriedadesMoldesDialog(QDialog):
    dados_aplicados = Signal()

    def __init__(self, canvas, parent: QWidget | None = None):
        super().__init__(parent)
        self.canvas = canvas
        self._refs: list[MoldeRef] = []
        self._indice_atual: int | None = None
        self._cor_visual = "#ffffff"
        self.setWindowTitle("Propriedades dos moldes")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.resize(1060, 780)
        self.setMinimumSize(1020, 740)
        self.setObjectName("PropriedadesMoldesDialog")
        self.setStyleSheet(self._stylesheet())
        self._construir_ui()
        self.recarregar_lista()

    def _stylesheet(self) -> str:
        return """
        QDialog#PropriedadesMoldesDialog {
            background: #efefef;
            color: #101010;
        }
        QLabel, QCheckBox, QLineEdit, QTextEdit, QComboBox, QTreeWidget, QTableWidget {
            color: #111111;
            font-size: 12px;
        }
        QFrame#PanelLeft, QFrame#PanelRight {
            background: transparent;
        }
        QTreeWidget {
            background: #ffffff;
            border: 1px solid #9fa8b2;
            selection-background-color: #c9d7ea;
            selection-color: #111111;
        }
        QTreeWidget::item { height: 21px; }
        QTreeWidget::item:selected { background: #b9cfe1; color: #111111; }
        QTabWidget::pane {
            border: none;
            background: transparent;
        }
        QTabBar::tab {
            background: #ebebeb;
            border: 1px solid #d2d2d2;
            padding: 5px 12px;
            min-width: 62px;
            margin-right: 1px;
            color: #000000;
        }
        QTabBar::tab:selected {
            background: #f5f5f5;
            border-bottom-color: #f5f5f5;
        }
        QTabBar::tab:hover { background: #f0f0f0; }
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget {
            background: #ffffff;
            border: 1px solid #b5bcc3;
            border-radius: 0px;
            selection-background-color: #2b7cd3;
            selection-color: #ffffff;
        }
        QTextEdit { padding: 4px; }
        QGroupBox {
            border: 1px solid #c8c8c8;
            margin-top: 6px;
            background: #f5f5f5;
            font-weight: 600;
        }
        QGroupBox::title {
            left: 6px;
            padding: 0 2px;
        }
        QPushButton {
            background: #f7f7f7;
            border: 1px solid #b7bec5;
            border-radius: 4px;
            padding: 3px 10px;
            min-height: 22px;
            color: #111111;
        }
        QPushButton:hover { background: #ffffff; }
        QPushButton#OkButton {
            color: #2f7d2f;
            min-width: 76px;
        }
        QPushButton#CancelButton {
            color: #b33b3b;
            min-width: 76px;
        }
        QPushButton#ApplyBlueButton {
            background: #d7e9f9;
            border-color: #b8d0ea;
        }
        QHeaderView::section {
            background: #f1f1f1;
            color: #111111;
            border: 1px solid #bfc6cc;
            padding: 3px;
            font-weight: 500;
        }
        """

    def _construir_ui(self):
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(10)

        painel_esq = QFrame()
        painel_esq.setObjectName("PanelLeft")
        painel_esq.setFixedWidth(205)
        lay_esq = QVBoxLayout(painel_esq)
        lay_esq.setContentsMargins(0, 0, 0, 0)
        lay_esq.setSpacing(8)

        self.arvore = QTreeWidget()
        self.arvore.setHeaderHidden(True)
        self.arvore.itemSelectionChanged.connect(self._quando_troca_selecao)
        lay_esq.addWidget(self.arvore, 1)

        self.btn_excluir_molde = QPushButton("🗑 Excluir molde")
        self.btn_excluir_molde.clicked.connect(self._excluir_molde_atual)
        self.btn_excluir_molde.setFixedHeight(48)
        lay_esq.addWidget(self.btn_excluir_molde)

        lbl_legenda = QLabel("◢ Legenda de status do molde:")
        lbl_legenda.setStyleSheet("padding-left:2px; color:#111111;")
        lay_esq.addWidget(lbl_legenda)

        painel_dir = QFrame()
        painel_dir.setObjectName("PanelRight")
        lay_dir = QVBoxLayout(painel_dir)
        lay_dir.setContentsMargins(0, 0, 0, 0)
        lay_dir.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._criar_tab_propriedades(), "Propriedades")
        self.tabs.addTab(self._criar_tab_graduacao(), "Graduação")
        self.tabs.addTab(self._criar_tab_visualizacao(), "Visualização")
        self.tabs.addTab(self._criar_tab_margem(), "Margem")
        self.tabs.addTab(self._criar_tab_cam(), "Pontos de CAM")
        lay_dir.addWidget(self.tabs, 0)

        self.preview = PreviewMoldeWidget()
        lay_dir.addWidget(self.preview, 1)

        barra_preview = QHBoxLayout()
        barra_preview.setContentsMargins(0, 0, 0, 0)
        barra_preview.setSpacing(6)
        for texto in ("🖐", "⤢", "🔍+", "🔎"):
            btn = QPushButton(texto)
            btn.setFixedSize(26, 22)
            barra_preview.addWidget(btn, 0, Qt.AlignLeft)
        barra_preview.addStretch(1)
        lay_dir.addLayout(barra_preview)

        rodape = QHBoxLayout()
        rodape.setContentsMargins(0, 0, 0, 0)
        rodape.addStretch(1)
        self.btn_ok = QPushButton("✓ OK")
        self.btn_ok.setObjectName("OkButton")
        self.btn_ok.clicked.connect(self._ok)
        self.btn_cancelar = QPushButton("✕ Cancelar")
        self.btn_cancelar.setObjectName("CancelButton")
        self.btn_cancelar.clicked.connect(self.close)
        rodape.addWidget(self.btn_ok)
        rodape.addWidget(self.btn_cancelar)
        lay_dir.addLayout(rodape)

        raiz.addWidget(painel_esq, 0)
        raiz.addWidget(painel_dir, 1)
        self._ajustar_larguras_campos()

    def _ajustar_larguras_campos(self):
        combos = [
            self.cmb_aplicar_grade,
            self.cmb_area_tamanho,
            self.cmb_grade_tamanhos,
            self.cmb_elementos_molde,
            self.cmb_tipo_corte,
            self.cmb_espelhar,
            self.cmb_giro,
            self.cmb_tipo_corte_cam,
        ]
        for combo in combos:
            combo.setMinimumContentsLength(18)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            combo.setMinimumWidth(170)

    def _criar_tab_propriedades(self) -> QWidget:
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(6, 8, 6, 0)
        layout.setSpacing(8)

        topo = QFrame()
        grid = QGridLayout(topo)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)

        self.ed_nome = QLineEdit()
        self.ed_descricao = QTextEdit()
        self.ed_descricao.setFixedHeight(56)
        self.cmb_tipo_corte = QComboBox()
        self.cmb_tipo_corte.addItems(["Completo", "Par", "Espelhado", "Único"])
        self.ed_tecido = QLineEdit()
        self.cmb_espelhar = QComboBox()
        self.cmb_espelhar.addItems(["Horizontal", "Vertical", "Nenhum"])
        self.sp_qtd_modelo = QSpinBox()
        self.sp_qtd_modelo.setRange(1, 999)
        self.cmb_giro = QComboBox()
        self.cmb_giro.addItems(["180 graus", "90 graus", "270 graus", "Livre"])
        self.ed_faixa_giro = QLineEdit("0")
        self.ed_giro_inicial = QLineEdit("0")
        self.chk_par = QCheckBox("Par")
        self.chk_dobra_v = QCheckBox("Dobra vertical")
        self.chk_dobra_h = QCheckBox("Dobra horizontal")
        self.chk_perm_alt = QCheckBox("Permitir alterações das propriedades no GUIMMA Encaixe")
        self.chk_reflete_v = QCheckBox("Refletido vertical")
        self.chk_reflete_h = QCheckBox("Refletido horizontal")

        grid.addWidget(QLabel("Molde"), 0, 0)
        grid.addWidget(self.ed_nome, 0, 1, 1, 4)
        grid.addWidget(QLabel("Descrição"), 1, 0)
        grid.addWidget(self.ed_descricao, 1, 1, 1, 4)

        box = QGroupBox("Propriedades de encaixe")
        box_layout = QGridLayout(box)
        box_layout.setContentsMargins(8, 8, 8, 8)
        box_layout.setHorizontalSpacing(8)
        box_layout.setVerticalSpacing(6)

        self.chk_molde_pronto = QCheckBox("Molde pronto")
        box_layout.addWidget(self.chk_molde_pronto, 0, 0)
        box_layout.addWidget(self.chk_perm_alt, 0, 3, 1, 3)

        box_layout.addWidget(QLabel("Tecido"), 1, 0)
        box_layout.addWidget(self.ed_tecido, 1, 3, 1, 2)
        box_layout.addWidget(QLabel("Espelhar"), 2, 0)
        box_layout.addWidget(self.cmb_espelhar, 2, 3, 1, 2)
        box_layout.addWidget(QLabel("Quantidade por modelo"), 3, 0)
        box_layout.addWidget(self.sp_qtd_modelo, 3, 3, 1, 2)
        box_layout.addWidget(self.chk_par, 3, 5)
        box_layout.addWidget(QLabel("Giro"), 4, 0)
        box_layout.addWidget(self.cmb_giro, 4, 3, 1, 2)
        box_layout.addWidget(self.chk_dobra_v, 4, 5)
        box_layout.addWidget(QLabel("Faixa de giro"), 5, 0)
        box_layout.addWidget(self.ed_faixa_giro, 5, 3, 1, 2)
        box_layout.addWidget(QLabel("°"), 5, 5)
        box_layout.addWidget(self.chk_dobra_h, 5, 6)

        box_layout.addWidget(QLabel("Configuração inicial do molde"), 6, 0, 1, 3)
        box_layout.addWidget(QLabel("Giro inicial"), 7, 0)
        box_layout.addWidget(self.ed_giro_inicial, 7, 1)
        box_layout.addWidget(QLabel("°"), 7, 2)
        box_layout.addWidget(self.chk_reflete_v, 7, 4)
        box_layout.addWidget(self.chk_reflete_h, 7, 5)

        self.btn_aplicar_todos_prop = QPushButton("Aplicar todos")
        self.btn_aplicar_todos_prop.setObjectName("ApplyBlueButton")
        self.btn_aplicar_todos_prop.clicked.connect(self._aplicar)
        box_layout.addWidget(self.btn_aplicar_todos_prop, 8, 0, 1, 2)

        layout.addWidget(topo)
        layout.addWidget(box)
        return aba

    def _criar_tab_graduacao(self) -> QWidget:
        aba = QWidget()
        layout = QHBoxLayout(aba)
        layout.setContentsMargins(14, 16, 14, 6)
        layout.setSpacing(12)

        quadro_esq = QFrame()
        grid_esq = QVBoxLayout(quadro_esq)
        grid_esq.setContentsMargins(0, 0, 0, 0)
        grid_esq.setSpacing(4)

        self.tbl_graduacao = QTableWidget(3, 3)
        self.tbl_graduacao.setHorizontalHeaderLabels(["Visão", "Tamanho", "Cor"])
        self.tbl_graduacao.verticalHeader().setVisible(False)
        self.tbl_graduacao.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_graduacao.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_graduacao.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_graduacao.setFixedWidth(230)
        self.tbl_graduacao.setFixedHeight(286)
        self.tbl_graduacao.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_graduacao.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_graduacao.setSelectionMode(QTableWidget.SingleSelection)
        self._popular_tabela_graduacao()
        grid_esq.addWidget(self.tbl_graduacao)

        botoes = QHBoxLayout()
        for texto in ("⬆ Novo", "Base", "⬇ Novo", "Excluir"):
            btn = QPushButton(texto)
            btn.setFixedHeight(24)
            botoes.addWidget(btn)
        grid_esq.addLayout(botoes)

        quadro_dir = QGroupBox()
        quadro_dir.setFixedWidth(320)
        form = QFormLayout(quadro_dir)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(8)
        self.cmb_aplicar_grade = QComboBox()
        self.cmb_aplicar_grade.addItems(["Ao modelo", "Ao molde"])
        self.cmb_area_tamanho = QComboBox()
        self.cmb_area_tamanho.addItems(["Manter diferença", "Igual tamanho", "Tamanho intermediário"])
        self.cmb_grade_tamanhos = QComboBox()
        self.cmb_grade_tamanhos.addItems(["P-G(M)", "PP-GG(M)", "PP-XG(M)", "S-L(M)", "S-XL(M)", "1-3(2)", "1-4(2)", "1-5(3)", "2-12(6)", "36-50(40)"])
        form.addRow("Aplicar", self.cmb_aplicar_grade)
        form.addRow("Área do tamanho", self.cmb_area_tamanho)
        form.addRow("Grade de tamanhos", self.cmb_grade_tamanhos)

        layout.addWidget(quadro_esq, 0)
        layout.addWidget(quadro_dir, 0, Qt.AlignTop)
        layout.addStretch(1)
        return aba

    def _popular_tabela_graduacao(self):
        dados = [("✓", "P", "#b6ff00"), ("✓", "M", "#1f8cff"), ("✓", "G", "#f3a300")]
        for linha, (visao, tamanho, cor) in enumerate(dados):
            item_v = QTableWidgetItem(visao)
            item_v.setTextAlignment(Qt.AlignCenter)
            self.tbl_graduacao.setItem(linha, 0, item_v)
            item_t = QTableWidgetItem(tamanho)
            item_t.setTextAlignment(Qt.AlignCenter)
            self.tbl_graduacao.setItem(linha, 1, item_t)
            item_c = QTableWidgetItem("")
            item_c.setBackground(QColor(cor))
            self.tbl_graduacao.setItem(linha, 2, item_c)
        self.tbl_graduacao.selectRow(1)

    def _criar_tab_visualizacao(self) -> QWidget:
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(12, 10, 12, 6)
        layout.setSpacing(8)

        topo = QGroupBox("Manipular")
        grid = QGridLayout(topo)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        self.cmb_elementos_molde = QComboBox()
        self.cmb_elementos_molde.addItems(["Nenhum", "Nome", "Descrição", "Observações", "Fio", "Números"])
        self.ed_referencia = QLineEdit()
        self.ed_alinhamento = QLineEdit()
        self.ed_angulo_texto = QLineEdit()
        self.ed_altura_texto = QLineEdit()
        self.ed_espaco_linhas = QLineEdit()
        for ed in (self.ed_referencia, self.ed_alinhamento, self.ed_angulo_texto, self.ed_altura_texto, self.ed_espaco_linhas):
            ed.setEnabled(False)

        grid.addWidget(QLabel("Elementos do molde"), 0, 0)
        grid.addWidget(self.cmb_elementos_molde, 0, 1)
        grid.addWidget(QLabel("Ângulo do texto"), 0, 2)
        grid.addWidget(self.ed_angulo_texto, 0, 3)
        grid.addWidget(QLabel("°"), 0, 4)
        grid.addWidget(QLabel("Referência"), 1, 0)
        grid.addWidget(self.ed_referencia, 1, 1)
        grid.addWidget(QLabel("Altura do texto (cm)"), 1, 2)
        grid.addWidget(self.ed_altura_texto, 1, 3, 1, 2)
        grid.addWidget(QLabel("Alinhamento"), 2, 0)
        grid.addWidget(self.ed_alinhamento, 2, 1)
        grid.addWidget(QLabel("Espaço entre linhas (cm)"), 2, 2)
        grid.addWidget(self.ed_espaco_linhas, 2, 3, 1, 2)

        box_vis = QGroupBox("Visualização")
        gvis = QGridLayout(box_vis)
        gvis.setContentsMargins(10, 8, 10, 8)
        gvis.setHorizontalSpacing(14)
        gvis.setVerticalSpacing(4)

        self.chk_mostrar_nome = QCheckBox("Nome")
        self.chk_preencher = QCheckBox("Preencher")
        self.chk_mostrar_fio = QCheckBox("Fio")
        self.chk_mostrar_numeros = QCheckBox("Números")
        self.chk_graduacao = QCheckBox("Graduação")
        self.chk_pique = QCheckBox("Pique")

        self.chk_visual_descricao = QCheckBox("Descrição")
        self.chk_linhas_aux = QCheckBox("Linhas auxiliares")
        self.chk_costura = QCheckBox("Costura")
        self.chk_caminho_grade = QCheckBox("Caminho grade")
        self.chk_perimetro_molde = QCheckBox("Perímetro molde")
        self.chk_margem_visual = QCheckBox("Margem")

        self.chk_modelo = QCheckBox("Modelo")
        self.chk_grade_tam = QCheckBox("Grade de tamanhos")
        self.chk_tecido_visual = QCheckBox("Tecido")
        self.chk_quantidade_visual = QCheckBox("Quantidade")
        self.chk_giro_visual = QCheckBox("Giro")

        self.chk_mostrar_nome.setChecked(True)
        self.chk_mostrar_fio.setChecked(True)
        self.chk_mostrar_numeros.setChecked(True)
        self.chk_pique.setChecked(True)
        self.chk_linhas_aux.setChecked(True)
        self.chk_quantidade_visual.setChecked(True)

        gvis.addWidget(self.chk_mostrar_nome, 0, 0)
        gvis.addWidget(self.chk_visual_descricao, 0, 2)
        gvis.addWidget(self.chk_modelo, 0, 4)
        gvis.addWidget(self.chk_preencher, 1, 0)
        gvis.addWidget(QLabel("-  Cor"), 1, 1)
        self.btn_cor_preenchimento = QPushButton("")
        self.btn_cor_preenchimento.setFixedSize(20, 20)
        self.btn_cor_preenchimento.setCursor(Qt.PointingHandCursor)
        self.btn_cor_preenchimento.setToolTip("Escolher cor de preenchimento do molde")
        self.btn_cor_preenchimento.clicked.connect(self._escolher_cor)
        self.btn_cor_preenchimento.setStyleSheet("background:#58dfe3; border:1px solid #8a939c; padding:0;")
        gvis.addWidget(self.btn_cor_preenchimento, 1, 2, alignment=Qt.AlignLeft)
        gvis.addWidget(self.chk_linhas_aux, 1, 3)
        gvis.addWidget(self.chk_grade_tam, 1, 5)
        gvis.addWidget(self.chk_mostrar_fio, 2, 0)
        gvis.addWidget(self.chk_costura, 2, 3)
        gvis.addWidget(self.chk_tecido_visual, 2, 5)
        gvis.addWidget(self.chk_mostrar_numeros, 3, 0)
        gvis.addWidget(self.chk_caminho_grade, 3, 3)
        gvis.addWidget(self.chk_quantidade_visual, 3, 5)
        gvis.addWidget(self.chk_graduacao, 4, 0)
        gvis.addWidget(self.chk_perimetro_molde, 4, 3)
        gvis.addWidget(self.chk_giro_visual, 4, 5)
        gvis.addWidget(self.chk_pique, 5, 0)
        gvis.addWidget(self.chk_margem_visual, 5, 3)

        rodape = QHBoxLayout()
        self.btn_aplicar_visual = QPushButton("Aplicar todos")
        self.btn_aplicar_visual.setObjectName("ApplyBlueButton")
        self.btn_aplicar_visual.clicked.connect(self._aplicar)
        rodape.addWidget(self.btn_aplicar_visual, 0, Qt.AlignLeft)
        rodape.addStretch(1)

        layout.addWidget(topo)
        layout.addWidget(box_vis)
        layout.addLayout(rodape)
        layout.addStretch(1)
        return aba

    def _criar_tab_margem(self) -> QWidget:
        aba = QWidget()
        layout = QHBoxLayout(aba)
        layout.setContentsMargins(14, 10, 14, 6)
        layout.setSpacing(12)

        self.tbl_margem = QTableWidget(8, 2)
        self.tbl_margem.setHorizontalHeaderLabels(["Elemento", "Margem(cm)"])
        self.tbl_margem.verticalHeader().setVisible(False)
        self.tbl_margem.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_margem.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_margem.setFixedSize(215, 242)
        self._popular_tabela_margem()

        box = QGroupBox()
        box.setFixedWidth(450)
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 8, 8, 8)
        self.btn_aplicar_margem = QPushButton("Aplicar")
        self.btn_aplicar_margem.setFixedWidth(82)
        self.btn_aplicar_margem.clicked.connect(self._aplicar)
        v.addWidget(self.btn_aplicar_margem, 0, Qt.AlignLeft)
        v.addStretch(1)

        layout.addWidget(self.tbl_margem, 0, Qt.AlignTop)
        layout.addWidget(box, 0, Qt.AlignTop)
        layout.addStretch(1)
        return aba

    def _popular_tabela_margem(self):
        pares = [("1-2", "0"), ("2-3", "0"), ("3-4", "0"), ("4-5", "0"), ("5-6", "0"), ("6-7", "0"), ("7-8", "0"), ("8-9", "0")]
        for i, (a, b) in enumerate(pares):
            self.tbl_margem.setItem(i, 0, QTableWidgetItem(a))
            self.tbl_margem.setItem(i, 1, QTableWidgetItem(b))

    def _criar_tab_cam(self) -> QWidget:
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(12, 10, 12, 6)
        layout.setSpacing(8)

        topo = QGroupBox()
        grid = QGridLayout(topo)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.addWidget(QLabel("Tipo corte"), 0, 0)
        self.cmb_tipo_corte_cam = QComboBox()
        self.cmb_tipo_corte_cam.addItems(["Completo", "Par", "Espelhado", "Único"])
        grid.addWidget(self.cmb_tipo_corte_cam, 0, 1)
        self.btn_add_cam = QPushButton("Adicionar")
        self.btn_rem_cam = QPushButton("Remover")
        grid.addWidget(self.btn_add_cam, 0, 3)
        grid.addWidget(self.btn_rem_cam, 0, 4)
        grid.setColumnStretch(2, 1)

        layout.addWidget(topo)
        layout.addStretch(1)
        return aba

    def recarregar_lista(self):
        atual_idx = self._indice_atual
        self._refs = self._coletar_moldes()
        self.arvore.clear()
        raiz = QTreeWidgetItem(["1"])
        raiz.setExpanded(True)
        self.arvore.addTopLevelItem(raiz)

        grupos: dict[str, list[MoldeRef]] = {}
        for ref in self._refs:
            grupo = str(ref.dados.get("grupo_molde") or "")
            grupos.setdefault(grupo, []).append(ref)

        for grupo_nome, itens in grupos.items():
            pai = raiz
            if grupo_nome:
                pai = QTreeWidgetItem([grupo_nome])
                raiz.addChild(pai)
            for ref in itens:
                item = QTreeWidgetItem([ref.nome or f"Molde {ref.indice + 1}"])
                item.setData(0, Qt.UserRole, ref.indice)
                pai.addChild(item)

        raiz.setExpanded(True)
        for i in range(raiz.childCount()):
            raiz.child(i).setExpanded(True)

        escolhido = None
        for item in self._iter_items(raiz):
            idx = item.data(0, Qt.UserRole)
            if idx is not None and idx == atual_idx:
                escolhido = item
                break
        if escolhido is None:
            for item in self._iter_items(raiz):
                if item.data(0, Qt.UserRole) is not None:
                    escolhido = item
                    break
        if escolhido:
            self.arvore.setCurrentItem(escolhido)
            self._indice_atual = int(escolhido.data(0, Qt.UserRole))
            self._preencher_campos(self._molde_atual())
        else:
            self._indice_atual = None
            self._preencher_campos(None)

    def _iter_items(self, pai: QTreeWidgetItem):
        for i in range(pai.childCount()):
            child = pai.child(i)
            yield child
            yield from self._iter_items(child)

    def _coletar_moldes(self) -> list[MoldeRef]:
        refs: list[MoldeRef] = []
        for idx, el in enumerate(self.canvas.cena.elementos):
            if not el.get("molde"):
                continue
            refs.append(MoldeRef(indice=idx, nome=str(el.get("nome_molde") or f"K{idx + 1}"), dados=el))
        return refs

    def _quando_troca_selecao(self):
        item = self.arvore.currentItem()
        if not item:
            self._indice_atual = None
            self._preencher_campos(None)
            return
        idx = item.data(0, Qt.UserRole)
        if idx is None:
            return
        self._indice_atual = int(idx)
        self._preencher_campos(self._molde_atual())

    def _molde_atual(self) -> dict | None:
        if self._indice_atual is None:
            return None
        if 0 <= self._indice_atual < len(self.canvas.cena.elementos):
            el = self.canvas.cena.elementos[self._indice_atual]
            if el.get("molde"):
                return el
        return None

    def _preencher_campos(self, molde: dict | None):
        self.preview.set_molde(molde)
        if molde is None:
            self.ed_nome.clear()
            self.ed_descricao.clear()
            self.ed_tecido.clear()
            self._cor_visual = "#ffffff"
            self.btn_cor_preenchimento.setStyleSheet("background:#58dfe3; border:1px solid #8a939c; padding:0;")
            return

        self.ed_nome.setText(str(molde.get("nome_molde") or ""))
        self.ed_descricao.setPlainText(str(molde.get("descricao") or ""))
        self.ed_tecido.setText(str(molde.get("tecido") or "1"))
        self.sp_qtd_modelo.setValue(int(molde.get("qtd_modelo", 1) or 1))
        self.chk_par.setChecked(bool(molde.get("par", False)))
        self.chk_mostrar_nome.setChecked(bool(molde.get("mostrar_nome", True)))
        self.chk_mostrar_fio.setChecked(bool(molde.get("mostrar_fio", True)))
        self.chk_mostrar_numeros.setChecked(bool(molde.get("mostrar_numeros", False)))
        self.chk_visual_descricao.setChecked(bool(molde.get("visual_descricao", False)))
        self.chk_quantidade_visual.setChecked(bool(molde.get("visual_quantidade", False)))
        self.chk_margem_visual.setChecked(bool(molde.get("mostrar_margem", False)))
        self.chk_preencher.setChecked(bool(molde.get("visual_preencher", False)))
        self._cor_visual = str(molde.get("cor") or "#ffffff")
        self.btn_cor_preenchimento.setStyleSheet(f"background:{self._cor_visual}; border:1px solid #8a939c; padding:0;")
        self.preview.set_molde(dict(molde))

    def _aplicar(self) -> bool:
        molde = self._molde_atual()
        if not molde:
            QMessageBox.information(self, "Propriedades", "Selecione um molde.")
            return False

        molde["nome_molde"] = self.ed_nome.text().strip() or molde.get("nome_molde") or "N22"
        molde["descricao"] = self.ed_descricao.toPlainText().strip()
        molde["tecido"] = self.ed_tecido.text().strip()
        molde["tipo_corte"] = self.cmb_tipo_corte.currentText().strip()
        molde["qtd_modelo"] = int(self.sp_qtd_modelo.value())
        molde["par"] = self.chk_par.isChecked()
        molde["refletido_vertical"] = self.chk_reflete_v.isChecked()
        molde["refletido_horizontal"] = self.chk_reflete_h.isChecked()
        molde["mostrar_nome"] = self.chk_mostrar_nome.isChecked()
        molde["mostrar_fio"] = self.chk_mostrar_fio.isChecked()
        molde["mostrar_numeros"] = self.chk_mostrar_numeros.isChecked()
        molde["visual_descricao"] = self.chk_visual_descricao.isChecked()
        molde["visual_quantidade"] = self.chk_quantidade_visual.isChecked()
        molde["mostrar_margem"] = self.chk_margem_visual.isChecked()
        molde["visual_preencher"] = self.chk_preencher.isChecked()
        molde["cor"] = self._cor_visual

        self.canvas.update()
        if hasattr(self.canvas, "_registrar_historico"):
            self.canvas._registrar_historico()
        self.preview.set_molde(dict(molde))
        self.dados_aplicados.emit()
        return True

    def _ok(self):
        if self._aplicar():
            self.close()

    def _excluir_molde_atual(self):
        if self._indice_atual is None:
            return
        if not (0 <= self._indice_atual < len(self.canvas.cena.elementos)):
            return
        del self.canvas.cena.elementos[self._indice_atual]
        if hasattr(self.canvas, "_registrar_historico"):
            self.canvas._registrar_historico()
        self.canvas.update()
        self._indice_atual = None
        self.recarregar_lista()

    def _escolher_cor(self):
        cor = QColorDialog.getColor(QColor(self._cor_visual), self, "Cor do molde")
        if not cor.isValid():
            return
        self._cor_visual = cor.name()
        self.btn_cor_preenchimento.setStyleSheet(f"background:{self._cor_visual}; border:1px solid #8a939c; padding:0;")
        molde = self._molde_atual()
        if molde:
            clone = dict(molde)
            clone["cor"] = self._cor_visual
            self.preview.set_molde(clone)


class Ferramenta(FerramentaBase):
    id_ferramenta = "propriedades"
    nome = "Propriedades"
    descricao_painel = "Abre a janela de propriedades dos moldes selecionados."

    _dialog_por_canvas: dict[int, PropriedadesMoldesDialog] = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        dialog = self._obter_dialog(canvas)
        dialog.recarregar_lista()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        if dialog._indice_atual is None:
            self.set_status("Nenhum molde disponível. Crie ou extraia um molde primeiro.")
        else:
            self.set_status("Janela de propriedades do molde aberta.")

    def _obter_dialog(self, canvas) -> PropriedadesMoldesDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is not None:
            return dialog
        parent = canvas.window() if hasattr(canvas, "window") else None
        dialog = PropriedadesMoldesDialog(canvas, parent)
        dialog.dados_aplicados.connect(lambda: self.set_status("Propriedades do molde aplicadas."))
        self._dialog_por_canvas[chave] = dialog
        return dialog
