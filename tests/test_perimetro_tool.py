from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    FerramentaPerimetro = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from tools.perimetro_tool import Ferramenta as FerramentaPerimetro


class _LabelFake:
    def __init__(self):
        self.texto = ""

    def setText(self, texto: str):
        self.texto = str(texto)


class _CanvasFake:
    def __init__(self):
        self.zoom = 20.0
        self.lbl_status = _LabelFake()
        self.atualizacoes = 0
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                    "graduacao_tamanhos": [
                        {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                        {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                        {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
                    ],
                }
            ]
        )

    def formatar_distancia(self, valor: float) -> str:
        return f"{valor:.1f} cm"

    def update(self):
        self.atualizacoes += 1


@unittest.skipIf(FerramentaPerimetro is None, "PySide6 nao disponivel neste ambiente")
class PerimetroToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_hover_atualiza_barra_com_tamanho_e_perimetro(self):
        canvas = _CanvasFake()
        ferramenta = FerramentaPerimetro()

        self.assertTrue(ferramenta._atualizar_medicao(canvas, QPointF(5.0, 0.0), silencioso=True))

        self.assertEqual(canvas.lbl_status.texto, "Tamanho M - Perímetro: 10.0 cm")
        self.assertEqual(ferramenta._texto_rotulo_medicao(canvas, ferramenta._medicao), "M 10.0 cm")


if __name__ == "__main__":
    unittest.main()
