from __future__ import annotations

from copy import deepcopy
from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt, QLocale, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QValidator
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.formatacao import formatar_numero, normalizar_decimal_ponto, numero_decimal_ponto
from core.geometry_cpp_bridge import seam_offset_closed_cpp
from tools.tool_base import FerramentaBase
from tools.unidades import unidade_canvas
from ui.posicao_janelas import restaurar_posicao, salvar_posicao


ACABAMENTOS_COSTURA = (
    ("Canto reto", "canto_reto"),
    ("V aberto", "v_aberto"),
    ("V fechado", "v_fechado"),
    ("Degrau", "degrau"),
    ("45 graus", "45_graus"),
    ("90 graus", "90_graus"),
    ("90 graus invertido", "90_graus_invertido"),
)


class NumeroLimpoSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox que mostra 1 em vez de 1,00 e aceita vírgula decimal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale.c())

    def textFromValue(self, value: float) -> str:  # noqa: N802 - API Qt
        texto = formatar_numero(value, 2)
        if texto == "-0":
            texto = "0"
        return texto

    def valueFromText(self, text: str) -> float:  # noqa: N802 - API Qt
        texto = str(text or "").strip().replace(" ", "")
        return numero_decimal_ponto(texto, float(self.value()))

    def validate(self, text: str, pos: int):  # noqa: N802 - API Qt
        try:
            texto = normalizar_decimal_ponto(str(text or "").strip().replace(" ", ""))
        except Exception:
            return QValidator.Invalid, text, pos
        if texto in {"", "+", "-", "0.", "+0.", "-0."}:
            return QValidator.Intermediate, text, pos
        try:
            float(texto)
        except ValueError:
            return QValidator.Invalid, text, pos
        return QValidator.Acceptable, text, pos


class CosturaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:costura"
        self._unidade_sigla = "cm"
        self._unidade_fator = 1.0
        self.setWindowTitle("Costura")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(480)
        self.setStyleSheet(
            """
            QDialog { background:#f2f2f2; color:#111111; }
            QLabel { color:#111111; font-size:11px; }
            QComboBox, QDoubleSpinBox {
                background:#ffffff; color:#111111;
                border:1px solid #aeb4ba; min-height:21px;
                padding-left:3px;
            }
            QCheckBox { color:#111111; font-size:11px; }
            QTableWidget {
                background:#ffffff; color:#111111;
                gridline-color:#dddddd; border:1px solid #b9b9b9;
                selection-background-color:#0b84d8;
            }
            QHeaderView::section {
                background:#efefef; color:#111111;
                border:1px solid #c8c8c8; padding:3px;
                font-size:11px;
            }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(6)

        topo = QGridLayout()
        topo.setHorizontalSpacing(12)
        topo.setVerticalSpacing(5)
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(["Costura", "Offset"])
        self.cmb_posicao = QComboBox()
        self.cmb_posicao.addItems(["Selecionar", "Todo molde"])
        self.sp_costura = NumeroLimpoSpinBox()
        self.sp_costura.setRange(0.0, 999999.0)
        self.sp_costura.setDecimals(2)
        self.sp_costura.setSingleStep(0.1)
        self.sp_costura.setValue(1.0)
        self.sp_costura.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_costura_fim = QCheckBox("Largura do fim da costura (cm)")
        self.sp_costura_fim = NumeroLimpoSpinBox()
        self.sp_costura_fim.setRange(0.0, 999999.0)
        self.sp_costura_fim.setDecimals(2)
        self.sp_costura_fim.setSingleStep(0.1)
        self.sp_costura_fim.setValue(1.0)
        self.sp_costura_fim.setEnabled(False)
        self.sp_costura_fim.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_pique = QCheckBox("Pique")
        self.chk_pique.setChecked(True)
        self.cmb_pique = QComboBox()
        self.cmb_pique.addItems(["T", "V", "I", "Nenhum"])

        topo.addWidget(self.cmb_tipo, 0, 0, 1, 2)
        topo.addWidget(QLabel("Posição"), 0, 2)
        topo.addWidget(self.cmb_posicao, 0, 3)
        self.lbl_costura = QLabel("Costura (cm)")
        topo.addWidget(self.lbl_costura, 1, 0)
        topo.addWidget(self.sp_costura, 1, 1)
        topo.addWidget(self.chk_pique, 1, 2)
        topo.addWidget(self.cmb_pique, 1, 3)
        topo.addWidget(self.chk_costura_fim, 2, 0)
        topo.addWidget(self.sp_costura_fim, 2, 1)
        raiz.addLayout(topo)

        acab = QGridLayout()
        acab.setHorizontalSpacing(8)
        self.cmb_acab_ini = QComboBox()
        self.cmb_acab_fim = QComboBox()
        self._configurar_combo_acabamento(self.cmb_acab_ini)
        self._configurar_combo_acabamento(self.cmb_acab_fim)
        acab.addWidget(QLabel("Acabamento inicial"), 0, 0)
        acab.addWidget(self.cmb_acab_ini, 0, 1)
        acab.addWidget(QLabel("Acabamento final"), 0, 2)
        acab.addWidget(self.cmb_acab_fim, 0, 3)
        raiz.addLayout(acab)

        self.tabela = QTableWidget(0, 3)
        self.tabela.setHorizontalHeaderLabels(["Pos.", "Costura (cm)", "Acabamento"])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setMinimumHeight(132)
        self.tabela.setColumnWidth(0, 46)
        self.tabela.setColumnWidth(1, 82)
        self.tabela.setColumnWidth(2, 150)
        raiz.addWidget(self.tabela)

        rodape = QHBoxLayout()
        self.lbl_status = QLabel("Selecione um molde/contorno.")
        self.lbl_status.setWordWrap(True)
        rodape.addWidget(self.lbl_status, 1)
        raiz.addLayout(rodape)

        self.sp_costura.valueChanged.connect(self._sincronizar_largura_fim_desabilitada)
        self.chk_costura_fim.toggled.connect(self._alternar_largura_fim)
        self.cmb_acab_ini.currentIndexChanged.connect(lambda _idx: self._atualizar_tooltip_acabamento(self.cmb_acab_ini))
        self.cmb_acab_fim.currentIndexChanged.connect(lambda _idx: self._atualizar_tooltip_acabamento(self.cmb_acab_fim))
        self._atualizar_tooltip_acabamento(self.cmb_acab_ini)
        self._atualizar_tooltip_acabamento(self.cmb_acab_fim)
        self._alternar_largura_fim(False)

    def set_unidade(self, sigla: str, fator: float) -> None:
        fator_antigo = max(1e-9, float(getattr(self, "_unidade_fator", 1.0)))
        largura_inicio = float(self.sp_costura.value()) * fator_antigo
        largura_fim = float(self.sp_costura_fim.value()) * fator_antigo
        self._unidade_sigla = str(sigla or "cm")
        self._unidade_fator = max(1e-9, float(fator or 1.0))
        self.lbl_costura.setText(f"Costura ({self._unidade_sigla})")
        self.chk_costura_fim.setText(f"Largura do fim da costura ({self._unidade_sigla})")
        self.tabela.setHorizontalHeaderLabels(["Pos.", f"Costura ({self._unidade_sigla})", "Acabamento"])
        self.set_margem_cena(largura_inicio)
        if self.chk_costura_fim.isChecked():
            self.set_margem_fim_cena(largura_fim)

    def _para_unidade(self, valor_cena: float) -> float:
        return float(valor_cena) / self._unidade_fator

    def _para_cena(self, valor_unidade: float) -> float:
        return float(valor_unidade) * self._unidade_fator

    def _fmt_medida(self, valor_cena: float) -> str:
        return Ferramenta._fmt(self._para_unidade(valor_cena))

    def set_margem_cena(self, valor_cena: float) -> None:
        self.sp_costura.blockSignals(True)
        self.sp_costura.setValue(self._para_unidade(valor_cena))
        self.sp_costura.blockSignals(False)
        if not self.chk_costura_fim.isChecked():
            self.set_margem_fim_cena(valor_cena)

    def set_margem_fim_cena(self, valor_cena: float) -> None:
        self.sp_costura_fim.blockSignals(True)
        self.sp_costura_fim.setValue(self._para_unidade(valor_cena))
        self.sp_costura_fim.blockSignals(False)

    def _configurar_combo_acabamento(self, combo: QComboBox) -> None:
        combo.setIconSize(QSize(42, 28))
        combo.setMinimumWidth(128)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.view().setIconSize(QSize(42, 28))
        for nome, chave in ACABAMENTOS_COSTURA:
            combo.addItem(self._icone_acabamento(nome), "", nome)
            combo.setItemData(combo.count() - 1, nome, Qt.ToolTipRole)
            combo.setItemData(combo.count() - 1, chave, Qt.AccessibleDescriptionRole)

    def _atualizar_tooltip_acabamento(self, combo: QComboBox) -> None:
        combo.setToolTip(self._acabamento_combo(combo))

    @staticmethod
    def _acabamento_combo(combo: QComboBox) -> str:
        return str(combo.currentData() or combo.currentText() or "Canto reto")

    def acabamento_inicial(self) -> str:
        return self._acabamento_combo(self.cmb_acab_ini)

    def acabamento_final(self) -> str:
        return self._acabamento_combo(self.cmb_acab_fim)

    @classmethod
    def nomes_acabamentos(cls) -> list[str]:
        return [nome for nome, _chave in ACABAMENTOS_COSTURA]

    @classmethod
    def _icone_acabamento(cls, nome: str) -> QIcon:
        pix = QPixmap(44, 30)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            cls._desenhar_icone_acabamento(painter, nome)
        finally:
            painter.end()
        return QIcon(pix)

    @staticmethod
    def _desenhar_icone_acabamento(painter: QPainter, nome: str) -> None:
        chave = str(nome or "").strip().lower()
        azul = QColor("#2b6f9e")
        amarelo = QColor("#d2d332")
        cinza = QColor("#9b9b9b")
        claro = QColor("#f7f7f7")

        painter.setPen(QPen(claro, 1.0))
        painter.drawRect(0, 0, 43, 29)

        base = QPainterPath(QPointF(9.0, 4.0))
        base.lineTo(QPointF(26.0, 15.0))
        base.lineTo(QPointF(9.0, 26.0))
        pen_base = QPen(cinza, 3.0, Qt.SolidLine)
        pen_base.setCapStyle(Qt.SquareCap)
        pen_base.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen_base)
        painter.drawPath(base)

        cor = amarelo if "invertido" in chave else azul
        pen = QPen(cor, 2.2, Qt.SolidLine)
        pen.setCapStyle(Qt.SquareCap)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)

        path = QPainterPath()
        if "aberto" in chave:
            path.moveTo(QPointF(13.0, 5.0))
            path.lineTo(QPointF(30.0, 15.0))
            path.moveTo(QPointF(13.0, 25.0))
            path.lineTo(QPointF(30.0, 15.0))
        elif "fechado" in chave:
            path.moveTo(QPointF(13.0, 5.0))
            path.lineTo(QPointF(30.0, 15.0))
            path.lineTo(QPointF(13.0, 25.0))
            path.lineTo(QPointF(13.0, 5.0))
        elif "degrau" in chave:
            path.moveTo(QPointF(13.0, 5.0))
            path.lineTo(QPointF(24.0, 5.0))
            path.lineTo(QPointF(24.0, 15.0))
            path.lineTo(QPointF(32.0, 15.0))
            path.lineTo(QPointF(24.0, 15.0))
            path.lineTo(QPointF(24.0, 25.0))
            path.lineTo(QPointF(13.0, 25.0))
        elif "45" in chave:
            path.moveTo(QPointF(12.0, 25.0))
            path.lineTo(QPointF(31.0, 6.0))
            painter.drawPath(path)
            painter.setPen(QPen(cinza, 1.0))
            painter.drawText(25, 13, "45")
            return
        elif "90" in chave:
            if "invertido" in chave:
                path.moveTo(QPointF(13.0, 25.0))
                path.lineTo(QPointF(13.0, 8.0))
                path.lineTo(QPointF(31.0, 8.0))
            else:
                path.moveTo(QPointF(13.0, 25.0))
                path.lineTo(QPointF(31.0, 25.0))
                path.lineTo(QPointF(31.0, 8.0))
            painter.drawPath(path)
            painter.setPen(QPen(cinza, 1.0))
            painter.drawText(25, 14, "90")
            return
        else:
            path.moveTo(QPointF(13.0, 4.0))
            path.lineTo(QPointF(31.0, 15.0))
            path.lineTo(QPointF(13.0, 26.0))
        painter.drawPath(path)

    def _alternar_largura_fim(self, ativo: bool) -> None:
        ativo = bool(ativo)
        self.sp_costura_fim.setEnabled(ativo)
        if not ativo:
            self._sincronizar_largura_fim_desabilitada()
        self.sp_costura_fim.setStyleSheet(
            "" if ativo else "QDoubleSpinBox { background:#eeeeee; color:#8b8b8b; border:1px solid #c7c7c7; }"
        )

    def _sincronizar_largura_fim_desabilitada(self, *_args) -> None:
        if self.chk_costura_fim.isChecked():
            return
        self.sp_costura_fim.blockSignals(True)
        self.sp_costura_fim.setValue(float(self.sp_costura.value()))
        self.sp_costura_fim.blockSignals(False)

    def margem(self) -> float:
        return self._para_cena(float(self.sp_costura.value()))

    def margem_final(self) -> float:
        return self._para_cena(float(self.sp_costura_fim.value())) if self.chk_costura_fim.isChecked() else self.margem()

    def usa_largura_final(self) -> bool:
        return bool(self.chk_costura_fim.isChecked())

    def atualizar_status(self, texto: str) -> None:
        self.lbl_status.setText(texto)

    def atualizar_trechos(self, pontos: list[QPointF]) -> None:
        if len(pontos) >= 2:
            if self.usa_largura_final():
                self.atualizar_status(
                    "Preview de costura: início "
                    f"{self._fmt_medida(self.margem())} {self._unidade_sigla} → fim "
                    f"{self._fmt_medida(self.margem_final())} {self._unidade_sigla}."
                )
            else:
                self.atualizar_status(
                    f"Preview de costura com largura de {self._fmt_medida(self.margem())} {self._unidade_sigla}."
                )

    def atualizar_tabela_segmentos(
        self,
        total: int,
        segmentos: set[int],
        ordem: list[int] | None = None,
        largura_inicio: float | None = None,
        largura_fim: float | None = None,
        usar_largura_fim: bool = False,
    ) -> None:
        total = max(0, int(total))
        segmentos = {int(s) % total for s in segmentos} if total else set()
        ordem_normalizada: list[int] = []
        if ordem and total:
            ordem_normalizada = [int(s) % total for s in ordem if int(s) % total in segmentos]
        if not ordem_normalizada:
            ordem_normalizada = sorted(segmentos)

        largura_inicio = self.margem() if largura_inicio is None else float(largura_inicio)
        largura_fim = self.margem_final() if largura_fim is None else float(largura_fim)
        posicoes = {seg_idx: pos for pos, seg_idx in enumerate(ordem_normalizada)}
        qtd = max(1, len(ordem_normalizada))

        self.tabela.setRowCount(total)
        for i in range(total):
            if i in segmentos:
                if usar_largura_fim and i in posicoes:
                    pos = posicoes[i]
                    ini = largura_inicio + ((largura_fim - largura_inicio) * (pos / qtd))
                    fim = largura_inicio + ((largura_fim - largura_inicio) * ((pos + 1) / qtd))
                    largura_txt = f"{self._fmt_medida(ini)}→{self._fmt_medida(fim)}"
                else:
                    largura_txt = self._fmt_medida(largura_inicio)
                acabamento_txt = self.cmb_acab_ini.currentText()
            else:
                largura_txt = "0"
                acabamento_txt = ""
            valores = [
                f"{i + 1}-{(i + 1) % total + 1}",
                largura_txt,
                acabamento_txt,
            ]
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col == 2 and acabamento_txt:
                    item.setIcon(self._icone_acabamento(acabamento_txt))
                    item.setToolTip(acabamento_txt)
                self.tabela.setItem(i, col, item)

    def moveEvent(self, event):
        salvar_posicao(self, self._chave_posicao)
        super().moveEvent(event)

    def hideEvent(self, event):
        salvar_posicao(self, self._chave_posicao)
        super().hideEvent(event)

    def closeEvent(self, event):
        salvar_posicao(self, self._chave_posicao)
        super().closeEvent(event)


class Ferramenta(FerramentaBase):
    id_ferramenta = "costura"
    nome = "Costura"
    usa_painel_auxiliar = False
    descricao_painel = (
        "Clique esquerdo seleciona, clique esquerdo aplica. Direito finaliza/fecha. +/- ajusta a margem."
    )
    _dialog_por_canvas: dict[int, CosturaDialog] = {}

    def __init__(self):
        super().__init__()
        self._margem_cm = 1.0
        self._preview: list[QPointF] = []
        self._preview_idx: int | None = None
        self._hover_segmento: tuple[int, int] | None = None
        self._costura_em_andamento = False
        self._costura_finalizada = False
        self._alvo_idx: int | None = None
        self._segmento_inicio: int | None = None
        self._segmentos_selecionados: set[int] = set()
        self._segmentos_ordem: list[int] = []
        self._realce_segmentos: list[tuple[QPointF, QPointF]] = []
        self._preview_conectores: list[tuple[QPointF, QPointF]] = []
        self._direito_confirma_fechamento = False

    def on_activate(self, canvas):
        dialog = self._obter_dialog(canvas)
        dialog.adjustSize()
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        restaurar_posicao(dialog, "dialog:costura", fallback=fallback)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._direito_confirma_fechamento = False
        dialog.atualizar_status(self._mensagem_pronta(canvas))

    def on_deactivate(self, canvas):
        self._limpar_estado()
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if self._modo(canvas) == "Selecionar":
            self._atualizar_hover_segmento(canvas, pos)
            if self._costura_em_andamento:
                self._atualizar_composicao_por_hover(canvas)
            else:
                self._atualizar_preview_segmento(canvas)
        else:
            idx = self._indice_alvo(canvas, pos)
            self._preview_idx = idx
            self._hover_segmento = None
            self._realce_segmentos = []
            self._preview = []
            if idx is not None:
                elemento = canvas.cena.elementos[idx]
                pontos = self._pontos_fechados(elemento)
                self._preview = [QPointF(x, y) for x, y in self._gerar_costura_atual(canvas, pontos, elemento)]
                self._atualizar_dialog_com_preview(canvas)
                total = self._total_segmentos(canvas, idx)
                self._atualizar_tabela_atual(canvas, total, set(range(total)), list(range(total)))
        canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._costura_em_andamento:
                self._finalizar_costura_segmentos(canvas)
                self._direito_confirma_fechamento = False
                event.accept()
                return True
            if self._costura_finalizada:
                if not self._direito_confirma_fechamento:
                    self._direito_confirma_fechamento = True
                    self.set_status("Operação finalizada. Clique direito novamente fecha a ferramenta.")
                else:
                    self._limpar_estado()
                    canvas.set_ferramenta_ativa("selecionar")
                    self.set_status("Ferramenta Costura finalizada. Voltando para Selecionar.")
                event.accept()
                return True
            self._limpar_estado()
            canvas.set_ferramenta_ativa("selecionar")
            self.set_status("Ferramenta Costura finalizada. Voltando para Selecionar.")
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        if self._modo(canvas) == "Selecionar":
            return self._on_left_selecionar(canvas, event, pos)
        idx = self._indice_alvo(canvas, pos)
        if idx is None:
            self.set_status("Costura: clique em um molde ou contorno fechado.")
            event.accept()
            return True
        selecionados = set(getattr(canvas, "_selecionados", set()) or set())
        if idx not in selecionados or self._costura_finalizada:
            canvas._selecionados = {idx}
            self._preview_idx = idx
            self._costura_finalizada = False
            self._direito_confirma_fechamento = False
            elemento = canvas.cena.elementos[idx]
            pontos = self._pontos_fechados(elemento)
            self._preview = [QPointF(x, y) for x, y in self._gerar_costura_atual(canvas, pontos, elemento)]
            total = self._total_segmentos(canvas, idx)
            self._atualizar_tabela_atual(canvas, total, set(range(total)), list(range(total)))
            self.set_status("Molde selecionado. Clique esquerdo novamente aplica; direito fecha.")
            canvas.update()
            event.accept()
            return True
        if self._aplicar_em_indices(canvas, [idx]):
            canvas._selecionados = {idx}
            self._costura_finalizada = True
            self._direito_confirma_fechamento = False
            self.set_status(
                f"Costura criada com margem de {self._fmt_medida_canvas(canvas, self._margem_cm)}. "
                "Clique esquerdo continua; direito fecha."
            )
        else:
            self.set_status("Nao foi possivel gerar costura para esse contorno.")
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        tecla = event.key()
        if tecla in (Qt.Key_Plus, Qt.Key_Equal):
            self._ajustar_margem(canvas, 0.1)
            return True
        if tecla in (Qt.Key_Minus, Qt.Key_Underscore):
            self._ajustar_margem(canvas, -0.1)
            return True
        if tecla in (Qt.Key_Return, Qt.Key_Enter):
            if self._costura_em_andamento:
                self._finalizar_costura_segmentos(canvas)
                return True
            indices = [idx for idx in sorted(getattr(canvas, "_selecionados", set())) if self._elemento_valido(canvas, idx)]
            if not indices and self._preview_idx is not None:
                indices = [self._preview_idx]
            if self._aplicar_em_indices(canvas, indices):
                self._costura_finalizada = True
                self.set_status(f"Costura aplicada em {len(indices)} molde(s).")
            else:
                self.set_status("Selecione um molde/contorno fechado ou passe o mouse sobre um alvo.")
            return True
        if tecla == Qt.Key_Escape:
            self._limpar_estado()
            canvas.update()
            self.set_status(self._mensagem_pronta(canvas))
            return True
        return False

    def on_paint_overlay(self, canvas, painter):
        if len(self._preview) < 2:
            return
        painter.save()
        modo_offset = self._tipo_operacao(canvas) == "Offset"
        if len(self._preview) >= 2:
            cor_preview = self._cor_preview_alvo(canvas)
            pen = QPen(cor_preview if modo_offset else QColor("#ff2d2d"), 2.0, Qt.SolidLine if modo_offset else Qt.DashLine)
            if not modo_offset:
                pen.setDashPattern([4.0, 3.0])
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath(canvas._cena_para_tela(self._preview[0]))
            for ponto in self._preview[1:]:
                path.lineTo(canvas._cena_para_tela(ponto))
            painter.drawPath(path)
            if not modo_offset:
                pen_conector = QPen(QColor("#ff2d2d"), 1.2, Qt.DotLine)
                painter.setPen(pen_conector)
                for a, b in self._preview_conectores:
                    painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        self._redesenhar_contorno_alvo_overlay(canvas, painter)
        painter.restore()

    def _redesenhar_contorno_alvo_overlay(self, canvas, painter) -> None:
        idx = self._alvo_idx if self._alvo_idx is not None else self._preview_idx
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        elemento = canvas.cena.elementos[idx]
        pontos = [QPointF(x, y) for x, y in self._pontos_fechados(elemento)]
        if len(pontos) < 2:
            return
        cor = QColor(str(elemento.get("cor") or "#ffffff"))
        if not cor.isValid():
            cor = QColor("#ffffff")
        pen = QPen(cor, 1.35, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        path = QPainterPath(canvas._cena_para_tela(pontos[0]))
        for ponto in pontos[1:]:
            path.lineTo(canvas._cena_para_tela(ponto))
        painter.drawPath(path)

    def set_status(self, texto: str):
        for dialog in self._dialog_por_canvas.values():
            if dialog is not None and dialog.isVisible():
                dialog.atualizar_status(texto)

    def _ajustar_margem(self, canvas, delta: float) -> None:
        self._margem_cm = max(0.0, round(self._margem_cm + delta, 2))
        dialog = self._obter_dialog(canvas)
        dialog.set_margem_cena(self._margem_cm)
        self._recalcular_preview(canvas)
        self.set_status(self._mensagem_pronta(canvas))

    def _obter_dialog(self, canvas) -> CosturaDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = CosturaDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        dialog.set_unidade(*unidade_canvas(canvas))
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.sp_costura.valueChanged.connect(lambda valor: self._definir_margem(canvas, float(valor)))
            dialog.sp_costura_fim.valueChanged.connect(lambda _valor: self._recalcular_preview(canvas))
            dialog.chk_costura_fim.toggled.connect(lambda _ativo: self._recalcular_preview(canvas))
            dialog.cmb_posicao.currentTextChanged.connect(lambda _txt: self._recalcular_preview(canvas))
            dialog.cmb_acab_ini.currentIndexChanged.connect(lambda _idx: self._recalcular_preview(canvas))
            dialog.cmb_acab_fim.currentIndexChanged.connect(lambda _idx: self._recalcular_preview(canvas))
            dialog.chk_pique.toggled.connect(lambda _ativo: self._atualizar_dialog_com_preview(canvas))
            dialog.cmb_pique.currentTextChanged.connect(lambda _txt: self._atualizar_dialog_com_preview(canvas))
        return dialog

    def on_unidade_medida_alterada(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.set_unidade(*unidade_canvas(canvas))
            self._atualizar_dialog_com_preview(canvas)
            self._recalcular_preview(canvas)

    def _definir_margem(self, canvas, valor: float) -> None:
        dialog = self._obter_dialog(canvas)
        self._margem_cm = max(0.0, round(float(dialog.margem()), 3))
        if not dialog.chk_costura_fim.isChecked():
            dialog._sincronizar_largura_fim_desabilitada()
        self._recalcular_preview(canvas)
        self.set_status(self._mensagem_pronta(canvas))

    def _recalcular_preview(self, canvas) -> None:
        if self._modo(canvas) == "Selecionar":
            if self._costura_em_andamento:
                self._atualizar_preview_segmentos(canvas)
            else:
                self._atualizar_preview_segmento(canvas)
        elif self._preview_idx is not None and self._elemento_valido(canvas, self._preview_idx):
            elemento = canvas.cena.elementos[self._preview_idx]
            pontos = self._pontos_fechados(elemento)
            self._preview = [QPointF(x, y) for x, y in self._gerar_costura_atual(canvas, pontos, elemento)]
            self._atualizar_dialog_com_preview(canvas)
            total = self._total_segmentos(canvas, self._preview_idx)
            self._atualizar_tabela_atual(canvas, total, set(range(total)), list(range(total)))
        canvas.update()

    def _atualizar_dialog_com_preview(self, canvas) -> None:
        dialog = self._obter_dialog(canvas)
        dialog.atualizar_trechos(self._preview)

    def _aplicar_dialog(self, canvas) -> None:
        indices = [idx for idx in sorted(getattr(canvas, "_selecionados", set())) if self._elemento_valido(canvas, idx)]
        if not indices and self._preview_idx is not None:
            indices = [self._preview_idx]
        if self._costura_em_andamento:
            self._finalizar_costura_segmentos(canvas)
        elif self._aplicar_em_indices(canvas, indices):
            self._costura_finalizada = True
            self.set_status(f"Costura aplicada em {len(indices)} molde(s).")
        else:
            self.set_status("Selecione um molde/contorno fechado ou passe o mouse sobre um alvo.")

    def _on_left_selecionar(self, canvas, event, pos: QPointF) -> bool:
        self._atualizar_hover_segmento(canvas, pos)
        if self._costura_em_andamento:
            self._finalizar_costura_segmentos(canvas)
            event.accept()
            return True
        if self._hover_segmento is None:
            self.set_status("Costura: passe o mouse sobre uma linha do molde e clique para iniciar.")
            event.accept()
            return True
        idx, seg_idx = self._hover_segmento
        self._alvo_idx = idx
        self._segmento_inicio = seg_idx
        self._segmentos_selecionados = {seg_idx}
        self._segmentos_ordem = [seg_idx]
        self._costura_em_andamento = True
        self._costura_finalizada = False
        self._direito_confirma_fechamento = False
        self._atualizar_preview_segmentos(canvas)
        self.set_status("Costura iniciada. Mova o hover no sentido horário do perímetro para acrescentar. Clique esquerdo termina.")
        canvas.update()
        event.accept()
        return True

    def _modo(self, canvas) -> str:
        return self._obter_dialog(canvas).cmb_posicao.currentText()

    def _tipo_operacao(self, canvas) -> str:
        return self._obter_dialog(canvas).cmb_tipo.currentText()

    def _acabamentos_atuais(self, canvas) -> tuple[str, str]:
        dialog = self._obter_dialog(canvas)
        return dialog.acabamento_inicial(), dialog.acabamento_final()

    def _larguras_atuais(self, canvas) -> tuple[float, float, bool]:
        dialog = self._obter_dialog(canvas)
        inicio = max(0.0, float(dialog.sp_costura.value()))
        fim = max(0.0, float(dialog.sp_costura_fim.value())) if dialog.chk_costura_fim.isChecked() else inicio
        usar_fim = bool(dialog.chk_costura_fim.isChecked())
        return inicio, fim, usar_fim

    def _atualizar_tabela_atual(
        self,
        canvas,
        total: int,
        segmentos: set[int],
        ordem: list[int] | None = None,
    ) -> None:
        inicio, fim, usar_fim = self._larguras_atuais(canvas)
        self._obter_dialog(canvas).atualizar_tabela_segmentos(
            total,
            set(segmentos),
            ordem=ordem,
            largura_inicio=inicio,
            largura_fim=fim,
            usar_largura_fim=usar_fim,
        )

    def _gerar_costura_atual(
        self,
        canvas,
        pontos: list[tuple[float, float]],
        elemento: dict | None = None,
    ) -> list[tuple[float, float]]:
        inicio, fim, usar_fim = self._larguras_atuais(canvas)
        if elemento is not None:
            costura_principal = self._gerar_costura_principal_atual(canvas, elemento, inicio, fim, usar_fim)
            if costura_principal:
                return costura_principal
        if not usar_fim:
            return self._gerar_costura(pontos, inicio)
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        total = len(base)
        if total < 3:
            return []
        ordem = self._ordem_segmentos_horaria_visual(base)
        return self._gerar_costura_segmentos_variavel(
            base + [base[0]],
            ordem,
            inicio,
            fim,
            *self._acabamentos_atuais(canvas),
        )

    def _gerar_costura_segmentos_atual(
        self,
        canvas,
        pontos: list[tuple[float, float]],
        segmentos: set[int],
        ordem: list[int] | None = None,
        elemento: dict | None = None,
    ) -> list[tuple[float, float]]:
        inicio, fim, usar_fim = self._larguras_atuais(canvas)
        acabamento_inicial, acabamento_final = self._acabamentos_atuais(canvas)
        if elemento is not None:
            costura_principal = self._gerar_costura_segmentos_principais_atual(
                canvas,
                elemento,
                segmentos,
                ordem,
                inicio,
                fim,
                usar_fim,
            )
            if costura_principal:
                return costura_principal
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        if len(base) < 3 or not segmentos:
            return []
        if ordem is None or not ordem:
            ordem = self._ordenar_segmentos_horario(base, segmentos)
        if not usar_fim and self._ordem_segmentos_contigua(base, ordem, segmentos):
            return self._gerar_costura_segmentos_variavel(
                pontos,
                ordem,
                inicio,
                inicio,
                acabamento_inicial,
                acabamento_final,
            )
        if not usar_fim:
            return self._gerar_costura_segmentos(
                pontos,
                segmentos,
                inicio,
                acabamento_inicial,
                acabamento_final,
            )
        return self._gerar_costura_segmentos_variavel(
            pontos,
            ordem,
            inicio,
            fim,
            acabamento_inicial,
            acabamento_final,
        )

    def _cor_preview_alvo(self, canvas) -> QColor:
        idx = self._alvo_idx if self._alvo_idx is not None else self._preview_idx
        if idx is not None and 0 <= idx < len(canvas.cena.elementos):
            return QColor(str(canvas.cena.elementos[idx].get("cor") or "#ffffff"))
        return QColor("#ffffff")

    def _atualizar_hover_segmento(self, canvas, pos: QPointF) -> None:
        melhor = None
        tolerancia = 9.0 / max(float(getattr(canvas, "zoom", 1.0)), 1e-6)
        for idx, el in enumerate(canvas.cena.elementos):
            trechos = self._segmentos_interativos_elemento(el)
            if not trechos:
                continue
            for seg_idx, trecho in enumerate(trechos):
                realce: list[tuple[QPointF, QPointF]] = []
                melhor_trecho = None
                for a_xy, b_xy in zip(trecho, trecho[1:]):
                    a = QPointF(float(a_xy[0]), float(a_xy[1]))
                    b = QPointF(float(b_xy[0]), float(b_xy[1]))
                    realce.append((a, b))
                    dist = self._distancia_ponto_segmento(a, b, pos)
                    if melhor_trecho is None or dist < melhor_trecho:
                        melhor_trecho = dist
                if melhor_trecho is not None and melhor_trecho <= tolerancia and (
                    melhor is None or melhor_trecho < melhor[0]
                ):
                    melhor = (melhor_trecho, idx, seg_idx, realce)
        if melhor is None:
            self._hover_segmento = None
            self._realce_segmentos = []
            return
        _, idx, seg_idx, realce = melhor
        self._hover_segmento = (idx, seg_idx)
        self._realce_segmentos = realce

    def _atualizar_preview_segmento(self, canvas) -> None:
        self._preview = []
        self._preview_conectores = []
        self._preview_idx = None
        if self._hover_segmento is None:
            return
        idx, seg_idx = self._hover_segmento
        if not self._elemento_valido(canvas, idx):
            return
        self._preview_idx = idx
        elemento = canvas.cena.elementos[idx]
        segmentos_preview = self._segmentos_com_costuras_adjacentes_para_preview(canvas, idx, {seg_idx})
        base_interativa = self._base_interativa_elemento(elemento)
        ordem_preview = self._ordenar_segmentos_contiguos(base_interativa, segmentos_preview) or [seg_idx]
        self._preview = [QPointF(x, y) for x, y in self._gerar_costura_segmentos_atual(
            canvas,
            self._pontos_fechados(elemento),
            segmentos_preview,
            ordem_preview,
            elemento,
        )]
        self._preview_conectores = self._gerar_conectores_preview_segmentos(canvas, idx, {seg_idx})
        self._atualizar_tabela_atual(canvas, self._total_segmentos(canvas, idx), segmentos_preview, ordem_preview)

    def _atualizar_composicao_por_hover(self, canvas) -> None:
        if self._hover_segmento is None or self._alvo_idx is None or self._segmento_inicio is None:
            return
        idx, seg_idx = self._hover_segmento
        if idx != self._alvo_idx:
            return
        if not self._elemento_valido(canvas, idx):
            return
        elemento = canvas.cena.elementos[idx]
        base = self._base_interativa_elemento(elemento)
        if len(base) < 3:
            return
        self._segmentos_ordem = self._segmentos_horarios(base, self._segmento_inicio, seg_idx)
        self._segmentos_selecionados = set(self._segmentos_ordem)
        self._atualizar_preview_segmentos(canvas)

    def _atualizar_preview_segmentos(self, canvas) -> None:
        self._preview = []
        self._preview_conectores = []
        self._realce_segmentos = []
        idx = self._alvo_idx
        if idx is None or not self._elemento_valido(canvas, idx):
            return
        pontos = self._pontos_fechados(canvas.cena.elementos[idx])
        base_interativa = self._base_interativa_elemento(canvas.cena.elementos[idx])
        segmentos_preview = self._segmentos_com_costuras_adjacentes_para_preview(canvas, idx, self._segmentos_selecionados)
        ordem = self._segmentos_ordem or self._ordenar_segmentos_horario(base_interativa, segmentos_preview)
        ordem = self._ordenar_segmentos_contiguos(base_interativa, segmentos_preview) or ordem
        self._segmentos_ordem = ordem
        self._preview = [QPointF(x, y) for x, y in self._gerar_costura_segmentos_atual(
            canvas,
            pontos,
            segmentos_preview,
            ordem,
            canvas.cena.elementos[idx],
        )]
        trechos = self._segmentos_interativos_elemento(canvas.cena.elementos[idx])
        total = len(trechos)
        for seg_idx in sorted(segmentos_preview):
            if 0 <= seg_idx < total:
                for a_xy, b_xy in zip(trechos[seg_idx], trechos[seg_idx][1:]):
                    self._realce_segmentos.append((QPointF(*a_xy), QPointF(*b_xy)))
        self._preview_conectores = self._gerar_conectores_preview_segmentos(canvas, idx, self._segmentos_selecionados)
        self._atualizar_tabela_atual(canvas, total, set(segmentos_preview), self._segmentos_ordem)

    def _finalizar_costura_segmentos(self, canvas) -> bool:
        if self._alvo_idx is None or not self._segmentos_selecionados:
            self.set_status("Nenhuma linha selecionada para costura.")
            return False
        if self._aplicar_segmentos(canvas, self._alvo_idx, self._segmentos_selecionados, self._segmentos_ordem):
            self._costura_em_andamento = False
            self._costura_finalizada = True
            self._direito_confirma_fechamento = False
            self._segmento_inicio = None
            self._segmentos_selecionados = set()
            self._segmentos_ordem = []
            self._limpar_preview_visual()
            self.set_status("Costura finalizada. Clique esquerdo em outra linha para continuar ou clique direito para fechar.")
            canvas.update()
            return True
        self.set_status("Nao foi possivel aplicar costura nesses segmentos.")
        return False

    def _aplicar_segmentos(
        self,
        canvas,
        idx: int,
        segmentos: set[int],
        ordem: list[int] | None = None,
    ) -> bool:
        if not self._elemento_valido(canvas, idx):
            return False
        if self._tipo_operacao(canvas) == "Offset":
            return self._aplicar_offset_segmentos(canvas, idx, segmentos)
        alvo = canvas.cena.elementos[idx]
        molde_id = str(alvo.get("molde_id") or alvo.get("id") or "")
        if not molde_id:
            molde_id = str(uuid4())
            alvo["molde_id"] = molde_id

        total_segmentos = self._total_segmentos(canvas, idx)
        segmentos_novos = {int(s) % total_segmentos for s in segmentos} if total_segmentos else set()
        segmentos_aplicar = set(segmentos_novos)
        if total_segmentos and 0 < len(segmentos_novos) < total_segmentos:
            segmentos_aplicar = self._segmentos_mesclados_com_costuras_adjacentes(
                canvas,
                molde_id,
                segmentos_novos,
                total_segmentos,
            )

        base_interativa = self._base_interativa_elemento(alvo)
        ordem_aplicar = self._ordenar_segmentos_contiguos(base_interativa, segmentos_aplicar) or (
            [int(s) for s in (ordem or sorted(segmentos_aplicar))]
        )
        pontos = self._pontos_fechados(alvo)
        costura = self._gerar_costura_segmentos_atual(canvas, pontos, segmentos_aplicar, ordem_aplicar, alvo)
        if len(costura) < 2:
            return False
        el = self._elemento_costura(canvas, costura, alvo, molde_id)
        el["costura_segmentos"] = [int(s) for s in ordem_aplicar]
        el["costura_parcial"] = len(segmentos_aplicar) < total_segmentos
        if el["costura_parcial"]:
            self._remover_costuras_segmentos_do_alvo(canvas, molde_id, segmentos_aplicar, total_segmentos)
        else:
            self._remover_costuras_do_alvo(canvas, molde_id)
        canvas.cena.elementos.append(el)
        self.sincronizar_costuras_graduacao_do_molde(canvas, molde_id)
        self._limpar_preview_visual()
        canvas._registrar_historico()
        canvas.update()
        return True

    def _aplicar_em_indices(self, canvas, indices: list[int]) -> bool:
        if self._tipo_operacao(canvas) == "Offset":
            alterou_offset = False
            for idx in indices:
                if self._aplicar_offset_total(canvas, idx):
                    alterou_offset = True
            if alterou_offset:
                canvas._registrar_historico()
                canvas.update()
            return alterou_offset
        alterou = False
        alvos = []
        for idx in indices:
            if not self._elemento_valido(canvas, idx):
                continue
            alvos.append(canvas.cena.elementos[idx])
        for alvo in alvos:
            pontos = self._pontos_fechados(alvo)
            costura = self._gerar_costura_atual(canvas, pontos, alvo)
            if len(costura) < 4:
                continue
            molde_id = str(alvo.get("molde_id") or alvo.get("id") or "")
            if not molde_id:
                molde_id = str(uuid4())
                alvo["molde_id"] = molde_id
            self._remover_costuras_do_alvo(canvas, molde_id)
            total_segmentos = self._total_segmentos_elemento(alvo)
            ordem = self._ordenar_segmentos_horario(self._base_interativa_elemento(alvo), set(range(total_segmentos)))
            el_costura = self._elemento_costura(canvas, costura, alvo, molde_id)
            el_costura["costura_segmentos"] = [int(s) for s in ordem]
            el_costura["costura_parcial"] = False
            canvas.cena.elementos.append(el_costura)
            self.sincronizar_costuras_graduacao_do_molde(canvas, molde_id)
            alterou = True
        if alterou:
            self._limpar_preview_visual()
            canvas._registrar_historico()
            canvas.update()
        return alterou

    def _aplicar_offset_total(self, canvas, idx: int) -> bool:
        if not self._elemento_valido(canvas, idx):
            return False
        alvo = canvas.cena.elementos[idx]
        pontos = self._pontos_fechados(alvo)
        novos = self._gerar_costura(pontos, self._margem_cm)
        if len(novos) < 4:
            return False
        self._atualizar_geometria_molde(alvo, novos)
        self._remover_costuras_do_alvo(canvas, str(alvo.get("molde_id") or alvo.get("id") or ""))
        return True

    def _aplicar_offset_segmentos(self, canvas, idx: int, segmentos: set[int]) -> bool:
        if not self._elemento_valido(canvas, idx):
            return False
        alvo = canvas.cena.elementos[idx]
        pontos = self._pontos_fechados(alvo)
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        total = len(base)
        if total < 3 or not segmentos:
            return False
        segmentos = {s % total for s in segmentos}
        if len(segmentos) >= total:
            return self._aplicar_offset_total(canvas, idx)
        costura_total = self._gerar_costura(base + [base[0]], self._margem_cm)
        if len(costura_total) < total + 1:
            return False
        grupos = self._agrupar_segmentos(segmentos, total)
        if len(grupos) != 1:
            return False
        grupo = grupos[0]
        inicio = grupo[0]
        fim = (grupo[-1] + 1) % total
        acabamento_ini, acabamento_fim = self._acabamentos_atuais(canvas)
        cap_ini = self._pontos_acabamento_extremidade(base, costura_total, inicio, grupo[0], self._margem_cm, acabamento_ini, inicio=True)
        cap_fim = self._pontos_acabamento_extremidade(base, costura_total, fim, grupo[-1], self._margem_cm, acabamento_fim, inicio=False)
        trecho_offset: list[tuple[float, float]] = []
        for pos, seg_idx in enumerate(grupo):
            if pos == 0:
                trecho_offset.append(costura_total[seg_idx])
            trecho_offset.append(costura_total[(seg_idx + 1) % total])
        faixa = self._deduplicar_pontos(cap_ini + trecho_offset + cap_fim)
        if inicio <= fim:
            novos = list(base[:inicio]) + faixa + list(base[fim + 1:])
        else:
            novos = faixa + list(base[fim + 1:inicio])
        if novos and self._dist(novos[0], novos[-1]) > 1e-6:
            novos.append(novos[0])
        self._atualizar_geometria_molde(alvo, novos)
        self._remover_costuras_do_alvo(canvas, str(alvo.get("molde_id") or alvo.get("id") or ""))
        canvas._registrar_historico()
        canvas.update()
        return True

    def _atualizar_geometria_molde(self, alvo: dict, pontos: list[tuple[float, float]]) -> None:
        pontos_fechados = list(pontos)
        if pontos_fechados and self._dist(pontos_fechados[0], pontos_fechados[-1]) > 1e-6:
            pontos_fechados.append(pontos_fechados[0])
        alvo["pontos"] = [(float(x), float(y)) for x, y in pontos_fechados]
        cantos = [(float(x), float(y)) for x, y in pontos_fechados[:-1]]
        if "controle_cantos" in alvo:
            alvo["controle_cantos"] = cantos
        if "controle_auxiliares" in alvo:
            alvo["controle_auxiliares"] = []
        if "pontos_controle_principais" in alvo:
            alvo["pontos_controle_principais"] = [{"x": x, "y": y} for x, y in cantos]
        if "pontos_auxiliares" in alvo:
            alvo["pontos_auxiliares"] = []
        alvo.setdefault("metadados", {})["offset_costura_cm"] = float(self._margem_cm)

    def _elemento_costura(self, canvas, pontos: list[tuple[float, float]], alvo: dict, molde_id: str) -> dict:
        dialog = self._dialog_por_canvas.get(id(canvas))
        tipo_costura = "Costura"
        posicao = "Selecionar"
        pique = ""
        acabamento_inicial = ""
        acabamento_final = ""
        largura_inicio = float(self._margem_cm)
        largura_fim = float(self._margem_cm)
        usar_largura_fim = False
        if dialog is not None:
            tipo_costura = dialog.cmb_tipo.currentText()
            posicao = dialog.cmb_posicao.currentText()
            pique = dialog.cmb_pique.currentText() if dialog.chk_pique.isChecked() else ""
            acabamento_inicial = dialog.acabamento_inicial()
            acabamento_final = dialog.acabamento_final()
            largura_inicio = float(dialog.margem())
            largura_fim = float(dialog.margem_final()) if dialog.chk_costura_fim.isChecked() else largura_inicio
            usar_largura_fim = bool(dialog.chk_costura_fim.isChecked())
        return {
            "tipo": "polyline",
            "pontos": pontos,
            "cor": str(alvo.get("cor") or "#ff5a00"),
            "espessura": 0.9,
            "estilo": "dash",
            "subtipo_audaces": "costura",
            "parte_do_molde": True,
            "molde_linha_vinculada": True,
            "selecionavel_individual": False,
            "molde_id": molde_id,
            "costura_de_molde_id": molde_id,
            "margem_costura_cm": float(largura_inicio),
            "margem_costura_fim_cm": float(largura_fim),
            "costura_fim_ativa": bool(usar_largura_fim),
            "tipo_costura": tipo_costura,
            "posicao_costura": posicao,
            "pique_costura": pique,
            "acabamento_inicial": acabamento_inicial,
            "acabamento_final": acabamento_final,
            "metadados": {
                "tipo_ferramenta": self.id_ferramenta,
                "subtipo_audaces": "costura",
                "origem_nome_molde": str(alvo.get("nome_molde") or ""),
                "tipo_costura": tipo_costura,
                "posicao_costura": posicao,
                "pique_costura": pique,
                "acabamento_inicial": acabamento_inicial,
                "acabamento_final": acabamento_final,
                "margem_costura_cm": float(largura_inicio),
                "margem_costura_fim_cm": float(largura_fim),
                "costura_fim_ativa": bool(usar_largura_fim),
            },
        }

    def _elementos_costura_graduacao(
        self,
        canvas,
        alvo: dict,
        molde_id: str,
        segmentos: set[int],
        ordem: list[int],
        total_segmentos: int,
    ) -> list[dict]:
        if total_segmentos <= 0 or not segmentos:
            return []
        contornos = self._contornos_graduacao_alvo(alvo)
        if not contornos:
            return []

        principal = self._contorno_principal_elemento(alvo)
        indices_principais: list[int] = principal[1] if principal is not None else []
        saida: list[dict] = []
        for nome, cor, pontos_qt in contornos:
            pontos = [(float(pt.x()), float(pt.y())) for pt in pontos_qt]
            if len(pontos) < 4:
                continue
            elemento_graduado = self._elemento_temporario_graduado(alvo, pontos, indices_principais)
            if self._total_segmentos_elemento(elemento_graduado) != total_segmentos:
                continue
            costura = self._gerar_costura_segmentos_atual(
                canvas,
                self._pontos_fechados(elemento_graduado),
                segmentos,
                ordem,
                elemento_graduado,
            )
            if len(costura) < 2:
                continue
            el = self._elemento_costura(canvas, costura, alvo, molde_id)
            el["cor"] = str(cor or el.get("cor") or "#ff5a00")
            el["graduacao_tamanho"] = str(nome or "")
            el["costura_graduacao"] = True
            el["costura_segmentos"] = [int(s) for s in ordem]
            el["costura_parcial"] = len(set(segmentos)) < total_segmentos
            el.setdefault("metadados", {}).update(
                {
                    "graduacao_tamanho": str(nome or ""),
                    "costura_graduacao": True,
                }
            )
            saida.append(el)
        return saida

    def _contornos_graduacao_alvo(self, alvo: dict) -> list[tuple[str, str, list[QPointF]]]:
        try:
            from canvas.visualizacao import VisualizacaoCanvas
        except Exception:
            return []
        base = VisualizacaoCanvas._base_graduacao_elemento(alvo)
        if len(base) < 2:
            return []
        try:
            return VisualizacaoCanvas._contornos_graduacao_tabela(alvo, base)
        except Exception:
            return []

    def _elemento_temporario_graduado(
        self,
        alvo: dict,
        pontos: list[tuple[float, float]],
        indices_principais: list[int],
    ) -> dict:
        elemento = dict(alvo)
        elemento["pontos"] = list(pontos)
        aberto = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        if indices_principais:
            controles: list[tuple[float, float]] = []
            for idx in indices_principais:
                if 0 <= int(idx) < len(aberto):
                    controles.append((float(aberto[int(idx)][0]), float(aberto[int(idx)][1])))
            if len(controles) >= 3:
                elemento["controle_cantos"] = controles
                elemento["pontos_controle_principais"] = [{"x": x, "y": y} for x, y in controles]
            else:
                self._limpar_controles_principais(elemento)
        else:
            self._limpar_controles_principais(elemento)
        return elemento

    @staticmethod
    def _limpar_controles_principais(elemento: dict) -> None:
        for chave in ("controle_cantos", "pontos_controle_principais", "pontos_controle", "controle_pontos"):
            elemento.pop(chave, None)

    def sincronizar_costuras_vinculadas(self, canvas) -> bool:
        if canvas is None or not hasattr(canvas, "cena"):
            return False
        elementos = list(getattr(canvas.cena, "elementos", []) or [])
        moldes: dict[str, dict] = {}
        for el in elementos:
            if isinstance(el, dict) and el.get("molde"):
                molde_id = str(el.get("molde_id") or el.get("id") or "").strip()
                if molde_id:
                    moldes[molde_id] = el
        if not moldes:
            return False

        alterou = False
        for el in elementos:
            if not self._costura_sincronizavel(el):
                continue
            molde_id = self._molde_id_costura(el)
            alvo = moldes.get(molde_id)
            if not isinstance(alvo, dict):
                continue
            novos = self._gerar_pontos_costura_sincronizada(canvas, alvo, el)
            if len(novos) < 2:
                continue
            pontos_atuais = self._lista_pontos_tupla(el.get("pontos", []) or [])
            if pontos_atuais != novos:
                el["pontos"] = novos
                alterou = True
        return alterou

    def sincronizar_costuras_graduacao_do_molde(self, canvas, molde_id: str) -> bool:
        alvo_id = str(molde_id or "").strip()
        if canvas is None or not hasattr(canvas, "cena") or not alvo_id:
            return False

        molde = None
        for el in list(getattr(canvas.cena, "elementos", []) or []):
            if isinstance(el, dict) and el.get("molde"):
                atual = str(el.get("molde_id") or el.get("id") or "").strip()
                if atual == alvo_id:
                    molde = el
                    break
        if not isinstance(molde, dict):
            return False

        total = self._total_segmentos_elemento(molde)
        if total <= 0:
            return False

        elementos_sem_graduacao: list[dict] = []
        costuras_base: list[dict] = []
        alterou = False
        for el in list(canvas.cena.elementos):
            if self._eh_costura_do_alvo(el, alvo_id) and self._eh_costura_graduacao(el):
                alterou = True
                continue
            elementos_sem_graduacao.append(el)
            if self._eh_costura_do_alvo(el, alvo_id):
                costuras_base.append(el)

        novas_graduadas: list[dict] = []
        for base in costuras_base:
            segmentos = set(self._segmentos_salvos_costura(base, total))
            parcial = bool(base.get("costura_parcial")) and bool(segmentos)
            if not parcial:
                segmentos = set(range(total))
            if not segmentos:
                continue
            ordem = [
                int(s) % total
                for s in (base.get("costura_segmentos") or [])
                if isinstance(s, (int, float)) and int(s) % total in segmentos
            ]
            base_interativa = self._base_interativa_elemento(molde)
            if not ordem:
                ordem = self._ordenar_segmentos_contiguos(base_interativa, segmentos) or self._ordenar_segmentos_horario(
                    base_interativa,
                    segmentos,
                )
            novas_graduadas.extend(
                self._elementos_costura_graduacao_de_base(canvas, molde, base, alvo_id, segmentos, ordem, total)
            )

        if alterou or novas_graduadas:
            canvas.cena.elementos = elementos_sem_graduacao + novas_graduadas
            return True
        return False

    def _elementos_costura_graduacao_de_base(
        self,
        canvas,
        molde: dict,
        costura_base: dict,
        molde_id: str,
        segmentos: set[int],
        ordem: list[int],
        total_segmentos: int,
    ) -> list[dict]:
        contornos = self._contornos_graduacao_alvo(molde)
        if not contornos:
            return []

        saida: list[dict] = []
        ordem_norm = [int(s) % total_segmentos for s in ordem if int(s) % total_segmentos in segmentos]
        parcial = len(set(segmentos)) < total_segmentos
        for nome, cor, _pontos_qt in contornos:
            temporaria = deepcopy(costura_base)
            temporaria["graduacao_tamanho"] = str(nome or "")
            temporaria["costura_graduacao"] = True
            temporaria["costura_segmentos"] = list(ordem_norm)
            temporaria["costura_parcial"] = bool(parcial)
            metadados = dict(temporaria.get("metadados") or {})
            metadados.update(
                {
                    "graduacao_tamanho": str(nome or ""),
                    "costura_graduacao": True,
                    "costura_segmentos": list(ordem_norm),
                    "costura_parcial": bool(parcial),
                }
            )
            temporaria["metadados"] = metadados

            pontos = self._gerar_pontos_costura_sincronizada(canvas, molde, temporaria)
            if len(pontos) < 2:
                continue
            el = deepcopy(temporaria)
            el["pontos"] = pontos
            el["cor"] = str(cor or el.get("cor") or "#ff5a00")
            el["tipo"] = "polyline"
            el["subtipo_audaces"] = "costura"
            el["parte_do_molde"] = True
            el["molde_linha_vinculada"] = True
            el["selecionavel_individual"] = False
            el["molde_id"] = molde_id
            el["costura_de_molde_id"] = molde_id
            saida.append(el)
        return saida

    def _gerar_pontos_costura_sincronizada(self, canvas, molde: dict, costura: dict) -> list[tuple[float, float]]:
        alvo = self._alvo_geometrico_costura_sincronizada(molde, costura)
        if not isinstance(alvo, dict):
            return []
        total = self._total_segmentos_elemento(alvo)
        if total <= 0:
            return []

        margem_inicio, margem_fim, usar_largura_fim = self._config_larguras_costura(costura)
        acabamento_inicial, acabamento_final = self._config_acabamentos_costura(costura)
        segmentos_salvos = self._segmentos_salvos_costura(costura, total)
        parcial = bool(costura.get("costura_parcial")) and bool(segmentos_salvos)
        if segmentos_salvos and len(segmentos_salvos) < total:
            parcial = True
        segmentos = set(segmentos_salvos) if parcial else set(range(total))

        ordem = [int(s) % total for s in (costura.get("costura_segmentos") or []) if isinstance(s, (int, float))]
        ordem = [s for s in ordem if s in segmentos]
        base_interativa = self._base_interativa_elemento(alvo)
        if not ordem:
            ordem = self._ordenar_segmentos_contiguos(base_interativa, segmentos) or self._ordenar_segmentos_horario(
                base_interativa,
                segmentos,
            )
        elif parcial:
            ordem = self._ordenar_segmentos_contiguos(base_interativa, segmentos) or ordem
        pontos = self._pontos_fechados(alvo)

        assinatura_cache = self._assinatura_costura_sincronizada(
            alvo,
            costura,
            total,
            segmentos,
            ordem,
            margem_inicio,
            margem_fim,
            usar_largura_fim,
            acabamento_inicial,
            acabamento_final,
        )
        cache = costura.get("_runtime_costura_sincronizada_cache") if isinstance(costura, dict) else None
        if isinstance(cache, dict) and cache.get("assinatura") == assinatura_cache:
            pontos_cache = cache.get("pontos")
            if isinstance(pontos_cache, tuple):
                return [tuple(ponto) for ponto in pontos_cache]

        original_larguras = self._larguras_atuais
        original_acabamentos = self._acabamentos_atuais
        self._larguras_atuais = lambda _canvas: (margem_inicio, margem_fim, usar_largura_fim)  # type: ignore[method-assign]
        self._acabamentos_atuais = lambda _canvas: (acabamento_inicial, acabamento_final)  # type: ignore[method-assign]
        try:
            if parcial:
                gerados = self._gerar_costura_segmentos_atual(canvas, pontos, segmentos, ordem, alvo)
            else:
                gerados = self._gerar_costura_atual(canvas, pontos, alvo)
        finally:
            self._larguras_atuais = original_larguras  # type: ignore[method-assign]
            self._acabamentos_atuais = original_acabamentos  # type: ignore[method-assign]
        costura["_runtime_costura_sincronizada_cache"] = {
            "assinatura": assinatura_cache,
            "pontos": tuple((float(x), float(y)) for x, y in gerados),
        }
        return gerados

    def _assinatura_costura_sincronizada(
        self,
        alvo: dict,
        costura: dict,
        total: int,
        segmentos: set[int],
        ordem: list[int],
        margem_inicio: float,
        margem_fim: float,
        usar_largura_fim: bool,
        acabamento_inicial: str,
        acabamento_final: str,
    ) -> tuple:
        metadados = costura.get("metadados") if isinstance(costura.get("metadados"), dict) else {}
        return (
            self._assinatura_geometria_costura(alvo),
            int(total),
            tuple(sorted(int(s) for s in segmentos)),
            tuple(int(s) for s in ordem),
            round(float(margem_inicio), 6),
            round(float(margem_fim), 6),
            bool(usar_largura_fim),
            str(acabamento_inicial),
            str(acabamento_final),
            bool(costura.get("costura_parcial")),
            str(costura.get("graduacao_tamanho") or metadados.get("graduacao_tamanho") or ""),
        )

    def _assinatura_geometria_costura(self, elemento: dict) -> tuple:
        return (
            tuple(self._lista_pontos_tupla(elemento.get("pontos", []) or [])),
            tuple(self._lista_pontos_tupla(elemento.get("controle_cantos", []) or [])),
            tuple(self._lista_pontos_tupla(elemento.get("pontos_controle_principais", []) or [])),
            tuple(self._lista_pontos_tupla(elemento.get("pontos_principais", []) or [])),
        )

    def _alvo_geometrico_costura_sincronizada(self, molde: dict, costura: dict) -> dict | None:
        metadados = costura.get("metadados") if isinstance(costura.get("metadados"), dict) else {}
        tamanho = str(costura.get("graduacao_tamanho") or metadados.get("graduacao_tamanho") or "").strip()
        if not tamanho:
            return molde
        principal = self._contorno_principal_elemento(molde)
        indices_principais: list[int] = principal[1] if principal is not None else []
        for nome, _cor, pontos_qt in self._contornos_graduacao_alvo(molde):
            if str(nome or "").strip() != tamanho:
                continue
            pontos = [(float(pt.x()), float(pt.y())) for pt in pontos_qt]
            if len(pontos) < 3:
                return None
            return self._elemento_temporario_graduado(molde, pontos, indices_principais)
        return None

    def _segmentos_salvos_costura(self, costura: dict, total: int) -> list[int]:
        segmentos = costura.get("costura_segmentos")
        if not isinstance(segmentos, list) or total <= 0:
            return []
        saida: list[int] = []
        for item in segmentos:
            try:
                seg = int(item) % total
            except Exception:
                continue
            if seg not in saida:
                saida.append(seg)
        return saida

    def _config_larguras_costura(self, costura: dict) -> tuple[float, float, bool]:
        metadados = costura.get("metadados") if isinstance(costura.get("metadados"), dict) else {}
        inicio = self._float_config_costura(costura.get("margem_costura_cm", metadados.get("margem_costura_cm")), 1.0)
        fim = self._float_config_costura(
            costura.get("margem_costura_fim_cm", metadados.get("margem_costura_fim_cm")),
            inicio,
        )
        usar_fim = bool(costura.get("costura_fim_ativa") or metadados.get("costura_fim_ativa"))
        return max(0.0, inicio), max(0.0, fim), usar_fim

    def _config_acabamentos_costura(self, costura: dict) -> tuple[str, str]:
        metadados = costura.get("metadados") if isinstance(costura.get("metadados"), dict) else {}
        inicial = str(costura.get("acabamento_inicial") or metadados.get("acabamento_inicial") or "Canto reto")
        final = str(costura.get("acabamento_final") or metadados.get("acabamento_final") or "Canto reto")
        return inicial, final

    @staticmethod
    def _float_config_costura(valor, padrao: float) -> float:
        try:
            return float(valor)
        except Exception:
            return float(padrao)

    def _costura_sincronizavel(self, el: dict) -> bool:
        if not isinstance(el, dict) or el.get("molde"):
            return False
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        subtipo = str(el.get("subtipo_audaces") or metadados.get("subtipo_audaces") or "").strip()
        if subtipo != "costura" and not el.get("costura_de_molde_id") and not metadados.get("costura_de_molde_id"):
            return False
        if str(el.get("tipo_ferramenta") or metadados.get("tipo_ferramenta") or "") == self.id_ferramenta:
            return True
        return el.get("costura_segmentos") is not None or metadados.get("costura_segmentos") is not None

    @staticmethod
    def _molde_id_costura(costura: dict) -> str:
        metadados = costura.get("metadados") if isinstance(costura.get("metadados"), dict) else {}
        return str(
            costura.get("costura_de_molde_id")
            or metadados.get("costura_de_molde_id")
            or costura.get("molde_id")
            or metadados.get("molde_id")
            or ""
        ).strip()

    def _eh_costura_do_alvo(self, el: dict, molde_id: str) -> bool:
        alvo_id = str(molde_id or "").strip()
        if not alvo_id or not isinstance(el, dict) or el.get("molde"):
            return False
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        subtipo = str(el.get("subtipo_audaces") or metadados.get("subtipo_audaces") or "").strip()
        costura_id = str(el.get("costura_de_molde_id") or metadados.get("costura_de_molde_id") or "").strip()
        if subtipo == "contorno" or (subtipo != "costura" and not costura_id):
            return False
        if not self._costura_substituivel(el):
            return False
        return (
            costura_id == alvo_id
            or str(el.get("molde_id") or "").strip() == alvo_id
            or str(metadados.get("molde_id") or "").strip() == alvo_id
        )

    def _costura_substituivel(self, el: dict) -> bool:
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        if str(el.get("tipo_ferramenta") or metadados.get("tipo_ferramenta") or "") == self.id_ferramenta:
            return True
        if el.get("costura_segmentos") is not None or metadados.get("costura_segmentos") is not None:
            return True
        if self._elemento_importado_audaces(el):
            return False
        return bool(el.get("costura_de_molde_id") or metadados.get("costura_de_molde_id"))

    @staticmethod
    def _eh_costura_graduacao(el: dict) -> bool:
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        return bool(
            el.get("costura_graduacao")
            or metadados.get("costura_graduacao")
            or el.get("graduacao_tamanho")
            or metadados.get("graduacao_tamanho")
        )

    @staticmethod
    def _elemento_importado_audaces(el: dict) -> bool:
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        if bool(metadados.get("importado_como_molde_real")):
            return True
        origens = (el.get("origem"), metadados.get("origem"))
        return any("audaces" in str(origem or "").lower() for origem in origens)

    def _remover_costuras_do_alvo(self, canvas, molde_id: str) -> None:
        alvo_id = str(molde_id or "").strip()
        if not alvo_id:
            return
        canvas.cena.elementos = [el for el in canvas.cena.elementos if not self._eh_costura_do_alvo(el, alvo_id)]

    def _segmentos_costura_existente(self, el: dict, total: int) -> set[int] | None:
        if total <= 0:
            return None
        origem = el.get("costura_segmentos")
        if origem is None:
            origem = el.get("metadados", {}).get("costura_segmentos")
        if not isinstance(origem, list):
            return None
        segmentos: set[int] = set()
        for item in origem:
            try:
                segmentos.add(int(item) % total)
            except Exception:
                continue
        return segmentos if segmentos else None

    def _segmentos_encostam(self, a: set[int], b: set[int], total: int) -> bool:
        if total <= 0 or not a or not b:
            return False
        a_norm = {int(s) % total for s in a}
        b_norm = {int(s) % total for s in b}
        if a_norm & b_norm:
            return True
        for seg_idx in a_norm:
            if ((seg_idx - 1) % total) in b_norm or ((seg_idx + 1) % total) in b_norm:
                return True
        return False

    def _segmentos_mesclados_com_costuras_adjacentes(
        self,
        canvas,
        molde_id: str,
        segmentos: set[int],
        total: int,
    ) -> set[int]:
        alvo_id = str(molde_id or "").strip()
        if not alvo_id or total <= 0 or not segmentos:
            return set()
        mesclados = {int(s) % total for s in segmentos}
        mudou = True
        while mudou:
            mudou = False
            for el in list(getattr(canvas.cena, "elementos", []) or []):
                if not self._eh_costura_do_alvo(el, alvo_id):
                    continue
                if not bool(el.get("costura_parcial", False)):
                    continue
                existentes = self._segmentos_costura_existente(el, total)
                if not existentes:
                    continue
                if self._segmentos_encostam(mesclados, existentes, total):
                    antes = set(mesclados)
                    mesclados.update(existentes)
                    if mesclados != antes:
                        mudou = True
        return mesclados

    def _segmentos_com_costuras_adjacentes_para_preview(
        self,
        canvas,
        idx: int,
        segmentos: set[int],
    ) -> set[int]:
        if not self._elemento_valido(canvas, idx):
            return {int(s) for s in segmentos}
        total = self._total_segmentos(canvas, idx)
        if total <= 0:
            return {int(s) for s in segmentos}
        segmentos_norm = {int(s) % total for s in segmentos}
        if not segmentos_norm or len(segmentos_norm) >= total:
            return segmentos_norm
        alvo = canvas.cena.elementos[idx]
        molde_id = str(alvo.get("molde_id") or alvo.get("id") or "").strip()
        if not molde_id:
            return segmentos_norm
        return self._segmentos_mesclados_com_costuras_adjacentes(canvas, molde_id, segmentos_norm, total)

    def _remover_costuras_segmentos_do_alvo(
        self,
        canvas,
        molde_id: str,
        segmentos: set[int],
        total: int,
    ) -> None:
        alvo_id = str(molde_id or "").strip()
        if not alvo_id or total <= 0 or not segmentos:
            return
        segmentos_novos = {int(s) % total for s in segmentos}
        elementos = []
        for el in canvas.cena.elementos:
            if not self._eh_costura_do_alvo(el, alvo_id):
                elementos.append(el)
                continue
            if not bool(el.get("costura_parcial", False)):
                continue
            segmentos_existentes = self._segmentos_costura_existente(el, total)
            if segmentos_existentes is None or segmentos_existentes & segmentos_novos:
                continue
            elementos.append(el)
        canvas.cena.elementos = elementos

    def _indice_alvo(self, canvas, pos: QPointF) -> int | None:
        for idx in canvas._indices_elementos_em_ponto(pos):
            if self._elemento_valido(canvas, idx):
                return idx
        return None

    def _elemento_valido(self, canvas, idx: int) -> bool:
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return False
        return len(self._pontos_fechados(canvas.cena.elementos[idx])) >= 4

    def _pontos_fechados(self, elemento: dict) -> list[tuple[float, float]]:
        if elemento.get("tipo") != "polyline":
            return []
        subtipo = str(elemento.get("subtipo_audaces") or elemento.get("metadados", {}).get("subtipo_audaces") or "")
        if subtipo == "costura" or elemento.get("costura_de_molde_id"):
            return []

        pontos = self._pontos_base_para_costura(elemento)
        if len(pontos) < 3:
            return []
        if self._dist(pontos[0], pontos[-1]) > 1e-6:
            if not elemento.get("molde"):
                return []
            pontos.append(pontos[0])
        return pontos if len(pontos) >= 4 else []

    def _pontos_base_para_costura(self, elemento: dict) -> list[tuple[float, float]]:
        """Retorna os pontos usados pela costura na mesma ordem visual dos números do molde.

        O canvas desenha os números do molde a partir de ``controle_cantos`` quando
        esse campo existe. Se a ferramenta usa ``pontos`` em outra ordem, o usuário
        clica numa borda vendo um número, mas a tabela/fluxo seleciona outra borda.
        Para contornos simples, onde ``controle_cantos`` representa os mesmos cantos
        do contorno, a costura deve seguir essa ordem numerada. Para moldes com
        muitos pontos/curvas, mantemos ``pontos`` para não perder a geometria fina.
        """
        pontos: list[tuple[float, float]] = []
        for item in elemento.get("pontos", []) or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    pontos.append((float(item[0]), float(item[1])))
                except Exception:
                    continue
        if len(pontos) >= 2 and self._dist(pontos[0], pontos[-1]) <= 1e-6:
            pontos_abertos = pontos[:-1]
        else:
            pontos_abertos = list(pontos)

        controles: list[tuple[float, float]] = []
        for item in elemento.get("controle_cantos", []) or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    controles.append((float(item[0]), float(item[1])))
                except Exception:
                    continue

        if len(controles) >= 3 and (not pontos_abertos or len(controles) == len(pontos_abertos)):
            return list(controles)
        return pontos_abertos

    def _ponto_tupla(self, item) -> tuple[float, float] | None:
        try:
            if isinstance(item, dict):
                return float(item.get("x", 0.0)), float(item.get("y", 0.0))
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                return float(item[0]), float(item[1])
        except Exception:
            return None
        return None

    def _lista_pontos_tupla(self, origem) -> list[tuple[float, float]]:
        if not isinstance(origem, list):
            return []
        pontos: list[tuple[float, float]] = []
        for item in origem:
            ponto = self._ponto_tupla(item)
            if ponto is not None:
                pontos.append(ponto)
        return pontos

    def _pontos_polyline_abertos(self, elemento: dict) -> list[tuple[float, float]]:
        pontos = self._lista_pontos_tupla(elemento.get("pontos", []) or [])
        if len(pontos) >= 2 and self._dist(pontos[0], pontos[-1]) <= 1e-6:
            pontos = pontos[:-1]
        return pontos

    def _controles_principais_elemento(self, elemento: dict) -> list[tuple[float, float]]:
        nao_dividem_costura = self._controles_que_nao_dividem_costura(elemento)
        for chave in ("controle_cantos", "pontos_controle_principais", "pontos_principais", "pontos_controle"):
            controles = self._lista_pontos_tupla(elemento.get(chave, []) or [])
            if len(controles) >= 3:
                saida: list[tuple[float, float]] = []
                for ponto in controles:
                    if not saida or self._dist(saida[-1], ponto) > 1e-6:
                        saida.append(ponto)
                if len(saida) >= 2 and self._dist(saida[0], saida[-1]) <= 1e-6:
                    saida = saida[:-1]
                filtrada = [
                    ponto for ponto in saida
                    if not any(self._dist(ponto, ignorar) <= 1e-6 for ignorar in nao_dividem_costura)
                ]
                if len(filtrada) >= 3:
                    saida = filtrada
                if len(saida) >= 3:
                    return saida
        return []

    def _controles_que_nao_dividem_costura(self, elemento: dict) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []

        def adicionar(ponto: tuple[float, float] | None) -> None:
            if ponto is None:
                return
            if not any(self._dist(ponto, existente) <= 1e-6 for existente in saida):
                saida.append(ponto)

        for item in elemento.get("pontos_controle_pique", []) or []:
            adicionar(self._ponto_tupla(item))
        for item in elemento.get("pontos_controle_principais", []) or []:
            if not isinstance(item, dict):
                continue
            origem = str(item.get("origem") or "").strip().lower()
            if item.get("divide_costura") is False or origem == "pique":
                adicionar(self._ponto_tupla(item))
        return saida

    def _indice_ponto_mais_proximo(
        self,
        pontos: list[tuple[float, float]],
        alvo: tuple[float, float],
    ) -> tuple[int, float] | None:
        if not pontos:
            return None
        melhor_idx = 0
        melhor_dist = self._dist(pontos[0], alvo)
        for idx, ponto in enumerate(pontos[1:], start=1):
            dist = self._dist(ponto, alvo)
            if dist < melhor_dist:
                melhor_idx = idx
                melhor_dist = dist
        return melhor_idx, melhor_dist

    def _indices_controles_no_contorno(
        self,
        pontos: list[tuple[float, float]],
        controles: list[tuple[float, float]],
    ) -> list[int]:
        if len(pontos) < 3 or len(controles) < 3:
            return []
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        diagonal = sqrt(((max(xs) - min(xs)) ** 2) + ((max(ys) - min(ys)) ** 2)) if xs and ys else 0.0
        tolerancia = max(1e-4, diagonal * 0.08)
        indices: list[int] = []
        for controle in controles:
            encontrado = self._indice_ponto_mais_proximo(pontos, controle)
            if encontrado is None:
                return []
            idx, dist = encontrado
            if dist > tolerancia:
                return []
            if idx in indices:
                return []
            indices.append(idx)
        return indices if len(indices) >= 3 else []

    def _trecho_contorno_indices(
        self,
        pontos: list[tuple[float, float]],
        inicio: int,
        fim: int,
    ) -> list[tuple[float, float]]:
        total = len(pontos)
        if total <= 0:
            return []
        inicio %= total
        fim %= total
        if inicio <= fim:
            trecho = list(pontos[inicio:fim + 1])
        else:
            trecho = list(pontos[inicio:]) + list(pontos[:fim + 1])
        return trecho if len(trecho) >= 2 else []

    def _contorno_principal_elemento(
        self,
        elemento: dict,
    ) -> tuple[list[tuple[float, float]], list[int], list[list[tuple[float, float]]]] | None:
        if not isinstance(elemento, dict):
            return None
        pontos = self._pontos_polyline_abertos(elemento)
        controles = self._controles_principais_elemento(elemento)
        indices = self._indices_controles_no_contorno(pontos, controles)
        if len(pontos) < 3 or len(controles) < 3 or len(indices) != len(controles):
            return None

        trechos: list[list[tuple[float, float]]] = []
        total_controles = len(controles)
        for i, inicio in enumerate(indices):
            fim = indices[(i + 1) % total_controles]
            trecho = self._trecho_contorno_indices(pontos, inicio, fim)
            if len(trecho) < 2:
                return None
            trecho[0] = controles[i]
            trecho[-1] = controles[(i + 1) % total_controles]
            trechos.append(trecho)
        return controles, indices, trechos

    def _base_interativa_elemento(self, elemento: dict) -> list[tuple[float, float]]:
        contorno = self._contorno_principal_elemento(elemento)
        if contorno is not None:
            controles, _indices, _trechos = contorno
            return list(controles)
        pontos = self._pontos_fechados(elemento)
        return pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else pontos

    def _segmentos_interativos_elemento(self, elemento: dict) -> list[list[tuple[float, float]]]:
        contorno = self._contorno_principal_elemento(elemento)
        if contorno is not None:
            _controles, _indices, trechos = contorno
            return [[tuple(p) for p in trecho] for trecho in trechos if len(trecho) >= 2]

        pontos = self._pontos_fechados(elemento)
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        total = len(base)
        if total < 2:
            return []
        return [[base[i], base[(i + 1) % total]] for i in range(total)]

    def _limpar_preview_visual(self) -> None:
        self._preview = []
        self._preview_conectores = []
        self._preview_idx = None
        self._hover_segmento = None
        self._realce_segmentos = []

    def _limpar_estado(self) -> None:
        self._limpar_preview_visual()
        self._costura_em_andamento = False
        self._costura_finalizada = False
        self._alvo_idx = None
        self._segmento_inicio = None
        self._segmentos_selecionados = set()
        self._segmentos_ordem = []
        self._direito_confirma_fechamento = False

    def _total_segmentos(self, canvas, idx: int) -> int:
        if not self._elemento_valido(canvas, idx):
            return 0
        return self._total_segmentos_elemento(canvas.cena.elementos[idx])

    def _total_segmentos_elemento(self, elemento: dict) -> int:
        trechos = self._segmentos_interativos_elemento(elemento)
        if trechos:
            return len(trechos)
        pontos = self._pontos_fechados(elemento)
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else pontos
        return len(base)

    @staticmethod
    def _distancia_circular(inicio: int, fim: int, total: int) -> int:
        if total <= 0:
            return 0
        return (fim - inicio) % total

    def _passo_horario(self, base: list[tuple[float, float]]) -> int:
        """Retorna o avanço de índice que representa o sentido horário visual no canvas."""
        if len(base) < 3:
            return 1
        # No canvas Qt, normalmente Y cresce para baixo. Nesse sistema, área positiva
        # representa o contorno visualmente horário; área negativa representa anti-horário.
        return 1 if self._area_assinada(base) >= 0.0 else -1

    def _ordem_segmentos_horaria_visual(self, base: list[tuple[float, float]]) -> list[int]:
        """Ordem horária seguindo o perímetro real do molde.

        A costura precisa percorrer o contorno, ponto a ponto. Ordenar segmentos
        pelo ângulo em torno do centro parece correto em retângulos, mas em cavas
        e moldes côncavos pula pelo meio do molde e deixa trechos de fora.
        """
        total = len(base)
        if total <= 0:
            return []
        if self._passo_horario(base) >= 0:
            return list(range(total))
        return list(range(total - 1, -1, -1))

    def _segmentos_horarios(self, base: list[tuple[float, float]], inicio: int, fim: int) -> list[int]:
        total = len(base)
        if total <= 0:
            return []
        inicio %= total
        fim %= total
        ciclo = self._ordem_segmentos_horaria_visual(base)
        if inicio not in ciclo or fim not in ciclo:
            return [inicio]
        pos_inicio = ciclo.index(inicio)
        pos_fim = ciclo.index(fim)
        ordem = [inicio]
        pos = pos_inicio
        limite = total + 1
        while pos != pos_fim and len(ordem) < limite:
            pos = (pos + 1) % total
            ordem.append(ciclo[pos])
        return ordem

    def _ordenar_segmentos_horario(self, base: list[tuple[float, float]], segmentos: set[int]) -> list[int]:
        total = len(base)
        if total <= 0 or not segmentos:
            return []
        segmentos_norm = {int(s) % total for s in segmentos}
        ciclo = self._ordem_segmentos_horaria_visual(base)
        return [seg_idx for seg_idx in ciclo if seg_idx in segmentos_norm] or sorted(segmentos_norm)

    def _ordenar_segmentos_contiguos(
        self,
        base: list[tuple[float, float]],
        segmentos: set[int],
    ) -> list[int]:
        total = len(base)
        if total <= 0 or not segmentos:
            return []
        segmentos_norm = {int(s) % total for s in segmentos}
        ciclo = self._ordem_segmentos_horaria_visual(base)
        if not ciclo:
            return sorted(segmentos_norm)
        if len(segmentos_norm) >= total:
            return list(ciclo)

        inicio = None
        for pos, seg_idx in enumerate(ciclo):
            if seg_idx in segmentos_norm and ciclo[pos - 1] not in segmentos_norm:
                inicio = pos
                break
        if inicio is None:
            return [seg_idx for seg_idx in ciclo if seg_idx in segmentos_norm]

        ordem: list[int] = []
        pos = inicio
        for _ in range(len(ciclo)):
            seg_idx = ciclo[pos]
            if seg_idx not in segmentos_norm:
                break
            ordem.append(seg_idx)
            pos = (pos + 1) % len(ciclo)

        if set(ordem) == segmentos_norm:
            return ordem
        return [seg_idx for seg_idx in ciclo if seg_idx in segmentos_norm]

    def _ordem_segmentos_contigua(
        self,
        base: list[tuple[float, float]],
        ordem: list[int] | None,
        segmentos: set[int],
    ) -> bool:
        total = len(base)
        if total <= 0 or not ordem or not segmentos:
            return False
        segmentos_norm = {int(s) % total for s in segmentos}
        ordem_norm = [int(s) % total for s in ordem]
        if set(ordem_norm) != segmentos_norm or len(ordem_norm) != len(segmentos_norm):
            return False
        if len(ordem_norm) <= 1:
            return True
        ciclo = self._ordem_segmentos_horaria_visual(base)
        if not ciclo or ordem_norm[0] not in ciclo:
            return False
        pos = ciclo.index(ordem_norm[0])
        esperado = []
        for _ in ordem_norm:
            esperado.append(ciclo[pos])
            pos = (pos + 1) % total
        return esperado == ordem_norm

    def _vertices_caminho_horario(
        self,
        base: list[tuple[float, float]],
        ordem: list[int],
    ) -> list[tuple[float, float]]:
        total = len(base)
        if total <= 0 or not ordem:
            return []
        passo = self._passo_horario(base)
        ordem = [int(s) % total for s in ordem]
        if passo >= 0:
            vertices = [base[ordem[0]]]
            for seg_idx in ordem:
                vertices.append(base[(seg_idx + 1) % total])
        else:
            vertices = [base[(ordem[0] + 1) % total]]
            for seg_idx in ordem:
                vertices.append(base[seg_idx % total])
        return vertices

    def _agrupar_segmentos(self, segmentos: set[int], total: int) -> list[list[int]]:
        if total <= 0 or not segmentos:
            return []
        ordenados = sorted({s % total for s in segmentos})
        grupos: list[list[int]] = []
        grupo = [ordenados[0]]
        for seg_idx in ordenados[1:]:
            if seg_idx == grupo[-1] + 1:
                grupo.append(seg_idx)
            else:
                grupos.append(grupo)
                grupo = [seg_idx]
        grupos.append(grupo)
        if len(grupos) > 1 and grupos[0][0] == 0 and grupos[-1][-1] == total - 1:
            grupos[0] = grupos[-1] + grupos[0]
            grupos.pop()
        return grupos

    @staticmethod
    def _acabamento_canto_reto(acabamento: str) -> bool:
        return str(acabamento or "").strip().lower() in {"", "canto reto", "reto"}

    def _deduplicar_pontos(self, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []
        for ponto in pontos:
            if not saida or self._dist(saida[-1], ponto) > 1e-6:
                saida.append((round(float(ponto[0]), 6), round(float(ponto[1]), 6)))
        return saida

    def _normal_externa_vetor(
        self,
        dx: float,
        dy: float,
        sentido: float,
    ) -> tuple[float, float]:
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-9:
            return 0.0, 0.0
        return sentido * (-dy / comp), sentido * (dx / comp)

    def _offsetar_trecho_principal(
        self,
        trecho: list[tuple[float, float]],
        margem_inicio: float,
        margem_fim: float,
        sentido: float,
    ) -> list[tuple[float, float]]:
        if len(trecho) < 2:
            return []

        comprimentos = [0.0]
        total = 0.0
        for a, b in zip(trecho, trecho[1:]):
            total += self._dist(a, b)
            comprimentos.append(total)
        if total <= 1e-9:
            total = 1.0

        saida: list[tuple[float, float]] = []
        ultimo = len(trecho) - 1
        for i, ponto in enumerate(trecho):
            if i == 0:
                ref_a, ref_b = trecho[0], trecho[1]
            elif i == ultimo:
                ref_a, ref_b = trecho[ultimo - 1], trecho[ultimo]
            else:
                ref_a, ref_b = trecho[i - 1], trecho[i + 1]
            nx, ny = self._normal_externa_vetor(ref_b[0] - ref_a[0], ref_b[1] - ref_a[1], sentido)
            frac = comprimentos[i] / total
            margem = float(margem_inicio) + ((float(margem_fim) - float(margem_inicio)) * frac)
            saida.append((ponto[0] + (nx * margem), ponto[1] + (ny * margem)))
        return self._deduplicar_pontos(saida)

    def _intersecao_offsets(
        self,
        anterior: list[tuple[float, float]],
        atual: list[tuple[float, float]],
    ) -> tuple[float, float] | None:
        if len(anterior) < 2 or len(atual) < 2:
            return None
        return self._intersecao_linhas(anterior[-2], anterior[-1], atual[0], atual[1])

    def _margens_vertices(
        self,
        quantidade_segmentos: int,
        margem_inicio: float,
        margem_fim: float,
        usar_largura_fim: bool,
    ) -> list[float]:
        quantidade_segmentos = max(1, int(quantidade_segmentos))
        if not usar_largura_fim:
            return [float(margem_inicio)] * (quantidade_segmentos + 1)
        return [
            float(margem_inicio)
            + ((float(margem_fim) - float(margem_inicio)) * (i / quantidade_segmentos))
            for i in range(quantidade_segmentos + 1)
        ]

    def _gerar_costura_principal_atual(
        self,
        canvas,
        elemento: dict,
        margem_inicio: float,
        margem_fim: float,
        usar_largura_fim: bool,
    ) -> list[tuple[float, float]]:
        contorno = self._contorno_principal_elemento(elemento)
        if contorno is None:
            return []
        controles, _indices, trechos = contorno
        if len(controles) < 3 or len(trechos) != len(controles):
            return []
        ordem = self._ordem_segmentos_horaria_visual(controles)
        return self._gerar_costura_principal_por_ordem(
            controles,
            trechos,
            ordem,
            margem_inicio,
            margem_fim,
            usar_largura_fim,
            selecao_total=True,
            acabamento_inicial=self._acabamentos_atuais(canvas)[0],
            acabamento_final=self._acabamentos_atuais(canvas)[1],
        )

    def _gerar_costura_segmentos_principais_atual(
        self,
        canvas,
        elemento: dict,
        segmentos: set[int],
        ordem: list[int] | None,
        margem_inicio: float,
        margem_fim: float,
        usar_largura_fim: bool,
    ) -> list[tuple[float, float]]:
        contorno = self._contorno_principal_elemento(elemento)
        if contorno is None:
            return []
        controles, _indices, trechos = contorno
        total = len(controles)
        if total < 3 or not segmentos or len(trechos) != total:
            return []
        segmentos_norm = {int(s) % total for s in segmentos}
        if not ordem:
            ordem = self._ordenar_segmentos_horario(controles, segmentos_norm)
        ordem_norm = [int(s) % total for s in ordem if int(s) % total in segmentos_norm]
        if not ordem_norm:
            return []
        selecao_total = len(segmentos_norm) >= total
        if not selecao_total and not self._ordem_segmentos_contigua(controles, ordem_norm, segmentos_norm):
            return []
        return self._gerar_costura_principal_por_ordem(
            controles,
            trechos,
            ordem_norm,
            margem_inicio,
            margem_fim,
            usar_largura_fim,
            selecao_total=selecao_total,
            acabamento_inicial=self._acabamentos_atuais(canvas)[0],
            acabamento_final=self._acabamentos_atuais(canvas)[1],
        )

    def _trecho_orientado_principal(
        self,
        trecho: list[tuple[float, float]],
        passo: int,
    ) -> list[tuple[float, float]]:
        if passo >= 0:
            return list(trecho)
        return list(reversed(trecho))

    def _offset_trecho_orientado_principal(
        self,
        trecho: list[tuple[float, float]],
        passo: int,
        margem_inicio: float,
        margem_fim: float,
        sentido: float,
    ) -> list[tuple[float, float]]:
        if passo >= 0:
            return self._offsetar_trecho_principal(trecho, margem_inicio, margem_fim, sentido)
        offset_original = self._offsetar_trecho_principal(trecho, margem_fim, margem_inicio, sentido)
        return list(reversed(offset_original))

    def _gerar_costura_principal_por_ordem(
        self,
        controles: list[tuple[float, float]],
        trechos: list[list[tuple[float, float]]],
        ordem: list[int],
        margem_inicio: float,
        margem_fim: float,
        usar_largura_fim: bool,
        selecao_total: bool,
        acabamento_inicial: str = "Canto reto",
        acabamento_final: str = "Canto reto",
    ) -> list[tuple[float, float]]:
        total = len(controles)
        if total < 3 or not ordem:
            return []

        sentido = 1.0 if self._area_assinada(controles) < 0.0 else -1.0
        passo = self._passo_horario(controles)

        if selecao_total:
            margens = self._margens_vertices(total, margem_inicio, margem_fim, usar_largura_fim)
            offsets = [
                self._offsetar_trecho_principal(trechos[i], margens[i], margens[i + 1], sentido)
                for i in range(total)
            ]
            if any(len(off) < 2 for off in offsets):
                return []

            encontros: list[tuple[float, float]] = []
            for i in range(total):
                anterior = offsets[(i - 1) % total]
                atual = offsets[i]
                inter = self._intersecao_offsets(anterior, atual)
                encontros.append(inter if inter is not None else atual[0])

            saida: list[tuple[float, float]] = [encontros[0]]
            for i in range(total):
                for ponto in offsets[i][1:-1]:
                    saida.append(ponto)
                saida.append(encontros[(i + 1) % total])
            if saida and self._dist(saida[0], saida[-1]) > 1e-6:
                saida.append(saida[0])
            return self._deduplicar_pontos(saida)

        ordem_norm = [int(s) % total for s in ordem]
        margens = self._margens_vertices(len(ordem_norm), margem_inicio, margem_fim, usar_largura_fim)
        partes_base: list[list[tuple[float, float]]] = []
        partes_offset: list[list[tuple[float, float]]] = []
        for pos, seg_idx in enumerate(ordem_norm):
            trecho = trechos[seg_idx]
            base_orientada = self._trecho_orientado_principal(trecho, passo)
            offset = self._offset_trecho_orientado_principal(trecho, passo, margens[pos], margens[pos + 1], sentido)
            if len(base_orientada) < 2 or len(offset) < 2:
                return []
            partes_base.append(base_orientada)
            partes_offset.append(offset)

        for i in range(1, len(partes_offset)):
            inter = self._intersecao_offsets(partes_offset[i - 1], partes_offset[i])
            if inter is not None:
                ponto = (round(float(inter[0]), 6), round(float(inter[1]), 6))
                partes_offset[i - 1][-1] = ponto
                partes_offset[i][0] = ponto

        saida: list[tuple[float, float]] = []
        inicio_base = partes_base[0][0]
        inicio_offset = partes_offset[0][0]
        fim_base = partes_base[-1][-1]
        fim_offset = partes_offset[-1][-1]

        if self._acabamento_canto_reto(acabamento_inicial):
            saida.extend([inicio_base, inicio_offset])
        else:
            tangente = self._vetor_normalizado(partes_base[0][0], partes_base[0][1])
            saida.extend(
                self._pontos_acabamento_livre(
                    inicio_base,
                    inicio_offset,
                    tangente,
                    float(margem_inicio),
                    acabamento_inicial,
                    inicio=True,
                )
            )

        for parte in partes_offset:
            for ponto in parte:
                if not saida or self._dist(saida[-1], ponto) > 1e-6:
                    saida.append(ponto)

        if self._acabamento_canto_reto(acabamento_final):
            if not saida or self._dist(saida[-1], fim_offset) > 1e-6:
                saida.append(fim_offset)
            saida.append(fim_base)
        else:
            tangente = self._vetor_normalizado(partes_base[-1][-2], partes_base[-1][-1])
            for ponto in self._pontos_acabamento_livre(
                fim_base,
                fim_offset,
                tangente,
                float(margem_fim),
                acabamento_final,
                inicio=False,
            ):
                if not saida or self._dist(saida[-1], ponto) > 1e-6:
                    saida.append(ponto)

        return self._deduplicar_pontos(saida)

    def _gerar_costura_segmentos(
        self,
        pontos: list[tuple[float, float]],
        segmentos: set[int],
        margem: float,
        acabamento_inicial: str = "Canto reto",
        acabamento_final: str = "Canto reto",
    ) -> list[tuple[float, float]]:
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        total = len(base)
        if total < 3 or not segmentos:
            return []
        segmentos = {s % total for s in segmentos}
        if len(segmentos) >= total:
            return self._gerar_costura(pontos, margem)
        costura_total = self._gerar_costura(pontos, margem)
        if len(costura_total) < total + 1:
            return []
        ordenados = sorted(segmentos)
        grupos: list[list[int]] = []
        grupo = [ordenados[0]]
        for seg_idx in ordenados[1:]:
            if seg_idx == grupo[-1] + 1:
                grupo.append(seg_idx)
            else:
                grupos.append(grupo)
                grupo = [seg_idx]
        grupos.append(grupo)
        if len(grupos) > 1 and grupos[0][0] == 0 and grupos[-1][-1] == total - 1:
            grupos[0] = grupos[-1] + grupos[0]
            grupos.pop()

        saida: list[tuple[float, float]] = []
        for grupo in grupos:
            inicio = grupo[0]
            fim_vertice = (grupo[-1] + 1) % total
            cap_ini = []
            if not self._acabamento_canto_reto(acabamento_inicial):
                cap_ini = self._pontos_acabamento_extremidade(
                    base,
                    costura_total,
                    inicio,
                    grupo[0],
                    margem,
                    acabamento_inicial,
                    inicio=True,
                )
            for ponto in cap_ini:
                if not saida or self._dist(saida[-1], ponto) > 1e-6:
                    saida.append(ponto)
            for pos, seg_idx in enumerate(grupo):
                if not saida or (pos == 0 and self._dist(saida[-1], costura_total[seg_idx]) > 1e-6):
                    saida.append(costura_total[seg_idx])
                prox = costura_total[(seg_idx + 1) % total]
                if not saida or self._dist(saida[-1], prox) > 1e-6:
                    saida.append(prox)
            cap_fim = []
            if not self._acabamento_canto_reto(acabamento_final):
                cap_fim = self._pontos_acabamento_extremidade(
                    base,
                    costura_total,
                    fim_vertice,
                    grupo[-1],
                    margem,
                    acabamento_final,
                    inicio=False,
                )
            for ponto in cap_fim:
                if not saida or self._dist(saida[-1], ponto) > 1e-6:
                    saida.append(ponto)
            if len(grupos) > 1:
                saida.append(saida[-1])
        return saida

    def _normal_externa_segmento(
        self,
        base: list[tuple[float, float]],
        seg_idx: int,
    ) -> tuple[float, float]:
        total = len(base)
        if total <= 0:
            return 0.0, 0.0
        a = base[seg_idx % total]
        b = base[(seg_idx + 1) % total]
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-9:
            return 0.0, 0.0
        sentido = 1.0 if self._area_assinada(base) < 0.0 else -1.0
        return sentido * (-dy / comp), sentido * (dx / comp)

    def _linha_offset_constante_segmento(
        self,
        base: list[tuple[float, float]],
        seg_idx: int,
        margem: float,
    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
        total = len(base)
        if total < 2:
            return None
        seg_idx %= total
        a = base[seg_idx]
        b = base[(seg_idx + 1) % total]
        nx, ny = self._normal_externa_segmento(base, seg_idx)
        return (
            (a[0] + (nx * margem), a[1] + (ny * margem)),
            (b[0] + (nx * margem), b[1] + (ny * margem)),
        )

    def _ajustar_extremos_costura_variavel(
        self,
        base: list[tuple[float, float]],
        ordem: list[int],
        linhas: list[tuple[tuple[float, float], tuple[float, float]]],
        costura: list[tuple[float, float]],
        margem_inicio: float,
        margem_fim: float,
    ) -> None:
        """Estende a costura parcial até encontrar as laterais deslocadas.

        Para acabamento "Canto reto", o trecho de costura não deve voltar para
        o ponto original do molde, mas também não pode parar exatamente em cima
        do vértice original deslocado. Ele precisa chegar até a interseção com
        a costura/lateral adjacente do molde. Esse é o pedaço que ficava
        faltando no canto mostrado pelo usuário.
        """
        total = len(base)
        if total < 3 or not ordem or not linhas or not costura:
            return
        if len(set(int(s) % total for s in ordem)) >= total:
            return

        passo = self._passo_horario(base)
        primeiro = int(ordem[0]) % total
        ultimo = int(ordem[-1]) % total
        if passo >= 0:
            anterior_inicio = (primeiro - 1) % total
            proximo_fim = (ultimo + 1) % total
        else:
            anterior_inicio = (primeiro + 1) % total
            proximo_fim = (ultimo - 1) % total

        linha_inicio = self._linha_offset_constante_segmento(base, anterior_inicio, float(margem_inicio))
        if linha_inicio is not None:
            inter_inicio = self._intersecao_linhas(linha_inicio[0], linha_inicio[1], linhas[0][0], linhas[0][1])
            if inter_inicio is not None:
                costura[0] = (round(float(inter_inicio[0]), 6), round(float(inter_inicio[1]), 6))

        linha_fim = self._linha_offset_constante_segmento(base, proximo_fim, float(margem_fim))
        if linha_fim is not None:
            inter_fim = self._intersecao_linhas(linhas[-1][0], linhas[-1][1], linha_fim[0], linha_fim[1])
            if inter_fim is not None:
                costura[-1] = (round(float(inter_fim[0]), 6), round(float(inter_fim[1]), 6))

    def _gerar_costura_segmentos_variavel(
        self,
        pontos: list[tuple[float, float]],
        ordem: list[int],
        margem_inicio: float,
        margem_fim: float,
        acabamento_inicial: str = "Canto reto",
        acabamento_final: str = "Canto reto",
    ) -> list[tuple[float, float]]:
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        total = len(base)
        if total < 3 or not ordem:
            return []

        ordem_normalizada: list[int] = []
        for seg_idx in ordem:
            seg = int(seg_idx) % total
            if not ordem_normalizada or ordem_normalizada[-1] != seg:
                ordem_normalizada.append(seg)
        if not ordem_normalizada:
            return []

        passo = self._passo_horario(base)
        qtd = len(ordem_normalizada)
        delta = float(margem_fim) - float(margem_inicio)
        margens = [float(margem_inicio) + (delta * (i / max(1, qtd))) for i in range(qtd + 1)]

        linhas: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for pos, seg_idx in enumerate(ordem_normalizada):
            if passo >= 0:
                a = base[seg_idx % total]
                b = base[(seg_idx + 1) % total]
            else:
                a = base[(seg_idx + 1) % total]
                b = base[seg_idx % total]
            nx, ny = self._normal_externa_segmento(base, seg_idx)
            m_ini = margens[pos]
            m_fim = margens[pos + 1]
            off_a = (a[0] + (nx * m_ini), a[1] + (ny * m_ini))
            off_b = (b[0] + (nx * m_fim), b[1] + (ny * m_fim))
            linhas.append((off_a, off_b))

        if not linhas:
            return []

        selecao_total = len(set(int(s) % total for s in ordem_normalizada)) >= total

        if selecao_total:
            # Quando a costura pega todo o perímetro, ela precisa ser um contorno
            # fechado. Mesmo com largura inicial/final diferente, o fechamento é
            # feito pela interseção da última linha deslocada com a primeira,
            # evitando pontas abertas e pequenos traços soltos nos cantos.
            fechamento = self._intersecao_linhas(
                linhas[-1][0],
                linhas[-1][1],
                linhas[0][0],
                linhas[0][1],
            )
            if fechamento is None:
                fechamento = linhas[0][0]
            costura: list[tuple[float, float]] = [
                (round(float(fechamento[0]), 6), round(float(fechamento[1]), 6))
            ]
            for i in range(1, len(linhas)):
                anterior = linhas[i - 1]
                atual = linhas[i]
                inter = self._intersecao_linhas(anterior[0], anterior[1], atual[0], atual[1])
                if inter is None:
                    inter = anterior[1]
                costura.append((round(float(inter[0]), 6), round(float(inter[1]), 6)))
            costura.append(costura[0])
            return self._deduplicar_pontos(costura)

        costura: list[tuple[float, float]] = [linhas[0][0]]
        for i in range(1, len(linhas)):
            anterior = linhas[i - 1]
            atual = linhas[i]
            inter = self._intersecao_linhas(anterior[0], anterior[1], atual[0], atual[1])
            if inter is None:
                inter = anterior[1]
            costura.append((round(float(inter[0]), 6), round(float(inter[1]), 6)))
        costura.append(linhas[-1][1])

        if self._acabamento_canto_reto(acabamento_inicial) and self._acabamento_canto_reto(acabamento_final):
            vertices = self._vertices_caminho_horario(base, ordem_normalizada)
            if len(vertices) >= 2:
                return self._deduplicar_pontos([vertices[0]] + costura + [vertices[-1]])
            return self._deduplicar_pontos(costura)

        vertices = self._vertices_caminho_horario(base, ordem_normalizada)
        if len(vertices) < 2:
            return self._deduplicar_pontos(costura)

        tang_ini = self._vetor_normalizado(vertices[0], vertices[1])
        tang_fim = self._vetor_normalizado(vertices[-2], vertices[-1])
        cap_ini = self._pontos_acabamento_livre(
            vertices[0],
            costura[0],
            tang_ini,
            float(margem_inicio),
            acabamento_inicial,
            inicio=True,
        )
        cap_fim = self._pontos_acabamento_livre(
            vertices[-1],
            costura[-1],
            tang_fim,
            float(margem_fim),
            acabamento_final,
            inicio=False,
        )
        return self._deduplicar_pontos(cap_ini + costura + cap_fim)

    @staticmethod
    def _vetor_normalizado(
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> tuple[float, float]:
        dx = float(b[0]) - float(a[0])
        dy = float(b[1]) - float(a[1])
        comp = sqrt((dx * dx) + (dy * dy)) or 1.0
        return dx / comp, dy / comp

    def _pontos_acabamento_livre(
        self,
        base_pt: tuple[float, float],
        off_pt: tuple[float, float],
        tangente: tuple[float, float],
        margem: float,
        acabamento: str,
        inicio: bool,
    ) -> list[tuple[float, float]]:
        tx, ty = tangente
        if inicio:
            tx = -tx
            ty = -ty

        nx = off_pt[0] - base_pt[0]
        ny = off_pt[1] - base_pt[1]
        ncomp = sqrt((nx * nx) + (ny * ny)) or max(1e-9, abs(float(margem)))
        nx /= ncomp
        ny /= ncomp
        dist = abs(float(margem))
        nome = str(acabamento or "Canto reto").strip().lower()

        def p(dx_t: float, dx_n: float) -> tuple[float, float]:
            return (
                round(base_pt[0] + (tx * dx_t) + (nx * dx_n), 6),
                round(base_pt[1] + (ty * dx_t) + (ny * dx_n), 6),
            )

        if "45" in nome:
            pontos = [base_pt, p(dist, dist)]
        elif "90" in nome and "invertido" in nome:
            pontos = [base_pt, p(0.0, dist), p(dist, dist)]
        elif "90" in nome:
            pontos = [base_pt, p(dist, 0.0), p(dist, dist)]
        elif "degrau" in nome:
            pontos = [base_pt, p(dist * 0.55, 0.0), p(dist * 0.55, dist), off_pt]
        elif "fechado" in nome:
            pontos = [base_pt, p(dist * 0.75, dist), off_pt]
        elif "aberto" in nome:
            pontos = [base_pt, p(dist * 0.75, 0.0), off_pt]
        else:
            pontos = [base_pt, off_pt]

        if not inicio:
            pontos = list(reversed(pontos))
        return [(round(float(x), 6), round(float(y), 6)) for x, y in pontos]

    def _pontos_acabamento_extremidade(
        self,
        base: list[tuple[float, float]],
        costura_total: list[tuple[float, float]],
        vertice_idx: int,
        seg_idx: int,
        margem: float,
        acabamento: str,
        inicio: bool,
    ) -> list[tuple[float, float]]:
        total = len(base)
        if total <= 0 or len(costura_total) < total + 1:
            return []
        base_pt = base[vertice_idx % total]
        off_pt = costura_total[vertice_idx % total]
        a = base[seg_idx % total]
        b = base[(seg_idx + 1) % total]
        tx = b[0] - a[0]
        ty = b[1] - a[1]
        comp = sqrt((tx * tx) + (ty * ty)) or 1.0
        tx /= comp
        ty /= comp
        if inicio:
            tx = -tx
            ty = -ty
        nx = off_pt[0] - base_pt[0]
        ny = off_pt[1] - base_pt[1]
        ncomp = sqrt((nx * nx) + (ny * ny)) or max(1e-9, abs(margem))
        nx /= ncomp
        ny /= ncomp
        dist = abs(float(margem))
        nome = str(acabamento or "Canto reto").strip().lower()

        def p(dx_t: float, dx_n: float) -> tuple[float, float]:
            return (
                round(base_pt[0] + (tx * dx_t) + (nx * dx_n), 6),
                round(base_pt[1] + (ty * dx_t) + (ny * dx_n), 6),
            )

        if "45" in nome:
            pontos = [base_pt, p(dist, dist)]
        elif "90" in nome and "invertido" in nome:
            pontos = [base_pt, p(0.0, dist), p(dist, dist)]
        elif "90" in nome:
            pontos = [base_pt, p(dist, 0.0), p(dist, dist)]
        elif "degrau" in nome:
            pontos = [base_pt, p(dist * 0.55, 0.0), p(dist * 0.55, dist), off_pt]
        elif "fechado" in nome:
            pontos = [base_pt, p(dist * 0.75, dist), off_pt]
        elif "aberto" in nome:
            pontos = [base_pt, p(dist * 0.75, 0.0), off_pt]
        else:
            pontos = [base_pt, off_pt]

        if not inicio:
            pontos = list(reversed(pontos))
        return [(round(float(x), 6), round(float(y), 6)) for x, y in pontos]

    def _gerar_conectores_preview_segmentos(
        self,
        canvas,
        idx: int,
        segmentos: set[int],
    ) -> list[tuple[QPointF, QPointF]]:
        if not segmentos or not self._elemento_valido(canvas, idx):
            return []
        if self._contorno_principal_elemento(canvas.cena.elementos[idx]) is not None:
            return []
        pontos = self._pontos_fechados(canvas.cena.elementos[idx])
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        total = len(base)
        if total < 3:
            return []
        segmentos = {s % total for s in segmentos}
        costura_total = self._gerar_costura(base + [base[0]], self._margem_cm)
        if len(costura_total) < total + 1:
            return []
        conectores: list[tuple[QPointF, QPointF]] = []
        for seg_idx in sorted(segmentos):
            a_base = QPointF(*base[seg_idx])
            b_base = QPointF(*base[(seg_idx + 1) % total])
            a_costura = QPointF(*costura_total[seg_idx])
            b_costura = QPointF(*costura_total[(seg_idx + 1) % total])
            conectores.append((a_base, a_costura))
            conectores.append((b_base, b_costura))
        return conectores

    @staticmethod
    def _distancia_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-9:
            return sqrt(((p.x() - a.x()) ** 2) + ((p.y() - a.y()) ** 2))
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return sqrt(((p.x() - proj.x()) ** 2) + ((p.y() - proj.y()) ** 2))

    def _gerar_costura(self, pontos: list[tuple[float, float]], margem: float) -> list[tuple[float, float]]:
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        if len(base) < 3:
            return []
        cpp = seam_offset_closed_cpp(base + [base[0]], margem)
        if cpp:
            return cpp
        sentido = 1.0 if self._area_assinada(base) < 0.0 else -1.0
        linhas = []
        total = len(base)
        for i in range(total):
            a = base[i]
            b = base[(i + 1) % total]
            dx = b[0] - a[0]
            dy = b[1] - a[1]
            comp = sqrt((dx * dx) + (dy * dy))
            if comp <= 1e-9:
                linhas.append((a, b, (0.0, 0.0)))
                continue
            nx = sentido * (-dy / comp)
            ny = sentido * (dx / comp)
            off_a = (a[0] + (nx * margem), a[1] + (ny * margem))
            off_b = (b[0] + (nx * margem), b[1] + (ny * margem))
            linhas.append((off_a, off_b, (nx, ny)))

        saida: list[tuple[float, float]] = []
        for i in range(total):
            prev_a, prev_b, prev_n = linhas[(i - 1) % total]
            curr_a, curr_b, curr_n = linhas[i]
            inter = self._intersecao_linhas(prev_a, prev_b, curr_a, curr_b)
            if inter is None:
                p = base[i]
                nx = (prev_n[0] + curr_n[0]) / 2.0
                ny = (prev_n[1] + curr_n[1]) / 2.0
                mod = sqrt((nx * nx) + (ny * ny)) or 1.0
                inter = (p[0] + (nx / mod * margem), p[1] + (ny / mod * margem))
            saida.append((round(inter[0], 6), round(inter[1], 6)))
        if saida and self._dist(saida[0], saida[-1]) > 1e-6:
            saida.append(saida[0])
        return saida

    @staticmethod
    def _intersecao_linhas(a1, a2, b1, b2) -> tuple[float, float] | None:
        x1, y1 = a1
        x2, y2 = a2
        x3, y3 = b1
        x4, y4 = b2
        den = ((x1 - x2) * (y3 - y4)) - ((y1 - y2) * (x3 - x4))
        if abs(den) <= 1e-9:
            return None
        px = (((x1 * y2) - (y1 * x2)) * (x3 - x4) - (x1 - x2) * ((x3 * y4) - (y3 * x4))) / den
        py = (((x1 * y2) - (y1 * x2)) * (y3 - y4) - (y1 - y2) * ((x3 * y4) - (y3 * x4))) / den
        return px, py

    @staticmethod
    def _area_assinada(pontos: list[tuple[float, float]]) -> float:
        area = 0.0
        for a, b in zip(pontos, pontos[1:] + pontos[:1]):
            area += (a[0] * b[1]) - (b[0] * a[1])
        return area / 2.0

    @staticmethod
    def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt(((a[0] - b[0]) ** 2) + ((a[1] - b[1]) ** 2))

    def _fmt_medida_canvas(self, canvas, valor_cena: float) -> str:
        sigla, fator = unidade_canvas(canvas)
        return f"{self._fmt(float(valor_cena) / max(1e-9, fator))} {sigla}"

    def _mensagem_pronta(self, canvas=None) -> str:
        largura = self._fmt_medida_canvas(canvas, self._margem_cm) if canvas is not None else f"{self._fmt(self._margem_cm)} cm"
        return (
            f"Costura pronta: largura inicial {largura}. "
            "Passe o mouse para prever, clique aplica. +/- ajusta, Enter aplica na seleção."
        )

    @staticmethod
    def _fmt(valor: float) -> str:
        texto = formatar_numero(valor, 2)
        if texto == "-0":
            texto = "0"
        return texto
