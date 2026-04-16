from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from canvas.cena import CenaDocumento


class PainelAuxiliarRetas(QFrame):
    desfazer_ponto = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PainelAuxiliarRetas")
        self.setFixedSize(200, 64)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        titulo = QLabel("Retas e curvas")
        titulo.setStyleSheet("font-size: 10px; color: #7c7c7c;")
        layout.addWidget(titulo)

        botao = QPushButton("Desfaz ponto")
        botao.setFixedHeight(24)
        botao.clicked.connect(self.desfazer_ponto.emit)
        layout.addWidget(botao)
        self._offset_arraste: QPointF | None = None

        self.setStyleSheet(
            """
            QFrame#PainelAuxiliarRetas {
                background: #ebebeb;
                border: 1px solid #9a9a9a;
                border-radius: 8px;
                color: #1f1f1f;
            }
            QPushButton {
                background: #f6f6f6;
                border: 1px solid #9b9b9b;
                font-size: 10px;
                font-weight: 600;
                color: #111111;
            }
            QPushButton:hover { background: #ffffff; }
            """
        )

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._offset_arraste = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._offset_arraste is not None and event.buttons() & Qt.LeftButton:
            destino = self.mapToParent(event.position().toPoint() - self._offset_arraste.toPoint())
            self.move(destino)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._offset_arraste = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class VisualizacaoCanvas(QWidget):
    zoom_changed = Signal(float)

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.cena = cena
        self.zoom = 1.0
        self.origem_cena = QPointF(0.0, 0.0)
        self.ferramenta_ativa: str | None = None
        self._pontos_reta: list[QPointF] = []
        self._preview_reta: QPointF | None = None
        self._historico_elementos: list[list[dict]] = [[]]
        self._indice_historico = 0
        self._buffer_copia: dict | None = None
        self._offset_colagem = 0
        self._selecionados: set[int] = set()
        self._inicio_selecao: QPointF | None = None
        self._fim_selecao: QPointF | None = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto: QPointF | None = None
        self._moveu_selecao = False

        self.setMinimumSize(100, 100)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)

        self.painel_retas = PainelAuxiliarRetas(self)
        self.painel_retas.desfazer_ponto.connect(self._desfazer_ponto)
        self.painel_retas.hide()

    def set_zoom(self, zoom: float):
        self.zoom = max(0.2, min(zoom, 8.0))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def set_ferramenta_ativa(self, tool_id: str):
        self.ferramenta_ativa = tool_id
        if tool_id in {"reta", "curva"}:
            self.painel_retas.show()
            self._reposicionar_painel_retas()
        else:
            self.painel_retas.hide()
            self._pontos_reta.clear()
            self._preview_reta = None
        self.update()

    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        cursor_tela = event.position()
        cursor_cena_antes = self._tela_para_cena(cursor_tela)
        delta = event.angleDelta().y()
        fator = 1.1 if delta > 0 else 0.9
        self.set_zoom(self.zoom * fator)
        self.origem_cena = QPointF(
            cursor_cena_antes.x() - (cursor_tela.x() / self.zoom),
            cursor_cena_antes.y() - (cursor_tela.y() / self.zoom),
        )
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if self.ferramenta_ativa not in {"reta", "curva"}:
            if event.button() == Qt.LeftButton:
                pos = self._tela_para_cena(event.position())
                idx = self._indice_elemento_em_ponto(pos)
                if idx is not None and idx in self._selecionados:
                    self._arrastando_selecao = True
                    self._ultimo_ponto_arrasto = pos
                    self._moveu_selecao = False
                    event.accept()
                    return
                self._arrastando_selecao = False
                self._inicio_selecao = pos
                self._fim_selecao = pos
                self._ultimo_ponto_arrasto = None
                self.update()
                event.accept()
                return
            return super().mousePressEvent(event)

        pos = self._tela_para_cena(event.position())
        if event.button() == Qt.LeftButton:
            if not self._pontos_reta:
                self._pontos_reta.append(pos)
            else:
                self._pontos_reta.append(pos)
            self._preview_reta = pos
            self.update()
            event.accept()
            return

        if event.button() == Qt.RightButton:
            self._finalizar_reta_atual()
            self.update()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):  # noqa: N802
        if self.ferramenta_ativa in {"reta", "curva"} and self._pontos_reta:
            self._preview_reta = self._tela_para_cena(event.position())
            self.update()
            event.accept()
            return
        if self.ferramenta_ativa not in {"reta", "curva"}:
            pos = self._tela_para_cena(event.position())
            if self._arrastando_selecao and self._ultimo_ponto_arrasto and self._selecionados:
                delta_x = pos.x() - self._ultimo_ponto_arrasto.x()
                delta_y = pos.y() - self._ultimo_ponto_arrasto.y()
                self._mover_selecionados(delta_x, delta_y)
                self._ultimo_ponto_arrasto = pos
                self._moveu_selecao = True
                self.update()
                event.accept()
                return
            if self._inicio_selecao:
                self._fim_selecao = pos
                self.update()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802
        if self.ferramenta_ativa in {"reta", "curva"}:
            return super().mouseReleaseEvent(event)
        if event.button() != Qt.LeftButton:
            return super().mouseReleaseEvent(event)

        if self._arrastando_selecao:
            self._arrastando_selecao = False
            self._ultimo_ponto_arrasto = None
            if self._moveu_selecao:
                self._registrar_historico()
            self._moveu_selecao = False
            event.accept()
            return

        if self._inicio_selecao and self._fim_selecao:
            self._atualizar_selecao_por_caixa(self._inicio_selecao, self._fim_selecao)
        self._inicio_selecao = None
        self._fim_selecao = None
        self.update()
        event.accept()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._reposicionar_painel_retas()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        painter.setRenderHint(QPainter.Antialiasing)

        for idx, elemento in enumerate(self.cena.elementos):
            if elemento.get("tipo") != "polyline":
                continue
            pontos = [QPointF(x, y) for x, y in elemento.get("pontos", [])]
            if len(pontos) < 2:
                continue
            cor = "#ffd54a" if idx in self._selecionados else elemento.get("cor", "#d0d0d0")
            self._desenhar_polilinha(painter, pontos, cor=cor)

        if self._pontos_reta:
            self._desenhar_polilinha(painter, self._pontos_reta, cor="#ff5a00")
            if self._preview_reta and self._preview_reta != self._pontos_reta[-1]:
                self._desenhar_segmento(painter, self._pontos_reta[-1], self._preview_reta, tracejado=True)
            self._desenhar_marcador(painter, self._pontos_reta[0])
        if self._inicio_selecao and self._fim_selecao:
            self._desenhar_caixa_selecao(painter, self._inicio_selecao, self._fim_selecao)

    def _desenhar_polilinha(self, painter: QPainter, pontos: list[QPointF], cor: str = "#ff5a00"):
        for inicio, fim in zip(pontos, pontos[1:]):
            self._desenhar_segmento(painter, inicio, fim, cor=cor)
        self._desenhar_marcador(painter, pontos[-1])

    def _desenhar_segmento(self, painter: QPainter, inicio: QPointF, fim: QPointF, tracejado: bool = False, cor: str = "#ff5a00"):
        pen = QPen(QColor(cor), 1)
        if tracejado:
            pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        painter.drawLine(self._cena_para_tela(inicio), self._cena_para_tela(fim))

    def _desenhar_marcador(self, painter: QPainter, ponto: QPointF):
        painter.setPen(QPen(QColor("#ff5a00"), 1))
        p = self._cena_para_tela(ponto)
        painter.drawLine(p.x() - 5, p.y(), p.x() + 5, p.y())
        painter.drawLine(p.x(), p.y() - 5, p.x(), p.y() + 5)

    def _desfazer_ponto(self):
        if not self._pontos_reta:
            return
        self._pontos_reta.pop()
        if self._pontos_reta:
            self._preview_reta = self._pontos_reta[-1]
        else:
            self._preview_reta = None
        self.update()

    def _finalizar_reta_atual(self):
        if len(self._pontos_reta) == 1:
            self._pontos_reta.clear()
            self._preview_reta = None
            return

        if len(self._pontos_reta) >= 2:
            self.cena.elementos.append(
                {
                    "tipo": "polyline",
                    "pontos": [(p.x(), p.y()) for p in self._pontos_reta],
                    "cor": "#ff5a00",
                }
            )
            self._registrar_historico()
            ultimo_ponto = self._pontos_reta[-1]
            self._pontos_reta = [ultimo_ponto]
            self._preview_reta = ultimo_ponto

    def _reposicionar_painel_retas(self):
        if not self.painel_retas.isVisible():
            return
        x = (self.width() - self.painel_retas.width()) // 2
        y = 24
        self.painel_retas.move(max(8, x), y)

    def _tela_para_cena(self, ponto: QPointF) -> QPointF:
        return QPointF((ponto.x() / self.zoom) + self.origem_cena.x(), (ponto.y() / self.zoom) + self.origem_cena.y())

    def _cena_para_tela(self, ponto: QPointF) -> QPointF:
        return QPointF((ponto.x() - self.origem_cena.x()) * self.zoom, (ponto.y() - self.origem_cena.y()) * self.zoom)

    def desfazer_acao(self):
        if self._pontos_reta:
            self._desfazer_ponto()
            return

        if self._indice_historico == 0:
            return
        self._indice_historico -= 1
        self.cena.elementos = deepcopy(self._historico_elementos[self._indice_historico])
        self.update()

    def copiar(self):
        if self._selecionados:
            self._buffer_copia = {
                "tipo": "multiplos",
                "elementos": [deepcopy(self.cena.elementos[idx]) for idx in sorted(self._selecionados)],
            }
            return
        if self._pontos_reta and len(self._pontos_reta) >= 2:
            self._buffer_copia = {
                "tipo": "polyline",
                "pontos": [(p.x(), p.y()) for p in self._pontos_reta],
                "cor": "#ff5a00",
            }
            return

        if self.cena.elementos:
            self._buffer_copia = deepcopy(self.cena.elementos[-1])

    def colar(self):
        if not self._buffer_copia:
            return
        self._offset_colagem += 10
        self._selecionados.clear()
        if self._buffer_copia.get("tipo") == "multiplos":
            for item in self._buffer_copia.get("elementos", []):
                novo = deepcopy(item)
                if novo.get("tipo") == "polyline":
                    novo["pontos"] = [(x + self._offset_colagem, y + self._offset_colagem) for x, y in novo.get("pontos", [])]
                self.cena.elementos.append(novo)
                self._selecionados.add(len(self.cena.elementos) - 1)
        else:
            novo = deepcopy(self._buffer_copia)
            if novo.get("tipo") == "polyline":
                novo["pontos"] = [(x + self._offset_colagem, y + self._offset_colagem) for x, y in novo.get("pontos", [])]
            self.cena.elementos.append(novo)
            self._selecionados.add(len(self.cena.elementos) - 1)
        self._registrar_historico()
        self.update()

    def apagar_selecionados(self):
        if not self._selecionados:
            return
        self.cena.elementos = [el for idx, el in enumerate(self.cena.elementos) if idx not in self._selecionados]
        self._selecionados.clear()
        self._registrar_historico()
        self.update()

    def _registrar_historico(self):
        snapshot = deepcopy(self.cena.elementos)
        if self._indice_historico < len(self._historico_elementos) - 1:
            self._historico_elementos = self._historico_elementos[: self._indice_historico + 1]
        self._historico_elementos.append(snapshot)
        if len(self._historico_elementos) > 200:
            self._historico_elementos.pop(0)
        self._indice_historico = len(self._historico_elementos) - 1

    def _retangulo_selecao(self, inicio: QPointF, fim: QPointF) -> tuple[float, float, float, float]:
        return min(inicio.x(), fim.x()), min(inicio.y(), fim.y()), max(inicio.x(), fim.x()), max(inicio.y(), fim.y())

    def _bbox_elemento(self, elemento: dict) -> tuple[float, float, float, float] | None:
        if elemento.get("tipo") != "polyline":
            return None
        pontos = elemento.get("pontos", [])
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    def _atualizar_selecao_por_caixa(self, inicio: QPointF, fim: QPointF):
        x1, y1, x2, y2 = self._retangulo_selecao(inicio, fim)
        if abs(x2 - x1) < 1 and abs(y2 - y1) < 1:
            idx = self._indice_elemento_em_ponto(inicio)
            self._selecionados = {idx} if idx is not None else set()
            return
        selecionados: set[int] = set()
        for idx, elemento in enumerate(self.cena.elementos):
            bbox = self._bbox_elemento(elemento)
            if not bbox:
                continue
            bx1, by1, bx2, by2 = bbox
            if not (bx2 < x1 or bx1 > x2 or by2 < y1 or by1 > y2):
                selecionados.add(idx)
        self._selecionados = selecionados

    def _indice_elemento_em_ponto(self, ponto: QPointF) -> int | None:
        tolerancia = 4 / max(self.zoom, 0.001)
        for idx in range(len(self.cena.elementos) - 1, -1, -1):
            bbox = self._bbox_elemento(self.cena.elementos[idx])
            if not bbox:
                continue
            x1, y1, x2, y2 = bbox
            if x1 - tolerancia <= ponto.x() <= x2 + tolerancia and y1 - tolerancia <= ponto.y() <= y2 + tolerancia:
                return idx
        return None

    def _mover_selecionados(self, dx: float, dy: float):
        for idx in self._selecionados:
            el = self.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                el["pontos"] = [(x + dx, y + dy) for x, y in el.get("pontos", [])]

    def _desenhar_caixa_selecao(self, painter: QPainter, inicio: QPointF, fim: QPointF):
        p1 = self._cena_para_tela(inicio)
        p2 = self._cena_para_tela(fim)
        x1, y1, x2, y2 = min(p1.x(), p2.x()), min(p1.y(), p2.y()), max(p1.x(), p2.x()), max(p1.y(), p2.y())
        painter.fillRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1), QColor(120, 0, 0, 80))
        painter.setPen(QPen(QColor("#ff3333"), 1))
        painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
