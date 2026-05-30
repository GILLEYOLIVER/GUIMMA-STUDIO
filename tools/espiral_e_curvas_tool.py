from __future__ import annotations

from math import atan2, cos, pi, sin, sqrt

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from tools.tool_base import FerramentaBase


def _dist(a: QPointF, b: QPointF) -> float:
    return sqrt(((b.x() - a.x()) ** 2) + ((b.y() - a.y()) ** 2))


# Pontos-base normalizados. O eixo Y menor desenha mais alto no canvas.
# A Curva Francesa 1 recebeu ajuste fino: corpo central um pouco mais alto,
# ápice levemente para a direita e descida final menos agressiva.
PERFIS_CURVAS: dict[str, list[tuple[float, float]]] = {
    "Curva Francesa 1": [
        (0.000, 0.500),
        (0.061, 0.454),
        (0.122, 0.408),
        (0.182, 0.365),
        (0.243, 0.324),
        (0.305, 0.288),
        (0.366, 0.256),
        (0.427, 0.226),
        (0.489, 0.198),
        (0.552, 0.174),
        (0.616, 0.158),
        (0.682, 0.151),
        (0.748, 0.156),
        (0.812, 0.173),
        (0.876, 0.213),
        (0.940, 0.295),
        (1.000, 0.500),
    ],
    "Curva Francesa 2": [(0.06, 0.84), (0.12, 0.74), (0.20, 0.62), (0.31, 0.50), (0.45, 0.38), (0.60, 0.28), (0.75, 0.19), (0.89, 0.13)],
    "Curva Francesa 3": [(0.08, 0.82), (0.16, 0.73), (0.27, 0.62), (0.39, 0.50), (0.52, 0.39), (0.65, 0.30), (0.78, 0.22), (0.90, 0.17)],
    "Curva Francesa 4": [(0.04, 0.73), (0.16, 0.71), (0.31, 0.69), (0.47, 0.66), (0.62, 0.63), (0.77, 0.59), (0.90, 0.55), (0.97, 0.52)],
    "Manga - Cava frente": [(0.08, 0.16), (0.08, 0.33), (0.11, 0.50), (0.20, 0.66), (0.37, 0.78), (0.61, 0.84), (0.90, 0.84)],
    "Cava costas": [(0.08, 0.84), (0.14, 0.74), (0.24, 0.67), (0.38, 0.62), (0.56, 0.59), (0.75, 0.58), (0.90, 0.57)],
    "Gancho calca": [(0.46, 0.14), (0.54, 0.20), (0.60, 0.30), (0.64, 0.43), (0.66, 0.59), (0.66, 0.78)],
    "Lado saia": [(0.06, 0.58), (0.18, 0.60), (0.33, 0.62), (0.49, 0.63), (0.67, 0.63), (0.83, 0.62), (0.94, 0.60)],
    "Decote": [(0.08, 0.46), (0.16, 0.56), (0.28, 0.64), (0.42, 0.69), (0.57, 0.69), (0.72, 0.64), (0.84, 0.56), (0.92, 0.48)],
}


class PreviewCurvaWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pontos: list[QPointF] = []
        self.setMinimumHeight(86)
        self.setMaximumHeight(110)

    def set_pontos(self, pontos: list[QPointF]):
        self._pontos = list(pontos)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#efefef"))
        if len(self._pontos) < 2:
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        xs = [p.x() for p in self._pontos]
        ys = [p.y() for p in self._pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        escala = min(
            max(1.0, self.width() - 12) / max(1e-6, max_x - min_x),
            max(1.0, self.height() - 12) / max(1e-6, max_y - min_y),
        )

        def mapear(pt: QPointF) -> QPointF:
            return QPointF(6 + ((pt.x() - min_x) * escala), 6 + ((pt.y() - min_y) * escala))

        pen = QPen(QColor("#101010"), 1.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        for a, b in zip(self._pontos, self._pontos[1:]):
            painter.drawLine(mapear(a), mapear(b))
        ini = mapear(self._pontos[0])
        fim = mapear(self._pontos[-1])
        painter.fillRect(int(ini.x()) - 2, int(ini.y()) - 2, 5, 5, QColor("#ff0000"))
        painter.fillRect(int(fim.x()) - 2, int(fim.y()) - 2, 5, 5, QColor("#ff00ff"))


class InserirCurvaDialog(QDialog):
    configuracao_alterada = Signal()
    OPCOES = [
        "Curva Francesa 1",
        "Curva Francesa 2",
        "Curva Francesa 3",
        "Curva Francesa 4",
        "Manga - Cava frente",
        "Cava costas",
        "Gancho calca",
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
        self._espelhado = False
        self.setStyleSheet(
            "QDialog{background:#efefef;color:#111} "
            "QLabel{color:#111} "
            "QComboBox{background:#fff;color:#111;border:1px solid #b5bcc3;min-height:22px} "
            "QPushButton{background:#f7f7f7;color:#111;border:1px solid #b7bec5;min-height:22px}"
        )
        self._montar_ui()
        self._atualizar_preview()

    def _montar_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(QLabel("Curva pré-definida"))

        self.cmb_curva = QComboBox()
        self.cmb_curva.addItems(self.OPCOES)
        layout.addWidget(self.cmb_curva)

        self.preview = PreviewCurvaWidget()
        layout.addWidget(self.preview)

        self.lbl_e1 = QLabel("Extremo 1 - 0.0 %")
        self.sl_e1 = QSlider(Qt.Horizontal)
        self.sl_e1.setRange(0, 95)
        self.sl_e1.setValue(0)

        self.lbl_e2 = QLabel("Extremo 2 - 100.0 %")
        self.sl_e2 = QSlider(Qt.Horizontal)
        self.sl_e2.setRange(5, 100)
        self.sl_e2.setValue(100)

        self.btn_espelhar = QPushButton("Espelhar")

        for widget in (self.lbl_e1, self.sl_e1, self.lbl_e2, self.sl_e2, self.btn_espelhar):
            layout.addWidget(widget)

        self.cmb_curva.currentTextChanged.connect(self._atualizar_preview)
        self.sl_e1.valueChanged.connect(self._atualizar_preview)
        self.sl_e2.valueChanged.connect(self._atualizar_preview)
        self.btn_espelhar.clicked.connect(self._alternar_espelho)

    def _alternar_espelho(self):
        self._espelhado = not self._espelhado
        self._atualizar_preview()

    def configuracao(self):
        return (
            self.cmb_curva.currentText(),
            self.sl_e1.value() / 100.0,
            self.sl_e2.value() / 100.0,
            self._espelhado,
        )

    def _atualizar_preview(self):
        if self.sl_e1.value() >= self.sl_e2.value():
            if self.sender() is self.sl_e1:
                self.sl_e1.setValue(max(0, self.sl_e2.value() - 1))
            else:
                self.sl_e2.setValue(min(100, self.sl_e1.value() + 1))
        self.lbl_e1.setText(f"Extremo 1 - {float(self.sl_e1.value()):.1f} %")
        self.lbl_e2.setText(f"Extremo 2 - {float(self.sl_e2.value()):.1f} %")
        self.preview.set_pontos(self.pontos_processados())
        self.configuracao_alterada.emit()

    def pontos_controle_processados(self) -> list[QPointF]:
        nome, ext1, ext2, espelhado = self.configuracao()
        controles = _gerar_pontos_controle_base(nome)
        if espelhado:
            controles = [QPointF(-p.x(), p.y()) for p in controles]
        if len(controles) < 2:
            return []
        i1 = max(0, min(int((len(controles) - 1) * ext1), len(controles) - 2))
        i2 = max(i1 + 1, min(int((len(controles) - 1) * ext2), len(controles) - 1))
        return controles[i1 : i2 + 1]

    def pontos_processados(self) -> list[QPointF]:
        nome, ext1, ext2, espelhado = self.configuracao()
        base = _gerar_curva_base(nome)
        if espelhado:
            base = [QPointF(-p.x(), p.y()) for p in base]
        if len(base) < 2:
            return []
        i1 = max(0, min(int((len(base) - 1) * ext1), len(base) - 2))
        i2 = max(i1 + 1, min(int((len(base) - 1) * ext2), len(base) - 1))
        return base[i1 : i2 + 1]


def _catmull_rom(pontos: list[QPointF], amostras: int = 32) -> list[QPointF]:
    if len(pontos) < 3:
        return list(pontos)
    pts = [
        QPointF(pontos[0].x() * 2 - pontos[1].x(), pontos[0].y() * 2 - pontos[1].y())
    ] + list(pontos) + [
        QPointF(pontos[-1].x() * 2 - pontos[-2].x(), pontos[-1].y() * 2 - pontos[-2].y())
    ]
    saida: list[QPointF] = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for j in range(amostras):
            t = j / amostras
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                (2 * p1.x())
                + (-p0.x() + p2.x()) * t
                + (2 * p0.x() - 5 * p1.x() + 4 * p2.x() - p3.x()) * t2
                + (-p0.x() + 3 * p1.x() - 3 * p2.x() + p3.x()) * t3
            )
            y = 0.5 * (
                (2 * p1.y())
                + (-p0.y() + p2.y()) * t
                + (2 * p0.y() - 5 * p1.y() + 4 * p2.y() - p3.y()) * t2
                + (-p0.y() + 3 * p1.y() - 3 * p2.y() + p3.y()) * t3
            )
            saida.append(QPointF(x, y))
    saida.append(pontos[-1])
    return saida


def _perfil_para_pontos(perfil: list[tuple[float, float]], sx=6.0, sy=4.0) -> list[QPointF]:
    return [QPointF((x - 0.5) * sx, (y - 0.5) * sy) for x, y in perfil]


def _gerar_pontos_controle_base(nome: str) -> list[QPointF]:
    if nome == "Spiral":
        return [
            QPointF(
                cos((2 * pi * 2.3 * (i / 28)) - (pi / 2)) * (3 * (i / 28)),
                sin((2 * pi * 2.3 * (i / 28)) - (pi / 2)) * (3 * (i / 28)),
            )
            for i in range(29)
        ]
    return _perfil_para_pontos(PERFIS_CURVAS.get(nome, PERFIS_CURVAS["Curva Francesa 1"]))


def _gerar_curva_base(nome: str) -> list[QPointF]:
    if nome == "Spiral":
        return [
            QPointF(
                cos((2 * pi * 2.3 * (i / 219)) - (pi / 2)) * (3 * (i / 219)),
                sin((2 * pi * 2.3 * (i / 219)) - (pi / 2)) * (3 * (i / 219)),
            )
            for i in range(220)
        ]
    return _catmull_rom(_gerar_pontos_controle_base(nome), 32)


class Ferramenta(FerramentaBase):
    id_ferramenta = "espiral_e_curvas"
    nome = "Espiral e Curvas"
    usa_painel_auxiliar = False
    descricao_painel = "Insere curvas pré-definidas editáveis."
    _dialog_por_canvas = {}
    _canvas_por_id = {}
    _ultimo_idx_por_canvas = {}
    _ultima_transformacao_por_canvas = {}
    _desenhando_por_canvas = {}
    _origem_por_canvas = {}
    _cursor_por_canvas = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        chave = id(canvas)
        self._canvas_por_id[chave] = canvas
        self._desenhando_por_canvas[chave] = False
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._atualizar_status_perimetro(canvas, dialog)
        msg = "Inserir curva: escolha o modelo, clique no início e clique no fim. Depois use Manipular Pontos para editar."
        self.set_status(msg)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(msg)

    def on_deactivate(self, canvas):
        super().on_deactivate(canvas)
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog:
            dialog.hide()
        for dicionario in (self._canvas_por_id, self._desenhando_por_canvas, self._origem_por_canvas, self._cursor_por_canvas):
            dicionario.pop(id(canvas), None)

    def on_mouse_press(self, canvas, event):
        chave = id(canvas)
        if event.button() == Qt.RightButton:
            if self._desenhando_por_canvas.get(chave):
                self._desenhando_por_canvas[chave] = False
                self._origem_por_canvas.pop(chave, None)
                self._cursor_por_canvas.pop(chave, None)
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

        controles = self._pontos_transformados(canvas, dialog, dialog.pontos_controle_processados())
        if len(controles) >= 2:
            elemento = self._criar_elemento_curva_editavel(canvas, dialog, controles)
            canvas.cena.elementos.append(elemento)
            self._ultimo_idx_por_canvas[chave] = len(canvas.cena.elementos) - 1
            origem = self._origem_por_canvas.get(chave)
            cursor = self._cursor_por_canvas.get(chave)
            self._ultima_transformacao_por_canvas[chave] = (QPointF(origem) if origem else None, QPointF(cursor) if cursor else None)
            canvas._registrar_historico()

        self._desenhando_por_canvas[chave] = False
        self._origem_por_canvas.pop(chave, None)
        self._cursor_por_canvas.pop(chave, None)
        self._atualizar_status_perimetro(canvas, dialog)
        canvas.update()
        event.accept()
        return True

    def _criar_elemento_curva_editavel(self, canvas, dialog: InserirCurvaDialog, controles: list[QPointF]) -> dict:
        nome_curva = dialog.cmb_curva.currentText()
        pontos = [(float(p.x()), float(p.y())) for p in controles]
        return {
            "tipo": "polyline",
            "pontos": pontos,
            "cor": getattr(canvas, "_linha_cor", "#ffffff"),
            "espessura": float(getattr(canvas, "_linha_espessura", 1.0)),
            "estilo": str(getattr(canvas, "_linha_estilo", "solid")),
            "amplitude": float(getattr(canvas, "_linha_amplitude", 1.0)),
            "fase_inicio": 0.0,
            "curva_suave": True,
            "suavizar": True,
            "renderizacao": "curva_suave",
            "tipo_curva": "spline_catmull_rom",
            "subtipo_audaces": "curva_predefinida",
            "nome_curva_predefinida": nome_curva,
            "metadados": {"tipo_ferramenta": self.id_ferramenta, "curva": nome_curva},
        }

    def _obter_dialog(self, canvas):
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = InserirCurvaDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        if not hasattr(dialog, "_callbacks_canvas"):
            dialog._callbacks_canvas = set()
        if chave not in dialog._callbacks_canvas:
            dialog.configuracao_alterada.connect(lambda chave_canvas=chave: self._quando_config_alterada(chave_canvas))
            dialog._callbacks_canvas.add(chave)
        return dialog

    def _quando_config_alterada(self, chave_canvas):
        dialog = self._dialog_por_canvas.get(chave_canvas)
        canvas = self._canvas_por_id.get(chave_canvas)
        if dialog is None or canvas is None:
            return
        self._atualizar_ultimo_elemento(canvas, dialog)
        self._atualizar_status_perimetro(canvas, dialog)
        canvas.update()

    def _atualizar_ultimo_elemento(self, canvas, dialog):
        chave = id(canvas)
        idx = self._ultimo_idx_por_canvas.get(chave)
        transformacao = self._ultima_transformacao_por_canvas.get(chave)
        if idx is None or transformacao is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        origem, cursor = transformacao
        if origem is None or cursor is None:
            return
        controles = self._transformar_pontos_por_referencia(dialog.pontos_controle_processados(), origem, cursor)
        if len(controles) >= 2 and canvas.cena.elementos[idx].get("tipo") == "polyline":
            canvas.cena.elementos[idx].update(self._criar_elemento_curva_editavel(canvas, dialog, controles))

    def _atualizar_status_perimetro(self, canvas, dialog):
        pontos = self._pontos_transformados(canvas, dialog, dialog.pontos_processados()) if self._desenhando_por_canvas.get(id(canvas)) else dialog.pontos_processados()
        total = sum(_dist(a, b) for a, b in zip(pontos, pontos[1:])) if len(pontos) >= 2 else 0.0
        msg = f"Perímetro: {canvas.formatar_valor_unidade(total)} ({getattr(canvas, '_unidade_sigla', 'cm')})"
        self.set_status(msg)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(msg)

    def on_mouse_move(self, canvas, event):
        if not self._desenhando_por_canvas.get(id(canvas)):
            return False
        self._cursor_por_canvas[id(canvas)] = canvas._ponto_com_snap(event.position())
        self._atualizar_status_perimetro(canvas, self._obter_dialog(canvas))
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if not self._desenhando_por_canvas.get(id(canvas)):
            return
        pontos = self._pontos_transformados(canvas, self._obter_dialog(canvas), self._obter_dialog(canvas).pontos_processados())
        if len(pontos) < 2:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            for a, b in zip(pontos, pontos[1:]):
                canvas._desenhar_segmento(painter, a, b, cor="#1e90ff", espessura=1.8)
        finally:
            painter.restore()

    def _pontos_transformados(self, canvas, dialog, base: list[QPointF]):
        origem = self._origem_por_canvas.get(id(canvas))
        cursor = self._cursor_por_canvas.get(id(canvas))
        if origem is None or cursor is None or len(base) < 2:
            return base
        return self._transformar_pontos_por_referencia(base, origem, cursor)

    @staticmethod
    def _transformar_pontos_por_referencia(base: list[QPointF], origem: QPointF, cursor: QPointF) -> list[QPointF]:
        if len(base) < 2:
            return list(base)
        p0, p1 = base[0], base[-1]
        bvx, bvy = p1.x() - p0.x(), p1.y() - p0.y()
        tvx, tvy = cursor.x() - origem.x(), cursor.y() - origem.y()
        escala = max(1e-6, sqrt((tvx * tvx) + (tvy * tvy))) / max(1e-6, sqrt((bvx * bvx) + (bvy * bvy)))
        delta = atan2(tvy, tvx) - atan2(bvy, bvx)
        cd, sd = cos(delta), sin(delta)
        saida = []
        for pt in base:
            rx, ry = (pt.x() - p0.x()) * escala, (pt.y() - p0.y()) * escala
            saida.append(QPointF(origem.x() + (rx * cd) - (ry * sd), origem.y() + (rx * sd) + (ry * cd)))
        return saida
