from __future__ import annotations

import json
import os
import unittest
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = object
    FerramentaAutoGraduacao = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.auto_graduacao_tool import Ferramenta as FerramentaAutoGraduacao


class _FakeMouseEvent:
    def __init__(self, pos: QPointF, *, button=None):
        self._pos = QPointF(pos)
        self._button = button if button is not None else Qt.LeftButton
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return QPointF(self._pos)

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "graduacao_tamanhos": [
                        {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                        {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                        {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
                    ],
                }
            ]
        )
        self._selecionados = set()
        self.historico = 0
        self.atualizou = False
        self.ferramenta_ativa = None
        self.lbl_status = None

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _indice_molde_em_ponto(self, pos):
        return 0 if 0.0 <= pos.x() <= 10.0 and 0.0 <= pos.y() <= 5.0 else None

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True

    def set_ferramenta_ativa(self, ferramenta):
        self.ferramenta_ativa = ferramenta


@unittest.skipIf(FerramentaAutoGraduacao is None, "PySide6 nao disponivel neste ambiente")
class AutoGraduacaoToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        FerramentaAutoGraduacao._dialog_por_canvas.clear()

    def test_aplica_dx_dy_incremental_em_todos_os_pontos_do_molde(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaAutoGraduacao()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.aplicar_auto(canvas))

        molde = canvas.cena.elementos[0]
        pontos = molde["graduacao_tabela"]["pontos"]
        self.assertEqual(set(pontos.keys()), {"0", "1", "2"})
        for cfg in pontos.values():
            self.assertEqual(cfg["valores"]["P"], {"dx": -5.0, "dy": -1.0})
            self.assertEqual(cfg["valores"]["M"], {"dx": 0.0, "dy": 0.0})
            self.assertEqual(cfg["valores"]["G"], {"dx": 5.0, "dy": 1.0})
        self.assertEqual(molde["graduacao_tamanhos_ativos"], ["P", "M", "G"])
        self.assertTrue(molde["mostrar_graduacao"])
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.atualizou)

    def test_aplicar_no_tamanho_preserva_outros_tamanhos_existentes(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        molde = canvas.cena.elementos[0]
        molde["graduacao_tabela"] = {
            "pontos": {
                "0": {
                    "valores": {
                        "P": {"dx": -2.0, "dy": -3.0},
                        "G": {"dx": 9.0, "dy": 9.0},
                    }
                }
            }
        }
        ferramenta = FerramentaAutoGraduacao()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        dialog.cmb_tamanho.setCurrentText("G")

        valores = molde["graduacao_tabela"]["pontos"]["0"]["valores"]
        self.assertEqual(valores["P"], {"dx": -2.0, "dy": -3.0})
        self.assertEqual(valores["G"], {"dx": 5.0, "dy": 1.0})
        self.assertNotIn("M", valores)

    def test_clique_no_molde_sem_selecao_aplica_auto_graduacao(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaAutoGraduacao()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(5.0, 2.0))))

        self.assertEqual(canvas._selecionados, {0})
        self.assertIn("graduacao_tabela", canvas.cena.elementos[0])
        self.assertEqual(canvas.historico, 1)

    def test_botao_esta_na_aba_graduacao(self):
        mapa = json.loads(Path("ui/tool_pages_map.json").read_text(encoding="utf-8"))
        aba = next(tab for tab in mapa["tabs"] if tab["id"] == "graduacao")
        grupo = next(group for group in aba["groups"] if group["title"] == "Graduar")

        self.assertIn("auto_graduacao", grupo["tools"])
        self.assertEqual(mapa["tools"]["auto_graduacao"]["module"], "tools/auto_graduacao_tool.py")
        self.assertEqual(mapa["tools"]["auto_graduacao"]["icon"], "auto_graduacao.svg")


if __name__ == "__main__":
    unittest.main()
