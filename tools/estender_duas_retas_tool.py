from __future__ import annotations

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "estender_duas_retas"
    nome = "Estender duas retas"

    def on_mouse_press(self, canvas, event) -> bool:
        from PySide6.QtCore import Qt

        if event.button() != Qt.LeftButton:
            return False
        canvas._processar_estender_duas_retas(canvas._ponto_com_snap(event.position()))
        event.accept()
        return True
