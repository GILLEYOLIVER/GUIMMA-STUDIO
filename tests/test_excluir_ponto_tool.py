from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaExcluirPonto = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.excluir_ponto_tool import Ferramenta as FerramentaExcluirPonto


class _FakeEvent:
    def __init__(self, pos):
        self._pos = pos
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.zoom = 20.0
        self._selecionados = set()
        self.historico = 0
        self.atualizou = False
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [
                        (0.0, 0.0),
                        (5.0, 0.0),
                        (10.0, 0.0),
                        (10.0, 5.0),
                        (0.0, 0.0),
                    ],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                    "controle_auxiliares": [(5.0, 0.0), (5.0, 2.5)],
                    "pontos_controle_principais": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 10.0, "y": 0.0},
                        {"x": 10.0, "y": 5.0},
                    ],
                    "pontos_auxiliares": [
                        {"x": 5.0, "y": 0.0},
                        {"x": 5.0, "y": 2.5},
                    ],
                }
            ]
        )

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _dist(self, a, b):
        return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaExcluirPonto is None, "PySide6 nao disponivel neste ambiente")
class ExcluirPontoToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _confirmar_molde(self, ferramenta, canvas, pos):
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos)))
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(ferramenta._molde_confirmado_idx, 0)

    def test_primeiro_clique_confirma_molde_sem_apagar(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaExcluirPonto()
        auxiliares = list(canvas.cena.elementos[0]["controle_auxiliares"])

        self._confirmar_molde(ferramenta, canvas, QPointF(5.0, 0.0))

        self.assertEqual(canvas.cena.elementos[0]["controle_auxiliares"], auxiliares)
        self.assertEqual(canvas.historico, 0)

    def test_excluir_auxiliar_remove_controles_espelhados(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaExcluirPonto()

        self._confirmar_molde(ferramenta, canvas, QPointF(5.0, 0.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertNotIn((5.0, 0.0), molde["pontos"])
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 2.5)])
        self.assertEqual(molde["pontos_auxiliares"], [{"x": 5.0, "y": 2.5}])
        self.assertEqual(canvas.historico, 1)

    def test_hover_em_molde_selecionado_trava_em_controle_proximo(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaExcluirPonto()

        alvo = ferramenta._controle_molde_em_ponto(canvas, QPointF(5.8, 0.0))

        self.assertEqual(alvo, (0, "aux", 0))

    def test_excluir_controle_trava_hover_no_proximo_controle(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaExcluirPonto()

        self._confirmar_molde(ferramenta, canvas, QPointF(5.0, 0.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        self.assertEqual(ferramenta._hover_alvo, ("molde", 0, "aux", 0))

    def test_excluir_canto_remove_controle_principal_espelhado(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0]["controle_cantos"] = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 5.0),
            (0.0, 5.0),
        ]
        canvas.cena.elementos[0]["controle_auxiliares"] = [
            (5.0, 0.0),
            (10.0, 2.5),
            (5.0, 5.0),
            (0.0, 2.5),
        ]
        ferramenta = FerramentaExcluirPonto()

        self._confirmar_molde(ferramenta, canvas, QPointF(10.0, 5.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 5.0))))

        molde = canvas.cena.elementos[0]
        self.assertNotIn((10.0, 5.0), molde["pontos"])
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0), (0.0, 5.0)])
        self.assertIn((5.0, 2.5), molde["controle_auxiliares"])
        self.assertNotIn((10.0, 2.5), molde["controle_auxiliares"])
        self.assertNotIn((5.0, 5.0), molde["controle_auxiliares"])
        self.assertEqual(
            molde["pontos_controle_principais"],
            [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 0.0, "y": 5.0}],
        )
        self.assertEqual(canvas.historico, 1)

    def test_excluir_canto_em_curva_mantem_trecho_curvo(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, 1.8),
                    (5.0, 3.0),
                    (8.0, 1.8),
                    (10.0, 0.0),
                    (12.0, 1.8),
                    (15.0, 3.0),
                    (18.0, 1.8),
                    (20.0, 0.0),
                    (20.0, 8.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (20.0, 8.0)],
                "controle_auxiliares": [(5.0, 3.0), (15.0, 3.0), (20.0, 4.0), (10.0, 4.0)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 20.0, "y": 0.0},
                    {"x": 20.0, "y": 8.0},
                ],
                "pontos_auxiliares": [
                    {"x": 5.0, "y": 3.0},
                    {"x": 15.0, "y": 3.0},
                    {"x": 20.0, "y": 4.0},
                    {"x": 10.0, "y": 4.0},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta._excluir_controle_molde(canvas, 0, "canto", 1))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (20.0, 0.0), (20.0, 8.0)])
        auxiliares_curva = [
            pt
            for pt in molde["controle_auxiliares"]
            if 0.0 < pt[0] < 20.0 and pt[1] > 0.1
        ]
        self.assertGreaterEqual(len(auxiliares_curva), 6)
        self.assertGreater(max(float(y) for _x, y in molde["pontos"]), 0.1)

    def test_excluir_canto_em_reta_bloqueia_minimo_de_tres_principais(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (10.0, 0.0), (0.0, 5.0), (0.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (0.0, 5.0)],
                "controle_auxiliares": [(5.0, 0.0), (5.0, 2.5), (0.0, 2.5)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 0.0, "y": 5.0},
                ],
                "pontos_auxiliares": [
                    {"x": 5.0, "y": 0.0},
                    {"x": 5.0, "y": 2.5},
                    {"x": 0.0, "y": 2.5},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self._confirmar_molde(ferramenta, canvas, QPointF(10.0, 0.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0), (0.0, 5.0)])
        self.assertEqual(canvas.historico, 0)

    def test_excluir_auxiliar_de_curva_com_dois_recompoe_tres_auxiliares(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, 1.8),
                    (5.0, 3.0),
                    (8.0, 1.8),
                    (10.0, 0.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": [(3.0, 2.2), (7.0, 2.2)],
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                "pontos_auxiliares": [{"x": 3.0, "y": 2.2}, {"x": 7.0, "y": 2.2}],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self._confirmar_molde(ferramenta, canvas, QPointF(3.0, 2.2))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(3.0, 2.2))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(len(molde["controle_cantos"]), 2)
        self.assertGreaterEqual(len(molde["controle_auxiliares"]), 3)
        self.assertEqual(len(molde["pontos_auxiliares"]), len(molde["controle_auxiliares"]))

    def test_excluir_canto_nao_permite_ficar_com_um_principal(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, 1.8),
                    (5.0, 3.0),
                    (8.0, 1.8),
                    (10.0, 0.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": [(3.0, 2.2), (7.0, 2.2)],
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                "pontos_auxiliares": [{"x": 3.0, "y": 2.2}, {"x": 7.0, "y": 2.2}],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self._confirmar_molde(ferramenta, canvas, QPointF(10.0, 0.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(canvas.historico, 0)

    def test_excluir_curva_editavel_remove_controle_e_nao_amostra(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0] = {
            "tipo": "polyline",
            "curva_editavel": True,
            "curva_suave": True,
            "pontos_tracado_real": True,
            "tipo_curva": "spline_catmull_rom",
            "pontos": [(0.0, 0.0), (2.0, 0.5), (5.0, 2.0), (8.0, 0.5), (10.0, 0.0)],
            "pontos_principais": [(0.0, 0.0), (5.0, 2.0), (10.0, 0.0)],
            "pontos_controle_curva": [(0.0, 0.0), (5.0, 2.0), (10.0, 0.0)],
            "pontos_controle_principais": [(0.0, 0.0), (5.0, 2.0), (10.0, 0.0)],
        }
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 2.0))))

        curva = canvas.cena.elementos[0]
        self.assertEqual(curva["pontos_principais"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(curva["pontos"], [(0.0, 0.0), (10.0, 0.0)])


if __name__ == "__main__":
    unittest.main()
