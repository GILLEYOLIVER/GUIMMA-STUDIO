from __future__ import annotations

import re
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
    quantidade: int | None = None
    quantidade_posicionada: int | None = None


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
    tamanho_base: str | None = None
    tamanhos: list[AudacesXMLPatternSize] = field(default_factory=list)


@dataclass
class AudacesXMLDocument:
    nome_modelo: str
    arquivo_adsx_original: str
    tamanhos_modelo: list[AudacesXMLSize]
    pecas: list[AudacesXMLPattern]
    bruto_normalizado: dict[str, Any]


class AudacesXMLImport:
    """Importa o XML exportado pelo Audaces em Exportar > Arquivo de dados.

    Observação importante: este XML é metadado técnico. Ele NÃO contém o contorno
    vetorial completo. A geometria deve vir do EMF; este XML fornece nomes,
    tamanhos, medidas, quantidades, tecidos, piques e propriedades.
    """

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
            except UnicodeDecodeError:
                continue
        if not texto:
            texto = bruto.decode("latin-1", errors="ignore")

        # Alguns exports antigos podem trazer caracteres inválidos antes/depois do XML.
        inicio = texto.find("<")
        if inicio > 0:
            texto = texto[inicio:]
        raiz = ET.fromstring(texto)
        bruto_normalizado = cls._xml_to_dict(raiz)
        parser = cls(raiz, bruto_normalizado)
        return parser.normalizar()

    def extrair_modelo(self) -> tuple[str, str]:
        model = self.raiz.find(".//MODEL")
        nome = ""
        adsx = ""
        if model is not None:
            nome = self._txt(model, "NAME_M", "MODEL_NAME", default="").strip()
        info = self.raiz.find(".//INFO")
        if info is not None:
            adsx = self._txt(info, "FILE", "ARQUIVO", default="").strip()
        return nome or "Modelo Audaces", adsx

    def extrair_tamanhos(self) -> list[AudacesXMLSize]:
        tamanhos: list[AudacesXMLSize] = []
        for no in self.raiz.findall(".//SIZES_M/SIZE_M"):
            # No XML real enviado pelo usuário o atributo é NAME_SP, não NAME_SM.
            nome = self._norm_size(self._txt(no, "NAME_SP", "NAME_SM", "SIZE", "NAME"))
            tamanhos.append(
                AudacesXMLSize(
                    nome=nome or "",
                    # No XML real os campos são PER_SM e AREA_SM.
                    perimetro_total=self._num(self._txt(no, "PER_SM", "PERIMETER_SM", "PERIMETRO_SM")),
                    area_total=self._num(self._txt(no, "AREA_SM", "AREA_TOTAL_SM")),
                )
            )
        return [t for t in tamanhos if t.nome]

    def extrair_pecas(self) -> list[AudacesXMLPattern]:
        pecas: list[AudacesXMLPattern] = []
        for pat in self.raiz.findall(".//PATTERNS/PATTERN"):
            tamanhos: list[AudacesXMLPatternSize] = []
            sizes_p = pat.find(".//SIZES_P")
            tamanho_base = ""
            if sizes_p is not None:
                tamanho_base = self._norm_size((self._txt(sizes_p, "BASE_NAME", default="") or "").replace('"', ""))
            for sp in pat.findall(".//SIZES_P/SIZE_P"):
                tamanhos.append(
                    AudacesXMLPatternSize(
                        tamanho=self._norm_size(self._txt(sp, "NAME_SP", "NAME_SIZE", "SIZE")),
                        # No XML real do Audaces os nomes curtos são estes.
                        perimetro=self._num(self._txt(sp, "PER_SP", "PERIMETER_SP", "PERIMETRO_SP")),
                        area=self._num(self._txt(sp, "AREA_SP")),
                        perimetro_retilineo=self._num(self._txt(sp, "RECTILINE_PER_SP", "RECTILINEAR_PERIMETER_SP")),
                        perimetro_curva=self._num(self._txt(sp, "CURVE_PER_SP", "CURVE_PERIMETER_SP")),
                        largura=self._num(self._txt(sp, "WIDTH_SP", "LARGURA_SP")),
                        altura=self._num(self._txt(sp, "HEIGHT_SP", "ALTURA_SP")),
                        quantidade=self._int(self._txt(sp, "QUANT_SP", "QUANTITY_SP", "QTD_SP")),
                        quantidade_posicionada=self._int(self._txt(sp, "QUANT_PLACED", "PLACED_SP")),
                    )
                )
            pecas.append(
                AudacesXMLPattern(
                    nome=self._txt(pat, "NAME_P", "NAME", default="Peça").strip() or "Peça",
                    descricao=self._txt(pat, "DESC_P", "DESCRIPTION_P", "DESC", default="").strip(),
                    tecido=self._txt(pat, "NAME_FAB", "FABRIC_P", "TECIDO", default="").strip(),
                    quantidade=self._int(self._txt(pat, "QT_MOD", "QUANTITY_P", "QTD", "QUANTIDADE")),
                    rotacao=self._int(self._txt(pat, "ROT_P", "ROTATION_P")),
                    dobra_horizontal=self._int(self._txt(pat, "FOLD_HOR", "HORIZONTAL_FOLD_P")),
                    dobra_vertical=self._int(self._txt(pat, "FOLD_VER", "VERTICAL_FOLD_P")),
                    piques=self._int(self._txt(pat, "NOTCHES_COUNT", "NOTCHS_P", "NOTCHES_P")),
                    piques_internos=self._int(self._txt(pat, "INTERNAL_NOTCHES_COUNT", "INTERNAL_NOTCHS_P")),
                    tamanho_base=tamanho_base or None,
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
        return " ".join(str(valor or "").strip().split())

    @staticmethod
    def _num(valor: str | None) -> float | None:
        if valor is None:
            return None
        txt = str(valor).strip().replace(",", ".")
        if not txt:
            return None
        # Remove comentários/unidades que venham junto por segurança.
        m = re.search(r"[-+]?\d+(?:\.\d+)?", txt)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None

    @classmethod
    def _int(cls, valor: str | None) -> int | None:
        n = cls._num(valor)
        if n is None:
            return None
        try:
            return int(round(n))
        except Exception:
            return None

    @staticmethod
    def _txt(no: ET.Element, *nomes: str, default: str | None = None) -> str | None:
        for nome in nomes:
            if nome in no.attrib:
                return no.attrib.get(nome)
        for nome in nomes:
            filho = no.find(nome)
            if filho is not None and filho.text is not None:
                return filho.text
        return default


def xml_doc_para_dict(doc: AudacesXMLDocument) -> dict[str, Any]:
    return asdict(doc)
