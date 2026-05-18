from __future__ import annotations


CHAVES_LISTAS_PONTOS = (
    "pontos",
    "controle_cantos",
    "controle_auxiliares",
    "marcacoes_no_perimetro",
    "distancias_no_perimetro",
    "marcacoes_perimetro",
    "pontos_principais",
    "pontos_controle_curva",
    "pontos_controle_principais",
    "pontos_controle",
    "controle_pontos",
    "pontos_auxiliares",
)

CHAVES_PONTOS_SOLTOS = (
    "p0",
    "p1",
    "p2",
    "pos",
    "ponto_texto",
    "ponto_texto_nome",
    "ponto_texto_descricao",
    "ponto_texto_observacoes",
    "nome_posicao",
    "nome_centro",
    "fio_origem",
    "fio_fim",
    "seta_origem",
    "seta_fim",
)


def mover_elemento_por_delta(elemento: dict, dx: float, dy: float) -> None:
    """Move o desenho e todos os pontos visuais anexados ao elemento."""
    if not isinstance(elemento, dict):
        return
    for chave in CHAVES_LISTAS_PONTOS:
        if chave in elemento:
            elemento[chave] = _mover_lista_ou_mapa_pontos(elemento.get(chave), dx, dy)
    for chave in CHAVES_PONTOS_SOLTOS:
        if chave in elemento:
            elemento[chave] = mover_ponto_por_delta(elemento.get(chave), dx, dy)


def _mover_lista_ou_mapa_pontos(valor, dx: float, dy: float):
    if isinstance(valor, dict):
        movido = {}
        for chave, ponto in valor.items():
            movido[chave] = mover_ponto_por_delta(ponto, dx, dy)
        return movido
    if isinstance(valor, list):
        return [mover_ponto_por_delta(ponto, dx, dy) for ponto in valor]
    if isinstance(valor, tuple):
        return tuple(mover_ponto_por_delta(ponto, dx, dy) for ponto in valor)
    return valor


def mover_ponto_por_delta(ponto, dx: float, dy: float):
    if isinstance(ponto, dict):
        if "x" not in ponto or "y" not in ponto:
            return ponto
        movido = dict(ponto)
        movido["x"] = float(movido.get("x", 0.0)) + dx
        movido["y"] = float(movido.get("y", 0.0)) + dy
        return movido
    if isinstance(ponto, (list, tuple)) and len(ponto) >= 2:
        movido = (float(ponto[0]) + dx, float(ponto[1]) + dy)
        if isinstance(ponto, list):
            return [*movido, *ponto[2:]]
        return (*movido, *ponto[2:])
    return ponto
