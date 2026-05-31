from __future__ import annotations

import unittest

from core.geometry_bridge import (
    extract_local_enclosing_contour as extract_local_python,
    extract_smallest_enclosing_contour as extract_smallest_python,
)
from core.geometry_bridge_accelerated import (
    extract_local_enclosing_contour as extract_local_accelerated,
    extract_smallest_enclosing_contour as extract_smallest_accelerated,
)
from core.geometry_cpp_bridge import cpp_disponivel
from core.geometry_cpp_bridge import (
    extract_local_enclosing_contour_cpp,
    extract_smallest_enclosing_contour_cpp,
)


def _rectangle_elements() -> list[dict]:
    return [
        {"tipo": "polyline", "pontos": [(0.0, 0.0), (10.0, 0.0)]},
        {"tipo": "polyline", "pontos": [(10.0, 0.0), (10.0, 6.0)]},
        {"tipo": "polyline", "pontos": [(10.0, 6.0), (0.0, 6.0)]},
        {"tipo": "polyline", "pontos": [(0.0, 6.0), (0.0, 0.0)]},
    ]


def _canonical_contour(points: list[tuple[float, float]] | None) -> set[tuple[float, float]] | None:
    if points is None:
        return None
    return {(round(x, 7), round(y, 7)) for x, y in points}


@unittest.skipUnless(cpp_disponivel(), "guimma_geometry_cpp nao compilado neste ambiente")
class GeometryCppBridgeTestCase(unittest.TestCase):
    def test_extracao_local_cpp_equivale_ao_python_em_retangulo(self):
        elements = _rectangle_elements()

        python_result = extract_local_python(elements, (5.0, 3.0), search_radius=20.0, tol=0.01)
        cpp_result = extract_local_enclosing_contour_cpp(elements, (5.0, 3.0), search_radius=20.0, tol=0.01)
        accelerated_result = extract_local_accelerated(elements, (5.0, 3.0), search_radius=20.0, tol=0.01)

        self.assertIsNotNone(cpp_result)
        self.assertEqual(_canonical_contour(cpp_result), _canonical_contour(python_result))
        self.assertEqual(_canonical_contour(accelerated_result), _canonical_contour(python_result))

    def test_menor_contorno_cpp_equivale_ao_python_com_linhas_cruzadas(self):
        elements = [
            *_rectangle_elements(),
            {"tipo": "polyline", "pontos": [(5.0, 0.0), (5.0, 6.0)]},
        ]

        python_result = extract_smallest_python(elements, (2.0, 3.0), tol=0.01)
        cpp_result = extract_smallest_enclosing_contour_cpp(elements, (2.0, 3.0), tol=0.01)
        accelerated_result = extract_smallest_accelerated(elements, (2.0, 3.0), tol=0.01)

        self.assertIsNotNone(cpp_result)
        self.assertEqual(_canonical_contour(cpp_result), _canonical_contour(python_result))
        self.assertEqual(_canonical_contour(accelerated_result), _canonical_contour(python_result))

    def test_extracao_local_cpp_equivale_ao_python_com_prolongamento(self):
        elements = [
            *_rectangle_elements(),
            {"tipo": "polyline", "pontos": [(-4.0, 3.0), (14.0, 3.0)]},
        ]

        python_result = extract_local_python(elements, (5.0, 1.0), search_radius=20.0, tol=0.01)
        cpp_result = extract_local_enclosing_contour_cpp(elements, (5.0, 1.0), search_radius=20.0, tol=0.01)
        accelerated_result = extract_local_accelerated(elements, (5.0, 1.0), search_radius=20.0, tol=0.01)

        self.assertIsNotNone(cpp_result)
        self.assertEqual(_canonical_contour(cpp_result), _canonical_contour(python_result))
        self.assertEqual(_canonical_contour(accelerated_result), _canonical_contour(python_result))

    def test_extracao_local_cpp_equivale_ao_python_em_triangulo(self):
        elements = [
            {"tipo": "polyline", "pontos": [(0.0, 0.0), (8.0, 0.0)]},
            {"tipo": "polyline", "pontos": [(8.0, 0.0), (4.0, 7.0)]},
            {"tipo": "polyline", "pontos": [(4.0, 7.0), (0.0, 0.0)]},
        ]

        python_result = extract_local_python(elements, (4.0, 2.0), search_radius=20.0, tol=0.01)
        cpp_result = extract_local_enclosing_contour_cpp(elements, (4.0, 2.0), search_radius=20.0, tol=0.01)

        self.assertIsNotNone(cpp_result)
        self.assertEqual(_canonical_contour(cpp_result), _canonical_contour(python_result))

    def test_extracao_local_cpp_equivale_ao_python_com_curva_amostrada(self):
        elements = [
            {
                "tipo": "bezier_quadratica",
                "p0": (0.0, 0.0),
                "p1": (5.0, -2.0),
                "p2": (10.0, 0.0),
            },
            {"tipo": "polyline", "pontos": [(10.0, 0.0), (10.0, 6.0)]},
            {"tipo": "polyline", "pontos": [(10.0, 6.0), (0.0, 6.0)]},
            {"tipo": "polyline", "pontos": [(0.0, 6.0), (0.0, 0.0)]},
        ]

        python_result = extract_local_python(elements, (5.0, 3.0), search_radius=20.0, tol=0.01)
        cpp_result = extract_local_enclosing_contour_cpp(elements, (5.0, 3.0), search_radius=20.0, tol=0.01)

        self.assertIsNotNone(cpp_result)
        self.assertEqual(_canonical_contour(cpp_result), _canonical_contour(python_result))


if __name__ == "__main__":
    unittest.main()
