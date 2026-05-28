from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPen

from tools.medicao_utils import mensagem_status
from tools.texto_config import aplicar_fonte_texto, cor_texto, configurar_texto_canvas
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "distancia"
    nome = "Distancia"
    descricao_painel = "Clique em 2 pontos para medir distância."

    def __init__(self):
        super().__init__()
        self._p0: QPointF | None = None
        self._p1: QPointF | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        configurar_texto_canvas(canvas)
        self._p0 = None
        self._p1 = None
        txt = "Distância: clique no ponto inicial."
        self.set_status(txt)
        mensagem_status(canvas, txt)

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        if self._p0 is None:
            self._p0 = pos
            self._p1 = None
            txt = "Distância: clique no ponto final."
            self.set_status(txt)
            mensagem_status(canvas, txt)
            canvas.update()
            event.accept()
            return True
        self._p1 = pos
        d = sqrt((self._p1.x() - self._p0.x()) ** 2 + (self._p1.y() - self._p0.y()) ** 2)
        txt = f"Distância: {canvas.formatar_distancia(d) if hasattr(canvas, 'formatar_distancia') else canvas.formatar_valor_unidade(d)}"
        self.set_status(txt)
        mensagem_status(canvas, txt)
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._p0 is None:
            return False
        self._p1 = canvas._ponto_com_snap(event.position())
        d = sqrt((self._p1.x() - self._p0.x()) ** 2 + (self._p1.y() - self._p0.y()) ** 2)
        txt = f"Distância (prévia): {canvas.formatar_distancia(d) if hasattr(canvas, 'formatar_distancia') else canvas.formatar_valor_unidade(d)}"
        self.set_status(txt)
        mensagem_status(canvas, txt)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._p0 is None or self._p1 is None:
            return
        cor = cor_texto(canvas)
        canvas._desenhar_segmento(painter, self._p0, self._p1, cor=cor.name(), espessura=1.8)
        meio = canvas._cena_para_tela(QPointF((self._p0.x() + self._p1.x()) / 2.0, (self._p0.y() + self._p1.y()) / 2.0))
        d = sqrt((self._p1.x() - self._p0.x()) ** 2 + (self._p1.y() - self._p0.y()) ** 2)
        txt = canvas.formatar_distancia(d) if hasattr(canvas, "formatar_distancia") else canvas.formatar_valor_unidade(d)
        aplicar_fonte_texto(painter, canvas, negrito=True)
        painter.setPen(QPen(cor, 1.0))
        painter.drawText(int(meio.x() + 8), int(meio.y() - 8), txt)
