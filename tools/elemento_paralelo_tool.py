from __future__ import annotations

from copy import deepcopy
from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from tools.medicao_utils import selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase


class ElementoParaleloDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Elemento paralelo")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(280)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QComboBox, QDoubleSpinBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            QPushButton { background:#f7f7f7; color:#111111; border:1px solid #b7bec5; min-height:24px; }
            QPushButton:hover { background:#ffffff; }
            """
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.cmb_alvo = QComboBox()
        self.cmb_alvo.addItems(["Segmento clicado", "Todo contorno selecionado"])
        self.cmb_lado = QComboBox()
        self.cmb_lado.addItems(["Lado do clique", "Inverter lado"])
        self.sp_distancia = QDoubleSpinBox()
        self.sp_distancia.setRange(0.001, 999999.0)
        self.sp_distancia.setDecimals(3)
        self.sp_distancia.setSingleStep(0.1)
        self.sp_distancia.setValue(1.0)
        self.chk_manter_molde = QCheckBox("Nova linha faz parte do molde")
        self.chk_manter_molde.setChecked(False)
        form.addRow("Alvo", self.cmb_alvo)
        form.addRow("Lado", self.cmb_lado)
        form.addRow("Distância (cm)", self.sp_distancia)
        raiz.addLayout(form)
        raiz.addWidget(self.chk_manter_molde)
        rod = QHBoxLayout()
        rod.addStretch(1)
        self.btn_aplicar = QPushButton("Aplicar na seleção")
        rod.addWidget(self.btn_aplicar)
        raiz.addLayout(rod)


class Ferramenta(FerramentaBase):
    id_ferramenta = "elemento_paralelo"
    nome = "Elemento Paralelo"
    usa_painel_auxiliar = False
    descricao_painel = "Cria linha/contorno paralelo por clique ou pela seleção."

    _dialog_por_canvas: dict[int, ElementoParaleloDialog] = {}

    def __init__(self):
        super().__init__()
        self._preview: list[QPointF] = []
        self._hover_info: dict | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._preview = []
        self._hover_info = None
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Elemento paralelo: passe o mouse sobre uma linha e clique para criar a paralela.")

    def on_deactivate(self, canvas):
        self._preview = []
        self._hover_info = None
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._atualizar_preview(canvas, pos)
        canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._atualizar_preview(canvas, pos)
        if not self._preview:
            self._status(canvas, "Nenhum segmento/contorno encontrado para criar paralelo.")
            return False
        self._criar_elemento(canvas, self._preview, self._hover_info)
        event.accept()
        return True

    def _obter_dialog(self, canvas) -> ElementoParaleloDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = ElementoParaleloDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.btn_aplicar.clicked.connect(lambda: self._aplicar_selecao(canvas))
            dialog.sp_distancia.valueChanged.connect(lambda _v: canvas.update())
        return dialog

    def _aplicar_selecao(self, canvas) -> None:
        indices = [int(i) for i in sorted(getattr(canvas, "_selecionados", set()) or []) if 0 <= int(i) < len(canvas.cena.elementos)]
        if not indices:
            self._status(canvas, "Elemento paralelo: selecione um contorno ou clique em um segmento.")
            return
        criou = 0
        for idx in indices:
            el = canvas.cena.elementos[idx]
            pts = self._pontos_poly(el)
            if len(pts) < 2:
                continue
            paralelo = self._offset_polyline(pts, self._distancia_cena(canvas), fechar=self._fechado(pts))
            if paralelo:
                self._criar_elemento(canvas, paralelo, {"elemento_idx": idx})
                criou += 1
        if criou:
            self._status(canvas, f"Criado(s) {criou} elemento(s) paralelo(s).")
        else:
            self._status(canvas, "Não foi possível criar paralelo da seleção.")

    def _atualizar_preview(self, canvas, pos: QPointF) -> None:
        dialog = self._obter_dialog(canvas)
        self._preview = []
        self._hover_info = None
        distancia = self._distancia_cena(canvas)
        if dialog.cmb_alvo.currentText() == "Todo contorno selecionado" and getattr(canvas, "_selecionados", set()):
            idx = sorted(canvas._selecionados)[0]
            if 0 <= idx < len(canvas.cena.elementos):
                pts = self._pontos_poly(canvas.cena.elementos[idx])
                self._preview = self._offset_polyline(pts, distancia, fechar=self._fechado(pts))
                self._hover_info = {"elemento_idx": idx}
                return
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if not info:
            return
        a = info["segmento_inicio"]
        b = info["segmento_fim"]
        nx, ny = self._normal_segmento(a, b)
        if dialog.cmb_lado.currentText() == "Inverter lado":
            nx, ny = -nx, -ny
        # Se o clique está do outro lado, inverte para respeitar "lado do clique".
        if dialog.cmb_lado.currentText() == "Lado do clique":
            mx = (a.x() + b.x()) / 2.0
            my = (a.y() + b.y()) / 2.0
            if ((pos.x() - mx) * nx + (pos.y() - my) * ny) < 0:
                nx, ny = -nx, -ny
        self._preview = [QPointF(a.x() + nx * distancia, a.y() + ny * distancia), QPointF(b.x() + nx * distancia, b.y() + ny * distancia)]
        self._hover_info = info

    def _criar_elemento(self, canvas, pontos: list[QPointF], info: dict | None) -> None:
        if len(pontos) < 2:
            return
        dialog = self._obter_dialog(canvas)
        origem = canvas.cena.elementos[int(info["elemento_idx"])] if info and "elemento_idx" in info and 0 <= int(info["elemento_idx"]) < len(canvas.cena.elementos) else {}
        novo = {
            "tipo": "polyline",
            "pontos": [(p.x(), p.y()) for p in pontos],
            "cor": origem.get("cor", getattr(canvas, "_linha_cor", "#ffffff")),
            "espessura": origem.get("espessura", getattr(canvas, "_linha_espessura", 1.0)),
            "estilo": origem.get("estilo", getattr(canvas, "_linha_estilo", "solid")),
            "id": str(uuid4()),
            "subtipo_audaces": "paralela",
            "parte_do_molde": bool(dialog.chk_manter_molde.isChecked()),
            "metadados": {"tipo_ferramenta": self.id_ferramenta, "origem_idx": info.get("elemento_idx") if info else None},
        }
        if dialog.chk_manter_molde.isChecked() and origem.get("molde_id"):
            novo["molde_id"] = origem.get("molde_id")
        canvas.cena.elementos.append(novo)
        canvas._selecionados = {len(canvas.cena.elementos) - 1}
        canvas._registrar_historico()
        canvas.update()
        self._status(canvas, "Elemento paralelo criado.")

    def on_paint_overlay(self, canvas, painter):
        if len(self._preview) < 2:
            return
        painter.save()
        pen = QPen(QColor("#00d2ff"), 1.8, Qt.DashLine)
        pen.setDashPattern([4.0, 3.0])
        painter.setPen(pen)
        for a, b in zip(self._preview, self._preview[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def _distancia_cena(self, canvas) -> float:
        valor = float(self._obter_dialog(canvas).sp_distancia.value())
        if hasattr(canvas, "converter_para_cena"):
            try:
                return float(canvas.converter_para_cena(valor))
            except Exception:
                pass
        return valor * max(1e-9, float(getattr(canvas, "_unidade_fator", 1.0)))

    def _pontos_poly(self, el: dict) -> list[QPointF]:
        if el.get("tipo") != "polyline":
            return []
        return [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]

    def _offset_polyline(self, pts: list[QPointF], distancia: float, fechar: bool) -> list[QPointF]:
        if len(pts) < 2:
            return []
        base = pts[:-1] if fechar and self._dist(pts[0], pts[-1]) <= 1e-6 else pts[:]
        if len(base) < 2:
            return []
        if not fechar:
            out = []
            for i, p in enumerate(base):
                if i == 0:
                    nx, ny = self._normal_segmento(base[0], base[1])
                elif i == len(base) - 1:
                    nx, ny = self._normal_segmento(base[-2], base[-1])
                else:
                    n1 = self._normal_segmento(base[i - 1], base[i])
                    n2 = self._normal_segmento(base[i], base[i + 1])
                    nx, ny = self._normalizar(n1[0] + n2[0], n1[1] + n2[1])
                out.append(QPointF(p.x() + nx * distancia, p.y() + ny * distancia))
            return out
        sentido = 1.0 if self._area(base) < 0 else -1.0
        linhas = []
        n = len(base)
        for i in range(n):
            a, b = base[i], base[(i + 1) % n]
            nx, ny = self._normal_segmento(a, b)
            nx, ny = nx * sentido, ny * sentido
            linhas.append((QPointF(a.x() + nx * distancia, a.y() + ny * distancia), QPointF(b.x() + nx * distancia, b.y() + ny * distancia)))
        out = []
        for i in range(n):
            inter = self._intersecao_linhas(linhas[(i - 1) % n][0], linhas[(i - 1) % n][1], linhas[i][0], linhas[i][1])
            out.append(inter if inter is not None else linhas[i][0])
        out.append(QPointF(out[0]))
        return out

    @staticmethod
    def _normal_segmento(a: QPointF, b: QPointF) -> tuple[float, float]:
        dx, dy = b.x() - a.x(), b.y() - a.y()
        comp = sqrt(dx * dx + dy * dy) or 1.0
        return -dy / comp, dx / comp

    @staticmethod
    def _normalizar(x: float, y: float) -> tuple[float, float]:
        d = sqrt(x * x + y * y) or 1.0
        return x / d, y / d

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

    @staticmethod
    def _fechado(pts: list[QPointF]) -> bool:
        return len(pts) >= 3 and Ferramenta._dist(pts[0], pts[-1]) <= 1e-6

    @staticmethod
    def _area(pts: list[QPointF]) -> float:
        return sum((a.x() * b.y()) - (b.x() * a.y()) for a, b in zip(pts, pts[1:] + pts[:1])) / 2.0

    @staticmethod
    def _intersecao_linhas(a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF) -> QPointF | None:
        x1, y1, x2, y2 = a1.x(), a1.y(), a2.x(), a2.y()
        x3, y3, x4, y4 = b1.x(), b1.y(), b2.x(), b2.y()
        den = ((x1 - x2) * (y3 - y4)) - ((y1 - y2) * (x3 - x4))
        if abs(den) <= 1e-9:
            return None
        px = (((x1 * y2) - (y1 * x2)) * (x3 - x4) - (x1 - x2) * ((x3 * y4) - (y3 * x4))) / den
        py = (((x1 * y2) - (y1 * x2)) * (y3 - y4) - (y1 - y2) * ((x3 * y4) - (y3 * x4))) / den
        return QPointF(px, py)

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
