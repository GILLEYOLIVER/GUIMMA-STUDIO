from __future__ import annotations

from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from tools.tool_base import FerramentaBase


class CosturaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Costura")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(378)
        self.setStyleSheet(
            """
            QDialog { background:#f2f2f2; color:#111111; }
            QLabel { color:#111111; font-size:11px; }
            QComboBox, QDoubleSpinBox {
                background:#ffffff; color:#111111;
                border:1px solid #aeb4ba; min-height:21px;
                padding-left:3px;
            }
            QCheckBox { color:#111111; font-size:11px; }
            QPushButton {
                background:#f7f7f7; color:#111111;
                border:1px solid #b7b7b7; min-height:24px;
                padding:2px 14px;
            }
            QPushButton:hover { background:#ffffff; }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(6)

        topo = QGridLayout()
        topo.setHorizontalSpacing(12)
        topo.setVerticalSpacing(5)
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(["Costura", "Offset"])
        self.cmb_posicao = QComboBox()
        self.cmb_posicao.addItems(["Selecionar", "Todo molde"])
        self.sp_costura = QDoubleSpinBox()
        self.sp_costura.setRange(0.1, 20.0)
        self.sp_costura.setDecimals(2)
        self.sp_costura.setSingleStep(0.1)
        self.sp_costura.setValue(1.0)
        self.sp_costura.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_costura_fim = QCheckBox("Costura fim (cm)")
        self.sp_costura_fim = QDoubleSpinBox()
        self.sp_costura_fim.setRange(0.0, 20.0)
        self.sp_costura_fim.setDecimals(2)
        self.sp_costura_fim.setSingleStep(0.1)
        self.sp_costura_fim.setValue(1.0)
        self.sp_costura_fim.setEnabled(False)
        self.sp_costura_fim.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_pique = QCheckBox("Pique")
        self.chk_pique.setChecked(True)
        self.cmb_pique = QComboBox()
        self.cmb_pique.addItems(["T", "V", "I", "Nenhum"])

        topo.addWidget(self.cmb_tipo, 0, 0, 1, 2)
        topo.addWidget(QLabel("Posicao"), 0, 2)
        topo.addWidget(self.cmb_posicao, 0, 3)
        topo.addWidget(QLabel("Costura (cm)"), 1, 0)
        topo.addWidget(self.sp_costura, 1, 1)
        topo.addWidget(self.chk_pique, 1, 2)
        topo.addWidget(self.cmb_pique, 1, 3)
        topo.addWidget(self.chk_costura_fim, 2, 0)
        topo.addWidget(self.sp_costura_fim, 2, 1)
        raiz.addLayout(topo)

        acab = QGridLayout()
        acab.setHorizontalSpacing(8)
        self.cmb_acab_ini = QComboBox()
        self.cmb_acab_fim = QComboBox()
        acabamentos = ["Canto reto", "V aberto", "V fechado", "Degrau", "45 graus", "90 graus"]
        self.cmb_acab_ini.addItems(acabamentos)
        self.cmb_acab_fim.addItems(acabamentos)
        acab.addWidget(QLabel("Acabamento inicial"), 0, 0)
        acab.addWidget(self.cmb_acab_ini, 0, 1)
        acab.addWidget(QLabel("Acabamento final"), 0, 2)
        acab.addWidget(self.cmb_acab_fim, 0, 3)
        raiz.addLayout(acab)

        rodape = QHBoxLayout()
        self.lbl_status = QLabel("Selecione um molde/contorno.")
        self.lbl_status.setWordWrap(True)
        self.btn_aplicar = QPushButton("Aplicar")
        rodape.addWidget(self.lbl_status, 1)
        rodape.addWidget(self.btn_aplicar, 0, Qt.AlignRight)
        raiz.addLayout(rodape)

        self.chk_costura_fim.toggled.connect(self.sp_costura_fim.setEnabled)

    def margem(self) -> float:
        return float(self.sp_costura.value())

    def atualizar_status(self, texto: str) -> None:
        self.lbl_status.setText(texto)

    def atualizar_trechos(self, pontos: list[QPointF]) -> None:
        if len(pontos) >= 4:
            self.atualizar_status(f"Preview de costura com margem de {Ferramenta._fmt(self.margem())} cm.")


class Ferramenta(FerramentaBase):
    id_ferramenta = "costura"
    nome = "Costura"
    usa_painel_auxiliar = False
    descricao_painel = (
        "Clique em um molde/contorno fechado para criar margem de costura. "
        "+/- ajusta a margem, Enter aplica na selecao."
    )
    _dialog_por_canvas: dict[int, CosturaDialog] = {}

    def __init__(self):
        super().__init__()
        self._margem_cm = 1.0
        self._preview: list[QPointF] = []
        self._preview_idx: int | None = None

    def on_activate(self, canvas):
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.atualizar_status(self._mensagem_pronta())

    def on_deactivate(self, canvas):
        self._preview = []
        self._preview_idx = None
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        idx = self._indice_alvo(canvas, pos)
        self._preview_idx = idx
        self._preview = []
        if idx is not None:
            pontos = self._pontos_fechados(canvas.cena.elementos[idx])
            self._preview = [QPointF(x, y) for x, y in self._gerar_costura(pontos, self._margem_cm)]
            self._atualizar_dialog_com_preview(canvas)
        canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        idx = self._indice_alvo(canvas, pos)
        if idx is None:
            self.set_status("Costura: clique em um molde ou contorno fechado.")
            event.accept()
            return True
        if self._aplicar_em_indices(canvas, [idx]):
            canvas._selecionados = {idx}
            self.set_status(f"Costura criada com margem de {self._fmt(self._margem_cm)} cm.")
        else:
            self.set_status("Nao foi possivel gerar costura para esse contorno.")
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        tecla = event.key()
        if tecla in (Qt.Key_Plus, Qt.Key_Equal):
            self._ajustar_margem(canvas, 0.1)
            return True
        if tecla in (Qt.Key_Minus, Qt.Key_Underscore):
            self._ajustar_margem(canvas, -0.1)
            return True
        if tecla in (Qt.Key_Return, Qt.Key_Enter):
            indices = [idx for idx in sorted(getattr(canvas, "_selecionados", set())) if self._elemento_valido(canvas, idx)]
            if not indices and self._preview_idx is not None:
                indices = [self._preview_idx]
            if self._aplicar_em_indices(canvas, indices):
                self.set_status(f"Costura aplicada em {len(indices)} molde(s).")
            else:
                self.set_status("Selecione um molde/contorno fechado ou passe o mouse sobre um alvo.")
            return True
        if tecla == Qt.Key_Escape:
            self._preview = []
            self._preview_idx = None
            canvas.update()
            self.set_status(self._mensagem_pronta())
            return True
        return False

    def on_paint_overlay(self, canvas, painter):
        if len(self._preview) < 2:
            return
        painter.save()
        pen = QPen(QColor("#69c6ff"), 1.2, Qt.DashLine)
        pen.setDashPattern([5.0, 3.0])
        painter.setPen(pen)
        for a, b in zip(self._preview, self._preview[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def set_status(self, texto: str):
        for dialog in self._dialog_por_canvas.values():
            if dialog is not None and dialog.isVisible():
                dialog.atualizar_status(texto)

    def _ajustar_margem(self, canvas, delta: float) -> None:
        self._margem_cm = max(0.1, round(self._margem_cm + delta, 2))
        dialog = self._obter_dialog(canvas)
        dialog.sp_costura.blockSignals(True)
        dialog.sp_costura.setValue(self._margem_cm)
        dialog.sp_costura.blockSignals(False)
        if self._preview_idx is not None and self._elemento_valido(canvas, self._preview_idx):
            pontos = self._pontos_fechados(canvas.cena.elementos[self._preview_idx])
            self._preview = [QPointF(x, y) for x, y in self._gerar_costura(pontos, self._margem_cm)]
            self._atualizar_dialog_com_preview(canvas)
        canvas.update()
        self.set_status(self._mensagem_pronta())

    def _obter_dialog(self, canvas) -> CosturaDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = CosturaDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.sp_costura.valueChanged.connect(lambda valor: self._definir_margem(canvas, float(valor)))
            dialog.cmb_posicao.currentTextChanged.connect(lambda _txt: self._recalcular_preview(canvas))
            dialog.cmb_acab_ini.currentTextChanged.connect(lambda _txt: self._atualizar_dialog_com_preview(canvas))
            dialog.cmb_acab_fim.currentTextChanged.connect(lambda _txt: self._atualizar_dialog_com_preview(canvas))
            dialog.chk_pique.toggled.connect(lambda _ativo: self._atualizar_dialog_com_preview(canvas))
            dialog.cmb_pique.currentTextChanged.connect(lambda _txt: self._atualizar_dialog_com_preview(canvas))
            dialog.btn_aplicar.clicked.connect(lambda: self._aplicar_dialog(canvas))
        return dialog

    def _definir_margem(self, canvas, valor: float) -> None:
        self._margem_cm = max(0.1, round(float(valor), 2))
        self._recalcular_preview(canvas)
        self.set_status(self._mensagem_pronta())

    def _recalcular_preview(self, canvas) -> None:
        if self._preview_idx is not None and self._elemento_valido(canvas, self._preview_idx):
            pontos = self._pontos_fechados(canvas.cena.elementos[self._preview_idx])
            self._preview = [QPointF(x, y) for x, y in self._gerar_costura(pontos, self._margem_cm)]
            self._atualizar_dialog_com_preview(canvas)
        canvas.update()

    def _atualizar_dialog_com_preview(self, canvas) -> None:
        dialog = self._obter_dialog(canvas)
        dialog.atualizar_trechos(self._preview)

    def _aplicar_dialog(self, canvas) -> None:
        indices = [idx for idx in sorted(getattr(canvas, "_selecionados", set())) if self._elemento_valido(canvas, idx)]
        if not indices and self._preview_idx is not None:
            indices = [self._preview_idx]
        if self._aplicar_em_indices(canvas, indices):
            self.set_status(f"Costura aplicada em {len(indices)} molde(s).")
        else:
            self.set_status("Selecione um molde/contorno fechado ou passe o mouse sobre um alvo.")

    def _aplicar_em_indices(self, canvas, indices: list[int]) -> bool:
        alterou = False
        alvos = []
        for idx in indices:
            if not self._elemento_valido(canvas, idx):
                continue
            alvos.append(canvas.cena.elementos[idx])
        for alvo in alvos:
            pontos = self._pontos_fechados(alvo)
            costura = self._gerar_costura(pontos, self._margem_cm)
            if len(costura) < 4:
                continue
            molde_id = str(alvo.get("molde_id") or alvo.get("id") or "")
            if not molde_id:
                molde_id = str(uuid4())
                alvo["molde_id"] = molde_id
            self._remover_costuras_do_alvo(canvas, molde_id)
            canvas.cena.elementos.append(self._elemento_costura(canvas, costura, alvo, molde_id))
            alterou = True
        if alterou:
            canvas._registrar_historico()
            canvas.update()
        return alterou

    def _elemento_costura(self, canvas, pontos: list[tuple[float, float]], alvo: dict, molde_id: str) -> dict:
        dialog = self._dialog_por_canvas.get(id(canvas))
        tipo_costura = "Costura"
        posicao = "Selecionar"
        pique = ""
        acabamento_inicial = ""
        acabamento_final = ""
        if dialog is not None:
            tipo_costura = dialog.cmb_tipo.currentText()
            posicao = dialog.cmb_posicao.currentText()
            pique = dialog.cmb_pique.currentText() if dialog.chk_pique.isChecked() else ""
            acabamento_inicial = dialog.cmb_acab_ini.currentText()
            acabamento_final = dialog.cmb_acab_fim.currentText()
        return {
            "tipo": "polyline",
            "pontos": pontos,
            "cor": "#a5c7ff",
            "espessura": 0.9,
            "estilo": "dash",
            "subtipo_audaces": "costura",
            "molde_id": molde_id,
            "costura_de_molde_id": molde_id,
            "margem_costura_cm": float(self._margem_cm),
            "tipo_costura": tipo_costura,
            "posicao_costura": posicao,
            "pique_costura": pique,
            "acabamento_inicial": acabamento_inicial,
            "acabamento_final": acabamento_final,
            "metadados": {
                "tipo_ferramenta": self.id_ferramenta,
                "subtipo_audaces": "costura",
                "origem_nome_molde": str(alvo.get("nome_molde") or ""),
                "tipo_costura": tipo_costura,
                "posicao_costura": posicao,
                "pique_costura": pique,
                "acabamento_inicial": acabamento_inicial,
                "acabamento_final": acabamento_final,
            },
        }

    def _remover_costuras_do_alvo(self, canvas, molde_id: str) -> None:
        canvas.cena.elementos = [
            el for el in canvas.cena.elementos
            if str(el.get("costura_de_molde_id") or "") != molde_id
        ]

    def _indice_alvo(self, canvas, pos: QPointF) -> int | None:
        for idx in canvas._indices_elementos_em_ponto(pos):
            if self._elemento_valido(canvas, idx):
                return idx
        return None

    def _elemento_valido(self, canvas, idx: int) -> bool:
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return False
        return len(self._pontos_fechados(canvas.cena.elementos[idx])) >= 4

    def _pontos_fechados(self, elemento: dict) -> list[tuple[float, float]]:
        if elemento.get("tipo") != "polyline":
            return []
        subtipo = str(elemento.get("subtipo_audaces") or elemento.get("metadados", {}).get("subtipo_audaces") or "")
        if subtipo == "costura" or elemento.get("costura_de_molde_id"):
            return []
        pontos = [(float(x), float(y)) for x, y in elemento.get("pontos", [])]
        if len(pontos) < 3:
            return []
        if self._dist(pontos[0], pontos[-1]) > 1e-6:
            if not elemento.get("molde"):
                return []
            pontos.append(pontos[0])
        return pontos if len(pontos) >= 4 else []

    def _gerar_costura(self, pontos: list[tuple[float, float]], margem: float) -> list[tuple[float, float]]:
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        if len(base) < 3:
            return []
        sentido = 1.0 if self._area_assinada(base) < 0.0 else -1.0
        linhas = []
        total = len(base)
        for i in range(total):
            a = base[i]
            b = base[(i + 1) % total]
            dx = b[0] - a[0]
            dy = b[1] - a[1]
            comp = sqrt((dx * dx) + (dy * dy))
            if comp <= 1e-9:
                linhas.append((a, b, (0.0, 0.0)))
                continue
            nx = sentido * (-dy / comp)
            ny = sentido * (dx / comp)
            off_a = (a[0] + (nx * margem), a[1] + (ny * margem))
            off_b = (b[0] + (nx * margem), b[1] + (ny * margem))
            linhas.append((off_a, off_b, (nx, ny)))

        saida: list[tuple[float, float]] = []
        for i in range(total):
            prev_a, prev_b, prev_n = linhas[(i - 1) % total]
            curr_a, curr_b, curr_n = linhas[i]
            inter = self._intersecao_linhas(prev_a, prev_b, curr_a, curr_b)
            if inter is None:
                p = base[i]
                nx = (prev_n[0] + curr_n[0]) / 2.0
                ny = (prev_n[1] + curr_n[1]) / 2.0
                mod = sqrt((nx * nx) + (ny * ny)) or 1.0
                inter = (p[0] + (nx / mod * margem), p[1] + (ny / mod * margem))
            saida.append((round(inter[0], 6), round(inter[1], 6)))
        if saida and self._dist(saida[0], saida[-1]) > 1e-6:
            saida.append(saida[0])
        return saida

    @staticmethod
    def _intersecao_linhas(a1, a2, b1, b2) -> tuple[float, float] | None:
        x1, y1 = a1
        x2, y2 = a2
        x3, y3 = b1
        x4, y4 = b2
        den = ((x1 - x2) * (y3 - y4)) - ((y1 - y2) * (x3 - x4))
        if abs(den) <= 1e-9:
            return None
        px = (((x1 * y2) - (y1 * x2)) * (x3 - x4) - (x1 - x2) * ((x3 * y4) - (y3 * x4))) / den
        py = (((x1 * y2) - (y1 * x2)) * (y3 - y4) - (y1 - y2) * ((x3 * y4) - (y3 * x4))) / den
        return px, py

    @staticmethod
    def _area_assinada(pontos: list[tuple[float, float]]) -> float:
        area = 0.0
        for a, b in zip(pontos, pontos[1:] + pontos[:1]):
            area += (a[0] * b[1]) - (b[0] * a[1])
        return area / 2.0

    @staticmethod
    def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt(((a[0] - b[0]) ** 2) + ((a[1] - b[1]) ** 2))

    def _mensagem_pronta(self) -> str:
        return (
            f"Costura pronta: margem {self._fmt(self._margem_cm)} cm. "
            "Passe o mouse para prever, clique aplica. +/- ajusta, Enter aplica na selecao."
        )

    @staticmethod
    def _fmt(valor: float) -> str:
        return f"{valor:.2f}".rstrip("0").rstrip(".")
