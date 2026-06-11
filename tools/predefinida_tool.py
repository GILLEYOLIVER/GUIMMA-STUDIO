from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from core.formatacao import formatar_numero
from tools.espiral_e_curvas_tool import Ferramenta as FerramentaEspiralCurvas
from tools.espiral_e_curvas_tool import _gerar_curva_base
from tools.espiral_e_curvas_tool import _gerar_pontos_controle_base


class InserirPredefinidaDialog(QDialog):
    configuracao_alterada = Signal()
    OPCOES = [
        "Decote",
        "Curva Francesa 1",
        "Curva Francesa 2",
        "Curva Francesa 3",
        "Curva Francesa 4",
        "Manga - Cava frente",
        "Cava costas",
        "Gancho calça",
        "Lado saia",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inserir curva")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(260)
        self._fator_escala = 1.0
        self._montar_ui()

    def _montar_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        lay.addWidget(QLabel("Curva pré-definida"))
        self.cmb_curva = QComboBox()
        self.cmb_curva.addItems(self.OPCOES)
        lay.addWidget(self.cmb_curva)

        linha_botoes = QHBoxLayout()
        for texto in ["↩", "⟳", "∡", "▯▯"]:
            btn = QPushButton(texto)
            btn.setEnabled(False)
            btn.setFixedWidth(34)
            linha_botoes.addWidget(btn)
        linha_botoes.addStretch(1)
        self.btn_menos = QPushButton("-")
        self.btn_mais = QPushButton("+")
        self.btn_menos.setFixedWidth(24)
        self.btn_mais.setFixedWidth(24)
        linha_botoes.addWidget(self.btn_menos)
        linha_botoes.addWidget(self.btn_mais)
        lay.addLayout(linha_botoes)

        self.chk_dividir = QCheckBox("Dividir elemento")
        self.chk_dividir.setChecked(True)
        lay.addWidget(self.chk_dividir)

        self.cmb_perimetro = QComboBox()
        self.cmb_perimetro.addItems(["Perímetro bi-direcional", "Perímetro uni-direcional 1", "Perímetro uni-direcional 2"])
        lay.addWidget(self.cmb_perimetro)

        grid = QGridLayout()
        grid.addWidget(QLabel("Incremento perímetro (cm)"), 0, 0)
        self.ed_incremento = QLineEdit("1")
        grid.addWidget(self.ed_incremento, 0, 1)
        self.lbl_total = QLabel("0")
        self.lbl_ext1 = QLabel("0")
        self.lbl_ext2 = QLabel("0")
        grid.addWidget(QLabel("Total (cm)"), 1, 0)
        grid.addWidget(self.lbl_total, 1, 1)
        grid.addWidget(QLabel("Extremo 1 (cm)"), 2, 0)
        grid.addWidget(self.lbl_ext1, 2, 1)
        grid.addWidget(QLabel("Extremo 2 (cm)"), 3, 0)
        grid.addWidget(self.lbl_ext2, 3, 1)
        lay.addLayout(grid)

        self.cmb_curva.currentTextChanged.connect(self._atualizar_metricas)
        self.cmb_perimetro.currentTextChanged.connect(self._atualizar_metricas)
        self.btn_menos.clicked.connect(self._diminuir_escala)
        self.btn_mais.clicked.connect(self._aumentar_escala)

        self._atualizar_metricas()

    def _diminuir_escala(self):
        self._fator_escala = max(0.2, self._fator_escala - 0.1)
        self._atualizar_metricas()

    def _aumentar_escala(self):
        self._fator_escala = min(4.0, self._fator_escala + 0.1)
        self._atualizar_metricas()

    def configuracao(self) -> tuple[str, float, float, bool]:
        return self.cmb_curva.currentText(), 0.0, 1.0, False

    def pontos_processados(self):
        pts = _gerar_curva_base(self.cmb_curva.currentText())
        return [p * self._fator_escala for p in pts]

    def pontos_controle_processados(self):
        pts = _gerar_pontos_controle_base(self.cmb_curva.currentText())
        return [p * self._fator_escala for p in pts]

    def _atualizar_metricas(self):
        pontos = self.pontos_processados()
        total = 0.0
        for a, b in zip(pontos, pontos[1:]):
            total += ((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5
        modo = self.cmb_perimetro.currentText()
        if modo == "Perímetro bi-direcional":
            ext1 = ext2 = total / 2.0
        elif modo.endswith("1"):
            ext1, ext2 = total, 0.0
        else:
            ext1, ext2 = 0.0, total
        self.lbl_total.setText(formatar_numero(total, 2))
        self.lbl_ext1.setText(formatar_numero(ext1, 2))
        self.lbl_ext2.setText(formatar_numero(ext2, 2))
        self.configuracao_alterada.emit()


class Ferramenta(FerramentaEspiralCurvas):
    id_ferramenta = "predefinida"
    nome = "Inserir curva"

    def _obter_dialog(self, canvas):
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent or not isinstance(dialog, InserirPredefinidaDialog):
            dialog = InserirPredefinidaDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        if not hasattr(dialog, "_callbacks_canvas"):
            dialog._callbacks_canvas = set()  # type: ignore[attr-defined]
        if chave not in dialog._callbacks_canvas:  # type: ignore[attr-defined]
            dialog.configuracao_alterada.connect(lambda chave_canvas=chave: self._quando_config_alterada(chave_canvas))
            dialog._callbacks_canvas.add(chave)  # type: ignore[attr-defined]
        return dialog
