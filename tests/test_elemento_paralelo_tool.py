from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    QWidget = None
    FerramentaElementoParalelo = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.elemento_paralelo_tool import Ferramenta as FerramentaElementoParalelo


_BaseWidget = QWidget if QWidget is not None else object


class _FakeCanvas(_BaseWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (10.0, 0.0)],
                    "cor": "#ffffff",
                    "espessura": 1.0,
                    "estilo": "solid",
                }
            ]
        )
        self._selecionados = {0}
        self._linha_cor = "#001dff"
        self._linha_espessura = 2.0
        self._linha_estilo = "dash"
        self.ferramenta_ativa = None

    def _registrar_historico(self):
        pass

    def update(self):
        pass

    def set_ferramenta_ativa(self, nome):
        self.ferramenta_ativa = nome


class _FakeEvent:
    def __init__(self, button):
        self._button = button
        self.accepted = False

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


@unittest.skipIf(FerramentaElementoParalelo is None, "PySide6 nao disponivel neste ambiente")
class ElementoParaleloToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_elemento_paralelo_usa_cor_configurada_no_canvas(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaElementoParalelo()

        ferramenta._criar_elemento(
            canvas,
            [QPointF(0.0, 1.0), QPointF(10.0, 1.0)],
            {"elemento_idx": 0},
            registrar=False,
        )

        self.assertEqual(canvas.cena.elementos[-1]["cor"], "#001dff")

    def test_elemento_paralelo_so_sai_com_botao_direito(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaElementoParalelo()

        duplo_esquerdo = _FakeEvent(Qt.LeftButton)
        self.assertTrue(ferramenta.on_mouse_double_click(canvas, duplo_esquerdo))
        self.assertTrue(duplo_esquerdo.accepted)
        self.assertIsNone(canvas.ferramenta_ativa)

        direito = _FakeEvent(Qt.RightButton)
        self.assertTrue(ferramenta.on_mouse_press(canvas, direito))
        self.assertTrue(direito.accepted)
        self.assertEqual(canvas.ferramenta_ativa, "selecionar")


if __name__ == "__main__":
    unittest.main()
