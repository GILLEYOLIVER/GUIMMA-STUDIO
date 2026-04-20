from __future__ import annotations

from PySide6.QtCore import Qt

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "reta"
    nome = "Reta"

    def on_mouse_press(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if event.button() == Qt.LeftButton:
            canvas.setFocus(Qt.MouseFocusReason)
            canvas._aguardando_retorno_selecao = False
            canvas._cliques_direito_reta = 0
            if not canvas._pontos_reta:
                canvas._pontos_reta.append(pos)
            else:
                pos = canvas._snap_angular(
                    canvas._pontos_reta[-1],
                    pos,
                    travar_snap_exato=canvas._snap_resultado is not None,
                    travar_principais=canvas._tecla_w_trava_principal,
                )
                pos = canvas._aplicar_guia_fechamento(canvas._pontos_reta[-1], pos)
                pos = canvas._aplicar_guias_alinhamento(canvas._pontos_reta[-1], pos)
                canvas._pontos_reta.append(pos)
            canvas._preview_reta = pos
            if len(canvas._pontos_reta) >= 2:
                canvas.painel_coordenadas.atualizar_preview(canvas._pontos_reta[-2], canvas._pontos_reta[-1])
            canvas.update()
            event.accept()
            return True
        if event.button() == Qt.RightButton:
            if canvas._cliques_direito_reta >= 2:
                canvas._pontos_reta.clear()
                canvas._preview_reta = None
                canvas._guia_fechamento = None
                canvas._guias_alinhamento = []
                canvas._aguardando_retorno_selecao = False
                canvas._cliques_direito_reta = 0
                canvas.ferramenta_padrao_solicitada.emit("selecionar")
                canvas.update()
                event.accept()
                return True
            if canvas._cliques_direito_reta >= 1:
                canvas._pontos_reta.clear()
                canvas._preview_reta = None
                canvas._guia_fechamento = None
                canvas._guias_alinhamento = []
                canvas._aguardando_retorno_selecao = False
                canvas._cliques_direito_reta = 2
                canvas.update()
                event.accept()
                return True
            canvas._finalizar_reta_atual()
            canvas._cliques_direito_reta = 1
            canvas.update()
            event.accept()
            return True
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        snap_pos = canvas._ponto_com_snap(event.position())
        if canvas._pontos_reta:
            canvas._preview_reta = canvas._snap_angular(
                canvas._pontos_reta[-1],
                snap_pos,
                travar_snap_exato=canvas._snap_resultado is not None,
                travar_principais=canvas._tecla_w_trava_principal,
            )
            canvas._preview_reta = canvas._aplicar_guia_fechamento(canvas._pontos_reta[-1], canvas._preview_reta)
            canvas._preview_reta = canvas._aplicar_guias_alinhamento(canvas._pontos_reta[-1], canvas._preview_reta)
            canvas.painel_coordenadas.atualizar_preview(canvas._pontos_reta[-1], canvas._preview_reta)
        else:
            canvas._guia_fechamento = None
            canvas._guias_alinhamento = []
        canvas.update()
        event.accept()
        return True
