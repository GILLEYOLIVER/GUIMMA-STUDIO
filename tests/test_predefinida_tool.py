from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaPredefinida = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from core.formatacao import formatar_numero
    from tools.predefinida_tool import Ferramenta as FerramentaPredefinida


class _FakeEvent:
    def __init__(self, pos, button=None):
        self._pos = pos
        self._button = button or Qt.LeftButton
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


_BaseWidget = QWidget if QWidget is not None else object


class _FakeCanvas(_BaseWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(elementos=[])
        self._linha_cor = "#00aaff"
        self._linha_espessura = 1.0
        self._linha_estilo = "solid"
        self._linha_amplitude = 1.0
        self._unidade_sigla = "cm"
        self.historico = 0
        self.atualizou = False

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def formatar_valor_unidade(self, valor):
        return formatar_numero(valor, 2)

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaPredefinida is None, "PySide6 nao disponivel neste ambiente")
class PredefinidaToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_segundo_clique_finaliza_curva_predefinida_no_canvas(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaPredefinida()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(8.0, 3.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(8.0, 3.0))))

        self.assertEqual(len(canvas.cena.elementos), 1)
        elemento = canvas.cena.elementos[0]
        self.assertEqual(elemento["tipo"], "polyline")
        self.assertEqual(elemento["subtipo_audaces"], "curva_predefinida")
        self.assertGreaterEqual(len(elemento["pontos"]), 2)
        self.assertEqual(canvas.historico, 1)


if __name__ == "__main__":
    unittest.main()
