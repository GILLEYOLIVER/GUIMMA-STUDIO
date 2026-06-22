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
    Signal = None
    QWidget = None
    FerramentaAgrupar = None
else:
    from PySide6.QtCore import QPointF, Qt, Signal
    from PySide6.QtGui import QPainterPath
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.agrupar_tool import Ferramenta as FerramentaAgrupar


class _FakeEvent:
    def __init__(self, pos: QPointF, button=Qt.LeftButton):
        self._pos = QPointF(pos)
        self._button = button
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return QPointF(self._pos)

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    elementos_alterados = Signal()

    def __init__(self):
        super().__init__()
        valores = {
            "0": {
                "indice": 0,
                "numero": 1,
                "ponto": (0.0, 0.0),
                "valores": {
                    "P": {"dx": 0.0, "dy": 0.0},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 0.0, "dy": 0.0},
                },
            },
            "1": {
                "indice": 1,
                "numero": 2,
                "ponto": (10.0, 0.0),
                "valores": {
                    "P": {"dx": -1.0, "dy": 0.5},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 2.0, "dy": 1.0},
                },
            },
            "2": {
                "indice": 2,
                "numero": 3,
                "ponto": (10.0, 5.0),
                "valores": {
                    "P": {"dx": -3.0, "dy": 1.5},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 4.0, "dy": 3.0},
                },
            },
            "3": {
                "indice": 3,
                "numero": 4,
                "ponto": (0.0, 5.0),
                "valores": {
                    "P": {"dx": 0.5, "dy": -0.5},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 1.0, "dy": -1.0},
                },
            },
        }
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "nome_molde": "K1",
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                    "graduacao_tamanhos": [
                        {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                        {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                        {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
                    ],
                    "graduacao_tabela": {"modo": "dx_dy", "pontos": valores},
                    "graduacao_pontos": valores,
                },
                {
                    "tipo": "polyline",
                    "molde": True,
                    "nome_molde": "K1 - G",
                    "origem_extracao": "separar_tamanho",
                    "tamanho_extraido": "G",
                    "pontos": [(30.0, 0.0), (42.0, 1.0), (44.0, 8.0), (31.0, 4.0), (30.0, 0.0)],
                    "controle_cantos": [(30.0, 0.0), (42.0, 1.0), (44.0, 8.0), (31.0, 4.0)],
                },
            ]
        )
        self._selecionados = set()
        self.zoom = 10.0
        self.historico = 0
        self.atualizou = False
        self.ferramenta_ativa = None
        self.lbl_status = None

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1
        self.elementos_alterados.emit()

    def update(self):
        self.atualizou = True

    def set_ferramenta_ativa(self, nome):
        self.ferramenta_ativa = nome


