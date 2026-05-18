from __future__ import annotations

import unittest

from core.geometry.engine import (
    quadratic_bezier_control_for_point,
    quadratic_bezier_parameter_for_point,
    sample_quadratic_bezier_through_point,
)


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

    def test_amostragem_forca_ponto_intermediario_clicado(self):
        p0 = (0.0, 0.0)
        p_meio = (3.0, -5.0)
        p2 = (10.0, 0.0)

        pontos = sample_quadratic_bezier_through_point(p0, p_meio, p2, 96)
        idx = round(quadratic_bezier_parameter_for_point(p0, p_meio, p2) * 96)

        self.assertEqual(pontos[0], p0)
        self.assertEqual(pontos[idx], p_meio)
        self.assertEqual(pontos[-1], p2)


if __name__ == "__main__":
    unittest.main()
