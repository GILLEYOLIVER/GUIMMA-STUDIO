from __future__ import annotations

from math import cos, pi, sin, sqrt

from PySide6.QtCore import QPointF


_EPS = 1e-9


def _dist(a: QPointF, b: QPointF) -> float:
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
    """Retorna os pontos reais/amostrados usados para medir e realçar o elemento.

    O objetivo da ferramenta de perímetro é medir a linha inteira clicada,
    incluindo curvas, e não apenas o pequeno segmento amostrado sob o cursor.
    """
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

    # Quando o canvas tem um render próprio para pontos originais do EMF,
    # respeitamos esse modo sem obrigar a ferramenta a conhecer todo o desenho.
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


def segmentos_de_elemento(elemento: dict, canvas=None) -> list[tuple[QPointF, QPointF]]:
    pts = pontos_de_elemento(elemento, canvas=canvas)
    return [(a, b) for a, b in zip(pts, pts[1:]) if _dist(a, b) > _EPS]


def comprimento_total_elemento(elemento: dict, canvas=None) -> float:
    return sum(_dist(a, b) for a, b in segmentos_de_elemento(elemento, canvas=canvas))


def _comprimento_pontos(pontos: list[QPointF]) -> float:
    return sum(_dist(a, b) for a, b in zip(pontos, pontos[1:]))


def selecionar_segmento_mais_proximo(canvas, pos: QPointF, tolerancia_px: float = 10.0) -> dict | None:
    """Seleciona a linha/curva mais próxima do clique.

    Mantém as chaves antigas de segmento para compatibilidade, mas também
    retorna a geometria completa do elemento em ``pontos_elemento`` e o
    comprimento total em ``perimetro_total``. Assim a ferramenta consegue
    realçar a curva inteira e escrever a medida ao lado do clique.
    """
    tolerancia_cena = float(tolerancia_px) / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
    elementos = list(getattr(getattr(canvas, "cena", None), "elementos", []) or [])
    melhor: dict | None = None

    for idx in range(len(elementos) - 1, -1, -1):
        el = elementos[idx]
        if not isinstance(el, dict):
            continue
        pontos = pontos_de_elemento(el, canvas=canvas)
        if len(pontos) < 2:
            continue
        total = _comprimento_pontos(pontos)
        if total <= _EPS:
            continue

        for indice_segmento, (a, b) in enumerate(zip(pontos, pontos[1:])):
            d = _dist_ponto_segmento(a, b, pos)
            if d > tolerancia_cena:
                continue
            proj = _projetar_ponto_segmento(a, b, pos)
            seg_len = _dist(a, b)
            if melhor is None or d < melhor["dist"]:
                melhor = {
                    "elemento_idx": idx,
                    "elemento": el,
                    "pontos_elemento": [QPointF(p) for p in pontos],
                    "ponto_inicial": QPointF(pontos[0]),
                    "ponto_final": QPointF(pontos[-1]),
                    "segmento_indice": indice_segmento,
                    "segmento_inicio": QPointF(a),
                    "segmento_fim": QPointF(b),
                    "segmento_comprimento": seg_len,
                    "perimetro_total": total,
                    "ponto_mais_proximo": proj,
                    "dist": d,
                }
    return melhor


def mensagem_status(canvas, texto: str):
    if getattr(canvas, "lbl_status", None) is not None:
        canvas.lbl_status.setText(texto)
