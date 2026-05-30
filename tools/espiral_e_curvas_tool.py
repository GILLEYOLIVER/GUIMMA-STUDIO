from __future__ import annotations

from math import atan2, cos, pi, sin, sqrt

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from tools.tool_base import FerramentaBase


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
        if len(self._pontos) < 2:
            return
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#efefef"))
        p.setRenderHint(QPainter.Antialiasing, True)
        xs = [pt.x() for pt in self._pontos]
        ys = [pt.y() for pt in self._pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        escala = min((self.width() - 12) / max(1e-6, max_x - min_x), (self.height() - 12) / max(1e-6, max_y - min_y))

        def m(pt: QPointF):
            return QPointF(6 + (pt.x() - min_x) * escala, 6 + (pt.y() - min_y) * escala)

        pen = QPen(QColor("#101010"), 1.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        for a, b in zip(self._pontos, self._pontos[1:]):
            p.drawLine(m(a), m(b))
        ini, fim = m(self._pontos[0]), m(self._pontos[-1])
        p.fillRect(int(ini.x()) - 2, int(ini.y()) - 2, 5, 5, QColor("#ff0000"))
        p.fillRect(int(fim.x()) - 2, int(fim.y()) - 2, 5, 5, QColor("#ff00ff"))


class InserirCurvaDialog(QDialog):
    configuracao_alterada = Signal()
    OPCOES = ["Curva Francesa 1", "Curva Francesa 2", "Curva Francesa 3", "Curva Francesa 4", "Manga - Cava frente", "Cava costas", "Gancho calca", "Lado saia", "Decote", "Spiral"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inserir curva")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(212)
        self._espelhado = False
        self.setStyleSheet("QDialog{background:#efefef;color:#111} QLabel{color:#111} QComboBox{background:#fff;color:#111;border:1px solid #b5bcc3;min-height:22px} QPushButton{background:#f7f7f7;color:#111;border:1px solid #b7bec5;min-height:22px}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        lay.addWidget(QLabel("Curva pre-definida"))
        self.cmb_curva = QComboBox()
        self.cmb_curva.addItems(self.OPCOES)
        lay.addWidget(self.cmb_curva)
        self.preview = PreviewCurvaWidget()
        lay.addWidget(self.preview)
        self.lbl_e1 = QLabel("Extremo 1 - 0.0 %")
        self.sl_e1 = QSlider(Qt.Horizontal)
        self.sl_e1.setRange(0, 95)
        self.sl_e1.setValue(0)
        self.lbl_e2 = QLabel("Extremo 2 - 100.0 %")
        self.sl_e2 = QSlider(Qt.Horizontal)
        self.sl_e2.setRange(5, 100)
        self.sl_e2.setValue(100)
        self.btn_espelhar = QPushButton("Espelhar")
        for w in (self.lbl_e1, self.sl_e1, self.lbl_e2, self.sl_e2, self.btn_espelhar):
            lay.addWidget(w)
        self.cmb_curva.currentTextChanged.connect(self._atualizar_preview)
        self.sl_e1.valueChanged.connect(self._atualizar_preview)
        self.sl_e2.valueChanged.connect(self._atualizar_preview)
        self.btn_espelhar.clicked.connect(self._alternar_espelho)
        self._atualizar_preview()

    def _alternar_espelho(self):
        self._espelhado = not self._espelhado
        self._atualizar_preview()

    def configuracao(self):
        return self.cmb_curva.currentText(), self.sl_e1.value() / 100.0, self.sl_e2.value() / 100.0, self._espelhado

    def _atualizar_preview(self):
        if self.sl_e1.value() >= self.sl_e2.value():
            self.sl_e2.setValue(min(100, self.sl_e1.value() + 1))
        self.lbl_e1.setText(f"Extremo 1 - {self.sl_e1.value():.1f} %")
        self.lbl_e2.setText(f"Extremo 2 - {self.sl_e2.value():.1f} %")
        self.preview.set_pontos(self.pontos_processados())
        self.configuracao_alterada.emit()

    def pontos_processados(self):
        nome, e1, e2, esp = self.configuracao()
        base = _gerar_curva_base(nome)
        if esp:
            base = [QPointF(-p.x(), p.y()) for p in base]
        if len(base) < 2:
            return []
        i1 = max(0, min(int((len(base) - 1) * e1), len(base) - 2))
        i2 = max(i1 + 1, min(int((len(base) - 1) * e2), len(base) - 1))
        return base[i1:i2 + 1]


def _catmull(pontos: list[QPointF], amostras=36):
    if len(pontos) < 3:
        return pontos
    pts = [QPointF(pontos[0].x() * 2 - pontos[1].x(), pontos[0].y() * 2 - pontos[1].y())] + pontos + [QPointF(pontos[-1].x() * 2 - pontos[-2].x(), pontos[-1].y() * 2 - pontos[-2].y())]
    saida: list[QPointF] = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for j in range(amostras):
            t = j / amostras
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2*p1.x()) + (-p0.x()+p2.x())*t + (2*p0.x()-5*p1.x()+4*p2.x()-p3.x())*t2 + (-p0.x()+3*p1.x()-3*p2.x()+p3.x())*t3)
            y = 0.5 * ((2*p1.y()) + (-p0.y()+p2.y())*t + (2*p0.y()-5*p1.y()+4*p2.y()-p3.y())*t2 + (-p0.y()+3*p1.y()-3*p2.y()+p3.y())*t3)
            saida.append(QPointF(x, y))
    saida.append(pontos[-1])
    return saida


def _interp(perfil, sx=6.0, sy=4.0):
    return _catmull([QPointF((x - 0.5) * sx, (y - 0.5) * sy) for x, y in perfil], 32)


def _gerar_curva_base(nome: str):
    perfis = {
        "Curva Francesa 1": [(0.000,0.500),(0.061,0.455),(0.122,0.410),(0.182,0.367),(0.243,0.326),(0.305,0.290),(0.366,0.258),(0.427,0.228),(0.489,0.199),(0.550,0.177),(0.612,0.162),(0.674,0.154),(0.737,0.161),(0.800,0.179),(0.865,0.222),(0.930,0.310),(1.000,0.500)],
        "Curva Francesa 2": [(0.06,0.84),(0.12,0.74),(0.20,0.62),(0.31,0.50),(0.45,0.38),(0.60,0.28),(0.75,0.19),(0.89,0.13)],
        "Curva Francesa 3": [(0.08,0.82),(0.16,0.73),(0.27,0.62),(0.39,0.50),(0.52,0.39),(0.65,0.30),(0.78,0.22),(0.90,0.17)],
        "Curva Francesa 4": [(0.04,0.73),(0.16,0.71),(0.31,0.69),(0.47,0.66),(0.62,0.63),(0.77,0.59),(0.90,0.55),(0.97,0.52)],
        "Manga - Cava frente": [(0.08,0.16),(0.08,0.33),(0.11,0.50),(0.20,0.66),(0.37,0.78),(0.61,0.84),(0.90,0.84)],
        "Cava costas": [(0.08,0.84),(0.14,0.74),(0.24,0.67),(0.38,0.62),(0.56,0.59),(0.75,0.58),(0.90,0.57)],
        "Gancho calca": [(0.46,0.14),(0.54,0.20),(0.60,0.30),(0.64,0.43),(0.66,0.59),(0.66,0.78)],
        "Lado saia": [(0.06,0.58),(0.18,0.60),(0.33,0.62),(0.49,0.63),(0.67,0.63),(0.83,0.62),(0.94,0.60)],
        "Decote": [(0.08,0.46),(0.16,0.56),(0.28,0.64),(0.42,0.69),(0.57,0.69),(0.72,0.64),(0.84,0.56),(0.92,0.48)],
    }
    if nome == "Spiral":
        return [QPointF(cos((2*pi*2.3*(i/219))-(pi/2))*(3*(i/219)), sin((2*pi*2.3*(i/219))-(pi/2))*(3*(i/219))) for i in range(220)]
    return _interp(perfis.get(nome, perfis["Curva Francesa 1"]))


class Ferramenta(FerramentaBase):
    id_ferramenta = "espiral_e_curvas"
    nome = "Espiral e Curvas"
    usa_painel_auxiliar = False
    descricao_painel = "Insere curvas pre-definidas."
    _dialog_por_canvas = {}
    _canvas_por_id = {}
    _ultimo_idx_por_canvas = {}
    _ultima_origem_por_canvas = {}
    _desenhando_por_canvas = {}
    _origem_por_canvas = {}
    _cursor_por_canvas = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._canvas_por_id[id(canvas)] = canvas
        self._desenhando_por_canvas[id(canvas)] = False
        d = self._obter_dialog(canvas)
        d.show(); d.raise_(); d.activateWindow()
        self._atualizar_status_perimetro(canvas, d)

    def on_deactivate(self, canvas):
        super().on_deactivate(canvas)
        d = self._dialog_por_canvas.get(id(canvas))
        if d:
            d.hide()
        for dic in (self._canvas_por_id, self._desenhando_por_canvas, self._origem_por_canvas, self._cursor_por_canvas):
            dic.pop(id(canvas), None)

    def on_mouse_press(self, canvas, event):
        chave = id(canvas)
        if event.button() == Qt.RightButton:
            if self._desenhando_por_canvas.get(chave):
                self._desenhando_por_canvas[chave] = False
                self._origem_por_canvas.pop(chave, None)
                self._cursor_por_canvas.pop(chave, None)
                canvas.update(); event.accept(); return True
            return False
        if event.button() != Qt.LeftButton:
            return False
        d = self._obter_dialog(canvas)
        pos = canvas._ponto_com_snap(event.position())
        if not self._desenhando_por_canvas.get(chave):
            self._desenhando_por_canvas[chave] = True
            self._origem_por_canvas[chave] = QPointF(pos)
            self._cursor_por_canvas[chave] = QPointF(pos)
            canvas.update(); event.accept(); return True
        pontos = self._pontos_transformados(canvas, d)
        if len(pontos) >= 2:
            canvas.cena.elementos.append({"tipo":"polyline","pontos":[(p.x(),p.y()) for p in pontos],"cor":getattr(canvas,"_linha_cor","#ffffff"),"espessura":float(getattr(canvas,"_linha_espessura",1.0)),"estilo":str(getattr(canvas,"_linha_estilo","solid")),"amplitude":float(getattr(canvas,"_linha_amplitude",1.0)),"fase_inicio":0.0})
            self._ultimo_idx_por_canvas[chave] = len(canvas.cena.elementos) - 1
            self._ultima_origem_por_canvas[chave] = QPointF(pontos[0])
            canvas._registrar_historico()
        self._desenhando_por_canvas[chave] = False
        self._origem_por_canvas.pop(chave, None); self._cursor_por_canvas.pop(chave, None)
        canvas.update(); event.accept(); return True

    def _obter_dialog(self, canvas):
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        d = self._dialog_por_canvas.get(chave)
        if d is None or d.parentWidget() is not parent:
            d = InserirCurvaDialog(parent); self._dialog_por_canvas[chave] = d
        if not hasattr(d, "_callbacks_canvas"):
            d._callbacks_canvas = set()
        if chave not in d._callbacks_canvas:
            d.configuracao_alterada.connect(lambda chave_canvas=chave: self._quando_config_alterada(chave_canvas))
            d._callbacks_canvas.add(chave)
        return d

    def _quando_config_alterada(self, chave_canvas):
        d = self._dialog_por_canvas.get(chave_canvas)
        canvas = self._canvas_por_id.get(chave_canvas)
        if d is None or canvas is None:
            return
        self._atualizar_ultimo_elemento(canvas, d)
        canvas.update()

    def _atualizar_ultimo_elemento(self, canvas, d):
        idx = self._ultimo_idx_por_canvas.get(id(canvas))
        origem = self._ultima_origem_por_canvas.get(id(canvas))
        if idx is None or origem is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        pts = d.pontos_processados()
        if len(pts) >= 2 and canvas.cena.elementos[idx].get("tipo") == "polyline":
            canvas.cena.elementos[idx]["pontos"] = [(origem.x()+p.x(), origem.y()+p.y()) for p in pts]

    def _atualizar_status_perimetro(self, canvas, d):
        pts = self._pontos_transformados(canvas, d) if self._desenhando_por_canvas.get(id(canvas)) else d.pontos_processados()
        total = sum(_dist(a,b) for a,b in zip(pts, pts[1:])) if len(pts) >= 2 else 0.0
        msg = f"Perimetro: {canvas.formatar_valor_unidade(total)} ({getattr(canvas,'_unidade_sigla','cm')})"
        self.set_status(msg)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(msg)

    def on_mouse_move(self, canvas, event):
        if not self._desenhando_por_canvas.get(id(canvas)):
            return False
        self._cursor_por_canvas[id(canvas)] = canvas._ponto_com_snap(event.position())
        self._atualizar_status_perimetro(canvas, self._obter_dialog(canvas))
        canvas.update(); event.accept(); return True

    def on_paint_overlay(self, canvas, painter):
        if not self._desenhando_por_canvas.get(id(canvas)):
            return
        pts = self._pontos_transformados(canvas, self._obter_dialog(canvas))
        if len(pts) < 2:
            return
        painter.save(); painter.setRenderHint(QPainter.Antialiasing, True)
        for a,b in zip(pts, pts[1:]):
            canvas._desenhar_segmento(painter, a, b, cor="#1e90ff", espessura=1.8)
        painter.restore()

    def _pontos_transformados(self, canvas, d):
        origem = self._origem_por_canvas.get(id(canvas)); cursor = self._cursor_por_canvas.get(id(canvas)); base = d.pontos_processados()
        if origem is None or cursor is None or len(base) < 2:
            return base
        p0, p1 = base[0], base[-1]
        bvx, bvy = p1.x()-p0.x(), p1.y()-p0.y(); tvx, tvy = cursor.x()-origem.x(), cursor.y()-origem.y()
        escala = max(1e-6, sqrt(tvx*tvx+tvy*tvy)) / max(1e-6, sqrt(bvx*bvx+bvy*bvy))
        delta = atan2(tvy,tvx) - atan2(bvy,bvx); cd, sd = cos(delta), sin(delta)
        out=[]
        for pt in base:
            rx, ry = (pt.x()-p0.x())*escala, (pt.y()-p0.y())*escala
            out.append(QPointF(origem.x() + rx*cd - ry*sd, origem.y() + rx*sd + ry*cd))
        return out
