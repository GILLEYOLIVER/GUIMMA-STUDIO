from __future__ import annotations

import base64
from collections import deque
from math import ceil
from math import hypot
from typing import Any

from PySide6.QtGui import QImage


def tamanho_preview_base64(imagem_base64: str) -> tuple[int, int]:
    try:
        bruto = base64.b64decode(imagem_base64 or "")
        img = QImage.fromData(bruto)
        if img.isNull():
            return 0, 0
        return int(img.width()), int(img.height())
    except Exception:
        return 0, 0


def vetorizar_preview_adsx(
    imagem_base64: str,
    escala_x: float = 1.0,
    escala_y: float | None = None,
    *,
    incluir_linhas_claras: bool = False,
) -> dict[str, Any]:
    """
    Vetorizacao de fallback para previews Audaces.

    O AMKX traz o encaixe como imagens PNG e um binario proprietario file.amk.
    Enquanto o binario nao e decodificado com seguranca, esta rotina converte
    areas verdes do preview em polylines editaveis, marcadas como revisao manual.
    """
    if escala_y is None:
        escala_y = escala_x
    escala_x = float(escala_x or 1.0)
    escala_y = float(escala_y or escala_x or 1.0)

    relatorio: dict[str, Any] = {
        "origem": "adsx_preview_trace",
        "confianca": "baixa",
        "editavel": True,
        "requer_revisao_manual": True,
        "elementos": [],
        "mensagem": "Contornos gerados a partir de preview. Revise antes de usar como molde final.",
        "sucesso": False,
    }
    try:
        bruto = base64.b64decode(imagem_base64 or "")
        img = QImage.fromData(bruto)
        if img.isNull():
            relatorio["erro"] = "Imagem preview invalida."
            return relatorio
        img = img.convertToFormat(QImage.Format_RGB32)
        w = int(img.width())
        h = int(img.height())
        mask = _mascara_linhas_preview(img) if incluir_linhas_claras else _mascara_areas_coloridas(img)
        if incluir_linhas_claras:
            mask = _dilatar_mask(mask, w, h)
        elementos: list[dict[str, Any]] = []
        area_minima = max(20 if incluir_linhas_claras else 80, int(w * h * (0.00035 if incluir_linhas_claras else 0.00015)))
        for componente in _componentes_conectados(mask):
            if len(componente) < area_minima:
                continue
            if incluir_linhas_claras and not _componente_tem_formato_de_molde(componente):
                continue
            contorno = _contorno_componente(componente)
            if len(contorno) < 8:
                continue
            simplificado = _simplificar_dp(contorno, max(3.0, min(w, h) * 0.01))
            simplificado = _limitar_pontos(simplificado, 360)
            if len(simplificado) < 5:
                continue
            pontos = [(float(x - (w / 2.0)) * escala_x, float(y - (h / 2.0)) * escala_y) for x, y in simplificado]
            if pontos[0] != pontos[-1]:
                pontos.append(pontos[0])
            elementos.append(
                {
                    "tipo": "polyline",
                    "pontos": pontos,
                    "origem": "adsx_preview_trace",
                    "confianca": "baixa",
                    "editavel": True,
                    "requer_revisao_manual": True,
                    "cor": "#00d000",
                    "molde": True,
                    "fechado": True,
                    "preview_trace": True,
                }
            )
        relatorio["elementos"] = elementos
        relatorio["sucesso"] = bool(elementos)
        relatorio["largura_preview_px"] = w
        relatorio["altura_preview_px"] = h
        relatorio["escala_x_cm_por_px"] = escala_x
        relatorio["escala_y_cm_por_px"] = escala_y
        return relatorio
    except Exception as exc:
        relatorio["erro"] = str(exc)
        return relatorio


def _mascara_areas_coloridas(img: QImage) -> set[tuple[int, int]]:
    mask: set[tuple[int, int]] = set()
    for y in range(int(img.height())):
        for x in range(int(img.width())):
            cor = img.pixelColor(x, y)
            r, g, b = cor.red(), cor.green(), cor.blue()
            maior = max(r, g, b)
            menor = min(r, g, b)
            saturado = maior >= 110 and (maior - menor) >= 70
            verde_preview = g >= 95 and g > r * 1.25 and g > b * 1.25
            if saturado or verde_preview:
                mask.add((x, y))
    return mask


