from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPen
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
from tools.texto_config import (
    ALTURA_TEXTO_PADRAO_CM,
    ESPACO_LINHAS_PADRAO_CM,
    aplicar_fonte_texto,
    configurar_texto_canvas,
    cor_texto,
    espaco_linhas_cm,
)
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
    usa_painel_auxiliar = False
    gerencia_coordenadas_operacao = True

    def __init__(self):
        super().__init__()
        self._dialogo_aberto = False

    def on_activate(self, canvas):
        # Não chama super(): assim não abre o painel lateral da FerramentaBase.
        configurar_texto_canvas(canvas)
        aplicar_patch_canvas_textos(canvas)
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
                elemento = self._criar_elemento_texto(canvas, valores, self._centro_canvas(canvas))
                if elemento is not None:
                    canvas.cena.elementos.append(elemento)
                    if hasattr(canvas, "_registrar_historico"):
                        canvas._registrar_historico()
                    if hasattr(canvas, "_emitir_elementos_alterados"):
                        canvas._emitir_elementos_alterados()
                    texto = "Texto inserido no centro visível do canvas."
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

    def _criar_elemento_texto(self, canvas, valores: dict, pos: QPointF) -> dict | None:
        texto = str(valores.get("texto") or "").strip("\n")
        if not texto.strip():
            return None
        cor = getattr(canvas, "_linha_cor", "#ffffff")
        return {
            "tipo": "texto",
            "texto": texto,
            "posicao": (float(pos.x()), float(pos.y())),
            "ponto": (float(pos.x()), float(pos.y())),
            "origem": (float(pos.x()), float(pos.y())),
            "angulo": float(valores.get("angulo", 0.0) or 0.0),
            "texto_altura_cm": float(valores.get("altura_cm", ALTURA_TEXTO_PADRAO_CM) or ALTURA_TEXTO_PADRAO_CM),
            "texto_espaco_linhas_cm": float(valores.get("espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM) or ESPACO_LINHAS_PADRAO_CM),
            "referencia": str(valores.get("referencia") or "Topo esquerda"),
            "justificacao": str(valores.get("justificacao") or "Esquerda"),
            "cor": str(cor),
            "cor_texto": str(cor),
        }

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        self._abrir_dialogo_e_inserir(canvas, forcar=True)
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        return None

    def _desenhar_texto_preview(self, canvas, painter, elemento: dict) -> None:
        # Mantido apenas para compatibilidade caso algum fluxo antigo chame preview.
        texto = str(elemento.get("texto") or "").strip("\n")
        if not texto:
            return
        try:
            pos = QPointF(float(elemento["posicao"][0]), float(elemento["posicao"][1]))
            tela = canvas._cena_para_tela(pos)
        except Exception:
            return
        cor = cor_texto(canvas, elemento)
        linhas = texto.splitlines() or [texto]
        painter.save()
        try:
            aplicar_fonte_texto(painter, canvas, elemento, negrito=False)
            metrics = painter.fontMetrics()
            line_h = max(float(metrics.height()), espaco_linhas_cm(canvas, elemento) * max(float(getattr(canvas, "zoom", 1.0)), 0.01))
            largura = max(metrics.horizontalAdvance(l) for l in linhas) + 10
            altura = line_h * len(linhas) + 8
            rect = QRectF(tela.x(), tela.y(), largura, altura)
            painter.setPen(QPen(QColor("#2da8ff"), 1.0, Qt.DashLine))
            painter.drawRect(rect)
            painter.setPen(QPen(cor, 1.0))
            for i, linha in enumerate(linhas):
                painter.drawText(QRectF(rect.x() + 4, rect.y() + 4 + i * line_h, rect.width(), line_h), Qt.AlignLeft | Qt.AlignVCenter, linha)
        finally:
            painter.restore()
