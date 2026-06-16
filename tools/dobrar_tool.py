from __future__ import annotations

from math import isfinite, sqrt
from time import monotonic

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QVBoxLayout

from canvas.snap import SnapResult
from core.formatacao import formatar_numero
from config import ICONS_DIR
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
        check_icon = (ICONS_DIR / "check_marcado.svg").as_posix()
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
                image:url(__CHECK_ICON__);
                background:#ffffff;
                border:1px solid #075f8c;
            }
            """
            .replace("__CHECK_ICON__", check_icon)
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(6)

        form = QFormLayout()
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Horizontal", "Vertical", "Elemento"])
        form.addRow("Modo da dobra", self.cmb_modo)
        self.cmb_acao = QComboBox()
        self.cmb_acao.addItems(["Dobrar", "Conferir lados"])
        self.cmb_acao.hide()
        form.addRow("Ação", self.cmb_acao)
        label_acao = form.labelForField(self.cmb_acao)
        if label_acao is not None:
            label_acao.hide()
        raiz.addLayout(form)

        self.chk_manter_dimensoes = QCheckBox("Manter dobra")
        self.chk_manter_dimensoes.setChecked(False)
        raiz.addWidget(self.chk_manter_dimensoes)
        self.chk_mostrar_original = QCheckBox("Mostrar lado original oculto")
        self.chk_mostrar_original.setChecked(True)
        self.chk_mostrar_original.hide()
        raiz.addWidget(self.chk_mostrar_original)
        self.chk_fio_meio = QCheckBox("Sentido do fio no meio do molde")
        self.chk_fio_meio.setChecked(False)
        raiz.addWidget(self.chk_fio_meio)


class Ferramenta(FerramentaBase):
    id_ferramenta = "dobrar"
    nome = "Dobrar"
    usa_painel_auxiliar = False
    descricao_painel = "Dobra moldes como papel: pela reta maior, pelo meio ou por uma linha reta, com original preservado."

    _dialog_por_canvas: dict[int, DobrarDialog] = {}

    def __init__(self):
        super().__init__()
        self._lado_preview = 0
        self._preview_pos: QPointF | None = None
        self._linha_p1: QPointF | None = None
        self._linha_p2: QPointF | None = None
        self._elemento_ref = None
        self._ultimo_direito = 0.0

    def on_activate(self, canvas):
        self._resetar_operacao()
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Dobrar: clique no molde. Shift soma moldes. Mova para escolher o lado que dobra; esquerdo aplica, direito cancela.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        # Ao fechar a ferramenta, limpa apenas guias temporárias da operação.
        # Se o molde permaneceu dobrado, o pontilhado do lado dobrado continua
        # visível até que a ferramenta Desdobrar abra/restaure o contorno.
        self._ocultar_marcacoes_dobra(canvas)
        self._resetar_operacao()
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._confirmacao_pendente(canvas):
                self._cancelar_operacao(canvas)
                event.accept()
                return True
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
        modo_norm = self._modo_normalizado(modo)
        if modo_norm == "linha":
            return self._clique_modo_linha(canvas, event, pos)
        if modo_norm == "elemento":
            return self._clique_modo_elemento(canvas, event, pos)
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
        if self._modo_normalizado(modo) == "linha" and self._linha_p1 is not None and self._linha_p2 is None and self._preview_pos is not None:
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

        self._desenhar_originais_preservados(canvas, painter, indices)

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
                pontos_preview = self._pontos_dobrados_preview(pontos, eixo_el, self._lado_preview, fechado=True)
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
                dialog = self._obter_dialog(canvas)
                if hasattr(dialog, "chk_mostrar_original"):
                    self._mostrar_original_alterado(canvas, dialog.chk_mostrar_original.isChecked())
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
                dialog = self._obter_dialog(canvas)
                if hasattr(dialog, "chk_mostrar_original"):
                    self._mostrar_original_alterado(canvas, dialog.chk_mostrar_original.isChecked())
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
        self._aplicar(canvas, "Linha")
        event.accept()
        return True

    def _clique_modo_elemento(self, canvas, event, pos: QPointF) -> bool:
        candidato = canvas._indice_molde_em_ponto(pos) if hasattr(canvas, "_indice_molde_em_ponto") else None
        selecionados = self._indices_moldes(canvas)
        shift = bool(event.modifiers() & Qt.ShiftModifier)
        if shift and candidato is not None:
            atual = set(getattr(canvas, "_selecionados", set()) or set())
            atual.add(int(candidato))
            canvas._selecionados = atual
            self._elemento_ref = None
            self._lado_preview = 0
            self._status(canvas, "Molde somado. Clique no elemento que serÃ¡ o eixo da dobra.")
            canvas.update()
            event.accept()
            return True
        if not selecionados or (candidato is not None and candidato not in selecionados and self._elemento_ref is None):
            if candidato is None:
                self._status(canvas, "Dobrar por elemento: selecione um molde primeiro.")
            else:
                canvas._selecionados = {int(candidato)}
                self._elemento_ref = None
                self._lado_preview = 0
                dialog = self._obter_dialog(canvas)
                if hasattr(dialog, "chk_mostrar_original"):
                    self._mostrar_original_alterado(canvas, dialog.chk_mostrar_original.isChecked())
                self._status(canvas, "Molde selecionado. Clique na linha ou elemento que serÃ¡ o eixo da dobra.")
                canvas.update()
            event.accept()
            return True

        if self._elemento_ref is None:
            ref = self._elemento_dobra_em_ponto(canvas, selecionados, pos)
            if ref is None:
                self._status(canvas, "Clique sobre uma linha interna, elemento ou trecho do perÃ­metro para usar como eixo.")
            else:
                self._elemento_ref = ref
                self._lado_preview = 0
                self._status(canvas, "Elemento escolhido. Mova para o lado que deseja dobrar e clique para aplicar.")
            canvas.update()
            event.accept()
            return True

        self._lado_preview = self._calcular_lado_preview(canvas, pos)
        if not self._lado_preview:
            self._status(canvas, "Mova o mouse para um dos lados do elemento antes de aplicar.")
            event.accept()
            return True
        self._aplicar(canvas, "Elemento")
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
        if str(getattr(dialog, "cmb_acao", None).currentText() if getattr(dialog, "cmb_acao", None) is not None else "Dobrar").strip().lower().startswith("conferir"):
            self._conferir_lados(canvas, indices, eixo)
            self._resetar_referencias()
            self._lado_preview = 0
            canvas.update()
            return
        preservar_original = dialog.chk_manter_dimensoes.isChecked()
        afetados = 0
        for idx in indices:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            eixo_el = eixo if eixo[0] == "line" else self._eixo(canvas, [idx], modo)
            if eixo_el is None:
                continue
            el = canvas.cena.elementos[idx]
            original = self._pontos_elemento(el)
            original_base = original[:-1] if len(original) > 2 and self._pontos_mesmos(original[0], original[-1]) else list(original)
            lado_movido = -self._lado_preview

            if preservar_original and len(original_base) >= 3:
                metade_original = self._recortar_poligono_lado(original_base, eixo_el, lado_movido)
                if len(metade_original) >= 3:
                    # Guarda DUAS referências diferentes:
                    # 1) metade_movida / contorno_lado_original: posição aberta original, usada para restaurar a assimetria real;
                    # 2) contorno_pontilhado / contorno_lado_dobrado: posição depois da dobra, usada para desenhar
                    #    no canvas onde o lado dobrado ficou. Isso imita o papel real: o pontilhado acompanha a dobra,
                    #    não fica parado mostrando o molde aberto antigo.
                    contorno_lado_original = self._fechar_contorno(metade_original)
                    contorno_lado_dobrado = self._fechar_contorno(
                        [
                            self._espelhar_ponto(p, eixo_el) if self._lado_ponto(p, eixo_el) == lado_movido else QPointF(p)
                            for p in metade_original
                        ]
                    )
                    registro = {
                        "pontos": [(p.x(), p.y()) for p in original],
                        "metade_movida": [(p.x(), p.y()) for p in metade_original],
                        "contorno_lado_original": [(p.x(), p.y()) for p in contorno_lado_original],
                        "contorno_lado_dobrado": [(p.x(), p.y()) for p in contorno_lado_dobrado],
                        # Compatibilidade: o visualizacao.py já procura contorno_pontilhado.
                        # A partir daqui ele representa o lado dobrado, não o lado aberto antigo.
                        "contorno_pontilhado": [(p.x(), p.y()) for p in contorno_lado_dobrado],
                        "eixo": self._serializar_eixo(eixo_el),
                        "lado_destino": int(self._lado_preview),
                    }
                    # Cada nova dobra é um processo novo. Mantemos só a referência
                    # visual/técnica da dobra atual para não deixar pontilhados antigos
                    # presos no canvas depois que o molde for movido ou dobrado de novo.
                    el["contornos_dobra_original"] = [registro]
                    el["estado_dobra"] = {
                        "ativo": True,
                        "eixo": self._serializar_eixo(eixo_el),
                        "lado_destino": int(self._lado_preview),
                        "lado_movido": int(lado_movido),
                        "contorno_original": [(p.x(), p.y()) for p in original],
                        "contorno_lado_original": [(p.x(), p.y()) for p in contorno_lado_original],
                        "contorno_lado_dobrado": [(p.x(), p.y()) for p in contorno_lado_dobrado],
                        # Nome antigo mantido para compatibilidade com versões anteriores do canvas.
                        "contorno_lado_oculto": [(p.x(), p.y()) for p in contorno_lado_dobrado],
                    }
                    mostrar_original = getattr(dialog, "chk_mostrar_original", None)
                    el["mostrar_contorno_dobra_original"] = bool(mostrar_original is None or mostrar_original.isChecked())

            self._dobrar_elemento(el, eixo_el, self._lado_preview)
            pontos_dobrados_el = self._pontos_elemento(el)
            if isinstance(el.get("estado_dobra"), dict):
                el["estado_dobra"]["contorno_dobrado"] = [(p.x(), p.y()) for p in pontos_dobrados_el]
                self._normalizar_registro_visual_dobra(el, pontos_dobrados_el)
            if getattr(dialog, "chk_fio_meio", None) is not None and dialog.chk_fio_meio.isChecked():
                self._centralizar_fio_no_molde(el, eixo_el)
            el["molde_dobrado"] = True
            if eixo_el[0] == "h":
                el["dobra_horizontal"] = True
                el["dobra_vertical"] = False
            elif eixo_el[0] == "v":
                el["dobra_vertical"] = True
                el["dobra_horizontal"] = False
            else:
                el["dobra_horizontal"] = False
                el["dobra_vertical"] = False
            el["dobra_eixo"] = self._serializar_eixo(eixo_el)
            el.setdefault("metadados", {})["ultima_transformacao"] = "dobrar"
            afetados += 1
            if hasattr(canvas, "_indices_costuras_vinculadas"):
                for vinculado in canvas._indices_costuras_vinculadas(el):
                    if 0 <= vinculado < len(canvas.cena.elementos):
                        self._dobrar_elemento(canvas.cena.elementos[vinculado], eixo_el, self._lado_preview)
        canvas._selecionados = set(indices)
        canvas._registrar_historico()
        self._resetar_referencias()
        self._lado_preview = 0
        canvas.update()
        detalhe = "Dobra mantida para desdobrar sem copiar" if preservar_original else "Dobra aplicada sem guardar o lado original"
        self._status(canvas, f"Dobra aplicada em {afetados} molde(s). {detalhe}; duplo direito finaliza.")

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
            if hasattr(dialog, "chk_mostrar_original"):
                dialog.chk_mostrar_original.toggled.connect(
                    lambda marcado, c=canvas: self._mostrar_original_alterado(c, bool(marcado))
                )
        return dialog

    def _restaurar_dialog(self, canvas, dialog: DobrarDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _modo_normalizado(self, modo: str) -> str:
        texto = str(modo or "").strip().lower()
        if "elemento" in texto or "element" in texto:
            return "elemento"
        if "linha" in texto or "line" in texto:
            return "linha"
        if "vertical" in texto:
            return "vertical"
        return "horizontal"

    def _mostrar_original_alterado(self, canvas, marcado: bool) -> None:
        """Liga/desliga imediatamente a referência pontilhada do lado dobrado.

        A marcação pode ter sido escondida ao fechar a ferramenta anterior.
        Quando o usuário volta a marcar a caixa, a visualização precisa aparecer
        na hora para os moldes selecionados, sem exigir nova dobra.
        """
        try:
            for idx in self._indices_moldes(canvas):
                el = canvas.cena.elementos[idx]
                if isinstance(el, dict) and (el.get("contornos_dobra_original") or el.get("estado_dobra")):
                    el["mostrar_contorno_dobra_original"] = bool(marcado)
            canvas.update()
        except Exception:
            pass

    def _modo_alterado(self, canvas):
        self._resetar_referencias()
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
        modo_norm = self._modo_normalizado(modo)
        if modo_norm == "linha":
            if self._linha_p1 is None or self._linha_p2 is None:
                return None
            return ("line", QPointF(self._linha_p1), QPointF(self._linha_p2))
        if modo_norm == "elemento":
            return self._eixo_elemento_ref(canvas, self._elemento_ref)
        bbox = self._bbox_indices(canvas, indices)
        if bbox is None:
            return None
        min_x, min_y, max_x, max_y = bbox
        if modo_norm == "horizontal":
            return ("h", (min_y + max_y) / 2.0)
        return ("v", (min_x + max_x) / 2.0)

    def _ponto_medio_reta_maior(self, canvas, indices: list[int], modo_norm: str) -> QPointF | None:
        melhor = None
        melhor_comprimento = 0.0
        fallback = None
        fallback_comprimento = 0.0
        for idx in indices:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            pontos = self._pontos_elemento(canvas.cena.elementos[idx])
            base = pontos[:-1] if len(pontos) > 2 and self._pontos_mesmos(pontos[0], pontos[-1]) else pontos
            if len(base) < 2:
                continue
            for a, b in zip(base, base[1:] + base[:1]):
                comprimento = self._dist(a, b)
                if comprimento > fallback_comprimento:
                    fallback_comprimento = comprimento
                    fallback = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
                dx = abs(b.x() - a.x())
                dy = abs(b.y() - a.y())
                orientacao_ok = dy >= dx if modo_norm == "horizontal" else dx >= dy
                if orientacao_ok and comprimento > melhor_comprimento:
                    melhor_comprimento = comprimento
                    melhor = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
        return melhor or fallback

    def _eixo_elemento_ref(self, canvas, ref):
        linha = self._elemento_linha_ref(canvas, ref)
        if linha is None:
            return None
        return self._eixo_linha(linha)

    def _elemento_dobra_em_ponto(self, canvas, indices: list[int], pos: QPointF):
        tolerancia = 8.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor_ref = None
        melhor_dist = tolerancia
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if idx in indices or not self._eh_linha_candidata_dobra(el):
                continue
            if not any(self._eh_linha_interna_do_molde(canvas, molde_idx, el) for molde_idx in indices):
                continue
            pontos = self._pontos_para_hit_linha(el)
            if len(pontos) < 2:
                continue
            dist = min(self._distancia_ponto_segmento(a, b, pos) for a, b in zip(pontos, pontos[1:]))
            if dist <= melhor_dist:
                melhor_ref = idx
                melhor_dist = dist
        if melhor_ref is not None:
            return melhor_ref

        melhor_linha = None
        for molde_idx in indices:
            linha = self._linha_do_proprio_molde_em_ponto(canvas, molde_idx, pos, tolerancia)
            if linha is None:
                continue
            pontos = self._pontos_para_hit_linha(linha)
            if len(pontos) < 2:
                continue
            dist = min(self._distancia_ponto_segmento(a, b, pos) for a, b in zip(pontos, pontos[1:]))
            if dist <= melhor_dist:
                melhor_linha = linha
                melhor_dist = dist
        return melhor_linha

    def _elemento_linha_ref(self, canvas, ref) -> dict | None:
        if isinstance(ref, int):
            if 0 <= ref < len(canvas.cena.elementos):
                el = canvas.cena.elementos[ref]
                return el if isinstance(el, dict) else None
            return None
        if isinstance(ref, dict):
            return ref
        return None

    def _eh_linha_candidata_dobra(self, el: dict) -> bool:
        if not isinstance(el, dict) or el.get("molde"):
            return False
        return el.get("tipo") in {"polyline", "bezier_quadratica"}

    def _linha_do_proprio_molde_em_ponto(self, canvas, molde_idx: int, pos: QPointF, tolerancia: float) -> dict | None:
        if not (0 <= molde_idx < len(canvas.cena.elementos)):
            return None
        molde = canvas.cena.elementos[molde_idx]
        melhor = None
        melhor_dist = tolerancia
        for linha in self._linhas_do_proprio_molde(molde):
            pontos = self._pontos_para_hit_linha(linha)
            if len(pontos) < 2:
                continue
            dist = min(self._distancia_ponto_segmento(a, b, pos) for a, b in zip(pontos, pontos[1:]))
            if dist <= melhor_dist:
                melhor = linha
                melhor_dist = dist
        return melhor

    def _linhas_do_proprio_molde(self, molde: dict) -> list[dict]:
        linhas: list[dict] = []
        pontos = self._pontos_elemento(molde)
        base = pontos[:-1] if len(pontos) > 2 and self._pontos_mesmos(pontos[0], pontos[-1]) else pontos
        if len(base) < 2:
            return linhas
        indices_principais = self._indices_pontos_principais(base, molde)
        if len(indices_principais) >= 2:
            total = len(base)
            for pos, inicio in enumerate(indices_principais):
                fim = indices_principais[(pos + 1) % len(indices_principais)]
                trecho = self._trecho_contorno(base, inicio, fim)
                if self._comprimento_trecho(trecho) <= 1e-9:
                    continue
                linhas.append(
                    {
                        "tipo": "polyline",
                        "pontos": [(p.x(), p.y()) for p in trecho],
                        "origem_dobrar": "perimetro_principal",
                        "indice_inicio": inicio,
                        "indice_fim": fim,
                    }
                )
                if len(linhas) > total:
                    break
            return linhas
        for a, b in zip(base, base[1:] + base[:1]):
            if self._dist(a, b) > 1e-9:
                linhas.append(
                    {
                        "tipo": "polyline",
                        "pontos": [(a.x(), a.y()), (b.x(), b.y())],
                        "origem_dobrar": "perimetro_molde",
                    }
                )
        return linhas

    def _indices_pontos_principais(self, base: list[QPointF], molde: dict) -> list[int]:
        indices: list[int] = []
        for ponto in self._pontos_principais_molde(molde):
            idx = min(range(len(base)), key=lambda i, p=ponto: self._dist(base[i], p))
            if idx not in indices:
                indices.append(idx)
        indices.sort()
        return indices

    def _pontos_principais_molde(self, molde: dict) -> list[QPointF]:
        pontos: list[QPointF] = []
        for chave in ("controle_cantos", "pontos_controle_referencia"):
            origem = molde.get(chave)
            if not isinstance(origem, list):
                continue
            for p in origem:
                if self._eh_ponto(p):
                    pontos.append(QPointF(float(p[0]), float(p[1])))
            if pontos:
                return pontos
        origem = molde.get("pontos_controle_principais")
        if isinstance(origem, list):
            for item in origem:
                if isinstance(item, dict) and "x" in item and "y" in item:
                    try:
                        pontos.append(QPointF(float(item["x"]), float(item["y"])))
                    except Exception:
                        continue
        return pontos

    def _trecho_contorno(self, base: list[QPointF], inicio: int, fim: int) -> list[QPointF]:
        if not base:
            return []
        total = len(base)
        trecho = [QPointF(base[inicio % total])]
        idx = inicio % total
        limite = total + 1
        while idx != (fim % total) and limite > 0:
            idx = (idx + 1) % total
            trecho.append(QPointF(base[idx]))
            limite -= 1
        return trecho

    def _comprimento_trecho(self, pontos: list[QPointF]) -> float:
        return sum(self._dist(a, b) for a, b in zip(pontos, pontos[1:]))

    def _eh_linha_interna_do_molde(self, canvas, molde_idx: int, el: dict) -> bool:
        if not self._eh_linha_candidata_dobra(el):
            return False
        subtipo = str(el.get("subtipo_audaces") or el.get("metadados", {}).get("subtipo_audaces") or "").strip()
        if subtipo in {"contorno", "costura"} or el.get("costura_de_molde_id"):
            return False
        if not (0 <= molde_idx < len(canvas.cena.elementos)):
            return False
        molde = canvas.cena.elementos[molde_idx]
        molde_id = str(molde.get("molde_id") or molde.get("id") or "").strip()
        el_molde_id = str(el.get("molde_id") or "").strip()
        if molde_id and el_molde_id == molde_id:
            return True
        pontos = self._pontos_para_hit_linha(el)
        if not pontos:
            return False
        amostras = self._amostras_linha(pontos)
        if any(self._ponto_dentro_molde(molde, p) for p in amostras):
            return True
        bbox = self._bbox_pontos(self._pontos_elemento(molde))
        if bbox is None:
            return False
        min_x, min_y, max_x, max_y = bbox
        margem = max(max_x - min_x, max_y - min_y, 1.0) * 0.02
        return any((min_x - margem) <= p.x() <= (max_x + margem) and (min_y - margem) <= p.y() <= (max_y + margem) for p in amostras)

    def _amostras_linha(self, pontos: list[QPointF]) -> list[QPointF]:
        amostras = [QPointF(p) for p in pontos]
        for a, b in zip(pontos, pontos[1:]):
            amostras.append(QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0))
        return amostras

    def _eixo_linha(self, el: dict):
        eixo_serializado = el.get("eixo_serializado") if isinstance(el, dict) else None
        eixo = self._eixo_serializado_para_eixo(eixo_serializado)
        if eixo is not None:
            return eixo
        if el.get("tipo") == "bezier_quadratica":
            p0 = el.get("p0")
            p2 = el.get("p2")
            if self._eh_ponto(p0) and self._eh_ponto(p2):
                return ("line", QPointF(float(p0[0]), float(p0[1])), QPointF(float(p2[0]), float(p2[1])))
            return None
        pontos = self._pontos_para_preview_linha(el)
        if len(pontos) >= 2 and self._dist(pontos[0], pontos[-1]) > 1e-9:
            return ("line", QPointF(pontos[0]), QPointF(pontos[-1]))
        return None

    def _eixo_serializado_para_eixo(self, eixo_info):
        if not isinstance(eixo_info, dict):
            return None
        tipo = str(eixo_info.get("tipo") or "").lower()
        if tipo == "h":
            try:
                return ("h", float(eixo_info.get("valor")))
            except Exception:
                return None
        if tipo == "v":
            try:
                return ("v", float(eixo_info.get("valor")))
            except Exception:
                return None
        if tipo == "line":
            p1 = eixo_info.get("p1")
            p2 = eixo_info.get("p2")
            if self._eh_ponto(p1) and self._eh_ponto(p2):
                return ("line", QPointF(float(p1[0]), float(p1[1])), QPointF(float(p2[0]), float(p2[1])))
        return None

    def _pontos_para_preview_linha(self, el: dict) -> list[QPointF]:
        pontos = self._pontos_para_hit_linha(el)
        if len(pontos) < 2:
            return pontos
        return [QPointF(pontos[0]), QPointF(pontos[-1])]

    def _pontos_para_hit_linha(self, el: dict) -> list[QPointF]:
        if el.get("tipo") == "bezier_quadratica":
            if self._eh_ponto(el.get("p0")) and self._eh_ponto(el.get("p1")) and self._eh_ponto(el.get("p2")):
                p0 = QPointF(float(el["p0"][0]), float(el["p0"][1]))
                p1 = QPointF(float(el["p1"][0]), float(el["p1"][1]))
                p2 = QPointF(float(el["p2"][0]), float(el["p2"][1]))
                return [self._bezier(p0, p1, p2, i / 24.0) for i in range(25)]
            return []
        return self._pontos_elemento(el)

    def _ponto_dentro_molde(self, molde: dict, ponto: QPointF) -> bool:
        pontos = self._pontos_elemento(molde)
        if len(pontos) < 3:
            return False
        base = pontos[:-1] if self._pontos_mesmos(pontos[0], pontos[-1]) else pontos
        dentro = False
        j = len(base) - 1
        for i, pi in enumerate(base):
            pj = base[j]
            denom = pj.y() - pi.y()
            if abs(denom) <= 1e-12:
                denom = 1e-12 if denom >= 0 else -1e-12
            cruza = ((pi.y() > ponto.y()) != (pj.y() > ponto.y())) and (
                ponto.x() < (pj.x() - pi.x()) * (ponto.y() - pi.y()) / denom + pi.x()
            )
            if cruza:
                dentro = not dentro
            j = i
        return dentro

    def _centralizar_fio_no_molde(self, el: dict, eixo) -> None:
        pontos = self._pontos_elemento(el)
        if not pontos:
            return
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        if max_x <= min_x or max_y <= min_y:
            return
        margem_x = (max_x - min_x) * 0.18
        margem_y = (max_y - min_y) * 0.18
        if eixo[0] == "v":
            x = (min_x + max_x) / 2.0
            origem = (x, min_y + margem_y)
            fim = (x, max_y - margem_y)
        else:
            y = (min_y + max_y) / 2.0
            origem = (min_x + margem_x, y)
            fim = (max_x - margem_x, y)
        el["fio_origem"] = origem
        el["fio_fim"] = fim

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
        lado_movido = -int(lado)
        dobrados_contorno: list[QPointF] = []
        controles_originais = {
            chave: list(el.get(chave, [])) if isinstance(el.get(chave), list) else []
            for chave in ("controle_cantos", "pontos_controle_referencia")
        }

        def conv(p):
            pt = QPointF(float(p[0]), float(p[1]))
            if self._lado_ponto(pt, eixo) == lado_movido:
                pt = self._espelhar_ponto(pt, eixo)
            return (pt.x(), pt.y())

        if isinstance(el.get("pontos"), list):
            pontos = self._pontos_elemento(el)
            dobrados = self._pontos_dobrados_preview(pontos, eixo, lado, fechado=bool(el.get("molde")))
            if len(dobrados) >= 2:
                dobrados_contorno = [QPointF(p) for p in dobrados]
                el["pontos"] = [(p.x(), p.y()) for p in dobrados]

        for chave in (
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
        if el.get("molde"):
            if len(dobrados_contorno) >= 3:
                self._atualizar_controles_dobra_visivel(el, eixo, int(lado), dobrados_contorno, controles_originais)
            else:
                self._deduplicar_controles_dobrados(el)

    def _atualizar_controles_dobra_visivel(
        self,
        el: dict,
        eixo,
        lado: int,
        contorno: list[QPointF],
        controles_originais: dict[str, list],
    ) -> None:
        base = contorno[:-1] if len(contorno) > 2 and self._pontos_mesmos(contorno[0], contorno[-1]) else list(contorno)
        if len(base) < 2:
            self._deduplicar_controles_dobrados(el)
            return
        tolerancia = self._tolerancia_contorno(base)
        candidatos: list[QPointF] = []
        for chave in ("controle_cantos", "pontos_controle_referencia"):
            for item in controles_originais.get(chave, []):
                if not self._eh_ponto(item):
                    continue
                ponto = QPointF(float(item[0]), float(item[1]))
                lado_ponto = self._lado_ponto(ponto, eixo)
                if lado_ponto not in {int(lado), 0}:
                    continue
                if self._ponto_no_contorno(ponto, base, tolerancia * 20.0):
                    candidatos.append(ponto)
            if candidatos:
                break
        candidatos.extend(self._pontos_controle_eixo_no_contorno(base, eixo))

        controles: list[QPointF] = []
        for ponto in base:
            if not candidatos or any(self._dist(ponto, candidato) <= tolerancia * 20.0 for candidato in candidatos):
                if not any(self._dist(ponto, existente) <= tolerancia for existente in controles):
                    controles.append(QPointF(ponto))
        if len(controles) < 2:
            controles = self._controles_fallback_contorno(base)
        serial = [(p.x(), p.y()) for p in controles]
        el["controle_cantos"] = serial
        el["pontos_controle_referencia"] = list(serial)

    def _pontos_controle_eixo_no_contorno(self, contorno: list[QPointF], eixo) -> list[QPointF]:
        tolerancia = self._tolerancia_contorno(contorno) * 20.0
        pontos = [QPointF(p) for p in contorno if abs(self._valor_lado(p, eixo)) <= tolerancia]
        if len(pontos) <= 2:
            return pontos
        inicio = min(pontos, key=lambda p: self._coordenada_no_eixo(p, eixo))
        fim = max(pontos, key=lambda p: self._coordenada_no_eixo(p, eixo))
        if self._dist(inicio, fim) <= tolerancia:
            return [QPointF(inicio)]
        return [QPointF(inicio), QPointF(fim)]

    def _coordenada_no_eixo(self, ponto: QPointF, eixo) -> float:
        if eixo[0] == "h":
            return ponto.x()
        if eixo[0] == "v":
            return ponto.y()
        a: QPointF = eixo[1]
        b: QPointF = eixo[2]
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        denom = (dx * dx) + (dy * dy)
        if denom <= 1e-12:
            return 0.0
        return (((ponto.x() - a.x()) * dx) + ((ponto.y() - a.y()) * dy)) / denom

    def _ponto_no_contorno(self, ponto: QPointF, contorno: list[QPointF], tolerancia: float) -> bool:
        if len(contorno) < 2:
            return False
        return any(
            self._distancia_ponto_segmento(a, b, ponto) <= tolerancia
            for a, b in zip(contorno, contorno[1:] + contorno[:1])
        )

    def _controles_fallback_contorno(self, contorno: list[QPointF]) -> list[QPointF]:
        if len(contorno) <= 16:
            return [QPointF(p) for p in contorno]
        passo = max(1, len(contorno) // 8)
        return [QPointF(p) for idx, p in enumerate(contorno) if idx % passo == 0][:8]

    def _tolerancia_contorno(self, pontos: list[QPointF]) -> float:
        bbox = self._bbox_pontos(pontos)
        if bbox is None:
            return 1e-6
        min_x, min_y, max_x, max_y = bbox
        escala = max(max_x - min_x, max_y - min_y, 1.0)
        return max(1e-6, escala * 1e-7)

    def _deduplicar_controles_dobrados(self, el: dict) -> None:
        for chave in ("controle_cantos", "pontos_controle_referencia"):
            origem = el.get(chave)
            if not isinstance(origem, list):
                continue
            controles: list[tuple[float, float]] = []
            for item in origem:
                if not self._eh_ponto(item):
                    continue
                ponto = QPointF(float(item[0]), float(item[1]))
                if any(self._dist(ponto, QPointF(x, y)) <= 1e-7 for x, y in controles):
                    continue
                controles.append((ponto.x(), ponto.y()))
            el[chave] = controles

    def _pontos_dobrados_preview(
        self,
        pontos: list[QPointF],
        eixo,
        lado_destino: int,
        fechado: bool | None = None,
    ) -> list[QPointF]:
        if len(pontos) < 2 or not lado_destino:
            return [QPointF(p) for p in pontos]
        fechado = self._contorno_fechado(pontos) if fechado is None else bool(fechado)
        if not fechado:
            lado_movido = -int(lado_destino)
            return [
                self._espelhar_ponto(p, eixo) if self._lado_ponto(p, eixo) == lado_movido else QPointF(p)
                for p in pontos
            ]

        base = pontos[:-1] if self._pontos_mesmos(pontos[0], pontos[-1]) else list(pontos)
        lado_destino = int(lado_destino)
        lado_movido = -lado_destino
        fixo = self._recortar_poligono_lado(base, eixo, lado_destino)
        movido = self._recortar_poligono_lado(base, eixo, lado_movido)
        movido_dobrado = [self._espelhar_ponto(p, eixo) for p in movido]
        referencias = [QPointF(p) for p in base]
        referencias.extend(self._espelhar_ponto(p, eixo) for p in base)
        if len(fixo) >= 3 and len(movido_dobrado) >= 3:
            unidos = self._unir_poligonos(fixo, movido_dobrado, referencias)
        elif len(fixo) >= 3:
            unidos = self._normalizar_vertices_dobra(fixo, referencias)
        else:
            unidos = self._normalizar_vertices_dobra(movido_dobrado, referencias)
        if len(unidos) >= 3 and not self._pontos_mesmos(unidos[0], unidos[-1]):
            unidos.append(QPointF(unidos[0]))
        return unidos

    def _recortar_poligono_lado(self, pontos: list[QPointF], eixo, lado: int) -> list[QPointF]:
        if len(pontos) < 3 or not lado:
            return []

        def valor(pt: QPointF) -> float:
            return self._valor_lado(pt, eixo) * float(lado)

        entrada = list(pontos)
        saida = []
        eps = 1e-9
        anterior = entrada[-1]
        valor_anterior = valor(anterior)
        anterior_dentro = valor_anterior >= -eps
        for atual in entrada:
            valor_atual = valor(atual)
            atual_dentro = valor_atual >= -eps
            if atual_dentro != anterior_dentro:
                inter = self._intersecao_segmento_eixo(anterior, atual, eixo)
                if inter is not None:
                    saida.append(inter)
            if atual_dentro:
                saida.append(QPointF(atual))
            anterior = atual
            valor_anterior = valor_atual
            anterior_dentro = atual_dentro
        return self._limpar_pontos_repetidos(saida)

    def _intersecao_segmento_eixo(self, a: QPointF, b: QPointF, eixo) -> QPointF | None:
        va = self._valor_lado(a, eixo)
        vb = self._valor_lado(b, eixo)
        denom = va - vb
        if abs(denom) <= 1e-12:
            return None
        t = max(0.0, min(1.0, va / denom))
        return QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))

    def _unir_poligonos(self, a: list[QPointF], b: list[QPointF], referencias: list[QPointF] | None = None) -> list[QPointF]:
        caminhos = []
        for pontos in (a, b):
            if len(pontos) < 3:
                continue
            path = QPainterPath()
            path.addPolygon(QPolygonF(pontos))
            path.closeSubpath()
            caminhos.append(path)
        if not caminhos:
            return []
        unido = caminhos[0]
        for path in caminhos[1:]:
            unido = unido.united(path)
        poligono = [QPointF(p) for p in unido.simplified().toFillPolygon()]
        return self._normalizar_vertices_dobra(poligono, referencias or (list(a) + list(b)))

    def _normalizar_vertices_dobra(self, pontos: list[QPointF], referencias: list[QPointF] | None = None) -> list[QPointF]:
        """Remove micro-cantos criados pela união geométrica da dobra.

        Quando uma metade assimétrica é dobrada sobre a outra, o QPainterPath pode
        gerar um pequeno chanfro/cantinho no encontro de duas linhas quase
        coincidentes. Para a dobra de molde isso não deve virar um novo vértice:
        a ponta precisa encaixar no canto real mais próximo, como papel dobrado.
        """
        base = self._limpar_pontos_repetidos([QPointF(p) for p in pontos])
        if len(base) < 3:
            return base

        refs = [QPointF(p) for p in (referencias or [])]
        tolerancia = self._tolerancia_encaixe_dobra(base + refs)

        if refs:
            encaixados: list[QPointF] = []
            for ponto in base:
                ref = self._referencia_mais_proxima(ponto, refs)
                if ref is not None and self._dist(ponto, ref) <= tolerancia:
                    ponto = QPointF(ref)
                encaixados.append(QPointF(ponto))
            base = self._limpar_pontos_repetidos(encaixados)

        # Remove segmentos minúsculos que aparecem como "dente" no canto.
        base = self._remover_micro_segmentos_dobra(base, tolerancia)

        # Remove pontos praticamente alinhados, evitando criar ponto de controle
        # falso em uma reta que deveria continuar limpa.
        base = self._remover_pontos_colineares_dobra(base, tolerancia * 0.18)
        return self._limpar_pontos_repetidos(base)

    def _tolerancia_encaixe_dobra(self, pontos: list[QPointF]) -> float:
        if not pontos:
            return 0.05
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        diag = sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2)
        # A dobra precisa ser rigida; esta folga cobre apenas ruido numerico.
        return max(1e-7, min(0.01, diag * 1e-6))

    def _referencia_mais_proxima(self, ponto: QPointF, referencias: list[QPointF]) -> QPointF | None:
        melhor = None
        melhor_dist = float("inf")
        for ref in referencias:
            d = self._dist(ponto, ref)
            if d < melhor_dist:
                melhor = ref
                melhor_dist = d
        return QPointF(melhor) if melhor is not None else None

    def _remover_micro_segmentos_dobra(self, pontos: list[QPointF], tolerancia: float) -> list[QPointF]:
        saida = [QPointF(p) for p in pontos]
        if len(saida) < 3:
            return saida
        mudou = True
        while mudou and len(saida) >= 3:
            mudou = False
            total = len(saida)
            remover: int | None = None
            for i in range(total):
                atual = saida[i]
                prox = saida[(i + 1) % total]
                if self._dist(atual, prox) <= tolerancia:
                    # Mantém o ponto seguinte, que normalmente é o canto real.
                    remover = i
                    break
            if remover is not None:
                saida.pop(remover)
                mudou = True
        return saida

    def _remover_pontos_colineares_dobra(self, pontos: list[QPointF], tolerancia: float) -> list[QPointF]:
        if len(pontos) < 4:
            return pontos
        saida: list[QPointF] = []
        total = len(pontos)
        for i, p in enumerate(pontos):
            anterior = pontos[(i - 1) % total]
            proximo = pontos[(i + 1) % total]
            if self._dist(anterior, p) <= tolerancia or self._dist(p, proximo) <= tolerancia:
                continue
            if self._distancia_ponto_segmento(anterior, proximo, p) <= tolerancia:
                continue
            saida.append(QPointF(p))
        return saida if len(saida) >= 3 else pontos

    def _limpar_pontos_repetidos(self, pontos: list[QPointF]) -> list[QPointF]:
        saida: list[QPointF] = []
        for p in pontos:
            if saida and self._pontos_mesmos(saida[-1], p):
                continue
            saida.append(QPointF(p))
        if len(saida) > 1 and self._pontos_mesmos(saida[0], saida[-1]):
            saida.pop()
        return saida

    def _fechar_contorno(self, pontos: list[QPointF]) -> list[QPointF]:
        saida = [QPointF(p) for p in pontos]
        if len(saida) >= 2 and not self._pontos_mesmos(saida[0], saida[-1]):
            saida.append(QPointF(saida[0]))
        return saida

    def _contorno_fechado(self, pontos: list[QPointF]) -> bool:
        if len(pontos) < 4:
            return False
        return self._pontos_mesmos(pontos[0], pontos[-1])

    @staticmethod
    def _pontos_mesmos(a: QPointF, b: QPointF) -> bool:
        return abs(a.x() - b.x()) <= 1e-7 and abs(a.y() - b.y()) <= 1e-7

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

    def _conferir_lados(self, canvas, indices: list[int], eixo) -> None:
        """Compara os dois lados como se o molde fosse dobrado no papel, sem alterar o molde."""
        resultados = []
        for idx in indices:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            eixo_el = eixo if eixo[0] == "line" else self._eixo(canvas, [idx], self._obter_dialog(canvas).cmb_modo.currentText())
            if eixo_el is None:
                continue
            pontos = self._pontos_elemento(el)
            if len(pontos) < 3:
                continue
            base = pontos[:-1] if len(pontos) > 2 and self._pontos_mesmos(pontos[0], pontos[-1]) else list(pontos)
            lado_destino = int(self._lado_preview or 1)
            lado_a = self._recortar_poligono_lado(base, eixo_el, lado_destino)
            lado_b = self._recortar_poligono_lado(base, eixo_el, -lado_destino)
            lado_b_espelhado = [self._espelhar_ponto(p, eixo_el) for p in lado_b]
            metricas = self._metricas_simetria(lado_a, lado_b_espelhado)
            nome = str(el.get("nome_molde") or el.get("nome") or f"molde {idx + 1}")
            el.setdefault("metadados", {})["ultima_conferencia_dobra"] = metricas
            resultados.append((nome, metricas))
        if not resultados:
            self._status(canvas, "Não foi possível conferir os lados: escolha um molde fechado e um eixo válido.")
            return
        partes = []
        for nome, met in resultados:
            max_txt = canvas.formatar_distancia(met["diferenca_maxima"]) if hasattr(canvas, "formatar_distancia") else formatar_numero(met["diferenca_maxima"], 2)
            media_txt = canvas.formatar_distancia(met["diferenca_media"]) if hasattr(canvas, "formatar_distancia") else formatar_numero(met["diferenca_media"], 2)
            situacao = "simétrico" if met["diferenca_maxima"] <= met["tolerancia"] else "assimétrico"
            partes.append(f"{nome}: {situacao} | máx. {max_txt} | média {media_txt}")
        self._status(canvas, "Conferência da dobra: " + " ; ".join(partes))

    def _metricas_simetria(self, lado_a: list[QPointF], lado_b: list[QPointF]) -> dict:
        if len(lado_a) < 2 or len(lado_b) < 2:
            return {"diferenca_maxima": float("inf"), "diferenca_media": float("inf"), "tolerancia": 0.05}
        distancias = []
        for ponto in lado_a:
            distancias.append(self._distancia_ponto_polilinha(ponto, lado_b))
        for ponto in lado_b:
            distancias.append(self._distancia_ponto_polilinha(ponto, lado_a))
        if not distancias:
            return {"diferenca_maxima": float("inf"), "diferenca_media": float("inf"), "tolerancia": 0.05}
        return {
            "diferenca_maxima": max(distancias),
            "diferenca_media": sum(distancias) / len(distancias),
            "tolerancia": 0.05,
            "amostras": len(distancias),
        }

    def _distancia_ponto_polilinha(self, ponto: QPointF, pontos: list[QPointF]) -> float:
        if len(pontos) == 1:
            return self._dist(ponto, pontos[0])
        return min(self._distancia_ponto_segmento(a, b, ponto) for a, b in zip(pontos, pontos[1:]))

    def _desenhar_originais_preservados(self, canvas, painter, indices: list[int]) -> None:
        """Mostra o lado que foi dobrado já na posição dobrada, como referência pontilhada."""
        if not indices:
            return
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None and hasattr(dialog, "chk_mostrar_original") and not dialog.chk_mostrar_original.isChecked():
            return
        painter.save()
        pen = QPen(QColor("#9aa0a6"), 1.1, Qt.DashLine)
        pen.setDashPattern([4.0, 3.0])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for idx in indices:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            registros = el.get("contornos_dobra_original")
            if not isinstance(registros, list) or not registros:
                estado = el.get("estado_dobra") if isinstance(el.get("estado_dobra"), dict) else None
                if estado and (estado.get("contorno_lado_dobrado") or estado.get("contorno_lado_oculto")):
                    registros = [{"contorno_lado_dobrado": estado.get("contorno_lado_dobrado") or estado.get("contorno_lado_oculto")}]
                else:
                    continue
            for registro in registros[-2:]:
                origem = (
                    registro.get("contorno_lado_dobrado")
                    or registro.get("contorno_pontilhado")
                    or registro.get("metade_movida")
                ) if isinstance(registro, dict) else registro
                if not isinstance(origem, list):
                    continue
                pontos = []
                for item in origem:
                    if self._eh_ponto(item):
                        pontos.append(QPointF(float(item[0]), float(item[1])))
                if len(pontos) >= 2:
                    if not self._pontos_mesmos(pontos[0], pontos[-1]):
                        pontos.append(QPointF(pontos[0]))
                    self._desenhar_polilinha_tela(canvas, painter, pontos)
        painter.restore()

    def _normalizar_registro_visual_dobra(self, el: dict, pontos_dobrados: list[QPointF]) -> None:
        """Faz a sombra/pontilhado encaixar no contorno dobrado real.

        Assim o lado oculto não cria um cantinho separado no vértice superior
        quando a metade dobrada termina muito perto de um canto existente.
        """
        referencias = [QPointF(p) for p in pontos_dobrados]
        estado = el.get("estado_dobra") if isinstance(el.get("estado_dobra"), dict) else None
        registros = el.get("contornos_dobra_original")
        alvos = []
        if estado is not None:
            alvos.append(estado)
        if isinstance(registros, list) and registros and isinstance(registros[-1], dict):
            alvos.append(registros[-1])

        for alvo in alvos:
            origem = alvo.get("contorno_lado_dobrado") or alvo.get("contorno_pontilhado") or alvo.get("contorno_lado_oculto")
            if not isinstance(origem, list):
                continue
            pontos = [QPointF(float(p[0]), float(p[1])) for p in origem if self._eh_ponto(p)]
            if len(pontos) < 2:
                continue
            fechado = bool(len(pontos) >= 3 and self._pontos_mesmos(pontos[0], pontos[-1]))
            pontos = pontos[:-1] if fechado else pontos
            pontos = self._normalizar_vertices_dobra(pontos, referencias)
            if fechado and pontos and not self._pontos_mesmos(pontos[0], pontos[-1]):
                pontos.append(QPointF(pontos[0]))
            serial = [(p.x(), p.y()) for p in pontos]
            alvo["contorno_lado_dobrado"] = serial
            alvo["contorno_pontilhado"] = serial
            alvo["contorno_lado_oculto"] = serial

    def _serializar_eixo(self, eixo) -> dict:
        if eixo[0] == "h":
            return {"tipo": "h", "valor": float(eixo[1])}
        if eixo[0] == "v":
            return {"tipo": "v", "valor": float(eixo[1])}
        return {
            "tipo": "line",
            "p1": (float(eixo[1].x()), float(eixo[1].y())),
            "p2": (float(eixo[2].x()), float(eixo[2].y())),
        }

    def _ocultar_marcacoes_dobra(self, canvas) -> None:
        """Limpa apenas marcações temporárias da ferramenta.

        O pontilhado do lado dobrado NÃO é rastro temporário: ele representa a
        posição real do papel após a dobra e deve permanecer enquanto o molde
        estiver dobrado. Ele só some quando o molde é desdobrado/restaurado.
        """
        try:
            elementos = getattr(getattr(canvas, "cena", None), "elementos", []) or []
            for el in elementos:
                if not isinstance(el, dict) or not el.get("molde"):
                    continue
                dobrado = bool(el.get("molde_dobrado"))
                estado = el.get("estado_dobra") if isinstance(el.get("estado_dobra"), dict) else None
                if estado and bool(estado.get("ativo")):
                    dobrado = True
                # Se não está dobrado, pode limpar a marcação. Se está dobrado,
                # preserva o valor atual de mostrar_contorno_dobra_original.
                if not dobrado:
                    el["mostrar_contorno_dobra_original"] = False
        except Exception:
            pass

    def _resetar_operacao(self):
        self._lado_preview = 0
        self._preview_pos = None
        self._resetar_referencias()
        self._ultimo_direito = 0.0

    def _resetar_referencias(self):
        self._resetar_linha()
        self._elemento_ref = None

    def _resetar_linha(self):
        self._linha_p1 = None
        self._linha_p2 = None

    def _confirmacao_pendente(self, canvas) -> bool:
        indices = self._indices_moldes(canvas)
        if not indices:
            return False
        dialog = self._obter_dialog(canvas)
        modo_norm = self._modo_normalizado(dialog.cmb_modo.currentText())
        if modo_norm == "linha":
            return self._linha_p1 is not None or self._linha_p2 is not None
        if modo_norm == "elemento":
            return self._elemento_ref is not None or bool(self._lado_preview)
        return bool(self._lado_preview)

    def _cancelar_operacao(self, canvas) -> None:
        self._lado_preview = 0
        self._preview_pos = None
        self._resetar_referencias()
        canvas.update()
        self._status(canvas, "Operação de dobra cancelada. A seleção foi mantida; escolha novamente o eixo/lado.")

    def _fechar(self, canvas):
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Dobrar finalizada. Voltando para Selecionar.")

    def obter_candidatos_snap(self, canvas, cursor: QPointF):
        if self._linha_p1 is None:
            return []
        pontos = [QPointF(self._linha_p1)]
        if self._linha_p2 is not None:
            pontos.append(QPointF(self._linha_p2))
        elif self._preview_pos is not None:
            pontos.append(QPointF(self._preview_pos))
        if len(pontos) < 2:
            return []

        tolerancia = canvas._tolerancia_snap_px() / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        candidatos: list[SnapResult] = []
        for ponto in pontos:
            dist = self._dist(cursor, ponto)
            if dist <= tolerancia:
                candidatos.append(SnapResult(QPointF(ponto), "nó", dist, None))
        inicio, fim = pontos[0], pontos[-1]
        meio = QPointF((inicio.x() + fim.x()) / 2.0, (inicio.y() + fim.y()) / 2.0)
        dist_meio = self._dist(cursor, meio)
        if dist_meio <= tolerancia:
            candidatos.append(SnapResult(meio, "ponto médio", dist_meio, None))
        proj = self._projetar_em_segmento(cursor, inicio, fim)
        dist_borda = self._dist(cursor, proj)
        if dist_borda <= tolerancia:
            candidatos.append(SnapResult(proj, "borda", dist_borda, None))
        return candidatos

    def _projetar_em_segmento(self, ponto: QPointF, inicio: QPointF, fim: QPointF) -> QPointF:
        vx = fim.x() - inicio.x()
        vy = fim.y() - inicio.y()
        denom = (vx * vx) + (vy * vy)
        if denom <= 1e-12:
            return QPointF(inicio)
        t = ((ponto.x() - inicio.x()) * vx + (ponto.y() - inicio.y()) * vy) / denom
        t = max(0.0, min(1.0, t))
        return QPointF(inicio.x() + (vx * t), inicio.y() + (vy * t))

    def _distancia_ponto_segmento(self, inicio: QPointF, fim: QPointF, ponto: QPointF) -> float:
        proj = self._projetar_em_segmento(ponto, inicio, fim)
        return self._dist(ponto, proj)

    def _bbox_pontos(self, pontos: list[QPointF]) -> tuple[float, float, float, float] | None:
        if not pontos:
            return None
        return min(p.x() for p in pontos), min(p.y() for p in pontos), max(p.x() for p in pontos), max(p.y() for p in pontos)

    @staticmethod
    def _bezier(p0: QPointF, p1: QPointF, p2: QPointF, t: float) -> QPointF:
        u = 1.0 - t
        return QPointF(
            (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x()),
            (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y()),
        )

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
