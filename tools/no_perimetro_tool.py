from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from tools.medicao_utils import mensagem_status, selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "no_perimetro"
    nome = "No Perimetro"
    descricao_painel = "Clique no contorno para exibir o perímetro na barra."

    def __init__(self):
        super().__init__()
        self._idx_destaque: int | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._idx_destaque = None
        texto = "Perímetro: clique em uma linha/curva para calcular o perímetro."
        self.set_status(texto)
        mensagem_status(canvas, texto)

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if info is None:
            self._idx_destaque = None
            texto = "Nenhum contorno encontrado para perímetro."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            canvas.update()
            event.accept()
            return True
        self._idx_destaque = int(info["elemento_idx"])
        per = canvas.formatar_valor_unidade(info["perimetro_total"])
        unidade = getattr(canvas, "_unidade_sigla", "cm")
        texto = f"Perímetro P: {per} ({unidade})"
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        idx = self._idx_destaque
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") == "polyline":
            pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            for a, b in zip(pts, pts[1:]):
                canvas._desenhar_segmento(painter, a, b, cor="#2f8bff", espessura=2.0)
        elif el.get("tipo") == "bezier_quadratica":
            canvas._desenhar_bezier_quadratica(
                painter,
                QPointF(*el.get("p0", (0.0, 0.0))),
                QPointF(*el.get("p1", (0.0, 0.0))),
                QPointF(*el.get("p2", (0.0, 0.0))),
                cor="#2f8bff",
                espessura=2.0,
                estilo="solid",
                amplitude=1.0,
                destacar_controles=False,
            )
