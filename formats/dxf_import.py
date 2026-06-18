from __future__ import annotations

from collections import defaultdict, deque
from math import hypot


TOLERANCIA_CONEXAO = 1e-5
TOLERANCIA_COLINEAR = 1e-5


def importar_dxf_para_elementos(caminho: str) -> list[dict]:
    with open(caminho, encoding="utf-8", errors="ignore") as f:
        bruto = [ln.rstrip("\n\r") for ln in f]
    pares = []
    i = 0
    while i + 1 < len(bruto):
        pares.append((bruto[i].strip(), bruto[i + 1].strip()))
        i += 2

    em_entities = False
    entidade: str | None = None
    atual: dict[str, object] = {}
    elementos: list[dict] = []
    segmentos_line: list[tuple[tuple[float, float], tuple[float, float]]] = []

    def flush():
        nonlocal atual, entidade
        if entidade == "LINE":
            x1 = _f(atual.get("10"))
            y1 = _f(atual.get("20"))
            x2 = _f(atual.get("11"))
            y2 = _f(atual.get("21"))
            if None not in (x1, y1, x2, y2):
                a = (float(x1), float(y1))
                b = (float(x2), float(y2))
                if _dist(a, b) > TOLERANCIA_CONEXAO:
                    segmentos_line.append((a, b))
        elif entidade == "LWPOLYLINE":
            xs = atual.get("10", [])
            ys = atual.get("20", [])
            if isinstance(xs, list) and isinstance(ys, list):
                pts = [(float(x), float(y)) for x, y in zip(xs, ys) if x is not None and y is not None]
                if len(pts) >= 2:
                    flag = int(_f(atual.get("70")) or 0)
                    fechado = bool(flag & 1)
                    if fechado and _dist(pts[0], pts[-1]) > TOLERANCIA_CONEXAO:
                        pts.append(pts[0])
                    pts = _simplificar_pontos_redundantes(pts)
                    if len(pts) >= 2:
                        elementos.append(_elemento_polyline(pts, fechado=fechado))
        atual = {}
        entidade = None

    for code, value in pares:
        if code == "0" and value == "SECTION":
            continue
        if code == "2" and value == "ENTITIES":
            em_entities = True
            continue
        if code == "0" and value == "ENDSEC":
            em_entities = False
            flush()
            continue
        if not em_entities:
            continue

        if code == "0":
            flush()
            if value in {"LINE", "LWPOLYLINE"}:
                entidade = value
            continue
        if entidade is None:
            continue

        if entidade == "LWPOLYLINE" and code in {"10", "20"}:
            atual.setdefault(code, []).append(_f(value))
        else:
            atual[code] = value
    flush()

    elementos.extend(_linhas_conectadas_para_polylines(segmentos_line))
    return elementos


def _elemento_polyline(pontos: list[tuple[float, float]], *, fechado: bool = False) -> dict:
    return {
        "tipo": "polyline",
        "pontos": pontos,
        "cor": "#ff5a00",
        "origem_importador": "dxf",
        "fechado": bool(fechado),
    }


def _linhas_conectadas_para_polylines(
    segmentos: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[dict]:
    if not segmentos:
        return []

    adj: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, (a, b) in enumerate(segmentos):
        adj[_chave_ponto(a)].append(idx)
        adj[_chave_ponto(b)].append(idx)

    usados: set[int] = set()
    elementos: list[dict] = []
    for idx, (a, b) in enumerate(segmentos):
        if idx in usados:
            continue
        usados.add(idx)
        cadeia: deque[tuple[float, float]] = deque([a, b])
        _estender_cadeia(cadeia, adj, segmentos, usados, frente=False)
        _estender_cadeia(cadeia, adj, segmentos, usados, frente=True)
        pontos = _simplificar_pontos_redundantes(list(cadeia))
        if len(pontos) >= 2:
            fechado = len(pontos) >= 4 and _dist(pontos[0], pontos[-1]) <= TOLERANCIA_CONEXAO
            elementos.append(_elemento_polyline(pontos, fechado=fechado))
    return elementos


def _estender_cadeia(
    cadeia: deque[tuple[float, float]],
    adj: dict[tuple[int, int], list[int]],
    segmentos: list[tuple[tuple[float, float], tuple[float, float]]],
    usados: set[int],
    *,
    frente: bool,
) -> None:
    while True:
        ponta = cadeia[-1] if frente else cadeia[0]
        candidatos = [idx for idx in adj.get(_chave_ponto(ponta), []) if idx not in usados]
        if not candidatos:
            return
        idx = candidatos[0]
        usados.add(idx)
        a, b = segmentos[idx]
        proximo = b if _pontos_iguais(a, ponta) else a
        if frente:
            cadeia.append(proximo)
        else:
            cadeia.appendleft(proximo)


def _simplificar_pontos_redundantes(pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    limpos: list[tuple[float, float]] = []
    for pt in pontos:
        p = (float(pt[0]), float(pt[1]))
        if not limpos or _dist(limpos[-1], p) > TOLERANCIA_CONEXAO:
            limpos.append(p)
    if len(limpos) < 3:
        return limpos

    fechado = _dist(limpos[0], limpos[-1]) <= TOLERANCIA_CONEXAO
    base = limpos[:-1] if fechado else limpos
    if len(base) < 3:
        return limpos

    mudou = True
    while mudou and len(base) >= 3:
        mudou = False
        saida: list[tuple[float, float]] = []
        total = len(base)
        for i, atual in enumerate(base):
            if not fechado and i in {0, total - 1}:
                saida.append(atual)
                continue
            anterior = base[i - 1]
            proximo = base[(i + 1) % total]
            if _ponto_colinear_redundante(anterior, atual, proximo):
                mudou = True
                continue
            saida.append(atual)
        base = saida
    if fechado and base:
        base = _rotacionar_para_inicio_estavel(base)
        return [*base, base[0]]
    return base


def _rotacionar_para_inicio_estavel(pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not pontos:
        return pontos
    inicio = min(range(len(pontos)), key=lambda i: (pontos[i][0], pontos[i][1]))
    return [*pontos[inicio:], *pontos[:inicio]]


def _ponto_colinear_redundante(
    anterior: tuple[float, float],
    atual: tuple[float, float],
    proximo: tuple[float, float],
) -> bool:
    ab = _dist(anterior, atual)
    bc = _dist(atual, proximo)
    ac = _dist(anterior, proximo)
    if ab <= TOLERANCIA_CONEXAO or bc <= TOLERANCIA_CONEXAO:
        return True
    if ac <= TOLERANCIA_CONEXAO:
        return False
    area2 = abs((atual[0] - anterior[0]) * (proximo[1] - anterior[1]) - (atual[1] - anterior[1]) * (proximo[0] - anterior[0]))
    return area2 / ac <= TOLERANCIA_COLINEAR and abs((ab + bc) - ac) <= max(TOLERANCIA_COLINEAR, ac * 1e-6)


def _chave_ponto(p: tuple[float, float]) -> tuple[int, int]:
    return (round(float(p[0]) / TOLERANCIA_CONEXAO), round(float(p[1]) / TOLERANCIA_CONEXAO))


def _pontos_iguais(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return _chave_ponto(a) == _chave_ponto(b)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
