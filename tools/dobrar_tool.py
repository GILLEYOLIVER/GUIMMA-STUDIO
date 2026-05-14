from __future__ import annotations

from math import isfinite, sqrt
from time import monotonic

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QVBoxLayout

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class DobrarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:dobrar"
        self.setWindowTitle("Dobrar")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(280)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QComboBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            QCheckBox::indicator {
                width:14px;
                height:14px;
                border:1px solid #6c7480;
                background:#ffffff;
            }
            QCheckBox::indicator:checked {
                background:#0b7fb8;
                border:1px solid #075f8c;
            }
            """
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(6)

        form = QFormLayout()
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Dobrar horizontal", "Dobrar vertical", "Dobrar na linha"])
        form.addRow("Modo", self.cmb_modo)
        raiz.addLayout(form)

        self.chk_manter_dimensoes = QCheckBox("Manter dimensoes originais")
        self.chk_manter_dimensoes.setChecked(False)
        raiz.addWidget(self.chk_manter_dimensoes)


class Ferramenta(FerramentaBase):
    id_ferramenta = "dobrar"
    nome = "Dobrar"
    usa_painel_auxiliar = False
    descricao_painel = "Dobra moldes pelo meio ou por uma linha reta, com preview azul."

    _dialog_por_canvas: dict[int, DobrarDialog] = {}

    def __init__(self):
        super().__init__()
        self._lado_preview = 0
        self._preview_pos: QPointF | None = None
        self._linha_p1: QPointF | None = None
        self._linha_p2: QPointF | None = None
        self._ultimo_direito = 0.0

    def on_activate(self, canvas):
        self._resetar_operacao()
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Dobrar: clique em um molde. Shift soma moldes. Mova para o lado da dobra e clique para aplicar.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._resetar_operacao()
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            agora = monotonic()
            if agora - self._ultimo_direito <= 0.45:
                self._fechar(canvas)
            else:
                self._status(canvas, "Clique direito novamente para finalizar Dobrar.")
            self._ultimo_direito = agora
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        self._preview_pos = QPointF(pos)
        dialog = self._obter_dialog(canvas)
        modo = dialog.cmb_modo.currentText()
        if modo == "Dobrar na linha":
            return self._clique_modo_linha(canvas, event, pos)
        return self._clique_modo_meio(canvas, event, pos, modo)

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._preview_pos = QPointF(pos)
        self._lado_preview = self._calcular_lado_preview(canvas, QPointF(pos))
        canvas.update()
        return bool(self._indices_moldes(canvas))

    def on_paint_overlay(self, canvas, painter):
        indices = self._indices_moldes(canvas)
        if not indices:
            return
        dialog = self._obter_dialog(canvas)
        modo = dialog.cmb_modo.currentText()
        if modo == "Dobrar na linha" and self._linha_p1 is not None and self._linha_p2 is None and self._preview_pos is not None:
            painter.save()
            cor_linha = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
            painter.setPen(QPen(cor_linha, 1.4, Qt.DashLine))
            painter.drawLine(canvas._cena_para_tela(self._linha_p1), canvas._cena_para_tela(self._preview_pos))
            painter.restore()
            return
        eixo = self._eixo(canvas, indices, modo)
        if eixo is None:
            return

        painter.save()
        cor = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        pen_eixo = QPen(cor, 1.4, Qt.DashLine)
        painter.setPen(pen_eixo)
        if eixo[0] == "line":
            self._desenhar_eixo(canvas, painter, eixo)
        else:
            for idx in indices:
                eixo_el = self._eixo(canvas, [idx], modo)
                if eixo_el is not None:
                    self._desenhar_eixo(canvas, painter, eixo_el)

        if self._lado_preview:
            pen_preview = QPen(cor, 2.0, Qt.SolidLine)
            pen_preview.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen_preview)
            for idx in indices:
                el = canvas.cena.elementos[idx]
                eixo_el = eixo if eixo[0] == "line" else self._eixo(canvas, [idx], modo)
                if eixo_el is None:
                    continue
                pontos = self._pontos_elemento(el)
                if len(pontos) < 2:
                    continue
                pontos_preview = [self._espelhar_ponto(p, eixo_el) if self._lado_ponto(p, eixo_el) == self._lado_preview else QPointF(p) for p in pontos]
                self._desenhar_polilinha_tela(canvas, painter, pontos_preview)
        painter.restore()

    def _clique_modo_meio(self, canvas, event, pos: QPointF, modo: str) -> bool:
        candidato = canvas._indice_molde_em_ponto(pos) if hasattr(canvas, "_indice_molde_em_ponto") else None
        selecionados = self._indices_moldes(canvas)
        shift = bool(event.modifiers() & Qt.ShiftModifier)
        if shift and candidato is not None:
            atual = set(getattr(canvas, "_selecionados", set()) or set())
            atual.add(int(candidato))
            canvas._selecionados = atual
            self._lado_preview = 0
            canvas.update()
            self._status(canvas, "Molde somado. Mova o mouse para escolher o lado da dobra.")
            event.accept()
            return True
        if not selecionados or (candidato is not None and candidato not in selecionados):
            if candidato is None:
                self._status(canvas, "Dobrar: clique sobre um molde para selecionar.")
            else:
                canvas._selecionados = {int(candidato)}
                self._lado_preview = 0
                canvas.update()
                self._status(canvas, "Molde selecionado. Mova para cima/baixo ou esquerda/direita e clique para dobrar.")
            event.accept()
            return True
        self._lado_preview = self._calcular_lado_preview(canvas, pos)
        if not self._lado_preview:
            self._status(canvas, "Mova o mouse para o lado que deseja dobrar antes de aplicar.")
            event.accept()
            return True
        self._aplicar(canvas, modo)
        event.accept()
        return True

    def _clique_modo_linha(self, canvas, event, pos: QPointF) -> bool:
        candidato = canvas._indice_molde_em_ponto(pos) if hasattr(canvas, "_indice_molde_em_ponto") else None
        selecionados = self._indices_moldes(canvas)
        shift = bool(event.modifiers() & Qt.ShiftModifier)
        if shift and candidato is not None:
            atual = set(getattr(canvas, "_selecionados", set()) or set())
            atual.add(int(candidato))
            canvas._selecionados = atual
            self._status(canvas, "Molde somado. Clique dois pontos para passar a linha de dobra.")
            canvas.update()
            event.accept()
            return True
        if not selecionados or (candidato is not None and candidato not in selecionados and self._linha_p1 is None):
            if candidato is None:
                self._status(canvas, "Dobrar na linha: selecione um molde primeiro.")
            else:
                canvas._selecionados = {int(candidato)}
                self._resetar_linha()
                self._status(canvas, "Molde selecionado. Clique o primeiro ponto da linha de dobra.")
                canvas.update()
            event.accept()
            return True
        if self._linha_p1 is None:
            self._linha_p1 = QPointF(pos)
            self._status(canvas, "Primeiro ponto marcado. Clique o segundo ponto da linha de dobra.")
            canvas.update()
            event.accept()
            return True
        if self._linha_p2 is None:
            if self._dist(self._linha_p1, pos) <= 1e-6:
                self._status(canvas, "A linha de dobra precisa ter dois pontos diferentes.")
            else:
                self._linha_p2 = QPointF(pos)
                self._status(canvas, "Linha marcada. Mova para um lado da linha e clique para aplicar.")
            canvas.update()
            event.accept()
            return True
        self._lado_preview = self._calcular_lado_preview(canvas, pos)
        if not self._lado_preview:
            self._status(canvas, "Mova o mouse para um dos lados da linha antes de aplicar.")
            event.accept()
            return True
        self._aplicar(canvas, "Dobrar na linha")
        event.accept()
        return True

    def _aplicar(self, canvas, modo: str) -> None:
        indices = self._indices_moldes(canvas)
        eixo = self._eixo(canvas, indices, modo)
        if eixo is None:
            self._status(canvas, "Não foi possível calcular o eixo de dobra.")
            return
        if not self._lado_preview:
            self._status(canvas, "Escolha o lado da dobra com o mouse.")
            return
        dialog = self._obter_dialog(canvas)
        manter = dialog.chk_manter_dimensoes.isChecked()
        afetados = 0
        for idx in indices:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            eixo_el = eixo if eixo[0] == "line" else self._eixo(canvas, [idx], modo)
            if eixo_el is None:
                continue
            el = canvas.cena.elementos[idx]
            original = self._pontos_elemento(el)
            if manter and len(original) >= 2:
                metade = [(p.x(), p.y()) for p in original if self._lado_ponto(p, eixo_el) == self._lado_preview]
                if len(metade) >= 2:
                    el.setdefault("contornos_dobra_original", []).append(metade)
            self._dobrar_elemento(el, eixo_el, self._lado_preview)
            el["molde_dobrado"] = True
            if eixo_el[0] == "h":
                el["dobra_horizontal"] = True
            elif eixo_el[0] == "v":
                el["dobra_vertical"] = True
            el.setdefault("metadados", {})["ultima_transformacao"] = "dobrar"
            afetados += 1
            if hasattr(canvas, "_indices_costuras_vinculadas"):
                for vinculado in canvas._indices_costuras_vinculadas(el):
                    if 0 <= vinculado < len(canvas.cena.elementos):
                        self._dobrar_elemento(canvas.cena.elementos[vinculado], eixo_el, self._lado_preview)
        canvas._selecionados = set(indices)
        canvas._registrar_historico()
        self._resetar_linha()
        self._lado_preview = 0
        canvas.update()
        self._status(canvas, f"Dobra aplicada em {afetados} molde(s). A ferramenta continua ativa; duplo direito finaliza.")

    def _obter_dialog(self, canvas) -> DobrarDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = DobrarDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.cmb_modo.currentTextChanged.connect(lambda _texto, c=canvas: self._modo_alterado(c))
        return dialog

    def _restaurar_dialog(self, canvas, dialog: DobrarDialog) -> None:
        fallback = None
        if hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _modo_alterado(self, canvas):
        self._resetar_linha()
        self._lado_preview = 0
        canvas.update()
        self._status(canvas, "Modo de dobra alterado. Selecione molde(s) e escolha o lado da dobra.")

    def _indices_moldes(self, canvas) -> list[int]:
        return [
            int(i)
            for i in sorted(getattr(canvas, "_selecionados", set()) or [])
            if 0 <= int(i) < len(canvas.cena.elementos) and canvas.cena.elementos[int(i)].get("molde")
        ]

    def _eixo(self, canvas, indices: list[int], modo: str):
        if modo == "Dobrar na linha":
            if self._linha_p1 is None or self._linha_p2 is None:
                return None
            return ("line", QPointF(self._linha_p1), QPointF(self._linha_p2))
        bbox = self._bbox_indices(canvas, indices)
        if bbox is None:
            return None
        min_x, min_y, max_x, max_y = bbox
        if modo == "Dobrar horizontal":
            return ("h", (min_y + max_y) / 2.0)
        return ("v", (min_x + max_x) / 2.0)

    def _calcular_lado_preview(self, canvas, pos: QPointF) -> int:
        indices = self._indices_moldes(canvas)
        if not indices:
            return 0
        eixo = self._eixo(canvas, indices, self._obter_dialog(canvas).cmb_modo.currentText())
        if eixo is None:
            return 0
        valor = self._valor_lado(pos, eixo)
        tolerancia = 4.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        if abs(valor) <= tolerancia:
            return 0
        return 1 if valor > 0 else -1

    def _bbox_indices(self, canvas, indices: list[int]) -> tuple[float, float, float, float] | None:
        pontos: list[QPointF] = []
        for idx in indices:
            pontos.extend(self._pontos_elemento(canvas.cena.elementos[idx]))
        if not pontos:
            return None
        return min(p.x() for p in pontos), min(p.y() for p in pontos), max(p.x() for p in pontos), max(p.y() for p in pontos)

    def _dobrar_elemento(self, el: dict, eixo, lado: int) -> None:
        def conv(p):
            pt = QPointF(float(p[0]), float(p[1]))
            if self._lado_ponto(pt, eixo) == lado:
                pt = self._espelhar_ponto(pt, eixo)
            return (pt.x(), pt.y())

        for chave in (
            "pontos",
            "controle_cantos",
            "controle_auxiliares",
            "pontos_controle_referencia",
            "marcacoes_no_perimetro",
            "distancias_no_perimetro",
            "marcacoes_perimetro",
        ):
            if isinstance(el.get(chave), list):
                el[chave] = [conv(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]
        for chave in ("fio_origem", "fio_fim", "p0", "p1", "p2", "ponto_texto", "nome_posicao", "nome_centro"):
            if self._eh_ponto(el.get(chave)):
                el[chave] = conv(el[chave])
        for chave in ("pontos_controle_principais", "pontos_auxiliares"):
            if isinstance(el.get(chave), list):
                for item in el[chave]:
                    if isinstance(item, dict) and "x" in item and "y" in item:
                        x, y = conv((item["x"], item["y"]))
                        item["x"] = x
                        item["y"] = y

    def _pontos_elemento(self, el: dict) -> list[QPointF]:
        pontos: list[QPointF] = []
        for p in el.get("pontos", []) if isinstance(el.get("pontos"), list) else []:
            if self._eh_ponto(p):
                pontos.append(QPointF(float(p[0]), float(p[1])))
        return pontos

    def _lado_ponto(self, ponto: QPointF, eixo) -> int:
        valor = self._valor_lado(ponto, eixo)
        if abs(valor) <= 1e-9:
            return 0
        return 1 if valor > 0 else -1

    def _valor_lado(self, ponto: QPointF, eixo) -> float:
        if eixo[0] == "h":
            return ponto.y() - float(eixo[1])
        if eixo[0] == "v":
            return ponto.x() - float(eixo[1])
        a: QPointF = eixo[1]
        b: QPointF = eixo[2]
        return ((b.x() - a.x()) * (ponto.y() - a.y())) - ((b.y() - a.y()) * (ponto.x() - a.x()))

    def _espelhar_ponto(self, ponto: QPointF, eixo) -> QPointF:
        if eixo[0] == "h":
            return QPointF(ponto.x(), (2.0 * float(eixo[1])) - ponto.y())
        if eixo[0] == "v":
            return QPointF((2.0 * float(eixo[1])) - ponto.x(), ponto.y())
        a: QPointF = eixo[1]
        b: QPointF = eixo[2]
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        denom = (dx * dx) + (dy * dy)
        if denom <= 1e-12:
            return QPointF(ponto)
        t = (((ponto.x() - a.x()) * dx) + ((ponto.y() - a.y()) * dy)) / denom
        proj = QPointF(a.x() + (t * dx), a.y() + (t * dy))
        return QPointF((2.0 * proj.x()) - ponto.x(), (2.0 * proj.y()) - ponto.y())

    def _desenhar_eixo(self, canvas, painter, eixo) -> None:
        if eixo[0] in {"h", "v"}:
            indices = self._indices_moldes(canvas)
            bbox = self._bbox_indices(canvas, indices)
            if bbox is None:
                return
            min_x, min_y, max_x, max_y = bbox
            margem = max(2.0, 24.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
            if eixo[0] == "h":
                y = float(eixo[1])
                painter.drawLine(canvas._cena_para_tela(QPointF(min_x - margem, y)), canvas._cena_para_tela(QPointF(max_x + margem, y)))
            else:
                x = float(eixo[1])
                painter.drawLine(canvas._cena_para_tela(QPointF(x, min_y - margem)), canvas._cena_para_tela(QPointF(x, max_y + margem)))
            return
        painter.drawLine(canvas._cena_para_tela(eixo[1]), canvas._cena_para_tela(eixo[2]))

    def _desenhar_polilinha_tela(self, canvas, painter, pontos: list[QPointF]) -> None:
        for a, b in zip(pontos, pontos[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))

    def _resetar_operacao(self):
        self._lado_preview = 0
        self._preview_pos = None
        self._resetar_linha()
        self._ultimo_direito = 0.0

    def _resetar_linha(self):
        self._linha_p1 = None
        self._linha_p2 = None

    def _fechar(self, canvas):
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Dobrar finalizada. Voltando para Selecionar.")

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)

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
        return sqrt(((a.x() - b.x()) ** 2) + ((a.y() - b.y()) ** 2))
