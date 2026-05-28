from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor
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
from tools.tool_base import FerramentaBase


_BITMAP_5X7 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01111", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "11110"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    ",": ["00000", "00000", "00000", "00000", "01100", "00100", "01000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "/": ["00001", "00001", "00010", "00100", "01000", "10000", "10000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "?": ["01110", "10001", "00001", "00010", "00100", "00000", "00100"],
}

_ACENTOS = str.maketrans("ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüç", "AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuuc")


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
        self.combo_referencia.addItems(["Topo esquerda", "Topo centro", "Topo direita", "Centro esquerda", "Centro centro", "Centro direita", "Baixo esquerda", "Baixo centro", "Baixo direita"])
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
    usa_painel_auxiliar = False
    gerencia_coordenadas_operacao = True

    def __init__(self):
        super().__init__()
        self._dialogo_aberto = False

    def on_activate(self, canvas):
        configurar_texto_canvas(canvas)
        self._dialogo_aberto = False
        QTimer.singleShot(0, lambda: self._abrir_dialogo_e_inserir(canvas))

    def on_deactivate(self, canvas):
        self._dialogo_aberto = False
        return None

    def _abrir_dialogo_e_inserir(self, canvas, forcar: bool = False) -> None:
        agora = monotonic()
        if getattr(canvas, "_inserir_texto_dialogo_ativo", False):
            return
        if not forcar and agora - float(getattr(canvas, "_inserir_texto_ultima_abertura", 0.0) or 0.0) < 0.8:
            return

        self._dialogo_aberto = True
        canvas._inserir_texto_dialogo_ativo = True
        canvas._inserir_texto_ultima_abertura = agora
        try:
            dlg = TextoDialog(canvas, canvas)
            if dlg.exec() == QDialog.Accepted:
                valores = dlg.valores()
                configurar_texto_canvas(canvas, valores["altura_cm"], valores["espaco_linhas_cm"])
                pos = self._centro_canvas(canvas)
                elementos = self._criar_elementos_vetor_texto(canvas, valores, pos)
                if elementos:
                    canvas.cena.elementos.extend(elementos)
                    if hasattr(canvas, "_registrar_historico"):
                        canvas._registrar_historico()
                    if hasattr(canvas, "_emitir_elementos_alterados"):
                        canvas._emitir_elementos_alterados()
                    texto = f"Texto inserido no canvas ({len(elementos)} traços)."
                else:
                    texto = "Inserir Texto: nenhum texto informado."
            else:
                texto = "Inserir Texto cancelado."
        finally:
            self._dialogo_aberto = False
            canvas._inserir_texto_dialogo_ativo = False
            canvas._inserir_texto_ultima_abertura = monotonic()

        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()

    def _centro_canvas(self, canvas) -> QPointF:
        try:
            return canvas._tela_para_cena(QPointF(float(canvas.width()) / 2.0, float(canvas.height()) / 2.0))
        except Exception:
            return QPointF(0.0, 0.0)

    def _texto_normalizado(self, texto: str) -> str:
        return str(texto or "").translate(_ACENTOS).upper()

    def _cor_atual_para_texto(self, canvas) -> str:
        candidatos: list[object] = []
        janela = None
        try:
            janela = canvas.window()
        except Exception:
            janela = None

        if janela is not None:
            estilo_janela = getattr(janela, "_estilo_desenho_atual", None)
            if isinstance(estilo_janela, dict):
                candidatos.append(estilo_janela.get("cor"))
            try:
                for widget in janela.findChildren(QWidget):
                    if widget.__class__.__name__ == "ColorControlWidget" and hasattr(widget, "valor"):
                        valor = widget.valor()
                        if isinstance(valor, dict):
                            candidatos.append(valor.get("cor"))
            except Exception:
                pass

        candidatos.append(getattr(canvas, "_linha_cor", None))
        cores_canvas = getattr(canvas, "_cores_canvas", None)
        if isinstance(cores_canvas, dict):
            candidatos.append(cores_canvas.get("desenho"))

        for valor in candidatos:
            cor = QColor(str(valor or ""))
            if cor.isValid():
                return cor.name()
        return "#ffffff"

    def _criar_elementos_vetor_texto(self, canvas, valores: dict, pos: QPointF) -> list[dict]:
        texto = self._texto_normalizado(str(valores.get("texto") or "").strip("\n"))
        if not texto.strip():
            return []
        cor = self._cor_atual_para_texto(canvas)
        try:
            canvas._linha_cor = cor
        except Exception:
            pass
        altura_cm = max(0.2, float(valores.get("altura_cm", ALTURA_TEXTO_PADRAO_CM) or ALTURA_TEXTO_PADRAO_CM))
        espaco_cm = max(0.2, float(valores.get("espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM) or ESPACO_LINHAS_PADRAO_CM))
        cel = altura_cm / 7.0
        avanco = cel * 6.0
        espessura = max(0.04, cel * 0.22)
        x0 = float(pos.x())
        y0 = float(pos.y())
        elementos: list[dict] = []
        for linha_idx, linha in enumerate(texto.splitlines() or [texto]):
            x = x0
            y = y0 + (linha_idx * espaco_cm)
            for ch in linha:
                if ch == " ":
                    x += avanco
                    continue
                bitmap = _BITMAP_5X7.get(ch, _BITMAP_5X7["?"])
                for row, bits in enumerate(bitmap):
                    for col, bit in enumerate(bits):
                        if bit != "1":
                            continue
                        px = x + (col * cel)
                        py = y + (row * cel)
                        elementos.append({
                            "tipo": "polyline",
                            "pontos": [(px, py), (px + cel * 0.82, py), (px + cel * 0.82, py + cel * 0.82), (px, py + cel * 0.82), (px, py)],
                            "cor": cor,
                            "espessura": espessura,
                            "estilo": "solid",
                            "amplitude": 1.0,
                            "texto_vetor": True,
                        })
                x += avanco
        return elementos

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        self._abrir_dialogo_e_inserir(canvas, forcar=True)
        event.accept()
        return True
