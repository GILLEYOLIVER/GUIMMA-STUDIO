from __future__ import annotations

from collections import defaultdict, deque
from math import acos, degrees, hypot
from pathlib import Path
import re
import unicodedata


TOLERANCIA_CONEXAO = 1e-5
TOLERANCIA_COLINEAR = 1e-5


def importar_dxf_para_elementos(
    caminho: str,
    *,
    agrupar_matriz: bool = False,
    tamanho_base: str = "P",
    grade_tamanhos: list[dict] | None = None,
    audaces_xml_path: str | None = None,
    audaces_emf_path: str | None = None,
    usar_audaces_associado: bool = True,
) -> list[dict]:
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
    textos: list[dict] = []

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
        elif entidade in {"TEXT", "MTEXT"}:
            texto = _texto_dxf_de_atual(atual)
            x = _f(atual.get("10"))
            y = _f(atual.get("20"))
            if texto and x is not None and y is not None:
                textos.append({
                    "texto": texto,
                    "pos": (float(x), float(y)),
                    "altura": _f(atual.get("40")),
                    "angulo": _angulo_texto_dxf(atual),
                    "entidade": entidade,
                })
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
            if value in {"LINE", "LWPOLYLINE", "TEXT", "MTEXT"}:
                entidade = value
            continue
        if entidade is None:
            continue

        if entidade == "LWPOLYLINE" and code in {"10", "20"}:
            atual.setdefault(code, []).append(_f(value))
        elif entidade in {"TEXT", "MTEXT"} and code in {"1", "3"}:
            atual.setdefault(code, []).append(value)
        else:
            atual[code] = value
    flush()

    elementos.extend(_linhas_conectadas_para_polylines(segmentos_line))
    if agrupar_matriz:
        contexto_audaces = _contexto_audaces_associado_dxf(
            caminho,
            xml_path=audaces_xml_path,
            emf_path=audaces_emf_path,
            habilitado=usar_audaces_associado,
        )
        matriz = _consolidar_matriz_tamanhos_dxf(
            elementos,
            textos,
            tamanho_base=tamanho_base,
            grade_tamanhos=grade_tamanhos,
            contexto_audaces=contexto_audaces,
        )
        return matriz or elementos
    elementos.extend(_textos_dxf_para_elementos(textos))
    return elementos


def detectar_tamanhos_matriz_dxf(
    caminho: str,
    grade_tamanhos: list[dict] | None = None,
    *,
    audaces_xml_path: str | None = None,
    audaces_emf_path: str | None = None,
) -> list[dict]:
    elementos = importar_dxf_para_elementos(
        caminho,
        agrupar_matriz=True,
        grade_tamanhos=grade_tamanhos,
        audaces_xml_path=audaces_xml_path,
        audaces_emf_path=audaces_emf_path,
    )
    grades = [
        (
            el.get("graduacao_tamanhos") or [],
            bool((el.get("metadados") or {}).get("audaces_xml_path")),
        )
        for el in elementos
        if isinstance(el, dict)
        and el.get("molde")
        and isinstance(el.get("graduacao_tamanhos"), list)
        and el.get("metadados", {}).get("matriz_tamanhos_dxf")
    ]
    grades = [(grade, tem_xml) for grade, tem_xml in grades if grade]
    if not grades:
        return []
    maior, tem_xml = max(grades, key=lambda item: len(item[0]))
    return [
        {
            "ativo": bool(linha.get("ativo", True)),
            "tamanho": str(linha.get("tamanho") or "").strip(),
            "cor": str(linha.get("cor") or CORES_GRADE_DXF_PADRAO[idx % len(CORES_GRADE_DXF_PADRAO)]),
            "base": bool(tem_xml and linha.get("base", False)),
        }
        for idx, linha in enumerate(maior)
        if isinstance(linha, dict) and str(linha.get("tamanho") or "").strip()
    ]


def _elemento_polyline(pontos: list[tuple[float, float]], *, fechado: bool = False) -> dict:
    return {
        "tipo": "polyline",
        "pontos": pontos,
        "cor": "#ff5a00",
        "origem_importador": "dxf",
        "fechado": bool(fechado),
    }


def _textos_dxf_para_elementos(textos: list[dict]) -> list[dict]:
    saida: list[dict] = []
    for texto in textos:
        conteudo = str(texto.get("texto") or "").strip()
        pos = texto.get("pos")
        if not conteudo or not isinstance(pos, tuple) or len(pos) < 2:
            continue
        altura = _f(texto.get("altura"))
        altura_cm = max(0.25, min(12.0, float(altura))) if altura is not None and altura > 0 else 1.0
        angulo = _f(texto.get("angulo"))
        saida.append({
            "tipo": "texto",
            "texto": conteudo,
            "conteudo": conteudo,
            "posicao": (float(pos[0]), float(pos[1])),
            "ponto": (float(pos[0]), float(pos[1])),
            "origem": (float(pos[0]), float(pos[1])),
            "cor": "#ffffff",
            "cor_texto": "#ffffff",
            "texto_altura_cm": altura_cm,
            "altura_cm": altura_cm,
            "texto_espaco_linhas_cm": max(altura_cm * 1.25, 0.35),
            "espaco_linhas_cm": max(altura_cm * 1.25, 0.35),
            "texto_espessura": 1.0,
            "espessura": 1.0,
            "angulo": float(angulo or 0.0),
            "referencia": "Centro centro",
            "justificacao": "Centro",
            "origem_importador": "dxf",
            "subtipo_audaces": "texto",
            "metadados": {
                "origem": "dxf_texto",
                "entidade_dxf": str(texto.get("entidade") or "TEXT"),
            },
        })
    return saida


def _texto_dxf_de_atual(atual: dict) -> str:
    partes: list[str] = []
    for code in ("3", "1"):
        valor = atual.get(code)
        if isinstance(valor, list):
            partes.extend(str(item) for item in valor)
        elif valor is not None:
            partes.append(str(valor))
    return _limpar_texto_dxf("".join(partes))


def _limpar_texto_dxf(texto: str) -> str:
    texto = str(texto or "")
    texto = texto.replace("\\P", "\n").replace("\\p", "\n")
    texto = texto.replace("%%d", "deg").replace("%%D", "deg")
    texto = re.sub(r"\\[A-Za-z][^;]*;", "", texto)
    texto = texto.replace("{", "").replace("}", "")
    linhas = [" ".join(linha.split()) for linha in texto.splitlines()]
    return "\n".join(linha for linha in linhas if linha).strip()


def _angulo_texto_dxf(atual: dict) -> float:
    angulo = _f(atual.get("50"))
    if angulo is not None:
        return float(angulo)
    vx = _f(atual.get("11"))
    vy = _f(atual.get("21"))
    if vx is None or vy is None:
        return 0.0
    if abs(vx) <= 1e-9 and abs(vy) <= 1e-9:
        return 0.0
    from math import atan2

    return degrees(atan2(float(vy), float(vx)))


def _contexto_audaces_associado_dxf(
    caminho: str,
    *,
    xml_path: str | None = None,
    emf_path: str | None = None,
    habilitado: bool = True,
) -> dict:
    if not habilitado:
        return {}
    base = Path(caminho)
    contexto: dict = {"audaces_associado": False}
    xml = _resolver_arquivo_associado(base, ".xml", xml_path)
    if xml is not None:
        try:
            from formats.audaces_xml_import import AudacesXMLImport

            xml_doc = AudacesXMLImport.abrir(xml)
            labels, base_xml = _grade_xml_doc_dxf(xml_doc)
            pecas_validas = _pecas_xml_validas_dxf(list(getattr(xml_doc, "pecas", []) or []))
            tem_quantidade_explicitada = any(
                _quantidade_tamanho_xml_dxf(tamanho) is not None
                for peca in pecas_validas
                for tamanho in (getattr(peca, "tamanhos", []) or [])
            )
            contexto.update({
                "audaces_associado": True,
                "xml_path": str(xml),
                "xml_doc": xml_doc,
                "xml_grade_labels": labels,
                "xml_tamanho_base": base_xml,
                "xml_grade_quantidade_explicitada": tem_quantidade_explicitada,
                "xml_modelo": getattr(xml_doc, "nome_modelo", ""),
                "xml_pecas": pecas_validas,
            })
        except Exception as exc:
            contexto["xml_path"] = str(xml)
            contexto["xml_erro"] = f"{type(exc).__name__}: {exc}"
    emf = _resolver_arquivo_associado(base, ".emf", emf_path)
    if emf is not None:
        contexto.update({
            "audaces_associado": True,
            "emf_path": str(emf),
            "emf_tamanho_bytes": int(emf.stat().st_size) if emf.exists() else 0,
        })
    return contexto if contexto.get("audaces_associado") else {}


def _resolver_arquivo_associado(base: Path, extensao: str, explicito: str | None) -> Path | None:
    if explicito:
        p = Path(explicito)
        return p if p.exists() else None
    alvo = base.with_suffix(extensao)
    if alvo.exists():
        return alvo
    alvo_upper = base.with_suffix(extensao.upper())
    if alvo_upper.exists():
        return alvo_upper
    try:
        stem_norm = base.stem.casefold()
        ext_norm = extensao.casefold()
        for candidato in base.parent.iterdir():
            if candidato.is_file() and candidato.stem.casefold() == stem_norm and candidato.suffix.casefold() == ext_norm:
                return candidato
    except Exception:
        return None
    return None


