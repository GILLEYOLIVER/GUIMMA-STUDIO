from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from formats.dxf_import import importar_dxf_para_elementos


def _dxf_entities(entidades: list[str]) -> str:
    return "\n".join(["0", "SECTION", "2", "ENTITIES", *entidades, "0", "ENDSEC", "0", "EOF"])


def _line(x1, y1, x2, y2) -> list[str]:
    return ["0", "LINE", "10", str(x1), "20", str(y1), "11", str(x2), "21", str(y2)]


class DxfImportTestCase(unittest.TestCase):
    def _importar_texto(self, texto: str):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "molde.dxf"
            caminho.write_text(texto, encoding="utf-8")
            return importar_dxf_para_elementos(str(caminho))

    def test_linhas_conectadas_viram_polyline_continua_sem_micro_vertices_colineares(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 5, 0),
                *_line(5, 0, 10, 0),
                *_line(10, 0, 10, 4),
                *_line(10, 4, 0, 4),
                *_line(0, 4, 0, 0),
            ]
        )

        elementos = self._importar_texto(texto)

        self.assertEqual(len(elementos), 1)
        self.assertEqual(
            elementos[0]["pontos"],
            [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0), (0.0, 0.0)],
        )
        self.assertTrue(elementos[0]["fechado"])

    def test_lwpolyline_fechada_nao_e_quebrada_em_segmentos(self):
        texto = _dxf_entities(
            [
                "0",
                "LWPOLYLINE",
                "70",
                "1",
                "10",
                "0",
                "20",
                "0",
                "10",
                "4",
                "20",
                "0",
                "10",
                "4",
                "20",
                "3",
                "10",
                "0",
                "20",
                "3",
            ]
        )

        elementos = self._importar_texto(texto)

        self.assertEqual(len(elementos), 1)
        self.assertEqual(len(elementos[0]["pontos"]), 5)
        self.assertEqual(elementos[0]["pontos"][0], elementos[0]["pontos"][-1])


if __name__ == "__main__":
    unittest.main()
