from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    VisualizacaoCanvas = None
    CenaDocumento = None
    FerramentaReta = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from canvas.cena import CenaDocumento
    from canvas.visualizacao import VisualizacaoCanvas
    from tools.reta_tool import Ferramenta as FerramentaReta


@unittest.skipIf(FerramentaReta is None, "PySide6 nao disponivel neste ambiente")
class RetaToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_desfazer_etapa_remove_ultimo_clique_sem_finalizar(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        ferramenta = FerramentaReta()
        ferramenta.on_activate(canvas)
        ferramenta._desenhando = True
        ferramenta._pontos_atuais = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 5.0)]
        canvas._pontos_reta = [QPointF(p) for p in ferramenta._pontos_atuais]

        self.assertTrue(ferramenta.desfazer_etapa(canvas))

        self.assertTrue(ferramenta._desenhando)
        self.assertEqual(len(ferramenta._pontos_atuais), 2)
        self.assertEqual(canvas._pontos_reta[-1], QPointF(10.0, 0.0))
        self.assertEqual(canvas._preview_reta, QPointF(10.0, 0.0))

    def test_desfazer_etapa_do_primeiro_clique_cancela_inicio(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        ferramenta = FerramentaReta()
        ferramenta.on_activate(canvas)
        ferramenta._desenhando = True
        ferramenta._pontos_atuais = [QPointF(0.0, 0.0)]
        canvas._pontos_reta = [QPointF(0.0, 0.0)]

        self.assertTrue(ferramenta.desfazer_etapa(canvas))

        self.assertFalse(ferramenta._desenhando)
        self.assertEqual(ferramenta._pontos_atuais, [])
        self.assertEqual(canvas._pontos_reta, [])
        self.assertIsNone(canvas._preview_reta)


if __name__ == "__main__":
    unittest.main()
