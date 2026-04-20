from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "manipular_pontos"
    nome = "Manipular Pontos"

    def __init__(self):
        self._arrastando_ponto_poly: tuple[int, int] | None = None
        self._hover_ponto_poly: tuple[int, int] | None = None
        self._guia_ponto_poly: tuple[QPointF, QPointF | None, QPointF | None] | None = None

    def on_activate(self, canvas):
        self._arrastando_ponto_poly = None
        self._hover_ponto_poly = None
        self._guia_ponto_poly = None

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        alca = canvas._alca_curva_em_ponto(pos)
        if alca is not None:
            canvas._arrastando_alca_curva = alca
            event.accept()
            return True
        ponto_poly = self._ponto_polilinha_em_ponto(canvas, pos)
        if ponto_poly is None:
            return False
        idx, p_idx = ponto_poly
        self._arrastando_ponto_poly = (idx, p_idx)
        self._hover_ponto_poly = (idx, p_idx)
        self._guia_ponto_poly = self._gerar_guia(canvas, idx, p_idx)
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._hover_ponto_poly = self._ponto_polilinha_em_ponto(canvas, pos)
        if self._arrastando_ponto_poly is not None:
            idx, p_idx = self._arrastando_ponto_poly
            self._atualizar_ponto(canvas, idx, p_idx, pos)
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton or self._arrastando_ponto_poly is None:
            return False
        self._arrastando_ponto_poly = None
        self._guia_ponto_poly = None
        canvas._registrar_historico()
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_guia(canvas, painter)
        self._desenhar_hover(canvas, painter)

    def _ponto_polilinha_em_ponto(self, canvas, ponto: QPointF) -> tuple[int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        candidatos = sorted(canvas._selecionados) if canvas._selecionados else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            for p_idx, (x, y) in enumerate(el.get("pontos", [])):
                if canvas._dist(QPointF(float(x), float(y)), ponto) <= tolerancia:
                    return idx, p_idx
        return None

    def _gerar_guia(self, canvas, idx: int, p_idx: int):
        el = canvas.cena.elementos[idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        anterior = pontos[p_idx - 1] if p_idx > 0 else None
        proximo = pontos[p_idx + 1] if p_idx + 1 < len(pontos) else None
        return QPointF(pontos[p_idx]), anterior, proximo

    def _atualizar_ponto(self, canvas, idx: int, p_idx: int, pos: QPointF):
        el = canvas.cena.elementos[idx]
        pontos = list(el.get("pontos", []))
        pontos[p_idx] = (pos.x(), pos.y())
        if len(pontos) >= 2:
            p0 = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            pn = QPointF(float(pontos[-1][0]), float(pontos[-1][1]))
            if canvas._dist(p0, pn) <= 0.0001:
                if p_idx == 0:
                    pontos[-1] = pontos[0]
                elif p_idx == len(pontos) - 1:
                    pontos[0] = pontos[-1]
        el["pontos"] = pontos
        if el.get("molde") and el.get("controle_cantos"):
            atualizados = []
            for cx, cy in el.get("controle_cantos", []):
                cp = QPointF(float(cx), float(cy))
                if canvas._dist(cp, pos) <= (10.0 / max(canvas.zoom, 0.001)):
                    atualizados.append((pos.x(), pos.y()))
                else:
                    atualizados.append((float(cx), float(cy)))
            el["controle_cantos"] = atualizados

    def _desenhar_guia(self, canvas, painter):
        if self._guia_ponto_poly is None or self._arrastando_ponto_poly is None:
            return
        origem, anterior, proximo = self._guia_ponto_poly
        if anterior is not None:
            canvas._desenhar_segmento(painter, anterior, origem, tracejado=True, cor="#ff48ff", espessura=1.0)
        if proximo is not None:
            canvas._desenhar_segmento(painter, origem, proximo, tracejado=True, cor="#ff48ff", espessura=1.0)

    def _desenhar_hover(self, canvas, painter):
        if self._hover_ponto_poly is None:
            return
        idx, p_idx = self._hover_ponto_poly
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        pontos = el.get("pontos", [])
        if p_idx < 0 or p_idx >= len(pontos):
            return
        x, y = pontos[p_idx]
        pt = canvas._cena_para_tela(QPointF(float(x), float(y)))
        painter.setPen(QPen(QColor("#ff2bd6"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(pt.x() - 9), int(pt.y() - 9), 18, 18)
