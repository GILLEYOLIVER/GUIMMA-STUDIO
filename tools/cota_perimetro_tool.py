from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from tools.medicao_utils import mensagem_status, selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "cota_perimetro"
    nome = "Cota Perímetro"
    descricao_painel = "Clique em uma linha/curva para medir o perímetro de ponto a ponto."

    COR_REALCE = "#2da8ff"
    COR_TEXTO = "#ffffff"
    COR_FUNDO = QColor(0, 0, 0, 205)

    def __init__(self):
        super().__init__()
        self._destaque: dict | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._destaque = None
        texto = "Perímetro: clique em uma linha ou curva para medir de ponto a ponto."
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()

    def on_deactivate(self, canvas):
        self._destaque = None
        canvas.update()
        if hasattr(super(), "on_deactivate"):
            try:
                super().on_deactivate(canvas)
            except Exception:
                pass

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._destaque = None
            texto = "Perímetro: medição limpa. Clique em outra linha ou curva."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            canvas.update()
            event.accept()
            return True

        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos, tolerancia_px=14.0)
        if info is None:
            texto = "Perímetro: nenhum segmento encontrado no clique."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            event.accept()
            return True

        self._destaque = info
        medida = self._formatar_medida(canvas, info["perimetro_total"])
        texto = f"Perímetro de ponto a ponto: {medida}"
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if not self._destaque:
            return

        pontos = self._destaque.get("pontos_elemento") or []
        if len(pontos) < 2:
            a = self._destaque.get("segmento_inicio")
            b = self._destaque.get("segmento_fim")
            pontos = [a, b] if a is not None and b is not None else []
        if len(pontos) < 2:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cor_realce = self._cor_realce(canvas)
        try:
            canvas._desenhar_polilinha(painter, pontos, cor=cor_realce, espessura=2.8)
        except Exception:
            for a, b in zip(pontos, pontos[1:]):
                canvas._desenhar_segmento(painter, a, b, cor=cor_realce, espessura=2.8)

        self._desenhar_marcador_extremo(canvas, painter, pontos[0], cor_realce)
        self._desenhar_marcador_extremo(canvas, painter, pontos[-1], cor_realce)
        self._desenhar_rotulo_medida(canvas, painter, pontos, cor_realce)

        painter.restore()

    def _cor_realce(self, canvas) -> str:
        try:
            cores = getattr(canvas, "_cores_canvas", {}) or {}
            cor = QColor(str(cores.get("selecao") or self.COR_REALCE))
            if cor.isValid():
                return cor.name()
        except Exception:
            pass
        return self.COR_REALCE

    def _formatar_medida(self, canvas, valor_cena: float) -> str:
        if hasattr(canvas, "formatar_distancia"):
            try:
                return canvas.formatar_distancia(valor_cena)
            except Exception:
                pass
        valor = canvas.formatar_valor_unidade(valor_cena) if hasattr(canvas, "formatar_valor_unidade") else f"{valor_cena:.2f}"
        unidade = getattr(canvas, "_unidade_sigla", "cm")
        return f"{valor} {unidade}"

    def _desenhar_marcador_extremo(self, canvas, painter, ponto: QPointF, cor: str):
        tela = canvas._cena_para_tela(ponto)
        painter.setPen(QPen(QColor(cor), 1.6))
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.drawRect(QRectF(tela.x() - 3.8, tela.y() - 3.8, 7.6, 7.6))

    def _desenhar_rotulo_medida(self, canvas, painter, pontos: list[QPointF], cor: str):
        texto = f"P {self._formatar_medida(canvas, self._destaque['perimetro_total'])}"
        base = self._destaque.get("ponto_mais_proximo")
        if base is None:
            base = pontos[len(pontos) // 2]
        tela = canvas._cena_para_tela(base)

        metrics = painter.fontMetrics()
        largura = metrics.horizontalAdvance(texto) + 14
        altura = metrics.height() + 8
        x = tela.x() + 12.0
        y = tela.y() - altura - 10.0

        # Evita que o rótulo saia para fora da área visível do canvas.
        try:
            max_x = max(4.0, float(canvas.width()) - largura - 4.0)
            max_y = max(4.0, float(canvas.height()) - altura - 4.0)
            x = min(max(4.0, x), max_x)
            y = min(max(4.0, y), max_y)
        except Exception:
            pass

        rect = QRectF(x, y, largura, altura)
        painter.fillRect(rect, self.COR_FUNDO)
        painter.setPen(QPen(QColor(cor), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 3.0, 3.0)
        painter.setPen(QPen(QColor(self.COR_TEXTO), 1.0))
        painter.drawText(rect, Qt.AlignCenter, texto)
