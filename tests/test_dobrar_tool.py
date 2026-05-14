from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QWidget = None
    QPointF = None
    FerramentaDobrar = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.dobrar_tool import DobrarDialog, Ferramenta as FerramentaDobrar


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)],
                    "pontos_controle_referencia": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)],
                }
            ]
        )
        self._selecionados = {0}
        self.zoom = 10.0
        self.historico = 0
        self.lbl_status = None

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        pass


@unittest.skipIf(FerramentaDobrar is None, "PySide6 nao disponivel neste ambiente")
class DobrarToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_manter_dimensoes_inicia_marcado(self):
        dialog = DobrarDialog()
        self.assertTrue(dialog.chk_manter_dimensoes.isChecked())
        dialog.deleteLater()

    def test_dobrar_mantem_contorno_pontilhado_fechado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDobrar()
        ferramenta._dialog_por_canvas[id(canvas)] = DobrarDialog(canvas)
        ferramenta._dialog_por_canvas[id(canvas)].chk_manter_dimensoes.setChecked(True)
        ferramenta._lado_preview = 1

        ferramenta._aplicar(canvas, "Dobrar horizontal")

        molde = canvas.cena.elementos[0]
        registros = molde.get("contornos_dobra_original")
        self.assertIsInstance(registros, list)
        self.assertTrue(registros)
        pontilhado = registros[-1].get("contorno_pontilhado")
        self.assertGreaterEqual(len(pontilhado), 4)
        self.assertEqual(pontilhado[0], pontilhado[-1])
        self.assertTrue(molde["molde_dobrado"])
        self.assertEqual(canvas.historico, 1)


if __name__ == "__main__":
    unittest.main()
