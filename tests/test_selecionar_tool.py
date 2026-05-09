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
        self.historico = 0
        self.atualizou = False

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _indice_molde_em_ponto(self, pos):
        return 0

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


if __name__ == "__main__":
    unittest.main()
