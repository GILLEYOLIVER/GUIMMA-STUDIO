from __future__ import annotations

import base64
import json
import traceback
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from core.projeto import Documento, Projeto
from formats.ads_decoder import ADSGeometryDecoder
from formats.adsx_image_trace import tamanho_preview_base64


class ADSXImportError(Exception):
    pass


def _safe_float(valor: Any) -> float | None:
    if valor is None:
        return None
    try:
        return float(str(valor).strip().replace(",", "."))
    except ValueError:
        return None


def _safe_int(valor: Any) -> int | None:
    if valor is None:
        return None
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except ValueError:
        return None


@dataclass
class ADSXArquivoPreservado:
    nome: str
    conteudo_base64: str
    tamanho_bytes: int
    tipo: str


@dataclass
class ADSXMoldInfo:
    nome: str
    tamanho: str | None
    quantidade: int | None
    area: float | None
    perimetro: float | None
    largura: float | None
    altura: float | None
    metadados: dict[str, Any] = field(default_factory=dict)


@dataclass
class ADSXDocument:
    caminho_original: str
    nome_arquivo: str
    tipo_pacote: str
    index_json: dict[str, Any]
    data_xml_texto: str
    data_xml_normalizado: dict[str, Any]
    file_information_json: dict[str, Any]
    moldes: list[ADSXMoldInfo]
    arquivos_preservados: dict[str, ADSXArquivoPreservado]
    avisos: list[str]


