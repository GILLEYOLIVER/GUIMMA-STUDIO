from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon

from tools.tool_base import FerramentaBase
from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos


class Ferramenta(FerramentaBase):
    id_ferramenta = "inserir_ponto"
    nome = "Adicionar Ponto"
    descricao_painel = "Adiciona ponto principal no molde/contorno."

    def __init__(self):
        super().__init__()
        self._hover_segmento: tuple[int, int, QPointF] | None = None
        self._hover_principal = False
        self._helper = FerramentaManipularPontos()

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover_segmento = None
        self._hover_principal = False
        self.set_status("Clique em um molde para selecionar; depois clique no contorno para adicionar o ponto.")
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        molde_alvo = self._molde_em_ponto(canvas, pos)
        moldes_selecionados = self._indices_moldes_selecionados(canvas)
        if molde_alvo is not None and molde_alvo not in moldes_selecionados:
            canvas._selecionados = {molde_alvo}
            self._hover_principal = self._shift_pressionado(event)
            self._hover_segmento = self._segmento_mais_proximo(canvas, pos, indices=[molde_alvo])
            canvas.update()
            self.set_status("Molde selecionado. Mova o mouse pelo contorno e clique novamente para inserir.")
            event.accept()
            return True

        indices = moldes_selecionados or None
        alvo = self._segmento_mais_proximo(canvas, pos, indices=indices)
        if alvo is None:
            self.set_status("Nenhum segmento encontrado sob o cursor.")
            return False
        idx, seg_idx, ponto_contorno = alvo
        el = canvas.cena.elementos[idx]
        principal = self._shift_pressionado(event)

        if el.get("molde") and self._tem_controles_molde(el):
            if not self._adicionar_controle_molde(canvas, el, ponto_contorno, seg_idx, principal=principal):
                self.set_status("Não foi possível adicionar ponto nesse molde.")
                return False
        elif self._curva_editavel(el):
            if not self._adicionar_controle_curva(canvas, el, ponto_contorno, seg_idx):
                self.set_status("Não foi possível adicionar ponto nessa curva.")
                return False
        else:
            pontos = list(el.get("pontos", []))
            inserir_em = seg_idx + 1
            pontos.insert(inserir_em, (ponto_contorno.x(), ponto_contorno.y()))
            el["pontos"] = pontos
            self._sincronizar_controles_apos_insercao(el, ponto_contorno)

        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self.set_status("Ponto principal adicionado." if principal else "Ponto auxiliar adicionado.")
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._hover_principal = self._shift_pressionado(event)
        moldes_selecionados = self._indices_moldes_selecionados(canvas)
        self._hover_segmento = self._segmento_mais_proximo(canvas, pos, indices=moldes_selecionados or None)
        if self._hover_segmento is not None and not moldes_selecionados:
            idx, _seg_idx, _ponto = self._hover_segmento
            if 0 <= idx < len(canvas.cena.elementos) and canvas.cena.elementos[idx].get("molde"):
                self._hover_segmento = None
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._hover_segmento is None:
            return
        idx, seg_idx, ponto = self._hover_segmento
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        pontos = [self._ponto_qt(p) for p in canvas.cena.elementos[idx].get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        if not (0 <= seg_idx < len(pontos) - 1):
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#00a6ff"), 2.0, Qt.DashLine))
        painter.drawLine(canvas._cena_para_tela(pontos[seg_idx]), canvas._cena_para_tela(pontos[seg_idx + 1]))
        self._desenhar_ponto_preview(canvas, painter, ponto)
        painter.restore()

    def _segmento_mais_proximo(self, canvas, pos: QPointF, indices: list[int] | None = None) -> tuple[int, int, QPointF] | None:
        tolerancia = 10.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int, QPointF] | None = None
        melhor_dist = tolerancia
        candidatos = indices if indices is not None else range(len(canvas.cena.elementos))
        for idx in candidatos:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pontos = [self._ponto_qt(p) for p in el.get("pontos", []) or []]
            pontos = [p for p in pontos if p is not None]
            if len(pontos) < 2:
                continue
            for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
                projetado = self._projetar_ponto_segmento(a, b, pos)
                d = self._dist_qt(projetado, pos)
                if d < melhor_dist:
                    melhor_dist = d
                    melhor = (idx, seg_idx, projetado)
        return melhor

    def _indices_moldes_selecionados(self, canvas) -> list[int]:
        saida: list[int] = []
        for idx in getattr(canvas, "_selecionados", set()) or set():
            try:
                idx_int = int(idx)
            except Exception:
                continue
            if 0 <= idx_int < len(canvas.cena.elementos) and canvas.cena.elementos[idx_int].get("molde"):
                saida.append(idx_int)
        return saida

    def _molde_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            try:
                return canvas._indice_molde_em_ponto(pos)
            except Exception:
                pass
        alvo = self._segmento_mais_proximo(canvas, pos)
        if alvo is None:
            return None
        idx, _seg_idx, _ponto = alvo
        if 0 <= idx < len(canvas.cena.elementos) and canvas.cena.elementos[idx].get("molde"):
            return idx
        return None

    def _desenhar_ponto_preview(self, canvas, painter, ponto: QPointF) -> None:
        chave = "ponto_controle" if self._hover_principal else "ponto_nao_graduado"
        cor = self._cor_ponto_config(canvas, chave, "#00a6ff")
        forma = self._forma_ponto_config(canvas, chave, "Circulo preenchido")
        self._desenhar_marcador_configurado(canvas, painter, ponto, cor, forma, 10)

    def _cor_ponto_config(self, canvas, chave: str, padrao: str) -> str:
        if hasattr(canvas, "_config_cor_molde"):
            try:
                return canvas._config_cor_molde(chave, padrao)
            except Exception:
                return padrao
        return padrao

    def _forma_ponto_config(self, canvas, chave: str, padrao: str) -> str:
        if hasattr(canvas, "_config_forma_molde"):
            try:
                return canvas._config_forma_molde(chave, padrao)
            except Exception:
                return padrao
        return padrao

    def _desenhar_marcador_configurado(self, canvas, painter, ponto: QPointF, cor: str, forma: str, tamanho: int) -> None:
        tela = canvas._cena_para_tela(ponto)
        meio = max(3, int(round(tamanho / 2)))
        forma_norm = self._normalizar_forma(forma)
        painter.setPen(QPen(QColor("#ffffff"), 1.2))
        painter.setBrush(QColor(cor))
        if forma_norm == "quadrado":
            painter.drawRect(int(tela.x() - meio), int(tela.y() - meio), meio * 2, meio * 2)
        elif forma_norm == "losango":
            painter.drawPolygon(QPolygon([
                QPoint(int(tela.x()), int(tela.y() - meio)),
                QPoint(int(tela.x() + meio), int(tela.y())),
                QPoint(int(tela.x()), int(tela.y() + meio)),
                QPoint(int(tela.x() - meio), int(tela.y())),
            ]))
        else:
            painter.drawEllipse(int(tela.x() - meio), int(tela.y() - meio), meio * 2, meio * 2)

    @staticmethod
    def _normalizar_forma(forma: str) -> str:
        texto = str(forma or "").lower()
        if "quadr" in texto:
            return "quadrado"
        if "los" in texto:
            return "losango"
        return "circulo"

    def _sincronizar_controles_apos_insercao(self, el: dict, ponto: QPointF) -> None:
        if el.get("molde"):
            auxiliares = list(el.get("controle_auxiliares", []) or [])
            novo = (float(ponto.x()), float(ponto.y()))
            if not any(self._dist_tuple(self._tupla_ponto(item), novo) <= 1e-6 for item in auxiliares):
                auxiliares.append(novo)
            el["controle_auxiliares"] = auxiliares
            el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]
            return

        if not (
            el.get("curva_suave")
            or el.get("curva_editavel")
            or el.get("pontos_controle_curva")
            or el.get("pontos_principais")
        ):
            return
        if el.get("pontos_tracado_real"):
            return

        controles = []
        for item in el.get("pontos", []) or []:
            pt = self._tupla_ponto(item)
            if pt is not None:
                controles.append(pt)
        if len(controles) < 2:
            return
        el["pontos_controle_curva"] = list(controles)
        el["pontos_principais"] = list(controles)
        el["pontos_controle"] = list(controles)
        el["curva_suave"] = True

    def _adicionar_controle_molde(self, canvas, el: dict, ponto: QPointF, seg_idx: int, principal: bool) -> bool:
        self._garantir_dist_canvas(canvas)
        pontos_originais = [p for p in (self._ponto_qt(item) for item in el.get("pontos", []) or []) if p is not None]
        cantos_originais = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        fechado = self._fechado_por_pontos(canvas, pontos_originais) or len(cantos_originais) >= 3
        novo = (float(ponto.x()), float(ponto.y()))
        if not principal:
            auxiliares = []
            for item in el.get("controle_auxiliares", []) or []:
                aux = self._tupla_ponto(item)
                if aux is not None:
                    auxiliares.append(aux)
            if not any(self._dist_tuple(item, novo) <= 1e-6 for item in auxiliares):
                auxiliares.append(novo)
            el["controle_auxiliares"] = auxiliares
            el["_controles_topologia_alterada"] = True
            self._helper._garantir_auxiliares_minimos_curva_molde(canvas, el)
            return self._helper._regenerar_molde_por_controles(canvas, el)

        cantos = list(el.get("controle_cantos", []) or [])
        inserir_em = self._indice_insercao_canto(canvas, el, seg_idx)
        if not any(self._dist_tuple(self._tupla_ponto(item), novo) <= 1e-6 for item in cantos):
            cantos.insert(inserir_em, novo)
        el["controle_cantos"] = cantos
        auxiliares = []
        for item in el.get("controle_auxiliares", []) or []:
            aux = self._tupla_ponto(item)
            if aux is None or self._dist_tuple(aux, novo) <= 1e-6:
                continue
            auxiliares.append(aux)
        for aux in self._auxiliares_preservacao_insercao(
            canvas,
            pontos_originais,
            cantos_originais,
            QPointF(ponto),
            seg_idx,
            inserir_em,
            fechado,
        ):
            tupla = (float(aux.x()), float(aux.y()))
            if any(self._dist_tuple(item, tupla) <= 1e-6 for item in auxiliares):
                continue
            if any(self._dist_tuple(self._tupla_ponto(item), tupla) <= 1e-6 for item in cantos):
                continue
            auxiliares.append(tupla)
        el["controle_auxiliares"] = auxiliares
        el["_controles_topologia_alterada"] = True
        self._helper._garantir_auxiliares_minimos_curva_molde(canvas, el)
        return self._helper._regenerar_molde_por_controles(canvas, el)

    def _auxiliares_preservacao_insercao(
        self,
        canvas,
        pontos: list[QPointF],
        cantos: list[QPointF],
        novo: QPointF,
        seg_idx: int,
        inserir_em: int,
        fechado: bool,
    ) -> list[QPointF]:
        if len(pontos) < 2 or len(cantos) < 2:
            return []
        base = list(pontos)
        if fechado and len(base) >= 2 and self._dist_canvas(canvas, base[0], base[-1]) <= 1e-6:
            base = base[:-1]
        if len(base) < 2:
            return []
        insert_idx = max(0, min(seg_idx + 1, len(base)))
        base_com_novo = list(base)
        base_com_novo.insert(insert_idx, QPointF(novo))
        n = len(base_com_novo)

        prev_canto = cantos[(inserir_em - 1) % len(cantos)] if fechado else cantos[max(0, min(inserir_em - 1, len(cantos) - 1))]
        next_canto = cantos[inserir_em % len(cantos)] if fechado else cantos[max(0, min(inserir_em, len(cantos) - 1))]
        prev_idx = self._indice_ponto_mais_proximo(canvas, base_com_novo, prev_canto)
        novo_idx = self._indice_ponto_mais_proximo(canvas, base_com_novo, novo)
        next_idx = self._indice_ponto_mais_proximo(canvas, base_com_novo, next_canto)

        auxiliares: list[QPointF] = []
        for a_idx, b_idx in ((prev_idx, novo_idx), (novo_idx, next_idx)):
            trecho = self._trecho_indices(base_com_novo, a_idx, b_idx, fechado)
            auxiliares.extend(self._amostrar_auxiliares_trecho(trecho))
        return auxiliares

    def _trecho_indices(self, pontos: list[QPointF], a_idx: int, b_idx: int, fechado: bool) -> list[QPointF]:
        if not pontos:
            return []
        if not fechado:
            lo, hi = sorted((a_idx, b_idx))
            return [QPointF(p) for p in pontos[lo : hi + 1]]
        saida = [QPointF(pontos[a_idx])]
        i = a_idx
        while i != b_idx:
            i = (i + 1) % len(pontos)
            saida.append(QPointF(pontos[i]))
            if len(saida) > len(pontos) + 1:
                break
        return saida

    def _amostrar_auxiliares_trecho(self, pontos: list[QPointF]) -> list[QPointF]:
        if len(pontos) < 4:
            return []
        comprimento = sum(self._dist_qt(a, b) for a, b in zip(pontos, pontos[1:]))
        if comprimento <= 1e-9:
            return []
        return [self._ponto_no_trecho_por_fracao(pontos, 1.0 / 3.0), self._ponto_no_trecho_por_fracao(pontos, 2.0 / 3.0)]

    def _ponto_no_trecho_por_fracao(self, pontos: list[QPointF], fracao: float) -> QPointF:
        alvo = sum(self._dist_qt(a, b) for a, b in zip(pontos, pontos[1:])) * max(0.0, min(1.0, fracao))
        acumulado = 0.0
        for a, b in zip(pontos, pontos[1:]):
            dist = self._dist_qt(a, b)
            if dist <= 1e-9:
                continue
            if acumulado + dist >= alvo:
                t = (alvo - acumulado) / dist
                return QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
            acumulado += dist
        return QPointF(pontos[-1])

    def _adicionar_controle_curva(self, canvas, el: dict, ponto: QPointF, seg_idx: int) -> bool:
        self._garantir_dist_canvas(canvas)
        controles = self._controles_curva(el)
        inserir_em = self._indice_insercao_controle(canvas, el, controles, seg_idx)
        controles.insert(inserir_em, QPointF(ponto))
        fechado = self._fechado_por_pontos(canvas, el.get("pontos", []) or [])
        tipo_curva = str(el.get("tipo_curva") or "spline_catmull_rom")
        el["pontos"] = self._helper._gerar_tracado_curva_real(controles, fechado=fechado, tipo_curva=tipo_curva)
        self._helper._salvar_controles_curva_real(el, controles)
        el["fechado"] = fechado
        return len(el.get("pontos", []) or []) >= 2

    def _indice_insercao_canto(self, canvas, el: dict, seg_idx: int) -> int:
        cantos = [self._ponto_qt(p) for p in el.get("controle_cantos", []) or []]
        cantos = [p for p in cantos if p is not None]
        return self._indice_insercao_controle(canvas, el, cantos, seg_idx)

    def _indice_insercao_controle(self, canvas, el: dict, controles: list[QPointF], seg_idx: int) -> int:
        if not controles:
            return 0
        pontos = [self._ponto_qt(p) for p in el.get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) < 2:
            return len(controles)
        fechado = self._fechado_por_pontos(canvas, pontos)
        n = len(pontos) - 1 if fechado else len(pontos)
        if n <= 0:
            return len(controles)
        indices = [self._indice_ponto_mais_proximo(canvas, pontos[:n], ctrl) for ctrl in controles]
        if not fechado:
            inserir = 0
            for i, indice in enumerate(indices):
                if indice <= seg_idx:
                    inserir = i + 1
            return max(0, min(len(controles), inserir))

        ordenados = sorted((indice, i) for i, indice in enumerate(indices))
        alvo = max(0, min(n - 1, seg_idx))
        for pos, (inicio, idx_controle) in enumerate(ordenados):
            fim = ordenados[(pos + 1) % len(ordenados)][0]
            dentro = inicio <= alvo < fim if inicio < fim else alvo >= inicio or alvo < fim
            if dentro:
                return idx_controle + 1
        return len(controles)

    def _controles_curva(self, el: dict) -> list[QPointF]:
        origem = el.get("pontos_principais") or el.get("pontos_controle_curva") or el.get("pontos_controle_principais") or []
        controles = [self._ponto_qt(p) for p in origem]
        return [p for p in controles if p is not None]

    def _curva_editavel(self, el: dict) -> bool:
        return bool(el.get("pontos_tracado_real") or el.get("curva_editavel") or el.get("pontos_principais") or el.get("pontos_controle_curva"))

    def _tem_controles_molde(self, el: dict) -> bool:
        return isinstance(el.get("controle_cantos"), list) and isinstance(el.get("controle_auxiliares"), list)

    def _shift_pressionado(self, event) -> bool:
        try:
            return bool(event.modifiers() & Qt.ShiftModifier)
        except Exception:
            return False

    def _indice_ponto_mais_proximo(self, canvas, pontos: list[QPointF], alvo: QPointF) -> int:
        return min(range(len(pontos)), key=lambda i: self._dist_canvas(canvas, pontos[i], alvo))

    def _fechado_por_pontos(self, canvas, pontos: list) -> bool:
        if len(pontos) < 3:
            return False
        p0 = self._ponto_qt(pontos[0])
        pn = self._ponto_qt(pontos[-1])
        return p0 is not None and pn is not None and self._dist_canvas(canvas, p0, pn) <= 1e-6

    def _garantir_dist_canvas(self, canvas) -> None:
        if not hasattr(canvas, "_dist"):
            canvas._dist = self._dist_qt

    def _dist_canvas(self, canvas, a: QPointF, b: QPointF) -> float:
        if hasattr(canvas, "_dist"):
            return canvas._dist(a, b)
        return self._dist_qt(a, b)

    @staticmethod
    def _projetar_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> QPointF:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-12:
            return QPointF(a)
        t = ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / denom
        t = max(0.0, min(1.0, t))
        return QPointF(a.x() + abx * t, a.y() + aby * t)

    @staticmethod
    def _dist_qt(a: QPointF, b: QPointF) -> float:
        return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5

    @staticmethod
    def _tupla_ponto(p) -> tuple[float, float] | None:
        try:
            if isinstance(p, QPointF):
                return float(p.x()), float(p.y())
            if isinstance(p, dict):
                return float(p["x"]), float(p["y"])
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                return float(p[0]), float(p[1])
        except Exception:
            return None
        return None

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

    @staticmethod
    def _dist_tuple(a: tuple[float, float] | None, b: tuple[float, float]) -> float:
        if a is None:
            return float("inf")
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
