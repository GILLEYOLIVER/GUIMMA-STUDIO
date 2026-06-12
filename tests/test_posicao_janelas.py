from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QEvent = None
    QWidget = None
    _FiltroMemoriaPosicao = None
else:
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QWidget

    from ui.posicao_janelas import _FiltroMemoriaPosicao


@unittest.skipIf(QApplication is None, "PySide6 nao disponivel neste ambiente")
class PosicaoJanelasTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_filtro_memoria_posicao_nao_quebra_sem_widget(self):
        widget = QWidget()
        filtro = _FiltroMemoriaPosicao(widget, "teste:filtro")
        delattr(filtro, "_widget")

        filtro.eventFilter(widget, QEvent(QEvent.Move))


if __name__ == "__main__":
    unittest.main()
