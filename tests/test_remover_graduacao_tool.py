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
    FerramentaRemoverGraduacao = None
else:
    from PySide6.QtCore import QPointF, Qt, Signal
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.remover_graduacao_tool import Ferramenta as FerramentaRemoverGraduacao


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
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 0.0)],
                    "graduacao_tabela": {"pontos": {"0": {"valores": {"G": {"dx": 1.0, "dy": 0.0}}}}},
                    "graduacao_pontos": {"0": {"valores": {"G": {"dx": 1.0, "dy": 0.0}}}},
                    "graduacao_tamanhos": [{"tamanho": "M", "base": True}],
                    "graduacao_grade_nome": "P-G(M)",
                    "graduacao_tamanhos_ativos": ["M"],
                },
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(20.0, 0.0), (30.0, 0.0), (30.0, 10.0), (20.0, 0.0)],
                    "graduacao_tabela": {"pontos": {}},
                },
            ]
        )
        self._selecionados = set()
        self.historico = 0
        self.atualizou = False
        self.ferramenta_ativa = None
        self.lbl_status = None

    def _indice_molde_em_ponto(self, pos):
        return 0 if pos.x() < 15.0 else 1

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1
        self.elementos_alterados.emit()

    def update(self):
        self.atualizou = True

    def set_ferramenta_ativa(self, nome):
        self.ferramenta_ativa = nome


@unittest.skipIf(FerramentaRemoverGraduacao is None, "PySide6 não disponível neste ambiente")
class RemoverGraduacaoToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_click_remove_toda_graduacao_apenas_do_molde_indicado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaRemoverGraduacao()
        event = _FakeEvent(QPointF(5.0, 5.0))

        self.assertTrue(ferramenta.on_mouse_press(canvas, event))

        molde = canvas.cena.elementos[0]
        outro = canvas.cena.elementos[1]
        self.assertFalse(any(str(chave).startswith("graduacao_") for chave in molde))
        self.assertIn("graduacao_tabela", outro)
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.atualizou)
        self.assertTrue(event.accepted)


if __name__ == "__main__":
    unittest.main()
