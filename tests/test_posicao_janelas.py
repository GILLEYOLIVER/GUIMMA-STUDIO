from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QEvent = None
    QPoint = None
    QSettings = None
    Qt = None
    QDialog = None
    QWidget = None
    _FiltroMemoriaPosicao = None
else:
    from PySide6.QtCore import QEvent, QPoint, QSettings, Qt
    from PySide6.QtWidgets import QApplication, QDialog, QWidget

    from ui.posicao_janelas import _FiltroMemoriaPosicao, _grupo, _grupo_estado, ajustar_para_area, restaurar_posicao, salvar_posicao


@unittest.skipIf(QApplication is None, "PySide6 nao disponivel neste ambiente")
class PosicaoJanelasTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_filtro_memoria_posicao_nao_quebra_sem_widget(self):
        widget = QWidget()
        filtro = _FiltroMemoriaPosicao(widget, "teste:filtro")
        delattr(filtro, "_widget")

        filtro.eventFilter(widget, QEvent(QEvent.Move))

    def test_restaurar_posicao_prioriza_fallback_na_primeira_abertura(self):
        chave = "teste:posicao_inicial_fallback"
        cfg = QSettings("GUIMMA", "GUIMMA-STUDIO")
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))
        widget = QWidget()
        widget.resize(40, 40)
        widget.move(QPoint(180, 180))
        salvar_posicao(widget, chave)

        widget.move(QPoint(0, 0))
        self.assertFalse(restaurar_posicao(widget, chave, fallback=QPoint(20, 30)))

        self.assertEqual(widget.pos(), QPoint(20, 30))
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))

    def test_restaurar_posicao_dialogo_abre_centralizado_na_tela(self):
        chave = "teste:dialogo_centralizado_tela"
        cfg = QSettings("GUIMMA", "GUIMMA-STUDIO")
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))
        antigo = QDialog()
        antigo.resize(120, 80)
        antigo.move(QPoint(12, 18))
        salvar_posicao(antigo, chave)

        dialog = QDialog()
        dialog.resize(160, 100)

        self.assertFalse(restaurar_posicao(dialog, chave, fallback=QPoint(0, 0)))

        tela = dialog.screen() or QApplication.primaryScreen()
        self.assertIsNotNone(tela)
        area = tela.availableGeometry()
        centro_dialogo = dialog.frameGeometry().center()
        self.assertLessEqual(abs(centro_dialogo.x() - area.center().x()), 2)
        self.assertLessEqual(abs(centro_dialogo.y() - area.center().y()), 2)
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))

    def test_ajustar_para_area_prende_dialogo_tool_na_janela_parent(self):
        parent = QWidget()
        parent.resize(360, 240)
        parent.move(100, 100)
        dialog = QDialog(parent)
        dialog.setWindowFlags(Qt.Tool)
        dialog.resize(120, 90)

        pos = ajustar_para_area(dialog, QPoint(9999, 9999))
        area = parent.window().frameGeometry().adjusted(8, 8, -8, -8)

        self.assertGreaterEqual(pos.x(), area.left())
        self.assertGreaterEqual(pos.y(), area.top())
        self.assertLessEqual(pos.x() + dialog.width(), area.right() + 1)
        self.assertLessEqual(pos.y() + dialog.height(), area.bottom() + 1)


if __name__ == "__main__":
    unittest.main()
