from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from tools.medicao_utils import mensagem_status, selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    """Ferramenta simples de leitura de perímetro.

    Esta ferramenta é independente da Cota Perímetro. Ela apenas destaca a
    linha/curva clicada em azul e mostra a medida ao lado do clique, sem criar
    uma cota permanente no desenho.
    """

    id_ferramenta = "perimetro"
    nome = "Perímetro"
    descricao_painel = "Clique em uma linha ou curva para ver o perímetro ao lado do ponto clicado."

    COR_REALCE = "#2da8ff"
    COR_TEXTO = "#ffffff"
    COR_FUNDO = QColor(0, 0, 0, 205)

    def __init__(self):
        super().__init__()
        self._medicao: dict | None = None

    def on_activate(self, canvas) -> None:
        super().on_activate(canvas)
        self._medicao = None
        texto = "Perímetro: clique em uma linha ou curva para medir de ponto a ponto."
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()

    def on_deactivate(self, canvas) -> None:
        self._medicao = None
        canvas.update()
        super().on_deactivate(canvas)

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._limpar(canvas)
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

        self._medicao = info
        medida = self._formatar_medida(canvas, float(info.get("perimetro_total", 0.0)))
        texto = f"Perímetro: {medida}"
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter) -> None:
        if not self._medicao:
            return

        pontos = self._pontos_para_realce()
        if len(pontos) < 2:
            return

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            cor_realce = QColor(self.COR_REALCE)
            if not cor_realce.isValid():
                cor_realce = QColor("#2da8ff")

            self._desenhar_realce(canvas, painter, pontos, cor_realce)
            self._desenhar_extremos(canvas, painter, pontos, cor_realce)
            self._desenhar_rotulo_medida(canvas, painter, pontos, cor_realce)
        finally:
            painter.restore()

    def _limpar(self, canvas) -> None:
        self._medicao = None
        texto = "Perímetro: medição limpa. Clique em outra linha ou curva."
        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()

    def _pontos_para_realce(self) -> list[QPointF]:
        if not self._medicao:
            return []

        pontos = self._medicao.get("pontos_elemento") or []
        resultado = [QPointF(p) for p in pontos if p is not None]
        if len(resultado) >= 2:
            return resultado

        a = self._medicao.get("segmento_inicio")
        b = self._medicao.get("segmento_fim")
        if a is not None and b is not None:
            return [QPointF(a), QPointF(b)]
        return []

    def _desenhar_realce(self, canvas, painter, pontos: list[QPointF], cor_realce: QColor) -> None:
        cor = cor_realce.name()
        try:
            canvas._desenhar_polilinha(painter, pontos, cor=cor, espessura=3.0)
            return
        except Exception:
            pass

        pen = QPen(cor_realce, 3.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for a, b in zip(pontos, pontos[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))

    def _desenhar_extremos(self, canvas, painter, pontos: list[QPointF], cor_realce: QColor) -> None:
        if len(pontos) < 2:
            return
        painter.setPen(QPen(cor_realce, 1.4))
        painter.setBrush(QColor(0, 0, 0, 170))
        for ponto in (pontos[0], pontos[-1]):
            tela = canvas._cena_para_tela(ponto)
            painter.drawEllipse(QRectF(tela.x() - 4.0, tela.y() - 4.0, 8.0, 8.0))

    def _desenhar_rotulo_medida(self, canvas, painter, pontos: list[QPointF], cor_realce: QColor) -> None:
        if not self._medicao:
            return

        texto = f"Perímetro {self._formatar_medida(canvas, float(self._medicao.get('perimetro_total', 0.0)))}"
        base = self._medicao.get("ponto_mais_proximo")
        if base is None:
            base = pontos[len(pontos) // 2]
        tela = canvas._cena_para_tela(base)

        metrics = painter.fontMetrics()
        largura = metrics.horizontalAdvance(texto) + 18
        altura = metrics.height() + 10
        x = tela.x() + 14.0
        y = tela.y() - altura - 12.0

        try:
            max_x = max(4.0, float(canvas.width()) - largura - 4.0)
            max_y = max(4.0, float(canvas.height()) - altura - 4.0)
            x = min(max(4.0, x), max_x)
            y = min(max(4.0, y), max_y)
        except Exception:
            pass

        rect = QRectF(x, y, largura, altura)
        painter.fillRect(rect, self.COR_FUNDO)
        painter.setPen(QPen(cor_realce, 1.3))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 4.0, 4.0)
        painter.setPen(QPen(QColor(self.COR_TEXTO), 1.0))
        painter.drawText(rect, Qt.AlignCenter, texto)

    def _formatar_medida(self, canvas, valor_cena: float) -> str:
        if hasattr(canvas, "formatar_distancia"):
            try:
                return canvas.formatar_distancia(valor_cena)
            except Exception:
                pass

        if hasattr(canvas, "formatar_valor_unidade"):
            try:
                valor = canvas.formatar_valor_unidade(valor_cena)
            except Exception:
                valor = f"{valor_cena:.2f}"
        else:
            valor = f"{valor_cena:.2f}"

        unidade = getattr(canvas, "_unidade_sigla", "cm")
        return f"{valor} {unidade}"
