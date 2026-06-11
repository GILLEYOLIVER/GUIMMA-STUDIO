from __future__ import annotations


def formatar_numero(valor: float, casas: int = 2) -> str:
    casas_final = max(0, min(12, int(casas)))
    texto = f"{float(valor):.{casas_final}f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return "0" if texto in {"", "-0"} else texto
