from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field
from math import atan2, cos, pi, sin
from pathlib import Path
from typing import Any

EMR_HEADER = 1
EMR_POLYBEZIER = 2
EMR_POLYGON = 3
EMR_POLYLINE = 4
EMR_POLYBEZIERTO = 5
EMR_POLYLINETO = 6
EMR_POLYPOLYLINE = 7
EMR_POLYPOLYGON = 8
EMR_SETWINDOWEXTEX = 9
EMR_SETWINDOWORGEX = 10
EMR_SETVIEWPORTEXTEX = 11
EMR_SETVIEWPORTORGEX = 12
EMR_SETBRUSHORGEX = 13
EMR_EOF = 14
EMR_SETPIXELV = 15
EMR_SETMAPPERFLAGS = 16
EMR_SETMAPMODE = 17
EMR_SETBKMODE = 18
EMR_SETPOLYFILLMODE = 19
EMR_SETROP2 = 20
EMR_SETSTRETCHBLTMODE = 21
EMR_SETTEXTALIGN = 22
EMR_SETCOLORADJUSTMENT = 23
EMR_SETTEXTCOLOR = 24
EMR_SETBKCOLOR = 25
EMR_OFFSETCLIPRGN = 26
EMR_MOVETOEX = 27
EMR_SETMETARGN = 28
EMR_EXCLUDECLIPRECT = 29
EMR_INTERSECTCLIPRECT = 30
EMR_SCALEVIEWPORTEXTEX = 31
EMR_SCALEWINDOWEXTEX = 32
EMR_SAVEDC = 33
EMR_RESTOREDC = 34
EMR_SETWORLDTRANSFORM = 35
EMR_MODIFYWORLDTRANSFORM = 36
EMR_SELECTOBJECT = 37
EMR_CREATEPEN = 38
EMR_DELETEOBJECT = 40
EMR_ELLIPSE = 42
EMR_RECTANGLE = 43
EMR_ARC = 45
EMR_LINETO = 54
EMR_POLYLINE16 = 87
EMR_POLYGON16 = 86
EMR_POLYBEZIER16 = 85
EMR_POLYPOLYLINE16 = 90
EMR_POLYPOLYGON16 = 91
EMR_EXTTEXTOUTA = 83
EMR_EXTTEXTOUTW = 84


@dataclass
class EMFVectorElement:
    tipo: str
    pontos: list[tuple[float, float]]
    fechado: bool
    cor: str | None
    espessura: float | None
    bbox: tuple[float, float, float, float] | None
    raw_record_type: int
    metadados: dict[str, Any] = field(default_factory=dict)


@dataclass
class AudacesEMFDocument:
    caminho: str
    largura: float
    altura: float
    bounds: tuple[float, float, float, float]
    elementos: list[EMFVectorElement]
    textos: list[dict[str, Any]]
    relatorio: dict[str, Any]


