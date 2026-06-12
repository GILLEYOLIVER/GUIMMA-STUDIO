from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import QPointF, Qt

from core.graduacao import aplicar_grade_graduacao_referencia_canvas
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "criar_molde"
    nome = "Criar Molde"
    descricao_painel = "Converte contornos selecionados em molde com metadados de modelagem."

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self.set_status("Selecione um contorno e clique para converter em molde.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        candidatos = canvas._indices_elementos_em_ponto(pos)
        if candidatos:
            canvas._selecionados = {candidatos[0]}
        if not canvas._selecionados:
            self.set_status("Nenhum contorno selecionado.")
            return False
        alterou = False
        for idx in sorted(canvas._selecionados):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pontos = [(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 3:
                continue
            if pontos[0] != pontos[-1]:
                pontos.append(pontos[0])
            el["pontos"] = pontos
            espessura_atual = max(1.0, float(getattr(canvas, "_linha_espessura", 1.0) or 1.0))
            el["espessura"] = max(1.0, float(el.get("espessura", espessura_atual) or espessura_atual))
            el["espessura_graduacao"] = max(
                1.0,
                float(el.get("espessura_graduacao", el.get("espessura", espessura_atual)) or espessura_atual),
            )
            el.setdefault("estilo", getattr(canvas, "_linha_estilo", "solid"))
            el.setdefault("amplitude", getattr(canvas, "_linha_amplitude", 1.0))
            el["molde"] = True
            el["molde_id"] = str(el.get("molde_id") or uuid4())
            el["fio_angulo"] = float(el.get("fio_angulo", 0.0))
            el["controle_cantos"] = self._estimar_cantos(pontos)
            el["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in el["controle_cantos"]]
            el["pontos_graduacao"] = [{"x": float(x), "y": float(y)} for x, y in pontos[:-1]]
            aplicar_grade_graduacao_referencia_canvas(el, canvas, sobrescrever=True)
            alterou = True
        if alterou:
            canvas._selecionados.clear()
            canvas._registrar_historico()
            canvas.update()
            self.set_status("Molde criado/atualizado com sucesso.")
            event.accept()
            return True
        self.set_status("Seleção inválida para criar molde.")
        return False

    def _estimar_cantos(self, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        xs = [x for x, _ in pontos]
        ys = [y for _, y in pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        candidatos = [
            QPointF(min_x, min_y),
            QPointF(max_x, min_y),
            QPointF(max_x, max_y),
            QPointF(min_x, max_y),
        ]
        return [(p.x(), p.y()) for p in candidatos]
