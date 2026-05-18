from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaManipularPontos = None
    FerramentaMoverPonto = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos
    try:
        from tools.mover_ponto_tool import Ferramenta as FerramentaMoverPonto
    except ModuleNotFoundError:
        FerramentaMoverPonto = None


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


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [
                        (0.0, 0.0),
                        (5.0, 0.0),
                        (10.0, 0.0),
                        (10.0, 2.5),
                        (10.0, 5.0),
                        (5.0, 2.5),
                        (0.0, 0.0),
                    ],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                    "controle_auxiliares": [(5.0, 0.0), (10.0, 2.5), (5.0, 2.5)],
                    "pontos_controle_principais": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 10.0, "y": 0.0},
                        {"x": 10.0, "y": 5.0},
                    ],
                    "pontos_auxiliares": [
                        {"x": 5.0, "y": 0.0},
                        {"x": 10.0, "y": 2.5},
                        {"x": 5.0, "y": 2.5},
                    ],
                    "fio_origem": (2.0, 1.0),
                    "fio_fim": (8.0, 1.0),
                }
            ]
        )
        self.zoom = 20.0
        self._selecionados = {0}
        self._snap_resultado = None
        self.historico = 0
        self.atualizou = False
        self.lbl_status = None

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _dist(self, a, b):
        return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5

    def _indices_elementos_em_ponto(self, pos):
        return [0]

    def _registrar_historico(self):
        self.historico += 1

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def calcular_posicao_painel_auxiliar(self, largura, altura, abaixo_coordenadas=False):
        return QPointF(0.0, 0.0)

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaManipularPontos is None, "PySide6 não disponível neste ambiente")
class ManipularPontosToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_manipular_pontos_e_mover_ponto_tem_caixas_separadas(self):
        if FerramentaMoverPonto is None:
            self.skipTest("tools.mover_ponto_tool não disponível neste checkout")
        canvas = _FakeCanvas()
        manipular = FerramentaManipularPontos()
        mover = FerramentaMoverPonto()

        manipular.on_activate(canvas)
        mover.on_activate(canvas)

        self.assertIsNot(manipular._dlg_passo, mover._dlg_passo)
        self.assertEqual(manipular._dlg_passo.windowTitle(), "Manipular Pontos")
        self.assertEqual(manipular._dlg_passo.objectName(), "guimma_manipular_pontos_dialog")
        self.assertEqual(mover._dlg_passo.windowTitle(), "Mover Ponto")
        self.assertEqual(mover._dlg_passo.objectName(), "guimma_mover_ponto_dialog")

    def test_arrasta_canto_principal_do_molde(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (12.0, 2.0))
        self.assertEqual(molde["pontos"][2], (12.0, 2.0))
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 12.0, "y": 2.0})
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 0.0), (10.0, 2.5), (5.0, 2.5)])
        self.assertEqual(molde["pontos_auxiliares"], [{"x": 5.0, "y": 0.0}, {"x": 10.0, "y": 2.5}, {"x": 5.0, "y": 2.5}])
        self.assertEqual(canvas.historico, 1)

    def test_arrasta_canto_do_molde_respeita_auxiliares_vizinhos(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.5, 0.0),
                    (5.0, 0.0),
                    (7.5, 0.0),
                    (10.0, 0.0),
                    (10.0, 1.25),
                    (10.0, 2.5),
                    (10.0, 3.75),
                    (10.0, 5.0),
                    (5.0, 2.5),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                "controle_auxiliares": [(5.0, 0.0), (10.0, 2.5), (5.0, 2.5)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 10.0, "y": 5.0},
                ],
                "pontos_auxiliares": [
                    {"x": 5.0, "y": 0.0},
                    {"x": 10.0, "y": 2.5},
                    {"x": 5.0, "y": 2.5},
                ],
            }
        )
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][1], (2.5, 0.0))
        self.assertEqual(molde["pontos"][2], (5.0, 0.0))
        self.assertEqual(molde["pontos"][3], (8.5, 1.0))
        self.assertEqual(molde["pontos"][4], (12.0, 2.0))
        self.assertEqual(molde["pontos"][5], (11.0, 2.25))
        self.assertEqual(molde["pontos"][6], (10.0, 2.5))
        self.assertEqual(molde["pontos"][8], (10.0, 5.0))
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 0.0), (10.0, 2.5), (5.0, 2.5)])

    def test_arrasta_auxiliar_do_molde_deforma_so_trechos_vizinhos(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.5, 0.0),
                    (5.0, 0.0),
                    (7.5, 0.0),
                    (10.0, 0.0),
                    (10.0, 2.5),
                    (10.0, 5.0),
                    (5.0, 2.5),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                "controle_auxiliares": [(5.0, 0.0), (10.0, 2.5), (5.0, 2.5)],
                "pontos_auxiliares": [
                    {"x": 5.0, "y": 0.0},
                    {"x": 10.0, "y": 2.5},
                    {"x": 5.0, "y": 2.5},
                ],
            }
        )
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][1], (2.5, 1.5))
        self.assertEqual(molde["pontos"][2], (5.0, 2.0))
        self.assertEqual(molde["pontos"][3], (7.5, 1.5))
        self.assertEqual(molde["pontos"][4], (10.0, 0.0))
        self.assertEqual(molde["pontos"][5], (10.0, 2.5))
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)])
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))

    def test_arrasta_ponto_auxiliar_do_molde_preserva_cantos_e_redefine_trecho(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 2.0), (10.0, 2.5), (5.0, 2.5)])
        self.assertEqual(molde["pontos"][1], (5.0, 2.0))
        self.assertEqual(molde["pontos_auxiliares"], [{"x": 5.0, "y": 2.0}, {"x": 10.0, "y": 2.5}, {"x": 5.0, "y": 2.5}])
        self.assertEqual(molde["controle_cantos"][0], (0.0, 0.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 0.0))
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][2], (10.0, 0.0))
        self.assertEqual(molde["pontos_controle_principais"][0], {"x": 0.0, "y": 0.0})
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 10.0, "y": 0.0})
        self.assertEqual(canvas.historico, 1)

    def test_arrasta_vertice_intermediario_de_molde_suave_ponto_a_ponto(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "curva_suave": True,
                "tipo_curva": "spline_catmull_rom",
                "pontos": [
                    (0.0, 0.0),
                    (2.0, 1.0),
                    (5.0, 0.0),
                    (10.0, 0.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": [(5.0, 0.0)],
                "pontos_principais": [(0.0, 0.0), (10.0, 0.0)],
                "pontos_controle_curva": [(0.0, 0.0), (10.0, 0.0)],
            }
        )
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(2.0, 1.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(2.0, 3.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(2.0, 3.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][1], (2.0, 3.0))
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][2], (5.0, 0.0))
        self.assertEqual(molde["pontos"][3], (10.0, 0.0))
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(molde["pontos_principais"], [(0.0, 0.0), (10.0, 0.0)])

    def test_shift_seleciona_varios_pontos_e_arrasta_juntos(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0), modifiers=Qt.ShiftModifier)))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0), modifiers=Qt.ShiftModifier)))
        self.assertEqual(ferramenta._controles_selecionados, {(0, "canto", 0), (0, "canto", 1)})

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(2.0, 1.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(2.0, 1.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][0], (2.0, 1.0))
        self.assertEqual(molde["controle_cantos"][1], (12.0, 1.0))
        self.assertEqual(molde["pontos_controle_principais"][0], {"x": 2.0, "y": 1.0})
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 12.0, "y": 1.0})
        self.assertEqual(canvas.historico, 1)

    def test_modo_discreto_reajusta_pontos_curvos_ao_arrastar_canto(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0] = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [
                (0.0, 0.0),
                (5.0, 2.0),
                (10.0, 0.0),
                (10.0, 8.0),
                (0.0, 0.0),
            ],
            "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0)],
            "controle_auxiliares": [(5.0, 2.0), (10.0, 4.0), (5.0, 4.0)],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 8.0},
            ],
            "pontos_auxiliares": [
                {"x": 5.0, "y": 2.0},
                {"x": 10.0, "y": 4.0},
                {"x": 5.0, "y": 4.0},
            ],
            "fio_origem": (2.0, 1.0),
            "fio_fim": (8.0, 1.0),
        }
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)
        ferramenta._chk_discreto.setChecked(True)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(2.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][0], (2.0, 2.0))
        self.assertEqual(molde["pontos"][1], (5.0, 2.0))
        self.assertEqual(molde["pontos"][2], (10.0, 0.0))
        self.assertEqual(molde["controle_cantos"][0], (2.0, 2.0))
        self.assertEqual(molde["pontos_controle_principais"][0], {"x": 2.0, "y": 2.0})

    def test_modo_discreto_reajusta_curva_quando_auxiliar_move_trecho(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0] = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [
                (0.0, 0.0),
                (5.0, 0.0),
                (10.0, 0.0),
                (10.0, 8.0),
                (0.0, 0.0),
            ],
            "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0)],
            "controle_auxiliares": [(5.0, 0.0), (10.0, 4.0), (5.0, 4.0)],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 8.0},
            ],
            "pontos_auxiliares": [
                {"x": 5.0, "y": 0.0},
                {"x": 10.0, "y": 4.0},
                {"x": 5.0, "y": 4.0},
            ],
            "fio_origem": (2.0, 1.0),
            "fio_fim": (8.0, 1.0),
        }
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)
        ferramenta._chk_discreto.setChecked(True)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][1], (5.0, 2.0))
        self.assertEqual(molde["pontos"][2], (10.0, 0.0))
        self.assertEqual(molde["controle_cantos"][0], (0.0, 0.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 0.0))

    def test_arraste_auxiliar_recalcula_a_partir_do_estado_inicial(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, -20.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][0], (0.0, 0.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 0.0))
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][1], (5.0, 2.0))
        self.assertEqual(molde["pontos"][2], (10.0, 0.0))
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))


if __name__ == "__main__":
    unittest.main()
