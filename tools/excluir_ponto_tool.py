from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon

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
        self.set_status("Clique em um molde ou elemento para selecionar; depois passe sobre um ponto e clique para excluir.")
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = self._posicao_evento_cena(canvas, event)
        selecionados = self._indices_elementos_selecionados(canvas)
        elemento_alvo = self._elemento_em_ponto(canvas, pos)
        if elemento_alvo is not None and elemento_alvo not in selecionados:
            canvas._selecionados = {elemento_alvo}
            self._atualizar_hover_selecao(canvas, pos)
            canvas.update()
            self.set_status("Elemento selecionado. Passe sobre o ponto desejado e clique novamente para excluir.")
            event.accept()
            return True

        alvo_controle = self._controle_molde_hover_selecionado(canvas)
        if alvo_controle is None:
            alvo_controle = self._controle_molde_em_ponto(canvas, pos, somente_selecionados=True)
        if alvo_controle is not None:
            idx, tipo, controle_idx = alvo_controle
            if not self._excluir_controle_molde(canvas, idx, tipo, controle_idx):
                return False
            canvas._selecionados = {idx}
            self._hover_alvo = None
            canvas._registrar_historico()
            canvas.update()
            self.set_status("Controle do molde excluído e contorno regenerado.")
            event.accept()
            return True

        alvo_curva = self._controle_curva_em_ponto(canvas, pos, selecionados)
        if alvo_curva is not None:
            idx, controle_idx = alvo_curva
            if not self._excluir_controle_curva(canvas, idx, controle_idx):
                return False
            canvas._selecionados = {idx}
            self._hover_alvo = None
            canvas._registrar_historico()
            canvas.update()
            self.set_status("Ponto de controle da curva excluído.")
            event.accept()
            return True

        alvo = self._vertice_em_ponto(canvas, pos, selecionados)
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
        self._hover_alvo = None
        canvas._registrar_historico()
        canvas.update()
        self.set_status("Ponto excluído com sucesso.")
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_evento_cena(canvas, event)
        self._atualizar_hover_selecao(canvas, pos)
        canvas.update()
        event.accept()
        return True

    def _posicao_evento_cena(self, canvas, event) -> QPointF:
        if hasattr(canvas, "_tela_para_cena"):
            try:
                return canvas._tela_para_cena(event.position())
            except Exception:
                pass
        return canvas._ponto_com_snap(event.position())

    def _atualizar_hover_selecao(self, canvas, pos: QPointF) -> bool:
        if self._atualizar_hover_molde_selecionado(canvas, pos):
            return True
        selecionados = self._indices_elementos_selecionados(canvas)
        alvo_curva = self._controle_curva_em_ponto(canvas, pos, selecionados)
        if alvo_curva is not None:
            idx, controle_idx = alvo_curva
            self._hover_alvo = ("curva", idx, controle_idx)
            return True
        alvo_vertice = self._vertice_em_ponto(canvas, pos, selecionados)
        if alvo_vertice is not None:
            idx, ponto_idx = alvo_vertice
            self._hover_alvo = ("vertice", idx, ponto_idx)
            return True
        self._hover_alvo = None
        return False

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_controles_molde_selecionado(canvas, painter)
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
            controles = self._controles_molde_tipo(canvas.cena.elementos[idx], tipo)
            if 0 <= controle_idx < len(controles):
                return QPointF(controles[controle_idx][2])
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
    def _controle_molde_em_ponto(self, canvas, pos: QPointF, somente_selecionados: bool = False) -> tuple[int, str, int] | None:
        selecionados = self._indices_moldes_selecionados(canvas)
        if selecionados:
            alvo = self._controle_molde_em_ponto_indices(canvas, pos, selecionados, 18.0)
            if alvo is not None:
                return alvo
            if somente_selecionados:
                return None
        elif somente_selecionados:
            return None
        todos = [
            idx
            for idx, el in enumerate(canvas.cena.elementos)
            if el.get("tipo") == "polyline" and el.get("molde")
        ]
        return self._controle_molde_em_ponto_indices(canvas, pos, todos, 10.0)

    def _atualizar_hover_molde_selecionado(self, canvas, pos: QPointF) -> bool:
        selecionados = self._indices_moldes_selecionados(canvas)
        if not selecionados:
            self._hover_alvo = None
            return False
        alvo_controle = self._controle_molde_em_ponto_indices(canvas, pos, selecionados, 18.0)
        if alvo_controle is None:
            self._hover_alvo = None
            return False
        idx, tipo, controle_idx = alvo_controle
        self._hover_alvo = ("molde", idx, tipo, controle_idx)
        return True

    def _controle_molde_hover_selecionado(self, canvas) -> tuple[int, str, int] | None:
        if self._hover_alvo is None or self._hover_alvo[0] != "molde":
            return None
        _kind, idx, tipo, controle_idx = self._hover_alvo
        if idx not in self._indices_moldes_selecionados(canvas):
            return None
        return int(idx), str(tipo), int(controle_idx)

    def _molde_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            try:
                return canvas._indice_molde_em_ponto(pos)
            except Exception:
                pass
        alvo = self._controle_molde_em_ponto_indices(
            canvas,
            pos,
            [idx for idx, el in enumerate(canvas.cena.elementos) if el.get("molde")],
            14.0,
        )
        return alvo[0] if alvo is not None else None

    def _controle_molde_em_ponto_indices(
        self,
        canvas,
        pos: QPointF,
        indices: list[int],
        tolerancia_px: float,
    ) -> tuple[int, str, int] | None:
        tolerancia = float(tolerancia_px) / max(canvas.zoom, 0.001)
        melhor: tuple[int, str, int] | None = None
        melhor_d = tolerancia
        for idx in indices:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline" or not el.get("molde"):
                continue
            for tipo in ("canto", "aux"):
                for c_idx, (_chave, _idx_original, pt) in enumerate(self._controles_molde_tipo(el, tipo)):
                    d = canvas._dist(pt, pos)
                    if d <= melhor_d:
                        melhor_d = d
                        melhor = (idx, tipo, c_idx)
        return melhor

    def _indices_moldes_selecionados(self, canvas) -> list[int]:
        return [
            idx
            for idx in self._indices_elementos_selecionados(canvas)
            if canvas.cena.elementos[idx].get("tipo") == "polyline" and canvas.cena.elementos[idx].get("molde")
        ]

    def _indices_elementos_selecionados(self, canvas) -> list[int]:
        selecionados = getattr(canvas, "_selecionados", set()) or set()
        saida: list[int] = []
        for idx in selecionados:
            try:
                idx_int = int(idx)
            except Exception:
                continue
            if not (0 <= idx_int < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx_int]
            if el.get("tipo") == "polyline":
                saida.append(idx_int)
        return saida

    def _elemento_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indices_elementos_em_ponto"):
            try:
                for idx in canvas._indices_elementos_em_ponto(pos):
                    if 0 <= idx < len(canvas.cena.elementos):
                        el = canvas.cena.elementos[idx]
                        if el.get("tipo") == "polyline":
                            return idx
            except Exception:
                pass
        molde = self._molde_em_ponto(canvas, pos)
        if molde is not None:
            return molde
        todos = [
            idx
            for idx, el in enumerate(canvas.cena.elementos)
            if el.get("tipo") == "polyline" and not el.get("molde")
        ]
        alvo_curva = self._controle_curva_em_ponto(canvas, pos, todos)
        if alvo_curva is not None:
            return alvo_curva[0]
        alvo_vertice = self._vertice_em_ponto(canvas, pos, todos)
        return alvo_vertice[0] if alvo_vertice is not None else None

    def _desenhar_controles_molde_selecionado(self, canvas, painter) -> None:
        indices = self._indices_moldes_selecionados(canvas)
        if not indices:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        for idx in indices:
            el = canvas.cena.elementos[idx]
            for tipo in ("canto", "aux"):
                chave_cfg = "ponto_controle" if tipo == "canto" else "ponto_nao_graduado"
                cor = self._cor_ponto_config(canvas, chave_cfg, "#ff4a3d" if tipo == "canto" else "#ff9a3d")
                forma = self._forma_ponto_config(canvas, chave_cfg, "Circulo preenchido" if tipo == "canto" else "Losango")
                tamanho = 9 if tipo == "canto" else 7
                for _chave, _idx_original, pt in self._controles_molde_tipo(el, tipo):
                    self._desenhar_marcador_configurado(canvas, painter, pt, cor, forma, tamanho)
        painter.restore()

    def _ponto_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int) -> QPointF | None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        controles = self._controles_molde_tipo(canvas.cena.elementos[idx], tipo)
        if not (0 <= controle_idx < len(controles)):
            return None
        return QPointF(controles[controle_idx][2])

    def _fixar_hover_proximo_controle(self, canvas, idx: int, pos: QPointF) -> None:
        alvo = self._controle_molde_em_ponto_indices(canvas, pos, [idx], 80.0)
        self._hover_alvo = ("molde", *alvo) if alvo is not None else None

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
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
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

    def _controles_molde_tipo(self, el: dict, tipo: str) -> list[tuple[str, int, QPointF]]:
        chaves = (
            ("controle_cantos", "pontos_controle_principais")
            if tipo == "canto"
            else ("controle_auxiliares", "pontos_auxiliares")
        )
        saida: list[tuple[str, int, QPointF]] = []
        vistos: set[tuple[float, float]] = set()
        for chave in chaves:
            valores = el.get(chave, []) or []
            if not isinstance(valores, list):
                continue
            for idx_original, item in enumerate(valores):
                pt = self._ponto_qt(item)
                if pt is None:
                    continue
                assinatura = (round(float(pt.x()), 7), round(float(pt.y()), 7))
                if assinatura in vistos:
                    continue
                vistos.add(assinatura)
                saida.append((chave, idx_original, QPointF(pt)))
        return saida

    def _excluir_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            return False

        controles_tipo = self._controles_molde_tipo(el, tipo)
        if not (0 <= controle_idx < len(controles_tipo)):
            self.set_status("Controle inválido para exclusão.")
            return False

        if tipo == "canto":
            molde_curvo = self._molde_tem_curva_para_exclusao(canvas, el)
            minimo_principais = 1 if molde_curvo else 3
            if len(controles_tipo) <= minimo_principais:
                self.set_status(
                    f"Não é possível excluir: o molde precisa manter pelo menos {minimo_principais} "
                    "ponto principal." if minimo_principais == 1
                    else "Não é possível excluir: o molde precisa manter pelo menos 3 pontos principais."
                )
                return False
        elif tipo == "aux" and self._molde_tem_curva_para_exclusao(canvas, el) and len(controles_tipo) <= 2:
            self.set_status(
                "Não é possível excluir: moldes curvos precisam manter pelo menos "
                "1 ponto principal e 2 pontos auxiliares."
            )
            return False

        ponto_removido = QPointF(controles_tipo[controle_idx][2])
        auxiliares_removidos: list[QPointF] = []
        auxiliares_adicionados: list[QPointF] = []
        if tipo == "canto":
            auxiliares_removidos, auxiliares_adicionados = self._ajuste_auxiliares_retas_apos_excluir_canto(canvas, el, controle_idx)
        restantes = [QPointF(pt) for pos, (_chave, _idx_original, pt) in enumerate(controles_tipo) if pos != controle_idx]
        if tipo == "canto":
            el["controle_cantos"] = [(float(pt.x()), float(pt.y())) for pt in restantes]
            el["pontos_controle_principais"] = [{"x": float(pt.x()), "y": float(pt.y())} for pt in restantes]
            if auxiliares_removidos:
                self._remover_auxiliares_por_pontos(el, auxiliares_removidos)
            if auxiliares_adicionados:
                self._adicionar_auxiliares_unicos(el, auxiliares_adicionados)
        else:
            el["controle_auxiliares"] = [(float(pt.x()), float(pt.y())) for pt in restantes]
            el["pontos_auxiliares"] = [{"x": float(pt.x()), "y": float(pt.y())} for pt in restantes]
            self._ajustar_retorno_reta_apos_excluir_auxiliar_curvo(canvas, el, ponto_removido)
        self._sincronizar_espelhos_controles_molde(el)
        self._remover_ponto_contorno_preservando_ordem(canvas, el, ponto_removido)
        for aux in auxiliares_removidos:
            self._remover_ponto_contorno_preservando_ordem(canvas, el, aux)
        el["_controles_topologia_alterada"] = True
        el["_preservar_ordem_contorno_auxiliares"] = not bool(auxiliares_adicionados)
        if not self._regenerar_molde_por_controles(canvas, el):
            self.set_status("Exclusão cancelada: não foi possível regenerar o contorno.")
            return False
        return True

    def _molde_tem_curva_para_exclusao(self, canvas, el: dict) -> bool:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        if len(auxiliares) < 2:
            return False
        if len(cantos) <= 1:
            return True
        fechado = self._helper._molde_fechado_por_pontos_ou_controles(canvas, el, el.get("pontos", []) or [], cantos)
        segmentos = self._helper._segmentos_cantos(cantos, fechado)
        por_segmento = self._helper._auxiliares_por_segmento_indexados(cantos, segmentos, auxiliares, preferir_ordem=False)
        return any(len(itens) >= 2 for itens in por_segmento.values())

    def _ajustar_retorno_reta_apos_excluir_auxiliar_curvo(self, canvas, el: dict, ponto_removido: QPointF) -> None:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        if len(cantos) < 2 or not auxiliares:
            return
        fechado = self._helper._molde_fechado_por_pontos_ou_controles(canvas, el, el.get("pontos", []) or [], cantos)
        segmentos = self._helper._segmentos_cantos(cantos, fechado)
        if not segmentos:
            return
        por_segmento = self._helper._auxiliares_por_segmento_indexados(cantos, segmentos, auxiliares, preferir_ordem=False)
        melhor_seg = None
        melhor_dist = float("inf")
        for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
            if a_idx == b_idx:
                continue
            dist = self._helper._distancia_ponto_segmento_local(ponto_removido, cantos[a_idx], cantos[b_idx])
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_seg = seg_ordem
        if melhor_seg is None:
            return
        itens = por_segmento.get(melhor_seg, [])
        if len(itens) != 1:
            return
        aux_idx, _t, _pt = itens[0]
        if not (0 <= aux_idx < len(auxiliares)):
            return
        a_idx, b_idx = segmentos[melhor_seg]
        a = cantos[a_idx]
        b = cantos[b_idx]
        auxiliares[aux_idx] = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
        el["controle_auxiliares"] = [(float(pt.x()), float(pt.y())) for pt in auxiliares]
        el["pontos_auxiliares"] = [{"x": float(pt.x()), "y": float(pt.y())} for pt in auxiliares]

    def _ajuste_auxiliares_retas_apos_excluir_canto(self, canvas, el: dict, canto_idx: int) -> tuple[list[QPointF], list[QPointF]]:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        if not cantos or not (0 <= canto_idx < len(cantos)):
            return [], []
        fechado = self._helper._molde_fechado_por_pontos_ou_controles(canvas, el, el.get("pontos", []) or [], cantos)
        segmentos = self._helper._segmentos_cantos(cantos, fechado)
        por_segmento = self._helper._auxiliares_por_segmento_indexados(cantos, segmentos, auxiliares, preferir_ordem=False)
        remover: list[QPointF] = []
        segmentos_reta_adjacentes: list[tuple[int, int]] = []
        for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
            if canto_idx not in {a_idx, b_idx}:
                continue
            itens = por_segmento.get(seg_ordem, [])
            if len(itens) <= 1:
                segmentos_reta_adjacentes.append((a_idx, b_idx))
            if len(itens) == 1:
                _aux_idx, _t, pt = itens[0]
                remover.append(QPointF(pt))
        adicionar: list[QPointF] = []
        if len(segmentos_reta_adjacentes) == 2:
            vizinhos = []
            for a_idx, b_idx in segmentos_reta_adjacentes:
                vizinhos.append(b_idx if a_idx == canto_idx else a_idx)
            if len(vizinhos) == 2 and vizinhos[0] != vizinhos[1]:
                a = cantos[vizinhos[0]]
                b = cantos[vizinhos[1]]
                adicionar.append(QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0))
        return remover, adicionar

    def _remover_auxiliares_por_pontos(self, el: dict, pontos_remover: list[QPointF]) -> None:
        if not pontos_remover:
            return
        def manter(item) -> bool:
            pt = self._ponto_qt(item)
            if pt is None:
                return False
            return not any(self._dist_local(pt, alvo) <= 1e-6 for alvo in pontos_remover)

        el["controle_auxiliares"] = [
            self._tupla_xy(item)
            for item in el.get("controle_auxiliares", []) or []
            if manter(item) and self._tupla_xy(item) is not None
        ]
        el["pontos_auxiliares"] = [
            {"x": float(pt[0]), "y": float(pt[1])}
            for pt in el["controle_auxiliares"]
        ]

    def _adicionar_auxiliares_unicos(self, el: dict, pontos_adicionar: list[QPointF]) -> None:
        auxiliares = [self._tupla_xy(item) for item in el.get("controle_auxiliares", []) or []]
        auxiliares = [item for item in auxiliares if item is not None]
        existentes = {(round(float(x), 7), round(float(y), 7)) for x, y in auxiliares}
        for pt in pontos_adicionar:
            assinatura = (round(float(pt.x()), 7), round(float(pt.y()), 7))
            if assinatura in existentes:
                continue
            existentes.add(assinatura)
            auxiliares.append((float(pt.x()), float(pt.y())))
        el["controle_auxiliares"] = auxiliares
        el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]

    def _remover_ponto_contorno_preservando_ordem(self, canvas, el: dict, ponto: QPointF) -> bool:
        pontos = [self._ponto_qt(item) for item in el.get("pontos", []) or []]
        pontos = [pt for pt in pontos if pt is not None]
        if len(pontos) < 2:
            return True
        fechado = len(pontos) >= 3 and self._dist_local(pontos[0], pontos[-1]) <= 1e-6
        base = pontos[:-1] if fechado else pontos
        if len(base) <= 2:
            return True
        melhor_idx = min(range(len(base)), key=lambda i: self._dist_local(base[i], ponto))
        tolerancia = max(0.20, 8.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        if self._dist_local(base[melhor_idx], ponto) > tolerancia:
            return True
        base.pop(melhor_idx)
        if len(base) < 2:
            return False
        novos = [(float(pt.x()), float(pt.y())) for pt in base]
        if fechado:
            novos.append(novos[0])
            el["fechado"] = True
        el["pontos"] = novos
        return True

    def _sincronizar_espelhos_controles_molde(self, el: dict) -> None:
        cantos = [self._tupla_xy(item) for item in el.get("controle_cantos", []) or []]
        auxiliares = [self._tupla_xy(item) for item in el.get("controle_auxiliares", []) or []]
        cantos = [item for item in cantos if item is not None]
        auxiliares = [item for item in auxiliares if item is not None]
        el["controle_cantos"] = cantos
        el["controle_auxiliares"] = auxiliares
        el["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in cantos]
        el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]

    def _segmentos_para_recompor_apos_exclusao(self, canvas, el: dict, tipo: str, controle_idx: int) -> set[int]:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        if not cantos:
            return set()
        pontos = list(el.get("pontos", []) or [])
        fechado = self._helper._molde_fechado_por_pontos_ou_controles(canvas, el, pontos, cantos)
        segmentos = self._helper._segmentos_cantos(cantos, fechado)
        if not segmentos:
            return set()
        if tipo == "canto":
            if len(cantos) <= 2:
                return {0}
            return {
                seg_idx
                for seg_idx, (a_idx, b_idx) in enumerate(segmentos)
                if a_idx == controle_idx or b_idx == controle_idx
            }
        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        por_segmento = self._helper._auxiliares_por_segmento_indexados(cantos, segmentos, auxiliares, preferir_ordem=False)
        for seg_idx, itens in por_segmento.items():
            if any(aux_idx == controle_idx for aux_idx, _t, _pt in itens):
                return {seg_idx}
        return set()

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
    def _vertice_em_ponto(self, canvas, pos: QPointF, indices: list[int] | None = None) -> tuple[int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int] | None = None
        melhor_d = tolerancia
        candidatos = indices if indices is not None else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
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

    def _controle_curva_em_ponto(self, canvas, pos: QPointF, indices: list[int] | None = None) -> tuple[int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int] | None = None
        melhor_d = tolerancia
        candidatos = indices if indices is not None else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
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
