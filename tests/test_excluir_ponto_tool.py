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

_BaseWidget = QWidget if QWidget is not None else object


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


class _FakeCanvas(_BaseWidget):
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

    def _tela_para_cena(self, pos):
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
        canvas.cena.elementos[0]["pontos"] = [
            (0.0, 0.0),
            (2.0, 0.0),
            (5.0, 0.0),
            (8.0, 0.0),
            (10.0, 0.0),
            (10.0, 5.0),
            (0.0, 0.0),
        ]
        canvas.cena.elementos[0]["controle_auxiliares"] = [(2.0, 0.0), (5.0, 0.0), (8.0, 0.0), (5.0, 2.5)]
        canvas.cena.elementos[0]["pontos_auxiliares"] = [
            {"x": 2.0, "y": 0.0},
            {"x": 5.0, "y": 0.0},
            {"x": 8.0, "y": 0.0},
            {"x": 5.0, "y": 2.5},
        ]
        ferramenta = FerramentaExcluirPonto()

        self._confirmar_molde(ferramenta, canvas, QPointF(2.0, 0.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertNotIn((2.0, 0.0), molde["controle_auxiliares"])
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 0.0), (8.0, 0.0), (5.0, 2.5)])
        self.assertEqual(len(molde["pontos_auxiliares"]), len(molde["controle_auxiliares"]))
        self.assertEqual(canvas.historico, 1)

    def test_excluir_auxiliar_de_dois_regenera_tres_no_trecho(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (3.0, 2.0), (7.0, 2.0), (10.0, 0.0), (0.0, 5.0), (0.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (0.0, 5.0)],
                "controle_auxiliares": [(3.0, 2.0), (7.0, 2.0)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 0.0, "y": 5.0},
                ],
                "pontos_auxiliares": [{"x": 3.0, "y": 2.0}, {"x": 7.0, "y": 2.0}],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta._excluir_controle_molde(canvas, 0, "aux", 0))

        molde = canvas.cena.elementos[0]
        self.assertNotIn((3.0, 2.0), molde["controle_auxiliares"])
        self.assertEqual(len(molde["controle_auxiliares"]), 3)
        self.assertEqual(len(molde["pontos_auxiliares"]), 3)

    def test_excluir_auxiliar_de_quatro_em_curva_permite_ficar_com_tres(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (1.5, 0.8),
                    (3.5, 1.8),
                    (6.5, 1.8),
                    (8.5, 0.8),
                    (10.0, 0.0),
                    (0.0, 5.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (0.0, 5.0)],
                "controle_auxiliares": [(1.5, 0.8), (3.5, 1.8), (6.5, 1.8), (8.5, 0.8)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 0.0, "y": 5.0},
                ],
                "pontos_auxiliares": [
                    {"x": 1.5, "y": 0.8},
                    {"x": 3.5, "y": 1.8},
                    {"x": 6.5, "y": 1.8},
                    {"x": 8.5, "y": 0.8},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta._excluir_controle_molde(canvas, 0, "aux", 0))

        molde = canvas.cena.elementos[0]
        self.assertNotIn((1.5, 0.8), molde["controle_auxiliares"])
        self.assertEqual(molde["controle_auxiliares"], [(3.5, 1.8), (6.5, 1.8), (8.5, 0.8)])
        self.assertEqual(len(molde["pontos_auxiliares"]), 3)
        self.assertGreater(max(float(y) for _x, y in molde["pontos"]), 1.0)

    def test_excluir_auxiliar_de_tres_em_curva_permite_ficar_com_dois(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (2.0, 1.0), (5.0, 2.0), (8.0, 1.0), (10.0, 0.0), (0.0, 5.0), (0.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (0.0, 5.0)],
                "controle_auxiliares": [(2.0, 1.0), (5.0, 2.0), (8.0, 1.0)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 0.0, "y": 5.0},
                ],
                "pontos_auxiliares": [
                    {"x": 2.0, "y": 1.0},
                    {"x": 5.0, "y": 2.0},
                    {"x": 8.0, "y": 1.0},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta._excluir_controle_molde(canvas, 0, "aux", 0))

        molde = canvas.cena.elementos[0]
        self.assertNotIn((2.0, 1.0), molde["controle_auxiliares"])
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 2.0), (8.0, 1.0)])
        self.assertEqual(len(molde["pontos_auxiliares"]), 2)
        xs = sorted(float(x) for x, _y in molde["controle_auxiliares"])
        self.assertAlmostEqual(xs[0], 5.0, places=5)
        self.assertAlmostEqual(xs[1], 8.0, places=5)
        self.assertEqual(molde["pontos"][0], molde["pontos"][-1])
        self.assertGreater(max(float(y) for _x, y in molde["pontos"]), 1.0)

    def test_excluir_auxiliar_preserva_trechos_distantes_do_molde(self):
        canvas = _FakeCanvas()
        pontos_distantes = [(15.0, 4.0), (20.0, 8.0), (25.0, 4.0), (30.0, 0.0), (15.0, -5.0)]
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, 1.0),
                    (5.0, 2.0),
                    (8.0, 1.0),
                    (10.0, 0.0),
                    *pontos_distantes,
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (30.0, 0.0)],
                "controle_auxiliares": [(2.0, 1.0), (5.0, 2.0), (8.0, 1.0)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 30.0, "y": 0.0},
                ],
                "pontos_auxiliares": [
                    {"x": 2.0, "y": 1.0},
                    {"x": 5.0, "y": 2.0},
                    {"x": 8.0, "y": 1.0},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta._excluir_controle_molde(canvas, 0, "aux", 0))

        molde = canvas.cena.elementos[0]
        for ponto in pontos_distantes:
            self.assertIn(ponto, molde["pontos"])
        self.assertNotIn((2.0, 1.0), molde["controle_auxiliares"])
        self.assertEqual(len(molde["controle_auxiliares"]), 2)
        xs = sorted(float(x) for x, _y in molde["controle_auxiliares"])
        self.assertAlmostEqual(xs[0], 5.0, places=5)
        self.assertAlmostEqual(xs[1], 8.0, places=5)

    def test_hover_em_molde_selecionado_trava_em_controle_proximo(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaExcluirPonto()

        alvo = ferramenta._controle_molde_em_ponto(canvas, QPointF(5.8, 0.0))

        self.assertEqual(alvo, (0, "aux", 0))

    def test_busca_ponto_usa_cursor_real_mesmo_com_snap_deslocado(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        canvas._ponto_com_snap = lambda _pos: QPointF(99.0, 99.0)
        ferramenta = FerramentaExcluirPonto()
        ferramenta._molde_confirmado_idx = 0

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        self.assertEqual(ferramenta._hover_alvo, ("molde", 0, "aux", 0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        self.assertEqual(canvas.cena.elementos[0]["controle_auxiliares"], [(5.0, 2.5)])

    def test_excluir_auxiliar_tambem_encontra_pontos_auxiliares_espelhados(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        molde = canvas.cena.elementos[0]
        molde["controle_auxiliares"] = []
        molde["pontos_auxiliares"] = [{"x": 5.0, "y": 0.0}, {"x": 5.0, "y": 2.5}]
        ferramenta = FerramentaExcluirPonto()
        ferramenta._molde_confirmado_idx = 0

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        self.assertEqual(ferramenta._hover_alvo, ("molde", 0, "aux", 0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        self.assertEqual(molde["controle_auxiliares"], [(5.0, 2.5)])
        self.assertEqual(molde["pontos_auxiliares"], [{"x": 5.0, "y": 2.5}])

    def test_excluir_controle_trava_hover_no_proximo_controle(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0]["pontos"] = [
            (0.0, 0.0),
            (2.0, 0.0),
            (5.0, 0.0),
            (8.0, 0.0),
            (10.0, 0.0),
            (10.0, 5.0),
            (0.0, 0.0),
        ]
        canvas.cena.elementos[0]["controle_auxiliares"] = [(2.0, 0.0), (5.0, 0.0), (8.0, 0.0), (5.0, 2.5)]
        canvas.cena.elementos[0]["pontos_auxiliares"] = [
            {"x": 2.0, "y": 0.0},
            {"x": 5.0, "y": 0.0},
            {"x": 8.0, "y": 0.0},
            {"x": 5.0, "y": 2.5},
        ]
        canvas._selecionados = {0}
        ferramenta = FerramentaExcluirPonto()

        self._confirmar_molde(ferramenta, canvas, QPointF(2.0, 0.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 0.0))))

        self.assertIsNotNone(ferramenta._hover_alvo)
        self.assertEqual(ferramenta._hover_alvo[:3], ("molde", 0, "canto"))

    def test_excluir_canto_remove_controle_principal_espelhado(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0]["controle_cantos"] = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 5.0),
            (0.0, 5.0),
        ]
        canvas.cena.elementos[0]["pontos"] = [
            (0.0, 0.0),
            (5.0, 0.0),
            (10.0, 0.0),
            (10.0, 2.5),
            (10.0, 5.0),
            (5.0, 5.0),
            (0.0, 5.0),
            (0.0, 2.5),
            (0.0, 0.0),
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
        self.assertNotIn((10.0, 2.5), molde["controle_cantos"])
        self.assertGreaterEqual(len(molde["controle_auxiliares"]), 3)
        self.assertEqual(
            molde["pontos_controle_principais"],
            [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 0.0, "y": 5.0},
            ],
        )
        self.assertEqual(canvas.historico, 1)

    def test_excluir_canto_em_curva_recalcula_pelos_controles_restantes(self):
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
        self.assertNotIn((10.0, 0.0), molde["pontos"])
        self.assertIn((5.0, 3.0), molde["controle_auxiliares"])
        self.assertIn((15.0, 3.0), molde["controle_auxiliares"])
        self.assertIn((10.0, 4.0), molde["controle_auxiliares"])
        self.assertNotIn({"x": 10.0, "y": 4.0}, molde["pontos_controle_principais"])
        self.assertGreater(len(molde["pontos"]), len(molde["controle_cantos"]) + len(molde["controle_auxiliares"]))
        self.assertEqual(molde["pontos"][0], molde["pontos"][-1])
        self.assertGreater(max(float(y) for _x, y in molde["pontos"]), 2.5)

    def test_excluir_canto_em_curva_remapeia_graduacao_sem_criar_promovido(self):
        canvas = _FakeCanvas()
        pontos_graduacao = {
            "0": {
                "indice": 0,
                "numero": 1,
                "ponto": (0.0, 0.0),
                "valores": {"P": {"dx": 0.0, "dy": -2.0}, "M": {"dx": 0.0, "dy": 0.0}, "G": {"dx": 0.0, "dy": 2.0}},
            },
            "1": {
                "indice": 1,
                "numero": 2,
                "ponto": (10.0, 0.0),
                "valores": {"P": {"dx": 0.0, "dy": -3.0}, "M": {"dx": 0.0, "dy": 0.0}, "G": {"dx": 0.0, "dy": 3.0}},
            },
            "2": {
                "indice": 2,
                "numero": 3,
                "ponto": (20.0, 0.0),
                "valores": {"P": {"dx": 0.0, "dy": -4.0}, "M": {"dx": 0.0, "dy": 0.0}, "G": {"dx": 0.0, "dy": 4.0}},
            },
            "3": {
                "indice": 3,
                "numero": 4,
                "ponto": (20.0, 8.0),
                "valores": {"P": {"dx": 0.0, "dy": -6.0}, "M": {"dx": 0.0, "dy": 0.0}, "G": {"dx": 0.0, "dy": 6.0}},
            },
        }
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
                "graduacao_tamanhos": [
                    {"tamanho": "P", "ativo": True},
                    {"tamanho": "M", "ativo": True},
                    {"tamanho": "G", "ativo": True},
                ],
                "graduacao_tabela": {"modo": "dx_dy", "pontos": pontos_graduacao},
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta._excluir_controle_molde(canvas, 0, "canto", 1))

        molde = canvas.cena.elementos[0]
        pontos_cfg = molde["graduacao_tabela"]["pontos"]
        cfg_por_ponto = {tuple(cfg["ponto"]): cfg for cfg in pontos_cfg.values()}
        self.assertEqual(set(cfg_por_ponto), set(molde["controle_cantos"]))
        self.assertNotIn((10.0, 0.0), cfg_por_ponto)
        self.assertNotIn((10.0, 4.0), cfg_por_ponto)
        self.assertIn((10.0, 4.0), molde["controle_auxiliares"])
        self.assertAlmostEqual(cfg_por_ponto[(20.0, 0.0)]["valores"]["G"]["dy"], 4.0, places=5)
        self.assertAlmostEqual(cfg_por_ponto[(20.0, 0.0)]["valores"]["P"]["dy"], -4.0, places=5)

    def test_excluir_canto_preserva_trechos_distantes_do_molde(self):
        canvas = _FakeCanvas()
        pontos_distantes = [(24.0, 6.0), (28.0, 0.0), (14.0, -5.0)]
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (4.0, 2.0),
                    (10.0, 0.0),
                    (16.0, 2.0),
                    (20.0, 0.0),
                    *pontos_distantes,
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (28.0, 0.0)],
                "controle_auxiliares": [(4.0, 2.0), (16.0, 2.0), (24.0, 6.0), (14.0, -5.0)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 20.0, "y": 0.0},
                    {"x": 28.0, "y": 0.0},
                ],
                "pontos_auxiliares": [
                    {"x": 4.0, "y": 2.0},
                    {"x": 16.0, "y": 2.0},
                    {"x": 24.0, "y": 6.0},
                    {"x": 14.0, "y": -5.0},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta._excluir_controle_molde(canvas, 0, "canto", 1))

        molde = canvas.cena.elementos[0]
        for ponto in pontos_distantes:
            self.assertIn(ponto, molde["pontos"])
        self.assertNotIn((10.0, 0.0), molde["controle_cantos"])

    def test_excluir_canto_em_reta_usa_auxiliares_restantes_como_controle(self):
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
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (5.0, 0.0), (0.0, 5.0)])
        self.assertNotIn((5.0, 0.0), molde["controle_auxiliares"])
        self.assertIn((5.0, 2.5), molde["controle_auxiliares"])
        self.assertIn({"x": 5.0, "y": 0.0}, molde["pontos_controle_principais"])
        self.assertNotIn((10.0, 0.0), molde["pontos"])
        self.assertEqual(molde["pontos"][0], molde["pontos"][-1])
        self.assertEqual(canvas.historico, 1)

    def test_excluir_auxiliar_de_curva_regenera_quando_ficaria_com_um(self):
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
        self.assertNotIn((3.0, 2.2), molde["controle_auxiliares"])
        self.assertEqual(len(molde["controle_auxiliares"]), 3)
        self.assertEqual(len(molde["pontos_auxiliares"]), len(molde["controle_auxiliares"]))
        self.assertEqual(molde["pontos"][0], molde["pontos"][-1])

    def test_excluir_auxiliar_recalcula_contorno_pelos_controles_restantes(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (4.0, 1.0),
                    (9.0, 2.0),
                    (10.0, 0.0),
                    (0.0, 10.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)],
                "controle_auxiliares": [(9.0, 2.0), (5.0, 5.0), (0.0, 5.0)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 0.0, "y": 10.0},
                ],
                "pontos_auxiliares": [
                    {"x": 9.0, "y": 2.0},
                    {"x": 5.0, "y": 5.0},
                    {"x": 0.0, "y": 5.0},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()
        self.assertTrue(ferramenta._excluir_controle_molde(canvas, 0, "aux", 0))

        molde = canvas.cena.elementos[0]
        self.assertNotIn((9.0, 2.0), molde["pontos"])
        self.assertNotIn((4.0, 1.0), molde["pontos"])
        self.assertIn((10.0, 0.0), molde["pontos"])
        self.assertGreater(len(molde["pontos"]), len(molde["controle_cantos"]) + len(molde["controle_auxiliares"]))
        self.assertNotIn((9.0, 2.0), molde["controle_auxiliares"])
        self.assertIn((5.0, 5.0), molde["controle_auxiliares"])
        self.assertIn((0.0, 5.0), molde["controle_auxiliares"])
        self.assertEqual(molde["pontos"][0], molde["pontos"][-1])

    def test_excluir_canto_promove_auxiliar_mais_proximo(self):
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
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (7.0, 2.2)])
        self.assertEqual(molde["controle_auxiliares"], [(3.0, 2.2)])
        self.assertIn({"x": 7.0, "y": 2.2}, molde["pontos_controle_principais"])
        self.assertNotIn((10.0, 0.0), molde["pontos"])
        self.assertEqual(molde["pontos"][0], molde["pontos"][-1])
        self.assertEqual(canvas.historico, 1)

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
        self.assertEqual(canvas._selecionados, {0})
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 2.0))))

        curva = canvas.cena.elementos[0]
        self.assertEqual(curva["pontos_principais"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(curva["pontos"], [(0.0, 0.0), (10.0, 0.0)])

    def test_elemento_livre_primeiro_clique_seleciona_segundo_exclui_vertice(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0] = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)],
        }
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 0)

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        self.assertEqual(canvas.cena.elementos[0]["pontos"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(canvas.historico, 1)

    def test_regenerar_tracado_curva_molde_usa_cpp_quando_disponivel(self):
        import tools.excluir_ponto_tool as modulo

        chamadas = []
        original = modulo.sample_catmull_rom_centripetal_dynamic_cpp

        def fake_cpp(controles, closed=False):
            chamadas.append((list(controles), bool(closed)))
            return [(0.0, 0.0), (5.0, 2.0), (10.0, 0.0)]

        modulo.sample_catmull_rom_centripetal_dynamic_cpp = fake_cpp
        try:
            ferramenta = FerramentaExcluirPonto()
            resultado = ferramenta._gerar_tracado_curva_molde(
                [QPointF(0.0, 0.0), QPointF(5.0, 2.0), QPointF(10.0, 0.0)],
                fechado=True,
            )
        finally:
            modulo.sample_catmull_rom_centripetal_dynamic_cpp = original

        self.assertEqual(resultado, [(0.0, 0.0), (5.0, 2.0), (10.0, 0.0)])
        self.assertEqual(chamadas, [([(0.0, 0.0), (5.0, 2.0), (10.0, 0.0)], True)])


if __name__ == "__main__":
    unittest.main()
