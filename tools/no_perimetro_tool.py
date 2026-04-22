from __future__ import annotations

from PySide6.QtCore import Qt

from tools.medicao_utils import mensagem_status, selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "no_perimetro"
    nome = "No Perimetro"
    descricao_painel = "Clique no contorno para exibir o perímetro na barra."

    def on_activate(self, canvas):
        super().on_activate(canvas)
        texto = "Perímetro: clique em uma linha/curva para calcular o perímetro."
        self.set_status(texto)
        mensagem_status(canvas, texto)

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if info is None:
            texto = "Nenhum contorno encontrado para perímetro."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            event.accept()
            return True
        per = canvas.formatar_valor_unidade(info["perimetro_total"])
        unidade = getattr(canvas, "_unidade_sigla", "cm")
        texto = f"Perímetro P: {per} ({unidade})"
        self.set_status(texto)
        mensagem_status(canvas, texto)
        event.accept()
        return True
