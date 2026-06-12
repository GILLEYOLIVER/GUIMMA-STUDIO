from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaTabela = None
    QApplication = None
    QPointF = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt, Signal
    from PySide6.QtWidgets import QApplication, QWidget

    from canvas.visualizacao import VisualizacaoCanvas
    from tools.tabela_tool import Ferramenta as FerramentaTabela


class _FakeMouseEvent:
    def __init__(self, pos: QPointF, *, modifiers=Qt.NoModifier):
        self._pos = QPointF(pos)
        self._modifiers = modifiers
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def position(self):
        return QPointF(self._pos)

    def modifiers(self):
        return self._modifiers

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    elementos_alterados = Signal()

    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "graduacao_tamanhos": [
                        {"ativo": True, "tamanho": "P", "cor": "#c87575", "base": False},
                        {"ativo": True, "tamanho": "M", "cor": "#ffff00", "base": True},
                        {"ativo": True, "tamanho": "G", "cor": "#5d95b7", "base": False},
                    ],
                }
            ]
        )
        self._selecionados = {0}
        self.zoom = 1.0
        self.historico = 0
        self.atualizou = False
        self.ferramenta_ativa = None
        self.lbl_status = None

    def _indice_molde_em_ponto(self, pos):
        return 0 if 0.0 <= pos.x() <= 10.0 and 0.0 <= pos.y() <= 5.0 else None

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True

    def set_ferramenta_ativa(self, nome):
        self.ferramenta_ativa = nome


