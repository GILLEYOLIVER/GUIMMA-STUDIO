from __future__ import annotations

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "dividir_curva"
    nome = "Dividir Curva"

    def on_mouse_press(self, canvas, event) -> bool:
        from PySide6.QtCore import Qt

        if event.button() != Qt.LeftButton:
            return False
        canvas._dividir_segmento_em_clique(canvas._ponto_com_snap(event.position()))
        event.accept()
        return True
