from __future__ import annotations

import os
import unittest
from copy import deepcopy
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
    FerramentaRedefinirPerimetro = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.redefinir_perimetro_tool import Ferramenta as FerramentaRedefinirPerimetro


class _FakeEvent:
    def __init__(self, pos=None, button=None):
        self._pos = pos or QPointF(0.0, 0.0)
        self._button = button if button is not None else Qt.LeftButton
        self.accepted = False

    def position(self):
        return self._pos

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


def _segmento_coords(registro):
    a, b = registro[0], registro[1]
    return ((a.x(), a.y()), (b.x(), b.y()))


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "molde_pronto": True,
                    "pontos": [
                        (0.0, 0.0),
                        (5.0, 0.0),
                        (10.0, 0.0),
                        (10.0, 5.0),
                        (0.0, 5.0),
                        (0.0, 0.0),
                    ],
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
                }
            ]
        )
        self.zoom = 10.0
        self.historico = 0
        self.atualizou = False
        self.segmentos_desenhados = []
        self.ferramenta_ativa = None
        self.lbl_status = SimpleNamespace(texto="", setText=lambda texto: setattr(self.lbl_status, "texto", texto))

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def formatar_valor_unidade(self, valor):
        return f"{float(valor):.2f}"

    def calcular_posicao_painel_auxiliar(self, largura, altura, abaixo_coordenadas=False):
        return QPointF(0.0, 0.0)

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True

    def _desenhar_segmento(self, painter, a, b, tracejado=False, cor="#ffffff", espessura=1.0):
        self.segmentos_desenhados.append((a, b, tracejado, cor, espessura))

    def set_ferramenta_ativa(self, nome):
        self.ferramenta_ativa = nome


