from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaManipularPontos = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos


class _FakeEvent:
    def __init__(self, button=Qt.LeftButton, pos=None):
        self._button = button
        self._pos = pos or QPointF(0.0, 0.0)
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                    "controle_auxiliares": [(5.0, 0.0)],
                    "pontos_controle_principais": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 10.0, "y": 0.0},
                        {"x": 10.0, "y": 5.0},
                    ],
                    "pontos_auxiliares": [{"x": 5.0, "y": 0.0}],
                    "fio_origem": (2.0, 1.0),
                    "fio_fim": (8.0, 1.0),
                }
            ]
        )
        self.zoom = 20.0
        self._selecionados = {0}
        self._snap_resultado = None
        self.historico = 0
        self.atualizou = False
        self.lbl_status = None

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _dist(self, a, b):
        return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5

    def _indices_elementos_em_ponto(self, pos):
        return [0]

    def _registrar_historico(self):
        self.historico += 1

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def calcular_posicao_painel_auxiliar(self, largura, altura, abaixo_coordenadas=False):
        return QPointF(0.0, 0.0)

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaManipularPontos is None, "PySide6 não disponível neste ambiente")
class ManipularPontosToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_arrasta_canto_principal_do_molde(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (12.0, 2.0))
        self.assertEqual(molde["pontos"][2], (12.0, 2.0))
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 12.0, "y": 2.0})
        self.assertEqual(canvas.historico, 1)

    def test_arrasta_ponto_auxiliar_do_molde_move_cantos_vizinhos(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))
        self.assertEqual(molde["pontos"][1], (5.0, 2.0))
        self.assertEqual(molde["pontos_auxiliares"][0], {"x": 5.0, "y": 2.0})
        self.assertEqual(molde["controle_cantos"][0], (0.0, 2.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 2.0))
        self.assertEqual(molde["pontos"][0], (0.0, 2.0))
        self.assertEqual(molde["pontos"][2], (10.0, 2.0))
        self.assertEqual(molde["pontos_controle_principais"][0], {"x": 0.0, "y": 2.0})
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 10.0, "y": 2.0})
        self.assertEqual(canvas.historico, 1)


if __name__ == "__main__":
    unittest.main()
