from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _carregar_modulo_build_local():
    build_dir = Path(__file__).resolve().parent / "geometry_cpp" / "build"
    if not build_dir.is_dir():
        return None
    for pattern in ("guimma_geometry_cpp*.so", "guimma_geometry_cpp*.pyd", "guimma_geometry_cpp*.dylib"):
        for artifact in sorted(build_dir.rglob(pattern)):
            try:
                spec = importlib.util.spec_from_file_location("guimma_geometry_cpp", artifact)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules.setdefault("guimma_geometry_cpp", module)
                spec.loader.exec_module(module)
                return module
            except Exception:
                sys.modules.pop("guimma_geometry_cpp", None)
    return None

try:
    import guimma_geometry_cpp as _cpp
except Exception:  # pragma: no cover - fallback quando o modulo C++ nao foi compilado
    _cpp = _carregar_modulo_build_local()


def cpp_disponivel() -> bool:
    """Retorna True quando o modulo C++ foi compilado e importado corretamente."""
    return _cpp is not None


def modulo_cpp():
    """Retorna o modulo C++ carregado, ou None quando o build nativo nao existe."""
    return _cpp


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


def seam_offset_closed_cpp(
    points: list[tuple[float, float]],
    margin: float,
) -> list[tuple[float, float]] | None:
    """
    Offset fechado de costura calculado pelo motor C++.

    Retorna None quando o modulo nativo nao esta disponivel ou quando a entrada
    nao permite gerar uma costura valida. As ferramentas devem manter fallback
    Python para preservar o funcionamento em ambientes sem build C++.
    """
    if _cpp is None:
        return None
    try:
        if len(points or []) < 3:
            return None
        resultado = _cpp.seam_offset_closed(
            [(float(x), float(y)) for x, y in points],
            float(margin),
        )
        if not resultado:
            return None
        return [(float(x), float(y)) for x, y in resultado]
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
