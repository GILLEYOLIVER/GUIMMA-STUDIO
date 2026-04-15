from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication
from janela_principal import GuimmaStudioMainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GUIMMA STUDIO")
    janela = GuimmaStudioMainWindow()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
