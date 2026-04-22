from __future__ import annotations

from tools.painel_ferramenta import PainelFerramentaBasico

class FerramentaBase:
    id_ferramenta = "base"
    nome = "Ferramenta Base"
    usa_painel_auxiliar = True
    descricao_painel = "Ajuste e execute esta ferramenta no canvas."

    def ativar(self) -> str:
        return f"{self.nome} ativada"

    def __init__(self):
        self._painel_auxiliar: PainelFerramentaBasico | None = None

    # Hooks de execução em runtime (canvas delega para a ferramenta ativa).
    def on_activate(self, canvas) -> None:  # pragma: no cover - hook opcional
        self._mostrar_painel_auxiliar(canvas)
        return None

    def on_deactivate(self, canvas) -> None:  # pragma: no cover - hook opcional
        self._ocultar_painel_auxiliar()
        return None

    def on_mouse_press(self, canvas, event) -> bool:  # pragma: no cover - hook opcional
        return False

    def on_mouse_move(self, canvas, event) -> bool:  # pragma: no cover - hook opcional
        return False

    def on_mouse_release(self, canvas, event) -> bool:  # pragma: no cover - hook opcional
        return False

    def on_key_press(self, canvas, event) -> bool:  # pragma: no cover - hook opcional
        return False

    def on_key_release(self, canvas, event) -> bool:  # pragma: no cover - hook opcional
        return False

    def on_paint_overlay(self, canvas, painter) -> None:  # pragma: no cover - hook opcional
        return None

    def on_canvas_resize(self, canvas) -> None:  # pragma: no cover - hook opcional
        painel = getattr(self, "_painel_auxiliar", None)
        if painel and painel.isVisible():
            painel.reposicionar_no_canto_superior_direito()

    def set_status(self, texto: str):
        painel = getattr(self, "_painel_auxiliar", None)
        if painel:
            painel.atualizar_status(texto)

    def _mostrar_painel_auxiliar(self, canvas):
        if not self.usa_painel_auxiliar:
            return
        parent = canvas if canvas is not None else None
        if parent is not None:
            for painel_existente in parent.findChildren(PainelFerramentaBasico):
                if painel_existente is not getattr(self, "_painel_auxiliar", None):
                    painel_existente.hide()
        painel = getattr(self, "_painel_auxiliar", None)
        if painel is None:
            self._painel_auxiliar = PainelFerramentaBasico(self.nome, self.descricao_painel, parent=parent)
            painel = self._painel_auxiliar
        elif parent is not None and painel.parentWidget() is not parent:
            painel.setParent(parent)
        painel.show()
        painel.raise_()
        painel.reposicionar_no_canto_superior_direito()

    def _ocultar_painel_auxiliar(self):
        painel = getattr(self, "_painel_auxiliar", None)
        if painel:
            painel.hide()
