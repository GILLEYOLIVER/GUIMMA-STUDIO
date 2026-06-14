from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = SimpleNamespace(LeftButton=1, RightButton=2)
    QWidget = object
    QDialog = None
    FerramentaPiqueTexto = None
    VisualizacaoCanvas = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QDialog, QWidget

    from canvas.visualizacao import VisualizacaoCanvas
    from tools.pique_texto_tool import Ferramenta as FerramentaPiqueTexto


class _FakeCanvas(QWidget if QWidget is not object else object):
    def __init__(self):
        super().__init__()
        self.zoom = 20.0
        self.historico = 0
        self._selecionados = set()
        self._linha_cor = "#22ccff"
        self.ferramenta_final = None
        self.lbl_status = SimpleNamespace(texto="", setText=lambda texto: setattr(self.lbl_status, "texto", texto))
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
                    "cor": "#ff8800",
                    "piques_config": [
                        {
                            "ponto": (5.0, 0.0),
                            "ponto_controle": (5.0, 0.0),
                            "sobre_contorno": True,
                            "segmentos": [((5.0, 0.0), (5.0, 1.0))],
                        }
                    ],
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
        self._pos = QPointF(pos)
        self._button = button
        self.accepted = False

    def position(self):
        return QPointF(self._pos)

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


class _FakeDialog:
    def __init__(self, valores):
        self._valores = dict(valores)
        self.carregado = None

    def carregar(self, cfg, cor_padrao):
        self.carregado = (cfg, cor_padrao)

    def exec(self):
        return QDialog.Accepted

    def valores(self):
        return dict(self._valores)


@unittest.skipIf(FerramentaPiqueTexto is None, "PySide6 nao disponivel neste ambiente")
class PiqueTextoToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_clique_no_pique_salva_texto_e_registra_historico(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaPiqueTexto()
        dialog = _FakeDialog(
            {
                "texto": "Centro",
                "altura_cm": 0.6,
                "dx_cm": 0.8,
                "dy_cm": -0.4,
                "cor": "#00ff66",
                "remover": False,
            }
        )
        ferramenta._dialogo = lambda _canvas: dialog
        ferramenta._reposicionar_dialogo = lambda *_args: None

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.0))))

        cfg = canvas.cena.elementos[0]["piques_config"][0]
        self.assertEqual(cfg["texto_pique"], "Centro")
        self.assertEqual(cfg["texto_altura_cm"], 0.6)
        self.assertEqual(cfg["texto_dx_cm"], 0.8)
        self.assertEqual(cfg["texto_dy_cm"], -0.4)
        self.assertEqual(cfg["texto_cor"], "#00ff66")
        self.assertEqual(canvas.historico, 1)
        self.assertEqual(canvas._selecionados, {0})
        self.assertIn("atualizado", canvas.lbl_status.texto)
        self.assertIs(dialog.carregado[0], cfg)

    def test_remover_apaga_campos_de_texto_do_pique(self):
        canvas = _FakeCanvas()
        cfg = canvas.cena.elementos[0]["piques_config"][0]
        cfg.update(
            {
                "texto_pique": "Antigo",
                "texto_altura_cm": 0.5,
                "texto_dx_cm": 1.0,
                "texto_dy_cm": -1.0,
                "texto_cor": "#123456",
            }
        )
        ferramenta = FerramentaPiqueTexto()
        ferramenta._dialogo = lambda _canvas: _FakeDialog({"texto": "", "remover": True})
        ferramenta._reposicionar_dialogo = lambda *_args: None

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, 0.4))))

        self.assertNotIn("texto_pique", cfg)
        self.assertNotIn("texto_altura_cm", cfg)
        self.assertNotIn("texto_cor", cfg)
        self.assertEqual(canvas.historico, 1)

    def test_helpers_visuais_leem_texto_posicao_e_cor(self):
        cfg = {
            "texto_pique": "Borda",
            "texto_dx_cm": 1.25,
            "texto_dy_cm": -0.75,
            "texto_cor": "#abcdef",
        }

        self.assertEqual(VisualizacaoCanvas._texto_cfg_pique(cfg), "Borda")
        pos = VisualizacaoCanvas._posicao_texto_cfg_pique(cfg, QPointF(5.0, 2.0))
        self.assertEqual(pos, QPointF(6.25, 1.25))
        self.assertEqual(VisualizacaoCanvas._cor_cfg_pique_texto(cfg, "#ffffff"), "#abcdef")

    def test_botao_direito_finaliza(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaPiqueTexto()

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0), button=Qt.RightButton)))

        self.assertEqual(canvas.ferramenta_final, "selecionar")


if __name__ == "__main__":
    unittest.main()
