from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    aplicar_fonte_padrao = None
    argv_com_fonte_padrao = None
else:
    from PySide6.QtWidgets import QApplication

    from ui.fonte_padrao import aplicar_fonte_padrao, argv_com_fonte_padrao


@unittest.skipIf(QApplication is None, "PySide6 nao disponivel neste ambiente")
class FontePadraoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication(["guimma-test"])

    def test_argv_com_fonte_padrao_inclui_fonte_quando_ausente(self):
        argumentos = argv_com_fonte_padrao(["guimma"])

        self.assertIn("-font", argumentos)

    def test_argv_com_fonte_padrao_preserva_fonte_existente(self):
        argumentos = argv_com_fonte_padrao(["guimma", "-font", "Helvetica"])

        self.assertEqual(argumentos, ["guimma", "-font", "Helvetica"])

    def test_aplicar_fonte_padrao_define_familia_real(self):
        familia = aplicar_fonte_padrao(self._app)

        self.assertTrue(familia)
        self.assertNotEqual(self._app.font().family(), "Sans Serif")


if __name__ == "__main__":
    unittest.main()
