from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaGirar = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.girar_tool import Ferramenta as FerramentaGirar


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
                    "pontos": [(0.0, 0.0), (10.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                    "pontos_controle_referencia": [(10.0, 0.0)],
                    "pontos_controle_principais": [{"x": 10.0, "y": 0.0}],
                    "pontos_auxiliares": [{"x": 5.0, "y": 0.0}],
                }
            ]
        )
        self._selecionados = {0}
        self.historico = 0
        self.atualizou = False
        self.ferramenta_ativa = None

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _indices_elementos_em_ponto(self, pos):
        return [0]

    def _registrar_historico(self):
        self.historico += 1

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def update(self):
        self.atualizou = True

    def set_ferramenta_ativa(self, nome):
        self.ferramenta_ativa = nome


@unittest.skipIf(FerramentaGirar is None, "PySide6 não disponível neste ambiente")
class GirarToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_girar_em_2_pontos_trava_e_confirma_em_angulo_principal(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaGirar()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).cmb_modo.setCurrentText("Girar em 2 pontos")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(7.0, -6.0))))

        ponto_girado = canvas.cena.elementos[0]["pontos"][1]
        self.assertAlmostEqual(ponto_girado[0], 7.0710678118654755)
        self.assertAlmostEqual(ponto_girado[1], -7.071067811865475)
        ponto_referencia = canvas.cena.elementos[0]["pontos_controle_referencia"][0]
        self.assertAlmostEqual(ponto_referencia[0], 7.0710678118654755)
        self.assertAlmostEqual(ponto_referencia[1], -7.071067811865475)
        ponto_principal = canvas.cena.elementos[0]["pontos_controle_principais"][0]
        self.assertAlmostEqual(ponto_principal["x"], 7.0710678118654755)
        self.assertAlmostEqual(ponto_principal["y"], -7.071067811865475)
        ponto_auxiliar = canvas.cena.elementos[0]["pontos_auxiliares"][0]
        self.assertAlmostEqual(ponto_auxiliar["x"], 3.5355339059327378)
        self.assertAlmostEqual(ponto_auxiliar["y"], -3.5355339059327373)
        self.assertEqual(ferramenta._angulo_preview_2p, 45.0)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(7.0, -6.0))))
        self.assertEqual(canvas.historico, 1)
        self.assertEqual(ferramenta._estado_2p, "pivo")

    def test_clique_direito_cancela_girar_em_2_pontos_sem_fechar(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaGirar()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).cmb_modo.setCurrentText("Girar em 2 pontos")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertEqual(ferramenta._estado_2p, "referencia")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(button=Qt.RightButton)))

        self.assertEqual(ferramenta._estado_2p, "pivo")
        self.assertIsNone(ferramenta._pivo_2p)
        self.assertIsNone(ferramenta._referencia_2p)
        self.assertEqual(canvas.historico, 0)
        self.assertIsNone(canvas.ferramenta_ativa)

    def test_clique_direito_cancela_preview_e_restaura_molde(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaGirar()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).cmb_modo.setCurrentText("Girar em 2 pontos")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(7.0, -6.0))))
        self.assertNotEqual(canvas.cena.elementos[0]["pontos"][1], (10.0, 0.0))

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(button=Qt.RightButton)))

        self.assertEqual(canvas.cena.elementos[0]["pontos"][1], (10.0, 0.0))
        self.assertEqual(ferramenta._estado_2p, "pivo")
        self.assertEqual(canvas.historico, 0)
        self.assertIsNone(canvas.ferramenta_ativa)


if __name__ == "__main__":
    unittest.main()
