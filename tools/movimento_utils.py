from __future__ import annotations


CHAVES_LISTAS_PONTOS = (
    "pontos",
    "controle_cantos",
    "controle_auxiliares",
    "marcacoes_no_perimetro",
    "distancias_no_perimetro",
    "marcacoes_perimetro",
    "pontos_graduacao",
    "pontos_principais",
    "pontos_controle_curva",
    "pontos_controle_principais",
    "pontos_controle_referencia",
    "pontos_controle",
    "controle_pontos",
    "pontos_controle_pique",
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

CHAVES_ROTACAO_LISTAS_TUPLAS = {
    "controle_cantos",
    "controle_auxiliares",
    "pontos_controle_referencia",
}

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


def rotacionar_elemento_por_funcao(elemento: dict, rotacionar_ponto) -> None:
    """Rotaciona pontos do elemento e vetores DX/DY de graduação."""
    if not isinstance(elemento, dict) or not callable(rotacionar_ponto):
        return
    for chave in CHAVES_LISTAS_PONTOS:
        if chave in elemento:
            elemento[chave] = _rotacionar_lista_ou_mapa_pontos(
                elemento.get(chave),
                rotacionar_ponto,
                normalizar_dict=chave in CHAVES_ROTACAO_LISTAS_TUPLAS,
            )
    for chave in CHAVES_PONTOS_SOLTOS:
        if chave in elemento:
            elemento[chave] = rotacionar_ponto_por_funcao(elemento.get(chave), rotacionar_ponto)
    for chave in CHAVES_ESTRUTURAS_COM_PONTOS:
        if chave in elemento:
            elemento[chave] = rotacionar_valor_estruturado_por_funcao(elemento.get(chave), rotacionar_ponto)
    rotacionar_vetores_graduacao_por_funcao(elemento, rotacionar_ponto)


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


def _rotacionar_lista_ou_mapa_pontos(valor, rotacionar_ponto, *, normalizar_dict: bool = False):
    if isinstance(valor, dict):
        return {
            chave: rotacionar_ponto_por_funcao(ponto, rotacionar_ponto, normalizar_dict=normalizar_dict)
            for chave, ponto in valor.items()
        }
    if isinstance(valor, list):
        return [rotacionar_ponto_por_funcao(ponto, rotacionar_ponto, normalizar_dict=normalizar_dict) for ponto in valor]
    if isinstance(valor, tuple):
        return tuple(rotacionar_ponto_por_funcao(ponto, rotacionar_ponto, normalizar_dict=normalizar_dict) for ponto in valor)
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


def rotacionar_ponto_por_funcao(ponto, rotacionar_ponto, *, normalizar_dict: bool = False):
    if isinstance(ponto, dict):
        if "x" not in ponto or "y" not in ponto:
            return ponto
        x, y = rotacionar_ponto((ponto.get("x", 0.0), ponto.get("y", 0.0)))
        if normalizar_dict:
            return (float(x), float(y))
        rotacionado = dict(ponto)
        rotacionado["x"] = float(x)
        rotacionado["y"] = float(y)
        return rotacionado
    if isinstance(ponto, (list, tuple)) and len(ponto) >= 2:
        x, y = rotacionar_ponto((ponto[0], ponto[1]))
        if isinstance(ponto, list):
            return [float(x), float(y), *ponto[2:]]
        return (float(x), float(y), *ponto[2:])
    if hasattr(ponto, "x") and hasattr(ponto, "y"):
        return rotacionar_ponto((ponto.x(), ponto.y()))
    return ponto


def mover_valor_estruturado_por_delta(valor, dx: float, dy: float):
    """Move pontos dentro de estruturas aninhadas sem alterar deltas de graduação.

    Campos como ``piques_config`` e ``graduacao_tabela`` guardam pontos dentro de
    listas e dicionários, mas também guardam medidas como dx/dy, altura e largura.
    Esta função percorre a estrutura e só desloca pares que representam
    coordenadas ou dicionários com ``x``/``y``.
    """
    return _mover_estrutura(valor, dx, dy, recursao_livre=True)


def rotacionar_valor_estruturado_por_funcao(valor, rotacionar_ponto):
    return _rotacionar_estrutura(valor, rotacionar_ponto, recursao_livre=True)


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


def _rotacionar_estrutura(valor, rotacionar_ponto, *, recursao_livre: bool):
    if isinstance(valor, dict):
        if "x" in valor and "y" in valor:
            return rotacionar_ponto_por_funcao(valor, rotacionar_ponto)
        rotacionado = dict(valor)
        for chave, item in list(rotacionado.items()):
            chave_txt = str(chave or "").lower()
            if chave_txt in CHAVES_SEM_COORDENADAS:
                continue
            if _chave_com_pontos(chave_txt) or (recursao_livre and isinstance(item, (dict, list, tuple))):
                rotacionado[chave] = _rotacionar_estrutura(
                    item,
                    rotacionar_ponto,
                    recursao_livre=_chave_com_pontos(chave_txt) or recursao_livre,
                )
        return rotacionado

    if isinstance(valor, list):
        if _eh_par_numerico(valor):
            return rotacionar_ponto_por_funcao(valor, rotacionar_ponto)
        return [_rotacionar_estrutura(item, rotacionar_ponto, recursao_livre=recursao_livre) for item in valor]

    if isinstance(valor, tuple):
        if _eh_par_numerico(valor):
            return rotacionar_ponto_por_funcao(valor, rotacionar_ponto)
        return tuple(_rotacionar_estrutura(item, rotacionar_ponto, recursao_livre=recursao_livre) for item in valor)

    return valor


def rotacionar_vetores_graduacao_por_funcao(elemento: dict, rotacionar_ponto) -> None:
    for pontos_cfg in _fontes_pontos_graduacao(elemento):
        for cfg in pontos_cfg.values():
            if not isinstance(cfg, dict):
                continue
            valores = cfg.get("valores")
            if not isinstance(valores, dict):
                continue
            for valor_tamanho in valores.values():
                if not isinstance(valor_tamanho, dict) or "dx" not in valor_tamanho or "dy" not in valor_tamanho:
                    continue
                dx, dy = _rotacionar_vetor(valor_tamanho.get("dx", 0.0), valor_tamanho.get("dy", 0.0), rotacionar_ponto)
                valor_tamanho["dx"] = dx
                valor_tamanho["dy"] = dy


def _fontes_pontos_graduacao(elemento: dict) -> list[dict]:
    fontes: list[dict] = []
    tabela = elemento.get("graduacao_tabela") if isinstance(elemento.get("graduacao_tabela"), dict) else None
    pontos_tabela = tabela.get("pontos") if isinstance(tabela, dict) else None
    if isinstance(pontos_tabela, dict):
        fontes.append(pontos_tabela)
    legado = elemento.get("graduacao_pontos")
    if isinstance(legado, dict):
        fontes.append(legado)
    return fontes


def _rotacionar_vetor(dx, dy, rotacionar_ponto) -> tuple[float, float]:
    ox, oy = rotacionar_ponto((0.0, 0.0))
    px, py = rotacionar_ponto((float(dx or 0.0), float(dy or 0.0)))
    return float(px) - float(ox), float(py) - float(oy)


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
