from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon

from tools.tool_base import FerramentaBase
from tools.graduacao_snap_utils import ponto_base_para_snap_graduacao
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
        pos = ponto_base_para_snap_graduacao(canvas, canvas._ponto_com_snap(event.position()))
        molde_alvo = self._molde_em_ponto(canvas, pos)
        moldes_selecionados = self._indices_moldes_selecionados(canvas)
        controle_alvo = None
        amostra_alvo = False
        if molde_alvo is not None:
            controle_alvo = self._controle_molde_em_ponto(canvas, molde_alvo, pos, 10.0)
            amostra_alvo = self._amostra_molde_em_ponto(canvas, molde_alvo, pos, 10.0)
        if (
            molde_alvo is not None
            and molde_alvo not in moldes_selecionados
            and (not self._shift_pressionado(event) or bool(controle_alvo) or not amostra_alvo)
        ):
            canvas._selecionados = {molde_alvo}
            self._hover_principal = self._shift_pressionado(event)
            self._hover_segmento = self._segmento_mais_proximo(canvas, pos, indices=[molde_alvo])
            canvas.update()
            self.set_status("Molde selecionado. Mova o mouse pelo contorno e clique novamente para inserir.")
            event.accept()
            return True

        indices = moldes_selecionados or ([molde_alvo] if molde_alvo is not None else None)
        alvo = self._segmento_mais_proximo(canvas, pos, indices=indices)
        if alvo is None:
            self.set_status("Nenhum segmento encontrado sob o cursor.")
            return False
        idx, seg_idx, ponto_contorno = alvo
        el = canvas.cena.elementos[idx]
        principal = True

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
            pontos_antes = [self._tupla_ponto(item) for item in pontos]
            pontos_antes = [item for item in pontos_antes if item is not None]
            pontos_depois = list(pontos_antes)
            if 0 <= inserir_em <= len(pontos_depois):
                pontos_depois.insert(inserir_em, (float(ponto_contorno.x()), float(ponto_contorno.y())))
                self._inserir_ponto_graduacao_no_contorno(
                    el,
                    pontos_antes,
                    pontos_depois,
                    inserir_em,
                    (float(ponto_contorno.x()), float(ponto_contorno.y())),
                    fechado=self._fechado_por_pontos(canvas, pontos_antes),
                )
            pontos.insert(inserir_em, (ponto_contorno.x(), ponto_contorno.y()))
            el["pontos"] = pontos
            self._sincronizar_controles_apos_insercao(el, ponto_contorno)

        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self.set_status("Ponto principal adicionado.")
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = ponto_base_para_snap_graduacao(canvas, canvas._ponto_com_snap(event.position()))
        hover_principal = self._shift_pressionado(event)
        moldes_selecionados = self._indices_moldes_selecionados(canvas)
        hover_segmento = self._segmento_mais_proximo(canvas, pos, indices=moldes_selecionados or None)
        if hover_segmento is not None and not moldes_selecionados:
            idx, _seg_idx, _ponto = hover_segmento
            if 0 <= idx < len(canvas.cena.elementos) and canvas.cena.elementos[idx].get("molde"):
                hover_segmento = None
        if hover_principal != self._hover_principal or not self._hover_segmento_igual(hover_segmento, self._hover_segmento):
            self._hover_principal = hover_principal
            self._hover_segmento = hover_segmento
            canvas.update()
        event.accept()
        return True

    def _hover_segmento_igual(
        self,
        a: tuple[int, int, QPointF] | None,
        b: tuple[int, int, QPointF] | None,
    ) -> bool:
        if a is None or b is None:
            return a is b
        if a[0] != b[0] or a[1] != b[1]:
            return False
        return self._dist_qt(a[2], b[2]) <= 1e-7

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
        tolerancia2 = tolerancia * tolerancia
        px = float(pos.x())
        py = float(pos.y())
        melhor: tuple[int, int, QPointF] | None = None
        melhor_dist2 = tolerancia2
        candidatos = indices if indices is not None else range(len(canvas.cena.elementos))
        for idx in candidatos:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pontos = el.get("pontos", []) or []
            if len(pontos) < 2:
                continue
            anterior = self._tupla_ponto(pontos[0])
            if anterior is None:
                continue
            for seg_idx, item in enumerate(pontos[1:]):
                atual = self._tupla_ponto(item)
                if atual is None:
                    continue
                ax, ay = anterior
                bx, by = atual
                anterior = atual
                if px < min(ax, bx) - tolerancia or px > max(ax, bx) + tolerancia:
                    continue
                if py < min(ay, by) - tolerancia or py > max(ay, by) + tolerancia:
                    continue
                t, dist2, proj_x, proj_y = self._projetar_ponto_segmento_numerico(ax, ay, bx, by, px, py)
                if 0.0 <= t <= 1.0 and dist2 < melhor_dist2:
                    melhor_dist2 = dist2
                    melhor = (idx, seg_idx, QPointF(proj_x, proj_y))
        return melhor

    @staticmethod
    def _projetar_ponto_segmento_numerico(
        ax: float,
        ay: float,
        bx: float,
        by: float,
        px: float,
        py: float,
    ) -> tuple[float, float, float, float]:
        abx = bx - ax
        aby = by - ay
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            dx = px - ax
            dy = py - ay
            return 0.0, (dx * dx) + (dy * dy), ax, ay
        t = ((px - ax) * abx + (py - ay) * aby) / den
        t = max(0.0, min(1.0, t))
        proj_x = ax + (abx * t)
        proj_y = ay + (aby * t)
        dx = px - proj_x
        dy = py - proj_y
        return t, (dx * dx) + (dy * dy), proj_x, proj_y

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

    def _controle_molde_em_ponto(self, canvas, idx: int, pos: QPointF, tolerancia_px: float) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        tolerancia = float(tolerancia_px) / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        el = canvas.cena.elementos[idx]
        for chave in ("controle_cantos", "controle_auxiliares"):
            for item in el.get(chave, []) or []:
                pt = self._ponto_qt(item)
                if pt is not None and canvas._dist(pt, pos) <= tolerancia:
                    return True
        return False

    def _amostra_molde_em_ponto(self, canvas, idx: int, pos: QPointF, tolerancia_px: float) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        tolerancia = float(tolerancia_px) / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        for item in canvas.cena.elementos[idx].get("pontos", []) or []:
            pt = self._ponto_qt(item)
            if pt is not None and canvas._dist(pt, pos) <= tolerancia:
                return True
        return False

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
            novo = (float(ponto.x()), float(ponto.y()))
            cantos = list(el.get("controle_cantos", []) or [])
            if not any(self._dist_tuple(self._tupla_ponto(item), novo) <= 1e-6 for item in cantos):
                cantos.append(novo)
            el["controle_cantos"] = cantos
            el["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in cantos]
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
        auxiliares_originais = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        fechado = self._fechado_por_pontos(canvas, pontos_originais) or len(cantos_originais) >= 3
        info_curva = self._info_segmento_curvo_para_insercao(
            canvas,
            pontos_originais,
            cantos_originais,
            auxiliares_originais,
            QPointF(ponto),
            seg_idx,
            fechado,
        )
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
            self._inserir_ponto_no_contorno_sem_deformar(canvas, el, ponto, seg_idx)
            self._sincronizar_controles_molde(el)
            return True

        cantos = list(el.get("controle_cantos", []) or [])
        inserir_em = self._indice_insercao_canto(canvas, el, seg_idx)
        inseriu_canto = False
        if not any(self._dist_tuple(self._tupla_ponto(item), novo) <= 1e-6 for item in cantos):
            cantos.insert(inserir_em, novo)
            inseriu_canto = True
        el["controle_cantos"] = cantos
        cantos_depois = []
        for item in cantos:
            pt = self._tupla_ponto(item)
            if pt is not None:
                cantos_depois.append(pt)
        if inseriu_canto:
            self._inserir_ponto_graduacao_no_contorno(
                el,
                [(float(p.x()), float(p.y())) for p in cantos_originais],
                cantos_depois,
                inserir_em,
                novo,
                fechado=fechado,
            )
        auxiliares = []
        for item in el.get("controle_auxiliares", []) or []:
            aux = self._tupla_ponto(item)
            if aux is None or self._dist_tuple(aux, novo) <= 1e-6:
                continue
            auxiliares.append(aux)
        if info_curva is not None:
            auxiliares = self._substituir_auxiliares_segmento_curvo_inserido(
                canvas,
                pontos_originais,
                cantos_originais,
                auxiliares,
                QPointF(ponto),
                seg_idx,
                info_curva,
                fechado,
            )
        el["controle_auxiliares"] = auxiliares
        self._inserir_ponto_no_contorno_sem_deformar(canvas, el, ponto, seg_idx)
        self._helper._garantir_auxiliares_minimos_curva_molde(canvas, el, normalizar_retas=False)
        self._sincronizar_controles_molde(el)
        return True

    def _info_segmento_curvo_para_insercao(
        self,
        canvas,
        pontos: list[QPointF],
        cantos: list[QPointF],
        auxiliares: list[QPointF],
        novo: QPointF,
        seg_idx: int,
        fechado: bool,
    ) -> dict | None:
        if len(pontos) < 2 or len(cantos) < 2:
            return None
        segmentos = self._helper._segmentos_cantos(cantos, fechado)
        if not segmentos:
            return None
        seg_ordem = self._segmento_controle_para_segmento_pontos(canvas, pontos, cantos, segmentos, seg_idx, fechado)
        if seg_ordem is None:
            return None
        a_idx, b_idx = segmentos[seg_ordem]
        por_segmento = self._helper._auxiliares_por_segmento_indexados(
            cantos,
            segmentos,
            auxiliares,
            preferir_ordem=False,
        )
        existentes = [QPointF(pt) for _aux_idx, _t, pt in por_segmento.get(seg_ordem, [])]
        trecho = self._helper._trecho_contorno_molde(canvas, pontos, cantos, a_idx, b_idx, fechado)
        if not self._helper._segmento_molde_eh_curvo(cantos[a_idx], cantos[b_idx], trecho, existentes):
            return None
        return {
            "seg_ordem": seg_ordem,
            "a_idx": a_idx,
            "b_idx": b_idx,
            "aux_indices": {aux_idx for aux_idx, _t, _pt in por_segmento.get(seg_ordem, [])},
            "a": QPointF(cantos[a_idx]),
            "b": QPointF(cantos[b_idx]),
            "novo": QPointF(novo),
        }

    def _substituir_auxiliares_segmento_curvo_inserido(
        self,
        canvas,
        pontos: list[QPointF],
        cantos: list[QPointF],
        auxiliares_atuais: list[tuple[float, float]],
        novo: QPointF,
        seg_idx: int,
        info_curva: dict,
        fechado: bool,
    ) -> list[tuple[float, float]]:
        remover = set(info_curva.get("aux_indices") or set())
        mantidos = [
            item
            for idx, item in enumerate(auxiliares_atuais)
            if idx not in remover and self._dist_tuple(item, (novo.x(), novo.y())) > 1e-6
        ]
        caminho = self._pontos_com_novo_no_contorno(canvas, pontos, novo, seg_idx, fechado)
        trecho_esquerda = self._trecho_entre_pontos(canvas, caminho, info_curva["a"], novo, fechado)
        trecho_direita = self._trecho_entre_pontos(canvas, caminho, novo, info_curva["b"], fechado)
        novos_aux = []
        for trecho, inicio, fim in (
            (trecho_esquerda, info_curva["a"], novo),
            (trecho_direita, novo, info_curva["b"]),
        ):
            novos_aux.extend(self._helper._amostrar_auxiliares_minimos_trecho(trecho, inicio, fim, quantidade=3))
        for aux in novos_aux:
            tupla = (float(aux.x()), float(aux.y()))
            if self._dist_tuple(tupla, (novo.x(), novo.y())) <= 1e-6:
                continue
            if any(self._dist_tuple(tupla, self._tupla_ponto(canto)) <= 1e-6 for canto in cantos):
                continue
            if any(self._dist_tuple(tupla, item) <= 1e-6 for item in mantidos):
                continue
            mantidos.append(tupla)
        return mantidos

    def _segmento_controle_para_segmento_pontos(
        self,
        canvas,
        pontos: list[QPointF],
        cantos: list[QPointF],
        segmentos: list[tuple[int, int]],
        seg_idx: int,
        fechado: bool,
    ) -> int | None:
        base = [QPointF(p) for p in pontos]
        if fechado and len(base) >= 2 and self._dist_canvas(canvas, base[0], base[-1]) <= 1e-6:
            base = base[:-1]
        if not base:
            return None
        total = len(base)
        alvo = max(0, min(seg_idx, total - 1))
        for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
            inicio = self._indice_ponto_mais_proximo(canvas, base, cantos[a_idx])
            fim = self._indice_ponto_mais_proximo(canvas, base, cantos[b_idx])
            indices = self._indices_intervalo(inicio, fim, total, fechado)
            pares = set(zip(indices, indices[1:]))
            if (alvo, (alvo + 1) % total) in pares or (alvo, alvo + 1) in pares:
                return seg_ordem
        return None

    def _pontos_com_novo_no_contorno(
        self,
        canvas,
        pontos: list[QPointF],
        novo: QPointF,
        seg_idx: int,
        fechado: bool,
    ) -> list[QPointF]:
        base = [QPointF(p) for p in pontos]
        if fechado and len(base) >= 2 and self._dist_canvas(canvas, base[0], base[-1]) <= 1e-6:
            base = base[:-1]
        if not any(self._dist_canvas(canvas, p, novo) <= 1e-6 for p in base):
            inserir_em = max(0, min(seg_idx + 1, len(base)))
            base.insert(inserir_em, QPointF(novo))
        return base

    def _trecho_entre_pontos(
        self,
        canvas,
        pontos: list[QPointF],
        inicio: QPointF,
        fim: QPointF,
        fechado: bool,
    ) -> list[QPointF]:
        if not pontos:
            return [QPointF(inicio), QPointF(fim)]
        a_idx = self._indice_ponto_mais_proximo(canvas, pontos, inicio)
        b_idx = self._indice_ponto_mais_proximo(canvas, pontos, fim)
        return [QPointF(pontos[i]) for i in self._indices_intervalo(a_idx, b_idx, len(pontos), fechado)]

    def _indices_intervalo(self, inicio: int, fim: int, total: int, fechado: bool) -> list[int]:
        if total <= 0:
            return []
        inicio = max(0, min(inicio, total - 1))
        fim = max(0, min(fim, total - 1))
        if not fechado or inicio <= fim:
            return list(range(inicio, fim + 1))
        return list(range(inicio, total)) + list(range(0, fim + 1))

    def _inserir_ponto_no_contorno_sem_deformar(self, canvas, el: dict, ponto: QPointF, seg_idx: int) -> None:
        pontos = [self._tupla_ponto(item) for item in el.get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) < 2:
            return
        if not (0 <= seg_idx < len(pontos) - 1):
            return
        novo = (float(ponto.x()), float(ponto.y()))
        a = QPointF(float(pontos[seg_idx][0]), float(pontos[seg_idx][1]))
        b = QPointF(float(pontos[seg_idx + 1][0]), float(pontos[seg_idx + 1][1]))
        if self._dist_canvas(canvas, QPointF(*novo), a) <= 1e-6:
            return
        if self._dist_canvas(canvas, QPointF(*novo), b) <= 1e-6:
            return
        if any(self._dist_tuple(item, novo) <= 1e-6 for item in pontos):
            return
        pontos.insert(seg_idx + 1, novo)
        el["pontos"] = pontos

    def _sincronizar_controles_molde(self, el: dict) -> None:
        cantos = []
        for item in el.get("controle_cantos", []) or []:
            ponto = self._tupla_ponto(item)
            if ponto is not None:
                cantos.append(ponto)
        auxiliares = []
        for item in el.get("controle_auxiliares", []) or []:
            ponto = self._tupla_ponto(item)
            if ponto is not None:
                auxiliares.append(ponto)
        el["controle_cantos"] = cantos
        el["controle_auxiliares"] = auxiliares
        el["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in cantos]
        el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]

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
        controles_antes = self._controles_curva(el)
        controles = list(controles_antes)
        inserir_em = self._indice_insercao_controle(canvas, el, controles_antes, seg_idx)
        controles.insert(inserir_em, QPointF(ponto))
        fechado = self._fechado_por_pontos(canvas, el.get("pontos", []) or [])
        tipo_curva = str(el.get("tipo_curva") or "spline_catmull_rom")
        el["pontos"] = self._helper._gerar_tracado_curva_real(controles, fechado=fechado, tipo_curva=tipo_curva)
        self._helper._salvar_controles_curva_real(el, controles)
        el["fechado"] = fechado
        self._inserir_ponto_graduacao_no_contorno(
            el,
            [(float(p.x()), float(p.y())) for p in controles_antes],
            [(float(p.x()), float(p.y())) for p in controles],
            inserir_em,
            (float(ponto.x()), float(ponto.y())),
            fechado=fechado,
        )
        return len(el.get("pontos", []) or []) >= 2

    def _inserir_ponto_graduacao_no_contorno(
        self,
        el: dict,
        pontos_antes: list[tuple[float, float]],
        pontos_depois: list[tuple[float, float]],
        novo_idx: int,
        novo: tuple[float, float],
        *,
        fechado: bool,
    ) -> None:
        pontos_cfg = self._pontos_config_graduacao(el)
        if not pontos_cfg:
            return
        base_antes = self._contorno_sem_fechamento(pontos_antes)
        base_depois = self._contorno_sem_fechamento(pontos_depois)
        if len(base_antes) < 2 or not (0 <= int(novo_idx) < len(base_depois)):
            return
        try:
            from canvas.visualizacao import VisualizacaoCanvas
        except Exception:
            return

        origem_idx = (int(novo_idx) - 1) % len(base_antes) if fechado else max(0, min(int(novo_idx) - 1, len(base_antes) - 1))
        destino_idx = int(novo_idx) % len(base_antes) if fechado else max(0, min(int(novo_idx), len(base_antes) - 1))
        origem = QPointF(*base_antes[origem_idx])
        destino = QPointF(*base_antes[destino_idx])
        fator = self._fracao_no_segmento(QPointF(float(novo[0]), float(novo[1])), origem, destino)
        referencias_antes = [QPointF(x, y) for x, y in base_antes]
        contorno_antes = [QPointF(x, y) for x, y in base_antes]

        nomes_tamanhos = self._nomes_tamanhos_graduacao(el, pontos_cfg)
        if not nomes_tamanhos:
            return

        valores_novo: dict[str, dict[str, float]] = {}
        for nome in nomes_tamanhos:
            deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
                pontos_cfg,
                nome,
                len(contorno_antes),
                contorno=contorno_antes,
                referencias=referencias_antes,
            )
            if deslocamentos and len(deslocamentos) == len(contorno_antes):
                dx_a, dy_a = deslocamentos[origem_idx]
                dx_b, dy_b = deslocamentos[destino_idx]
            else:
                dx_a = dy_a = dx_b = dy_b = 0.0
            valores_novo[str(nome)] = {
                "dx": float(dx_a + ((dx_b - dx_a) * fator)),
                "dy": float(dy_a + ((dy_b - dy_a) * fator)),
            }

        pontos_remapeados = self._remapear_graduacao_apos_insercao(
            pontos_cfg,
            base_antes,
            base_depois,
            int(novo_idx),
        )
        pontos_remapeados[str(int(novo_idx))] = {
            "indice": int(novo_idx),
            "numero": int(novo_idx) + 1,
            "ponto": (float(novo[0]), float(novo[1])),
            "valores": valores_novo,
        }
        pontos_ordenados = self._ordenar_pontos_graduacao(pontos_remapeados)
        tabela = el.setdefault("graduacao_tabela", {})
        if isinstance(tabela, dict):
            tabela["modo"] = "dx_dy"
            tabela["pontos"] = pontos_ordenados
        el["graduacao_pontos"] = deepcopy(pontos_ordenados)

    def _pontos_config_graduacao(self, el: dict) -> dict:
        tabela = el.get("graduacao_tabela") if isinstance(el.get("graduacao_tabela"), dict) else None
        if isinstance(tabela, dict) and isinstance(tabela.get("pontos"), dict):
            return tabela.get("pontos") or {}
        legado = el.get("graduacao_pontos")
        return legado if isinstance(legado, dict) else {}

    def _nomes_tamanhos_graduacao(self, el: dict, pontos_cfg: dict) -> list[str]:
        nomes: list[str] = []
        for linha in el.get("graduacao_tamanhos", []) or []:
            if not isinstance(linha, dict) or not linha.get("ativo", True):
                continue
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if nome and nome not in nomes:
                nomes.append(nome)
        for cfg in pontos_cfg.values():
            valores = cfg.get("valores") if isinstance(cfg, dict) else None
            if not isinstance(valores, dict):
                continue
            for nome in valores:
                texto = str(nome or "").strip()
                if texto and texto not in nomes:
                    nomes.append(texto)
        return nomes

    def _remapear_graduacao_apos_insercao(
        self,
        pontos_cfg: dict,
        base_antes: list[tuple[float, float]],
        base_depois: list[tuple[float, float]],
        novo_idx: int,
    ) -> dict:
        saida: dict[str, dict] = {}
        for chave, cfg in pontos_cfg.items():
            if not isinstance(cfg, dict):
                continue
            antigo_idx = self._indice_graduacao_cfg(cfg, chave, base_antes)
            if antigo_idx is None or not (0 <= antigo_idx < len(base_antes)):
                continue
            indice = antigo_idx + 1 if antigo_idx >= int(novo_idx) else antigo_idx
            if not (0 <= indice < len(base_depois)):
                continue
            novo_cfg = deepcopy(cfg)
            novo_cfg["indice"] = int(indice)
            novo_cfg["numero"] = int(indice) + 1
            novo_cfg["ponto"] = (float(base_depois[indice][0]), float(base_depois[indice][1]))
            saida[str(indice)] = novo_cfg
        return saida

    def _indice_graduacao_cfg(self, cfg: dict, chave: str, base: list[tuple[float, float]]) -> int | None:
        ponto_cfg = self._tupla_ponto(cfg.get("ponto")) if isinstance(cfg, dict) else None
        if ponto_cfg is not None:
            return self._indice_tupla_mais_proximo(base, ponto_cfg)
        try:
            return int(cfg.get("indice", chave))
        except Exception:
            return None

    @staticmethod
    def _ordenar_pontos_graduacao(pontos_cfg: dict) -> dict:
        def chave_ordem(item) -> int:
            try:
                return int(item[0])
            except Exception:
                return 0

        return {str(chave): valor for chave, valor in sorted(pontos_cfg.items(), key=chave_ordem)}

    def _contorno_sem_fechamento(self, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        contorno = list(pontos)
        if len(contorno) > 1 and self._dist_tuple(contorno[0], contorno[-1]) <= 1e-6:
            contorno = contorno[:-1]
        return contorno

    @staticmethod
    def _fracao_no_segmento(ponto: QPointF, origem: QPointF, destino: QPointF) -> float:
        vx = destino.x() - origem.x()
        vy = destino.y() - origem.y()
        denom = (vx * vx) + (vy * vy)
        if denom <= 1e-12:
            return 0.0
        t = ((ponto.x() - origem.x()) * vx + (ponto.y() - origem.y()) * vy) / denom
        return max(0.0, min(1.0, float(t)))

    def _indice_tupla_mais_proximo(self, pontos: list[tuple[float, float]], alvo: tuple[float, float]) -> int | None:
        if not pontos:
            return None
        melhor_idx = 0
        melhor_dist = float("inf")
        for idx, ponto in enumerate(pontos):
            dist = self._dist_tuple(ponto, alvo)
            if dist < melhor_dist:
                melhor_idx = idx
                melhor_dist = dist
        return melhor_idx

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
