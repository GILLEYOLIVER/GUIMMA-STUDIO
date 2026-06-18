from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = object
    FerramentaMouse = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.mouse_tool import Ferramenta as FerramentaMouse


class _FakeMouseEvent:
    def __init__(self, pos: QPointF, *, button=None):
        self._pos = QPointF(pos)
        self._button = button if button is not None else Qt.LeftButton
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return QPointF(self._pos)

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
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "graduacao_tamanhos": [
                        {"ativo": True, "tamanho": "PP", "cor": "#00ff00", "base": False},
                        {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                        {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                        {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
                        {"ativo": True, "tamanho": "GG", "cor": "#ff00ff", "base": False},
                    ],
                }
            ]
        )
        self._selecionados = set()
        self.zoom = 30.0
        self.historico = 0
        self.atualizou = False
        self.ferramenta_ativa = None
        self.lbl_status = None

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def _indice_molde_em_ponto(self, pos):
        return 0 if 0.0 <= pos.x() <= 10.0 and 0.0 <= pos.y() <= 5.0 else None

    def _registrar_historico(self):
        self.historico += 1

    def set_ferramenta_ativa(self, ferramenta):
        self.ferramenta_ativa = ferramenta

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaMouse is None, "PySide6 nao disponivel neste ambiente")
class MouseToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        FerramentaMouse._dialog_por_canvas.clear()

    def test_dialogo_tem_modos_da_graduacao_manual(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaMouse()
        dialog = ferramenta._obter_dialog(canvas)

        self.assertEqual([dialog.cmb_modo.itemText(i) for i in range(dialog.cmb_modo.count())], ["Incremental", "Absoluto", "Proporcional"])
        self.assertEqual(dialog.cmb_modo.currentText(), "Incremental")

    def test_arrastar_ponto_aplica_incremental_em_tempo_real_e_registra_ao_soltar(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaMouse()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(12.0, 3.0))))

        valores = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]["1"]["valores"]
        self.assertEqual(valores["PP"], {"dx": -4.0, "dy": -6.0})
        self.assertEqual(valores["P"], {"dx": -2.0, "dy": -3.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 2.0, "dy": 3.0})
        self.assertEqual(valores["GG"], {"dx": 4.0, "dy": 6.0})
        self.assertEqual(canvas.historico, 0)

        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeMouseEvent(QPointF(12.0, 3.0))))
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.cena.elementos[0]["mostrar_graduacao"])

    def test_modo_absoluto_aplica_mesmo_deslocamento_em_tamanhos_nao_base(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaMouse()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Absoluto")

        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0)))
        ferramenta.on_mouse_release(canvas, _FakeMouseEvent(QPointF(13.0, -2.0)))

        valores = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]["1"]["valores"]
        self.assertEqual(valores["PP"], {"dx": 3.0, "dy": -2.0})
        self.assertEqual(valores["P"], {"dx": 3.0, "dy": -2.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 3.0, "dy": -2.0})
        self.assertEqual(valores["GG"], {"dx": 3.0, "dy": -2.0})

    def test_modo_proporcional_distribui_ate_as_pontas_da_grade(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaMouse()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Proporcional")

        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0)))
        self.assertEqual(ferramenta._proporcional_etapa, "menor")
        ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(6.0, 0.0)))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(6.0, 0.0)))
        self.assertEqual(ferramenta._proporcional_etapa, "maior")
        ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(14.0, 0.0)))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(14.0, 0.0)))
        self.assertEqual(ferramenta._proporcional_etapa, "confirmar")
        self.assertEqual(canvas.historico, 0)
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(14.0, 0.0)))

        valores = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]["1"]["valores"]
        self.assertEqual(valores["PP"], {"dx": -4.0, "dy": 0.0})
        self.assertEqual(valores["P"], {"dx": -2.0, "dy": 0.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 2.0, "dy": 0.0})
        self.assertEqual(valores["GG"], {"dx": 4.0, "dy": 0.0})
        self.assertIsNone(ferramenta._proporcional_etapa)
        self.assertEqual(canvas.historico, 1)

    def test_modo_proporcional_trava_em_angulos_padrao(self):
        origem = QPointF(10.0, 0.0)
        delta = FerramentaMouse._delta_angular(origem, QPointF(14.0, 1.0))

        self.assertAlmostEqual(delta.x(), 4.1231056256, places=6)
        self.assertAlmostEqual(delta.y(), 0.0, places=6)

    def test_sem_molde_selecionado_primeiro_clique_seleciona_molde(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaMouse()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(5.0, 2.0))))

        self.assertEqual(canvas._selecionados, {0})
        self.assertIsNone(ferramenta._ponto_idx)
        self.assertNotIn("graduacao_tabela", canvas.cena.elementos[0])


if __name__ == "__main__":
    unittest.main()
