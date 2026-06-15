from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QMessageBox

from tools.tool_base import FerramentaBase
from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos

try:
    from core.geometry_cpp_bridge import sample_catmull_rom_centripetal_dynamic_cpp
except Exception:  # pragma: no cover - ambientes sem ponte C++
    sample_catmull_rom_centripetal_dynamic_cpp = None


class Ferramenta(FerramentaBase):
    id_ferramenta = "excluir_ponto"
    nome = "Excluir Ponto"
    descricao_painel = "Remove pontos de controle mantendo a geometria válida."

    def __init__(self):
        super().__init__()
        self._hover_alvo: tuple[str, int, str, int] | tuple[str, int, int] | None = None
        self._molde_confirmado_idx: int | None = None
        self._helper = FerramentaManipularPontos()

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover_alvo = None
        self._molde_confirmado_idx = None
        self.set_status("Clique no molde para confirmar; depois indique o ponto a apagar.")
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        pos_sem_snap = canvas._tela_para_cena(event.position()) if hasattr(canvas, "_tela_para_cena") else pos

        if self._molde_confirmado_idx is None:
            idx_confirmar = self._indice_molde_para_confirmar(canvas, pos_sem_snap, pos)
            if idx_confirmar is not None:
                self._confirmar_molde(canvas, idx_confirmar, pos)
                event.accept()
                return True

        alvo_controle = self._controle_molde_em_ponto(canvas, pos_sem_snap) or self._controle_molde_em_ponto(canvas, pos)
        if alvo_controle is not None:
            idx, tipo, controle_idx = alvo_controle
            if self._molde_confirmado_idx is not None and idx != self._molde_confirmado_idx:
                self._confirmar_molde(canvas, idx, pos)
                event.accept()
                return True
            ponto_removido = self._ponto_controle_molde(canvas, idx, tipo, controle_idx) or QPointF(pos)
            if not self._excluir_controle_molde(canvas, idx, tipo, controle_idx):
                self._mostrar_alerta_apagar_molde(canvas)
                canvas.update()
                event.accept()
                return True
            canvas._selecionados = {idx}
            self._molde_confirmado_idx = idx
            self._fixar_hover_proximo_controle(canvas, idx, ponto_removido)
            canvas._registrar_historico()
            canvas.update()
            self.set_status("Ponto do molde excluído e curva recalculada.")
            event.accept()
            return True

        if self._molde_confirmado_idx is not None:
            idx_confirmar = self._indice_molde_para_confirmar(canvas, pos_sem_snap, pos)
            if idx_confirmar is not None and idx_confirmar != self._molde_confirmado_idx:
                self._confirmar_molde(canvas, idx_confirmar, pos)
                event.accept()
                return True
            self.set_status("Indique um ponto principal ou auxiliar do molde para apagar.")
            event.accept()
            return True

        alvo_curva = self._controle_curva_em_ponto(canvas, pos)
        if alvo_curva is not None:
            idx, controle_idx = alvo_curva
            if idx not in (getattr(canvas, "_selecionados", set()) or set()):
                canvas._selecionados = {idx}
                canvas.update()
                self.set_status("Elemento selecionado. Clique novamente no ponto para excluir.")
                event.accept()
                return True
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

        if idx not in (getattr(canvas, "_selecionados", set()) or set()):
            canvas._selecionados = {idx}
            canvas.update()
            self.set_status("Elemento selecionado. Clique novamente no ponto para excluir.")
            event.accept()
            return True

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
        pos_sem_snap = canvas._tela_para_cena(event.position()) if hasattr(canvas, "_tela_para_cena") else pos
        if self._molde_confirmado_idx is not None:
            alvo_controle = (
                self._controle_molde_em_ponto_indices(canvas, pos_sem_snap, [self._molde_confirmado_idx], 22.0)
                or self._controle_molde_em_ponto_indices(canvas, pos, [self._molde_confirmado_idx], 22.0)
            )
        else:
            alvo_controle = self._controle_molde_em_ponto(canvas, pos_sem_snap) or self._controle_molde_em_ponto(canvas, pos)
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
        self._desenhar_controles_molde_selecionado(canvas, painter)
        ponto = self._ponto_hover(canvas)
        if ponto is None:
            return
        tela = canvas._cena_para_tela(ponto)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#ffffff"), 1.2))
        painter.setBrush(QColor("#2da8ff"))
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
    def _confirmar_molde(self, canvas, idx: int, pos: QPointF | None = None) -> None:
        canvas._selecionados = {idx}
        self._molde_confirmado_idx = idx
        if pos is not None:
            alvo = self._controle_molde_em_ponto_indices(canvas, pos, [idx], 22.0)
            self._hover_alvo = ("molde", *alvo) if alvo is not None else None
        else:
            self._hover_alvo = None
        self.set_status("Molde confirmado. Indique o ponto a apagar.")
        canvas.update()

    def _indice_molde_para_confirmar(self, canvas, pos_sem_snap: QPointF, pos_snap: QPointF) -> int | None:
        for pos in (pos_sem_snap, pos_snap):
            if hasattr(canvas, "_indice_molde_em_ponto"):
                try:
                    idx = canvas._indice_molde_em_ponto(pos)
                    if idx is not None:
                        return int(idx)
                except Exception:
                    pass
            alvo = self._controle_molde_em_ponto_indices(canvas, pos, self._indices_todos_moldes(canvas), 18.0)
            if alvo is not None:
                return int(alvo[0])
            idx = self._molde_fechado_contendo_ponto(canvas, pos)
            if idx is not None:
                return idx
        return None

    def _indices_todos_moldes(self, canvas) -> list[int]:
        return [
            idx
            for idx, el in enumerate(canvas.cena.elementos)
            if el.get("tipo") == "polyline" and el.get("molde")
        ]

    def _molde_fechado_contendo_ponto(self, canvas, pos: QPointF) -> int | None:
        for idx in reversed(self._indices_todos_moldes(canvas)):
            pontos = [self._ponto_qt(item) for item in canvas.cena.elementos[idx].get("pontos", []) or []]
            pontos = [p for p in pontos if p is not None]
            if len(pontos) < 3:
                continue
            if self._pontos_mesmos(pontos[0], pontos[-1]):
                pontos = pontos[:-1]
            if len(pontos) >= 3 and self._ponto_dentro_poligono(pos, pontos):
                return idx
        return None

    def _mostrar_alerta_apagar_molde(self, canvas) -> None:
        mensagem = "Não foi possível apagar ponto do molde!"
        self.set_status(mensagem)
        try:
            if hasattr(canvas, "isVisible") and canvas.isVisible():
                QMessageBox.warning(canvas, "Apagar pontos do molde", mensagem)
        except Exception:
            pass

    @staticmethod
    def _pontos_mesmos(a: QPointF, b: QPointF) -> bool:
        return abs(a.x() - b.x()) <= 1e-7 and abs(a.y() - b.y()) <= 1e-7

    @staticmethod
    def _ponto_dentro_poligono(pos: QPointF, pontos: list[QPointF]) -> bool:
        dentro = False
        j = len(pontos) - 1
        x = pos.x()
        y = pos.y()
        for i, pi in enumerate(pontos):
            pj = pontos[j]
            cruza = (pi.y() > y) != (pj.y() > y)
            if cruza:
                denom = pj.y() - pi.y()
                if abs(denom) <= 1e-12:
                    j = i
                    continue
                x_inter = ((pj.x() - pi.x()) * (y - pi.y()) / denom) + pi.x()
                if x < x_inter:
                    dentro = not dentro
            j = i
        return dentro

    def _controle_molde_em_ponto(self, canvas, pos: QPointF) -> tuple[int, str, int] | None:
        selecionados = self._indices_moldes_selecionados(canvas)
        if selecionados:
            alvo = self._controle_molde_em_ponto_indices(canvas, pos, selecionados, 22.0)
            if alvo is not None:
                return alvo
        todos = [
            idx
            for idx, el in enumerate(canvas.cena.elementos)
            if el.get("tipo") == "polyline" and el.get("molde")
        ]
        return self._controle_molde_em_ponto_indices(canvas, pos, todos, 10.0)

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
            for tipo, chave in (("canto", "controle_cantos"), ("aux", "controle_auxiliares")):
                controles = el.get(chave, []) or []
                if tipo == "aux" and not controles:
                    controles = el.get("pontos_auxiliares", []) or []
                for c_idx, item in enumerate(controles):
                    pt = self._ponto_qt(item)
                    if pt is None:
                        continue
                    d = canvas._dist(pt, pos)
                    if d <= melhor_d:
                        melhor_d = d
                        melhor = (idx, tipo, c_idx)
        return melhor

    def _indices_moldes_selecionados(self, canvas) -> list[int]:
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
            if el.get("tipo") == "polyline" and el.get("molde"):
                saida.append(idx_int)
        return saida

    def _desenhar_controles_molde_selecionado(self, canvas, painter) -> None:
        indices = self._indices_moldes_selecionados(canvas)
        if not indices:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        for idx in indices:
            el = canvas.cena.elementos[idx]
            for tipo, chave in (("canto", "controle_cantos"), ("aux", "controle_auxiliares")):
                cor = QColor("#2da8ff") if tipo == "canto" else QColor("#7fd8ff")
                painter.setPen(QPen(QColor("#ffffff"), 1.0))
                painter.setBrush(cor)
                raio = 4 if tipo == "canto" else 3
                for item in el.get(chave, []) or []:
                    pt = self._ponto_qt(item)
                    if pt is None:
                        continue
                    tela = canvas._cena_para_tela(pt)
                    painter.drawEllipse(int(tela.x() - raio), int(tela.y() - raio), raio * 2, raio * 2)
        painter.restore()

    def _ponto_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int) -> QPointF | None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
        controles = canvas.cena.elementos[idx].get(chave, []) or []
        if tipo == "aux" and not controles:
            controles = canvas.cena.elementos[idx].get("pontos_auxiliares", []) or []
        if not (0 <= controle_idx < len(controles)):
            return None
        return self._ponto_qt(controles[controle_idx])

    def _fixar_hover_proximo_controle(self, canvas, idx: int, pos: QPointF) -> None:
        alvo = self._controle_molde_em_ponto_indices(canvas, pos, [idx], 80.0)
        self._hover_alvo = ("molde", *alvo) if alvo is not None else None

    def _excluir_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            return False

        chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
        controles = list(el.get(chave, []) or [])
        if tipo == "aux" and not controles:
            controles = list(el.get("pontos_auxiliares", []) or [])
            el["controle_auxiliares"] = [
                (float(pt.x()), float(pt.y()))
                for pt in (self._ponto_qt(item) for item in controles)
                if pt is not None
            ]
            controles = list(el.get("controle_auxiliares", []) or [])
        if not (0 <= controle_idx < len(controles)):
            self.set_status("Controle inválido para exclusão.")
            return False

        if tipo == "canto" and self._deve_bloquear_exclusao_canto_molde(canvas, el):
            self.set_status("O molde precisa manter pelo menos 3 pontos principais.")
            return False

        if self._excluir_controle_molde_por_controles_restantes(canvas, el, tipo, controle_idx):
            return True

        self.set_status("Exclusão cancelada: controles restantes insuficientes para regenerar a curva.")
        return False

    def _deve_bloquear_exclusao_canto_molde(self, canvas, el: dict) -> bool:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        pontos = list(el.get("pontos", []) or [])
        fechado = self._helper._molde_fechado_por_pontos_ou_controles(canvas, el, pontos, cantos)
        return bool(fechado and (len(cantos) + len(auxiliares)) <= 3)

    def _excluir_controle_molde_por_controles_restantes(
        self,
        canvas,
        el: dict,
        tipo: str,
        controle_idx: int,
    ) -> bool:
        chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
        controles = list(el.get(chave, []) or [])
        if not (0 <= controle_idx < len(controles)):
            return False
        alvo = self._ponto_qt(controles[controle_idx])
        if alvo is None:
            return False

        pontos_anteriores = [self._tupla_xy(item) for item in el.get("pontos", []) or []]
        pontos_anteriores = [pt for pt in pontos_anteriores if pt is not None]
        cantos_anteriores = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        fechado = self._contorno_fechado_por_tuplas(pontos_anteriores) or bool(el.get("fechado"))
        segmento_repor_auxiliares = None
        if tipo == "aux":
            segmento_repor_auxiliares = self._segmento_principal_do_ponto(
                pontos_anteriores,
                cantos_anteriores,
                alvo,
                fechado,
            )
        segmento_recalcular_canto = None
        if tipo == "canto":
            segmento_recalcular_canto = self._segmento_mesclado_ao_remover_canto(
                pontos_anteriores,
                cantos_anteriores,
                alvo,
                fechado,
            )

        controles.pop(controle_idx)
        novos_controles = [self._tupla_xy(item) for item in controles if self._tupla_xy(item) is not None]
        outra_chave = "controle_auxiliares" if tipo == "canto" else "controle_cantos"
        outros_controles = self._remover_ponto_duplicado_de_controles(el.get(outra_chave, []) or [], alvo)

        if tipo == "canto":
            novos_cantos = novos_controles
            novos_auxiliares = outros_controles
        else:
            novos_cantos = outros_controles
            novos_auxiliares = novos_controles
        minimo_cantos = 3 if fechado else 2
        if tipo == "canto" and len(novos_cantos) < minimo_cantos:
            realocados = self._realocar_canto_removido(
                pontos_anteriores,
                novos_cantos,
                novos_auxiliares,
                alvo,
                fechado,
            )
            if realocados is None:
                return False
            novos_cantos, novos_auxiliares = realocados
        novos_cantos = self._ordenar_controles_no_contorno(novos_cantos, pontos_anteriores, fechado)
        cantos = [p for p in (self._ponto_qt(item) for item in novos_cantos) if p is not None]
        auxiliares = [p for p in (self._ponto_qt(item) for item in novos_auxiliares) if p is not None]
        if segmento_repor_auxiliares is not None:
            novos_auxiliares = self._garantir_minimo_auxiliares_no_segmento(
                pontos_anteriores,
                cantos,
                auxiliares,
                segmento_repor_auxiliares,
                fechado,
                evitar=[alvo],
                regenerar_abaixo_de=2,
            )
            auxiliares = [p for p in (self._ponto_qt(item) for item in novos_auxiliares) if p is not None]
        minimo = 3 if fechado else 2
        segmento_local = segmento_repor_auxiliares or segmento_recalcular_canto
        if segmento_local is not None:
            if segmento_recalcular_canto is not None:
                novos_auxiliares = self._garantir_minimo_auxiliares_no_segmento(
                    pontos_anteriores,
                    cantos,
                    auxiliares,
                    segmento_recalcular_canto,
                    fechado,
                    evitar=[alvo],
                )
                auxiliares = [p for p in (self._ponto_qt(item) for item in novos_auxiliares) if p is not None]
            novos_pontos = self._regenerar_apenas_segmento_auxiliar(
                pontos_anteriores,
                cantos,
                auxiliares,
                segmento_local,
                fechado,
            )
        else:
            controles_ordenados = self._controles_molde_restantes_ordenados(canvas, pontos_anteriores, cantos, auxiliares, fechado)
            if len(controles_ordenados) < minimo:
                return False
            novos_pontos = self._gerar_tracado_curva_molde(controles_ordenados, fechado=fechado)
        if len(novos_pontos) < minimo:
            return False
        if fechado and novos_pontos and not self._contorno_fechado_por_tuplas(novos_pontos):
            novos_pontos.append(novos_pontos[0])

        el["controle_cantos"] = [(float(x), float(y)) for x, y in novos_cantos]
        el["controle_auxiliares"] = [(float(x), float(y)) for x, y in novos_auxiliares]
        el["pontos"] = [(float(x), float(y)) for x, y in novos_pontos]
        el["fechado"] = bool(fechado)
        self._sincronizar_controles_molde(el)
        if tipo == "canto":
            self._remapear_graduacao_apos_remocao(
                el,
                [(float(p.x()), float(p.y())) for p in cantos_anteriores],
                [(float(x), float(y)) for x, y in el.get("controle_cantos", []) or []],
                controle_idx,
                fechado=fechado,
            )
        for temp_key in (
            "_controles_topologia_alterada",
            "_segmentos_auxiliares_arraste",
            "_auxiliares_retos_arraste",
            "_auxiliar_arrastado_idx",
        ):
            el.pop(temp_key, None)
        return True

    def _garantir_minimo_auxiliares_no_segmento(
        self,
        pontos_anteriores: list[tuple[float, float]],
        cantos: list[QPointF],
        auxiliares: list[QPointF],
        segmento: tuple[QPointF, QPointF],
        fechado: bool,
        evitar: list[QPointF] | None = None,
        regenerar_abaixo_de: int = 3,
        redistribuir_quando_curvo: bool = False,
    ) -> list[tuple[float, float]]:
        auxiliares_saida = [QPointF(p) for p in auxiliares]
        evitar = [QPointF(p) for p in (evitar or [])]
        regenerar_abaixo_de = max(0, int(regenerar_abaixo_de))
        auxiliares_no_segmento = [
            p
            for p in auxiliares_saida
            if self._mesmo_segmento_principal(
                self._segmento_principal_do_ponto(pontos_anteriores, cantos, p, fechado),
                segmento,
            )
        ]
        trecho = self._trecho_contorno_entre_pontos(pontos_anteriores, segmento[0], segmento[1], fechado)
        if not self._helper._segmento_molde_eh_curvo(segmento[0], segmento[1], trecho, auxiliares_no_segmento):
            return [(float(p.x()), float(p.y())) for p in auxiliares_saida]
        if len(auxiliares_no_segmento) >= regenerar_abaixo_de:
            if redistribuir_quando_curvo:
                return self._redistribuir_auxiliares_no_segmento(
                    pontos_anteriores,
                    cantos,
                    auxiliares_saida,
                    segmento,
                    fechado,
                    trecho,
                    len(auxiliares_no_segmento),
                    evitar,
                )
            return [(float(p.x()), float(p.y())) for p in auxiliares_saida]

        return self._redistribuir_auxiliares_no_segmento(
            pontos_anteriores,
            cantos,
            auxiliares_saida,
            segmento,
            fechado,
            trecho,
            3,
            evitar,
        )

    def _redistribuir_auxiliares_no_segmento(
        self,
        pontos_anteriores: list[tuple[float, float]],
        cantos: list[QPointF],
        auxiliares: list[QPointF],
        segmento: tuple[QPointF, QPointF],
        fechado: bool,
        trecho: list[QPointF],
        quantidade: int,
        evitar: list[QPointF] | None = None,
    ) -> list[tuple[float, float]]:
        quantidade = max(0, int(quantidade))
        evitar = [QPointF(p) for p in (evitar or [])]
        if quantidade <= 0:
            return [(float(p.x()), float(p.y())) for p in auxiliares]

        auxiliares_fora_segmento = [
            QPointF(p)
            for p in auxiliares
            if not self._mesmo_segmento_principal(
                self._segmento_principal_do_ponto(pontos_anteriores, cantos, p, fechado),
                segmento,
            )
        ]
        novos_segmento: list[QPointF] = []
        candidatos_alvo = self._pontos_auxiliares_em_trecho(trecho, segmento[0], segmento[1], total=quantidade)
        total_pool = max(quantidade * 6, 12)
        candidatos_pool = self._pontos_auxiliares_em_trecho(trecho, segmento[0], segmento[1], total=total_pool)

        for idx in range(quantidade):
            candidato = candidatos_alvo[idx] if idx < len(candidatos_alvo) else None
            if candidato is not None and self._ponto_auxiliar_distribuido_valido(
                candidato,
                cantos,
                auxiliares_fora_segmento,
                novos_segmento,
                evitar,
            ):
                novos_segmento.append(QPointF(candidato))
                continue

            alvo_fracao = (idx + 1) / float(quantidade + 1)
            melhor = None
            for pool_idx, pool_pt in enumerate(candidatos_pool):
                if not self._ponto_auxiliar_distribuido_valido(
                    pool_pt,
                    cantos,
                    auxiliares_fora_segmento,
                    novos_segmento,
                    evitar,
                ):
                    continue
                pool_fracao = (pool_idx + 1) / float(total_pool + 1)
                distancia_fracao = abs(pool_fracao - alvo_fracao)
                if melhor is None or distancia_fracao < melhor[0]:
                    melhor = (distancia_fracao, pool_pt)
            if melhor is not None:
                novos_segmento.append(QPointF(melhor[1]))
            elif candidato is not None:
                novos_segmento.append(QPointF(candidato))

        saida = [*auxiliares_fora_segmento, *novos_segmento]
        return [(float(p.x()), float(p.y())) for p in saida]

    def _ponto_auxiliar_distribuido_valido(
        self,
        candidato: QPointF,
        cantos: list[QPointF],
        auxiliares_fora_segmento: list[QPointF],
        novos_segmento: list[QPointF],
        evitar: list[QPointF],
    ) -> bool:
        if self._ponto_duplicado_em(candidato, evitar, 1e-5):
            return False
        if self._ponto_duplicado_em(candidato, cantos, 1e-5):
            return False
        if self._ponto_duplicado_em(candidato, auxiliares_fora_segmento, 1e-5):
            return False
        return not self._ponto_duplicado_em(candidato, novos_segmento, 1e-5)

    def _realocar_canto_removido(
        self,
        pontos_anteriores: list[tuple[float, float]],
        cantos: list[tuple[float, float]],
        auxiliares: list[tuple[float, float]],
        removido: QPointF,
        fechado: bool,
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]] | None:
        cantos_qt = [p for p in (self._ponto_qt(item) for item in cantos) if p is not None]
        auxiliares_qt = [p for p in (self._ponto_qt(item) for item in auxiliares) if p is not None]
        candidatos_aux = [
            (self._dist_local(pt, removido), idx, pt)
            for idx, pt in enumerate(auxiliares_qt)
            if not self._ponto_duplicado_em(pt, cantos_qt, 1e-5)
        ]
        if candidatos_aux:
            _dist, idx_promovido, promovido = min(candidatos_aux, key=lambda item: item[0])
            novos_aux = [pt for idx, pt in enumerate(auxiliares_qt) if idx != idx_promovido]
            novos_cantos = [*cantos_qt, QPointF(promovido)]
            return (
                self._ordenar_controles_qt_no_contorno(novos_cantos, pontos_anteriores, fechado),
                [(float(p.x()), float(p.y())) for p in novos_aux],
            )

        caminho = self._caminho_contorno_qt(pontos_anteriores, fechado)
        candidatos_contorno = [
            (self._dist_local(pt, removido), pt)
            for pt in caminho
            if self._dist_local(pt, removido) > 1e-5 and not self._ponto_duplicado_em(pt, cantos_qt, 1e-5)
        ]
        if not candidatos_contorno:
            return None
        _dist, promovido = min(candidatos_contorno, key=lambda item: item[0])
        novos_cantos = [*cantos_qt, QPointF(promovido)]
        return (
            self._ordenar_controles_qt_no_contorno(novos_cantos, pontos_anteriores, fechado),
            [(float(p.x()), float(p.y())) for p in auxiliares_qt],
        )

    def _segmento_principal_do_ponto(
        self,
        pontos_anteriores: list[tuple[float, float]],
        cantos: list[QPointF],
        ponto: QPointF,
        fechado: bool,
    ) -> tuple[QPointF, QPointF] | None:
        caminho = self._caminho_contorno_qt(pontos_anteriores, fechado)
        cantos_ordenados = self._cantos_ordenados_no_caminho(caminho, cantos, fechado)
        if len(cantos_ordenados) < 2 or len(caminho) < 2:
            return None

        posicoes = [
            (self._posicao_ponto_no_contorno(caminho, canto, fechado), QPointF(canto))
            for canto in cantos_ordenados
        ]
        posicoes.sort(key=lambda item: item[0])
        pos_ponto = self._posicao_ponto_no_contorno(caminho, ponto, fechado)
        tolerancia = 1e-6

        limite = len(posicoes) if fechado else len(posicoes) - 1
        for idx in range(limite):
            pos_a, a = posicoes[idx]
            pos_b, b = posicoes[(idx + 1) % len(posicoes)]
            if idx == len(posicoes) - 1 and fechado:
                if pos_ponto >= pos_a - tolerancia or pos_ponto <= pos_b + tolerancia:
                    return (a, b)
            elif pos_a - tolerancia <= pos_ponto <= pos_b + tolerancia:
                return (a, b)

        if fechado:
            return min(
                ((posicoes[i][1], posicoes[(i + 1) % len(posicoes)][1]) for i in range(len(posicoes))),
                key=lambda seg: self._distancia_ponto_segmento_qt(ponto, seg[0], seg[1]),
            )
        return None

    def _segmento_mesclado_ao_remover_canto(
        self,
        pontos_anteriores: list[tuple[float, float]],
        cantos: list[QPointF],
        canto_removido: QPointF,
        fechado: bool,
    ) -> tuple[QPointF, QPointF] | None:
        caminho = self._caminho_contorno_qt(pontos_anteriores, fechado)
        cantos_ordenados = self._cantos_ordenados_no_caminho(caminho, cantos, fechado)
        if len(cantos_ordenados) < 3 or len(caminho) < 2:
            return None
        idx = min(range(len(cantos_ordenados)), key=lambda i: self._dist_local(cantos_ordenados[i], canto_removido))
        if self._dist_local(cantos_ordenados[idx], canto_removido) > 1e-5:
            return None
        if fechado:
            return (QPointF(cantos_ordenados[idx - 1]), QPointF(cantos_ordenados[(idx + 1) % len(cantos_ordenados)]))
        if idx <= 0 or idx >= len(cantos_ordenados) - 1:
            return None
        return (QPointF(cantos_ordenados[idx - 1]), QPointF(cantos_ordenados[idx + 1]))

    def _caminho_contorno_qt(self, pontos: list[tuple[float, float]], fechado: bool) -> list[QPointF]:
        caminho = [QPointF(float(x), float(y)) for x, y in pontos]
        if fechado and len(caminho) >= 2 and self._dist_local(caminho[0], caminho[-1]) <= 1e-7:
            caminho = caminho[:-1]
        return caminho

    def _cantos_ordenados_no_caminho(self, caminho: list[QPointF], cantos: list[QPointF], fechado: bool) -> list[QPointF]:
        unicos = self._pontos_unicos([QPointF(p) for p in cantos])
        if len(unicos) <= 2 or len(caminho) < 2:
            return unicos
        return sorted(unicos, key=lambda pt: self._posicao_ponto_no_contorno(caminho, pt, fechado))

    def _ordenar_controles_no_contorno(
        self,
        controles: list[tuple[float, float]],
        pontos_anteriores: list[tuple[float, float]],
        fechado: bool,
    ) -> list[tuple[float, float]]:
        pontos = [p for p in (self._ponto_qt(item) for item in controles) if p is not None]
        return self._ordenar_controles_qt_no_contorno(pontos, pontos_anteriores, fechado)

    def _ordenar_controles_qt_no_contorno(
        self,
        controles: list[QPointF],
        pontos_anteriores: list[tuple[float, float]],
        fechado: bool,
    ) -> list[tuple[float, float]]:
        caminho = self._caminho_contorno_qt(pontos_anteriores, fechado)
        ordenados = self._cantos_ordenados_no_caminho(caminho, controles, fechado)
        return [(float(p.x()), float(p.y())) for p in ordenados]

    def _mesmo_segmento_principal(
        self,
        segmento_a: tuple[QPointF, QPointF] | None,
        segmento_b: tuple[QPointF, QPointF] | None,
    ) -> bool:
        if segmento_a is None or segmento_b is None:
            return False
        a0, a1 = segmento_a
        b0, b1 = segmento_b
        direto = self._dist_local(a0, b0) <= 1e-5 and self._dist_local(a1, b1) <= 1e-5
        inverso = self._dist_local(a0, b1) <= 1e-5 and self._dist_local(a1, b0) <= 1e-5
        return direto or inverso

    def _trecho_contorno_entre_pontos(
        self,
        pontos_anteriores: list[tuple[float, float]],
        inicio: QPointF,
        fim: QPointF,
        fechado: bool,
    ) -> list[QPointF]:
        caminho = self._caminho_contorno_qt(pontos_anteriores, fechado)
        if len(caminho) < 2:
            return [QPointF(inicio), QPointF(fim)]
        idx_inicio = min(range(len(caminho)), key=lambda i: self._dist_local(caminho[i], inicio))
        idx_fim = min(range(len(caminho)), key=lambda i: self._dist_local(caminho[i], fim))
        if fechado:
            trecho = [QPointF(caminho[idx_inicio])]
            idx = idx_inicio
            while idx != idx_fim:
                idx = (idx + 1) % len(caminho)
                trecho.append(QPointF(caminho[idx]))
                if len(trecho) > len(caminho) + 1:
                    break
        else:
            if idx_inicio > idx_fim:
                idx_inicio, idx_fim = idx_fim, idx_inicio
                inicio, fim = fim, inicio
            trecho = [QPointF(p) for p in caminho[idx_inicio : idx_fim + 1]]
        if trecho:
            trecho[0] = QPointF(inicio)
            trecho[-1] = QPointF(fim)
        return trecho if len(trecho) >= 2 else [QPointF(inicio), QPointF(fim)]

    def _pontos_auxiliares_em_trecho(
        self,
        trecho: list[QPointF],
        inicio: QPointF,
        fim: QPointF,
        total: int,
    ) -> list[QPointF]:
        total = max(0, int(total))
        if total <= 0:
            return []
        if len(trecho) < 2:
            return [self._interpolar(inicio, fim, (idx + 1) / (total + 1)) for idx in range(total)]
        comprimentos = [self._dist_local(a, b) for a, b in zip(trecho, trecho[1:])]
        perimetro = sum(comprimentos)
        if perimetro <= 1e-9:
            return [self._interpolar(inicio, fim, (idx + 1) / (total + 1)) for idx in range(total)]

        saida: list[QPointF] = []
        for idx in range(total):
            alvo = perimetro * ((idx + 1) / (total + 1))
            acumulado = 0.0
            for seg_idx, comprimento in enumerate(comprimentos):
                prox = acumulado + comprimento
                if alvo <= prox or seg_idx == len(comprimentos) - 1:
                    t = 0.0 if comprimento <= 1e-9 else (alvo - acumulado) / comprimento
                    saida.append(self._interpolar(trecho[seg_idx], trecho[seg_idx + 1], t))
                    break
                acumulado = prox
        return saida

    @staticmethod
    def _interpolar(a: QPointF, b: QPointF, t: float) -> QPointF:
        return QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))

    def _ponto_duplicado_em(self, ponto: QPointF, pontos: list[QPointF], tolerancia: float) -> bool:
        return any(self._dist_local(ponto, existente) <= tolerancia for existente in pontos)

    def _distancia_ponto_segmento_qt(self, ponto: QPointF, a: QPointF, b: QPointF) -> float:
        return self._parametro_e_distancia_segmento(ponto, a, b)[1]

    def _regenerar_apenas_segmento_auxiliar(
        self,
        pontos_anteriores: list[tuple[float, float]],
        cantos: list[QPointF],
        auxiliares: list[QPointF],
        segmento: tuple[QPointF, QPointF],
        fechado: bool,
    ) -> list[tuple[float, float]]:
        caminho = self._caminho_contorno_qt(pontos_anteriores, fechado)
        if len(caminho) < 2:
            return []
        a, b = QPointF(segmento[0]), QPointF(segmento[1])
        idx_a = min(range(len(caminho)), key=lambda i: self._dist_local(caminho[i], a))
        idx_b = min(range(len(caminho)), key=lambda i: self._dist_local(caminho[i], b))
        trecho_original = self._trecho_contorno_entre_pontos(pontos_anteriores, a, b, fechado)
        controles_internos = [
            QPointF(p)
            for p in [*cantos, *auxiliares]
            if self._dist_local(p, a) > 1e-5
            and self._dist_local(p, b) > 1e-5
            and self._ponto_esta_no_intervalo_contorno(caminho, p, a, b, fechado)
        ]
        controles_internos = self._pontos_unicos(controles_internos)
        controles_internos.sort(key=lambda p: self._posicao_ponto_no_trecho(trecho_original, p))
        controles_segmento = [a, *controles_internos, b]
        trecho_novo = [
            QPointF(float(x), float(y))
            for x, y in self._gerar_tracado_curva_molde(controles_segmento, fechado=False)
        ]
        if len(trecho_novo) < 2:
            trecho_novo = [a, b]
        trecho_novo[0] = a
        trecho_novo[-1] = b

        if fechado:
            if idx_a <= idx_b:
                novo_caminho = [*caminho[:idx_a], *trecho_novo, *caminho[idx_b + 1 :]]
            else:
                novo_caminho = [*trecho_novo, *caminho[idx_b + 1 : idx_a]]
        else:
            if idx_a <= idx_b:
                novo_caminho = [*caminho[:idx_a], *trecho_novo, *caminho[idx_b + 1 :]]
            else:
                trecho_invertido = list(reversed(trecho_novo))
                novo_caminho = [*caminho[:idx_b], *trecho_invertido, *caminho[idx_a + 1 :]]

        novo_caminho = self._remover_duplicados_consecutivos(novo_caminho)
        if fechado and novo_caminho:
            if self._dist_local(novo_caminho[0], novo_caminho[-1]) > 1e-7:
                novo_caminho.append(QPointF(novo_caminho[0]))
            else:
                novo_caminho[-1] = QPointF(novo_caminho[0])
        return [(float(p.x()), float(p.y())) for p in novo_caminho]

    def _gerar_tracado_curva_molde(self, controles: list[QPointF], fechado: bool) -> list[tuple[float, float]]:
        controles_qt = [QPointF(p) for p in controles]
        controles_tuplas = [(float(p.x()), float(p.y())) for p in controles_qt]
        if sample_catmull_rom_centripetal_dynamic_cpp is not None:
            pontos_cpp = sample_catmull_rom_centripetal_dynamic_cpp(controles_tuplas, closed=fechado)
            if pontos_cpp:
                return pontos_cpp
        return self._helper._gerar_tracado_curva_real(
            controles_qt,
            fechado=fechado,
            tipo_curva="spline_catmull_rom",
        )

    def _posicao_ponto_no_trecho(self, trecho: list[QPointF], ponto: QPointF) -> float:
        if len(trecho) < 2:
            return 0.0
        acumulado = 0.0
        melhor = 0.0
        melhor_dist = float("inf")
        for a, b in zip(trecho, trecho[1:]):
            comprimento = self._dist_local(a, b)
            t, dist = self._parametro_e_distancia_segmento(ponto, a, b)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor = acumulado + (comprimento * t)
            acumulado += comprimento
        return melhor

    def _ponto_esta_no_intervalo_contorno(
        self,
        caminho: list[QPointF],
        ponto: QPointF,
        inicio: QPointF,
        fim: QPointF,
        fechado: bool,
    ) -> bool:
        if len(caminho) < 2:
            return False
        pos_inicio = self._posicao_ponto_no_contorno(caminho, inicio, fechado)
        pos_fim = self._posicao_ponto_no_contorno(caminho, fim, fechado)
        pos_ponto = self._posicao_ponto_no_contorno(caminho, ponto, fechado)
        tolerancia = 1e-6
        if fechado and pos_inicio > pos_fim:
            return pos_ponto >= pos_inicio - tolerancia or pos_ponto <= pos_fim + tolerancia
        return pos_inicio - tolerancia <= pos_ponto <= pos_fim + tolerancia

    def _remover_duplicados_consecutivos(self, pontos: list[QPointF]) -> list[QPointF]:
        saida: list[QPointF] = []
        for ponto in pontos:
            if saida and self._dist_local(saida[-1], ponto) <= 1e-7:
                continue
            saida.append(QPointF(ponto))
        return saida

    def _controles_molde_restantes_ordenados(
        self,
        canvas,
        pontos_anteriores: list[tuple[float, float]],
        cantos: list[QPointF],
        auxiliares: list[QPointF],
        fechado: bool,
    ) -> list[QPointF]:
        controles = [QPointF(p) for p in cantos] + [QPointF(p) for p in auxiliares]
        controles = self._pontos_unicos(controles)
        if len(controles) <= 2:
            return controles

        caminho = [QPointF(float(x), float(y)) for x, y in pontos_anteriores]
        if fechado and len(caminho) >= 2 and self._dist_local(caminho[0], caminho[-1]) <= 1e-7:
            caminho = caminho[:-1]
        if len(caminho) < 2:
            return controles

        ordenados = sorted(
            controles,
            key=lambda pt: self._posicao_ponto_no_contorno(caminho, pt, fechado),
        )
        return self._rotacionar_controles_para_primeiro_canto(ordenados, cantos) if fechado else ordenados

    def _rotacionar_controles_para_primeiro_canto(self, controles: list[QPointF], cantos: list[QPointF]) -> list[QPointF]:
        if not controles or not cantos:
            return controles
        primeiro = cantos[0]
        melhor = min(range(len(controles)), key=lambda idx: self._dist_local(controles[idx], primeiro))
        return [*controles[melhor:], *controles[:melhor]]

    def _posicao_ponto_no_contorno(self, caminho: list[QPointF], ponto: QPointF, fechado: bool) -> float:
        if len(caminho) < 2:
            return 0.0
        limite = len(caminho) if fechado else len(caminho) - 1
        acumulado = 0.0
        melhor_pos = 0.0
        melhor_dist = float("inf")
        for idx in range(limite):
            a = caminho[idx]
            b = caminho[(idx + 1) % len(caminho)]
            dist_ab = self._dist_local(a, b)
            t, dist = self._parametro_e_distancia_segmento(ponto, a, b)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_pos = acumulado + (dist_ab * t)
            acumulado += dist_ab
        return melhor_pos

    @staticmethod
    def _parametro_e_distancia_segmento(p: QPointF, a: QPointF, b: QPointF) -> tuple[float, float]:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return 0.0, Ferramenta._dist_local(p, a)
        t = max(0.0, min(1.0, (((p.x() - a.x()) * abx) + ((p.y() - a.y()) * aby)) / den))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return t, Ferramenta._dist_local(p, proj)

    def _pontos_unicos(self, pontos: list[QPointF]) -> list[QPointF]:
        saida: list[QPointF] = []
        for ponto in pontos:
            if any(self._dist_local(ponto, existente) <= 1e-7 for existente in saida):
                continue
            saida.append(QPointF(ponto))
        return saida

    def _sincronizar_controles_molde(self, el: dict) -> None:
        cantos = [pt for item in el.get("controle_cantos", []) or [] if (pt := self._tupla_xy(item)) is not None]
        auxiliares = [pt for item in el.get("controle_auxiliares", []) or [] if (pt := self._tupla_xy(item)) is not None]
        el["controle_cantos"] = [(float(x), float(y)) for x, y in cantos]
        el["controle_auxiliares"] = [(float(x), float(y)) for x, y in auxiliares]
        el["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in cantos]
        el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]

    def _remapear_graduacao_apos_remocao(
        self,
        el: dict,
        pontos_antes: list[tuple[float, float]],
        pontos_depois: list[tuple[float, float]],
        removido_idx: int,
        *,
        fechado: bool,
    ) -> None:
        pontos_cfg = self._pontos_config_graduacao(el)
        if not pontos_cfg:
            return
        base_antes = self._contorno_sem_fechamento(pontos_antes)
        base_depois = self._contorno_sem_fechamento(pontos_depois)
        if len(base_antes) < 2 or len(base_depois) < 2:
            return
        if not (0 <= int(removido_idx) < len(base_antes)):
            return
        try:
            from canvas.visualizacao import VisualizacaoCanvas
        except Exception:
            return

        nomes_tamanhos = self._nomes_tamanhos_graduacao(el, pontos_cfg)
        if not nomes_tamanhos:
            return

        contorno_antes = [QPointF(x, y) for x, y in base_antes]
        referencias_antes = [QPointF(x, y) for x, y in base_antes]
        deslocamentos_por_tamanho: dict[str, list[tuple[float, float]]] = {}
        for nome in nomes_tamanhos:
            deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
                pontos_cfg,
                nome,
                len(contorno_antes),
                contorno=contorno_antes,
                referencias=referencias_antes,
            )
            if not deslocamentos or len(deslocamentos) != len(contorno_antes):
                deslocamentos = [(0.0, 0.0) for _ in contorno_antes]
            deslocamentos_por_tamanho[str(nome)] = deslocamentos

        pontos_remapeados: dict[str, dict] = {}
        for novo_idx, ponto in enumerate(base_depois):
            ponto_qt = QPointF(float(ponto[0]), float(ponto[1]))
            valores: dict[str, dict[str, float]] = {}
            for nome, deslocamentos in deslocamentos_por_tamanho.items():
                dx, dy = self._deslocamento_interpolado_remocao(
                    ponto_qt,
                    contorno_antes,
                    deslocamentos,
                    fechado=fechado,
                )
                valores[nome] = {"dx": float(dx), "dy": float(dy)}
            pontos_remapeados[str(novo_idx)] = {
                "indice": int(novo_idx),
                "numero": int(novo_idx) + 1,
                "ponto": (float(ponto[0]), float(ponto[1])),
                "valores": valores,
            }

        pontos_ordenados = self._ordenar_pontos_graduacao(pontos_remapeados)
        tabela = el.setdefault("graduacao_tabela", {})
        if isinstance(tabela, dict):
            tabela["modo"] = "dx_dy"
            tabela["pontos"] = pontos_ordenados
        el["graduacao_pontos"] = deepcopy(pontos_ordenados)

    def _deslocamento_interpolado_remocao(
        self,
        ponto: QPointF,
        contorno: list[QPointF],
        deslocamentos: list[tuple[float, float]],
        *,
        fechado: bool,
    ) -> tuple[float, float]:
        if not contorno or len(contorno) != len(deslocamentos):
            return (0.0, 0.0)
        for idx, existente in enumerate(contorno):
            if self._dist_local(ponto, existente) <= 1e-6:
                dx, dy = deslocamentos[idx]
                return (float(dx), float(dy))

        limite = len(contorno) if fechado and len(contorno) > 2 else len(contorno) - 1
        melhor: tuple[float, int, int, float] | None = None
        for idx in range(max(0, limite)):
            prox_idx = (idx + 1) % len(contorno)
            t, distancia = self._parametro_e_distancia_segmento(ponto, contorno[idx], contorno[prox_idx])
            if melhor is None or distancia < melhor[0]:
                melhor = (distancia, idx, prox_idx, t)
        if melhor is None:
            return (0.0, 0.0)

        _distancia, idx_a, idx_b, fator = melhor
        dx_a, dy_a = deslocamentos[idx_a]
        dx_b, dy_b = deslocamentos[idx_b]
        return (
            float(dx_a + ((dx_b - dx_a) * fator)),
            float(dy_a + ((dy_b - dy_a) * fator)),
        )

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

    @staticmethod
    def _ordenar_pontos_graduacao(pontos_cfg: dict) -> dict:
        def chave_ordem(item) -> int:
            try:
                return int(item[0])
            except Exception:
                return 0

        return {str(chave): valor for chave, valor in sorted(pontos_cfg.items(), key=chave_ordem)}

    def _contorno_sem_fechamento(self, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        contorno = [(float(x), float(y)) for x, y in pontos]
        if len(contorno) > 1 and self._dist_tuple(contorno[0], contorno[-1]) <= 1e-6:
            contorno = contorno[:-1]
        return contorno

    def _remover_ponto_duplicado_de_controles(self, controles: list, alvo: QPointF) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []
        for item in controles:
            pt = self._tupla_xy(item)
            if pt is None:
                continue
            if self._dist_local(QPointF(float(pt[0]), float(pt[1])), alvo) <= 1e-6:
                continue
            saida.append((float(pt[0]), float(pt[1])))
        return saida

    @staticmethod
    def _contorno_fechado_por_tuplas(pontos: list[tuple[float, float]]) -> bool:
        if len(pontos) < 3:
            return False
        return abs(float(pontos[0][0]) - float(pontos[-1][0])) <= 1e-7 and abs(float(pontos[0][1]) - float(pontos[-1][1])) <= 1e-7

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

    @staticmethod
    def _dist_tuple(a: tuple[float, float] | None, b: tuple[float, float]) -> float:
        if a is None:
            return float("inf")
        dx = float(a[0]) - float(b[0])
        dy = float(a[1]) - float(b[1])
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
        controles_antes = self._controles_curva(el)
        controles = list(controles_antes)
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
        self._remapear_graduacao_apos_remocao(
            el,
            [(float(p.x()), float(p.y())) for p in controles_antes],
            [(float(p.x()), float(p.y())) for p in controles],
            controle_idx,
            fechado=fechado,
        )
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
