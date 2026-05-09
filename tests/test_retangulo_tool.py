from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaRetangulo = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.retangulo_tool import Ferramenta as FerramentaRetangulo


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
        self.cena = SimpleNamespace(elementos=[])
        self._selecionados = set()
        self._retangulo_criar_molde = True
        self._linha_cor = "#ff48a8"
        self._linha_espessura = 1.0
        self._linha_estilo = "solid"
        self._linha_amplitude = 1.0
        self.historico = 0
        self.atualizou = False

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaRetangulo is None, "PySide6 não disponível neste ambiente")
class RetanguloToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_retangulo_molde_cria_auxiliar_no_meio_de_cada_reta(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRetangulo()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 4.0))))

        self.assertEqual(len(canvas.cena.elementos), 1)
        molde = canvas.cena.elementos[0]
        auxiliares = molde["controle_auxiliares"]
        self.assertEqual(len(auxiliares), 4)
        self.assertIn((5.0, 0.0), auxiliares)
        self.assertIn((10.0, 2.0), auxiliares)
        self.assertIn((5.0, 4.0), auxiliares)
        self.assertIn((0.0, 2.0), auxiliares)
        self.assertEqual(molde["pontos_auxiliares"], [{"x": x, "y": y} for x, y in auxiliares])


if __name__ == "__main__":
    unittest.main()
