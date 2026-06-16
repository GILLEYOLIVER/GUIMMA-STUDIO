from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QDialog = None
    delete = None
else:
    from PySide6.QtWidgets import QApplication, QDialog
    from shiboken6 import delete

    from tools.dialog_lifetime import esconder_se_valido, qobject_valido


@unittest.skipIf(QApplication is None, "PySide6 nao disponivel neste ambiente")
class DialogLifetimeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_qobject_valido_fica_falso_apos_delete_cpp(self):
        dialog = QDialog()
        self.assertTrue(qobject_valido(dialog))

        delete(dialog)

        self.assertFalse(qobject_valido(dialog))
        esconder_se_valido(dialog)


if __name__ == "__main__":
    unittest.main()
