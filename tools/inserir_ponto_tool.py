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
