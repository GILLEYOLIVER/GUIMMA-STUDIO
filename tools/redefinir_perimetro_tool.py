from __future__ import annotations

from copy import deepcopy
from math import sqrt

from PySide6.QtCore import QPointF, QSignalBlocker, Qt
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from core.formatacao import numero_decimal_ponto
from tools.medicao_utils import selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase
from tools.unidades import SUFIXOS_MEDIDA, unidade_canvas, valor_unidade_para_cena
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class RedefinirPerimetroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Redefinir perímetro")
        self._unidade_sigla = "cm"
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(255)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel { color:#111111; }
            QComboBox, QLineEdit {
                background:#ffffff; color:#111111;
                border:1px solid #b5bcc3; min-height:22px;
            }
            QPushButton {
                background:#f7f7f7; color:#111111;
                border:1px solid #b7bec5; min-height:22px;
            }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        form = QFormLayout()
        self.cmb_modo = QComboBox()
        self.cmb_modo.setObjectName("modo")
        self.cmb_modo.addItems(["Manter extremos", "Uni-direcional", "Bi-direcional"])
        self.ed_de = QLineEdit("0")
        self.ed_de.setObjectName("de")
        self.ed_de.setReadOnly(True)
        self.ed_para = QLineEdit("0")
        self.ed_para.setObjectName("para")
        self.lbl_de = QLabel("De (cm)")
        self.lbl_para = QLabel("Para (cm)")
        form.addRow("Modo", self.cmb_modo)
        form.addRow(self.lbl_de, self.ed_de)
        form.addRow(self.lbl_para, self.ed_para)
        lay.addLayout(form)
        rod = QHBoxLayout()
        self.btn_aplicar = QPushButton("Aplicar")
        rod.addStretch(1)
        rod.addWidget(self.btn_aplicar)
        lay.addLayout(rod)

    def set_unidade(self, sigla: str) -> None:
        self._unidade_sigla = str(sigla or "cm")
        self.lbl_de.setText(f"De ({self._unidade_sigla})")
        self.lbl_para.setText(f"Para ({self._unidade_sigla})")
        self.ed_de.setPlaceholderText(self._unidade_sigla)
        self.ed_para.setPlaceholderText(self._unidade_sigla)


class Ferramenta(FerramentaBase):
    id_ferramenta = "redefinir_perimetro"
    nome = "Redefinir Perimetro"
    usa_painel_auxiliar = False

    _dialog_por_canvas: dict[int, RedefinirPerimetroDialog] = {}
    _idx_por_canvas: dict[int, int] = {}
    _preview_ativo_por_canvas: dict[int, bool] = {}
    _snapshot_por_canvas: dict[int, dict] = {}
    _segmentos_iguais_por_canvas: dict[int, list[tuple[QPointF, QPointF]]] = {}
    _segmento_alvo_por_canvas: dict[int, dict] = {}
    _segmentos_originais_afetados_por_canvas: dict[int, list[tuple[QPointF, QPointF]]] = {}
    _confirmacao_pendente_por_canvas: dict[int, bool] = {}
    _elemento_preview_por_canvas: dict[int, dict] = {}
    _selecionados_snapshot_por_canvas: dict[int, set[int]] = {}

    def on_activate(self, canvas):
        chave = id(canvas)
        self._idx_por_canvas.pop(chave, None)
        self._preview_ativo_por_canvas.pop(chave, None)
        self._snapshot_por_canvas.pop(chave, None)
        self._segmentos_iguais_por_canvas.pop(chave, None)
        self._segmento_alvo_por_canvas.pop(chave, None)
        self._segmentos_originais_afetados_por_canvas.pop(chave, None)
        self._confirmacao_pendente_por_canvas.pop(chave, None)
        self._elemento_preview_por_canvas.pop(chave, None)
        self._selecionados_snapshot_por_canvas.pop(chave, None)
        dialog = self._obter_dialog(canvas)
        with QSignalBlocker(dialog.ed_de), QSignalBlocker(dialog.ed_para):
            dialog.ed_de.setText("0")
            dialog.ed_para.setText("0")
        dialog.adjustSize()
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        restaurar_posicao(dialog, "dialog:redefinir_perimetro", fallback=fallback)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        with QSignalBlocker(dialog.ed_de), QSignalBlocker(dialog.ed_para):
            dialog.ed_de.setText("0")
            dialog.ed_para.setText("0")
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText("Redefinir perímetro: clique em um contorno para carregar o valor atual.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._preview_ativo_por_canvas.pop(id(canvas), None)
        self._snapshot_por_canvas.pop(id(canvas), None)
        self._idx_por_canvas.pop(id(canvas), None)
        self._segmentos_iguais_por_canvas.pop(id(canvas), None)
        self._segmento_alvo_por_canvas.pop(id(canvas), None)
        self._segmentos_originais_afetados_por_canvas.pop(id(canvas), None)
        self._confirmacao_pendente_por_canvas.pop(id(canvas), None)
        self._elemento_preview_por_canvas.pop(id(canvas), None)
        self._selecionados_snapshot_por_canvas.pop(id(canvas), None)

    def on_mouse_press(self, canvas, event) -> bool:
        chave = id(canvas)
        if event.button() == Qt.RightButton:
            if self._preview_ativo_por_canvas.get(chave):
                self._cancelar_preview(canvas)
                if getattr(canvas, "lbl_status", None) is not None:
                    canvas.lbl_status.setText("Redefinição cancelada. Clique em uma linha para recomeçar; outro direito sai.")
            else:
                self._fechar(canvas)
            canvas.update()
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        if self._preview_ativo_por_canvas.get(chave):
            idx = self._idx_por_canvas.get(chave)
            preview = self._elemento_preview_por_canvas.get(chave)
            if idx is not None and preview is not None and 0 <= idx < len(canvas.cena.elementos):
                canvas.cena.elementos[idx] = deepcopy(preview)
            canvas._registrar_historico()
            self._preview_ativo_por_canvas[chave] = False
            self._idx_por_canvas.pop(chave, None)
            self._snapshot_por_canvas.pop(chave, None)
            self._segmentos_iguais_por_canvas.pop(chave, None)
            self._segmento_alvo_por_canvas.pop(chave, None)
            self._segmentos_originais_afetados_por_canvas.pop(chave, None)
            self._confirmacao_pendente_por_canvas.pop(chave, None)
            self._elemento_preview_por_canvas.pop(chave, None)
            self._selecionados_snapshot_por_canvas.pop(chave, None)
            self._limpar_selecao_fantasma(canvas, idx)
            canvas.update()
            if getattr(canvas, "lbl_status", None) is not None:
                canvas.lbl_status.setText("Redefinição de perímetro aplicada.")
            event.accept()
            return True
        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if info is None:
            return True
        idx = int(info["elemento_idx"])
        alvo_segmento = self._segmento_alvo_para_posicao(canvas, idx, pos)
        if alvo_segmento is None:
            return True
        self._idx_por_canvas[id(canvas)] = idx
        self._segmento_alvo_por_canvas[chave] = alvo_segmento
        per = float(alvo_segmento.get("comprimento", 0.0))
        dialog = self._obter_dialog(canvas)
        dialog.ed_de.setText(canvas.formatar_valor_unidade(per))
        self._snapshot_por_canvas[chave] = deepcopy(canvas.cena.elementos[idx])
        self._selecionados_snapshot_por_canvas[chave] = set(getattr(canvas, "_selecionados", set()) or set())
        self._preview_ativo_por_canvas[chave] = True
        self._aplicar_preview(canvas)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText("Prévia azul pronta. Clique esquerdo aplica; botão direito cancela.")
        canvas.update()
        event.accept()
        return True

    def _cancelar_preview(self, canvas) -> None:
        chave = id(canvas)
        idx = self._idx_por_canvas.get(chave)
        snapshot = self._snapshot_por_canvas.get(chave)
        if snapshot is not None and idx is not None and 0 <= idx < len(canvas.cena.elementos):
            canvas.cena.elementos[idx] = deepcopy(snapshot)
        self._preview_ativo_por_canvas.pop(chave, None)
        self._idx_por_canvas.pop(chave, None)
        self._snapshot_por_canvas.pop(chave, None)
        self._segmentos_iguais_por_canvas.pop(chave, None)
        self._segmento_alvo_por_canvas.pop(chave, None)
        self._segmentos_originais_afetados_por_canvas.pop(chave, None)
        self._confirmacao_pendente_por_canvas.pop(chave, None)
        self._elemento_preview_por_canvas.pop(chave, None)
        selecionados_snapshot = self._selecionados_snapshot_por_canvas.pop(chave, None)
        if selecionados_snapshot is not None and hasattr(canvas, "_selecionados"):
            canvas._selecionados = set(selecionados_snapshot)
        dialog = self._obter_dialog(canvas)
        with QSignalBlocker(dialog.ed_de), QSignalBlocker(dialog.ed_para):
            dialog.ed_de.setText("0")
            dialog.ed_para.setText("0")
        canvas.update()

    def _fechar(self, canvas) -> None:
        self._cancelar_preview(canvas)
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText("Ferramenta Redefinir perímetro finalizada. Voltando para Selecionar.")

    def _obter_dialog(self, canvas) -> RedefinirPerimetroDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = RedefinirPerimetroDialog(parent)
            instalar_memoria_posicao(dialog, "dialog:redefinir_perimetro")
            self._dialog_por_canvas[chave] = dialog
        dialog.set_unidade(unidade_canvas(canvas)[0])
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.btn_aplicar.clicked.connect(lambda: self._aplicar(canvas))
            dialog.ed_para.returnPressed.connect(lambda: self._aplicar(canvas))
            dialog.ed_para.textChanged.connect(lambda _txt: self._aplicar_preview(canvas))
            dialog.ed_para.editingFinished.connect(lambda: self._aplicar_preview(canvas))
            dialog.cmb_modo.currentTextChanged.connect(lambda _txt: self._aplicar_preview(canvas))
        return dialog

    def on_unidade_medida_alterada(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.set_unidade(unidade_canvas(canvas)[0])

    def _aplicar(self, canvas):
        if self._segmento_alvo_por_canvas.get(id(canvas)) is None:
            return
        self._aplicar_preview(canvas)
        if self._segmento_alvo_por_canvas.get(id(canvas)) is not None:
            self._preview_ativo_por_canvas[id(canvas)] = True

    def _aplicar_preview(self, canvas):
        chave = id(canvas)
        idx = self._idx_por_canvas.get(chave)
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        snapshot = self._snapshot_por_canvas.get(chave)
        if not snapshot:
            self._snapshot_por_canvas[chave] = deepcopy(canvas.cena.elementos[idx])
            snapshot = self._snapshot_por_canvas[chave]
        alvo_segmento = self._segmento_alvo_por_canvas.get(chave)
        if alvo_segmento is None:
            return
        dialog = self._obter_dialog(canvas)
        alvo_u = numero_decimal_ponto(dialog.ed_para.text(), 0.0, SUFIXOS_MEDIDA)
        alvo = valor_unidade_para_cena(canvas, alvo_u)
        atual = float(alvo_segmento.get("comprimento", 0.0))
        if atual <= 1e-9:
            return
        if alvo <= 1e-9:
            alvo = atual
        modo = dialog.cmb_modo.currentText().strip().lower()
        el = deepcopy(snapshot)
        segmento_preview: tuple[QPointF, QPointF] | None = None
        if el.get("tipo") == "polyline":
            segmento_preview = self._aplicar_preview_segmento_polyline(canvas, el, alvo_segmento, alvo, modo)
        if segmento_preview is None:
            return
        self._invalidar_metadados_visuais_molde(el)
        self._elemento_preview_por_canvas[chave] = el
        canvas.cena.elementos[idx] = deepcopy(el)
        afetados = self._segmentos_originais_afetados(snapshot, el)
        if not afetados:
            afetados = [(QPointF(alvo_segmento["a"]), QPointF(alvo_segmento["b"]))]
        self._segmentos_originais_afetados_por_canvas[chave] = afetados
        self._segmentos_iguais_por_canvas[chave] = [segmento_preview]
        self._confirmacao_pendente_por_canvas[chave] = False
        canvas.update()
        if getattr(canvas, "lbl_status", None) is not None:
            novo_per = canvas.formatar_valor_unidade(self._dist(segmento_preview[0], segmento_preview[1]))
            canvas.lbl_status.setText(f"Prévia linha: {novo_per} ({getattr(canvas, '_unidade_sigla', 'cm')}) | clique esquerdo aplica")

    def _garantir_preview_visivel(self, canvas) -> bool:
        chave = id(canvas)
        if not self._preview_ativo_por_canvas.get(chave):
            return False
        idx = self._idx_por_canvas.get(chave)
        preview = self._elemento_preview_por_canvas.get(chave)
        if idx is None or preview is None or not (0 <= idx < len(canvas.cena.elementos)):
            self._aplicar_preview(canvas)
            idx = self._idx_por_canvas.get(chave)
            preview = self._elemento_preview_por_canvas.get(chave)
        if idx is None or preview is None or not (0 <= idx < len(canvas.cena.elementos)):
            return False
        if canvas.cena.elementos[idx] != preview:
            canvas.cena.elementos[idx] = deepcopy(preview)
        if not self._segmentos_iguais_por_canvas.get(chave):
            self._aplicar_preview(canvas)
        return bool(self._segmentos_iguais_por_canvas.get(chave))

    def _invalidar_metadados_visuais_molde(self, el: dict) -> None:
        for chave in (
            "contornos_dobra_original",
            "estado_dobra",
            "dobra_eixo",
            "molde_dobrado",
            "mostrar_contorno_dobra_original",
            "contorno_original",
            "contorno_dobrado",
            "contorno_lado_original",
            "contorno_lado_dobrado",
            "contorno_lado_oculto",
            "contorno_pontilhado",
            "pontos_restauracao",
            "pontos_de_restauracao",
            "_pontos_restauracao",
        ):
            el.pop(chave, None)

    def _limpar_selecao_fantasma(self, canvas, idx_atual: int | None) -> None:
        if hasattr(canvas, "_selecionados"):
            if idx_atual is not None and 0 <= idx_atual < len(canvas.cena.elementos):
                canvas._selecionados = {idx_atual}
            else:
                canvas._selecionados = set()
        for nome in ("_marcacoes_temporarias", "_piscando_ponto_restauracao_indices"):
            valor = getattr(canvas, nome, None)
            if hasattr(valor, "clear"):
                valor.clear()
        if hasattr(canvas, "_piscando_ponto_restauracao_visivel"):
            canvas._piscando_ponto_restauracao_visivel = False

    def _segmento_alvo_para_posicao(self, canvas, idx: int, pos: QPointF) -> dict | None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return None
        if el.get("molde"):
            alvo = self._segmento_controle_molde_mais_proximo(canvas, el, pos)
            if alvo is not None:
                return alvo
        pontos = [self._ponto_qt(p) for p in el.get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        melhor = None
        melhor_dist = float("inf")
        for p_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
            dist = self._dist_ponto_segmento(pos, a, b)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor = {
                    "tipo": "pontos",
                    "ponto_idx": p_idx,
                    "a": QPointF(a),
                    "b": QPointF(b),
                    "comprimento": self._dist(a, b),
                    "clique_t": self._parametro_segmento(pos, a, b),
                }
        return melhor

    def _segmento_controle_molde_mais_proximo(self, canvas, el: dict, pos: QPointF) -> dict | None:
        cantos = [self._ponto_qt(p) for p in el.get("controle_cantos", []) or []]
        cantos = [p for p in cantos if p is not None]
        if len(cantos) < 2:
            return None
        fechado = self._molde_fechado(canvas, el, cantos)
        limite = len(cantos) if fechado else len(cantos) - 1
        melhor = None
        melhor_dist = float("inf")
        for a_idx in range(max(limite, 0)):
            b_idx = (a_idx + 1) % len(cantos)
            if not fechado and b_idx <= a_idx:
                continue
            a = cantos[a_idx]
            b = cantos[b_idx]
            dist = self._dist_ponto_segmento(pos, a, b)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor = {
                    "tipo": "controle_molde",
                    "a_idx": a_idx,
                    "b_idx": b_idx,
                    "a": QPointF(a),
                    "b": QPointF(b),
                    "comprimento": self._dist(a, b),
                    "clique_t": self._parametro_segmento(pos, a, b),
                }
        return melhor

    def _aplicar_preview_segmento_polyline(self, canvas, el: dict, alvo_segmento: dict, tamanho: float, modo: str) -> tuple[QPointF, QPointF] | None:
        a = alvo_segmento.get("a")
        b = alvo_segmento.get("b")
        if not isinstance(a, QPointF) or not isinstance(b, QPointF):
            return None
        comprimento = self._dist(a, b)
        if comprimento <= 1e-9:
            return None
        ux = (b.x() - a.x()) / comprimento
        uy = (b.y() - a.y()) / comprimento
        delta = float(tamanho) - comprimento
        if "bi" in modo:
            delta_a = QPointF(-(ux * delta) / 2.0, -(uy * delta) / 2.0)
            delta_b = QPointF((ux * delta) / 2.0, (uy * delta) / 2.0)
        elif "uni" in modo:
            clique_t = float(alvo_segmento.get("clique_t", 0.5))
            if clique_t <= 0.5:
                # No unidirecional a base fica no ponto mais distante do clique.
                novo_a_tmp = QPointF(b.x() - (ux * float(tamanho)), b.y() - (uy * float(tamanho)))
                delta_a = QPointF(novo_a_tmp.x() - a.x(), novo_a_tmp.y() - a.y())
                delta_b = QPointF(0.0, 0.0)
            else:
                delta_a = QPointF(0.0, 0.0)
                delta_b = QPointF(ux * delta, uy * delta)
        else:
            delta_a = QPointF(0.0, 0.0)
            delta_b = QPointF(ux * delta, uy * delta)
        novo_a = QPointF(a.x() + delta_a.x(), a.y() + delta_a.y())
        novo_b = QPointF(b.x() + delta_b.x(), b.y() + delta_b.y())
        if alvo_segmento.get("tipo") == "controle_molde":
            self._aplicar_segmento_controle_molde(el, alvo_segmento, a, b, novo_a, novo_b, delta_a, delta_b)
        else:
            self._aplicar_segmento_pontos(el, alvo_segmento, a, b, novo_a, novo_b)
        return novo_a, novo_b

    def _aplicar_segmento_controle_molde(
        self,
        el: dict,
        alvo_segmento: dict,
        a: QPointF,
        b: QPointF,
        novo_a: QPointF,
        novo_b: QPointF,
        delta_a: QPointF,
        delta_b: QPointF,
    ) -> None:
        a_idx = int(alvo_segmento.get("a_idx", -1))
        b_idx = int(alvo_segmento.get("b_idx", -1))
        cantos = list(el.get("controle_cantos", []) or [])
        if 0 <= a_idx < len(cantos):
            cantos[a_idx] = (novo_a.x(), novo_a.y())
        if 0 <= b_idx < len(cantos):
            cantos[b_idx] = (novo_b.x(), novo_b.y())
        el["controle_cantos"] = cantos
        self._atualizar_lista_ponto(el, "pontos_controle_principais", a_idx, novo_a)
        self._atualizar_lista_ponto(el, "pontos_controle_principais", b_idx, novo_b)

        pontos = list(el.get("pontos", []) or [])
        fechado = len(pontos) >= 2 and self._pontos_mesmos(pontos[0], pontos[-1])
        novos_pontos = [self._remapear_ponto_segmento(p, a, b, novo_a, novo_b, delta_a, delta_b) for p in pontos]
        if fechado and novos_pontos:
            novos_pontos[-1] = novos_pontos[0]
        el["pontos"] = novos_pontos

        self._sincronizar_auxiliares_molde(el)

    def _aplicar_segmento_pontos(self, el: dict, alvo_segmento: dict, a: QPointF, b: QPointF, novo_a: QPointF, novo_b: QPointF) -> None:
        p_idx = int(alvo_segmento.get("ponto_idx", -1))
        pontos = list(el.get("pontos", []) or [])
        if not (0 <= p_idx < len(pontos) - 1):
            return
        pontos[p_idx] = (novo_a.x(), novo_a.y())
        pontos[p_idx + 1] = (novo_b.x(), novo_b.y())
        if len(pontos) >= 2 and self._pontos_mesmos(pontos[0], pontos[-1]):
            pontos[-1] = pontos[0]
        el["pontos"] = pontos

    def _sincronizar_auxiliares_molde(self, el: dict) -> None:
        cantos = [self._ponto_qt(item) for item in el.get("controle_cantos", []) or []]
        cantos = [p for p in cantos if p is not None]
        if len(cantos) < 2:
            return
        fechado = bool(el.get("fechado")) or len(cantos) >= 3
        limite = len(cantos) if fechado else len(cantos) - 1
        auxiliares: list[tuple[float, float]] = []
        for idx in range(max(limite, 0)):
            proximo_idx = (idx + 1) % len(cantos)
            if not fechado and proximo_idx <= idx:
                continue
            atual = cantos[idx]
            proximo = cantos[proximo_idx]
            auxiliares.append(((atual.x() + proximo.x()) / 2.0, (atual.y() + proximo.y()) / 2.0))
        el["controle_auxiliares"] = auxiliares
        el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]
        el["pontos_controle_principais"] = [{"x": float(p.x()), "y": float(p.y())} for p in cantos]

    def _remapear_ponto_segmento(self, item, a: QPointF, b: QPointF, novo_a: QPointF, novo_b: QPointF, delta_a: QPointF, delta_b: QPointF):
        pt = self._ponto_qt(item)
        if pt is None:
            return item
        tol = 1e-4
        if self._dist(pt, a) <= tol:
            return (novo_a.x(), novo_a.y())
        if self._dist(pt, b) <= tol:
            return (novo_b.x(), novo_b.y())
        if self._dist_ponto_segmento(pt, a, b) <= tol:
            t = self._parametro_segmento(pt, a, b)
            x = novo_a.x() + ((novo_b.x() - novo_a.x()) * t)
            y = novo_a.y() + ((novo_b.y() - novo_a.y()) * t)
            return (x, y)
        return item

    def _atualizar_lista_ponto(self, el: dict, chave: str, idx: int, ponto: QPointF) -> None:
        itens = el.get(chave)
        if not isinstance(itens, list) or not (0 <= idx < len(itens)):
            return
        if isinstance(itens[idx], dict):
            novo = dict(itens[idx])
            novo["x"] = float(ponto.x())
            novo["y"] = float(ponto.y())
            itens[idx] = novo
        else:
            itens[idx] = (float(ponto.x()), float(ponto.y()))

    def _molde_fechado(self, canvas, el: dict, cantos: list[QPointF]) -> bool:
        if bool(el.get("fechado")) or len(cantos) >= 3:
            return True
        pontos = el.get("pontos", []) or []
        return len(pontos) >= 2 and self._pontos_mesmos(pontos[0], pontos[-1])

    def _ponto_qt(self, item) -> QPointF | None:
        try:
            if isinstance(item, dict):
                return QPointF(float(item.get("x", 0.0)), float(item.get("y", 0.0)))
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                return QPointF(float(item[0]), float(item[1]))
        except Exception:
            return None
        return None

    def _pontos_mesmos(self, a, b) -> bool:
        pa = self._ponto_qt(a)
        pb = self._ponto_qt(b)
        if pa is None or pb is None:
            return False
        return self._dist(pa, pb) <= 1e-7

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return sqrt(((b.x() - a.x()) ** 2) + ((b.y() - a.y()) ** 2))

    def _dist_ponto_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        t = self._parametro_segmento(p, a, b)
        proj = QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
        return self._dist(p, proj)

    def _parametro_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return 0.0
        return max(0.0, min(1.0, (((p.x() - a.x()) * abx) + ((p.y() - a.y()) * aby)) / den))

    def _segmentos_originais_afetados(self, original: dict, novo: dict) -> list[tuple[QPointF, QPointF]]:
        segmentos_original = self._segmentos_para_comparacao(original)
        segmentos_novo = self._segmentos_para_comparacao(novo)
        afetados: list[tuple[QPointF, QPointF]] = []
        for (orig_a, orig_b), (novo_a, novo_b) in zip(segmentos_original, segmentos_novo):
            if not self._pontos_qt_mesmos(orig_a, novo_a) or not self._pontos_qt_mesmos(orig_b, novo_b):
                afetados.append((QPointF(orig_a), QPointF(orig_b)))
        return afetados

    def _segmentos_para_comparacao(self, el: dict) -> list[tuple[QPointF, QPointF]]:
        if el.get("molde"):
            cantos = [self._ponto_qt(p) for p in el.get("controle_cantos", []) or []]
            pontos = [p for p in cantos if p is not None]
            if len(pontos) >= 2:
                fechado = bool(el.get("fechado")) or len(pontos) >= 3
                return self._segmentos_de_pontos(pontos, fechado=fechado)
        pontos = [self._ponto_qt(p) for p in el.get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) < 2:
            return []
        fechado = self._pontos_qt_mesmos(pontos[0], pontos[-1])
        return self._segmentos_de_pontos(pontos, fechado=fechado)

    def _segmentos_de_pontos(self, pontos: list[QPointF], fechado: bool) -> list[tuple[QPointF, QPointF]]:
        if len(pontos) < 2:
            return []
        segmentos = [(QPointF(a), QPointF(b)) for a, b in zip(pontos, pontos[1:])]
        if fechado and not self._pontos_qt_mesmos(pontos[0], pontos[-1]):
            segmentos.append((QPointF(pontos[-1]), QPointF(pontos[0])))
        return segmentos

    def _pontos_qt_mesmos(self, a: QPointF, b: QPointF) -> bool:
        return self._dist(a, b) <= 1e-7

    def on_paint_overlay(self, canvas, painter):
        chave = id(canvas)
        self._garantir_preview_visivel(canvas)
        if self._preview_ativo_por_canvas.get(chave):
            for a_original, b_original in self._segmentos_originais_afetados_por_canvas.get(chave, []):
                canvas._desenhar_segmento(painter, a_original, b_original, tracejado=True, cor="#f4f4f4", espessura=1.4)
        segs = self._segmentos_iguais_por_canvas.get(chave, [])
        if not segs:
            return
        for a, b in segs:
            canvas._desenhar_segmento(painter, a, b, tracejado=True, cor="#2da8ff", espessura=2.0)
