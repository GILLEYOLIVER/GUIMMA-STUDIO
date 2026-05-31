from __future__ import annotations

from math import cos, pi, sin, sqrt

from PySide6.QtCore import QPointF

try:
    from tools import medicao_cpp_bridge as _medicao_cpp
except Exception:  # pragma: no cover - fallback quando a ponte C++ nao existir
    _medicao_cpp = None


_EPS = 1e-9


def _dist(a: QPointF, b: QPointF) -> float:
    if _medicao_cpp is not None:
        try:
            return float(_medicao_cpp.dist(a, b))
        except Exception:
            pass
    return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)


def _qpoint(item) -> QPointF | None:
    try:
        if isinstance(item, QPointF):
            return QPointF(item)
        if isinstance(item, dict):
            return QPointF(float(item.get("x", 0.0)), float(item.get("y", 0.0)))
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            return QPointF(float(item[0]), float(item[1]))
    except Exception:
        return None
    return None


def _pontos_lista(origem) -> list[QPointF]:
    if not isinstance(origem, list):
        return []
    pontos: list[QPointF] = []
    for item in origem:
        ponto = _qpoint(item)
        if ponto is not None:
            pontos.append(ponto)
    return pontos


def _dist_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> float:
    if _medicao_cpp is not None:
        try:
            return float(_medicao_cpp.dist_ponto_segmento(a, b, p))
        except Exception:
            pass
    abx = b.x() - a.x()
    aby = b.y() - a.y()
    apx = p.x() - a.x()
    apy = p.y() - a.y()
    denom = (abx * abx) + (aby * aby)
    if denom <= _EPS:
        return _dist(a, p)
    t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
    proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
    return _dist(proj, p)


def _projetar_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> QPointF:
    if _medicao_cpp is not None:
        try:
            return QPointF(_medicao_cpp.projetar_ponto_segmento(a, b, p))
        except Exception:
            pass
    abx = b.x() - a.x()
    aby = b.y() - a.y()
    apx = p.x() - a.x()
    apy = p.y() - a.y()
    denom = (abx * abx) + (aby * aby)
    if denom <= _EPS:
        return QPointF(a)
    t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
    return QPointF(a.x() + (abx * t), a.y() + (aby * t))


def _amostrar_bezier_quadratica(p0: QPointF, p1: QPointF, p2: QPointF, segmentos: int = 64) -> list[QPointF]:
    if _medicao_cpp is not None:
        try:
            return _medicao_cpp.amostrar_bezier_quadratica(p0, p1, p2, segmentos=segmentos)
        except Exception:
            pass
    pontos: list[QPointF] = []
    n = max(4, int(segmentos))
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x())
        y = (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y())
        pontos.append(QPointF(x, y))
    return pontos


def _controle_bezier_por_3_pontos(p0: QPointF, p_meio: QPointF, p2: QPointF) -> QPointF:
    """Controle quadrático para curva que passa por p_meio no t=0.5."""
    return QPointF(
        (2.0 * p_meio.x()) - (0.5 * (p0.x() + p2.x())),
        (2.0 * p_meio.y()) - (0.5 * (p0.y() + p2.y())),
    )


def _controles_parabola_3p(elemento: dict) -> list[QPointF]:
    if str(elemento.get("tipo_curva") or "").strip().lower() != "parabola_3p":
        return []
    for chave in ("pontos_principais", "pontos_controle_curva", "pontos_controle_principais", "pontos_controle", "pontos"):
        pontos = _pontos_lista(elemento.get(chave))
        if len(pontos) == 3:
            return pontos
    return []


