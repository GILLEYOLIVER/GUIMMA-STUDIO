from __future__ import annotations

from copy import deepcopy
from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QAbstractSpinBox, QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QLabel, QVBoxLayout

from tools.medicao_utils import selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class ElementoParaleloDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:elemento_paralelo"
        self.setWindowTitle("Elemento paralelo")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(305)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QDoubleSpinBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            """
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.sp_distancia = QDoubleSpinBox()
        self.sp_distancia.setRange(0.001, 999999.0)
        self.sp_distancia.setDecimals(3)
        self.sp_distancia.setSingleStep(0.1)
        self.sp_distancia.setValue(2.0)
        self.sp_distancia.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_distancia_2 = QCheckBox("Distância paralela 2 (cm)")
        self.sp_distancia_2 = QDoubleSpinBox()
        self.sp_distancia_2.setRange(0.001, 999999.0)
        self.sp_distancia_2.setDecimals(3)
        self.sp_distancia_2.setSingleStep(0.1)
        self.sp_distancia_2.setValue(1.0)
        self.sp_distancia_2.setEnabled(False)
        self.sp_distancia_2.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_linha_auxiliar = QCheckBox("Inserir elemento como linha auxiliar")
        form.addRow("Distância paralela (cm)", self.sp_distancia)
        form.addRow(self.chk_distancia_2, self.sp_distancia_2)
        raiz.addLayout(form)
        raiz.addWidget(self.chk_linha_auxiliar)
        self.chk_distancia_2.toggled.connect(self.sp_distancia_2.setEnabled)


class Ferramenta(FerramentaBase):
    id_ferramenta = "elemento_paralelo"
    nome = "Elemento Paralelo"
    usa_painel_auxiliar = False
    descricao_painel = "Cria linha/contorno paralelo por clique ou pela seleção."

    _dialog_por_canvas: dict[int, ElementoParaleloDialog] = {}

    def __init__(self):
        super().__init__()
        self._preview: list[QPointF] = []
        self._preview_2: list[QPointF] = []
        self._hover_info: dict | None = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._preview = []
        self._preview_2 = []
        self._hover_info = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Elemento paralelo: mova o mouse para indicar o lado. Esquerdo aplica; direito fecha.")

    def on_deactivate(self, canvas):
        self._preview = []
        self._preview_2 = []
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
        if event.button() == Qt.RightButton:
            if self._operacao_finalizada and not self._direito_confirma_fechamento:
                self._direito_confirma_fechamento = True
                self._status(canvas, "Operação finalizada. Clique direito novamente fecha a ferramenta.")
            else:
                self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._atualizar_preview(canvas, pos)
        if not self._preview:
            self._status(canvas, "Nenhum segmento/contorno encontrado para criar paralelo.")
            return False
        if self._preview_2:
            self._criar_elemento(canvas, self._preview, self._hover_info, registrar=False)
            self._criar_elemento(canvas, self._preview_2, self._hover_info, registrar=False)
            canvas._registrar_historico()
            canvas.update()
        else:
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
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.sp_distancia.valueChanged.connect(lambda _v: self._redesenhar(canvas))
            dialog.sp_distancia_2.valueChanged.connect(lambda _v: self._redesenhar(canvas))
            dialog.chk_distancia_2.toggled.connect(lambda _ativo: self._redesenhar(canvas))
        return dialog

    def _restaurar_dialog(self, canvas, dialog: ElementoParaleloDialog) -> None:
        fallback = None
        if hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

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

    def _redesenhar(self, canvas) -> None:
        canvas.update()

    def _atualizar_preview(self, canvas, pos: QPointF) -> None:
        dialog = self._obter_dialog(canvas)
        self._preview = []
        self._preview_2 = []
        self._hover_info = None
        distancia = self._distancia_cena(canvas)
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if not info:
            return
        a = info["segmento_inicio"]
        b = info["segmento_fim"]
        nx, ny = self._normal_segmento(a, b)
        mx = (a.x() + b.x()) / 2.0
        my = (a.y() + b.y()) / 2.0
        if ((pos.x() - mx) * nx + (pos.y() - my) * ny) < 0:
            nx, ny = -nx, -ny
        self._preview = [QPointF(a.x() + nx * distancia, a.y() + ny * distancia), QPointF(b.x() + nx * distancia, b.y() + ny * distancia)]
        if dialog.chk_distancia_2.isChecked():
            distancia_2 = self._distancia_cena_2(canvas)
            self._preview_2 = [QPointF(a.x() + nx * distancia_2, a.y() + ny * distancia_2), QPointF(b.x() + nx * distancia_2, b.y() + ny * distancia_2)]
        self._hover_info = info

    def _criar_elemento(self, canvas, pontos: list[QPointF], info: dict | None, registrar: bool = True) -> None:
        if len(pontos) < 2:
            return
        dialog = self._obter_dialog(canvas)
        origem = canvas.cena.elementos[int(info["elemento_idx"])] if info and "elemento_idx" in info and 0 <= int(info["elemento_idx"]) < len(canvas.cena.elementos) else {}
        auxiliar = bool(dialog.chk_linha_auxiliar.isChecked())
        novo = {
            "tipo": "polyline",
            "pontos": [(p.x(), p.y()) for p in pontos],
            "cor": origem.get("cor", getattr(canvas, "_linha_cor", "#ffffff")),
            "espessura": origem.get("espessura", getattr(canvas, "_linha_espessura", 1.0)),
            "estilo": origem.get("estilo", getattr(canvas, "_linha_estilo", "solid")),
            "id": str(uuid4()),
            "subtipo_audaces": "linha_interna" if auxiliar else "paralela",
            "linha_auxiliar": auxiliar,
            "metadados": {"tipo_ferramenta": self.id_ferramenta, "origem_idx": info.get("elemento_idx") if info else None},
        }
        canvas.cena.elementos.append(novo)
        canvas._selecionados = {len(canvas.cena.elementos) - 1}
        if registrar:
            canvas._registrar_historico()
            canvas.update()
        self._operacao_finalizada = True
        self._direito_confirma_fechamento = False
        self._status(canvas, "Elemento paralelo criado. Clique esquerdo continua; direito fecha.")

    def _fechar(self, canvas) -> None:
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Elemento Paralelo finalizada. Voltando para Selecionar.")

    def on_paint_overlay(self, canvas, painter):
        if len(self._preview) < 2 and len(self._preview_2) < 2:
            return
        painter.save()
        for pontos, cor in ((self._preview, "#00d2ff"), (self._preview_2, "#7fdcff")):
            if len(pontos) < 2:
                continue
            pen = QPen(QColor(cor), 1.8, Qt.DashLine)
            pen.setDashPattern([4.0, 3.0])
            painter.setPen(pen)
            for a, b in zip(pontos, pontos[1:]):
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

    def _distancia_cena_2(self, canvas) -> float:
        valor = float(self._obter_dialog(canvas).sp_distancia_2.value())
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
