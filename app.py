from __future__ import annotations

import sys
from typing import Sequence

from PySide6.QtWidgets import QApplication

from config import APP_NOME
from ui.janela_principal import GuimmaStudioMainWindow


class GuimmaStudioApp:
    def __init__(self, argv: Sequence[str] | None = None):
        self._argv = list(argv or sys.argv)
        self.qt_app = QApplication(self._argv)
        self.qt_app.setApplicationName(APP_NOME)
        self.janela_principal = GuimmaStudioMainWindow()

    def run(self) -> int:
        self.janela_principal.show()
        return self.qt_app.exec()
