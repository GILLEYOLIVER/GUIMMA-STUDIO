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
        self.zoom = 1.0
        self.snap_points = []
        self.ignorar_snap_movimento = []
        self.sombras_snap_movimento = []
        self.historico = 0
        self.atualizou = False
        self.rotacionar_duplo_clique = True

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _ponto_com_snap(self, pos):
        if self.snap_points:
            return QPointF(self.snap_points.pop(0))
        return QPointF(pos)

    def _ponto_com_snap_movimento(self, pos, ignorar_elementos=None, elementos_sombra=None):
        self.ignorar_snap_movimento.append(set(ignorar_elementos or []))
        self.sombras_snap_movimento.append(elementos_sombra)
        return self._ponto_com_snap(pos)

    def _indice_molde_em_ponto(self, pos):
        x = float(pos.x())
        y = float(pos.y())
        return 0 if -4.0 <= x <= 14.0 and -4.0 <= y <= 8.0 else None

    def _indices_elementos_em_ponto(self, pos):
        return [0]

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True

    def window(self):
        return SimpleNamespace(_opcoes_app={"rotacionar_duplo_clique": self.rotacionar_duplo_clique})

    def findChildren(self, _tipo):
        return []


@unittest.skipIf(FerramentaSelecionar is None, "PySide6 não disponível neste ambiente")
class SelecionarToolTestCase(unittest.TestCase):
    def test_duplo_clique_esquerdo_alinha_borda_ou_fio_em_0_ou_90(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaSelecionar()
        evento_borda = _FakeEvent(pos=QPointF(5.0, -1.0))
        molde = canvas.cena.elementos[0]
        molde["pontos"] = [(0.0, 0.0), (10.0, -2.0), (10.0, 4.0), (0.0, 0.0)]
        molde["controle_cantos"] = [(0.0, 0.0), (10.0, -2.0), (10.0, 4.0)]
        ang = math.radians(53.0)
        molde["fio_origem"] = (5.0, 2.0)
        molde["fio_fim"] = (5.0 + (math.cos(ang) * 4.0), 2.0 - (math.sin(ang) * 4.0))
        molde["fio_angulo"] = 53.0

        self.assertTrue(ferramenta.on_mouse_double_click(canvas, evento_borda))
        referencia_borda = {"tipo": "borda", "chave": "controle_cantos", "a_idx": 0, "b_idx": 1}
        self.assertAlmostEqual(ferramenta._angulo_referencia_alinhamento(molde, referencia_borda), 0.0)

        fo = molde["fio_origem"]
        ff = molde["fio_fim"]
        evento_fio = _FakeEvent(pos=QPointF((fo[0] + ff[0]) / 2.0, (fo[1] + ff[1]) / 2.0))

        self.assertTrue(ferramenta.on_mouse_double_click(canvas, evento_fio))
        self.assertEqual(molde["fio_angulo"], 0.0)
        self.assertAlmostEqual(ferramenta._angulo_fio_atual(molde), 0.0)
        self.assertEqual(ferramenta._eixo_fio_0_90_mais_proximo(179.0), 0.0)

        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 2)
        self.assertTrue(canvas.atualizou)
        self.assertTrue(evento_borda.accepted)
        self.assertTrue(evento_fio.accepted)

    def test_duplo_clique_nao_rotaciona_quando_opcao_desligada(self):
        canvas = _FakeCanvas()
        canvas.rotacionar_duplo_clique = False
        ferramenta = FerramentaSelecionar()
        molde = canvas.cena.elementos[0]
        fio_antes = molde["fio_angulo"]

        self.assertFalse(ferramenta.on_mouse_double_click(canvas, _FakeEvent(pos=QPointF(10.0, 2.0))))

        self.assertEqual(molde["fio_angulo"], fio_antes)
        self.assertEqual(canvas.historico, 0)

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
        self.assertEqual(ferramenta._originais_arraste[0]["pontos"][0], (0.0, 0.0))
        self.assertEqual(ferramenta._originais_arraste[1]["p0"], (20.0, 0.0))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(4.0, 3.0))))
        self.assertEqual(ferramenta._originais_arraste[0]["pontos"][0], (0.0, 0.0))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(4.0, 3.0))))

        molde = canvas.cena.elementos[0]
        curva = canvas.cena.elementos[1]
        self.assertEqual(molde["pontos"][0], (3.0, 2.0))
        self.assertEqual(molde["controle_cantos"][0], (3.0, 2.0))
        self.assertEqual(molde["fio_origem"], (3.0, 2.0))
        self.assertEqual(curva["p0"], (23.0, 2.0))
        self.assertEqual(curva["p1"], (28.0, 7.0))
        self.assertEqual(curva["p2"], (33.0, 2.0))
        self.assertEqual(ferramenta._originais_arraste, {})
        self.assertEqual(canvas.historico, 1)

    def test_arraste_de_selecao_usa_ponto_snapado_como_destino(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        canvas.snap_points = [QPointF(0.0, 0.0), QPointF(10.0, 0.0)]
        ferramenta = FerramentaSelecionar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(1.0, 1.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(4.0, 3.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][0], (10.0, 0.0))
        self.assertEqual(molde["controle_cantos"][0], (10.0, 0.0))
        self.assertEqual(canvas.ignorar_snap_movimento[-1], {0})
        self.assertEqual(canvas.sombras_snap_movimento[-1][0]["pontos"][0], (0.0, 0.0))

    def test_caixa_de_selecao_pega_elementos_que_cruzam_a_area(self):
        canvas = _FakeCanvas()
        canvas._indices_elementos_em_ponto = lambda _pos: []
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "pontos": [(-5.0, 2.0), (15.0, 2.0)],
            }
        )
        ferramenta = FerramentaSelecionar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(-20.0, -20.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(20.0, 10.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(20.0, 10.0))))

        self.assertEqual(canvas._selecionados, {0, 1})

    def test_arraste_sobre_elemento_nao_selecionado_abre_caixa_de_selecao(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "pontos": [(-5.0, 2.0), (15.0, 2.0)],
            }
        )
        ferramenta = FerramentaSelecionar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertEqual(canvas._selecionados, {0})
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(20.0, 10.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(20.0, 10.0))))

        self.assertEqual(canvas._selecionados, {0, 1})
        self.assertEqual(canvas.historico, 0)


if __name__ == "__main__":
    unittest.main()
