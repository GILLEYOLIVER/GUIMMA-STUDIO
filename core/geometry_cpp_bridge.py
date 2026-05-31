from __future__ import annotations

from typing import Iterable

try:
    import guimma_geometry_cpp as _cpp
except Exception:  # pragma: no cover - fallback quando o modulo C++ nao foi compilado
    _cpp = None


def cpp_disponivel() -> bool:
    """Retorna True quando o modulo C++ foi compilado e importado corretamente."""
    return _cpp is not None


def _elementos_para_polylines(elements: list[dict]) -> list[list[tuple[float, float]]]:
    """
    Converte elementos do GUIMMA para polylines simples aceitas pelo motor C++.
    Mantem a leitura tolerante para nao quebrar ferramentas existentes.
    """
    from core.geometry_bridge import polyline_from_element

    polylines: list[list[tuple[float, float]]] = []
    for el in elements:
        try:
            pts = polyline_from_element(el)
        except Exception:
            pts = []
        if len(pts) >= 2:
            polylines.append([(float(x), float(y)) for x, y in pts])
    return polylines


def _resultado_para_pontos(resultado) -> list[tuple[float, float]] | None:
    if not resultado:
        return None
    try:
        pontos = resultado.get("points")
    except Exception:
        return None
    if not pontos:
        return None
    return [(float(x), float(y)) for x, y in pontos]


def extract_local_enclosing_contour_cpp(
    elements: list[dict],
    point: tuple[float, float],
    search_radius: float = 20.0,
    tol: float = 0.01,
) -> list[tuple[float, float]] | None:
    """
    Versao C++ da extracao local de contorno.
    Retorna None se o C++ nao estiver disponivel ou se falhar.
    """
    if _cpp is None:
        return None
    try:
        polylines = _elementos_para_polylines(elements)
        if not polylines:
            return None
        resultado = _cpp.extract_local_enclosing_contour(
            polylines,
            float(point[0]),
            float(point[1]),
            float(search_radius),
            float(tol),
        )
        return _resultado_para_pontos(resultado)
    except Exception:
        return None


def extract_smallest_enclosing_contour_cpp(
    elements: list[dict],
    point: tuple[float, float],
    tol: float = 0.001,
    search_radius: float | None = None,
) -> list[tuple[float, float]] | None:
    """
    Versao C++ da extracao do menor contorno contendo o ponto.
    O parametro search_radius e aceito por compatibilidade com o Python atual.
    """
    if _cpp is None:
        return None
    try:
        polylines = _elementos_para_polylines(elements)
        if not polylines:
            return None
        if search_radius is not None and search_radius > 0:
            resultado = _cpp.extract_local_enclosing_contour(
                polylines,
                float(point[0]),
                float(point[1]),
                float(search_radius),
                float(tol),
            )
        else:
            resultado = _cpp.extract_smallest_enclosing_contour(
                polylines,
                float(point[0]),
                float(point[1]),
                float(tol),
            )
        return _resultado_para_pontos(resultado)
    except Exception:
        return None


def extract_local_enclosing_contour_safe(
    elements: list[dict],
    point: tuple[float, float],
    search_radius: float = 20.0,
    tol: float = 0.01,
) -> list[tuple[float, float]] | None:
    """
    Usa C++ quando disponivel; se nao houver resultado, volta ao Python atual.
    """
    contorno = extract_local_enclosing_contour_cpp(elements, point, search_radius=search_radius, tol=tol)
    if contorno:
        return contorno

    from core.geometry_bridge import extract_local_enclosing_contour

    return extract_local_enclosing_contour(elements, point, search_radius=search_radius, tol=tol)


def extract_smallest_enclosing_contour_safe(
    elements: list[dict],
    point: tuple[float, float],
    tol: float = 0.001,
    search_radius: float | None = None,
) -> list[tuple[float, float]] | None:
    """
    Usa C++ quando disponivel; se nao houver resultado, volta ao Python atual.
    """
    contorno = extract_smallest_enclosing_contour_cpp(elements, point, tol=tol, search_radius=search_radius)
    if contorno:
        return contorno

    from core.geometry_bridge import extract_smallest_enclosing_contour

    return extract_smallest_enclosing_contour(elements, point, tol=tol, search_radius=search_radius)
