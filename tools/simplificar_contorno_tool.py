from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "simplificar_contorno"
    nome = "Simplificar Contorno"
    descricao_painel = "Remove pontos redundantes do contorno mantendo os controles."

    TOLERANCIA_PADRAO = 0.08
    EPS = 1e-6

    def on_activate(self, canvas):
        super().on_activate(canvas)
        selecionados = sorted(getattr(canvas, "_selecionados", set()) or [])
        if selecionados:
            self._aplicar_em_indices(canvas, selecionados)
            return
        self.set_status("Selecione um contorno ou clique em um contorno para simplificar.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if hasattr(canvas, "set_tool"):
                canvas.set_tool("selecionar")
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        indices = self._indices_no_ponto(canvas, pos)
        if not indices:
            self.set_status("Nenhum contorno encontrado sob o cursor.")
            event.accept()
            return True

        idx = indices[0]
        canvas._selecionados = {idx}
        self._aplicar_em_indices(canvas, [idx])
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        if event.key() == Qt.Key_Escape:
            if hasattr(canvas, "set_tool"):
                canvas.set_tool("selecionar")
            event.accept()
            return True
        return False

    def _aplicar_em_indices(self, canvas, indices: list[int]) -> bool:
        elementos = getattr(getattr(canvas, "cena", None), "elementos", [])
        alterados = 0
        removidos = 0
        for idx in indices:
            if not (0 <= int(idx) < len(elementos)):
                continue
            el = elementos[int(idx)]
            antes = len(el.get("pontos", []) or []) if isinstance(el, dict) else 0
            if self._simplificar_elemento(el, self.TOLERANCIA_PADRAO):
                depois = len(el.get("pontos", []) or [])
                removidos += max(0, antes - depois)
                alterados += 1

        if not alterados:
            self.set_status("Contorno ja esta simplificado.")
            return False

        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        if hasattr(canvas, "update"):
            canvas.update()

        sufixo = "ponto removido" if removidos == 1 else "pontos removidos"
        self.set_status(f"Simplificacao aplicada: {alterados} contorno(s), {removidos} {sufixo}.")
        return True

    def _simplificar_elemento(self, el: dict, tolerancia: float | None = None) -> bool:
        if not isinstance(el, dict) or el.get("tipo") != "polyline":
            return False

        pontos = [p for p in (self._ponto_tuple(item) for item in el.get("pontos", []) or []) if p is not None]
        if len(pontos) < 3:
            return False

        tolerancia = self.TOLERANCIA_PADRAO if tolerancia is None else max(0.0, float(tolerancia))
        fechado = self._dist_tuple(pontos[0], pontos[-1]) <= self.EPS
        base = pontos[:-1] if fechado else pontos
        if len(base) < (3 if fechado else 2):
            return False

        obrigatorios = self._indices_obrigatorios(base, el)
        indices = self._indices_simplificados(base, fechado, obrigatorios, tolerancia)
        if fechado and len(indices) < 3:
            return False
        if not fechado and len(indices) < 2:
            return False

        novos = [base[i] for i in indices]
        if fechado:
            novos.append(novos[0])

        if self._pontos_iguais(pontos, novos):
            self._sincronizar_metadados_controle(el)
            return False

        el["pontos"] = novos
        self._sincronizar_metadados_controle(el)
        return True

    def _indices_simplificados(
        self,
        pontos: list[tuple[float, float]],
        fechado: bool,
        obrigatorios: set[int],
        tolerancia: float,
    ) -> list[int]:
        total = len(pontos)
        if total <= 2:
            return list(range(total))

        keep: set[int] = set()
        if fechado:
            ancoras = sorted(i for i in obrigatorios if 0 <= i < total)
            if len(ancoras) < 2:
                segundo = self._indice_mais_distante(pontos, ancoras[0] if ancoras else 0)
                ancoras = sorted({ancoras[0] if ancoras else 0, segundo})
            for pos, inicio in enumerate(ancoras):
                fim = ancoras[(pos + 1) % len(ancoras)]
                trecho = self._trecho_circular(inicio, fim, total)
                self._rdp_trecho(pontos, trecho, tolerancia, keep)
        else:
            ancoras = sorted({0, total - 1, *[i for i in obrigatorios if 0 <= i < total]})
            for inicio, fim in zip(ancoras, ancoras[1:]):
                trecho = list(range(inicio, fim + 1))
                self._rdp_trecho(pontos, trecho, tolerancia, keep)

        keep.update(i for i in obrigatorios if 0 <= i < total)
        return sorted(keep)

    def _rdp_trecho(
        self,
        pontos: list[tuple[float, float]],
        indices: list[int],
        tolerancia: float,
        keep: set[int],
    ) -> None:
        if not indices:
            return
        keep.add(indices[0])
        keep.add(indices[-1])
        if len(indices) <= 2:
            return

        a = pontos[indices[0]]
        b = pontos[indices[-1]]
        maior_dist = -1.0
        maior_local = -1
        for local, idx in enumerate(indices[1:-1], start=1):
            dist = self._distancia_ponto_segmento(pontos[idx], a, b)
            if dist > maior_dist:
                maior_dist = dist
                maior_local = local

        if maior_dist <= tolerancia or maior_local <= 0:
            return

        self._rdp_trecho(pontos, indices[: maior_local + 1], tolerancia, keep)
        self._rdp_trecho(pontos, indices[maior_local:], tolerancia, keep)

    def _indices_obrigatorios(self, pontos: list[tuple[float, float]], el: dict) -> set[int]:
        obrigatorios: set[int] = set()
        controles = []
        principais = el.get("controle_cantos")
        if isinstance(principais, list) and principais:
            controles.extend(principais)
        else:
            controles.extend(el.get("pontos_controle_principais", []) or [])

        auxiliares = el.get("controle_auxiliares")
        if isinstance(auxiliares, list) and auxiliares:
            controles.extend(auxiliares)
        else:
            controles.extend(el.get("pontos_auxiliares", []) or [])

        tolerancia = max(self.EPS, self._diagonal(pontos) * 1e-7)
        for item in controles:
            ponto = self._ponto_tuple(item)
            if ponto is None:
                continue
            idx, dist = self._indice_mais_proximo(pontos, ponto)
            if idx is not None and dist <= tolerancia:
                obrigatorios.add(idx)
        return obrigatorios

    def _sincronizar_metadados_controle(self, el: dict) -> None:
        cantos = [self._ponto_tuple(item) for item in el.get("controle_cantos", []) or []]
        cantos = [p for p in cantos if p is not None]
        if cantos:
            el["controle_cantos"] = cantos
            el["pontos_controle_principais"] = [{"x": x, "y": y} for x, y in cantos]

        auxiliares = [self._ponto_tuple(item) for item in el.get("controle_auxiliares", []) or []]
        auxiliares = [p for p in auxiliares if p is not None]
        if auxiliares or isinstance(el.get("controle_auxiliares"), list):
            el["controle_auxiliares"] = auxiliares
            el["pontos_auxiliares"] = [{"x": x, "y": y} for x, y in auxiliares]

    def _indices_no_ponto(self, canvas, pos: QPointF) -> list[int]:
        if hasattr(canvas, "_indices_elementos_em_ponto"):
            try:
                return [idx for idx in canvas._indices_elementos_em_ponto(pos) if self._elemento_simplificavel(canvas, idx)]
            except Exception:
                pass

        tolerancia = 8.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        encontrados = []
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if not self._elemento_simplificavel(canvas, idx):
                continue
            pontos = [p for p in (self._ponto_qt(item) for item in el.get("pontos", []) or []) if p is not None]
            if any(self._distancia_ponto_segmento_qt(pos, a, b) <= tolerancia for a, b in zip(pontos, pontos[1:])):
                encontrados.append(idx)
        return list(reversed(encontrados))

    def _elemento_simplificavel(self, canvas, idx: int) -> bool:
        elementos = getattr(getattr(canvas, "cena", None), "elementos", [])
        return 0 <= int(idx) < len(elementos) and isinstance(elementos[int(idx)], dict) and elementos[int(idx)].get("tipo") == "polyline"

    def _trecho_circular(self, inicio: int, fim: int, total: int) -> list[int]:
        if inicio <= fim:
            return list(range(inicio, fim + 1))
        return list(range(inicio, total)) + list(range(0, fim + 1))

    def _indice_mais_distante(self, pontos: list[tuple[float, float]], origem_idx: int) -> int:
        origem = pontos[max(0, min(origem_idx, len(pontos) - 1))]
        melhor_idx = 0
        melhor_dist = -1.0
        for idx, ponto in enumerate(pontos):
            dist = self._dist_tuple(origem, ponto)
            if dist > melhor_dist:
                melhor_dist = dist
                melhor_idx = idx
        return melhor_idx

    def _indice_mais_proximo(
        self,
        pontos: list[tuple[float, float]],
        alvo: tuple[float, float],
    ) -> tuple[int | None, float]:
        melhor_idx = None
        melhor_dist = float("inf")
        for idx, ponto in enumerate(pontos):
            dist = self._dist_tuple(ponto, alvo)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_idx = idx
        return melhor_idx, melhor_dist

    @staticmethod
    def _ponto_tuple(item) -> tuple[float, float] | None:
        try:
            if isinstance(item, QPointF):
                return float(item.x()), float(item.y())
            if isinstance(item, dict):
                return float(item["x"]), float(item["y"])
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                return float(item[0]), float(item[1])
        except Exception:
            return None
        return None

    @staticmethod
    def _ponto_qt(item) -> QPointF | None:
        ponto = Ferramenta._ponto_tuple(item)
        if ponto is None:
            return None
        return QPointF(float(ponto[0]), float(ponto[1]))

    @staticmethod
    def _dist_tuple(a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt(((a[0] - b[0]) ** 2) + ((a[1] - b[1]) ** 2))

    @staticmethod
    def _distancia_ponto_segmento(
        ponto: tuple[float, float],
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> float:
        px, py = ponto
        ax, ay = a
        bx, by = b
        abx = bx - ax
        aby = by - ay
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-12:
            return sqrt(((px - ax) ** 2) + ((py - ay) ** 2))
        t = max(0.0, min(1.0, (((px - ax) * abx) + ((py - ay) * aby)) / denom))
        qx = ax + (abx * t)
        qy = ay + (aby * t)
        return sqrt(((px - qx) ** 2) + ((py - qy) ** 2))

    @classmethod
    def _distancia_ponto_segmento_qt(cls, ponto: QPointF, a: QPointF, b: QPointF) -> float:
        return cls._distancia_ponto_segmento(
            (float(ponto.x()), float(ponto.y())),
            (float(a.x()), float(a.y())),
            (float(b.x()), float(b.y())),
        )

    @staticmethod
    def _diagonal(pontos: list[tuple[float, float]]) -> float:
        if not pontos:
            return 0.0
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return sqrt(((max(xs) - min(xs)) ** 2) + ((max(ys) - min(ys)) ** 2))

    def _pontos_iguais(self, a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
        if len(a) != len(b):
            return False
        return all(self._dist_tuple(pa, pb) <= self.EPS for pa, pb in zip(a, b))
