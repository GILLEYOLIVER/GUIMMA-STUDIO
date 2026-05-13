from __future__ import annotations

from math import ceil, floor, log10

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QToolButton, QWidget

from canvas.visualizacao import VisualizacaoCanvas
from canvas.cena import CenaDocumento


class ReguaWidget(QWidget):
    def __init__(self, horizontal: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.horizontal = horizontal
        self.zoom = 1.0
        self.origem_x = 0.0
        self.origem_y = 0.0
        self.unidade_sigla = "cm"
        self._fator_unidade = 1.0  # 1 unidade de cena = 1 cm
        self.passo_preferido_unidade = 0.5
        if horizontal:
            self.setFixedHeight(20)
        else:
            self.setFixedWidth(28)

    def atualizar_viewport(self, zoom: float, origem_x: float, origem_y: float):
        self.zoom = max(0.1, zoom)
        self.origem_x = origem_x
        self.origem_y = origem_y
        self.update()

    def atualizar_zoom(self, zoom: float):
        self.atualizar_viewport(zoom, self.origem_x, self.origem_y)

    def definir_unidade(self, sigla: str, fator_unidade: float, passo_preferido_unidade: float):
        self.unidade_sigla = str(sigla or "cm")
        self._fator_unidade = max(1e-9, float(fator_unidade))
        self.passo_preferido_unidade = max(1e-6, float(passo_preferido_unidade))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f2f2f2"))
        painter.setPen(QPen(QColor("#222222"), 1))

        pixel_step = max(25, int(40 * self.zoom))
        passo_unidade = self._passo_principal()
        if self.horizontal:
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            for x in range(0, self.width(), 5):
                if x % pixel_step == 0:
                    painter.drawLine(x, self.height() - 12, x, self.height())
                elif x % max(1, pixel_step // 2) == 0:
                    painter.drawLine(x, self.height() - 8, x, self.height())
                else:
                    painter.drawLine(x, self.height() - 4, x, self.height())
            inicio = self.origem_x
            fim = self.origem_x + (self.width() / max(self.zoom, 0.001))
            valor = floor(inicio / passo_unidade) * passo_unidade
            while valor <= fim + passo_unidade:
                px = int((valor - self.origem_x) * self.zoom)
                if 0 <= px <= self.width():
                    painter.drawLine(px, self.height() - 12, px, self.height())
                    painter.drawText(px + 2, 9, self._formatar_valor(valor, passo_unidade))
                valor += passo_unidade
        else:
            painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
            for y in range(0, self.height(), 5):
                if y % pixel_step == 0:
                    painter.drawLine(self.width() - 12, y, self.width(), y)
                elif y % max(1, pixel_step // 2) == 0:
                    painter.drawLine(self.width() - 8, y, self.width(), y)
                else:
                    painter.drawLine(self.width() - 4, y, self.width(), y)
            inicio = self.origem_y
            fim = self.origem_y + (self.height() / max(self.zoom, 0.001))
            valor = floor(inicio / passo_unidade) * passo_unidade
            while valor <= fim + passo_unidade:
                py = int((valor - self.origem_y) * self.zoom)
                if 0 <= py <= self.height():
                    painter.drawLine(self.width() - 12, py, self.width(), py)
                    painter.save()
                    painter.translate(9, py + 2)
                    painter.rotate(-90)
                    painter.drawText(0, 0, self._formatar_valor(valor, passo_unidade))
                    painter.restore()
                valor += passo_unidade

    def _passo_principal(self) -> float:
        alvo_px = 85.0
        bruto = max(alvo_px / max(self.zoom, 0.001), 1e-6)
        passo_base = self.passo_preferido_unidade * self._fator_unidade
        mult = max(1, ceil(bruto / max(passo_base, 1e-6)))
        return passo_base * mult

    def _formatar_valor(self, valor: float, passo: float) -> str:
        valor_unidade = valor / self._fator_unidade
        passo_unidade = passo / self._fator_unidade
        if passo_unidade >= 1:
            return f"{valor_unidade:.0f}"
        dec = max(0, min(6, int(abs(floor(log10(passo_unidade))))))
        return f"{valor_unidade:.{dec}f}"


class AreaDocumentoWidget(QWidget):
    zoom_changed = Signal(float)
    unidade_menu_solicitado = Signal(int, int)

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.regua_h = ReguaWidget(horizontal=True)
        self.regua_v = ReguaWidget(horizontal=False)
        self.canto = QToolButton()
        self.canto.setText("cm")
        self.canto.setCursor(Qt.PointingHandCursor)
        self.canto.setStyleSheet(
            "QToolButton { background:#f8f8f8; border-right:1px solid #cdd6df; border-bottom:1px solid #cdd6df; font-size:10px; }"
            "QToolButton:hover { background:#eaf5ff; }"
        )
        self.canto.clicked.connect(self._emitir_menu_unidade)

        self.canvas = VisualizacaoCanvas(cena)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)

        layout.addWidget(self.canto, 0, 0)
        layout.addWidget(self.regua_h, 0, 1)
        layout.addWidget(self.regua_v, 1, 0)
        layout.addWidget(self.canvas, 1, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(1, 1)
        self._reguas_visiveis = True
        self.aplicar_config_unidade("cm", 0.5)

    def _on_zoom_changed(self, zoom: float):
        self.regua_h.atualizar_viewport(zoom, self.canvas.origem_cena.x(), self.canvas.origem_cena.y())
        self.regua_v.atualizar_viewport(zoom, self.canvas.origem_cena.x(), self.canvas.origem_cena.y())
        self.zoom_changed.emit(zoom)
    
    def _emitir_menu_unidade(self):
        pos = self.canto.mapToGlobal(self.canto.rect().bottomLeft())
        self.unidade_menu_solicitado.emit(pos.x(), pos.y())

    def aplicar_config_unidade(self, unidade_sigla: str, passo_unidade: float):
        mapa_fator = {
            "mm": 0.1,
            "cm": 1.0,
            "m": 100.0,
            "pol": 2.54,
            "ft": 30.48,
            "yd": 91.44,
        }
        fator = mapa_fator.get(unidade_sigla, 1.0)
        self.regua_h.definir_unidade(unidade_sigla, fator, passo_unidade)
        self.regua_v.definir_unidade(unidade_sigla, fator, passo_unidade)
        self.canto.setText(unidade_sigla)
        if hasattr(self.canvas, "set_unidade_medida"):
            self.canvas.set_unidade_medida(unidade_sigla, fator)
        self._on_zoom_changed(self.canvas.zoom)

    def set_reguas_visiveis(self, visivel: bool):
        self._reguas_visiveis = bool(visivel)
        self.regua_h.setVisible(self._reguas_visiveis)
        self.regua_v.setVisible(self._reguas_visiveis)
        self.canto.setVisible(self._reguas_visiveis)
