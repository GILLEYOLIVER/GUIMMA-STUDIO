from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QTextEdit,
    QWidget,
)

from tools.medicao_utils import mensagem_status
from tools.texto_config import ALTURA_TEXTO_PADRAO_CM, ESPACO_LINHAS_PADRAO_CM, configurar_texto_canvas
from tools.texto_persistente_utils import aplicar_patch_canvas_textos
from tools.tool_base import FerramentaBase


class TextoDialog(QDialog):
    def __init__(self, canvas, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Criar texto")
        self.setModal(True)
        self.resize(520, 360)

        configurar_texto_canvas(canvas)

        self.txt_texto = QTextEdit(self)
        self.txt_texto.setPlainText("Texto")
        self.txt_texto.selectAll()

        self.spin_angulo = QDoubleSpinBox(self)
        self.spin_angulo.setRange(-360.0, 360.0)
        self.spin_angulo.setDecimals(2)
        self.spin_angulo.setValue(0.0)

        self.spin_altura = QDoubleSpinBox(self)
        self.spin_altura.setRange(0.2, 200.0)
        self.spin_altura.setDecimals(2)
        self.spin_altura.setValue(float(getattr(canvas, "_texto_altura_cm", ALTURA_TEXTO_PADRAO_CM)))
        self.spin_altura.setSuffix(" cm")

        self.spin_espaco = QDoubleSpinBox(self)
        self.spin_espaco.setRange(0.2, 200.0)
        self.spin_espaco.setDecimals(2)
        self.spin_espaco.setValue(float(getattr(canvas, "_texto_espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM)))
        self.spin_espaco.setSuffix(" cm")

        self.combo_referencia = QComboBox(self)
        self.combo_referencia.addItems([
            "Topo esquerda",
            "Topo centro",
            "Topo direita",
            "Centro esquerda",
            "Centro centro",
            "Centro direita",
            "Baixo esquerda",
            "Baixo centro",
            "Baixo direita",
        ])
        self.combo_referencia.setCurrentText("Topo esquerda")

        self.combo_justificacao = QComboBox(self)
        self.combo_justificacao.addItems(["Esquerda", "Centro", "Direita"])
        self.combo_justificacao.setCurrentText("Esquerda")

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout = QGridLayout(self)
        layout.addWidget(self.txt_texto, 0, 0, 1, 6)
        layout.addWidget(QLabel("Ângulo"), 1, 0)
        layout.addWidget(QLabel("Altura (cm)"), 1, 2)
        layout.addWidget(QLabel("Espaço entre linhas (cm)"), 1, 4)
        layout.addWidget(self.spin_angulo, 2, 0, 1, 2)
        layout.addWidget(self.spin_altura, 2, 2, 1, 2)
        layout.addWidget(self.spin_espaco, 2, 4, 1, 2)
        layout.addWidget(QLabel("Referência"), 3, 0)
        layout.addWidget(QLabel("Justificação"), 3, 3)
        layout.addWidget(self.combo_referencia, 4, 0, 1, 3)
        layout.addWidget(self.combo_justificacao, 4, 3, 1, 3)
        layout.addWidget(botoes, 5, 0, 1, 6)
        layout.setRowStretch(0, 1)

    def valores(self) -> dict:
        return {
            "texto": self.txt_texto.toPlainText(),
            "angulo": float(self.spin_angulo.value()),
            "altura_cm": float(self.spin_altura.value()),
            "espaco_linhas_cm": float(self.spin_espaco.value()),
            "referencia": self.combo_referencia.currentText(),
            "justificacao": self.combo_justificacao.currentText(),
        }


class Ferramenta(FerramentaBase):
    id_ferramenta = "inserir_texto"
    nome = "Inserir Texto"
    descricao_painel = ""
    gerencia_coordenadas_operacao = True

    def __init__(self):
        super().__init__()
        self._config_pendente: dict | None = None
        self._dialogo_aberto = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        configurar_texto_canvas(canvas)
        aplicar_patch_canvas_textos(canvas)
        self._config_pendente = None
        self._dialogo_aberto = False
        QTimer.singleShot(0, lambda: self._abrir_dialogo_inicial(canvas))

    def _abrir_dialogo_inicial(self, canvas) -> None:
        if self._dialogo_aberto:
            return
        self._dialogo_aberto = True
        dlg = TextoDialog(canvas, canvas)
        if dlg.exec() == QDialog.Accepted:
            valores = dlg.valores()
            configurar_texto_canvas(canvas, valores["altura_cm"], valores["espaco_linhas_cm"])
            self._config_pendente = valores
            texto = "Inserir Texto: clique no canvas para posicionar o texto."
        else:
            self._config_pendente = None
            texto = "Inserir Texto cancelado."
        self._dialogo_aberto = False
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        aplicar_patch_canvas_textos(canvas)

        if not self._config_pendente:
            self._abrir_dialogo_inicial(canvas)
            event.accept()
            return True

        pos = canvas._ponto_com_snap(event.position())
        valores = self._config_pendente
        cor = getattr(canvas, "_linha_cor", "#ffffff")
        elemento = {
            "tipo": "texto",
            "texto": valores["texto"],
            "posicao": (float(pos.x()), float(pos.y())),
            "angulo": valores["angulo"],
            "texto_altura_cm": valores["altura_cm"],
            "texto_espaco_linhas_cm": valores["espaco_linhas_cm"],
            "referencia": valores["referencia"],
            "justificacao": valores["justificacao"],
            "cor": str(cor),
            "cor_texto": str(cor),
        }
        canvas.cena.elementos.append(elemento)
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        canvas.update()
        self._config_pendente = None
        mensagem_status(canvas, "Texto criado. Clique na ferramenta novamente para criar outro texto.")
        event.accept()
        return True
