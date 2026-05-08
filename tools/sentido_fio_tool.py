from __future__ import annotations

from math import atan2, cos, degrees, hypot, isfinite, radians, sin

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class SentidoFioDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:sentido_fio"
        self.setWindowTitle("Sentido do fio")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(240)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QComboBox, QDoubleSpinBox {
                background:#ffffff;
                color:#111111;
                border:1px solid #8796a4;
                min-height:20px;
            }
            """
        )

        raiz = QFormLayout(self)
        raiz.setContentsMargins(6, 8, 6, 6)
        raiz.setHorizontalSpacing(6)
        raiz.setVerticalSpacing(4)

        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(
            [
                "Pontos do mouse",
                "Pontos do molde",
                "Por selecao",
                "Alinhar molde",
                "Horizontal",
                "Vertical",
                "Posicionar fio",
            ]
        )
        raiz.addRow("Modo", self.cmb_modo)

        linha_angulo = QHBoxLayout()
        linha_angulo.setContentsMargins(0, 0, 0, 0)
        self.chk_usar_angulo = QCheckBox("Usar angulo")
        self.chk_usar_angulo.setChecked(True)
        self.sp_angulo = QDoubleSpinBox()
        self.sp_angulo.setRange(-3600.0, 3600.0)
        self.sp_angulo.setDecimals(2)
        self.sp_angulo.setSingleStep(5.0)
        self.sp_angulo.setSuffix(" deg")
        self.sp_angulo.setValue(0.0)
        linha_angulo.addWidget(self.chk_usar_angulo, 0)
        linha_angulo.addWidget(self.sp_angulo, 1)
        raiz.addRow(linha_angulo)

        self.chk_girar_molde = QCheckBox("Girar molde")
        self.chk_girar_molde.setChecked(False)
        raiz.addRow(self.chk_girar_molde)


class Ferramenta(FerramentaBase):
    id_ferramenta = "sentido_fio"
    nome = "Sentido Fio"
    usa_painel_auxiliar = False
    descricao_painel = "Define o sentido do fio do molde com dois pontos e angulo opcional."

    _dialog_por_canvas: dict[int, SentidoFioDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._inicio: QPointF | None = None
        self._fim_preview: QPointF | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._molde_idx = self._molde_selecionado(canvas)
        self._inicio = None
        self._fim_preview = None
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Sentido do fio: clique no molde para selecionar ou clique o inicio do fio.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._inicio = None
        self._fim_preview = None
        if canvas is not None:
            canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        alvo = self._molde_em_ponto(canvas, pos)
        if alvo is not None and (self._molde_idx is None or alvo != self._molde_idx):
            self._selecionar_molde(canvas, alvo)
            self._inicio = None
            self._fim_preview = None
            self._status(canvas, "Molde selecionado. Clique para marcar o inicio do fio.")
            event.accept()
            return True

        if self._molde_idx is None:
            self._status(canvas, "Sentido do fio: selecione um molde primeiro.")
            event.accept()
            return True

        if self._inicio is None:
            self._inicio = QPointF(pos)
            self._fim_preview = QPointF(pos)
            self._status(canvas, "Inicio marcado. Mova o mouse no sentido desejado e clique para aplicar.")
            canvas.update()
            event.accept()
            return True

        fim = self._ponto_final_com_config(canvas, self._inicio, pos)
        if self._dist(self._inicio, fim) <= 1e-6:
            self._status(canvas, "Sentido do fio: informe um segundo ponto diferente do inicio.")
            event.accept()
            return True
        self._aplicar(canvas, self._molde_idx, self._inicio, fim)
        self._inicio = None
        self._fim_preview = None
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._inicio is None:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._fim_preview = self._ponto_final_com_config(canvas, self._inicio, pos)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._inicio is None or self._fim_preview is None:
            return

        p0 = canvas._cena_para_tela(self._inicio)
        p1 = canvas._cena_para_tela(self._fim_preview)
        ang = self._angulo(self._inicio, self._fim_preview)

        painter.save()
        pen = QPen(QColor("#ff00d4"), 1.0, Qt.DashLine)
        pen.setDashPattern([3.0, 2.0])
        painter.setPen(pen)
        painter.drawLine(p0, p1)
        painter.drawLine(QPointF(p0.x() - 5, p0.y()), QPointF(p0.x() + 5, p0.y()))
        painter.drawLine(QPointF(p0.x(), p0.y() - 5), QPointF(p0.x(), p0.y() + 5))
        painter.drawLine(QPointF(p1.x() - 7, p1.y() - 7), QPointF(p1.x() + 7, p1.y() + 7))
        painter.drawLine(QPointF(p1.x() + 7, p1.y() - 7), QPointF(p1.x() - 7, p1.y() + 7))

        raio = max(22.0, min(78.0, hypot(p1.x() - p0.x(), p1.y() - p0.y()) * 0.45))
        painter.drawEllipse(QRectF(p0.x() - raio, p0.y() - raio, raio * 2.0, raio * 2.0))
        painter.drawText(int(p1.x() + 6), int(p1.y() + 12), f"{self._normalizar_angulo(ang):g} deg")
        painter.restore()

    def _obter_dialog(self, canvas) -> SentidoFioDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = SentidoFioDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
            dialog.cmb_modo.currentTextChanged.connect(lambda _texto, c=canvas: c.update())
            dialog.chk_usar_angulo.toggled.connect(lambda _marcado, c=canvas: c.update())
            dialog.sp_angulo.valueChanged.connect(lambda _valor, c=canvas: c.update())
            dialog.chk_girar_molde.toggled.connect(lambda _marcado, c=canvas: c.update())
        return dialog

    def _restaurar_dialog(self, canvas, dialog: SentidoFioDialog) -> None:
        fallback = None
        if hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 80))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _ponto_final_com_config(self, canvas, inicio: QPointF, pos_mouse: QPointF) -> QPointF:
        dialog = self._obter_dialog(canvas)
        modo = dialog.cmb_modo.currentText()
        if modo == "Horizontal":
            pos_mouse = QPointF(pos_mouse.x(), inicio.y())
        elif modo == "Vertical":
            pos_mouse = QPointF(inicio.x(), pos_mouse.y())

        dx = pos_mouse.x() - inicio.x()
        dy = pos_mouse.y() - inicio.y()
        comp = hypot(dx, dy)
        if comp <= 1e-9:
            return QPointF(pos_mouse)
        ang = atan2(dy, dx)
        if dialog.chk_usar_angulo.isChecked():
            ang += radians(float(dialog.sp_angulo.value()))
        return QPointF(inicio.x() + (cos(ang) * comp), inicio.y() + (sin(ang) * comp))

    def _aplicar(self, canvas, idx: int, inicio: QPointF, fim: QPointF) -> None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            self._status(canvas, "Sentido do fio: o elemento selecionado nao e molde.")
            return

        dialog = self._obter_dialog(canvas)
        angulo_novo = self._angulo(inicio, fim)
        if dialog.chk_girar_molde.isChecked():
            angulo_antigo = self._angulo_fio_atual(el)
            self._girar_molde(el, inicio, angulo_novo - angulo_antigo)

        el["fio_origem"] = (float(inicio.x()), float(inicio.y()))
        el["fio_fim"] = (float(fim.x()), float(fim.y()))
        el["fio_angulo"] = self._normalizar_angulo(angulo_novo)
        el["mostrar_fio"] = True
        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self._status(canvas, f"Sentido do fio aplicado em {self._normalizar_angulo(angulo_novo):g} deg.")

    def _molde_selecionado(self, canvas) -> int | None:
        for idx in sorted(getattr(canvas, "_selecionados", set()) or []):
            if 0 <= int(idx) < len(canvas.cena.elementos) and canvas.cena.elementos[int(idx)].get("molde"):
                return int(idx)
        return None

    def _molde_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
            el = canvas.cena.elementos[idx]
            if not el.get("molde") or el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 3:
                continue
            path = QPainterPath(pontos[0])
            for pt in pontos[1:]:
                path.lineTo(pt)
            path.closeSubpath()
            if path.contains(pos):
                return idx
        return None

    def _selecionar_molde(self, canvas, idx: int) -> None:
        self._molde_idx = idx
        canvas._selecionados = {idx}
        canvas.update()

    def _fechar(self, canvas) -> None:
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Sentido Fio finalizada. Voltando para Selecionar.")

    def _girar_molde(self, el: dict, pivo: QPointF, angulo: float) -> None:
        a = radians(angulo)
        ca, sa = cos(a), sin(a)

        def rot(p):
            x, y = float(p[0]), float(p[1])
            dx, dy = x - pivo.x(), y - pivo.y()
            return (pivo.x() + (dx * ca) - (dy * sa), pivo.y() + (dx * sa) + (dy * ca))

        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro", "distancias_no_perimetro", "marcacoes_perimetro"):
            if isinstance(el.get(chave), list):
                el[chave] = [rot(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]
        for chave in ("ponto_texto", "seta_origem", "seta_fim", "fio_origem", "fio_fim"):
            if self._eh_ponto(el.get(chave)):
                el[chave] = rot(el[chave])

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _angulo(inicio: QPointF, fim: QPointF) -> float:
        return degrees(atan2(fim.y() - inicio.y(), fim.x() - inicio.x()))

    @staticmethod
    def _normalizar_angulo(angulo: float) -> float:
        valor = float(angulo) % 360.0
        return 0.0 if abs(valor - 360.0) <= 1e-9 else valor

    def _angulo_fio_atual(self, el: dict) -> float:
        origem = el.get("fio_origem")
        fim = el.get("fio_fim")
        if self._eh_ponto(origem) and self._eh_ponto(fim):
            return self._angulo(QPointF(float(origem[0]), float(origem[1])), QPointF(float(fim[0]), float(fim[1])))
        try:
            return float(el.get("fio_angulo") or 0.0)
        except Exception:
            return 0.0

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
