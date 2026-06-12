from __future__ import annotations


def formatar_numero(valor: float, casas: int = 2) -> str:
    casas_final = max(0, min(12, int(casas)))
    texto = f"{float(valor):.{casas_final}f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return "0" if texto in {"", "-0"} else texto


def normalizar_decimal_ponto(texto, remover: tuple[str, ...] = ()) -> str:
    """Normaliza texto numérico digitado pelo usuário usando ponto decimal.

    A regra da interface é aceitar ".5" como "0.5", mas não aceitar vírgula
    como separador decimal.
    """

    valor = str("" if texto is None else texto).strip()
    for token in remover:
        if token:
            valor = valor.replace(token, "")
            valor = valor.replace(token.upper(), "")
    valor = valor.strip().replace(" ", "")
    if "," in valor:
        raise ValueError("Use ponto como separador decimal.")
    if valor.startswith("."):
        valor = "0" + valor
    elif valor.startswith("-."):
        valor = "-0" + valor[1:]
    elif valor.startswith("+."):
        valor = "+0" + valor[1:]
    return valor


def numero_decimal_ponto(texto, padrao: float = 0.0, remover: tuple[str, ...] = ()) -> float:
    try:
        normalizado = normalizar_decimal_ponto(texto, remover)
        if normalizado in {"", "+", "-"}:
            raise ValueError
        return float(normalizado)
    except Exception:
        return float(padrao)


def texto_decimal_ponto_aceitavel(texto, remover: tuple[str, ...] = ()) -> bool:
    try:
        normalizado = normalizar_decimal_ponto(texto, remover)
    except Exception:
        return False
    if normalizado in {"", "+", "-", "0.", "+0.", "-0."}:
        return True
    try:
        float(normalizado)
        return True
    except Exception:
        return False
