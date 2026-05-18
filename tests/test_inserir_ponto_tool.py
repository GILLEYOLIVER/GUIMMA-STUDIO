from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaInserirPonto = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.inserir_ponto_tool import Ferramenta as FerramentaInserirPonto


class _FakeEvent:
    def __init__(self, pos):
        self._pos = pos
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.zoom = 20.0
        self._selecionados = set()
        self.historico = 0
        self.atualizou = False
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [
                        (0.0, 0.0),
                        (10.0, 0.0),
                        (10.0, 5.0),
                        (0.0, 0.0),
                    ],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                    "controle_auxiliares": [(10.0, 2.5)],
                    "pontos_controle_principais": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 10.0, "y": 0.0},
                        {"x": 10.0, "y": 5.0},
                    ],
                    "pontos_auxiliares": [{"x": 10.0, "y": 2.5}],
                }
            ]
        )

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _distancia_ponto_segmento(self, a, b, p):
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return ((p.x() - a.x()) ** 2 + (p.y() - a.y()) ** 2) ** 0.5
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / den))
        px = a.x() + (abx * t)
        py = a.y() + (aby * t)
        return ((p.x() - px) ** 2 + (p.y() - py) ** 2) ** 0.5

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaInserirPonto is None, "PySide6 nao disponivel neste ambiente")
class InserirPontoToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_inserir_ponto_em_molde_cria_auxiliar_manipulavel(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaInserirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][1], (5.0, 0.0))
        self.assertIn((5.0, 0.0), molde["controle_auxiliares"])
        self.assertIn({"x": 5.0, "y": 0.0}, molde["pontos_auxiliares"])
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 1)

    def test_inserir_ponto_em_curva_livre_sincroniza_controles(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0] = {
            "tipo": "polyline",
            "curva_suave": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "pontos_controle_curva": [(0.0, 0.0), (10.0, 0.0)],
            "pontos_principais": [(0.0, 0.0), (10.0, 0.0)],
        }
        ferramenta = FerramentaInserirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        curva = canvas.cena.elementos[0]
        self.assertEqual(curva["pontos"], [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)])
        self.assertEqual(curva["pontos_controle_curva"], curva["pontos"])
        self.assertEqual(curva["pontos_principais"], curva["pontos"])


if __name__ == "__main__":
    unittest.main()