@unittest.skipIf(FerramentaRedefinirPerimetro is None, "PySide6 nao disponivel neste ambiente")
class RedefinirPerimetroToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_primeiro_clique_mostra_previa_segundo_aplica(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("14")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))
        self.assertEqual(canvas.historico, 0)
        self.assertEqual(dialog.ed_de.text(), "10.00")
        self.assertEqual(canvas.cena.elementos[0]["controle_cantos"][1], (14.0, 0.0))
        self.assertEqual(ferramenta._elemento_preview_por_canvas[id(canvas)]["controle_cantos"][1], (14.0, 0.0))

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))
        self.assertEqual(canvas.historico, 1)
        self.assertEqual(canvas.cena.elementos[0]["controle_cantos"][1], (14.0, 0.0))
        self.assertFalse(ferramenta._preview_ativo_por_canvas.get(id(canvas), False))
        self.assertNotIn(id(canvas), ferramenta._confirmacao_pendente_por_canvas)
        self.assertNotIn(id(canvas), ferramenta._elemento_preview_por_canvas)

    def test_digitacao_no_para_atualiza_previa_ao_vivo(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("14")

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        self.assertEqual(canvas.cena.elementos[0]["controle_cantos"][1], (14.0, 0.0))

        dialog.ed_para.setText("18")

        self.assertEqual(canvas.cena.elementos[0]["controle_cantos"][1], (18.0, 0.0))
        self.assertEqual(ferramenta._elemento_preview_por_canvas[id(canvas)]["controle_cantos"][1], (18.0, 0.0))
        self.assertTrue(ferramenta._preview_ativo_por_canvas.get(id(canvas), False))
        self.assertEqual(canvas.historico, 0)

    def test_abrir_ferramenta_zera_campos_e_estado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.ed_de.setText("10.00")
        dialog.ed_para.setText("14")
        chave = id(canvas)
        ferramenta._idx_por_canvas[chave] = 0
        ferramenta._preview_ativo_por_canvas[chave] = True
        ferramenta._snapshot_por_canvas[chave] = {"tipo": "polyline"}
        ferramenta._segmentos_iguais_por_canvas[chave] = [(QPointF(0.0, 0.0), QPointF(1.0, 0.0))]
        ferramenta._segmento_alvo_por_canvas[chave] = {"tipo": "pontos"}
        ferramenta._segmentos_originais_afetados_por_canvas[chave] = [(QPointF(0.0, 0.0), QPointF(1.0, 0.0))]
        ferramenta._confirmacao_pendente_por_canvas[chave] = True
        ferramenta._elemento_preview_por_canvas[chave] = {"tipo": "polyline"}

        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        self.assertEqual(dialog.ed_de.text(), "0")
        self.assertEqual(dialog.ed_para.text(), "0")
        self.assertNotIn(chave, ferramenta._idx_por_canvas)
        self.assertNotIn(chave, ferramenta._preview_ativo_por_canvas)
        self.assertNotIn(chave, ferramenta._snapshot_por_canvas)
        self.assertNotIn(chave, ferramenta._segmentos_iguais_por_canvas)
        self.assertNotIn(chave, ferramenta._segmento_alvo_por_canvas)
        self.assertNotIn(chave, ferramenta._segmentos_originais_afetados_por_canvas)
        self.assertNotIn(chave, ferramenta._confirmacao_pendente_por_canvas)
        self.assertNotIn(chave, ferramenta._elemento_preview_por_canvas)

    def test_aplicar_sem_linha_selecionada_nao_redefine_molde_inteiro(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("20")
        original = deepcopy(canvas.cena.elementos[0])

        ferramenta._aplicar(canvas)

        self.assertEqual(canvas.cena.elementos[0], original)
        self.assertFalse(ferramenta._preview_ativo_por_canvas.get(id(canvas), False))
        self.assertEqual(canvas.historico, 0)

    def test_primeiro_clique_com_para_zero_realca_linha_sem_alterar(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        ferramenta.on_paint_overlay(canvas, None)

        self.assertEqual(ferramenta._obter_dialog(canvas).ed_de.text(), "10.00")
        self.assertEqual(canvas.cena.elementos[0]["controle_cantos"][1], (10.0, 0.0))
        self.assertTrue(canvas.segmentos_desenhados)
        self.assertEqual(canvas.segmentos_desenhados[-1][3], "#2da8ff")

    def test_molde_pronto_redefine_apenas_linha_clicada(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("14")

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0)))

        molde = ferramenta._elemento_preview_por_canvas[id(canvas)]
        self.assertEqual(molde["controle_cantos"][0], (0.0, 0.0))
        self.assertEqual(molde["controle_cantos"][1], (14.0, 0.0))
        self.assertEqual(molde["controle_cantos"][2], (10.0, 5.0))
        self.assertEqual(molde["controle_cantos"][3], (0.0, 5.0))
        self.assertEqual(molde["controle_auxiliares"][0], (7.0, 0.0))
        self.assertEqual(molde["controle_auxiliares"][1], (10.0, 2.5))
        self.assertIn((14.0, 0.0), molde["pontos"])
        self.assertNotIn((14.0, 5.0), molde["pontos"])

    def test_unidirecional_usa_ponto_mais_longe_do_clique_como_base(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Uni-direcional")
        dialog.ed_para.setText("14")

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 0.0)))
        molde = ferramenta._elemento_preview_por_canvas[id(canvas)]
        self.assertEqual(molde["controle_cantos"][0], (-4.0, 0.0))
        self.assertEqual(molde["controle_cantos"][1], (10.0, 0.0))
        self.assertEqual(molde["controle_auxiliares"][0], (3.0, 0.0))

        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Uni-direcional")
        dialog.ed_para.setText("14")

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(8.0, 0.0)))
        molde = ferramenta._elemento_preview_por_canvas[id(canvas)]
        self.assertEqual(molde["controle_cantos"][0], (0.0, 0.0))
        self.assertEqual(molde["controle_cantos"][1], (14.0, 0.0))
        self.assertEqual(molde["controle_auxiliares"][0], (7.0, 0.0))

    def test_previa_realca_novo_perimetro_em_azul(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("14")

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        ferramenta.on_paint_overlay(canvas, None)

        self.assertTrue(canvas.segmentos_desenhados)
        self.assertEqual(canvas.segmentos_desenhados[-1][3], "#2da8ff")

    def test_overlay_mantem_posicoes_originais_afetadas_pontilhadas_e_previa_azul(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("14")

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        ferramenta.on_paint_overlay(canvas, None)

        originais = [seg for seg in canvas.segmentos_desenhados if seg[3] == "#f4f4f4"]
        self.assertEqual(len(originais), 2)
        self.assertIn(((0.0, 0.0), (10.0, 0.0)), [_segmento_coords(seg) for seg in originais])
        self.assertIn(((10.0, 0.0), (10.0, 5.0)), [_segmento_coords(seg) for seg in originais])
        previa = canvas.segmentos_desenhados[-1]
        self.assertTrue(previa[2])
        self.assertEqual(previa[3], "#2da8ff")
        self.assertEqual((previa[0].x(), previa[0].y()), (0.0, 0.0))
        self.assertEqual((previa[1].x(), previa[1].y()), (14.0, 0.0))

    def test_overlay_reaplica_previa_se_canvas_perder_estado_visual(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("14")
        original = deepcopy(canvas.cena.elementos[0])

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        ferramenta._segmentos_iguais_por_canvas.pop(id(canvas), None)
        canvas.cena.elementos[0] = original

        ferramenta.on_paint_overlay(canvas, None)

        self.assertEqual(canvas.cena.elementos[0]["controle_cantos"][1], (14.0, 0.0))
        self.assertTrue(canvas.segmentos_desenhados)
        self.assertEqual(canvas.segmentos_desenhados[-1][3], "#2da8ff")

    def test_botao_direito_cancela_previa_e_restaura_linha(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("14")
        original = deepcopy(canvas.cena.elementos[0])

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0)))
        self.assertNotEqual(canvas.cena.elementos[0], original)
        self.assertNotEqual(ferramenta._elemento_preview_por_canvas[id(canvas)], original)

        evento = _FakeEvent(QPointF(5.0, 0.0), button=Qt.RightButton)
        self.assertTrue(ferramenta.on_mouse_press(canvas, evento))

        self.assertTrue(evento.accepted)
        self.assertEqual(canvas.cena.elementos[0], original)
        self.assertEqual(dialog.ed_de.text(), "0")
        self.assertEqual(dialog.ed_para.text(), "0")
        self.assertFalse(ferramenta._preview_ativo_por_canvas.get(id(canvas), False))
        self.assertNotIn(id(canvas), ferramenta._segmento_alvo_por_canvas)
        self.assertNotIn(id(canvas), ferramenta._segmentos_originais_afetados_por_canvas)
        self.assertNotIn(id(canvas), ferramenta._confirmacao_pendente_por_canvas)
        self.assertEqual(canvas.historico, 0)

    def test_dois_cliques_direitos_cancelam_e_soltem_ferramenta(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRedefinirPerimetro()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Manter extremos")
        dialog.ed_para.setText("14")

        ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0)))

        primeiro = _FakeEvent(QPointF(5.0, 0.0), button=Qt.RightButton)
        self.assertTrue(ferramenta.on_mouse_press(canvas, primeiro))
        self.assertTrue(primeiro.accepted)
        self.assertIsNone(canvas.ferramenta_ativa)
        self.assertFalse(ferramenta._preview_ativo_por_canvas.get(id(canvas), False))

        segundo = _FakeEvent(QPointF(5.0, 0.0), button=Qt.RightButton)
        self.assertTrue(ferramenta.on_mouse_press(canvas, segundo))
        self.assertTrue(segundo.accepted)
        self.assertEqual(canvas.ferramenta_ativa, "selecionar")


if __name__ == "__main__":
    unittest.main()
