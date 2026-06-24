from __future__ import annotations

import base64
import json
import re
from collections import Counter
from math import acos, atan2, degrees, sqrt
from statistics import median
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from core.projeto import Documento, Molde, Parte, Ponto, Projeto
from formats.ads_decoder import ADSGeometryDecoder
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

        def ponto_xy(valor):
            try:
                if isinstance(valor, dict) and {"x", "y"}.issubset(valor):
                    return float(valor["x"]), float(valor["y"])
                if isinstance(valor, (tuple, list)) and len(valor) >= 2:
                    return float(valor[0]), float(valor[1])
            except (TypeError, ValueError):
                return None
            return None

        for el in elementos_canvas or []:
            if not isinstance(el, dict):
                continue
            for pt in el.get("pontos", []) or []:
                xy = ponto_xy(pt)
                if xy is not None:
                    pontos.append(xy)
            pos = el.get("pos")
            xy_pos = ponto_xy(pos)
            if xy_pos is not None:
                pontos.append(xy_pos)
            for chave in ("controle_cantos", "controle_auxiliares", "pontos_controle_principais", "pontos_auxiliares"):
                for pt in el.get(chave, []) or []:
                    xy = ponto_xy(pt)
                    if xy is not None:
                        pontos.append(xy)
            for chave in ("graduacao_contornos_importados", "graduacao_contornos_regularizados_preview"):
                for item in el.get(chave, []) or []:
                    if isinstance(item, dict):
                        for pt in item.get("pontos", []) or []:
                            xy = ponto_xy(pt)
                            if xy is not None:
                                pontos.append(xy)
        bbox = cls._bbox_pontos(pontos)
        if not bbox:
            return {"aplicado": False, "dx": 0.0, "dy": 0.0, "bbox_original": None}
        minx, miny, maxx, maxy = bbox
        dx = -((minx + maxx) / 2.0)
        dy = -((miny + maxy) / 2.0)
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return {"aplicado": False, "dx": 0.0, "dy": 0.0, "bbox_original": bbox, "bbox_final": bbox}

        def mover_ponto(valor):
            if isinstance(valor, dict) and {"x", "y"}.issubset(valor):
                novo = dict(valor)
                novo["x"] = float(valor["x"]) + dx
                novo["y"] = float(valor["y"]) + dy
                return novo
            if isinstance(valor, (tuple, list)) and len(valor) >= 2:
                return (float(valor[0]) + dx, float(valor[1]) + dy)
            return valor

        for el in elementos_canvas or []:
            if not isinstance(el, dict):
                continue
            if el.get("pontos"):
                el["pontos"] = [mover_ponto(pt) for pt in el.get("pontos", [])]
            for chave in (
                "pos",
                "fio_origem",
                "fio_fim",
                "ponto_texto",
                "controle_cantos",
                "controle_auxiliares",
                "pontos_controle_principais",
                "pontos_auxiliares",
            ):
                if chave in el:
                    valor = el.get(chave)
                    el[chave] = [mover_ponto(pt) for pt in valor] if isinstance(valor, list) else mover_ponto(valor)
            for chave in ("graduacao_contornos_importados", "graduacao_contornos_regularizados_preview"):
                for item in el.get(chave, []) or []:
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

    @classmethod
    def _transformar_ponto_canvas(
        cls,
        valor,
        *,
        cx: float,
        cy: float,
        sx: float,
        sy: float,
    ):
        def aplicar_xy(x: float, y: float) -> tuple[float, float]:
            return cx + ((float(x) - cx) * sx), cy + ((float(y) - cy) * sy)

        if isinstance(valor, dict) and {"x", "y"}.issubset(valor):
            novo = dict(valor)
            novo["x"], novo["y"] = aplicar_xy(float(valor["x"]), float(valor["y"]))
            return novo
        if isinstance(valor, (tuple, list)) and len(valor) >= 2:
            return aplicar_xy(float(valor[0]), float(valor[1]))
        return valor

    @classmethod
    def _transformar_elemento_canvas_por_bbox(
        cls,
        elemento: dict,
        *,
        bbox: tuple[float, float, float, float],
        sx: float,
        sy: float,
    ) -> None:
        minx, miny, maxx, maxy = bbox
        cx = (float(minx) + float(maxx)) / 2.0
        cy = (float(miny) + float(maxy)) / 2.0

        def mover(valor):
            return cls._transformar_ponto_canvas(valor, cx=cx, cy=cy, sx=sx, sy=sy)

        if elemento.get("pontos"):
            elemento["pontos"] = [mover(pt) for pt in elemento.get("pontos", [])]
        for chave in (
            "pos",
            "fio_origem",
            "fio_fim",
            "ponto_texto",
            "ponto_texto_nome",
            "nome_posicao",
            "nome_centro",
            "controle_cantos",
            "controle_auxiliares",
            "pontos_controle_principais",
            "pontos_auxiliares",
        ):
            if chave not in elemento:
                continue
            valor = elemento.get(chave)
            elemento[chave] = [mover(pt) for pt in valor] if isinstance(valor, list) else mover(valor)
        for chave in ("graduacao_contornos_importados", "graduacao_contornos_regularizados_preview"):
            for item in elemento.get(chave, []) or []:
                if isinstance(item, dict) and item.get("pontos"):
                    item["pontos"] = [mover(pt) for pt in item.get("pontos", [])]
        for chave in list(elemento):
            if str(chave).startswith("_runtime_"):
                elemento.pop(chave, None)

    @classmethod
    def _calibrar_moldes_por_dimensoes_xml(
        cls,
        elementos_canvas: list[dict],
        doc: Documento | None = None,
    ) -> dict:
        """Ajusta cada molde para a largura/altura oficial do tamanho base no XML.

        O EMF preserva o desenho vetorial, mas pequenos desvios de escala por
        peça aparecem depois da união de segmentos. A calibração abaixo aplica a
        mesma transformação ao contorno, graduação, controles, fio e texto.
        """
        detalhes: list[dict] = []
        transformacoes_por_nome: dict[str, dict[str, float]] = {}
        for elemento in elementos_canvas or []:
            if not isinstance(elemento, dict) or not elemento.get("molde"):
                continue
            dimensoes_xml = elemento.get("graduacao_dimensoes_xml")
            if not isinstance(dimensoes_xml, dict) or not dimensoes_xml:
                continue
            base_nome = str(elemento.get("tamanho_base_detectado") or "").strip()
            if not base_nome:
                for nome, dim in dimensoes_xml.items():
                    if isinstance(dim, dict) and dim.get("base"):
                        base_nome = str(nome or "").strip()
                        break
            if not base_nome:
                continue
            base_dim = dimensoes_xml.get(base_nome) or dimensoes_xml.get(cls._normalizar_tamanho_grade(base_nome))
            if not isinstance(base_dim, dict):
                continue
            largura_xml = float(base_dim.get("largura") or 0.0)
            altura_xml = float(base_dim.get("altura") or 0.0)
            if largura_xml <= 0.0 or altura_xml <= 0.0:
                continue
            pontos = cls._sem_fecho_repetido(cls._pontos_float(elemento.get("pontos")))
            bbox = cls._bbox_pontos(pontos)
            if not bbox:
                continue
            largura_atual = max(float(bbox[2]) - float(bbox[0]), 1e-9)
            altura_atual = max(float(bbox[3]) - float(bbox[1]), 1e-9)
            sx = largura_xml / largura_atual
            sy = altura_xml / altura_atual
            if not (0.50 <= sx <= 1.50 and 0.50 <= sy <= 1.50):
                detalhes.append({
                    "molde": elemento.get("nome_molde"),
                    "base": base_nome,
                    "aplicado": False,
                    "motivo": "fator_fora_da_faixa_segura",
                    "sx": sx,
                    "sy": sy,
                })
                continue
            if abs(sx - 1.0) <= 1e-5 and abs(sy - 1.0) <= 1e-5:
                detalhes.append({
                    "molde": elemento.get("nome_molde"),
                    "base": base_nome,
                    "aplicado": False,
                    "motivo": "ja_calibrado",
                    "largura": largura_atual,
                    "altura": altura_atual,
                })
                continue
            cls._transformar_elemento_canvas_por_bbox(elemento, bbox=bbox, sx=sx, sy=sy)
            cls._aplicar_controles_cantos_canvas(elemento)
            if elemento.get("graduacao_contornos_importados") and not elemento.get("graduacao_regularizacao_bloqueada"):
                cls._regularizar_graduacao_importada(elemento)
            novo_bbox = cls._bbox_pontos(cls._sem_fecho_repetido(cls._pontos_float(elemento.get("pontos"))))
            detalhe = {
                "molde": elemento.get("nome_molde"),
                "base": base_nome,
                "aplicado": True,
                "sx": sx,
                "sy": sy,
                "largura_antes": largura_atual,
                "altura_antes": altura_atual,
                "largura_xml": largura_xml,
                "altura_xml": altura_xml,
                "bbox_original": bbox,
                "bbox_final": novo_bbox,
            }
            elemento["calibracao_dimensoes_xml"] = detalhe
            detalhes.append(detalhe)
            nome = str(elemento.get("nome_molde") or "").strip()
            if nome:
                transformacoes_por_nome[nome] = {
                    "cx": (float(bbox[0]) + float(bbox[2])) / 2.0,
                    "cy": (float(bbox[1]) + float(bbox[3])) / 2.0,
                    "sx": sx,
                    "sy": sy,
                }

        if doc is not None and transformacoes_por_nome:
            for molde in getattr(doc, "moldes", []) or []:
                tr = transformacoes_por_nome.get(str(getattr(molde, "nome", "") or "").strip())
                if not tr:
                    continue
                for parte in getattr(molde, "partes", []) or []:
                    for ponto in getattr(parte, "pontos", []) or []:
                        ponto.x, ponto.y = cls._transformar_ponto_canvas(
                            (float(ponto.x), float(ponto.y)),
                            cx=tr["cx"],
                            cy=tr["cy"],
                            sx=tr["sx"],
                            sy=tr["sy"],
                        )

        return {
            "aplicado": any(item.get("aplicado") for item in detalhes),
            "moldes_calibrados": sum(1 for item in detalhes if item.get("aplicado")),
            "detalhes": detalhes,
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
            return "G1", 5
        if nome_cor == "roxo":
            return "G2", 6
        return None

    @staticmethod
    def _normalizar_tamanho_grade(valor: str | None) -> str:
        texto = str(valor or "").strip().strip('"').strip("'")
        texto = " ".join(texto.split())
        return texto.upper()

    @classmethod
    def _tamanho_em_lista(cls, valor: str | None, labels: list[str]) -> str | None:
        alvo = cls._normalizar_tamanho_grade(valor)
        if not alvo:
            return None
        for label in labels:
            if cls._normalizar_tamanho_grade(label) == alvo:
                return label
        return None

    @classmethod
    def _base_de_nome_grade(cls, nome_grade: str | None, labels: list[str]) -> str | None:
        texto = str(nome_grade or "").strip()
        if not texto:
            return None
        candidatos = re.findall(r"\(([^()]+)\)", texto)
        for candidato in reversed(candidatos):
            base = cls._tamanho_em_lista(candidato, labels)
            if base:
                return base
        return None

    @classmethod
    def _base_padrao_por_labels(cls, labels: list[str]) -> str | None:
        if not labels:
            return None
        numericos: list[tuple[float, str]] = []
        for label in labels:
            normalizado = cls._normalizar_tamanho_grade(label).replace(",", ".")
            if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalizado):
                numericos = []
                break
            numericos.append((float(normalizado), label))
        if numericos:
            ordenados = sorted(numericos, key=lambda item: item[0])
            return ordenados[len(ordenados) // 2][1]

        normalizados = {cls._normalizar_tamanho_grade(label): label for label in labels}
        if "PP" in normalizados and "P" in normalizados:
            return normalizados["P"]
        if "M" in normalizados:
            return normalizados["M"]
        if "P" in normalizados:
            return normalizados["P"]
        if "G" in normalizados:
            return normalizados["G"]
        return labels[len(labels) // 2]

    @classmethod
    def _resolver_tamanho_base(
        cls,
        labels: list[str],
        candidatos: list[str | None] | None = None,
        *,
        nome_grade: str | None = None,
    ) -> str | None:
        labels_validos: list[str] = []
        vistos: set[str] = set()
        for label in labels or []:
            texto = str(label or "").strip()
            chave = cls._normalizar_tamanho_grade(texto)
            if texto and chave not in vistos:
                labels_validos.append(texto)
                vistos.add(chave)
        if not labels_validos:
            return None

        votos: list[str] = []
        for candidato in candidatos or []:
            base = cls._tamanho_em_lista(candidato, labels_validos)
            if base:
                votos.append(base)
        if votos:
            contador = Counter(votos)
            ordem = {label: idx for idx, label in enumerate(labels_validos)}
            return max(contador, key=lambda label: (contador[label], -ordem.get(label, 10**6)))

        base_nome_grade = cls._base_de_nome_grade(nome_grade, labels_validos)
        if base_nome_grade:
            return base_nome_grade
        return cls._base_padrao_por_labels(labels_validos)

    @classmethod
    def _garantir_base_unica_linhas(
        cls,
        linhas: list[dict],
        tamanho_base: str | None,
    ) -> tuple[list[dict], str | None]:
        labels = [str(linha.get("tamanho") or "").strip() for linha in linhas if str(linha.get("tamanho") or "").strip()]
        base = cls._resolver_tamanho_base(labels, [tamanho_base])
        for linha in linhas:
            linha["base"] = bool(base and cls._normalizar_tamanho_grade(linha.get("tamanho")) == cls._normalizar_tamanho_grade(base))
        return linhas, base

    @classmethod
    def _valores_xml_por_chave(cls, no, chaves: set[str]) -> list[str]:
        valores: list[str] = []
        chaves_normalizadas = {str(chave).upper() for chave in chaves}

        def visitar(valor) -> None:
            if isinstance(valor, dict):
                for chave, item in valor.items():
                    if str(chave).upper() in chaves_normalizadas and isinstance(item, (str, int, float)):
                        texto = str(item).strip()
                        if texto:
                            valores.append(texto)
                    visitar(item)
                return
            if isinstance(valor, list):
                for item in valor:
                    visitar(item)

        visitar(no)
        return valores

    @classmethod
    def _grade_xml_doc(cls, xml_doc) -> tuple[list[str], str | None]:
        if xml_doc is None:
            return [], None
        labels: list[str] = []
        bases: list[str | None] = []
        for peca in getattr(xml_doc, "pecas", []) or []:
            bases.append(getattr(peca, "tamanho_base", None))
            for tamanho in getattr(peca, "tamanhos", []) or []:
                nome = str(getattr(tamanho, "tamanho", "") or "").strip()
                if nome and nome not in labels:
                    labels.append(nome)
        if not labels:
            for tamanho in getattr(xml_doc, "tamanhos_modelo", []) or []:
                nome = str(getattr(tamanho, "nome", "") or "").strip()
                if nome and nome not in labels:
                    labels.append(nome)
        nomes_grade = cls._valores_xml_por_chave(
            getattr(xml_doc, "bruto_normalizado", None),
            {"NAME_GRAD", "GRADE", "GRADE_NAME", "GRADENAME", "NOME_GRADE"},
        )
        nome_grade = next((nome for nome in nomes_grade if "(" in nome and ")" in nome), nomes_grade[0] if nomes_grade else None)
        base = cls._resolver_tamanho_base(labels, bases, nome_grade=nome_grade)
        return labels, base

    @staticmethod
    def _cor_grade_faltante(label: str) -> str:
        mapa = {
            "PP": "#bdbdbd",
            "P": "#00d000",
            "M": "#0080ff",
            "G": "#ffffff",
            "GG": "#ff00ff",
            "G1": "#ff8000",
            "G2": "#aa00ff",
        }
        return mapa.get(str(label or "").strip().upper(), "#6a6a6a")

    @classmethod
    def _grade_por_dimensoes_xml(
        cls,
        dimensoes_xml: dict | None,
        tamanho_base: str | None = None,
    ) -> tuple[str, list[dict], str | None] | None:
        if not isinstance(dimensoes_xml, dict) or not dimensoes_xml:
            return None
        labels: list[str] = []
        bases: list[str | None] = [tamanho_base]
        for label, dados in dimensoes_xml.items():
            nome = str(label or "").strip()
            if not nome:
                continue
            if nome not in labels:
                labels.append(nome)
            if isinstance(dados, dict) and dados.get("base"):
                bases.append(nome)
        if not labels:
            return None
        base = cls._resolver_tamanho_base(labels, bases)
        linhas = [
            {
                "ativo": True,
                "tamanho": label,
                "cor": cls._cor_grade_faltante(label),
                "base": bool(base and cls._normalizar_tamanho_grade(label) == cls._normalizar_tamanho_grade(base)),
                "visivel_emf": False,
            }
            for label in labels
        ]
        linhas, base = cls._garantir_base_unica_linhas(linhas, base)
        grade_nome = f"{labels[0]}-{labels[-1]}({base})" if base else f"{labels[0]}-{labels[-1]}"
        return grade_nome, linhas, base

    @staticmethod
    def _angulo_interno_ponto(
        anterior: tuple[float, float],
        atual: tuple[float, float],
        proximo: tuple[float, float],
    ) -> float:
        ux = float(anterior[0]) - float(atual[0])
        uy = float(anterior[1]) - float(atual[1])
        vx = float(proximo[0]) - float(atual[0])
        vy = float(proximo[1]) - float(atual[1])
        nu = sqrt((ux * ux) + (uy * uy))
        nv = sqrt((vx * vx) + (vy * vy))
        if nu <= 1e-9 or nv <= 1e-9:
            return 180.0
        dot = max(-1.0, min(1.0, ((ux * vx) + (uy * vy)) / (nu * nv)))
        return degrees(acos(dot))

    @classmethod
    def _controle_cantos_por_quinas(
        cls,
        pontos: list[tuple[float, float]],
        *,
        limite_graus: float = 136.0,
        quina_forte_graus: float = 112.0,
        contraste_minimo_graus: float = 8.0,
    ) -> list[tuple[float, float]]:
        pts = [(float(x), float(y)) for x, y in (pontos or [])]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3:
            return pts
        cantos: list[tuple[float, float]] = []
        total = len(pts)
        angulos = [
            cls._angulo_interno_ponto(pts[(idx - 1) % total], ponto, pts[(idx + 1) % total])
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

    @classmethod
    def _aplicar_controles_cantos_canvas(cls, elemento: dict) -> None:
        if not isinstance(elemento, dict) or not elemento.get("molde"):
            return
        pontos = elemento.get("pontos")
        if not isinstance(pontos, list):
            return
        cantos = cls._controle_cantos_por_quinas([(float(x), float(y)) for x, y in pontos])
        pontos_base = cls._sem_fecho_repetido(cls._pontos_float(pontos))
        if not cantos and not pontos_base:
            return
        chaves_cantos = {(round(float(x), 7), round(float(y), 7)) for x, y in cantos}
        auxiliares: list[tuple[float, float]] = []
        vistos_aux: set[tuple[float, float]] = set()
        for x, y in pontos_base:
            chave = (round(float(x), 7), round(float(y), 7))
            if chave in chaves_cantos or chave in vistos_aux:
                continue
            vistos_aux.add(chave)
            auxiliares.append((float(x), float(y)))
        elemento["controle_cantos"] = [(float(x), float(y)) for x, y in cantos]
        elemento["controle_auxiliares"] = auxiliares
        elemento.setdefault("mostrar_controles", True)
        elemento["pontos_controle_principais"] = [
            {"x": float(x), "y": float(y), "origem": "audaces_emf_quina"}
            for x, y in cantos
        ]
        elemento["pontos_auxiliares"] = [
            {"x": float(x), "y": float(y), "origem": "audaces_emf_auxiliar"}
            for x, y in auxiliares
        ]
        elemento["cantos_preservados_importacao"] = len(cantos)
        elemento["auxiliares_preservados_importacao"] = len(auxiliares)

    @staticmethod
    def _distancia_pontos(a: tuple[float, float], b: tuple[float, float]) -> float:
        return ((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2) ** 0.5

    @classmethod
    def _pontos_float(cls, pontos) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []
        for ponto in pontos or []:
            try:
                saida.append((float(ponto[0]), float(ponto[1])))
            except (TypeError, ValueError, IndexError):
                continue
        return saida

    @classmethod
    def _sem_fecho_repetido(cls, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        pts = list(pontos or [])
        if len(pts) >= 2 and cls._distancia_pontos(pts[0], pts[-1]) <= 1e-7:
            pts = pts[:-1]
        return pts

    @staticmethod
    def _area_assinada_pontos(pontos: list[tuple[float, float]]) -> float:
        if len(pontos) < 3:
            return 0.0
        area = 0.0
        total = len(pontos)
        for idx, (x1, y1) in enumerate(pontos):
            x2, y2 = pontos[(idx + 1) % total]
            area += (float(x1) * float(y2)) - (float(x2) * float(y1))
        return area / 2.0

    @classmethod
    def _reamostrar_contorno_fechado(
        cls,
        pontos: list[tuple[float, float]],
        quantidade: int,
    ) -> list[tuple[float, float]]:
        pts = cls._sem_fecho_repetido(cls._pontos_float(pontos))
        if quantidade <= 0 or not pts:
            return []
        if len(pts) == quantidade:
            return list(pts)
        if len(pts) == 1:
            return [pts[0] for _ in range(quantidade)]
        comprimentos: list[float] = []
        total = 0.0
        for idx, ponto in enumerate(pts):
            prox = pts[(idx + 1) % len(pts)]
            total += cls._distancia_pontos(ponto, prox)
            comprimentos.append(total)
        if total <= 1e-9:
            return [pts[0] for _ in range(quantidade)]
        saida: list[tuple[float, float]] = []
        seg_idx = 0
        anterior_acumulado = 0.0
        for pos in range(quantidade):
            alvo = (total * pos) / quantidade
            while seg_idx < len(comprimentos) - 1 and comprimentos[seg_idx] < alvo:
                anterior_acumulado = comprimentos[seg_idx]
                seg_idx += 1
            inicio = pts[seg_idx]
            fim = pts[(seg_idx + 1) % len(pts)]
            comp_seg = max(comprimentos[seg_idx] - anterior_acumulado, 1e-9)
            t = max(0.0, min(1.0, (alvo - anterior_acumulado) / comp_seg))
            saida.append((
                inicio[0] + ((fim[0] - inicio[0]) * t),
                inicio[1] + ((fim[1] - inicio[1]) * t),
            ))
        return saida

    @classmethod
    def _alinhar_contorno_a_base(
        cls,
        base: list[tuple[float, float]],
        alvo: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        if not base or not alvo:
            return []
        quantidade = len(base)
        reamostrado = cls._reamostrar_contorno_fechado(alvo, quantidade)
        if not reamostrado:
            return []
        candidatos = [reamostrado]
        if cls._area_assinada_pontos(base) * cls._area_assinada_pontos(reamostrado) < 0:
            candidatos.insert(0, list(reversed(reamostrado)))
        else:
            candidatos.append(list(reversed(reamostrado)))
        passo = max(1, quantidade // 18)
        amostras = list(range(0, quantidade, passo))
        if quantidade - 1 not in amostras:
            amostras.append(quantidade - 1)
        melhor: tuple[float, list[tuple[float, float]]] | None = None
        for candidato in candidatos:
            for deslocamento in range(quantidade):
                alinhado = candidato[deslocamento:] + candidato[:deslocamento]
                erro = 0.0
                for idx in amostras:
                    erro += cls._distancia_pontos(base[idx], alinhado[idx])
                if melhor is None or erro < melhor[0]:
                    melhor = (erro, alinhado)
        return list(melhor[1]) if melhor else reamostrado

    @staticmethod
    def _suavizar_vetores_circulares(
        vetores: list[tuple[float, float]],
        passes: int = 3,
    ) -> list[tuple[float, float]]:
        if len(vetores) < 5:
            return list(vetores)
        atual = [(float(dx), float(dy)) for dx, dy in vetores]
        for _ in range(max(0, int(passes))):
            novo: list[tuple[float, float]] = []
            total = len(atual)
            for idx, (dx, dy) in enumerate(atual):
                ax, ay = atual[(idx - 1) % total]
                bx, by = atual[(idx + 1) % total]
                novo.append((
                    (ax * 0.20) + (dx * 0.60) + (bx * 0.20),
                    (ay * 0.20) + (dy * 0.60) + (by * 0.20),
                ))
            atual = novo
        return atual

    @classmethod
    def _interpolar_campos_deslocamento(
        cls,
        campos: dict[int, list[tuple[float, float]]],
        passo_alvo: int,
    ) -> list[tuple[float, float]] | None:
        if passo_alvo in campos:
            return campos[passo_alvo]
        passos = sorted(campos)
        if not passos:
            return None
        menores = [passo for passo in passos if passo < passo_alvo]
        maiores = [passo for passo in passos if passo > passo_alvo]
        if menores and maiores:
            a = menores[-1]
            b = maiores[0]
            if a == b:
                return campos[a]
            t = (passo_alvo - a) / float(b - a)
            return [
                ((v1[0] * (1.0 - t)) + (v2[0] * t), (v1[1] * (1.0 - t)) + (v2[1] * t))
                for v1, v2 in zip(campos[a], campos[b])
            ]
        referencia = menores[-1] if menores else maiores[0]
        if referencia == 0:
            return None
        fator = passo_alvo / float(referencia)
        return [(dx * fator, dy * fator) for dx, dy in campos[referencia]]

    @staticmethod
    def _centroide_pontos(pontos: list[tuple[float, float]]) -> tuple[float, float]:
        if not pontos:
            return 0.0, 0.0
        return (
            sum(float(x) for x, _y in pontos) / len(pontos),
            sum(float(y) for _x, y in pontos) / len(pontos),
        )

    @classmethod
    def _normais_externas_contorno(cls, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        pts = cls._sem_fecho_repetido(cls._pontos_float(pontos))
        if len(pts) < 3:
            return []
        cx, cy = cls._centroide_pontos(pts)
        normais: list[tuple[float, float]] = []
        total = len(pts)
        for idx, ponto in enumerate(pts):
            anterior = pts[(idx - 1) % total]
            proximo = pts[(idx + 1) % total]
            tx = float(proximo[0]) - float(anterior[0])
            ty = float(proximo[1]) - float(anterior[1])
            norma = sqrt((tx * tx) + (ty * ty))
            if norma <= 1e-9:
                normais.append((0.0, 0.0))
                continue
            nx = ty / norma
            ny = -tx / norma
            vx = float(ponto[0]) - cx
            vy = float(ponto[1]) - cy
            if (nx * vx) + (ny * vy) < 0:
                nx = -nx
                ny = -ny
            normais.append((nx, ny))
        return normais

    @classmethod
    def _unidade_offset_por_contorno(
        cls,
        base: list[tuple[float, float]],
        normais: list[tuple[float, float]],
        alvo: list[tuple[float, float]],
        passo: int,
    ) -> float | None:
        if passo == 0 or len(base) < 3 or len(base) != len(normais):
            return None
        alvo_pts = cls._sem_fecho_repetido(cls._pontos_float(alvo))
        if len(alvo_pts) < 3:
            return None
        projecoes_filtradas: list[float] = []
        projecoes_todas: list[float] = []
        for ponto, normal in zip(base, normais):
            nx, ny = normal
            if abs(nx) <= 1e-9 and abs(ny) <= 1e-9:
                continue
            mais_proximo = min(alvo_pts, key=lambda pt: cls._distancia_pontos(ponto, pt))
            proj = ((float(mais_proximo[0]) - float(ponto[0])) * nx) + (
                (float(mais_proximo[1]) - float(ponto[1])) * ny
            )
            unidade = proj / float(passo)
            projecoes_todas.append(unidade)
            if unidade > 1e-6:
                projecoes_filtradas.append(unidade)
        valores = projecoes_filtradas if len(projecoes_filtradas) >= max(3, len(base) // 5) else projecoes_todas
        valores = [valor for valor in valores if abs(valor) > 1e-6]
        if not valores:
            return None
        return float(median(valores))

    @classmethod
    def _contorno_por_offset_normal(
        cls,
        base: list[tuple[float, float]],
        normais: list[tuple[float, float]],
        offset: float,
    ) -> list[tuple[float, float]]:
        pontos = [
            (float(ponto[0]) + (float(normal[0]) * offset), float(ponto[1]) + (float(normal[1]) * offset))
            for ponto, normal in zip(base, normais)
        ]
        if pontos:
            pontos.append(pontos[0])
        return pontos

    @classmethod
    def _transformacao_bbox_contorno(
        cls,
        base: list[tuple[float, float]],
        alvo: list[tuple[float, float]],
    ) -> dict[str, float] | None:
        base_pts = cls._sem_fecho_repetido(cls._pontos_float(base))
        alvo_pts = cls._sem_fecho_repetido(cls._pontos_float(alvo))
        if len(base_pts) < 3 or len(alvo_pts) < 3:
            return None
        bbox_base = cls._bbox_pontos(base_pts)
        bbox_alvo = cls._bbox_pontos(alvo_pts)
        if not bbox_base or not bbox_alvo:
            return None
        bw = max(float(bbox_base[2]) - float(bbox_base[0]), 1e-9)
        bh = max(float(bbox_base[3]) - float(bbox_base[1]), 1e-9)
        aw = max(float(bbox_alvo[2]) - float(bbox_alvo[0]), 1e-9)
        ah = max(float(bbox_alvo[3]) - float(bbox_alvo[1]), 1e-9)
        return {
            "base_cx": (float(bbox_base[0]) + float(bbox_base[2])) / 2.0,
            "base_cy": (float(bbox_base[1]) + float(bbox_base[3])) / 2.0,
            "cx": (float(bbox_alvo[0]) + float(bbox_alvo[2])) / 2.0,
            "cy": (float(bbox_alvo[1]) + float(bbox_alvo[3])) / 2.0,
            "sx": aw / bw,
            "sy": ah / bh,
        }

    @staticmethod
    def _interpolar_transformacao_bbox(
        transformacoes: dict[int, dict[str, float]],
        base_idx: int,
        alvo_idx: int,
    ) -> dict[str, float] | None:
        if alvo_idx in transformacoes:
            return dict(transformacoes[alvo_idx])
        if base_idx not in transformacoes:
            return None
        base = transformacoes[base_idx]
        refs = [idx for idx in sorted(transformacoes) if idx != base_idx]
        if not refs:
            return dict(base)
        if alvo_idx < base_idx:
            candidatos = [idx for idx in refs if idx > base_idx] or refs
        elif alvo_idx > base_idx:
            candidatos = [idx for idx in refs if idx < base_idx] or refs
        else:
            return dict(base)
        ref_idx = min(candidatos, key=lambda idx: abs(idx - alvo_idx))
        if ref_idx == base_idx:
            return dict(base)
        ref = transformacoes[ref_idx]
        fator = (alvo_idx - base_idx) / float(ref_idx - base_idx)
        saida: dict[str, float] = {}
        for chave in ("base_cx", "base_cy"):
            saida[chave] = float(base.get(chave, 0.0))
        for chave in ("cx", "cy", "sx", "sy"):
            valor = float(base.get(chave, 0.0)) + ((float(ref.get(chave, 0.0)) - float(base.get(chave, 0.0))) * fator)
            if chave in {"sx", "sy"}:
                valor = max(0.05, valor)
            saida[chave] = valor
        return saida

    @staticmethod
    def _contorno_por_transformacao_base(
        base: list[tuple[float, float]],
        transformacao: dict[str, float],
    ) -> list[tuple[float, float]]:
        base_cx = float(transformacao.get("base_cx", 0.0))
        base_cy = float(transformacao.get("base_cy", 0.0))
        cx = float(transformacao.get("cx", base_cx))
        cy = float(transformacao.get("cy", base_cy))
        sx = float(transformacao.get("sx", 1.0))
        sy = float(transformacao.get("sy", 1.0))
        pontos = [
            (
                cx + ((float(x) - base_cx) * sx),
                cy + ((float(y) - base_cy) * sy),
            )
            for x, y in base
        ]
        if pontos:
            pontos.append(pontos[0])
        return pontos

    @classmethod
    def _contorno_por_escala_dimensoes_xml(
        cls,
        pontos: list[tuple[float, float]],
        dim_origem: dict | None,
        dim_destino: dict | None,
    ) -> list[tuple[float, float]]:
        pts = cls._sem_fecho_repetido(cls._pontos_float(pontos))
        if len(pts) < 3 or not isinstance(dim_destino, dict):
            return []
        bbox = cls._bbox_pontos(pts)
        if not bbox:
            return []
        largura_origem = float((dim_origem or {}).get("largura") or 0.0)
        altura_origem = float((dim_origem or {}).get("altura") or 0.0)
        if largura_origem <= 0.0:
            largura_origem = max(float(bbox[2]) - float(bbox[0]), 1e-9)
        if altura_origem <= 0.0:
            altura_origem = max(float(bbox[3]) - float(bbox[1]), 1e-9)
        largura_destino = float(dim_destino.get("largura") or 0.0)
        altura_destino = float(dim_destino.get("altura") or 0.0)
        if largura_destino <= 0.0 or altura_destino <= 0.0:
            return []
        sx = max(0.05, largura_destino / max(largura_origem, 1e-9))
        sy = max(0.05, altura_destino / max(altura_origem, 1e-9))
        cx = (float(bbox[0]) + float(bbox[2])) / 2.0
        cy = (float(bbox[1]) + float(bbox[3])) / 2.0
        saida = [(cx + ((float(x) - cx) * sx), cy + ((float(y) - cy) * sy)) for x, y in pts]
        if saida:
            saida.append(saida[0])
        return saida

    @classmethod
    def _ajustar_contorno_para_dimensoes_xml(
        cls,
        pontos: list[tuple[float, float]],
        dim_destino: dict | None,
    ) -> list[tuple[float, float]]:
        pts = cls._sem_fecho_repetido(cls._pontos_float(pontos))
        if len(pts) < 3 or not isinstance(dim_destino, dict):
            return list(pontos)
        bbox = cls._bbox_pontos(pts)
        if not bbox:
            return list(pontos)
        largura_atual = max(float(bbox[2]) - float(bbox[0]), 1e-9)
        altura_atual = max(float(bbox[3]) - float(bbox[1]), 1e-9)
        largura_destino = float(dim_destino.get("largura") or 0.0)
        altura_destino = float(dim_destino.get("altura") or 0.0)
        if largura_destino <= 0.0 or altura_destino <= 0.0:
            return list(pontos)
        sx = largura_destino / largura_atual
        sy = altura_destino / altura_atual
        if not (0.35 <= sx <= 2.85 and 0.35 <= sy <= 2.85):
            return list(pontos)
        cx = (float(bbox[0]) + float(bbox[2])) / 2.0
        cy = (float(bbox[1]) + float(bbox[3])) / 2.0
        saida = [(cx + ((float(x) - cx) * sx), cy + ((float(y) - cy) * sy)) for x, y in pts]
        if saida:
            saida.append(saida[0])
        return saida

    @classmethod
    def _aplicar_tabela_dxdy_por_contornos(
        cls,
        elemento: dict,
        *,
        origem: str,
        contornos: list[dict] | None = None,
        regras_exatas: bool = False,
        preferir_render: bool = False,
    ) -> dict:
        if not isinstance(elemento, dict):
            return {"aplicado": False, "motivo": "elemento_invalido"}
        base = cls._sem_fecho_repetido(cls._pontos_float(elemento.get("pontos")))
        if len(base) < 2:
            return {"aplicado": False, "motivo": "base_invalida"}
        contornos = [
            dict(item)
            for item in ((contornos if contornos is not None else elemento.get("graduacao_contornos_importados")) or [])
            if isinstance(item, dict)
        ]
        if not contornos:
            return {"aplicado": False, "motivo": "sem_contornos"}

        linhas = [dict(linha) for linha in elemento.get("graduacao_tamanhos", []) if isinstance(linha, dict)]
        base_nome = next(
            (
                str(linha.get("tamanho") or linha.get("nome") or "").strip()
                for linha in linhas
                if linha.get("base")
            ),
            "",
        )
        referencias = cls._sem_fecho_repetido(cls._pontos_float(elemento.get("controle_cantos")))
        if not referencias:
            referencias = cls._controle_cantos_por_quinas(base)
        if not referencias:
            referencias = base if len(base) <= 12 else [base[0], base[len(base) // 3], base[(len(base) * 2) // 3]]

        indices_referencia: list[int] = []
        for ponto in referencias:
            if not base:
                continue
            idx = min(range(len(base)), key=lambda i: cls._distancia_pontos(base[i], ponto))
            if idx not in indices_referencia:
                indices_referencia.append(idx)
        if not indices_referencia:
            return {"aplicado": False, "motivo": "sem_pontos_referencia"}

        pontos_cfg: dict[str, dict] = {
            str(pos): {
                "indice": idx,
                "ponto": (float(base[idx][0]), float(base[idx][1])),
                "valores": {},
            }
            for pos, idx in enumerate(indices_referencia)
        }
        tamanhos_com_valores: list[str] = []
        for item in contornos:
            nome = str(item.get("tamanho") or item.get("nome") or "").strip()
            if not nome or nome == base_nome or item.get("base"):
                continue
            alvo = cls._sem_fecho_repetido(cls._pontos_float(item.get("pontos")))
            if len(alvo) < 2:
                continue
            alinhado = cls._alinhar_contorno_a_base(base, alvo)
            if len(alinhado) != len(base):
                alinhado = cls._reamostrar_contorno_fechado(alvo, len(base))
            if len(alinhado) != len(base):
                continue
            for pos, idx in enumerate(indices_referencia):
                ponto_base = base[idx]
                ponto_alvo = alinhado[idx]
                pontos_cfg[str(pos)]["valores"][nome] = {
                    "dx": float(ponto_alvo[0]) - float(ponto_base[0]),
                    "dy": float(ponto_alvo[1]) - float(ponto_base[1]),
                }
            tamanhos_com_valores.append(nome)

        if not tamanhos_com_valores:
            return {"aplicado": False, "motivo": "sem_tamanhos_com_dxdy"}
        tabela = {
            "modo": "dx_dy",
            "origem": origem,
            "base": base_nome,
            "pontos": pontos_cfg,
            "regras_exatas": bool(regras_exatas),
        }
        if regras_exatas:
            elemento["graduacao_tabela"] = tabela
            elemento["graduacao_pontos"] = pontos_cfg
        else:
            elemento["graduacao_tabela_derivada"] = tabela
            elemento["graduacao_pontos_derivados"] = pontos_cfg
        elemento["graduacao_dxdy_origem"] = origem
        elemento["graduacao_regras_exatas"] = bool(regras_exatas)
        elemento["graduacao_preferir_tabela_dxdy"] = bool(preferir_render and regras_exatas)
        elemento["graduacao_dxdy_resumo"] = {
            "aplicado": True,
            "origem": origem,
            "base": base_nome,
            "pontos": len(pontos_cfg),
            "tamanhos": tamanhos_com_valores,
            "regras_exatas": bool(regras_exatas),
            "tabela_chave": "graduacao_tabela" if regras_exatas else "graduacao_tabela_derivada",
        }
        return elemento["graduacao_dxdy_resumo"]

    @classmethod
    def _contornos_topologia_base_por_dimensoes_xml(
        cls,
        *,
        base: list[tuple[float, float]],
        labels: list[str],
        base_idx: int,
        linhas: list[dict],
        dimensoes_por_label: dict[str, dict],
    ) -> list[dict]:
        if len(base) < 3 or not labels or not (0 <= base_idx < len(labels)):
            return []
        norm_base = cls._normalizar_tamanho_grade(labels[base_idx])
        base_dim = dimensoes_por_label.get(norm_base)
        if not base_dim:
            return []
        saida: list[dict] = []
        for idx, label in enumerate(labels):
            if idx == base_idx or not label:
                continue
            norm_label = cls._normalizar_tamanho_grade(label)
            dim_label = dimensoes_por_label.get(norm_label)
            if not dim_label:
                continue
            pontos = cls._contorno_por_escala_dimensoes_xml(base, base_dim, dim_label)
            if len(cls._sem_fecho_repetido(cls._pontos_float(pontos))) < 3:
                continue
            cor = str(linhas[idx].get("cor") or cls._cor_grade_faltante(label)) if idx < len(linhas) else cls._cor_grade_faltante(label)
            saida.append({
                "tamanho": label,
                "cor": cor,
                "base": False,
                "pontos": pontos,
                "regularizado_por_base": True,
                "sintetico": True,
                "metodo_regularizacao": "dimensoes_xml_base",
                "topologia_base_xml": True,
            })
        return saida

    @classmethod
    def _regularizar_graduacao_importada(cls, elemento: dict) -> dict:
        if not isinstance(elemento, dict):
            return {"aplicado": False, "motivo": "elemento_invalido"}
        if elemento.get("graduacao_regras_exatas"):
            return {"aplicado": False, "motivo": "regras_exatas_presentes"}
        linhas = [dict(linha) for linha in elemento.get("graduacao_tamanhos", []) if isinstance(linha, dict)]
        if len(linhas) < 2:
            return {"aplicado": False, "motivo": "sem_grade"}
        labels = [str(linha.get("tamanho") or linha.get("nome") or "").strip() for linha in linhas]
        base_idx = next((idx for idx, linha in enumerate(linhas) if linha.get("base")), None)
        if base_idx is None:
            base_nome = cls._resolver_tamanho_base(labels, [])
            base_idx = next(
                (idx for idx, label in enumerate(labels) if cls._normalizar_tamanho_grade(label) == cls._normalizar_tamanho_grade(base_nome)),
                len(labels) // 2,
            )
        base_nome = labels[base_idx]
        if not base_nome:
            return {"aplicado": False, "motivo": "sem_base"}

        norm_base = cls._normalizar_tamanho_grade(base_nome)
        contornos_raw = [
            dict(item)
            for item in (elemento.get("graduacao_contornos_importados") or [])
            if isinstance(item, dict)
        ]
        por_nome: dict[str, dict] = {}
        for item in contornos_raw:
            nome = str(item.get("tamanho") or item.get("nome") or "").strip()
            if nome:
                norm_nome = cls._normalizar_tamanho_grade(nome)
                item["base"] = norm_nome == norm_base
                por_nome[norm_nome] = item

        if isinstance(elemento.get("graduacao_contornos_importados"), list):
            for item in elemento.get("graduacao_contornos_importados") or []:
                if not isinstance(item, dict):
                    continue
                nome = str(item.get("tamanho") or item.get("nome") or "").strip()
                item["base"] = bool(nome and cls._normalizar_tamanho_grade(nome) == norm_base)

        dimensoes_xml = elemento.get("graduacao_dimensoes_xml")
        dimensoes_xml = dimensoes_xml if isinstance(dimensoes_xml, dict) else {}
        dimensoes_por_label = {
            cls._normalizar_tamanho_grade(label): dict(valor)
            for label, valor in dimensoes_xml.items()
            if isinstance(valor, dict)
        }
        base_dim = dimensoes_por_label.get(norm_base)

        label_idx_por_norm = {
            cls._normalizar_tamanho_grade(label): idx
            for idx, label in enumerate(labels)
            if label
        }
        base_item = por_nome.get(norm_base)
        base_pontos = cls._pontos_float(base_item.get("pontos") if base_item else elemento.get("pontos"))
        base = cls._sem_fecho_repetido(base_pontos)
        base_sintetizada = False
        base_referencia_nome = ""
        if not base_item:
            referencias = [
                (abs(label_idx_por_norm.get(norm, base_idx) - base_idx), norm, item)
                for norm, item in por_nome.items()
                if cls._pontos_float(item.get("pontos"))
            ]
            referencias.sort(key=lambda item: item[0])
            for _dist, norm_ref, item_ref in referencias:
                ref_dim = dimensoes_por_label.get(norm_ref)
                if not base_dim or not ref_dim:
                    continue
                gerado = cls._contorno_por_escala_dimensoes_xml(
                    cls._pontos_float(item_ref.get("pontos")),
                    ref_dim,
                    base_dim,
                )
                base_gerada = cls._sem_fecho_repetido(gerado)
                if len(base_gerada) >= 3:
                    base = base_gerada
                    base_sintetizada = True
                    base_referencia_nome = str(item_ref.get("tamanho") or item_ref.get("nome") or "").strip()
                    break
        if len(base) < 3:
            return {"aplicado": False, "motivo": "base_invalida"}

        if base_sintetizada or not base_item:
            base_fechada = list(base)
            if base_fechada and cls._distancia_pontos(base_fechada[0], base_fechada[-1]) > 1e-7:
                base_fechada.append(base_fechada[0])
            elemento["pontos"] = base_fechada
            elemento["tamanho_base_sintetizado_de"] = base_referencia_nome
            cls._aplicar_controles_cantos_canvas(elemento)

        contornos_topologia_xml = cls._contornos_topologia_base_por_dimensoes_xml(
            base=base,
            labels=labels,
            base_idx=base_idx,
            linhas=linhas,
            dimensoes_por_label=dimensoes_por_label,
        )

        campos_deslocamento: dict[int, list[tuple[float, float]]] = {}
        usados_raw = 0
        for norm_nome, item in por_nome.items():
            idx = label_idx_por_norm.get(norm_nome)
            if idx is None or idx == base_idx:
                continue
            alvo = cls._sem_fecho_repetido(cls._pontos_float(item.get("pontos")))
            if len(alvo) < 3:
                continue
            alinhado = cls._alinhar_contorno_a_base(base, alvo)
            if len(alinhado) != len(base):
                continue
            campos_deslocamento[idx - base_idx] = [
                (float(alinhado[pos][0]) - float(base[pos][0]), float(alinhado[pos][1]) - float(base[pos][1]))
                for pos in range(len(base))
            ]
            usados_raw += 1

        if usados_raw <= 0 and not base_dim:
            return {"aplicado": False, "motivo": "sem_contorno_referencia"}

        complementos: list[dict] = []
        sintetizados = 0
        for idx, linha in enumerate(linhas):
            label = labels[idx]
            if not label:
                continue
            passo = idx - base_idx
            cor = str(linha.get("cor") or cls._cor_grade_faltante(label))
            norm_label = cls._normalizar_tamanho_grade(label)
            if passo == 0 or norm_label in por_nome:
                continue
            dim_label = dimensoes_por_label.get(norm_label)
            campos_mesmo_lado = [valor for valor in campos_deslocamento if (valor < 0) == (passo < 0)]
            usar_campo = bool(campos_mesmo_lado) or not (base_dim and dim_label)
            campo = cls._interpolar_campos_deslocamento(campos_deslocamento, passo) if usar_campo else None
            if campo and len(campo) == len(base):
                if len(campo) >= 10:
                    campo = cls._suavizar_vetores_circulares(campo, passes=1)
                pontos = [
                    (float(base[pos][0]) + float(dx), float(base[pos][1]) + float(dy))
                    for pos, (dx, dy) in enumerate(campo)
                ]
            else:
                if not base_dim or not dim_label:
                    continue
                pontos = cls._contorno_por_escala_dimensoes_xml(base, base_dim, dim_label)
            if dim_label:
                pontos = cls._ajustar_contorno_para_dimensoes_xml(pontos, dim_label)
            if len(cls._sem_fecho_repetido(cls._pontos_float(pontos))) < 3:
                continue
            sintetizados += 1
            if pontos and cls._distancia_pontos(pontos[0], pontos[-1]) > 1e-7:
                pontos = pontos + [pontos[0]]
            complementos.append({
                "tamanho": label,
                "cor": cor,
                "base": False,
                "pontos": pontos,
                "regularizado_por_base": True,
                "sintetico": True,
                "metodo_regularizacao": "campo_deslocamento_base" if campo else "dimensoes_xml_base",
            })

        nomes_disponiveis = {norm_base} | set(por_nome) | {
            cls._normalizar_tamanho_grade(item.get("tamanho"))
            for item in complementos
        }
        faltantes = [label for label in labels if cls._normalizar_tamanho_grade(label) not in nomes_disponiveis]
        contornos_para_tabela = []
        if contornos_topologia_xml:
            base_para_tabela = {
                "tamanho": base_nome,
                "cor": next((str(linha.get("cor") or "") for linha in linhas if linha.get("base")), "#00d000"),
                "base": True,
                "pontos": list(base) + ([base[0]] if base else []),
            }
            contornos_para_tabela.append(base_para_tabela)
            contornos_para_tabela.extend(dict(item) for item in contornos_topologia_xml)
        else:
            for item in contornos_raw:
                if isinstance(item, dict):
                    contornos_para_tabela.append(dict(item))
            contornos_para_tabela.extend(dict(item) for item in complementos)

        elemento["graduacao_contornos_regularizados_preview"] = complementos
        elemento["graduacao_renderizar_regularizada"] = False
        elemento["graduacao_regras_exatas"] = False
        elemento["graduacao_regras_status"] = (
            "contornos_emf_reais_com_complemento_xml" if complementos else "file_ads_nao_decodificado"
        )
        elemento["graduacao_preferir_tabela_dxdy"] = False
        elemento["graduacao_suavizar_topologia_base"] = False
        resumo_dxdy = cls._aplicar_tabela_dxdy_por_contornos(
            elemento,
            origem=(
                "audaces_xml_dimensoes_topologia_base"
                if contornos_topologia_xml
                else "audaces_emf_contornos_reais_com_complementos"
            ),
            contornos=contornos_para_tabela,
            regras_exatas=False,
            preferir_render=False,
        )
        elemento["graduacao_renderizar_por_tabela_derivada"] = False
        elemento["graduacao_regularizada_por_base"] = {
            "aplicado": bool(complementos or resumo_dxdy.get("aplicado") or base_sintetizada),
            "base": base_nome,
            "tamanhos_gerados": [item.get("tamanho") for item in complementos],
            "tamanhos_reais": [
                item.get("tamanho")
                for item in contornos_raw
                if isinstance(item, dict) and item.get("tamanho")
            ],
            "tamanhos_faltantes": faltantes,
            "metodo": "contornos_reais_emf_com_complementos_por_campo_dxdy",
            "tipo": "complemento_visual_derivado",
            "base_sintetizada_de": base_referencia_nome,
            "campos_medidos": sorted(campos_deslocamento),
            "contornos_referencia": usados_raw,
            "dimensoes_xml_referencia": bool(base_dim),
            "contornos_sinteticos": sintetizados,
            "pontos_base": len(base),
            "aviso": (
                "Contornos existentes do EMF sao preservados; apenas tamanhos ausentes "
                "sao derivados por campo de deslocamento/XML, sem substituir a tabela dx/dy original do file.ads."
            ),
        }
        return elemento["graduacao_regularizada_por_base"]

    @classmethod
    def _mapear_cores_para_grade_xml(
        cls,
        cores_ordenadas: list[str],
        labels_xml: list[str],
        tamanho_base: str | None,
    ) -> dict[str, str]:
        labels = [str(label or "").strip() for label in labels_xml if str(label or "").strip()]
        cores = [str(cor or "").strip().lower() for cor in cores_ordenadas if str(cor or "").strip()]
        if not labels or not cores:
            return {}
        base = cls._tamanho_em_lista(tamanho_base, labels)
        if len(cores) == len(labels):
            labels_visiveis = labels
        elif base in labels and len(cores) <= len(labels) - labels.index(base):
            inicio = labels.index(base)
            labels_visiveis = labels[inicio:inicio + len(cores)]
        else:
            labels_visiveis = labels[:len(cores)]
        return {
            cor: label
            for cor, label in zip(cores, labels_visiveis)
            if cor and label
        }

    @classmethod
    def _grade_detectada_por_cores(
        cls,
        elementos,
        grade_labels: list[str] | None = None,
        tamanho_base: str | None = None,
    ) -> tuple[str, list[dict], str | None] | None:
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

        labels_xml = [str(label or "").strip() for label in (grade_labels or []) if str(label or "").strip()]
        base_xml = cls._resolver_tamanho_base(labels_xml, [tamanho_base])
        if labels_xml:
            cores_ordenadas = [cor for _ordem, _label, cor in ordenadas]
            label_por_cor = cls._mapear_cores_para_grade_xml(cores_ordenadas, labels_xml, base_xml)
            labels_visiveis: list[str] = []
            cor_por_label: dict[str, str] = {}
            for cor in cores_ordenadas:
                label = str(label_por_cor.get(cor) or "").strip()
                if not label:
                    continue
                if label not in labels_visiveis:
                    labels_visiveis.append(label)
                    cor_por_label[label] = cor
            if len(labels_visiveis) >= 2:
                base_visivel = cls._tamanho_em_lista(base_xml, labels_visiveis)
                if not base_visivel:
                    base_visivel = cls._resolver_tamanho_base(labels_visiveis, [])
                linhas = [
                    {
                        "ativo": True,
                        "tamanho": label,
                        "cor": cor_por_label.get(label) or cls._cor_grade_faltante(label),
                        "base": label == base_visivel,
                        "visivel_emf": True,
                    }
                    for label in labels_visiveis
                ]
                linhas, base_visivel = cls._garantir_base_unica_linhas(linhas, base_visivel)
                grade_nome = (
                    f"{labels_visiveis[0]}-{labels_visiveis[-1]}({base_visivel})"
                    if base_visivel
                    else f"{labels_visiveis[0]}-{labels_visiveis[-1]}"
                )
                return grade_nome, linhas, base_visivel

        labels = [label for _ordem, label, _cor in ordenadas]
        candidato_cor = "P" if "P" in labels else "G" if "G" in labels else None
        base = cls._resolver_tamanho_base(labels, [candidato_cor])

        linhas: list[dict] = []
        for _ordem, label, cor in ordenadas:
            linhas.append({"ativo": True, "tamanho": label, "cor": cor, "base": label == base})
        linhas, base = cls._garantir_base_unica_linhas(linhas, base)
        grade_nome = f"{labels[0]}-{labels[-1]}({base})" if base else f"{labels[0]}-{labels[-1]}"
        return grade_nome, linhas, base

    @staticmethod
    def _nome_texto_contido(contorno, textos: list[dict], fallback: str) -> str:
        candidatos: list[tuple[int, str]] = []
        for tx in textos or []:
            texto = " ".join(str(tx.get("texto") or "").strip().split())
            if len(texto) < 2 or "#" in texto:
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

    @classmethod
    def _contorno_candidato_graduacao(
        cls,
        elemento,
        *,
        permitir_quase_fechado: bool,
    ) -> dict | None:
        pontos = cls._pontos_float(getattr(elemento, "pontos", None))
        if len(pontos) < 4:
            return None
        fechado_real = bool(getattr(elemento, "fechado", False))
        pontos_fechados = list(pontos)
        fechado_forcado = False
        if fechado_real:
            if cls._distancia_pontos(pontos_fechados[0], pontos_fechados[-1]) > 1e-7:
                pontos_fechados.append(pontos_fechados[0])
        elif permitir_quase_fechado:
            if len(pontos) < 8:
                return None
            bbox_aberto = cls._bbox_pontos(pontos)
            if not bbox_aberto:
                return None
            diag = cls._diagonal_bbox(bbox_aberto)
            perimetro = AudacesEMFImport._comprimento_polyline(pontos)
            gap = cls._distancia_pontos(pontos[0], pontos[-1])
            max_gap = max(0.35, min(diag * 0.24, perimetro * 0.08))
            if gap > max_gap:
                max_gap_fragmento = max(diag * 1.15, perimetro * 0.35)
                if gap > max_gap_fragmento:
                    return None
                largura = max(float(bbox_aberto[2]) - float(bbox_aberto[0]), 0.0)
                altura = max(float(bbox_aberto[3]) - float(bbox_aberto[1]), 0.0)
                if min(largura, altura) < 1.2:
                    return None
                area_aberta = abs(AudacesEMFImport._area_assinada(pontos))
                area_bbox_aberta = cls._area_bbox(bbox_aberto)
                preenchimento_aberto = area_aberta / area_bbox_aberta if area_bbox_aberta > 1e-9 else 0.0
                if area_aberta < 12.0:
                    return None
                if preenchimento_aberto < 0.22 and not (area_aberta >= 80.0 and len(pontos) >= 40):
                    return None
            pontos_fechados.append(pontos_fechados[0])
            fechado_forcado = True
        else:
            return None

        bbox = cls._bbox_pontos(pontos_fechados)
        if not bbox:
            return None
        area = abs(AudacesEMFImport._area_assinada(pontos_fechados))
        area_bbox = cls._area_bbox(bbox)
        if area < 10.0 or area_bbox <= 1e-9:
            return None
        preenchimento = area / area_bbox
        if preenchimento < 0.08:
            return None
        return {
            "pontos": pontos_fechados,
            "bbox": bbox,
            "area": area,
            "fechado_forcado": fechado_forcado,
        }

    @classmethod
    def _conectar_fragmentos_contorno(cls, itens: list[dict]) -> list[tuple[float, float]]:
        fragmentos = []
        for item in itens:
            pontos = cls._sem_fecho_repetido(cls._pontos_float(item.get("pontos")))
            if len(pontos) < 2:
                continue
            fragmentos.append({
                "pontos": pontos,
                "bbox": cls._bbox_pontos(pontos),
                "area": float(item.get("area") or 0.0),
            })
        if not fragmentos:
            return []

        fragmentos.sort(
            key=lambda item: (
                float("inf") if item.get("bbox") is None else float(item["bbox"][1]),
                float("inf") if item.get("bbox") is None else float(item["bbox"][0]),
                -float(item.get("area") or 0.0),
            )
        )
        pontos = list(fragmentos.pop(0)["pontos"])
        while fragmentos and pontos:
            fim = pontos[-1]
            melhor_idx = 0
            melhor_reverso = False
            melhor_dist = float("inf")
            for idx, fragmento in enumerate(fragmentos):
                pts = fragmento["pontos"]
                dist_inicio = cls._distancia_pontos(fim, pts[0])
                dist_fim = cls._distancia_pontos(fim, pts[-1])
                if dist_inicio < melhor_dist:
                    melhor_idx = idx
                    melhor_reverso = False
                    melhor_dist = dist_inicio
                if dist_fim < melhor_dist:
                    melhor_idx = idx
                    melhor_reverso = True
                    melhor_dist = dist_fim
            proximo = list(fragmentos.pop(melhor_idx)["pontos"])
            if melhor_reverso:
                proximo.reverse()
            if proximo and cls._distancia_pontos(pontos[-1], proximo[0]) <= 1e-7:
                pontos.extend(proximo[1:])
            else:
                pontos.extend(proximo)
        if pontos and cls._distancia_pontos(pontos[0], pontos[-1]) > 1e-7:
            pontos.append(pontos[0])
        return pontos

    @classmethod
    def _fundir_fragmentos_mesmo_tamanho_graduacao(cls, itens: list[dict]) -> dict | None:
        if not itens:
            return None
        if len(itens) == 1:
            return itens[0]

        fechados = [item for item in itens if not item.get("fechado_forcado")]
        if fechados:
            return max(fechados, key=lambda item: (float(item.get("area") or 0.0), len(item.get("pontos") or [])))

        ordenados = sorted(itens, key=lambda item: float(item.get("area") or 0.0), reverse=True)
        maior = ordenados[0]
        maior_bbox = maior.get("bbox")
        if maior_bbox:
            sobreposicoes = [
                cls._sobreposicao_bbox_menor(maior_bbox, item["bbox"])
                for item in ordenados[1:]
                if item.get("bbox")
            ]
            if sobreposicoes and max(sobreposicoes) >= 0.42:
                return maior

        pontos = cls._conectar_fragmentos_contorno(ordenados)
        bbox = cls._bbox_pontos(pontos)
        if not bbox:
            return maior
        area = abs(AudacesEMFImport._area_assinada(pontos))
        area_bbox = cls._area_bbox(bbox)
        preenchimento = area / area_bbox if area_bbox > 1e-9 else 0.0
        if area < max(12.0, float(maior.get("area") or 0.0) * 0.75) or preenchimento < 0.08:
            return maior
        return {
            **maior,
            "pontos": pontos,
            "bbox": bbox,
            "area": area,
            "fechado_forcado": True,
            "fragmentos_fundidos": len(ordenados),
            "_assinaturas_fundidas": {
                assinatura
                for assinatura in (cls._assinatura_elemento(item.get("el")) for item in ordenados)
                if assinatura
            },
            "_score": (0, area, len(pontos)),
        }

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
        *,
        exigir_base_xml: bool = False,
    ) -> list[dict]:
        mapa_cores = cls._mapa_grade_por_cor(grade_detectada)
        cores_grade = set(mapa_cores)
        candidatos = []
        for el in elementos or []:
            subtipo = str(getattr(el, "metadados", {}).get("subtipo_audaces") or "")
            if subtipo not in {"contorno", "costura", "linha_interna", "costura_ou_linha_tecnica"}:
                continue
            cor = str(getattr(el, "cor", "") or "").strip().lower()
            permitir_quase_fechado = bool(cor in cores_grade)
            candidato = cls._contorno_candidato_graduacao(el, permitir_quase_fechado=permitir_quase_fechado)
            if not candidato:
                continue
            if not getattr(el, "fechado", False) and cor not in cores_grade:
                continue
            candidatos.append({
                "el": el,
                "bbox": candidato["bbox"],
                "area": candidato["area"],
                "cor": cor,
                "pontos": candidato["pontos"],
                "fechado_forcado": candidato["fechado_forcado"],
            })

        grupos: list[dict] = []
        for item in sorted(candidatos, key=lambda it: (-it["area"], it["bbox"][1], it["bbox"][0])):
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
            membros_brutos = grupo["membros"]
            itens_por_tamanho: dict[str, list[dict]] = {}
            for item in membros_brutos:
                linha = mapa_cores.get(item["cor"], {})
                nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
                chave = cls._normalizar_tamanho_grade(nome or item["cor"] or str(len(itens_por_tamanho)))
                score = (
                    0 if item.get("fechado_forcado") else 1,
                    float(item.get("area") or 0.0),
                    len(item.get("pontos") or []),
                )
                itens_por_tamanho.setdefault(chave, []).append({**item, "_score": score})
            membros = [
                fundido
                for fundido in (
                    cls._fundir_fragmentos_mesmo_tamanho_graduacao(itens)
                    for itens in itens_por_tamanho.values()
                )
                if fundido is not None
            ]
            if not membros:
                continue
            base_item = None
            for item in membros:
                if getattr(item["el"], "metadados", {}).get("xml_pattern_index") is not None:
                    base_item = item
                    break
            if base_item is None:
                for item in membros:
                    linha = mapa_cores.get(item["cor"])
                    if linha and linha.get("base"):
                        base_item = item
                        break
            if exigir_base_xml and (
                base_item is None
                or getattr(base_item["el"], "metadados", {}).get("xml_pattern_index") is None
            ):
                continue
            if base_item is None:
                ordenados_area = sorted(membros, key=lambda it: it["area"])
                base_item = ordenados_area[len(ordenados_area) // 2]

            contornos = []
            for item in sorted(membros, key=lambda it: int(mapa_cores.get(it["cor"], {}).get("_ordem", 999))):
                linha = mapa_cores.get(item["cor"], {})
                nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
                if not nome:
                    nome = f"T{len(contornos) + 1}"
                pontos = [(float(x), float(y)) for x, y in item["pontos"]]
                contornos.append({
                    "tamanho": nome,
                    "cor": item["el"].cor or linha.get("cor") or "#ffcc00",
                    "base": item is base_item,
                    "pontos": pontos,
                    "assinatura": cls._assinatura_elemento(item["el"]),
                    "assinaturas_fundidas": sorted(item.get("_assinaturas_fundidas") or []),
                    "fechado_forcado": bool(item.get("fechado_forcado")),
                    "fragmentos_fundidos": int(item.get("fragmentos_fundidos") or 1),
                })
            if base_item.get("fechado_forcado"):
                base_item["el"].pontos = list(base_item["pontos"])
                base_item["el"].fechado = True
                base_item["el"].bbox = cls._bbox_pontos(base_item["pontos"])
            base_item["el"].metadados["subtipo_audaces"] = "contorno"
            for item in membros:
                if item is not base_item:
                    if item["el"].metadados.get("xml_pattern_index") is not None:
                        item["el"].metadados["subtipo_audaces"] = "contorno"
                    else:
                        item["el"].metadados["subtipo_audaces"] = "graduacao_importada"
                    if item.get("fechado_forcado"):
                        item["el"].metadados["contorno_quase_fechado_graduacao"] = True
            saida.append({
                "base": base_item["el"],
                "assinatura_base": cls._assinatura_elemento(base_item["el"]),
                "assinaturas_membros": {
                    assinatura
                    for item in membros
                    for assinatura in (
                        [cls._assinatura_elemento(item["el"])]
                        + list(item.get("_assinaturas_fundidas") or [])
                    )
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
        diagnostico_file_ads: dict | None = None,
        xml_doc=None,
        regularizar_graduacao_importada: bool = True,
    ) -> dict:
        regras_exatas = bool((diagnostico_file_ads or {}).get("regras_graduacao_decodificadas"))
        motivo_regras = str((diagnostico_file_ads or {}).get("motivo_regras_graduacao") or "")
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
            nome_xml = str(getattr(contorno, "metadados", {}).get("xml_pattern_name") or "").strip()
            nome_detectado = nome_xml or cls._nome_texto_contido(contorno, getattr(emf_doc, "textos", []), nome_base)
            xml_pattern_index = getattr(contorno, "metadados", {}).get("xml_pattern_index")
            peca_xml = None
            if xml_doc is not None and xml_pattern_index is not None:
                try:
                    idx_xml = int(xml_pattern_index)
                    pecas_xml = list(getattr(xml_doc, "pecas", []) or [])
                    if 0 <= idx_xml < len(pecas_xml):
                        peca_xml = pecas_xml[idx_xml]
                except (TypeError, ValueError):
                    peca_xml = None
            fio = cls._detectar_fio_do_contorno(contorno, getattr(emf_doc, "elementos", []))
            bbox = cls._bbox_pontos([(float(x), float(y)) for x, y in contorno.pontos])
            ponto_texto = None
            if bbox:
                ponto_texto = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
            mapa[assinatura] = {
                "nome": nome_detectado,
                "nome_origem_texto": nome_detectado != nome_base,
                "xml_pattern_index": xml_pattern_index,
                "xml_pattern_name": nome_xml,
                "xml_pattern_sizes": cls._dimensoes_tamanhos_peca_xml(peca_xml) if peca_xml is not None else {},
                "molde_id": f"emf-{idx:03d}",
                "fio": fio,
                "ponto_texto": ponto_texto,
                "grupo": grupos_por_base.get(assinatura),
            }
        contornos_com_meta = [
            (contorno, mapa.get(cls._assinatura_elemento(contorno)))
            for contorno in contornos
            if mapa.get(cls._assinatura_elemento(contorno))
        ]

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
                subtipo = str(el.get("subtipo_audaces") or "").strip()
                if el.get("origem") == "audaces_emf" and subtipo in {"linha_interna", "costura"}:
                    meta_el = el.setdefault("metadados", {})
                    el["ocultar_quando_graduacao_oculta"] = True
                    meta_el["ocultar_quando_graduacao_oculta"] = True
                    meta_el["audaces_residuo_importado"] = True
                    pontos_el = cls._pontos_float(el.get("pontos"))
                    if pontos_el:
                        for contorno, meta_contorno in contornos_com_meta:
                            if (
                                isinstance(meta_contorno, dict)
                                and contorno.pontos
                                and AudacesEMFImport._ponto_em_poligono(pontos_el[0], contorno.pontos)
                            ):
                                molde_id = str(meta_contorno.get("molde_id") or "").strip()
                                if molde_id:
                                    el["ocultar_graduacao_molde_id"] = molde_id
                                    meta_el["ocultar_graduacao_molde_id"] = molde_id
                                break
                continue
            meta = mapa.get(cls._assinatura_elemento(el))
            if not meta:
                continue
            el["nome_molde"] = meta["nome"]
            el["molde_id"] = meta["molde_id"]
            el["mostrar_nome"] = bool(meta.get("nome_origem_texto"))
            if meta.get("xml_pattern_index") is not None:
                el["audaces_xml_pattern_index"] = meta.get("xml_pattern_index")
            if meta.get("xml_pattern_name"):
                el["audaces_xml_pattern_name"] = meta.get("xml_pattern_name")
            if meta.get("xml_pattern_sizes"):
                el["graduacao_dimensoes_xml"] = dict(meta.get("xml_pattern_sizes") or {})
            cls._aplicar_controles_cantos_canvas(el)
            if meta.get("ponto_texto"):
                el["ponto_texto"] = meta["ponto_texto"]
            grade_local = grade_detectada
            peca_base_xml = None
            if xml_doc is not None and meta.get("xml_pattern_index") is not None:
                try:
                    idx_xml = int(meta.get("xml_pattern_index"))
                    pecas_xml = list(getattr(xml_doc, "pecas", []) or [])
                    if 0 <= idx_xml < len(pecas_xml):
                        peca_base_xml = getattr(pecas_xml[idx_xml], "tamanho_base", None)
                except (TypeError, ValueError):
                    peca_base_xml = None
            if grade_local:
                grade_nome, linhas, base = grade_local
                el["graduacao_grade_nome"] = grade_nome
                el["graduacao_tamanhos"] = [dict(linha) for linha in linhas]
                el["graduacao_tamanhos_ativos"] = [
                    str(linha.get("tamanho") or "")
                    for linha in linhas
                    if linha.get("ativo", True)
                ]
                el["tamanho_base_detectado"] = base
                el["tamanho_base"] = base
                el["espessura_graduacao"] = max(1.35, float(el.get("espessura", 1.0) or 1.0))
                el["graduacao_regras_exatas"] = regras_exatas
                el["graduacao_regras_status"] = "file_ads_decodificado" if regras_exatas else "file_ads_nao_decodificado"
                if motivo_regras:
                    el["graduacao_regras_motivo"] = motivo_regras
            grupo = meta.get("grupo")
            if isinstance(grupo, dict) and grupo.get("contornos"):
                base_norm = cls._normalizar_tamanho_grade(base) if grade_local else ""
                el["graduacao_contornos_importados"] = [
                    {
                        "tamanho": item.get("tamanho"),
                        "cor": item.get("cor"),
                        "base": (
                            cls._normalizar_tamanho_grade(item.get("tamanho")) == base_norm
                            if base_norm
                            else bool(item.get("base"))
                        ),
                        "pontos": list(item.get("pontos") or []),
                    }
                    for item in grupo.get("contornos", [])
                ]
                if regularizar_graduacao_importada:
                    cls._regularizar_graduacao_importada(el)
                else:
                    el["graduacao_contornos_regularizados_preview"] = []
                    el["graduacao_renderizar_regularizada"] = False
                    el["graduacao_renderizar_por_tabela_derivada"] = False
                    el["graduacao_preferir_tabela_dxdy"] = False
                    el["graduacao_regularizacao_bloqueada"] = True
                el["mostrar_graduacao"] = True
                el["metadados"].setdefault("graduacao_importada_origem", "emf_contornos_coloridos")
                el["metadados"].setdefault(
                    "graduacao_regras_origem",
                    "file_ads" if regras_exatas else "emf_contornos_coloridos_sem_tabela_file_ads",
                )
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
    @staticmethod
    def _desativar_overlays_importacao_inicial(elementos_canvas: list[dict]) -> list[dict]:
        for el in elementos_canvas or []:
            if not isinstance(el, dict) or not bool(el.get("molde")):
                continue
            origem = str(el.get("origem") or el.get("metadados", {}).get("origem") or "")
            if origem.startswith("audaces_"):
                el["mostrar_controles"] = False
                el["mostrar_numeros"] = False
        return elementos_canvas

    @classmethod
    def _filtrar_canvas_para_moldes_reais(cls, elementos_canvas: list[dict]) -> list[dict]:
        """Remove residuos soltos do EMF quando o XML ja definiu os moldes reais."""
        moldes: list[dict] = []
        for el in elementos_canvas or []:
            if not isinstance(el, dict) or not bool(el.get("molde")):
                continue
            moldes.append(el)
        return cls._desativar_overlays_importacao_inicial(moldes)

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

    @staticmethod
    def _dimensoes_tamanhos_peca_xml(peca) -> dict[str, dict]:
        if peca is None:
            return {}
        base = str(getattr(peca, "tamanho_base", "") or "").strip().strip('"').strip("'")
        saida: dict[str, dict] = {}
        for tamanho in getattr(peca, "tamanhos", []) or []:
            nome = str(getattr(tamanho, "tamanho", "") or "").strip()
            if not nome:
                continue
            largura = float(getattr(tamanho, "largura", 0.0) or 0.0)
            altura = float(getattr(tamanho, "altura", 0.0) or 0.0)
            if largura <= 0 or altura <= 0:
                continue
            saida[nome] = {
                "largura": largura,
                "altura": altura,
                "perimetro": float(getattr(tamanho, "perimetro", 0.0) or 0.0),
                "area": float(getattr(tamanho, "area", 0.0) or 0.0),
                "base": bool(nome.strip().upper() == base.strip().upper()) if base else False,
            }
        return saida

    @staticmethod
    def _xml_doc_adjacente_para_emf(emf_path: Path):
        xml_path = emf_path.with_suffix(".xml")
        if xml_path.exists():
            try:
                return AudacesXMLImport.abrir(xml_path), str(xml_path), "xml_adjacente"
            except Exception:
                pass
        for sufixo in (".adsx", ".amkx"):
            pacote = emf_path.with_suffix(sufixo)
            if not pacote.exists():
                continue
            try:
                with ZipFile(pacote) as zipf:
                    nomes = {nome.lower(): nome for nome in zipf.namelist()}
                    data_xml = nomes.get("data.xml")
                    if not data_xml:
                        continue
                    bruto = zipf.read(data_xml)
                with TemporaryDirectory() as td:
                    temp_xml = Path(td) / "data.xml"
                    temp_xml.write_bytes(bruto)
                    return AudacesXMLImport.abrir(temp_xml), str(pacote), "adsx_data_xml"
            except (BadZipFile, KeyError, OSError):
                continue
            except Exception:
                continue
        return None, None, None

    @staticmethod
    def _diagnostico_file_ads_adjacente_para_emf(emf_path: Path) -> dict:
        for sufixo in (".adsx", ".amkx"):
            pacote = emf_path.with_suffix(sufixo)
            if not pacote.exists():
                continue
            try:
                with ZipFile(pacote) as zipf:
                    nomes_zip = {nome.replace("\\", "/").lower(): nome for nome in zipf.namelist()}
                    candidatos: list[str] = []
                    index_nome = nomes_zip.get("index.json")
                    if index_nome:
                        try:
                            index = json.loads(zipf.read(index_nome).decode("utf-8", errors="ignore"))
                            arquivos = index.get("files") if isinstance(index, dict) else {}
                            nome_binario = arquivos.get("file") if isinstance(arquivos, dict) else None
                            if isinstance(nome_binario, str) and nome_binario.strip():
                                candidatos.append(nome_binario.replace("\\", "/").lower())
                        except Exception:
                            pass
                    candidatos.extend(["file.ads", "file.amk"])
                    for candidato in candidatos:
                        nome_real = nomes_zip.get(candidato.replace("\\", "/").lower())
                        if not nome_real:
                            continue
                        relatorio = ADSGeometryDecoder(zipf.read(nome_real)).analisar()
                        relatorio["arquivo_binario"] = nome_real
                        relatorio["pacote"] = str(pacote)
                        relatorio.setdefault("regras_graduacao_decodificadas", False)
                        relatorio.setdefault("pontos_controle_decodificados", False)
                        relatorio.setdefault("tabela_graduacao", {})
                        return relatorio
            except (BadZipFile, KeyError, OSError):
                continue
            except Exception as exc:
                return {
                    "assinatura": None,
                    "arquivo_binario": "",
                    "pacote": str(pacote),
                    "regras_graduacao_decodificadas": False,
                    "pontos_controle_decodificados": False,
                    "tabela_graduacao": {},
                    "motivo_regras_graduacao": f"falha ao ler file.ads adjacente: {exc}",
                }
        return {
            "assinatura": None,
            "arquivo_binario": "",
            "pacote": "",
            "regras_graduacao_decodificadas": False,
            "pontos_controle_decodificados": False,
            "tabela_graduacao": {},
            "motivo_regras_graduacao": "pacote ADSX/AMKX adjacente nao encontrado",
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
                elemento = {
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
                    "render_smooth": True,
                    "renderizacao": "curva_suave_importada",
                    "metadados": {"origem": "audaces_emf_xml", "importado_como_molde_real": True, "subtipo_audaces": "contorno"},
                    "cor": "#ff7b00",
                    "bloqueado": False,
                }
                AudacesPairImport._aplicar_controles_cantos_canvas(elemento)
                elementos.append(elemento)
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
        grade_labels, grade_base_xml = cls._grade_xml_doc(xml_doc)
        grade_detectada = cls._grade_detectada_por_cores(
            emf_doc.elementos,
            grade_labels=grade_labels,
            tamanho_base=grade_base_xml,
        )
        grupos_graduados = cls._agrupar_contornos_graduados_emf(
            emf_doc.elementos,
            grade_detectada,
            exigir_base_xml=True,
        )
        assinaturas_contornos_xml = {
            cls._assinatura_elemento(el)
            for el in emf_doc.elementos
            if (
                getattr(el, "fechado", False)
                and getattr(el, "metadados", {}).get("xml_pattern_index") is not None
            )
        }
        assinaturas_bases_grupos: set[tuple] = set()
        assinaturas_graduacao_ocultas: set[tuple] = set()
        assinaturas_grupos: set[tuple] = set()
        for grupo in grupos_graduados:
            assinatura_base = grupo.get("assinatura_base")
            if assinatura_base:
                assinaturas_bases_grupos.add(assinatura_base)
            membros = {
                assinatura
                for assinatura in (grupo.get("assinaturas_membros") or set())
                if assinatura
            }
            assinaturas_grupos.update(membros)
            assinaturas_graduacao_ocultas.update(membros)
            if assinatura_base in assinaturas_graduacao_ocultas:
                assinaturas_graduacao_ocultas.remove(assinatura_base)
        assinaturas_graduacao_ocultas.difference_update(
            assinatura for assinatura in assinaturas_contornos_xml if assinatura
        )
        elementos_canvas = AudacesEMFImport(b"", emf_path).converter_para_elementos_guimma(emf_doc)
        if assinaturas_graduacao_ocultas:
            elementos_canvas = [
                el
                for el in elementos_canvas
                if cls._assinatura_elemento(el) not in assinaturas_graduacao_ocultas
            ]
        diagnostico_file_ads = cls._diagnostico_file_ads_adjacente_para_emf(Path(emf_path))
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
        }
        contornos = [grupo["base"] for grupo in grupos_graduados if grupo.get("base") is not None]
        contornos.extend(
            el
            for el in emf_doc.elementos
            if (
                el.fechado
                and len(el.pontos) >= 4
                and el.metadados.get("subtipo_audaces") == "contorno"
                and cls._assinatura_elemento(el) not in assinaturas_bases_grupos
            )
        )
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

        metadados_moldes = cls._aplicar_metadados_moldes_emf(
            elementos_canvas,
            contornos,
            emf_doc,
            Path(emf_path).name,
            grade_detectada,
            grupos_graduados,
            diagnostico_file_ads,
            xml_doc,
            regularizar_graduacao_importada=False,
        )
        elementos_canvas = cls._filtrar_canvas_para_moldes_reais(elementos_canvas)
        calibracao_dimensoes = cls._calibrar_moldes_por_dimensoes_xml(elementos_canvas, doc)
        centralizacao_canvas = cls._centralizar_elementos_canvas_no_zero(elementos_canvas, doc)
        depois.update({
            **metadados_moldes,
            "calibracao_dimensoes_xml": calibracao_dimensoes,
            "elementos_canvas_final": len(elementos_canvas),
        })

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
            "contornos_graduacao_ocultos": depois["contornos_graduacao_ocultos"],
            "grupos_graduados_detectados": depois["grupos_graduados_detectados"],
            "bounds_emf": emf_doc.bounds,
            "escala": dict(emf_doc.relatorio.get("escala", {})),
            "escala_manual_aplicada": fator_escala_final,
            "escala_x_aplicada": fator_escala_x,
            "escala_y_aplicada": fator_escala_y,
            "diagnostico_escala": diagnostico_escala,
            "diagnostico_file_ads": diagnostico_file_ads,
            "calibracao_dimensoes_xml": calibracao_dimensoes,
            "graduacao_regras_exatas": bool(diagnostico_file_ads.get("regras_graduacao_decodificadas")),
            "graduacao_regras_motivo": str(diagnostico_file_ads.get("motivo_regras_graduacao") or ""),
            "grade_detectada": {
                "nome": grade_detectada[0],
                "tamanho_base": grade_detectada[2],
                "quantidade_tamanhos": len(grade_detectada[1]),
            } if grade_detectada else None,
            "fios_detectados": metadados_moldes.get("fios_detectados", 0),
            "fator_escala_final": fator_escala_final,
            "unidade_resultado": "cm_calibrado_por_xml",
            "centralizacao_importacao": {
                "aplicado": False,
                "dx": 0.0,
                "dy": 0.0,
                "bbox_original": None,
                "canvas_visivel": centralizacao_canvas,
            },
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
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["elementos_canvas"] = elementos_canvas
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_origem"] = "moldes_reais_processados"
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_moldes_renderizados"] = len(
                [el for el in elementos_canvas if isinstance(el, dict) and el.get("molde")]
            )
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_elementos_emf_renderizados"] = len(elementos_canvas)
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
        return projeto

    @classmethod
    def importar_apenas_emf(cls, emf_path: str | Path, projeto: Projeto) -> Projeto:
        emf_path = Path(emf_path)
        nome_arquivo = emf_path.stem or emf_path.name
        emf_doc = AudacesEMFImport.abrir(emf_path, reconstruir_curvas=False, suavizar_curvas=False)
        xml_adj, xml_adj_origem, xml_adj_tipo = cls._xml_doc_adjacente_para_emf(emf_path)
        diagnostico_file_ads = cls._diagnostico_file_ads_adjacente_para_emf(emf_path)
        diagnostico_escala = {
            "metodo": "fallback_fixo",
            "motivo": "sem_xml_adjacente",
            "fator": cls.ESCALA_CALIBRACAO_EMF_DIRETO,
            "fator_x": cls.ESCALA_CALIBRACAO_EMF_DIRETO,
            "fator_y": cls.ESCALA_CALIBRACAO_EMF_DIRETO,
        }
        if xml_adj is not None:
            parser_pre_escala = AudacesEMFImport(b"", emf_path)
            unidos_pre_escala = parser_pre_escala._unir_segmentos_em_contornos(emf_doc.elementos)
            fatores_escala, diagnostico_escala = cls._fator_escala_por_xml(xml_adj, unidos_pre_escala)
        else:
            fatores_escala = (cls.ESCALA_CALIBRACAO_EMF_DIRETO, cls.ESCALA_CALIBRACAO_EMF_DIRETO)
        fator_escala_x, fator_escala_y = float(fatores_escala[0]), float(fatores_escala[1])
        fator_escala_final = (fator_escala_x + fator_escala_y) / 2.0
        cls._aplicar_escala_emf_doc(emf_doc, fatores_escala)
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
            cls._classificar_contornos_unidos(unidos, xml_adj)
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
        grade_labels, grade_base_xml = cls._grade_xml_doc(xml_adj)
        grade_detectada = cls._grade_detectada_por_cores(
            emf_doc.elementos,
            grade_labels=grade_labels,
            tamanho_base=grade_base_xml,
        )
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
        def ordem_contorno(el) -> tuple:
            try:
                idx_xml = int(el.metadados.get("xml_pattern_index", 10**9))
            except (TypeError, ValueError):
                idx_xml = 10**9
            return (
                idx_xml,
                min((p[1] for p in el.pontos), default=0.0),
                min((p[0] for p in el.pontos), default=0.0),
                -abs(AudacesEMFImport._area_assinada(el.pontos)),
            )

        contornos = sorted(contornos, key=ordem_contorno)
        for idx, el in enumerate(contornos, start=1):
            nome_molde = str(el.metadados.get("xml_pattern_name") or "").strip() or cls._nome_texto_contido(
                el,
                emf_doc.textos,
                f"K{idx}",
            )
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
            diagnostico_file_ads,
            xml_adj,
        )
        cls._desativar_overlays_importacao_inicial(elementos_canvas)
        calibracao_dimensoes = cls._calibrar_moldes_por_dimensoes_xml(elementos_canvas, doc)
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
            "calibracao_dimensoes_xml": calibracao_dimensoes,
            **metadados_moldes,
        }
        nomes_moldes_origem = (
            "xml_adjacente"
            if any(str(getattr(el, "metadados", {}).get("xml_pattern_name") or "").strip() for el in contornos)
            else (
                "texto_emf_decodificado"
                if any(str(tx.get("texto") or "").strip() for tx in getattr(emf_doc, "textos", []) or [])
                else "indice_temporario_sem_strings_texto_no_emf"
            )
        )

        projeto.preferencias_usuario["audaces_emf_importacao"] = {
            "origem": "audaces_emf",
            "emf_path": str(emf_path),
            "xml_adjacente_usado": bool(xml_adj is not None),
            "xml_adjacente_origem": xml_adj_origem,
            "xml_adjacente_tipo": xml_adj_tipo,
            "nome_arquivo": nome_arquivo,
            "elementos_canvas": elementos_canvas,
            "relatorio": dict(emf_doc.relatorio),
            "diagnostico_file_ads": diagnostico_file_ads,
            "calibracao_dimensoes_xml": calibracao_dimensoes,
            "graduacao_regras_exatas": bool(diagnostico_file_ads.get("regras_graduacao_decodificadas")),
            "graduacao_regras_motivo": str(diagnostico_file_ads.get("motivo_regras_graduacao") or ""),
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
            "escala_x_aplicada": fator_escala_x,
            "escala_y_aplicada": fator_escala_y,
            "diagnostico_escala": diagnostico_escala,
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
            "nomes_moldes_origem": nomes_moldes_origem,
            "fator_escala_final": fator_escala_final,
            "unidade_resultado": "cm_calibrado_por_xml_adjacente" if xml_adj is not None else "cm_calibrado_por_referencia_emf_direto",
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
