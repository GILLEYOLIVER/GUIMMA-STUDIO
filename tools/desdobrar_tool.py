from __future__ import annotations

from math import isfinite
from time import monotonic

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.dobrar_tool import Ferramenta as _DobrarBase


class Ferramenta(_DobrarBase):
    id_ferramenta = "desdobrar"
    nome = "Desdobrar"
    usa_painel_auxiliar = False
    descricao_painel = "Desdobra um molde usando uma linha interna como eixo."

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._hover_idx: int | None = None
        self._ultimo_direito = 0.0

    def on_activate(self, canvas):
        self._resetar_desdobrar(canvas, limpar_selecao=False)
        self._status(canvas, "Desdobrar: clique em um molde. Depois passe o mouse em uma linha interna e clique para desdobrar.")

    def on_deactivate(self, canvas):
        self._resetar_desdobrar(canvas, limpar_selecao=False)
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._molde_idx is not None:
                self._resetar_desdobrar(canvas, limpar_selecao=True)
                self._status(canvas, "Desdobrar cancelado. Clique em um molde para começar novamente.")
                event.accept()
                return True
            agora = monotonic()
            if agora - self._ultimo_direito <= 0.45:
                canvas.set_ferramenta_ativa("selecionar")
                self._status(canvas, "Ferramenta Desdobrar finalizada. Voltando para Selecionar.")
            else:
                self._status(canvas, "Clique direito novamente para finalizar Desdobrar.")
            self._ultimo_direito = agora
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        if self._molde_idx is None:
            molde_idx = canvas._indice_molde_em_ponto(pos) if hasattr(canvas, "_indice_molde_em_ponto") else None
            if molde_idx is None:
                self._status(canvas, "Desdobrar: clique sobre um molde primeiro.")
                event.accept()
                return True
            self._molde_idx = int(molde_idx)
            canvas._selecionados = {self._molde_idx}
            self._hover_idx = None
            canvas.update()
            self._status(canvas, "Molde selecionado. Passe o mouse sobre uma linha interna para escolher o eixo.")
            event.accept()
            return True

        alvo = self._hover_idx
        if alvo is None:
            alvo = self._linha_interna_em_ponto(canvas, self._molde_idx, pos)
        if alvo is None:
            self._status(canvas, "Passe o mouse sobre uma linha interna do molde e clique para desdobrar.")
            event.accept()
            return True
        self._aplicar_desdobrar(canvas, self._molde_idx, int(alvo))
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._molde_idx is None:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._hover_idx = self._linha_interna_em_ponto(canvas, self._molde_idx, pos)
        canvas.update()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._molde_idx is None or self._hover_idx is None:
            return
        if not (0 <= self._hover_idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[self._hover_idx]
        pontos = self._pontos_para_preview_linha(el)
        if len(pontos) < 2:
            return
        painter.save()
        cor = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        painter.setPen(QPen(cor, 2.2, Qt.SolidLine))
        for a, b in zip(pontos, pontos[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def _aplicar_desdobrar(self, canvas, molde_idx: int, linha_idx: int) -> None:
        if not (0 <= molde_idx < len(canvas.cena.elementos)):
            return
        if not (0 <= linha_idx < len(canvas.cena.elementos)):
            return
        molde = canvas.cena.elementos[molde_idx]
        linha = canvas.cena.elementos[linha_idx]
        eixo = self._eixo_linha(linha)
        if eixo is None:
            self._status(canvas, "A linha escolhida não tem extremidades válidas para desdobrar.")
            return
        pontos = self._pontos_elemento(molde)
        if len(pontos) < 3:
            self._status(canvas, "Molde sem contorno suficiente para desdobrar.")
            return
        base = pontos[:-1] if self._pontos_mesmos(pontos[0], pontos[-1]) else list(pontos)
        espelhado = [self._espelhar_ponto(p, eixo) for p in base]
        unidos = self._unir_poligonos(base, espelhado)
        if len(unidos) < 3:
            self._status(canvas, "Não foi possível formar o contorno desdobrado.")
            return
        if not self._pontos_mesmos(unidos[0], unidos[-1]):
            unidos.append(QPointF(unidos[0]))
        molde["pontos"] = [(p.x(), p.y()) for p in unidos]
        cantos = unidos[:-1] if self._pontos_mesmos(unidos[0], unidos[-1]) else unidos
        molde["controle_cantos"] = [(p.x(), p.y()) for p in cantos]
        molde["pontos_controle_referencia"] = [(p.x(), p.y()) for p in cantos]
        molde["molde_dobrado"] = False
        molde["dobra_horizontal"] = False
        molde["dobra_vertical"] = False
        molde.pop("contornos_dobra_original", None)
        molde.setdefault("metadados", {})["ultima_transformacao"] = "desdobrar"
        canvas._selecionados = {molde_idx}
        canvas._registrar_historico()
        self._resetar_desdobrar(canvas, limpar_selecao=False)
        canvas._selecionados = {molde_idx}
        canvas.update()
        self._status(canvas, "Molde desdobrado pela linha escolhida. A ferramenta continua ativa.")

    def _linha_interna_em_ponto(self, canvas, molde_idx: int, pos: QPointF) -> int | None:
        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        for idx in candidatos:
            if idx == molde_idx or not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if self._eh_linha_interna_do_molde(canvas, molde_idx, el):
                return int(idx)
        return None

    def _eh_linha_interna_do_molde(self, canvas, molde_idx: int, el: dict) -> bool:
        if not isinstance(el, dict) or el.get("molde"):
            return False
        if el.get("tipo") not in {"polyline", "bezier_quadratica"}:
            return False
        subtipo = str(el.get("subtipo_audaces") or el.get("metadados", {}).get("subtipo_audaces") or "").strip()
        if subtipo in {"contorno", "costura"} or el.get("costura_de_molde_id"):
            return False
        molde = canvas.cena.elementos[molde_idx]
        molde_id = str(molde.get("molde_id") or molde.get("id") or "").strip()
        el_molde_id = str(el.get("molde_id") or "").strip()
        if molde_id and el_molde_id == molde_id:
            return True
        if bool(el.get("molde_linha_vinculada")) and molde_id and el_molde_id == molde_id:
            return True
        pontos = self._pontos_para_preview_linha(el)
        if not pontos:
            return False
        return any(self._ponto_dentro_molde(molde, p) for p in pontos)

    def _eixo_linha(self, el: dict):
        if el.get("tipo") == "bezier_quadratica":
            p0 = el.get("p0")
            p2 = el.get("p2")
            if self._eh_ponto(p0) and self._eh_ponto(p2):
                return ("line", QPointF(float(p0[0]), float(p0[1])), QPointF(float(p2[0]), float(p2[1])))
            return None
        pontos = self._pontos_elemento(el)
        if len(pontos) >= 2:
            return ("line", QPointF(pontos[0]), QPointF(pontos[-1]))
        return None

    def _pontos_para_preview_linha(self, el: dict) -> list[QPointF]:
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

    def _resetar_desdobrar(self, canvas, limpar_selecao: bool) -> None:
        self._molde_idx = None
        self._hover_idx = None
        if limpar_selecao:
            canvas._selecionados = set()
        canvas.update()

    @staticmethod
    def _bezier(p0: QPointF, p1: QPointF, p2: QPointF, t: float) -> QPointF:
        u = 1.0 - t
        return QPointF(
            (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x()),
            (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y()),
        )

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False
