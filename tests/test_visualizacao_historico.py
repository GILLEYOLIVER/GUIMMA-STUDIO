from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    VisualizacaoCanvas = None
    CenaDocumento = None
else:
    from PySide6.QtWidgets import QApplication

    from canvas.cena import CenaDocumento
    from canvas.visualizacao import VisualizacaoCanvas


@unittest.skipIf(VisualizacaoCanvas is None, "PySide6 não disponível neste ambiente")
class VisualizacaoHistoricoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_desfazer_para_no_primeiro_estado_real_sem_apagar_molde(self):
        inicial = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
        }
        canvas = VisualizacaoCanvas(CenaDocumento(elementos=[inicial]))

        canvas.cena.elementos[0]["nome_molde"] = "K1"
        canvas._registrar_historico()

        canvas.desfazer_acao()
        self.assertEqual(len(canvas.cena.elementos), 1)
        self.assertNotIn("nome_molde", canvas.cena.elementos[0])

        canvas.desfazer_acao()
        self.assertEqual(len(canvas.cena.elementos), 1)
        self.assertEqual(canvas._indice_historico, 0)

    def test_historico_mantem_250_passos_de_desfazer(self):
        canvas = VisualizacaoCanvas(CenaDocumento())

        for i in range(260):
            canvas.cena.elementos = [{"tipo": "polyline", "pontos": [(float(i), 0.0), (float(i), 1.0)]}]
            canvas._registrar_historico()

        self.assertEqual(len(canvas._historico_elementos), 251)
        self.assertEqual(canvas._indice_historico, 250)
        primeiro = canvas._historico_elementos[0][0]["pontos"][0][0]
        ultimo = canvas._historico_elementos[-1][0]["pontos"][0][0]
        self.assertEqual(primeiro, 9.0)
        self.assertEqual(ultimo, 259.0)

        for _ in range(250):
            canvas.desfazer_acao()

        self.assertEqual(canvas._indice_historico, 0)
        self.assertEqual(canvas.cena.elementos[0]["pontos"][0][0], 9.0)

    def test_desfazer_registra_estado_atual_se_faltou_registro(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.cena.elementos = [{"tipo": "polyline", "pontos": [(1.0, 0.0), (1.0, 1.0)]}]

        canvas.desfazer_acao()

        self.assertEqual(canvas.cena.elementos, [])
        self.assertEqual(len(canvas._historico_elementos), 2)
        canvas.refazer_acao()
        self.assertEqual(canvas.cena.elementos[0]["pontos"][0], (1.0, 0.0))


if __name__ == "__main__":
    unittest.main()
