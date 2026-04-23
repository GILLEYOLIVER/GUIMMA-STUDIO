from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt

from tools.medicao_utils import mensagem_status
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "conferir_multiplos"
    nome = "Conferir Multiplos"
    descricao_painel = "Clique em múltiplos pontos para somar distâncias (RMB finaliza)."

    def __init__(self):
        super().__init__()
        self._pontos: list[QPointF] = []

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._pontos = []
        txt = "Conferir múltiplos: clique em pontos para medir sequência. RMB finaliza."
        self.set_status(txt)
        mensagem_status(canvas, txt)

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            total = self._total()
            txt = f"Conferência múltipla finalizada. Total: {canvas.formatar_valor_unidade(total)} ({getattr(canvas, '_unidade_sigla', 'cm')})"
            self.set_status(txt)
            mensagem_status(canvas, txt)
            self._pontos = []
            canvas.update()
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        self._pontos.append(canvas._ponto_com_snap(event.position()))
        total = self._total()
        txt = f"Conferência múltipla: {canvas.formatar_valor_unidade(total)} ({getattr(canvas, '_unidade_sigla', 'cm')})"
        self.set_status(txt)
        mensagem_status(canvas, txt)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if len(self._pontos) < 2:
            return
        for a, b in zip(self._pontos, self._pontos[1:]):
            canvas._desenhar_segmento(painter, a, b, cor="#74ff00", espessura=1.2)

    def _total(self) -> float:
        total = 0.0
        for a, b in zip(self._pontos, self._pontos[1:]):
            total += sqrt((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2)
        return total
