import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaEditarPontosCurva = None
    QPointF = None
else:
    from PySide6.QtCore import QPointF

    from tools.editar_pontos_de_curva_tool import Ferramenta as FerramentaEditarPontosCurva


class _FakeEvent:
    def __init__(self, pos):
        self._pos = pos

    def position(self):
        return self._pos


class _FakeCanvas:
    def __init__(self):
        self.snap_usado = 0
        self.raw_usado = 0
        self.ignorar_snap_movimento = []
        self.sombras_snap_movimento = []

    def _ponto_com_snap(self, _pos):
        self.snap_usado += 1
        return QPointF(20.0, 30.0)

    def _ponto_com_snap_movimento(self, pos, ignorar_elementos=None, elementos_sombra=None):
        self.ignorar_snap_movimento.append(set(ignorar_elementos or []))
        self.sombras_snap_movimento.append(elementos_sombra)
        return self._ponto_com_snap(pos)

    def _tela_para_cena(self, _pos):
        self.raw_usado += 1
        return QPointF(1.0, 2.0)


@unittest.skipIf(FerramentaEditarPontosCurva is None, "PySide6 nao disponivel neste ambiente")
class EditarPontosCurvaToolTestCase(unittest.TestCase):
    def test_usa_posicao_real_para_escolher_linha_ou_alca(self):
        ferramenta = FerramentaEditarPontosCurva()
        canvas = _FakeCanvas()

        ponto = ferramenta._ponto_mouse_cena(canvas, _FakeEvent(QPointF(5.0, 6.0)))

        self.assertEqual(ponto, QPointF(1.0, 2.0))
        self.assertEqual(canvas.raw_usado, 1)
        self.assertEqual(canvas.snap_usado, 0)

    def test_usa_snap_durante_arraste_de_ponto(self):
        ferramenta = FerramentaEditarPontosCurva()
        ferramenta._arrastando = (0, 0)
        canvas = _FakeCanvas()

        ponto = ferramenta._ponto_mouse_cena(canvas, _FakeEvent(QPointF(5.0, 6.0)))

        self.assertEqual(ponto, QPointF(20.0, 30.0))
        self.assertEqual(canvas.snap_usado, 1)
        self.assertEqual(canvas.raw_usado, 0)
        self.assertEqual(canvas.ignorar_snap_movimento[-1], {0})
        self.assertEqual(canvas.sombras_snap_movimento[-1], {})


if __name__ == "__main__":
    unittest.main()
