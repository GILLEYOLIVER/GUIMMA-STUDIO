from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QWidget = None
    FerramentaBase = None
    PainelFerramentaBasico = None
else:
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.painel_ferramenta import PainelFerramentaBasico
    from tools.tool_base import FerramentaBase


@unittest.skipIf(FerramentaBase is None, "PySide6 nao disponivel neste ambiente")
class ToolBaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_on_activate_nao_cria_painel_basico_generico(self):
        canvas = QWidget()
        ferramenta = FerramentaBase()

        ferramenta.on_activate(canvas)

        self.assertEqual(canvas.findChildren(PainelFerramentaBasico), [])

    def test_on_activate_oculta_paineis_basicos_remanescentes(self):
        canvas = QWidget()
        painel = PainelFerramentaBasico("Mover", "Instrucao generica", parent=canvas)
        painel.show()
        self.assertFalse(painel.isHidden())

        ferramenta = FerramentaBase()
        ferramenta.on_activate(canvas)

        self.assertTrue(painel.isHidden())


if __name__ == "__main__":
    unittest.main()
