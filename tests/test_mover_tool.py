from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaMover = None
    QApplication = None
    QPointF = None

    class _QtIndisponivel:
        LeftButton = 1

    class QWidget:
        pass

    Qt = _QtIndisponivel()
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPainterPath
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.mover_tool import Ferramenta as FerramentaMover

from tools.movimento_utils import mover_elemento_por_delta, rotacionar_elemento_por_funcao


class _FakeEvent:
    def __init__(self, pos, button=None):
        self._pos = pos
        self._button = button or Qt.LeftButton
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._selecionados = {0}
        self.historico = 0
        self.atualizou = False
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (10.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                    "controle_auxiliares": [],
                }
            ]
        )
        self.ignorar_snap_movimento = []
        self.sombras_snap_movimento = []

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _ponto_com_snap_movimento(self, pos, ignorar_elementos=None, elementos_sombra=None):
        self.ignorar_snap_movimento.append(set(ignorar_elementos or []))
        self.sombras_snap_movimento.append(elementos_sombra)
        return self._ponto_com_snap(pos)

    def _indices_elementos_em_ponto(self, _pos):
        return [0]

    def iniciar_operacao_coordenadas(self, _pos):
        pass

    def atualizar_operacao_coordenadas(self, _pos):
        pass

    def finalizar_operacao_coordenadas(self, _pos):
        pass

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


class MovimentoUtilsTestCase(unittest.TestCase):
    def test_mover_molde_desloca_pontos_de_graduacao_e_tabela(self):
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "pontos_graduacao": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "indice": 0,
                        "ponto": (0.0, 0.0),
                        "valores": {"G": {"dx": 0.0, "dy": 1.0}},
                    }
                }
            },
        }

        mover_elemento_por_delta(molde, 5.0, -2.0)

        self.assertEqual(molde["pontos"], [(5.0, -2.0), (15.0, -2.0)])
        self.assertEqual(molde["pontos_graduacao"], [{"x": 5.0, "y": -2.0}, {"x": 15.0, "y": -2.0}])
        self.assertEqual(molde["graduacao_tabela"]["pontos"]["0"]["ponto"], (5.0, -2.0))
        self.assertEqual(molde["graduacao_tabela"]["pontos"]["0"]["valores"]["G"], {"dx": 0.0, "dy": 1.0})

    def test_mover_molde_desloca_contornos_importados_da_graduacao(self):
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "_runtime_path_polilinha_tela_cache_multi": {"antigo": object()},
            "graduacao_contornos_importados": [
                {
                    "tamanho": "P",
                    "base": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                },
                {
                    "tamanho": "M",
                    "base": False,
                    "pontos": [(1.0, 1.0), (11.0, 1.0), (11.0, 6.0)],
                },
            ],
        }

        mover_elemento_por_delta(molde, 5.0, -2.0)

        self.assertEqual(molde["pontos"], [(5.0, -2.0), (15.0, -2.0)])
        self.assertEqual(
            molde["graduacao_contornos_importados"][0]["pontos"],
            [(5.0, -2.0), (15.0, -2.0), (15.0, 3.0)],
        )
        self.assertEqual(
            molde["graduacao_contornos_importados"][1]["pontos"],
            [(6.0, -1.0), (16.0, -1.0), (16.0, 4.0)],
        )
        self.assertNotIn("_runtime_path_polilinha_tela_cache_multi", molde)

    def test_rotacionar_molde_gira_pontos_e_vetores_de_graduacao(self):
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(10.0, 0.0), (10.0, 5.0)],
            "pontos_graduacao": [{"x": 10.0, "y": 0.0}],
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "indice": 0,
                        "ponto": (10.0, 0.0),
                        "valores": {
                            "P": {"dx": 0.0, "dy": -2.0},
                            "G": {"dx": 0.0, "dy": 2.0},
                        },
                    }
                }
            },
            "graduacao_pontos": {
                "0": {
                    "indice": 0,
                    "ponto": (10.0, 0.0),
                    "valores": {"G": {"dx": 0.0, "dy": 2.0}},
                }
            },
        }

        def rotacionar_90(p):
            x, y = float(p[0]), float(p[1])
            return -y, x

        rotacionar_elemento_por_funcao(molde, rotacionar_90)

        self.assertEqual(molde["pontos"], [(0.0, 10.0), (-5.0, 10.0)])
        self.assertEqual(molde["pontos_graduacao"], [{"x": 0.0, "y": 10.0}])
        ponto = molde["graduacao_tabela"]["pontos"]["0"]
        self.assertEqual(ponto["ponto"], (0.0, 10.0))
        self.assertEqual(ponto["valores"]["P"], {"dx": 2.0, "dy": 0.0})
        self.assertEqual(ponto["valores"]["G"], {"dx": -2.0, "dy": 0.0})
        self.assertEqual(molde["graduacao_pontos"]["0"]["ponto"], (0.0, 10.0))
        self.assertEqual(molde["graduacao_pontos"]["0"]["valores"]["G"], {"dx": -2.0, "dy": 0.0})


@unittest.skipIf(FerramentaMover is None, "PySide6 nao disponivel neste ambiente")
class MoverToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_mover_mantem_snapshot_original_ate_soltar(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaMover()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0))))
        self.assertEqual(ferramenta._originais_arraste[0]["pontos"], [(0.0, 0.0), (10.0, 0.0)])

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(2.0, 1.0))))
        self.assertEqual(canvas.cena.elementos[0]["pontos"], [(2.0, 1.0), (12.0, 1.0)])
        self.assertEqual(ferramenta._originais_arraste[0]["pontos"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(canvas.ignorar_snap_movimento[-1], {0})
        self.assertEqual(canvas.sombras_snap_movimento[-1][0]["pontos"], [(0.0, 0.0), (10.0, 0.0)])

        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(QPointF(2.0, 1.0))))
        self.assertEqual(ferramenta._originais_arraste, {})
        self.assertEqual(canvas.historico, 1)

    def test_mover_ignora_cache_runtime_qpainterpath_no_snapshot_original(self):
        canvas = _FakeCanvas()
        path = QPainterPath(QPointF(0.0, 0.0))
        path.lineTo(QPointF(10.0, 0.0))
        canvas.cena.elementos[0]["_runtime_path_polilinha_tela_cache"] = {"valor": path}
        ferramenta = FerramentaMover()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0))))

        self.assertIn(0, ferramenta._originais_arraste)
        self.assertNotIn("_runtime_path_polilinha_tela_cache", ferramenta._originais_arraste[0])


if __name__ == "__main__":
    unittest.main()
