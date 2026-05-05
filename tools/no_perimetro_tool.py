from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QGridLayout, QLineEdit, QPushButton, QVBoxLayout

from tools.medicao_utils import mensagem_status, selecionar_segmento_mais_proximo, segmentos_de_elemento
from tools.tool_base import FerramentaBase


class PontosNoPerimetroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pontos no elemento")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(270)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        grid = QGridLayout()
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Perímetro"])
        self.ed_passo = QLineEdit("2")  # Distância (cm)
        grid.addWidget(self.cmb_modo, 0, 0)
        grid.addWidget(self.ed_passo, 0, 1)
        lay.addLayout(grid)

        self.chk_dividir = QCheckBox("Dividir elemento")
        self.chk_dividir.setChecked(False)
        lay.addWidget(self.chk_dividir)

        self.chk_colocar = QCheckBox("Colocar ponto")
        self.chk_colocar.setChecked(False)
        lay.addWidget(self.chk_colocar)

        self.chk_manter = QCheckBox("Manter distâncias nos moldes")
        self.chk_manter.setChecked(False)
        lay.addWidget(self.chk_manter)

        self.btn_remover_marcacoes = QPushButton("Remover marcações")
        lay.addWidget(self.btn_remover_marcacoes)

    def passo_unidade(self) -> float:
        try:
            return max(0.001, float(self.ed_passo.text().replace(",", ".").strip()))
        except Exception:
            return 2.0


