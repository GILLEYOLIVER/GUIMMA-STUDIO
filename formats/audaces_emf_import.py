from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field
from math import acos, atan2, cos, pi, sin
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
EMR_EOF = 14
EMR_SETMAPMODE = 17
EMR_MOVETOEX = 27
EMR_SETWORLDTRANSFORM = 35
EMR_MODIFYWORLDTRANSFORM = 36
EMR_SELECTOBJECT = 37
EMR_CREATEPEN = 38
EMR_DELETEOBJECT = 40
EMR_ELLIPSE = 42
EMR_RECTANGLE = 43
EMR_ARC = 45
EMR_LINETO = 54
EMR_BEGINPATH = 59
EMR_ENDPATH = 60
EMR_CLOSEFIGURE = 61
EMR_FILLPATH = 62
EMR_STROKEANDFILLPATH = 63
EMR_STROKEPATH = 64
EMR_EXTTEXTOUTA = 83
EMR_EXTTEXTOUTW = 84
EMR_POLYBEZIER16 = 85
EMR_POLYGON16 = 86
EMR_POLYLINE16 = 87
EMR_POLYBEZIERTO16 = 88
EMR_POLYLINETO16 = 89
EMR_POLYPOLYLINE16 = 90
EMR_POLYPOLYGON16 = 91
EMR_POLYDRAW = 56
EMR_POLYDRAW16 = 92


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
        self._unsupported: dict[int, int] = {}
        self._current_point: tuple[float, float] | None = None
        self._in_path = False
        self._path_points: list[tuple[float, float]] = []
        self._path_closed = False
        self._world = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        self._window_org = (0.0, 0.0)
        self._window_ext = (1.0, 1.0)
        self._viewport_org = (0.0, 0.0)
        self._viewport_ext = (1.0, 1.0)
        self._map_mode = 1
        self._frame_cm: tuple[float, float, float, float] | None = None
        self._dedupe_stats: dict[str, int] = {"removidas": 0, "reclassificadas_costura": 0, "ignoradas": 0}
        self.suavizar_curvas_audaces = True
        self.reconstruir_curvas_audaces = True
        self._smooth_stats: dict[str, int] = {
            "elementos_suavizados": 0,
            "pontos_removidos_jitter": 0,
            "cantos_preservados": 0,
            "suavizados_contorno": 0,
            "suavizados_costura": 0,
            "trechos_reconstruidos": 0,
            "trechos_rejeitados_perimetro": 0,
        }
        self.tolerancia_uniao_mm = 1.5
        self._join_stats: dict[str, int] = {"segmentos_originais": 0, "segmentos_unidos": 0, "contornos_fechados": 0, "curvas_reconstruidas": 0}

    @classmethod
    def abrir(cls, caminho: str | Path) -> AudacesEMFDocument:
        raw = Path(caminho).read_bytes()
        parser = cls(raw, caminho)
        parser.parse_records()
        elementos, textos, bounds = parser.extrair_elementos_vetoriais()
        relatorio = parser.gerar_relatorio(elementos, textos, bounds)
        return AudacesEMFDocument(
            caminho=str(caminho),
            largura=max(bounds[2] - bounds[0], 0.0),
            altura=max(bounds[3] - bounds[1], 0.0),
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
                self._frame_cm = self._parse_frame_header_cm(p) or self._frame_cm
            elif t in {EMR_SETWINDOWORGEX, EMR_SETWINDOWEXTEX, EMR_SETVIEWPORTORGEX, EMR_SETVIEWPORTEXTEX, EMR_SETMAPMODE,
                       EMR_SETWORLDTRANSFORM, EMR_MODIFYWORLDTRANSFORM}:
                self._process_transform_record(t, p)
            elif t in {EMR_POLYLINE, EMR_POLYGON, EMR_POLYBEZIER, EMR_POLYLINETO, EMR_POLYBEZIERTO}:
                pontos = self._parse_poly_points32(p)
                pontos = self._apply_transform_points(pontos)
                if t in {EMR_POLYBEZIER, EMR_POLYBEZIERTO}:
                    pontos = self._densificar_bezier(pontos)
                fechado = t == EMR_POLYGON
                if t in {EMR_POLYLINETO, EMR_POLYBEZIERTO} and self._current_point:
                    pontos = [self._current_point] + pontos
                if pontos:
                    self._current_point = pontos[-1]
                    self._push_points(t, pontos, fechado, elementos)
            elif t in {EMR_POLYLINE16, EMR_POLYGON16, EMR_POLYBEZIER16, EMR_POLYLINETO16, EMR_POLYBEZIERTO16}:
                pontos = self._parse_poly_points16(p)
                pontos = self._apply_transform_points(pontos)
                if t in {EMR_POLYBEZIER16, EMR_POLYBEZIERTO16}:
                    pontos = self._densificar_bezier(pontos)
                fechado = t == EMR_POLYGON16
                if t in {EMR_POLYLINETO16, EMR_POLYBEZIERTO16} and self._current_point:
                    pontos = [self._current_point] + pontos
                if pontos:
                    self._current_point = pontos[-1]
                    self._push_points(t, pontos, fechado, elementos)
            elif t in {EMR_POLYPOLYLINE, EMR_POLYPOLYGON}:
                for pts in self._parse_poly_poly32(p):
                    pts = self._apply_transform_points(pts)
                    self._push_points(t, pts, t == EMR_POLYPOLYGON, elementos)
            elif t in {EMR_POLYPOLYLINE16, EMR_POLYPOLYGON16}:
                for pts in self._parse_poly_poly16(p):
                    pts = self._apply_transform_points(pts)
                    self._push_points(t, pts, t == EMR_POLYPOLYGON16, elementos)
            elif t == EMR_POLYDRAW:
                pts = self._apply_transform_points(self._parse_poly_points32(p))
                types = self._parse_polydraw_types32(p)
                self._apply_polydraw(pts, types, t, elementos)
            elif t == EMR_POLYDRAW16:
                pts = self._apply_transform_points(self._parse_poly_points16(p))
                types = self._parse_polydraw_types16(p)
                self._apply_polydraw(pts, types, t, elementos)
            elif t == EMR_MOVETOEX:
                pt = self._parse_pointl(p, 0)
                if pt:
                    pt = self._apply_transform_point(pt)
                    self._current_point = pt
                    if self._in_path:
                        self._path_points = [pt]
                        self._path_closed = False
            elif t == EMR_LINETO:
                pt = self._parse_pointl(p, 0)
                if pt:
                    pt = self._apply_transform_point(pt)
                    if self._current_point:
                        self._push_points(t, [self._current_point, pt], False, elementos)
                    self._current_point = pt
                    if self._in_path:
                        self._path_points.append(pt)
            elif t == EMR_BEGINPATH:
                self._in_path = True
                self._path_points = []
                self._path_closed = False
            elif t == EMR_CLOSEFIGURE:
                if self._path_points:
                    self._path_points.append(self._path_points[0])
                    self._path_closed = True
            elif t in {EMR_ENDPATH, EMR_FILLPATH, EMR_STROKEPATH, EMR_STROKEANDFILLPATH}:
                if t in {EMR_FILLPATH, EMR_STROKEANDFILLPATH} and self._path_points:
                    self._push_points(t, list(self._path_points), True or self._path_closed, elementos)
                elif t == EMR_STROKEPATH and self._path_points:
                    self._push_points(t, list(self._path_points), self._path_closed, elementos)
                if t != EMR_ENDPATH:
                    self._in_path = False
                    self._path_points = []
                    self._path_closed = False
            elif t == EMR_RECTANGLE:
                pts = self._apply_transform_points(self._parse_rect_poly(p))
                self._push_points(t, pts, True, elementos)
            elif t == EMR_ELLIPSE:
                pts = self._apply_transform_points(self._parse_ellipse_poly(p))
                self._push_points(t, pts, True, elementos)
            elif t == EMR_ARC:
                pts = self._apply_transform_points(self._parse_arc_poly(p))
                self._push_points(t, pts, False, elementos)
            elif t in {EMR_EXTTEXTOUTA, EMR_EXTTEXTOUTW}:
                txt = self._parse_text_record(p, wide=t == EMR_EXTTEXTOUTW)
                if txt:
                    x, y = txt.get("pos", (0.0, 0.0))
                    txt["pos"] = self._apply_transform_point((x, y))
                    textos.append(txt)
            elif t in {EMR_CREATEPEN, EMR_SELECTOBJECT, EMR_DELETEOBJECT}:
                continue
            else:
                self._unsupported[t] = self._unsupported.get(t, 0) + 1

        elementos = [e for e in elementos if len(e.pontos) >= 2]
        self._normalizar_para_cm(elementos, textos, bounds)
        elementos = self._filtrar_ruido_emf(elementos)
        elementos = self._limpar_duplicatas_e_classificar_pares(elementos)
        self._classificar_subtipos(elementos)
        if self.reconstruir_curvas_audaces:
            self._aplicar_reconstrucao_curvas(elementos)
        if self.suavizar_curvas_audaces:
            self._aplicar_suavizacao_audaces(elementos)
        return elementos, textos, bounds

    @staticmethod
    def _area_assinada(pontos: list[tuple[float, float]]) -> float:
        if len(pontos) < 3:
            return 0.0
        area = 0.0
        pts = list(pontos)
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            area += (ax * by) - (bx * ay)
        return area / 2.0

    @staticmethod
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

    def _classificar_subtipos(self, elementos: list[EMFVectorElement]) -> None:
        """Classifica vetores Audaces para snap/medição.

        O contorno principal deve ser o único elemento fechado marcado como
        molde. Costura/margem pontilhada continua visível, mas não deve ser
        tratada como molde principal. Linhas abertas permanecem como
        linhas internas/técnicas.
        """
        fechados = [
            (i, e, abs(self._area_assinada(e.pontos)))
            for i, e in enumerate(elementos)
            if e.fechado and len(e.pontos) >= 4
        ]
        idx_contorno = None
        if fechados:
            idx_contorno = max(fechados, key=lambda item: item[2])[0]

        contorno = elementos[idx_contorno] if idx_contorno is not None else None
        for i, el in enumerate(elementos):
            subtipo_forcado = str(el.metadados.get("subtipo_audaces") or "").strip()
            if subtipo_forcado in {"texto", "fio", "pique", "anotacao", "costura", "linha_interna", "contorno"}:
                subtipo = subtipo_forcado
            elif el.fechado:
                if i == idx_contorno:
                    subtipo = "contorno"
                elif contorno is not None and el.pontos and self._ponto_em_poligono(el.pontos[0], contorno.pontos):
                    subtipo = "costura"
                else:
                    subtipo = "linha_interna"
            else:
                subtipo = "linha_interna"
            el.metadados["subtipo_audaces"] = subtipo
            el.metadados["snap_habilitado"] = subtipo in {"contorno", "costura", "linha_interna", "fio", "pique"}

    def converter_para_elementos_guimma(self, doc: AudacesEMFDocument) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for el in doc.elementos:
            pts = list(el.pontos)
            if el.fechado and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            out.append(
                {
                    "tipo": "polyline",
                    "pontos": pts,
                    "cor": el.cor or "#ff7b00",
                    "origem": "audaces_emf",
                    "raw_record_type": el.raw_record_type,
                    "metadados": dict(el.metadados),
                    "subtipo_audaces": el.metadados.get("subtipo_audaces", "linha_interna"),
                    "molde": bool(el.fechado and el.metadados.get("subtipo_audaces") == "contorno"),
                    "bloqueado": False,
                    "render_smooth": bool(el.metadados.get("subtipo_audaces") in {"contorno", "costura"}),
                }
            )
        for tx in doc.textos:
            out.append({
                "tipo": "texto",
                "texto": tx.get("texto", ""),
                "pos": tx.get("pos", (0.0, 0.0)),
                "cor": "#d9d9d9",
                "tamanho": 0.9,
                "origem": "audaces_emf_texto",
                "subtipo_audaces": "texto",
                "metadados": {"subtipo_audaces": "texto", "snap_habilitado": False},
            })
        return out

    def _unir_segmentos_em_contornos(self, elementos: list[EMFVectorElement]) -> list[EMFVectorElement]:
        tolerancia_cm = max(0.1, min(0.2, float(self.tolerancia_uniao_mm) / 10.0))
        self._join_stats["segmentos_originais"] = len(elementos)
        agrupados: dict[str, list[EMFVectorElement]] = {}
        for el in elementos:
            subtipo = str(el.metadados.get("subtipo_audaces") or "")
            if subtipo in {"texto", "anotacao", "fio", "pique"}:
                continue
            if len(el.pontos) < 2:
                continue
            agrupados.setdefault(subtipo, []).append(el)
        saida: list[EMFVectorElement] = []
        unidos = 0
        for subtipo, grupo in agrupados.items():
            pendentes = [EMFVectorElement(**asdict(el)) for el in grupo]
            while pendentes:
                base = pendentes.pop(0)
                pts = list(base.pontos)
                alterou = True
                while alterou:
                    alterou = False
                    for i, cand in enumerate(pendentes):
                        a0, a1 = pts[0], pts[-1]
                        b0, b1 = cand.pontos[0], cand.pontos[-1]
                        if self._dist(a1, b0) <= tolerancia_cm:
                            pts.extend(cand.pontos[1:])
                        elif self._dist(a1, b1) <= tolerancia_cm:
                            pts.extend(reversed(cand.pontos[:-1]))
                        elif self._dist(a0, b1) <= tolerancia_cm:
                            pts = list(cand.pontos[:-1]) + pts
                        elif self._dist(a0, b0) <= tolerancia_cm:
                            pts = list(reversed(cand.pontos[1:])) + pts
                        else:
                            continue
                        pendentes.pop(i)
                        unidos += 1
                        alterou = True
                        break
                fechado = self._dist(pts[0], pts[-1]) <= tolerancia_cm
                if fechado and pts[0] != pts[-1]:
                    pts.append(pts[0])
                novo = self._mk_element(base.tipo, pts, fechado, base.raw_record_type)
                novo.metadados.update(base.metadados)
                novo.metadados["subtipo_audaces"] = subtipo
                saida.append(novo)
        self._join_stats["segmentos_unidos"] = unidos
        self._join_stats["contornos_fechados"] = sum(1 for e in saida if e.fechado and e.metadados.get("subtipo_audaces") == "contorno")
        return saida

    @staticmethod
    def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def _reconstruir_curvas_do_contorno(self, contorno: EMFVectorElement) -> EMFVectorElement:
        antes = self._comprimento_polyline(contorno.pontos)
        novo = self._reconstruir_curvas_por_trechos(contorno)
        if isinstance(novo, list):
            contorno_novo = self._mk_element(contorno.tipo, novo, contorno.fechado, contorno.raw_record_type)
            contorno_novo.metadados.update(contorno.metadados)
            novo = contorno_novo
        depois = self._comprimento_polyline(novo.pontos)
        if antes > 0 and abs(depois - antes) / antes > 0.005:
            return contorno
        novo.metadados["curva_reconstruida"] = True
        novo.metadados["metodo_curva"] = "catmull_rom_centripeto"
        novo.metadados["perimetro_antes"] = antes
        novo.metadados["perimetro_depois"] = depois
        self._join_stats["curvas_reconstruidas"] += 1
        return novo

    def gerar_relatorio(self, elementos: list[EMFVectorElement], textos: list[dict[str, Any]], bounds: tuple[float, float, float, float]) -> dict[str, Any]:
        return {
            "tamanho_arquivo": len(self.raw),
            "bounds_emf": bounds,
            "frame_cm": self._frame_cm,
            "orientacao_y": "preservada_do_emf_sem_espelhar_vertical",
            "records_total": len(self.records),
            "records_tipos": dict(sorted(self._record_types.items())),
            "records_nao_suportados": dict(sorted(self._unsupported.items())),
            "quantidade_polylines": sum(self._record_types.get(k, 0) for k in (EMR_POLYLINE, EMR_POLYLINE16, EMR_POLYLINETO, EMR_POLYLINETO16, EMR_POLYPOLYLINE, EMR_POLYPOLYLINE16, EMR_POLYDRAW, EMR_POLYDRAW16)),
            "quantidade_polygons": sum(self._record_types.get(k, 0) for k in (EMR_POLYGON, EMR_POLYGON16, EMR_POLYPOLYGON, EMR_POLYPOLYGON16)),
            "quantidade_beziers": sum(self._record_types.get(k, 0) for k in (EMR_POLYBEZIER, EMR_POLYBEZIER16, EMR_POLYBEZIERTO, EMR_POLYBEZIERTO16)),
            "quantidade_textos": len(textos),
            "elementos_convertidos": len(elementos),
            "contornos_fechados": sum(1 for e in elementos if e.fechado),
            "possiveis_moldes": sum(1 for e in elementos if e.fechado),
            "contornos_detectados": sum(1 for e in elementos if e.metadados.get("subtipo_audaces") == "contorno"),
            "costuras_detectadas": sum(1 for e in elementos if e.metadados.get("subtipo_audaces") == "costura"),
            "linhas_internas_detectadas": sum(1 for e in elementos if e.metadados.get("subtipo_audaces") == "linha_interna"),
            "textos_detectados": len(textos),
            "duplicatas_removidas": int(self._dedupe_stats.get("removidas", 0)),
            "duplicatas_reclassificadas_costura": int(self._dedupe_stats.get("reclassificadas_costura", 0)),
            "elementos_ignorados": int(self._dedupe_stats.get("ignoradas", 0)),
            "suavizacao_curvas_audaces": bool(self.suavizar_curvas_audaces),
            "reconstrucao_curvas_audaces": bool(self.reconstruir_curvas_audaces),
            "elementos_suavizados": int(self._smooth_stats.get("elementos_suavizados", 0)),
            "pontos_removidos_jitter": int(self._smooth_stats.get("pontos_removidos_jitter", 0)),
            "cantos_preservados": int(self._smooth_stats.get("cantos_preservados", 0)),
            "suavizados_contorno": int(self._smooth_stats.get("suavizados_contorno", 0)),
            "suavizados_costura": int(self._smooth_stats.get("suavizados_costura", 0)),
            "trechos_reconstruidos": int(self._smooth_stats.get("trechos_reconstruidos", 0)),
            "trechos_rejeitados_perimetro": int(self._smooth_stats.get("trechos_rejeitados_perimetro", 0)),
            "segmentos_originais_lidos_emf": int(self._join_stats.get("segmentos_originais", 0)),
            "segmentos_unidos": int(self._join_stats.get("segmentos_unidos", 0)),
            "contornos_fechados_encontrados": int(self._join_stats.get("contornos_fechados", 0)),
            "curvas_reconstruidas": int(self._join_stats.get("curvas_reconstruidas", 0)),
            "map_mode": self._map_mode,
            "window_org": self._window_org,
            "window_ext": self._window_ext,
            "viewport_org": self._viewport_org,
            "viewport_ext": self._viewport_ext,
            "world_transform": self._world,
            "escala": self._calc_scale(),
            "avisos": list(self._warnings),
        }

    def _process_transform_record(self, t: int, payload: bytes):
        if t == EMR_SETMAPMODE and len(payload) >= 4:
            self._map_mode = struct.unpack_from("<i", payload, 0)[0]
        elif t == EMR_SETWINDOWORGEX and len(payload) >= 8:
            self._window_org = tuple(float(v) for v in struct.unpack_from("<2i", payload, 0))
        elif t == EMR_SETWINDOWEXTEX and len(payload) >= 8:
            w, h = struct.unpack_from("<2i", payload, 0)
            self._window_ext = (float(w or 1), float(h or 1))
        elif t == EMR_SETVIEWPORTORGEX and len(payload) >= 8:
            self._viewport_org = tuple(float(v) for v in struct.unpack_from("<2i", payload, 0))
        elif t == EMR_SETVIEWPORTEXTEX and len(payload) >= 8:
            w, h = struct.unpack_from("<2i", payload, 0)
            self._viewport_ext = (float(w or 1), float(h or 1))
        elif t == EMR_SETWORLDTRANSFORM and len(payload) >= 24:
            self._world = tuple(float(v) for v in struct.unpack_from("<6f", payload, 0))
        elif t == EMR_MODIFYWORLDTRANSFORM and len(payload) >= 28:
            m = tuple(float(v) for v in struct.unpack_from("<6f", payload, 0))
            mode = struct.unpack_from("<I", payload, 24)[0]
            self._world = self._combine_world(self._world, m, mode)

    @staticmethod
    def _combine_world(a: tuple[float, ...], b: tuple[float, ...], mode: int) -> tuple[float, ...]:
        if mode == 1:  # MWT_IDENTITY
            return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        if mode == 2:  # left multiply
            return AudacesEMFImport._mul_world(b, a)
        if mode == 3:  # right multiply
            return AudacesEMFImport._mul_world(a, b)
        return b

    @staticmethod
    def _mul_world(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
        a11, a12, a21, a22, adx, ady = a
        b11, b12, b21, b22, bdx, bdy = b
        return (
            a11 * b11 + a12 * b21,
            a11 * b12 + a12 * b22,
            a21 * b11 + a22 * b21,
            a21 * b12 + a22 * b22,
            adx * b11 + ady * b21 + bdx,
            adx * b12 + ady * b22 + bdy,
        )

    def _apply_transform_point(self, pt: tuple[float, float]) -> tuple[float, float]:
        x, y = pt
        a11, a12, a21, a22, dx, dy = self._world
        wx = (x * a11) + (y * a21) + dx
        wy = (x * a12) + (y * a22) + dy
        wo_x, wo_y = self._window_org
        we_x, we_y = self._window_ext
        vo_x, vo_y = self._viewport_org
        ve_x, ve_y = self._viewport_ext
        sx = ve_x / we_x if abs(we_x) > 1e-9 else 1.0
        sy = ve_y / we_y if abs(we_y) > 1e-9 else 1.0
        mx = ((wx - wo_x) * sx) + vo_x
        my = ((wy - wo_y) * sy) + vo_y
        return float(mx), float(my)

    def _apply_transform_points(self, pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [self._apply_transform_point(p) for p in pts]

    def _push_points(self, rec_type: int, pontos: list[tuple[float, float]], fechado: bool, elementos: list[EMFVectorElement]):
        if not pontos:
            return
        if self._in_path:
            if not self._path_points:
                self._path_points = list(pontos)
            else:
                self._path_points.extend(pontos[1:] if len(pontos) > 1 else pontos)
            self._path_closed = self._path_closed or fechado
            return
        elementos.append(self._mk_element("polyline", pontos, fechado, rec_type))

    @staticmethod
    def _bbox(pontos: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    def _mk_element(self, tipo: str, pontos: list[tuple[float, float]], fechado: bool, raw_type: int) -> EMFVectorElement:
        if fechado and pontos and pontos[0] != pontos[-1]:
            pontos = list(pontos) + [pontos[0]]
        return EMFVectorElement(tipo=tipo, pontos=list(pontos), fechado=fechado, cor="#ff7b00", espessura=None, bbox=self._bbox(pontos), raw_record_type=raw_type)

    @staticmethod
    def _parse_bounds_header(payload: bytes) -> tuple[float, float, float, float] | None:
        if len(payload) < 16:
            return None
        return tuple(float(v) for v in struct.unpack_from("<4i", payload, 0))

    @staticmethod
    def _parse_pointl(payload: bytes, offset: int) -> tuple[float, float] | None:
        if len(payload) < offset + 8:
            return None
        x, y = struct.unpack_from("<2i", payload, offset)
        return float(x), float(y)

    @staticmethod
    def _parse_points16(payload: bytes, offset: int, count: int) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for i in range(count):
            start = offset + (i * 4)
            if len(payload) < start + 4:
                break
            x, y = struct.unpack_from("<2h", payload, start)
            out.append((float(x), float(y)))
        return out

    @staticmethod
    def _parse_points32(payload: bytes, offset: int, count: int) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for i in range(count):
            start = offset + (i * 8)
            if len(payload) < start + 8:
                break
            x, y = struct.unpack_from("<2i", payload, start)
            out.append((float(x), float(y)))
        return out

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

    def _parse_polydraw_types32(self, payload: bytes) -> list[int]:
        if len(payload) < 20:
            return []
        cpt = struct.unpack_from("<I", payload, 16)[0]
        types_off = 20 + (cpt * 8)
        return list(payload[types_off : types_off + cpt])

    def _parse_polydraw_types16(self, payload: bytes) -> list[int]:
        if len(payload) < 20:
            return []
        cpt = struct.unpack_from("<I", payload, 16)[0]
        types_off = 20 + (cpt * 4)
        return list(payload[types_off : types_off + cpt])

    def _apply_polydraw(self, pts: list[tuple[float, float]], types: list[int], rec_type: int, elementos: list[EMFVectorElement]):
        if not pts:
            return
        seq: list[tuple[float, float]] = []
        for pt, tp in zip(pts, types):
            base = tp & 0x06
            close = bool(tp & 0x01)
            if base == 0x06:  # move
                if len(seq) >= 2:
                    self._push_points(rec_type, seq, False, elementos)
                seq = [pt]
            elif base in {0x02, 0x04}:
                seq.append(pt)
            else:
                seq.append(pt)
            if close and seq:
                seq.append(seq[0])
                self._push_points(rec_type, seq, True, elementos)
                seq = []
        if len(seq) >= 2:
            self._push_points(rec_type, seq, False, elementos)

    def _parse_poly_poly32(self, payload: bytes) -> list[list[tuple[float, float]]]:
        if len(payload) < 24:
            return []
        n_poly, cpt = struct.unpack_from("<2I", payload, 16)
        counts = [struct.unpack_from("<I", payload, 24 + (i * 4))[0] for i in range(n_poly) if len(payload) >= 28 + (i * 4)]
        pts_off = 24 + (4 * len(counts))
        all_pts = self._parse_points32(payload, pts_off, cpt)
        out = []
        idx = 0
        for c in counts:
            chunk = all_pts[idx : idx + c]
            if chunk:
                out.append(chunk)
            idx += c
        return out

    def _parse_poly_poly16(self, payload: bytes) -> list[list[tuple[float, float]]]:
        if len(payload) < 24:
            return []
        n_poly, cpt = struct.unpack_from("<2I", payload, 16)
        counts = [struct.unpack_from("<I", payload, 24 + (i * 4))[0] for i in range(n_poly) if len(payload) >= 28 + (i * 4)]
        pts_off = 24 + (4 * len(counts))
        all_pts = self._parse_points16(payload, pts_off, cpt)
        out = []
        idx = 0
        for c in counts:
            chunk = all_pts[idx : idx + c]
            if chunk:
                out.append(chunk)
            idx += c
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
        steps = 128
        return [(cx + (rx * cos((2 * pi * i) / steps)), cy + (ry * sin((2 * pi * i) / steps))) for i in range(steps + 1)]

    def _parse_arc_poly(self, payload: bytes) -> list[tuple[float, float]]:
        if len(payload) < 32:
            return []
        l, t, r, b, sx, sy, ex, ey = struct.unpack_from("<8i", payload, 0)
        cx, cy = (l + r) / 2.0, (t + b) / 2.0
        rx, ry = abs(r - l) / 2.0, abs(b - t) / 2.0
        if rx <= 0 or ry <= 0:
            return []
        a0 = atan2((sy - cy) / max(ry, 1e-6), (sx - cx) / max(rx, 1e-6))
        a1 = atan2((ey - cy) / max(ry, 1e-6), (ex - cx) / max(rx, 1e-6))
        if a1 < a0:
            a1 += 2 * pi
        steps = 64
        return [(cx + (rx * cos(a0 + ((a1 - a0) * (i / steps)))), cy + (ry * sin(a0 + ((a1 - a0) * (i / steps))))) for i in range(steps + 1)]

    @staticmethod
    def _densificar_bezier(pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Converte Bézier cúbica em pontos densos.

        O Audaces usa curvas suaves. Com poucas subdivisões, a cava,
        decote, gancho e laterais ficam serrilhados. Usamos 48
        subdivisões por trecho para deixar as curvas mais nítidas.
        """
        if len(pontos) < 4:
            return pontos
        out = [pontos[0]]
        i = 1
        steps = 96
        while i + 2 < len(pontos):
            p0 = out[-1]
            p1, p2, p3 = pontos[i], pontos[i + 1], pontos[i + 2]
            for j in range(1, steps + 1):
                t = j / float(steps)
                mt = 1 - t
                x = (mt**3) * p0[0] + 3 * (mt**2) * t * p1[0] + 3 * mt * (t**2) * p2[0] + (t**3) * p3[0]
                y = (mt**3) * p0[1] + 3 * (mt**2) * t * p1[1] + 3 * mt * (t**2) * p2[1] + (t**3) * p3[1]
                if not out or abs(out[-1][0] - x) > 1e-9 or abs(out[-1][1] - y) > 1e-9:
                    out.append((x, y))
            i += 3
        return out

    @staticmethod
    def _parse_text_record(payload: bytes, wide: bool) -> dict[str, Any] | None:
        if len(payload) < 8:
            return None
        x, y = struct.unpack_from("<2i", payload, 0)
        txt = payload.decode("utf-16-le" if wide else "latin-1", errors="ignore")
        txt = " ".join("".join(ch for ch in txt if ch.isprintable()).split())[:140]
        if not txt:
            return None
        return {"texto": txt, "pos": (float(x), float(y))}

    @staticmethod
    def _parse_frame_header_cm(payload: bytes) -> tuple[float, float, float, float] | None:
        # EMR_HEADER.rclFrame fica logo após rclBounds e usa unidade 0,01 mm.
        # Como o canvas do GUIMMA trabalha em cm, convertemos: 0,01 mm = 0,001 cm.
        if len(payload) < 32:
            return None
        l, t, r, b = struct.unpack_from("<4i", payload, 16)
        return (l / 1000.0, t / 1000.0, r / 1000.0, b / 1000.0)

    def _normalizar_para_cm(self, elementos: list[EMFVectorElement], textos: list[dict[str, Any]], bounds: tuple[float, float, float, float]):
        left, top, right, bottom = bounds
        bw = max(right - left, 1.0)
        bh = max(bottom - top, 1.0)
        if self._frame_cm:
            fl, ft, fr, fb = self._frame_cm
            fw = abs(fr - fl) or bw
            fh = abs(fb - ft) or bh
            sx = fw / bw
            sy = fh / bh
        else:
            sx = 1.0
            sy = 1.0

        def conv(pt: tuple[float, float]) -> tuple[float, float]:
            x, y = pt
            return ((x - left) * sx, (y - top) * sy)

        for el in elementos:
            el.pontos = [conv((float(x), float(y))) for x, y in el.pontos]
            el.bbox = AudacesEMFImport._bbox(el.pontos)
            el.metadados.setdefault("escala_origem", "emf_frame_cm")
        for tx in textos:
            x, y = tx.get("pos", (0.0, 0.0))
            tx["pos"] = conv((float(x), float(y)))

    @staticmethod
    def _comprimento_polyline(pontos: list[tuple[float, float]]) -> float:
        total = 0.0
        for a, b in zip(pontos, pontos[1:]):
            dx = b[0] - a[0]
            dy = b[1] - a[1]
            total += (dx * dx + dy * dy) ** 0.5
        return total

    def _filtrar_ruido_emf(self, elementos: list[EMFVectorElement]) -> list[EMFVectorElement]:
        """Filtra somente sujeira real, preservando costura/margem.

        No EMF do Audaces, a linha pontilhada em volta do molde é
        informação técnica de costura/margem. Ela não deve ser descartada.
        Removemos apenas fragmentos mínimos típicos de textos, números e
        símbolos pequenos.
        """
        filtrados: list[EMFVectorElement] = []
        vistos: set[tuple] = set()
        for el in elementos:
            bbox = el.bbox or self._bbox(el.pontos)
            if not bbox:
                continue
            minx, miny, maxx, maxy = bbox
            w = abs(maxx - minx)
            h = abs(maxy - miny)
            area = w * h
            comp = self._comprimento_polyline(el.pontos)

            # Ruído muito pequeno de caracteres, graus, números e logo.
            if max(w, h) < 0.04:
                self._dedupe_stats["ignoradas"] += 1
                continue
            if comp < 0.06:
                self._dedupe_stats["ignoradas"] += 1
                continue
            if el.fechado and area < 0.008:
                self._dedupe_stats["ignoradas"] += 1
                continue
            if el.raw_record_type == EMR_RECTANGLE and area < 0.08:
                self._dedupe_stats["ignoradas"] += 1
                continue

            # Remove duplicata exata/quase exata sem apagar costuras paralelas.
            chave = (
                round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3),
                round(comp, 3), bool(el.fechado), el.raw_record_type,
            )
            if chave in vistos:
                continue
            vistos.add(chave)

            if el.fechado:
                el.metadados.setdefault("subtipo_audaces", "contorno")
            else:
                el.metadados.setdefault("subtipo_audaces", "costura_ou_linha_tecnica")
            filtrados.append(el)
        return filtrados

    @staticmethod
    def _angulo_interno_graus(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        v1x, v1y = a[0] - b[0], a[1] - b[1]
        v2x, v2y = c[0] - b[0], c[1] - b[1]
        n1 = (v1x * v1x + v1y * v1y) ** 0.5
        n2 = (v2x * v2x + v2y * v2y) ** 0.5
        if n1 <= 1e-9 or n2 <= 1e-9:
            return 180.0
        cosv = max(-1.0, min(1.0, ((v1x * v2x) + (v1y * v2y)) / (n1 * n2)))
        return abs(acos(cosv) * 180.0 / pi)

    def _suavizar_curvas_audaces(self, pontos: list[tuple[float, float]], fechado: bool = False) -> list[tuple[float, float]]:
        if len(pontos) < 4:
            return pontos
        base = list(pontos)
        if fechado and base[0] == base[-1]:
            base = base[:-1]
        if len(base) < 4:
            return pontos

        deslocamento_maximo = 0.15
        threshold_canto_graus = 30.0
        pontos_removidos = 0
        cantos_preservados = 0

        # remove jitter mínimo preservando extremos
        limp: list[tuple[float, float]] = [base[0]]
        for i in range(1, len(base) - 1):
            prev = limp[-1]
            cur = base[i]
            nxt = base[i + 1]
            seg = self._dist_pt(prev, cur)
            if seg < 0.012 and self._dist_pt(prev, nxt) < 0.05:
                pontos_removidos += 1
                continue
            limp.append(cur)
        limp.append(base[-1])
        work = limp
        if len(work) < 4:
            return pontos

        iters = 2 if len(work) > 24 else 1
        for _ in range(iters):
            novo = list(work)
            start = 0 if fechado else 1
            end = len(work) if fechado else len(work) - 1
            for i in range(start, end):
                im1 = (i - 1) % len(work)
                ip1 = (i + 1) % len(work)
                a, b, c = work[im1], work[i], work[ip1]
                ang = self._angulo_interno_graus(a, b, c)
                if ang <= threshold_canto_graus:
                    cantos_preservados += 1
                    continue
                midx = (a[0] + c[0]) * 0.5
                midy = (a[1] + c[1]) * 0.5
                nx = (b[0] * 0.6) + (midx * 0.4)
                ny = (b[1] * 0.6) + (midy * 0.4)
                dx = nx - b[0]
                dy = ny - b[1]
                d = (dx * dx + dy * dy) ** 0.5
                if d > deslocamento_maximo:
                    f = deslocamento_maximo / max(d, 1e-9)
                    nx = b[0] + (dx * f)
                    ny = b[1] + (dy * f)
                novo[i] = (nx, ny)
            work = novo
        if not fechado:
            work[0] = base[0]
            work[-1] = base[-1]
        self._smooth_stats["pontos_removidos_jitter"] += pontos_removidos
        self._smooth_stats["cantos_preservados"] += cantos_preservados
        if fechado:
            work.append(work[0])
        return work

    def _aplicar_suavizacao_audaces(self, elementos: list[EMFVectorElement]) -> None:
        for el in elementos:
            subtipo = str(el.metadados.get("subtipo_audaces") or "").strip()
            if subtipo not in {"contorno", "costura", "linha_interna"}:
                continue
            if subtipo == "linha_interna" and (not el.fechado or len(el.pontos) < 16):
                continue
            antes = list(el.pontos)
            depois = self._suavizar_curvas_audaces(antes, fechado=el.fechado)
            if len(depois) >= 2 and depois != antes:
                el.pontos = depois
                el.bbox = self._bbox(el.pontos)
                self._smooth_stats["elementos_suavizados"] += 1
                if subtipo == "contorno":
                    self._smooth_stats["suavizados_contorno"] += 1
                elif subtipo == "costura":
                    self._smooth_stats["suavizados_costura"] += 1

    def _aplicar_reconstrucao_curvas(self, elementos: list[EMFVectorElement]) -> None:
        for el in elementos:
            subtipo = str(el.metadados.get("subtipo_audaces") or "").strip()
            if subtipo not in {"contorno", "costura"}:
                continue
            if len(el.pontos) < 8:
                continue
            novos = self._reconstruir_curvas_por_trechos(el)
            if novos and novos != el.pontos:
                el.metadados["pontos_originais_emf"] = list(el.pontos)
                el.pontos = novos
                el.bbox = self._bbox(el.pontos)

    def _reconstruir_curvas_por_trechos(self, elemento: EMFVectorElement) -> list[tuple[float, float]]:
        pts = list(elemento.pontos)
        fechado = bool(elemento.fechado)
        if fechado and pts and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 6:
            return elemento.pontos
        forte = 30.0
        cortes = [0]
        for i in range(1, len(pts) - 1):
            ang = self._angulo_interno_graus(pts[i - 1], pts[i], pts[i + 1])
            if ang <= forte:
                cortes.append(i)
                self._smooth_stats["cantos_preservados"] += 1
        cortes.append(len(pts) - 1)
        cortes = sorted(set(cortes))
        saida: list[tuple[float, float]] = [pts[0]]
        per_antes = self._comprimento_polyline(pts + ([pts[0]] if fechado else []))
        for a, b in zip(cortes, cortes[1:]):
            trecho = pts[a:b + 1]
            if len(trecho) < 5:
                for p in trecho[1:]:
                    saida.append(p)
                continue
            novo = self._reamostrar_catmull_rom(trecho, amostras=max(len(trecho) * 2, 18))
            limitado = self._limitar_deslocamento(trecho, novo, max_desloc=0.15)
            comp_a = self._comprimento_polyline(trecho)
            comp_b = self._comprimento_polyline(limitado)
            if comp_a > 1e-9 and abs(comp_b - comp_a) / comp_a > 0.005:
                self._smooth_stats["trechos_rejeitados_perimetro"] += 1
                for p in trecho[1:]:
                    saida.append(p)
                continue
            self._smooth_stats["trechos_reconstruidos"] += 1
            for p in limitado[1:]:
                saida.append(p)
        if fechado and saida[0] != saida[-1]:
            saida.append(saida[0])
        per_dep = self._comprimento_polyline(saida)
        if per_antes > 1e-9 and abs(per_dep - per_antes) / per_antes > 0.005:
            return elemento.pontos
        elemento.metadados["curva_reconstruida"] = True
        elemento.metadados["metodo_curva"] = "catmull_rom_centripeto"
        elemento.metadados["perimetro_antes"] = per_antes
        elemento.metadados["perimetro_depois"] = per_dep
        return saida

    def _reamostrar_catmull_rom(self, pts: list[tuple[float, float]], amostras: int) -> list[tuple[float, float]]:
        if len(pts) < 4:
            return pts
        out: list[tuple[float, float]] = [pts[0]]
        for i in range(1, len(pts) - 2):
            p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
            n = max(6, amostras // max(1, len(pts) - 3))
            for j in range(1, n + 1):
                t = j / n
                t2, t3 = t * t, t * t * t
                x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2*p0[0]-5*p1[0]+4*p2[0]-p3[0]) * t2 + (-p0[0]+3*p1[0]-3*p2[0]+p3[0]) * t3)
                y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2*p0[1]-5*p1[1]+4*p2[1]-p3[1]) * t2 + (-p0[1]+3*p1[1]-3*p2[1]+p3[1]) * t3)
                out.append((x, y))
        out.append(pts[-1])
        return out

    def _limitar_deslocamento(self, original: list[tuple[float, float]], novo: list[tuple[float, float]], max_desloc: float) -> list[tuple[float, float]]:
        if len(novo) <= 2:
            return novo
        res = [novo[0]]
        for i in range(1, len(novo) - 1):
            t = i / max(1, len(novo) - 1)
            idx = min(len(original) - 1, max(0, int(round(t * (len(original) - 1)))))
            ref = original[idx]
            cur = novo[i]
            dx, dy = cur[0] - ref[0], cur[1] - ref[1]
            d = (dx * dx + dy * dy) ** 0.5
            if d > max_desloc:
                f = max_desloc / d
                cur = (ref[0] + dx * f, ref[1] + dy * f)
            res.append(cur)
        res.append(novo[-1])
        return res

    @staticmethod
    def _dist_pt(a: tuple[float, float], b: tuple[float, float]) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return (dx * dx + dy * dy) ** 0.5

    def _similaridade_geometrica(self, a: EMFVectorElement, b: EMFVectorElement) -> tuple[bool, bool]:
        if not a.bbox or not b.bbox:
            return False, False
        a_minx, a_miny, a_maxx, a_maxy = a.bbox
        b_minx, b_miny, b_maxx, b_maxy = b.bbox
        aw, ah = max(a_maxx - a_minx, 1e-9), max(a_maxy - a_miny, 1e-9)
        bw, bh = max(b_maxx - b_minx, 1e-9), max(b_maxy - b_miny, 1e-9)
        tol_bbox = max(0.06, max(aw, ah, bw, bh) * 0.01)
        bbox_quase_igual = (
            abs(a_minx - b_minx) <= tol_bbox and abs(a_miny - b_miny) <= tol_bbox and
            abs(a_maxx - b_maxx) <= tol_bbox and abs(a_maxy - b_maxy) <= tol_bbox
        )
        ca = self._comprimento_polyline(a.pontos)
        cb = self._comprimento_polyline(b.pontos)
        tol_len = max(0.08, max(ca, cb) * 0.02)
        len_quase_igual = abs(ca - cb) <= tol_len
        pa = a.pontos[min(len(a.pontos) - 1, len(a.pontos) // 2)]
        pb = b.pontos[min(len(b.pontos) - 1, len(b.pontos) // 2)]
        desloc = self._dist_pt(pa, pb)
        quase_identico = bbox_quase_igual and len_quase_igual and desloc <= max(0.03, tol_bbox * 0.5)
        paralelo_proximo = bbox_quase_igual and len_quase_igual and desloc <= max(0.22, tol_bbox * 3.0)
        return quase_identico, paralelo_proximo

    def _limpar_duplicatas_e_classificar_pares(self, elementos: list[EMFVectorElement]) -> list[EMFVectorElement]:
        saida: list[EMFVectorElement] = []
        for el in elementos:
            if len(el.pontos) < 2:
                self._dedupe_stats["ignoradas"] += 1
                continue
            duplicado = False
            for kept in saida:
                quase_identico, paralelo_proximo = self._similaridade_geometrica(kept, el)
                if quase_identico:
                    self._dedupe_stats["removidas"] += 1
                    duplicado = True
                    break
                if paralelo_proximo and kept.fechado and el.fechado:
                    if kept.metadados.get("subtipo_audaces") != "costura":
                        kept.metadados["subtipo_audaces"] = "contorno"
                    el.metadados["subtipo_audaces"] = "costura"
                    self._dedupe_stats["reclassificadas_costura"] += 1
            if not duplicado:
                saida.append(el)
        return saida

    def _calc_scale(self) -> dict[str, float]:
        sx_vp = self._viewport_ext[0] / self._window_ext[0] if abs(self._window_ext[0]) > 1e-9 else 1.0
        sy_vp = self._viewport_ext[1] / self._window_ext[1] if abs(self._window_ext[1]) > 1e-9 else 1.0
        if self._frame_cm:
            # escala real aplicada ao EMF: pixel/EMF bounds -> centímetros de cena.
            return {"sx": float(sx_vp), "sy": float(sy_vp), "frame_cm": list(self._frame_cm)}
        return {"sx": float(sx_vp), "sy": float(sy_vp)}


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
