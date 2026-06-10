from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    QLineEdit = None
    QWidget = None
    FerramentaDefinirCurva = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

    from tools.definir_curva_tool import Ferramenta as FerramentaDefinirCurva

_BaseWidget = QWidget if QWidget is not None else object


class _FakeCanvas(_BaseWidget):
    def __init__(self):
        super().__init__()
        self.zoom = 20.0
        self.historico = 0
        self.atualizou = False
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "fechado": True,
                    "pontos": [
                        (0.0, 0.0),
                        (2.0, 1.0),
                        (4.0, 2.0),
                        (6.0, 1.0),
                        (8.0, 0.0),
                        (8.0, 5.0),
                        (0.0, 0.0),
                    ],
                    "controle_cantos": [(0.0, 0.0), (8.0, 0.0), (8.0, 5.0)],
                    "controle_auxiliares": [(2.0, 1.0), (4.0, 2.0), (6.0, 1.0)],
                    "pontos_controle_principais": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 8.0, "y": 0.0},
                        {"x": 8.0, "y": 5.0},
                    ],
                    "pontos_auxiliares": [
                        {"x": 2.0, "y": 1.0},
                        {"x": 4.0, "y": 2.0},
                        {"x": 6.0, "y": 1.0},
                    ],
                }
            ]
        )

    def _dist(self, a, b):
        return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaDefinirCurva is None, "PySide6 nao disponivel neste ambiente")
class DefinirCurvaToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _ferramenta(self, valor: str):
        ferramenta = FerramentaDefinirCurva()
        ferramenta._edt_pontos = QLineEdit(valor)
        return ferramenta

    def test_quantidade_2_transforma_trecho_em_reta(self):
        canvas = _FakeCanvas()
        ferramenta = self._ferramenta("2")

        self.assertTrue(ferramenta._aplicar_trecho(canvas, 0, 0, 4))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][:2], [(0.0, 0.0), (8.0, 0.0)])
        self.assertNotIn((2.0, 1.0), molde["controle_auxiliares"])
        self.assertNotIn((4.0, 2.0), molde["controle_auxiliares"])
        self.assertNotIn((6.0, 1.0), molde["controle_auxiliares"])
        self.assertEqual(molde["pontos_auxiliares"], [])

    def test_quantidade_3_redistribui_auxiliares_no_tracado_original(self):
        canvas = _FakeCanvas()
        ferramenta = self._ferramenta("3")

        self.assertTrue(ferramenta._aplicar_trecho(canvas, 0, 0, 4))

        molde = canvas.cena.elementos[0]
        self.assertEqual(len(molde["controle_auxiliares"]), 3)
        self.assertEqual(molde["controle_auxiliares"][1], (4.0, 2.0))
        self.assertEqual(len(molde["pontos_auxiliares"]), 3)
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][4], (8.0, 0.0))


if __name__ == "__main__":
    unittest.main()
