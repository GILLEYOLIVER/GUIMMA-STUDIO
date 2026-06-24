from __future__ import annotations

import unittest

import core.geometry_cpp_bridge as geometry_cpp_bridge
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
    diagnostico_cpp,
    extract_local_enclosing_contour_cpp,
    sample_catmull_rom_centripetal_dynamic_cpp,
    extract_smallest_enclosing_contour_cpp,
    unfold_mirrored_contour_cpp,
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


class GeometryCppDiagnosticsTestCase(unittest.TestCase):
    def test_diagnostico_cpp_tem_contrato_estavel(self):
        diagnostico = diagnostico_cpp()

        self.assertEqual(diagnostico["disponivel"], cpp_disponivel())
        self.assertIn("modulo", diagnostico)
        self.assertIn("arquivo", diagnostico)
        self.assertIn("simbolos", diagnostico)
        self.assertIn("simbolos_ausentes", diagnostico)
        self.assertIn("wrappers_python", diagnostico)
        self.assertIsInstance(diagnostico["simbolos"], dict)
        self.assertIsInstance(diagnostico["simbolos_ausentes"], list)
        self.assertIsInstance(diagnostico["wrappers_python"], list)

        simbolos_obrigatorios = {
            "distance",
            "project_on_segment",
            "seam_offset_closed",
            "extract_local_enclosing_contour",
            "extract_smallest_enclosing_contour",
            "SnapEngine",
        }
        self.assertTrue(simbolos_obrigatorios.issubset(diagnostico["simbolos"]))
        self.assertIn("seam_offset_closed_cpp", diagnostico["wrappers_python"])

        if cpp_disponivel():
            self.assertEqual(diagnostico["modulo"], "guimma_geometry_cpp")
            self.assertTrue(diagnostico["arquivo"])
            self.assertTrue(any(diagnostico["simbolos"].values()))
        else:
            self.assertEqual(diagnostico["modulo"], "")
            self.assertEqual(diagnostico["arquivo"], "")

    def test_wrappers_cpp_retornam_none_sem_modulo_nativo(self):
        modulo_original = geometry_cpp_bridge._cpp
        geometry_cpp_bridge._cpp = None
        try:
            self.assertFalse(geometry_cpp_bridge.cpp_disponivel())
            self.assertFalse(geometry_cpp_bridge.diagnostico_cpp()["disponivel"])
            self.assertIsNone(geometry_cpp_bridge.seam_offset_closed_cpp([(0.0, 0.0), (1.0, 0.0)], 1.0))
            self.assertIsNone(
                geometry_cpp_bridge.extract_local_enclosing_contour_cpp(
                    _rectangle_elements(),
                    (5.0, 3.0),
                )
            )
        finally:
            geometry_cpp_bridge._cpp = modulo_original


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

    def test_catmull_rom_centripeta_dinamica_cpp_expoe_amostragem(self):
        controles = [(0.0, 0.0), (5.0, 3.0), (10.0, 0.0), (15.0, 2.0)]

        resultado = sample_catmull_rom_centripetal_dynamic_cpp(controles, closed=False)

        self.assertIsNotNone(resultado)
        self.assertGreater(len(resultado), len(controles))
        self.assertEqual(resultado[0], controles[0])
        self.assertEqual(resultado[-1], controles[-1])
        pontos_arredondados = {(round(x, 7), round(y, 7)) for x, y in resultado}
        self.assertIn((5.0, 3.0), pontos_arredondados)
        self.assertIn((10.0, 0.0), pontos_arredondados)

    def test_desdobrar_espelhado_cpp_monta_contorno_pela_borda_de_dobra(self):
        meia_peca = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)]

        resultado = unfold_mirrored_contour_cpp(meia_peca, 1, 0.0, (0.0, 0.0), (0.0, 1.0))

        self.assertEqual(
            resultado,
            [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (-10.0, 5.0), (-10.0, 0.0), (0.0, 0.0)],
        )


if __name__ == "__main__":
    unittest.main()
