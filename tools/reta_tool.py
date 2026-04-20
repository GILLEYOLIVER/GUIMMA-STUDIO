from __future__ import annotations

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "reta"
    nome = "Reta"

    def on_mouse_press(self, canvas, event) -> bool:
        canvas._mouse_press_reta(event)
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        canvas._mouse_move_reta(event)
        return True
