from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, degrees, hypot, isfinite, radians, sin

from PySide6.QtCore import QLocale, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QValidator
from PySide6.QtWidgets import (
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QMessageBox,
)

from core.graduacao import grade_graduacao_padrao
from core.formatacao import normalizar_decimal_ponto, numero_decimal_ponto
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class MedidaCmSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale.c())
        self.setRange(0.0, 1000.0)
        self.setDecimals(3)
        self.setSingleStep(0.05)
        self.setSpecialValueText("")

    def textFromValue(self, value: float) -> str:  # noqa: N802
        if abs(float(value or 0.0)) <= 1e-9:
            return ""
        texto = f"{float(value):.3f}".rstrip("0").rstrip(".")
        return f"{texto} cm"

    def valueFromText(self, text: str) -> float:  # noqa: N802
        texto = str(text or "").lower()
        try:
            return numero_decimal_ponto(texto, float(self.value()), ("cm",))
        except ValueError:
            return float(self.value())

    def validate(self, text: str, pos: int):  # noqa: N802
        try:
            texto = normalizar_decimal_ponto(str(text or "").lower(), ("cm",))
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
            return valor
        return float(self.value())


class GraduarTabelaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:graduar_tabela"
        self.setWindowTitle("Graduar via tabela")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.resize(360, 520)
        self.setMinimumSize(330, 470)
        self._ferramenta = None
        self._canvas = None
        self._bloquear_eventos = False
        self._base_row = 0
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QComboBox, QDoubleSpinBox {
                background:#ffffff;
                color:#111111;
                border:1px solid #b5bcc3;
                min-height:22px;
            }
            QTableWidget {
                background:#ffffff;
                color:#111111;
                gridline-color:#d9dde2;
                border:1px solid #b5bcc3;
            }
            QHeaderView::section {
                background:#f2f2f2;
                color:#111111;
                border:1px solid #c8cdd3;
                padding:4px;
                font-weight:600;
            }
            QPushButton {
                background:#f8f8f8;
                color:#111111;
                border:1px solid #b8bec5;
                min-height:24px;
                padding:2px 6px;
            }
            QPushButton:hover { background:#ffffff; }
            QPushButton:pressed {
                background:#2b7cd3;
                color:#ffffff;
                border:1px solid #0f5fae;
                padding-top:3px;
                padding-left:7px;
            }
            """
        )
        self._construir_ui()

    def _construir_ui(self):
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(6)

        linha_ponto = QHBoxLayout()
        linha_ponto.addWidget(QLabel("Nº ponto"))
        self.cmb_ponto = QComboBox()
        self.cmb_ponto.currentIndexChanged.connect(self._ponto_alterado)
        linha_ponto.addWidget(self.cmb_ponto, 1)
        raiz.addLayout(linha_ponto)

        tabs = QTabWidget()
        self.tabs = tabs
        pagina_dxdy = QWidget()
        lay_dxdy = QVBoxLayout(pagina_dxdy)
        lay_dxdy.setContentsMargins(0, 0, 0, 0)
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Tamanho", "DX (cm)", "DY (cm)"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl.itemChanged.connect(self._celula_alterada)
        lay_dxdy.addWidget(self.tbl)
        tabs.addTab(pagina_dxdy, "DX / DY")

        pagina_dist = QWidget()
        lay_dist = QVBoxLayout(pagina_dist)
        lay_dist.setContentsMargins(0, 0, 0, 0)
        self.tbl_polar = QTableWidget(0, 3)
        self.tbl_polar.setHorizontalHeaderLabels(["Tamanho", "Dist.(cm)", "Ang°"])
        self.tbl_polar.verticalHeader().setVisible(False)
        self.tbl_polar.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_polar.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_polar.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_polar.itemChanged.connect(self._celula_polar_alterada)
        lay_dist.addWidget(self.tbl_polar)
        tabs.addTab(pagina_dist, "Distância / Ângulo")

        pagina_perimetro = QWidget()
        lay_perimetro = QVBoxLayout(pagina_perimetro)
        lay_perimetro.setContentsMargins(0, 0, 0, 0)
        self.tbl_perimetro = QTableWidget(0, 7)
        self.tbl_perimetro.setHorizontalHeaderLabels(
            ["Tamanho", "Perim. X", "Dif. X", "Perim. Y", "Dif. Y", "Total", "Dif. total"]
        )
        self.tbl_perimetro.verticalHeader().setVisible(False)
        self.tbl_perimetro.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in range(1, 7):
            self.tbl_perimetro.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        lay_perimetro.addWidget(self.tbl_perimetro)
        tabs.addTab(pagina_perimetro, "Perímetro")
        raiz.addWidget(tabs, 1)

        botoes_topo = QGridLayout()
        self.btn_aplicar = QPushButton("Aplicar")
        self.btn_zerar_dx = QPushButton("DX = 0")
        self.btn_zerar_dy = QPushButton("DY = 0")
        self.btn_aplicar.clicked.connect(self._aplicar)
        self.btn_zerar_dx.clicked.connect(lambda: self._preencher_coluna_atual(1, 0.0))
        self.btn_zerar_dy.clicked.connect(lambda: self._preencher_coluna_atual(2, 0.0))
        botoes_topo.addWidget(self.btn_aplicar, 0, 0)
        botoes_topo.addWidget(self.btn_zerar_dx, 0, 1)
        botoes_topo.addWidget(self.btn_zerar_dy, 0, 2)
        raiz.addLayout(botoes_topo)
        tabs.currentChanged.connect(self._aba_alterada)

        linha_inc = QHBoxLayout()
        self.chk_incremental = QCheckBox("Incremental")
        self.chk_incremental.setChecked(True)
        self.sp_incremento = MedidaCmSpinBox()
        linha_inc.addWidget(self.chk_incremental)
        linha_inc.addWidget(self.sp_incremento, 1)
        raiz.addLayout(linha_inc)

        grade_setas = QGridLayout()
        self.btn_cima = QPushButton("▲")
        self.btn_baixo = QPushButton("▼")
        self.btn_esq = QPushButton("◀")
        self.btn_dir = QPushButton("▶")
        self.btn_zero = QPushButton("0")
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
        raiz.addLayout(grade_setas)

        botoes_copia = QGridLayout()
        for texto, slot, linha, col in (
            ("Copiar", self._copiar, 0, 0),
            ("Colar", self._colar, 1, 0),
            ("Inverte DX", lambda: self._inverter_coluna(1), 0, 1),
            ("Inverte DY", lambda: self._inverter_coluna(2), 0, 2),
            ("Colar DX", lambda: self._colar_coluna(1), 1, 1),
            ("Colar DY", lambda: self._colar_coluna(2), 1, 2),
        ):
            btn = QPushButton(texto)
            btn.clicked.connect(slot)
            botoes_copia.addWidget(btn, linha, col)
        raiz.addLayout(botoes_copia)
        self._aba_alterada(0)

    def conectar(self, ferramenta, canvas):
        self._ferramenta = ferramenta
        self._canvas = canvas

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
            cor = str(tamanho.get("cor") or "")
            if cor:
                item_t.setBackground(QColor(cor))
            if row == base_row:
                self._destacar_item_tamanho_base(item_t, cor)
            self.tbl.setItem(row, 0, item_t)
            item_polar_t = QTableWidgetItem(nome)
            item_polar_t.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_polar_t.setTextAlignment(Qt.AlignCenter)
            if cor:
                item_polar_t.setBackground(QColor(cor))
            if row == base_row:
                self._destacar_item_tamanho_base(item_polar_t, cor)
            self.tbl_polar.setItem(row, 0, item_polar_t)

            dados = valores.get(nome, {}) if isinstance(valores, dict) else {}
            for col, chave in ((1, "dx"), (2, "dy")):
                item = QTableWidgetItem(self._formatar_float(dados.get(chave, 0.0)))
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
            cor = str(linha.get("cor") or "")
            base = bool(linha.get("base", False))
            item_t = QTableWidgetItem(str(linha.get("tamanho") or ""))
            item_t.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_t.setTextAlignment(Qt.AlignCenter)
            if cor:
                item_t.setBackground(QColor(cor))
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
                item = QTableWidgetItem(self._formatar_float(linha.get(chave, 0.0), casas=2))
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
                item.setText(self._formatar_float(valor))
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
                fator = 1 if row > base_row else (-1 if row < base_row else 0)
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
        self.btn_zerar_dx.setText("dist" if polar else "DX = 0")
        self.btn_zerar_dy.setText("âng" if polar else "DY = 0")

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
                saida.append({
                    "tamanho": item.text().strip(),
                    "cor": item.background().color().name(),
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
        return numero_decimal_ponto(item.text(), 0.0)

    def _set_valor(self, row: int, col: int, valor: float):
        item = self.tbl.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tbl.setItem(row, col, item)
        item.setText(self._formatar_float(valor))
        item.setTextAlignment(Qt.AlignCenter)
        if row == self._linha_base():
            self._destacar_item_valor_base(item)

    def _set_valor_polar(self, row: int, col: int, valor: float, *, casas: int = 3):
        item = self.tbl_polar.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tbl_polar.setItem(row, col, item)
        item.setText(self._formatar_float(valor, casas=casas))
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
        return numero_decimal_ponto(item.text(), 0.0)

    @staticmethod
    def _destacar_item_tamanho_base(item: QTableWidgetItem, cor: str):
        fonte = item.font()
        fonte.setBold(True)
        item.setFont(fonte)
        cor_base = QColor(str(cor or ""))
        if cor_base.isValid():
            item.setBackground(cor_base)
            luminosidade = (0.299 * cor_base.red()) + (0.587 * cor_base.green()) + (0.114 * cor_base.blue())
            item.setForeground(QColor("#111111" if luminosidade >= 150 else "#ffffff"))

    @staticmethod
    def _destacar_item_valor_base(item: QTableWidgetItem):
        fonte = item.font()
        fonte.setBold(True)
        item.setFont(fonte)
        item.setForeground(QColor("#ffffff"))
        item.setBackground(QColor("#2b7cd3"))

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
        self._modo_copia_graduacao = False
        self._graduacao_copiada: dict | None = None
        self._origem_copia: tuple[int, int] | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        molde_inicial = self._molde_selecionado(canvas)
        if molde_inicial is not None and not self._preparar_molde_para_tabela(canvas, molde_inicial):
            molde_inicial = None
        self._definir_molde_idx(canvas, molde_inicial)
        self._ponto_idx = None
        self._hover_ponto_idx = None
        self._pontos_selecionados.clear()
        if self._molde_idx is not None and hasattr(canvas, "_selecionados"):
            canvas._selecionados = {self._molde_idx}
        self._observar_canvas(canvas)
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
        pontos = self._pontos_contorno(canvas.cena.elementos[self._molde_idx])
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
            cor_ponto = QColor("#008cff")
            painter.setPen(QPen(cor_ponto, 1.6))
            painter.setBrush(QColor(0, 140, 255, 34))
            painter.drawEllipse(tela, 5, 5)
        for idx in selecionados:
            tela = canvas._cena_para_tela(pontos[idx])
            ativo = idx == self._ponto_idx
            cor = QColor("#ff006e" if ativo else "#00d6ff")
            painter.setPen(QPen(cor, 2.0))
            painter.setBrush(QColor(cor.red(), cor.green(), cor.blue(), 80))
            painter.drawEllipse(tela, 7, 7)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(tela.x() + 8), int(tela.y() - 8), str(idx + 1))
        if hover_idx is not None:
            idx = int(hover_idx)
            tela = canvas._cena_para_tela(pontos[idx])
            cor_hover = QColor("#008cff")
            painter.setPen(QPen(cor_hover, 3.0))
            painter.setBrush(QColor(0, 140, 255, 60))
            painter.drawEllipse(tela, 11, 11)
            painter.drawLine(QPointF(tela.x() - 14, tela.y()), QPointF(tela.x() - 8, tela.y()))
            painter.drawLine(QPointF(tela.x() + 8, tela.y()), QPointF(tela.x() + 14, tela.y()))
            painter.drawLine(QPointF(tela.x(), tela.y() - 14), QPointF(tela.x(), tela.y() - 8))
            painter.drawLine(QPointF(tela.x(), tela.y() + 8), QPointF(tela.x(), tela.y() + 14))
            painter.setPen(cor_hover)
            painter.drawText(int(tela.x() + 13), int(tela.y() - 12), str(idx + 1))
        painter.restore()

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
            pontos_cfg[chave] = {
                "indice": int(ponto_idx),
                "numero": int(ponto_idx) + 1,
                "ponto": (float(pontos[ponto_idx].x()), float(pontos[ponto_idx].y())),
                "valores": deepcopy(valores),
            }
        molde["graduacao_pontos"] = deepcopy(pontos_cfg)
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
        chave = id(canvas)
        if chave in self._canvas_observados:
            return
        sinal = getattr(canvas, "elementos_alterados", None)
        if sinal is None:
            return
        try:
            sinal.connect(lambda *_args, canvas=canvas: self._quando_canvas_elementos_alterados(canvas))
            self._canvas_observados.add(chave)
        except Exception:
            return

    def _quando_canvas_elementos_alterados(self, canvas) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is None or not dialog.isVisible():
            return
        selecionado = self._molde_selecionado(canvas)
        if selecionado is not None and selecionado != self._molde_idx:
            self._definir_molde_idx(canvas, selecionado)
            self._ponto_idx = None
            self._hover_ponto_idx = None
            self._pontos_selecionados.clear()
        if not self._molde_atual_corresponde(canvas):
            self._fechar_dialog_molde_indisponivel(canvas)
            return
        pontos = self._pontos_contorno(self._molde_atual(canvas))
        if not pontos:
            self._fechar_dialog_molde_indisponivel(canvas)
            return
        if self._ponto_idx is not None and not (0 <= self._ponto_idx < len(pontos)):
            self._ponto_idx = None
        self._pontos_selecionados = self._pontos_validos_selecionados(len(pontos))
        self._atualizar_dialog(canvas)
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
        dialog = self._obter_dialog(canvas)
        molde = self._molde_atual(canvas)
        pontos = self._pontos_contorno(molde) if molde else []
        if molde is not None:
            self._garantir_tamanhos_no_molde(molde)
        if self._ponto_idx is not None and not self._pontos_selecionados:
            self._pontos_selecionados = {int(self._ponto_idx)}
        if pontos:
            self._pontos_selecionados = self._pontos_validos_selecionados(len(pontos))
        dialog.definir_pontos(len(pontos), self._ponto_idx)
        tamanhos = self._tamanhos_molde(molde)
        valores = self._valores_ponto(molde, self._ponto_idx)
        dialog.definir_tamanhos(tamanhos, valores)
        self._atualizar_perimetros_dialog(canvas)

    def _atualizar_perimetros_dialog(self, canvas) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is None:
            return
        molde = self._molde_atual(canvas)
        pontos = self._pontos_contorno(molde) if molde else []
        tamanhos = self._tamanhos_molde(molde)
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
        dialog.definir_tamanhos(self._tamanhos_molde(molde), deepcopy(self._graduacao_copiada))
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
        origem = None
        for chave in (
            "pontos_controle_principais",
            "controle_cantos",
            "pontos_graduacao",
            "pontos_controle_curva",
            "pontos_controle",
            "pontos",
        ):
            valor = molde.get(chave)
            if isinstance(valor, list) and valor:
                origem = valor
                break
        pontos: list[QPointF] = []
        for item in origem or []:
            ponto = self._ponto_qt(item)
            if ponto is not None:
                pontos.append(ponto)
        if len(pontos) > 1 and self._dist(pontos[0], pontos[-1]) <= 1e-7:
            pontos.pop()
        return pontos

    def _tamanhos_molde(self, molde: dict | None) -> list[dict]:
        linhas = molde.get("graduacao_tamanhos") if isinstance(molde, dict) else None
        if isinstance(linhas, list) and linhas:
            return [dict(l) for l in linhas if isinstance(l, dict) and l.get("ativo", True)]
        _grade_nome, linhas_padrao = grade_graduacao_padrao()
        return [dict(linha) for linha in linhas_padrao]

    def _garantir_tamanhos_no_molde(self, molde: dict, dialog: GraduarTabelaDialog | None = None) -> None:
        linhas = molde.get("graduacao_tamanhos") if isinstance(molde, dict) else None
        if isinstance(linhas, list) and linhas:
            return
        tamanhos = dialog._tamanhos_atuais() if dialog is not None else self._tamanhos_molde(molde)
        linhas_normalizadas = [dict(linha) for linha in tamanhos if isinstance(linha, dict)]
        if not linhas_normalizadas:
            return
        if not any(linha.get("base") for linha in linhas_normalizadas):
            linhas_normalizadas[len(linhas_normalizadas) // 2]["base"] = True
        molde["graduacao_tamanhos"] = linhas_normalizadas
        molde["graduacao_tamanhos_ativos"] = [
            str(linha.get("tamanho") or linha.get("nome") or "")
            for linha in linhas_normalizadas
            if linha.get("ativo", True) and str(linha.get("tamanho") or linha.get("nome") or "").strip()
        ]
        grade_nome, _linhas_padrao = grade_graduacao_padrao()
        molde.setdefault("graduacao_grade_nome", grade_nome)

    def _preparar_molde_para_tabela(self, canvas, molde_idx: int | None) -> bool:
        if molde_idx is None or not (0 <= int(molde_idx) < len(canvas.cena.elementos)):
            return False
        molde = canvas.cena.elementos[int(molde_idx)]
        if not self._eh_molde_graduavel(molde):
            return False
        if not self._eh_tamanho_separado_sem_grade(molde):
            return True
        if not self._confirmar_definir_grade_molde_separado(canvas, molde):
            self._status(canvas, "Tabela: esse molde separado ainda não possui grade.")
            return False
        self._definir_grade_base_molde_separado(molde)
        self._status(canvas, "Tabela: grade definida; o tamanho separado virou base.")
        return True

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
        caixa.setText("Esse molde não possui grade.\nDeseja definir agora?")
        caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        caixa.setDefaultButton(QMessageBox.Yes)
        traduzir = getattr(parent, "_traduzir_botoes_padrao_message_box", None)
        if callable(traduzir):
            traduzir(caixa)
        return caixa.exec() == QMessageBox.Yes

    def _definir_grade_base_molde_separado(self, molde: dict) -> None:
        grade_nome, linhas_padrao = grade_graduacao_padrao()
        linhas = [dict(linha) for linha in linhas_padrao if isinstance(linha, dict)]
        if not linhas:
            return

        tamanho_base = self._tamanho_base_molde_separado(molde)
        base_idx = next((idx for idx, linha in enumerate(linhas) if bool(linha.get("base"))), len(linhas) // 2)
        if tamanho_base:
            idx_tamanho = next(
                (
                    idx
                    for idx, linha in enumerate(linhas)
                    if str(linha.get("tamanho") or linha.get("nome") or "").strip() == tamanho_base
                ),
                None,
            )
            if idx_tamanho is None:
                linhas[base_idx]["tamanho"] = tamanho_base
                idx_tamanho = base_idx
            base_idx = int(idx_tamanho)
            grade_nome = self._grade_nome_com_base(grade_nome, tamanho_base)

        cor_base = str(molde.get("cor") or "").strip()
        for idx, linha in enumerate(linhas):
            linha["base"] = idx == base_idx
            linha["ativo"] = bool(linha.get("ativo", True))
            if idx == base_idx and cor_base:
                linha["cor"] = cor_base

        molde["graduacao_grade_nome"] = grade_nome
        molde["graduacao_tamanhos"] = linhas
        molde["graduacao_tamanhos_ativos"] = [
            str(linha.get("tamanho") or linha.get("nome") or "")
            for linha in linhas
            if linha.get("ativo", True) and str(linha.get("tamanho") or linha.get("nome") or "").strip()
        ]
        molde["mostrar_graduacao"] = True

    @staticmethod
    def _eh_tamanho_separado_sem_grade(molde: dict) -> bool:
        if not isinstance(molde, dict):
            return False
        if str(molde.get("origem_extracao") or "").strip() != "separar_tamanho":
            return False
        linhas = molde.get("graduacao_tamanhos")
        return not (isinstance(linhas, list) and any(isinstance(linha, dict) for linha in linhas))

    @staticmethod
    def _tamanho_base_molde_separado(molde: dict) -> str:
        tamanho = str(molde.get("tamanho_extraido") or "").strip()
        if tamanho:
            return tamanho
        nome = str(molde.get("nome_molde") or "").strip()
        if " - " in nome:
            return nome.rsplit(" - ", 1)[-1].strip()
        return ""

    @staticmethod
    def _grade_nome_com_base(grade_nome: str, tamanho_base: str) -> str:
        grade = str(grade_nome or "").strip()
        base = str(tamanho_base or "").strip()
        if not grade or not base:
            return grade
        inicio = grade.rfind("(")
        fim = grade.rfind(")")
        if 0 <= inicio < fim:
            return f"{grade[:inicio + 1]}{base}{grade[fim:]}"
        return f"{grade}({base})"

    def _valores_ponto(self, molde: dict | None, ponto_idx: int | None) -> dict[str, dict]:
        if not isinstance(molde, dict) or ponto_idx is None:
            return {}
        tabela = molde.get("graduacao_tabela")
        if isinstance(tabela, dict):
            pontos = tabela.get("pontos")
            if isinstance(pontos, dict):
                dados = pontos.get(str(int(ponto_idx)))
                if isinstance(dados, dict) and isinstance(dados.get("valores"), dict):
                    return deepcopy(dados["valores"])
        legado = molde.get("graduacao_pontos")
        if isinstance(legado, dict):
            dados = legado.get(str(int(ponto_idx)))
            if isinstance(dados, dict) and isinstance(dados.get("valores"), dict):
                return deepcopy(dados["valores"])
        return {}

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
