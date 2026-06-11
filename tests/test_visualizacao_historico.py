from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    VisualizacaoCanvas = None
    CenaDocumento = None
    QPointF = None
    Qt = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication

    from canvas.cena import CenaDocumento
    from canvas.visualizacao import VisualizacaoCanvas


class _FakeMouseEvent:
    def __init__(self, pos: QPointF, button=None):
        self._pos = QPointF(pos)
        self._button = Qt.LeftButton if button is None else button

    def position(self):
        return QPointF(self._pos)

    def button(self):
        return self._button


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

    def test_limpar_e_desfazer_removem_marcacoes_de_coordenadas(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas._marcacoes_temporarias = [QPointF(1.0, 1.0), QPointF(2.0, 2.0)]
        canvas._ponto_coordenada_aplicada = QPointF(2.0, 2.0)

        canvas.desfazer_acao()

        self.assertEqual(len(canvas._marcacoes_temporarias), 1)
        self.assertEqual(canvas._ponto_coordenada_aplicada, QPointF(1.0, 1.0))

        canvas._limpar_marcacoes_coordenadas()

        self.assertEqual(canvas._marcacoes_temporarias, [])
        self.assertIsNone(canvas._ponto_coordenada_aplicada)

    def test_preview_coordenadas_congela_ao_finalizar_operacao(self):
        canvas = VisualizacaoCanvas(CenaDocumento())

        canvas.iniciar_operacao_coordenadas(QPointF(10.0, 5.0))
        canvas.atualizar_operacao_coordenadas(QPointF(13.0, 1.0))

        self.assertEqual(canvas.painel_coordenadas.dx_preview.text(), "3")
        self.assertEqual(canvas.painel_coordenadas.dy_preview.text(), "-4")
        self.assertEqual(canvas.painel_coordenadas.d_preview.text(), "5")

        canvas.finalizar_operacao_coordenadas(QPointF(13.0, 1.0))
        canvas._atualizar_preview_coordenadas_mouse(QPointF(50.0, 50.0))

        self.assertEqual(canvas.painel_coordenadas.dx_preview.text(), "3")
        self.assertEqual(canvas.painel_coordenadas.dy_preview.text(), "-4")
        self.assertEqual(canvas.painel_coordenadas.d_preview.text(), "5")

    def test_ferramenta_futura_usa_ciclo_automatico_de_coordenadas(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas._runtime_tool = object()

        canvas._coordenadas_auto_apos_press(_FakeMouseEvent(QPointF(4.0, 6.0)), True, False)
        canvas.atualizar_operacao_coordenadas(QPointF(7.0, 2.0))

        self.assertTrue(canvas._operacao_coordenadas_ativa)
        self.assertEqual(canvas.painel_coordenadas.dx_preview.text(), "3")
        self.assertEqual(canvas.painel_coordenadas.dy_preview.text(), "-4")

        canvas._coordenadas_auto_apos_release(_FakeMouseEvent(QPointF(7.0, 2.0)), True)
        canvas._atualizar_preview_coordenadas_mouse(QPointF(50.0, 50.0))

        self.assertFalse(canvas._operacao_coordenadas_ativa)
        self.assertEqual(canvas.painel_coordenadas.dx_preview.text(), "3")
        self.assertEqual(canvas.painel_coordenadas.dy_preview.text(), "-4")

    def test_desfazer_consulta_ferramenta_ativa_antes_de_marcacoes(self):
        class _Ferramenta:
            def __init__(self):
                self.chamadas = 0

            def desfazer_etapa(self, canvas):
                self.chamadas += 1
                return True

        canvas = VisualizacaoCanvas(CenaDocumento())
        ferramenta = _Ferramenta()
        canvas._runtime_tool = ferramenta
        canvas._marcacoes_temporarias = [QPointF(1.0, 1.0)]

        canvas.desfazer_acao()

        self.assertEqual(ferramenta.chamadas, 1)
        self.assertEqual(len(canvas._marcacoes_temporarias), 1)

    def test_finalizar_reta_grava_cada_segmento_no_historico(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas._pontos_reta = [
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 5.0),
            QPointF(3.0, 5.0),
        ]

        canvas._finalizar_reta_atual()

        self.assertEqual(len(canvas.cena.elementos), 3)
        canvas.desfazer_acao()
        self.assertEqual(len(canvas.cena.elementos), 2)
        canvas.desfazer_acao()
        self.assertEqual(len(canvas.cena.elementos), 1)


if __name__ == "__main__":
    unittest.main()
