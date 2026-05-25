from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from canvas.cena import CenaDocumento
from canvas.snap import rotulo_tipo_snap, tipo_snap_movimento_fluido
from canvas.visualizacao import VisualizacaoCanvas


class SnapRotuloTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_rotulos_principais_do_snap(self):
        self.assertEqual(rotulo_tipo_snap("nó"), "Nó")
        self.assertEqual(rotulo_tipo_snap("borda"), "Borda")
        self.assertEqual(rotulo_tipo_snap("ponto médio"), "Ponto mediano")
        self.assertEqual(rotulo_tipo_snap("controle principal"), "Nó principal")

    def test_snap_de_movimento_trava_so_em_no_borda_e_ponto_mediano(self):
        for tipo in ("nó", "controle principal", "controle auxiliar", "borda", "ponto médio"):
            self.assertTrue(tipo_snap_movimento_fluido(tipo))
        for tipo in ("interseção", "centro", "grade", "coord", "fio", "nome", "angulo 90°"):
            self.assertFalse(tipo_snap_movimento_fluido(tipo))

    def test_snap_movimento_ignora_elemento_vivo_mas_usa_sombra_original(self):
        vivo = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
            "controle_auxiliares": [(5.0, 0.0)],
        }
        sombra = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
            "controle_auxiliares": [(5.0, 0.0)],
        }
        canvas = VisualizacaoCanvas(CenaDocumento(elementos=[vivo]))
        canvas.zoom = 20.0

        ponto = canvas._ponto_com_snap_movimento(
            canvas._cena_para_tela(QPointF(5.0, 0.0)),
            ignorar_elementos={0},
            elementos_sombra={0: sombra},
        )

        self.assertEqual(ponto, QPointF(5.0, 0.0))
        self.assertIsNotNone(canvas._snap_resultado)
        self.assertIsNone(canvas._snap_resultado.elemento_idx)


if __name__ == "__main__":
    unittest.main()
