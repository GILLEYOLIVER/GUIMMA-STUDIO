from __future__ import annotations

from math import atan2, degrees

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
        self._angulo_info: tuple[QPointF, QPointF, QPointF, float] | None = None

    def on_activate(self, canvas):
        self._arrastando_ponto_poly = None
        self._hover_ponto_poly = None
        self._guia_ponto_poly = None
        self._angulo_info = None
        self.set_status("Selecione os pontos, arraste um ponto para iniciar a mover.")

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
            self._atualizar_info_angulo(canvas, idx, p_idx, pos)
        elif canvas._arrastando_alca_curva is not None:
            idx, chave = canvas._arrastando_alca_curva
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                if el.get("tipo") == "bezier_quadratica":
                    el[chave] = (pos.x(), pos.y())
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        alterou = False
        if self._arrastando_ponto_poly is not None:
            self._arrastando_ponto_poly = None
            self._guia_ponto_poly = None
            self._angulo_info = None
            alterou = True
        if canvas._arrastando_alca_curva is not None:
            canvas._arrastando_alca_curva = None
            alterou = True
        if alterou:
            canvas._registrar_historico()
            canvas.update()
            event.accept()
            return True
        return False

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_guia(canvas, painter)
        self._desenhar_hover(canvas, painter)
        self._desenhar_angulo(canvas, painter)

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

    def _atualizar_info_angulo(self, canvas, idx: int, p_idx: int, atual: QPointF):
        self._angulo_info = None
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pts) < 3:
            return
        fechado = canvas._dist(pts[0], pts[-1]) <= 1e-6
        if fechado and p_idx == len(pts) - 1:
            p_idx = 0
        prev_idx = p_idx - 1
        next_idx = p_idx + 1
        if fechado:
            if prev_idx < 0:
                prev_idx = len(pts) - 2
            if next_idx >= len(pts) - 1:
                next_idx = 1
        if not (0 <= prev_idx < len(pts)) or not (0 <= next_idx < len(pts)):
            return
        p_prev = pts[prev_idx]
        p_next = pts[next_idx]
        ang = self._angulo_interno(p_prev, atual, p_next)
        self._angulo_info = (atual, p_prev, p_next, ang)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(f"Ângulo: {ang:.0f}°")

    def _angulo_interno(self, a: QPointF, c: QPointF, b: QPointF) -> float:
        v1x, v1y = a.x() - c.x(), a.y() - c.y()
        v2x, v2y = b.x() - c.x(), b.y() - c.y()
        ang1 = atan2(v1y, v1x)
        ang2 = atan2(v2y, v2x)
        deg = abs(degrees(ang2 - ang1))
        while deg > 360.0:
            deg -= 360.0
        if deg > 180.0:
            deg = 360.0 - deg
        return max(0.0, min(360.0, deg))

    def _desenhar_angulo(self, canvas, painter):
        if self._angulo_info is None:
            return
        centro, p1, p2, ang = self._angulo_info
        c_tela = canvas._cena_para_tela(centro)
        a_tela = canvas._cena_para_tela(p1)
        b_tela = canvas._cena_para_tela(p2)
        raio = 44
        painter.setPen(QPen(QColor("#ff2bd6"), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(c_tela.x() - raio), int(c_tela.y() - raio), raio * 2, raio * 2)
        painter.drawLine(c_tela, a_tela)
        painter.drawLine(c_tela, b_tela)
        painter.drawText(int(c_tela.x() + 8), int(c_tela.y() - 8), f"{ang:.0f}°")
