from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, degrees, isfinite, radians, sin, sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from core.formatacao import formatar_numero
from tools.movimento_utils import mover_elemento_por_delta, rotacionar_elemento_por_funcao
from tools.preview_original_utils import desenhar_elementos_originais
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "selecionar"
    nome = "Selecionar"
    usa_painel_auxiliar = False
    descricao_painel = "Selecione elementos com clique, caixa de seleção e ciclo com botão direito."
    DISTANCIA_VISUAL_SELECAO_CM = 1.5

    def __init__(self):
        super().__init__()
        self._inicio_caixa: QPointF | None = None
        self._fim_caixa: QPointF | None = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto: QPointF | None = None
        self._movido = False
        self._hover_idx: int | None = None
        self._originais_arraste: dict[int, dict] = {}
        self._alinhamento_duplo_molde: dict[tuple[int, int], dict] = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._inicio_caixa = None
        self._fim_caixa = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto = None
        self._movido = False
        self._hover_idx = None
        self._originais_arraste = {}
        self.set_status("Clique para selecionar. Arraste para seleção por área. RMB cicla sobrepostos.")

    def on_mouse_press(self, canvas, event) -> bool:
        # Para selecionar curvas suaves, o teste precisa usar primeiro o ponto real
        # do mouse sem snap. Se usar só o ponto com snap, o cursor pode ser puxado
        # para um nó/controle e ficar longe do traçado visual da curva.
        pos_sem_snap = canvas._tela_para_cena(event.position())
        pos_snap = canvas._ponto_com_snap(event.position())

        if event.button() == Qt.RightButton:
            if canvas._selecionar_proximo_em_ponto(pos_sem_snap) or canvas._selecionar_proximo_em_ponto(pos_snap):
                self.set_status("Elemento alternado com botão direito.")
                event.accept()
                return True
            indices_curva = self._indices_elementos_em_ponto(canvas, pos_sem_snap)
            if not indices_curva:
                indices_curva = self._indices_elementos_em_ponto(canvas, pos_snap)
            if indices_curva:
                canvas._selecionados = {indices_curva[0]}
                self.set_status("Elemento alternado com botão direito.")
                canvas.update()
                event.accept()
                return True
            if canvas._snap_resultado and canvas._snap_resultado.elemento_idx is not None:
                idx_snap = int(canvas._snap_resultado.elemento_idx)
                if 0 <= idx_snap < len(canvas.cena.elementos):
                    canvas._selecionados = {idx_snap}
                    self.set_status("Elemento alternado via snap.")
                    canvas.update()
                    event.accept()
                    return True
            return False
        if event.button() != Qt.LeftButton:
            return False

        indices = self._indices_elementos_em_ponto(canvas, pos_sem_snap)
        if not indices:
            indices = self._indices_elementos_em_ponto(canvas, pos_snap)
        if not indices and canvas._snap_resultado and canvas._snap_resultado.elemento_idx is not None:
            idx_snap = int(canvas._snap_resultado.elemento_idx)
            if 0 <= idx_snap < len(canvas.cena.elementos):
                indices = [idx_snap]
        if indices:
            selecionado = indices[0]
            if event.modifiers() & Qt.ShiftModifier:
                if selecionado in canvas._selecionados:
                    canvas._selecionados.remove(selecionado)
                else:
                    canvas._selecionados.add(selecionado)
                self._arrastando_selecao = False
                self._ultimo_ponto_arrasto = None
                self._originais_arraste = {}
            else:
                if selecionado not in canvas._selecionados:
                    canvas._selecionados = {selecionado}
                self._arrastando_selecao = True
                self._ultimo_ponto_arrasto = pos_snap
                self._movido = False
                self._originais_arraste = self._capturar_originais(canvas, self._indices_para_mover(canvas))
            self._inicio_caixa = None
            self._fim_caixa = None
            self.set_status(f"{len(canvas._selecionados)} elemento(s) selecionado(s).")
            canvas.update()
            event.accept()
            return True

        if not (event.modifiers() & Qt.ShiftModifier):
            canvas._selecionados.clear()
        self._inicio_caixa = pos_sem_snap
        self._fim_caixa = pos_sem_snap
        self.set_status("Arraste para selecionar por área.")
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos_sem_snap = canvas._tela_para_cena(event.position())
        if self._arrastando_selecao and self._ultimo_ponto_arrasto is not None:
            pos = self._ponto_movimento(canvas, event)
            self._hover_idx = None
            dx = pos.x() - self._ultimo_ponto_arrasto.x()
            dy = pos.y() - self._ultimo_ponto_arrasto.y()
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                self._mover_selecionados(canvas, dx, dy)
                self._ultimo_ponto_arrasto = pos
                self._movido = True
            snap_info = f" | {canvas.descricao_snap_atual()}" if hasattr(canvas, "descricao_snap_atual") and canvas.descricao_snap_atual() else ""
            self.set_status(f"Movendo seleção ({len(canvas._selecionados)} elemento(s)){snap_info}")
            canvas.update()
            event.accept()
            return True

        pos_snap = canvas._ponto_com_snap(event.position())
        self._hover_idx = (self._indices_elementos_em_ponto(canvas, pos_sem_snap) or self._indices_elementos_em_ponto(canvas, pos_snap) or [None])[0]
        if self._inicio_caixa is None:
            if canvas.lbl_status:
                snap_info = f" | {canvas.descricao_snap_atual()}" if hasattr(canvas, "descricao_snap_atual") and canvas.descricao_snap_atual() else ""
                x_txt = formatar_numero(pos_sem_snap.x(), 2)
                y_txt = formatar_numero(pos_sem_snap.y(), 2)
                canvas.lbl_status.setText(f"Selecionar | X {x_txt} Y {y_txt}{snap_info}")
                self.set_status(f"Cursor X {x_txt} Y {y_txt}{snap_info}")
            canvas.update()
            return True
        self._fim_caixa = pos_sem_snap
        canvas.update()
        event.accept()
        return True

    def _ponto_movimento(self, canvas, event) -> QPointF:
        ignorar = self._indices_para_mover(canvas)
        if hasattr(canvas, "_ponto_com_snap_movimento"):
            return canvas._ponto_com_snap_movimento(
                event.position(),
                ignorar_elementos=ignorar,
                elementos_sombra=self._originais_arraste,
            )
        return canvas._ponto_com_snap(event.position())

    def _indices_elementos_em_ponto(self, canvas, pos: QPointF) -> list[int]:
        indices: list[int] = []
        try:
            indices = list(canvas._indices_elementos_em_ponto(pos) or [])
        except Exception:
            indices = []

        existentes = set(indices)
        tolerancia = max(18.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001), 0.18)

        # A seleção nativa pega bem polylines retas. Para curvas suaves, como as
        # criadas por Curvas e Espirais, o desenho real é interpolado entre os
        # pontos de controle. Por isso o clique precisa testar a curva amostrada,
        # não só a corda reta entre os controles.
        extras: list[tuple[int, float]] = []
        for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
            if idx in existentes:
                continue
            el = canvas.cena.elementos[idx]
            pontos = self._pontos_elemento_para_selecao(canvas, el)
            if len(pontos) < 2:
                continue
            melhor = self._distancia_ponto_polyline(pos, pontos)
            if melhor <= tolerancia:
                extras.append((idx, melhor))

        extras.sort(key=lambda item: item[1])
        for idx, _distancia in extras:
            if idx not in existentes:
                indices.append(idx)
                existentes.add(idx)
        return indices

    def _pontos_elemento_para_selecao(self, canvas, el: dict) -> list[QPointF]:
        if not isinstance(el, dict):
            return []
        subtipo = str(el.get("subtipo_audaces") or el.get("metadados", {}).get("subtipo_audaces") or "").strip()
        if subtipo == "costura" or el.get("costura_de_molde_id"):
            return []
        if el.get("tipo") == "polyline":
            pontos_base = self._pontos_polyline(el)
            if self._elemento_curva_suave(canvas, el) and len(pontos_base) >= 3:
                return self._amostrar_curva_suave(pontos_base, amostras=28)
            return pontos_base
        if el.get("tipo") == "bezier_quadratica":
            try:
                p0 = QPointF(*el["p0"])
                p1 = QPointF(*el["p1"])
                p2 = QPointF(*el["p2"])
                if hasattr(canvas, "_amostrar_bezier_quadratica"):
                    return canvas._amostrar_bezier_quadratica(p0, p1, p2, segmentos=64)
                return [p0, p1, p2]
            except Exception:
                return []
        return []

    @staticmethod
    def _elemento_curva_suave(canvas, el: dict) -> bool:
        if hasattr(canvas, "_elemento_curva_suave"):
            try:
                return bool(canvas._elemento_curva_suave(el))
            except Exception:
                pass
        return bool(
            el.get("curva_suave")
            or el.get("suavizar")
            or str(el.get("tipo_curva") or "").lower().startswith("spline")
            or str(el.get("renderizacao") or "").lower() == "curva_suave"
            or str(el.get("subtipo_audaces") or "").lower() == "curva_predefinida"
            or str(el.get("nome_curva_predefinida") or "").strip()
        )

    @staticmethod
    def _qpoint_item(item) -> QPointF | None:
        try:
            if isinstance(item, dict):
                return QPointF(float(item.get("x", 0.0)), float(item.get("y", 0.0)))
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                return QPointF(float(item[0]), float(item[1]))
        except Exception:
            return None
        return None

    def _pontos_polyline(self, el: dict) -> list[QPointF]:
        pontos: list[QPointF] = []
        origem = (
            el.get("pontos")
            or el.get("pontos_controle_curva")
            or el.get("pontos_principais")
            or el.get("pontos_controle")
            or []
        )
        for item in origem:
            pt = self._qpoint_item(item)
            if pt is not None:
                pontos.append(pt)
        return pontos

    @staticmethod
    def _amostrar_curva_suave(controles: list[QPointF], amostras: int = 28) -> list[QPointF]:
        if len(controles) < 3:
            return [QPointF(p) for p in controles]
        fechado = len(controles) > 3 and Ferramenta._dist_qp(controles[0], controles[-1]) <= 1e-7
        pts = [QPointF(p) for p in (controles[:-1] if fechado else controles)]
        total = len(pts)
        if total < 3:
            return [QPointF(p) for p in controles]
        saida: list[QPointF] = []
        limite = total if fechado else total - 1
        for i in range(limite):
            p0 = pts[(i - 1) % total] if fechado or i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[(i + 1) % total]
            p3 = pts[(i + 2) % total] if fechado or i + 2 < total else p2
            for j in range(amostras):
                t = j / float(amostras)
                t2 = t * t
                t3 = t2 * t
                x = 0.5 * (
                    (2.0 * p1.x())
                    + (-p0.x() + p2.x()) * t
                    + (2.0 * p0.x() - 5.0 * p1.x() + 4.0 * p2.x() - p3.x()) * t2
                    + (-p0.x() + 3.0 * p1.x() - 3.0 * p2.x() + p3.x()) * t3
                )
                y = 0.5 * (
                    (2.0 * p1.y())
                    + (-p0.y() + p2.y()) * t
                    + (2.0 * p0.y() - 5.0 * p1.y() + 4.0 * p2.y() - p3.y()) * t2
                    + (-p0.y() + 3.0 * p1.y() - 3.0 * p2.y() + p3.y()) * t3
                )
                saida.append(QPointF(x, y))
        if fechado and saida:
            saida.append(QPointF(saida[0]))
        elif not fechado:
            saida.append(QPointF(pts[-1]))
        return saida

    @staticmethod
    def _dist_qp(a: QPointF, b: QPointF) -> float:
        return sqrt(((a.x() - b.x()) ** 2) + ((a.y() - b.y()) ** 2))

    def _distancia_ponto_polyline(self, pos: QPointF, pontos: list[QPointF]) -> float:
        melhor = float("inf")
        for a, b in zip(pontos, pontos[1:]):
            melhor = min(melhor, self._distancia_ponto_segmento(pos, a, b))
        return melhor

    @staticmethod
    def _distancia_ponto_segmento(p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return sqrt((p.x() - a.x()) ** 2 + (p.y() - a.y()) ** 2)
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / den))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return sqrt((p.x() - proj.x()) ** 2 + (p.y() - proj.y()) ** 2)

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() == Qt.LeftButton and self._arrastando_selecao:
            self._arrastando_selecao = False
            self._ultimo_ponto_arrasto = None
            self._originais_arraste = {}
            if self._movido:
                canvas._registrar_historico()
                self.set_status(f"Movimento concluído ({len(canvas._selecionados)} elemento(s)).")
            self._movido = False
            canvas.update()
            event.accept()
            return True
        if event.button() != Qt.LeftButton or self._inicio_caixa is None or self._fim_caixa is None:
            return False
        x1 = min(self._inicio_caixa.x(), self._fim_caixa.x())
        y1 = min(self._inicio_caixa.y(), self._fim_caixa.y())
        x2 = max(self._inicio_caixa.x(), self._fim_caixa.x())
        y2 = max(self._inicio_caixa.y(), self._fim_caixa.y())

        if sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) > (4.0 / max(canvas.zoom, 0.001)):
            selecionados_area: set[int] = set()
            for idx, el in enumerate(canvas.cena.elementos):
                pontos = self._pontos_elemento_para_selecao(canvas, el)
                if pontos and all(x1 <= p.x() <= x2 and y1 <= p.y() <= y2 for p in pontos):
                    selecionados_area.add(idx)
            if event.modifiers() & Qt.ShiftModifier:
                canvas._selecionados |= selecionados_area
            else:
                canvas._selecionados = selecionados_area
            self.set_status(f"Seleção por área: {len(canvas._selecionados)} elemento(s).")

        self._inicio_caixa = None
        self._fim_caixa = None
        canvas.update()
        event.accept()
        return True

    def on_mouse_double_click(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        if not self._rotacao_duplo_clique_ativa(canvas):
            return False

        pos = canvas._tela_para_cena(event.position())
        alvo = self._alvo_duplo_clique(canvas, pos)
        if alvo is None:
            pos_snap = canvas._ponto_com_snap(event.position())
            alvo = self._alvo_duplo_clique(canvas, pos_snap)
        if alvo is None and getattr(canvas, "_snap_resultado", None) is not None:
            idx_snap = getattr(canvas._snap_resultado, "elemento_idx", None)
            try:
                idx_candidato = int(idx_snap)
            except Exception:
                idx_candidato = -1
            if 0 <= idx_candidato < len(canvas.cena.elementos) and canvas.cena.elementos[idx_candidato].get("molde"):
                ponto_snap = getattr(canvas._snap_resultado, "ponto", pos)
                alvo = self._alvo_duplo_clique(canvas, ponto_snap)
                if alvo is None:
                    alvo = (idx_candidato, self._referencia_fio())
        if alvo is None:
            return False

        idx, referencia = alvo
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return False

        molde = canvas.cena.elementos[idx]
        if not molde.get("molde"):
            return False

        chave = (id(canvas), idx)
        estado = self._alinhamento_duplo_molde.get(chave)
        angulo_atual = self._angulo_referencia_alinhamento(molde, referencia)
        if angulo_atual is None:
            self._alinhamento_duplo_molde.pop(chave, None)
            return False
        mesmo_alvo = bool(estado and self._mesma_referencia(estado.get("referencia"), referencia))
        angulo_alvo = float(estado.get("proximo_alvo", 0.0)) if mesmo_alvo else self._eixo_fio_0_90_mais_proximo(angulo_atual)

        delta = self._delta_para_eixo(angulo_atual, angulo_alvo)
        pivo = self._pivo_rotacao_fio(molde)
        self._girar_molde_para_fio(molde, pivo, delta)
        self._atualizar_angulo_fio_molde(molde, fallback=angulo_alvo if referencia.get("tipo") == "fio" else None)
        molde["mostrar_fio"] = True
        self._alinhamento_duplo_molde[chave] = {
            "referencia": referencia,
            "proximo_alvo": 90.0 if self._distancia_angular(angulo_alvo, 0.0) <= 1e-6 else 0.0,
        }

        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto = None
        self._movido = False
        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        rotulo = "fio" if referencia.get("tipo") == "fio" else "borda"
        self.set_status(f"Molde girado: {rotulo} alinhada em {int(angulo_alvo)}°.")
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._arrastando_selecao:
            desenhar_elementos_originais(canvas, painter, self._originais_arraste)
        self._desenhar_realce_elementos(canvas, painter)
        if self._inicio_caixa is None or self._fim_caixa is None:
            return
        p1 = canvas._cena_para_tela(self._inicio_caixa)
        p2 = canvas._cena_para_tela(self._fim_caixa)
        x = min(p1.x(), p2.x())
        y = min(p1.y(), p2.y())
        w = abs(p2.x() - p1.x())
        h = abs(p2.y() - p1.y())
        painter.setPen(QPen(QColor("#33c1ff"), 1, Qt.DashLine))
        painter.setBrush(QColor(40, 160, 255, 40))
        painter.drawRect(int(x), int(y), int(w), int(h))

    def _desenhar_realce_elementos(self, canvas, painter):
        selecionados = set(canvas._selecionados)
        idxs = set()
        if self._hover_idx is not None and self._hover_idx not in selecionados:
            idxs.add(self._hover_idx)
        for idx in idxs:
            if idx is None or idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            pontos = self._pontos_elemento_para_selecao(canvas, el)
            if el.get("tipo") == "polyline" and hasattr(canvas, "_pontos_costuras_vinculadas"):
                pontos.extend(canvas._pontos_costuras_vinculadas(el))
            if not pontos:
                continue
            margem = self.DISTANCIA_VISUAL_SELECAO_CM
            min_x = min(p.x() for p in pontos) - margem
            max_x = max(p.x() for p in pontos) + margem
            min_y = min(p.y() for p in pontos) - margem
            max_y = max(p.y() for p in pontos) + margem
            p1 = canvas._cena_para_tela(QPointF(min_x, min_y))
            p2 = canvas._cena_para_tela(QPointF(max_x, max_y))
            x = min(p1.x(), p2.x())
            y = min(p1.y(), p2.y())
            w = abs(p2.x() - p1.x())
            h = abs(p2.y() - p1.y())
            painter.setPen(QPen(QColor("#33c1ff"), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(x), int(y), int(w), int(h))

    def _mover_selecionados(self, canvas, dx: float, dy: float):
        for idx in self._indices_para_mover(canvas):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            mover_elemento_por_delta(el, dx, dy)

    def _indices_para_mover(self, canvas) -> list[int]:
        indices = set(int(idx) for idx in getattr(canvas, "_selecionados", set()))
        if hasattr(canvas, "_indices_transformacao_com_vinculados"):
            return list(canvas._indices_transformacao_com_vinculados(indices))
        return sorted(indices)

    def _capturar_originais(self, canvas, indices: list[int]) -> dict[int, dict]:
        originais: dict[int, dict] = {}
        for idx in indices:
            if 0 <= idx < len(canvas.cena.elementos) and isinstance(canvas.cena.elementos[idx], dict):
                originais[idx] = deepcopy(canvas.cena.elementos[idx])
        return originais

    def _girar_molde_para_fio(self, el: dict, pivo: QPointF, angulo: float) -> None:
        a = radians(angulo)
        ca, sa = cos(a), sin(a)

        def rot(p):
            x, y = float(p[0]), float(p[1])
            dx, dy = x - pivo.x(), y - pivo.y()
            return (pivo.x() + (dx * ca) + (dy * sa), pivo.y() - (dx * sa) + (dy * ca))

        rotacionar_elemento_por_funcao(el, rot)

    def _pivo_rotacao_fio(self, el: dict) -> QPointF:
        fio_origem = el.get("fio_origem")
        if self._eh_ponto(fio_origem):
            return QPointF(float(fio_origem[0]), float(fio_origem[1]))

        pontos = self._todos_pontos_elemento(el)
        if pontos:
            return QPointF(
                (min(x for x, _ in pontos) + max(x for x, _ in pontos)) / 2.0,
                (min(y for _, y in pontos) + max(y for _, y in pontos)) / 2.0,
            )
        return QPointF(0.0, 0.0)

    def _todos_pontos_elemento(self, el: dict) -> list[tuple[float, float]]:
        pontos: list[tuple[float, float]] = []
        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro"):
            if isinstance(el.get(chave), list):
                for p in el.get(chave, []):
                    if self._eh_ponto(p):
                        pontos.append((float(p[0]), float(p[1])))
        for chave in ("fio_origem", "fio_fim", "ponto_texto", "seta_origem", "seta_fim"):
            if self._eh_ponto(el.get(chave)):
                p = el[chave]
                pontos.append((float(p[0]), float(p[1])))
        return pontos

    def _angulo_fio_atual(self, el: dict) -> float:
        origem = el.get("fio_origem")
        fim = el.get("fio_fim")
        if self._eh_ponto(origem) and self._eh_ponto(fim):
            return self._normalizar_angulo(
                degrees(atan2(-(float(fim[1]) - float(origem[1])), float(fim[0]) - float(origem[0])))
            )
        try:
            return self._normalizar_angulo(float(el.get("fio_angulo") or 0.0))
        except Exception:
            return 0.0

    def _alvo_duplo_clique(self, canvas, pos: QPointF) -> tuple[int, dict] | None:
        idx = canvas._indice_molde_em_ponto(pos) if hasattr(canvas, "_indice_molde_em_ponto") else None
        if idx is not None and 0 <= int(idx) < len(canvas.cena.elementos):
            el = canvas.cena.elementos[int(idx)]
            referencia = self._referencia_fio_em_ponto(el, pos) or self._referencia_borda_em_ponto(el, pos)
            if referencia is not None:
                return int(idx), referencia

        idx_fio = self._indice_molde_por_fio(canvas, pos)
        if idx_fio is not None:
            return idx_fio, self._referencia_fio()
        return None

    def _indice_molde_por_fio(self, canvas, pos: QPointF) -> int | None:
        tolerancia = max(10.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001), 0.12)
        for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
            el = canvas.cena.elementos[idx]
            if not isinstance(el, dict) or not el.get("molde"):
                continue
            origem = self._qpoint_item(el.get("fio_origem"))
            fim = self._qpoint_item(el.get("fio_fim"))
            if origem is None or fim is None or self._dist_qp(origem, fim) <= 1e-9:
                continue
            if self._distancia_ponto_segmento(pos, origem, fim) <= tolerancia:
                return idx
        return None

    def _referencia_fio_em_ponto(self, el: dict, pos: QPointF) -> dict | None:
        origem = self._qpoint_item(el.get("fio_origem"))
        fim = self._qpoint_item(el.get("fio_fim"))
        if origem is None or fim is None or self._dist_qp(origem, fim) <= 1e-9:
            return None
        if self._distancia_ponto_segmento(pos, origem, fim) <= self.DISTANCIA_VISUAL_SELECAO_CM:
            return self._referencia_fio()
        return None

    @staticmethod
    def _referencia_fio() -> dict:
        return {"tipo": "fio"}

    def _referencia_borda_em_ponto(self, el: dict, pos: QPointF) -> dict | None:
        melhor: dict | None = None
        melhor_dist = float("inf")
        for segmento in self._segmentos_borda_molde(el):
            dist = self._distancia_ponto_segmento(pos, segmento["a"], segmento["b"])
            if dist < melhor_dist:
                melhor_dist = dist
                melhor = segmento
        if melhor is None:
            return None
        return melhor

    def _segmentos_borda_molde(self, el: dict) -> list[dict]:
        segmentos = self._segmentos_lista_indexada(el, "controle_cantos", fechado=True)
        if segmentos:
            return segmentos
        return self._segmentos_lista_indexada(el, "pontos", fechado=False)

    def _segmentos_lista_indexada(self, el: dict, chave: str, fechado: bool) -> list[dict]:
        origem = el.get(chave)
        if not isinstance(origem, list):
            return []
        pontos = [self._qpoint_item(item) for item in origem]
        pares = [(idx, ponto) for idx, ponto in enumerate(pontos) if ponto is not None]
        if len(pares) < 2:
            return []

        segmentos: list[dict] = []
        for (a_idx, a), (b_idx, b) in zip(pares, pares[1:]):
            if self._dist_qp(a, b) > 1e-9:
                segmentos.append({"tipo": "borda", "chave": chave, "a_idx": a_idx, "b_idx": b_idx, "a": QPointF(a), "b": QPointF(b)})
        if fechado and len(pares) > 2:
            a_idx, a = pares[-1]
            b_idx, b = pares[0]
            if self._dist_qp(a, b) > 1e-9:
                segmentos.append({"tipo": "borda", "chave": chave, "a_idx": a_idx, "b_idx": b_idx, "a": QPointF(a), "b": QPointF(b)})
        return segmentos

    def _angulo_referencia_alinhamento(self, el: dict, referencia: dict | None) -> float | None:
        if not isinstance(referencia, dict):
            return None
        if referencia.get("tipo") == "fio":
            return self._angulo_fio_atual(el)
        if referencia.get("tipo") != "borda":
            return None
        chave = referencia.get("chave")
        try:
            a_idx = int(referencia.get("a_idx"))
            b_idx = int(referencia.get("b_idx"))
        except Exception:
            return None
        origem = el.get(chave)
        if not isinstance(origem, list) or not (0 <= a_idx < len(origem)) or not (0 <= b_idx < len(origem)):
            return None
        a = self._qpoint_item(origem[a_idx])
        b = self._qpoint_item(origem[b_idx])
        if a is None or b is None or self._dist_qp(a, b) <= 1e-9:
            return None
        return self._normalizar_angulo(degrees(atan2(-(b.y() - a.y()), b.x() - a.x())))

    @staticmethod
    def _mesma_referencia(a: dict | None, b: dict | None) -> bool:
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        if a.get("tipo") != b.get("tipo"):
            return False
        if a.get("tipo") == "fio":
            return True
        return (
            a.get("chave") == b.get("chave")
            and int(a.get("a_idx", -1)) == int(b.get("a_idx", -2))
            and int(a.get("b_idx", -1)) == int(b.get("b_idx", -2))
        )

    def _atualizar_angulo_fio_molde(self, el: dict, fallback: float | None = None) -> None:
        origem = el.get("fio_origem")
        fim = el.get("fio_fim")
        if self._eh_ponto(origem) and self._eh_ponto(fim):
            el["fio_angulo"] = self._angulo_fio_atual(el)
        elif fallback is not None:
            el["fio_angulo"] = self._normalizar_angulo(fallback)

    def _eixo_fio_0_90_mais_proximo(self, angulo_atual: float) -> float:
        atual = self._normalizar_angulo(angulo_atual)
        eixo = atual % 180.0
        return min((0.0, 90.0), key=lambda alvo: self._distancia_eixo_abs(eixo, alvo))

    def _delta_para_eixo(self, angulo_atual: float, angulo_alvo: float) -> float:
        atual = self._normalizar_angulo(angulo_atual) % 180.0
        alvo = self._normalizar_angulo(angulo_alvo) % 180.0
        return ((alvo - atual + 90.0) % 180.0) - 90.0

    @staticmethod
    def _distancia_eixo_abs(a: float, b: float) -> float:
        diferenca = abs((float(a) - float(b)) % 180.0)
        return min(diferenca, 180.0 - diferenca)

    @staticmethod
    def _distancia_angular(a: float, b: float) -> float:
        return abs(((float(a) - float(b) + 180.0) % 360.0) - 180.0)

    @staticmethod
    def _normalizar_angulo(angulo: float) -> float:
        valor = float(angulo) % 360.0
        return 0.0 if abs(valor - 360.0) <= 1e-9 else valor

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    @staticmethod
    def _rotacao_duplo_clique_ativa(canvas) -> bool:
        janela = canvas.window() if hasattr(canvas, "window") else None
        opcoes = getattr(janela, "_opcoes_app", {}) if janela is not None else {}
        return bool(opcoes.get("rotacionar_duplo_clique", True))