class ADSXIO:
    _ALIAS_CHAVES = {
        "nome": {"nome", "name", "model", "modelo", "parte", "part", "pattern", "piece", "molde"},
        "tamanho": {"tamanho", "size", "grade"},
        "quantidade": {"quantidade", "quantity", "qty", "qtd"},
        "area": {"area", "área"},
        "perimetro": {"perimetro", "perímetro", "perimeter"},
        "largura": {"largura", "width"},
        "altura": {"altura", "height"},
    }

    @classmethod
    def abrir(cls, caminho: str | Path) -> ADSXDocument:
        origem = Path(caminho)
        if not origem.exists():
            raise ADSXImportError("Arquivo ADSX não encontrado.")
        if not origem.is_file():
            raise ADSXImportError("Arquivo ADSX inválido.")

        avisos: list[str] = []
        arquivos_preservados: dict[str, ADSXArquivoPreservado] = {}
        diagnostico_file_ads: dict[str, Any] = {}
        file_information_json: dict[str, Any] = {}
        tipo_pacote = origem.suffix.lower().lstrip(".") or "adsx"
        try:
            with ZipFile(origem, mode="r") as pacote:
                nomes_no_zip = set(pacote.namelist())

                index_json = cls._ler_index_json(pacote, nomes_no_zip, avisos, arquivos_preservados)
                data_xml_texto, data_xml_normalizado = cls._ler_data_xml(pacote, nomes_no_zip, avisos, arquivos_preservados)
                file_information_json = cls._ler_file_information_json(pacote, nomes_no_zip, avisos, arquivos_preservados)
                moldes = cls._extrair_moldes_do_xml(data_xml_normalizado.get("xml", {}))
                if not moldes:
                    moldes = cls._extrair_moldes_do_file_information(file_information_json)
                diagnostico_file_ads = cls._ler_binario_audaces(
                    pacote, nomes_no_zip, avisos, arquivos_preservados, data_xml_normalizado, index_json
                )
                cls._ler_previews(pacote, nomes_no_zip, avisos, arquivos_preservados)
                cls._ler_ids_json(pacote, nomes_no_zip, avisos, arquivos_preservados)
        except BadZipFile as exc:
            raise ADSXImportError("Arquivo ADSX inválido: o arquivo não é um pacote ZIP reconhecido.") from exc
        except ADSXImportError:
            raise
        except Exception as exc:
            raise ADSXImportError("Não foi possível abrir o pacote ADSX.") from exc

        if not moldes:
            avisos.append("O ADSX foi importado, mas a geometria binária Audaces ainda não foi convertida para edição direta.")
        data_xml_normalizado["diagnostico_file_ads"] = diagnostico_file_ads

        return ADSXDocument(
            caminho_original=str(origem),
            nome_arquivo=origem.name,
            tipo_pacote=tipo_pacote,
            index_json=index_json,
            data_xml_texto=data_xml_texto,
            data_xml_normalizado=data_xml_normalizado,
            file_information_json=file_information_json,
            moldes=moldes,
            arquivos_preservados=arquivos_preservados,
            avisos=avisos,
        )

    @classmethod
    def importar_para_projeto(cls, caminho: str | Path, projeto: Projeto) -> Projeto:
        doc = cls.abrir(caminho)
        nome_base = Path(doc.nome_arquivo).stem
        projeto.nome = nome_base or projeto.nome

        tamanhos = sorted({m.tamanho for m in doc.moldes if m.tamanho})
        placeholders = []
        for molde_info in doc.moldes:
            placeholders.append(
                {
                    "id": str(uuid4()),
                    "nome": molde_info.nome,
                    "origem": doc.tipo_pacote,
                    "tamanho": molde_info.tamanho,
                    "quantidade": molde_info.quantidade,
                    "area": molde_info.area,
                    "perimetro": molde_info.perimetro,
                    "largura": molde_info.largura,
                    "altura": molde_info.altura,
                    "geometria_convertida": False,
                    "geometria_adsx_nao_convertida": True,
                    "metadados_adsx": dict(molde_info.metadados),
                }
            )
        previews = [
            nome
            for nome, arquivo in doc.arquivos_preservados.items()
            if arquivo.tipo in {"preview_image_jpg", "preview_image_png"}
        ]
        preview_dimensoes = cls._dimensoes_previews(doc)
        binario_nome = next(
            (
                nome
                for nome, arquivo in doc.arquivos_preservados.items()
                if arquivo.tipo in {"audaces_binary_ads", "audaces_binary_amk"}
            ),
            "",
        )
        diagnostico_ads = dict(doc.data_xml_normalizado.get("diagnostico_file_ads", {}))
        elementos_canvas = list(diagnostico_ads.get("elementos_canvas", []) or [])
        geometry_confidence = str(diagnostico_ads.get("geometry_confidence", "none"))
        geometria_convertida = geometry_confidence == "high" and bool(elementos_canvas)
        geometria_aproximada = False
        projeto.preferencias_usuario["adsx_importacao"] = {
            "tipo_pacote": doc.tipo_pacote,
            "nome_projeto": projeto.nome,
            "tamanhos": tamanhos,
            "moldes": placeholders,
            "preview_disponivel": bool(previews),
            "previews": previews,
            "preview_dimensoes_px": preview_dimensoes,
            "binario_audaces": binario_nome,
            "diagnostico_file_ads": diagnostico_ads,
            "geometry_confidence": geometry_confidence,
            "geometria_convertida": geometria_convertida,
            "geometria_aproximada": geometria_aproximada,
            "preview_apenas_referencia": bool(previews) and not geometria_convertida,
            "motivo_sem_geometria": str(diagnostico_ads.get("motivo") or ""),
            "elementos_canvas": elementos_canvas,
        }
        if not projeto.documentos:
            projeto.documentos.append(Documento(nome="Documento 1"))
        projeto.documentos[0].moldes = []

        cls._preservar_pacote_original(doc, projeto)
        return projeto

    @classmethod
    def _dimensoes_previews(cls, doc: ADSXDocument) -> dict[str, dict[str, int]]:
        dimensoes: dict[str, dict[str, int]] = {}
        for nome, arquivo in doc.arquivos_preservados.items():
            if arquivo.tipo not in {"preview_image_jpg", "preview_image_png"}:
                continue
            largura, altura = tamanho_preview_base64(arquivo.conteudo_base64)
            if largura > 0 and altura > 0:
                dimensoes[nome] = {"largura": largura, "altura": altura}
        return dimensoes

    @classmethod
    def _ler_index_json(
        cls,
        pacote: ZipFile,
        nomes_no_zip: set[str],
        avisos: list[str],
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
    ) -> dict[str, Any]:
        if "index.json" not in nomes_no_zip:
            avisos.append("index.json inválido ou ilegível.")
            return {}
        bruto = pacote.read("index.json")
        cls._preservar_bytes("index.json", "metadata_json", bruto, arquivos_preservados)
        for enc in ("utf-8", "latin-1", "iso-8859-1"):
            try:
                return json.loads(bruto.decode(enc))
            except Exception:
                continue
        avisos.append("index.json inválido ou ilegível.")
        return {}

    @classmethod
    def _ler_data_xml(
        cls,
        pacote: ZipFile,
        nomes_no_zip: set[str],
        avisos: list[str],
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
    ) -> tuple[str, dict[str, Any]]:
        if "data.xml" not in nomes_no_zip:
            avisos.append("O arquivo data.xml não foi encontrado. Alguns metadados não poderão ser importados.")
            return "", {}
        bruto = pacote.read("data.xml")
        cls._preservar_bytes("data.xml", "metadata_xml", bruto, arquivos_preservados)
        texto = ""
        for enc in ("utf-8", "iso-8859-1", "latin-1"):
            try:
                texto = bruto.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not texto:
            avisos.append("O arquivo data.xml não foi encontrado.")
            return "", {}
        try:
            raiz = ET.fromstring(texto)
            xml_dict = cls._xml_to_dict(raiz)
            return texto, cls._normalizar_metadados(xml_dict)
        except Exception:
            avisos.append("data.xml inválido ou ilegível.")
            return texto, {}

    @classmethod
    def _ler_file_information_json(
        cls,
        pacote: ZipFile,
        nomes_no_zip: set[str],
        avisos: list[str],
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
    ) -> dict[str, Any]:
        caminho_info = "fileInformation.json"
        if caminho_info not in nomes_no_zip:
            return {}
        bruto = pacote.read(caminho_info)
        cls._preservar_bytes(caminho_info, "metadata_json", bruto, arquivos_preservados)
        for enc in ("utf-8", "latin-1", "iso-8859-1"):
            try:
                return json.loads(bruto.decode(enc))
            except Exception:
                continue
        avisos.append("fileInformation.json invalido ou ilegivel.")
        return {}

    @classmethod
    def _ler_binario_audaces(
        cls,
        pacote: ZipFile,
        nomes_no_zip: set[str],
        avisos: list[str],
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
        data_xml_normalizado: dict[str, Any],
        index_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        candidatos: list[str] = []
        if isinstance(index_json, dict):
            arquivos = index_json.get("files")
            if isinstance(arquivos, dict):
                nome = arquivos.get("file")
                if isinstance(nome, str) and nome:
                    candidatos.append(nome.replace("\\", "/"))
        candidatos.extend(["file.ads", "file.amk"])
        caminho_binario = next((nome for nome in candidatos if nome in nomes_no_zip), "")
        if not caminho_binario:
            avisos.append("O arquivo binario Audaces nao foi encontrado. A geometria original nao podera ser preservada.")
            return {
                "assinatura": None,
                "tamanho_bytes": 0,
                "blocos_comprimidos_detectados": 0,
                "strings_encontradas": 0,
                "possiveis_pontos_float32": 0,
                "possiveis_pontos_float64": 0,
                "contornos_candidatos": 0,
                "geometria_convertida": False,
                "motivo": "binario Audaces ausente",
                "arquivo_binario": "",
                "elementos_canvas": [],
            }
        conteudo = pacote.read(caminho_binario)
        tipo_binario = "audaces_binary_amk" if caminho_binario.lower().endswith(".amk") else "audaces_binary_ads"
        cls._preservar_bytes(caminho_binario, tipo_binario, conteudo, arquivos_preservados)
        primeiros_bytes = conteudo[:64]
        if b"CADZ" in primeiros_bytes:
            data_xml_normalizado["ads_signature"] = "CADZ"
        diagnostico = cls._tentar_extrair_geometria_file_ads(conteudo)
        diagnostico["arquivo_binario"] = caminho_binario
        if diagnostico.get("geometry_confidence") != "high":
            avisos.append("O pacote Audaces foi importado e preservado, mas a geometria binaria ainda nao pode ser decodificada com seguranca.")
        return diagnostico

    @classmethod
    def _ler_file_ads(
        cls,
        pacote: ZipFile,
        nomes_no_zip: set[str],
        avisos: list[str],
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
        data_xml_normalizado: dict[str, Any],
    ) -> dict[str, Any]:
        if "file.ads" not in nomes_no_zip:
            avisos.append("O arquivo file.ads não foi encontrado. A geometria Audaces original não poderá ser preservada.")
            return {
                "assinatura": None,
                "tamanho_bytes": 0,
                "blocos_comprimidos_detectados": 0,
                "strings_encontradas": 0,
                "possiveis_pontos_float32": 0,
                "possiveis_pontos_float64": 0,
                "contornos_candidatos": 0,
                "geometria_convertida": False,
                "motivo": "file.ads ausente",
                "elementos_canvas": [],
            }
        conteudo = pacote.read("file.ads")
        cls._preservar_bytes("file.ads", "audaces_binary_ads", conteudo, arquivos_preservados)
        primeiros_bytes = conteudo[:64]
        if b"CADZ" in primeiros_bytes:
            data_xml_normalizado["ads_signature"] = "CADZ"
        diagnostico = cls._tentar_extrair_geometria_file_ads(conteudo)
        if diagnostico.get("geometry_confidence") != "high":
            avisos.append("O ADSX foi importado e preservado, mas a geometria file.ads ainda não pôde ser decodificada.")
        return diagnostico

    @classmethod
    def _tentar_extrair_geometria_file_ads(cls, conteudo: bytes) -> dict[str, Any]:
        decoder = ADSGeometryDecoder(conteudo)
        relatorio = decoder.analisar()
        relatorio.setdefault("geometry_confidence", "none")
        relatorio.setdefault("geometria_convertida", False)
        relatorio.setdefault("elementos_canvas", [])
        return relatorio

    @classmethod
    def _ler_preview_jpg(
        cls,
        pacote: ZipFile,
        nomes_no_zip: set[str],
        avisos: list[str],
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
    ):
        if "file.jpg" not in nomes_no_zip:
            avisos.append("file.jpg não encontrado no pacote ADSX.")
            return
        conteudo = pacote.read("file.jpg")
        cls._preservar_bytes("file.jpg", "preview_image_jpg", conteudo, arquivos_preservados)

    @classmethod
    def _ler_previews(
        cls,
        pacote: ZipFile,
        nomes_no_zip: set[str],
        avisos: list[str],
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
    ):
        encontrados = False
        for nome in sorted(nomes_no_zip):
            baixo = nome.lower()
            if baixo.endswith(".jpg") or baixo.endswith(".jpeg") or baixo.endswith(".png"):
                tipo = "preview_image_png" if baixo.endswith(".png") else "preview_image_jpg"
                cls._preservar_bytes(nome, tipo, pacote.read(nome), arquivos_preservados)
                encontrados = True
        if not encontrados:
            avisos.append("Preview de imagem nao encontrado no pacote Audaces.")

    @classmethod
    def _ler_ids_json(
        cls,
        pacote: ZipFile,
        nomes_no_zip: set[str],
        avisos: list[str],
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
    ) -> dict[str, Any]:
        caminho_ids = "print/IDS.json"
        if caminho_ids not in nomes_no_zip:
            return {}
        bruto = pacote.read(caminho_ids)
        cls._preservar_bytes(caminho_ids, "print_ids_json", bruto, arquivos_preservados)
        for enc in ("utf-8", "latin-1", "iso-8859-1"):
            try:
                return json.loads(bruto.decode(enc))
            except Exception:
                continue
        avisos.append("print/IDS.json inválido ou ilegível.")
        return {}

    @classmethod
    def _normalizar_metadados(cls, xml_dict: dict[str, Any]) -> dict[str, Any]:
        resultado = {
            "xml": xml_dict,
            "campos": {},
        }

        campos = resultado["campos"]

        def _varrer(no: Any):
            if not isinstance(no, dict):
                return
            tag = cls._normalizar_chave(str(no.get("tag", "")))
            texto = (no.get("texto") or "").strip()
            if texto:
                campos.setdefault(tag, texto)
            for ak, av in (no.get("atributos") or {}).items():
                campos.setdefault(f"{tag}.{cls._normalizar_chave(str(ak))}", str(av))
            for filho in no.get("filhos", []):
                _varrer(filho)

        _varrer(xml_dict)
        return resultado

    @classmethod
    def _preservar_pacote_original(cls, doc: ADSXDocument, projeto: Projeto):
        projeto.audaces_adsx_original = {
            "origem": "Audaces ADSX",
            "nome_arquivo_original": doc.nome_arquivo,
            "tipo_pacote": doc.tipo_pacote,
            "caminho_original": doc.caminho_original,
            "importado_em": datetime.now(timezone.utc).isoformat(),
            "index_json": doc.index_json,
            "data_xml_normalizado": doc.data_xml_normalizado,
            "file_information_json": doc.file_information_json,
            "data_xml_texto_base64": base64.b64encode(doc.data_xml_texto.encode("utf-8")).decode("ascii") if doc.data_xml_texto else "",
            "arquivos_preservados": {nome: asdict(arquivo) for nome, arquivo in doc.arquivos_preservados.items()},
            "avisos": list(doc.avisos),
        }

    @staticmethod
    def _preservar_bytes(
        nome: str,
        tipo: str,
        bruto: bytes,
        arquivos_preservados: dict[str, ADSXArquivoPreservado],
    ):
        arquivos_preservados[nome] = ADSXArquivoPreservado(
            nome=nome,
            tipo=tipo,
            conteudo_base64=base64.b64encode(bruto).decode("ascii"),
            tamanho_bytes=len(bruto),
        )

    @staticmethod
    def _normalizar_chave(chave: str) -> str:
        texto = unicodedata.normalize("NFD", str(chave or ""))
        texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
        texto = texto.strip().lower().replace("-", "_")
        return "_".join(texto.split())

    @classmethod
    def _xml_to_dict(cls, element: ET.Element) -> dict[str, Any]:
        return {
            "tag": element.tag,
            "atributos": dict(element.attrib or {}),
            "texto": (element.text or "").strip(),
            "filhos": [cls._xml_to_dict(filho) for filho in list(element)],
        }

    @classmethod
    def _extrair_padroes_audaces_xml(cls, xml_dict: dict[str, Any]) -> list[ADSXMoldInfo]:
        padroes: list[ADSXMoldInfo] = []

        def _float(valor: Any) -> float | None:
            if valor is None:
                return None
            try:
                return float(str(valor).strip().replace(",", "."))
            except ValueError:
                return None

        def _int(valor: Any) -> int | None:
            if valor is None:
                return None
            try:
                return int(float(str(valor).strip().replace(",", ".")))
            except ValueError:
                return None

        def _filhos(no: dict[str, Any], tag: str) -> list[dict[str, Any]]:
            alvo = cls._normalizar_chave(tag)
            return [
                filho
                for filho in no.get("filhos", [])
                if isinstance(filho, dict) and cls._normalizar_chave(filho.get("tag", "")) == alvo
            ]

        def _texto_filho(no: dict[str, Any], tag: str) -> str:
            filhos = _filhos(no, tag)
            if not filhos:
                return ""
            return str(filhos[0].get("texto") or "").strip().strip('"')

        def _varrer(no: Any):
            if not isinstance(no, dict):
                return
            tag = cls._normalizar_chave(no.get("tag", ""))
            if tag == "pattern":
                attrs = no.get("atributos") or {}
                nome = str(attrs.get("NAME_P") or attrs.get("name_p") or attrs.get("nome") or "").strip()
                if nome:
                    sizes_p = _filhos(no, "SIZES_P")
                    size_base = ""
                    medidas_base: dict[str, Any] = {}
                    grade = ""
                    if sizes_p:
                        grade = str((sizes_p[0].get("atributos") or {}).get("NAME_GRAD") or "").strip()
                        size_base = _texto_filho(sizes_p[0], "BASE_NAME")
                        for size_node in _filhos(sizes_p[0], "SIZE_P"):
                            sp = str((size_node.get("atributos") or {}).get("NAME_SP") or "").strip()
                            if not size_base or sp.strip('"') == size_base.strip('"'):
                                medidas_base = {
                                    "perimetro": _float(_texto_filho(size_node, "PER_SP")),
                                    "area": _float(_texto_filho(size_node, "AREA_SP")),
                                    "largura": _float(_texto_filho(size_node, "WIDTH_SP")),
                                    "altura": _float(_texto_filho(size_node, "HEIGHT_SP")),
                                }
                                if not size_base:
                                    size_base = sp
                                break
                    padroes.append(
                        ADSXMoldInfo(
                            nome=nome,
                            tamanho=size_base or None,
                            quantidade=_int(_texto_filho(no, "QT_MOD")),
                            area=medidas_base.get("area"),
                            perimetro=medidas_base.get("perimetro"),
                            largura=medidas_base.get("largura"),
                            altura=medidas_base.get("altura"),
                            metadados={
                                "tag": no.get("tag"),
                                "atributos": dict(attrs),
                                "grade": grade,
                                "tamanho_base": size_base,
                                "tecido": _texto_filho(no, "NAME_FAB"),
                            },
                        )
                    )
            for filho in no.get("filhos", []):
                _varrer(filho)

        _varrer(xml_dict)
        return padroes

    @classmethod
    def _extrair_moldes_do_file_information(cls, info: dict[str, Any]) -> list[ADSXMoldInfo]:
        if not isinstance(info, dict):
            return []
        saida: list[ADSXMoldInfo] = []
        modelos = info.get("models")
        if isinstance(modelos, dict):
            for nome, dados in modelos.items():
                if not isinstance(dados, dict):
                    dados = {}
                tamanhos = dados.get("sizes")
                tamanho_txt = ", ".join(str(t).strip() for t in tamanhos if str(t).strip()) if isinstance(tamanhos, list) else None
                saida.append(
                    ADSXMoldInfo(
                        nome=str(nome),
                        tamanho=tamanho_txt,
                        quantidade=_safe_int(dados.get("patterns")),
                        area=None,
                        perimetro=None,
                        largura=None,
                        altura=None,
                        metadados={"origem": "amkx_fileInformation", "tipo": "modelo_encaixe", **dict(dados)},
                    )
                )
        marcadores = info.get("markers")
        if isinstance(marcadores, dict):
            for ident, dados in marcadores.items():
                if not isinstance(dados, dict):
                    continue
                saida.append(
                    ADSXMoldInfo(
                        nome=f"Encaixe {ident}",
                        tamanho=None,
                        quantidade=_safe_int(dados.get("placed") or dados.get("toPlace")),
                        area=_safe_float(dados.get("area")),
                        perimetro=_safe_float(dados.get("cutPerimeter")),
                        largura=_safe_float(dados.get("width")),
                        altura=_safe_float(dados.get("length")),
                        metadados={"origem": "amkx_fileInformation", "tipo": "marker", "id": str(ident), **dict(dados)},
                    )
                )
        return saida

    @classmethod
    def _extrair_moldes_do_xml(cls, xml_dict: dict[str, Any]) -> list[ADSXMoldInfo]:
        candidatos: list[ADSXMoldInfo] = []
        if not xml_dict:
            return candidatos

        padroes_audaces = cls._extrair_padroes_audaces_xml(xml_dict)
        if padroes_audaces:
            return padroes_audaces

        nome_alias = {cls._normalizar_chave(v) for v in cls._ALIAS_CHAVES["nome"]}

        def _capturar_float(valor: Any) -> float | None:
            if valor is None:
                return None
            if isinstance(valor, (int, float)):
                return float(valor)
            txt = str(valor).strip().replace(",", ".")
            try:
                return float(txt)
            except ValueError:
                return None

        def _capturar_int(valor: Any) -> int | None:
            if valor is None:
                return None
            if isinstance(valor, int):
                return valor
            txt = str(valor).strip()
            try:
                return int(float(txt.replace(",", ".")))
            except ValueError:
                return None

        def _valor_semelhante(chaves: dict[str, Any], grupo: str) -> Any:
            alvos = {cls._normalizar_chave(a) for a in cls._ALIAS_CHAVES[grupo]}
            for chave in chaves:
                if cls._normalizar_chave(chave) in alvos:
                    return chaves[chave]
            return None

        def _varrer(no: Any):
            if not isinstance(no, dict):
                return
            tag = cls._normalizar_chave(no.get("tag", ""))
            atributos = no.get("atributos") or {}
            mapa = {k: v for k, v in atributos.items()}
            texto = (no.get("texto") or "").strip()
            if tag in nome_alias or any(cls._normalizar_chave(k) in nome_alias for k in mapa):
                nome = (
                    _valor_semelhante(mapa, "nome")
                    or texto
                    or (f"Molde {len(candidatos) + 1}")
                )
                molde = ADSXMoldInfo(
                    nome=str(nome),
                    tamanho=_valor_semelhante(mapa, "tamanho"),
                    quantidade=_capturar_int(_valor_semelhante(mapa, "quantidade")),
                    area=_capturar_float(_valor_semelhante(mapa, "area")),
                    perimetro=_capturar_float(_valor_semelhante(mapa, "perimetro")),
                    largura=_capturar_float(_valor_semelhante(mapa, "largura")),
                    altura=_capturar_float(_valor_semelhante(mapa, "altura")),
                    metadados={
                        "tag": no.get("tag"),
                        "atributos": dict(atributos),
                        "texto": texto,
                    },
                )
                candidatos.append(molde)
            for filho in no.get("filhos", []):
                _varrer(filho)

        _varrer(xml_dict)

        unicos: list[ADSXMoldInfo] = []
        vistos: set[tuple[str, str | None]] = set()
        for item in candidatos:
            chave = (item.nome, item.tamanho)
            if chave in vistos:
                continue
            vistos.add(chave)
            unicos.append(item)
        return unicos


def importar_adsx_seguro(caminho: str | Path, projeto: Projeto) -> tuple[Projeto | None, str | None]:
    try:
        return ADSXIO.importar_para_projeto(caminho, projeto), None
    except ADSXImportError as exc:
        return None, str(exc)
    except Exception:
        traceback.print_exc()
        return None, "Não foi possível abrir o pacote ADSX."