def _amostrar_curva_suave(pontos_base: list[QPointF], segmentos_por_trecho: int = 18) -> list[QPointF]:
    """Amostra uma curva suave do mesmo tipo visual usado no canvas."""
    if len(pontos_base) < 3:
        return [QPointF(p) for p in pontos_base]

    fechado = len(pontos_base) > 3 and _dist(pontos_base[0], pontos_base[-1]) <= 1e-6
    if _medicao_cpp is not None and hasattr(_medicao_cpp, "amostrar_catmull_rom"):
        try:
            return _medicao_cpp.amostrar_catmull_rom(pontos_base, segmentos_por_trecho=segmentos_por_trecho, fechado=fechado)
        except Exception:
            pass

    pts = [QPointF(p) for p in (pontos_base[:-1] if fechado else pontos_base)]
    if len(pts) < 3:
        return [QPointF(p) for p in pontos_base]

    resultado: list[QPointF] = [QPointF(pts[0])]
    total = len(pts)
    limite = total if fechado else total - 1
    n = max(4, int(segmentos_por_trecho))
    tensao = 1.0

    for i in range(limite):
        p0 = pts[(i - 1) % total] if fechado or i > 0 else pts[i]
        p1 = pts[i]
        p2 = pts[(i + 1) % total]
        p3 = pts[(i + 2) % total] if fechado or i + 2 < total else p2

        c1 = QPointF(
            p1.x() + (p2.x() - p0.x()) * tensao / 6.0,
            p1.y() + (p2.y() - p0.y()) * tensao / 6.0,
        )
        c2 = QPointF(
            p2.x() - (p3.x() - p1.x()) * tensao / 6.0,
            p2.y() - (p3.y() - p1.y()) * tensao / 6.0,
        )

        for s in range(1, n + 1):
            t = s / n
            u = 1.0 - t
            x = (
                (u ** 3) * p1.x()
                + 3.0 * (u ** 2) * t * c1.x()
                + 3.0 * u * (t ** 2) * c2.x()
                + (t ** 3) * p2.x()
            )
            y = (
                (u ** 3) * p1.y()
                + 3.0 * (u ** 2) * t * c1.y()
                + 3.0 * u * (t ** 2) * c2.y()
                + (t ** 3) * p2.y()
            )
            resultado.append(QPointF(x, y))

    if fechado and _dist(resultado[0], resultado[-1]) > 1e-6:
        resultado.append(QPointF(resultado[0]))
    return resultado


def pontos_de_elemento(elemento: dict, canvas=None) -> list[QPointF]:
    """Retorna os pontos reais/amostrados usados para medir e realçar o elemento."""
    if not isinstance(elemento, dict):
        return []

    tipo = str(elemento.get("tipo") or "").lower().strip()
    tipo_curva = str(elemento.get("tipo_curva") or "").lower().strip()

    if tipo == "bezier_quadratica":
        p0 = _qpoint(elemento.get("p0", (0.0, 0.0)))
        p1 = _qpoint(elemento.get("p1", (0.0, 0.0)))
        p2 = _qpoint(elemento.get("p2", (0.0, 0.0)))
        if p0 is not None and p1 is not None and p2 is not None:
            return _amostrar_bezier_quadratica(p0, p1, p2, segmentos=96)
        return []

    if tipo_curva == "parabola_3p":
        controles = _controles_parabola_3p(elemento)
        if len(controles) == 3:
            p0, p_meio, p2 = controles
            if _medicao_cpp is not None and hasattr(_medicao_cpp, "amostrar_parabola_3p"):
                try:
                    return _medicao_cpp.amostrar_parabola_3p(p0, p_meio, p2, segmentos=96)
                except Exception:
                    pass
            p1 = _controle_bezier_por_3_pontos(p0, p_meio, p2)
            return _amostrar_bezier_quadratica(p0, p1, p2, segmentos=96)

    if tipo in {"circle", "esfera"}:
        centro = _qpoint(elemento.get("centro"))
        try:
            raio = float(elemento.get("raio", 0.0))
        except Exception:
            raio = 0.0
        if centro is not None and raio > 0:
            return [
                QPointF(centro.x() + cos((2.0 * pi * i) / 96) * raio, centro.y() + sin((2.0 * pi * i) / 96) * raio)
                for i in range(97)
            ]
        return []

    pontos = _pontos_lista(elemento.get("pontos"))

    if canvas is not None and hasattr(canvas, "_pontos_render_elemento") and tipo == "polyline":
        try:
            render = canvas._pontos_render_elemento(elemento)
            if isinstance(render, list) and len(render) >= 2:
                pontos = [QPointF(p) for p in render]
        except Exception:
            pass

    if len(pontos) >= 3 and (
        elemento.get("curva_suave")
        or elemento.get("suavizar")
        or str(elemento.get("renderizacao") or "").lower() == "curva_suave"
        or tipo_curva.startswith("spline")
    ):
        return _amostrar_curva_suave(pontos, segmentos_por_trecho=18)

    return pontos