def _grade_xml_doc_dxf(xml_doc) -> tuple[list[str], str | None]:
    labels_todos: list[str] = []
    labels_disponiveis: list[str] = []
    bases: list[str] = []
    tem_quantidade_explicitada = False
    for peca in getattr(xml_doc, "pecas", []) or []:
        if _nome_marcado_reflexao_dxf(getattr(peca, "nome", "")):
            continue
        base = str(getattr(peca, "tamanho_base", "") or "").strip()
        if base:
            bases.append(base)
        for tamanho in getattr(peca, "tamanhos", []) or []:
            nome = str(getattr(tamanho, "tamanho", "") or "").strip()
            if not nome:
                continue
            if _normalizar_tamanho_dxf(nome) not in {_normalizar_tamanho_dxf(label) for label in labels_todos}:
                labels_todos.append(nome)
            quantidade = _quantidade_tamanho_xml_dxf(tamanho)
            if quantidade is not None:
                tem_quantidade_explicitada = True
            if quantidade is not None and quantidade > 0:
                if _normalizar_tamanho_dxf(nome) not in {_normalizar_tamanho_dxf(label) for label in labels_disponiveis}:
                    labels_disponiveis.append(nome)
    labels = labels_disponiveis if tem_quantidade_explicitada and labels_disponiveis else labels_todos
    if not labels:
        for tamanho in getattr(xml_doc, "tamanhos_modelo", []) or []:
            nome = str(getattr(tamanho, "nome", "") or "").strip()
            if nome and _normalizar_tamanho_dxf(nome) not in {_normalizar_tamanho_dxf(label) for label in labels}:
                labels.append(nome)
    base = _resolver_tamanho_base_dxf(labels, bases)
    return labels, base


def _quantidade_tamanho_xml_dxf(tamanho) -> int | None:
    for attr in ("quantidade_posicionada", "quantidade"):
        valor = getattr(tamanho, attr, None)
        if valor is None:
            continue
        try:
            return int(valor)
        except (TypeError, ValueError):
            continue
    return None


