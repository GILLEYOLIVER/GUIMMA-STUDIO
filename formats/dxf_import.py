from __future__ import annotations


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

    def flush():
        nonlocal atual, entidade
        if entidade == "LINE":
            x1 = _f(atual.get("10"))
            y1 = _f(atual.get("20"))
            x2 = _f(atual.get("11"))
            y2 = _f(atual.get("21"))
            if None not in (x1, y1, x2, y2):
                elementos.append({"tipo": "polyline", "pontos": [(x1, y1), (x2, y2)], "cor": "#ff5a00"})
        elif entidade == "LWPOLYLINE":
            xs = atual.get("10", [])
            ys = atual.get("20", [])
            if isinstance(xs, list) and isinstance(ys, list):
                pts = list(zip(xs, ys))
                if len(pts) >= 2:
                    for a, b in zip(pts, pts[1:]):
                        elementos.append({"tipo": "polyline", "pontos": [a, b], "cor": "#ff5a00"})
                    flag = int(_f(atual.get("70")) or 0)
                    if flag & 1:
                        elementos.append({"tipo": "polyline", "pontos": [pts[-1], pts[0]], "cor": "#ff5a00"})
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
    return elementos


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
