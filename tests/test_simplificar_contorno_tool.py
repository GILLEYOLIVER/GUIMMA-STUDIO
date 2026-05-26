from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
    FerramentaSimplificarContorno = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.simplificar_contorno_tool import Ferramenta as FerramentaSimplificarContorno


class _FakeEvent:
    def __init__(self, pos=None, button=None):
        self._pos = pos or QPointF(0.0, 0.0)
        self._button = button if button is not None else Qt.LeftButton
        self.accepted = False

    def position(self):
        return self._pos

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.zoom = 10.0
        self._selecionados = set()
        self.historico = 0
        self.atualizou = False
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "molde_pronto": True,
                    "pontos": [
                        (0.0, 0.0),
                        (2.5, 0.0),
                        (5.0, 0.0),
                        (7.5, 0.0),
                        (10.0, 0.0),
                        (10.0, 2.5),
                        (10.0, 5.0),
                        (7.5, 5.0),
                        (5.0, 5.0),
                        (2.5, 5.0),
                        (0.0, 5.0),
                        (0.0, 2.5),
                        (0.0, 0.0),
                    ],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                    "controle_auxiliares": [(5.0, 0.0), (10.0, 2.5), (5.0, 5.0), (0.0, 2.5)],
                    "pontos_controle_principais": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 10.0, "y": 0.0},
                        {"x": 10.0, "y": 5.0},
                        {"x": 0.0, "y": 5.0},
                    ],
                    "pontos_auxiliares": [
                        {"x": 5.0, "y": 0.0},
                        {"x": 10.0, "y": 2.5},
                        {"x": 5.0, "y": 5.0},
                        {"x": 0.0, "y": 2.5},
                    ],
                }
            ]
        )

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True

    def _indices_elementos_em_ponto(self, pos):
        return [0]


@unittest.skipIf(FerramentaSimplificarContorno is None, "PySide6 nao disponivel neste ambiente")
class SimplificarContornoToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_simplificar_molde_remove_amostras_e_preserva_controles(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaSimplificarContorno()

        self.assertTrue(ferramenta._simplificar_elemento(canvas.cena.elementos[0], tolerancia=0.1))

        molde = canvas.cena.elementos[0]
        self.assertEqual(
            molde["pontos"],
            [
                (0.0, 0.0),
                (5.0, 0.0),
                (10.0, 0.0),
                (10.0, 2.5),
                (10.0, 5.0),
                (5.0, 5.0),
                (0.0, 5.0),
                (0.0, 2.5),
                (0.0, 0.0),
            ],
        )
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)])
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 0.0), (10.0, 2.5), (5.0, 5.0), (0.0, 2.5)])
        self.assertEqual(
            molde["pontos_controle_principais"],
            [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 5.0},
                {"x": 0.0, "y": 5.0},
            ],
        )
        self.assertEqual(
            molde["pontos_auxiliares"],
            [
                {"x": 5.0, "y": 0.0},
                {"x": 10.0, "y": 2.5},
                {"x": 5.0, "y": 5.0},
                {"x": 0.0, "y": 2.5},
            ],
        )

    def test_aplicar_em_selecao_registra_historico_uma_vez(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaSimplificarContorno()

        self.assertTrue(ferramenta._aplicar_em_indices(canvas, [0]))

        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.atualizou)
        self.assertEqual(canvas._selecionados, {0})

    def test_clique_sem_selecao_escolhe_contorno_e_aplica(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaSimplificarContorno()
        evento = _FakeEvent(QPointF(2.0, 0.0))

        self.assertTrue(ferramenta.on_mouse_press(canvas, evento))

        self.assertTrue(evento.accepted)
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 1)
        self.assertLess(len(canvas.cena.elementos[0]["pontos"]), 13)

    def test_linha_aberta_sem_controles_preserva_extremos(self):
        ferramenta = FerramentaSimplificarContorno()
        elemento = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (2.0, 0.02), (4.0, -0.01), (6.0, 0.0), (6.0, 5.0)],
        }

        self.assertTrue(ferramenta._simplificar_elemento(elemento, tolerancia=0.1))

        self.assertEqual(elemento["pontos"], [(0.0, 0.0), (6.0, 0.0), (6.0, 5.0)])


if __name__ == "__main__":
    unittest.main()