def _mascara_linhas_preview(img: QImage) -> set[tuple[int, int]]:
    mask: set[tuple[int, int]] = set()
    for y in range(int(img.height())):
        for x in range(int(img.width())):
            cor = img.pixelColor(x, y)
            r, g, b = cor.red(), cor.green(), cor.blue()
            maior = max(r, g, b)
            menor = min(r, g, b)
            luminancia = (r + g + b) / 3.0
            colorido = maior >= 28 and (maior - menor) >= 10
            claro = luminancia >= 70 and maior >= 80
            if colorido or claro:
                mask.add((x, y))
    return mask


def _dilatar_mask(mask: set[tuple[int, int]], largura: int, altura: int) -> set[tuple[int, int]]:
    dilatado = set(mask)
    for x, y in list(mask):
        for nx in (x - 1, x, x + 1):
            for ny in (y - 1, y, y + 1):
                if 0 <= nx < largura and 0 <= ny < altura:
                    dilatado.add((nx, ny))
    return dilatado


def _componente_tem_formato_de_molde(comp: set[tuple[int, int]]) -> bool:
    xs = [x for x, _ in comp]
    ys = [y for _, y in comp]
    largura = max(xs) - min(xs) + 1
    altura = max(ys) - min(ys) + 1
    if largura < 5 or altura < 5:
        return False
    razao = max(largura / max(altura, 1), altura / max(largura, 1))
    if razao > 18:
        return False
    if len(comp) < max(18, int((largura + altura) * 0.45)):
        return False
    return True


def _componentes_conectados(mask: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    restantes = set(mask)
    componentes: list[set[tuple[int, int]]] = []
    while restantes:
        inicio = restantes.pop()
        comp = {inicio}
        fila: deque[tuple[int, int]] = deque([inicio])
        while fila:
            x, y = fila.popleft()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in restantes:
                    restantes.remove(nb)
                    comp.add(nb)
                    fila.append(nb)
        componentes.append(comp)
    return componentes


def _contorno_componente(comp: set[tuple[int, int]]) -> list[tuple[float, float]]:
    proximos: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for x, y in comp:
        if (x, y - 1) not in comp:
            _adicionar_aresta_borda(proximos, (x, y), (x + 1, y))
        if (x + 1, y) not in comp:
            _adicionar_aresta_borda(proximos, (x + 1, y), (x + 1, y + 1))
        if (x, y + 1) not in comp:
            _adicionar_aresta_borda(proximos, (x + 1, y + 1), (x, y + 1))
        if (x - 1, y) not in comp:
            _adicionar_aresta_borda(proximos, (x, y + 1), (x, y))
    if not proximos:
        return []

    usados: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    loops: list[list[tuple[int, int]]] = []
    inicios = sorted(proximos.keys(), key=lambda p: (p[1], p[0]))
    for inicio in inicios:
        for primeiro in list(proximos.get(inicio, [])):
            aresta = (inicio, primeiro)
            if aresta in usados:
                continue
            loop = [inicio]
            atual = inicio
            proximo = primeiro
            while True:
                usados.add((atual, proximo))
                atual = proximo
                loop.append(atual)
                if atual == inicio:
                    break
                candidatos = proximos.get(atual, [])
                pendentes = [p for p in candidatos if (atual, p) not in usados]
                if not pendentes:
                    break
                proximo = pendentes[0]
            if len(loop) > 3:
                loops.append(loop)
    if not loops:
        return []
    loop_maior = max(loops, key=len)
    return [(float(x), float(y)) for x, y in loop_maior]


def _adicionar_aresta_borda(
    proximos: dict[tuple[int, int], list[tuple[int, int]]], inicio: tuple[int, int], fim: tuple[int, int]
) -> None:
    proximos.setdefault(inicio, []).append(fim)


def _dist_ponto_segmento(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ((dx * dx) + (dy * dy))))
    proj = (ax + t * dx, ay + t * dy)
    return hypot(px - proj[0], py - proj[1])


def _simplificar_dp(pontos: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    if len(pontos) <= 3:
        return pontos
    a = pontos[0]
    b = pontos[-1]
    idx = 0
    maior = 0.0
    for i in range(1, len(pontos) - 1):
        dist = _dist_ponto_segmento(pontos[i], a, b)
        if dist > maior:
            maior = dist
            idx = i
    if maior <= eps:
        return [a, b]
    esquerda = _simplificar_dp(pontos[: idx + 1], eps)
    direita = _simplificar_dp(pontos[idx:], eps)
    return esquerda[:-1] + direita


def _limitar_pontos(pontos: list[tuple[float, float]], max_pontos: int) -> list[tuple[float, float]]:
    if len(pontos) <= max_pontos:
        return pontos
    passo = max(1, ceil(len(pontos) / max_pontos))
    reduzidos = pontos[::passo]
    if pontos[-1] not in reduzidos:
        reduzidos.append(pontos[-1])
    return reduzidos
