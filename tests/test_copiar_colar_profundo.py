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
    Qt = SimpleNamespace(LeftButton=1, RightButton=2)
    QWidget = object
    CenaDocumento = None
    VisualizacaoCanvas = None
    FerramentaColar = None
    FerramentaCopiarOuTrocar = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from canvas.cena import CenaDocumento
    from canvas.visualizacao import VisualizacaoCanvas
    from tools.colar_tool import Ferramenta as FerramentaColar
    from tools.copiar_ou_trocar_elemento_tool import Ferramenta as FerramentaCopiarOuTrocar


def _molde_com_pique_e_grade(x: float = 0.0, y: float = 0.0) -> dict:
    return {
        "tipo": "polyline",
        "molde": True,
        "nome_molde": "K2",
        "pontos": [(x, y), (x + 10.0, y), (x + 10.0, y + 5.0), (x, y + 5.0), (x, y)],
        "fio_origem": [x + 1.0, y],
        "fio_fim": [x + 9.0, y],
        "piques_config": [
            {
                "ponto": (x + 5.0, y),
                "ponto_controle": {"x": x + 5.0, "y": y},
                "sobre_contorno": True,
                "segmentos": [((x + 5.0, y), (x + 5.0, y + 1.0))],
                "texto_pique": "Meio",
                "texto_dx_cm": 0.4,
                "texto_dy_cm": -0.3,
            }
        ],
        "graduacao_grade_nome": "36-44(40)",
        "graduacao_tamanhos": [
            {"ativo": True, "tamanho": "36", "base": False},
            {"ativo": True, "tamanho": "40", "base": True},
            {"ativo": True, "tamanho": "44", "base": False},
        ],
        "graduacao_tabela": {
            "modo": "dx_dy",
            "pontos": {
                "1": {
                    "indice": 1,
                    "numero": 2,
                    "ponto": (x + 10.0, y),
                    "valores": {"44": {"dx": 1.5, "dy": 0.25}},
                }
            },
        },
    }


class _FakeCanvas(QWidget if QWidget is not object else object):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(elementos=[])
        self._selecionados = set()
        self._buffer = None
        self._offset_colagem = 0
        self.historico = 0
        self.alvo_idx = None
        self.lbl_status = SimpleNamespace(texto="", setText=lambda texto: setattr(self.lbl_status, "texto", texto))

    def definir_buffer_copia(self, buffer):
        self._buffer = deepcopy(buffer)

    def obter_buffer_copia(self):
        return deepcopy(self._buffer)

    def _registrar_historico(self):
        self.historico += 1

    def _indices_elementos_em_ponto(self, _pos):
        return [] if self.alvo_idx is None else [self.alvo_idx]

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

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


@unittest.skipIf(VisualizacaoCanvas is None, "PySide6 nao disponivel neste ambiente")
class CopiarColarProfundoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_canvas_copia_em_um_arquivo_e_cola_em_outro_movendo_piques_e_grade(self):
        VisualizacaoCanvas._buffer_copia_compartilhado = None
        origem = VisualizacaoCanvas(CenaDocumento())
        destino = VisualizacaoCanvas(CenaDocumento())
        destino.resize(400, 300)
        destino.zoom = 10.0
        origem.cena.elementos.append(_molde_com_pique_e_grade())
        origem._selecionados = {0}

        origem.copiar()
        destino.colar()

        self.assertEqual(len(destino.cena.elementos), 1)
        colado = destino.cena.elementos[0]
        dx = colado["pontos"][0][0]
        dy = colado["pontos"][0][1]
        pique = colado["piques_config"][0]
        self.assertEqual(pique["ponto"], (5.0 + dx, dy))
        self.assertEqual(pique["ponto_controle"], {"x": 5.0 + dx, "y": dy})
        self.assertEqual(pique["segmentos"][0], ((5.0 + dx, dy), (5.0 + dx, 1.0 + dy)))
        self.assertEqual(colado["graduacao_tabela"]["pontos"]["1"]["ponto"], (10.0 + dx, dy))
        self.assertEqual(colado["graduacao_tabela"]["pontos"]["1"]["valores"], {"44": {"dx": 1.5, "dy": 0.25}})

    def test_ferramenta_colar_move_piques_e_pontos_da_tabela(self):
        canvas = _FakeCanvas()
        canvas.definir_buffer_copia({"elementos": [_molde_com_pique_e_grade()]})

        total = FerramentaColar()._colar(canvas)

        self.assertEqual(total, 1)
        colado = canvas.cena.elementos[0]
        self.assertEqual(colado["pontos"][0], (2.0, 2.0))
        pique = colado["piques_config"][0]
        self.assertEqual(pique["ponto"], (7.0, 2.0))
        self.assertEqual(pique["ponto_controle"], {"x": 7.0, "y": 2.0})
        self.assertEqual(pique["segmentos"][0], ((7.0, 2.0), (7.0, 3.0)))
        self.assertEqual(colado["graduacao_tabela"]["pontos"]["1"]["ponto"], (12.0, 2.0))
        self.assertEqual(colado["graduacao_tabela"]["pontos"]["1"]["valores"]["44"], {"dx": 1.5, "dy": 0.25})
        self.assertEqual(canvas.historico, 1)

    def test_copiar_ou_trocar_elemento_substitui_alvo_centralizando_copia(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos = [_molde_com_pique_e_grade(0.0, 0.0), _molde_com_pique_e_grade(100.0, 0.0)]
        canvas._selecionados = {0}
        ferramenta = FerramentaCopiarOuTrocar()

        ferramenta.on_activate(canvas)
        canvas.alvo_idx = 1
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(105.0, 0.0))))

        self.assertEqual(len(canvas.cena.elementos), 2)
        substituto = canvas.cena.elementos[1]
        self.assertEqual(substituto["pontos"][0], (100.0, 0.0))
        self.assertEqual(substituto["piques_config"][0]["ponto"], (105.0, 0.0))
        self.assertEqual(substituto["graduacao_tabela"]["pontos"]["1"]["ponto"], (110.0, 0.0))
        self.assertEqual(canvas._selecionados, {1})
        self.assertEqual(canvas.historico, 1)


if __name__ == "__main__":
    unittest.main()
