from __future__ import annotations

from PySide6.QtWidgets import QDialog

from tools.dialog_position import posicionar_dialogo_abaixo_coordenadas


_TITULOS_TEXTO = {"Criar texto", "Editar texto"}


def aplicar_patch_posicao_dialogos_texto() -> None:
    if getattr(QDialog, "_guimma_dialog_pos_patch", False):
        return

    exec_original = QDialog.exec
    show_original = QDialog.show
    open_original = QDialog.open

    def _posicionar(dialogo):
        try:
            titulo = str(dialogo.windowTitle() or "")
            if titulo not in _TITULOS_TEXTO:
                return
            parent = dialogo.parent()
            if parent is not None:
                posicionar_dialogo_abaixo_coordenadas(dialogo, parent)
        except Exception:
            pass

    def exec_posicionado(self):  # noqa: N802
        _posicionar(self)
        return exec_original(self)

    def show_posicionado(self):  # noqa: N802
        _posicionar(self)
        return show_original(self)

    def open_posicionado(self):  # noqa: N802
        _posicionar(self)
        return open_original(self)

    QDialog.exec = exec_posicionado
    QDialog.show = show_posicionado
    QDialog.open = open_posicionado
    QDialog._guimma_dialog_pos_patch = True


aplicar_patch_posicao_dialogos_texto()
