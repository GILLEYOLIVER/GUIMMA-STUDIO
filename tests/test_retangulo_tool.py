from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaRetangulo = None
    QApplication = None
    QPointF = None
    Qt = None
    QWidget = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.retangulo_tool import Ferramenta as FerramentaRetangulo

_BaseWidget = QWidget if QWidget is not None else object


class _FakeEvent:
    def __init__(self, button=None, pos=None):
        self._button = button if button is not None else Qt.LeftButton
        self._pos = pos or QPointF(0.0, 0.0)
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


class _FakeCanvas(_BaseWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(elementos=[])
        self._selecionados = set()
        self._retangulo_criar_molde = True
        self._linha_cor = "#ff48a8"
        self._linha_espessura = 1.0
        self._linha_estilo = "solid"
        self._linha_amplitude = 1.0
        self.historico = 0
        self.atualizou = False
        self.brushes_preview = []

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True

    def _desenhar_polilinha(self, painter, pontos, **_kwargs):
        self.brushes_preview.append(getattr(painter, "brush_atual", None))
        self.pontos_preview = list(pontos)


class _FakePainter:
    def __init__(self):
        self.brush_atual = "preenchido"
        self.salvou = 0
        self.restaurou = 0

    def save(self):
        self.salvou += 1

    def restore(self):
        self.restaurou += 1

    def setBrush(self, brush):  # noqa: N802
        self.brush_atual = brush


@unittest.skipIf(FerramentaRetangulo is None, "PySide6 não disponível neste ambiente")
class RetanguloToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_retangulo_molde_cria_auxiliar_no_meio_de_cada_reta(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRetangulo()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 4.0))))

        self.assertEqual(len(canvas.cena.elementos), 1)
        molde = canvas.cena.elementos[0]
        self.assertEqual(
            molde["controle_cantos"],
            [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)],
        )
        auxiliares = molde["controle_auxiliares"]
        self.assertEqual(len(auxiliares), 4)
        self.assertIn((5.0, 4.0), auxiliares)
        self.assertIn((10.0, 2.0), auxiliares)
        self.assertIn((5.0, 0.0), auxiliares)
        self.assertIn((0.0, 2.0), auxiliares)
        self.assertEqual(molde["pontos_auxiliares"], [{"x": x, "y": y} for x, y in auxiliares])
        self.assertEqual(canvas._selecionados, set())

    def test_retangulo_desenho_quando_criar_molde_desmarcado(self):
        canvas = _FakeCanvas()
        canvas._retangulo_criar_molde = False
        ferramenta = FerramentaRetangulo()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 4.0))))

        self.assertEqual(len(canvas.cena.elementos), 4)
        self.assertTrue(all(not el.get("molde") for el in canvas.cena.elementos))
        self.assertEqual(canvas.cena.elementos[0]["pontos"], [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(canvas.cena.elementos[1]["pontos"], [(10.0, 0.0), (10.0, 4.0)])
        self.assertEqual(canvas.cena.elementos[2]["pontos"], [(10.0, 4.0), (0.0, 4.0)])
        self.assertEqual(canvas.cena.elementos[3]["pontos"], [(0.0, 4.0), (0.0, 0.0)])
        self.assertEqual(canvas.historico, 1)

    def test_preview_retangulo_nao_usa_preenchimento_herdado_do_painter(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRetangulo()
        ferramenta._inicio = QPointF(0.0, 0.0)
        ferramenta._preview = QPointF(10.0, 4.0)
        ferramenta._desenhar_cota_preview = lambda *_args, **_kwargs: None
        painter = _FakePainter()

        ferramenta._desenhar_preview(canvas, painter)

        self.assertEqual(canvas.brushes_preview, [Qt.NoBrush])
        self.assertEqual(painter.salvou, 1)
        self.assertEqual(painter.restaurou, 1)

    def test_retangulo_molde_numera_cantos_em_ordem_horaria_visual(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRetangulo()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(10.0, 4.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(pos=QPointF(0.0, 0.0))))

        molde = canvas.cena.elementos[0]
        self.assertEqual(
            molde["controle_cantos"],
            [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)],
        )
        self.assertEqual(
            molde["pontos_controle_principais"],
            [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 4.0},
                {"x": 0.0, "y": 4.0},
            ],
        )
        self.assertEqual(
            molde["pontos"],
            [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0), (0.0, 0.0)],
        )


if __name__ == "__main__":
    unittest.main()
