from __future__ import annotations

from core.formatacao import formatar_numero, numero_decimal_ponto


FATORES_UNIDADE = {
    "mm": 0.1,
    "cm": 1.0,
    "m": 100.0,
    "pol": 2.54,
    "in": 2.54,
    "ft": 30.48,
    "yd": 91.44,
}

SUFIXOS_MEDIDA = tuple(FATORES_UNIDADE.keys())


def unidade_canvas(canvas) -> tuple[str, float]:
    sigla = str(getattr(canvas, "_unidade_sigla", "cm") or "cm")
    fator_padrao = FATORES_UNIDADE.get(sigla, 1.0)
    try:
        fator = float(getattr(canvas, "_unidade_fator", fator_padrao) or fator_padrao)
    except (TypeError, ValueError):
        fator = fator_padrao
    return sigla, max(1e-9, fator)


def valor_unidade_para_cena(canvas, valor: float) -> float:
    try:
        conversor = getattr(canvas, "converter_para_cena", None)
        if callable(conversor):
            return float(conversor(float(valor)))
    except Exception:
        pass
    return float(valor) * unidade_canvas(canvas)[1]


def valor_cena_para_unidade(canvas, valor: float) -> float:
    try:
        conversor = getattr(canvas, "converter_de_cena", None)
        if callable(conversor):
            return float(conversor(float(valor)))
    except Exception:
        pass
    return float(valor) / unidade_canvas(canvas)[1]


def numero_texto_unidade(texto, padrao: float = 0.0) -> float:
    return numero_decimal_ponto(texto, padrao, SUFIXOS_MEDIDA)


def formatar_valor_unidade(canvas, valor_cena: float, casas: int = 3) -> str:
    try:
        formatador = getattr(canvas, "formatar_valor_unidade", None)
        if callable(formatador):
            return str(formatador(float(valor_cena), casas=casas))
    except Exception:
        pass
    return formatar_numero(valor_cena_para_unidade(canvas, valor_cena), casas)


def formatar_rotulo_unidade(rotulo: str, canvas=None, sigla: str | None = None) -> str:
    unidade = str(sigla or unidade_canvas(canvas)[0] if canvas is not None else sigla or "cm")
    return f"{rotulo} ({unidade})"
