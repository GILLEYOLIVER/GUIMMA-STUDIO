from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QPointF, Qt

from tools.movimento_utils import mover_elemento_por_delta
from tools.preview_original_utils import desenhar_elementos_originais
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "mover"
    nome = "Mover"
    gerencia_coordenadas_operacao = True
    descricao_painel = "Arraste os elementos selecionados. Se nada estiver selecionado, clique em um elemento."

    def __init__(self):
        super().__init__()
        self._arrastando = False
        self._ultimo_ponto: QPointF | None = None
        self._movido = False
        self._originais_arraste: dict[int, dict] = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._arrastando = False
        self._ultimo_ponto = None
        self._movido = False
        self._originais_arraste = {}
        self.set_status("Clique e arraste para mover a seleção.")

    def on_deactivate(self, canvas):
        self._arrastando = False
        self._ultimo_ponto = None
        self._movido = False
        self._originais_arraste = {}

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
        self._originais_arraste = self._capturar_originais(canvas, self._indices_para_mover(canvas))
        if hasattr(canvas, "iniciar_operacao_coordenadas"):
            canvas.iniciar_operacao_coordenadas(pos)
        self.set_status(f"Movendo {len(canvas._selecionados)} elemento(s)...")
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if not self._arrastando or self._ultimo_ponto is None:
            return False
        atual = self._ponto_movimento(canvas, event)
        dx = atual.x() - self._ultimo_ponto.x()
        dy = atual.y() - self._ultimo_ponto.y()
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return True
        for idx in self._indices_para_mover(canvas):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            mover_elemento_por_delta(el, dx, dy)
        self._ultimo_ponto = atual
        if hasattr(canvas, "atualizar_operacao_coordenadas"):
            canvas.atualizar_operacao_coordenadas(atual)
        self._movido = True
        snap_info = f" | {canvas.descricao_snap_atual()}" if hasattr(canvas, "descricao_snap_atual") and canvas.descricao_snap_atual() else ""
        self.set_status(f"Movendo {len(canvas._selecionados)} elemento(s)...{snap_info}")
        canvas.update()
        event.accept()
        return True

    def _indices_para_mover(self, canvas) -> list[int]:
        indices = set(int(idx) for idx in getattr(canvas, "_selecionados", set()))
        if hasattr(canvas, "_indices_transformacao_com_vinculados"):
            return list(canvas._indices_transformacao_com_vinculados(indices))
        return sorted(indices)

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton or not self._arrastando:
            return False
        destino = self._ponto_movimento(canvas, event)
        self._arrastando = False
        self._ultimo_ponto = None
        self._originais_arraste = {}
        if hasattr(canvas, "finalizar_operacao_coordenadas"):
            canvas.finalizar_operacao_coordenadas(destino)
        if self._movido:
            canvas._registrar_historico()
            self.set_status(f"Movimento concluído ({len(canvas._selecionados)} elemento(s)).")
        else:
            self.set_status("Sem deslocamento.")
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._arrastando:
            desenhar_elementos_originais(canvas, painter, self._originais_arraste)

    def _ponto_movimento(self, canvas, event) -> QPointF:
        ignorar = self._indices_para_mover(canvas)
        if hasattr(canvas, "_ponto_com_snap_movimento"):
            return canvas._ponto_com_snap_movimento(
                event.position(),
                ignorar_elementos=ignorar,
                elementos_sombra=self._originais_arraste,
            )
        return canvas._ponto_com_snap(event.position())

    def _capturar_originais(self, canvas, indices: list[int]) -> dict[int, dict]:
        originais: dict[int, dict] = {}
        for idx in indices:
            if 0 <= idx < len(canvas.cena.elementos) and isinstance(canvas.cena.elementos[idx], dict):
                originais[idx] = deepcopy(canvas.cena.elementos[idx])
        return originais
