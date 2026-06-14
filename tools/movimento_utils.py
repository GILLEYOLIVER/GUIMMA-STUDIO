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

CHAVES_ESTRUTURAS_COM_PONTOS = (
    "piques_config",
    "graduacao_tabela",
    "graduacao_pontos",
)

CHAVES_SEM_COORDENADAS = {
    "valores",
    "valor",
    "dx",
    "dy",
    "largura",
    "altura",
    "largura_cm",
    "altura_cm",
    "texto_dx_cm",
    "texto_dy_cm",
}


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
    for chave in CHAVES_ESTRUTURAS_COM_PONTOS:
        if chave in elemento:
            elemento[chave] = mover_valor_estruturado_por_delta(elemento.get(chave), dx, dy)


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


def mover_valor_estruturado_por_delta(valor, dx: float, dy: float):
    """Move pontos dentro de estruturas aninhadas sem alterar deltas de graduação.

    Campos como ``piques_config`` e ``graduacao_tabela`` guardam pontos dentro de
    listas e dicionários, mas também guardam medidas como dx/dy, altura e largura.
    Esta função percorre a estrutura e só desloca pares que representam
    coordenadas ou dicionários com ``x``/``y``.
    """
    return _mover_estrutura(valor, dx, dy, recursao_livre=True)


def _mover_estrutura(valor, dx: float, dy: float, *, recursao_livre: bool):
    if isinstance(valor, dict):
        if "x" in valor and "y" in valor:
            return mover_ponto_por_delta(valor, dx, dy)
        movido = dict(valor)
        for chave, item in list(movido.items()):
            chave_txt = str(chave or "").lower()
            if chave_txt in CHAVES_SEM_COORDENADAS:
                continue
            if _chave_com_pontos(chave_txt) or (recursao_livre and isinstance(item, (dict, list, tuple))):
                movido[chave] = _mover_estrutura(item, dx, dy, recursao_livre=_chave_com_pontos(chave_txt) or recursao_livre)
        return movido

    if isinstance(valor, list):
        if _eh_par_numerico(valor):
            return mover_ponto_por_delta(valor, dx, dy)
        return [_mover_estrutura(item, dx, dy, recursao_livre=recursao_livre) for item in valor]

    if isinstance(valor, tuple):
        if _eh_par_numerico(valor):
            return mover_ponto_por_delta(valor, dx, dy)
        return tuple(_mover_estrutura(item, dx, dy, recursao_livre=recursao_livre) for item in valor)

    return valor


def _chave_com_pontos(chave: str) -> bool:
    return any(
        termo in chave
        for termo in (
            "ponto",
            "pontos",
            "contorno",
            "controle",
            "marcacao",
            "marcação",
            "segmento",
            "segmentos",
            "pique",
            "piques",
            "origem",
            "fim",
            "posicao",
            "posição",
            "seta",
            "fio",
            "eixo",
        )
    )


def _eh_par_numerico(valor) -> bool:
    if not isinstance(valor, (list, tuple)) or len(valor) < 2:
        return False
    try:
        float(valor[0])
        float(valor[1])
        return True
    except Exception:
        return False
