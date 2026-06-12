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
    FerramentaManipularPontos = None
    DesdobrarDialog = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.dobrar_tool import DobrarDialog, Ferramenta as FerramentaDobrar
    from tools.desdobrar_tool import DesdobrarDialog
    from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos


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
        self.assertEqual(dialog.chk_manter_dimensoes.text(), "Preservar original para desdobrar")
        self.assertEqual([dialog.cmb_modo.itemText(i) for i in range(dialog.cmb_modo.count())], ["Horizontal", "Vertical", "Linha"])
        self.assertFalse(dialog.chk_fio_meio.isChecked())
        dialog.deleteLater()

    def test_desdobrar_dialog_fluxo_padrao(self):
        dialog = DesdobrarDialog()
        self.assertTrue(dialog.chk_automatico.isChecked())
        self.assertTrue(dialog.chk_fio_meio.isChecked())
        self.assertTrue(hasattr(dialog, "chk_inserir_pique"))
        self.assertFalse(dialog.chk_inserir_pique.isChecked())
        dialog.deleteLater()

    def test_dobra_meio_respeita_ponto_medio_da_reta_maior(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDobrar()

        self.assertEqual(ferramenta._eixo(canvas, [0], "Horizontal"), ("h", 4.0))
        self.assertEqual(ferramenta._eixo(canvas, [0], "Vertical"), ("v", 5.0))

    def test_dobrar_mantem_contorno_pontilhado_fechado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDobrar()
        ferramenta._dialog_por_canvas[id(canvas)] = DobrarDialog(canvas)
        ferramenta._dialog_por_canvas[id(canvas)].chk_manter_dimensoes.setChecked(True)
        ferramenta._lado_preview = 1

        ferramenta._aplicar(canvas, "Horizontal")

        molde = canvas.cena.elementos[0]
        registros = molde.get("contornos_dobra_original")
        self.assertIsInstance(registros, list)
        self.assertTrue(registros)
        pontilhado = registros[-1].get("contorno_pontilhado")
        self.assertGreaterEqual(len(pontilhado), 4)
        self.assertEqual(pontilhado[0], pontilhado[-1])
        self.assertTrue(molde["molde_dobrado"])
        self.assertEqual(canvas.historico, 1)

    def test_manipular_pontos_edita_contorno_pontilhado_da_dobra(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde["contornos_dobra_original"] = [
            {
                "contorno_pontilhado": [(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 0.0)],
                "metade_movida": [(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 0.0)],
            }
        ]
        ferramenta = FerramentaManipularPontos()

        ferramenta._atualizar_dobra_pontilhada(canvas, (0, 0, 1), QPointF(6.0, 1.0))

        registro = molde["contornos_dobra_original"][0]
        self.assertEqual(registro["contorno_pontilhado"][1], (6.0, 1.0))
        self.assertEqual(registro["metade_movida"][1], (6.0, 1.0))


if __name__ == "__main__":
    unittest.main()
