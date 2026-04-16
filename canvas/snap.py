from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from PySide6.QtCore import QPointF

from canvas.cena import CenaDocumento


@dataclass(slots=True)
class SnapResult:
    ponto: QPointF
    tipo: str
    distancia: float
    elemento_idx: int | None = None


class SnapManager:
    """Calcula pontos de captura (snap) para o cursor no canvas."""

    def __init__(self, tolerancia_px: float = 10.0):
        self.tolerancia_px = tolerancia_px

    def calcular(self, cena: CenaDocumento, cursor: QPointF, zoom: float) -> SnapResult | None:
        tolerancia_cena = self.tolerancia_px / max(zoom, 0.001)
        candidatos: list[SnapResult] = []

        for idx, elemento in enumerate(cena.elementos):
            tipo = elemento.get("tipo")
            if tipo == "polyline":
                self._candidatos_polyline(idx, elemento, cursor, candidatos)
            elif tipo in {"circle", "esfera"}:
                self._candidatos_circulo(idx, elemento, cursor, candidatos)

        if not candidatos:
            return None
        candidatos_validos = [c for c in candidatos if c.distancia <= tolerancia_cena]
        if not candidatos_validos:
            return None
        return min(candidatos_validos, key=lambda c: (self._prioridade(c.tipo), c.distancia))

    def _candidatos_polyline(self, idx: int, elemento: dict, cursor: QPointF, candidatos: list[SnapResult]):
        pontos = [QPointF(float(x), float(y)) for x, y in elemento.get("pontos", [])]
        if not pontos:
            return

        for ponto in pontos:
            candidatos.append(SnapResult(ponto=ponto, tipo="nó", distancia=self._dist(cursor, ponto), elemento_idx=idx))

        for inicio, fim in zip(pontos, pontos[1:]):
            meio = QPointF((inicio.x() + fim.x()) / 2.0, (inicio.y() + fim.y()) / 2.0)
            candidatos.append(SnapResult(ponto=meio, tipo="ponto médio", distancia=self._dist(cursor, meio), elemento_idx=idx))

            proj = self._projetar_em_segmento(cursor, inicio, fim)
            candidatos.append(SnapResult(ponto=proj, tipo="borda", distancia=self._dist(cursor, proj), elemento_idx=idx))

    def _candidatos_circulo(self, idx: int, elemento: dict, cursor: QPointF, candidatos: list[SnapResult]):
        centro = elemento.get("centro")
        if not isinstance(centro, (list, tuple)) or len(centro) != 2:
            return
        ponto = QPointF(float(centro[0]), float(centro[1]))
        candidatos.append(SnapResult(ponto=ponto, tipo="centro", distancia=self._dist(cursor, ponto), elemento_idx=idx))

    def _projetar_em_segmento(self, ponto: QPointF, inicio: QPointF, fim: QPointF) -> QPointF:
        vx = fim.x() - inicio.x()
        vy = fim.y() - inicio.y()
        denom = vx * vx + vy * vy
        if denom <= 0.000001:
            return QPointF(inicio)
        t = ((ponto.x() - inicio.x()) * vx + (ponto.y() - inicio.y()) * vy) / denom
        t = max(0.0, min(1.0, t))
        return QPointF(inicio.x() + t * vx, inicio.y() + t * vy)

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    def _prioridade(self, tipo: str) -> int:
        if tipo == "nó":
            return 0
        if tipo == "centro":
            return 1
        if tipo == "ponto médio":
            return 2
        if tipo == "borda":
            return 3
        return 9
