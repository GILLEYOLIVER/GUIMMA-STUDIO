from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF


def _dist(a: QPointF, b: QPointF) -> float:
    return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)


def _dist_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> float:
    abx = b.x() - a.x()
    aby = b.y() - a.y()
    apx = p.x() - a.x()
    apy = p.y() - a.y()
    denom = (abx * abx) + (aby * aby)
    if denom <= 1e-9:
        return _dist(a, p)
    t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
    proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
    return _dist(proj, p)


def _amostrar_bezier_quadratica(p0: QPointF, p1: QPointF, p2: QPointF, segmentos: int = 48) -> list[QPointF]:
    pontos = []
    for i in range(segmentos + 1):
        t = i / max(segmentos, 1)
        u = 1.0 - t
        x = (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x())
        y = (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y())
        pontos.append(QPointF(x, y))
    return pontos


def segmentos_de_elemento(elemento: dict) -> list[tuple[QPointF, QPointF]]:
    if elemento.get("tipo") == "polyline":
        pts = [QPointF(float(x), float(y)) for x, y in elemento.get("pontos", [])]
    elif elemento.get("tipo") == "bezier_quadratica":
        pts = _amostrar_bezier_quadratica(
            QPointF(*elemento.get("p0", (0.0, 0.0))),
            QPointF(*elemento.get("p1", (0.0, 0.0))),
            QPointF(*elemento.get("p2", (0.0, 0.0))),
            segmentos=64,
        )
    else:
        return []
    return list(zip(pts, pts[1:]))


def comprimento_total_elemento(elemento: dict) -> float:
    return sum(_dist(a, b) for a, b in segmentos_de_elemento(elemento))


def selecionar_segmento_mais_proximo(canvas, pos: QPointF, tolerancia_px: float = 10.0) -> dict | None:
    tolerancia_cena = tolerancia_px / max(canvas.zoom, 0.001)
    melhor: dict | None = None
    for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
        el = canvas.cena.elementos[idx]
        segs = segmentos_de_elemento(el)
        if not segs:
            continue
        total = sum(_dist(a, b) for a, b in segs)
        for a, b in segs:
            d = _dist_ponto_segmento(a, b, pos)
            if d > tolerancia_cena:
                continue
            seg_len = _dist(a, b)
            if melhor is None or d < melhor["dist"]:
                melhor = {
                    "elemento_idx": idx,
                    "segmento_inicio": a,
                    "segmento_fim": b,
                    "segmento_comprimento": seg_len,
                    "perimetro_total": total,
                    "dist": d,
                }
    return melhor


def mensagem_status(canvas, texto: str):
    if getattr(canvas, "lbl_status", None) is not None:
        canvas.lbl_status.setText(texto)