def _fechado(pontos: list[QPointF]) -> bool:
    return len(pontos) >= 3 and _dist(pontos[0], pontos[-1]) <= 1e-6


def _controles_limite_medicao(elemento: dict) -> list[QPointF]:
    """Pontos que quebram um molde em trechos de perímetro.

    Em moldes, a medida não deve pegar o contorno inteiro: ela deve ir do ponto
    de controle/canto até o próximo ponto de controle/canto, como nos sistemas de
    modelagem. Para linhas soltas, a ponta inicial e a ponta final continuam
    sendo a referência.
    """
    if not isinstance(elemento, dict):
        return []
    if not bool(elemento.get("molde")) and not elemento.get("controle_cantos"):
        return []

    for chave in (
        "controle_cantos",
        "pontos_controle_principais",
        "pontos_principais",
        "pontos_controle",
    ):
        pontos = _pontos_lista(elemento.get(chave))
        if len(pontos) >= 2:
            # Remove duplicações próximas preservando a ordem original.
            saida: list[QPointF] = []
            for ponto in pontos:
                if not saida or _dist(saida[-1], ponto) > 1e-6:
                    saida.append(QPointF(ponto))
            if len(saida) >= 2 and _dist(saida[0], saida[-1]) <= 1e-6:
                saida = saida[:-1]
            if len(saida) >= 2:
                return saida
    return []


def _indice_mais_proximo(pontos: list[QPointF], alvo: QPointF) -> int | None:
    if not pontos:
        return None
    melhor_idx = 0
    melhor_dist = _dist(pontos[0], alvo)
    for idx, ponto in enumerate(pontos[1:], start=1):
        d = _dist(ponto, alvo)
        if d < melhor_dist:
            melhor_idx = idx
            melhor_dist = d
    return melhor_idx


def _indices_controle_no_contorno(elemento: dict, pontos: list[QPointF]) -> list[int]:
    controles = _controles_limite_medicao(elemento)
    if len(controles) < 2 or len(pontos) < 2:
        return []
    base = pontos[:-1] if _fechado(pontos) else pontos
    if len(base) < 2:
        return []

    indices: list[int] = []
    for controle in controles:
        idx = _indice_mais_proximo(base, controle)
        if idx is None:
            continue
        if idx not in indices:
            indices.append(idx)
    indices.sort()
    return indices if len(indices) >= 2 else []


def _trecho_fechado_entre_controles(pontos: list[QPointF], controles_idx: list[int], indice_segmento: int) -> list[QPointF]:
    base = pontos[:-1] if _fechado(pontos) else pontos
    total = len(base)
    if total < 2 or len(controles_idx) < 2:
        return [QPointF(p) for p in pontos]

    seg_idx = max(0, min(int(indice_segmento), total - 1))
    controles = sorted(set(int(i) % total for i in controles_idx))

    inicio = controles[0]
    fim = controles[1]
    for pos, atual in enumerate(controles):
        proximo = controles[(pos + 1) % len(controles)]
        if atual <= proximo:
            dentro = atual <= seg_idx < proximo
        else:
            dentro = seg_idx >= atual or seg_idx < proximo
        if dentro:
            inicio = atual
            fim = proximo
            break

    if inicio <= fim:
        trecho = [QPointF(p) for p in base[inicio:fim + 1]]
    else:
        trecho = [QPointF(p) for p in base[inicio:]] + [QPointF(p) for p in base[:fim + 1]]

    if len(trecho) < 2:
        return [QPointF(p) for p in pontos]
    return trecho


