from __future__ import annotations

from core.geometry.engine import (
    build_mold_from_shape,
    build_shape_from_polyline,
    contour_is_valid,
    ensure_closed_polyline,
    normalize_closed_polyline,
    point_in_polygon,
)


def polyline_from_element(element: dict) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in element.get("pontos", [])]


def element_contains_point(element: dict, point: tuple[float, float]) -> bool:
    return point_in_polygon(point, polyline_from_element(element))


def create_mold_payload(element: dict) -> dict:
    polyline = normalize_closed_polyline(polyline_from_element(element), clockwise=True)
    if not contour_is_valid(polyline):
        raise ValueError("Contorno inválido para criação de molde.")
    shape = build_shape_from_polyline(polyline)
    mold = build_mold_from_shape(shape)
    return {
        "shape_id": shape.id,
        "node_ids": [n.id for n in shape.nodes],
        "segment_ids": [s.id for s in shape.segments],
        "pontos": polyline,
        "controle_cantos": mold.corner_controls,
        "pontos_controle_principais": mold.main_controls,
        "pontos_auxiliares": mold.helper_controls,
    }


def compose_closed_contour(elements: list[dict], tol: float = 0.001) -> list[tuple[float, float]]:
    """Compõe um único contorno fechado a partir de múltiplas polylines abertas/fechadas."""
    parts: list[list[tuple[float, float]]] = []
    for el in elements:
        pts = polyline_from_element(el)
        if pts:
            parts.append(pts)
    if not parts:
        raise ValueError("Nenhuma polyline disponível para composição.")

    chain = list(parts.pop(0))
    while parts:
        changed = False
        start = chain[0]
        end = chain[-1]
        for i, pts in enumerate(parts):
            a = pts[0]
            b = pts[-1]
            if _near(end, a, tol):
                chain.extend(pts[1:])
            elif _near(end, b, tol):
                chain.extend(list(reversed(pts[:-1])))
            elif _near(start, b, tol):
                chain = [*pts[:-1], *chain]
            elif _near(start, a, tol):
                chain = [*list(reversed(pts[1:])), *chain]
            else:
                continue
            parts.pop(i)
            changed = True
            break
        if not changed:
            raise ValueError("Não foi possível compor o contorno: segmentos desconectados.")

    chain = normalize_closed_polyline(chain, clockwise=True)
    if not contour_is_valid(chain):
        raise ValueError("Contorno composto inválido.")
    return chain


def _near(a: tuple[float, float], b: tuple[float, float], tol: float) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol
