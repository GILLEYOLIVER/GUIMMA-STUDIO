from __future__ import annotations

"""
Bridge geométrico acelerado do GUIMMA STUDIO.

Este módulo mantém compatibilidade com core.geometry_bridge e substitui apenas
as funções pesadas de extração por versões que tentam usar o motor C++ primeiro.
Se o C++ não estiver compilado, indisponível ou não retornar contorno válido,
o fluxo volta automaticamente para o Python original.

Uso futuro seguro:
    from core.geometry_bridge_accelerated import extract_local_enclosing_contour

Sem quebrar o fluxo atual:
    - todas as demais funções continuam vindas de core.geometry_bridge;
    - create_mold_payload continua usando a estrutura oficial Python atual;
    - compose_closed_contour continua usando a composição oficial Python atual;
    - as ferramentas continuam protegidas por fallback.
"""

from core.geometry_bridge import *  # noqa: F401,F403
from core.geometry_bridge import (
    extract_local_enclosing_contour as _py_extract_local_enclosing_contour,
    extract_smallest_enclosing_contour as _py_extract_smallest_enclosing_contour,
)
from core.geometry_cpp_bridge import (
    extract_local_enclosing_contour_cpp,
    extract_smallest_enclosing_contour_cpp,
)


def extract_local_enclosing_contour(
    elements: list[dict],
    point: tuple[float, float],
    search_radius: float = 20.0,
    tol: float = 0.01,
) -> list[tuple[float, float]] | None:
    """
    Versão acelerada e segura da extração local.

    Primeiro tenta o motor C++.
    Se o C++ não estiver pronto ou não encontrar contorno, volta para o Python original.
    """
    contorno = extract_local_enclosing_contour_cpp(
        elements,
        point,
        search_radius=search_radius,
        tol=tol,
    )
    if contorno:
        return contorno

    return _py_extract_local_enclosing_contour(
        elements,
        point,
        search_radius=search_radius,
        tol=tol,
    )


def extract_smallest_enclosing_contour(
    elements: list[dict],
    point: tuple[float, float],
    tol: float = 0.001,
    search_radius: float | None = None,
) -> list[tuple[float, float]] | None:
    """
    Versão acelerada e segura da menor face envolvente.

    Primeiro tenta o motor C++.
    Se o C++ não estiver pronto ou não encontrar contorno, volta para o Python original.
    """
    contorno = extract_smallest_enclosing_contour_cpp(
        elements,
        point,
        tol=tol,
        search_radius=search_radius,
    )
    if contorno:
        return contorno

    return _py_extract_smallest_enclosing_contour(
        elements,
        point,
        tol=tol,
        search_radius=search_radius,
    )
