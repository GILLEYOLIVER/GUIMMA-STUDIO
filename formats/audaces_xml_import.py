from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AudacesXMLSize:
    nome: str
    perimetro_total: float | None
    area_total: float | None


@dataclass
class AudacesXMLPatternSize:
    tamanho: str
    perimetro: float | None
    area: float | None
    perimetro_retilineo: float | None
    perimetro_curva: float | None
    largura: float | None
    altura: float | None


@dataclass
class AudacesXMLPattern:
    nome: str
    descricao: str
    tecido: str
    quantidade: int | None
    rotacao: int | None
    dobra_horizontal: int | None
    dobra_vertical: int | None
    piques: int | None
    piques_internos: int | None
    tamanhos: list[AudacesXMLPatternSize] = field(default_factory=list)


@dataclass
class AudacesXMLDocument:
    nome_modelo: str
    arquivo_adsx_original: str
    tamanhos_modelo: list[AudacesXMLSize]
    pecas: list[AudacesXMLPattern]
    bruto_normalizado: dict[str, Any]


class AudacesXMLImport:
    def __init__(self, raiz: ET.Element, bruto_normalizado: dict[str, Any]):
        self.raiz = raiz
        self.bruto_normalizado = bruto_normalizado

    @classmethod
    def abrir(cls, caminho: str | Path) -> AudacesXMLDocument:
        p = Path(caminho)
        bruto = p.read_bytes()
        texto = ""
        for enc in ("iso-8859-1", "utf-8", "latin-1"):
            try:
                texto = bruto.decode(enc)
                break
            except Exception:
                continue
        if not texto:
            texto = bruto.decode("latin-1", errors="ignore")
        raiz = ET.fromstring(texto)
        bruto_normalizado = cls._xml_to_dict(raiz)
        parser = cls(raiz, bruto_normalizado)
        return parser.normalizar()

    def extrair_modelo(self) -> tuple[str, str]:
        model = self.raiz.find(".//MODEL")
        nome = ""
        adsx = ""
        if model is not None:
            nome = (model.attrib.get("NAME_M") or model.findtext("NAME_M") or "").strip()
        info = self.raiz.find(".//INFO")
        if info is not None:
            adsx = (info.attrib.get("FILE") or info.findtext("FILE") or "").strip()
        return nome or "Modelo Audaces", adsx

    def extrair_tamanhos(self) -> list[AudacesXMLSize]:
        tamanhos: list[AudacesXMLSize] = []
        for no in self.raiz.findall(".//SIZES_M/SIZE_M"):
            nome = self._norm_size(no.attrib.get("NAME_SM") or no.findtext("NAME_SM"))
            tamanhos.append(
                AudacesXMLSize(
                    nome=nome or "",
                    perimetro_total=self._num(no.attrib.get("PERIMETER_SM") or no.findtext("PERIMETER_SM")),
                    area_total=self._num(no.attrib.get("AREA_SM") or no.findtext("AREA_SM")),
                )
            )
        return [t for t in tamanhos if t.nome]

    def extrair_pecas(self) -> list[AudacesXMLPattern]:
        pecas: list[AudacesXMLPattern] = []
        for pat in self.raiz.findall(".//PATTERNS/PATTERN"):
            tamanhos: list[AudacesXMLPatternSize] = []
            for sp in pat.findall(".//SIZES_P/SIZE_P"):
                tamanhos.append(
                    AudacesXMLPatternSize(
                        tamanho=self._norm_size(sp.attrib.get("NAME_SP") or sp.findtext("NAME_SP") or ""),
                        perimetro=self._num(sp.attrib.get("PERIMETER_SP") or sp.findtext("PERIMETER_SP")),
                        area=self._num(sp.attrib.get("AREA_SP") or sp.findtext("AREA_SP")),
                        perimetro_retilineo=self._num(sp.attrib.get("RECTILINEAR_PERIMETER_SP") or sp.findtext("RECTILINEAR_PERIMETER_SP")),
                        perimetro_curva=self._num(sp.attrib.get("CURVE_PERIMETER_SP") or sp.findtext("CURVE_PERIMETER_SP")),
                        largura=self._num(sp.attrib.get("WIDTH_SP") or sp.findtext("WIDTH_SP")),
                        altura=self._num(sp.attrib.get("HEIGHT_SP") or sp.findtext("HEIGHT_SP")),
                    )
                )
            pecas.append(
                AudacesXMLPattern(
                    nome=(pat.attrib.get("NAME_P") or pat.findtext("NAME_P") or "Peça").strip(),
                    descricao=(pat.attrib.get("DESCRIPTION_P") or pat.findtext("DESCRIPTION_P") or "").strip(),
                    tecido=(pat.attrib.get("FABRIC_P") or pat.findtext("FABRIC_P") or "").strip(),
                    quantidade=self._int(pat.attrib.get("QUANTITY_P") or pat.findtext("QUANTITY_P")),
                    rotacao=self._int(pat.attrib.get("ROTATION_P") or pat.findtext("ROTATION_P")),
                    dobra_horizontal=self._int(pat.attrib.get("HORIZONTAL_FOLD_P") or pat.findtext("HORIZONTAL_FOLD_P")),
                    dobra_vertical=self._int(pat.attrib.get("VERTICAL_FOLD_P") or pat.findtext("VERTICAL_FOLD_P")),
                    piques=self._int(pat.attrib.get("NOTCHS_P") or pat.findtext("NOTCHS_P")),
                    piques_internos=self._int(pat.attrib.get("INTERNAL_NOTCHS_P") or pat.findtext("INTERNAL_NOTCHS_P")),
                    tamanhos=[t for t in tamanhos if t.tamanho],
                )
            )
        return pecas

    def normalizar(self) -> AudacesXMLDocument:
        nome_modelo, arquivo_adsx_original = self.extrair_modelo()
        return AudacesXMLDocument(
            nome_modelo=nome_modelo,
            arquivo_adsx_original=arquivo_adsx_original,
            tamanhos_modelo=self.extrair_tamanhos(),
            pecas=self.extrair_pecas(),
            bruto_normalizado=self.bruto_normalizado,
        )

    @staticmethod
    def _xml_to_dict(element: ET.Element) -> dict[str, Any]:
        return {
            "tag": element.tag,
            "atributos": dict(element.attrib),
            "texto": (element.text or "").strip(),
            "filhos": [AudacesXMLImport._xml_to_dict(f) for f in list(element)],
        }

    @staticmethod
    def _norm_size(valor: str | None) -> str:
        return str(valor or "").strip()

    @staticmethod
    def _num(valor: str | None) -> float | None:
        if valor is None:
            return None
        txt = str(valor).strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            return None

    @classmethod
    def _int(cls, valor: str | None) -> int | None:
        n = cls._num(valor)
        if n is None:
            return None
        try:
            return int(n)
        except Exception:
            return None


def xml_doc_para_dict(doc: AudacesXMLDocument) -> dict[str, Any]:
    return asdict(doc)
