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

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _dist(self, a, b):
        return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5

    def _indice_molde_em_ponto(self, pos):
        tolerancia = 10.0 / max(self.zoom, 0.001)
        for idx, el in enumerate(self.cena.elementos):
            if not el.get("molde"):
                continue
            for item in (el.get("controle_cantos", []) or []) + (el.get("controle_auxiliares", []) or []):
                pt = QPointF(float(item[0]), float(item[1]))
                if self._dist(pt, pos) <= tolerancia:
                    return idx
        return None

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaExcluirPonto is None, "PySide6 nao disponivel neste ambiente")
class ExcluirPontoToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_excluir_auxiliar_remove_controles_espelhados(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 0)
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

    def test_excluir_controle_limpa_hover_para_evitar_exclusao_em_cascata(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaExcluirPonto()
        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(5.0, 0.0)))

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        self.assertIsNone(ferramenta._hover_alvo)

    def test_excluir_auxiliares_em_sequencia_exige_apenas_mover_hover(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))
        self.assertEqual(canvas._selecionados, {0})

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))
        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(5.0, 2.5)))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 2.5))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_auxiliares"], [])
        self.assertEqual(molde["pontos_auxiliares"], [])
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 2)

    def test_busca_ponto_usa_cursor_real_mesmo_com_snap_deslocado(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        canvas._ponto_com_snap = lambda _pos: QPointF(99.0, 99.0)
        ferramenta = FerramentaExcluirPonto()

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

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        self.assertEqual(ferramenta._hover_alvo, ("molde", 0, "aux", 0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        self.assertEqual(molde["controle_auxiliares"], [(5.0, 2.5)])
        self.assertEqual(molde["pontos_auxiliares"], [{"x": 5.0, "y": 2.5}])

    def test_excluir_canto_bloqueia_molde_com_tres_principais(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaExcluirPonto()
        mensagens = []
        ferramenta.set_status = mensagens.append

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))
        self.assertEqual(canvas.historico, 0)
        self.assertFalse(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)])
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 0.0), (5.0, 2.5)])
        self.assertEqual(
            molde["pontos_controle_principais"],
            [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 10.0, "y": 5.0}],
        )
        self.assertIn("pelo menos 3 pontos principais", mensagens[-1])
        self.assertEqual(canvas.historico, 0)

    def test_excluir_canto_de_reta_remove_auxiliar_imediato_sem_criar_curva(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                "controle_auxiliares": [(5.0, 0.0), (10.0, 2.5), (5.0, 5.0), (0.0, 2.5)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 10.0, "y": 5.0},
                    {"x": 0.0, "y": 5.0},
                ],
                "pontos_auxiliares": [
                    {"x": 5.0, "y": 0.0},
                    {"x": 10.0, "y": 2.5},
                    {"x": 5.0, "y": 5.0},
                    {"x": 0.0, "y": 2.5},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 5.0), (0.0, 5.0)])
        self.assertNotIn((5.0, 0.0), molde["controle_auxiliares"])
        self.assertNotIn((10.0, 2.5), molde["controle_auxiliares"])
        self.assertIn((5.0, 2.5), molde["controle_auxiliares"])
        self.assertEqual(molde["pontos"], [(0.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)])

    def test_excluir_numero_2_do_retangulo_cria_reta_1_3_com_auxiliar_no_meio(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                "controle_auxiliares": [(5.0, 0.0), (10.0, 2.5), (5.0, 5.0), (0.0, 2.5)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 10.0, "y": 5.0},
                    {"x": 0.0, "y": 5.0},
                ],
                "pontos_auxiliares": [
                    {"x": 5.0, "y": 0.0},
                    {"x": 10.0, "y": 2.5},
                    {"x": 5.0, "y": 5.0},
                    {"x": 0.0, "y": 2.5},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 5.0), (0.0, 5.0)])
        self.assertEqual(
            molde["pontos_controle_principais"],
            [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 5.0}, {"x": 0.0, "y": 5.0}],
        )
        self.assertNotIn((5.0, 0.0), molde["controle_auxiliares"])
        self.assertNotIn((10.0, 2.5), molde["controle_auxiliares"])
        self.assertIn((5.0, 2.5), molde["controle_auxiliares"])
        self.assertIn((5.0, 5.0), molde["controle_auxiliares"])
        self.assertIn((0.0, 2.5), molde["controle_auxiliares"])
        self.assertEqual(molde["pontos"], [(0.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)])

    def test_excluir_auxiliar_de_curva_remove_apenas_o_ponto_confirmado(self):
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
                "controle_auxiliares": [(3.0, 2.2), (5.0, 2.8), (7.0, 2.2)],
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                "pontos_auxiliares": [
                    {"x": 3.0, "y": 2.2},
                    {"x": 5.0, "y": 2.8},
                    {"x": 7.0, "y": 2.2},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(3.0, 2.2))))
        self.assertEqual(canvas.historico, 0)
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(3.0, 2.2))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(len(molde["controle_cantos"]), 2)
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 2.8), (7.0, 2.2)])
        self.assertEqual(len(molde["pontos_auxiliares"]), len(molde["controle_auxiliares"]))

    def test_excluir_auxiliar_faz_trecho_curvo_voltar_para_reta_com_auxiliar_no_meio(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (3.0, 2.0),
                    (7.0, 2.0),
                    (10.0, 0.0),
                    (10.0, 2.5),
                    (10.0, 5.0),
                    (5.0, 5.0),
                    (0.0, 5.0),
                    (0.0, 2.5),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                "controle_auxiliares": [(3.0, 2.0), (7.0, 2.0), (10.0, 2.5), (5.0, 5.0), (0.0, 2.5)],
                "pontos_controle_principais": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 10.0, "y": 5.0},
                    {"x": 0.0, "y": 5.0},
                ],
                "pontos_auxiliares": [
                    {"x": 3.0, "y": 2.0},
                    {"x": 7.0, "y": 2.0},
                    {"x": 10.0, "y": 2.5},
                    {"x": 5.0, "y": 5.0},
                    {"x": 0.0, "y": 2.5},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(3.0, 2.0)))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(3.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 0.0))
        self.assertEqual(molde["pontos_auxiliares"][0], {"x": 5.0, "y": 0.0})
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertIn((10.0, 0.0), molde["pontos"])

    def test_excluir_auxiliar_em_molde_fechado_com_dois_cantos_preserva_arcos(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, -3.2),
                    (5.0, -4.0),
                    (8.0, -3.2),
                    (10.0, 0.0),
                    (8.0, 3.2),
                    (5.0, 4.0),
                    (2.0, 3.2),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": [
                    (2.0, -3.2),
                    (5.0, -4.0),
                    (8.0, -3.2),
                    (8.0, 3.2),
                    (5.0, 4.0),
                    (2.0, 3.2),
                ],
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                "pontos_auxiliares": [
                    {"x": 2.0, "y": -3.2},
                    {"x": 5.0, "y": -4.0},
                    {"x": 8.0, "y": -3.2},
                    {"x": 8.0, "y": 3.2},
                    {"x": 5.0, "y": 4.0},
                    {"x": 2.0, "y": 3.2},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -4.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -4.0))))

        molde = canvas.cena.elementos[0]
        self.assertNotIn((5.0, -4.0), molde["controle_auxiliares"])
        pontos = [QPointF(float(x), float(y)) for x, y in molde["pontos"]]
        idx_direita = min(range(len(pontos)), key=lambda i: canvas._dist(pontos[i], QPointF(10.0, 0.0)))
        arco_superior = pontos[1:idx_direita]
        arco_inferior = pontos[idx_direita + 1 : -1]
        self.assertTrue(arco_superior)
        self.assertTrue(arco_inferior)
        self.assertLessEqual(max(p.y() for p in arco_superior), 0.25)
        self.assertGreaterEqual(min(p.y() for p in arco_inferior), -0.25)

    def test_excluir_auxiliares_em_sequencia_reajusta_curva_sem_ziguezague(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, -3.2),
                    (5.0, -4.0),
                    (8.0, -3.2),
                    (10.0, 0.0),
                    (8.0, 3.2),
                    (5.0, 4.0),
                    (2.0, 3.2),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": [
                    (2.0, -3.2),
                    (5.0, -4.0),
                    (8.0, -3.2),
                    (8.0, 3.2),
                    (5.0, 4.0),
                    (2.0, 3.2),
                ],
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                "pontos_auxiliares": [
                    {"x": 2.0, "y": -3.2},
                    {"x": 5.0, "y": -4.0},
                    {"x": 8.0, "y": -3.2},
                    {"x": 8.0, "y": 3.2},
                    {"x": 5.0, "y": 4.0},
                    {"x": 2.0, "y": 3.2},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        pontos_para_excluir = (QPointF(5.0, -4.0), QPointF(8.0, -3.2), QPointF(8.0, 3.2))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pontos_para_excluir[0])))

        for ponto in pontos_para_excluir:
            ferramenta.on_mouse_move(canvas, _FakeEvent(ponto))
            self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(ponto)))

            molde = canvas.cena.elementos[0]
            pontos = [QPointF(float(x), float(y)) for x, y in molde["pontos"]]
            idx_direita = min(range(len(pontos)), key=lambda i: canvas._dist(pontos[i], QPointF(10.0, 0.0)))
            arco_superior = pontos[1:idx_direita]
            arco_inferior = pontos[idx_direita + 1 : -1]
            if arco_superior:
                self.assertLessEqual(max(p.y() for p in arco_superior), 0.35)
            if arco_inferior:
                self.assertGreaterEqual(min(p.y() for p in arco_inferior), -0.35)
            self.assertLessEqual(max(abs(p.y()) for p in pontos), 4.1)

    def test_excluir_auxiliar_fora_da_amostra_preserva_lado_do_arco(self):
        canvas = _FakeCanvas()
        canvas.zoom = 1000.0
        auxiliares = [
            (2.05, -3.25),
            (2.05, 3.25),
            (5.05, -4.05),
            (5.05, 4.05),
            (8.05, -3.25),
            (8.05, 3.25),
        ]
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, -3.2),
                    (5.0, -4.0),
                    (8.0, -3.2),
                    (10.0, 0.0),
                    (8.0, 3.2),
                    (5.0, 4.0),
                    (2.0, 3.2),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": auxiliares,
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                "pontos_auxiliares": [{"x": x, "y": y} for x, y in auxiliares],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.05, -4.05))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.05, -4.05))))

        molde = canvas.cena.elementos[0]
        pontos = [QPointF(float(x), float(y)) for x, y in molde["pontos"]]
        idx_direita = min(range(len(pontos)), key=lambda i: canvas._dist(pontos[i], QPointF(10.0, 0.0)))
        arco_superior = pontos[1:idx_direita]
        arco_inferior = pontos[idx_direita + 1 : -1]
        self.assertTrue(arco_superior)
        self.assertTrue(arco_inferior)
        self.assertLessEqual(max(p.y() for p in arco_superior), 0.35)
        self.assertGreaterEqual(min(p.y() for p in arco_inferior), -0.35)

    def test_excluir_principal_de_curva_permite_ficar_com_um_principal(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, -3.2),
                    (5.0, -4.0),
                    (8.0, -3.2),
                    (10.0, 0.0),
                    (8.0, 3.2),
                    (5.0, 4.0),
                    (2.0, 3.2),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": [
                    (2.0, -3.2),
                    (5.0, -4.0),
                    (8.0, -3.2),
                    (8.0, 3.2),
                    (5.0, 4.0),
                    (2.0, 3.2),
                ],
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                "pontos_auxiliares": [
                    {"x": 2.0, "y": -3.2},
                    {"x": 5.0, "y": -4.0},
                    {"x": 8.0, "y": -3.2},
                    {"x": 8.0, "y": 3.2},
                    {"x": 5.0, "y": 4.0},
                    {"x": 2.0, "y": 3.2},
                ],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(10.0, 0.0)))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0)])
        self.assertEqual(molde["pontos_controle_principais"], [{"x": 0.0, "y": 0.0}])
        self.assertEqual(len(molde["controle_auxiliares"]), 6)
        self.assertEqual(len(molde["pontos_auxiliares"]), 6)
        self.assertEqual(molde["pontos"][0], molde["pontos"][-1])
        self.assertGreater(len(molde["pontos"]), 20)
        self.assertEqual(canvas.historico, 1)

    def test_excluir_principal_de_curva_reordena_auxiliares_pelo_contorno(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        auxiliares_fora_de_ordem = [
            (8.0, 3.2),
            (2.0, -3.2),
            (5.0, 4.0),
            (8.0, -3.2),
            (2.0, 3.2),
            (5.0, -4.0),
        ]
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (2.0, -3.2),
                    (5.0, -4.0),
                    (8.0, -3.2),
                    (10.0, 0.0),
                    (8.0, 3.2),
                    (5.0, 4.0),
                    (2.0, 3.2),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": auxiliares_fora_de_ordem,
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                "pontos_auxiliares": [{"x": x, "y": y} for x, y in auxiliares_fora_de_ordem],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(10.0, 0.0)))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(
            molde["controle_auxiliares"],
            [
                (2.0, -3.2),
                (5.0, -4.0),
                (8.0, -3.2),
                (8.0, 3.2),
                (5.0, 4.0),
                (2.0, 3.2),
            ],
        )
        primeiros_pontos = [QPointF(float(x), float(y)) for x, y in molde["pontos"][1:12]]
        self.assertLess(max(p.y() for p in primeiros_pontos), 0.0)

    def test_excluir_principal_bloqueia_curva_com_apenas_um_principal(self):
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
                "controle_cantos": [(0.0, 0.0)],
                "controle_auxiliares": [(3.0, 2.2), (7.0, 2.2)],
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}],
                "pontos_auxiliares": [{"x": 3.0, "y": 2.2}, {"x": 7.0, "y": 2.2}],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0))))
        self.assertEqual(canvas.historico, 0)
        self.assertFalse(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0)])
        self.assertEqual(molde["controle_auxiliares"], [(3.0, 2.2), (7.0, 2.2)])
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][-1], (0.0, 0.0))
        self.assertEqual(canvas.historico, 0)

    def test_excluir_auxiliar_bloqueia_curva_no_minimo_de_um_principal_e_dois_auxiliares(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (3.0, 2.2),
                    (7.0, 2.2),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0)],
                "controle_auxiliares": [(3.0, 2.2), (7.0, 2.2)],
                "pontos_controle_principais": [{"x": 0.0, "y": 0.0}],
                "pontos_auxiliares": [{"x": 3.0, "y": 2.2}, {"x": 7.0, "y": 2.2}],
                "fechado": True,
            }
        )
        ferramenta = FerramentaExcluirPonto()
        mensagens = []
        ferramenta.set_status = mensagens.append

        ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(3.0, 2.2)))
        self.assertFalse(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(3.0, 2.2))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0)])
        self.assertEqual(molde["controle_auxiliares"], [(3.0, 2.2), (7.0, 2.2)])
        self.assertEqual(molde["pontos_auxiliares"], [{"x": 3.0, "y": 2.2}, {"x": 7.0, "y": 2.2}])
        self.assertEqual(canvas.historico, 0)
        self.assertIn("1 ponto principal e 2 pontos auxiliares", mensagens[-1])

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


if __name__ == "__main__":
    unittest.main()
