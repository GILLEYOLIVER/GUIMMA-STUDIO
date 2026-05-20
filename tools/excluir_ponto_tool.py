from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from tools.tool_base import FerramentaBase
from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos


class Ferramenta(FerramentaBase):
    id_ferramenta = "excluir_ponto"
    nome = "Excluir Ponto"
    descricao_painel = "Remove pontos de controle mantendo a geometria válida."

    def __init__(self):
        super().__init__()
        self._hover_alvo: tuple[str, int, str, int] | tuple[str, int, int] | None = None
        self._helper = FerramentaManipularPontos()

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover_alvo = None
        self.set_status("Clique sobre um ponto de controle para excluir.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())

        alvo_controle = self._controle_molde_em_ponto(canvas, pos)
        if alvo_controle is not None:
            idx, tipo, controle_idx = alvo_controle
            if not self._excluir_controle_molde(canvas, idx, tipo, controle_idx):
                return False
            canvas._selecionados = {idx}
            canvas._registrar_historico()
            canvas.update()
            self.set_status("Controle do molde excluído e contorno regenerado.")
            event.accept()
            return True

        alvo_curva = self._controle_curva_em_ponto(canvas, pos)
        if alvo_curva is not None:
            idx, controle_idx = alvo_curva
            if not self._excluir_controle_curva(canvas, idx, controle_idx):
                return False
            canvas._selecionados = {idx}
            canvas._registrar_historico()
            canvas.update()
            self.set_status("Ponto de controle da curva excluído.")
            event.accept()
            return True

        alvo = self._vertice_em_ponto(canvas, pos)
        if alvo is None:
            self.set_status("Nenhum ponto encontrado para exclusão.")
            return False
        idx, p_idx = alvo
        el = canvas.cena.elementos[idx]
        if el.get("molde"):
            self.set_status("Em moldes, exclua apenas cantos/auxiliares oficiais, não pontos da amostra.")
            return False

        pontos = list(el.get("pontos", []))
        if len(pontos) <= 2:
            self.set_status("Elemento com poucos pontos: não é possível excluir.")
            return False

        fechado = (
            len(pontos) >= 3
            and abs(float(pontos[0][0]) - float(pontos[-1][0])) < 1e-9
            and abs(float(pontos[0][1]) - float(pontos[-1][1])) < 1e-9
        )
        if fechado and p_idx in {0, len(pontos) - 1}:
            ponto_removido = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            pontos.pop(0)
            if pontos:
                pontos[-1] = pontos[0]
        else:
            ponto_removido = QPointF(float(pontos[p_idx][0]), float(pontos[p_idx][1]))
            pontos.pop(p_idx)
            if fechado and pontos:
                pontos[-1] = pontos[0]

        if len(pontos) < 2:
            self.set_status("Exclusão cancelada para evitar geometria inválida.")
            return False

        el["pontos"] = pontos
        self._sincronizar_curva_livre(el, ponto_removido)
        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self.set_status("Ponto excluído com sucesso.")
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        alvo_controle = self._controle_molde_em_ponto(canvas, pos)
        if alvo_controle is not None:
            idx, tipo, controle_idx = alvo_controle
            self._hover_alvo = ("molde", idx, tipo, controle_idx)
        else:
            alvo_curva = self._controle_curva_em_ponto(canvas, pos)
            if alvo_curva is not None:
                idx, controle_idx = alvo_curva
                self._hover_alvo = ("curva", idx, controle_idx)
            else:
                alvo_vertice = self._vertice_em_ponto(canvas, pos)
                if alvo_vertice is not None:
                    idx, ponto_idx = alvo_vertice
                    self._hover_alvo = ("vertice", idx, ponto_idx)
                else:
                    self._hover_alvo = None
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        ponto = self._ponto_hover(canvas)
        if ponto is None:
            return
        tela = canvas._cena_para_tela(ponto)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#ffffff"), 1.2))
        painter.setBrush(QColor("#ff3030"))
        painter.drawEllipse(int(tela.x() - 6), int(tela.y() - 6), 12, 12)
        painter.setPen(QPen(QColor("#ffffff"), 1.6))
        painter.drawLine(int(tela.x() - 4), int(tela.y() - 4), int(tela.x() + 4), int(tela.y() + 4))
        painter.drawLine(int(tela.x() - 4), int(tela.y() + 4), int(tela.x() + 4), int(tela.y() - 4))
        painter.restore()

    def _ponto_hover(self, canvas) -> QPointF | None:
        if self._hover_alvo is None:
            return None
        kind = self._hover_alvo[0]
        if kind == "molde":
            _, idx, tipo, controle_idx = self._hover_alvo
            if not (0 <= idx < len(canvas.cena.elementos)):
                return None
            chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
            controles = canvas.cena.elementos[idx].get(chave, []) or []
            if 0 <= controle_idx < len(controles):
                return self._ponto_qt(controles[controle_idx])
        if kind == "curva":
            _, idx, controle_idx = self._hover_alvo
            if not (0 <= idx < len(canvas.cena.elementos)):
                return None
            controles = self._controles_curva(canvas.cena.elementos[idx])
            if 0 <= controle_idx < len(controles):
                return controles[controle_idx]
        if kind == "vertice":
            _, idx, ponto_idx = self._hover_alvo
            if not (0 <= idx < len(canvas.cena.elementos)):
                return None
            pontos = canvas.cena.elementos[idx].get("pontos", []) or []
            if 0 <= ponto_idx < len(pontos):
                return self._ponto_qt(pontos[ponto_idx])
        return None

    # ------------------------------------------------------------------
    # Moldes: controle_cantos/controle_auxiliares são a autoridade.
    # ------------------------------------------------------------------
    def _controle_molde_em_ponto(self, canvas, pos: QPointF) -> tuple[int, str, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, str, int] | None = None
        melhor_d = tolerancia
        for idx, el in enumerate(canvas.cena.elementos):
            if el.get("tipo") != "polyline" or not el.get("molde"):
                continue
            for tipo, chave in (("canto", "controle_cantos"), ("aux", "controle_auxiliares")):
                for c_idx, item in enumerate(el.get(chave, []) or []):
                    pt = self._ponto_qt(item)
                    if pt is None:
                        continue
                    d = canvas._dist(pt, pos)
                    if d <= melhor_d:
                        melhor_d = d
                        melhor = (idx, tipo, c_idx)
        return melhor

    def _excluir_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            return False

        chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
        controles = list(el.get(chave, []) or [])
        if not (0 <= controle_idx < len(controles)):
            self.set_status("Controle inválido para exclusão.")
            return False

        if tipo == "canto" and len(el.get("controle_cantos", []) or []) <= 2:
            self.set_status("O molde precisa manter pelo menos 2 cantos.")
            return False

        controles.pop(controle_idx)
        el[chave] = [self._tupla_xy(item) for item in controles if self._tupla_xy(item) is not None]
        el["_controles_topologia_alterada"] = True
        if not self._regenerar_molde_por_controles(canvas, el):
            self.set_status("Exclusão cancelada: não foi possível regenerar o contorno.")
            return False
        return True

    def _regenerar_molde_por_controles(self, canvas, el: dict) -> bool:
        return self._helper._regenerar_molde_por_controles(canvas, el)

    def _regenerar_molde_por_controles_legado(self, canvas, el: dict) -> bool:
        cantos = [pt for item in el.get("controle_cantos", []) or [] if (pt := self._ponto_qt(item)) is not None]
        if len(cantos) < 2:
            return False
        auxiliares = [pt for item in el.get("controle_auxiliares", []) or [] if (pt := self._ponto_qt(item)) is not None]
        pontos_anteriores = list(el.get("pontos", []) or [])
        fechado = self._molde_fechado(canvas, el, pontos_anteriores, cantos)
        segmentos = [(i, (i + 1) % len(cantos)) for i in range(len(cantos))] if fechado else [(i, i + 1) for i in range(len(cantos) - 1)]
        if not segmentos:
            return False

        atribuicoes = self._atribuir_auxiliares(cantos, segmentos, auxiliares)
        novos: list[tuple[float, float]] = []
        for ordem, (a_idx, b_idx) in enumerate(segmentos):
            a = cantos[a_idx]
            b = cantos[b_idx]
            controles = [a, *atribuicoes.get(ordem, []), b]
            trecho = self._amostrar_trecho(controles, segmentos=24)
            if not trecho:
                continue
            if novos:
                trecho = trecho[1:]
            novos.extend((float(p.x()), float(p.y())) for p in trecho)

        if fechado and novos:
            if self._dist_local(QPointF(*novos[0]), QPointF(*novos[-1])) > 1e-6:
                novos.append(novos[0])
            else:
                novos[-1] = novos[0]
        if len(novos) < 2:
            return False

        el["pontos"] = novos
        el["controle_cantos"] = [(float(p.x()), float(p.y())) for p in cantos]
        el["controle_auxiliares"] = [(float(p.x()), float(p.y())) for p in auxiliares]
        el["pontos_controle_principais"] = [{"x": float(p.x()), "y": float(p.y())} for p in cantos]
        el["pontos_auxiliares"] = [{"x": float(p.x()), "y": float(p.y())} for p in auxiliares]
        return True

    def _molde_fechado(self, canvas, el: dict, pontos: list, cantos: list[QPointF]) -> bool:
        if bool(el.get("fechado")):
            return True
        if len(pontos) >= 3:
            p0 = self._ponto_qt(pontos[0])
            pn = self._ponto_qt(pontos[-1])
            if p0 is not None and pn is not None and canvas._dist(p0, pn) <= 1e-6:
                return True
        return len(cantos) >= 3

    def _atribuir_auxiliares(self, cantos: list[QPointF], segmentos: list[tuple[int, int]], auxiliares: list[QPointF]) -> dict[int, list[QPointF]]:
        saida: dict[int, list[tuple[float, QPointF]]] = {i: [] for i in range(len(segmentos))}
        for aux in auxiliares:
            melhor_seg: int | None = None
            melhor_t = 0.0
            melhor_d = float("inf")
            for ordem, (a_idx, b_idx) in enumerate(segmentos):
                a = cantos[a_idx]
                b = cantos[b_idx]
                t = self._parametro_segmento(aux, a, b)
                proj = QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
                d = self._dist_local(aux, proj)
                if d < melhor_d:
                    melhor_d = d
                    melhor_seg = ordem
                    melhor_t = t
            if melhor_seg is not None:
                saida[melhor_seg].append((melhor_t, QPointF(aux)))
        return {idx: [pt for _t, pt in sorted(valores, key=lambda item: item[0])] for idx, valores in saida.items()}

    def _amostrar_trecho(self, controles: list[QPointF], segmentos: int = 24) -> list[QPointF]:
        pts = [QPointF(p) for p in controles]
        if len(pts) <= 2:
            return pts
        if len(pts) == 3:
            return [QPointF(pts[0]), QPointF(pts[-1])]
        saida: list[QPointF] = []
        total = len(pts)
        for i in range(total - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2] if i + 2 < total else p2
            if i == 0:
                saida.append(QPointF(p1))
            for s in range(1, 13):
                saida.append(self._catmull_rom(p0, p1, p2, p3, s / 12.0))
        return self._garantir_controles_no_trecho(self._limitar_envelope(saida, pts), pts)

    def _garantir_controles_no_trecho(self, pontos: list[QPointF], controles: list[QPointF]) -> list[QPointF]:
        saida = [QPointF(p) for p in pontos]
        for ctrl in controles:
            assinatura = (round(ctrl.x(), 7), round(ctrl.y(), 7))
            if any((round(p.x(), 7), round(p.y(), 7)) == assinatura for p in saida):
                continue
            if not saida:
                saida.append(QPointF(ctrl))
                continue
            melhor = min(range(len(saida)), key=lambda i: self._dist_local(saida[i], ctrl))
            if melhor <= 0:
                saida.insert(0, QPointF(ctrl))
            elif melhor >= len(saida) - 1:
                saida.append(QPointF(ctrl))
            else:
                saida.insert(melhor + 1, QPointF(ctrl))
        return saida

    def _limitar_envelope(self, pontos: list[QPointF], controles: list[QPointF]) -> list[QPointF]:
        if len(pontos) < 3 or len(controles) < 2:
            return pontos
        xs = [p.x() for p in controles]
        ys = [p.y() for p in controles]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        margem_x = max(0.001, (max_x - min_x) * 0.015)
        margem_y = max(0.001, (max_y - min_y) * 0.015)
        controles_sig = {(round(p.x(), 7), round(p.y(), 7)) for p in controles}
        out: list[QPointF] = []
        for p in pontos:
            sig = (round(p.x(), 7), round(p.y(), 7))
            if sig in controles_sig:
                out.append(QPointF(p))
            else:
                out.append(QPointF(max(min_x - margem_x, min(max_x + margem_x, p.x())), max(min_y - margem_y, min(max_y + margem_y, p.y()))))
        return out

    @staticmethod
    def _controle_quadratico_passando_por_meio(a: QPointF, meio: QPointF, b: QPointF) -> QPointF:
        return QPointF((2.0 * meio.x()) - (0.5 * a.x()) - (0.5 * b.x()), (2.0 * meio.y()) - (0.5 * a.y()) - (0.5 * b.y()))

    @staticmethod
    def _catmull_rom(p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        t2 = t * t
        t3 = t2 * t
        x = 0.5 * ((2.0 * p1.x()) + (-p0.x() + p2.x()) * t + (2.0 * p0.x() - 5.0 * p1.x() + 4.0 * p2.x() - p3.x()) * t2 + (-p0.x() + 3.0 * p1.x() - 3.0 * p2.x() + p3.x()) * t3)
        y = 0.5 * ((2.0 * p1.y()) + (-p0.y() + p2.y()) * t + (2.0 * p0.y() - 5.0 * p1.y() + 4.0 * p2.y() - p3.y()) * t2 + (-p0.y() + 3.0 * p1.y() - 3.0 * p2.y() + p3.y()) * t3)
        return QPointF(x, y)

    @staticmethod
    def _parametro_segmento(p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-12:
            return 0.0
        t = ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / denom
        return max(0.0, min(1.0, t))

    @staticmethod
    def _dist_local(a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return (dx * dx + dy * dy) ** 0.5

    # ------------------------------------------------------------------
    # Elementos livres: comportamento antigo mantido.
    # ------------------------------------------------------------------
    def _vertice_em_ponto(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int] | None = None
        melhor_d = tolerancia
        for idx, el in enumerate(canvas.cena.elementos):
            if el.get("tipo") != "polyline" or el.get("molde"):
                continue
            if self._curva_editavel(el):
                continue
            for p_idx, item in enumerate(el.get("pontos", []) or []):
                pt = self._ponto_qt(item)
                if pt is None:
                    continue
                d = canvas._dist(pt, pos)
                if d <= melhor_d:
                    melhor_d = d
                    melhor = (idx, p_idx)
        return melhor

    def _controle_curva_em_ponto(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int] | None = None
        melhor_d = tolerancia
        for idx, el in enumerate(canvas.cena.elementos):
            if el.get("tipo") != "polyline" or el.get("molde") or not self._curva_editavel(el):
                continue
            for controle_idx, pt in enumerate(self._controles_curva(el)):
                d = canvas._dist(pt, pos)
                if d <= melhor_d:
                    melhor_d = d
                    melhor = (idx, controle_idx)
        return melhor

    def _excluir_controle_curva(self, canvas, idx: int, controle_idx: int) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        controles = self._controles_curva(el)
        if not (0 <= controle_idx < len(controles)):
            self.set_status("Controle inválido para exclusão.")
            return False
        fechado = self._fechado_por_pontos(canvas, el.get("pontos", []) or [])
        minimo = 3 if fechado else 2
        if len(controles) <= minimo:
            self.set_status("A curva precisa manter pontos suficientes para continuar válida.")
            return False
        controles.pop(controle_idx)
        tipo_curva = str(el.get("tipo_curva") or "spline_catmull_rom")
        el["pontos"] = self._helper._gerar_tracado_curva_real(controles, fechado=fechado, tipo_curva=tipo_curva)
        self._helper._salvar_controles_curva_real(el, controles)
        el["fechado"] = fechado
        return len(el.get("pontos", []) or []) >= 2

    def _curva_editavel(self, el: dict) -> bool:
        return bool(el.get("pontos_tracado_real") or el.get("curva_editavel") or el.get("pontos_principais") or el.get("pontos_controle_curva"))

    def _controles_curva(self, el: dict) -> list[QPointF]:
        origem = el.get("pontos_principais") or el.get("pontos_controle_curva") or el.get("pontos_controle_principais") or []
        controles = [self._ponto_qt(p) for p in origem]
        return [p for p in controles if p is not None]

    def _fechado_por_pontos(self, canvas, pontos: list) -> bool:
        if len(pontos) < 3:
            return False
        p0 = self._ponto_qt(pontos[0])
        pn = self._ponto_qt(pontos[-1])
        return p0 is not None and pn is not None and canvas._dist(p0, pn) <= 1e-6

    def _sincronizar_curva_livre(self, el: dict, removido: QPointF) -> None:
        if not (
            el.get("curva_suave")
            or el.get("curva_editavel")
            or el.get("pontos_controle_curva")
            or el.get("pontos_principais")
        ):
            return
        tolerancia = 1e-6
        for chave in ("pontos_controle_curva", "pontos_principais", "pontos_controle", "pontos_controle_principais"):
            origem = el.get(chave)
            if not isinstance(origem, list):
                continue
            filtrados = []
            for item in origem:
                pt = self._ponto_qt(item)
                if pt is None:
                    continue
                if self._dist_local(pt, removido) <= tolerancia:
                    continue
                filtrados.append((pt.x(), pt.y()))
            el[chave] = filtrados

    @staticmethod
    def _tupla_xy(p) -> tuple[float, float] | None:
        pt = Ferramenta._ponto_qt(p)
        if pt is None:
            return None
        return (float(pt.x()), float(pt.y()))

    @staticmethod
    def _ponto_qt(p) -> QPointF | None:
        try:
            if isinstance(p, QPointF):
                return QPointF(p)
            if isinstance(p, dict):
                return QPointF(float(p["x"]), float(p["y"]))
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                return QPointF(float(p[0]), float(p[1]))
        except Exception:
            return None
        return None
