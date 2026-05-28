from __future__ import annotations

try:
    import canvas.visualizacao_texto_nativo_patch as _texto_patch

    def _sem_borda_texto(canvas, painter, elemento) -> None:
        return None

    _texto_patch.desenhar_selecao_texto = _sem_borda_texto
except Exception:
    pass
