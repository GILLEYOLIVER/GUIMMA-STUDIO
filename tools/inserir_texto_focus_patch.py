from __future__ import annotations

from PySide6.QtCore import Qt, QTimer


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

    # No macOS, um único setFocus logo após o clique às vezes perde para o foco do canvas.
    # Por isso aplicamos agora e repetimos em pequenos atrasos.
    aplicar()
    QTimer.singleShot(0, aplicar)
    QTimer.singleShot(35, aplicar)
    QTimer.singleShot(80, aplicar)


def aplicar_patch_foco_inserir_texto() -> None:
    try:
        from tools import inserir_texto_tool
    except Exception:
        return

    Ferramenta = getattr(inserir_texto_tool, "Ferramenta", None)
    if Ferramenta is None or getattr(Ferramenta, "_guimma_patch_foco_texto_v1", False):
        return

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


aplicar_patch_foco_inserir_texto()
