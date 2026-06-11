from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from tools.dialog_position import posicionar_dialogo_abaixo_coordenadas
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


_CLASSES_IGNORADAS = {
    "QColorDialog",
    "QFileDialog",
    "QFontDialog",
    "QInputDialog",
    "QMessageBox",
    "QPrintDialog",
    "QProgressDialog",
}


def _classe_dialogo(dialogo: QDialog) -> str:
    try:
        return str(dialogo.metaObject().className() or dialogo.__class__.__name__)
    except Exception:
        return dialogo.__class__.__name__


def _chave_dialogo(dialogo: QDialog) -> str:
    chave_explicitada = getattr(dialogo, "_guimma_memoria_posicao_chave", None) or getattr(dialogo, "_chave_posicao", None)
    if chave_explicitada:
        return str(chave_explicitada)
    nome = str(dialogo.objectName() or "").strip() or _classe_dialogo(dialogo)
    titulo = str(dialogo.windowTitle() or "").strip() or nome
    return f"dialog:auto:{nome}:{titulo}"


def _deve_gerenciar(dialogo: QDialog) -> bool:
    if getattr(dialogo, "_guimma_ignorar_patch_posicao", False):
        return False
    if dialogo.parent() is None and dialogo.parentWidget() is None:
        return False
    classe = _classe_dialogo(dialogo)
    if classe in _CLASSES_IGNORADAS:
        return False
    try:
        return bool(dialogo.windowFlags() & Qt.Tool) or not dialogo.isModal()
    except Exception:
        return True


def aplicar_patch_posicao_dialogos() -> None:
    if getattr(QDialog, "_guimma_dialog_pos_patch", False):
        return

    exec_original = QDialog.exec
    show_original = QDialog.show
    open_original = QDialog.open

    def _preparar(dialogo: QDialog):
        try:
            if not _deve_gerenciar(dialogo):
                return
            chave = _chave_dialogo(dialogo)
            instalar_memoria_posicao(dialogo, chave)
            restaurou = restaurar_posicao(dialogo, chave)
            parent = dialogo.parentWidget() or dialogo.parent()
            if parent is not None and not restaurou:
                posicionar_dialogo_abaixo_coordenadas(dialogo, parent)
        except Exception:
            pass

    def exec_posicionado(self):  # noqa: N802
        _preparar(self)
        return exec_original(self)

    def show_posicionado(self):  # noqa: N802
        _preparar(self)
        return show_original(self)

    def open_posicionado(self):  # noqa: N802
        _preparar(self)
        return open_original(self)

    QDialog.exec = exec_posicionado
    QDialog.show = show_posicionado
    QDialog.open = open_posicionado
    QDialog._guimma_dialog_pos_patch = True


aplicar_patch_posicao_dialogos()
