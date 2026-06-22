from __future__ import annotations

import struct
import unittest
import zlib

from formats.ads_decoder import ADSGeometryDecoder


class ADSDecoderTestCase(unittest.TestCase):
    @staticmethod
    def _nibble_swap_ascii(texto: bytes) -> bytes:
        return bytes(((b & 0x0F) << 4) | (b >> 4) for b in texto)

    def test_analisar_sem_geometria_confiavel(self):
        bruto = b"CADZ vs9.1\x00\x01\x02"
        rel = ADSGeometryDecoder(bruto).analisar()
        self.assertEqual(rel.get("assinatura"), "CADZ")
        self.assertFalse(rel.get("geometria_convertida"))
        self.assertFalse(rel.get("regras_graduacao_decodificadas"))
        self.assertFalse(rel.get("pontos_controle_decodificados"))
        self.assertEqual(rel.get("tabela_graduacao"), {})
        self.assertIn("dx/dy", rel.get("motivo_regras_graduacao", ""))

    def test_analisar_com_bloco_zlib_float32(self):
        pontos = [
            (0.0, 0.0),
            (4.0, 0.0),
            (8.0, 0.0),
            (10.0, 2.0),
            (10.0, 6.0),
            (8.0, 8.0),
            (4.0, 8.0),
            (0.0, 8.0),
            (-1.0, 6.0),
            (-1.0, 3.0),
            (0.0, 1.0),
            (0.0, 0.0),
        ]
        payload = b"".join(struct.pack("<ff", x, y) for x, y in pontos)
        bruto = b"CADZ vs9.1" + zlib.compress(payload)

        rel = ADSGeometryDecoder(bruto).analisar()
        self.assertEqual(rel.get("assinatura"), "CADZ")
        self.assertGreaterEqual(rel.get("blocos_comprimidos_detectados", 0), 1)
        self.assertIn(rel.get("geometry_confidence"), {"low", "medium"})
        self.assertFalse(rel.get("geometria_convertida"))
        self.assertFalse(rel.get("regras_graduacao_decodificadas"))
        self.assertIn("parser estrutural", rel.get("motivo", ""))

    def test_diagnostico_cadz_detecta_camada_protegida_nibble_swap(self):
        cabecalho = b"CADZ vs9.1 \x1a\x17\xc6\x95\xff\x80\x00\x00\x00"
        prefixo = self._nibble_swap_ascii((b"1234567890" * 13) + b"XYZ")
        payload_alta_entropia = bytes(range(256)) * 24
        bruto = cabecalho + prefixo + payload_alta_entropia

        rel = ADSGeometryDecoder(bruto).analisar()
        diagnostico = rel.get("diagnostico_cadz", {})
        self.assertTrue(diagnostico.get("nibble_swap_detectado"))
        self.assertGreaterEqual(diagnostico.get("cabecalho_digitos_len", 0), 64)
        self.assertTrue(diagnostico.get("payload_provavelmente_protegido"))
        self.assertFalse(diagnostico.get("texto_ou_compressao_valida_detectada"))
        self.assertFalse(rel.get("regras_graduacao_decodificadas"))


if __name__ == "__main__":
    unittest.main()
