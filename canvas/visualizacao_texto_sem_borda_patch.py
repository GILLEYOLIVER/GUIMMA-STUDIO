from __future__ import annotations

# Compatibilidade com versões antigas.
# Antes este arquivo substituía canvas.visualizacao_texto_nativo_patch.desenhar_selecao_texto
# por uma função vazia, removendo a seleção visual do texto.
# Agora a seleção do texto precisa aparecer como caixa azul translúcida com borda tracejada,
# então este patch não deve mais sobrescrever o desenho oficial.

try:
    import canvas.visualizacao_texto_nativo_patch  # noqa: F401
except Exception:
    pass
