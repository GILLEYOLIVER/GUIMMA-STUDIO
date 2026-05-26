from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    FerramentaDividirElementos = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.dividir_elementos_tool import Ferramenta as FerramentaDividirElementos


class _FakeLabel:
    def __init__(self):
        self.texto = ""

    def setText(self, texto):  # noqa: N802
        self.texto = texto


class _FakeEvent:
    def __init__(self, pos, modifiers=Qt.NoModifier, button=Qt.LeftButton):
        self._pos = QPointF(pos)
        self._modifiers = modifiers
        self._button = button
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return QPointF(self._pos)

    def modifiers(self):
        return self._modifiers

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.zoom = 20.0
        self._selecionados = set()
        self.historico = 0
        self.atualizou = False
        self.lbl_status = _FakeLabel()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)],
                    "cor": "#ffffff",
                }
            ]
        )

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaDividirElementos is None, "PySide6 nao disponivel neste ambiente")
class DividirElementosToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_ativacao_mostra_ajuda_de_uso(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDividirElementos()

        ferramenta.on_activate(canvas)

        self.assertIn("clique", canvas.lbl_status.texto.lower())
        self.assertIn("Shift", canvas.lbl_status.texto)

    def test_clique_em_polyline_aberta_divide_em_duas_partes(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDividirElementos()
        ferramenta.on_activate(canvas)
        evento = _FakeEvent(QPointF(5.0, 0.0), modifiers=Qt.ShiftModifier)

        self.assertTrue(ferramenta.on_mouse_press(canvas, evento))

        self.assertTrue(evento.accepted)
        self.assertEqual(len(canvas.cena.elementos), 2)
        self.assertEqual(canvas.cena.elementos[0]["pontos"], [(0.0, 0.0), (5.0, 0.0)])
        self.assertEqual(canvas.cena.elementos[1]["pontos"], [(5.0, 0.0), (10.0, 0.0), (20.0, 0.0)])
        self.assertEqual(canvas._selecionados, {0, 1})
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.atualizou)


if __name__ == "__main__":
    unittest.main()