class AudacesEMFImport:
    def __init__(self, raw: bytes, caminho: str | Path):
        self.raw = raw
        self.caminho = str(caminho)
        self.records: list[dict[str, Any]] = []
        self._record_types: dict[int, int] = {}
        self._warnings: list[str] = []
        self._current_point: tuple[float, float] | None = None

    @classmethod
    def abrir(cls, caminho: str | Path) -> AudacesEMFDocument:
        raw = Path(caminho).read_bytes()
        parser = cls(raw, caminho)
        parser.parse_records()
        elementos, textos, bounds = parser.extrair_elementos_vetoriais()
        relatorio = parser.gerar_relatorio(elementos, textos, bounds)
        largura = max(bounds[2] - bounds[0], 0.0)
        altura = max(bounds[3] - bounds[1], 0.0)
        return AudacesEMFDocument(
            caminho=str(caminho),
            largura=largura,
            altura=altura,
            bounds=bounds,
            elementos=elementos,
            textos=textos,
            relatorio=relatorio,
        )

    def parse_records(self):
        off = 0
        total = len(self.raw)
        while off + 8 <= total:
            tipo, tamanho = struct.unpack_from("<II", self.raw, off)
            if tamanho < 8 or off + tamanho > total:
                self._warnings.append(f"Record EMF inválido em offset {off}.")
                break
            payload = self.raw[off + 8 : off + tamanho]
            self.records.append({"tipo": tipo, "tamanho": tamanho, "offset": off, "payload": payload})
            self._record_types[tipo] = self._record_types.get(tipo, 0) + 1
            off += tamanho
            if tipo == EMR_EOF:
                break

    def extrair_elementos_vetoriais(self) -> tuple[list[EMFVectorElement], list[dict[str, Any]], tuple[float, float, float, float]]:
        elementos: list[EMFVectorElement] = []
        textos: list[dict[str, Any]] = []
        bounds = (0.0, 0.0, 100.0, 100.0)

        for rec in self.records:
            t = rec["tipo"]
            p = rec["payload"]
            if t == EMR_HEADER:
                bounds = self._parse_bounds_header(p) or bounds
            elif t in {EMR_POLYLINE, EMR_POLYGON, EMR_POLYBEZIER}:
                pontos = self._parse_poly_points32(p)
                fechado = t == EMR_POLYGON
                if t == EMR_POLYBEZIER:
                    pontos = self._densificar_bezier(pontos)
                if pontos:
                    elementos.append(self._mk_element("polyline", pontos, fechado, t))
            elif t in {EMR_POLYLINE16, EMR_POLYGON16, EMR_POLYBEZIER16}:
                pontos = self._parse_poly_points16(p)
                fechado = t == EMR_POLYGON16
                if t == EMR_POLYBEZIER16:
                    pontos = self._densificar_bezier(pontos)
                if pontos:
                    elementos.append(self._mk_element("polyline", pontos, fechado, t))
            elif t in {EMR_POLYPOLYLINE, EMR_POLYPOLYGON}:
                for pts in self._parse_poly_poly32(p):
                    elementos.append(self._mk_element("polyline", pts, t == EMR_POLYPOLYGON, t))
            elif t in {EMR_POLYPOLYLINE16, EMR_POLYPOLYGON16}:
                for pts in self._parse_poly_poly16(p):
                    elementos.append(self._mk_element("polyline", pts, t == EMR_POLYPOLYGON16, t))
            elif t == EMR_MOVETOEX:
                self._current_point = self._parse_pointl(p, 0)
            elif t == EMR_LINETO:
                pt = self._parse_pointl(p, 0)
                if self._current_point and pt:
                    elementos.append(self._mk_element("polyline", [self._current_point, pt], False, t))
                self._current_point = pt
            elif t == EMR_RECTANGLE:
                pts = self._parse_rect_poly(p)
                if pts:
                    elementos.append(self._mk_element("polyline", pts, True, t))
            elif t == EMR_ELLIPSE:
                pts = self._parse_ellipse_poly(p)
                if pts:
                    elementos.append(self._mk_element("polyline", pts, True, t))
            elif t == EMR_ARC:
                pts = self._parse_arc_poly(p)
                if pts:
                    elementos.append(self._mk_element("polyline", pts, False, t))
            elif t in {EMR_EXTTEXTOUTA, EMR_EXTTEXTOUTW}:
                txt = self._parse_text_record(p, wide=t == EMR_EXTTEXTOUTW)
                if txt:
                    textos.append(txt)

        elementos = [e for e in elementos if len(e.pontos) >= 2]
        self._normalizar_eixo_y(elementos, textos, bounds)
        return elementos, textos, bounds

    def converter_para_elementos_guimma(self, doc: AudacesEMFDocument) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for el in doc.elementos:
            item = {
                "tipo": "polyline",
                "pontos": list(el.pontos),
                "cor": el.cor or "#ff7b00",
                "origem": "audaces_emf",
                "raw_record_type": el.raw_record_type,
                "metadados": dict(el.metadados),
            }
            if el.fechado and el.pontos and el.pontos[0] != el.pontos[-1]:
                item["pontos"].append(el.pontos[0])
            out.append(item)
        for tx in doc.textos:
            out.append(
                {
                    "tipo": "texto",
                    "texto": tx.get("texto", ""),
                    "pos": tx.get("pos", (0.0, 0.0)),
                    "cor": "#22313f",
                    "tamanho": 0.9,
                    "origem": "audaces_emf",
                }
            )
        return out

    def gerar_relatorio(
        self, elementos: list[EMFVectorElement], textos: list[dict[str, Any]], bounds: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        polylines = sum(1 for e in elementos if e.tipo == "polyline")
        fechados = sum(1 for e in elementos if e.fechado)
        return {
            "tamanho_arquivo": len(self.raw),
            "bounds_emf": bounds,
            "records_total": len(self.records),
            "records_tipos": dict(sorted(self._record_types.items())),
            "quantidade_polylines": polylines,
            "quantidade_polygons": sum(self._record_types.get(k, 0) for k in (EMR_POLYGON, EMR_POLYGON16, EMR_POLYPOLYGON, EMR_POLYPOLYGON16)),
            "quantidade_beziers": sum(self._record_types.get(k, 0) for k in (EMR_POLYBEZIER, EMR_POLYBEZIER16)),
            "quantidade_textos": len(textos),
            "elementos_convertidos": len(elementos),
            "contornos_fechados": fechados,
            "possiveis_moldes": fechados,
            "avisos": list(self._warnings),
        }

    @staticmethod
    def _bbox(pontos: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    def _mk_element(self, tipo: str, pontos: list[tuple[float, float]], fechado: bool, raw_type: int) -> EMFVectorElement:
        return EMFVectorElement(tipo=tipo, pontos=pontos, fechado=fechado, cor="#ff7b00", espessura=None, bbox=self._bbox(pontos), raw_record_type=raw_type)

    @staticmethod
    def _parse_bounds_header(payload: bytes) -> tuple[float, float, float, float] | None:
        if len(payload) < 16:
            return None
        left, top, right, bottom = struct.unpack_from("<4i", payload, 0)
        return float(left), float(top), float(right), float(bottom)

    @staticmethod
    def _parse_pointl(payload: bytes, offset: int) -> tuple[float, float] | None:
        if len(payload) < offset + 8:
            return None
        x, y = struct.unpack_from("<2i", payload, offset)
        return float(x), float(y)

    @staticmethod
    def _parse_points16(payload: bytes, offset: int, count: int) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for i in range(count):
            start = offset + (i * 4)
            if len(payload) < start + 4:
                break
            x, y = struct.unpack_from("<2h", payload, start)
            pts.append((float(x), float(y)))
        return pts

    @staticmethod
    def _parse_points32(payload: bytes, offset: int, count: int) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for i in range(count):
            start = offset + (i * 8)
            if len(payload) < start + 8:
                break
            x, y = struct.unpack_from("<2i", payload, start)
            pts.append((float(x), float(y)))
        return pts

    def _parse_poly_points32(self, payload: bytes) -> list[tuple[float, float]]:
        if len(payload) < 20:
            return []
        cpt = struct.unpack_from("<I", payload, 16)[0]
        return self._parse_points32(payload, 20, cpt)

    def _parse_poly_points16(self, payload: bytes) -> list[tuple[float, float]]:
        if len(payload) < 20:
            return []
        cpt = struct.unpack_from("<I", payload, 16)[0]
        return self._parse_points16(payload, 20, cpt)

    def _parse_poly_poly32(self, payload: bytes) -> list[list[tuple[float, float]]]:
        if len(payload) < 24:
            return []
        n_poly, cpt = struct.unpack_from("<2I", payload, 16)
        counts_off = 24
        counts = []
        for i in range(n_poly):
            if len(payload) < counts_off + ((i + 1) * 4):
                break
            counts.append(struct.unpack_from("<I", payload, counts_off + (i * 4))[0])
        pts_off = counts_off + (4 * len(counts))
        all_pts = self._parse_points32(payload, pts_off, cpt)
        out = []
        cursor = 0
        for c in counts:
            chunk = all_pts[cursor : cursor + c]
            if chunk:
                out.append(chunk)
            cursor += c
        return out

    def _parse_poly_poly16(self, payload: bytes) -> list[list[tuple[float, float]]]:
        if len(payload) < 24:
            return []
        n_poly, cpt = struct.unpack_from("<2I", payload, 16)
        counts_off = 24
        counts = []
        for i in range(n_poly):
            if len(payload) < counts_off + ((i + 1) * 4):
                break
            counts.append(struct.unpack_from("<I", payload, counts_off + (i * 4))[0])
        pts_off = counts_off + (4 * len(counts))
        all_pts = self._parse_points16(payload, pts_off, cpt)
        out = []
        cursor = 0
        for c in counts:
            chunk = all_pts[cursor : cursor + c]
            if chunk:
                out.append(chunk)
            cursor += c
        return out

    def _parse_rect_poly(self, payload: bytes) -> list[tuple[float, float]]:
        if len(payload) < 16:
            return []
        l, t, r, b = struct.unpack_from("<4i", payload, 0)
        return [(l, t), (r, t), (r, b), (l, b), (l, t)]

    def _parse_ellipse_poly(self, payload: bytes) -> list[tuple[float, float]]:
        if len(payload) < 16:
            return []
        l, t, r, b = struct.unpack_from("<4i", payload, 0)
        cx, cy = (l + r) / 2.0, (t + b) / 2.0
        rx, ry = abs(r - l) / 2.0, abs(b - t) / 2.0
        pts = []
        for i in range(41):
            a = (2 * pi * i) / 40.0
            pts.append((cx + (rx * cos(a)), cy + (ry * sin(a))))
        return pts

    def _parse_arc_poly(self, payload: bytes) -> list[tuple[float, float]]:
        if len(payload) < 32:
            return []
        l, t, r, b, sx, sy, ex, ey = struct.unpack_from("<8i", payload, 0)
        cx, cy = (l + r) / 2.0, (t + b) / 2.0
        rx, ry = abs(r - l) / 2.0, abs(b - t) / 2.0
        if rx <= 0 or ry <= 0:
            return []

        def _ang(px: float, py: float) -> float:
            return atan2((py - cy) / max(ry, 1e-6), (px - cx) / max(rx, 1e-6))

        a0, a1 = _ang(sx, sy), _ang(ex, ey)
        if a1 < a0:
            a1 += 2 * pi
        segs = 24
        return [(cx + (rx * cos(a0 + ((a1 - a0) * (i / segs)))), cy + (ry * sin(a0 + ((a1 - a0) * (i / segs))))) for i in range(segs + 1)]

    @staticmethod
    def _densificar_bezier(pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(pontos) < 4:
            return pontos
        out = [pontos[0]]
        i = 1
        while i + 2 < len(pontos):
            p1, p2, p3 = pontos[i], pontos[i + 1], pontos[i + 2]
            p0 = out[-1]
            for j in range(1, 9):
                t = j / 8.0
                mt = 1 - t
                x = (mt**3) * p0[0] + 3 * (mt**2) * t * p1[0] + 3 * mt * (t**2) * p2[0] + (t**3) * p3[0]
                y = (mt**3) * p0[1] + 3 * (mt**2) * t * p1[1] + 3 * mt * (t**2) * p2[1] + (t**3) * p3[1]
                out.append((x, y))
            i += 3
        return out

    def _parse_text_record(self, payload: bytes, wide: bool) -> dict[str, Any] | None:
        if len(payload) < 28:
            return None
        x, y = struct.unpack_from("<2i", payload, 0)
        # fallback robusto: extrai trecho textual imprimível do payload
        if wide:
            txt = payload.decode("utf-16-le", errors="ignore")
        else:
            txt = payload.decode("latin-1", errors="ignore")
        txt = "".join(ch for ch in txt if ch.isprintable())
        txt = " ".join(txt.split())[:120]
        if not txt:
            return None
        return {"texto": txt, "pos": (float(x), float(y))}

    @staticmethod
    def _normalizar_eixo_y(elementos: list[EMFVectorElement], textos: list[dict[str, Any]], bounds: tuple[float, float, float, float]):
        _, top, _, bottom = bounds
        h = max(bottom - top, 1.0)
        for e in elementos:
            e.pontos = [(x, (h - (y - top))) for x, y in e.pontos]
            e.bbox = AudacesEMFImport._bbox(e.pontos)
        for t in textos:
            x, y = t.get("pos", (0.0, 0.0))
            t["pos"] = (x, (h - (y - top)))


def emf_doc_para_dict(doc: AudacesEMFDocument) -> dict[str, Any]:
    return {
        "caminho": doc.caminho,
        "largura": doc.largura,
        "altura": doc.altura,
        "bounds": doc.bounds,
        "elementos": [asdict(e) for e in doc.elementos],
        "textos": list(doc.textos),
        "relatorio": dict(doc.relatorio),
    }