@unittest.skipIf(FerramentaAgrupar is None, "PySide6 não disponível neste ambiente")
class AgruparToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_click_em_ponto_graduado_ancora_dx_dy_zero_e_recalcula_demais_pontos(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaAgrupar()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(12.0, 1.0))))

        pontos = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]
        self.assertEqual(pontos["1"]["valores"]["P"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos["1"]["valores"]["G"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos["0"]["valores"]["P"], {"dx": 1.0, "dy": -0.5})
        self.assertEqual(pontos["0"]["valores"]["G"], {"dx": -2.0, "dy": -1.0})
        self.assertEqual(pontos["2"]["valores"]["P"], {"dx": -2.0, "dy": 1.0})
        self.assertEqual(pontos["2"]["valores"]["G"], {"dx": 2.0, "dy": 2.0})
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.atualizou)

    def test_click_em_tamanho_separado_nao_reagrupa_no_molde_de_origem(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaAgrupar()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(42.0, 1.0))))

        self.assertEqual(canvas.historico, 0)
        self.assertEqual(len(canvas.cena.elementos), 2)
        self.assertNotEqual(canvas._selecionados, {0})

    def test_hover_aplica_previa_sem_historico_e_esquerdo_confirma(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaAgrupar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(12.0, 1.0))))

        pontos = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]
        self.assertEqual(pontos["1"]["valores"]["P"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos["1"]["valores"]["G"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(canvas.historico, 0)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(12.0, 1.0))))

        self.assertEqual(canvas.historico, 1)
        self.assertIsNone(ferramenta._preview_original)

    def test_preview_ignora_cache_runtime_qpainterpath_do_molde(self):
        canvas = _FakeCanvas()
        path = QPainterPath(QPointF(0.0, 0.0))
        path.lineTo(QPointF(1.0, 1.0))
        canvas.cena.elementos[0]["_runtime_path_polilinha_tela_cache"] = {"path": path}
        ferramenta = FerramentaAgrupar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(12.0, 1.0))))

        self.assertIsNotNone(ferramenta._preview_original)
        self.assertNotIn(
            "_runtime_path_polilinha_tela_cache",
            ferramenta._preview_original["elemento"],
        )

    def test_hover_depois_de_confirmar_restaura_ultimo_ponto_confirmado_ao_sair(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaAgrupar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(12.0, 1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(12.0, 1.0))))
        self.assertEqual(canvas.historico, 1)

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(12.0, 7.0))))
        pontos = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]
        self.assertEqual(pontos["2"]["valores"]["P"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos["2"]["valores"]["G"], {"dx": 0.0, "dy": 0.0})

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(200.0, 200.0))))

        pontos = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]
        self.assertEqual(pontos["1"]["valores"]["P"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos["1"]["valores"]["G"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos["2"]["valores"]["P"], {"dx": -2.0, "dy": 1.0})
        self.assertEqual(pontos["2"]["valores"]["G"], {"dx": 2.0, "dy": 2.0})
        self.assertIsNone(ferramenta._preview_original)
        self.assertIsNone(ferramenta._hover_alvo)

    def test_direito_cancela_previa_e_segundo_direito_larga_ferramenta(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaAgrupar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(12.0, 1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(12.0, 1.0), button=Qt.RightButton)))

        pontos = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]
        self.assertEqual(pontos["1"]["valores"]["P"], {"dx": -1.0, "dy": 0.5})
        self.assertEqual(pontos["1"]["valores"]["G"], {"dx": 2.0, "dy": 1.0})
        self.assertEqual(canvas.historico, 0)
        self.assertIsNone(canvas.ferramenta_ativa)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(12.0, 1.0), button=Qt.RightButton)))

        self.assertEqual(canvas.ferramenta_ativa, "selecionar")

    def test_pontos_contorno_dxf_agrupado_usa_so_pontos_principais(self):
        ferramenta = FerramentaAgrupar()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "origem": "dxf_matriz_graduada",
            "pontos": [
                (0.0, 0.0),
                (2.0, 0.4),
                (4.0, 0.8),
                (6.0, 0.4),
                (8.0, 0.0),
                (8.0, 5.0),
                (0.0, 5.0),
                (0.0, 0.0),
            ],
            "controle_cantos": [(0.0, 0.0), (8.0, 0.0), (8.0, 5.0), (0.0, 5.0)],
            "graduacao_preferir_tabela_dxdy": True,
            "graduacao_tabela": {
                "pontos": {
                    str(idx): {"indice": idx, "ponto": ponto, "valores": {"G": {"dx": 1.0, "dy": 0.0}}}
                    for idx, ponto in enumerate(
                        [
                            (0.0, 0.0),
                            (2.0, 0.4),
                            (4.0, 0.8),
                            (6.0, 0.4),
                            (8.0, 0.0),
                            (8.0, 5.0),
                            (0.0, 5.0),
                        ]
                    )
                }
            },
        }

        pontos = ferramenta._pontos_contorno(molde)

        self.assertEqual(
            pontos,
            [QPointF(0.0, 0.0), QPointF(8.0, 0.0), QPointF(8.0, 5.0), QPointF(0.0, 5.0)],
        )


if __name__ == "__main__":
    unittest.main()
