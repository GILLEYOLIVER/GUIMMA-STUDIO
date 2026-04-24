from __future__ import annotations

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "estender_reta"
    nome = "Estender reta"
    usa_painel_auxiliar = False

    def on_mouse_press(self, canvas, event) -> bool:
        from PySide6.QtCore import Qt

        if event.button() != Qt.LeftButton:
            return False
        canvas._processar_estender_reta(canvas._ponto_com_snap(event.position()), ate_elemento=False)
        event.accept()
        return True
