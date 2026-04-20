from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "curva"
    nome = "Curva"
    descricao_painel = "Curva 2P/3P. Clique esquerdo marca pontos. Clique direito finaliza/cancela."

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self.set_status("Defina os pontos da curva. RMB finaliza e outro RMB retorna para Selecionar.")

    def on_mouse_press(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if event.button() == Qt.RightButton:
            if canvas._cliques_direito_curva >= 2:
                canvas._resetar_estado_curva()
                canvas._cliques_direito_curva = 0
                canvas.ferramenta_padrao_solicitada.emit("selecionar")
                canvas.update()
                event.accept()
                return True
            if canvas._cliques_direito_curva >= 1:
                canvas._resetar_estado_curva()
                canvas._cliques_direito_curva = 2
                canvas.update()
                event.accept()
                return True
            if canvas._curva_pronta_para_finalizar():
                canvas._finalizar_curva()
            else:
                canvas._resetar_estado_curva()
            canvas._cliques_direito_curva = 1
            canvas.update()
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        if canvas._curva_estado == "parada":
            alca = canvas._alca_curva_em_ponto(pos)
            if alca is not None:
                canvas._arrastando_alca_curva = alca
                event.accept()
                return True
        canvas._cliques_direito_curva = 0
        if canvas._modo_curva == "3p":
            if canvas._curva_estado in {"parada", "aguardando_inicial"}:
                canvas._curva_p0 = pos
                canvas._curva_pmedio = None
                canvas._curva_p2 = None
                canvas._curva_p1 = None
                canvas._curva_preview_fim = None
                canvas._curva_estado = "aguardando_ponto2"
            elif canvas._curva_estado == "aguardando_ponto2":
                canvas._curva_pmedio = pos
                canvas._curva_estado = "aguardando_ponto3"
            elif canvas._curva_estado == "aguardando_ponto3":
                canvas._curva_p2 = pos
                canvas._curva_p1 = canvas._controle_para_tres_pontos(canvas._curva_p0, canvas._curva_pmedio, canvas._curva_p2)
                canvas._finalizar_curva()
            canvas.update()
            event.accept()
            return True
        if canvas._curva_estado in {"parada", "aguardando_inicial"}:
            canvas._curva_p0 = pos
            canvas._curva_p2 = None
            canvas._curva_p1 = None
            canvas._curva_preview_fim = None
            canvas._curva_estado = "aguardando_final"
        elif canvas._curva_estado == "aguardando_final":
            canvas._curva_p2 = pos
            canvas._curva_p1 = QPointF((canvas._curva_p0.x() + canvas._curva_p2.x()) / 2.0, (canvas._curva_p0.y() + canvas._curva_p2.y()) / 2.0)
            canvas._curva_estado = "aguardando_controle"
        elif canvas._curva_estado == "aguardando_controle":
            canvas._curva_p1 = pos
            canvas._finalizar_curva()
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if canvas._curva_estado == "aguardando_final":
            canvas._curva_preview_fim = pos
        elif canvas._curva_estado == "aguardando_controle":
            canvas._curva_p1 = pos
        elif canvas._curva_estado == "aguardando_ponto3" and canvas._curva_p0 and canvas._curva_pmedio:
            canvas._curva_preview_fim = pos
            canvas._curva_p2 = pos
            canvas._curva_p1 = canvas._controle_para_tres_pontos(canvas._curva_p0, canvas._curva_pmedio, canvas._curva_p2)
        canvas.update()
        event.accept()
        return True
