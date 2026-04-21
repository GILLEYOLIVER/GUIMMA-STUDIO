from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "mover"
    nome = "Mover"
    descricao_painel = "Arraste os elementos selecionados. Se nada estiver selecionado, clique em um elemento."

    def __init__(self):
        super().__init__()
        self._arrastando = False
        self._ultimo_ponto: QPointF | None = None
        self._movido = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._arrastando = False
        self._ultimo_ponto = None
        self._movido = False
        self.set_status("Clique e arraste para mover a seleção.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        if not canvas._selecionados:
            candidatos = canvas._indices_elementos_em_ponto(pos)
            if candidatos:
                canvas._selecionados = {candidatos[0]}
            else:
                self.set_status("Nenhum elemento sob o cursor para mover.")
                return False
        self._arrastando = True
        self._ultimo_ponto = pos
        self._movido = False
        self.set_status(f"Movendo {len(canvas._selecionados)} elemento(s)...")
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if not self._arrastando or self._ultimo_ponto is None:
            return False
        atual = canvas._ponto_com_snap(event.position())
        dx = atual.x() - self._ultimo_ponto.x()
        dy = atual.y() - self._ultimo_ponto.y()
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return True
        for idx in list(canvas._selecionados):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                el["pontos"] = [(x + dx, y + dy) for x, y in el.get("pontos", [])]
                if "controle_cantos" in el:
                    el["controle_cantos"] = [(x + dx, y + dy) for x, y in el.get("controle_cantos", [])]
                if "controle_auxiliares" in el:
                    el["controle_auxiliares"] = [(x + dx, y + dy) for x, y in el.get("controle_auxiliares", [])]
                if "fio_origem" in el:
                    fx, fy = el.get("fio_origem", (0.0, 0.0))
                    el["fio_origem"] = (float(fx) + dx, float(fy) + dy)
                if "fio_fim" in el:
                    fx, fy = el.get("fio_fim", (0.0, 0.0))
                    el["fio_fim"] = (float(fx) + dx, float(fy) + dy)
            elif el.get("tipo") == "bezier_quadratica":
                for chave in ("p0", "p1", "p2"):
                    x, y = el[chave]
                    el[chave] = (x + dx, y + dy)
        self._ultimo_ponto = atual
        self._movido = True
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton or not self._arrastando:
            return False
        self._arrastando = False
        self._ultimo_ponto = None
        if self._movido:
            canvas._registrar_historico()
            self.set_status(f"Movimento concluído ({len(canvas._selecionados)} elemento(s)).")
        else:
            self.set_status("Sem deslocamento.")
        canvas.update()
        event.accept()
        return True
