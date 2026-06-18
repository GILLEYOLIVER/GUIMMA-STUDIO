from __future__ import annotations

import unittest
import base64

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage

from formats.adsx_image_trace import vetorizar_preview_adsx


class ADSXImageTraceTestCase(unittest.TestCase):
    def test_vetorizacao_relatorio_basico(self):
        rel = vetorizar_preview_adsx("invalido")
        self.assertEqual(rel.get("origem"), "adsx_preview_trace")
        self.assertEqual(rel.get("confianca"), "baixa")
        self.assertTrue(rel.get("requer_revisao_manual"))
        self.assertIn("elementos", rel)

    def test_vetoriza_area_colorida_sem_opencv(self):
        img = QImage(120, 80, QImage.Format_RGB32)
        img.fill(QColor("#f0f0f0"))
        for y in range(15, 65):
            for x in range(20, 95):
                img.setPixelColor(x, y, QColor("#00d000"))
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        img.save(buffer, "PNG")
        b64 = base64.b64encode(bytes(buffer.data())).decode("ascii")

        rel = vetorizar_preview_adsx(b64, escala_x=0.5, escala_y=0.25)
        self.assertTrue(rel.get("sucesso"))
        self.assertGreaterEqual(len(rel.get("elementos", [])), 1)
        self.assertEqual(rel["elementos"][0].get("tipo"), "polyline")
        self.assertTrue(rel["elementos"][0].get("molde"))
        self.assertEqual(rel.get("escala_x_cm_por_px"), 0.5)
        self.assertEqual(rel.get("escala_y_cm_por_px"), 0.25)
        pontos = rel["elementos"][0].get("pontos", [])
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        self.assertLessEqual(max(xs) - min(xs), 40.0)
        self.assertLessEqual(max(ys) - min(ys), 15.0)


if __name__ == "__main__":
    unittest.main()