def _resolver_tamanho_base_dxf(labels: list[str], candidatos: list[str] | None = None) -> str | None:
    labels_validos = [str(label or "").strip() for label in labels if str(label or "").strip()]
    if not labels_validos:
        return None
    por_norm = {_normalizar_tamanho_dxf(label): label for label in labels_validos}
    for candidato in candidatos or []:
        chave = _normalizar_tamanho_dxf(candidato)
        if chave in por_norm:
            return por_norm[chave]
    for preferido in ("P", "M", "38", "40", "G"):
        chave = _normalizar_tamanho_dxf(preferido)
        if chave in por_norm:
            return por_norm[chave]
    return labels_validos[len(labels_validos) // 2]


def _normalizar_tamanho_dxf(valor: str | None) -> str:
    return re.sub(r"\s+", "", str(valor or "").strip().upper())


def _linhas_grade_xml_dxf(
    labels: list[str],
    *,
    tamanho_base: str,
    grade_tamanhos: list[dict] | None = None,
) -> list[dict]:
    cores_usuario = {
        _normalizar_tamanho_dxf(linha.get("tamanho")): str(linha.get("cor") or "")
        for linha in (grade_tamanhos or [])
        if isinstance(linha, dict) and str(linha.get("tamanho") or "").strip()
    }
    ativos_usuario = {
        _normalizar_tamanho_dxf(linha.get("tamanho")): bool(linha.get("ativo", True))
        for linha in (grade_tamanhos or [])
        if isinstance(linha, dict) and str(linha.get("tamanho") or "").strip()
    }
    base_norm = _normalizar_tamanho_dxf(tamanho_base)
    if base_norm not in {_normalizar_tamanho_dxf(label) for label in labels}:
        base = _resolver_tamanho_base_dxf(labels, [tamanho_base])
        base_norm = _normalizar_tamanho_dxf(base)
    linhas: list[dict] = []
    for idx, label in enumerate(labels):
        chave = _normalizar_tamanho_dxf(label)
        cor = cores_usuario.get(chave) or CORES_GRADE_DXF_PADRAO[idx % len(CORES_GRADE_DXF_PADRAO)]
        linhas.append({
            "tamanho": str(label).strip(),
            "ativo": ativos_usuario.get(chave, True),
            "base": chave == base_norm,
            "cor": cor,
        })
    return linhas


def _limitar_linhas_grade_aos_contornos_dxf(linhas: list[dict], qtd_contornos: int, tamanho_base: str) -> list[dict]:
    if qtd_contornos <= 0 or len(linhas) <= qtd_contornos:
        return linhas
    base_norm = _normalizar_tamanho_dxf(tamanho_base)
    idx_base = next(
        (
            i
            for i, linha in enumerate(linhas)
            if _normalizar_tamanho_dxf(linha.get("tamanho")) == base_norm or linha.get("base")
        ),
        min(len(linhas) - 1, qtd_contornos // 2),
    )
    inicio = min(max(0, idx_base - (qtd_contornos // 2)), max(0, len(linhas) - qtd_contornos))
    return [dict(linha) for linha in linhas[inicio:inicio + qtd_contornos]]


def _aplicar_contexto_audaces_dxf(
    molde: dict,
    contexto: dict,
    *,
    nome: str,
    xml_usados: set[int],
    labels: list[str],
    tamanho_base: str,
) -> None:
    if not contexto:
        return
    metadados = molde.setdefault("metadados", {})
    if not isinstance(metadados, dict):
        metadados = {}
        molde["metadados"] = metadados
    metadados["audaces_associado"] = True
    if contexto.get("xml_path"):
        metadados["audaces_xml_path"] = str(contexto.get("xml_path"))
        metadados["audaces_xml_modelo"] = str(contexto.get("xml_modelo") or "")
    if contexto.get("emf_path"):
        metadados["audaces_emf_path"] = str(contexto.get("emf_path"))
        metadados["audaces_emf_tamanho_bytes"] = int(contexto.get("emf_tamanho_bytes") or 0)
    if contexto.get("xml_erro"):
        metadados["audaces_xml_erro"] = str(contexto.get("xml_erro"))

    peca_info = _selecionar_peca_xml_dxf(nome, contexto.get("xml_pecas") or [], xml_usados)
    if peca_info is None:
        return
    idx_xml, peca = peca_info
    xml_usados.add(int(idx_xml))
    nome_xml = str(getattr(peca, "nome", "") or "").strip()
    if nome_xml:
        molde["nome_molde"] = nome_xml
    molde["descricao_molde"] = str(getattr(peca, "descricao", "") or "").strip()
    tecido = str(getattr(peca, "tecido", "") or "").strip()
    if tecido:
        molde["tecido"] = tecido
    for chave_molde, attr in (
        ("quantidade", "quantidade"),
        ("rotacao_audaces", "rotacao"),
        ("dobra_horizontal_audaces", "dobra_horizontal"),
        ("dobra_vertical_audaces", "dobra_vertical"),
        ("piques_audaces", "piques"),
        ("piques_internos_audaces", "piques_internos"),
    ):
        valor = getattr(peca, attr, None)
        if valor is not None:
            molde[chave_molde] = valor
    dims = _dimensoes_peca_xml_dxf(peca, labels=labels, tamanho_base=tamanho_base)
    if dims:
        molde["graduacao_dimensoes_xml"] = dims
    metadados["audaces_xml_pattern_index"] = int(idx_xml)
    metadados["audaces_xml_pattern_name"] = nome_xml
    metadados["audaces_xml_enriquecido"] = True


def _selecionar_peca_xml_dxf(nome: str, pecas: list, usados: set[int]) -> tuple[int, object] | None:
    if not pecas:
        return None
    alvo = _normalizar_nome_peca_dxf(nome)
    candidatos: list[tuple[int, object, int]] = []
    for idx, peca in enumerate(pecas):
        if _nome_marcado_reflexao_dxf(getattr(peca, "nome", "")):
            continue
        nome_peca = _normalizar_nome_peca_dxf(getattr(peca, "nome", ""))
        if not nome_peca:
            continue
        if nome_peca == alvo:
            candidatos.append((idx, peca, 3))
        elif nome_peca in alvo or alvo in nome_peca:
            candidatos.append((idx, peca, 2))
    if not candidatos:
        return None
    candidatos.sort(key=lambda item: (-item[2], item[0] in usados, item[0]))
    idx, peca, _score = candidatos[0]
    return idx, peca


def _normalizar_nome_peca_dxf(valor: str | None) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.upper()
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _nome_marcado_reflexao_dxf(valor: str | None) -> bool:
    return "#" in str(valor or "")


def _pecas_xml_validas_dxf(pecas: list) -> list:
    return [
        peca
        for peca in (pecas or [])
        if not _nome_marcado_reflexao_dxf(getattr(peca, "nome", ""))
    ]


def _dimensoes_peca_xml_dxf(peca, *, labels: list[str], tamanho_base: str) -> dict:
    labels_norm = {_normalizar_tamanho_dxf(label): label for label in labels}
    base_norm = _normalizar_tamanho_dxf(tamanho_base)
    dims: dict[str, dict] = {}
    for tamanho in getattr(peca, "tamanhos", []) or []:
        nome = str(getattr(tamanho, "tamanho", "") or "").strip()
        if not nome:
            continue
        nome_final = labels_norm.get(_normalizar_tamanho_dxf(nome), nome)
        dims[nome_final] = {
            "perimetro": getattr(tamanho, "perimetro", None),
            "area": getattr(tamanho, "area", None),
            "perimetro_retilineo": getattr(tamanho, "perimetro_retilineo", None),
            "perimetro_curva": getattr(tamanho, "perimetro_curva", None),
            "largura": getattr(tamanho, "largura", None),
            "altura": getattr(tamanho, "altura", None),
            "base": _normalizar_tamanho_dxf(nome_final) == base_norm,
        }
    return dims


def _contornos_fechados_ou_quase_fechados_matriz_dxf(elementos: list[dict]) -> list[dict]:
    saida: list[dict] = []
    for el in elementos:
        if not isinstance(el, dict) or len(el.get("pontos") or []) < 4:
            continue
        if el.get("fechado"):
            saida.append(el)
            continue
        pontos = [(float(x), float(y)) for x, y in (el.get("pontos") or [])]
        bbox = _bbox(pontos)
        if not bbox:
            continue
        largura = max(float(bbox[2]) - float(bbox[0]), 0.0)
        altura = max(float(bbox[3]) - float(bbox[1]), 0.0)
        if max(largura, altura) < 4.0 or min(largura, altura) < 1.0:
            continue
        diag = max((largura * largura + altura * altura) ** 0.5, 1e-9)
        gap = _dist(pontos[0], pontos[-1])
        if gap > max(0.35, diag * 0.015):
            continue
        fechados = list(pontos)
        if _dist(fechados[0], fechados[-1]) > TOLERANCIA_CONEXAO:
            fechados.append(fechados[0])
        area = abs(_area_assinada_dxf(fechados))
        area_bbox = max(largura * altura, 1e-9)
        if area < 8.0 or area / area_bbox < 0.05:
            continue
        novo = dict(el)
        novo["pontos"] = _simplificar_pontos_redundantes(fechados)
        novo["fechado"] = True
        novo["fechado_por_gap_importacao"] = True
        metadados = dict(novo.get("metadados") or {})
        metadados["fechado_por_gap_importacao"] = True
        novo["metadados"] = metadados
        saida.append(novo)
    return saida


def _consolidar_matriz_tamanhos_dxf(
    elementos: list[dict],
    textos: list[dict],
    *,
    tamanho_base: str = "P",
    grade_tamanhos: list[dict] | None = None,
    contexto_audaces: dict | None = None,
) -> list[dict]:
    if not textos:
        return []
    contexto_audaces = contexto_audaces or {}
    pecas_xml_validas = _pecas_xml_validas_dxf(contexto_audaces.get("xml_pecas") or [])
    nomes_xml_validos = {
        _normalizar_nome_peca_dxf(getattr(peca, "nome", ""))
        for peca in pecas_xml_validas
        if _normalizar_nome_peca_dxf(getattr(peca, "nome", ""))
    }
    fechados = _contornos_fechados_ou_quase_fechados_matriz_dxf(elementos)
    abertos = [
        el
        for el in elementos
        if isinstance(el, dict) and not el.get("fechado") and len(el.get("pontos") or []) >= 2
    ]
    if not fechados:
        return []

    por_nome = _agrupar_contornos_por_texto_central(fechados, textos)
    grupos = {}
    dedup_stats_por_nome: dict[str, dict] = {}
    for nome, contornos in por_nome.items():
        if _nome_marcado_reflexao_dxf(nome):
            continue
        nome_xml = _normalizar_nome_peca_dxf(nome)
        manter_unitario_xml = bool(nome_xml and nome_xml in nomes_xml_validos)
        if len(contornos) < 2 and not manter_unitario_xml:
            continue
        contornos, dedup_stats = _deduplicar_contornos_matriz_dxf(contornos)
        contornos = _cluster_principal_contornos_compativeis(contornos)
        if len(contornos) >= 2 or (len(contornos) == 1 and manter_unitario_xml):
            grupos[nome] = contornos
            dedup_stats_por_nome[nome] = dedup_stats
    if not grupos:
        return []

    saida: list[dict] = []
    moldes_para_linhas: list[tuple[dict, list[tuple[float, float]]]] = []
    labels_xml = [
        str(label or "").strip()
        for label in (contexto_audaces.get("xml_grade_labels") or [])
        if str(label or "").strip()
    ]
    tamanho_base_xml = str(contexto_audaces.get("xml_tamanho_base") or "").strip()
    tamanho_base_efetivo = tamanho_base_xml or str(tamanho_base or "P").strip() or "P"
    if labels_xml:
        linhas_grade_global = _linhas_grade_xml_dxf(
            labels_xml,
            tamanho_base=tamanho_base_efetivo,
            grade_tamanhos=grade_tamanhos,
        )
        if not contexto_audaces.get("xml_grade_quantidade_explicitada"):
            qtd_grade_global = max(len(contornos) for contornos in grupos.values())
            linhas_grade_global = _limitar_linhas_grade_aos_contornos_dxf(
                linhas_grade_global,
                qtd_grade_global,
                tamanho_base_efetivo,
            )
    else:
        qtd_grade_global = max(len(contornos) for contornos in grupos.values())
        linhas_grade_global = _linhas_grade_para_quantidade(
            qtd_grade_global,
            tamanho_base=tamanho_base,
            grade_tamanhos=grade_tamanhos,
        )
    xml_usados: set[int] = set()
    for nome, contornos in sorted(grupos.items(), key=lambda item: _ordem_visual_contornos(item[1])):
        contornos = sorted(contornos, key=lambda el: (_area_bbox(el), _centro_bbox(_bbox(el.get("pontos") or []))[0]))
        linhas_grade = [dict(linha) for linha in linhas_grade_global]
        labels = [linha["tamanho"] for linha in linhas_grade]
        cores = {linha["tamanho"]: linha["cor"] for linha in linhas_grade}
        tamanho_base_norm = _normalizar_tamanho_dxf(tamanho_base_efetivo)
        idx_base_linha = next(
            (
                i
                for i, label in enumerate(labels)
                if _normalizar_tamanho_dxf(label) == tamanho_base_norm
            ),
            next((i for i, linha in enumerate(linhas_grade) if linha.get("base")), 0),
        )
        tamanho_base_final = labels[idx_base_linha]
        base_idx = next((i for i, label in enumerate(labels) if label == tamanho_base_final), 0)
        base_idx = min(base_idx, len(contornos) - 1)
        base = contornos[base_idx]
        base_pontos = [(float(x), float(y)) for x, y in base.get("pontos", [])]
        graduacao = []
        for label, contorno in zip(labels, contornos):
            pontos = [(float(x), float(y)) for x, y in contorno.get("pontos", [])]
            pontos = _alinhar_pontos_ao_base(pontos, base_pontos)
            graduacao.append({
                "tamanho": label,
                "cor": cores.get(label, "#ff5a00"),
                "base": label == tamanho_base_final,
                "pontos": pontos,
            })
        tabela_graduacao = _graduacao_tabela_dxf_de_contornos(base_pontos, graduacao, labels=labels)
        graduacao = _graduacao_contornos_dxf_de_tabela(
            base_pontos,
            labels,
            cores,
            tamanho_base_final,
            tabela_graduacao,
            graduacao,
            gerar_faltantes=True,
        )
        molde_id = f"dxf-{len(moldes_para_linhas) + 1:03d}"
        molde = {
            "tipo": "polyline",
            "pontos": base_pontos,
            "cor": cores.get(tamanho_base_final, "#ff5a00"),
            "origem_importador": "dxf",
            "origem": "dxf_matriz_graduada",
            "fechado": True,
            "molde": True,
            "molde_pronto": True,
            "nome_molde": nome,
            "molde_id": molde_id,
            "mostrar_nome": True,
            "mostrar_fio": True,
            "mostrar_controles": True,
            "mostrar_controles_permanente": True,
            "mostrar_numeros": False,
            "mostrar_graduacao": True,
            "mostrar_linhas_auxiliares": True,
            "subtipo_audaces": "contorno",
            "graduacao_preferir_tabela_dxdy": True,
            "graduacao_renderizar_por_tabela_derivada": False,
            "graduacao_preservar_cores_importadas": False,
            "graduacao_cores_sinteticas": True,
            "graduacao_grade_nome": "-".join(labels) + f"({tamanho_base_final})",
            "graduacao_tamanhos": [
                {
                    "tamanho": linha["tamanho"],
                    "ativo": bool(linha.get("ativo", True)),
                    "base": linha["tamanho"] == tamanho_base_final,
                    "cor": linha["cor"],
                }
                for linha in linhas_grade
            ],
            "graduacao_tamanhos_ativos": labels,
            "tamanho_base": tamanho_base_final,
            "tamanho_base_detectado": tamanho_base_final,
            "graduacao_contornos_importados": graduacao,
            "graduacao_tabela": tabela_graduacao,
            "graduacao_pontos": dict(tabela_graduacao.get("pontos", {})),
            "graduacao_regularizada_por_base": {
                "aplicado": True,
                "base": tamanho_base_final,
                "metodo": "dxf_matriz_por_texto_e_dimensao",
                "tamanhos_reais": labels,
            },
            "metadados": {
                "origem": "dxf_matriz_graduada",
                "matriz_tamanhos_dxf": True,
                "contornos_origem": len(contornos),
                "agrupamento": "sobreposto_por_texto_central_e_geometria",
                "graduacao_cores_origem": "sintetica_guimma",
            },
        }
        _aplicar_contexto_audaces_dxf(
            molde,
            contexto_audaces,
            nome=nome,
            xml_usados=xml_usados,
            labels=labels,
            tamanho_base=tamanho_base_final,
        )
        _aplicar_fio_padrao_guimma_dxf(molde, base_pontos)
        dedup_stats = dedup_stats_por_nome.get(nome) or {}
        if dedup_stats.get("par_detectado"):
            molde["par"] = True
            molde["qtd_modelo"] = 1
            molde["duplicatas_refletidas_ignoradas_dxf"] = int(dedup_stats.get("pares_ignorados", 0) or 0)
            molde["metadados"]["pares_refletidos_ignorados_dxf"] = int(dedup_stats.get("pares_ignorados", 0) or 0)
            molde["metadados"]["par_detectado_por_perimetro_dxf"] = True
        _aplicar_controles_base_dxf(molde)
        tabela_principais = _graduacao_tabela_dxf_de_pontos_base(
            base_pontos,
            molde.get("controle_cantos") or [],
            graduacao,
            labels=labels,
        )
        if tabela_principais.get("pontos"):
            molde["graduacao_tabela"] = tabela_principais
            molde["graduacao_pontos"] = dict(tabela_principais.get("pontos", {}))
            molde["graduacao_tabela_apenas_pontos_principais"] = True
            molde["metadados"]["graduacao_tabela_pontos"] = "pontos_principais"
            molde["graduacao_preferir_tabela_dxdy"] = True
            molde["graduacao_renderizar_por_tabela_derivada"] = False
        saida.append(molde)
        moldes_para_linhas.append((molde, base_pontos))
    saida.extend(_vincular_linhas_auxiliares_base_dxf(abertos, moldes_para_linhas))
    return saida


def _aplicar_fio_padrao_guimma_dxf(elemento: dict, pontos_base: list[tuple[float, float]]) -> None:
    base = _sem_fecho_repetido([(float(x), float(y)) for x, y in pontos_base])
    bbox = _bbox(base)
    if not base or not bbox:
        return
    min_x, min_y, max_x, max_y = bbox
    largura = max_x - min_x
    altura = max_y - min_y
    diag = hypot(largura, altura)
    if diag <= 1e-9:
        return
    if largura >= max(altura * 0.35, 1e-6):
        margem = min(max(largura * 0.12, diag * 0.03), largura * 0.42)
        y = min_y + (altura * 0.50)
        origem = (float(min_x + margem), float(y))
        fim = (float(max_x - margem), float(y))
        angulo = 0.0
    else:
        margem = min(max(altura * 0.12, diag * 0.03), altura * 0.42)
        x = min_x + (largura * 0.50)
        origem = (float(x), float(min_y + margem))
        fim = (float(x), float(max_y - margem))
        angulo = 90.0
    if _dist(origem, fim) <= 1e-9:
        return
    elemento["fio_origem"] = origem
    elemento["fio_fim"] = fim
    elemento["fio_angulo"] = angulo
    elemento["mostrar_fio"] = True


def _aplicar_controles_base_dxf(elemento: dict) -> None:
    pontos_base = _sem_fecho_repetido([(float(x), float(y)) for x, y in elemento.get("pontos", [])])
    if not pontos_base:
        return
    cantos = _controle_cantos_por_quinas(pontos_base)
    cantos = _complementar_controles_principais_suaves_dxf(pontos_base, cantos)
    auxiliares = _controle_auxiliares_reduzidos_dxf(pontos_base, cantos)
    elemento["controle_cantos"] = [(float(x), float(y)) for x, y in cantos]
    elemento["controle_auxiliares"] = auxiliares
    elemento["pontos_controle_principais"] = [
        {"x": float(x), "y": float(y), "origem": "dxf_matriz_ponto_base"}
        for x, y in cantos
    ]
    elemento["pontos_auxiliares"] = [
        {"x": float(x), "y": float(y), "origem": "dxf_matriz_auxiliar"}
        for x, y in auxiliares
    ]
    elemento["cantos_preservados_importacao"] = len(cantos)
    elemento["auxiliares_preservados_importacao"] = len(auxiliares)
    elemento["cantos_detectados_importacao"] = len(cantos)


def _complementar_controles_principais_suaves_dxf(
    pontos_base: list[tuple[float, float]],
    cantos: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    base = _sem_fecho_repetido(pontos_base)
    if not base or len(cantos) >= 4:
        return cantos
    candidatos = [*cantos, *_controles_principais_extremos_dxf(base)]
    indices: set[int] = set()
    for ponto in candidatos:
        if not ponto:
            continue
        idx = min(range(len(base)), key=lambda i: _dist(base[i], ponto))
        indices.add(int(idx))
    return [base[idx] for idx in sorted(indices)]


def _controles_principais_extremos_dxf(pontos_base: list[tuple[float, float]]) -> list[tuple[float, float]]:
    base = _sem_fecho_repetido(pontos_base)
    if len(base) <= 4:
        return base
    indices = {
        min(range(len(base)), key=lambda idx: (base[idx][0], idx)),
        max(range(len(base)), key=lambda idx: (base[idx][0], -idx)),
        min(range(len(base)), key=lambda idx: (base[idx][1], idx)),
        max(range(len(base)), key=lambda idx: (base[idx][1], -idx)),
    }
    return [base[idx] for idx in sorted(indices)]


def _controle_auxiliares_reduzidos_dxf(
    pontos_base: list[tuple[float, float]],
    cantos: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    base = _sem_fecho_repetido(pontos_base)
    if not base:
        return []
    chaves_cantos = {_chave_ponto_controle(ponto) for ponto in cantos}
    if not chaves_cantos:
        return _deduplicar_pontos_controle(_reduzir_controles_trecho_dxf([*base, base[0]], fechado=True))

    indices_cantos = [
        idx
        for idx, ponto in enumerate(base)
        if _chave_ponto_controle(ponto) in chaves_cantos
    ]
    if not indices_cantos:
        return _deduplicar_pontos_controle(_reduzir_controles_trecho_dxf([*base, base[0]], fechado=True))

    auxiliares: list[tuple[float, float]] = []
    total = len(base)
    for pos, inicio in enumerate(indices_cantos):
        fim = indices_cantos[(pos + 1) % len(indices_cantos)]
        trecho = [base[inicio]]
        atual = inicio
        while atual != fim:
            atual = (atual + 1) % total
            trecho.append(base[atual])
        if len(trecho) <= 2:
            continue
        reduzidos = _reduzir_controles_trecho_dxf(trecho)
        auxiliares.extend(reduzidos[1:-1])

    return _deduplicar_pontos_controle(
        ponto
        for ponto in auxiliares
        if _chave_ponto_controle(ponto) not in chaves_cantos
    )


def _reduzir_controles_trecho_dxf(
    pontos: list[tuple[float, float]],
    *,
    fechado: bool = False,
) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in pontos]
    if len(pts) <= 3:
        return _sem_fecho_repetido(pts) if fechado else pts
    tolerancia = _tolerancia_controle_auxiliar_dxf(pts)
    reduzidos = _rdp_pontos_dxf(pts, tolerancia)
    maximo = _max_controles_auxiliares_trecho_dxf(pts, incluir_extremos=not fechado)
    tentativas = 0
    while len(reduzidos) > maximo and tentativas < 8:
        tolerancia *= 1.35
        reduzidos = _rdp_pontos_dxf(pts, tolerancia)
        tentativas += 1
    if fechado:
        reduzidos = _sem_fecho_repetido(reduzidos)
    return reduzidos


def _rdp_pontos_dxf(
    pontos: list[tuple[float, float]],
    tolerancia: float,
) -> list[tuple[float, float]]:
    if len(pontos) <= 2:
        return list(pontos)
    inicio = pontos[0]
    fim = pontos[-1]
    maior_distancia = -1.0
    maior_idx = 0
    for idx, ponto in enumerate(pontos[1:-1], start=1):
        distancia = _distancia_ponto_segmento(ponto, inicio, fim)
        if distancia > maior_distancia:
            maior_distancia = distancia
            maior_idx = idx
    if maior_distancia <= tolerancia:
        return [inicio, fim]
    esquerda = _rdp_pontos_dxf(pontos[: maior_idx + 1], tolerancia)
    direita = _rdp_pontos_dxf(pontos[maior_idx:], tolerancia)
    return [*esquerda[:-1], *direita]


def _tolerancia_controle_auxiliar_dxf(pontos: list[tuple[float, float]]) -> float:
    bbox = _bbox(pontos)
    if not bbox:
        return 0.12
    diagonal = hypot(float(bbox[2]) - float(bbox[0]), float(bbox[3]) - float(bbox[1]))
    return max(0.08, min(0.45, diagonal * 0.006))


def _max_controles_auxiliares_trecho_dxf(
    pontos: list[tuple[float, float]],
    *,
    incluir_extremos: bool,
) -> int:
    comprimento = sum(_dist(a, b) for a, b in zip(pontos, pontos[1:]))
    base = int(max(4, min(22, round(comprimento / 2.8))))
    return base + (2 if incluir_extremos else 0)


def _deduplicar_pontos_controle(pontos) -> list[tuple[float, float]]:
    saida: list[tuple[float, float]] = []
    vistos: set[tuple[int, int]] = set()
    for ponto in pontos or []:
        chave = _chave_ponto_controle(ponto)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append((float(ponto[0]), float(ponto[1])))
    return saida


def _chave_ponto_controle(ponto: tuple[float, float]) -> tuple[int, int]:
    return (round(float(ponto[0]) * 1000000), round(float(ponto[1]) * 1000000))


def _graduacao_tabela_dxf_de_contornos(
    base_pontos: list[tuple[float, float]],
    graduacao: list[dict],
    *,
    labels: list[str] | None = None,
) -> dict:
    base = _sem_fecho_repetido(base_pontos)
    if not base:
        return {"modo": "dx_dy", "pontos": {}}
    parametros_base = _parametros_contorno(base)
    pontos_cfg: dict[str, dict] = {}
    contornos_por_tamanho: dict[str, list[tuple[float, float]]] = {}
    for item in graduacao:
        if not isinstance(item, dict):
            continue
        tamanho = str(item.get("tamanho") or "").strip()
        if not tamanho:
            continue
        contornos_por_tamanho[tamanho] = _sem_fecho_repetido(
            [(float(x), float(y)) for x, y in (item.get("pontos") or [])]
        )
    labels_ordenados = [
        str(label).strip()
        for label in (labels or list(contornos_por_tamanho))
        if str(label).strip()
    ]
    for idx, ponto_base in enumerate(base):
        valores_existentes: dict[str, tuple[float, float]] = {}
        parametro = parametros_base[idx] if idx < len(parametros_base) else 0.0
        for tamanho, contorno in contornos_por_tamanho.items():
            ponto_tamanho = _ponto_correspondente_contorno(contorno, idx, len(base), parametro)
            valores_existentes[tamanho] = (
                _zero_pequeno(ponto_tamanho[0] - ponto_base[0]),
                _zero_pequeno(ponto_tamanho[1] - ponto_base[1]),
            )
        valores: dict[str, dict[str, float]] = {}
        anchors = {
            ordem: valores_existentes[label]
            for ordem, label in enumerate(labels_ordenados)
            if label in valores_existentes
        }
        for ordem, tamanho in enumerate(labels_ordenados):
            dx, dy = valores_existentes.get(tamanho, _interpolar_deslocamento_grade(ordem, anchors))
            valores[tamanho] = {"dx": _zero_pequeno(dx), "dy": _zero_pequeno(dy)}
        pontos_cfg[str(idx)] = {
            "indice": int(idx),
            "numero": int(idx) + 1,
            "ponto": (float(ponto_base[0]), float(ponto_base[1])),
            "valores": valores,
        }
    return {"modo": "dx_dy", "origem": "dxf_matriz_aproximada", "regras_exatas": False, "pontos": pontos_cfg}


def _graduacao_tabela_dxf_de_pontos_base(
    base_pontos: list[tuple[float, float]],
    pontos_referencia: list[tuple[float, float]],
    graduacao: list[dict],
    *,
    labels: list[str] | None = None,
) -> dict:
    base = _sem_fecho_repetido(base_pontos)
    referencias = _deduplicar_pontos_controle(pontos_referencia)
    if not base or not referencias:
        return {"modo": "dx_dy", "origem": "dxf_matriz_pontos_principais", "regras_exatas": False, "pontos": {}}

    parametros_base = _parametros_contorno(base)
    contornos_por_tamanho: dict[str, list[tuple[float, float]]] = {}
    for item in graduacao:
        if not isinstance(item, dict):
            continue
        tamanho = str(item.get("tamanho") or "").strip()
        if not tamanho:
            continue
        contornos_por_tamanho[tamanho] = _sem_fecho_repetido(
            [(float(x), float(y)) for x, y in (item.get("pontos") or [])]
        )

    labels_ordenados = [
        str(label).strip()
        for label in (labels or list(contornos_por_tamanho))
        if str(label).strip()
    ]
    pontos_cfg: dict[str, dict] = {}
    indices_usados: set[int] = set()
    for numero, ponto_ref in enumerate(referencias, start=1):
        idx_base = min(range(len(base)), key=lambda idx: _dist(base[idx], ponto_ref))
        if idx_base in indices_usados:
            continue
        indices_usados.add(idx_base)
        ponto_base = base[idx_base]
        parametro = parametros_base[idx_base] if idx_base < len(parametros_base) else 0.0
        valores_existentes: dict[str, tuple[float, float]] = {}
        for tamanho, contorno in contornos_por_tamanho.items():
            ponto_tamanho = _ponto_correspondente_contorno(contorno, idx_base, len(base), parametro)
            valores_existentes[tamanho] = (
                _zero_pequeno(ponto_tamanho[0] - ponto_base[0]),
                _zero_pequeno(ponto_tamanho[1] - ponto_base[1]),
            )

        valores: dict[str, dict[str, float]] = {}
        anchors = {
            ordem: valores_existentes[label]
            for ordem, label in enumerate(labels_ordenados)
            if label in valores_existentes
        }
        for ordem, tamanho in enumerate(labels_ordenados):
            dx, dy = valores_existentes.get(tamanho, _interpolar_deslocamento_grade(ordem, anchors))
            valores[tamanho] = {"dx": _zero_pequeno(dx), "dy": _zero_pequeno(dy)}

        chave = str(len(pontos_cfg))
        pontos_cfg[chave] = {
            "indice": int(len(pontos_cfg)),
            "indice_base": int(idx_base),
            "numero": int(len(pontos_cfg)) + 1,
            "ponto": (float(ponto_base[0]), float(ponto_base[1])),
            "valores": valores,
        }

    return {
        "modo": "dx_dy",
        "origem": "dxf_matriz_pontos_principais",
        "regras_exatas": False,
        "pontos_principais_apenas": True,
        "pontos": pontos_cfg,
    }


def _graduacao_contornos_dxf_de_tabela(
    base_pontos: list[tuple[float, float]],
    labels: list[str],
    cores: dict[str, str],
    tamanho_base: str,
    tabela: dict,
    existentes: list[dict],
    *,
    gerar_faltantes: bool = True,
) -> list[dict]:
    base = _sem_fecho_repetido(base_pontos)
    pontos_cfg = tabela.get("pontos") if isinstance(tabela, dict) else {}
    if not base or not isinstance(pontos_cfg, dict):
        return existentes
    existentes_por_tamanho = {
        str(item.get("tamanho") or "").strip(): item
        for item in existentes
        if isinstance(item, dict) and str(item.get("tamanho") or "").strip()
    }
    saida: list[dict] = []
    for label in labels:
        tamanho = str(label or "").strip()
        if not tamanho:
            continue
        existente = existentes_por_tamanho.get(tamanho)
        if existente is not None:
            pontos = [
                (_zero_pequeno(float(x)), _zero_pequeno(float(y)))
                for x, y in (existente.get("pontos") or [])
            ]
            if pontos and pontos[0] != pontos[-1]:
                pontos.append(pontos[0])
        else:
            if not gerar_faltantes:
                continue
            pontos = []
            for idx, ponto in enumerate(base):
                cfg = pontos_cfg.get(str(idx)) if isinstance(pontos_cfg, dict) else None
                valores = cfg.get("valores") if isinstance(cfg, dict) else None
                deslocamento = valores.get(tamanho) if isinstance(valores, dict) else None
                dx = _zero_pequeno(deslocamento.get("dx", 0.0)) if isinstance(deslocamento, dict) else 0.0
                dy = _zero_pequeno(deslocamento.get("dy", 0.0)) if isinstance(deslocamento, dict) else 0.0
                pontos.append((_zero_pequeno(float(ponto[0]) + dx), _zero_pequeno(float(ponto[1]) + dy)))
            if pontos and pontos[0] != pontos[-1]:
                pontos.append(pontos[0])
        item = {
            "tamanho": tamanho,
            "cor": cores.get(tamanho, "#ff5a00"),
            "base": tamanho == tamanho_base,
            "pontos": pontos,
        }
        if existente is None:
            item["gerado_por_tabela_dxf"] = True
        saida.append(item)
    return saida


def _interpolar_deslocamento_grade(
    indice: int,
    anchors: dict[int, tuple[float, float]],
) -> tuple[float, float]:
    if not anchors:
        return (0.0, 0.0)
    if indice in anchors:
        return anchors[indice]
    ordenados = sorted(anchors.items())
    if len(ordenados) == 1:
        return ordenados[0][1]
    if indice < ordenados[0][0]:
        return _extrapolar_deslocamento(indice, ordenados[0], ordenados[1])
    if indice > ordenados[-1][0]:
        return _extrapolar_deslocamento(indice, ordenados[-2], ordenados[-1])
    for (idx_a, valor_a), (idx_b, valor_b) in zip(ordenados, ordenados[1:]):
        if idx_a <= indice <= idx_b:
            if idx_a == idx_b:
                return valor_a
            t = (indice - idx_a) / float(idx_b - idx_a)
            return (
                valor_a[0] + (valor_b[0] - valor_a[0]) * t,
                valor_a[1] + (valor_b[1] - valor_a[1]) * t,
            )
    return ordenados[-1][1]


def _extrapolar_deslocamento(
    indice: int,
    a: tuple[int, tuple[float, float]],
    b: tuple[int, tuple[float, float]],
) -> tuple[float, float]:
    idx_a, valor_a = a
    idx_b, valor_b = b
    if idx_a == idx_b:
        return valor_b
    t = (indice - idx_a) / float(idx_b - idx_a)
    return (
        valor_a[0] + (valor_b[0] - valor_a[0]) * t,
        valor_a[1] + (valor_b[1] - valor_a[1]) * t,
    )


def _parametros_contorno(pontos: list[tuple[float, float]]) -> list[float]:
    pts = _sem_fecho_repetido(pontos)
    if not pts:
        return []
    if len(pts) == 1:
        return [0.0]
    segmentos = [_dist(a, b) for a, b in zip(pts, [*pts[1:], pts[0]])]
    total = sum(segmentos)
    if total <= 1e-9:
        return [0.0 for _ in pts]
    saida = []
    acumulado = 0.0
    for idx, _ponto in enumerate(pts):
        saida.append(acumulado / total)
        if idx < len(segmentos):
            acumulado += segmentos[idx]
    return saida


def _ponto_correspondente_contorno(
    contorno: list[tuple[float, float]],
    indice: int,
    total_base: int,
    parametro: float,
) -> tuple[float, float]:
    pts = _sem_fecho_repetido(contorno)
    if not pts:
        return (0.0, 0.0)
    if len(pts) == total_base and 0 <= indice < len(pts):
        return pts[indice]
    if len(pts) == 1:
        return pts[0]
    return _ponto_no_contorno_por_parametro(pts, parametro)


def _ponto_no_contorno_por_parametro(
    pontos: list[tuple[float, float]],
    parametro: float,
) -> tuple[float, float]:
    pts = _sem_fecho_repetido(pontos)
    if not pts:
        return (0.0, 0.0)
    if len(pts) == 1:
        return pts[0]
    segmentos = [_dist(a, b) for a, b in zip(pts, [*pts[1:], pts[0]])]
    total = sum(segmentos)
    if total <= 1e-9:
        return pts[0]
    alvo = (float(parametro) % 1.0) * total
    acumulado = 0.0
    for (a, b), comprimento in zip(zip(pts, [*pts[1:], pts[0]]), segmentos):
        if comprimento <= 1e-9:
            continue
        if acumulado + comprimento >= alvo:
            t = (alvo - acumulado) / comprimento
            return (float(a[0]) + (float(b[0]) - float(a[0])) * t, float(a[1]) + (float(b[1]) - float(a[1])) * t)
        acumulado += comprimento
    return pts[-1]


def _zero_pequeno(valor: float) -> float:
    valor = float(valor)
    return 0.0 if abs(valor) <= 1e-9 else valor


def _controle_cantos_por_quinas(
    pontos: list[tuple[float, float]],
    *,
    limite_graus: float = 136.0,
    quina_forte_graus: float = 112.0,
    contraste_minimo_graus: float = 8.0,
) -> list[tuple[float, float]]:
    pts = _sem_fecho_repetido(pontos)
    if len(pts) < 3:
        return pts
    cantos: list[tuple[float, float]] = []
    total = len(pts)
    angulos = [
        _angulo_interno_ponto(pts[(idx - 1) % total], ponto, pts[(idx + 1) % total])
        for idx, ponto in enumerate(pts)
    ]
    for idx, ponto in enumerate(pts):
        angulo = angulos[idx]
        if angulo > limite_graus:
            continue
        if angulo <= quina_forte_graus:
            cantos.append(ponto)
            continue
        vizinho_mais_suave = min(angulos[(idx - 1) % total], angulos[(idx + 1) % total])
        if (vizinho_mais_suave - angulo) >= contraste_minimo_graus:
            cantos.append(ponto)
    return cantos


def _angulo_interno_ponto(
    anterior: tuple[float, float],
    atual: tuple[float, float],
    proximo: tuple[float, float],
) -> float:
    ux = float(anterior[0]) - float(atual[0])
    uy = float(anterior[1]) - float(atual[1])
    vx = float(proximo[0]) - float(atual[0])
    vy = float(proximo[1]) - float(atual[1])
    nu = hypot(ux, uy)
    nv = hypot(vx, vy)
    if nu <= 1e-9 or nv <= 1e-9:
        return 180.0
    dot = max(-1.0, min(1.0, ((ux * vx) + (uy * vy)) / (nu * nv)))
    return degrees(acos(dot))


def _vincular_linhas_auxiliares_base_dxf(
    abertos: list[dict],
    moldes_para_linhas: list[tuple[dict, list[tuple[float, float]]]],
) -> list[dict]:
    if not abertos or not moldes_para_linhas:
        return []
    candidatos_por_molde: dict[str, list[dict]] = defaultdict(list)
    moldes_por_id = {str(molde.get("molde_id") or "").strip(): molde for molde, _base in moldes_para_linhas}
    base_por_id = {str(molde.get("molde_id") or "").strip(): base for molde, base in moldes_para_linhas}
    for aberto in abertos:
        pontos = [(float(x), float(y)) for x, y in aberto.get("pontos", [])]
        if len(pontos) < 2:
            continue
        candidatos = []
        for molde, base_pontos in moldes_para_linhas:
            score = _score_linha_auxiliar_no_contorno(pontos, base_pontos)
            if score is not None:
                candidatos.append((score, molde))
        if not candidatos:
            continue
        _score, molde = min(candidatos, key=lambda item: item[0])
        molde_id = str(molde.get("molde_id") or "").strip()
        if not molde_id:
            continue
        candidatos_por_molde[molde_id].append({"origem": aberto, "pontos": pontos, "score": _score})

    for molde_id, candidatos in candidatos_por_molde.items():
        molde = moldes_por_id.get(molde_id)
        if not isinstance(molde, dict):
            continue
        base = base_por_id.get(molde_id) or []
        usados, piques = _detectar_piques_cruz_dxf(candidatos, base)
        if piques:
            molde.setdefault("piques_config", []).extend(piques)
            molde["mostrar_piques"] = True
            molde["piques_internos_importados"] = int(molde.get("piques_internos_importados", 0) or 0) + len(piques)
        linhas_base = molde.setdefault("linhas_auxiliares_base", [])
        qtd_linhas = 0
        for idx, candidato in enumerate(candidatos):
            if idx in usados:
                continue
            qtd_linhas += 1
            linhas_base.append(_criar_linha_auxiliar_base_dxf(candidato["origem"], molde, candidato["pontos"], qtd_linhas))
        qtd = qtd_linhas
        molde["linhas_auxiliares_importadas"] = qtd
        metadados = molde.setdefault("metadados", {})
        if isinstance(metadados, dict):
            metadados["linhas_auxiliares_dxf"] = qtd
            if piques:
                metadados["piques_internos_cruz_dxf"] = len(piques)
    return []


def _detectar_piques_cruz_dxf(
    candidatos: list[dict],
    base_pontos: list[tuple[float, float]],
) -> tuple[set[int], list[dict]]:
    base = _sem_fecho_repetido(base_pontos)
    bbox_base = _bbox(base)
    if not candidatos or not bbox_base:
        return set(), []
    diag = hypot(bbox_base[2] - bbox_base[0], bbox_base[3] - bbox_base[1])
    comprimento_max = max(0.8, diag * 0.16)
    usados: set[int] = set()
    piques: list[dict] = []
    segmentos: list[tuple[int, tuple[float, float], tuple[float, float], float]] = []
    for idx, candidato in enumerate(candidatos):
        pontos = candidato.get("pontos") or []
        if len(pontos) != 2:
            continue
        a, b = pontos[0], pontos[1]
        comprimento = _dist(a, b)
        if comprimento <= TOLERANCIA_CONEXAO or comprimento > comprimento_max:
            continue
        segmentos.append((idx, a, b, comprimento))

    for pos, (idx_a, a1, a2, comp_a) in enumerate(segmentos):
        if idx_a in usados:
            continue
        for idx_b, b1, b2, comp_b in segmentos[pos + 1:]:
            if idx_b in usados:
                continue
            inter = _intersecao_segmentos_dxf(a1, a2, b1, b2)
            if inter is None:
                continue
            ux = (a2[0] - a1[0], a2[1] - a1[1])
            vx = (b2[0] - b1[0], b2[1] - b1[1])
            denom = max(comp_a * comp_b, 1e-9)
            cos_abs = abs(((ux[0] * vx[0]) + (ux[1] * vx[1])) / denom)
            if cos_abs > 0.45:
                continue
            ratio = max(comp_a, comp_b) / max(min(comp_a, comp_b), 1e-9)
            if ratio > 3.0:
                continue
            usados.update({idx_a, idx_b})
            largura = max(comp_a, comp_b)
            piques.append({
                "tipo": "M+ - marca +",
                "ponto": (float(inter[0]), float(inter[1])),
                "ponto_controle": (float(inter[0]), float(inter[1])),
                "sobre_contorno": False,
                "interno": True,
                "aplicar_todos_tamanhos": True,
                "largura": float(largura),
                "altura": float(largura),
                "segmentos": [
                    ((float(a1[0]), float(a1[1])), (float(a2[0]), float(a2[1]))),
                    ((float(b1[0]), float(b1[1])), (float(b2[0]), float(b2[1]))),
                ],
                "origem": "dxf_matriz_pique_cruz",
            })
            break
    return usados, piques


def _intersecao_segmentos_dxf(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> tuple[float, float] | None:
    ax = a2[0] - a1[0]
    ay = a2[1] - a1[1]
    bx = b2[0] - b1[0]
    by = b2[1] - b1[1]
    denom = (ax * by) - (ay * bx)
    if abs(denom) <= 1e-9:
        return None
    cx = b1[0] - a1[0]
    cy = b1[1] - a1[1]
    t = ((cx * by) - (cy * bx)) / denom
    u = ((cx * ay) - (cy * ax)) / denom
    folga = 1e-6
    if not (folga <= t <= 1.0 - folga and folga <= u <= 1.0 - folga):
        return None
    return (float(a1[0] + ax * t), float(a1[1] + ay * t))


def _criar_linha_auxiliar_base_dxf(
    origem: dict,
    molde: dict,
    pontos: list[tuple[float, float]],
    ordem: int,
) -> dict:
    metadados_origem = origem.get("metadados") if isinstance(origem.get("metadados"), dict) else {}
    return {
        "pontos": [(float(x), float(y)) for x, y in pontos],
        "cor": str(molde.get("cor") or origem.get("cor") or "#bfbfbf"),
        "estilo": "solid",
        "subtipo_audaces": "linha_auxiliar",
        "ordem_linha_auxiliar": int(ordem),
        "aplicar_todos_tamanhos": True,
        "metadados": {
            **dict(metadados_origem),
            "origem": "dxf_matriz_graduada",
            "subtipo_audaces": "linha_interna",
            "detalhe_dxf_agrupado": True,
        },
    }


def _score_linha_auxiliar_no_contorno(
    pontos: list[tuple[float, float]],
    base_pontos: list[tuple[float, float]],
) -> tuple[float, float, float] | None:
    base = _sem_fecho_repetido(base_pontos)
    bbox_base = _bbox(base)
    bbox_linha = _bbox(pontos)
    if len(base) < 3 or not bbox_base or not bbox_linha:
        return None

    largura = max(bbox_base[2] - bbox_base[0], 1e-9)
    altura = max(bbox_base[3] - bbox_base[1], 1e-9)
    diag = hypot(largura, altura)
    margem = max(0.35, diag * 0.08)
    if not _bbox_intersecta_expandido(bbox_base, bbox_linha, margem):
        return None

    tolerancia_borda = max(0.15, diag * 0.015)
    dentro = sum(1 for ponto in pontos if _ponto_dentro_ou_na_borda(ponto, base, tolerancia_borda))
    centro_linha = _centro_bbox(bbox_linha)
    centro_dentro = _ponto_dentro_ou_na_borda(centro_linha, base, tolerancia_borda)
    minimo = max(1, (len(pontos) + 1) // 2)
    if dentro < minimo and not centro_dentro:
        return None

    base_centro = _centro_bbox(bbox_base)
    distancia_centros = hypot(centro_linha[0] - base_centro[0], centro_linha[1] - base_centro[1]) / max(diag, 1e-9)
    area_base = largura * altura
    return (area_base, distancia_centros, -float(dentro))


def _criar_linha_auxiliar_dxf(
    origem: dict,
    molde: dict,
    pontos: list[tuple[float, float]],
    ordem: int,
) -> dict:
    molde_id = str(molde.get("molde_id") or "").strip()
    nome_molde = str(molde.get("nome_molde") or "").strip()
    metadados_origem = origem.get("metadados") if isinstance(origem.get("metadados"), dict) else {}
    metadados = dict(metadados_origem)
    metadados.update({
        "origem": "dxf_matriz_graduada",
        "subtipo_audaces": "linha_interna",
        "molde_id": molde_id,
        "nome_molde": nome_molde,
        "detalhe_dxf_agrupado": True,
        "ordem_linha_auxiliar": ordem,
    })
    return {
        "tipo": "polyline",
        "pontos": pontos,
        "cor": str(origem.get("cor") or "#bfbfbf"),
        "origem_importador": "dxf",
        "origem": "dxf_matriz_graduada",
        "fechado": False,
        "molde": False,
        "molde_id": molde_id,
        "nome_molde": nome_molde,
        "molde_linha_vinculada": True,
        "selecionavel_individual": True,
        "subtipo_audaces": "linha_interna",
        "mostrar_controles": False,
        "metadados": metadados,
    }


def _agrupar_contornos_por_texto_central(fechados: list[dict], textos: list[dict]) -> dict[str, list[dict]]:
    por_nome: dict[str, list[dict]] = defaultdict(list)
    textos_validos = [
        texto
        for texto in textos
        if (
            str(texto.get("texto") or "").strip()
            and not _nome_marcado_reflexao_dxf(texto.get("texto"))
            and isinstance(texto.get("pos"), tuple)
        )
    ]
    for contorno in fechados:
        nome = _texto_central_do_contorno(contorno, textos_validos)
        if nome:
            por_nome[nome].append(contorno)
    return por_nome


def _texto_central_do_contorno(contorno: dict, textos: list[dict]) -> str | None:
    pontos = contorno.get("pontos") or []
    bbox = _bbox(pontos)
    if not bbox:
        return None
    cx, cy = _centro_bbox(bbox)
    largura = max(bbox[2] - bbox[0], 1e-9)
    altura = max(bbox[3] - bbox[1], 1e-9)
    candidatos = []
    for texto in textos:
        nome = str(texto.get("texto") or "").strip()
        pos = texto.get("pos")
        if not nome or _nome_marcado_reflexao_dxf(nome) or not isinstance(pos, tuple):
            continue
        dentro = _ponto_em_poligono(pos, pontos)
        if not dentro:
            continue
        px, py = pos
        dx = (px - cx) / largura
        dy = (py - cy) / altura
        candidatos.append(((dx * dx + dy * dy) ** 0.5, nome))
    if not candidatos:
        return None
    return min(candidatos, key=lambda item: item[0])[1]


def _cluster_principal_contornos_compativeis(contornos: list[dict]) -> list[dict]:
    clusters: list[list[dict]] = []
    for contorno in sorted(contornos, key=lambda el: _area_bbox(el)):
        bbox = _bbox(contorno.get("pontos") or [])
        if not bbox:
            continue
        destino = None
        for cluster in clusters:
            if _contornos_geometricamente_compativeis(cluster[0], contorno):
                destino = cluster
                break
        if destino is None:
            clusters.append([contorno])
        else:
            destino.append(contorno)
    if not clusters:
        return []
    return max(clusters, key=lambda cluster: (len(cluster), -_area_bbox(cluster[0])))


def _contornos_geometricamente_compativeis(a: dict, b: dict) -> bool:
    bbox_a = _bbox(a.get("pontos") or [])
    bbox_b = _bbox(b.get("pontos") or [])
    if not bbox_a or not bbox_b:
        return False
    wa = max(bbox_a[2] - bbox_a[0], 1e-9)
    ha = max(bbox_a[3] - bbox_a[1], 1e-9)
    wb = max(bbox_b[2] - bbox_b[0], 1e-9)
    hb = max(bbox_b[3] - bbox_b[1], 1e-9)
    area_a = wa * ha
    area_b = wb * hb
    area_ratio = max(area_a, area_b) / max(min(area_a, area_b), 1e-9)
    aspecto_a = max(wa / ha, ha / wa)
    aspecto_b = max(wb / hb, hb / wb)
    aspecto_ratio = max(aspecto_a, aspecto_b) / max(min(aspecto_a, aspecto_b), 1e-9)
    return area_ratio <= 3.2 and aspecto_ratio <= 1.35


def _alinhar_pontos_ao_base(
    pontos: list[tuple[float, float]],
    base_pontos: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    bbox_origem = _bbox(pontos)
    bbox_base = _bbox(base_pontos)
    if not pontos or not bbox_origem or not bbox_base:
        return pontos
    cx, cy = _centro_bbox(bbox_origem)
    bx, by = _centro_bbox(bbox_base)
    candidatos = []
    for transformacao in _transformacoes_orientacao():
        transformados = []
        for x, y in pontos:
            tx, ty = transformacao(x - cx, y - cy)
            transformados.append((tx + bx, ty + by))
        transformados = _reordenar_contorno_para_base(transformados, base_pontos)
        candidatos.append((_score_alinhamento_contornos(base_pontos, transformados), transformados))
    return min(candidatos, key=lambda item: item[0])[1]


def _reordenar_contorno_para_base(
    pontos: list[tuple[float, float]],
    base_pontos: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    pts = _sem_fecho_repetido([(float(x), float(y)) for x, y in pontos])
    base = _sem_fecho_repetido([(float(x), float(y)) for x, y in base_pontos])
    if len(pts) < 3 or len(base) < 3 or len(pts) != len(base):
        return pontos
    fechado = _dist(pontos[0], pontos[-1]) <= TOLERANCIA_CONEXAO if len(pontos) > 2 else False
    total = len(pts)
    melhor: tuple[float, list[tuple[float, float]]] | None = None
    for invertido in (False, True):
        origem = list(reversed(pts)) if invertido else pts
        for inicio in range(total):
            candidato = [origem[(inicio + idx) % total] for idx in range(total)]
            score = sum(_dist(a, b) for a, b in zip(base, candidato)) / float(total)
            if melhor is None or score < melhor[0]:
                melhor = (score, candidato)
    if melhor is None:
        return pontos
    reordenado = melhor[1]
    if fechado:
        reordenado = [*reordenado, reordenado[0]]
    return reordenado


def _transformacoes_orientacao():
    return [
        lambda x, y: (x, y),
        lambda x, y: (-x, -y),
        lambda x, y: (-x, y),
        lambda x, y: (x, -y),
        lambda x, y: (-y, x),
        lambda x, y: (y, -x),
    ]


def _score_alinhamento_contornos(base: list[tuple[float, float]], candidato: list[tuple[float, float]]) -> float:
    base_norm = _normalizar_pontos_para_score(base)
    cand_norm = _normalizar_pontos_para_score(candidato)
    if not base_norm or not cand_norm:
        return float("inf")
    return _distancia_media_mais_proxima(base_norm, cand_norm) + _distancia_media_mais_proxima(cand_norm, base_norm)


def _normalizar_pontos_para_score(pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    bbox = _bbox(pontos)
    if not bbox:
        return []
    cx, cy = _centro_bbox(bbox)
    escala = max(bbox[2] - bbox[0], bbox[3] - bbox[1], 1e-9)
    pts = [(float(x - cx) / escala, float(y - cy) / escala) for x, y in pontos]
    if len(pts) > 80:
        passo = max(1, len(pts) // 80)
        pts = pts[::passo]
    return pts


def _distancia_media_mais_proxima(origem: list[tuple[float, float]], destino: list[tuple[float, float]]) -> float:
    total = 0.0
    for x, y in origem:
        total += min((x - dx) ** 2 + (y - dy) ** 2 for dx, dy in destino)
    return total / max(len(origem), 1)


def _contorno_para_texto(pos: tuple[float, float], contornos: list[dict]) -> dict | None:
    contendo = [el for el in contornos if _ponto_em_poligono(pos, el.get("pontos") or [])]
    if contendo:
        return min(contendo, key=_area_bbox)
    px, py = pos
    candidatos = []
    for el in contornos:
        bbox = _bbox(el.get("pontos") or [])
        if not bbox:
            continue
        minx, miny, maxx, maxy = bbox
        w = max(maxx - minx, 1e-9)
        h = max(maxy - miny, 1e-9)
        margem = max(w, h) * 0.18
        if (minx - margem) <= px <= (maxx + margem) and (miny - margem) <= py <= (maxy + margem):
            cx, cy = _centro_bbox(bbox)
            candidatos.append((((px - cx) ** 2 + (py - cy) ** 2) ** 0.5, el))
    if candidatos:
        return min(candidatos, key=lambda item: item[0])[1]
    return None


def _deduplicar_contornos_por_dimensao(contornos: list[dict]) -> list[dict]:
    ordenados = sorted(contornos, key=lambda el: (_area_bbox(el), _centro_bbox(_bbox(el.get("pontos") or []))[0]))
    grupos: list[list[dict]] = []
    for el in ordenados:
        bbox = _bbox(el.get("pontos") or [])
        if not bbox:
            continue
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        destino = None
        for grupo in grupos:
            gb = _bbox(grupo[0].get("pontos") or [])
            if not gb:
                continue
            gw = gb[2] - gb[0]
            gh = gb[3] - gb[1]
            if abs(w - gw) <= max(0.25, max(w, gw) * 0.004) and abs(h - gh) <= max(0.25, max(h, gh) * 0.004):
                destino = grupo
                break
        if destino is None:
            grupos.append([el])
        else:
            destino.append(el)
    return [min(grupo, key=lambda el: _centro_bbox(_bbox(el.get("pontos") or []))[0]) for grupo in grupos]


def _deduplicar_contornos_matriz_dxf(contornos: list[dict]) -> tuple[list[dict], dict]:
    ordenados = sorted(contornos, key=lambda el: (_area_bbox(el), _centro_bbox(_bbox(el.get("pontos") or []))[0]))
    grupos: list[dict] = []
    for el in ordenados:
        bbox = _bbox(el.get("pontos") or [])
        if not bbox:
            continue
        w = float(bbox[2] - bbox[0])
        h = float(bbox[3] - bbox[1])
        perimetro = _perimetro_contorno_dxf(el.get("pontos") or [])
        destino = None
        for grupo in grupos:
            if (
                abs(w - grupo["w"]) <= max(0.25, max(abs(w), abs(grupo["w"])) * 0.004)
                and abs(h - grupo["h"]) <= max(0.25, max(abs(h), abs(grupo["h"])) * 0.004)
                and abs(perimetro - grupo["perimetro"]) <= max(0.35, max(abs(perimetro), abs(grupo["perimetro"])) * 0.004)
            ):
                destino = grupo
                break
        if destino is None:
            grupos.append({"w": w, "h": h, "perimetro": perimetro, "itens": [el]})
        else:
            destino["itens"].append(el)

    saida = [
        min(grupo["itens"], key=lambda el: _centro_bbox(_bbox(el.get("pontos") or []))[0])
        for grupo in grupos
        if grupo.get("itens")
    ]
    pares_ignorados = sum(max(0, len(grupo.get("itens") or []) - 1) for grupo in grupos)
    stats = {
        "par_detectado": pares_ignorados > 0,
        "pares_ignorados": int(pares_ignorados),
        "grupos_pares": sum(1 for grupo in grupos if len(grupo.get("itens") or []) > 1),
    }
    return saida, stats


def _perimetro_contorno_dxf(pontos) -> float:
    pts = _sem_fecho_repetido([(float(x), float(y)) for x, y in pontos or []])
    if len(pts) < 2:
        return 0.0
    return sum(_dist(a, b) for a, b in zip(pts, [*pts[1:], pts[0]]))


CORES_GRADE_DXF_PADRAO = [
    "#00e6d0",
    "#d7df00",
    "#0000ff",
    "#ffffff",
    "#169bd5",
    "#008000",
    "#8cff00",
    "#ff5a00",
    "#b000ff",
    "#ff00a8",
]


def _linhas_grade_para_quantidade(
    qtd: int,
    *,
    tamanho_base: str = "P",
    grade_tamanhos: list[dict] | None = None,
) -> list[dict]:
    labels = _labels_grade_para_quantidade(qtd, tamanho_base=tamanho_base, grade_tamanhos=grade_tamanhos)
    linhas_por_nome = {
        str(linha.get("tamanho") or "").strip().upper(): linha
        for linha in (grade_tamanhos or [])
        if isinstance(linha, dict) and str(linha.get("tamanho") or "").strip()
    }
    linhas = []
    for idx, label in enumerate(labels):
        cfg = linhas_por_nome.get(label.upper(), {})
        linhas.append({
            "tamanho": label,
            "ativo": bool(cfg.get("ativo", True)),
            "cor": str(cfg.get("cor") or CORES_GRADE_DXF_PADRAO[idx % len(CORES_GRADE_DXF_PADRAO)]),
        })
    return linhas


def _labels_grade_para_quantidade(
    qtd: int,
    *,
    tamanho_base: str = "P",
    grade_tamanhos: list[dict] | None = None,
) -> list[str]:
    if qtd <= 1:
        return [str(tamanho_base or "P").strip() or "P"]
    base = [
        str(linha.get("tamanho") or "").strip()
        for linha in (grade_tamanhos or [])
        if isinstance(linha, dict) and str(linha.get("tamanho") or "").strip()
    ] or ["PP", "P", "M", "G", "GG", "G1", "G2", "G3", "G4", "G5"]
    if grade_tamanhos:
        while qtd > len(base):
            base.append(f"T{len(base) + 1}")
        return base[:qtd]
    tamanho_base = str(tamanho_base or "P").strip().upper() or "P"
    while tamanho_base not in [label.upper() for label in base]:
        base.append(f"T{len(base) + 1}")
        if len(base) > 40:
            tamanho_base = "P"
            break
    while qtd > len(base):
        base.append(f"T{len(base) + 1}")
    if qtd >= len(base):
        return base[:qtd]
    idx = next((i for i, label in enumerate(base) if label.upper() == tamanho_base), 0)
    start = min(max(0, idx - 1), len(base) - qtd)
    return base[start:start + qtd]


def _ordem_visual_contornos(contornos: list[dict]) -> tuple[float, float]:
    bboxes = [_bbox(el.get("pontos") or []) for el in contornos]
    bboxes = [b for b in bboxes if b]
    if not bboxes:
        return (0.0, 0.0)
    return (min(b[1] for b in bboxes), min(b[0] for b in bboxes))


def _bbox(pontos: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    if not pontos:
        return None
    xs = [float(x) for x, _ in pontos]
    ys = [float(y) for _, y in pontos]
    return min(xs), min(ys), max(xs), max(ys)


def _area_bbox(el: dict) -> float:
    bbox = _bbox(el.get("pontos") or [])
    if not bbox:
        return 0.0
    return max(bbox[2] - bbox[0], 0.0) * max(bbox[3] - bbox[1], 0.0)


def _area_assinada_dxf(pontos: list[tuple[float, float]]) -> float:
    pts = [(float(x), float(y)) for x, y in (pontos or [])]
    if len(pts) < 3:
        return 0.0
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return sum((x1 * y2) - (x2 * y1) for (x1, y1), (x2, y2) in zip(pts, pts[1:])) / 2.0


def _centro_bbox(bbox: tuple[float, float, float, float] | None) -> tuple[float, float]:
    if not bbox:
        return (0.0, 0.0)
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _sem_fecho_repetido(pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in (pontos or [])]
    if len(pts) >= 2 and _dist(pts[0], pts[-1]) <= TOLERANCIA_CONEXAO:
        return pts[:-1]
    return pts


def _bbox_intersecta_expandido(
    base: tuple[float, float, float, float],
    outro: tuple[float, float, float, float],
    margem: float,
) -> bool:
    return not (
        outro[2] < base[0] - margem
        or outro[0] > base[2] + margem
        or outro[3] < base[1] - margem
        or outro[1] > base[3] + margem
    )


def _ponto_dentro_ou_na_borda(
    ponto: tuple[float, float],
    contorno: list[tuple[float, float]],
    tolerancia: float,
) -> bool:
    return _ponto_em_poligono(ponto, contorno) or _distancia_ponto_contorno(ponto, contorno) <= tolerancia


def _distancia_ponto_contorno(
    ponto: tuple[float, float],
    contorno: list[tuple[float, float]],
) -> float:
    pts = _sem_fecho_repetido(contorno)
    if len(pts) < 2:
        return float("inf")
    fechado = [*pts, pts[0]]
    return min(_distancia_ponto_segmento(ponto, a, b) for a, b in zip(fechado, fechado[1:]))


def _distancia_ponto_segmento(
    ponto: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    px, py = float(ponto[0]), float(ponto[1])
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    vx = bx - ax
    vy = by - ay
    denom = (vx * vx) + (vy * vy)
    if denom <= 1e-12:
        return hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (((px - ax) * vx) + ((py - ay) * vy)) / denom))
    cx = ax + (t * vx)
    cy = ay + (t * vy)
    return hypot(px - cx, py - cy)


def _ponto_em_poligono(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    if len(poly) < 3:
        return False
    x, y = pt
    inside = False
    pts = list(poly)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1
            if x < xin:
                inside = not inside
    return inside


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
