from __future__ import annotations

import struct
import unittest
import zlib

from formats.ads_decoder import ADSGeometryDecoder


class ADSDecoderTestCase(unittest.TestCase):
    def test_analisar_sem_geometria_confiavel(self):
        bruto = b"CADZ vs9.1\x00\x01\x02"
        rel = ADSGeometryDecoder(bruto).analisar()
        self.assertEqual(rel.get("assinatura"), "CADZ")
        self.assertFalse(rel.get("geometria_convertida"))

    def test_analisar_com_bloco_zlib_float32(self):
        pontos = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0), (0.0, 0.0)]
        payload = b"".join(struct.pack("<ff", x, y) for x, y in pontos)
        bruto = b"CADZ vs9.1" + zlib.compress(payload)

        rel = ADSGeometryDecoder(bruto).analisar()
        self.assertEqual(rel.get("assinatura"), "CADZ")
        self.assertGreaterEqual(rel.get("blocos_comprimidos_detectados", 0), 1)
        self.assertTrue(rel.get("geometria_convertida"))
        self.assertTrue(rel.get("elementos_canvas"))


if __name__ == "__main__":
    unittest.main()
