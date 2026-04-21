from __future__ import annotations

from core.geometry.engine import (
    build_mold_from_shape,
    build_shape_from_polyline,
    ensure_closed_polyline,
    point_in_polygon,
)


def polyline_from_element(element: dict) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in element.get("pontos", [])]


def element_contains_point(element: dict, point: tuple[float, float]) -> bool:
    return point_in_polygon(point, polyline_from_element(element))


def create_mold_payload(element: dict) -> dict:
    polyline = ensure_closed_polyline(polyline_from_element(element))
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
