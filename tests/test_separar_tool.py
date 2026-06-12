from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = None
    Signal = None
    QWidget = None
    FerramentaSeparar = None
else:
    from PySide6.QtCore import QPointF, Qt, Signal
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.separar_tool import Ferramenta as FerramentaSeparar


class _FakeEvent:
    def __init__(self, pos: QPointF, button=Qt.LeftButton):
        self._pos = QPointF(pos)
        self._button = button
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return QPointF(self._pos)

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    elementos_alterados = Signal()

    def __init__(self):
        super().__init__()
        valores_g = {
            str(idx): {"valores": {"M": {"dx": 0.0, "dy": 0.0}, "G": {"dx": 1.0, "dy": 0.0}}}
            for idx in range(4)
        }
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "nome_molde": "K1",
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                    "graduacao_tamanhos": [
                        {"ativo": True, "tamanho": "M", "cor": "#ffff00", "base": True},
                        {"ativo": True, "tamanho": "G", "cor": "#5d95b7", "base": False},
                    ],
                    "graduacao_tabela": {"pontos": valores_g},
                    "graduacao_pontos": valores_g,
                }
            ]
        )
        self._selecionados = set()
        self._snap_ativo = True
        self.zoom = 10.0
        self.historico = 0
        self.atualizou = False
        self.lbl_status = None

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1
        self.elementos_alterados.emit()

    def update(self):
        self.atualizou = True

    def set_ferramenta_ativa(self, _nome):
        pass


@unittest.skipIf(FerramentaSeparar is None, "PySide6 não disponível neste ambiente")
class SepararToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_hover_e_clique_criam_copia_nomeada_do_tamanho(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaSeparar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(11.0, 2.5))))
        self.assertEqual(ferramenta._hover["nome_tamanho"], "G")
        self.assertEqual(ferramenta._hover_pos, QPointF(11.0, 2.5))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(11.0, 2.5))))

        self.assertEqual(len(canvas.cena.elementos), 2)
        copia = canvas.cena.elementos[1]
        self.assertEqual(copia["nome_molde"], "K1 - G")
        self.assertEqual(copia["tamanho_extraido"], "G")
        self.assertFalse(any(str(chave).startswith("graduacao_") for chave in copia))
        self.assertEqual(copia["cor"], "#5d95b7")
        self.assertEqual(canvas._selecionados, {1})

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(21.0, 2.5))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(21.0, 2.5))))
        self.assertEqual(canvas.historico, 1)
        self.assertIsNone(ferramenta._arrastando_idx)

    def test_botao_direito_cancela_copia_em_arraste(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaSeparar()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(11.0, 2.5))))
        self.assertEqual(len(canvas.cena.elementos), 2)
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(11.0, 2.5), button=Qt.RightButton)))

        self.assertEqual(len(canvas.cena.elementos), 1)
        self.assertEqual(canvas._selecionados, set())


if __name__ == "__main__":
    unittest.main()