class Ferramenta(FerramentaBase):
    id_ferramenta = "no_perimetro"
    nome = "No Perimetro"
    descricao_painel = ""
    usa_painel_auxiliar = False

    _dialog_global: PontosNoPerimetroDialog | None = None

    def __init__(self):
        super().__init__()
        self._idx_destaque: int | None = None
        self._pontos_preview: list[QPointF] = []
        self._segmentos_ativos: list[tuple[QPointF, QPointF]] = []
        self._inicio_dist: float | None = None
        self._ultimo_dist: float | None = None
        self._progresso_assinado = 0.0
        self._marcando = False

    def _obter_dialog(self, canvas) -> PontosNoPerimetroDialog:
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = Ferramenta._dialog_global
        if dialog is None or dialog.parentWidget() is not parent:
            if dialog is not None:
                dialog.close()
            dialog = PontosNoPerimetroDialog(parent)
            dialog.btn_remover_marcacoes.clicked.connect(lambda: self._remover_marcacoes(canvas))
            Ferramenta._dialog_global = dialog
        return dialog

    def _remover_marcacoes(self, canvas):
        idxs = sorted(getattr(canvas, "_selecionados", set()) or [])
        if not idxs:
            txt = "Indique o molde: selecione o molde antes de remover as marcações."
            self.set_status(txt)
            mensagem_status(canvas, txt)
            return
        idx = idxs[0]
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[idx]
        chaves = [
            "marcacoes_no_perimetro", "marcacoes_no_perimetro_config", "no_perimetro_marcacoes",
            "no_perimetro_config", "distancias_no_perimetro", "distancias_perimetro", "marcacoes_perimetro",
        ]
        tinha = any(ch in el for ch in chaves)
        if not tinha:
            txt = "O molde selecionado não possui marcações para remover."
            self.set_status(txt)
            mensagem_status(canvas, txt)
            return
        for ch in chaves:
            el.pop(ch, None)
        canvas._registrar_historico()
        self._pontos_preview = []
        self._marcando = False
        canvas._registrar_historico()
        canvas.update()
        txt = "Marcações removidas do molde selecionado."
        self.set_status(txt)
        mensagem_status(canvas, txt)

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._idx_destaque = None
        self._pontos_preview = []
        self._segmentos_ativos = []
        self._inicio_dist = None
        self._ultimo_dist = None
        self._progresso_assinado = 0.0
        self._marcando = False
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        texto = "No perímetro: 1º clique define início; mova no perímetro e 2º clique confirma."
        self.set_status(texto)
        mensagem_status(canvas, texto)


    def on_deactivate(self, canvas):
        super().on_deactivate(canvas)
        dialog = Ferramenta._dialog_global
        if dialog is not None:
            dialog.hide()

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

    def _dist_ao_longo_do_perimetro(self, pos: QPointF) -> float | None:
        if not self._segmentos_ativos:
            return None
        melhor = None
        acumulado = 0.0
        for a, b in self._segmentos_ativos:
            abx = b.x() - a.x()
            aby = b.y() - a.y()
            denom = (abx * abx) + (aby * aby)
            seg_len = self._dist(a, b)
            if seg_len <= 1e-9:
                continue
            if denom <= 1e-9:
                t = 0.0
            else:
                apx = pos.x() - a.x()
                apy = pos.y() - a.y()
                t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
            proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
            d = self._dist(proj, pos)
            val = acumulado + (seg_len * t)
            if melhor is None or d < melhor[0]:
                melhor = (d, val)
            acumulado += seg_len
        return None if melhor is None else float(melhor[1])

    def _perimetro_total(self) -> float:
        return sum(self._dist(a, b) for a, b in self._segmentos_ativos)

    def _ponto_por_distancia(self, distancia: float) -> QPointF | None:
        total = self._perimetro_total()
        if total <= 1e-9:
            return None
        d = distancia % total
        acumulado = 0.0
        for a, b in self._segmentos_ativos:
            seg_len = self._dist(a, b)
            if seg_len <= 1e-9:
                continue
            if acumulado + seg_len >= d - 1e-9:
                t = (d - acumulado) / seg_len
                return QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
            acumulado += seg_len
        return QPointF(self._segmentos_ativos[-1][1]) if self._segmentos_ativos else None

    def _pontos_por_progresso(self, inicio: float, progresso: float, passo: float) -> list[QPointF]:
        if passo <= 1e-9:
            return []
        qtd = int(abs(progresso) // passo)
        if qtd <= 0:
            return []
        direcao = 1.0 if progresso >= 0 else -1.0
        pts: list[QPointF] = []
        for i in range(1, qtd + 1):
            p = self._ponto_por_distancia(inicio + (direcao * passo * i))
            if p is not None:
                pts.append(p)
        return pts

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if info is None:
            return False

        idx = int(info["elemento_idx"])
        if not self._marcando:
            self._idx_destaque = idx
            canvas._selecionados = {idx}
            self._segmentos_ativos = segmentos_de_elemento(canvas.cena.elementos[idx])
            self._inicio_dist = self._dist_ao_longo_do_perimetro(pos)
            self._ultimo_dist = self._inicio_dist
            self._progresso_assinado = 0.0
            self._pontos_preview = []
            self._marcando = self._inicio_dist is not None
            texto = "Início marcado. Percorra o perímetro com o mouse e clique para confirmar."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            canvas.update()
            event.accept()
            return True

        if idx != self._idx_destaque:
            txt = "Confirme no mesmo elemento onde o início foi marcado."
            self.set_status(txt)
            mensagem_status(canvas, txt)
            return True

        self._confirmar_marcacoes(canvas)
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if not self._marcando or self._inicio_dist is None or self._idx_destaque is None:
            return False
        pos = canvas._ponto_com_snap(event.position())
        atual = self._dist_ao_longo_do_perimetro(pos)
        if atual is None:
            txt = "Mantenha o cursor sobre o perímetro do molde."
            self.set_status(txt)
            mensagem_status(canvas, txt)
            return True
        total = self._perimetro_total()
        if total <= 1e-9:
            return False
        if self._ultimo_dist is not None:
            delta = atual - self._ultimo_dist
            if delta > (total / 2.0):
                delta -= total
            elif delta < -(total / 2.0):
                delta += total
            self._progresso_assinado += delta
        self._ultimo_dist = atual

        dialog = self._obter_dialog(canvas)
        passo_u = dialog.passo_unidade()
        passo = canvas.converter_para_cena(passo_u) if hasattr(canvas, "converter_para_cena") else passo_u * max(1e-9, float(getattr(canvas, "_unidade_fator", 1.0)))
        self._pontos_preview = self._pontos_por_progresso(self._inicio_dist, self._progresso_assinado, passo)
        canvas.update()
        return True

    def _confirmar_marcacoes(self, canvas):
        if self._idx_destaque is None:
            return
        el = canvas.cena.elementos[self._idx_destaque]
        if dialog.chk_dividir.isChecked() and el.get("tipo") == "polyline":
            orig = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            el["pontos"] = [(p.x(), p.y()) for p in self._inserir_pontos_em_polyline(orig, self._pontos_preview)]
        el["marcacoes_no_perimetro"] = [(p.x(), p.y()) for p in self._pontos_preview]
        if dialog.chk_colocar.isChecked():
            atuais_cantos = list(el.get("controle_cantos", []))
            atuais_cantos.extend([(p.x(), p.y()) for p in self._pontos_preview])
            el["controle_cantos"] = atuais_cantos

            principais = list(el.get("pontos_controle_principais", []))
            base = dict(principais[0]) if principais else {"x": 0.0, "y": 0.0}
            for i, p in enumerate(self._pontos_preview, start=len(principais) + 1):
                d = dict(base)
                d["x"] = float(p.x())
                d["y"] = float(p.y())
                if "indice" in d:
                    d["indice"] = i
                principais.append(d)
            el["pontos_controle_principais"] = principais

        self._marcando = False
        self._inicio_dist = None
        self._ultimo_dist = None
        self._progresso_assinado = 0.0
        canvas._registrar_historico()
        txt = f"Marcação confirmada: {len(self._pontos_preview)} pontos."
        self.set_status(txt)
        mensagem_status(canvas, txt)
        canvas.update()

    def _inserir_pontos_em_polyline(self, pontos_orig: list[QPointF], inserir: list[QPointF]) -> list[QPointF]:
        if len(pontos_orig) < 2 or not inserir:
            return pontos_orig
        restantes = list(inserir)
        saida = [QPointF(pontos_orig[0])]
        for a, b in zip(pontos_orig, pontos_orig[1:]):
            seg_len = self._dist(a, b)
            if seg_len <= 1e-9:
                continue
            dentro = []
            sobrou = []
            for p in restantes:
                d1 = self._dist(a, p)
                d2 = self._dist(p, b)
                if abs((d1 + d2) - seg_len) <= 1e-3:
                    dentro.append((d1, p))
                else:
                    sobrou.append(p)
            restantes = sobrou
            for _, p in sorted(dentro, key=lambda x: x[0]):
                if self._dist(saida[-1], p) > 1e-6:
                    saida.append(QPointF(p))
            if self._dist(saida[-1], b) > 1e-9:
                saida.append(QPointF(b))
        return saida

    def on_paint_overlay(self, canvas, painter):
        if self._idx_destaque is None or not (0 <= self._idx_destaque < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[self._idx_destaque]
        if el.get("tipo") == "polyline":
            pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            for a, b in zip(pts, pts[1:]):
                canvas._desenhar_segmento(painter, a, b, cor="#2f8bff", espessura=2.0)

        pontos_persistidos = [QPointF(float(x), float(y)) for x, y in el.get("marcacoes_no_perimetro", []) or []]
        for p in pontos_persistidos:
            canvas._desenhar_marca_x(painter, p, cor="#ff2f2f", tamanho_px=5)
        for p in self._pontos_preview:
            canvas._desenhar_marca_x(painter, p, cor="#ffd100", tamanho_px=6)
