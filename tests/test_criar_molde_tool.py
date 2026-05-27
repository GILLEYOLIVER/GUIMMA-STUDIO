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
    FerramentaCriarMolde = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication

    from tools.criar_molde_tool import Ferramenta as FerramentaCriarMolde


class _FakeEvent:
    def __init__(self, pos: QPointF):
        self._pos = QPointF(pos)
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def position(self):
        return QPointF(self._pos)

    def accept(self):
        self.accepted = True


class _FakeCanvas:
    def __init__(self):
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                }
            ]
        )
        self._selecionados = set()
        self.historico = 0
        self.atualizou = False

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _indices_elementos_em_ponto(self, _pos):
        return [0]

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaCriarMolde is None, "PySide6 nao disponivel neste ambiente")
class CriarMoldeToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_criar_molde_nao_deixa_molde_novo_selecionado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaCriarMolde()
        event = _FakeEvent(QPointF(1.0, 1.0))

        self.assertTrue(ferramenta.on_mouse_press(canvas, event))

        self.assertTrue(canvas.cena.elementos[0]["molde"])
        self.assertEqual(canvas._selecionados, set())
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(event.accepted)


if __name__ == "__main__":
    unittest.main()
