from __future__ import annotations

from copy import deepcopy
from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QLabel, QVBoxLayout

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class RecortarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:recortar"
        self.setWindowTitle("Recortar")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(270)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel { color:#111111; }
            QComboBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            """
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.cmb_trecho = QComboBox()
        self.cmb_trecho.addItems(["Remover trecho menor", "Remover trecho maior", "Manter trecho menor", "Manter trecho maior"])
        form.addRow("Ação", self.cmb_trecho)
        raiz.addLayout(form)


class Ferramenta(FerramentaBase):
    id_ferramenta = "recortar"
    nome = "Recortar"
    usa_painel_auxiliar = False
    descricao_painel = "Remove ou mantém o trecho entre dois cliques no mesmo contorno/polyline."

    _dialog_por_canvas: dict[int, RecortarDialog] = {}

    def __init__(self):
        super().__init__()
        self._primeiro: tuple[int, int, QPointF] | None = None
        self._hover: tuple[int, int, QPointF] | None = None
        self._preview: list[QPointF] = []
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._primeiro = None
        self._hover = None
        self._preview = []
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Recortar: esquerdo marca inicio e fim. Direito limpa/finaliza; direito novamente fecha.")

    def on_deactivate(self, canvas):
        self._primeiro = None
        self._hover = None
        self._preview = []
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if canvas is not None:
            canvas.update()

    def on_key_press(self, canvas, event) -> bool:
        if event.key() == Qt.Key_Escape:
            self._limpar(canvas)
            event.accept()
            return True
        return False

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._hover = self._segmento_mais_proximo(canvas, pos)
        self._atualizar_preview(canvas)
        canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._primeiro is not None:
                self._limpar(canvas)
                self._operacao_finalizada = True
                self._direito_confirma_fechamento = True
                self._status(canvas, "Recorte finalizado sem aplicar. Clique direito novamente fecha.")
            elif self._operacao_finalizada and not self._direito_confirma_fechamento:
                self._direito_confirma_fechamento = True
                self._status(canvas, "Operação finalizada. Clique direito novamente fecha a ferramenta.")
            else:
                self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        alvo = self._segmento_mais_proximo(canvas, pos)
        if alvo is None:
            self._status(canvas, "Recortar: nenhum segmento encontrado.")
            return False
        if self._primeiro is None:
            self._primeiro = alvo
            self._operacao_finalizada = False
            self._direito_confirma_fechamento = False
            canvas._selecionados = {alvo[0]}
            self._status(canvas, "Primeiro ponto marcado. Clique no segundo ponto do mesmo elemento.")
            canvas.update()
            event.accept()
            return True
        if alvo[0] != self._primeiro[0]:
            self._status(canvas, "O segundo ponto precisa estar no mesmo elemento do primeiro.")
            event.accept()
            return True
        if self._aplicar_recorte(canvas, self._primeiro, alvo):
            self._limpar(canvas, status=False)
            self._operacao_finalizada = True
            self._direito_confirma_fechamento = False
            self._status(canvas, "Recorte aplicado. Clique esquerdo inicia outro recorte; direito fecha.")
            event.accept()
            return True
        self._status(canvas, "Recorte cancelado para evitar geometria inválida.")
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        painter.save()
        if self._preview:
            pen = QPen(QColor("#ff3b30"), 2.0, Qt.DashLine)
            painter.setPen(pen)
            for a, b in zip(self._preview, self._preview[1:]):
                painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        for item, cor in ((self._primeiro, "#00ff7f"), (self._hover, "#ffcf00")):
            if item is None:
                continue
            p = item[2]
            tela = canvas._cena_para_tela(p)
            painter.setPen(QPen(QColor(cor), 1.4))
            painter.drawLine(QPointF(tela.x() - 6, tela.y()), QPointF(tela.x() + 6, tela.y()))
            painter.drawLine(QPointF(tela.x(), tela.y() - 6), QPointF(tela.x(), tela.y() + 6))
        painter.restore()

    def _obter_dialog(self, canvas) -> RecortarDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = RecortarDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.cmb_trecho.currentTextChanged.connect(lambda _txt: self._atualizar_preview_e_redesenhar(canvas))
        return dialog

    def _restaurar_dialog(self, canvas, dialog: RecortarDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _aplicar_recorte(self, canvas, a_info, b_info) -> bool:
        idx, seg_a, p_a = a_info
        _, seg_b, p_b = b_info
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return False
        pontos = [(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pontos) < 2:
            return False
        fechado = self._fechado(pontos)
        pts, ia = self._inserir_ponto(pontos, seg_a, (p_a.x(), p_a.y()))
        # Se o segundo segmento vem após o primeiro, o índice pode deslocar.
        if seg_b > seg_a:
            seg_b += 1
        pts, ib = self._inserir_ponto(pts, seg_b, (p_b.x(), p_b.y()))
        if ia == ib:
            return False
        if ia > ib:
            ia, ib = ib, ia
        modo = self._obter_dialog(canvas).cmb_trecho.currentText()

        if fechado:
            base = pts[:-1] if self._fechado(pts) else pts[:]
            n = len(base)
            trecho_ab = base[ia: ib + 1]
            trecho_ba = base[ib:] + base[: ia + 1]
            len_ab = self._comprimento(trecho_ab)
            len_ba = self._comprimento(trecho_ba)
            if "menor" in modo:
                manter = trecho_ba if modo.startswith("Remover") and len_ab <= len_ba else trecho_ab if modo.startswith("Remover") else trecho_ab if len_ab <= len_ba else trecho_ba
            else:
                manter = trecho_ba if modo.startswith("Remover") and len_ab > len_ba else trecho_ab if modo.startswith("Remover") else trecho_ab if len_ab > len_ba else trecho_ba
            if len(manter) < 2:
                return False
            novo = deepcopy(el)
            novo["pontos"] = [(p[0], p[1]) if isinstance(p, tuple) else (p.x(), p.y()) for p in manter]
            if novo.get("molde") and self._fechado(novo["pontos"]):
                self._reconstruir_controles_molde(novo)
            else:
                novo["molde"] = False if novo.get("molde") else novo.get("molde", False)
                self._limpar_controles_invalidos(novo)
            canvas.cena.elementos[idx] = novo
            canvas._selecionados = {idx}
        else:
            trecho = pts[ia: ib + 1]
            antes = pts[: ia + 1]
            depois = pts[ib:]
            len_trecho = self._comprimento(trecho)
            len_fora = self._comprimento(antes) + self._comprimento(depois)
            manter_trecho = ("Manter" in modo and (("menor" in modo and len_trecho <= len_fora) or ("maior" in modo and len_trecho > len_fora))) or ("Remover" in modo and False)
            if manter_trecho:
                if len(trecho) < 2:
                    return False
                novo = deepcopy(el)
                novo["pontos"] = trecho
                novo["molde"] = False if novo.get("molde") else novo.get("molde", False)
                self._limpar_controles_invalidos(novo)
                canvas.cena.elementos[idx] = novo
                canvas._selecionados = {idx}
            else:
                novos = []
                if len(antes) >= 2:
                    ea = deepcopy(el)
                    ea["pontos"] = antes
                    ea["id"] = str(uuid4())
                    ea["molde"] = False if ea.get("molde") else ea.get("molde", False)
                    self._limpar_controles_invalidos(ea)
                    novos.append(ea)
                if len(depois) >= 2:
                    eb = deepcopy(el)
                    eb["pontos"] = depois
                    eb["id"] = str(uuid4())
                    eb["molde"] = False if eb.get("molde") else eb.get("molde", False)
                    self._limpar_controles_invalidos(eb)
                    novos.append(eb)
                if not novos:
                    return False
                canvas.cena.elementos[idx: idx + 1] = novos
                canvas._selecionados = set(range(idx, idx + len(novos)))
        canvas._registrar_historico()
        canvas.update()
        self._status(canvas, "Recorte aplicado.")
        return True

    def _atualizar_preview(self, canvas) -> None:
        self._preview = []
        if self._primeiro is None or self._hover is None or self._primeiro[0] != self._hover[0]:
            return
        idx, seg_a, p_a = self._primeiro
        _, seg_b, p_b = self._hover
        el = canvas.cena.elementos[idx]
        pts = [(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pts) < 2:
            return
        pts, ia = self._inserir_ponto(pts, seg_a, (p_a.x(), p_a.y()))
        if seg_b > seg_a:
            seg_b += 1
        pts, ib = self._inserir_ponto(pts, seg_b, (p_b.x(), p_b.y()))
        if ia > ib:
            ia, ib = ib, ia
        self._preview = [QPointF(x, y) for x, y in pts[ia: ib + 1]]

    def _atualizar_preview_e_redesenhar(self, canvas) -> None:
        self._atualizar_preview(canvas)
        canvas.update()

    def _limpar(self, canvas, status: bool = True):
        self._primeiro = None
        self._hover = None
        self._preview = []
        if status:
            self._status(canvas, "Recortar: pontos limpos. Clique no início do trecho.")
        canvas.update()

    def _fechar(self, canvas) -> None:
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Recortar finalizada. Voltando para Selecionar.")

    def _segmento_mais_proximo(self, canvas, pos: QPointF) -> tuple[int, int, QPointF] | None:
        tolerancia = 10.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor = None
        candidatos = sorted(getattr(canvas, "_selecionados", set()) or []) or list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
                proj, dist = self._projetar(a, b, pos)
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, seg_idx, proj)
        if melhor is None:
            return None
        return melhor[1], melhor[2], melhor[3]

    @staticmethod
    def _projetar(a: QPointF, b: QPointF, p: QPointF) -> tuple[QPointF, float]:
        abx, aby = b.x() - a.x(), b.y() - a.y()
        apx, apy = p.x() - a.x(), p.y() - a.y()
        den = abx * abx + aby * aby
        t = 0.0 if den <= 1e-9 else max(0.0, min(1.0, (apx * abx + apy * aby) / den))
        proj = QPointF(a.x() + abx * t, a.y() + aby * t)
        return proj, sqrt((proj.x() - p.x()) ** 2 + (proj.y() - p.y()) ** 2)

    @staticmethod
    def _inserir_ponto(pontos: list[tuple[float, float]], seg_idx: int, ponto: tuple[float, float]) -> tuple[list[tuple[float, float]], int]:
        pts = list(pontos)
        if seg_idx < 0:
            return pts, 0
        if seg_idx >= len(pts) - 1:
            return pts, len(pts) - 1
        if Ferramenta._dist(pts[seg_idx], ponto) <= 1e-7:
            return pts, seg_idx
        if Ferramenta._dist(pts[seg_idx + 1], ponto) <= 1e-7:
            return pts, seg_idx + 1
        pts.insert(seg_idx + 1, (float(ponto[0]), float(ponto[1])))
        return pts, seg_idx + 1

    @staticmethod
    def _comprimento(pontos: list[tuple[float, float]]) -> float:
        return sum(Ferramenta._dist(a, b) for a, b in zip(pontos, pontos[1:]))

    @staticmethod
    def _fechado(pontos: list[tuple[float, float]]) -> bool:
        return len(pontos) >= 3 and Ferramenta._dist(pontos[0], pontos[-1]) <= 1e-7

    @staticmethod
    def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2)

    @staticmethod
    def _limpar_controles_invalidos(el: dict) -> None:
        for chave in ("controle_cantos", "controle_auxiliares", "pontos_controle_principais", "pontos_auxiliares", "segment_ids", "node_ids"):
            el.pop(chave, None)
        if el.get("molde"):
            el["molde"] = False

    @staticmethod
    def _reconstruir_controles_molde(el: dict) -> None:
        pontos = [(float(x), float(y)) for x, y in el.get("pontos", [])]
        base = pontos[:-1] if len(pontos) >= 2 and Ferramenta._dist(pontos[0], pontos[-1]) <= 1e-7 else pontos
        controles = base[:]
        el["controle_cantos"] = controles
        el["controle_auxiliares"] = []
        el["pontos_controle_principais"] = [{"x": x, "y": y} for x, y in controles]
        el["pontos_auxiliares"] = []
        el["mostrar_controles"] = True
        el.setdefault("metadados", {})["controles_recalculados_por"] = "recortar"

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
