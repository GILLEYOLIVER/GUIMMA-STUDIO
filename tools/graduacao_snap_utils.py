from __future__ import annotations

from PySide6.QtCore import QPointF

from canvas.snap import chave_tipo_snap


def ponto_base_para_snap_graduacao(canvas, pos: QPointF) -> QPointF:
    """Converte snap em graduacao para a coordenada equivalente do molde base."""
    snap = getattr(canvas, "_snap_resultado", None)
    if snap is None:
        return QPointF(pos)
    tipo_snap = chave_tipo_snap(getattr(snap, "tipo", ""))
    if tipo_snap not in {"graduacao", "borda graduacao"}:
        return QPointF(pos)
    try:
        idx = int(getattr(snap, "elemento_idx"))
    except Exception:
        return QPointF(pos)
    elementos = getattr(getattr(canvas, "cena", None), "elementos", []) or []
    if not (0 <= idx < len(elementos)):
        return QPointF(pos)

    try:
        from canvas.visualizacao import VisualizacaoCanvas

        el = elementos[idx]
        base = [QPointF(pt) for pt in VisualizacaoCanvas._base_graduacao_elemento(el)]
        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(el, base)
        caminhos = VisualizacaoCanvas._caminhos_graduacao_tabela(el, base)
    except Exception:
        return QPointF(pos)

    ponto = QPointF(pos)
    origem_caminho = _origem_caminho_graduacao(ponto, caminhos) if tipo_snap == "graduacao" else None
    if origem_caminho is not None:
        return origem_caminho

    ponto_base = _mapear_contorno_graduado_para_base(ponto, base, contornos)
    return ponto_base if ponto_base is not None else QPointF(pos)


def snap_atual_eh_graduacao(canvas) -> bool:
    snap = getattr(canvas, "_snap_resultado", None)
    if snap is None:
        return False
    return chave_tipo_snap(getattr(snap, "tipo", "")) in {"graduacao", "borda graduacao"}


def _origem_caminho_graduacao(
    ponto: QPointF,
    caminhos: list[tuple[str, str, QPointF, QPointF]],
) -> QPointF | None:
    melhor: tuple[float, QPointF] | None = None
    for _nome, _cor, origem, destino in caminhos or []:
        dist2 = _dist2(ponto, destino)
        if melhor is None or dist2 < melhor[0]:
            melhor = (dist2, QPointF(origem))
    if melhor is None:
        return None
    return melhor[1]


def _mapear_contorno_graduado_para_base(
    ponto: QPointF,
    base: list[QPointF],
    contornos: list[tuple[str, str, list[QPointF]]],
) -> QPointF | None:
    if len(base) < 2:
        return None
    melhor: tuple[float, QPointF] | None = None
    for _nome, _cor, contorno in contornos or []:
        pontos = [QPointF(pt) for pt in contorno]
        if len(pontos) < 2:
            continue
        fechado = _dist2(pontos[0], pontos[-1]) <= 1e-12 and len(pontos) == len(base) + 1
        limite = len(base) if fechado else min(len(base), len(pontos)) - 1
        for seg_idx in range(max(0, limite)):
            a = pontos[seg_idx]
            b = pontos[(seg_idx + 1) % len(pontos)]
            t, dist2 = _parametro_distancia_segmento(ponto, a, b)
            base_a = base[seg_idx % len(base)]
            base_b = base[(seg_idx + 1) % len(base)]
            base_ponto = QPointF(
                base_a.x() + ((base_b.x() - base_a.x()) * t),
                base_a.y() + ((base_b.y() - base_a.y()) * t),
            )
            if melhor is None or dist2 < melhor[0]:
                melhor = (dist2, base_ponto)
    if melhor is None:
        return None
    return melhor[1]


def _parametro_distancia_segmento(p: QPointF, a: QPointF, b: QPointF) -> tuple[float, float]:
    abx = b.x() - a.x()
    aby = b.y() - a.y()
    den = (abx * abx) + (aby * aby)
    if den <= 1e-12:
        return 0.0, _dist2(p, a)
    t = (((p.x() - a.x()) * abx) + ((p.y() - a.y()) * aby)) / den
    t = max(0.0, min(1.0, t))
    proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
    return t, _dist2(p, proj)


def _dist2(a: QPointF, b: QPointF) -> float:
    dx = a.x() - b.x()
    dy = a.y() - b.y()
    return (dx * dx) + (dy * dy)
