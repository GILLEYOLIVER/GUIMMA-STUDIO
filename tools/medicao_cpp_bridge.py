from __future__ import annotations

from math import sqrt
from PySide6.QtCore import QPointF

try:
    from core.geometry_cpp_bridge import modulo_cpp

    _cpp = modulo_cpp()
except Exception:
    _cpp = None


def cpp_disponivel() -> bool:
    return _cpp is not None


def dist(a: QPointF, b: QPointF) -> float:
    if _cpp is not None:
        try:
            return float(_cpp.distance(float(a.x()), float(a.y()), float(b.x()), float(b.y())))
        except Exception:
            pass
    return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)


def projetar_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> QPointF:
    if _cpp is not None:
        try:
            x, y = _cpp.project_on_segment(
                float(p.x()), float(p.y()),
                float(a.x()), float(a.y()),
                float(b.x()), float(b.y()),
            )
            return QPointF(float(x), float(y))
        except Exception:
            pass
    abx = b.x() - a.x()
    aby = b.y() - a.y()
    apx = p.x() - a.x()
    apy = p.y() - a.y()
    denom = (abx * abx) + (aby * aby)
    if denom <= 1e-9:
        return QPointF(a)
    t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
    return QPointF(a.x() + (abx * t), a.y() + (aby * t))


def dist_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> float:
    return dist(projetar_ponto_segmento(a, b, p), p)


def _tp(p: QPointF) -> tuple[float, float]:
    return float(p.x()), float(p.y())


def _qpairs(pairs) -> list[QPointF]:
    return [QPointF(float(x), float(y)) for x, y in pairs]


def amostrar_bezier_quadratica(p0: QPointF, p1: QPointF, p2: QPointF, segmentos: int = 64) -> list[QPointF]:
    if _cpp is not None and hasattr(_cpp, "sample_quadratic_bezier"):
        try:
            return _qpairs(_cpp.sample_quadratic_bezier(_tp(p0), _tp(p1), _tp(p2), int(segmentos)))
        except Exception:
            pass
    pontos: list[QPointF] = []
    n = max(4, int(segmentos))
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        pontos.append(QPointF(
            (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x()),
            (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y()),
        ))
    return pontos


def amostrar_parabola_3p(p0: QPointF, meio: QPointF, p2: QPointF, segmentos: int = 48) -> list[QPointF]:
    if _cpp is not None and hasattr(_cpp, "sample_parabola_3p"):
        try:
            return _qpairs(_cpp.sample_parabola_3p(_tp(p0), _tp(meio), _tp(p2), int(segmentos)))
        except Exception:
            pass
    controle = QPointF(
        (2.0 * meio.x()) - (0.5 * p0.x()) - (0.5 * p2.x()),
        (2.0 * meio.y()) - (0.5 * p0.y()) - (0.5 * p2.y()),
    )
    return amostrar_bezier_quadratica(p0, controle, p2, segmentos)
