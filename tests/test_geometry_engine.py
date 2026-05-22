from __future__ import annotations

import unittest

from core.geometry.engine import (
    quadratic_bezier_control_for_point,
    quadratic_bezier_parameter_for_point,
    sample_quadratic_bezier_through_point,
)
from core.geometry_bridge import polyline_from_element


def _bezier(p0, p1, p2, t: float) -> tuple[float, float]:
    u = 1.0 - t
    return (
        (u * u * p0[0]) + (2.0 * u * t * p1[0]) + (t * t * p2[0]),
        (u * u * p0[1]) + (2.0 * u * t * p1[1]) + (t * t * p2[1]),
    )


class GeometryEngineTestCase(unittest.TestCase):
    def test_quadratic_control_passa_por_ponto_3p_assimetrico(self):
        p0 = (0.0, 0.0)
        p_meio = (3.0, -5.0)
        p2 = (10.0, 0.0)

        t = quadratic_bezier_parameter_for_point(p0, p_meio, p2)
        controle = quadratic_bezier_control_for_point(p0, p_meio, p2)
        x, y = _bezier(p0, controle, p2, t)

        self.assertNotAlmostEqual(t, 0.5)
        self.assertAlmostEqual(x, p_meio[0], places=7)
        self.assertAlmostEqual(y, p_meio[1], places=7)

    def test_amostragem_insere_ponto_intermediario_sem_quebrar_vizinhos(self):
        p0 = (0.0, 0.0)
        p_meio = (3.0, -5.0)
        p2 = (10.0, 0.0)

        pontos = sample_quadratic_bezier_through_point(p0, p_meio, p2, 96)
        idx = pontos.index(p_meio)

        self.assertEqual(pontos[0], p0)
        self.assertGreater(len(pontos), 97)
        self.assertGreater(p_meio[0], pontos[idx - 1][0])
        self.assertLess(p_meio[0], pontos[idx + 1][0])
        self.assertLess(abs(pontos[idx - 1][1] - p_meio[1]), 0.25)
        self.assertLess(abs(pontos[idx + 1][1] - p_meio[1]), 0.25)
        self.assertEqual(pontos[-1], p2)

    def test_bezier_quadratica_usa_amostras_padrao_no_contorno(self):
        pontos = polyline_from_element(
            {
                "tipo": "bezier_quadratica",
                "p0": (0.0, 0.0),
                "p1": (5.0, 4.0),
                "p2": (10.0, 0.0),
            }
        )

        self.assertEqual(len(pontos), 25)


if __name__ == "__main__":
    unittest.main()