def pontos_medicao_para_segmento(elemento: dict, pontos: list[QPointF], indice_segmento: int) -> list[QPointF]:
    """Retorna exatamente o trecho que deve ser medido.

    - Linha/curva solta: mede de uma ponta até a outra.
    - Molde fechado: mede do ponto de controle/canto anterior até o próximo.
    """
    if not isinstance(elemento, dict) or len(pontos) < 2:
        return []

    controles_idx = _indices_controle_no_contorno(elemento, pontos)
    if bool(elemento.get("molde")) and controles_idx and _fechado(pontos):
        return _trecho_fechado_entre_controles(pontos, controles_idx, indice_segmento)

    return [QPointF(p) for p in pontos]


def segmentos_de_elemento(elemento: dict, canvas=None) -> list[tuple[QPointF, QPointF]]:
    pts = pontos_de_elemento(elemento, canvas=canvas)
    return [(a, b) for a, b in zip(pts, pts[1:]) if _dist(a, b) > _EPS]


def comprimento_total_elemento(elemento: dict, canvas=None) -> float:
    return sum(_dist(a, b) for a, b in segmentos_de_elemento(elemento, canvas=canvas))


def _comprimento_pontos(pontos: list[QPointF]) -> float:
    return sum(_dist(a, b) for a, b in zip(pontos, pontos[1:]))


def selecionar_segmento_mais_proximo(canvas, pos: QPointF, tolerancia_px: float = 10.0) -> dict | None:
    """Seleciona o perímetro/trecho mais próximo do clique ou do cursor.

    A chave ``pontos_elemento`` passa a representar o trecho medido. Para linhas
    soltas, é a linha inteira. Para molde com controle_cantos, é somente o trecho
    entre um ponto de controle e o próximo.
    """
    tolerancia_cena = float(tolerancia_px) / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
    elementos = list(getattr(getattr(canvas, "cena", None), "elementos", []) or [])
    melhor: dict | None = None

    for idx in range(len(elementos) - 1, -1, -1):
        el = elementos[idx]
        if not isinstance(el, dict):
            continue
        if str(el.get("tipo") or "").lower() in {"cota_perimetro", "cota_distancia", "texto"}:
            continue
        pontos_completos = pontos_de_elemento(el, canvas=canvas)
        if len(pontos_completos) < 2:
            continue

        for indice_segmento, (a, b) in enumerate(zip(pontos_completos, pontos_completos[1:])):
            d = _dist_ponto_segmento(a, b, pos)
            if d > tolerancia_cena:
                continue

            pontos_medicao = pontos_medicao_para_segmento(el, pontos_completos, indice_segmento)
            total = _comprimento_pontos(pontos_medicao)
            if total <= _EPS:
                continue

            proj = _projetar_ponto_segmento(a, b, pos)
            seg_len = _dist(a, b)
            if melhor is None or d < melhor["dist"]:
                melhor = {
                    "elemento_idx": idx,
                    "elemento": el,
                    "pontos_elemento": [QPointF(p) for p in pontos_medicao],
                    "pontos_medicao": [QPointF(p) for p in pontos_medicao],
                    "pontos_contorno_completo": [QPointF(p) for p in pontos_completos],
                    "ponto_inicial": QPointF(pontos_medicao[0]),
                    "ponto_final": QPointF(pontos_medicao[-1]),
                    "segmento_indice": indice_segmento,
                    "segmento_inicio": QPointF(a),
                    "segmento_fim": QPointF(b),
                    "segmento_comprimento": seg_len,
                    "perimetro_total": total,
                    "perimetro_medicao": total,
                    "ponto_mais_proximo": proj,
                    "dist": d,
                }
    return melhor


def mensagem_status(canvas, texto: str):
    if getattr(canvas, "lbl_status", None) is not None:
        canvas.lbl_status.setText(texto)
