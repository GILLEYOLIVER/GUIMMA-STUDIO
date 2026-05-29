from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget


_FILTRO_TEXTO_APP = None


def _dialogo_visivel_mais_recente():
    try:
        from tools import inserir_texto_tool
    except Exception:
        return None

    Ferramenta = getattr(inserir_texto_tool, "Ferramenta", None)
    if Ferramenta is None:
        return None

    try:
        dialogos = list(getattr(Ferramenta, "_dialog_por_canvas", {}).values())
    except Exception:
        return None

    for dialog in reversed(dialogos):
        try:
            if dialog is not None and dialog.isVisible() and hasattr(dialog, "txt_texto"):
                return dialog
        except Exception:
            pass
    return None


def _objeto_esta_dentro_dialogo(obj, dialog) -> bool:
    if obj is None or dialog is None:
        return False
    if obj is dialog:
        return True
    try:
        if isinstance(obj, QWidget) and dialog.isAncestorOf(obj):
            return True
    except Exception:
        pass
    try:
        parent = obj.parent()
        while parent is not None:
            if parent is dialog:
                return True
            parent = parent.parent()
    except Exception:
        pass
    return False


def _reativar_caixa_texto(ferramenta, canvas) -> None:
    def aplicar():
        try:
            dialog = ferramenta._dialogo(canvas)
        except Exception:
            dialog = None
        if dialog is None:
            return
        try:
            if not dialog.isVisible():
                dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception:
            pass
        try:
            dialog.txt_texto.setFocus(Qt.OtherFocusReason)
        except Exception:
            pass

    aplicar()
    QTimer.singleShot(0, aplicar)
    QTimer.singleShot(20, aplicar)
    QTimer.singleShot(60, aplicar)
    QTimer.singleShot(120, aplicar)


class _FiltroTecladoTexto(QObject):
    def __init__(self, app):
        super().__init__(app)
        self._redirecionando = False

    def eventFilter(self, obj, event):  # noqa: N802
        if self._redirecionando:
            return False

        tipo = event.type()
        if tipo not in (QEvent.KeyPress, QEvent.KeyRelease, QEvent.ShortcutOverride):
            return False

        dialog = _dialogo_visivel_mais_recente()
        if dialog is None:
            return False

        if _objeto_esta_dentro_dialogo(obj, dialog):
            return False

        try:
            editor = dialog.txt_texto
        except Exception:
            return False

        # Não rouba atalhos principais com Ctrl/Cmd/Alt, exceto texto comum sem modificadores especiais.
        try:
            modificadores = event.modifiers()
            if modificadores & (Qt.ControlModifier | Qt.MetaModifier | Qt.AltModifier):
                return False
        except Exception:
            pass

        try:
            novo_evento = QKeyEvent(
                event.type(),
                event.key(),
                event.modifiers(),
                event.nativeScanCode(),
                event.nativeVirtualKey(),
                event.nativeModifiers(),
                event.text(),
                event.isAutoRepeat(),
                event.count(),
            )
        except Exception:
            try:
                novo_evento = QKeyEvent(event.type(), event.key(), event.modifiers(), event.text())
            except Exception:
                return False

        self._redirecionando = True
        try:
            editor.setFocus(Qt.OtherFocusReason)
            QApplication.sendEvent(editor, novo_evento)
        finally:
            self._redirecionando = False
        return True


def _instalar_filtro_teclado_global() -> None:
    global _FILTRO_TEXTO_APP
    app = QApplication.instance()
    if app is None or _FILTRO_TEXTO_APP is not None:
        return
    filtro = _FiltroTecladoTexto(app)
    app.installEventFilter(filtro)
    _FILTRO_TEXTO_APP = filtro


def aplicar_patch_foco_inserir_texto() -> None:
    try:
        from tools import inserir_texto_tool
    except Exception:
        return

    Ferramenta = getattr(inserir_texto_tool, "Ferramenta", None)
    if Ferramenta is None or getattr(Ferramenta, "_guimma_patch_foco_texto_v2", False):
        return

    _instalar_filtro_teclado_global()

    original_fixar = getattr(Ferramenta, "_fixar_previa_como_copia_e_manter_caixa", None)
    original_on_mouse_press = getattr(Ferramenta, "on_mouse_press", None)

    if original_fixar is not None:
        def _fixar_previa_como_copia_e_manter_caixa_com_foco(self, canvas):
            resultado = original_fixar(self, canvas)
            _reativar_caixa_texto(self, canvas)
            return resultado

        Ferramenta._fixar_previa_como_copia_e_manter_caixa = _fixar_previa_como_copia_e_manter_caixa_com_foco

    if original_on_mouse_press is not None:
        def on_mouse_press_com_foco(self, canvas, event):
            resultado = original_on_mouse_press(self, canvas, event)
            try:
                if event.button() == Qt.LeftButton and self._dialogo(canvas) is not None:
                    _reativar_caixa_texto(self, canvas)
            except Exception:
                pass
            return resultado

        Ferramenta.on_mouse_press = on_mouse_press_com_foco

    Ferramenta._guimma_patch_foco_texto_v1 = True
    Ferramenta._guimma_patch_foco_texto_v2 = True


aplicar_patch_foco_inserir_texto()
