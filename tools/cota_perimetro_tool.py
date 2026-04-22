from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.medicao_utils import mensagem_status, selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "cota_perimetro"
    nome = "Cota Perimetro"
    descricao_painel = "Clique em um segmento para obter cota e perímetro."

    def __init__(self):
        super().__init__()
        self._destaque: dict | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._destaque = None
        texto = "Cota perímetro: clique em uma linha/curva para medir."
        self.set_status(texto)
        mensagem_status(canvas, texto)

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if info is None:
            texto = "Nenhum segmento encontrado para cota de perímetro."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            event.accept()
            return True
        self._destaque = info
        seg = canvas.formatar_valor_unidade(info["segmento_comprimento"])
        per = canvas.formatar_valor_unidade(info["perimetro_total"])
        unidade = getattr(canvas, "_unidade_sigla", "cm")
        texto = f"Cota P: {seg} ({unidade}) | Perímetro total: {per} ({unidade})"
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if not self._destaque:
            return
        a = self._destaque["segmento_inicio"]
        b = self._destaque["segmento_fim"]
        canvas._desenhar_segmento(painter, a, b, cor="#ff1c1c", espessura=2.0)
        meio = canvas._cena_para_tela(QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0))
        txt = canvas.formatar_valor_unidade(self._destaque["segmento_comprimento"])
        painter.setPen(QPen(QColor("#f2f200"), 1.0))
        painter.drawText(int(meio.x() + 6), int(meio.y() - 6), txt)
