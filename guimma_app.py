from __future__ import annotations

import sys
from typing import Sequence

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from config import APP_NOME
from ui.janela_principal import GuimmaStudioMainWindow


class GuimmaStudioApp:
    def __init__(self, argv: Sequence[str] | None = None):
        self._argv = list(argv or sys.argv)
        self.qt_app = QApplication(self._argv)
        self.qt_app.setApplicationName(APP_NOME)
        self._aplicar_traducao_qt_ptbr()
        self._aplicar_tema_claro_global()
        self.janela_principal = GuimmaStudioMainWindow()

    def _aplicar_traducao_qt_ptbr(self):
        self._tradutor_qt = QTranslator(self.qt_app)
        caminho_i18n = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        for idioma in ("pt_BR", "pt"):
            if self._tradutor_qt.load(f"qtbase_{idioma}", caminho_i18n):
                self.qt_app.installTranslator(self._tradutor_qt)
                QLocale.setDefault(QLocale(idioma))
                return

    def _aplicar_tema_claro_global(self):
        self.qt_app.setStyle("Fusion")
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor("#efefef"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        pal.setColor(QPalette.Base, QColor("#ffffff"))
        pal.setColor(QPalette.AlternateBase, QColor("#f4f4f4"))
        pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        pal.setColor(QPalette.ToolTipText, QColor("#111111"))
        pal.setColor(QPalette.Text, QColor("#111111"))
        pal.setColor(QPalette.Button, QColor("#f6f6f6"))
        pal.setColor(QPalette.ButtonText, QColor("#111111"))
        pal.setColor(QPalette.BrightText, QColor("#ffffff"))
        pal.setColor(QPalette.Highlight, QColor("#2b7cd3"))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.qt_app.setPalette(pal)

    def run(self) -> int:
        self.janela_principal.showMaximized()
        return self.qt_app.exec()
