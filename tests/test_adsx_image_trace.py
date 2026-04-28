from __future__ import annotations

import unittest

from formats.adsx_image_trace import vetorizar_preview_adsx


class ADSXImageTraceTestCase(unittest.TestCase):
    def test_vetorizacao_relatorio_basico(self):
        rel = vetorizar_preview_adsx("invalido")
        self.assertEqual(rel.get("origem"), "adsx_preview_trace")
        self.assertEqual(rel.get("confianca"), "baixa")
        self.assertTrue(rel.get("requer_revisao_manual"))
        self.assertIn("elementos", rel)


if __name__ == "__main__":
    unittest.main()
