from __future__ import annotations

from tools.tool_base import FerramentaBase


class FerramentaSelecaoInstantanea(FerramentaBase):
    metodo_canvas = ""
    mensagem_status = "Seleção atualizada."

    def on_activate(self, canvas) -> None:
        super().on_activate(canvas)
        metodo = getattr(canvas, self.metodo_canvas, None)
        if callable(metodo):
            metodo()
        self._voltar_para_selecionar(canvas)
        self._status(canvas, self._mensagem(canvas))

    def _mensagem(self, canvas) -> str:
        total = len(getattr(canvas, "_selecionados", set()) or set())
        return self.mensagem_status.format(total=total)

    def _voltar_para_selecionar(self, canvas) -> None:
        sinal = getattr(canvas, "ferramenta_padrao_solicitada", None)
        emitir = getattr(sinal, "emit", None)
        if callable(emitir):
            emitir("selecionar")
            return
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        label = getattr(canvas, "lbl_status", None)
        if label is not None:
            if hasattr(label, "setText"):
                label.setText(texto)
            else:
                try:
                    label.text = texto
                except Exception:
                    pass
