from __future__ import annotations

from math import atan2, degrees, sqrt

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPen

from tools.medicao_utils import mensagem_status
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "comparar_distancia"
    nome = "Comparar Distancia"
    descricao_painel = "Compare distâncias entre pontos ou locais no perímetro."

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._ponto_inicio: QPointF | None = None
        self._ponto_preview: QPointF | None = None
        self._ponto_final: QPointF | None = None
        self._medidas: list[tuple[QPointF, QPointF]] = []

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._resetar_fluxo()
        self._status(canvas, "Comparar distância: clique no molde inicial.")
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._voltar_etapa(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        if self._molde_idx is None:
            molde_idx = self._molde_em_posicao(canvas, pos)
            if molde_idx is None:
                self._status(canvas, "Comparar distância: clique sobre o molde inicial.")
                event.accept()
                return True
            self._molde_idx = molde_idx
            self._ponto_inicio = None
            self._ponto_preview = None
            self._ponto_final = None
            canvas._selecionados = {molde_idx}
            self._status(canvas, "Molde inicial realçado. Clique no ponto ou local do perímetro.")
            canvas.update()
            event.accept()
            return True

        if self._ponto_inicio is None:
            ponto = self._ponto_no_perimetro(canvas, self._molde_idx, pos)
            if ponto is None:
                self._status(canvas, "Comparar distância: indique um ponto no perímetro do molde realçado.")
                event.accept()
                return True
            self._ponto_inicio = ponto
            self._ponto_preview = ponto
            self._ponto_final = None
            self._status(canvas, "Ponto inicial cravado. Mova o mouse até o destino e clique para finalizar.")
            canvas.update()
            event.accept()
            return True

        destino = self._ponto_destino(canvas, pos)
        self._ponto_final = destino
        self._medidas.append((QPointF(self._ponto_inicio), QPointF(destino)))
        self._status_medida(canvas, self._ponto_inicio, destino, final=True)
        self._molde_idx = None
        self._ponto_inicio = None
        self._ponto_preview = None
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if self._molde_idx is None:
            return False
        if self._ponto_inicio is None:
            self._ponto_preview = self._ponto_no_perimetro(canvas, self._molde_idx, pos)
            canvas.update()
            return True
        self._ponto_preview = self._ponto_destino(canvas, pos)
        self._status_medida(canvas, self._ponto_inicio, self._ponto_preview, final=False)
        canvas.update()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_medidas_finalizadas(canvas, painter)
        if self._molde_idx is not None:
            self._desenhar_realce_molde(canvas, painter, self._molde_idx)
        if self._ponto_inicio is not None:
            self._desenhar_alvo(canvas, painter, self._ponto_inicio, "#ff2a2a")
        elif self._ponto_preview is not None:
            self._desenhar_alvo(canvas, painter, self._ponto_preview, "#ff2a2a")
        if self._ponto_inicio is not None and self._ponto_preview is not None:
            self._desenhar_linha_medida(canvas, painter, self._ponto_inicio, self._ponto_preview, preview=True)

    def _voltar_etapa(self, canvas):
        if self._ponto_inicio is not None:
            self._ponto_inicio = None
            self._ponto_preview = None
            self._ponto_final = None
            self._status(canvas, "Etapa cancelada. Clique em outro ponto do perímetro.")
        elif self._molde_idx is not None:
            self._molde_idx = None
            self._ponto_preview = None
            self._ponto_final = None
            self._status(canvas, "Etapa cancelada. Clique no molde inicial.")
        elif self._medidas:
            self._medidas.pop()
            self._status(canvas, "Última comparação removida. Clique no molde inicial.")
        else:
            self._status(canvas, "Comparar distância: clique no molde inicial.")
        canvas.update()

    def _resetar_fluxo(self):
        self._molde_idx = None
        self._ponto_inicio = None
        self._ponto_preview = None
        self._ponto_final = None
        self._medidas.clear()

    def _status(self, canvas, texto: str):
        self.set_status(texto)
        mensagem_status(canvas, texto)

    def _status_medida(self, canvas, inicio: QPointF, fim: QPointF, *, final: bool):
        dx = fim.x() - inicio.x()
        dy = fim.y() - inicio.y()
        distancia = sqrt((dx * dx) + (dy * dy))
        angulo = degrees(atan2(-dy, dx)) % 360.0
        prefixo = "Comparação finalizada" if final else "Comparação prévia"
        texto = (
            f"{prefixo}: distância {canvas.formatar_valor_unidade(distancia)} "
            f"| DX {canvas.formatar_valor_unidade(dx)} | DY {canvas.formatar_valor_unidade(dy)} "
            f"| ângulo {angulo:.1f}°"
        )
        self._status(canvas, texto)

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        molde_idx = canvas._indice_molde_em_ponto(pos)
        if molde_idx is not None:
            return molde_idx
        melhor: tuple[float, int] | None = None
        tolerancia = max(0.1, 18.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.01))
        for idx, el in enumerate(canvas.cena.elementos):
            if not isinstance(el, dict) or not el.get("molde"):
                continue
            pontos_molde = canvas._pontos_render_elemento(el)
            if self._ponto_dentro_poligono(pos, pontos_molde):
                return idx
            ponto = self._ponto_no_perimetro(canvas, idx, pos)
            if ponto is None:
                continue
            dist = self._dist(pos, ponto)
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, idx)
        return melhor[1] if melhor is not None else None

    def _ponto_destino(self, canvas, pos: QPointF) -> QPointF:
        molde_idx = self._molde_em_posicao(canvas, pos)
        if molde_idx is not None:
            ponto = self._ponto_no_perimetro(canvas, molde_idx, pos)
            if ponto is not None:
                return ponto
        return QPointF(pos)

    def _ponto_no_perimetro(self, canvas, molde_idx: int, pos: QPointF) -> QPointF | None:
        if molde_idx < 0 or molde_idx >= len(canvas.cena.elementos):
            return None
        pontos = canvas._pontos_render_elemento(canvas.cena.elementos[molde_idx])
        if len(pontos) < 2:
            return None
        melhor_ponto: QPointF | None = None
        melhor_dist = float("inf")
        for a, b in zip(pontos, pontos[1:]):
            ponto = self._projetar_ponto_segmento(a, b, pos)
            dist = self._dist(pos, ponto)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_ponto = ponto
        return melhor_ponto

    def _desenhar_realce_molde(self, canvas, painter, molde_idx: int):
        if molde_idx < 0 or molde_idx >= len(canvas.cena.elementos):
            return
        pontos = canvas._pontos_render_elemento(canvas.cena.elementos[molde_idx])
        if len(pontos) < 2:
            return
        painter.save()
        canvas._desenhar_polilinha(painter, pontos, cor="#ff2020", espessura=2.2)
        painter.restore()

    def _desenhar_medidas_finalizadas(self, canvas, painter):
        for inicio, fim in self._medidas[-6:]:
            self._desenhar_linha_medida(canvas, painter, inicio, fim, preview=False)

    def _desenhar_linha_medida(self, canvas, painter, inicio: QPointF, fim: QPointF, *, preview: bool):
        cor = "#ff2020" if preview else "#e02020"
        estilo = Qt.DashLine if preview else Qt.SolidLine
        p0 = canvas._cena_para_tela(inicio)
        p1 = canvas._cena_para_tela(fim)
        painter.save()
        painter.setPen(QPen(QColor(cor), 2.0, estilo))
        painter.drawLine(p0, p1)
        self._desenhar_alvo(canvas, painter, inicio, cor)
        self._desenhar_alvo(canvas, painter, fim, cor)
        distancia = self._dist(inicio, fim)
        texto = canvas.formatar_valor_unidade(distancia)
        meio = QPointF((p0.x() + p1.x()) / 2.0, (p0.y() + p1.y()) / 2.0)
        metrics = QFontMetrics(painter.font())
        largura = metrics.horizontalAdvance(texto) + 10
        altura = metrics.height() + 6
        rect = QRectF(meio.x() + 8, meio.y() - altura - 4, largura, altura)
        painter.fillRect(rect, QColor(0, 0, 0, 190))
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.drawText(rect, Qt.AlignCenter, texto)
        painter.restore()

    def _desenhar_alvo(self, canvas, painter, ponto: QPointF, cor: str):
        tela = canvas._cena_para_tela(ponto)
        painter.save()
        painter.setPen(QPen(QColor(cor), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(tela.x() - 7.0, tela.y() - 7.0, 14.0, 14.0))
        painter.drawLine(QPointF(tela.x() - 10.0, tela.y()), QPointF(tela.x() + 10.0, tela.y()))
        painter.drawLine(QPointF(tela.x(), tela.y() - 10.0), QPointF(tela.x(), tela.y() + 10.0))
        painter.restore()

    @staticmethod
    def _projetar_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> QPointF:
        vx = b.x() - a.x()
        vy = b.y() - a.y()
        den = (vx * vx) + (vy * vy)
        if den <= 1e-12:
            return QPointF(a)
        t = ((p.x() - a.x()) * vx + (p.y() - a.y()) * vy) / den
        t = max(0.0, min(1.0, t))
        return QPointF(a.x() + (vx * t), a.y() + (vy * t))

    @staticmethod
    def _ponto_dentro_poligono(ponto: QPointF, pontos: list[QPointF]) -> bool:
        if len(pontos) < 3:
            return False
        base = pontos[:-1] if pontos[0] == pontos[-1] else pontos
        dentro = False
        j = len(base) - 1
        px = ponto.x()
        py = ponto.y()
        for i, atual in enumerate(base):
            anterior = base[j]
            yi = atual.y()
            yj = anterior.y()
            cruza = (yi > py) != (yj > py)
            if cruza:
                xi = atual.x()
                xj = anterior.x()
                den = yj - yi
                if abs(den) <= 1e-12:
                    j = i
                    continue
                x_inter = ((xj - xi) * (py - yi) / den) + xi
                if px < x_inter:
                    dentro = not dentro
            j = i
        return dentro

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)
