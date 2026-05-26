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
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor
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


if __name__ == "__main__":
    unittest.main()
