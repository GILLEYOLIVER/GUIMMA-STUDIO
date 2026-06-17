from __future__ import annotations


from copy import deepcopy
from importlib import import_module
from math import atan2, cos, degrees, hypot, isfinite, radians, sin

from PySide6.QtCore import QLocale, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QStyledItemDelegate,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QMessageBox,
)

from core.graduacao import grade_graduacao_padrao, grade_graduacao_referencia_canvas
from core.formatacao import normalizar_decimal_ponto, numero_decimal_ponto
from tools.tool_base import FerramentaBase
from tools.unidades import SUFIXOS_MEDIDA, unidade_canvas, valor_cena_para_unidade, valor_unidade_para_cena
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


CORES_TAMANHOS_PADRAO_TABELA = {
    "PP": "#00ff00",
    "P": "#ffff00",
    "M": "#2b7cd3",
    "G": "#ffffff",
    "GG": "#ff00ff",
    "EXG": "#ff8c00",
    "XG": "#ff8c00",
    "EG": "#ff8c00",
    "G1": "#ff8c00",
    "G2": "#7b1fff",
}

GRADES_TAMANHOS_CORES_FIXAS = {
    "PP-G2(P)": {
        "PP": "#00ff00",
        "P": "#ffff00",
        "M": "#2b7cd3",
        "G": "#ffffff",
        "GG": "#ff00ff",
        "EXG": "#ff8c00",
        "G1": "#ff8c00",
        "G2": "#7b1fff",
    },
}


class TamanhoColorDelegate(QStyledItemDelegate):
    """Desenha a coluna Tamanho com a cor real da grade, sem a QSS apagar o fundo."""

    def paint(self, painter, option, index):  # noqa: N802
        if index.column() != 0:
            super().paint(painter, option, index)
            return

        cor = QColor(str(index.data(Qt.UserRole) or ""))
        if not cor.isValid():
            cor = QColor("#ffffff")

        painter.save()
        painter.fillRect(option.rect, cor)

        # Mantém uma borda leve para a coluna continuar legível.
        painter.setPen(QColor("#d2dbe5"))
        painter.drawLine(option.rect.topRight(), option.rect.bottomRight())
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

        fonte = index.data(Qt.FontRole)
        if isinstance(fonte, QFont):
            painter.setFont(fonte)
        painter.setPen(QColor("#000000"))
        painter.drawText(option.rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, str(index.data(Qt.DisplayRole) or ""))

        # Se a célula estiver selecionada, mostra só um contorno, sem trocar a cor do tamanho.
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor("#1f7ed6"), 2))
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
        painter.restore()


class MedidaCmSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._unidade_sigla = "cm"
        self._unidade_fator = 1.0
        self.setLocale(QLocale.c())
        self.setRange(0.0, 1000.0)
        self.setDecimals(3)
        self.setSingleStep(0.05)
        self.setSpecialValueText("")

    def set_unidade(self, sigla: str, fator: float) -> None:
        fator_antigo = max(1e-9, float(getattr(self, "_unidade_fator", 1.0)))
        valor_cena = float(self.value()) * fator_antigo
        self._unidade_sigla = str(sigla or "cm")
        self._unidade_fator = max(1e-9, float(fator or 1.0))
        self.blockSignals(True)
        self.setValue(valor_cena / self._unidade_fator)
        self.blockSignals(False)
        passo = 1.0 if self._unidade_sigla == "mm" else 0.05
        self.setSingleStep(passo)
        self.lineEdit().setPlaceholderText(self._unidade_sigla)

    def textFromValue(self, value: float) -> str:  # noqa: N802
        if abs(float(value or 0.0)) <= 1e-9:
            return ""
        return f"{float(value):.3f}".rstrip("0").rstrip(".")

    def valueFromText(self, text: str) -> float:  # noqa: N802
        texto = str(text or "").lower()
        try:
            return numero_decimal_ponto(texto, float(self.value()), SUFIXOS_MEDIDA)
        except ValueError:
            return float(self.value())

    def validate(self, text: str, pos: int):  # noqa: N802
        try:
            texto = normalizar_decimal_ponto(str(text or "").lower(), SUFIXOS_MEDIDA)
        except Exception:
            return QValidator.Invalid, text, pos
        if texto in {"", "+", "-", "0.", "+0.", "-0."}:
            return QValidator.Intermediate, text, pos
        try:
            float(texto)
        except Exception:
            return QValidator.Invalid, text, pos
        return QValidator.Acceptable, text, pos

    def valor_atual(self) -> float:
        texto = self.lineEdit().text() if self.lineEdit() is not None else ""
        valor = self.valueFromText(texto)
        if abs(valor) > 1e-9:
            self.setValue(valor)
            return valor * self._unidade_fator
        return float(self.value()) * self._unidade_fator


class GraduarTabelaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:graduar_tabela"
        self.setWindowTitle("Graduar via tabela")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        # Janela um pouco mais larga para a tabela respirar melhor e, na aba
        # Perímetro, abrir num formato mais confortável.
        self._largura_padrao = 460
        self._largura_perimetro = 690
        self.resize(self._largura_padrao, 585)
        self.setMinimumSize(435, 540)
        self._ferramenta = None
        self._canvas = None
        self._unidade_sigla = "cm"
        self._unidade_fator = 1.0
        self._bloquear_eventos = False
        self._base_row = 0
        self.setStyleSheet(
            """
            QDialog {
                background:#f4f7fb;
                color:#17202a;
                font-family:"Segoe UI", Arial, sans-serif;
                font-size:9pt;
            }
            QLabel, QCheckBox {
                color:#17202a;
            }
            QLabel#labelCampo {
                font-weight:600;
                color:#233142;
            }
            QLabel#labelUnidade {
                color:#5d6875;
                font-weight:600;
                padding-left:2px;
            }
            QComboBox, QDoubleSpinBox {
                background:#ffffff;
                color:#17202a;
                border:1px solid #bac6d3;
                border-radius:3px;
                min-height:24px;
                padding:2px 6px;
                selection-background-color:#2f7ed8;
                selection-color:#ffffff;
            }
            QComboBox:hover, QDoubleSpinBox:hover {
                border-color:#6aa9e9;
            }
            QComboBox:focus, QDoubleSpinBox:focus {
                border:1px solid #2374c8;
                background:#ffffff;
            }
            QTabWidget::pane {
                background:#ffffff;
                border:1px solid #b9c7d7;
                border-radius:3px;
                top:-1px;
            }
            QTabBar::tab {
                background:#e8eef5;
                color:#243447;
                border:1px solid #bdc9d6;
                padding:6px 10px;
                min-width:78px;
                font-weight:600;
            }
            QTabBar::tab:selected {
                background:#ffffff;
                color:#0078d4;
                border-top:2px solid #0078d4;
                border-bottom-color:#ffffff;
            }
            QTabBar::tab:hover:!selected {
                background:#f5f9ff;
            }
            QTableWidget {
                background:#ffffff;
                alternate-background-color:#f7f9fc;
                color:#111827;
                border:1px solid #b9c7d7;
                gridline-color:#dde4ec;
                selection-background-color:#2f7ed8;
                selection-color:#ffffff;
                outline:0;
            }
            QTableWidget::item {
                padding:3px 5px;
                border:0;
            }
            QTableWidget::item:selected {
                background:#2f7ed8;
                color:#000000;
            }
            QHeaderView::section {
                background:#f0f4f8;
                color:#111827;
                border:0;
                border-right:1px solid #d2dbe5;
                border-bottom:1px solid #c7d2de;
                padding:5px 4px;
                font-weight:700;
            }
            QWidget#painelComandos {
                background:#eef3f8;
                border:1px solid #cbd6e2;
                border-radius:6px;
            }
            QWidget#painelSetas {
                background:#e6edf5;
                border:1px solid #c4d0dd;
                border-radius:4px;
            }
            QPushButton {
                background:#ffffff;
                color:#17202a;
                border:1px solid #b7c3d0;
                border-radius:3px;
                min-height:26px;
                padding:3px 8px;
                font-weight:500;
            }
            QPushButton:hover {
                background:#eef6ff;
                border-color:#6aa9e9;
            }
            QPushButton:pressed {
                background:#2f7ed8;
                color:#ffffff;
                border-color:#1d63a9;
                padding-top:4px;
                padding-left:9px;
            }
            QPushButton#botaoPrincipal {
                background:#0078d4;
                color:#ffffff;
                border-color:#006bbd;
                font-weight:700;
            }
            QPushButton#botaoPrincipal:hover {
                background:#0d86e4;
            }
            QPushButton#botaoSeta {
                min-width:28px;
                max-width:28px;
                min-height:24px;
                max-height:24px;
                padding:0;
                font-weight:800;
            }
            QPushButton#botaoCentro {
                min-width:28px;
                max-width:28px;
                min-height:24px;
                max-height:24px;
                padding:0;
                font-weight:700;
                background:#f9fbfd;
            }
            """
        )
        self._construir_ui()

    def _construir_ui(self):
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(10, 10, 10, 10)
        raiz.setSpacing(8)

        linha_ponto = QHBoxLayout()
        linha_ponto.setSpacing(8)
        lbl_ponto = QLabel("Nº ponto")
        lbl_ponto.setObjectName("labelCampo")
        linha_ponto.addWidget(lbl_ponto)
        self.cmb_ponto = QComboBox()
        self.cmb_ponto.setMinimumHeight(26)
        self.cmb_ponto.currentIndexChanged.connect(self._ponto_alterado)
        linha_ponto.addWidget(self.cmb_ponto, 1)
        raiz.addLayout(linha_ponto)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self.tabs = tabs

        pagina_dxdy = QWidget()
        lay_dxdy = QVBoxLayout(pagina_dxdy)
        lay_dxdy.setContentsMargins(6, 6, 6, 6)
        lay_dxdy.setSpacing(0)
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Tamanho", "DX (cm)", "DY (cm)"])
        self._configurar_tabela_valores(self.tbl)
        self._delegate_tamanho_dxdy = TamanhoColorDelegate(self.tbl)
        self.tbl.setItemDelegateForColumn(0, self._delegate_tamanho_dxdy)
        self.tbl.itemChanged.connect(self._celula_alterada)
        lay_dxdy.addWidget(self.tbl)
        tabs.addTab(pagina_dxdy, "DX / DY")

        pagina_dist = QWidget()
        lay_dist = QVBoxLayout(pagina_dist)
        lay_dist.setContentsMargins(6, 6, 6, 6)
        lay_dist.setSpacing(0)
        self.tbl_polar = QTableWidget(0, 3)
        self.tbl_polar.setHorizontalHeaderLabels(["Tamanho", "Dist.(cm)", "Ang°"])
        self._configurar_tabela_valores(self.tbl_polar)
        self._delegate_tamanho_polar = TamanhoColorDelegate(self.tbl_polar)
        self.tbl_polar.setItemDelegateForColumn(0, self._delegate_tamanho_polar)
        self.tbl_polar.itemChanged.connect(self._celula_polar_alterada)
        lay_dist.addWidget(self.tbl_polar)
        tabs.addTab(pagina_dist, "Distância / Ângulo")

        pagina_perimetro = QWidget()
        lay_perimetro = QVBoxLayout(pagina_perimetro)
        lay_perimetro.setContentsMargins(6, 6, 6, 6)
        lay_perimetro.setSpacing(0)
        self.tbl_perimetro = QTableWidget(0, 7)
        self.tbl_perimetro.setHorizontalHeaderLabels(
            ["Tamanho", "Perim. X", "Dif. X", "Perim. Y", "Dif. Y", "Total", "Dif. total"]
        )
        self._configurar_tabela_valores(self.tbl_perimetro, leitura=True)
        self._delegate_tamanho_perimetro = TamanhoColorDelegate(self.tbl_perimetro)
        self.tbl_perimetro.setItemDelegateForColumn(0, self._delegate_tamanho_perimetro)
        self._configurar_tabela_perimetro()
        lay_perimetro.addWidget(self.tbl_perimetro)
        tabs.addTab(pagina_perimetro, "Perímetro")
        raiz.addWidget(tabs, 1)

        painel = QWidget()
        painel.setObjectName("painelComandos")
        painel_lay = QVBoxLayout(painel)
        painel_lay.setContentsMargins(8, 8, 8, 8)
        painel_lay.setSpacing(6)

        botoes_topo = QGridLayout()
        botoes_topo.setHorizontalSpacing(5)
        botoes_topo.setVerticalSpacing(5)
        self.btn_aplicar = self._criar_botao("Aplicar", destaque=True)
        self.btn_zerar_dx = self._criar_botao("DX")
        self.btn_zerar_dy = self._criar_botao("DY")
        self.btn_aplicar.setToolTip("Aplicar a graduação do ponto selecionado")
        self.btn_zerar_dx.setToolTip("Zerar a coluna DX da aba atual")
        self.btn_zerar_dy.setToolTip("Zerar a coluna DY da aba atual")
        self.btn_aplicar.clicked.connect(self._aplicar)
        self.btn_zerar_dx.clicked.connect(lambda: self._preencher_coluna_atual(1, 0.0))
        self.btn_zerar_dy.clicked.connect(lambda: self._preencher_coluna_atual(2, 0.0))
        botoes_topo.addWidget(self.btn_aplicar, 0, 0)
        botoes_topo.addWidget(self.btn_zerar_dx, 0, 1)
        botoes_topo.addWidget(self.btn_zerar_dy, 0, 2)
        botoes_topo.setColumnStretch(0, 1)
        botoes_topo.setColumnStretch(1, 1)
        botoes_topo.setColumnStretch(2, 1)
        painel_lay.addLayout(botoes_topo)
        tabs.currentChanged.connect(self._aba_alterada)

        linha_inc = QHBoxLayout()
        linha_inc.setSpacing(6)
        self.chk_incremental = QCheckBox("Incremental")
        self.chk_incremental.setChecked(True)
        self.chk_incremental.setToolTip("Quando marcado, distribui o valor por tamanho a partir do tamanho base")
        self.sp_incremento = MedidaCmSpinBox()
        self.sp_incremento.setMinimumHeight(26)
        self.sp_incremento.setMinimumWidth(128)
        self.sp_incremento.setToolTip("Valor usado pelas setas de incremento")
        self.lbl_unidade_incremento = QLabel("(cm)")
        self.lbl_unidade_incremento.setObjectName("labelUnidade")
        linha_inc.addWidget(self.chk_incremental)
        linha_inc.addWidget(self.sp_incremento, 1)
        linha_inc.addWidget(self.lbl_unidade_incremento)

        painel_setas = QWidget()
        painel_setas.setObjectName("painelSetas")
        grade_setas = QGridLayout(painel_setas)
        grade_setas.setContentsMargins(4, 4, 4, 4)
        grade_setas.setHorizontalSpacing(3)
        grade_setas.setVerticalSpacing(3)
        self.btn_cima = self._criar_botao_seta("▲")
        self.btn_baixo = self._criar_botao_seta("▼")
        self.btn_esq = self._criar_botao_seta("◀")
        self.btn_dir = self._criar_botao_seta("▶")
        self.btn_zero = self._criar_botao_seta("0", centro=True)
        self.btn_cima.setToolTip("Aplicar incremento para cima")
        self.btn_baixo.setToolTip("Aplicar incremento para baixo")
        self.btn_esq.setToolTip("Aplicar incremento para a esquerda")
        self.btn_dir.setToolTip("Aplicar incremento para a direita")
        self.btn_zero.setToolTip("Zerar DX e DY")
        self.btn_cima.pressed.connect(lambda: self._aplicar_incremento(0.0, -1.0))
        self.btn_baixo.pressed.connect(lambda: self._aplicar_incremento(0.0, 1.0))
        self.btn_esq.pressed.connect(lambda: self._aplicar_incremento(-1.0, 0.0))
        self.btn_dir.pressed.connect(lambda: self._aplicar_incremento(1.0, 0.0))
        self.btn_zero.pressed.connect(lambda: self._aplicar_incremento(0.0, 0.0, zerar=True))
        grade_setas.addWidget(self.btn_cima, 0, 1)
        grade_setas.addWidget(self.btn_esq, 1, 0)
        grade_setas.addWidget(self.btn_zero, 1, 1)
        grade_setas.addWidget(self.btn_dir, 1, 2)
        grade_setas.addWidget(self.btn_baixo, 2, 1)
        linha_inc.addWidget(painel_setas, 0, Qt.AlignRight)
        painel_lay.addLayout(linha_inc)

        botoes_igual = QGridLayout()
        botoes_igual.setHorizontalSpacing(5)
        botoes_igual.setVerticalSpacing(5)
        self.btn_igual_dx = self._criar_botao("= DX")
        self.btn_igual_dy = self._criar_botao("= DY")
        self.btn_igual_dxdy = self._criar_botao("= DX = DY")
        self.btn_igual_dx.setToolTip("Usar o valor incremental para preencher DX")
        self.btn_igual_dy.setToolTip("Usar o valor incremental para preencher DY")
        self.btn_igual_dxdy.setToolTip("Usar o valor incremental para preencher DX e DY")
        self.btn_igual_dx.clicked.connect(lambda: self._aplicar_incremento_direto(1))
        self.btn_igual_dy.clicked.connect(lambda: self._aplicar_incremento_direto(2))
        self.btn_igual_dxdy.clicked.connect(lambda: self._aplicar_incremento_direto(None))
        botoes_igual.addWidget(self.btn_igual_dx, 0, 0)
        botoes_igual.addWidget(self.btn_igual_dy, 0, 1)
        botoes_igual.addWidget(self.btn_igual_dxdy, 0, 2)
        for col in range(3):
            botoes_igual.setColumnStretch(col, 1)
        painel_lay.addLayout(botoes_igual)

        botoes_copia = QGridLayout()
        botoes_copia.setHorizontalSpacing(5)
        botoes_copia.setVerticalSpacing(5)
        self.btn_copiar_graduacao = self._criar_botao("Copiar")
        self.btn_copiar_graduacao.setToolTip("Copiar graduação do ponto atual")
        self.btn_copiar_graduacao.clicked.connect(self._copiar)
        self.btn_colar_graduacao = self._criar_botao("Colar")
        self.btn_colar_graduacao.setToolTip("Colar graduação copiada")
        self.btn_colar_graduacao.clicked.connect(self._colar)
        self.btn_colar_relativo = self._criar_botao("Colar rel.")
        self.btn_colar_relativo.setToolTip("Somar a graduação copiada aos valores atuais")
        self.btn_colar_relativo.clicked.connect(self._colar_relativo)
        botoes_copia.addWidget(self.btn_copiar_graduacao, 0, 0)
        botoes_copia.addWidget(self.btn_colar_graduacao, 1, 0)
        botoes_copia.addWidget(self.btn_colar_relativo, 2, 0)
        for texto, dica, slot, linha, col in (
            ("Inverte DX", "Inverter o sinal da coluna DX", lambda: self._inverter_coluna(1), 0, 1),
            ("Inverte DY", "Inverter o sinal da coluna DY", lambda: self._inverter_coluna(2), 0, 2),
            ("Colar DX", "Colar apenas a coluna DX", lambda: self._colar_coluna(1), 1, 1),
            ("Colar DY", "Colar apenas a coluna DY", lambda: self._colar_coluna(2), 1, 2),
            ("Colar rel. DX", "Somar apenas a coluna DX copiada", lambda: self._colar_coluna_relativa(1), 2, 1),
            ("Colar rel. DY", "Somar apenas a coluna DY copiada", lambda: self._colar_coluna_relativa(2), 2, 2),
        ):
            btn = self._criar_botao(texto)
            btn.setToolTip(dica)
            btn.clicked.connect(slot)
            botoes_copia.addWidget(btn, linha, col)
        for col in range(3):
            botoes_copia.setColumnStretch(col, 1)
        painel_lay.addLayout(botoes_copia)
        raiz.addWidget(painel)

        self._aba_alterada(0)
        self._atualizar_cabecalhos_unidade()

    def _configurar_tabela_valores(self, tabela: QTableWidget, *, leitura: bool = False) -> None:
        tabela.verticalHeader().setVisible(False)
        tabela.verticalHeader().setDefaultSectionSize(28)
        tabela.verticalHeader().setMinimumSectionSize(26)
        tabela.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        tabela.horizontalHeader().setHighlightSections(False)
        tabela.setAlternatingRowColors(True)
        tabela.setShowGrid(True)
        tabela.setWordWrap(False)
        tabela.setCornerButtonEnabled(False)
        tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        tabela.setSelectionBehavior(QAbstractItemView.SelectItems)
        tabela.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tabela.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tabela.setItemDelegateForColumn(0, TamanhoColorDelegate(tabela))
        if leitura:
            tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        else:
            tabela.setEditTriggers(
                QAbstractItemView.DoubleClicked
                | QAbstractItemView.SelectedClicked
                | QAbstractItemView.EditKeyPressed
            )
        tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in range(1, tabela.columnCount()):
            tabela.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)

    @staticmethod
    def _cor_tamanho_dialog(dados: dict | None, nome: str) -> str:
        nome_txt = str(nome or "").strip()
        nome_upper = nome_txt.upper()
        cor_atual = QColor()
        if isinstance(dados, dict):
            for chave in ("cor", "color", "cor_tamanho", "cor_grade", "cor_fundo", "background"):
                cor_tentativa = QColor(str(dados.get(chave) or ""))
                if cor_tentativa.isValid():
                    cor_atual = cor_tentativa
                    break
        cor_padrao_txt = (
            CORES_TAMANHOS_PADRAO_TABELA.get(nome_txt)
            or CORES_TAMANHOS_PADRAO_TABELA.get(nome_upper)
            or CORES_TAMANHOS_PADRAO_TABELA.get(nome_upper.replace("XG", "EXG"))
            or CORES_TAMANHOS_PADRAO_TABELA.get(nome_upper.replace("G1", "EXG"))
            or ""
        )
        cor_padrao = QColor(str(cor_padrao_txt or ""))

        # Se veio uma cor real das propriedades, preserva.
        # Se veio branco/vazio para um tamanho que tem cor oficial, aplica a cor oficial.
        if cor_atual.isValid() and cor_atual.name().lower() != "#ffffff":
            return cor_atual.name()
        if cor_padrao.isValid():
            return cor_padrao.name()
        return cor_atual.name() if cor_atual.isValid() else ""

    def _configurar_tabela_perimetro(self) -> None:
        tabela = self.tbl_perimetro
        header = tabela.horizontalHeader()
        header.setMinimumSectionSize(64)
        header.setSectionResizeMode(QHeaderView.Interactive)
        larguras = {0: 84, 1: 92, 2: 92, 3: 92, 4: 92, 5: 96, 6: 108}
        for col, largura in larguras.items():
            tabela.setColumnWidth(col, largura)

    def _criar_botao(self, texto: str, *, destaque: bool = False) -> QPushButton:
        btn = QPushButton(texto)
        btn.setMinimumHeight(28)
        btn.setCursor(Qt.PointingHandCursor)
        if destaque:
            btn.setObjectName("botaoPrincipal")
        return btn

    def _criar_botao_seta(self, texto: str, *, centro: bool = False) -> QPushButton:
        btn = QPushButton(texto)
        btn.setObjectName("botaoCentro" if centro else "botaoSeta")
        btn.setFixedSize(28, 24)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def conectar(self, ferramenta, canvas):
        self._ferramenta = ferramenta
        self._canvas = canvas
        self.set_unidade(*unidade_canvas(canvas))

    def set_unidade(self, sigla: str, fator: float) -> None:
        self._unidade_sigla = str(sigla or "cm")
        self._unidade_fator = max(1e-9, float(fator or 1.0))
        self.sp_incremento.set_unidade(self._unidade_sigla, self._unidade_fator)
        self._atualizar_cabecalhos_unidade()

    def _atualizar_cabecalhos_unidade(self) -> None:
        unidade = self._unidade_sigla
        self.tbl.setHorizontalHeaderLabels(["Tamanho", f"DX ({unidade})", f"DY ({unidade})"])
        self.tbl_polar.setHorizontalHeaderLabels(["Tamanho", f"Dist. ({unidade})", "Ang°"])
        self.tbl_perimetro.setHorizontalHeaderLabels(
            [
                "Tamanho",
                f"Perim. X ({unidade})",
                f"Dif. X ({unidade})",
                f"Perim. Y ({unidade})",
                f"Dif. Y ({unidade})",
                f"Total ({unidade})",
                f"Dif. total ({unidade})",
            ]
        )
        if hasattr(self, "lbl_unidade_incremento"):
            self.lbl_unidade_incremento.setText(f"({unidade})")

    def _para_unidade(self, valor_cena: float) -> float:
        if self._canvas is not None:
            return valor_cena_para_unidade(self._canvas, valor_cena)
        return float(valor_cena) / self._unidade_fator

    def _para_cena(self, valor_unidade: float) -> float:
        if self._canvas is not None:
            return valor_unidade_para_cena(self._canvas, valor_unidade)
        return float(valor_unidade) * self._unidade_fator

    def _formatar_medida(self, valor_cena: float, casas: int = 3) -> str:
        return self._formatar_float(self._para_unidade(valor_cena), casas=casas)

    def definir_pontos(self, quantidade: int, atual: int | None):
        self._bloquear_eventos = True
        self.cmb_ponto.clear()
        for idx in range(max(0, int(quantidade))):
            self.cmb_ponto.addItem(str(idx + 1), idx)
        if atual is not None and 0 <= int(atual) < self.cmb_ponto.count():
            self.cmb_ponto.setCurrentIndex(int(atual))
        self._bloquear_eventos = False

    def definir_tamanhos(self, tamanhos: list[dict], valores: dict[str, dict]):
        self._bloquear_eventos = True
        self.tbl.setRowCount(len(tamanhos))
        self.tbl_polar.setRowCount(len(tamanhos))
        base_row = next((i for i, t in enumerate(tamanhos) if t.get("base")), len(tamanhos) // 2 if tamanhos else 0)
        self._base_row = base_row
        for row, tamanho in enumerate(tamanhos):
            nome = str(tamanho.get("tamanho") or tamanho.get("nome") or f"T{row + 1}")
            item_t = QTableWidgetItem(nome)
            item_t.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_t.setTextAlignment(Qt.AlignCenter)
            cor = self._cor_tamanho_dialog(tamanho, nome)
            item_t.setData(Qt.UserRole, cor)
            item_t.setData(Qt.UserRole + 1, row == base_row)
            if cor:
                self._aplicar_cor_tamanho(item_t, cor)
            if row == base_row:
                self._destacar_item_tamanho_base(item_t, cor)
            self.tbl.setItem(row, 0, item_t)
            item_polar_t = QTableWidgetItem(nome)
            item_polar_t.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_polar_t.setTextAlignment(Qt.AlignCenter)
            item_polar_t.setData(Qt.UserRole, cor)
            item_polar_t.setData(Qt.UserRole + 1, row == base_row)
            if cor:
                self._aplicar_cor_tamanho(item_polar_t, cor)
            if row == base_row:
                self._destacar_item_tamanho_base(item_polar_t, cor)
            self.tbl_polar.setItem(row, 0, item_polar_t)

            dados = valores.get(nome, {}) if isinstance(valores, dict) else {}
            for col, chave in ((1, "dx"), (2, "dy")):
                item = QTableWidgetItem(self._formatar_medida(dados.get(chave, 0.0)))
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                if row == base_row:
                    self._destacar_item_valor_base(item)
                self.tbl.setItem(row, col, item)
            self._sincronizar_polar_linha(row)
        self._bloquear_eventos = False

    def valores(self) -> dict[str, dict]:
        saida: dict[str, dict] = {}
        for row in range(self.tbl.rowCount()):
            nome_item = self.tbl.item(row, 0)
            if nome_item is None:
                continue
            nome = nome_item.text().strip()
            if not nome:
                continue
            saida[nome] = {
                "dx": self._valor_item(row, 1),
                "dy": self._valor_item(row, 2),
            }
        return saida

    def definir_perimetros(self, linhas: list[dict]) -> None:
        self._bloquear_eventos = True
        self.tbl_perimetro.setRowCount(len(linhas))
        for row, linha in enumerate(linhas):
            cor = self._cor_tamanho_dialog(linha, str(linha.get("tamanho") or ""))
            base = bool(linha.get("base", False))
            item_t = QTableWidgetItem(str(linha.get("tamanho") or ""))
            item_t.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_t.setTextAlignment(Qt.AlignCenter)
            item_t.setData(Qt.UserRole, cor)
            item_t.setData(Qt.UserRole + 1, base)
            if cor:
                self._aplicar_cor_tamanho(item_t, cor)
            if base:
                self._destacar_item_tamanho_base(item_t, cor)
            self.tbl_perimetro.setItem(row, 0, item_t)
            for col, chave in (
                (1, "perimetro_x"),
                (2, "diferenca_x"),
                (3, "perimetro_y"),
                (4, "diferenca_y"),
                (5, "perimetro"),
                (6, "diferenca"),
            ):
                item = QTableWidgetItem(self._formatar_medida(linha.get(chave, 0.0), casas=2))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setTextAlignment(Qt.AlignCenter)
                if base:
                    self._destacar_item_valor_base(item)
                self.tbl_perimetro.setItem(row, col, item)
        self._bloquear_eventos = False

    def _ponto_alterado(self):
        if self._bloquear_eventos or self._ferramenta is None or self._canvas is None:
            return
        idx = self.cmb_ponto.currentData()
        self._ferramenta.selecionar_ponto(self._canvas, int(idx) if idx is not None else None)

    def _celula_alterada(self, item):
        if self._bloquear_eventos:
            return
        if item is not None and item.column() in (1, 2):
            self._bloquear_eventos = True
            self._sincronizar_polar_linha(item.row())
            self._bloquear_eventos = False
        if self._ferramenta is not None and self._canvas is not None:
            self._ferramenta.atualizar_preview_dialog(self._canvas)

    def _celula_polar_alterada(self, item):
        if self._bloquear_eventos:
            return
        if item is None or item.column() not in (1, 2):
            return
        self._bloquear_eventos = True
        self._sincronizar_dxdy_linha_de_polar(item.row())
        self._bloquear_eventos = False
        if self._ferramenta is not None and self._canvas is not None:
            self._ferramenta.atualizar_preview_dialog(self._canvas)

    def _aplicar(self):
        if self._ferramenta is not None and self._canvas is not None:
            self._ferramenta.aplicar_dialog(self._canvas)

    def _preencher_coluna(self, col: int, valor: float):
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            item = self.tbl.item(row, col)
            if item is not None:
                self._set_valor(row, col, valor)
                self._sincronizar_polar_linha(row)
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _aplicar_incremento(self, dx_dir: float, dy_dir: float, *, zerar: bool = False):
        row_atual = self.tbl.currentRow()
        if row_atual < 0:
            row_atual = 0
        base_row = self._linha_base()
        incremento = float(self.sp_incremento.valor_atual())
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            if zerar:
                self._set_valor(row, 1, 0.0)
                self._set_valor(row, 2, 0.0)
                self._sincronizar_polar_linha(row)
                continue
            elif self.chk_incremental.isChecked():
                fator = row - base_row
                dx = dx_dir * incremento * fator
                dy = dy_dir * incremento * fator
            elif row == row_atual:
                dx = dx_dir * incremento
                dy = dy_dir * incremento
            else:
                continue
            if abs(dx_dir) > 1e-9:
                self._set_valor(row, 1, dx)
            if abs(dy_dir) > 1e-9:
                self._set_valor(row, 2, dy)
            self._sincronizar_polar_linha(row)
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _aplicar_incremento_direto(self, col: int | None):
        row_atual = self.tbl.currentRow()
        if row_atual < 0:
            row_atual = self._linha_base()
        base_row = self._linha_base()
        incremento = float(self.sp_incremento.valor_atual())
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            if self.chk_incremental.isChecked():
                valor = incremento * (row - base_row)
            elif row == row_atual:
                valor = incremento
            else:
                continue
            if col in (None, 1):
                self._set_valor(row, 1, valor)
            if col in (None, 2):
                self._set_valor(row, 2, valor)
            self._sincronizar_polar_linha(row)
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _copiar(self):
        self._copiado = self.valores()
        if self._ferramenta is not None and self._canvas is not None:
            self._ferramenta.iniciar_copia_graduacao(self._canvas)

    def _colar(self):
        dados = getattr(self, "_copiado", None)
        if not isinstance(dados, dict):
            return
        self.definir_tamanhos(self._tamanhos_atuais(), dados)
        self._celula_alterada(None)

    def _colar_coluna(self, col: int):
        dados = getattr(self, "_copiado", None)
        if not isinstance(dados, dict):
            return
        chave = "dx" if col == 1 else "dy"
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            nome_item = self.tbl.item(row, 0)
            if nome_item is None:
                continue
            valor = dados.get(nome_item.text().strip(), {}).get(chave, 0.0)
            self._set_valor(row, col, valor)
            self._sincronizar_polar_linha(row)
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _colar_relativo(self):
        dados = getattr(self, "_copiado", None)
        if not isinstance(dados, dict):
            return
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            nome_item = self.tbl.item(row, 0)
            if nome_item is None:
                continue
            nome = nome_item.text().strip()
            origem = dados.get(nome, {})
            if not isinstance(origem, dict):
                origem = {}
            self._set_valor(row, 1, self._valor_item(row, 1) + self._float_item_graduacao(origem.get("dx", 0.0)))
            self._set_valor(row, 2, self._valor_item(row, 2) + self._float_item_graduacao(origem.get("dy", 0.0)))
            self._sincronizar_polar_linha(row)
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _colar_coluna_relativa(self, col: int):
        dados = getattr(self, "_copiado", None)
        if not isinstance(dados, dict):
            return
        chave = "dx" if col == 1 else "dy"
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            nome_item = self.tbl.item(row, 0)
            if nome_item is None:
                continue
            origem = dados.get(nome_item.text().strip(), {})
            if not isinstance(origem, dict):
                origem = {}
            self._set_valor(row, col, self._valor_item(row, col) + self._float_item_graduacao(origem.get(chave, 0.0)))
            self._sincronizar_polar_linha(row)
        self._bloquear_eventos = False
        self._celula_alterada(None)

    @staticmethod
    def _float_item_graduacao(valor) -> float:
        try:
            return float(valor or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _preencher_coluna_atual(self, col: int, valor: float):
        if self._aba_polar_ativa():
            self._bloquear_eventos = True
            for row in range(self.tbl_polar.rowCount()):
                self._set_valor_polar(row, col, valor, casas=2 if col == 1 else 3)
                self._sincronizar_dxdy_linha_de_polar(row)
            self._bloquear_eventos = False
            self._celula_polar_alterada(None)
            return
        self._preencher_coluna(col, valor)

    def _aba_polar_ativa(self) -> bool:
        return getattr(self, "tabs", None) is not None and self.tabs.currentIndex() == 1

    def _aba_alterada(self, idx: int):
        polar = int(idx) == 1
        perimetro = int(idx) == 2
        self.btn_zerar_dx.setText("Dist." if polar else "DX")
        self.btn_zerar_dy.setText("Âng." if polar else "DY")
        self.btn_zerar_dx.setToolTip("Zerar a distância" if polar else "Zerar a coluna DX")
        self.btn_zerar_dy.setToolTip("Zerar o ângulo" if polar else "Zerar a coluna DY")
        largura_alvo = self._largura_perimetro if perimetro else self._largura_padrao
        if self.width() != largura_alvo:
            self.resize(largura_alvo, self.height())

    def _inverter_coluna(self, col: int):
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            self._set_valor(row, col, -self._valor_item(row, col))
            self._sincronizar_polar_linha(row)
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _tamanhos_atuais(self) -> list[dict]:
        saida = []
        base_row = self._linha_base()
        for row in range(self.tbl.rowCount()):
            item = self.tbl.item(row, 0)
            if item is not None:
                cor_item = item.data(Qt.UserRole)
                cor_texto = str(cor_item or "").strip() or item.background().color().name()
                saida.append({
                    "tamanho": item.text().strip(),
                    "cor": cor_texto,
                    "base": row == base_row,
                })
        return saida

    def _linha_base(self) -> int:
        if 0 <= int(getattr(self, "_base_row", 0)) < self.tbl.rowCount():
            return int(self._base_row)
        return self.tbl.rowCount() // 2 if self.tbl.rowCount() else 0

    def _valor_item(self, row: int, col: int) -> float:
        item = self.tbl.item(row, col)
        if item is None:
            return 0.0
        return self._para_cena(numero_decimal_ponto(item.text(), 0.0, SUFIXOS_MEDIDA))

    def _set_valor(self, row: int, col: int, valor: float):
        item = self.tbl.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tbl.setItem(row, col, item)
        item.setText(self._formatar_medida(valor))
        item.setTextAlignment(Qt.AlignCenter)
        if row == self._linha_base():
            self._destacar_item_valor_base(item)

    def _set_valor_polar(self, row: int, col: int, valor: float, *, casas: int = 3):
        item = self.tbl_polar.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tbl_polar.setItem(row, col, item)
        texto = self._formatar_medida(valor, casas=casas) if col == 1 else self._formatar_float(valor, casas=casas)
        item.setText(texto)
        item.setTextAlignment(Qt.AlignCenter)
        if row == self._linha_base():
            self._destacar_item_valor_base(item)

    def _sincronizar_polar_linha(self, row: int) -> None:
        if not (0 <= int(row) < self.tbl.rowCount()):
            return
        dx = self._valor_item(row, 1)
        dy = self._valor_item(row, 2)
        distancia = hypot(dx, dy)
        angulo = 0.0 if distancia <= 1e-9 else degrees(atan2(dy, dx)) % 360.0
        self._set_valor_polar(row, 1, distancia, casas=2)
        self._set_valor_polar(row, 2, angulo, casas=3)

    def _sincronizar_dxdy_linha_de_polar(self, row: int) -> None:
        if not (0 <= int(row) < self.tbl_polar.rowCount()):
            return
        distancia = self._valor_item_polar(row, 1)
        angulo = self._valor_item_polar(row, 2)
        dx = distancia * cos(radians(angulo))
        dy = distancia * sin(radians(angulo))
        if abs(dx) < 1e-9:
            dx = 0.0
        if abs(dy) < 1e-9:
            dy = 0.0
        self._set_valor(row, 1, dx)
        self._set_valor(row, 2, dy)

    def _valor_item_polar(self, row: int, col: int) -> float:
        item = self.tbl_polar.item(row, col)
        if item is None:
            return 0.0
        valor = numero_decimal_ponto(item.text(), 0.0, SUFIXOS_MEDIDA)
        return self._para_cena(valor) if col == 1 else valor

    @staticmethod
    def _aplicar_cor_tamanho(item: QTableWidgetItem, cor: str):
        cor_base = QColor(str(cor or ""))
        if not cor_base.isValid():
            cor_base = QColor("#ffffff")
        item.setData(Qt.UserRole, cor_base.name())
        item.setData(Qt.BackgroundRole, cor_base)
        item.setData(Qt.ForegroundRole, QColor("#000000"))
        item.setBackground(cor_base)
        item.setForeground(QColor("#000000"))

    @staticmethod
    def _destacar_item_tamanho_base(item: QTableWidgetItem, cor: str):
        fonte = item.font()
        fonte.setBold(True)
        fonte.setUnderline(True)
        item.setFont(fonte)
        item.setData(Qt.UserRole + 1, True)
        cor_base = QColor(str(cor or item.data(Qt.UserRole) or ""))
        if not cor_base.isValid():
            cor_base = QColor("#ffffff")
        item.setData(Qt.UserRole, cor_base.name())
        item.setData(Qt.BackgroundRole, cor_base)
        item.setData(Qt.ForegroundRole, QColor("#000000"))
        item.setBackground(cor_base)
        item.setForeground(QColor("#000000"))

    @staticmethod
    def _destacar_item_valor_base(item: QTableWidgetItem):
        fonte = item.font()
        fonte.setBold(True)
        item.setFont(fonte)
        item.setForeground(QColor("#000000"))
        item.setData(Qt.ForegroundRole, QColor("#000000"))
        cor_base = QColor("#d9ecff")
        item.setBackground(cor_base)
        item.setData(Qt.BackgroundRole, cor_base)

    @staticmethod
    def _formatar_float(valor, casas: int = 3) -> str:
        try:
            numero = float(valor or 0.0)
        except (TypeError, ValueError):
            numero = 0.0
        texto = f"{numero:.{max(0, int(casas))}f}".rstrip("0").rstrip(".")
        return "0" if texto in {"", "-0"} else texto


class Ferramenta(FerramentaBase):
    id_ferramenta = "tabela"
    nome = "Tabela"
    descricao_painel = "Configura graduação DX/DY por tamanho nos pontos do contorno do molde."

    _dialog_por_canvas: dict[int, GraduarTabelaDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._molde_chave: str | None = None
        self._ponto_idx: int | None = None
        self._hover_ponto_idx: int | None = None
        self._pontos_selecionados: set[int] = set()
        self._canvas_observados: set[int] = set()
        self._dialog_propriedades_observados: set[tuple[int, int]] = set()
        self._modo_copia_graduacao = False
        self._graduacao_copiada: dict | None = None
        self._origem_copia: tuple[int, int] | None = None
        self._atualizacoes_canvas_agendadas: set[int] = set()

    def on_activate(self, canvas):
        super().on_activate(canvas)
        molde_inicial = self._molde_selecionado(canvas)
        if molde_inicial is None:
            molde_inicial = self._molde_referencia_inicial(canvas)
        bloquear_tabela = False
        if molde_inicial is not None and not self._preparar_molde_para_tabela(canvas, molde_inicial, permitir_propriedades=False):
            bloquear_tabela = self._molde_precisa_definir_grade(canvas, molde_inicial)
            molde_inicial = None
        self._definir_molde_idx(canvas, molde_inicial)
        self._ponto_idx = None
        self._hover_ponto_idx = None
        self._pontos_selecionados.clear()
        if self._molde_idx is not None and hasattr(canvas, "_selecionados"):
            canvas._selecionados = {self._molde_idx}
        self._observar_canvas(canvas)
        if bloquear_tabela:
            self._ocultar_dialog(canvas)
            self._status(canvas, "Tabela: defina a grade do molde separado antes de graduar.")
            return
        dialog = self._obter_dialog(canvas)
        dialog.conectar(self, canvas)
        self._atualizar_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Tabela: clique em um molde; depois clique no ponto do contorno para graduar.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._hover_ponto_idx = None
        if canvas is not None:
            canvas.update()

    def on_unidade_medida_alterada(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is None:
            return
        dialog.conectar(self, canvas)
        self._atualizar_dialog(canvas)
        self._repintar_canvas_agora(canvas)

    def on_mouse_press(self, canvas, event) -> bool:
        acumular = self._evento_ctrl(event)
        if event.button() == Qt.RightButton and not acumular:
            self._fechar(canvas)
            event.accept()
            return True
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return False
        pos = canvas._ponto_com_snap(event.position()) if hasattr(canvas, "_ponto_com_snap") else QPointF(event.position())
        alvo = self._molde_e_ponto_em_posicao(canvas, pos)
        molde_idx = alvo[0] if alvo is not None else self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            self._status(canvas, "Tabela: clique sobre um molde graduável.")
            event.accept()
            return True
        if not self._preparar_molde_para_tabela(canvas, molde_idx):
            event.accept()
            return True
        if self._processar_clique_modo_copia(canvas, molde_idx, alvo, pos):
            event.accept()
            return True
        if molde_idx != self._molde_idx:
            self._selecionar_molde(canvas, molde_idx)
            self._status(canvas, "Tabela: molde selecionado; passe o mouse nos pontos e clique no ponto para graduar.")
            event.accept()
            return True
        if alvo is None:
            self._selecionar_molde(canvas, molde_idx)
            self._status(canvas, "Tabela: molde selecionado; clique diretamente em um ponto para graduar.")
            event.accept()
            return True
        ponto_idx = alvo[1] if alvo is not None else self._ponto_mais_proximo(canvas.cena.elementos[molde_idx], pos)
        if ponto_idx is not None:
            self._selecionar_ponto_contorno(canvas, ponto_idx, acumular=acumular)
        self._atualizar_dialog(canvas)
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        molde = self._molde_atual(canvas)
        hover_idx = None
        if molde is not None:
            pos = canvas._ponto_com_snap(event.position()) if hasattr(canvas, "_ponto_com_snap") else QPointF(event.position())
            hover_idx = self._ponto_hover(molde, pos, canvas)
        if hover_idx == self._hover_ponto_idx:
            return False
        self._hover_ponto_idx = hover_idx
        if hasattr(canvas, "update"):
            canvas.update()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._molde_idx is None:
            return
        if not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return
        molde = canvas.cena.elementos[self._molde_idx]
        pontos = self._pontos_contorno(molde)
        selecionados = self._pontos_validos_selecionados(len(pontos))
        hover_idx = self._hover_ponto_idx if self._hover_ponto_idx is not None and 0 <= int(self._hover_ponto_idx) < len(pontos) else None
        if not pontos:
            return
        painter.save()
        font = QFont("Arial", 8)
        font.setBold(True)
        painter.setFont(font)
        for idx, ponto in enumerate(pontos):
            if idx in selecionados or idx == hover_idx:
                continue
            tela = canvas._cena_para_tela(ponto)
            self._desenhar_ponto_overlay(canvas, painter, molde, idx, tela, raio=5)
        for idx in selecionados:
            tela = canvas._cena_para_tela(pontos[idx])
            ativo = idx == self._ponto_idx
            cor = QColor("#ff006e" if ativo else "#00d6ff")
            painter.setPen(QPen(cor, 2.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(tela, 9, 9)
            self._desenhar_ponto_overlay(canvas, painter, molde, idx, tela, raio=6)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(tela.x() + 8), int(tela.y() - 8), str(idx + 1))
        if hover_idx is not None:
            idx = int(hover_idx)
            tela = canvas._cena_para_tela(pontos[idx])
            cor_hover = QColor("#008cff")
            painter.setPen(QPen(cor_hover, 3.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(tela, 11, 11)
            self._desenhar_ponto_overlay(canvas, painter, molde, idx, tela, raio=6)
            painter.drawLine(QPointF(tela.x() - 14, tela.y()), QPointF(tela.x() - 8, tela.y()))
            painter.drawLine(QPointF(tela.x() + 8, tela.y()), QPointF(tela.x() + 14, tela.y()))
            painter.drawLine(QPointF(tela.x(), tela.y() - 14), QPointF(tela.x(), tela.y() - 8))
            painter.drawLine(QPointF(tela.x(), tela.y() + 8), QPointF(tela.x(), tela.y() + 14))
            painter.setPen(cor_hover)
            painter.drawText(int(tela.x() + 13), int(tela.y() - 12), str(idx + 1))
        painter.restore()

    def _desenhar_ponto_overlay(self, canvas, painter, molde: dict, ponto_idx: int, tela: QPointF, raio: int = 5) -> None:
        cor, forma = self._config_visual_ponto_overlay(canvas, molde, ponto_idx)
        desenhar = getattr(canvas, "_desenhar_marcador_ponto_tela", None)
        if callable(desenhar):
            desenhar(painter, tela, cor, forma, raio)
            return
        cor_qt = QColor(str(cor or "#008cff"))
        if not cor_qt.isValid():
            cor_qt = QColor("#008cff")
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.setBrush(cor_qt)
        d = max(2, int(raio))
        forma_txt = str(forma or "").strip().lower()
        if "quadrado" in forma_txt:
            painter.drawRect(int(tela.x() - d), int(tela.y() - d), d * 2, d * 2)
        elif "circulo" in forma_txt or "círculo" in forma_txt:
            painter.drawEllipse(tela, d, d)
        else:
            path = QPainterPath(QPointF(tela.x(), tela.y() - d))
            path.lineTo(QPointF(tela.x() + d, tela.y()))
            path.lineTo(QPointF(tela.x(), tela.y() + d))
            path.lineTo(QPointF(tela.x() - d, tela.y()))
            path.closeSubpath()
            painter.drawPath(path)

    def _config_visual_ponto_overlay(self, canvas, molde: dict, ponto_idx: int) -> tuple[str, str]:
        chave = self._chave_config_ponto_overlay(molde, ponto_idx)
        cor_padrao = "#008cff"
        forma_padrao = "Circulo preenchido" if chave == "ponto_controle" else "Losango"
        config = getattr(canvas, "_config_ponto_molde", None)
        if callable(config):
            try:
                return config(chave, cor_padrao, forma_padrao)
            except Exception:
                pass
        return cor_padrao, forma_padrao

    def _chave_config_ponto_overlay(self, molde: dict | None, ponto_idx: int | None) -> str:
        return "ponto_controle" if self._valores_ponto(molde, ponto_idx) else "ponto_nao_graduado"

    def selecionar_ponto(self, canvas, ponto_idx: int | None):
        self._ponto_idx = ponto_idx
        self._pontos_selecionados = {int(ponto_idx)} if ponto_idx is not None else set()
        self._atualizar_dialog(canvas)
        canvas.update()

    def iniciar_copia_graduacao(self, canvas) -> None:
        self._modo_copia_graduacao = True
        self._origem_copia = None
        if self._molde_idx is not None and self._ponto_idx is not None:
            molde = self._molde_atual(canvas)
            valores = self._valores_ponto(molde, self._ponto_idx)
            if not valores:
                valores = self._obter_dialog(canvas).valores()
            if valores:
                self._graduacao_copiada = deepcopy(valores)
                self._origem_copia = (int(self._molde_idx), int(self._ponto_idx))
                self._status(canvas, "Tabela: graduação copiada; clique no molde e no ponto de destino para colar.")
                self._repintar_canvas_agora(canvas)
                return
        self._graduacao_copiada = None
        self._status(canvas, "Tabela: modo copiar; clique no molde e no ponto de origem.")
        self._repintar_canvas_agora(canvas)

    def atualizar_preview_dialog(self, canvas):
        self._salvar_valores_dialog(canvas, registrar_historico=False)
        self._atualizar_perimetros_dialog(canvas)
        self._repintar_canvas_agora(canvas)

    def aplicar_dialog(self, canvas):
        if self._salvar_valores_dialog(canvas, registrar_historico=True):
            self._status(canvas, "Graduação por tabela aplicada ao ponto selecionado.")
            self._repintar_canvas_agora(canvas)
        else:
            self._status(canvas, "Tabela: selecione um molde e um ponto para aplicar.")

    def _salvar_valores_dialog(self, canvas, *, registrar_historico: bool) -> bool:
        if self._molde_idx is None:
            return False
        if not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return False
        molde = canvas.cena.elementos[self._molde_idx]
        if not isinstance(molde, dict) or not molde.get("molde"):
            return False
        if not self._preparar_molde_para_tabela(canvas, self._molde_idx):
            return False
        dialog = self._obter_dialog(canvas)
        self._garantir_tamanhos_no_molde(molde, dialog)
        pontos = self._pontos_contorno(molde)
        alvo_indices = self._pontos_alvo_salvar(len(pontos))
        if not alvo_indices:
            return False
        tabela = molde.setdefault("graduacao_tabela", {})
        tabela["modo"] = "dx_dy"
        pontos_cfg = tabela.setdefault("pontos", {})
        valores = dialog.valores()
        for ponto_idx in alvo_indices:
            chave = str(ponto_idx)
            self._remover_graduacao_mesmo_ponto(pontos_cfg, pontos[ponto_idx], chave)
            pontos_cfg[chave] = {
                "indice": int(ponto_idx),
                "numero": int(ponto_idx) + 1,
                "ponto": (float(pontos[ponto_idx].x()), float(pontos[ponto_idx].y())),
                "valores": deepcopy(valores),
            }
        molde["graduacao_pontos"] = deepcopy(pontos_cfg)
        molde["mostrar_graduacao"] = True
        if registrar_historico and hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        return True

    def _obter_dialog(self, canvas) -> GraduarTabelaDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = GraduarTabelaDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        return dialog

    def _ocultar_dialog(self, canvas) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()

    def _restaurar_dialog(self, canvas, dialog: GraduarTabelaDialog):
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _observar_canvas(self, canvas) -> None:
        if canvas is None:
            return

        if not hasattr(self, "_canvas_observados"):
            self._canvas_observados = set()
        if not hasattr(self, "_dialog_propriedades_observados"):
            self._dialog_propriedades_observados = set()
        if not hasattr(self, "_atualizacoes_canvas_agendadas"):
            self._atualizacoes_canvas_agendadas = set()

        chave = id(canvas)

        # Observa alterações reais no canvas.
        # Não pode retornar cedo demais, porque mesmo sem esse sinal
        # ainda precisamos tentar observar a janela de Propriedades.
        if chave not in self._canvas_observados:
            sinal = getattr(canvas, "elementos_alterados", None)

            if sinal is not None and hasattr(sinal, "connect"):
                try:
                    sinal.connect(
                        lambda *_args, canvas=canvas: self._agendar_atualizacao_canvas(canvas)
                    )
                except Exception:
                    pass

            self._canvas_observados.add(chave)

        # Observa também a janela Propriedades, quando ela estiver aberta.
        self._observar_dialog_propriedades(canvas)

    def _observar_dialog_propriedades(self, canvas) -> None:
        if canvas is None:
            return

        if not hasattr(self, "_dialog_propriedades_observados"):
            self._dialog_propriedades_observados = set()

        dialog = self._dialog_propriedades_aberta(canvas)
        if dialog is None:
            return

        chave_dialog = (id(canvas), id(dialog))
        if chave_dialog in self._dialog_propriedades_observados:
            return

        # A janela Propriedades emite dados_aplicados quando o usuário confirma.
        sinal = getattr(dialog, "dados_aplicados", None)
        if sinal is not None and hasattr(sinal, "connect"):
            try:
                sinal.connect(
                    lambda *_args, canvas=canvas: self._agendar_atualizacao_canvas(canvas)
                )
            except Exception:
                pass

        # Quando a janela fechar/destruir, libera a chave para poder conectar novamente
        # numa próxima abertura.
        try:
            dialog.destroyed.connect(
                lambda *_args, chave_dialog=chave_dialog: self._dialog_propriedades_observados.discard(chave_dialog)
            )
        except Exception:
            pass

        self._dialog_propriedades_observados.add(chave_dialog)


    def _agendar_atualizacao_canvas(self, canvas) -> None:
        if canvas is None:
            return

        if not hasattr(self, "_atualizacoes_canvas_agendadas"):
            self._atualizacoes_canvas_agendadas = set()

        chave = id(canvas)

        # Evita várias atualizações seguidas no mesmo ciclo do Qt.
        if chave in self._atualizacoes_canvas_agendadas:
            return

        self._atualizacoes_canvas_agendadas.add(chave)

        def executar():
            try:
                self._atualizacoes_canvas_agendadas.discard(chave)
            except Exception:
                pass

            try:
                self._quando_canvas_elementos_alterados(canvas)
            except Exception:
                pass

        try:
            QTimer.singleShot(0, executar)
        except Exception:
            executar()

    def _quando_canvas_elementos_alterados(self, canvas) -> None:
        if canvas is None:
            return

        # Tenta capturar a janela Propriedades sempre que houver alteração,
        # porque ela pode ter sido aberta depois da Tabela.
        self._observar_dialog_propriedades(canvas)

        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is None:
            return

        visivel = bool(dialog.isVisible())

        selecionado = self._molde_selecionado(canvas)
        if selecionado is not None and selecionado != self._molde_idx:
            self._definir_molde_idx(canvas, selecionado)
            self._ponto_idx = None
            self._hover_ponto_idx = None
            self._pontos_selecionados.clear()

        if not self._molde_atual_corresponde(canvas):
            if visivel:
                self._fechar_dialog_molde_indisponivel(canvas)
            else:
                self._molde_idx = None
                self._molde_chave = None
                self._ponto_idx = None
                self._hover_ponto_idx = None
                self._pontos_selecionados.clear()
            return

        pontos = self._pontos_contorno(self._molde_atual(canvas))
        if not pontos:
            if visivel:
                self._fechar_dialog_molde_indisponivel(canvas)
            return

        if self._ponto_idx is not None and not (0 <= self._ponto_idx < len(pontos)):
            self._ponto_idx = None

        self._pontos_selecionados = self._pontos_validos_selecionados(len(pontos))
        self._atualizar_dialog(canvas)

        if visivel:
            self._repintar_canvas_agora(canvas)

    def _fechar_dialog_molde_indisponivel(self, canvas) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._molde_idx = None
        self._molde_chave = None
        self._ponto_idx = None
        self._hover_ponto_idx = None
        self._pontos_selecionados.clear()
        self._status(canvas, "Tabela fechada: o molde não está mais disponível no canvas.")
        if hasattr(canvas, "update"):
            canvas.update()

    def _atualizar_dialog(self, canvas):
        self._observar_dialog_propriedades(canvas)
        dialog = self._obter_dialog(canvas)
        dialog.conectar(self, canvas)
        molde = self._molde_atual(canvas)
        pontos = self._pontos_contorno(molde) if molde else []
        if molde is not None:
            self._garantir_tamanhos_no_molde(molde, canvas=canvas)
        if self._ponto_idx is not None and not self._pontos_selecionados:
            self._pontos_selecionados = {int(self._ponto_idx)}
        if pontos:
            self._pontos_selecionados = self._pontos_validos_selecionados(len(pontos))
        dialog.definir_pontos(len(pontos), self._ponto_idx)
        tamanhos = self._tamanhos_molde(molde, canvas=canvas)
        valores = self._valores_ponto(molde, self._ponto_idx)
        dialog.definir_tamanhos(tamanhos, valores)
        self._atualizar_perimetros_dialog(canvas)

    def _atualizar_perimetros_dialog(self, canvas) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is None:
            return
        dialog.set_unidade(*unidade_canvas(canvas))
        molde = self._molde_atual(canvas)
        pontos = self._pontos_contorno(molde) if molde else []
        tamanhos = self._tamanhos_molde(molde, canvas=canvas)
        dialog.definir_perimetros(self._linhas_perimetro_graduacao(molde, pontos, tamanhos))

    def _linhas_perimetro_graduacao(self, molde: dict | None, pontos: list[QPointF], tamanhos: list[dict]) -> list[dict]:
        if not pontos:
            return []
        perimetro_base = self._perimetro_pontos(pontos)
        pontos_cfg = {}
        if isinstance(molde, dict):
            tabela = molde.get("graduacao_tabela")
            if isinstance(tabela, dict) and isinstance(tabela.get("pontos"), dict):
                pontos_cfg = tabela.get("pontos") or {}
            elif isinstance(molde.get("graduacao_pontos"), dict):
                pontos_cfg = molde.get("graduacao_pontos") or {}
        linhas: list[dict] = []
        for linha in tamanhos:
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if not nome:
                continue
            if bool(linha.get("base", False)):
                perimetro = perimetro_base
                perimetro_x = perimetro_base
                perimetro_y = perimetro_base
            else:
                pontos_graduados = []
                pontos_x = []
                pontos_y = []
                for idx, ponto in enumerate(pontos):
                    valores = {}
                    dados_ponto = pontos_cfg.get(str(idx)) if isinstance(pontos_cfg, dict) else None
                    if isinstance(dados_ponto, dict) and isinstance(dados_ponto.get("valores"), dict):
                        valores = dados_ponto["valores"].get(nome, {}) or {}
                    dx = self._float_seguro(valores.get("dx", 0.0) if isinstance(valores, dict) else 0.0)
                    dy = self._float_seguro(valores.get("dy", 0.0) if isinstance(valores, dict) else 0.0)
                    pontos_x.append(QPointF(ponto.x() + dx, ponto.y()))
                    pontos_y.append(QPointF(ponto.x(), ponto.y() + dy))
                    pontos_graduados.append(QPointF(ponto.x() + dx, ponto.y() + dy))
                perimetro_x = self._perimetro_pontos(pontos_x)
                perimetro_y = self._perimetro_pontos(pontos_y)
                perimetro = self._perimetro_pontos(pontos_graduados)
            linhas.append(
                {
                    "tamanho": nome,
                    "cor": linha.get("cor"),
                    "base": bool(linha.get("base", False)),
                    "perimetro_x": perimetro_x,
                    "diferenca_x": perimetro_x - perimetro_base,
                    "perimetro_y": perimetro_y,
                    "diferenca_y": perimetro_y - perimetro_base,
                    "perimetro": perimetro,
                    "diferenca": perimetro - perimetro_base,
                }
            )
        return linhas

    @staticmethod
    def _perimetro_pontos(pontos: list[QPointF]) -> float:
        if len(pontos) < 2:
            return 0.0
        total = 0.0
        for idx, atual in enumerate(pontos):
            prox = pontos[(idx + 1) % len(pontos)]
            total += hypot(prox.x() - atual.x(), prox.y() - atual.y())
        return total

    @staticmethod
    def _float_seguro(valor) -> float:
        try:
            numero = numero_decimal_ponto(valor, 0.0)
            return numero if isfinite(numero) else 0.0
        except Exception:
            return 0.0

    def _molde_atual(self, canvas) -> dict | None:
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return None
        molde = canvas.cena.elementos[self._molde_idx]
        return molde if self._eh_molde_graduavel(molde) else None

    @staticmethod
    def _eh_molde_graduavel(elemento) -> bool:
        if not isinstance(elemento, dict) or not elemento.get("molde"):
            return False
        tipo = str(elemento.get("tipo") or "").strip().lower()
        if tipo and tipo not in {"polyline", "molde"}:
            return False
        return True

    def _definir_molde_idx(self, canvas, molde_idx: int | None) -> None:
        self._molde_idx = int(molde_idx) if molde_idx is not None else None
        molde = self._molde_atual(canvas)
        self._molde_chave = self._chave_molde(molde) if molde is not None else None

    def _selecionar_molde(self, canvas, molde_idx: int | None) -> None:
        if molde_idx is not None and not self._preparar_molde_para_tabela(canvas, int(molde_idx)):
            return
        self._definir_molde_idx(canvas, molde_idx)
        self._ponto_idx = None
        self._hover_ponto_idx = None
        self._pontos_selecionados.clear()
        if molde_idx is not None and hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(molde_idx)}
        self._atualizar_dialog(canvas)
        self._repintar_canvas_agora(canvas)

    def _processar_clique_modo_copia(
        self,
        canvas,
        molde_idx: int,
        alvo: tuple[int, int] | None,
        pos: QPointF,
    ) -> bool:
        if not self._modo_copia_graduacao:
            return False
        if molde_idx != self._molde_idx:
            self._selecionar_molde(canvas, molde_idx)
            if alvo is None:
                self._status(canvas, "Tabela: molde selecionado no modo copiar; clique em um ponto.")
                return True
        if alvo is None:
            alvo = self._molde_e_ponto_em_posicao(canvas, pos)
        if alvo is None or int(alvo[0]) != int(molde_idx):
            self._status(canvas, "Tabela: clique diretamente em um ponto do molde para copiar ou colar.")
            return True
        ponto_idx = int(alvo[1])
        if self._graduacao_copiada is None:
            self._selecionar_ponto_contorno(canvas, ponto_idx, acumular=False)
            valores = self._valores_ponto(canvas.cena.elementos[molde_idx], ponto_idx)
            if not valores:
                valores = self._obter_dialog(canvas).valores()
            self._graduacao_copiada = deepcopy(valores)
            self._origem_copia = (int(molde_idx), ponto_idx)
            self._atualizar_dialog(canvas)
            self._status(canvas, "Tabela: graduação copiada; clique no ponto de destino.")
            self._repintar_canvas_agora(canvas)
            return True
        self._colar_graduacao_copiada(canvas, int(molde_idx), ponto_idx)
        self._modo_copia_graduacao = False
        self._status(canvas, "Tabela: graduação colada no ponto de destino.")
        return True

    def _colar_graduacao_copiada(self, canvas, molde_idx: int, ponto_idx: int) -> None:
        if self._graduacao_copiada is None:
            return
        self._definir_molde_idx(canvas, molde_idx)
        self._ponto_idx = int(ponto_idx)
        self._pontos_selecionados = {int(ponto_idx)}
        self._hover_ponto_idx = None
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(molde_idx)}
        if not self._preparar_molde_para_tabela(canvas, molde_idx):
            return
        dialog = self._obter_dialog(canvas)
        molde = canvas.cena.elementos[int(molde_idx)]
        self._garantir_tamanhos_no_molde(molde, dialog)
        dialog.definir_pontos(len(self._pontos_contorno(molde)), int(ponto_idx))
        dialog.definir_tamanhos(self._tamanhos_molde(molde, canvas=canvas), deepcopy(self._graduacao_copiada))
        self._salvar_valores_dialog(canvas, registrar_historico=True)
        self._atualizar_dialog(canvas)
        self._repintar_canvas_agora(canvas)

    def _selecionar_ponto_contorno(self, canvas, ponto_idx: int, *, acumular: bool) -> None:
        ponto_idx = int(ponto_idx)
        if acumular:
            if ponto_idx in self._pontos_selecionados and len(self._pontos_selecionados) > 1:
                self._pontos_selecionados.remove(ponto_idx)
            else:
                self._pontos_selecionados.add(ponto_idx)
        else:
            self._pontos_selecionados = {ponto_idx}
        self._ponto_idx = ponto_idx
        total = len(self._pontos_selecionados)
        if total > 1:
            self._status(canvas, f"Tabela: {total} pontos selecionados para graduação.")
        else:
            self._status(canvas, f"Tabela: ponto {ponto_idx + 1} selecionado para graduação.")

    def _pontos_validos_selecionados(self, quantidade: int) -> set[int]:
        return {int(idx) for idx in self._pontos_selecionados if 0 <= int(idx) < int(quantidade)}

    def _pontos_alvo_salvar(self, quantidade: int) -> list[int]:
        selecionados = self._pontos_validos_selecionados(quantidade)
        if not selecionados and self._ponto_idx is not None and 0 <= int(self._ponto_idx) < int(quantidade):
            selecionados = {int(self._ponto_idx)}
        return sorted(selecionados)

    @staticmethod
    def _evento_ctrl(event) -> bool:
        try:
            mods = event.modifiers()
            return bool(mods & Qt.ControlModifier or mods & Qt.MetaModifier)
        except Exception:
            return False

    def _molde_atual_corresponde(self, canvas) -> bool:
        molde = self._molde_atual(canvas)
        if molde is None:
            return False
        chave = self._chave_molde(molde)
        return self._molde_chave is None or chave == self._molde_chave

    @staticmethod
    def _chave_molde(molde: dict) -> str:
        for chave in ("molde_id", "id", "uuid"):
            valor = str(molde.get(chave) or "").strip()
            if valor:
                return f"{chave}:{valor}"
        return f"obj:{id(molde)}"

    @staticmethod
    def _identidade_molde_para_propriedades(molde: dict | None) -> dict:
        if not isinstance(molde, dict):
            return {}
        identidade: dict[str, str] = {}
        for chave in ("molde_id", "shape_id", "id", "uuid"):
            valor = str(molde.get(chave) or "").strip()
            if valor:
                identidade[chave] = valor
        for chave in ("nome_molde", "origem_extracao", "tamanho_extraido"):
            valor = str(molde.get(chave) or "").strip()
            if valor:
                identidade[chave] = valor
        return identidade

    def _molde_selecionado(self, canvas) -> int | None:
        for idx in sorted(getattr(canvas, "_selecionados", set()) or []):
            if 0 <= int(idx) < len(canvas.cena.elementos) and self._eh_molde_graduavel(canvas.cena.elementos[int(idx)]):
                return int(idx)
        return None

    def _molde_padrao(self, canvas) -> int | None:
        selecionado = self._molde_selecionado(canvas)
        if selecionado is not None:
            return selecionado
        for idx, elemento in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if self._eh_molde_graduavel(elemento):
                return int(idx)
        return None

    def _molde_referencia_inicial(self, canvas) -> int | None:
        elementos = getattr(getattr(canvas, "cena", None), "elementos", []) or []
        for exigir_valores in (True, False):
            for idx, elemento in enumerate(elementos):
                if not self._eh_molde_graduavel(elemento):
                    continue
                if self._molde_precisa_definir_grade(canvas, int(idx)):
                    continue
                if not self._molde_tem_grade(elemento):
                    continue
                if exigir_valores and not self._tem_valores_graduacao(elemento):
                    continue
                return int(idx)
        return None

    @staticmethod
    def _molde_tem_grade(molde: dict) -> bool:
        linhas = molde.get("graduacao_tamanhos") if isinstance(molde, dict) else None
        if not isinstance(linhas, list):
            return False
        return any(
            isinstance(linha, dict)
            and str(linha.get("tamanho") or linha.get("nome") or "").strip()
            for linha in linhas
        )

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        alvo = self._molde_e_ponto_em_posicao(canvas, pos)
        if alvo is not None:
            return alvo[0]
        idx_area = self._molde_por_area_em_posicao(canvas, pos)
        if idx_area is not None:
            return idx_area
        idx_segmento = self._molde_por_segmento_em_posicao(canvas, pos)
        if idx_segmento is not None:
            return idx_segmento
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None and 0 <= int(idx) < len(canvas.cena.elementos) and self._eh_molde_graduavel(canvas.cena.elementos[int(idx)]):
                return int(idx)
        melhor: tuple[float, int] | None = None
        tolerancia = max(0.15, 16.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        for idx, el in enumerate(canvas.cena.elementos):
            if not self._eh_molde_graduavel(el):
                continue
            ponto_idx = self._ponto_mais_proximo(el, pos)
            if ponto_idx is None:
                continue
            dist = self._dist(self._pontos_contorno(el)[ponto_idx], pos)
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, idx)
        return melhor[1] if melhor else None

    def _molde_e_ponto_em_posicao(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        melhor: tuple[float, int, int] | None = None
        tolerancia = max(0.18, 24.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if not self._eh_molde_graduavel(el):
                continue
            pontos = self._pontos_contorno(el)
            if not pontos:
                continue
            dist, ponto_idx = min((self._dist(ponto, pos), p_idx) for p_idx, ponto in enumerate(pontos))
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, int(idx), int(ponto_idx))
        if melhor is not None:
            return melhor[1], melhor[2]
        return None

    def _molde_por_area_em_posicao(self, canvas, pos: QPointF) -> int | None:
        elementos = getattr(canvas.cena, "elementos", []) or []
        for idx in range(len(elementos) - 1, -1, -1):
            el = elementos[idx]
            if not self._eh_molde_graduavel(el):
                continue
            pontos = self._pontos_contorno(el)
            if len(pontos) < 3:
                continue
            path = QPainterPath(pontos[0])
            for ponto in pontos[1:]:
                path.lineTo(ponto)
            path.closeSubpath()
            if path.contains(pos):
                return int(idx)
        return None

    def _molde_por_segmento_em_posicao(self, canvas, pos: QPointF) -> int | None:
        melhor: tuple[float, int] | None = None
        tolerancia = max(0.18, 18.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        elementos = getattr(canvas.cena, "elementos", []) or []
        for idx in range(len(elementos) - 1, -1, -1):
            el = elementos[idx]
            if not self._eh_molde_graduavel(el):
                continue
            pontos = self._pontos_contorno(el)
            if len(pontos) < 2:
                continue
            segmentos = list(zip(pontos, pontos[1:]))
            if len(pontos) > 2:
                segmentos.append((pontos[-1], pontos[0]))
            for a, b in segmentos:
                dist = self._distancia_ponto_segmento(pos, a, b)
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, int(idx))
        return melhor[1] if melhor is not None else None

    def _ponto_mais_proximo(self, molde: dict, pos: QPointF) -> int | None:
        pontos = self._pontos_contorno(molde)
        if not pontos:
            return None
        distancias = [(self._dist(ponto, pos), idx) for idx, ponto in enumerate(pontos)]
        return min(distancias, key=lambda item: item[0])[1]

    def _ponto_hover(self, molde: dict, pos: QPointF, canvas) -> int | None:
        pontos = self._pontos_contorno(molde)
        if not pontos:
            return None
        tolerancia = max(0.12, min(0.6, 14.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)))
        dist, idx = min((self._dist(ponto, pos), idx) for idx, ponto in enumerate(pontos))
        return int(idx) if dist <= tolerancia else None

    def _pontos_contorno(self, molde: dict | None) -> list[QPointF]:
        if not self._eh_molde_graduavel(molde):
            return []
        base = self._pontos_de_origem(molde.get("pontos") if isinstance(molde, dict) else None)
        for chave in (
            "pontos_controle_principais",
            "controle_cantos",
            "pontos_controle_curva",
            "pontos_controle",
            "pontos",
            "pontos_graduacao",
        ):
            valor = molde.get(chave)
            pontos = self._pontos_de_origem(valor)
            if not pontos:
                continue
            if chave != "pontos" and self._pontos_desalinhados_do_contorno(pontos, base):
                continue
            return pontos
        return base

    def _pontos_de_origem(self, origem) -> list[QPointF]:
        pontos: list[QPointF] = []
        for item in origem or []:
            ponto = self._ponto_qt(item)
            if ponto is not None:
                pontos.append(ponto)
        if len(pontos) > 1 and self._dist(pontos[0], pontos[-1]) <= 1e-7:
            pontos.pop()
        return pontos

    def _pontos_desalinhados_do_contorno(self, pontos: list[QPointF], base: list[QPointF]) -> bool:
        if len(pontos) < 2 or len(base) < 2:
            return False
        tolerancia = self._tolerancia_fonte_contorno(base)
        distantes = [
            ponto
            for ponto in pontos
            if self._distancia_ponto_contorno(ponto, base) > tolerancia
        ]
        return bool(distantes)

    def _tolerancia_fonte_contorno(self, base: list[QPointF]) -> float:
        xs = [p.x() for p in base]
        ys = [p.y() for p in base]
        diagonal = hypot(max(xs) - min(xs), max(ys) - min(ys)) if xs and ys else 0.0
        return max(1.0, diagonal * 0.08)

    def _distancia_ponto_contorno(self, ponto: QPointF, base: list[QPointF]) -> float:
        if not base:
            return float("inf")
        segmentos = list(zip(base, base[1:]))
        if len(base) > 2:
            segmentos.append((base[-1], base[0]))
        if not segmentos:
            return min(self._dist(ponto, item) for item in base)
        return min(self._distancia_ponto_segmento(ponto, a, b) for a, b in segmentos)

    def _tamanhos_molde(self, molde: dict | None, *, canvas=None) -> list[dict]:
        if not isinstance(molde, dict):
            return []

        grade_nome = str(molde.get("graduacao_grade_nome") or "").strip()
        linhas_origem = molde.get("graduacao_tamanhos") if isinstance(molde.get("graduacao_tamanhos"), list) else []

        if linhas_origem:
            linhas = [dict(l) for l in linhas_origem if isinstance(l, dict) and l.get("ativo", True)]
        else:
            _grade_nome, linhas_padrao = grade_graduacao_padrao()
            grade_nome = grade_nome or str(_grade_nome or "").strip()
            linhas = [dict(linha) for linha in linhas_padrao]

        if not grade_nome:
            grade_nome = self._inferir_grade_pelos_tamanhos(linhas)

        linhas_propriedades = self._linhas_graduacao_propriedades_aberta(canvas, molde)
        cores_propriedades = self._mapa_cores_linhas(linhas_propriedades)
        if linhas_propriedades:
            base_props = next((str(linha.get("tamanho") or linha.get("nome") or "").strip() for linha in linhas_propriedades if linha.get("base")), "")
            if base_props:
                for linha in linhas:
                    if str(linha.get("tamanho") or linha.get("nome") or "").strip() == base_props:
                        linha["base"] = True
                    elif "base" in linha:
                        linha["base"] = False

        return self._normalizar_linhas_tamanhos_com_cores(
            linhas,
            grade_nome,
            cores_prioritarias=cores_propriedades,
        )

    def _normalizar_linhas_tamanhos_com_cores(
            self,
            linhas: list[dict],
            grade_nome: str,
            *,
            cores_prioritarias: dict[str, str] | None = None,
    ) -> list[dict]:
        grade_nome = str(grade_nome or "").strip()
        cores_padrao = self._cores_padrao_grade_tabela(grade_nome)
        cores_prioritarias = cores_prioritarias or {}
        base_grade = self._base_grade_tabela(grade_nome)
        resultado: list[dict] = []

        for idx, linha in enumerate(linhas):
            if not isinstance(linha, dict):
                continue
            nova = dict(linha)
            nome = str(nova.get("tamanho") or nova.get("nome") or "").strip()
            if not nome:
                continue
            nova["tamanho"] = nome

            cor_prioritaria = self._cor_hex_valida(cores_prioritarias.get(nome))
            cor_atual = self._cor_hex_valida(nova.get("cor"))
            cor_grade = self._cor_hex_valida(cores_padrao.get(nome))
            if cor_prioritaria:
                cor = cor_prioritaria
            elif cor_atual and not (cor_atual.lower() == "#ffffff" and cor_grade and cor_grade.lower() != "#ffffff"):
                cor = cor_atual
            else:
                cor = cor_grade or cor_atual
            if cor:
                nova["cor"] = cor
            else:
                nova["cor"] = "#ffffff"

            if base_grade and nome == base_grade and not any(bool(item.get("base", False)) for item in linhas if isinstance(item, dict)):
                nova["base"] = True
            resultado.append(nova)

        if resultado and not any(bool(linha.get("base", False)) for linha in resultado):
            resultado[min(len(resultado) // 2, len(resultado) - 1)]["base"] = True
        return resultado

    @staticmethod
    def _cor_hex_valida(valor) -> str:
        cor = QColor(str(valor or ""))
        return cor.name() if cor.isValid() else ""

    @staticmethod
    def _base_grade_tabela(grade_nome: str) -> str:
        texto = str(grade_nome or "").strip()
        if "(" in texto and ")" in texto:
            return texto[texto.find("(") + 1:texto.find(")")].strip()
        return ""

    @staticmethod
    def _inferir_grade_pelos_tamanhos(linhas: list[dict]) -> str:
        nomes = [
            str(linha.get("tamanho") or linha.get("nome") or "").strip()
            for linha in linhas
            if isinstance(linha, dict) and str(linha.get("tamanho") or linha.get("nome") or "").strip()
        ]
        if not nomes:
            return ""
        for grade_nome, cores in GRADES_TAMANHOS_CORES_FIXAS.items():
            ordem = list(cores.keys())
            if nomes == ordem:
                return grade_nome
            pos = 0
            corresponde = True
            for nome in nomes:
                try:
                    encontrado = ordem.index(nome, pos)
                except ValueError:
                    corresponde = False
                    break
                pos = encontrado + 1
            if corresponde:
                return grade_nome
        return ""

    @staticmethod
    def _cores_padrao_grade_tabela(grade_nome: str) -> dict[str, str]:
        texto = str(grade_nome or "").strip()
        cores_fixas = GRADES_TAMANHOS_CORES_FIXAS.get(texto)
        if cores_fixas:
            return dict(cores_fixas)
        for idioma in ("pt", "es"):
            try:
                nome_padrao, linhas_padrao = grade_graduacao_padrao(idioma)
            except TypeError:
                if idioma != "pt":
                    continue
                nome_padrao, linhas_padrao = grade_graduacao_padrao()
            if texto and texto != str(nome_padrao or "").strip():
                continue
            mapa = {}
            for linha in linhas_padrao:
                if isinstance(linha, dict):
                    nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
                    cor_qt = QColor(str(linha.get("cor") or ""))
                    cor = cor_qt.name() if cor_qt.isValid() else ""
                    if nome and cor:
                        mapa[nome] = cor
            if mapa:
                return mapa
        return dict(CORES_TAMANHOS_PADRAO_TABELA)

    @staticmethod
    def _mapa_cores_linhas(linhas: list[dict]) -> dict[str, str]:
        mapa: dict[str, str] = {}
        for linha in linhas or []:
            if not isinstance(linha, dict):
                continue
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            cor = Ferramenta._cor_hex_valida(linha.get("cor"))
            if nome and cor:
                mapa[nome] = cor
        return mapa

    def _linhas_graduacao_propriedades_aberta(self, canvas, molde: dict | None) -> list[dict]:
        if canvas is None or not isinstance(molde, dict):
            return []
        dialog = self._dialog_propriedades_aberta(canvas)
        if dialog is None:
            return []
        try:
            indice_atual = getattr(dialog, "_indice_atual", None)
            if indice_atual is not None and self._molde_idx is not None and int(indice_atual) != int(self._molde_idx):
                return []
        except Exception:
            pass

        # Preferência máxima: ler a tabela de Propriedades aberta, porque ela contém
        # exatamente as cores que o usuário está vendo na coluna Cor.
        linhas_ui = self._linhas_tabela_graduacao_dialog(dialog)
        if linhas_ui:
            return linhas_ui

        linhas = getattr(dialog, "_graduacao_linhas", None)
        if isinstance(linhas, list) and linhas:
            return [dict(linha) for linha in linhas if isinstance(linha, dict) and linha.get("ativo", True)]
        try:
            rascunho = getattr(dialog, "_elementos_rascunho", None)
            if isinstance(rascunho, list) and self._molde_idx is not None and 0 <= int(self._molde_idx) < len(rascunho):
                molde_rascunho = rascunho[int(self._molde_idx)]
                linhas_rascunho = molde_rascunho.get("graduacao_tamanhos") if isinstance(molde_rascunho, dict) else None
                if isinstance(linhas_rascunho, list):
                    return [dict(linha) for linha in linhas_rascunho if isinstance(linha, dict) and linha.get("ativo", True)]
        except Exception:
            pass
        return []

    @staticmethod
    def _linhas_tabela_graduacao_dialog(dialog) -> list[dict]:
        tabela = getattr(dialog, "tbl_graduacao", None)
        if tabela is None or not all(hasattr(tabela, nome) for nome in ("rowCount", "item")):
            return []
        linhas: list[dict] = []
        try:
            total = int(tabela.rowCount())
        except Exception:
            return []
        for row in range(total):
            item_ativo = tabela.item(row, 0)
            item_tamanho = tabela.item(row, 1)
            item_cor = tabela.item(row, 2)
            nome = str(item_tamanho.text() if item_tamanho is not None else "").strip()
            if not nome:
                continue
            ativo_txt = str(item_ativo.text() if item_ativo is not None else "✓").strip()
            cor = ""
            if item_cor is not None:
                try:
                    cor = item_cor.background().color().name()
                except Exception:
                    cor = ""
            if not QColor(str(cor or "")).isValid() and item_tamanho is not None:
                try:
                    cor = item_tamanho.background().color().name()
                except Exception:
                    cor = ""
            linhas.append({
                "ativo": bool(ativo_txt),
                "tamanho": nome,
                "cor": cor if QColor(str(cor or "")).isValid() else "#ffffff",
                "base": bool(item_tamanho.font().bold()) if item_tamanho is not None else False,
            })
        if linhas and not any(linha.get("base") for linha in linhas):
            base_idx = getattr(dialog, "_linha_gradacao_atual", None)
            try:
                base_idx = int(base_idx)
            except Exception:
                base_idx = -1
            if 0 <= base_idx < len(linhas):
                linhas[base_idx]["base"] = True
        return [linha for linha in linhas if linha.get("ativo", True)]

    @staticmethod
    def _dialog_propriedades_aberta(canvas):
        def dialog_valido(dialog) -> bool:
            if dialog is None:
                return False
            nome_classe = type(dialog).__name__.lower()
            return (
                "propriedades" in nome_classe
                or hasattr(dialog, "_graduacao_linhas")
                or hasattr(dialog, "tbl_graduacao")
            )

        # Consulta primeiro a classe da ferramenta Propriedades. A ferramenta Tabela
        # também possui _dialog_por_canvas, então buscar ferramentas sem filtrar pode
        # retornar o próprio diálogo da tabela e perder as cores da graduação.
        try:
            modulo = import_module("tools.propriedades_tool")
            ferramenta_cls = getattr(modulo, "Ferramenta", None)
            mapa = getattr(ferramenta_cls, "_dialog_por_canvas", None)
            if isinstance(mapa, dict):
                dialog = mapa.get(id(canvas))
                if dialog_valido(dialog):
                    return dialog
        except Exception:
            pass

        candidatos = []
        runtime = getattr(canvas, "_runtime_tool", None)
        if runtime is not None:
            candidatos.append(runtime)
        cache = getattr(canvas, "_runtime_tool_cache", None)
        if isinstance(cache, dict):
            candidatos.extend(obj for obj in cache.values() if obj is not None)

        for ferramenta in candidatos:
            classe = getattr(ferramenta, "__class__", None)
            id_ferramenta = str(getattr(ferramenta, "id_ferramenta", "") or getattr(classe, "id_ferramenta", "")).strip().lower()
            modulo_nome = str(getattr(classe, "__module__", "") or "").lower()
            if id_ferramenta != "propriedades" and "propriedades_tool" not in modulo_nome:
                continue
            mapa = getattr(classe, "_dialog_por_canvas", None)
            if isinstance(mapa, dict):
                dialog = mapa.get(id(canvas))
                if dialog_valido(dialog):
                    return dialog
        return None

    def _garantir_tamanhos_no_molde(self, molde: dict, dialog: GraduarTabelaDialog | None = None, *, canvas=None) -> None:
        linhas = molde.get("graduacao_tamanhos") if isinstance(molde, dict) else None
        if dialog is not None:
            tamanhos = dialog._tamanhos_atuais()
        elif isinstance(linhas, list) and linhas:
            tamanhos = [dict(linha) for linha in linhas if isinstance(linha, dict)]
        else:
            tamanhos = self._tamanhos_molde(molde, canvas=canvas)
        grade_nome_atual = str(molde.get("graduacao_grade_nome") or "").strip()
        if not grade_nome_atual:
            grade_nome_atual = self._inferir_grade_pelos_tamanhos([dict(linha) for linha in tamanhos if isinstance(linha, dict)])
        linhas_normalizadas = self._normalizar_linhas_tamanhos_com_cores(
            [dict(linha) for linha in tamanhos if isinstance(linha, dict)],
            grade_nome_atual,
        )
        if not linhas_normalizadas:
            return
        molde["graduacao_tamanhos"] = linhas_normalizadas
        molde["graduacao_tamanhos_ativos"] = [
            str(linha.get("tamanho") or linha.get("nome") or "")
            for linha in linhas_normalizadas
            if linha.get("ativo", True) and str(linha.get("tamanho") or linha.get("nome") or "").strip()
        ]
        if not str(molde.get("graduacao_grade_nome") or "").strip():
            if not grade_nome_atual:
                grade_nome_atual, _linhas_padrao = grade_graduacao_padrao()
            molde["graduacao_grade_nome"] = grade_nome_atual

    def _preparar_molde_para_tabela(self, canvas, molde_idx: int | None, *, permitir_propriedades: bool = True) -> bool:
        if molde_idx is None or not (0 <= int(molde_idx) < len(canvas.cena.elementos)):
            return False
        molde = canvas.cena.elementos[int(molde_idx)]
        if not self._eh_molde_graduavel(molde):
            return False
        if self._molde_precisa_definir_grade(canvas, int(molde_idx)):
            self._ocultar_dialog(canvas)
            if not permitir_propriedades:
                return False
            if not self._confirmar_definir_grade_molde_separado(canvas, molde):
                self._status(canvas, "Tabela: defina a grade do molde separado antes de graduar.")
                return False
            self._abrir_propriedades_graduacao(canvas, int(molde_idx))
            self._status(canvas, "Escolha a grade do molde separado em Propriedades.")
            return False
        self._sincronizar_grade_molde_extraido_sem_valores(canvas, molde)
        return True

    def _molde_precisa_definir_grade(self, canvas, molde_idx: int | None) -> bool:
        if molde_idx is None or not (0 <= int(molde_idx) < len(canvas.cena.elementos)):
            return False
        molde = canvas.cena.elementos[int(molde_idx)]
        return self._eh_tamanho_separado_com_grade_incompleta(molde) or self._eh_tamanho_separado_sem_grade(molde)

    def _confirmar_definir_grade_molde_separado(self, canvas, molde: dict) -> bool:
        confirmador = getattr(canvas, "confirmar_definir_grade_molde_separado", None)
        if callable(confirmador):
            return bool(confirmador(molde))

        parent = canvas.window() if hasattr(canvas, "window") else canvas
        caixa = QMessageBox(parent)
        estilizar = getattr(parent, "_estilizar_message_box", None)
        if callable(estilizar):
            estilizar(caixa)
        caixa.setWindowTitle("Definir grade")
        caixa.setIcon(QMessageBox.Question)
        caixa.setText("Este molde separado possui apenas o tamanho extraído.\nEscolher grade agora?")
        caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        caixa.setDefaultButton(QMessageBox.Yes)
        traduzir = getattr(parent, "_traduzir_botoes_padrao_message_box", None)
        if callable(traduzir):
            traduzir(caixa)
        return caixa.exec() == QMessageBox.Yes

    def _abrir_propriedades_graduacao(self, canvas, molde_idx: int) -> None:
        molde = None
        elementos = getattr(getattr(canvas, "cena", None), "elementos", []) or []
        if 0 <= int(molde_idx) < len(elementos):
            candidato = elementos[int(molde_idx)]
            if isinstance(candidato, dict):
                molde = candidato
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(molde_idx)}
        identidade = self._identidade_molde_para_propriedades(molde)
        if identidade:
            setattr(canvas, "_propriedades_molde_identidade_preferida", identidade)
        if isinstance(molde, dict):
            setattr(canvas, "_propriedades_molde_objeto_preferido", molde)
        setattr(canvas, "_indice_propriedades_preferido", int(molde_idx))
        setattr(canvas, "_propriedades_tab_preferida", "graduacao")
        if hasattr(canvas, "update"):
            canvas.update()
        ativar_canvas = getattr(canvas, "set_ferramenta_ativa", None)
        if callable(ativar_canvas):
            ativar_canvas("propriedades")
            return
        parent = canvas.window() if hasattr(canvas, "window") else None
        abrir = getattr(parent, "_abrir_pagina_ferramenta", None)
        if callable(abrir):
            abrir("propriedades")

    def _sincronizar_grade_molde_extraido_sem_valores(self, canvas, molde: dict) -> None:
        if not isinstance(molde, dict):
            return
        if str(molde.get("origem_extracao") or "").strip() not in {"contorno", "face_auto"}:
            return
        if self._tem_valores_graduacao(molde):
            return
        referencia = grade_graduacao_referencia_canvas(canvas, ignorar_molde=molde)
        if referencia is None:
            return
        grade_nome, linhas_ref, ativos_ref = referencia
        if not linhas_ref:
            return
        if self._assinatura_grade_molde(molde) == self._assinatura_grade(grade_nome, linhas_ref):
            return
        molde["graduacao_grade_nome"] = grade_nome
        linhas_coloridas = self._normalizar_linhas_tamanhos_com_cores(
            [dict(linha) for linha in linhas_ref if isinstance(linha, dict)],
            str(grade_nome or ""),
        )
        molde["graduacao_tamanhos"] = linhas_coloridas
        molde["graduacao_tamanhos_ativos"] = list(ativos_ref)

    @staticmethod
    def _assinatura_grade_molde(molde: dict) -> tuple[str, tuple[str, ...]]:
        return Ferramenta._assinatura_grade(
            str(molde.get("graduacao_grade_nome") or "").strip(),
            molde.get("graduacao_tamanhos") if isinstance(molde.get("graduacao_tamanhos"), list) else [],
        )

    @staticmethod
    def _assinatura_grade(grade_nome: str, linhas: list[dict]) -> tuple[str, tuple[str, ...]]:
        nomes = [
            str(linha.get("tamanho") or linha.get("nome") or "").strip()
            for linha in linhas
            if isinstance(linha, dict)
        ]
        return str(grade_nome or "").strip(), tuple(nome for nome in nomes if nome)

    def _tem_valores_graduacao(self, molde: dict) -> bool:
        for pontos_cfg in self._fontes_pontos_graduacao(molde):
            for cfg in pontos_cfg.values():
                if not isinstance(cfg, dict):
                    continue
                valores = cfg.get("valores")
                if isinstance(valores, dict) and valores:
                    return True
        return False

    @staticmethod
    def _eh_tamanho_separado_sem_grade(molde: dict) -> bool:
        if not isinstance(molde, dict):
            return False
        if str(molde.get("origem_extracao") or "").strip() != "separar_tamanho":
            return False
        linhas = molde.get("graduacao_tamanhos")
        return not (isinstance(linhas, list) and any(isinstance(linha, dict) for linha in linhas))

    def _eh_tamanho_separado_com_grade_incompleta(self, molde: dict) -> bool:
        if not isinstance(molde, dict):
            return False
        if str(molde.get("origem_extracao") or "").strip() != "separar_tamanho":
            return False
        if self._tem_valores_graduacao(molde):
            return False
        linhas = [
            linha
            for linha in (molde.get("graduacao_tamanhos") or [])
            if isinstance(linha, dict) and linha.get("ativo", True)
        ]
        if len(linhas) != 1:
            return False
        tamanho_unico = str(linhas[0].get("tamanho") or linhas[0].get("nome") or "").strip()
        return bool(tamanho_unico and tamanho_unico == self._tamanho_base_molde_separado(molde))

    @staticmethod
    def _tamanho_base_molde_separado(molde: dict) -> str:
        tamanho = str(molde.get("tamanho_extraido") or "").strip()
        if tamanho:
            return tamanho
        nome = str(molde.get("nome_molde") or "").strip()
        if " - " in nome:
            return nome.rsplit(" - ", 1)[-1].strip()
        return ""

    def _valores_ponto(self, molde: dict | None, ponto_idx: int | None) -> dict[str, dict]:
        if not isinstance(molde, dict) or ponto_idx is None:
            return {}
        ponto = self._ponto_contorno_por_indice(molde, ponto_idx)
        for pontos_cfg in self._fontes_pontos_graduacao(molde):
            dados = self._dados_graduacao_por_ponto(pontos_cfg, ponto)
            valores = self._valores_dados_graduacao(dados)
            if valores:
                return valores
            dados = pontos_cfg.get(str(int(ponto_idx)))
            if isinstance(dados, dict):
                valores = self._valores_dados_graduacao(dados)
                if valores:
                    return valores
        return {}

    def _ponto_contorno_por_indice(self, molde: dict, ponto_idx: int | None) -> QPointF | None:
        if ponto_idx is None:
            return None
        pontos = self._pontos_contorno(molde)
        idx = int(ponto_idx)
        return QPointF(pontos[idx]) if 0 <= idx < len(pontos) else None

    def _fontes_pontos_graduacao(self, molde: dict) -> list[dict]:
        fontes: list[dict] = []
        tabela = molde.get("graduacao_tabela")
        if isinstance(tabela, dict) and isinstance(tabela.get("pontos"), dict):
            fontes.append(tabela.get("pontos") or {})
        legado = molde.get("graduacao_pontos")
        if isinstance(legado, dict) and legado not in fontes:
            fontes.append(legado)
        return fontes

    def _dados_graduacao_por_ponto(self, pontos_cfg: dict, ponto: QPointF | None) -> dict | None:
        if ponto is None or not isinstance(pontos_cfg, dict):
            return None
        melhor: tuple[float, dict] | None = None
        for dados in pontos_cfg.values():
            if not isinstance(dados, dict):
                continue
            ponto_dados = self._ponto_qt(dados.get("ponto"))
            if ponto_dados is None:
                continue
            dist = self._dist(ponto, ponto_dados)
            if dist <= 1e-5 and (melhor is None or dist < melhor[0]):
                melhor = (dist, dados)
        return melhor[1] if melhor else None

    @staticmethod
    def _valores_dados_graduacao(dados: dict | None) -> dict[str, dict]:
        if isinstance(dados, dict) and isinstance(dados.get("valores"), dict):
            return deepcopy(dados["valores"])
        return {}

    def _remover_graduacao_mesmo_ponto(self, pontos_cfg: dict, ponto: QPointF, chave_atual: str) -> None:
        if not isinstance(pontos_cfg, dict):
            return
        for chave, dados in list(pontos_cfg.items()):
            if str(chave) == str(chave_atual) or not isinstance(dados, dict):
                continue
            ponto_dados = self._ponto_qt(dados.get("ponto"))
            if ponto_dados is not None and self._dist(ponto, ponto_dados) <= 1e-5:
                pontos_cfg.pop(chave, None)

    def _fechar(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Tabela finalizada. Voltando para Selecionar.")

    @staticmethod
    def _repintar_canvas_agora(canvas) -> None:
        if canvas is None:
            return
        if hasattr(canvas, "update"):
            canvas.update()
        if hasattr(canvas, "repaint"):
            canvas.repaint()

    def _status(self, canvas, texto: str):
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)

    @staticmethod
    def _ponto_qt(valor) -> QPointF | None:
        try:
            if isinstance(valor, QPointF):
                x, y = valor.x(), valor.y()
            elif isinstance(valor, dict):
                x, y = valor["x"], valor["y"]
            elif isinstance(valor, (list, tuple)) and len(valor) >= 2:
                x, y = valor[0], valor[1]
            else:
                return None
            x, y = float(x), float(y)
            if not isfinite(x) or not isfinite(y):
                return None
            return QPointF(x, y)
        except Exception:
            return None

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _distancia_ponto_segmento(ponto: QPointF, a: QPointF, b: QPointF) -> float:
        ax, ay = float(a.x()), float(a.y())
        bx, by = float(b.x()), float(b.y())
        px, py = float(ponto.x()), float(ponto.y())
        dx, dy = bx - ax, by - ay
        comprimento2 = dx * dx + dy * dy
        if comprimento2 <= 1e-12:
            return hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / comprimento2))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return hypot(px - proj_x, py - proj_y)
