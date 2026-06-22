from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QPointF = None
    desenhar_elementos_originais = None
else:
    from PySide6.QtCore import QPointF

    from tools.preview_original_utils import desenhar_elementos_originais


class _FakeCanvas:
    def _cena_para_tela(self, ponto):
        return QPointF(ponto)


class _FakePainter:
    def __init__(self):
        self.linhas = []

    def save(self):
        pass

    def restore(self):
        pass

    def setPen(self, _pen):
        pass

    def setBrush(self, _brush):
        pass

    def drawLine(self, a, b):
        self.linhas.append((QPointF(a), QPointF(b)))


@unittest.skipIf(desenhar_elementos_originais is None, "PySide6 nao disponivel neste ambiente")
class PreviewOriginalUtilsTestCase(unittest.TestCase):
    def test_sombra_usa_cantos_oficiais_e_ignora_principais_redundantes(self):
        canvas = _FakeCanvas()
        painter = _FakePainter()
        elemento = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
            "controle_cantos": [(0.0, 0.0)],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 5.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 5.0},
            ],
            "controle_auxiliares": [],
        }

        desenhar_elementos_originais(canvas, painter, {0: elemento})

        self.assertEqual(len(painter.linhas), 6)

    def test_sombra_ignora_molde_audaces_graduado(self):
        canvas = _FakeCanvas()
        painter = _FakePainter()
        elemento = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
            "graduacao_tamanhos": [{"tamanho": "P", "base": True}],
            "graduacao_contornos_importados": [
                {"tamanho": "P", "base": True, "pontos": [(0.0, 0.0), (10.0, 0.0)]}
            ],
        }

        desenhar_elementos_originais(canvas, painter, {0: elemento})

        self.assertEqual(painter.linhas, [])


if __name__ == "__main__":
    unittest.main()
