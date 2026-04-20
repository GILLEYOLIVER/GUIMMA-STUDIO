from __future__ import annotations

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "curva"
    nome = "Curva"

    def on_mouse_press(self, canvas, event) -> bool:
        canvas._mouse_press_curva(event)
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        canvas._mouse_move_curva(event)
        return True
