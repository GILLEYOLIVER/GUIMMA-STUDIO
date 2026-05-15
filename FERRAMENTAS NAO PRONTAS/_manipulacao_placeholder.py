from __future__ import annotations

from tools.tool_base import FerramentaBase


class FerramentaManipulacaoPlaceholder(FerramentaBase):
    usa_painel_auxiliar = False
    descricao_painel = "Comando reservado para a aba Manipulação."

    def ativar(self) -> str:
        return f"{self.nome}: comando disponivel na aba Manipulacao."

    def on_activate(self, canvas) -> None:
        texto = self.ativar()
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
