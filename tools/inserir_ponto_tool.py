from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "inserir_ponto"
    nome = "Inserir Ponto"
    descricao_painel = "Insere ponto em contorno (polyline) no segmento mais próximo."

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self.set_status("Clique em um segmento para inserir novo ponto.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        alvo = self._segmento_mais_proximo(canvas, pos)
        if alvo is None:
            self.set_status("Nenhum segmento encontrado sob o cursor.")
            return False
        idx, seg_idx = alvo
        el = canvas.cena.elementos[idx]
        pontos = list(el.get("pontos", []))
        inserir_em = seg_idx + 1
        pontos.insert(inserir_em, (pos.x(), pos.y()))
        el["pontos"] = pontos
        self._sincronizar_controles_apos_insercao(el, pos)
        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self.set_status("Ponto inserido com sucesso.")
        event.accept()
        return True

    def _segmento_mais_proximo(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        tolerancia = 10.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int] | None = None
        melhor_dist = tolerancia
        for idx, el in enumerate(canvas.cena.elementos):
            if el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 2:
                continue
            for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
                d = canvas._distancia_ponto_segmento(a, b, pos)
                if d < melhor_dist:
                    melhor_dist = d
                    melhor = (idx, seg_idx)
        return melhor

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
    def _dist_tuple(a: tuple[float, float] | None, b: tuple[float, float]) -> float:
        if a is None:
            return float("inf")
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
