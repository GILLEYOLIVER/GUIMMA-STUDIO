from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = SimpleNamespace(LeftButton=1, RightButton=2)
    QWidget = object
    FerramentaRemoverPique = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.remover_pique_tool import Ferramenta as FerramentaRemoverPique


class _FakeCanvas(QWidget if QWidget is not object else object):
    def __init__(self):
        super().__init__()
        self.zoom = 20.0
        self.historico = 0
        self._selecionados = set()
        self.ferramenta_final = None
        self.lbl_status = SimpleNamespace(texto="", setText=lambda texto: setattr(self.lbl_status, "texto", texto))
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                    "pontos_controle_principais": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 5.0, "y": 0.0},
                        {"x": 10.0, "y": 0.0},
                        {"x": 10.0, "y": 5.0},
                        {"x": 0.0, "y": 5.0},
                    ],
                    "controle_auxiliares": [],
                    "pontos_auxiliares": [],
                    "marcacoes_no_perimetro": [(5.0, 0.0)],
                    "piques_config": [
                        {
                            "ponto": (5.0, 0.0),
                            "ponto_controle": (5.0, 0.0),
                            "sobre_contorno": True,
                            "adicionar_ponto_controle": True,
                            "segmentos": [((5.0, 0.0), (5.0, 1.0))],
                        }
                    ],
                    "graduacao_tabela": {
                        "modo": "dx_dy",
                        "pontos": {
                            "0": {"indice": 0, "numero": 1, "ponto": (0.0, 0.0), "valores": {"G": {"dx": 0.0, "dy": 0.0}}},
                            "1": {"indice": 1, "numero": 2, "ponto": (5.0, 0.0), "valores": {"G": {"dx": 1.0, "dy": 0.0}}},
                            "2": {"indice": 2, "numero": 3, "ponto": (10.0, 0.0), "valores": {"G": {"dx": 2.0, "dy": 0.0}}},
                            "3": {"indice": 3, "numero": 4, "ponto": (10.0, 5.0), "valores": {"G": {"dx": 3.0, "dy": 0.0}}},
                            "4": {"indice": 4, "numero": 5, "ponto": (0.0, 5.0), "valores": {"G": {"dx": 4.0, "dy": 0.0}}},
                        },
                    },
                }
            ]
        )

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def set_ferramenta_ativa(self, ferramenta):
        self.ferramenta_final = ferramenta

    def update(self):
        pass


class _FakeEvent:
    def __init__(self, pos: QPointF, button=Qt.LeftButton):
        self._pos = QPointF(pos)
        self._button = button
        self.accepted = False

    def position(self):
        return QPointF(self._pos)

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


@unittest.skipIf(FerramentaRemoverPique is None, "PySide6 nao disponivel neste ambiente")
class RemoverPiqueToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_remove_pique_configurado_e_ponto_intermediario_do_contorno(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRemoverPique()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertNotIn("piques_config", molde)
        self.assertNotIn("marcacoes_no_perimetro", molde)
        self.assertEqual(molde["pontos"], [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)])
        self.assertNotIn((5.0, 0.0), molde["controle_cantos"])
        self.assertEqual(molde["graduacao_tabela"]["pontos"]["1"]["ponto"], (10.0, 0.0))
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 1)

    def test_remove_pique_interno_e_limpa_auxiliar(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde["pontos"] = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)]
        molde["piques_config"] = [
            {
                "ponto": (5.0, 2.5),
                "ponto_controle": (5.0, 2.5),
                "sobre_contorno": False,
                "adicionar_ponto_controle": True,
                "segmentos": [((5.0, 2.5), (6.0, 2.5))],
            }
        ]
        molde["controle_auxiliares"] = [(5.0, 2.5)]
        molde["pontos_auxiliares"] = [{"x": 5.0, "y": 2.5}]

        ferramenta = FerramentaRemoverPique()
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 2.5))))

        self.assertNotIn("piques_config", molde)
        self.assertEqual(molde["controle_auxiliares"], [])
        self.assertEqual(molde["pontos_auxiliares"], [])

    def test_remove_marcacao_simples_sem_config(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde.pop("piques_config", None)
        molde["marcacoes_no_perimetro"] = [(2.0, 0.0), (8.0, 0.0)]

        ferramenta = FerramentaRemoverPique()
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 0.0))))

        self.assertEqual(molde["marcacoes_no_perimetro"], [(8.0, 0.0)])
        self.assertEqual(canvas.historico, 1)

    def test_remover_todos_do_contorno_preserva_piques_internos(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde["piques_config"].append(
            {
                "ponto": (5.0, 2.5),
                "ponto_controle": (5.0, 2.5),
                "sobre_contorno": False,
                "adicionar_ponto_controle": True,
                "segmentos": [((5.0, 2.5), (6.0, 2.5))],
            }
        )
        molde["controle_auxiliares"] = [(5.0, 2.5)]
        molde["pontos_auxiliares"] = [{"x": 5.0, "y": 2.5}]
        ferramenta = FerramentaRemoverPique()

        removidos = ferramenta._remover_piques_do_molde(canvas, 0, "contorno")

        self.assertEqual(removidos, 1)
        self.assertEqual(len(molde["piques_config"]), 1)
        self.assertFalse(molde["piques_config"][0]["sobre_contorno"])
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 2.5)])
        self.assertNotIn("marcacoes_no_perimetro", molde)

    def test_dialogo_remove_por_caixas_exclusivas(self):
        from tools.remover_pique_tool import RemoverPiqueDialog

        dialog = RemoverPiqueDialog()
        dialog.chk_contorno.setChecked(True)
        dialog._marcar_exclusivo(dialog.chk_contorno)
        dialog.chk_internos.setChecked(True)
        dialog._marcar_exclusivo(dialog.chk_internos)

        self.assertFalse(dialog.chk_contorno.isChecked())
        self.assertTrue(dialog.chk_internos.isChecked())
        self.assertEqual(dialog.modo(), "internos")

    def test_botao_direito_finaliza(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRemoverPique()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0), button=Qt.RightButton)))

        self.assertEqual(canvas.ferramenta_final, "selecionar")


if __name__ == "__main__":
    unittest.main()
