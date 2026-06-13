from __future__ import annotations

from copy import deepcopy
from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "remover_pique"
    nome = "Remover Pique"
    usa_painel_auxiliar = False
    descricao_painel = "Remove piques configurados ou marcações simples do molde."

    def __init__(self):
        super().__init__()
        self._hover: tuple[int, str, int, QPointF] | None = None
        self._molde_idx: int | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover = None
        self._molde_idx = None
        self._status(canvas, "Remover Pique: clique no pique para apagar. Direito finaliza.")
        canvas.update()

    def on_deactivate(self, canvas):
        self._hover = None
        self._molde_idx = None
        canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_cena(canvas, event)
        indices = {self._molde_idx} if self._molde_idx is not None else None
        self._hover = self._alvo_pique(canvas, pos, indices=indices)
        canvas.update()
        event.accept()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._finalizar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = self._posicao_cena(canvas, event)
        indices = {self._molde_idx} if self._molde_idx is not None else None
        alvo = self._alvo_pique(canvas, pos, indices=indices)
        if alvo is None and self._molde_idx is None:
            molde_idx = self._molde_em_posicao(canvas, pos)
            if molde_idx is not None:
                self._selecionar_molde(canvas, molde_idx)
                self._status(canvas, "Molde selecionado. Clique no pique que deseja remover.")
                canvas.update()
                event.accept()
                return True
        if alvo is None:
            self._status(canvas, "Nenhum pique encontrado no clique.")
            event.accept()
            return True

        if self._remover_alvo(canvas, alvo):
            self._hover = None
            self._selecionar_molde(canvas, alvo[0])
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
            canvas.update()
            self._status(canvas, "Pique removido.")
            event.accept()
            return True

        self._status(canvas, "Não foi possível remover o pique indicado.")
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._hover is None:
            return
        _idx, _tipo, _pos_idx, ponto = self._hover
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        cor = QColor(self._cor_realce_canvas(canvas))
        painter.setPen(QPen(cor, 2))
        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        painter.drawEllipse(tela, 7, 7)
        painter.drawLine(QPointF(tela.x() - 9, tela.y() - 9), QPointF(tela.x() + 9, tela.y() + 9))
        painter.drawLine(QPointF(tela.x() - 9, tela.y() + 9), QPointF(tela.x() + 9, tela.y() - 9))
        painter.restore()

    def _selecionar_molde(self, canvas, idx: int) -> None:
        self._molde_idx = int(idx)
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(idx)}

    def _finalizar(self, canvas) -> None:
        self._hover = None
        self._molde_idx = None
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        else:
            canvas.update()
        self._status(canvas, "Ferramenta Remover Pique finalizada.")

    def _alvo_pique(
        self,
        canvas,
        pos: QPointF,
        *,
        indices: set[int] | None = None,
    ) -> tuple[int, str, int, QPointF] | None:
        tolerancia = 14.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor: tuple[float, int, str, int, QPointF] | None = None
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if indices is not None and idx not in indices:
                continue
            if not isinstance(el, dict) or not el.get("molde"):
                continue
            configs = [cfg for cfg in (el.get("piques_config", []) or []) if isinstance(cfg, dict)]
            for cfg_idx, cfg in enumerate(configs):
                ponto = self._ponto_pique_para_alvo(cfg)
                dist = self._dist(pos, ponto) if ponto is not None else float("inf")
                for segmento in cfg.get("segmentos", []) or []:
                    pts = self._segmento_cfg(segmento)
                    if pts is None:
                        continue
                    proj = self._projetar_ponto_segmento(pos, pts[0], pts[1])
                    dist_seg = self._dist(pos, proj)
                    if dist_seg < dist:
                        ponto = proj
                        dist = dist_seg
                if ponto is not None and dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, "config", cfg_idx, QPointF(ponto))
            for marc_idx, item in enumerate(el.get("marcacoes_no_perimetro", []) or []):
                ponto = self._ponto_qt(item)
                if ponto is None:
                    continue
                if any(self._mesmo_ponto(ponto, self._ponto_cfg(cfg)) for cfg in configs):
                    continue
                dist = self._dist(pos, ponto)
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, "marcacao", marc_idx, QPointF(ponto))
        if melhor is None:
            return None
        _dist, idx, tipo, item_idx, ponto = melhor
        return idx, tipo, item_idx, ponto

    def _remover_alvo(self, canvas, alvo: tuple[int, str, int, QPointF]) -> bool:
        idx, tipo, item_idx, ponto = alvo
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        if not isinstance(el, dict):
            return False

        if tipo == "marcacao":
            marcacoes = list(el.get("marcacoes_no_perimetro", []) or [])
            if not (0 <= item_idx < len(marcacoes)):
                return False
            del marcacoes[item_idx]
            if marcacoes:
                el["marcacoes_no_perimetro"] = marcacoes
            else:
                el.pop("marcacoes_no_perimetro", None)
            return True

        configs = [cfg for cfg in (el.get("piques_config", []) or []) if isinstance(cfg, dict)]
        if not (0 <= item_idx < len(configs)):
            return False
        cfg = configs.pop(item_idx)
        if configs:
            el["piques_config"] = configs
        else:
            el.pop("piques_config", None)

        ponto_cfg = self._ponto_cfg(cfg) or QPointF(ponto)
        self._remover_marcacao_sem_config_restante(el, ponto_cfg, configs)

        if bool(cfg.get("adicionar_ponto_controle")):
            ponto_controle = self._ponto_qt(cfg.get("ponto_controle")) or ponto_cfg
            if bool(cfg.get("sobre_contorno", True)):
                self._remover_ponto_principal_intermediario(el, ponto_controle, configs)
            else:
                self._remover_ponto_auxiliar(el, ponto_controle, configs)
        return True

    def _remover_marcacao_sem_config_restante(self, el: dict, ponto: QPointF, configs_restantes: list[dict]) -> None:
        if self._ponto_usado_por_configs(configs_restantes, ponto, incluir_controle=False):
            return
        marcacoes = []
        for item in el.get("marcacoes_no_perimetro", []) or []:
            pt = self._ponto_qt(item)
            if pt is not None and self._dist(pt, ponto) <= 1e-6:
                continue
            marcacoes.append(item)
        if marcacoes:
            el["marcacoes_no_perimetro"] = marcacoes
        else:
            el.pop("marcacoes_no_perimetro", None)

    def _remover_ponto_auxiliar(self, el: dict, ponto: QPointF, configs_restantes: list[dict]) -> None:
        if self._ponto_usado_por_configs(configs_restantes, ponto, incluir_controle=True):
            return
        auxiliares = [
            pt for pt in (self._tupla_ponto(item) for item in el.get("controle_auxiliares", []) or [])
            if pt is not None and self._dist_tuple(pt, (ponto.x(), ponto.y())) > 1e-6
        ]
        if auxiliares:
            el["controle_auxiliares"] = auxiliares
            el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]
        else:
            el["controle_auxiliares"] = []
            el["pontos_auxiliares"] = []

    def _remover_ponto_principal_intermediario(self, el: dict, ponto: QPointF, configs_restantes: list[dict]) -> None:
        if self._ponto_usado_por_configs(configs_restantes, ponto, incluir_controle=True):
            return
        pontos = [pt for pt in (self._tupla_ponto(item) for item in el.get("pontos", []) or []) if pt is not None]
        if len(pontos) < 3:
            return
        fechado = self._dist_tuple(pontos[0], pontos[-1]) <= 1e-6
        base = pontos[:-1] if fechado else list(pontos)
        idx = self._indice_ponto_mais_proximo(base, (ponto.x(), ponto.y()))
        if idx is None or self._dist_tuple(base[idx], (ponto.x(), ponto.y())) > 1e-6:
            return
        if not self._ponto_intermediario_colinear(base, idx, fechado):
            return

        base_depois = list(base)
        del base_depois[idx]
        if len(base_depois) < 2:
            return
        novos_pontos = list(base_depois)
        if fechado:
            novos_pontos.append(novos_pontos[0])
        self._remapear_graduacao_apos_remocao(el, base, base_depois, idx)
        el["pontos"] = novos_pontos

        cantos = [
            pt for pt in (self._tupla_ponto(item) for item in el.get("controle_cantos", []) or [])
            if pt is not None and self._dist_tuple(pt, (ponto.x(), ponto.y())) > 1e-6
        ]
        el["controle_cantos"] = cantos
        el["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in cantos]

    def _remapear_graduacao_apos_remocao(
        self,
        el: dict,
        base_antes: list[tuple[float, float]],
        base_depois: list[tuple[float, float]],
        removido_idx: int,
    ) -> None:
        pontos_cfg = self._pontos_config_graduacao(el)
        if not pontos_cfg:
            return
        remapeados: dict[str, dict] = {}
        for chave, cfg in pontos_cfg.items():
            if not isinstance(cfg, dict):
                continue
            antigo_idx = self._indice_graduacao_cfg(cfg, chave, base_antes)
            if antigo_idx is None or antigo_idx == removido_idx:
                continue
            novo_idx = antigo_idx - 1 if antigo_idx > removido_idx else antigo_idx
            if not (0 <= novo_idx < len(base_depois)):
                continue
            novo_cfg = deepcopy(cfg)
            novo_cfg["indice"] = int(novo_idx)
            novo_cfg["numero"] = int(novo_idx) + 1
            novo_cfg["ponto"] = (float(base_depois[novo_idx][0]), float(base_depois[novo_idx][1]))
            remapeados[str(novo_idx)] = novo_cfg
        remapeados = self._ordenar_pontos_graduacao(remapeados)
        tabela = el.get("graduacao_tabela") if isinstance(el.get("graduacao_tabela"), dict) else None
        if isinstance(tabela, dict):
            tabela["modo"] = "dx_dy"
            tabela["pontos"] = remapeados
        el["graduacao_pontos"] = deepcopy(remapeados)

    @staticmethod
    def _ponto_intermediario_colinear(base: list[tuple[float, float]], idx: int, fechado: bool) -> bool:
        if len(base) < 3:
            return False
        if not fechado and (idx == 0 or idx == len(base) - 1):
            return False
        anterior = base[(idx - 1) % len(base)]
        atual = base[idx]
        proximo = base[(idx + 1) % len(base)]
        area = abs(
            ((atual[0] - anterior[0]) * (proximo[1] - anterior[1]))
            - ((atual[1] - anterior[1]) * (proximo[0] - anterior[0]))
        )
        comp = max(1e-9, sqrt(((proximo[0] - anterior[0]) ** 2) + ((proximo[1] - anterior[1]) ** 2)))
        return (area / comp) <= 1e-6

    def _pontos_config_graduacao(self, el: dict) -> dict:
        tabela = el.get("graduacao_tabela") if isinstance(el.get("graduacao_tabela"), dict) else None
        if isinstance(tabela, dict) and isinstance(tabela.get("pontos"), dict):
            return tabela.get("pontos") or {}
        legado = el.get("graduacao_pontos")
        return legado if isinstance(legado, dict) else {}

    def _indice_graduacao_cfg(self, cfg: dict, chave: str, base: list[tuple[float, float]]) -> int | None:
        ponto_cfg = self._tupla_ponto(cfg.get("ponto")) if isinstance(cfg, dict) else None
        if ponto_cfg is not None:
            return self._indice_ponto_mais_proximo(base, ponto_cfg)
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

    def _ponto_usado_por_configs(self, configs: list[dict], ponto: QPointF, *, incluir_controle: bool) -> bool:
        for cfg in configs:
            candidatos = [self._ponto_cfg(cfg)]
            if incluir_controle:
                candidatos.append(self._ponto_qt(cfg.get("ponto_controle")))
            for candidato in candidatos:
                if candidato is not None and self._dist(candidato, ponto) <= 1e-6:
                    return True
        return False

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if isinstance(el, dict) and el.get("molde") and self._ponto_dentro_bbox(el, pos):
                return idx
        return None

    def _posicao_cena(self, canvas, event) -> QPointF:
        try:
            return canvas._ponto_com_snap(event.position())
        except Exception:
            if hasattr(canvas, "_tela_para_cena"):
                return canvas._tela_para_cena(event.position())
            return QPointF(event.position())

    @staticmethod
    def _ponto_pique_para_alvo(cfg: dict) -> QPointF | None:
        ponto = Ferramenta._ponto_cfg(cfg)
        if ponto is not None:
            return ponto
        return Ferramenta._ponto_qt(cfg.get("ponto_controle"))

    @staticmethod
    def _ponto_cfg(cfg: dict) -> QPointF | None:
        try:
            return Ferramenta._ponto_qt(cfg.get("ponto"))
        except Exception:
            return None

    @staticmethod
    def _ponto_qt(valor) -> QPointF | None:
        try:
            if isinstance(valor, QPointF):
                return QPointF(valor)
            if isinstance(valor, dict):
                return QPointF(float(valor["x"]), float(valor["y"]))
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return QPointF(float(valor[0]), float(valor[1]))
        except Exception:
            return None
        return None

    @staticmethod
    def _tupla_ponto(valor) -> tuple[float, float] | None:
        try:
            if isinstance(valor, QPointF):
                return float(valor.x()), float(valor.y())
            if isinstance(valor, dict):
                return float(valor["x"]), float(valor["y"])
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return float(valor[0]), float(valor[1])
        except Exception:
            return None
        return None

    @staticmethod
    def _segmento_cfg(segmento) -> tuple[QPointF, QPointF] | None:
        try:
            if isinstance(segmento, dict):
                a = segmento.get("a") or segmento.get("inicio")
                b = segmento.get("b") or segmento.get("fim")
            elif isinstance(segmento, (list, tuple)) and len(segmento) >= 2:
                a, b = segmento[0], segmento[1]
            else:
                return None
            pa = Ferramenta._ponto_qt(a)
            pb = Ferramenta._ponto_qt(b)
            if pa is None or pb is None:
                return None
            return pa, pb
        except Exception:
            return None

    @staticmethod
    def _projetar_ponto_segmento(p: QPointF, a: QPointF, b: QPointF) -> QPointF:
        vx = b.x() - a.x()
        vy = b.y() - a.y()
        denom = (vx * vx) + (vy * vy)
        if denom <= 1e-12:
            return QPointF(a)
        t = ((p.x() - a.x()) * vx + (p.y() - a.y()) * vy) / denom
        t = max(0.0, min(1.0, t))
        return QPointF(a.x() + (vx * t), a.y() + (vy * t))

    def _ponto_dentro_bbox(self, molde: dict, pos: QPointF) -> bool:
        pontos = [pt for pt in (self._tupla_ponto(item) for item in molde.get("pontos", []) or []) if pt is not None]
        if not pontos:
            return False
        xs = [x for x, _y in pontos]
        ys = [y for _x, y in pontos]
        return min(xs) <= pos.x() <= max(xs) and min(ys) <= pos.y() <= max(ys)

    @staticmethod
    def _indice_ponto_mais_proximo(pontos: list[tuple[float, float]], alvo: tuple[float, float]) -> int | None:
        if not pontos:
            return None
        melhor_idx = 0
        melhor_dist = float("inf")
        for idx, ponto in enumerate(pontos):
            dist = Ferramenta._dist_tuple(ponto, alvo)
            if dist < melhor_dist:
                melhor_idx = idx
                melhor_dist = dist
        return melhor_idx

    @staticmethod
    def _mesmo_ponto(a: QPointF | None, b: QPointF | None) -> bool:
        return a is not None and b is not None and Ferramenta._dist(a, b) <= 1e-6

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt(((a.x() - b.x()) ** 2) + ((a.y() - b.y()) ** 2))

    @staticmethod
    def _dist_tuple(a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt(((float(a[0]) - float(b[0])) ** 2) + ((float(a[1]) - float(b[1])) ** 2))

    @staticmethod
    def _cor_realce_canvas(canvas) -> str:
        try:
            cor = str(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
            return cor if QColor(cor).isValid() else "#2da8ff"
        except Exception:
            return "#2da8ff"

    def _status(self, canvas, texto: str):
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
