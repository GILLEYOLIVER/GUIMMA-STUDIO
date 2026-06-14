from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = SimpleNamespace(LeftButton=1, RightButton=2)
    QWidget = object
    FerramentaMultiplos = None
    MultiplosPiquesDialog = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.multiplos_tool import Ferramenta as FerramentaMultiplos
    from tools.multiplos_tool import MultiplosPiquesDialog


class _FakeCanvas(QWidget if QWidget is not object else object):
    def __init__(self):
        super().__init__()
        self.zoom = 20.0
        self.historico = 0
        self._selecionados = set()
        self.ferramenta_final = None
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0), (0.0, 0.0)],
                    "controle_auxiliares": [],
                    "pontos_auxiliares": [],
                }
            ]
        )

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def set_ferramenta_ativa(self, ferramenta):
        self.ferramenta_final = ferramenta

    def update(self):
        pass


class _FakeEvent:
    def __init__(self, pos: QPointF, button=Qt.LeftButton):
        self._pos = QPointF(pos)
        self._button = button
        self.accepted = False

    def position(self):
        return QPointF(self._pos)

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


@unittest.skipIf(FerramentaMultiplos is None, "PySide6 nao disponivel neste ambiente")
class MultiplosPiquesToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dialogo_opcoes_iniciais(self):
        dialog = MultiplosPiquesDialog()

        self.assertEqual(
            [dialog.cmb_modo.itemText(i) for i in range(dialog.cmb_modo.count())],
            ["Pontos do mouse", "Elemento", "Sobre o contorno"],
        )
        self.assertEqual(dialog.quantidade(), 10)
        self.assertEqual(dialog.largura(), 0.5)
        self.assertEqual(dialog.altura(), 0.3)
        self.assertEqual(dialog.cmb_tipo.currentText(), "T - forma T")

    def test_distribui_quantidade_no_contorno_com_um_historico(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaMultiplos()
        ferramenta._dialog = MultiplosPiquesDialog()
        ferramenta._dialog.cmb_modo.setCurrentText("Sobre o contorno")
        ferramenta._dialog.spn_quantidade.setValue(3)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0))))
        self.assertNotIn("piques_config", canvas.cena.elementos[0])

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(12.0, 0.0))))
        self.assertEqual(len(ferramenta._preview_pontos), 3)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(12.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(len(molde["piques_config"]), 3)
        self.assertTrue(all(cfg["sobre_contorno"] for cfg in molde["piques_config"]))
        self.assertEqual(canvas.historico, 1)
        self.assertEqual(canvas._selecionados, {0})
        self.assertIsNone(ferramenta._interativo)

    def test_pontos_do_mouse_interno_divide_linha_com_snap_angular(self):
        canvas = _FakeCanvas()
        canvas._snap_angular = lambda origem, destino, travar_principais=False: QPointF(destino.x(), origem.y())
        ferramenta = FerramentaMultiplos()
        ferramenta._dialog = MultiplosPiquesDialog()
        ferramenta._dialog.cmb_modo.setCurrentText("Pontos do mouse")
        ferramenta._dialog.spn_quantidade.setValue(2)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(6.0, 3.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(10.0, 5.0))))
        self.assertEqual([round(p.y(), 6) for p in ferramenta._preview_pontos], [3.0, 3.0])
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 5.0))))

        configs = canvas.cena.elementos[0]["piques_config"]
        self.assertEqual(len(configs), 2)
        self.assertTrue(all(not cfg["sobre_contorno"] for cfg in configs))
        self.assertEqual(canvas.cena.elementos[0]["controle_auxiliares"], [(7.333333333333333, 3.0), (8.666666666666666, 3.0)])


if __name__ == "__main__":
    unittest.main()
