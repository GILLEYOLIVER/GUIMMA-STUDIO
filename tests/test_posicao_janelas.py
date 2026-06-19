from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

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

    from tools.dialog_position_patch import aplicar_patch_posicao_dialogos
    from ui.janela_principal import GuimmaStudioMainWindow
    from ui.posicao_janelas import _FiltroMemoriaPosicao, _grupo, _grupo_estado, ajustar_para_area, instalar_memoria_posicao, restaurar_posicao, salvar_posicao


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

    def test_restaurar_posicao_dialogo_prioriza_fallback_inicial(self):
        chave = "teste:dialogo_fallback_inicial"
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

        self.assertEqual(dialog.pos(), QPoint(0, 0))
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))

    def test_restaurar_posicao_dialogo_com_fallback_ignora_salvo_mesmo_apos_mover(self):
        chave = "teste:dialogo_fallback_ate_mover"
        cfg = QSettings("GUIMMA", "GUIMMA-STUDIO")
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))
        antigo = QDialog()
        antigo.resize(120, 80)
        antigo.move(QPoint(300, 260))
        salvar_posicao(antigo, chave)

        dialog = QDialog()
        dialog.resize(160, 100)

        self.assertFalse(restaurar_posicao(dialog, chave, fallback=QPoint(20, 30)))
        self.assertEqual(dialog.pos(), QPoint(20, 30))
        self.assertFalse(restaurar_posicao(dialog, chave, fallback=QPoint(40, 50)))
        self.assertEqual(dialog.pos(), QPoint(40, 50))

        dialog._guimma_posicao_movida_usuario = True
        self.assertFalse(restaurar_posicao(dialog, chave, fallback=QPoint(60, 70)))
        self.assertEqual(dialog.pos(), QPoint(60, 70))
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))

    def test_dialogo_reaplica_fallback_apos_show(self):
        chave = "teste:dialogo_reaplica_fallback_show"
        cfg = QSettings("GUIMMA", "GUIMMA-STUDIO")
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))
        dialog = QDialog()
        dialog.resize(160, 100)
        instalar_memoria_posicao(dialog, chave)

        self.assertFalse(restaurar_posicao(dialog, chave, fallback=QPoint(25, 35)))
        dialog._guimma_ultima_posicao_programatica = QPoint(300, 260)
        dialog.move(QPoint(300, 260))
        dialog.show()
        QApplication.processEvents()
        QApplication.processEvents()

        self.assertEqual(dialog.pos(), QPoint(25, 35))
        dialog.close()
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))

    def test_patch_global_show_respeita_fallback_da_ferramenta(self):
        aplicar_patch_posicao_dialogos()
        chave = "teste:dialogo_patch_fallback"
        cfg = QSettings("GUIMMA", "GUIMMA-STUDIO")
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))
        dialog = QDialog()
        dialog.resize(160, 100)
        instalar_memoria_posicao(dialog, chave)

        self.assertFalse(restaurar_posicao(dialog, chave, fallback=QPoint(45, 55)))
        dialog.move(QPoint(300, 260))
        dialog.show()
        QApplication.processEvents()

        self.assertEqual(dialog.pos(), QPoint(45, 55))
        dialog.close()
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))

    def test_restaurar_posicao_dialogo_sem_fallback_centraliza(self):
        chave = "teste:dialogo_centralizado_sem_fallback"
        cfg = QSettings("GUIMMA", "GUIMMA-STUDIO")
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))
        dialog = QDialog()
        dialog.resize(160, 100)

        self.assertFalse(restaurar_posicao(dialog, chave))

        tela = dialog.screen() or QApplication.primaryScreen()
        self.assertIsNotNone(tela)
        area = tela.availableGeometry()
        centro_dialogo = dialog.frameGeometry().center()
        self.assertLessEqual(abs(centro_dialogo.x() - area.center().x()), 2)
        self.assertLessEqual(abs(centro_dialogo.y() - area.center().y()), 2)
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))

    def test_restaurar_posicao_dialogo_de_ferramenta_sem_fallback_usa_canvas(self):
        chave = "teste:dialogo_tool_sem_fallback_canvas"
        cfg = QSettings("GUIMMA", "GUIMMA-STUDIO")
        cfg.remove(_grupo(chave))
        cfg.remove(_grupo_estado(chave))
        canvas = QWidget()
        canvas.resize(1000, 700)
        canvas.calcular_posicao_painel_auxiliar = lambda largura, altura, abaixo_coordenadas=True: QPoint(720, 128)  # type: ignore[attr-defined]
        dialog = QDialog(canvas)
        dialog.resize(180, 90)

        self.assertFalse(restaurar_posicao(dialog, chave))

        self.assertEqual(dialog.pos(), canvas.mapToGlobal(QPoint(720, 128)))
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

    def test_caixa_auxiliar_ferramenta_ignora_posicao_salva_no_meio(self):
        canvas = QWidget()
        canvas.resize(1000, 700)
        canvas.calcular_posicao_painel_auxiliar = lambda largura, altura, abaixo_coordenadas=True: QPoint(700, 90)  # type: ignore[attr-defined]
        fake_main = SimpleNamespace(
            _posicoes_caixas_aux={"curva": (300, 260)},
            _area_documento_atual=lambda: SimpleNamespace(canvas=canvas),
        )
        dialog = QDialog(canvas)
        dialog.resize(220, 120)
        dialog._guimma_posicao_movida_usuario = True  # type: ignore[attr-defined]

        GuimmaStudioMainWindow._restaurar_posicao_caixa_aux(fake_main, dialog, "curva")

        self.assertEqual(dialog.pos(), canvas.mapToGlobal(QPoint(700, 90)))
        self.assertFalse(getattr(dialog, "_guimma_posicao_movida_usuario", True))

    def test_caixa_auxiliar_ferramenta_posiciona_com_tamanho_ajustado(self):
        chamadas = []
        canvas = QWidget()
        canvas.resize(1000, 700)

        def calcular(largura, altura, abaixo_coordenadas=True):
            chamadas.append((largura, altura, abaixo_coordenadas))
            return QPoint(1000 - largura - 12, 150)

        canvas.calcular_posicao_painel_auxiliar = calcular  # type: ignore[attr-defined]
        fake_main = SimpleNamespace(
            _posicoes_caixas_aux={},
            _area_documento_atual=lambda: SimpleNamespace(canvas=canvas),
        )
        dialog = QDialog(canvas)
        dialog.setMinimumSize(260, 120)
        dialog.resize(40, 30)

        GuimmaStudioMainWindow._restaurar_posicao_caixa_aux(fake_main, dialog, "retangulo")

        self.assertEqual(chamadas[-1], (260, 120, True))
        self.assertEqual(dialog.pos(), canvas.mapToGlobal(QPoint(728, 150)))
        self.assertEqual(getattr(dialog, "_guimma_fallback_inicial", None), canvas.mapToGlobal(QPoint(728, 150)))

    def test_caixa_auxiliar_retangulo_mantem_posicao_apos_show(self):
        aplicar_patch_posicao_dialogos()
        canvas = QWidget()
        canvas.resize(1000, 700)
        canvas.calcular_posicao_painel_auxiliar = lambda largura, altura, abaixo_coordenadas=True: QPoint(700, 90)  # type: ignore[attr-defined]
        fake_main = SimpleNamespace(
            _posicoes_caixas_aux={},
            _area_documento_atual=lambda: SimpleNamespace(canvas=canvas),
        )
        parent_sem_posicionamento = QWidget()
        parent_sem_posicionamento.resize(1200, 800)
        dialog = QDialog(parent_sem_posicionamento)
        dialog.setWindowTitle("Definir retangulos")
        dialog.resize(260, 120)

        GuimmaStudioMainWindow._restaurar_posicao_caixa_aux(fake_main, dialog, "retangulo")
        esperado = canvas.mapToGlobal(QPoint(700, 90))
        dialog.move(QPoint(300, 260))
        dialog.show()
        QApplication.processEvents()

        self.assertEqual(dialog.pos(), esperado)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
