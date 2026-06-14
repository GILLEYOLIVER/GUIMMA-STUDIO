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
    FerramentaCriarMolde = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication

    from tools.criar_molde_tool import Ferramenta as FerramentaCriarMolde


class _FakeEvent:
    def __init__(self, pos: QPointF):
        self._pos = QPointF(pos)
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def position(self):
        return QPointF(self._pos)

    def accept(self):
        self.accepted = True


class _FakeCanvas:
    def __init__(self):
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                }
            ]
        )
        self._selecionados = set()
        self._linha_espessura = 4.0
        self._linha_estilo = "solid"
        self._linha_amplitude = 1.0
        self.historico = 0
        self.atualizou = False

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _indices_elementos_em_ponto(self, _pos):
        return [0]

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaCriarMolde is None, "PySide6 nao disponivel neste ambiente")
class CriarMoldeToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_criar_molde_nao_deixa_molde_novo_selecionado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaCriarMolde()
        event = _FakeEvent(QPointF(1.0, 1.0))

        self.assertTrue(ferramenta.on_mouse_press(canvas, event))

        self.assertTrue(canvas.cena.elementos[0]["molde"])
        self.assertEqual(
            canvas.cena.elementos[0]["graduacao_tamanhos"],
            [
                {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
            ],
        )
        self.assertEqual(canvas.cena.elementos[0]["graduacao_tamanhos_ativos"], ["P", "M", "G"])
        self.assertEqual(canvas.cena.elementos[0]["espessura"], 4.0)
        self.assertEqual(canvas.cena.elementos[0]["espessura_graduacao"], 4.0)
        self.assertEqual(
            canvas.cena.elementos[0]["pontos_controle_principais"],
            [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 5.0},
            ],
        )
        self.assertEqual(
            canvas.cena.elementos[0]["pontos_graduacao"],
            [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 5.0},
            ],
        )
        self.assertEqual(canvas._selecionados, set())
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(event.accepted)

    def test_criar_molde_herda_grade_de_molde_existente_no_canvas(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.insert(
            0,
            {
                "tipo": "polyline",
                "molde": True,
                "pontos": [(20.0, 0.0), (30.0, 0.0), (30.0, 5.0), (20.0, 0.0)],
                "graduacao_grade_nome": "36-44(40)",
                "graduacao_tamanhos": [
                    {"ativo": True, "tamanho": "36", "cor": "#3355ff", "base": False},
                    {"ativo": True, "tamanho": "40", "cor": "#22aa88", "base": True},
                    {"ativo": True, "tamanho": "44", "cor": "#dd7733", "base": False},
                ],
                "graduacao_tamanhos_ativos": ["36", "40", "44"],
            },
        )
        canvas._indices_elementos_em_ponto = lambda _pos: [1]
        ferramenta = FerramentaCriarMolde()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(1.0, 1.0))))

        novo = canvas.cena.elementos[1]
        self.assertEqual(novo["graduacao_grade_nome"], "36-44(40)")
        self.assertEqual([linha["tamanho"] for linha in novo["graduacao_tamanhos"]], ["36", "40", "44"])
        self.assertEqual([linha["cor"] for linha in novo["graduacao_tamanhos"]], ["#3355ff", "#22aa88", "#dd7733"])


if __name__ == "__main__":
    unittest.main()
