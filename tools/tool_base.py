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
            self._painel_auxiliar = PainelFerramentaBasico(
                self.nome,
                self.descricao_painel,
                parent=parent,
                chave_posicao=f"painel:{self.id_ferramenta}",
            )
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

    def _obter_janela_principal(self, canvas):
        if canvas is None:
            return None
        janela = canvas.window() if hasattr(canvas, "window") else None
        if janela is None:
            return None
        if not hasattr(janela, "projeto_atual"):
            return None
        return janela

    def carregar_preferencias_ferramenta(self, canvas, padrao: dict | None = None) -> dict:
        janela = self._obter_janela_principal(canvas)
        if janela is None:
            return dict(padrao or {})
        prefs_usuario = getattr(janela.projeto_atual, "preferencias_usuario", {})
        ferramentas_cfg = prefs_usuario.get("ferramentas_cfg", {})
        cfg = ferramentas_cfg.get(self.id_ferramenta, {})
        base = dict(padrao or {})
        if isinstance(cfg, dict):
            base.update(cfg)
        return base

    def salvar_preferencias_ferramenta(self, canvas, cfg: dict) -> None:
        janela = self._obter_janela_principal(canvas)
        if janela is None:
            return
        prefs_usuario = janela.projeto_atual.preferencias_usuario
        ferramentas_cfg = prefs_usuario.setdefault("ferramentas_cfg", {})
        ferramentas_cfg[self.id_ferramenta] = dict(cfg)
        if hasattr(janela, "_salvar_preferencias_app"):
            janela._salvar_preferencias_app()
