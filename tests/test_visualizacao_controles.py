from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    VisualizacaoCanvas = None
    CenaDocumento = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from canvas.cena import CenaDocumento
    from canvas.visualizacao import VisualizacaoCanvas


@unittest.skipIf(VisualizacaoCanvas is None, "PySide6 nao disponivel neste ambiente")
class VisualizacaoControlesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_selecao_molde_usa_controles_oficiais_mesmo_com_um_controle(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        base = [
            QPointF(0.0, 0.0),
            QPointF(1.0, 0.0),
            QPointF(2.0, 0.0),
            QPointF(3.0, 0.0),
        ]
        molde = {"controle_cantos": [(10.0, 5.0)]}

        controles = canvas._pontos_controle_selecao_molde(base, molde)

        self.assertEqual(len(controles), 1)
        self.assertEqual((controles[0].x(), controles[0].y()), (10.0, 5.0))

    def test_selecao_molde_antigo_sem_controles_mantem_fallback_visual(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        base = [
            QPointF(0.0, 0.0),
            QPointF(1.0, 0.0),
            QPointF(2.0, 0.0),
            QPointF(3.0, 0.0),
            QPointF(4.0, 0.0),
        ]

        controles = canvas._pontos_controle_selecao_molde(base, {})

        self.assertEqual([(p.x(), p.y()) for p in controles], [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])

    def test_polilinha_fechada_nao_herda_brush_preenchido(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        image = QImage(140, 100, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        try:
            painter.setBrush(QColor("#ff00ff"))
            canvas._desenhar_polilinha(
                painter,
                [
                    QPointF(2.0, 2.0),
                    QPointF(10.0, 2.0),
                    QPointF(10.0, 7.0),
                    QPointF(2.0, 7.0),
                    QPointF(2.0, 2.0),
                ],
                cor="#ffffff",
                espessura=1.0,
                estilo="solid",
            )
        finally:
            painter.end()

        self.assertEqual(image.pixelColor(60, 45).alpha(), 0)


if __name__ == "__main__":
    unittest.main()