@unittest.skipIf(FerramentaTabela is None, "PySide6 não disponível neste ambiente")
class TabelaToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_aplicar_salva_dx_dy_por_tamanho_no_ponto_do_contorno(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        ferramenta.selecionar_ponto(canvas, 1)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.tbl.item(0, 1).setText("-0.5")
        dialog.tbl.item(0, 2).setText("0.25")
        dialog.tbl.item(2, 1).setText("0.5")
        dialog.tbl.item(2, 2).setText("-0.25")

        ferramenta.aplicar_dialog(canvas)

        molde = canvas.cena.elementos[0]
        ponto = molde["graduacao_tabela"]["pontos"]["1"]
        self.assertEqual(ponto["numero"], 2)
        self.assertEqual(ponto["ponto"], (10.0, 0.0))
        self.assertEqual(ponto["valores"]["P"], {"dx": -0.5, "dy": 0.25})
        self.assertEqual(ponto["valores"]["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(ponto["valores"]["G"], {"dx": 0.5, "dy": -0.25})
        self.assertEqual(canvas.historico, 1)

    def test_pontos_contorno_remove_fechamento_duplicado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()

        pontos = ferramenta._pontos_contorno(canvas.cena.elementos[0])

        self.assertEqual(len(pontos), 3)
        self.assertEqual(pontos[0], QPointF(0.0, 0.0))
        self.assertEqual(pontos[-1], QPointF(10.0, 5.0))

    def test_seta_para_cima_distribui_dy_negativo_a_partir_da_base(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.setValue(1.0)

        dialog.btn_cima.click()

        valores = dialog.valores()
        self.assertEqual(valores["P"], {"dx": 0.0, "dy": 1.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 0.0, "dy": -1.0})

    def test_incremento_abre_limpo_e_formata_sem_zeros_sobrando(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        self.assertEqual(dialog.sp_incremento.text().strip(), "")
        for valor, texto in ((1.0, "1 cm"), (1.1, "1.1 cm"), (1.78, "1.78 cm"), (1.99, "1.99 cm"), (2.0, "2 cm")):
            dialog.sp_incremento.setValue(valor)
            self.assertEqual(dialog.sp_incremento.text(), texto)

    def test_tamanho_base_preserva_cor_e_realca_apenas_valores_dx_dy(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        item_tamanho = dialog.tbl.item(1, 0)
        self.assertEqual(item_tamanho.background().color().name().lower(), "#ffff00")
        self.assertEqual(item_tamanho.foreground().color().name().lower(), "#111111")
        self.assertTrue(item_tamanho.font().bold())
        for col in (1, 2):
            item = dialog.tbl.item(1, col)
            self.assertEqual(item.background().color().name().lower(), "#2b7cd3")
            self.assertEqual(item.foreground().color().name().lower(), "#ffffff")
            self.assertTrue(item.font().bold())

    def test_seta_de_um_eixo_preserva_graduacao_do_outro_eixo(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.setValue(1.0)

        dialog.btn_cima.click()
        dialog.btn_dir.click()

        valores = dialog.valores()
        self.assertEqual(valores["P"], {"dx": -1.0, "dy": 1.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 1.0, "dy": -1.0})

    def test_seta_incremental_com_base_maior_cria_apenas_para_dentro(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.definir_tamanhos(
            [
                {"ativo": True, "tamanho": "P", "cor": "#c87575", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#d60b0b", "base": False},
                {"ativo": True, "tamanho": "G", "cor": "#5d95b7", "base": True},
            ],
            {},
        )
        dialog.sp_incremento.setValue(1.0)

        dialog.btn_cima.click()

        valores = dialog.valores()
        self.assertEqual(valores["P"], {"dx": 0.0, "dy": 2.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 1.0})
        self.assertEqual(valores["G"], {"dx": 0.0, "dy": 0.0})

    def test_canvas_monta_contornos_graduados_com_dx_dy_da_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        ferramenta.selecionar_ponto(canvas, 1)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.setValue(1.0)
        dialog.btn_cima.click()
        ferramenta.aplicar_dialog(canvas)

        molde = canvas.cena.elementos[0]
        base = ferramenta._pontos_contorno(molde)
        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)

        nomes = [nome for nome, _cor, _pontos in contornos]
        self.assertEqual(nomes, ["P", "G"])
        contorno_p = contornos[0][2]
        contorno_g = contornos[1][2]
        self.assertEqual(contorno_p[0], QPointF(0.0, 1.0))
        self.assertEqual(contorno_p[1], QPointF(10.0, 1.0))
        self.assertEqual(contorno_g[0], QPointF(0.0, -1.0))
        self.assertEqual(contorno_g[1], QPointF(10.0, -1.0))
        self.assertEqual(contorno_g[-1], contorno_g[0])

    def test_ctrl_click_graduar_varios_pontos_sem_fechar_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        ev_p1 = _FakeMouseEvent(QPointF(0.0, 0.0))
        ev_p2 = _FakeMouseEvent(QPointF(10.0, 0.0), modifiers=Qt.ControlModifier)
        self.assertTrue(ferramenta.on_mouse_press(canvas, ev_p1))
        self.assertTrue(ferramenta.on_mouse_press(canvas, ev_p2))
        dialog.sp_incremento.setValue(1.0)
        dialog.btn_dir.click()
        ferramenta.aplicar_dialog(canvas)

        pontos = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]
        self.assertEqual(set(pontos.keys()), {"0", "1"})
        self.assertEqual(pontos["0"]["valores"]["P"], {"dx": -1.0, "dy": 0.0})
        self.assertEqual(pontos["1"]["valores"]["G"], {"dx": 1.0, "dy": 0.0})
        self.assertTrue(dialog.isVisible())
        self.assertEqual(ferramenta._pontos_selecionados, {0, 1})

    def test_clique_normal_substitui_pontos_selecionados_da_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(0.0, 0.0)))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0), modifiers=Qt.ControlModifier))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 5.0)))

        self.assertEqual(ferramenta._pontos_selecionados, {2})
        self.assertEqual(ferramenta._ponto_idx, 2)

    def test_janela_fecha_quando_molde_sai_do_canvas(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        self.assertTrue(dialog.isVisible())

        canvas.cena.elementos.clear()
        canvas._selecionados.clear()
        canvas.elementos_alterados.emit()

        self.assertFalse(dialog.isVisible())
        self.assertIsNone(ferramenta._molde_idx)


if __name__ == "__main__":
    unittest.main()
