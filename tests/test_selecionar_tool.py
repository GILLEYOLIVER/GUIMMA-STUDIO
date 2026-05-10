from __future__ import annotations

import math
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

if find_spec("PySide6") is None:
    FerramentaSelecionar = None
    QPointF = None
    Qt = None
else:
    from PySide6.QtCore import QPointF, Qt

    from tools.selecionar_tool import Ferramenta as FerramentaSelecionar


class _FakeEvent:
    def __init__(self, button=Qt.LeftButton, pos=None, modifiers=Qt.NoModifier):
        self._button = button
        self._pos = pos or QPointF(0.0, 0.0)
        self._modifiers = modifiers
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return self._pos

    def modifiers(self):
        return self._modifiers

    def accept(self):
        self.accepted = True


class _FakeCanvas:
    def __init__(self):
        ang = math.radians(53.0)
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0)],
                    "fio_origem": (0.0, 0.0),
                    "fio_fim": (math.cos(ang) * 5.0, -(math.sin(ang) * 5.0)),
                    "fio_angulo": 53.0,
                }
            ]
        )
        self._selecionados = set()
        self._snap_resultado = None
        self.historico = 0
        self.atualizou = False

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _indice_molde_em_ponto(self, pos):
        return 0

    def _indices_elementos_em_ponto(self, pos):
        return [0]

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True

    def window(self):
        return SimpleNamespace(_opcoes_app={"rotacionar_duplo_clique": True})


@unittest.skipIf(FerramentaSelecionar is None, "PySide6 não disponível neste ambiente")
class SelecionarToolTestCase(unittest.TestCase):
    def test_duplo_clique_esquerdo_cicla_eixos_do_fio(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaSelecionar()
        evento = _FakeEvent()
        molde = canvas.cena.elementos[0]

        for esperado in (0.0, 270.0, 180.0, 90.0):
            self.assertTrue(ferramenta.on_mouse_double_click(canvas, evento))
            self.assertEqual(molde["fio_angulo"], esperado)
            self.assertAlmostEqual(ferramenta._angulo_fio_atual(molde), esperado)

        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 4)
        self.assertTrue(canvas.atualizou)
        self.assertTrue(evento.accepted)

    def test_arrastar_item_ja_selecionado_move_toda_selecao(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(
            {
                "tipo": "bezier_quadratica",
                "p0": (20.0, 0.0),
                "p1": (25.0, 5.0),
                "p2": (30.0, 0.0),
            }
        )
        canvas._selecionados = {0, 1}
        ferramenta = FerramentaSelecionar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(1.0, 1.0))))
        self.assertEqual(canvas._selecionados, {0, 1})
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(4.0, 3.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(4.0, 3.0))))

        molde = canvas.cena.elementos[0]
        curva = canvas.cena.elementos[1]
        self.assertEqual(molde["pontos"][0], (3.0, 2.0))
        self.assertEqual(molde["controle_cantos"][0], (3.0, 2.0))
        self.assertEqual(molde["fio_origem"], (3.0, 2.0))
        self.assertEqual(curva["p0"], (23.0, 2.0))
        self.assertEqual(curva["p1"], (28.0, 7.0))
        self.assertEqual(curva["p2"], (33.0, 2.0))
        self.assertEqual(canvas.historico, 1)


if __name__ == "__main__":
    unittest.main()
