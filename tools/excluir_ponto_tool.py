from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "excluir_ponto"
    nome = "Excluir Ponto"
    descricao_painel = "Remove pontos de contorno mantendo geometria mínima válida."

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self.set_status("Clique sobre um vértice para excluir.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        alvo = self._vertice_em_ponto(canvas, pos)
        if alvo is None:
            self.set_status("Nenhum vértice encontrado para exclusão.")
            return False
        idx, p_idx = alvo
        el = canvas.cena.elementos[idx]
        pontos = list(el.get("pontos", []))
        if len(pontos) <= 2:
            self.set_status("Elemento com poucos pontos: não é possível excluir.")
            return False

        fechado = (
            len(pontos) >= 3
            and abs(pontos[0][0] - pontos[-1][0]) < 1e-9
            and abs(pontos[0][1] - pontos[-1][1]) < 1e-9
        )
        if fechado and p_idx in {0, len(pontos) - 1}:
            pontos.pop(0)
            if pontos:
                pontos[-1] = pontos[0]
        else:
            pontos.pop(p_idx)
            if fechado and pontos:
                pontos[-1] = pontos[0]

        if len(pontos) < 2:
            self.set_status("Exclusão cancelada para evitar geometria inválida.")
            return False

        el["pontos"] = pontos
        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self.set_status("Ponto excluído com sucesso.")
        event.accept()
        return True

    def _vertice_em_ponto(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int] | None = None
        melhor_d = tolerancia
        for idx, el in enumerate(canvas.cena.elementos):
            if el.get("tipo") != "polyline":
                continue
            for p_idx, (x, y) in enumerate(el.get("pontos", [])):
                d = canvas._dist(QPointF(float(x), float(y)), pos)
                if d <= melhor_d:
                    melhor_d = d
                    melhor = (idx, p_idx)
        return melhor
