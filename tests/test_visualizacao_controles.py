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

    def test_numeracao_de_controles_segue_sentido_horario_na_tela(self):
        cantos = [
            QPointF(0.0, 4.0),
            QPointF(10.0, 4.0),
            QPointF(10.0, 0.0),
            QPointF(0.0, 0.0),
        ]

        ordenados = VisualizacaoCanvas._cantos_para_numeracao_horaria_tela(cantos)

        self.assertEqual(
            [(p.x(), p.y()) for p in ordenados],
            [(0.0, 4.0), (0.0, 0.0), (10.0, 0.0), (10.0, 4.0)],
        )

    def test_numeracao_de_controles_mantem_horario_visual_existente(self):
        cantos = [
            QPointF(0.0, 4.0),
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 4.0),
        ]

        ordenados = VisualizacaoCanvas._cantos_para_numeracao_horaria_tela(cantos)

        self.assertEqual(
            [(p.x(), p.y()) for p in ordenados],
            [(0.0, 4.0), (0.0, 0.0), (10.0, 0.0), (10.0, 4.0)],
        )

    def test_numeracao_de_dois_controles_usa_leitura_visual(self):
        cantos = [
            QPointF(10.0, 4.0),
            QPointF(0.0, 4.0),
        ]

        ordenados = VisualizacaoCanvas._cantos_para_numeracao_horaria_tela(cantos)

        self.assertEqual([(p.x(), p.y()) for p in ordenados], [(0.0, 4.0), (10.0, 4.0)])

    def test_numeracao_de_dois_controles_verticais_usa_cima_para_baixo(self):
        cantos = [
            QPointF(3.0, 8.0),
            QPointF(3.0, 2.0),
        ]

        ordenados = VisualizacaoCanvas._cantos_para_numeracao_horaria_tela(cantos)

        self.assertEqual([(p.x(), p.y()) for p in ordenados], [(3.0, 2.0), (3.0, 8.0)])

    def test_cor_de_preenchimento_do_molde_usa_cor_visual_escolhida(self):
        cor = VisualizacaoCanvas._cor_preenchimento_molde({"cor": "#ffff00"})

        self.assertEqual(cor.name(), QColor("#ffff00").name())

    def test_cor_de_preenchimento_do_molde_tem_fallback_visivel(self):
        cor = VisualizacaoCanvas._cor_preenchimento_molde({"cor": "cor-invalida"})

        self.assertEqual(cor.name(), QColor("#ffffff").name())

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

    def test_elemento_fora_do_viewport_nao_precisa_ser_desenhado(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(800, 600)
        canvas.zoom = 10.0
        canvas.origem_cena = QPointF(0.0, 0.0)

        self.assertTrue(canvas._elemento_visivel_no_viewport({"tipo": "polyline", "pontos": [(1.0, 1.0), (2.0, 2.0)]}))
        self.assertFalse(canvas._elemento_visivel_no_viewport({"tipo": "polyline", "pontos": [(500.0, 500.0), (510.0, 510.0)]}))

    def test_cache_bbox_invalida_quando_pontos_sao_substituidos(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(800, 600)
        canvas.zoom = 10.0
        canvas.origem_cena = QPointF(0.0, 0.0)
        elemento = {"tipo": "polyline", "pontos": [(1.0, 1.0), (2.0, 2.0)]}

        self.assertTrue(canvas._elemento_visivel_no_viewport(elemento))
        elemento["pontos"] = [(500.0, 500.0), (510.0, 510.0)]

        self.assertFalse(canvas._elemento_visivel_no_viewport(elemento))

    def test_finalizar_zoom_interativo_restaura_renderizacao_completa(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas._zoom_interativo = True

        canvas._finalizar_zoom_interativo()

        self.assertFalse(canvas._zoom_interativo)


if __name__ == "__main__":
    unittest.main()
