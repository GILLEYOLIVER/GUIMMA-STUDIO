from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    QWidget = None
    InserirPiqueDialog = None
    FerramentaInserirPique = None
    VisualizacaoCanvas = None
    CenaDocumento = None
    TIPOS_PIQUE = []
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from canvas.cena import CenaDocumento
    from canvas.visualizacao import VisualizacaoCanvas
    from tools.inserir_pique_tool import Ferramenta as FerramentaInserirPique
    from tools.inserir_pique_tool import InserirPiqueDialog, TIPOS_PIQUE

_BaseWidget = QWidget if QWidget is not None else object


class _FakeCanvas(_BaseWidget):
    def __init__(self):
        super().__init__()
        self.zoom = 20.0
        self.historico = 0
        self._selecionados = set()
        self.ferramenta_final = None
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "controle_auxiliares": [],
                    "pontos_auxiliares": [],
                }
            ]
        )

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def set_ferramenta_ativa(self, ferramenta):
        self.ferramenta_final = ferramenta

    def update(self):
        pass


class _FakeEvent:
    def __init__(self, pos: QPointF, button=Qt.LeftButton):
        self._pos = pos
        self._button = button
        self.accepted = False

    def position(self):
        return QPointF(self._pos)

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


@unittest.skipIf(FerramentaInserirPique is None, "PySide6 nao disponivel neste ambiente")
class InserirPiqueToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dialogo_opcoes_iniciais(self):
        dialog = InserirPiqueDialog()

        self.assertEqual(dialog.edt_largura.text(), "0.3")
        self.assertEqual(dialog.edt_altura.text(), "0.3")
        self.assertEqual(dialog.edt_angulo.text(), "0")
        self.assertEqual([dialog.cmb_tipo.itemText(i) for i in range(dialog.cmb_tipo.count())], TIPOS_PIQUE)
        self.assertEqual(dialog.cmb_tipo.currentText(), "T - forma T")
        self.assertTrue(dialog.chk_sobre_contorno.isChecked())
        self.assertTrue(dialog.chk_ponto_controle.isChecked())
        self.assertEqual(dialog.cmb_costura.currentText(), "Estendido")

    def test_aplicar_pique_registra_marcacao_config_e_controle(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaInserirPique()
        ferramenta._dialog = InserirPiqueDialog()

        self.assertTrue(ferramenta._aplicar_pique(canvas, 0, QPointF(5.0, 0.0)))

        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["marcacoes_no_perimetro"], [(5.0, 0.0)])
        self.assertEqual(molde["controle_auxiliares"], [(5.0, 0.0)])
        self.assertEqual(molde["pontos_auxiliares"], [{"x": 5.0, "y": 0.0}])
        self.assertEqual(molde["piques_config"][0]["tipo"], "T - forma T")
        self.assertEqual(molde["piques_config"][0]["pique_na_costura"], "Estendido")
        self.assertEqual(len(molde["piques_config"][0]["segmentos"]), 2)

    def test_primeiro_clique_seleciona_segundo_insere_e_direito_finaliza(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaInserirPique()
        ferramenta._dialog = InserirPiqueDialog()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))
        self.assertEqual(canvas._selecionados, {0})
        self.assertNotIn("piques_config", canvas.cena.elementos[0])

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(6.0, 0.0))))
        self.assertEqual(len(canvas.cena.elementos[0]["piques_config"]), 1)
        self.assertEqual(canvas.historico, 1)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(6.0, 0.0), button=Qt.RightButton)))
        self.assertEqual(canvas.ferramenta_final, "selecionar")
        self.assertIsNone(ferramenta._molde_idx)

    def test_forma_v_salva_segmentos_com_altura_e_largura(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaInserirPique()
        ferramenta._dialog = InserirPiqueDialog()
        ferramenta._dialog.cmb_tipo.setCurrentText("V - forma V")
        ferramenta._dialog.edt_largura.setText("4")
        ferramenta._dialog.edt_altura.setText("2")

        self.assertTrue(ferramenta._aplicar_pique(canvas, 0, QPointF(10.0, 2.5)))

        segmentos = canvas.cena.elementos[0]["piques_config"][0]["segmentos"]
        self.assertEqual(len(segmentos), 2)
        pontos = [p for segmento in segmentos for p in segmento]
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        self.assertAlmostEqual(max(xs) - min(xs), 4.0)
        self.assertAlmostEqual(max(ys) - min(ys), 2.0)

    def test_largura_e_altura_alteram_tamanho_do_pique(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaInserirPique()
        ferramenta._dialog = InserirPiqueDialog()
        ferramenta._dialog.cmb_tipo.setCurrentText("T - forma T")
        ferramenta._dialog.edt_largura.setText("3")
        ferramenta._dialog.edt_altura.setText("1")

        self.assertTrue(ferramenta._aplicar_pique(canvas, 0, QPointF(5.0, 0.0)))

        segmentos = canvas.cena.elementos[0]["piques_config"][0]["segmentos"]
        pontos = [p for segmento in segmentos for p in segmento]
        self.assertAlmostEqual(max(x for x, _y in pontos) - min(x for x, _y in pontos), 3.0)
        self.assertAlmostEqual(max(y for _x, y in pontos) - min(y for _x, y in pontos), 1.0)

    def test_pique_interno_fora_do_molde_e_rejeitado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaInserirPique()
        ferramenta._dialog = InserirPiqueDialog()
        ferramenta._dialog.chk_sobre_contorno.setChecked(False)
        ferramenta._dialog.edt_largura.setText("1")
        ferramenta._dialog.edt_altura.setText("3")
        ferramenta._dialog.edt_angulo.setText("180")

        self.assertFalse(ferramenta._aplicar_pique(canvas, 0, QPointF(5.0, 0.0)))

        molde = canvas.cena.elementos[0]
        self.assertNotIn("piques_config", molde)
        self.assertEqual(molde.get("marcacoes_no_perimetro", []), [])

    def test_cor_pique_configurada_ou_cor_do_molde(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {"tipo": "polyline", "molde": True, "cor": "#00ff00"}

        self.assertEqual(canvas._cor_piques_elemento(molde, "#00ff00"), "#00ff00")

        canvas.set_config_cores_moldes({"piques": {"ativo": True, "cor": "#ff0000"}})
        self.assertEqual(canvas._cor_piques_elemento(molde, "#00ff00"), "#ff0000")


if __name__ == "__main__":
    unittest.main()
