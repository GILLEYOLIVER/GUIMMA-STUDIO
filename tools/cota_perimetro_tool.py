from __future__ import annotations

from math import atan2, cos, sin, sqrt

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from tools.cota_persistente_utils import aplicar_patch_canvas_cotas, serializar_cota
from tools.medicao_utils import mensagem_status, selecionar_segmento_mais_proximo
from tools.texto_config import aplicar_fonte_texto, cor_texto, configurar_texto_canvas
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "cota_perimetro"
    nome = "Cota Perímetro"
    descricao_painel = "1º clique seleciona o perímetro, 2º clique cria a cota, mova o mouse e clique para fixar."
    gerencia_coordenadas_operacao = True

    COR_REALCE = "#2da8ff"
    COR_FUNDO = QColor(0, 0, 0, 0)

    def __init__(self):
        super().__init__()
        self._selecionado: dict | None = None
        self._cota_em_maos: dict | None = None
        self._estado = "aguardando_perimetro"

    def on_activate(self, canvas):
        super().on_activate(canvas)
        configurar_texto_canvas(canvas)
        aplicar_patch_canvas_cotas(canvas)
        self._selecionado = None
        self._cota_em_maos = None
        self._estado = "aguardando_perimetro"
        texto = "Cota Perímetro: clique no trecho que deseja cotar."
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()

    def on_deactivate(self, canvas):
        self._selecionado = None
        self._cota_em_maos = None
        self._estado = "aguardando_perimetro"
        canvas.update()
        super().on_deactivate(canvas)

    def on_mouse_press(self, canvas, event) -> bool:
        aplicar_patch_canvas_cotas(canvas)
        if event.button() == Qt.RightButton:
            self._cancelar_etapa(canvas)
            event.accept()
            return True

        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())

        if self._estado == "aguardando_perimetro":
            info = selecionar_segmento_mais_proximo(canvas, pos, tolerancia_px=14.0)
            if info is None:
                texto = "Cota Perímetro: nenhum perímetro encontrado no clique."
                self.set_status(texto)
                mensagem_status(canvas, texto)
                event.accept()
                return True
            self._selecionado = info
            self._estado = "perimetro_selecionado"
            medida = self._formatar_medida(canvas, float(info.get("perimetro_total", 0.0)))
            texto = f"Cota Perímetro: trecho selecionado {medida}. Clique para criar a seta."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            canvas.update()
            event.accept()
            return True

        if self._estado == "perimetro_selecionado" and self._selecionado:
            self._cota_em_maos = self._criar_cota(canvas, self._selecionado, pos)
            self._estado = "arrastando_cota"
            texto = "Cota Perímetro: mova o mouse para posicionar a medida e clique para fixar."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            canvas.update()
            event.accept()
            return True

        if self._estado == "arrastando_cota" and self._cota_em_maos:
            self._cota_em_maos["label_pos"] = QPointF(pos)
            elemento = serializar_cota(self._cota_em_maos, canvas)
            canvas.cena.elementos.append(elemento)
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
            self._selecionado = None
            self._cota_em_maos = None
            self._estado = "aguardando_perimetro"
            texto = "Cota Perímetro: cota fixada. Clique em outro trecho para criar nova cota."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            canvas.update()
            event.accept()
            return True

        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._estado == "arrastando_cota" and self._cota_em_maos:
            pos = canvas._ponto_com_snap(event.position())
            self._cota_em_maos["label_pos"] = QPointF(pos)
            canvas.update()
            return True
        return False

    def on_paint_overlay(self, canvas, painter):
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            if self._selecionado:
                pontos = self._pontos_para_realce(self._selecionado)
                if len(pontos) >= 2:
                    self._desenhar_realce(canvas, painter, pontos)

            if self._cota_em_maos:
                self._desenhar_cota(canvas, painter, self._cota_em_maos)
        finally:
            painter.restore()

    def desfazer_etapa(self, canvas) -> bool:
        if self._estado == "arrastando_cota":
            self._cota_em_maos = None
            self._estado = "perimetro_selecionado" if self._selecionado else "aguardando_perimetro"
            canvas.update()
            return True
        if self._selecionado:
            self._selecionado = None
            self._estado = "aguardando_perimetro"
            canvas.update()
            return True
        return False

    def _cancelar_etapa(self, canvas) -> None:
        if self._estado == "arrastando_cota":
            self._cota_em_maos = None
            self._estado = "perimetro_selecionado" if self._selecionado else "aguardando_perimetro"
            texto = "Cota Perímetro: arraste cancelado."
        elif self._selecionado:
            self._selecionado = None
            self._estado = "aguardando_perimetro"
            texto = "Cota Perímetro: seleção limpa. Clique em outro trecho."
        else:
            texto = "Cota Perímetro: clique no trecho que deseja cotar."
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()

    def _criar_cota(self, canvas, info: dict, label_pos: QPointF) -> dict:
        pontos = self._pontos_para_realce(info)
        ancora = info.get("ponto_mais_proximo")
        if ancora is None:
            ancora = pontos[len(pontos) // 2] if pontos else QPointF(label_pos)
        return {
            "pontos": [QPointF(p) for p in pontos],
            "ancora": QPointF(ancora),
            "label_pos": QPointF(label_pos),
            "valor": float(info.get("perimetro_total", 0.0)),
        }

    def _pontos_para_realce(self, info: dict) -> list[QPointF]:
        pontos = info.get("pontos_elemento") or info.get("pontos_medicao") or []
        resultado = [QPointF(p) for p in pontos if p is not None]
        if len(resultado) >= 2:
            return resultado
        a = info.get("segmento_inicio")
        b = info.get("segmento_fim")
        if a is not None and b is not None:
            return [QPointF(a), QPointF(b)]
        return []

    def _desenhar_realce(self, canvas, painter, pontos: list[QPointF]):
        cor = QColor(self.COR_REALCE)
        try:
            canvas._desenhar_polilinha(painter, pontos, cor=cor.name(), espessura=3.0)
            return
        except Exception:
            pass
        pen = QPen(cor, 3.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for a, b in zip(pontos, pontos[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))

    def _desenhar_cota(self, canvas, painter, cota: dict):
        ancora = QPointF(cota.get("ancora", QPointF(0.0, 0.0)))
        label_pos = QPointF(cota.get("label_pos", ancora))
        valor = float(cota.get("valor", 0.0))
        texto = self._formatar_medida(canvas, valor)
        cor = cor_texto(canvas)

        p_ancora = canvas._cena_para_tela(ancora)
        p_label = canvas._cena_para_tela(label_pos)

        pen = QPen(cor, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        self._desenhar_seta(painter, p_label, p_ancora, cor)

        aplicar_fonte_texto(painter, canvas, negrito=True)
        metrics = painter.fontMetrics()
        largura = metrics.horizontalAdvance(texto) + 16
        altura = metrics.height() + 8
        rect = QRectF(p_label.x() - largura / 2.0, p_label.y() - altura / 2.0, largura, altura)
        painter.fillRect(rect, self.COR_FUNDO)
        painter.setPen(QPen(cor, 1.0))
        painter.drawText(rect, Qt.AlignCenter, texto)

    def _desenhar_seta(self, painter, inicio: QPointF, fim: QPointF, cor: QColor):
        painter.drawLine(inicio, fim)
        dx = inicio.x() - fim.x()
        dy = inicio.y() - fim.y()
        dist = sqrt((dx * dx) + (dy * dy))
        if dist <= 1e-6:
            return
        ang = atan2(dy, dx)
        tam = 16.0
        abertura = 0.55
        p1 = QPointF(fim.x() + cos(ang - abertura) * tam, fim.y() + sin(ang - abertura) * tam)
        p2 = QPointF(fim.x() + cos(ang + abertura) * tam, fim.y() + sin(ang + abertura) * tam)
        painter.drawLine(fim, p1)
        painter.drawLine(fim, p2)

    def _formatar_medida(self, canvas, valor_cena: float) -> str:
        if hasattr(canvas, "formatar_distancia"):
            try:
                return canvas.formatar_distancia(valor_cena)
            except Exception:
                pass
        valor = canvas.formatar_valor_unidade(valor_cena) if hasattr(canvas, "formatar_valor_unidade") else f"{valor_cena:.2f}"
        unidade = getattr(canvas, "_unidade_sigla", "cm")
        return f"{valor} {unidade}"
