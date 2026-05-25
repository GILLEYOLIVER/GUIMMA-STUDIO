from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaMover = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.mover_tool import Ferramenta as FerramentaMover


class _FakeEvent:
    def __init__(self, pos, button=None):
        self._pos = pos
        self._button = button or Qt.LeftButton
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._selecionados = {0}
        self.historico = 0
        self.atualizou = False
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (10.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0)],
                    "controle_auxiliares": [],
                }
            ]
        )
        self.ignorar_snap_movimento = []
        self.sombras_snap_movimento = []

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _ponto_com_snap_movimento(self, pos, ignorar_elementos=None, elementos_sombra=None):
        self.ignorar_snap_movimento.append(set(ignorar_elementos or []))
        self.sombras_snap_movimento.append(elementos_sombra)
        return self._ponto_com_snap(pos)

    def _indices_elementos_em_ponto(self, _pos):
        return [0]

    def iniciar_operacao_coordenadas(self, _pos):
        pass

    def atualizar_operacao_coordenadas(self, _pos):
        pass

    def finalizar_operacao_coordenadas(self, _pos):
        pass

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaMover is None, "PySide6 nao disponivel neste ambiente")
class MoverToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_mover_mantem_snapshot_original_ate_soltar(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaMover()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(0.0, 0.0))))
        self.assertEqual(ferramenta._originais_arraste[0]["pontos"], [(0.0, 0.0), (10.0, 0.0)])

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(2.0, 1.0))))
        self.assertEqual(canvas.cena.elementos[0]["pontos"], [(2.0, 1.0), (12.0, 1.0)])
        self.assertEqual(ferramenta._originais_arraste[0]["pontos"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(canvas.ignorar_snap_movimento[-1], {0})
        self.assertEqual(canvas.sombras_snap_movimento[-1][0]["pontos"], [(0.0, 0.0), (10.0, 0.0)])

        self.assertTrue(ferramenta.on_mouse_release(canvas, _FakeEvent(QPointF(2.0, 1.0))))
        self.assertEqual(ferramenta._originais_arraste, {})
        self.assertEqual(canvas.historico, 1)


if __name__ == "__main__":
    unittest.main()
