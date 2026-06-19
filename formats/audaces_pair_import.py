from __future__ import annotations

import base64
import json
from math import atan2, degrees
from statistics import median
from pathlib import Path

from core.projeto import Documento, Molde, Parte, Ponto, Projeto
from formats.audaces_emf_import import AudacesEMFImport, emf_doc_para_dict
from formats.audaces_xml_import import AudacesXMLImport, xml_doc_para_dict


class AudacesPairImport:
    # Calibração manual temporária medida no teste real ATUAL.
    # A versão anterior ficou grande demais:
    #   referência 1: Audaces 400.17 mm / GUIMMA 544.28 mm = 0.7352281914
    #   referência 2: Audaces 407.25 mm / GUIMMA 549.57 mm = 0.7410338992
    #   correção média = 0.7381310453
    #
    # Fator anterior fino: 19.2020894467
    # Fator final corrigido: 19.2020894467 * 0.7381310453 = 14.1736583552598
    ESCALA_CALIBRACAO_PADRAO = 14.1736583552598
    # EMF sem XML vem com outra relacao de escala neste export do Audaces. O
    # fator abaixo mantém a calibracao separada do par EMF+XML e inclui as
    # conferencias visuais mais recentes: 41.7 -> 43 cm e 16.41 -> 17.22 cm.
    ESCALA_CALIBRACAO_EMF_DIRETO = 8.782369373988214

    @staticmethod
    def _dimensoes_elemento(elemento) -> tuple[float, float, float, float]:
        if not getattr(elemento, "pontos", None):
            return 0.0, 0.0, 0.0, 0.0
        xs = [float(x) for x, _ in elemento.pontos]
        ys = [float(y) for _, y in elemento.pontos]
        largura = max(xs) - min(xs)
        altura = max(ys) - min(ys)
        perimetro = AudacesEMFImport._comprimento_polyline(elemento.pontos)
        area = abs(AudacesEMFImport._area_assinada(elemento.pontos))
        return largura, altura, perimetro, area

    @staticmethod
    def _bbox_pontos(pontos: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
        if not pontos:
            return None
        xs = [float(x) for x, _ in pontos]
        ys = [float(y) for _, y in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    @classmethod
    def _bbox_emf_doc(cls, emf_doc) -> tuple[float, float, float, float] | None:
        pontos: list[tuple[float, float]] = []
        for el in getattr(emf_doc, "elementos", []) or []:
            pontos.extend((float(x), float(y)) for x, y in getattr(el, "pontos", []) or [])
        for tx in getattr(emf_doc, "textos", []) or []:
            pos = tx.get("pos") if isinstance(tx, dict) else None
            if isinstance(pos, (tuple, list)) and len(pos) == 2:
                pontos.append((float(pos[0]), float(pos[1])))
        return cls._bbox_pontos(pontos)

    @classmethod
    def _transladar_emf_doc(cls, emf_doc, dx: float, dy: float) -> None:
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return
        for el in getattr(emf_doc, "elementos", []) or []:
            el.pontos = [(float(x) + dx, float(y) + dy) for x, y in getattr(el, "pontos", []) or []]
            el.bbox = AudacesEMFImport._bbox(el.pontos)
            el.metadados["deslocamento_importacao"] = (dx, dy)
        for tx in getattr(emf_doc, "textos", []) or []:
            pos = tx.get("pos") if isinstance(tx, dict) else None
            if isinstance(pos, (tuple, list)) and len(pos) == 2:
                tx["pos"] = (float(pos[0]) + dx, float(pos[1]) + dy)
        bbox = cls._bbox_emf_doc(emf_doc)
        if bbox:
            emf_doc.bounds = bbox
            emf_doc.largura = max(bbox[2] - bbox[0], 0.0)
            emf_doc.altura = max(bbox[3] - bbox[1], 0.0)

    @classmethod
    def _centralizar_emf_doc_no_zero(cls, emf_doc) -> dict:
        bbox = cls._bbox_emf_doc(emf_doc)
        if not bbox:
            return {"aplicado": False, "dx": 0.0, "dy": 0.0, "bbox_original": None}
        minx, miny, maxx, maxy = bbox
        dx = -((minx + maxx) / 2.0)
        dy = -((miny + maxy) / 2.0)
        cls._transladar_emf_doc(emf_doc, dx, dy)
        return {
            "aplicado": True,
            "dx": dx,
            "dy": dy,
            "bbox_original": bbox,
            "bbox_final": cls._bbox_emf_doc(emf_doc),
        }

    @classmethod
    def _centralizar_elementos_canvas_no_zero(cls, elementos_canvas: list[dict], doc: Documento | None = None) -> dict:
        pontos: list[tuple[float, float]] = []
        for el in elementos_canvas or []:
            if not isinstance(el, dict):
                continue
            pontos.extend((float(x), float(y)) for x, y in el.get("pontos", []) or [])
            pos = el.get("pos")
            if isinstance(pos, (tuple, list)) and len(pos) == 2:
                pontos.append((float(pos[0]), float(pos[1])))
            for item in el.get("graduacao_contornos_importados", []) or []:
                if isinstance(item, dict):
                    pontos.extend((float(x), float(y)) for x, y in item.get("pontos", []) or [])
        bbox = cls._bbox_pontos(pontos)
        if not bbox:
            return {"aplicado": False, "dx": 0.0, "dy": 0.0, "bbox_original": None}
        minx, miny, maxx, maxy = bbox
        dx = -((minx + maxx) / 2.0)
        dy = -((miny + maxy) / 2.0)
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return {"aplicado": False, "dx": 0.0, "dy": 0.0, "bbox_original": bbox, "bbox_final": bbox}

        def mover_ponto(valor):
            if isinstance(valor, (tuple, list)) and len(valor) >= 2:
                return (float(valor[0]) + dx, float(valor[1]) + dy)
            return valor

        for el in elementos_canvas or []:
            if not isinstance(el, dict):
                continue
            if el.get("pontos"):
                el["pontos"] = [mover_ponto(pt) for pt in el.get("pontos", [])]
            for chave in ("pos", "fio_origem", "fio_fim", "ponto_texto"):
                if chave in el:
                    el[chave] = mover_ponto(el.get(chave))
            for item in el.get("graduacao_contornos_importados", []) or []:
                if isinstance(item, dict) and item.get("pontos"):
                    item["pontos"] = [mover_ponto(pt) for pt in item.get("pontos", [])]

        if doc is not None:
            for molde in getattr(doc, "moldes", []) or []:
                for parte in getattr(molde, "partes", []) or []:
                    for ponto in getattr(parte, "pontos", []) or []:
                        ponto.x = float(ponto.x) + dx
                        ponto.y = float(ponto.y) + dy

        return {
            "aplicado": True,
            "dx": dx,
            "dy": dy,
            "bbox_original": bbox,
            "bbox_final": (
                bbox[0] + dx,
                bbox[1] + dy,
                bbox[2] + dx,
                bbox[3] + dy,
            ),
        }

    @staticmethod
    def _assinatura_elemento(elemento) -> tuple | None:
        pontos = getattr(elemento, "pontos", None)
        if pontos is None and isinstance(elemento, dict):
            pontos = elemento.get("pontos")
        if not pontos:
            return None
        pts = [(float(x), float(y)) for x, y in pontos]
        bbox = AudacesEMFImport._bbox(pts)
        if not bbox:
            return None
        area = abs(AudacesEMFImport._area_assinada(pts))
        return (
            round(bbox[0], 3),
            round(bbox[1], 3),
            round(bbox[2], 3),
            round(bbox[3], 3),
            round(area, 3),
        )

    @staticmethod
    def _rgb_hex(cor: str | None) -> tuple[int, int, int] | None:
        texto = str(cor or "").strip()
        if texto.startswith("#"):
            texto = texto[1:]
        if len(texto) != 6:
            return None
        try:
            return int(texto[0:2], 16), int(texto[2:4], 16), int(texto[4:6], 16)
        except ValueError:
            return None

    @staticmethod
    def _dist_rgb(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5

    @classmethod
    def _cor_proxima(cls, cor: str | None, alvo: tuple[int, int, int], tolerancia: float = 90.0) -> bool:
        rgb = cls._rgb_hex(cor)
        return bool(rgb and cls._dist_rgb(rgb, alvo) <= tolerancia)

    @classmethod
    def _tamanho_audaces_por_cor(cls, cor: str, tem_amarelo: bool) -> tuple[str, int] | None:
        """Mapeia cores usuais de grade do Audaces para nomes de tamanho.

        Alguns EMFs exportados sem XML nao carregam a linha amarela da grade.
        Nesses casos a sequencia vem deslocada e o verde passa a representar o
        tamanho base P, nao PP.
        """
        referencias = [
            ("verde", (0, 208, 0)),
            ("amarelo", (255, 255, 0)),
            ("azul", (0, 128, 255)),
            ("branco", (255, 255, 255)),
            ("magenta", (255, 0, 255)),
            ("laranja", (255, 128, 0)),
            ("roxo", (170, 0, 255)),
        ]
        rgb = cls._rgb_hex(cor)
        if not rgb:
            return None
        nome_cor, distancia = min(
            ((nome, cls._dist_rgb(rgb, ref)) for nome, ref in referencias),
            key=lambda item: item[1],
        )
        if distancia > 95.0:
            return None
        if nome_cor == "verde":
            return ("PP", 0) if tem_amarelo else ("P", 1)
        if nome_cor == "amarelo":
            return "P", 1
        if nome_cor == "azul":
            return "M", 2
        if nome_cor == "branco":
            return "G", 3
        if nome_cor == "magenta":
            return "GG", 4
        if nome_cor == "laranja":
            return "EXG", 5
        if nome_cor == "roxo":
            return "G2", 6
        return None

    @classmethod
    def _grade_detectada_por_cores(cls, elementos) -> tuple[str, list[dict], str | None] | None:
        cores: list[str] = []
        for el in elementos or []:
            subtipo = str(getattr(el, "metadados", {}).get("subtipo_audaces") or "")
            if subtipo not in {"contorno", "costura"}:
                continue
            cor = str(getattr(el, "cor", "") or "").strip().lower()
            if not cor or cor == "#ff7b00":
                continue
            if cor not in cores:
                cores.append(cor)
        if len(cores) < 2:
            return None

        tem_amarelo = any(cls._cor_proxima(cor, (255, 255, 0), tolerancia=95.0) for cor in cores)
        conhecidas: list[tuple[int, str, str]] = []
        desconhecidas: list[tuple[int, str, str]] = []
        labels_usados: set[str] = set()
        for idx, cor in enumerate(cores):
            info = cls._tamanho_audaces_por_cor(cor, tem_amarelo)
            if info:
                label, ordem = info
                if label not in labels_usados:
                    conhecidas.append((ordem, label, cor))
                    labels_usados.add(label)
                    continue
            desconhecidas.append((100 + idx, f"T{len(desconhecidas) + 1}", cor))
        ordenadas = sorted(conhecidas + desconhecidas, key=lambda item: (item[0], item[1]))
        if len(ordenadas) < 2:
            return None

        labels = [label for _ordem, label, _cor in ordenadas]
        if "P" in labels:
            base = "P"
        elif "G" in labels:
            base = "G"
        else:
            base = labels[len(labels) // 2]

        linhas: list[dict] = []
        for _ordem, label, cor in ordenadas:
            linhas.append({"ativo": True, "tamanho": label, "cor": cor, "base": label == base})
        grade_nome = f"{labels[0]}-{labels[-1]}({base})" if base else f"{labels[0]}-{labels[-1]}"
        return grade_nome, linhas, base

    @staticmethod
    def _nome_texto_contido(contorno, textos: list[dict], fallback: str) -> str:
        candidatos: list[tuple[int, str]] = []
        for tx in textos or []:
            texto = " ".join(str(tx.get("texto") or "").strip().split())
            if len(texto) < 2:
                continue
            pos = tx.get("pos")
            if not isinstance(pos, (tuple, list)) or len(pos) != 2:
                continue
            if AudacesEMFImport._ponto_em_poligono((float(pos[0]), float(pos[1])), contorno.pontos):
                limpo = texto.replace("\x00", "").strip()
                if limpo and "quantidade" not in limpo.lower():
                    candidatos.append((len(limpo), limpo[:60]))
        if candidatos:
            return max(candidatos, key=lambda item: item[0])[1]
        return fallback

    @classmethod
    def _detectar_fio_do_contorno(cls, contorno, elementos) -> tuple[tuple[float, float], tuple[float, float]] | None:
        bbox = cls._bbox_pontos([(float(x), float(y)) for x, y in contorno.pontos])
        if not bbox:
            return None
        minx, miny, maxx, maxy = bbox
        cx = (minx + maxx) / 2.0
        cy = (miny + maxy) / 2.0
        diagonal = max(((maxx - minx) ** 2 + (maxy - miny) ** 2) ** 0.5, 1.0)
        candidatos: list[tuple[float, tuple[tuple[float, float], tuple[float, float]]]] = []
        for extra in elementos or []:
            if extra is contorno or getattr(extra, "fechado", False):
                continue
            subtipo = str(getattr(extra, "metadados", {}).get("subtipo_audaces") or "")
            if subtipo in {"texto", "anotacao", "pique"}:
                continue
            pontos = [(float(x), float(y)) for x, y in getattr(extra, "pontos", []) or []]
            if len(pontos) < 2:
                continue
            p0, p1 = pontos[0], pontos[-1]
            direto = AudacesEMFImport._dist(p0, p1)
            if direto < max(1.2, diagonal * 0.15):
                continue
            total = AudacesEMFImport._comprimento_polyline(pontos)
            if direto <= 1e-9:
                continue
            meio = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
            dentro_meio = AudacesEMFImport._ponto_em_poligono(meio, contorno.pontos)
            dentro_inicio = AudacesEMFImport._ponto_em_poligono(p0, contorno.pontos)
            dentro_fim = AudacesEMFImport._ponto_em_poligono(p1, contorno.pontos)
            if not (dentro_meio or (dentro_inicio and dentro_fim)):
                continue
            ebbox = cls._bbox_pontos(pontos)
            if not ebbox:
                continue
            ew = max(ebbox[2] - ebbox[0], 1e-9)
            eh = max(ebbox[3] - ebbox[1], 1e-9)
            eixo_dominante = max(ew, eh) / max(min(ew, eh), 1e-9)
            # O EMF do Audaces pode fundir haste, seta e texto em uma mesma
            # polyline; por isso aceitamos uma caixa fina mesmo quando o
            # comprimento acumulado fica maior que a distancia ponta-a-ponta.
            if total / direto > 1.2 and eixo_dominante < 3.0:
                continue
            distancia_centro = AudacesEMFImport._dist(meio, (cx, cy))
            score = direto + (eixo_dominante * 0.25) - (distancia_centro * 0.25)
            candidatos.append((score, (p0, p1)))
        if not candidatos:
            return None
        return max(candidatos, key=lambda item: item[0])[1]

    @staticmethod
    def _area_bbox(bbox: tuple[float, float, float, float]) -> float:
        return max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))

    @classmethod
    def _sobreposicao_bbox_menor(cls, a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
        ix1 = max(float(a[0]), float(b[0]))
        iy1 = max(float(a[1]), float(b[1]))
        ix2 = min(float(a[2]), float(b[2]))
        iy2 = min(float(a[3]), float(b[3]))
        inter = cls._area_bbox((ix1, iy1, ix2, iy2))
        menor = min(cls._area_bbox(a), cls._area_bbox(b))
        if menor <= 1e-9:
            return 0.0
        return inter / menor

    @staticmethod
    def _centro_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
        return (float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0

    @staticmethod
    def _diagonal_bbox(bbox: tuple[float, float, float, float]) -> float:
        return max(
            ((float(bbox[2]) - float(bbox[0])) ** 2 + (float(bbox[3]) - float(bbox[1])) ** 2) ** 0.5,
            1e-9,
        )

    @classmethod
    def _bboxes_mesma_familia(cls, a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
        if cls._sobreposicao_bbox_menor(a, b) >= 0.48:
            return True
        ca = cls._centro_bbox(a)
        cb = cls._centro_bbox(b)
        dist = AudacesEMFImport._dist(ca, cb)
        diag = max(cls._diagonal_bbox(a), cls._diagonal_bbox(b))
        aw, ah = max(float(a[2]) - float(a[0]), 1e-9), max(float(a[3]) - float(a[1]), 1e-9)
        bw, bh = max(float(b[2]) - float(b[0]), 1e-9), max(float(b[3]) - float(b[1]), 1e-9)
        proporcao_ok = 0.38 <= aw / bw <= 2.65 and 0.38 <= ah / bh <= 2.65
        return proporcao_ok and dist <= diag * 0.28

    @staticmethod
    def _mapa_grade_por_cor(grade_detectada: tuple[str, list[dict], str | None] | None) -> dict[str, dict]:
        if not grade_detectada:
            return {}
        _grade_nome, linhas, _base = grade_detectada
        mapa: dict[str, dict] = {}
        for idx, linha in enumerate(linhas or []):
            cor = str(linha.get("cor") or "").strip().lower()
            if not cor:
                continue
            mapa[cor] = {**dict(linha), "_ordem": idx}
        return mapa

    @classmethod
    def _agrupar_contornos_graduados_emf(
        cls,
        elementos,
        grade_detectada: tuple[str, list[dict], str | None] | None,
    ) -> list[dict]:
        mapa_cores = cls._mapa_grade_por_cor(grade_detectada)
        fechados = []
        for el in elementos or []:
            if not getattr(el, "fechado", False) or len(getattr(el, "pontos", []) or []) < 4:
                continue
            subtipo = str(getattr(el, "metadados", {}).get("subtipo_audaces") or "")
            if subtipo not in {"contorno", "costura"}:
                continue
            area = abs(AudacesEMFImport._area_assinada(el.pontos))
            if area < 10.0:
                continue
            bbox = cls._bbox_pontos([(float(x), float(y)) for x, y in el.pontos])
            if not bbox:
                continue
            fechados.append({"el": el, "bbox": bbox, "area": area, "cor": str(el.cor or "").strip().lower()})

        grupos: list[dict] = []
        for item in sorted(fechados, key=lambda it: (-it["area"], it["bbox"][1], it["bbox"][0])):
            destino = None
            for grupo in grupos:
                if any(cls._bboxes_mesma_familia(item["bbox"], membro["bbox"]) for membro in grupo["membros"]):
                    destino = grupo
                    break
            if destino is None:
                destino = {"membros": [], "bbox": item["bbox"]}
                grupos.append(destino)
            destino["membros"].append(item)

        saida: list[dict] = []
        for grupo in grupos:
            membros = grupo["membros"]
            if not membros:
                continue
            base_item = None
            for item in membros:
                linha = mapa_cores.get(item["cor"])
                if linha and linha.get("base"):
                    base_item = item
                    break
            if base_item is None:
                ordenados_area = sorted(membros, key=lambda it: it["area"])
                base_item = ordenados_area[len(ordenados_area) // 2]

            contornos = []
            for item in sorted(membros, key=lambda it: int(mapa_cores.get(it["cor"], {}).get("_ordem", 999))):
                linha = mapa_cores.get(item["cor"], {})
                nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
                if not nome:
                    nome = f"T{len(contornos) + 1}"
                pontos = [(float(x), float(y)) for x, y in item["el"].pontos]
                if pontos and pontos[0] != pontos[-1]:
                    pontos.append(pontos[0])
                contornos.append({
                    "tamanho": nome,
                    "cor": item["el"].cor or linha.get("cor") or "#ffcc00",
                    "base": item is base_item,
                    "pontos": pontos,
                    "assinatura": cls._assinatura_elemento(item["el"]),
                })
            base_item["el"].metadados["subtipo_audaces"] = "contorno"
            for item in membros:
                if item is not base_item:
                    item["el"].metadados["subtipo_audaces"] = "graduacao_importada"
            saida.append({
                "base": base_item["el"],
                "assinatura_base": cls._assinatura_elemento(base_item["el"]),
                "assinaturas_membros": {
                    assinatura
                    for assinatura in (cls._assinatura_elemento(item["el"]) for item in membros)
                    if assinatura
                },
                "contornos": contornos,
                "quantidade_tamanhos": len(contornos),
            })
        return saida

    @classmethod
    def _aplicar_metadados_moldes_emf(
        cls,
        elementos_canvas: list[dict],
        contornos,
        emf_doc,
        nome_arquivo: str,
        grade_detectada: tuple[str, list[dict], str | None] | None,
        grupos_graduados: list[dict] | None = None,
    ) -> dict:
        grupos_por_base = {
            grupo.get("assinatura_base"): grupo
            for grupo in (grupos_graduados or [])
            if grupo.get("assinatura_base")
        }
        mapa: dict[tuple, dict] = {}
        for idx, contorno in enumerate(contornos, start=1):
            assinatura = cls._assinatura_elemento(contorno)
            if not assinatura:
                continue
            nome_base = f"K{idx}"
            nome_detectado = cls._nome_texto_contido(contorno, getattr(emf_doc, "textos", []), nome_base)
            fio = cls._detectar_fio_do_contorno(contorno, getattr(emf_doc, "elementos", []))
            bbox = cls._bbox_pontos([(float(x), float(y)) for x, y in contorno.pontos])
            ponto_texto = None
            if bbox:
                ponto_texto = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
            mapa[assinatura] = {
                "nome": nome_detectado,
                "nome_origem_texto": nome_detectado != nome_base,
                "molde_id": f"emf-{idx:03d}",
                "fio": fio,
                "ponto_texto": ponto_texto,
                "grupo": grupos_por_base.get(assinatura),
            }

        aplicados = 0
        fios = 0
        grupos_aplicados = 0
        for el in elementos_canvas:
            if not isinstance(el, dict):
                continue
            if el.get("origem") == "audaces_emf":
                el["render_smooth"] = bool(
                    el.get("molde")
                    or str(el.get("subtipo_audaces") or "").strip() in {"contorno", "costura"}
                )
            if not el.get("molde"):
                continue
            meta = mapa.get(cls._assinatura_elemento(el))
            if not meta:
                continue
            el["nome_molde"] = meta["nome"]
            el["molde_id"] = meta["molde_id"]
            el["mostrar_nome"] = bool(meta.get("nome_origem_texto"))
            if meta.get("ponto_texto"):
                el["ponto_texto"] = meta["ponto_texto"]
            if grade_detectada:
                grade_nome, linhas, base = grade_detectada
                el["graduacao_grade_nome"] = grade_nome
                el["graduacao_tamanhos"] = [dict(linha) for linha in linhas]
                el["graduacao_tamanhos_ativos"] = [
                    str(linha.get("tamanho") or "")
                    for linha in linhas
                    if linha.get("ativo", True)
                ]
                el["tamanho_base_detectado"] = base
            grupo = meta.get("grupo")
            if isinstance(grupo, dict) and grupo.get("contornos"):
                el["graduacao_contornos_importados"] = [
                    {
                        "tamanho": item.get("tamanho"),
                        "cor": item.get("cor"),
                        "base": bool(item.get("base")),
                        "pontos": list(item.get("pontos") or []),
                    }
                    for item in grupo.get("contornos", [])
                ]
                el["mostrar_graduacao"] = True
                el["metadados"].setdefault("graduacao_importada_origem", "emf_contornos_coloridos")
                grupos_aplicados += 1
            fio = meta.get("fio")
            if fio:
                p0, p1 = fio
                el["fio_origem"] = p0
                el["fio_fim"] = p1
                el["fio_angulo"] = degrees(atan2(p1[1] - p0[1], p1[0] - p0[0]))
                el["mostrar_fio"] = True
                fios += 1
            el.setdefault("metadados", {})["nome_arquivo_origem"] = nome_arquivo
            aplicados += 1
        return {"moldes_nomeados": aplicados, "fios_detectados": fios, "grupos_graduados": grupos_aplicados}

    @staticmethod
    def _dimensoes_peca_xml(peca) -> dict | None:
        tamanhos = list(getattr(peca, "tamanhos", None) or [])
        tamanho = tamanhos[0] if tamanhos else None
        base = str(getattr(peca, "tamanho_base", "") or "").strip()
        if base:
            for item in tamanhos:
                if str(getattr(item, "tamanho", "") or "").strip() == base:
                    tamanho = item
                    break
        if tamanho is None:
            return None
        largura = float(tamanho.largura or 0.0)
        altura = float(tamanho.altura or 0.0)
        perimetro = float(tamanho.perimetro or 0.0)
        area = float(tamanho.area or 0.0)
        if largura <= 0 or altura <= 0:
            return None
        return {
            "nome": peca.nome,
            "largura": largura,
            "altura": altura,
            "perimetro": perimetro,
            "area": area,
        }

    @classmethod
    def _candidatos_fechados_validos(cls, elementos) -> list:
        fechados = [e for e in elementos if e.fechado and len(e.pontos) >= 4]
        if not fechados:
            return []
        areas = [cls._dimensoes_elemento(e)[3] for e in fechados]
        area_ref = max(areas) if areas else 0.0
        area_min = max(0.002, area_ref * 0.0008)
        return [e for e in fechados if cls._dimensoes_elemento(e)[3] >= area_min]

    @staticmethod
    def _erro_dimensional(cand_dims: tuple[float, float, float, float], xml_dims: dict, escala: float) -> float:
        cw, ch, cp, _ca = cand_dims
        xw = float(xml_dims.get("largura") or 0.0)
        xh = float(xml_dims.get("altura") or 0.0)
        xp = float(xml_dims.get("perimetro") or 0.0)
        if cw <= 0 or ch <= 0 or xw <= 0 or xh <= 0:
            return 999.0
        erro = abs((cw * escala) - xw) / xw
        erro += abs((ch * escala) - xh) / xh
        if cp > 0 and xp > 0:
            erro += 0.35 * abs((cp * escala) - xp) / xp
        return erro

    @classmethod
    def _parear_contornos_com_xml(cls, elementos, xml_doc, escala: float = 1.0) -> list[tuple[int, int, float]]:
        xml_dims = [cls._dimensoes_peca_xml(p) for p in getattr(xml_doc, "pecas", []) or []]
        xml_dims = [d for d in xml_dims if d is not None]
        if not xml_dims:
            return []
        candidatos = cls._candidatos_fechados_validos(elementos)
        if not candidatos:
            return []
        itens = []
        for idx_cand, cand in enumerate(candidatos):
            dims = cls._dimensoes_elemento(cand)
            for idx_xml, xdim in enumerate(xml_dims):
                erro = cls._erro_dimensional(dims, xdim, escala)
                if erro <= 0.75:
                    itens.append((erro, idx_cand, idx_xml))
        itens.sort(key=lambda item: item[0])
        usados_cand: set[int] = set()
        usados_xml: set[int] = set()
        pares: list[tuple[int, int, float]] = []
        for erro, idx_cand, idx_xml in itens:
            if idx_cand in usados_cand or idx_xml in usados_xml:
                continue
            usados_cand.add(idx_cand)
            usados_xml.add(idx_xml)
            pares.append((idx_cand, idx_xml, erro))
            if len(pares) >= min(len(candidatos), len(xml_dims)):
                break
        return pares

    @classmethod
    def _fator_escala_por_xml(cls, xml_doc, elementos_unidos) -> tuple[float, dict]:
        xml_dims = [cls._dimensoes_peca_xml(p) for p in getattr(xml_doc, "pecas", []) or []]
        xml_dims = [d for d in xml_dims if d is not None]
        candidatos = cls._candidatos_fechados_validos(elementos_unidos)
        if not xml_dims or not candidatos:
            return (cls.ESCALA_CALIBRACAO_PADRAO, cls.ESCALA_CALIBRACAO_PADRAO), {
                "metodo": "fallback_fixo",
                "motivo": "sem_dimensoes_xml_ou_contornos",
                "fator": cls.ESCALA_CALIBRACAO_PADRAO,
                "fator_x": cls.ESCALA_CALIBRACAO_PADRAO,
                "fator_y": cls.ESCALA_CALIBRACAO_PADRAO,
            }

        sementes: list[float] = []
        for cand in candidatos:
            cw, ch, cp, _ca = cls._dimensoes_elemento(cand)
            if cw <= 0 or ch <= 0:
                continue
            for xdim in xml_dims:
                rw = xdim["largura"] / cw
                rh = xdim["altura"] / ch
                if rw <= 0 or rh <= 0:
                    continue
                proporcao = max(rw, rh) / max(min(rw, rh), 1e-9)
                if proporcao <= 1.28:
                    valores = [rw, rh]
                    if cp > 0 and xdim.get("perimetro", 0.0) > 0:
                        valores.append(xdim["perimetro"] / cp)
                    sementes.append(float(median(valores)))

        if not sementes:
            return (cls.ESCALA_CALIBRACAO_PADRAO, cls.ESCALA_CALIBRACAO_PADRAO), {
                "metodo": "fallback_fixo",
                "motivo": "sem_pares_dimensionais_confiaveis",
                "fator": cls.ESCALA_CALIBRACAO_PADRAO,
                "fator_x": cls.ESCALA_CALIBRACAO_PADRAO,
                "fator_y": cls.ESCALA_CALIBRACAO_PADRAO,
            }

        melhor = None
        for fator in sementes:
            pares = cls._parear_contornos_com_xml(candidatos, xml_doc, escala=fator)
            if not pares:
                continue
            erro_total = sum(p[2] for p in pares)
            score = (len(pares), -erro_total)
            if melhor is None or score > melhor["score"]:
                melhor = {
                    "fator": float(fator),
                    "pares": pares,
                    "erro_total": float(erro_total),
                    "score": score,
                }

        if melhor is None:
            fator = float(median(sementes))
            pares = cls._parear_contornos_com_xml(candidatos, xml_doc, escala=fator)
            erro_total = sum(p[2] for p in pares)
        else:
            fator = melhor["fator"]
            pares = melhor["pares"]
            erro_total = melhor["erro_total"]

        ratios_x: list[float] = []
        ratios_y: list[float] = []
        pares_info = []
        for idx_cand, idx_xml, erro in pares:
            cand = candidatos[idx_cand]
            xdim = xml_dims[idx_xml]
            cw, ch, cp, ca = cls._dimensoes_elemento(cand)
            if erro <= 0.45 and cw > 0 and ch > 0:
                ratios_x.append(float(xdim["largura"]) / cw)
                ratios_y.append(float(xdim["altura"]) / ch)
            pares_info.append({
                "peca": xdim["nome"],
                "largura_xml_cm": xdim["largura"],
                "altura_xml_cm": xdim["altura"],
                "largura_vetor_cm": cw,
                "altura_vetor_cm": ch,
                "largura_importada_cm": cw * fator,
                "altura_importada_cm": ch * fator,
                "perimetro_vetor_cm": cp,
                "area_vetor_cm2": ca,
                "erro": erro,
            })
        fator_x = float(median(ratios_x)) if ratios_x else fator
        fator_y = float(median(ratios_y)) if ratios_y else fator
        fator_medio = (fator_x + fator_y) / 2.0
        return (fator_x, fator_y), {
            "metodo": "xml_dimensoes_auto",
            "fator": fator_medio,
            "fator_x": fator_x,
            "fator_y": fator_y,
            "pares_usados": pares_info,
            "pares": len(pares),
            "pecas_xml": len(xml_dims),
            "contornos_candidatos": len(candidatos),
            "erro_total": erro_total,
        }

    @staticmethod
    def _classificar_contornos_unidos(elementos, xml_doc=None):
        if xml_doc is not None and getattr(xml_doc, "pecas", None):
            return AudacesPairImport._classificar_contornos_por_dimensoes_xml(elementos, xml_doc)
        fechados = [e for e in elementos if e.fechado and len(e.pontos) >= 4]
        abertos = [e for e in elementos if not e.fechado and len(e.pontos) >= 2]
        if not fechados:
            return elementos, 0, 0, len(abertos), 0
        areas = []
        for e in fechados:
            area = abs(AudacesEMFImport._area_assinada(e.pontos))
            e.metadados["area_contorno"] = area
            areas.append(area)
        area_ref = max(areas) if areas else 0.0
        area_min = max(0.08, area_ref * 0.003)
        fechados_validos = [e for e in fechados if e.metadados.get("area_contorno", 0.0) >= area_min]
        ignorados = len(fechados) - len(fechados_validos)
        fechados_ordenados = sorted(fechados_validos, key=lambda e: e.metadados.get("area_contorno", 0.0), reverse=True)
        principais = []
        costuras = 0
        internas = 0
        alvo_xml = len(getattr(xml_doc, "pecas", []) or [])
        for e in fechados_ordenados:
            pt = e.pontos[0]
            dentro_de_principal = any(AudacesEMFImport._ponto_em_poligono(pt, p.pontos) for p in principais)
            if not dentro_de_principal and (alvo_xml <= 0 or len(principais) < alvo_xml):
                e.metadados["subtipo_audaces"] = "contorno"
                principais.append(e)
            elif dentro_de_principal:
                e.metadados["subtipo_audaces"] = "costura"
                costuras += 1
            else:
                e.metadados["subtipo_audaces"] = "linha_interna"
                internas += 1
        for e in abertos:
            e.metadados["subtipo_audaces"] = "linha_interna"
        return elementos, len(principais), costuras, internas + len(abertos), ignorados

    @classmethod
    def _classificar_contornos_por_dimensoes_xml(cls, elementos, xml_doc):
        candidatos = cls._candidatos_fechados_validos(elementos)
        abertos = [e for e in elementos if not e.fechado and len(e.pontos) >= 2]
        pares = cls._parear_contornos_com_xml(candidatos, xml_doc, escala=1.0)
        xml_pecas = list(getattr(xml_doc, "pecas", []) or [])
        principais = {id(candidatos[idx_cand]) for idx_cand, _idx_xml, _erro in pares}
        xml_por_contorno = {
            id(candidatos[idx_cand]): (idx_xml, xml_pecas[idx_xml] if idx_xml < len(xml_pecas) else None, erro)
            for idx_cand, idx_xml, erro in pares
        }
        if not principais:
            return cls._classificar_contornos_unidos(elementos, None)

        costuras = 0
        internas = 0
        ignorados = 0
        contornos_principais = [e for e in candidatos if id(e) in principais]
        for e in elementos:
            if not e.fechado:
                e.metadados["subtipo_audaces"] = "linha_interna"
                continue
            if id(e) in principais:
                e.metadados["subtipo_audaces"] = "contorno"
                idx_xml, peca_xml, erro = xml_por_contorno.get(id(e), (None, None, None))
                if idx_xml is not None:
                    e.metadados["xml_pattern_index"] = idx_xml
                if peca_xml is not None:
                    e.metadados["xml_pattern_name"] = getattr(peca_xml, "nome", "")
                if erro is not None:
                    e.metadados["xml_match_error"] = float(erro)
                continue
            area = cls._dimensoes_elemento(e)[3]
            if area < 0.002:
                e.metadados["subtipo_audaces"] = "linha_interna"
                ignorados += 1
                continue
            pt = e.pontos[0] if e.pontos else None
            dentro_de_principal = bool(
                pt is not None and any(AudacesEMFImport._ponto_em_poligono(pt, p.pontos) for p in contornos_principais)
            )
            if dentro_de_principal:
                e.metadados["subtipo_audaces"] = "costura"
                costuras += 1
            else:
                e.metadados["subtipo_audaces"] = "linha_interna"
                internas += 1
        for e in abertos:
            e.metadados["subtipo_audaces"] = "linha_interna"
        return elementos, len(contornos_principais), costuras, internas + len(abertos), ignorados

    @staticmethod
    def _converter_moldes_para_canvas(moldes: list[Molde]) -> list[dict]:
        elementos: list[dict] = []
        for molde in moldes:
            for parte in molde.partes:
                pts = [(p.x, p.y) for p in parte.pontos]
                if len(pts) < 2:
                    continue
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                base = pts[:-1]
                xs = [x for x, _ in base]
                ys = [y for _, y in base]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                largura = max(xs) - min(xs)
                altura = max(ys) - min(ys)
                margem = largura * 0.20
                y_fio = min(max(ys) - max(0.15, altura * 0.06), cy + max(0.25, altura * 0.08))
                elementos.append({
                    "tipo": "polyline",
                    "pontos": pts,
                    "origem": "audaces_emf_xml_molde_real",
                    "subtipo_audaces": "contorno",
                    "molde": True,
                    "molde_id": molde.id,
                    "nome_molde": molde.nome,
                    "fio_angulo": 0.0,
                    "fio_origem": (min(xs) + margem, y_fio),
                    "fio_fim": (max(xs) - margem, y_fio),
                    "ponto_texto": (cx, cy),
                    "mostrar_nome": True,
                    "mostrar_fio": True,
                    "metadados": {"origem": "audaces_emf_xml", "importado_como_molde_real": True, "subtipo_audaces": "contorno"},
                    "cor": "#ff7b00",
                    "bloqueado": False,
                })
        return elementos

    @classmethod
    def importar(cls, emf_path: str | Path, xml_path: str | Path, projeto: Projeto) -> Projeto:
        xml_doc = AudacesXMLImport.abrir(xml_path)
        emf_doc = AudacesEMFImport.abrir(emf_path)

        parser_pre_escala = AudacesEMFImport(b"", emf_path)
        unidos_pre_escala = parser_pre_escala._unir_segmentos_em_contornos(emf_doc.elementos)
        fatores_escala, diagnostico_escala = cls._fator_escala_por_xml(xml_doc, unidos_pre_escala)
        fator_escala_x, fator_escala_y = fatores_escala
        fator_escala_final = (float(fator_escala_x) + float(fator_escala_y)) / 2.0
        cls._aplicar_escala_emf_doc(emf_doc, fatores_escala)

        projeto.nome = xml_doc.nome_modelo or projeto.nome
        if not projeto.documentos:
            projeto.documentos.append(Documento(nome="Documento 1"))
        doc = projeto.documentos[0]
        doc.moldes = []

        parser_ops = AudacesEMFImport(b"", emf_path)
        antes = {
            "elementos_emf": len(emf_doc.elementos),
            "segmentos_soltos": sum(1 for e in emf_doc.elementos if not e.fechado),
            "contorno": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "contorno"),
            "costura": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "costura"),
            "linha_interna": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "linha_interna"),
        }
        unidos = parser_ops._unir_segmentos_em_contornos(emf_doc.elementos)
        unidos, total_contornos_principais, total_costuras, total_linhas_internas, total_ignorados = cls._classificar_contornos_unidos(unidos, xml_doc)
        reconstruidos: list = []
        for el in unidos:
            subtipo = str(el.metadados.get("subtipo_audaces") or "")
            if subtipo in {"contorno", "costura"} and len(el.pontos) >= 5:
                reconstruidos.append(parser_ops._reconstruir_curvas_do_contorno(el))
            else:
                reconstruidos.append(el)
        emf_doc.elementos = reconstruidos
        elementos_canvas = AudacesEMFImport(b"", emf_path).converter_para_elementos_guimma(emf_doc)
        depois = {
            "segmentos_unidos": parser_ops._join_stats.get("segmentos_unidos", 0),
            "contornos_fechados_encontrados": sum(1 for e in emf_doc.elementos if e.fechado),
            "contornos_classificados_como_contorno": total_contornos_principais,
            "contornos_classificados_como_costura": total_costuras,
            "contornos_classificados_como_linha_interna": total_linhas_internas,
            "contornos_ignorados": total_ignorados,
            "contornos_abertos_restantes": sum(1 for e in emf_doc.elementos if not e.fechado),
            "curvas_reconstruidas": parser_ops._join_stats.get("curvas_reconstruidas", 0),
            "motor_cpp_curvas": parser_ops._join_stats.get("motor_cpp_curvas", 0),
            "motor_cpp_falhas": parser_ops._join_stats.get("motor_cpp_falhas", 0),
            "elementos_canvas_final": len(elementos_canvas),
        }
        contornos = [el for el in emf_doc.elementos if el.fechado and len(el.pontos) >= 4 and el.metadados.get("subtipo_audaces") == "contorno"]
        contornos = sorted(
            contornos,
            key=lambda el: (
                int(el.metadados.get("xml_pattern_index", 10**9)),
                -abs(AudacesEMFImport._area_assinada(el.pontos)),
            ),
        )
        avisos: list[str] = []
        aplicados = 0
        total_assoc = min(len(contornos), len(xml_doc.pecas))

        for idx, contorno in enumerate(contornos):
            peca = xml_doc.pecas[idx] if idx < len(xml_doc.pecas) else None
            nome = peca.nome if peca else f"Molde EMF {idx + 1}"
            parte = Parte(
                nome=nome,
                pontos=[Ponto(x=float(x), y=float(y)) for x, y in contorno.pontos],
                marcacoes=["origem:audaces_emf_xml"],
            )
            parte.marcacoes.append("contorno")
            for extra in emf_doc.elementos:
                if extra is contorno:
                    continue
                subtipo = str(extra.metadados.get("subtipo_audaces") or "")
                if subtipo not in {"costura", "linha_interna", "fio", "pique"}:
                    continue
                if extra.pontos and contorno.pontos and AudacesEMFImport._ponto_em_poligono(extra.pontos[0], contorno.pontos):
                    parte.marcacoes.append(subtipo)
            molde = Molde(nome=nome, partes=[parte])
            doc.moldes.append(molde)
            aplicados += 1 if peca else 0
            if peca:
                tamanho = peca.tamanhos[0] if peca.tamanhos else None
                meta = {
                    "tecido": peca.tecido,
                    "quantidade": peca.quantidade,
                    "tamanho": tamanho.tamanho if tamanho else None,
                    "area": tamanho.area if tamanho else None,
                    "perimetro": tamanho.perimetro if tamanho else None,
                    "largura": tamanho.largura if tamanho else None,
                    "altura": tamanho.altura if tamanho else None,
                }
                parte.marcacoes.append(f"xml_meta:{json.dumps(meta, ensure_ascii=False)}")

        if len(contornos) != len(xml_doc.pecas):
            avisos.append("Alguns contornos EMF não puderam ser associados automaticamente às peças do XML.")

        projeto.preferencias_usuario["audaces_emf_xml_importacao"] = {
            "origem": "audaces_emf_xml",
            "emf_path": str(emf_path),
            "xml_path": str(xml_path),
            "vetores": len([el for el in elementos_canvas if el.get("tipo") == "polyline"]),
            "elementos_canvas_antes_uniao": antes["elementos_emf"],
            "moldes_detectados": len(contornos),
            "metadados_xml_aplicados": aplicados,
            "avisos": avisos,
            "elementos_canvas": elementos_canvas,
            "xml": xml_doc_para_dict(xml_doc),
            "emf": emf_doc_para_dict(emf_doc),
            "associacoes": total_assoc,
            "pecas_xml": len(xml_doc.pecas),
            "pecas_xml_sem_associacao": max(0, len(xml_doc.pecas) - total_assoc),
            "contornos_fechados": len(contornos),
            "moldes_reais": len(doc.moldes),
            "segmentos_originais_lidos_emf": parser_ops._join_stats.get("segmentos_originais", 0),
            "segmentos_unidos": parser_ops._join_stats.get("segmentos_unidos", 0),
            "curvas_reconstruidas": parser_ops._join_stats.get("curvas_reconstruidas", 0),
            "motor_cpp_curvas": parser_ops._join_stats.get("motor_cpp_curvas", 0),
            "motor_cpp_falhas": parser_ops._join_stats.get("motor_cpp_falhas", 0),
            "contornos_abertos_restantes": depois["contornos_abertos_restantes"],
            "bounds_emf": emf_doc.bounds,
            "escala": dict(emf_doc.relatorio.get("escala", {})),
            "escala_manual_aplicada": fator_escala_final,
            "escala_x_aplicada": fator_escala_x,
            "escala_y_aplicada": fator_escala_y,
            "diagnostico_escala": diagnostico_escala,
            "fator_escala_final": fator_escala_final,
            "unidade_resultado": "cm_calibrado_por_xml",
        }
        projeto.preferencias_usuario["audaces_emf_xml_importacao"]["diagnostico_antes"] = antes
        projeto.preferencias_usuario["audaces_emf_xml_importacao"]["diagnostico_depois"] = {
            **depois,
            "moldes_reais_criados": len(doc.moldes),
        }

        projeto.preferencias_usuario["audaces_importados_originais"] = {
            "emf": {
                "nome": Path(emf_path).name,
                "conteudo_base64": base64.b64encode(Path(emf_path).read_bytes()).decode("ascii"),
            },
            "xml": {
                "nome": Path(xml_path).name,
                "conteudo_base64": base64.b64encode(Path(xml_path).read_bytes()).decode("ascii"),
            },
        }
        if doc.moldes:
            elementos_moldes_canvas = cls._converter_moldes_para_canvas(doc.moldes)
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["elementos_canvas"] = elementos_moldes_canvas
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_origem"] = "moldes_reais"
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_moldes_renderizados"] = len(doc.moldes)
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_elementos_emf_renderizados"] = 0
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                f"Audaces EMF + XML importado: {len(doc.moldes)} moldes reais criados, "
                f"{parser_ops._join_stats.get('segmentos_unidos', 0)} contornos unidos, "
                f"{parser_ops._join_stats.get('curvas_reconstruidas', 0)} curvas reconstruídas."
            )
        else:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_origem"] = "elementos_emf"
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_moldes_renderizados"] = 0
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_elementos_emf_renderizados"] = len(elementos_canvas)
            if depois["contornos_fechados_encontrados"] > 0:
                projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                    "Foram encontrados contornos fechados, mas nenhum foi classificado como molde principal. Verifique regras de classificação."
                )
            else:
                projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                    "Nenhum contorno fechado confiável foi encontrado. O arquivo foi importado como linhas técnicas, mas não como moldes."
                )

        elementos_crus_ignorados = max(0, antes["elementos_emf"] - len(emf_doc.elementos))
        alterou_geometria = len(unidos) != len(emf_doc.elementos) or parser_ops._join_stats.get("curvas_reconstruidas", 0) > 0
        if not alterou_geometria:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_diagnostico"] = "Pós-processamento não alterou geometria."
        print(f"[AUDACES_IMPORT] usando elementos processados no canvas: SIM")
        print(f"[AUDACES_IMPORT] moldes reais criados: {len(doc.moldes)}")
        print(f"[AUDACES_IMPORT] moldes no projeto.documentos[0].moldes: {len(doc.moldes)}")
        print(f"[AUDACES_IMPORT] canvas renderizando moldes reais: {'SIM' if len(doc.moldes) > 0 else 'NAO'}")
        print(f"[AUDACES_IMPORT] canvas renderizando elementos EMF crus: {'NAO' if len(doc.moldes) > 0 else 'SIM'}")
        print(f"[AUDACES_IMPORT] contornos fechados encontrados: {depois['contornos_fechados_encontrados']}")
        print(f"[AUDACES_IMPORT] elementos crus ignorados: {elementos_crus_ignorados}")

        relatorio = cls._gerar_relatorio_importacao(xml_doc, emf_doc, projeto.preferencias_usuario["audaces_emf_xml_importacao"])
        report_path = cls._salvar_relatorio_debug(relatorio)
        projeto.preferencias_usuario["audaces_emf_xml_importacao"]["debug_report_path"] = str(report_path)

        if doc.moldes:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                f"Audaces EMF + XML importado: {len(doc.moldes)} moldes reais criados, "
                f"{parser_ops._join_stats.get('segmentos_unidos', 0)} contornos unidos, "
                f"{parser_ops._join_stats.get('curvas_reconstruidas', 0)} curvas reconstruídas."
            )
        else:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                "Nenhum contorno fechado confiável foi encontrado. O arquivo foi importado como linhas técnicas, mas não como moldes."
            )

        elementos_crus_ignorados = max(0, antes["elementos_emf"] - len(emf_doc.elementos))
        alterou_geometria = len(unidos) != len(emf_doc.elementos) or parser_ops._join_stats.get("curvas_reconstruidas", 0) > 0
        if not alterou_geometria:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_diagnostico"] = "Pós-processamento não alterou geometria."
        print(f"[AUDACES_IMPORT] usando elementos processados no canvas: SIM")
        print(f"[AUDACES_IMPORT] moldes reais criados: {len(doc.moldes)}")
        print(f"[AUDACES_IMPORT] contornos fechados encontrados: {depois['contornos_fechados_encontrados']}")
        print(f"[AUDACES_IMPORT] elementos crus ignorados: {elementos_crus_ignorados}")

        return projeto

    @classmethod
    def importar_apenas_emf(cls, emf_path: str | Path, projeto: Projeto) -> Projeto:
        emf_path = Path(emf_path)
        nome_arquivo = emf_path.stem or emf_path.name
        emf_doc = AudacesEMFImport.abrir(emf_path, reconstruir_curvas=False, suavizar_curvas=False)
        fator_escala_final = cls.ESCALA_CALIBRACAO_EMF_DIRETO
        cls._aplicar_escala_emf_doc(emf_doc, fator_escala_final)
        parser_ops = AudacesEMFImport(b"", emf_path)
        antes = {
            "elementos_emf": len(emf_doc.elementos),
            "segmentos_soltos": sum(1 for e in emf_doc.elementos if not e.fechado),
            "contorno": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "contorno"),
            "costura": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "costura"),
            "linha_interna": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "linha_interna"),
        }
        unidos = parser_ops._unir_segmentos_em_contornos(emf_doc.elementos)
        unidos, total_contornos_principais, total_costuras, total_linhas_internas, total_ignorados = (
            cls._classificar_contornos_unidos(unidos, None)
        )
        reconstruidos: list = []
        for el in unidos:
            subtipo = str(el.metadados.get("subtipo_audaces") or "")
            if subtipo in {"contorno", "costura"} and len(el.pontos) >= 5:
                reconstruidos.append(parser_ops._reconstruir_curvas_do_contorno(el))
            else:
                reconstruidos.append(el)
        unidos = reconstruidos
        emf_doc.elementos = unidos
        centralizacao = cls._centralizar_emf_doc_no_zero(emf_doc)
        grade_detectada = cls._grade_detectada_por_cores(emf_doc.elementos)
        grupos_graduados = cls._agrupar_contornos_graduados_emf(emf_doc.elementos, grade_detectada)
        assinaturas_graduacao_ocultas: set[tuple] = set()
        assinaturas_grupos: set[tuple] = set()
        for grupo in grupos_graduados:
            assinatura_base = grupo.get("assinatura_base")
            membros = {
                assinatura
                for assinatura in (grupo.get("assinaturas_membros") or set())
                if assinatura
            }
            assinaturas_grupos.update(membros)
            assinaturas_graduacao_ocultas.update(membros)
            if assinatura_base in assinaturas_graduacao_ocultas:
                assinaturas_graduacao_ocultas.remove(assinatura_base)
        elementos_canvas = AudacesEMFImport(b"", emf_path).converter_para_elementos_guimma(emf_doc)
        if assinaturas_graduacao_ocultas:
            elementos_canvas = [
                el
                for el in elementos_canvas
                if cls._assinatura_elemento(el) not in assinaturas_graduacao_ocultas
            ]
        if not projeto.documentos:
            projeto.documentos.append(Documento(nome=nome_arquivo))
        projeto.nome = nome_arquivo
        doc = projeto.documentos[0]
        doc.nome = nome_arquivo
        doc.moldes = []
        contornos = [grupo["base"] for grupo in grupos_graduados if grupo.get("base") is not None]
        contornos.extend(
            e
            for e in emf_doc.elementos
            if (
                e.fechado
                and len(e.pontos) >= 4
                and e.metadados.get("subtipo_audaces") == "contorno"
                and cls._assinatura_elemento(e) not in assinaturas_grupos
            )
        )
        contornos = sorted(
            contornos,
            key=lambda el: (
                min((p[1] for p in el.pontos), default=0.0),
                min((p[0] for p in el.pontos), default=0.0),
                -abs(AudacesEMFImport._area_assinada(el.pontos)),
            ),
        )
        for idx, el in enumerate(contornos, start=1):
            nome_molde = cls._nome_texto_contido(el, emf_doc.textos, f"K{idx}")
            parte = Parte(nome=nome_molde, pontos=[Ponto(x=float(x), y=float(y)) for x, y in el.pontos])
            parte.marcacoes.extend(["origem:audaces_emf", "contorno"])
            for extra in emf_doc.elementos:
                if extra is el:
                    continue
                subtipo = str(extra.metadados.get("subtipo_audaces") or "")
                if subtipo not in {"costura", "linha_interna", "fio", "pique"}:
                    continue
                if extra.pontos and el.pontos and AudacesEMFImport._ponto_em_poligono(extra.pontos[0], el.pontos):
                    parte.marcacoes.append(subtipo)
            if cls._detectar_fio_do_contorno(el, emf_doc.elementos):
                parte.marcacoes.append("fio")
            doc.moldes.append(Molde(nome=nome_molde, partes=[parte]))
        metadados_moldes = cls._aplicar_metadados_moldes_emf(
            elementos_canvas,
            contornos,
            emf_doc,
            nome_arquivo,
            grade_detectada,
            grupos_graduados,
        )
        centralizacao_canvas = cls._centralizar_elementos_canvas_no_zero(elementos_canvas, doc)
        depois = {
            "segmentos_unidos": parser_ops._join_stats.get("segmentos_unidos", 0),
            "contornos_fechados_encontrados": sum(1 for e in emf_doc.elementos if e.fechado),
            "contornos_classificados_como_contorno": total_contornos_principais,
            "contornos_classificados_como_costura": total_costuras,
            "contornos_classificados_como_linha_interna": total_linhas_internas,
            "contornos_ignorados": total_ignorados,
            "contornos_abertos_restantes": sum(1 for e in emf_doc.elementos if not e.fechado),
            "curvas_reconstruidas": parser_ops._join_stats.get("curvas_reconstruidas", 0),
            "motor_cpp_curvas": parser_ops._join_stats.get("motor_cpp_curvas", 0),
            "motor_cpp_falhas": parser_ops._join_stats.get("motor_cpp_falhas", 0),
            "elementos_canvas_final": len(elementos_canvas),
            "contornos_graduacao_ocultos": len(assinaturas_graduacao_ocultas),
            "grupos_graduados_detectados": len(grupos_graduados),
            **metadados_moldes,
        }

        projeto.preferencias_usuario["audaces_emf_importacao"] = {
            "origem": "audaces_emf",
            "emf_path": str(emf_path),
            "nome_arquivo": nome_arquivo,
            "elementos_canvas": elementos_canvas,
            "relatorio": dict(emf_doc.relatorio),
            "vetores": len([el for el in elementos_canvas if el.get("tipo") == "polyline"]),
            "elementos_canvas_antes_uniao": antes["elementos_emf"],
            "moldes_detectados": len(contornos),
            "contornos_fechados": len(contornos),
            "moldes_reais": len(doc.moldes),
            "segmentos_originais_lidos_emf": parser_ops._join_stats.get("segmentos_originais", 0),
            "segmentos_unidos": parser_ops._join_stats.get("segmentos_unidos", 0),
            "curvas_reconstruidas": parser_ops._join_stats.get("curvas_reconstruidas", 0),
            "motor_cpp_curvas": parser_ops._join_stats.get("motor_cpp_curvas", 0),
            "motor_cpp_falhas": parser_ops._join_stats.get("motor_cpp_falhas", 0),
            "contornos_abertos_restantes": depois["contornos_abertos_restantes"],
            "centralizacao_importacao": {
                **centralizacao,
                "canvas_visivel": centralizacao_canvas,
            },
            "diagnostico_antes": antes,
            "diagnostico_depois": {
                **depois,
                "moldes_reais_criados": len(doc.moldes),
            },
            "escala_manual_aplicada": fator_escala_final,
            "medidas_calibracao": [
                {"audaces_cm": 40.0, "guimma_cm_anterior": 65.54},
                {"audaces_cm": 16.0, "guimma_cm_anterior": 27.54},
                {"audaces_cm": 43.0, "guimma_cm_anterior": 41.7},
                {"audaces_cm": 17.22, "guimma_cm_anterior": 16.41},
            ],
            "grade_detectada": {
                "nome": grade_detectada[0],
                "tamanho_base": grade_detectada[2],
                "quantidade_tamanhos": len(grade_detectada[1]),
            } if grade_detectada else None,
            "fios_detectados": metadados_moldes.get("fios_detectados", 0),
            "textos_emf_detectados": len(getattr(emf_doc, "textos", []) or []),
            "nomes_moldes_origem": (
                "texto_emf_decodificado"
                if any(str(tx.get("texto") or "").strip() for tx in getattr(emf_doc, "textos", []) or [])
                else "indice_temporario_sem_strings_texto_no_emf"
            ),
            "fator_escala_final": fator_escala_final,
            "unidade_resultado": "cm_calibrado_por_referencia_emf_direto",
            "canvas_origem": "moldes_reais_processados" if doc.moldes else "elementos_emf",
            "canvas_moldes_renderizados": len(doc.moldes),
            "canvas_elementos_emf_renderizados": len(elementos_canvas),
            "mensagem_final": (
                f"EMF importado: {len(doc.moldes)} moldes reais detectados, "
                f"{parser_ops._join_stats.get('segmentos_unidos', 0)} segmentos unidos, "
                f"{metadados_moldes.get('fios_detectados', 0)} fios detectados."
                if doc.moldes
                else "Nenhum contorno fechado confiavel foi encontrado. O EMF foi importado como linhas tecnicas."
            ),
        }
        projeto.preferencias_usuario.setdefault("audaces_importados_originais", {})["emf"] = {
            "nome": Path(emf_path).name,
            "conteudo_base64": base64.b64encode(Path(emf_path).read_bytes()).decode("ascii"),
        }
        return projeto


    @classmethod
    def _fator_escala_calibrado(cls, xml_doc, emf_doc) -> float:
        """Retorna o fator final de escala para EMF do Audaces.

        A escala automática do EMF exportado como Metafile nesta instalação
        não bate com a régua técnica do Audaces. O fator abaixo foi calibrado
        com a medida real enviada: 544.28 mm no GUIMMA corresponde a 400.17 mm no Audaces,
        com validação secundária de 549.57 mm para 407.25 mm. Depois a interface pode expor esse fator como calibração
        manual editável.
        """
        return float(cls.ESCALA_CALIBRACAO_PADRAO)

    @staticmethod
    def _aplicar_escala_emf_doc(emf_doc, fator: float):
        if isinstance(fator, (tuple, list)):
            fator_x = float(fator[0] or 1.0)
            fator_y = float(fator[1] or fator_x)
        else:
            fator_x = float(fator or 1.0)
            fator_y = fator_x
        fator_medio = (fator_x + fator_y) / 2.0
        if abs(fator_x - 1.0) < 1e-12 and abs(fator_y - 1.0) < 1e-12:
            return

        def _scale_pt(pt):
            x, y = pt
            return float(x) * fator_x, float(y) * fator_y

        for el in getattr(emf_doc, "elementos", []):
            el.pontos = [_scale_pt(p) for p in el.pontos]
            if el.pontos:
                xs = [p[0] for p in el.pontos]
                ys = [p[1] for p in el.pontos]
            el.bbox = (min(xs), min(ys), max(xs), max(ys))
            el.metadados["escala_manual_aplicada"] = fator_medio
            el.metadados["escala_x_aplicada"] = fator_x
            el.metadados["escala_y_aplicada"] = fator_y
            el.metadados["unidade_resultado"] = "cm_calibrado_por_xml"

        for tx in getattr(emf_doc, "textos", []):
            if "pos" in tx:
                tx["pos"] = _scale_pt(tx["pos"])

        try:
            l, t, r, b = emf_doc.bounds
            emf_doc.bounds = (l * fator_x, t * fator_y, r * fator_x, b * fator_y)
            emf_doc.largura = max(emf_doc.bounds[2] - emf_doc.bounds[0], 0.0)
            emf_doc.altura = max(emf_doc.bounds[3] - emf_doc.bounds[1], 0.0)
        except Exception:
            pass

        rel = getattr(emf_doc, "relatorio", {})
        if isinstance(rel, dict):
            rel["escala_manual_aplicada"] = fator_medio
            rel["escala_x_aplicada"] = fator_x
            rel["escala_y_aplicada"] = fator_y
            rel["fator_escala_final"] = fator_medio
            rel["unidade_resultado"] = "cm_calibrado_por_xml"
            rel.setdefault("avisos", []).append(
                f"Escala calibrada aplicada ao EMF: X {fator_x:.8f}, Y {fator_y:.8f}."
            )

    @staticmethod
    def _gerar_relatorio_importacao(xml_doc, emf_doc, info: dict) -> dict:
        rel = dict(emf_doc.relatorio)
        records_tipos = rel.get("records_tipos", {})
        return {
            "arquivo_emf": str(emf_doc.caminho),
            "records_emf_total": rel.get("records_total", 0),
            "records_emf_tipos": records_tipos,
            "quantidade_polyline": rel.get("quantidade_polylines", 0),
            "quantidade_polygon": rel.get("quantidade_polygons", 0),
            "quantidade_polybezier": rel.get("quantidade_beziers", 0),
            "quantidade_textos": rel.get("quantidade_textos", 0),
            "elementos_vetoriais_convertidos": rel.get("elementos_convertidos", 0),
            "contornos_fechados": info.get("contornos_fechados", 0),
            "moldes_reais_criados": info.get("moldes_reais", 0),
            "pecas_xml_lidas": len(xml_doc.pecas),
            "pecas_xml_associadas": info.get("associacoes", 0),
            "pecas_xml_sem_associacao": info.get("pecas_xml_sem_associacao", 0),
            "bounds_emf": emf_doc.bounds,
            "escala_usada": rel.get("escala", {}),
            "escala_manual_aplicada": info.get("escala_manual_aplicada"),
            "medida_guimma_referencia_mm": info.get("medida_guimma_referencia_mm"),
            "medida_audaces_referencia_mm": info.get("medida_audaces_referencia_mm"),
            "fator_escala_final": info.get("fator_escala_final") or info.get("escala_manual_aplicada"),
            "unidade_resultado": info.get("unidade_resultado"),
            "records_nao_suportados": rel.get("records_nao_suportados", {}),
            "avisos": list(info.get("avisos", [])) + list(rel.get("avisos", [])),
            "diagnostico_antes": info.get("diagnostico_antes", {}),
            "diagnostico_depois": info.get("diagnostico_depois", {}),
            "mensagem_final": info.get("mensagem_final"),
            "mensagem_diagnostico": info.get("mensagem_diagnostico"),
            "canvas_origem": info.get("canvas_origem"),
            "canvas_moldes_renderizados": info.get("canvas_moldes_renderizados"),
            "canvas_elementos_emf_renderizados": info.get("canvas_elementos_emf_renderizados"),
        }

    @staticmethod
    def _salvar_relatorio_debug(relatorio: dict) -> Path:
        out = Path("debug") / "audaces_emf_xml_import_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
