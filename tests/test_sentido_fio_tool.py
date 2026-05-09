from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaSentidoFio = None
    QPointF = None
    QApplication = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from canvas.snap import SnapManager
    from tools.sentido_fio_tool import Ferramenta as FerramentaSentidoFio


class _FakeEvent:
    def __init__(self, button, pos):
        self._button = button
        self._pos = pos
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
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                }
            ]
        )
        self.zoom = 1.0
        self._selecionados = {0}
        self._snap_resultado = None
        self._snap_candidatos = []
        self._snap_indice = 0
        self._snap_manager = SnapManager()
        self.lbl_status = None
        self.historico = 0
        self.atualizou = False

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _indice_molde_em_ponto(self, pos):
        return 0 if 0.0 <= pos.x() <= 10.0 and 0.0 <= pos.y() <= 5.0 else None

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaSentidoFio is None, "PySide6 não disponível neste ambiente")
class SentidoFioToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dois_pontos_definem_fio_no_molde(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaSentidoFio()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).cmb_modo.setCurrentText("Pontos do molde")

        inicio = _FakeEvent(Qt.LeftButton, QPointF(2.0, 1.0))
        fim = _FakeEvent(Qt.LeftButton, QPointF(8.0, 1.0))

        self.assertTrue(ferramenta.on_mouse_press(canvas, inicio))
        self.assertTrue(inicio.accepted)
        self.assertEqual(canvas._selecionados, {0})

        self.assertTrue(ferramenta.on_mouse_press(canvas, fim))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["fio_origem"], (2.0, 1.0))
        self.assertEqual(molde["fio_fim"], (8.0, 1.0))
        self.assertEqual(molde["fio_angulo"], 0.0)
        self.assertTrue(molde["mostrar_fio"])
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.atualizou)

    def test_modo_livre_nao_arredonda_angulo(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaSentidoFio()
        ferramenta.on_activate(canvas)

        fim, angulo = ferramenta._ponto_final_com_config(canvas, QPointF(2.0, 1.0), QPointF(8.0, 2.0))

        self.assertEqual(fim, QPointF(8.0, 2.0))
        self.assertAlmostEqual(angulo, 9.462322, places=5)


if __name__ == "__main__":
    unittest.main()
