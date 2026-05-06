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
    QTableWidget,
    QTableWidgetItem,
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
            QTableWidget {
                background:#ffffff; color:#111111;
                gridline-color:#dddddd; border:1px solid #b9b9b9;
                selection-background-color:#0b84d8;
            }
            QHeaderView::section {
                background:#efefef; color:#111111;
                border:1px solid #c8c8c8; padding:3px;
                font-size:11px;
            }
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
        self.sp_costura.setRange(0.0, 999999.0)
        self.sp_costura.setDecimals(2)
        self.sp_costura.setSingleStep(0.1)
        self.sp_costura.setValue(1.0)
        self.sp_costura.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_costura_fim = QCheckBox("Costura fim (cm)")
        self.sp_costura_fim = QDoubleSpinBox()
        self.sp_costura_fim.setRange(0.0, 999999.0)
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

        self.tabela = QTableWidget(0, 3)
        self.tabela.setHorizontalHeaderLabels(["Pos.", "Costura (cm)", "Acabamento"])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setMinimumHeight(132)
        self.tabela.setColumnWidth(0, 46)
        self.tabela.setColumnWidth(1, 82)
        self.tabela.setColumnWidth(2, 150)
        raiz.addWidget(self.tabela)

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

    def atualizar_tabela_segmentos(self, total: int, segmentos: set[int]) -> None:
        self.tabela.setRowCount(max(0, total))
        for i in range(max(0, total)):
            valores = [
                f"{i + 1}-{(i + 1) % total + 1}",
                Ferramenta._fmt(self.margem()) if i in segmentos else "0",
                self.cmb_acab_ini.currentText() if i in segmentos else "",
            ]
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.tabela.setItem(i, col, item)


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
        self._hover_segmento: tuple[int, int] | None = None
        self._costura_em_andamento = False
        self._costura_finalizada = False
        self._alvo_idx: int | None = None
        self._segmento_inicio: int | None = None
        self._segmentos_selecionados: set[int] = set()
        self._realce_segmentos: list[tuple[QPointF, QPointF]] = []

    def on_activate(self, canvas):
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.atualizar_status(self._mensagem_pronta())

    def on_deactivate(self, canvas):
        self._limpar_estado()
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if self._modo(canvas) == "Selecionar":
            self._atualizar_hover_segmento(canvas, pos)
            if self._costura_em_andamento:
                self._atualizar_composicao_por_hover(canvas)
            else:
                self._atualizar_preview_segmento(canvas)
        else:
            idx = self._indice_alvo(canvas, pos)
            self._preview_idx = idx
            self._hover_segmento = None
            self._realce_segmentos = []
            self._preview = []
            if idx is not None:
                pontos = self._pontos_fechados(canvas.cena.elementos[idx])
                self._preview = [QPointF(x, y) for x, y in self._gerar_costura(pontos, self._margem_cm)]
                self._atualizar_dialog_com_preview(canvas)
                total = self._total_segmentos(canvas, idx)
                self._obter_dialog(canvas).atualizar_tabela_segmentos(total, set(range(total)))
        canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._costura_finalizada:
                self._limpar_estado()
                canvas.set_ferramenta_ativa("selecionar")
                self.set_status("Ferramenta Costura finalizada. Voltando para Selecionar.")
                event.accept()
                return True
            return False
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        if self._modo(canvas) == "Selecionar":
            return self._on_left_selecionar(canvas, event, pos)
        idx = self._indice_alvo(canvas, pos)
        if idx is None:
            self.set_status("Costura: clique em um molde ou contorno fechado.")
            event.accept()
            return True
        if self._aplicar_em_indices(canvas, [idx]):
            canvas._selecionados = {idx}
            self._costura_finalizada = True
            self.set_status(f"Costura criada com margem de {self._fmt(self._margem_cm)} cm. Clique direito encerra.")
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
            if self._costura_em_andamento:
                self._finalizar_costura_segmentos(canvas)
                return True
            indices = [idx for idx in sorted(getattr(canvas, "_selecionados", set())) if self._elemento_valido(canvas, idx)]
            if not indices and self._preview_idx is not None:
                indices = [self._preview_idx]
            if self._aplicar_em_indices(canvas, indices):
                self._costura_finalizada = True
                self.set_status(f"Costura aplicada em {len(indices)} molde(s).")
            else:
                self.set_status("Selecione um molde/contorno fechado ou passe o mouse sobre um alvo.")
            return True
        if tecla == Qt.Key_Escape:
            self._limpar_estado()
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
        if self._realce_segmentos:
            pen_realce = QPen(QColor("#ffe000"), 2.0, Qt.DotLine)
            pen_realce.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_realce)
            for a, b in self._realce_segmentos:
                painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def set_status(self, texto: str):
        for dialog in self._dialog_por_canvas.values():
            if dialog is not None and dialog.isVisible():
                dialog.atualizar_status(texto)

    def _ajustar_margem(self, canvas, delta: float) -> None:
        self._margem_cm = max(0.0, round(self._margem_cm + delta, 2))
        dialog = self._obter_dialog(canvas)
        dialog.sp_costura.blockSignals(True)
        dialog.sp_costura.setValue(self._margem_cm)
        dialog.sp_costura.blockSignals(False)
        self._recalcular_preview(canvas)
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
        self._margem_cm = max(0.0, round(float(valor), 2))
        self._recalcular_preview(canvas)
        self.set_status(self._mensagem_pronta())

    def _recalcular_preview(self, canvas) -> None:
        if self._modo(canvas) == "Selecionar":
            if self._costura_em_andamento:
                self._atualizar_preview_segmentos(canvas)
            else:
                self._atualizar_preview_segmento(canvas)
        elif self._preview_idx is not None and self._elemento_valido(canvas, self._preview_idx):
            pontos = self._pontos_fechados(canvas.cena.elementos[self._preview_idx])
            self._preview = [QPointF(x, y) for x, y in self._gerar_costura(pontos, self._margem_cm)]
            self._atualizar_dialog_com_preview(canvas)
            total = self._total_segmentos(canvas, self._preview_idx)
            self._obter_dialog(canvas).atualizar_tabela_segmentos(total, set(range(total)))
        canvas.update()

    def _atualizar_dialog_com_preview(self, canvas) -> None:
        dialog = self._obter_dialog(canvas)
        dialog.atualizar_trechos(self._preview)

    def _aplicar_dialog(self, canvas) -> None:
        indices = [idx for idx in sorted(getattr(canvas, "_selecionados", set())) if self._elemento_valido(canvas, idx)]
        if not indices and self._preview_idx is not None:
            indices = [self._preview_idx]
        if self._costura_em_andamento:
            self._finalizar_costura_segmentos(canvas)
        elif self._aplicar_em_indices(canvas, indices):
            self._costura_finalizada = True
            self.set_status(f"Costura aplicada em {len(indices)} molde(s).")
        else:
            self.set_status("Selecione um molde/contorno fechado ou passe o mouse sobre um alvo.")

    def _on_left_selecionar(self, canvas, event, pos: QPointF) -> bool:
        self._atualizar_hover_segmento(canvas, pos)
        if self._costura_em_andamento:
            self._finalizar_costura_segmentos(canvas)
            event.accept()
            return True
        if self._hover_segmento is None:
            self.set_status("Costura: passe o mouse sobre uma linha do molde e clique para iniciar.")
            event.accept()
            return True
        idx, seg_idx = self._hover_segmento
        self._alvo_idx = idx
        self._segmento_inicio = seg_idx
        self._segmentos_selecionados = {seg_idx}
        self._costura_em_andamento = True
        self._costura_finalizada = False
        self._atualizar_preview_segmentos(canvas)
        self.set_status("Costura iniciada. Mova no sentido horario para acrescentar; anti-horario seleciona todo o molde. Clique esquerdo termina.")
        canvas.update()
        event.accept()
        return True

    def _modo(self, canvas) -> str:
        return self._obter_dialog(canvas).cmb_posicao.currentText()

    def _atualizar_hover_segmento(self, canvas, pos: QPointF) -> None:
        melhor = None
        tolerancia = 9.0 / max(float(getattr(canvas, "zoom", 1.0)), 1e-6)
        for idx, el in enumerate(canvas.cena.elementos):
            pontos = [QPointF(x, y) for x, y in self._pontos_fechados(el)]
            if len(pontos) < 4:
                continue
            base = pontos[:-1] if pontos[0] == pontos[-1] else pontos
            for seg_idx, (a, b) in enumerate(zip(base, base[1:] + base[:1])):
                dist = self._distancia_ponto_segmento(a, b, pos)
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, seg_idx, a, b)
        if melhor is None:
            self._hover_segmento = None
            self._realce_segmentos = []
            return
        _, idx, seg_idx, a, b = melhor
        self._hover_segmento = (idx, seg_idx)
        self._realce_segmentos = [(a, b)]

    def _atualizar_preview_segmento(self, canvas) -> None:
        self._preview = []
        self._preview_idx = None
        if self._hover_segmento is None:
            return
        idx, seg_idx = self._hover_segmento
        if not self._elemento_valido(canvas, idx):
            return
        self._preview_idx = idx
        self._preview = [QPointF(x, y) for x, y in self._gerar_costura_segmentos(
            self._pontos_fechados(canvas.cena.elementos[idx]),
            {seg_idx},
            self._margem_cm,
        )]
        self._obter_dialog(canvas).atualizar_tabela_segmentos(self._total_segmentos(canvas, idx), {seg_idx})

    def _atualizar_composicao_por_hover(self, canvas) -> None:
        if self._hover_segmento is None or self._alvo_idx is None or self._segmento_inicio is None:
            return
        idx, seg_idx = self._hover_segmento
        if idx != self._alvo_idx:
            return
        total = self._total_segmentos(canvas, idx)
        if total <= 0:
            return
        frente = self._distancia_circular(self._segmento_inicio, seg_idx, total)
        tras = self._distancia_circular(seg_idx, self._segmento_inicio, total)
        if tras < frente:
            self._segmentos_selecionados = set(range(total))
        else:
            self._segmentos_selecionados = {(self._segmento_inicio + i) % total for i in range(frente + 1)}
        self._atualizar_preview_segmentos(canvas)

    def _atualizar_preview_segmentos(self, canvas) -> None:
        self._preview = []
        self._realce_segmentos = []
        idx = self._alvo_idx
        if idx is None or not self._elemento_valido(canvas, idx):
            return
        pontos = self._pontos_fechados(canvas.cena.elementos[idx])
        self._preview = [QPointF(x, y) for x, y in self._gerar_costura_segmentos(
            pontos,
            self._segmentos_selecionados,
            self._margem_cm,
        )]
        base = [QPointF(x, y) for x, y in pontos[:-1]]
        total = len(base)
        for seg_idx in sorted(self._segmentos_selecionados):
            if 0 <= seg_idx < total:
                self._realce_segmentos.append((base[seg_idx], base[(seg_idx + 1) % total]))
        self._obter_dialog(canvas).atualizar_tabela_segmentos(total, set(self._segmentos_selecionados))

    def _finalizar_costura_segmentos(self, canvas) -> bool:
        if self._alvo_idx is None or not self._segmentos_selecionados:
            self.set_status("Nenhuma linha selecionada para costura.")
            return False
        if self._aplicar_segmentos(canvas, self._alvo_idx, self._segmentos_selecionados):
            self._costura_em_andamento = False
            self._costura_finalizada = True
            self._segmento_inicio = None
            self._segmentos_selecionados = set()
            self.set_status("Costura finalizada. Clique esquerdo em outra linha para continuar ou clique direito para encerrar.")
            canvas.update()
            return True
        self.set_status("Nao foi possivel aplicar costura nesses segmentos.")
        return False

    def _aplicar_segmentos(self, canvas, idx: int, segmentos: set[int]) -> bool:
        if not self._elemento_valido(canvas, idx):
            return False
        alvo = canvas.cena.elementos[idx]
        pontos = self._pontos_fechados(alvo)
        costura = self._gerar_costura_segmentos(pontos, segmentos, self._margem_cm)
        if len(costura) < 2:
            return False
        molde_id = str(alvo.get("molde_id") or alvo.get("id") or "")
        if not molde_id:
            molde_id = str(uuid4())
            alvo["molde_id"] = molde_id
        el = self._elemento_costura(canvas, costura, alvo, molde_id)
        el["costura_segmentos"] = sorted(int(s) for s in segmentos)
        el["costura_parcial"] = len(segmentos) < self._total_segmentos(canvas, idx)
        canvas.cena.elementos.append(el)
        canvas._registrar_historico()
        canvas.update()
        return True

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
            "cor": str(alvo.get("cor") or "#ff5a00"),
            "espessura": 0.9,
            "estilo": "dash",
            "subtipo_audaces": "costura",
            "parte_do_molde": True,
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

    def _limpar_estado(self) -> None:
        self._preview = []
        self._preview_idx = None
        self._hover_segmento = None
        self._costura_em_andamento = False
        self._costura_finalizada = False
        self._alvo_idx = None
        self._segmento_inicio = None
        self._segmentos_selecionados = set()
        self._realce_segmentos = []

    def _total_segmentos(self, canvas, idx: int) -> int:
        if not self._elemento_valido(canvas, idx):
            return 0
        pontos = self._pontos_fechados(canvas.cena.elementos[idx])
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else pontos
        return len(base)

    @staticmethod
    def _distancia_circular(inicio: int, fim: int, total: int) -> int:
        if total <= 0:
            return 0
        return (fim - inicio) % total

    def _gerar_costura_segmentos(
        self,
        pontos: list[tuple[float, float]],
        segmentos: set[int],
        margem: float,
    ) -> list[tuple[float, float]]:
        base = pontos[:-1] if pontos and self._dist(pontos[0], pontos[-1]) <= 1e-6 else list(pontos)
        total = len(base)
        if total < 3 or not segmentos:
            return []
        segmentos = {s % total for s in segmentos}
        if len(segmentos) >= total:
            return self._gerar_costura(pontos, margem)
        costura_total = self._gerar_costura(pontos, margem)
        if len(costura_total) < total + 1:
            return []
        ordenados = sorted(segmentos)
        grupos: list[list[int]] = []
        grupo = [ordenados[0]]
        for seg_idx in ordenados[1:]:
            if seg_idx == grupo[-1] + 1:
                grupo.append(seg_idx)
            else:
                grupos.append(grupo)
                grupo = [seg_idx]
        grupos.append(grupo)
        if len(grupos) > 1 and grupos[0][0] == 0 and grupos[-1][-1] == total - 1:
            grupos[0] = grupos[-1] + grupos[0]
            grupos.pop()

        saida: list[tuple[float, float]] = []
        for grupo in grupos:
            for pos, seg_idx in enumerate(grupo):
                if not saida or pos == 0:
                    saida.append(costura_total[seg_idx])
                saida.append(costura_total[(seg_idx + 1) % total])
            if len(grupos) > 1:
                saida.append(saida[-1])
        return saida

    @staticmethod
    def _distancia_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-9:
            return sqrt(((p.x() - a.x()) ** 2) + ((p.y() - a.y()) ** 2))
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return sqrt(((p.x() - proj.x()) ** 2) + ((p.y() - proj.y()) ** 2))

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
