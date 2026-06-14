from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    FerramentaDimensionar = None
else:
    from PySide6.QtWidgets import QApplication

    from tools.dimensionar_tool import Ferramenta as FerramentaDimensionar


class _FakeCanvas:
    def __init__(self):
        self.cena = SimpleNamespace(elementos=[])
        self._selecionados = set()
        self.historico = 0
        self.lbl_status = SimpleNamespace(texto="", setText=lambda texto: setattr(self.lbl_status, "texto", texto))

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        pass


def _molde_base() -> dict:
    valores = {
        "1": {
            "indice": 1,
            "numero": 2,
            "ponto": (10.0, 0.0),
            "valores": {
                "P": {"dx": -1.0, "dy": -2.0},
                "G": {"dx": 1.0, "dy": 2.0},
            },
        }
    }
    return {
        "tipo": "polyline",
        "molde": True,
        "molde_id": "molde-1",
        "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
        "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        "pontos_controle_principais": [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
        ],
        "fio_origem": (2.0, 5.0),
        "fio_fim": (8.0, 5.0),
        "piques_config": [
            {
                "ponto": (10.0, 5.0),
                "ponto_controle": {"x": 10.0, "y": 5.0},
                "largura_cm": 1.0,
                "altura_cm": 2.0,
                "dx_cm": 0.5,
                "dy_cm": -0.25,
                "texto_pique": "Meio",
                "texto_dx_cm": 0.4,
                "texto_dy_cm": -0.2,
                "texto_altura_cm": 0.3,
                "segmentos": [((10.0, 5.0), (10.0, 7.0))],
            }
        ],
        "graduacao_tabela": {"modo": "dx_dy", "pontos": valores},
        "graduacao_pontos": valores.copy(),
    }


@unittest.skipIf(FerramentaDimensionar is None, "PySide6 nao disponivel neste ambiente")
class DimensionarToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dimensionar_preserva_e_escala_graduacao_piques_e_fio(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(_molde_base())
        canvas._selecionados = {0}
        ferramenta = FerramentaDimensionar()

        self.assertTrue(ferramenta._dimensionar_selecao(canvas, 200.0, 50.0))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"][0], (-5.0, 2.5))
        self.assertEqual(molde["pontos"][1], (15.0, 2.5))
        self.assertEqual(molde["fio_origem"], (-1.0, 5.0))
        self.assertEqual(molde["fio_fim"], (11.0, 5.0))

        pique = molde["piques_config"][0]
        self.assertEqual(pique["ponto"], (15.0, 5.0))
        self.assertEqual(pique["ponto_controle"], {"x": 15.0, "y": 5.0})
        self.assertEqual(pique["segmentos"][0], ((15.0, 5.0), (15.0, 6.0)))
        self.assertEqual(pique["largura_cm"], 1.25)
        self.assertEqual(pique["altura_cm"], 2.5)
        self.assertEqual(pique["dx_cm"], 1.0)
        self.assertEqual(pique["dy_cm"], -0.125)
        self.assertEqual(pique["texto_dx_cm"], 0.8)
        self.assertEqual(pique["texto_dy_cm"], -0.1)

        ponto_grade = molde["graduacao_tabela"]["pontos"]["1"]
        self.assertEqual(ponto_grade["ponto"], (15.0, 2.5))
        self.assertEqual(ponto_grade["valores"]["G"], {"dx": 2.0, "dy": 1.0})
        self.assertEqual(ponto_grade["valores"]["P"], {"dx": -2.0, "dy": -1.0})
        self.assertEqual(molde["graduacao_pontos"]["1"]["valores"]["G"], {"dx": 2.0, "dy": 1.0})
        self.assertEqual(canvas.historico, 1)

    def test_dimensionar_molde_move_linha_vinculada_junto(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos = [
            _molde_base(),
            {
                "tipo": "polyline",
                "molde_linha_vinculada": True,
                "molde_id": "molde-1",
                "pontos": [(2.0, 2.0), (8.0, 2.0)],
            },
        ]
        canvas._selecionados = {0}

        self.assertTrue(FerramentaDimensionar()._dimensionar_selecao(canvas, 100.0, 200.0))

        linha = canvas.cena.elementos[1]
        self.assertEqual(linha["pontos"], [(2.0, -1.0), (8.0, -1.0)])

    def test_dimensionar_nao_duplica_escala_quando_tabela_e_legado_compartilham_cfg(self):
        canvas = _FakeCanvas()
        molde = _molde_base()
        canvas.cena.elementos.append(molde)
        canvas._selecionados = {0}

        self.assertIs(molde["graduacao_tabela"]["pontos"]["1"], molde["graduacao_pontos"]["1"])
        self.assertTrue(FerramentaDimensionar()._dimensionar_selecao(canvas, 200.0, 200.0))

        valores = molde["graduacao_tabela"]["pontos"]["1"]["valores"]["G"]
        self.assertEqual(valores, {"dx": 2.0, "dy": 4.0})

    def test_sem_alteracao_para_escala_100_porcento(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(_molde_base())
        canvas._selecionados = {0}

        self.assertFalse(FerramentaDimensionar()._dimensionar_selecao(canvas, 100.0, 100.0))
        self.assertEqual(canvas.historico, 0)


if __name__ == "__main__":
    unittest.main()
