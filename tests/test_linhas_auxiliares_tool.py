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
    FerramentaLinhasAuxiliares = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.linhas_auxiliares_tool import Ferramenta as FerramentaLinhasAuxiliares


class _FakeEvent:
    def __init__(self, button, pos):
        self._button = button
        self._pos = pos
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


class _FakeLabel:
    def __init__(self):
        self.texto = ""

    def setText(self, texto):
        self.texto = str(texto)


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "molde_id": "molde-1",
                    "cor": "#00ffff",
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
                },
                {
                    "tipo": "polyline",
                    "molde": False,
                    "pontos": [(2.0, 2.0), (4.0, 5.0), (6.0, 2.0)],
                    "subtipo_audaces": "linha_interna",
                    "molde_id": "molde-1",
                    "cor": "#ff00ff",
                },
            ]
        )
        self.zoom = 10.0
        self._selecionados = set()
        self.lbl_status = _FakeLabel()
        self.historico = 0
        self.atualizou = False

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def _indice_molde_em_ponto(self, pos):
        return 0 if 0.0 <= pos.x() <= 10.0 and 0.0 <= pos.y() <= 8.0 else None

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


class ToolPagesMapLinhasAuxiliaresTestCase(unittest.TestCase):
    def test_ferramenta_aparece_na_aba_marcacoes(self):
        mapa = json.loads(Path("ui/tool_pages_map.json").read_text(encoding="utf-8"))

        marcacoes = next(aba for aba in mapa["tabs"] if aba["id"] == "marcacoes")
        grupos = {grupo["title"]: grupo["tools"] for grupo in marcacoes["groups"]}

        self.assertIn("linhas_auxiliares", grupos["Linhas auxiliares"])
        self.assertEqual(mapa["tools"]["linhas_auxiliares"]["module"], "tools/linhas_auxiliares_tool.py")


@unittest.skipIf(FerramentaLinhasAuxiliares is None, "PySide6 nao disponivel neste ambiente")
class LinhasAuxiliaresToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_adiciona_linha_solta_como_linha_auxiliar_do_molde(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaLinhasAuxiliares()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).cmb_acao.setCurrentText("Adicionar")

        ferramenta.on_mouse_press(canvas, _FakeEvent(Qt.LeftButton, QPointF(5.0, 4.0)))
        ferramenta.on_mouse_press(canvas, _FakeEvent(Qt.LeftButton, QPointF(4.0, 4.0)))
        ferramenta.on_mouse_press(canvas, _FakeEvent(Qt.LeftButton, QPointF(4.0, 4.0)))

        self.assertEqual(len(canvas.cena.elementos), 1)
        molde = canvas.cena.elementos[0]
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 1)
        self.assertEqual(len(molde["linhas_auxiliares_base"]), 1)
        self.assertEqual(
            molde["linhas_auxiliares_base"][0]["pontos"],
            [(2.0, 2.0), (4.0, 5.0), (6.0, 2.0)],
        )
        self.assertEqual(molde["linhas_auxiliares_base"][0]["cor"], "#00ffff")
        self.assertTrue(molde["mostrar_linhas_auxiliares"])

    def test_remove_linha_auxiliar_do_molde(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde["linhas_auxiliares_base"] = [
            {
                "tipo": "linha_auxiliar",
                "pontos": [(2.0, 2.0), (4.0, 5.0), (6.0, 2.0)],
                "cor": "#00ffff",
            }
        ]
        canvas.cena.elementos = [molde]
        ferramenta = FerramentaLinhasAuxiliares()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).cmb_acao.setCurrentText("Remover")

        ferramenta.on_mouse_press(canvas, _FakeEvent(Qt.LeftButton, QPointF(5.0, 4.0)))
        ferramenta.on_mouse_press(canvas, _FakeEvent(Qt.LeftButton, QPointF(4.0, 4.0)))
        ferramenta.on_mouse_press(canvas, _FakeEvent(Qt.LeftButton, QPointF(4.0, 4.0)))

        self.assertEqual(molde["linhas_auxiliares_base"], [])
        self.assertEqual(canvas.historico, 1)


if __name__ == "__main__":
    unittest.main()
