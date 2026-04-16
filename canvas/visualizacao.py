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

        self.setStyleSheet(
            """
            QFrame#PainelAuxiliarRetas {
                background: #e8e8e8;
                border: 1px solid #a8a8a8;
                border-radius: 8px;
            }
            QPushButton {
                background: #f8f8f8;
                border: 1px solid #b7b7b7;
                font-size: 10px;
            }
            QPushButton:hover { background: #ffffff; }
            """
        )


class VisualizacaoCanvas(QWidget):
    zoom_changed = Signal(float)

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.cena = cena
        self.zoom = 1.0
        self.ferramenta_ativa: str | None = None
        self._pontos_reta: list[QPointF] = []
        self._preview_reta: QPointF | None = None
        self._historico_elementos: list[list[dict]] = [[]]
        self._indice_historico = 0
        self._buffer_copia: dict | None = None
        self._offset_colagem = 0

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
        delta = event.angleDelta().y()
        fator = 1.1 if delta > 0 else 0.9
        self.set_zoom(self.zoom * fator)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if self.ferramenta_ativa not in {"reta", "curva"}:
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
        super().mouseMoveEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._reposicionar_painel_retas()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()
        painter.scale(self.zoom, self.zoom)

        for elemento in self.cena.elementos:
            if elemento.get("tipo") != "polyline":
                continue
            pontos = [QPointF(x, y) for x, y in elemento.get("pontos", [])]
            if len(pontos) < 2:
                continue
            self._desenhar_polilinha(painter, pontos)

        if self._pontos_reta:
            self._desenhar_polilinha(painter, self._pontos_reta)
            if self._preview_reta and self._preview_reta != self._pontos_reta[-1]:
                self._desenhar_segmento(painter, self._pontos_reta[-1], self._preview_reta, tracejado=True)
            self._desenhar_marcador(painter, self._pontos_reta[0])
        painter.restore()

    def _desenhar_polilinha(self, painter: QPainter, pontos: list[QPointF]):
        for inicio, fim in zip(pontos, pontos[1:]):
            self._desenhar_segmento(painter, inicio, fim)
        self._desenhar_marcador(painter, pontos[-1])

    def _desenhar_segmento(self, painter: QPainter, inicio: QPointF, fim: QPointF, tracejado: bool = False):
        pen = QPen(QColor("#ff5a00"), 1)
        if tracejado:
            pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        painter.drawLine(inicio, fim)

    def _desenhar_marcador(self, painter: QPainter, ponto: QPointF):
        painter.setPen(QPen(QColor("#ff5a00"), 1))
        painter.drawLine(ponto.x() - 5, ponto.y(), ponto.x() + 5, ponto.y())
        painter.drawLine(ponto.x(), ponto.y() - 5, ponto.x(), ponto.y() + 5)

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
        return QPointF(ponto.x() / self.zoom, ponto.y() / self.zoom)

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
        novo = deepcopy(self._buffer_copia)
        self._offset_colagem += 10
        if novo.get("tipo") == "polyline":
            novo["pontos"] = [(x + self._offset_colagem, y + self._offset_colagem) for x, y in novo.get("pontos", [])]
        self.cena.elementos.append(novo)
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
