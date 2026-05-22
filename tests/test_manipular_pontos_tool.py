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


class _FakeCheck:
    def __init__(self, checked=False):
        self._checked = checked

    def setChecked(self, checked):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked


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
        self.coordenadas_canceladas = False
        self.snap_override = None
        self.lbl_status = None

    def _ponto_com_snap(self, pos):
        if self.snap_override is not None:
            return QPointF(self.snap_override)
        return QPointF(pos)

    def _tela_para_cena(self, pos):
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

    def cancelar_operacao_coordenadas(self, limpar_preview=False):
        self.coordenadas_canceladas = bool(limpar_preview)


@unittest.skipIf(FerramentaManipularPontos is None, "PySide6 nao disponivel neste ambiente")
class ManipularPontosToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def assertContemPonto(self, pontos, esperado, casas=7):
        ex, ey = esperado
        self.assertTrue(
            any(abs(float(x) - ex) <= 10 ** -casas and abs(float(y) - ey) <= 10 ** -casas for x, y in pontos),
            f"{esperado} nao encontrado em {pontos}",
        )

    def assertPontoNaReta(self, ponto, inicio, fim, casas=6):
        px, py = ponto
        ax, ay = inicio
        bx, by = fim
        abx = bx - ax
        aby = by - ay
        den = (abx * abx) + (aby * aby)
        self.assertGreater(den, 1e-12)
        t = max(0.0, min(1.0, (((px - ax) * abx) + ((py - ay) * aby)) / den))
        proj_x = ax + (abx * t)
        proj_y = ay + (aby * t)
        dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5
        self.assertLessEqual(dist, 10 ** -casas, f"{ponto} nao esta sobre a reta {inicio}->{fim}")

    def test_um_auxiliar_fora_do_eixo_deforma_trecho_sem_mover_principais(self):
        ferramenta = FerramentaManipularPontos()

        pontos = ferramenta._amostrar_trecho_molde(
            [QPointF(0.0, 0.0), QPointF(5.0, 4.0), QPointF(10.0, 0.0)],
            segmentos=24,
        )

        self.assertEqual((pontos[0].x(), pontos[0].y()), (0.0, 0.0))
        self.assertEqual((pontos[-1].x(), pontos[-1].y()), (10.0, 0.0))
        self.assertGreaterEqual(len(pontos), 17)
        self.assertTrue(any(abs(p.x() - 5.0) <= 1e-7 and abs(p.y() - 4.0) <= 1e-7 for p in pontos))

    def test_dois_auxiliares_entre_principais_transformam_trecho_em_curva(self):
        ferramenta = FerramentaManipularPontos()

        pontos = ferramenta._amostrar_trecho_molde(
            [QPointF(0.0, 0.0), QPointF(3.0, 4.0), QPointF(7.0, 4.0), QPointF(10.0, 0.0)],
            segmentos=24,
        )

        self.assertGreater(len(pontos), 2)
        self.assertGreaterEqual(len(pontos), 31)
        self.assertGreater(max(p.y() for p in pontos), 1.0)

    def test_manipular_pontos_nao_abre_caixa_e_mover_ponto_mantem_caixa(self):
        if FerramentaMoverPonto is None:
            self.skipTest("tools.mover_ponto_tool nao disponivel neste checkout")
        canvas = _FakeCanvas()
        manipular = FerramentaManipularPontos()
        mover = FerramentaMoverPonto()

        manipular.on_activate(canvas)
        mover.on_activate(canvas)

        self.assertIsNone(manipular._dlg_passo)
        self.assertIsNotNone(mover._dlg_passo)
        self.assertEqual(mover._dlg_passo.windowTitle(), "Mover Ponto")
        self.assertEqual(mover._dlg_passo.objectName(), "guimma_mover_ponto_dialog")

    def test_mover_ponto_dx_dy_negativos_movem_para_esquerda_e_baixo(self):
        if FerramentaMoverPonto is None:
            self.skipTest("tools.mover_ponto_tool nao disponivel neste checkout")
        canvas = _FakeCanvas()
        ferramenta = FerramentaMoverPonto()
        ferramenta.on_activate(canvas)
        ferramenta._edt_dx.setText("-2")
        ferramenta._edt_dy.setText("-1")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (8.0, 1.0))
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 8.0, "y": 1.0})
        self.assertEqual(canvas.historico, 1)

    def test_mover_ponto_dx_dy_positivos_movem_para_direita_e_cima(self):
        if FerramentaMoverPonto is None:
            self.skipTest("tools.mover_ponto_tool nao disponivel neste checkout")
        canvas = _FakeCanvas()
        ferramenta = FerramentaMoverPonto()
        ferramenta.on_activate(canvas)
        ferramenta._edt_dx.setText("2")
        ferramenta._edt_dy.setText("1")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (12.0, -1.0))
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 12.0, "y": -1.0})
        self.assertEqual(canvas.historico, 1)

    def test_mover_ponto_opcao_varios_pontos_ativa_modo_n_pontos(self):
        if FerramentaMoverPonto is None:
            self.skipTest("tools.mover_ponto_tool nao disponivel neste checkout")
        canvas = _FakeCanvas()
        ferramenta = FerramentaMoverPonto()
        ferramenta.on_activate(canvas)

        ferramenta._cmb_n_pontos.setCurrentIndex(1)

        self.assertTrue(ferramenta._modo_n_pontos())

    def test_mover_ponto_auxiliar_em_reta_move_extremos_por_dx_dy(self):
        if FerramentaMoverPonto is None:
            self.skipTest("tools.mover_ponto_tool nao disponivel neste checkout")
        canvas = _FakeCanvas()
        ferramenta = FerramentaMoverPonto()
        ferramenta.on_activate(canvas)
        ferramenta._edt_dx.setText("0")
        ferramenta._edt_dy.setText("-2")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][0], (0.0, 2.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 2.0))
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))
        self.assertEqual(molde["pontos_controle_principais"][0], {"x": 0.0, "y": 2.0})
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 10.0, "y": 2.0})

    def test_arrasta_canto_principal_do_molde(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (12.0, 2.0))
        self.assertContemPonto(molde["pontos"], (12.0, 2.0))
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 12.0, "y": 2.0})
        self.assertPontoNaReta(molde["controle_auxiliares"][0], (0.0, 0.0), (12.0, 2.0))
        self.assertPontoNaReta(molde["controle_auxiliares"][1], (12.0, 2.0), (10.0, 5.0))
        self.assertEqual(molde["pontos_auxiliares"][0], {"x": molde["controle_auxiliares"][0][0], "y": molde["controle_auxiliares"][0][1]})
        self.assertEqual(canvas.historico, 1)
        self.assertEqual(molde["pontos"], [(0.0, 0.0), (12.0, 2.0), (10.0, 5.0), (0.0, 0.0)])

    def test_botao_direito_cancela_arraste_em_andamento_sem_gravar_historico(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))
        evento_cancelar = _FakeEvent(button=Qt.RightButton, pos=QPointF(12.0, 2.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, evento_cancelar))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (10.0, 0.0))
        self.assertEqual(molde["pontos"], [
            (0.0, 0.0),
            (5.0, 0.0),
            (10.0, 0.0),
            (10.0, 2.5),
            (10.0, 5.0),
            (5.0, 2.5),
            (0.0, 0.0),
        ])
        self.assertFalse(ferramenta._arraste_ativo())
        self.assertTrue(evento_cancelar.accepted)
        self.assertTrue(canvas.coordenadas_canceladas)
        self.assertEqual(canvas.historico, 0)

    def test_coordenadas_usam_origem_do_ponto_preso_na_manipulacao(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertEqual(ferramenta.origem_coordenadas(canvas), QPointF(10.0, 0.0))

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))
        self.assertEqual(ferramenta.origem_coordenadas(canvas), QPointF(10.0, 0.0))

    def test_arraste_de_controle_mantem_movimento_livre_sem_snap_angular(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 0.05))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(12.0, 0.05))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (12.0, 0.05))
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 12.0, "y": 0.05})

    def test_arraste_ignora_snap_de_borda_para_permitir_ajuste_fino(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        canvas.snap_override = QPointF(12.0, 0.0)
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 0.6))))
        canvas.snap_override = None
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(12.0, 0.6))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (12.0, 0.6))

    def test_arraste_de_controle_nao_trava_forte_no_angulo(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(12.0, 1.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (12.0, 1.0))

    def test_auxiliares_sao_atribuidos_por_proximidade_mesmo_com_mesma_quantidade_de_segmentos(self):
        ferramenta = FerramentaManipularPontos()
        cantos = [QPointF(0.0, 0.0), QPointF(5.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 10.0)]
        segmentos = [(0, 1), (1, 2), (2, 3)]
        auxiliares_fora_de_ordem = [QPointF(10.0, 5.0), QPointF(2.5, 0.0), QPointF(7.5, 0.0)]

        atribuicoes = ferramenta._atribuir_auxiliares_a_segmentos(
            cantos,
            segmentos,
            auxiliares_fora_de_ordem,
            preferir_ordem=False,
        )

        self.assertEqual([(p.x(), p.y()) for p in atribuicoes[0]], [(2.5, 0.0)])
        self.assertEqual([(p.x(), p.y()) for p in atribuicoes[1]], [(7.5, 0.0)])
        self.assertEqual([(p.x(), p.y()) for p in atribuicoes[2]], [(10.0, 5.0)])

    def test_mapa_de_auxiliares_usa_proximidade_mesmo_com_mesma_quantidade_de_segmentos(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (5.0, 10.0), (10.0, 0.0), (0.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (5.0, 10.0), (10.0, 0.0)],
                "controle_auxiliares": [(5.0, -2.0), (2.5, 5.0), (7.5, 5.0)],
            }
        )

        mapa = ferramenta._mapa_segmentos_auxiliares_molde(canvas, canvas.cena.elementos[0])

        self.assertEqual(mapa, [2, 0, 1])

    def test_arraste_de_canto_cruzando_linhas_preserva_trechos_auxiliares(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (3.0, 0.0),
                    (6.0, 0.0),
                    (10.0, 0.0),
                    (10.0, 5.0),
                    (10.0, 10.0),
                    (5.0, 5.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
                "controle_auxiliares": [(3.0, 0.0), (6.0, 0.0), (10.0, 5.0), (5.0, 5.0)],
                "pontos_auxiliares": [
                    {"x": 3.0, "y": 0.0},
                    {"x": 6.0, "y": 0.0},
                    {"x": 10.0, "y": 5.0},
                    {"x": 5.0, "y": 5.0},
                ],
            }
        )
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(0.0, 8.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 8.0))))

        molde = canvas.cena.elementos[0]
        cantos = [QPointF(float(x), float(y)) for x, y in molde["controle_cantos"]]
        segmentos = ferramenta._segmentos_cantos(cantos, True)
        auxiliares = [QPointF(float(x), float(y)) for x, y in molde["controle_auxiliares"]]
        atribuicoes = ferramenta._atribuir_auxiliares_por_mapa(cantos, segmentos, auxiliares, [0, 0, 1, 2])

        self.assertEqual(molde["controle_cantos"][1], (0.0, 8.0))
        self.assertEqual([(p.x(), p.y()) for p in atribuicoes[0]], [(3.0, 0.0), (6.0, 0.0)])
        self.assertEqual(len(atribuicoes[1]), 1)
        self.assertEqual(len(atribuicoes[2]), 1)
        self.assertPontoNaReta((atribuicoes[1][0].x(), atribuicoes[1][0].y()), molde["controle_cantos"][1], molde["controle_cantos"][2])
        self.assertPontoNaReta((atribuicoes[2][0].x(), atribuicoes[2][0].y()), molde["controle_cantos"][2], molde["controle_cantos"][0])

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
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))

        molde = canvas.cena.elementos[0]
        for esperado in [(12.0, 2.0), (10.0, 5.0)]:
            self.assertContemPonto(molde["pontos"], esperado)
        self.assertPontoNaReta(molde["controle_auxiliares"][0], (0.0, 0.0), (12.0, 2.0))
        self.assertPontoNaReta(molde["controle_auxiliares"][1], (12.0, 2.0), (10.0, 5.0))
        self.assertNotIn((5.0, 0.0), molde["pontos"])
        self.assertNotIn((10.0, 2.5), molde["pontos"])

    def test_arrasta_canto_nao_achata_auxiliar_curvo_para_reta(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (5.0, 2.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                "controle_auxiliares": [(5.0, 2.0), (10.0, 2.5), (5.0, 2.5)],
                "pontos_auxiliares": [
                    {"x": 5.0, "y": 2.0},
                    {"x": 10.0, "y": 2.5},
                    {"x": 5.0, "y": 2.5},
                ],
            }
        )
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(12.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][1], (12.0, 2.0))
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))
        self.assertGreater(
            ferramenta._distancia_ponto_segmento_local(
                QPointF(*molde["controle_auxiliares"][0]),
                QPointF(*molde["controle_cantos"][0]),
                QPointF(*molde["controle_cantos"][1]),
            ),
            0.5,
        )
        self.assertGreater(max(float(y) for _x, y in molde["pontos"]), 2.1)

    def test_arrasta_auxiliar_de_reta_move_extremos_da_reta(self):
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
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][0], (0.0, 2.0))
        for esperado in [(10.0, 2.0), (10.0, 5.0)]:
            self.assertContemPonto(molde["pontos"], esperado)
        self.assertEqual(molde["controle_cantos"], [(0.0, 2.0), (10.0, 2.0), (10.0, 5.0)])
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))

    def test_arrasta_ponto_auxiliar_em_reta_move_cantos_e_redefine_trecho(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))
        self.assertEqual(molde["pontos_auxiliares"][0], {"x": 5.0, "y": 2.0})
        self.assertEqual(molde["controle_cantos"][0], (0.0, 2.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 2.0))
        self.assertEqual(molde["pontos"][0], (0.0, 2.0))
        self.assertContemPonto(molde["pontos"], (10.0, 2.0))
        self.assertEqual(molde["pontos_controle_principais"][0], {"x": 0.0, "y": 2.0})
        self.assertEqual(molde["pontos_controle_principais"][1], {"x": 10.0, "y": 2.0})
        self.assertEqual(canvas.historico, 1)

    def test_arrasta_auxiliar_ja_fora_da_reta_preserva_cantos_e_deforma_curva(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (5.0, 2.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                "controle_auxiliares": [(5.0, 2.0), (10.0, 2.5), (5.0, 2.5)],
                "pontos_auxiliares": [
                    {"x": 5.0, "y": 2.0},
                    {"x": 10.0, "y": 2.5},
                    {"x": 5.0, "y": 2.5},
                ],
            }
        )
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 3.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 3.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][0], (0.0, 0.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 0.0))
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 3.0))
        self.assertContemPonto(molde["pontos"], (5.0, 3.0))

    def test_auxiliar_nao_ultrapassa_outro_auxiliar_do_mesmo_trecho(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, 0.0), (3.0, 0.0), (6.0, 0.0), (10.0, 0.0)],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                "controle_auxiliares": [(3.0, 0.0), (6.0, 0.0)],
                "pontos_auxiliares": [{"x": 3.0, "y": 0.0}, {"x": 6.0, "y": 0.0}],
            }
        )
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(3.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(8.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(8.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertLess(molde["controle_auxiliares"][0][0], molde["controle_auxiliares"][1][0])
        self.assertEqual(molde["controle_auxiliares"][1], (6.0, 0.0))
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0)])

    def test_curva_fechada_com_um_principal_regenera_pelos_auxiliares(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0] = {
            "tipo": "polyline",
            "molde": True,
            "fechado": True,
            "pontos": [(10.0, 0.0), (0.0, 5.0), (-10.0, 0.0), (0.0, -5.0), (10.0, 0.0)],
            "controle_cantos": [(10.0, 0.0)],
            "controle_auxiliares": [(0.0, 5.0), (-10.0, 0.0), (0.0, -5.0), (5.0, -2.0)],
            "pontos_auxiliares": [
                {"x": 0.0, "y": 5.0},
                {"x": -10.0, "y": 0.0},
                {"x": 0.0, "y": -5.0},
                {"x": 5.0, "y": -2.0},
            ],
        }
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 5.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(0.0, 8.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 8.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"], [(10.0, 0.0)])
        self.assertEqual(molde["controle_auxiliares"][0], (0.0, 8.0))
        self.assertContemPonto(molde["pontos"], (0.0, 8.0))
        self.assertEqual(molde["pontos"][0], molde["pontos"][-1])
        self.assertGreater(len(molde["pontos"]), 40)

    def test_nao_arrasta_vertice_intermediario_de_molde_fora_dos_controles(self):
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

        self.assertFalse(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(2.0, 1.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][1], (2.0, 1.0))
        self.assertEqual(molde["pontos"][0], (0.0, 0.0))
        self.assertEqual(molde["pontos"][2], (5.0, 0.0))
        self.assertEqual(molde["pontos"][3], (10.0, 0.0))
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(molde["pontos_principais"], [(0.0, 0.0), (10.0, 0.0)])
        controles_visiveis = [(p.x(), p.y()) for p in ferramenta._pontos_polyline_editaveis_molde(molde)]
        self.assertEqual(controles_visiveis, [(0.0, 0.0), (10.0, 0.0), (5.0, 0.0)])
        self.assertNotIn((2.0, 1.0), controles_visiveis)

    def test_shift_seleciona_varios_pontos_e_arrasta_juntos(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0), modifiers=Qt.ShiftModifier)))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 0.0), modifiers=Qt.ShiftModifier)))
        self.assertEqual(ferramenta._controles_selecionados, {(0, "canto", 0), (0, "canto", 1)})

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(2.0, 1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(2.0, 1.0))))

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
        ferramenta._chk_discreto = _FakeCheck()
        ferramenta._chk_discreto.setChecked(True)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(2.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertContemPonto(molde["pontos"], (2.0, 2.0))
        self.assertContemPonto(molde["pontos"], (10.0, 0.0))
        self.assertEqual(molde["controle_cantos"][0], (2.0, 2.0))
        self.assertEqual(molde["pontos_controle_principais"][0], {"x": 2.0, "y": 2.0})
        self.assertNotIn((5.0, 2.0), molde["pontos"])

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
        ferramenta._chk_discreto = _FakeCheck()
        ferramenta._chk_discreto.setChecked(True)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][0], (0.0, 2.0))
        self.assertContemPonto(molde["pontos"], (10.0, 2.0))
        self.assertEqual(molde["controle_cantos"][0], (0.0, 2.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 2.0))
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))

    def test_arraste_auxiliar_recalcula_a_partir_do_estado_inicial(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaManipularPontos()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, -20.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(5.0, 2.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["controle_cantos"][0], (0.0, 2.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 2.0))
        self.assertEqual(molde["pontos"][0], (0.0, 2.0))
        self.assertContemPonto(molde["pontos"], (10.0, 2.0))
        self.assertEqual(molde["controle_auxiliares"][0], (5.0, 2.0))


if __name__ == "__main__":
    unittest.main()
