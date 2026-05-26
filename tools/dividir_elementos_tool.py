from __future__ import annotations

from PySide6.QtCore import Qt

from tools.cortar_tool import Ferramenta as FerramentaCortar


class Ferramenta(FerramentaCortar):
    id_ferramenta = "dividir_elementos"
    nome = "Dividir elementos"
    usa_painel_auxiliar = True
    descricao_painel = (
        "Clique sobre uma linha do elemento para separar a polyline em partes independentes. "
        "Use Shift ao clicar para manter as duas partes selecionadas."
    )

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._status(canvas, self._texto_ajuda())

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            self._status(canvas, self._texto_ajuda())
            return False
        return super().on_mouse_press(canvas, event)

    def _texto_ajuda(self) -> str:
        return (
            "Dividir elementos: clique em cima de uma linha/curva. "
            "Elemento aberto vira duas partes independentes. "
            "Contorno fechado é aberto no ponto clicado. "
            "Shift + clique mantém os dois lados selecionados."
        )
