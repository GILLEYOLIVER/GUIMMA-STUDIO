from __future__ import annotations

import gzip
import json
import math
import re
import struct
import zlib
from pathlib import Path
from typing import Any


class ADSGeometryDecoder:
    def __init__(self, raw: bytes):
        self.raw = raw or b""
        self._relatorio: dict[str, Any] = {}

    def analisar(self) -> dict[str, Any]:
        assinatura = self._detectar_assinatura()
        blocos = self.tentar_descomprimir_blocos()
        strings = self.extrair_strings()
        pontos32 = self.extrair_pontos_float32()
        pontos64 = self.extrair_pontos_float64()
        polilinhas = self.detectar_polilinhas()

        geometria_convertida = bool(polilinhas)
        motivo = "contornos coerentes detectados" if geometria_convertida else "nenhum contorno confiável detectado"

        self._relatorio = {
            "assinatura": assinatura,
            "tamanho_bytes": len(self.raw),
            "blocos_comprimidos_detectados": len(blocos),
            "strings_encontradas": len(strings),
            "possiveis_pontos_float32": len(pontos32),
            "possiveis_pontos_float64": len(pontos64),
            "contornos_candidatos": len(polilinhas),
            "geometria_convertida": geometria_convertida,
            "motivo": motivo,
            "polilinhas": polilinhas,
            "elementos_canvas": [self._polyline_para_elemento(i, p) for i, p in enumerate(polilinhas, start=1)],
        }
        return self._relatorio

    def tentar_descomprimir_blocos(self) -> list[bytes]:
        blocos: list[bytes] = []
        bruto = self.raw
        for i in range(max(0, len(bruto) - 2)):
            if bruto[i] == 0x78 and bruto[i + 1] in (0x01, 0x5E, 0x9C, 0xDA):
                try:
                    dados = zlib.decompress(bruto[i:])
                    if len(dados) >= 32:
                        blocos.append(dados)
                except Exception:
                    continue
            if i < len(bruto) - 3 and bruto[i : i + 3] == b"\x1f\x8b\x08":
                try:
                    dados = gzip.decompress(bruto[i:])
                    if len(dados) >= 32:
                        blocos.append(dados)
                except Exception:
                    continue
            if len(blocos) >= 32:
                break
        return blocos

    def extrair_strings(self) -> list[str]:
        encontrados = re.findall(rb"[ -~]{4,}", self.raw)
        saida: list[str] = []
        for item in encontrados:
            try:
                saida.append(item.decode("utf-8", errors="ignore"))
            except Exception:
                continue
        return saida

    def extrair_pontos_float32(self) -> list[tuple[float, float]]:
        buffers = [self.raw, *self.tentar_descomprimir_blocos()]
        pontos: list[tuple[float, float]] = []
        for buf in buffers:
            pontos.extend(self._extrair_pontos_de_buffer(buf, "f", 4))
        return pontos

    def extrair_pontos_float64(self) -> list[tuple[float, float]]:
        buffers = [self.raw, *self.tentar_descomprimir_blocos()]
        pontos: list[tuple[float, float]] = []
        for buf in buffers:
            pontos.extend(self._extrair_pontos_de_buffer(buf, "d", 8))
        return pontos

    def detectar_polilinhas(self) -> list[dict[str, Any]]:
        buffers = [self.raw, *self.tentar_descomprimir_blocos()]
        candidatos: list[dict[str, Any]] = []
        for buf in buffers:
            for fmt, size in (("f", 4), ("d", 8)):
                pontos = self._extrair_pontos_de_buffer(buf, fmt, size)
                sequencias = self._segmentar_sequencias(pontos)
                for seq in sequencias:
                    if self._sequencia_valida(seq):
                        candidatos.append(
                            {
                                "formato": "float32" if fmt == "f" else "float64",
                                "pontos": seq,
                                "fechado": self._eh_fechado(seq),
                            }
                        )
        return candidatos[:20]

    def gerar_relatorio(self) -> dict[str, Any]:
        return self._relatorio or self.analisar()

    def _detectar_assinatura(self) -> str | None:
        cabecalho = self.raw[:64]
        if b"CADZ" in cabecalho:
            return "CADZ"
        return None

    @staticmethod
    def _polyline_para_elemento(idx: int, poly: dict[str, Any]) -> dict[str, Any]:
        return {
            "tipo": "polyline",
            "pontos": [(float(x), float(y)) for x, y in poly.get("pontos", [])],
            "molde": True,
            "nome_molde": f"Molde ADSX {idx}",
            "origem": "adsx",
            "geometria_convertida": True,
            "cor": "#6fa8dc",
        }

    @staticmethod
    def _extrair_pontos_de_buffer(buf: bytes, fmt: str, size: int) -> list[tuple[float, float]]:
        pontos: list[tuple[float, float]] = []
        step = size * 2
        if len(buf) < step:
            return pontos
        for i in range(0, len(buf) - step + 1, size):
            try:
                x, y = struct.unpack_from(f"<{fmt}{fmt}", buf, i)
            except Exception:
                continue
            if ADSGeometryDecoder._coord_valida(x) and ADSGeometryDecoder._coord_valida(y):
                pontos.append((float(x), float(y)))
        return pontos

    @staticmethod
    def _coord_valida(v: float) -> bool:
        return math.isfinite(v) and abs(v) <= 100000.0

    @staticmethod
    def _segmentar_sequencias(pontos: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
        if not pontos:
            return []
        sequencias: list[list[tuple[float, float]]] = []
        atual: list[tuple[float, float]] = [pontos[0]]
        for p in pontos[1:]:
            dx = p[0] - atual[-1][0]
            dy = p[1] - atual[-1][1]
            dist = math.hypot(dx, dy)
            if 0.0001 <= dist <= 5000:
                atual.append(p)
                continue
            if len(atual) >= 6:
                sequencias.append(atual)
            atual = [p]
        if len(atual) >= 6:
            sequencias.append(atual)
        return sequencias

    @staticmethod
    def _eh_fechado(seq: list[tuple[float, float]]) -> bool:
        if len(seq) < 4:
            return False
        a, b = seq[0], seq[-1]
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= 3.0

    @staticmethod
    def _sequencia_valida(seq: list[tuple[float, float]]) -> bool:
        if len(seq) < 6:
            return False
        xs = [p[0] for p in seq]
        ys = [p[1] for p in seq]
        largura = max(xs) - min(xs)
        altura = max(ys) - min(ys)
        if largura <= 0.001 or altura <= 0.001:
            return False
        if largura > 100000 or altura > 100000:
            return False
        return ADSGeometryDecoder._eh_fechado(seq)


def salvar_relatorio_debug(caminho_json: str | Path, relatorio: dict):
    caminho = Path(caminho_json)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
