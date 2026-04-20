from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "editar_pontos_de_curva"
    nome = "Editar Pontos de Curva"
    descricao_painel = "Edite pontos de controle Bézier (início, controle e fim)."

    def __init__(self):
        super().__init__()
        self._arrastando: tuple[int, str] | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._arrastando = None
        self.set_status("Clique em uma alça da curva e arraste para editar.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        alca = self._alca_em_ponto(canvas, pos)
        if alca is None:
            return False
        self._arrastando = alca
        canvas._selecionados = {alca[0]}
        self.set_status(f"Editando alça {alca[1]} da curva.")
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._arrastando is None:
            return False
        idx, chave = self._arrastando
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return False
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "bezier_quadratica":
            return False
        pos = canvas._ponto_com_snap(event.position())
        el[chave] = (pos.x(), pos.y())
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton or self._arrastando is None:
            return False
        self._arrastando = None
        canvas._registrar_historico()
        self.set_status("Curva atualizada.")
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        tolerancia = 4.5
        for idx, el in enumerate(canvas.cena.elementos):
            if el.get("tipo") != "bezier_quadratica":
                continue
            p0 = QPointF(*el["p0"])
            p1 = QPointF(*el["p1"])
            p2 = QPointF(*el["p2"])
            canvas._desenhar_segmento(painter, p0, p1, tracejado=True, cor="#ffc857", espessura=1.0)
            canvas._desenhar_segmento(painter, p1, p2, tracejado=True, cor="#ffc857", espessura=1.0)
            for chave, ponto, cor in (("p0", p0, "#4dd2ff"), ("p1", p1, "#ffd166"), ("p2", p2, "#4dd2ff")):
                pt = canvas._cena_para_tela(ponto)
                painter.setPen(QPen(QColor(cor), 1.4))
                painter.setBrush(QColor(cor))
                raio = tolerancia + (1.8 if self._arrastando == (idx, chave) else 0.0)
                painter.drawEllipse(pt, raio, raio)

    def _alca_em_ponto(self, canvas, pos: QPointF) -> tuple[int, str] | None:
        tolerancia = 10.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, str] | None = None
        melhor_d = tolerancia
        for idx, el in enumerate(canvas.cena.elementos):
            if el.get("tipo") != "bezier_quadratica":
                continue
            for chave in ("p0", "p1", "p2"):
                p = QPointF(*el[chave])
                d = canvas._dist(p, pos)
                if d <= melhor_d:
                    melhor_d = d
                    melhor = (idx, chave)
        return melhor
