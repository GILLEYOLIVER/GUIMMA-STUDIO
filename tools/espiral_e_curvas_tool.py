from __future__ import annotations

from math import atan2, cos, pi, sin, sqrt

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from tools.tool_base import FerramentaBase


class PreviewCurvaWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pontos: list[QPointF] = []
        self.setMinimumHeight(86)
        self.setMaximumHeight(110)

    def set_pontos(self, pontos: list[QPointF]):
        self._pontos = list(pontos)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#efefef"))
        if len(self._pontos) < 2:
            return
        xs = [p.x() for p in self._pontos]
        ys = [p.y() for p in self._pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w = max(1e-6, max_x - min_x)
        h = max(1e-6, max_y - min_y)
        margem = 6
        area_w = max(1.0, self.width() - (margem * 2))
        area_h = max(1.0, self.height() - (margem * 2))
        escala = min(area_w / w, area_h / h)

        def mapear(pt: QPointF) -> QPoint:
            x = margem + ((pt.x() - min_x) * escala)
            y = margem + ((pt.y() - min_y) * escala)
            return QPoint(int(x), int(y))

        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#101010"), 1.0))
        for a, b in zip(self._pontos, self._pontos[1:]):
            painter.drawLine(mapear(a), mapear(b))
        ini = mapear(self._pontos[0])
        fim = mapear(self._pontos[-1])
        painter.fillRect(ini.x() - 2, ini.y() - 2, 5, 5, QColor("#ff0000"))
        painter.fillRect(fim.x() - 2, fim.y() - 2, 5, 5, QColor("#ff00ff"))


class InserirCurvaDialog(QDialog):
    configuracao_alterada = Signal()
    OPCOES = [
        "Curva Francesa 1",
        "Curva Francesa 2",
        "Curva Francesa 3",
        "Curva Francesa 4",
        "Manga - Cava frente",
        "Cava costas",
        "Gancho calça",
        "Lado saia",
        "Decote",
        "Spiral",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inserir curva")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(212)
        self.setStyleSheet(
            """
            QDialog { background: #efefef; color: #111111; }
            QLabel { color: #111111; }
            QComboBox {
                background: #ffffff; color: #111111;
                border: 1px solid #b5bcc3; min-height: 22px;
            }
            QSlider::groove:horizontal { height: 4px; background: #d5d5d5; }
            QSlider::handle:horizontal { width: 10px; background: #0f73c6; margin: -6px 0; }
            QPushButton {
                background: #f7f7f7; color: #111111;
                border: 1px solid #b7bec5; min-height: 22px;
            }
            """
        )
        self._espelhado = False
        self._montar_ui()
        self._atualizar_preview()

    def _montar_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        lay.addWidget(QLabel("Curva pré-definida"))
        self.cmb_curva = QComboBox()
        self.cmb_curva.addItems(self.OPCOES)
        lay.addWidget(self.cmb_curva)
        self.preview = PreviewCurvaWidget()
        lay.addWidget(self.preview)

        self.lbl_e1 = QLabel("Extremo 1 - 0.0 %")
        lay.addWidget(self.lbl_e1)
        self.sl_e1 = QSlider(Qt.Horizontal)
        self.sl_e1.setRange(0, 95)
        self.sl_e1.setValue(0)
        lay.addWidget(self.sl_e1)

        self.lbl_e2 = QLabel("Extremo 2 - 100.0 %")
        lay.addWidget(self.lbl_e2)
        self.sl_e2 = QSlider(Qt.Horizontal)
        self.sl_e2.setRange(5, 100)
        self.sl_e2.setValue(100)
        lay.addWidget(self.sl_e2)

        hl = QHBoxLayout()
        self.btn_espelhar = QPushButton("Espelhar")
        hl.addWidget(self.btn_espelhar)
        lay.addLayout(hl)

        self.cmb_curva.currentTextChanged.connect(self._atualizar_preview)
        self.sl_e1.valueChanged.connect(self._atualizar_preview)
        self.sl_e2.valueChanged.connect(self._atualizar_preview)
        self.btn_espelhar.clicked.connect(self._alternar_espelho)

    def _alternar_espelho(self):
        self._espelhado = not self._espelhado
        self._atualizar_preview()

    def _atualizar_preview(self):
        e1 = float(self.sl_e1.value())
        e2 = float(self.sl_e2.value())
        if e1 >= e2:
            if self.sender() is self.sl_e1:
                self.sl_e1.setValue(max(0, self.sl_e2.value() - 1))
            else:
                self.sl_e2.setValue(min(100, self.sl_e1.value() + 1))
            e1 = float(self.sl_e1.value())
            e2 = float(self.sl_e2.value())
        self.lbl_e1.setText(f"Extremo 1 - {e1:.1f} %")
        self.lbl_e2.setText(f"Extremo 2 - {e2:.1f} %")
        self.preview.set_pontos(self.pontos_processados())
        self.configuracao_alterada.emit()

    def configuracao(self) -> tuple[str, float, float, bool]:
        return self.cmb_curva.currentText(), float(self.sl_e1.value()) / 100.0, float(self.sl_e2.value()) / 100.0, self._espelhado

    def pontos_processados(self) -> list[QPointF]:
        nome, ext1, ext2, esp = self.configuracao()
        base = _gerar_curva_base(nome)
        if not base:
            return []
        if esp:
            base = [QPointF(-p.x(), p.y()) for p in base]
        i1 = int((len(base) - 1) * ext1)
        i2 = int((len(base) - 1) * ext2)
        i1 = max(0, min(i1, len(base) - 2))
        i2 = max(i1 + 1, min(i2, len(base) - 1))
        return base[i1 : i2 + 1]


def _interp(perfil: list[tuple[float, float]], sx: float = 6.0, sy: float = 4.0, amostras: int = 24) -> list[QPointF]:
    base = [QPointF((x - 0.5) * sx, (y - 0.5) * sy) for x, y in perfil]
    if len(base) < 3:
        return base
    saida: list[QPointF] = []
    for i in range(len(base) - 1):
        p0 = base[max(0, i - 1)]
        p1 = base[i]
        p2 = base[i + 1]
        p3 = base[min(len(base) - 1, i + 2)]
        for j in range(amostras):
            t = j / amostras
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                (2.0 * p1.x())
                + (-p0.x() + p2.x()) * t
                + ((2.0 * p0.x()) - (5.0 * p1.x()) + (4.0 * p2.x()) - p3.x()) * t2
                + (-p0.x() + (3.0 * p1.x()) - (3.0 * p2.x()) + p3.x()) * t3
            )
            y = 0.5 * (
                (2.0 * p1.y())
                + (-p0.y() + p2.y()) * t
                + ((2.0 * p0.y()) - (5.0 * p1.y()) + (4.0 * p2.y()) - p3.y()) * t2
                + (-p0.y() + (3.0 * p1.y()) - (3.0 * p2.y()) + p3.y()) * t3
            )
            saida.append(QPointF(x, y))
    saida.append(base[-1])
    return saida


def _gerar_curva_base(nome: str) -> list[QPointF]:
    perfis = {
        "Curva Francesa 1": [(0.04, 0.68), (0.18, 0.62), (0.45, 0.58), (0.76, 0.60), (0.96, 0.86)],
        "Curva Francesa 2": [(0.10, 0.82), (0.22, 0.64), (0.42, 0.42), (0.62, 0.24), (0.78, 0.14)],
        "Curva Francesa 3": [(0.10, 0.82), (0.24, 0.64), (0.42, 0.44), (0.58, 0.28), (0.72, 0.18)],
        "Curva Francesa 4": [(0.06, 0.72), (0.28, 0.69), (0.50, 0.63), (0.72, 0.58), (0.94, 0.52)],
        "Manga - Cava frente": [(0.08, 0.16), (0.08, 0.38), (0.14, 0.60), (0.28, 0.76), (0.58, 0.84), (0.90, 0.84)],
        "Cava costas": [(0.08, 0.84), (0.16, 0.70), (0.30, 0.62), (0.54, 0.58), (0.88, 0.57)],
        "Gancho calça": [(0.46, 0.14), (0.56, 0.22), (0.62, 0.36), (0.66, 0.54), (0.66, 0.78)],
        "Lado saia": [(0.06, 0.58), (0.22, 0.62), (0.40, 0.64), (0.64, 0.64), (0.90, 0.62)],
        "Decote": [(0.08, 0.46), (0.20, 0.60), (0.36, 0.68), (0.54, 0.70), (0.74, 0.64), (0.90, 0.50)],
    }
    if nome == "Spiral":
        pts: list[QPointF] = []
        voltas = 2.3
        for i in range(160):
            t = i / 159
            ang = (2.0 * pi * voltas * t) - (pi / 2.0)
            r = 3.0 * t
            pts.append(QPointF(cos(ang) * r, sin(ang) * r))
        return pts
    return _interp(perfis.get(nome, perfis["Curva Francesa 1"]), amostras=28)


class Ferramenta(FerramentaBase):
    id_ferramenta = "espiral_e_curvas"
    nome = "Espiral e Curvas"
    usa_painel_auxiliar = False
    descricao_painel = "Insere curvas pré-definidas (sem modal)."
    _dialog_por_canvas: dict[int, InserirCurvaDialog] = {}
    _canvas_por_id: dict[int, object] = {}
    _ultimo_idx_por_canvas: dict[int, int] = {}
    _ultima_origem_por_canvas: dict[int, QPointF] = {}
    _desenhando_por_canvas: dict[int, bool] = {}
    _origem_por_canvas: dict[int, QPointF] = {}
    _cursor_por_canvas: dict[int, QPointF] = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._canvas_por_id[id(canvas)] = canvas
        self._desenhando_por_canvas[id(canvas)] = False
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._atualizar_status_perimetro(canvas, dialog)
        msg = "Inserir curva: selecione o modelo e clique no canvas."
        self.set_status(msg)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(msg)

    def on_deactivate(self, canvas):
        super().on_deactivate(canvas)
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog:
            dialog.hide()
        self._canvas_por_id.pop(id(canvas), None)
        self._desenhando_por_canvas.pop(id(canvas), None)
        self._origem_por_canvas.pop(id(canvas), None)
        self._cursor_por_canvas.pop(id(canvas), None)

    def on_mouse_press(self, canvas, event) -> bool:
        chave = id(canvas)
        if event.button() == Qt.RightButton:
            if self._desenhando_por_canvas.get(chave):
                self._desenhando_por_canvas[chave] = False
                self._origem_por_canvas.pop(chave, None)
                self._cursor_por_canvas.pop(chave, None)
                if getattr(canvas, "lbl_status", None) is not None:
                    canvas.lbl_status.setText("Inserção de curva cancelada.")
                canvas.update()
                event.accept()
                return True
            return False
        if event.button() != Qt.LeftButton:
            return False
        dialog = self._obter_dialog(canvas)
        pos = canvas._ponto_com_snap(event.position())
        if not self._desenhando_por_canvas.get(chave):
            self._desenhando_por_canvas[chave] = True
            self._origem_por_canvas[chave] = QPointF(pos)
            self._cursor_por_canvas[chave] = QPointF(pos)
            self._atualizar_status_perimetro(canvas, dialog)
            canvas.update()
            event.accept()
            return True
        pontos_cena_qt = self._pontos_transformados(canvas, dialog)
        if len(pontos_cena_qt) < 2:
            return True
        pontos_cena = [(p.x(), p.y()) for p in pontos_cena_qt]
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "pontos": pontos_cena,
                "cor": getattr(canvas, "_linha_cor", "#ffffff"),
                "espessura": float(getattr(canvas, "_linha_espessura", 1.0)),
                "estilo": str(getattr(canvas, "_linha_estilo", "solid")),
                "amplitude": float(getattr(canvas, "_linha_amplitude", 1.0)),
                "fase_inicio": 0.0,
            }
        )
        idx = len(canvas.cena.elementos) - 1
        self._ultimo_idx_por_canvas[chave] = idx
        self._ultima_origem_por_canvas[chave] = QPointF(pontos_cena_qt[0])
        self._desenhando_por_canvas[chave] = False
        self._origem_por_canvas.pop(chave, None)
        self._cursor_por_canvas.pop(chave, None)
        canvas._registrar_historico()
        canvas.update()
        msg = f"Curva \"{dialog.cmb_curva.currentText()}\" inserida. {self._texto_perimetro(pontos_cena_qt, canvas)}"
        self.set_status(msg)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(msg)
        event.accept()
        return True

    def _obter_dialog(self, canvas) -> InserirCurvaDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = InserirCurvaDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        if not hasattr(dialog, "_callbacks_canvas"):
            dialog._callbacks_canvas = set()  # type: ignore[attr-defined]
        if chave not in dialog._callbacks_canvas:  # type: ignore[attr-defined]
            dialog.configuracao_alterada.connect(lambda chave_canvas=chave: self._quando_config_alterada(chave_canvas))
            dialog._callbacks_canvas.add(chave)  # type: ignore[attr-defined]
        return dialog

    def _quando_config_alterada(self, chave_canvas: int):
        dialog = self._dialog_por_canvas.get(chave_canvas)
        if dialog is None:
            return
        canvas = self._canvas_por_id.get(chave_canvas)
        if canvas is None:
            return
        self._atualizar_status_perimetro(canvas, dialog)
        self._atualizar_ultimo_elemento(canvas, dialog)
        if self._desenhando_por_canvas.get(chave_canvas):
            canvas.update()

    def _atualizar_ultimo_elemento(self, canvas, dialog: InserirCurvaDialog):
        chave = id(canvas)
        idx = self._ultimo_idx_por_canvas.get(chave)
        origem = self._ultima_origem_por_canvas.get(chave)
        if idx is None or origem is None:
            return
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        pontos = dialog.pontos_processados()
        if len(pontos) < 2:
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        el["pontos"] = [(origem.x() + p.x(), origem.y() + p.y()) for p in pontos]
        canvas.update()

    def _atualizar_status_perimetro(self, canvas, dialog: InserirCurvaDialog):
        pontos = self._pontos_transformados(canvas, dialog) if self._desenhando_por_canvas.get(id(canvas)) else dialog.pontos_processados()
        msg = self._texto_perimetro(pontos, canvas)
        self.set_status(msg)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(msg)

    def _texto_perimetro(self, pontos: list[QPointF], canvas) -> str:
        if len(pontos) < 2:
            return "Perímetro: 0.00"
        total = 0.0
        for a, b in zip(pontos, pontos[1:]):
            total += ((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5
        return f"Perímetro: {canvas.formatar_valor_unidade(total)} ({getattr(canvas, '_unidade_sigla', 'cm')})"

    def on_mouse_move(self, canvas, event) -> bool:
        chave = id(canvas)
        if not self._desenhando_por_canvas.get(chave):
            return False
        self._cursor_por_canvas[chave] = canvas._ponto_com_snap(event.position())
        self._atualizar_status_perimetro(canvas, self._obter_dialog(canvas))
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if not self._desenhando_por_canvas.get(id(canvas)):
            return
        pontos = self._pontos_transformados(canvas, self._obter_dialog(canvas))
        if len(pontos) < 2:
            return
        for a, b in zip(pontos, pontos[1:]):
            canvas._desenhar_segmento(painter, a, b, cor="#ff1245", espessura=1.8)

    def _pontos_transformados(self, canvas, dialog: InserirCurvaDialog) -> list[QPointF]:
        chave = id(canvas)
        origem = self._origem_por_canvas.get(chave)
        cursor = self._cursor_por_canvas.get(chave)
        base = dialog.pontos_processados()
        if origem is None or cursor is None or len(base) < 2:
            return base
        p0 = base[0]
        p1 = base[-1]
        bvx = p1.x() - p0.x()
        bvy = p1.y() - p0.y()
        comp_base = max(1e-6, sqrt((bvx * bvx) + (bvy * bvy)))
        tvx = cursor.x() - origem.x()
        tvy = cursor.y() - origem.y()
        comp_target = max(1e-6, sqrt((tvx * tvx) + (tvy * tvy)))
        escala = comp_target / comp_base
        ang_base = atan2(bvy, bvx)
        ang_target = atan2(tvy, tvx)
        delta = ang_target - ang_base
        cd = cos(delta)
        sd = sin(delta)
        out: list[QPointF] = []
        for pt in base:
            rx = (pt.x() - p0.x()) * escala
            ry = (pt.y() - p0.y()) * escala
            x = (rx * cd) - (ry * sd)
            y = (rx * sd) + (ry * cd)
            out.append(QPointF(origem.x() + x, origem.y() + y))
        return out
