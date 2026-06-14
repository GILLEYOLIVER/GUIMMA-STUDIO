from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


FONTE_PADRAO = "Arial"


def argv_com_fonte_padrao(argv: list[str]) -> list[str]:
    argumentos = list(argv)
    if any(arg in {"-font", "--font"} for arg in argumentos):
        return argumentos
    return argumentos + ["-font", FONTE_PADRAO]


def aplicar_fonte_padrao(app: QApplication | None = None) -> str:
    app = app or QApplication.instance()
    if app is None:
        return FONTE_PADRAO
    familias = set(QFontDatabase.families())
    familia = FONTE_PADRAO if FONTE_PADRAO in familias else QFontDatabase.systemFont(QFontDatabase.GeneralFont).family()
    if not familia:
        familia = FONTE_PADRAO
    app.setFont(QFont(familia))
    return familia
