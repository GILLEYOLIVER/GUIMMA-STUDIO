from __future__ import annotations

from copy import deepcopy
from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "cortar"
    nome = "Cortar"
    usa_painel_auxiliar = False
    descricao_painel = "Corta/divide uma polyline no ponto clicado. Em contorno fechado, abre o contorno no corte."

    def __init__(self):
        super().__init__()
        self._hover: tuple[int, int, QPointF] | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover = None
        self._status(canvas, "Cortar: clique sobre uma linha/curva para dividir. Shift mantém os dois lados selecionados.")

    def on_deactivate(self, canvas):
        self._hover = None
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._hover = self._segmento_mais_proximo(canvas, pos)
        canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        alvo = self._segmento_mais_proximo(canvas, pos)
        if alvo is None:
            self._status(canvas, "Cortar: nenhum segmento encontrado no clique.")
            return False
        idx, seg_idx, ponto_corte = alvo
        if not self._cortar_elemento(canvas, idx, seg_idx, ponto_corte, manter_selecionados=bool(event.modifiers() & Qt.ShiftModifier)):
            self._status(canvas, "Corte cancelado para evitar geometria inválida.")
            return False
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._hover is None:
            return
        _idx, _seg, p = self._hover
        painter.save()
        tela = canvas._cena_para_tela(p)
        pen = QPen(QColor("#ffcf00"), 1.4, Qt.SolidLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(tela.x() - 7, tela.y()), QPointF(tela.x() + 7, tela.y()))
        painter.drawLine(QPointF(tela.x(), tela.y() - 7), QPointF(tela.x(), tela.y() + 7))
        painter.restore()

    def _cortar_elemento(self, canvas, idx: int, seg_idx: int, ponto: QPointF, manter_selecionados: bool) -> bool:
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return False
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return False
        pontos = [(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pontos) < 2 or seg_idx < 0 or seg_idx >= len(pontos) - 1:
            return False
        corte = (float(ponto.x()), float(ponto.y()))
        fechado = self._fechado(pontos)
        pontos = self._inserir_corte(pontos, seg_idx, corte)
        corte_idx = seg_idx + 1

        if fechado:
            base = pontos[:-1]
            # Em contorno fechado, o corte transforma em uma polyline aberta começando e terminando no ponto de corte.
            nova_seq = [corte] + base[corte_idx + 1:] + base[:corte_idx + 1]
            novo = deepcopy(el)
            novo["pontos"] = nova_seq
            novo.setdefault("metadados", {})["aberto_por_corte"] = True
            if novo.get("molde") and self._fechado(nova_seq):
                self._reconstruir_controles_molde(novo)
            else:
                novo["molde"] = False if novo.get("molde") else novo.get("molde", False)
                self._limpar_controles_invalidos(novo)
            canvas.cena.elementos[idx] = novo
            canvas._selecionados = {idx}
            canvas._registrar_historico()
            canvas.update()
            self._status(canvas, "Contorno fechado reposicionado no ponto de corte.")
            return True

        parte_a = pontos[: corte_idx + 1]
        parte_b = pontos[corte_idx:]
        if len(parte_a) < 2 or len(parte_b) < 2:
            return False
        el_a = deepcopy(el)
        el_b = deepcopy(el)
        el_a["pontos"] = parte_a
        el_b["pontos"] = parte_b
        el_a["id"] = str(uuid4())
        el_b["id"] = str(uuid4())
        el_a["molde"] = False if el.get("molde") else el.get("molde", False)
        el_b["molde"] = False if el.get("molde") else el.get("molde", False)
        el_a.setdefault("metadados", {})["origem_corte"] = idx
        el_b.setdefault("metadados", {})["origem_corte"] = idx
        self._limpar_controles_invalidos(el_a)
        self._limpar_controles_invalidos(el_b)
        canvas.cena.elementos[idx] = el_a
        canvas.cena.elementos.insert(idx + 1, el_b)
        canvas._selecionados = {idx, idx + 1} if manter_selecionados else {idx + 1}
        canvas._registrar_historico()
        canvas.update()
        self._status(canvas, "Elemento cortado em duas partes.")
        return True

    def _segmento_mais_proximo(self, canvas, pos: QPointF) -> tuple[int, int, QPointF] | None:
        tolerancia = 10.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor = None
        candidatos = sorted(getattr(canvas, "_selecionados", set()) or []) or list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            for seg_idx, (a, b) in enumerate(zip(pts, pts[1:])):
                proj, dist = self._projetar_ponto_segmento(a, b, pos)
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, seg_idx, proj)
        if melhor is None:
            return None
        return melhor[1], melhor[2], melhor[3]

    @staticmethod
    def _projetar_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> tuple[QPointF, float]:
        abx, aby = b.x() - a.x(), b.y() - a.y()
        apx, apy = p.x() - a.x(), p.y() - a.y()
        den = abx * abx + aby * aby
        if den <= 1e-9:
            proj = QPointF(a)
        else:
            t = max(0.0, min(1.0, (apx * abx + apy * aby) / den))
            proj = QPointF(a.x() + abx * t, a.y() + aby * t)
        return proj, sqrt((proj.x() - p.x()) ** 2 + (proj.y() - p.y()) ** 2)

    @staticmethod
    def _inserir_corte(pontos: list[tuple[float, float]], seg_idx: int, corte: tuple[float, float]) -> list[tuple[float, float]]:
        out = list(pontos)
        if seg_idx + 1 < len(out) and Ferramenta._dist_tuple(out[seg_idx + 1], corte) <= 1e-7:
            return out
        if Ferramenta._dist_tuple(out[seg_idx], corte) <= 1e-7:
            return out
        out.insert(seg_idx + 1, corte)
        return out

    @staticmethod
    def _fechado(pontos: list[tuple[float, float]]) -> bool:
        return len(pontos) >= 3 and Ferramenta._dist_tuple(pontos[0], pontos[-1]) <= 1e-7

    @staticmethod
    def _dist_tuple(a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2)

    @staticmethod
    def _limpar_controles_invalidos(el: dict) -> None:
        # Após cortar, controles de molde/costura antigos podem ficar incoerentes.
        for chave in ("controle_cantos", "controle_auxiliares", "pontos_controle_principais", "pontos_auxiliares", "segment_ids", "node_ids"):
            if chave in el:
                el.pop(chave, None)
        if el.get("molde"):
            el["molde"] = False

    @staticmethod
    def _reconstruir_controles_molde(el: dict) -> None:
        pontos = [(float(x), float(y)) for x, y in el.get("pontos", [])]
        base = pontos[:-1] if len(pontos) >= 2 and Ferramenta._dist_tuple(pontos[0], pontos[-1]) <= 1e-7 else pontos
        controles = base[:]
        el["controle_cantos"] = controles
        el["controle_auxiliares"] = []
        el["pontos_controle_principais"] = [{"x": x, "y": y} for x, y in controles]
        el["pontos_auxiliares"] = []
        el["mostrar_controles"] = True
        el.setdefault("metadados", {})["controles_recalculados_por"] = "cortar"

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
