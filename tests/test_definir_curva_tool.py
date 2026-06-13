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

    def assertContemPonto(self, pontos, esperado, casas=6):
        ex, ey = esperado
        self.assertTrue(
            any(abs(float(x) - ex) <= 10 ** -casas and abs(float(y) - ey) <= 10 ** -casas for x, y in pontos),
            f"{esperado} nao encontrado em {pontos}",
        )

    def test_quantidade_2_transforma_trecho_em_reta(self):
        canvas = _FakeCanvas()
        ferramenta = self._ferramenta("2")

        self.assertTrue(ferramenta._aplicar_trecho(canvas, 0, 0, 4))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][:3], [(0.0, 0.0), (4.0, 0.0), (8.0, 0.0)])
        self.assertNotIn((2.0, 1.0), molde["controle_auxiliares"])
        self.assertNotIn((4.0, 2.0), molde["controle_auxiliares"])
        self.assertNotIn((6.0, 1.0), molde["controle_auxiliares"])
        self.assertEqual(molde["controle_auxiliares"], [(4.0, 0.0)])
        self.assertEqual(molde["pontos_auxiliares"], [{"x": 4.0, "y": 0.0}])
        self.assertTrue(molde["pontos_tracado_real"])

    def test_quantidade_3_redistribui_auxiliares_no_tracado_original(self):
        canvas = _FakeCanvas()
        ferramenta = self._ferramenta("3")

        self.assertTrue(ferramenta._aplicar_trecho(canvas, 0, 0, 4))

        molde = canvas.cena.elementos[0]
        self.assertEqual(len(molde["controle_auxiliares"]), 3)
        self.assertEqual(molde["controle_auxiliares"][1], (4.0, 2.0))
        self.assertEqual(len(molde["pontos_auxiliares"]), 3)
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][-1], molde["pontos"][0])
        self.assertGreater(len(molde["pontos"]), 40)
        self.assertContemPonto(molde["pontos"], (8.0, 0.0))
        self.assertTrue(molde["pontos_tracado_real"])

    def test_preview_realca_trecho_e_auxiliares_sem_alterar_molde(self):
        canvas = _FakeCanvas()
        ferramenta = self._ferramenta("3")
        ferramenta._inicio = (0, 0, QPointF(0.0, 0.0))
        ferramenta._hover = (0, 4, QPointF(8.0, 0.0))
        pontos_antes = list(canvas.cena.elementos[0]["pontos"])

        preview = ferramenta._preview_trecho(canvas)

        self.assertIsNotNone(preview)
        self.assertEqual(len(preview["auxiliares"]), 3)
        self.assertEqual((preview["auxiliares"][1].x(), preview["auxiliares"][1].y()), (4.0, 2.0))
        self.assertGreater(len(preview["amostras"]), 40)
        self.assertEqual(canvas.cena.elementos[0]["pontos"], pontos_antes)

    def test_mudar_quantidade_na_caixa_repinta_preview_instantaneamente(self):
        FerramentaDefinirCurva._dlg_global = None
        FerramentaDefinirCurva._edt_pontos_global = None
        FerramentaDefinirCurva._canvas_preview_global = None
        FerramentaDefinirCurva._preview_signal_conectado = False
        canvas = _FakeCanvas()
        ferramenta = FerramentaDefinirCurva()

        try:
            ferramenta.on_activate(canvas)
            ferramenta._inicio = (0, 0, QPointF(0.0, 0.0))
            ferramenta._hover = (0, 4, QPointF(8.0, 0.0))
            canvas.atualizou = False

            self.assertTrue(ferramenta._edt_pontos.keyboardTracking())
            ferramenta._edt_pontos.setValue(4)

            self.assertTrue(canvas.atualizou)
            preview = ferramenta._preview_trecho(canvas)
            self.assertEqual(len(preview["auxiliares"]), 4)
        finally:
            ferramenta.on_deactivate(canvas)
            FerramentaDefinirCurva._dlg_global = None
            FerramentaDefinirCurva._edt_pontos_global = None
            FerramentaDefinirCurva._canvas_preview_global = None
            FerramentaDefinirCurva._preview_signal_conectado = False

    def test_trecho_fechado_usa_sentido_horario_visual(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0] = {
            "tipo": "polyline",
            "molde": True,
            "fechado": True,
            "pontos": [
                (0.0, 0.0),
                (0.0, 10.0),
                (10.0, 10.0),
                (10.0, 0.0),
                (0.0, 0.0),
            ],
            "controle_cantos": [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)],
            "controle_auxiliares": [],
            "pontos_auxiliares": [],
        }
        ferramenta = self._ferramenta("3")

        self.assertTrue(ferramenta._aplicar_trecho(canvas, 0, 0, 2))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 0.0), (10.0, 0.0), (10.0, 5.0)])
        self.assertNotIn((0.0, 5.0), molde["controle_auxiliares"])
        self.assertNotIn((0.0, 10.0), molde["controle_auxiliares"])


if __name__ == "__main__":
    unittest.main()
