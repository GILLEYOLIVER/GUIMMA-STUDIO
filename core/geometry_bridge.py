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
    tipo = str(element.get("tipo", ""))
    if tipo == "bezier_quadratica":
        p0 = element.get("p0")
        p1 = element.get("p1")
        p2 = element.get("p2")
        if not (isinstance(p0, (list, tuple)) and isinstance(p1, (list, tuple)) and isinstance(p2, (list, tuple))):
            return []
        x0, y0 = float(p0[0]), float(p0[1])
        x1, y1 = float(p1[0]), float(p1[1])
        x2, y2 = float(p2[0]), float(p2[1])
        amostras = max(8, int(element.get("amostras_contorno", 24)))
        pontos: list[tuple[float, float]] = []
        for i in range(amostras + 1):
            t = i / amostras
            u = 1.0 - t
            x = (u * u * x0) + (2.0 * u * t * x1) + (t * t * x2)
            y = (u * u * y0) + (2.0 * u * t * y1) + (t * t * y2)
            pontos.append((x, y))
        return pontos
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


def extract_smallest_enclosing_contour(
    elements: list[dict],
    point: tuple[float, float],
    tol: float = 0.001,
) -> list[tuple[float, float]] | None:
    """Extrai a menor face fechada que contém o ponto, a partir de polylines abertas/fechadas."""
    segments = _explode_segments(elements)
    if not segments:
        return None
    split_segments = _split_segments_at_intersections(segments, tol=tol)
    if not split_segments:
        return None
    cycles = _find_cycles(split_segments, tol=tol)
    if not cycles:
        return None
    best: list[tuple[float, float]] | None = None
    best_area = float("inf")
    for cycle in cycles:
        poly = normalize_closed_polyline(cycle, clockwise=True)
        if not contour_is_valid(poly):
            continue
        if not point_in_polygon(point, poly):
            continue
        area = abs(_polygon_area(poly))
        if area <= 1e-6:
            continue
        if area < best_area:
            best = poly
            best_area = area
    return best


def _near(a: tuple[float, float], b: tuple[float, float], tol: float) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _explode_segments(elements: list[dict]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for el in elements:
        pts = polyline_from_element(el)
        if len(pts) < 2:
            continue
        for a, b in zip(pts, pts[1:]):
            if _near(a, b, 1e-12):
                continue
            segments.append((a, b))
    return segments


def _split_segments_at_intersections(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    tol: float,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i, (a, b) in enumerate(segments):
        points_on_seg = [a, b]
        for j, (c, d) in enumerate(segments):
            if i == j:
                continue
            ip = _segment_intersection(a, b, c, d, tol=tol)
            if ip is None:
                continue
            points_on_seg.append(ip)
        points_sorted = sorted(points_on_seg, key=lambda p: ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2))
        dedup: list[tuple[float, float]] = []
        for p in points_sorted:
            if not dedup or not _near(p, dedup[-1], tol):
                dedup.append(p)
        for p1, p2 in zip(dedup, dedup[1:]):
            if not _near(p1, p2, tol):
                out.append((p1, p2))
    return out


def _find_cycles(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    tol: float,
) -> list[list[tuple[float, float]]]:
    def key(p: tuple[float, float]) -> tuple[int, int]:
        return (round(p[0] / tol), round(p[1] / tol))

    node_points: dict[tuple[int, int], tuple[float, float]] = {}
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for a, b in segments:
        ka = key(a)
        kb = key(b)
        if ka == kb:
            continue
        node_points.setdefault(ka, a)
        node_points.setdefault(kb, b)
        adjacency.setdefault(ka, set()).add(kb)
        adjacency.setdefault(kb, set()).add(ka)

    cycles: dict[tuple[tuple[int, int], ...], list[tuple[float, float]]] = {}
    # Curvas amostradas podem gerar muitos segmentos no mesmo ciclo.
    # Profundidade fixa baixa (ex.: 32) perde faces válidas.
    max_depth = max(64, min(1024, len(adjacency) + 8))
    for start in adjacency:
        stack: list[tuple[tuple[int, int], list[tuple[int, int]]]] = [(start, [start])]
        while stack:
            node, path = stack.pop()
            if len(path) > max_depth:
                continue
            for nxt in adjacency.get(node, set()):
                if len(path) >= 2 and nxt == path[-2]:
                    continue
                if nxt == start and len(path) >= 3:
                    cycle_keys = path[:]
                    canonical = _canonical_cycle(cycle_keys)
                    if canonical not in cycles:
                        pts = [node_points[k] for k in cycle_keys]
                        cycles[canonical] = [*pts, pts[0]]
                    continue
                if nxt in path:
                    continue
                stack.append((nxt, [*path, nxt]))
    return list(cycles.values())


def _canonical_cycle(cycle: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    if not cycle:
        return tuple()
    n = len(cycle)
    rots = [tuple(cycle[i:] + cycle[:i]) for i in range(n)]
    rev = list(reversed(cycle))
    rev_rots = [tuple(rev[i:] + rev[:i]) for i in range(n)]
    return min([*rots, *rev_rots])


def _segment_intersection(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    tol: float,
) -> tuple[float, float] | None:
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    r = (bx - ax, by - ay)
    s = (dx - cx, dy - cy)
    rxs = (r[0] * s[1]) - (r[1] * s[0])
    q_p = (cx - ax, cy - ay)
    qpxr = (q_p[0] * r[1]) - (q_p[1] * r[0])
    if abs(rxs) <= tol and abs(qpxr) <= tol:
        # Colinear: usa apenas extremos que caem no outro segmento.
        candidates = [a, b, c, d]
        for p in candidates:
            if _on_segment(p, a, b, tol) and _on_segment(p, c, d, tol):
                return p
        return None
    if abs(rxs) <= tol:
        return None
    t = ((q_p[0] * s[1]) - (q_p[1] * s[0])) / rxs
    u = ((q_p[0] * r[1]) - (q_p[1] * r[0])) / rxs
    if -tol <= t <= 1.0 + tol and -tol <= u <= 1.0 + tol:
        return (ax + t * r[0], ay + t * r[1])
    return None


def _on_segment(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float], tol: float) -> bool:
    return (
        min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol
        and min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol
    )


def _polygon_area(poly: list[tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    acc = 0.0
    for a, b in zip(poly, poly[1:]):
        acc += (a[0] * b[1]) - (b[0] * a[1])
    return 0.5 * acc
