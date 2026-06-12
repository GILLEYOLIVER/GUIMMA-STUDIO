from __future__ import annotations

from copy import deepcopy
from math import hypot, isfinite

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPen
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
)

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class MedidaCmSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
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
        texto = str(text or "").lower().replace("cm", "").replace(",", ".").strip()
        try:
            return float(texto or 0.0)
        except ValueError:
            return 0.0


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
        lay_dist.addWidget(QLabel("Distância / Ângulo será usado para graduação polar em uma próxima etapa."))
        lay_dist.addStretch(1)
        tabs.addTab(pagina_dist, "Distância / Ângulo")
        tabs.setTabEnabled(1, False)
        raiz.addWidget(tabs, 1)

        botoes_topo = QGridLayout()
        self.btn_aplicar = QPushButton("Aplicar")
        self.btn_zerar_dx = QPushButton("DX = 0")
        self.btn_zerar_dy = QPushButton("DY = 0")
        self.btn_aplicar.clicked.connect(self._aplicar)
        self.btn_zerar_dx.clicked.connect(lambda: self._preencher_coluna(1, 0.0))
        self.btn_zerar_dy.clicked.connect(lambda: self._preencher_coluna(2, 0.0))
        botoes_topo.addWidget(self.btn_aplicar, 0, 0)
        botoes_topo.addWidget(self.btn_zerar_dx, 0, 1)
        botoes_topo.addWidget(self.btn_zerar_dy, 0, 2)
        raiz.addLayout(botoes_topo)

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
        self.btn_cima.clicked.connect(lambda: self._aplicar_incremento(0.0, -1.0))
        self.btn_baixo.clicked.connect(lambda: self._aplicar_incremento(0.0, 1.0))
        self.btn_esq.clicked.connect(lambda: self._aplicar_incremento(-1.0, 0.0))
        self.btn_dir.clicked.connect(lambda: self._aplicar_incremento(1.0, 0.0))
        self.btn_zero.clicked.connect(lambda: self._aplicar_incremento(0.0, 0.0, zerar=True))
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

            dados = valores.get(nome, {}) if isinstance(valores, dict) else {}
            for col, chave in ((1, "dx"), (2, "dy")):
                item = QTableWidgetItem(self._formatar_float(dados.get(chave, 0.0)))
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                if row == base_row:
                    self._destacar_item_valor_base(item)
                self.tbl.setItem(row, col, item)
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

    def _ponto_alterado(self):
        if self._bloquear_eventos or self._ferramenta is None or self._canvas is None:
            return
        idx = self.cmb_ponto.currentData()
        self._ferramenta.selecionar_ponto(self._canvas, int(idx) if idx is not None else None)

    def _celula_alterada(self, _item):
        if self._bloquear_eventos:
            return
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
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _aplicar_incremento(self, dx_dir: float, dy_dir: float, *, zerar: bool = False):
        row_atual = self.tbl.currentRow()
        if row_atual < 0:
            row_atual = 0
        base_row = self._linha_base()
        incremento = float(self.sp_incremento.value())
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            if zerar:
                self._set_valor(row, 1, 0.0)
                self._set_valor(row, 2, 0.0)
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
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _copiar(self):
        self._copiado = self.valores()

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
        self._bloquear_eventos = False
        self._celula_alterada(None)

    def _inverter_coluna(self, col: int):
        self._bloquear_eventos = True
        for row in range(self.tbl.rowCount()):
            self._set_valor(row, col, -self._valor_item(row, col))
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
        try:
            return float((item.text() or "0").replace(",", "."))
        except ValueError:
            return 0.0

    def _set_valor(self, row: int, col: int, valor: float):
        item = self.tbl.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tbl.setItem(row, col, item)
        item.setText(self._formatar_float(valor))
        item.setTextAlignment(Qt.AlignCenter)
        if row == self._linha_base():
            self._destacar_item_valor_base(item)

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
    def _formatar_float(valor) -> str:
        try:
            numero = float(valor or 0.0)
        except (TypeError, ValueError):
            numero = 0.0
        texto = f"{numero:.3f}".rstrip("0").rstrip(".")
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
        self._pontos_selecionados: set[int] = set()
        self._canvas_observados: set[int] = set()

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._definir_molde_idx(canvas, self._molde_selecionado(canvas))
        self._ponto_idx = None
        self._pontos_selecionados.clear()
        self._observar_canvas(canvas)
        dialog = self._obter_dialog(canvas)
        dialog.conectar(self, canvas)
        self._atualizar_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Tabela: selecione um molde e clique no ponto do contorno para graduar.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if canvas is not None:
            canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position()) if hasattr(canvas, "_ponto_com_snap") else QPointF(event.position())
        molde_idx = self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            self._status(canvas, "Tabela: clique sobre um molde ou sobre um ponto do contorno.")
            event.accept()
            return True
        if molde_idx != self._molde_idx:
            self._definir_molde_idx(canvas, molde_idx)
            self._ponto_idx = None
            self._pontos_selecionados.clear()
            canvas._selecionados = {molde_idx}
        ponto_idx = self._ponto_mais_proximo(canvas.cena.elementos[molde_idx], pos)
        if ponto_idx is not None:
            self._selecionar_ponto_contorno(canvas, ponto_idx, acumular=self._evento_ctrl(event))
        self._atualizar_dialog(canvas)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._molde_idx is None:
            return
        if not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return
        pontos = self._pontos_contorno(canvas.cena.elementos[self._molde_idx])
        selecionados = self._pontos_validos_selecionados(len(pontos))
        if not selecionados:
            return
        painter.save()
        font = QFont("Arial", 8)
        font.setBold(True)
        painter.setFont(font)
        for idx in selecionados:
            tela = canvas._cena_para_tela(pontos[idx])
            ativo = idx == self._ponto_idx
            cor = QColor("#ff006e" if ativo else "#00d6ff")
            painter.setPen(QPen(cor, 2.0))
            painter.setBrush(QColor(cor.red(), cor.green(), cor.blue(), 80))
            painter.drawEllipse(tela, 7, 7)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(tela.x() + 8), int(tela.y() - 8), str(idx + 1))
        painter.restore()

    def selecionar_ponto(self, canvas, ponto_idx: int | None):
        self._ponto_idx = ponto_idx
        self._pontos_selecionados = {int(ponto_idx)} if ponto_idx is not None else set()
        self._atualizar_dialog(canvas)
        canvas.update()

    def atualizar_preview_dialog(self, canvas):
        self._salvar_valores_dialog(canvas, registrar_historico=False)
        canvas.update()

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
        dialog = self._obter_dialog(canvas)
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
            self._pontos_selecionados.clear()
        if not self._molde_atual_corresponde(canvas):
            self._fechar_dialog_molde_indisponivel(canvas)
            return
        pontos = self._pontos_contorno(self._molde_atual(canvas))
        if not pontos:
            self._fechar_dialog_molde_indisponivel(canvas)
            return
        if self._ponto_idx is None or not (0 <= self._ponto_idx < len(pontos)):
            self._ponto_idx = 0
        self._pontos_selecionados = self._pontos_validos_selecionados(len(pontos)) or {int(self._ponto_idx)}
        self._atualizar_dialog(canvas)
        canvas.update()

    def _fechar_dialog_molde_indisponivel(self, canvas) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._molde_idx = None
        self._molde_chave = None
        self._ponto_idx = None
        self._pontos_selecionados.clear()
        self._status(canvas, "Tabela fechada: o molde não está mais disponível no canvas.")
        if hasattr(canvas, "update"):
            canvas.update()

    def _atualizar_dialog(self, canvas):
        dialog = self._obter_dialog(canvas)
        molde = self._molde_atual(canvas)
        pontos = self._pontos_contorno(molde) if molde else []
        if self._ponto_idx is None and pontos:
            self._ponto_idx = 0
        if self._ponto_idx is not None and not self._pontos_selecionados:
            self._pontos_selecionados = {int(self._ponto_idx)}
        if pontos:
            self._pontos_selecionados = self._pontos_validos_selecionados(len(pontos))
        dialog.definir_pontos(len(pontos), self._ponto_idx)
        tamanhos = self._tamanhos_molde(molde)
        valores = self._valores_ponto(molde, self._ponto_idx)
        dialog.definir_tamanhos(tamanhos, valores)

    def _molde_atual(self, canvas) -> dict | None:
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return None
        molde = canvas.cena.elementos[self._molde_idx]
        return molde if isinstance(molde, dict) and molde.get("molde") else None

    def _definir_molde_idx(self, canvas, molde_idx: int | None) -> None:
        self._molde_idx = int(molde_idx) if molde_idx is not None else None
        molde = self._molde_atual(canvas)
        self._molde_chave = self._chave_molde(molde) if molde is not None else None

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
            return bool(event.modifiers() & Qt.ControlModifier)
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
            if 0 <= int(idx) < len(canvas.cena.elementos) and canvas.cena.elementos[int(idx)].get("molde"):
                return int(idx)
        return None

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        melhor: tuple[float, int] | None = None
        tolerancia = max(0.15, 16.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        for idx, el in enumerate(canvas.cena.elementos):
            if not isinstance(el, dict) or not el.get("molde"):
                continue
            ponto_idx = self._ponto_mais_proximo(el, pos)
            if ponto_idx is None:
                continue
            dist = self._dist(self._pontos_contorno(el)[ponto_idx], pos)
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, idx)
        return melhor[1] if melhor else None

    def _ponto_mais_proximo(self, molde: dict, pos: QPointF) -> int | None:
        pontos = self._pontos_contorno(molde)
        if not pontos:
            return None
        distancias = [(self._dist(ponto, pos), idx) for idx, ponto in enumerate(pontos)]
        return min(distancias, key=lambda item: item[0])[1]

    def _pontos_contorno(self, molde: dict | None) -> list[QPointF]:
        if not isinstance(molde, dict):
            return []
        origem = molde.get("controle_cantos") if isinstance(molde.get("controle_cantos"), list) else molde.get("pontos")
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
        return [
            {"tamanho": "P", "cor": "#c87575", "base": False},
            {"tamanho": "M", "cor": "#d60b0b", "base": True},
            {"tamanho": "G", "cor": "#5d95b7", "base": False},
        ]

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
