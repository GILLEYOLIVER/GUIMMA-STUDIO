from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from math import cos, pi, sin

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaExtrairMolde = None
    QApplication = None
else:
    from PySide6.QtWidgets import QApplication

    from tools.extrair_molde_tool import Ferramenta as FerramentaExtrairMolde


@unittest.skipIf(FerramentaExtrairMolde is None, "PySide6 não disponível neste ambiente")
class ExtrairMoldeToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_enriquecer_molde_reto_insere_auxiliar_no_meio_de_cada_reta(self):
        ferramenta = FerramentaExtrairMolde()
        molde = {
            "tipo": "molde",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0), (0.0, 0.0)],
            "preservar_todos_vertices_controle": True,
        }

        ferramenta._enriquecer_metadados_molde(molde)

        auxiliares = molde["controle_auxiliares"]
        self.assertEqual(len(auxiliares), 4)
        self.assertIn((5.0, 0.0), auxiliares)
        self.assertIn((10.0, 2.0), auxiliares)
        self.assertIn((5.0, 4.0), auxiliares)
        self.assertIn((0.0, 2.0), auxiliares)
        self.assertEqual(molde["pontos_auxiliares"], [{"x": x, "y": y} for x, y in auxiliares])

    def test_auxiliares_detectados_na_curva_preservam_trecho_sem_ponto_extra(self):
        ferramenta = FerramentaExtrairMolde()
        base = [
            (0.0, 0.0),
            (5.0, 0.0),
            (10.0, 0.0),
            (10.0, 4.0),
            (0.0, 4.0),
        ]

        auxiliares = ferramenta._calcular_auxiliares_no_contorno(base, [0, 2, 3, 4])

        self.assertIn((5.0, 0.0), auxiliares)
        self.assertIn((10.0, 2.0), auxiliares)
        self.assertIn((5.0, 4.0), auxiliares)
        self.assertIn((0.0, 2.0), auxiliares)
        self.assertEqual(len(auxiliares), 4)

    def test_contorno_arredondado_recebe_mais_controles_principais(self):
        ferramenta = FerramentaExtrairMolde()
        pontos = [
            (10.0 + cos((2.0 * pi * i) / 48.0) * 5.0, 8.0 + sin((2.0 * pi * i) / 48.0) * 4.4)
            for i in range(48)
        ]
        molde = {"tipo": "molde", "pontos": [*pontos, pontos[0]]}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertGreaterEqual(len(molde["controle_cantos"]), 8)
        self.assertGreaterEqual(len(molde["controle_auxiliares"]), 8)

    def test_trecho_curvo_longo_recebe_multiplos_auxiliares(self):
        ferramenta = FerramentaExtrairMolde()
        trecho = [(float(x), (float(x) - 5.0) ** 2 * 0.18) for x in range(11)]

        auxiliares = ferramenta._auxiliares_para_trecho_curvo(trecho)

        self.assertGreaterEqual(len(auxiliares), 3)


if __name__ == "__main__":
    unittest.main()
