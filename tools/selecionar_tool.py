from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "selecionar"
    nome = "Selecionar"
    descricao_painel = "Selecione elementos com clique, caixa de seleção e ciclo com botão direito."

    def __init__(self):
        super().__init__()
        self._inicio_caixa: QPointF | None = None
        self._fim_caixa: QPointF | None = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto: QPointF | None = None
        self._movido = False
        self._hover_idx: int | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._inicio_caixa = None
        self._fim_caixa = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto = None
        self._movido = False
        self._hover_idx = None
        self.set_status("Clique para selecionar. Arraste para seleção por área. RMB cicla sobrepostos.")

    def on_mouse_press(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if event.button() == Qt.RightButton:
            if canvas._selecionar_proximo_em_ponto(pos):
                self.set_status("Elemento alternado com botão direito.")
                event.accept()
                return True
            if canvas._snap_resultado and canvas._snap_resultado.elemento_idx is not None:
                idx_snap = int(canvas._snap_resultado.elemento_idx)
                if 0 <= idx_snap < len(canvas.cena.elementos):
                    canvas._selecionados = {idx_snap}
                    self.set_status("Elemento alternado via snap.")
                    canvas.update()
                    event.accept()
                    return True
            return False
        if event.button() != Qt.LeftButton:
            return False

        indices = canvas._indices_elementos_em_ponto(pos)
        if not indices and canvas._snap_resultado and canvas._snap_resultado.elemento_idx is not None:
            idx_snap = int(canvas._snap_resultado.elemento_idx)
            if 0 <= idx_snap < len(canvas.cena.elementos):
                indices = [idx_snap]
        if indices:
            selecionado = indices[0]
            if event.modifiers() & Qt.ShiftModifier:
                if selecionado in canvas._selecionados:
                    canvas._selecionados.remove(selecionado)
                else:
                    canvas._selecionados.add(selecionado)
                self._arrastando_selecao = False
                self._ultimo_ponto_arrasto = None
            else:
                canvas._selecionados = {selecionado}
                # Inicia arraste já no primeiro clique pressionado sobre o elemento
                # para evitar exigir um segundo clique para mover.
                self._arrastando_selecao = True
                self._ultimo_ponto_arrasto = pos
                self._movido = False
            self._inicio_caixa = None
            self._fim_caixa = None
            self.set_status(f"{len(canvas._selecionados)} elemento(s) selecionado(s).")
            canvas.update()
            event.accept()
            return True

        if not (event.modifiers() & Qt.ShiftModifier):
            canvas._selecionados.clear()
        self._inicio_caixa = pos
        self._fim_caixa = pos
        self.set_status("Arraste para selecionar por área.")
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._hover_idx = (canvas._indices_elementos_em_ponto(pos) or [None])[0]
        if self._arrastando_selecao and self._ultimo_ponto_arrasto is not None:
            dx = pos.x() - self._ultimo_ponto_arrasto.x()
            dy = pos.y() - self._ultimo_ponto_arrasto.y()
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                self._mover_selecionados(canvas, dx, dy)
                self._ultimo_ponto_arrasto = pos
                self._movido = True
            snap_info = f" | Snap: {canvas._snap_resultado.tipo}" if canvas._snap_resultado else ""
            self.set_status(f"Movendo seleção ({len(canvas._selecionados)} elemento(s)){snap_info}")
            canvas.update()
            event.accept()
            return True
        if self._inicio_caixa is None:
            if canvas.lbl_status:
                snap_info = f" | Snap: {canvas._snap_resultado.tipo}" if canvas._snap_resultado else ""
                canvas.lbl_status.setText(f"Selecionar | X {pos.x():.2f} Y {pos.y():.2f}{snap_info}")
                self.set_status(f"Cursor X {pos.x():.2f} Y {pos.y():.2f}{snap_info}")
            canvas.update()
            return True
        self._fim_caixa = pos
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() == Qt.LeftButton and self._arrastando_selecao:
            self._arrastando_selecao = False
            self._ultimo_ponto_arrasto = None
            if self._movido:
                canvas._registrar_historico()
                self.set_status(f"Movimento concluído ({len(canvas._selecionados)} elemento(s)).")
            self._movido = False
            canvas.update()
            event.accept()
            return True
        if event.button() != Qt.LeftButton or self._inicio_caixa is None or self._fim_caixa is None:
            return False
        x1 = min(self._inicio_caixa.x(), self._fim_caixa.x())
        y1 = min(self._inicio_caixa.y(), self._fim_caixa.y())
        x2 = max(self._inicio_caixa.x(), self._fim_caixa.x())
        y2 = max(self._inicio_caixa.y(), self._fim_caixa.y())

        if sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) > (4.0 / max(canvas.zoom, 0.001)):
            selecionados_area: set[int] = set()
            for idx, el in enumerate(canvas.cena.elementos):
                if el.get("tipo") == "polyline":
                    pontos = [QPointF(float(px), float(py)) for px, py in el.get("pontos", [])]
                elif el.get("tipo") == "bezier_quadratica":
                    p0 = QPointF(*el["p0"])
                    p1 = QPointF(*el["p1"])
                    p2 = QPointF(*el["p2"])
                    pontos = canvas._amostrar_bezier_quadratica(p0, p1, p2, segmentos=24)
                else:
                    pontos = []
                if pontos and all(x1 <= p.x() <= x2 and y1 <= p.y() <= y2 for p in pontos):
                    selecionados_area.add(idx)
            if event.modifiers() & Qt.ShiftModifier:
                canvas._selecionados |= selecionados_area
            else:
                canvas._selecionados = selecionados_area
            self.set_status(f"Seleção por área: {len(canvas._selecionados)} elemento(s).")

        self._inicio_caixa = None
        self._fim_caixa = None
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_realce_elementos(canvas, painter)
        if self._inicio_caixa is None or self._fim_caixa is None:
            return
        p1 = canvas._cena_para_tela(self._inicio_caixa)
        p2 = canvas._cena_para_tela(self._fim_caixa)
        x = min(p1.x(), p2.x())
        y = min(p1.y(), p2.y())
        w = abs(p2.x() - p1.x())
        h = abs(p2.y() - p1.y())
        painter.setPen(QPen(QColor("#33c1ff"), 1, Qt.DashLine))
        painter.setBrush(QColor(40, 160, 255, 40))
        painter.drawRect(int(x), int(y), int(w), int(h))

    def _desenhar_realce_elementos(self, canvas, painter):
        idxs = set(canvas._selecionados)
        if self._hover_idx is not None:
            idxs.add(self._hover_idx)
        for idx in idxs:
            if idx is None or idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            pontos: list[QPointF] = []
            if el.get("tipo") == "polyline":
                pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            elif el.get("tipo") == "bezier_quadratica":
                pontos = [QPointF(*el["p0"]), QPointF(*el["p1"]), QPointF(*el["p2"])]
            if not pontos:
                continue
            margem = 0.5
            min_x = min(p.x() for p in pontos) - margem
            max_x = max(p.x() for p in pontos) + margem
            min_y = min(p.y() for p in pontos) - margem
            max_y = max(p.y() for p in pontos) + margem
            p1 = canvas._cena_para_tela(QPointF(min_x, min_y))
            p2 = canvas._cena_para_tela(QPointF(max_x, max_y))
            x = min(p1.x(), p2.x())
            y = min(p1.y(), p2.y())
            w = abs(p2.x() - p1.x())
            h = abs(p2.y() - p1.y())
            painter.setPen(QPen(QColor("#33c1ff"), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(x), int(y), int(w), int(h))

    def _mover_selecionados(self, canvas, dx: float, dy: float):
        for idx in list(canvas._selecionados):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                el["pontos"] = [(x + dx, y + dy) for x, y in el.get("pontos", [])]
                if "controle_cantos" in el:
                    el["controle_cantos"] = [(x + dx, y + dy) for x, y in el.get("controle_cantos", [])]
                if "controle_auxiliares" in el:
                    el["controle_auxiliares"] = [(x + dx, y + dy) for x, y in el.get("controle_auxiliares", [])]
                if "fio_origem" in el:
                    fx, fy = el.get("fio_origem", (0.0, 0.0))
                    el["fio_origem"] = (float(fx) + dx, float(fy) + dy)
                if "fio_fim" in el:
                    fx, fy = el.get("fio_fim", (0.0, 0.0))
                    el["fio_fim"] = (float(fx) + dx, float(fy) + dy)
            elif el.get("tipo") == "bezier_quadratica":
                for chave in ("p0", "p1", "p2"):
                    x, y = el[chave]
                    el[chave] = (x + dx, y + dy)
