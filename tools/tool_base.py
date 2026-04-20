from __future__ import annotations


class FerramentaBase:
    id_ferramenta = "base"
    nome = "Ferramenta Base"

    def ativar(self) -> str:
        return f"{self.nome} ativada"

    # Hooks de execução em runtime (canvas delega para a ferramenta ativa).
    def on_activate(self, canvas) -> None:  # pragma: no cover - hook opcional
        return None

    def on_mouse_press(self, canvas, event) -> bool:  # pragma: no cover - hook opcional
        return False

    def on_mouse_move(self, canvas, event) -> bool:  # pragma: no cover - hook opcional
        return False

    def on_mouse_release(self, canvas, event) -> bool:  # pragma: no cover - hook opcional
        return False

    def on_paint_overlay(self, canvas, painter) -> None:  # pragma: no cover - hook opcional
        return None
