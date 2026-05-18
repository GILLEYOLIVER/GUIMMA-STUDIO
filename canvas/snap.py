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

    def __init__(self, tolerancia_px: float = 10.0, snap_grade: bool = False, passo_grade: float = 0.1):
        self.tolerancia_px = tolerancia_px
        self.snap_grade = snap_grade
        self.passo_grade = max(0.001, passo_grade)

    def calcular(self, cena: CenaDocumento, cursor: QPointF, zoom: float, tolerancia_px: float | None = None) -> SnapResult | None:
        candidatos_validos = self.calcular_candidatos(cena, cursor, zoom, tolerancia_px=tolerancia_px)
        if not candidatos_validos:
            return None
        return candidatos_validos[0]

    def calcular_candidatos(
        self,
        cena: CenaDocumento,
        cursor: QPointF,
        zoom: float,
        tolerancia_px: float | None = None,
    ) -> list[SnapResult]:
        tolerancia_efetiva = self.tolerancia_px if tolerancia_px is None else tolerancia_px
        tolerancia_cena = tolerancia_efetiva / max(zoom, 0.001)
        candidatos: list[SnapResult] = []

        segmentos: list[tuple[int, QPointF, QPointF]] = []
        for idx, elemento in enumerate(cena.elementos):
            tipo = elemento.get("tipo")
            if not self._participa_snap(elemento):
                continue
            if tipo == "polyline":
                self._candidatos_polyline(idx, elemento, cursor, tolerancia_cena, candidatos)
                segmentos.extend(self._segmentos_polyline(idx, elemento))
            elif tipo in {"circle", "esfera"}:
                self._candidatos_circulo(idx, elemento, cursor, candidatos)
        self._candidatos_interseccoes(segmentos, cursor, tolerancia_cena, candidatos)
        self._candidato_grade(cursor, tolerancia_cena, candidatos)

        candidatos_validos = [c for c in candidatos if c.distancia <= tolerancia_cena]
        candidatos_validos.sort(key=lambda c: (self._prioridade_elemento(cena, c.elemento_idx), self._prioridade(c.tipo), c.distancia))
        return candidatos_validos

    def _elemento_curva_suave(self, elemento: dict) -> bool:
        tipo_curva = str(elemento.get("tipo_curva") or "").lower()
        return bool(elemento.get("curva_suave") or tipo_curva == "parabola_3p" or tipo_curva.startswith("spline"))

    def _amostrar_curva_suave(self, pontos: list[QPointF], amostras_por_trecho: int = 18) -> list[QPointF]:
        if len(pontos) < 3:
            return [QPointF(p) for p in pontos]
        fechado = len(pontos) > 3 and self._dist(pontos[0], pontos[-1]) <= 1e-6
        pts = [QPointF(p) for p in (pontos[:-1] if fechado else pontos)]
        if len(pts) < 3:
            return [QPointF(p) for p in pontos]
        saida: list[QPointF] = []
        total = len(pts)
        limite = total if fechado else total - 1
        for i in range(limite):
            p0 = pts[(i - 1) % total] if fechado or i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[(i + 1) % total]
            p3 = pts[(i + 2) % total] if fechado or i + 2 < total else p2
            for s in range(amostras_por_trecho):
                t = s / float(amostras_por_trecho)
                t2 = t * t
                t3 = t2 * t
                x = 0.5 * ((2*p1.x()) + (-p0.x()+p2.x())*t + (2*p0.x()-5*p1.x()+4*p2.x()-p3.x())*t2 + (-p0.x()+3*p1.x()-3*p2.x()+p3.x())*t3)
                y = 0.5 * ((2*p1.y()) + (-p0.y()+p2.y())*t + (2*p0.y()-5*p1.y()+4*p2.y()-p3.y())*t2 + (-p0.y()+3*p1.y()-3*p2.y()+p3.y())*t3)
                saida.append(QPointF(x, y))
        if fechado and saida:
            saida.append(QPointF(saida[0]))
        elif pts:
            saida.append(QPointF(pts[-1]))
        return saida

    def _candidato_grade(self, cursor: QPointF, tolerancia_cena: float, candidatos: list[SnapResult]):
        if not self.snap_grade:
            return
        gx = round(cursor.x() / self.passo_grade) * self.passo_grade
        gy = round(cursor.y() / self.passo_grade) * self.passo_grade
        ponto_grade = QPointF(gx, gy)
        distancia = self._dist(cursor, ponto_grade)
        if distancia > (tolerancia_cena * 0.55):
            return
        candidatos.append(SnapResult(ponto=ponto_grade, tipo="grade", distancia=distancia, elemento_idx=None))

    def _candidatos_polyline(
        self,
        idx: int,
        elemento: dict,
        cursor: QPointF,
        tolerancia_cena: float,
        candidatos: list[SnapResult],
    ):
        pontos = [QPointF(float(x), float(y)) for x, y in elemento.get("pontos", [])]
        controles_principais = self._pontos_controle_serializados(elemento.get("controle_cantos", []) or elemento.get("pontos_controle_principais", []))
        controles_auxiliares = self._pontos_controle_serializados(elemento.get("controle_auxiliares", []) or elemento.get("pontos_auxiliares", []))
        pontos_bbox = pontos + controles_principais + controles_auxiliares
        if not pontos_bbox:
            return
        xs = [p.x() for p in pontos_bbox]
        ys = [p.y() for p in pontos_bbox]
        margem = tolerancia_cena * 2.5
        if cursor.x() < min(xs) - margem or cursor.x() > max(xs) + margem or cursor.y() < min(ys) - margem or cursor.y() > max(ys) + margem:
            return

        for ponto in controles_principais:
            candidatos.append(SnapResult(ponto=ponto, tipo="controle principal", distancia=self._dist(cursor, ponto), elemento_idx=idx))
        for ponto in controles_auxiliares:
            candidatos.append(SnapResult(ponto=ponto, tipo="controle auxiliar", distancia=self._dist(cursor, ponto), elemento_idx=idx))
        # Nós reais/controladores: poucos pontos principais da curva.
        for ponto in pontos:
            candidatos.append(SnapResult(ponto=ponto, tipo="nó", distancia=self._dist(cursor, ponto), elemento_idx=idx))

        pontos_borda = self._amostrar_curva_suave(pontos) if self._elemento_curva_suave(elemento) else pontos
        for inicio, fim in zip(pontos_borda, pontos_borda[1:]):
            meio = QPointF((inicio.x() + fim.x()) / 2.0, (inicio.y() + fim.y()) / 2.0)
            candidatos.append(SnapResult(ponto=meio, tipo="ponto médio", distancia=self._dist(cursor, meio), elemento_idx=idx))

            proj = self._projetar_em_segmento(cursor, inicio, fim)
            candidatos.append(SnapResult(ponto=proj, tipo="borda", distancia=self._dist(cursor, proj), elemento_idx=idx))

    def _pontos_controle_serializados(self, origem) -> list[QPointF]:
        pontos: list[QPointF] = []
        if not isinstance(origem, list):
            return pontos
        for item in origem:
            try:
                if isinstance(item, dict):
                    pontos.append(QPointF(float(item["x"]), float(item["y"])))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    pontos.append(QPointF(float(item[0]), float(item[1])))
            except Exception:
                continue
        return pontos

    def _candidatos_circulo(self, idx: int, elemento: dict, cursor: QPointF, candidatos: list[SnapResult]):
        centro = elemento.get("centro")
        if not isinstance(centro, (list, tuple)) or len(centro) != 2:
            return
        ponto = QPointF(float(centro[0]), float(centro[1]))
        candidatos.append(SnapResult(ponto=ponto, tipo="centro", distancia=self._dist(cursor, ponto), elemento_idx=idx))

    def _segmentos_polyline(self, idx: int, elemento: dict) -> list[tuple[int, QPointF, QPointF]]:
        pontos = [QPointF(float(x), float(y)) for x, y in elemento.get("pontos", [])]
        if len(pontos) < 2:
            return []
        if self._elemento_curva_suave(elemento):
            pontos = self._amostrar_curva_suave(pontos)
        return [(idx, inicio, fim) for inicio, fim in zip(pontos, pontos[1:])]

    def _candidatos_interseccoes(
        self,
        segmentos: list[tuple[int, QPointF, QPointF]],
        cursor: QPointF,
        tolerancia_cena: float,
        candidatos: list[SnapResult],
    ):
        proximos: list[tuple[int, QPointF, QPointF]] = []
        for idx, a1, a2 in segmentos:
            if self._dist_ponto_segmento(cursor, a1, a2) <= tolerancia_cena * 2.0:
                proximos.append((idx, a1, a2))
        if len(proximos) > 120:
            proximos = sorted(proximos, key=lambda s: self._dist_ponto_segmento(cursor, s[1], s[2]))[:120]

        for i in range(len(proximos)):
            idx_a, a1, a2 = proximos[i]
            for j in range(i + 1, len(proximos)):
                idx_b, b1, b2 = proximos[j]
                if idx_a == idx_b:
                    continue
                pt = self._intersecao_segmentos(a1, a2, b1, b2)
                if pt is None:
                    continue
                dist = self._dist(cursor, pt)
                candidatos.append(SnapResult(ponto=pt, tipo="interseção", distancia=dist, elemento_idx=idx_a))
                candidatos.append(SnapResult(ponto=pt, tipo="interseção", distancia=dist, elemento_idx=idx_b))

    def _intersecao_segmentos(self, a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF) -> QPointF | None:
        x1, y1 = a1.x(), a1.y()
        x2, y2 = a2.x(), a2.y()
        x3, y3 = b1.x(), b1.y()
        x4, y4 = b2.x(), b2.y()

        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) <= 1e-9:
            return None

        det1 = x1 * y2 - y1 * x2
        det2 = x3 * y4 - y3 * x4
        px = (det1 * (x3 - x4) - (x1 - x2) * det2) / den
        py = (det1 * (y3 - y4) - (y1 - y2) * det2) / den

        if not self._ponto_no_segmento(px, py, a1, a2):
            return None
        if not self._ponto_no_segmento(px, py, b1, b2):
            return None
        return QPointF(px, py)

    def _ponto_no_segmento(self, px: float, py: float, p1: QPointF, p2: QPointF) -> bool:
        margem = 1e-6
        return (
            min(p1.x(), p2.x()) - margem <= px <= max(p1.x(), p2.x()) + margem
            and min(p1.y(), p2.y()) - margem <= py <= max(p1.y(), p2.y()) + margem
        )

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

    def _dist_ponto_segmento(self, ponto: QPointF, inicio: QPointF, fim: QPointF) -> float:
        proj = self._projetar_em_segmento(ponto, inicio, fim)
        return self._dist(ponto, proj)

    def _prioridade_elemento(self, cena: CenaDocumento, idx: int | None) -> int:
        if idx is None or idx < 0 or idx >= len(cena.elementos):
            return 4
        subtipo = str(cena.elementos[idx].get("subtipo_audaces") or "")
        if subtipo == "contorno":
            return 0
        if subtipo == "linha_interna":
            return 1
        if subtipo == "costura":
            return 2
        if subtipo in {"texto", "anotacao"}:
            return 9
        return 3

    def _participa_snap(self, elemento: dict) -> bool:
        subtipo = str(elemento.get("subtipo_audaces") or elemento.get("metadados", {}).get("subtipo_audaces") or "").strip()
        if subtipo in {"texto", "anotacao"}:
            return False
        if elemento.get("tipo") == "texto":
            return False
        return True

    def _prioridade(self, tipo: str) -> int:
        if tipo == "interseção":
            return 0
        if tipo in {"controle principal", "controle auxiliar", "controle"}:
            return 1
        if tipo == "nó":
            return 2
        if tipo == "centro":
            return 3
        if tipo == "ponto médio":
            return 4
        if tipo == "borda":
            return 5
        if tipo == "grade":
            return 5
        return 9
