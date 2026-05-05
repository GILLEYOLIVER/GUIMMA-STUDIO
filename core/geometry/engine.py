from __future__ import annotations

from dataclasses import dataclass
from math import acos, sqrt

from core.geometry.model import GeoNode, GeoSegment, GeoShape

try:
    import geometry_native as _geometry_native  # type: ignore
except Exception:  # pragma: no cover - backend opcional
    _geometry_native = None


@dataclass(slots=True)
class MoldResult:
    corner_controls: list[tuple[float, float]]
    main_controls: list[dict]
    helper_controls: list[dict]


def polygon_signed_area(points: list[tuple[float, float]]) -> float:
    poly = ensure_closed_polyline(points)
    if len(poly) < 4:
        return 0.0
    acc = 0.0
    for a, b in zip(poly, poly[1:]):
        acc += (a[0] * b[1]) - (b[0] * a[1])
    return 0.5 * acc


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)


def point_segment_distance(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    if _geometry_native is not None:
        try:
            return float(_geometry_native.point_segment_distance(point, a, b))
        except Exception:
            pass
    px, py = point
    ax, ay = a
    bx, by = b
    abx = bx - ax
    aby = by - ay
    denom = (abx * abx) + (aby * aby)
    if denom <= 1e-12:
        return sqrt(((px - ax) ** 2) + ((py - ay) ** 2))
    t = max(0.0, min(1.0, (((px - ax) * abx) + ((py - ay) * aby)) / denom))
    qx = ax + (abx * t)
    qy = ay + (aby * t)
    return sqrt(((px - qx) ** 2) + ((py - qy) ** 2))


def polyline_perimeter(points: list[tuple[float, float]]) -> float:
    if _geometry_native is not None:
        try:
            return float(_geometry_native.polyline_perimeter(points))
        except Exception:
            pass
    if len(points) < 2:
        return 0.0
    return sum(dist(a, b) for a, b in zip(points, points[1:]))


def ensure_closed_polyline(points: list[tuple[float, float]], eps: float = 0.001) -> list[tuple[float, float]]:
    if len(points) < 2:
        return points
    if dist(points[0], points[-1]) <= eps:
        return list(points)
    return [*points, points[0]]


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    if _geometry_native is not None:
        try:
            return bool(_geometry_native.point_in_polygon(point, polygon))
        except Exception:
            pass

    poly = ensure_closed_polyline(polygon)
    if len(poly) < 4:
        return False

    x, y = point
    for a, b in zip(poly, poly[1:]):
        if point_segment_distance((x, y), a, b) <= 1e-9:
            return True

    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        cruza = (yi > y) != (yj > y)
        if cruza:
            dy = yj - yi
            if abs(dy) > 1e-12:
                x_intersect = ((xj - xi) * (y - yi) / dy) + xi
                if x <= x_intersect:
                    inside = not inside
        j = i

    return inside


def normalize_closed_polyline(points: list[tuple[float, float]], clockwise: bool = True) -> list[tuple[float, float]]:
    poly = ensure_closed_polyline(points)
    if len(poly) < 4:
        return poly
    area = polygon_signed_area(poly)
    is_clockwise = area < 0
    if clockwise != is_clockwise:
        rev = list(reversed(poly[:-1]))
        return [*rev, rev[0]]
    return poly


def contour_is_valid(points: list[tuple[float, float]], min_vertices: int = 3, min_abs_area: float = 1e-4) -> bool:
    poly = ensure_closed_polyline(points)
    if len(poly) < (min_vertices + 1):
        return False
    return abs(polygon_signed_area(poly)) >= min_abs_area


def build_shape_from_polyline(points: list[tuple[float, float]]) -> GeoShape:
    closed_points = normalize_closed_polyline(points, clockwise=True)
    if not contour_is_valid(closed_points):
        raise ValueError("Polyline fechada precisa de ao menos 3 vértices.")

    nodes = [GeoNode(x=p[0], y=p[1]) for p in closed_points[:-1]]
    segments: list[GeoSegment] = []
    for i, node in enumerate(nodes):
        nxt = nodes[(i + 1) % len(nodes)]
        segments.append(GeoSegment(start_node_id=node.id, end_node_id=nxt.id, segment_type="line"))
    return GeoShape(nodes=nodes, segments=segments, closed=True)


def build_mold_from_shape(shape: GeoShape) -> MoldResult:
    corners = [(n.x, n.y) for n in shape.nodes]
    mains = [{"id": n.id, "indice": i + 1, "x": n.x, "y": n.y} for i, n in enumerate(shape.nodes)]
    helpers: list[dict] = []
    for seg in shape.segments:
        start = next(n for n in shape.nodes if n.id == seg.start_node_id)
        end = next(n for n in shape.nodes if n.id == seg.end_node_id)
        helpers.append(
            {
                "segment_id": seg.id,
                "x": (start.x + end.x) / 2.0,
                "y": (start.y + end.y) / 2.0,
                "oculto": True,
            }
        )
    return MoldResult(corner_controls=corners, main_controls=mains, helper_controls=helpers)


def internal_angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    if _geometry_native is not None:
        try:
            return float(_geometry_native.internal_angle(a, b, c))
        except Exception:
            pass
    bax, bay = a[0] - b[0], a[1] - b[1]
    bcx, bcy = c[0] - b[0], c[1] - b[1]
    na = sqrt((bax * bax) + (bay * bay))
    nb = sqrt((bcx * bcx) + (bcy * bcy))
    if na <= 1e-9 or nb <= 1e-9:
        return 180.0
    cosv = max(-1.0, min(1.0, ((bax * bcx) + (bay * bcy)) / (na * nb)))
    return acos(cosv) * (180.0 / 3.141592653589793)
