from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

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
        if canvas._modo_curva in {"3p", "np"}:
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
                if canvas._modo_curva == "np":
                    novo_inicio = QPointF(canvas._curva_p2)
                    canvas._finalizar_curva()
                    canvas._curva_p0 = novo_inicio
                    canvas._curva_estado = "aguardando_ponto2"
                    canvas._curva_preview_fim = None
                else:
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
        if canvas._arrastando_alca_curva is not None:
            idx, chave = canvas._arrastando_alca_curva
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                if el.get("tipo") == "bezier_quadratica":
                    el[chave] = (pos.x(), pos.y())
                    canvas.update()
                    event.accept()
                    return True
        if canvas._curva_estado == "aguardando_final":
            canvas._curva_preview_fim = pos
        elif canvas._curva_estado == "aguardando_ponto2":
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

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton or canvas._arrastando_alca_curva is None:
            return False
        canvas._arrastando_alca_curva = None
        canvas._registrar_historico()
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        estado = canvas._curva_estado
        p0 = canvas._curva_p0
        p1 = canvas._curva_p1
        p2 = canvas._curva_p2
        pm = canvas._curva_pmedio
        preview = canvas._curva_preview_fim

        pen_guia = QPen(QColor("#f36cff"), 1.0, Qt.DashLine)
        painter.setPen(pen_guia)

        if estado == "aguardando_ponto2" and p0 is not None:
            canvas._desenhar_marca_x(painter, p0, cor="#ff4fd8")
            if preview is not None:
                canvas._desenhar_segmento(painter, p0, preview, tracejado=True, cor="#f36cff", espessura=1.0)
            return

        if estado == "aguardando_final" and p0 is not None:
            canvas._desenhar_marca_x(painter, p0, cor="#ff4fd8")
            if preview is not None:
                canvas._desenhar_segmento(painter, p0, preview, tracejado=True, cor="#f36cff", espessura=1.0)
            return

        if estado == "aguardando_ponto3" and p0 is not None and pm is not None:
            canvas._desenhar_marca_x(painter, p0, cor="#ff4fd8")
            canvas._desenhar_marca_x(painter, pm, cor="#5dc8ff")
            canvas._desenhar_segmento(painter, p0, pm, tracejado=True, cor="#f36cff", espessura=1.0)
            if preview is not None:
                canvas._desenhar_segmento(painter, pm, preview, tracejado=True, cor="#f36cff", espessura=1.0)
            if p1 is not None and p2 is not None:
                canvas._desenhar_bezier_quadratica(
                    painter,
                    p0,
                    p1,
                    p2,
                    cor="#ff4fd8",
                    espessura=max(1.0, float(getattr(canvas, "_linha_espessura", 1.0))),
                    estilo="solid",
                    amplitude=1.0,
                    destacar_controles=True,
                )
            return

        if estado == "aguardando_controle" and p0 is not None and p2 is not None and p1 is not None:
            canvas._desenhar_segmento(painter, p0, p1, tracejado=True, cor="#5dc8ff", espessura=1.0)
            canvas._desenhar_segmento(painter, p1, p2, tracejado=True, cor="#5dc8ff", espessura=1.0)
            canvas._desenhar_bezier_quadratica(
                painter,
                p0,
                p1,
                p2,
                cor="#ff4fd8",
                espessura=max(1.0, float(getattr(canvas, "_linha_espessura", 1.0))),
                estilo="solid",
                amplitude=1.0,
                destacar_controles=True,
            )
