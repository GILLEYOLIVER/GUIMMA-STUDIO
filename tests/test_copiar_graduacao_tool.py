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
    QWidget = object
    FerramentaCopiarGraduacao = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.copiar_graduacao_tool import Ferramenta as FerramentaCopiarGraduacao


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
                    "graduacao_tabela": {
                        "pontos": {
                            "0": {
                                "valores": {
                                    "P": {"dx": -0.5, "dy": 0.5},
                                    "G": {"dx": 0.5, "dy": -0.5},
                                }
                            },
                            "1": {
                                "valores": {
                                    "P": {"dx": -1.0, "dy": 2.0},
                                    "G": {"dx": 3.0, "dy": -4.0},
                                }
                            }
                        }
                    },
                    "graduacao_pontos": {
                        "1": {
                            "valores": {
                                "P": {"dx": -1.0, "dy": 2.0},
                                "G": {"dx": 3.0, "dy": -4.0},
                            }
                        }
                    },
                },
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(100.0, 0.0), (110.0, 0.0), (110.0, 5.0), (100.0, 0.0)],
                    "controle_cantos": [(100.0, 0.0), (110.0, 0.0), (110.0, 5.0), (100.0, 0.0)],
                    "graduacao_tamanhos": [
                        {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                        {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                        {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
                    ],
                },
            ]
        )
        self._selecionados = set()
        self.zoom = 1.0
        self.historico = 0
        self.atualizou = False
        self.ferramenta_ativa = None
        self.lbl_status = None

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def _indice_molde_em_ponto(self, pos):
        if 0.0 <= pos.x() <= 10.0 and 0.0 <= pos.y() <= 5.0:
            return 0
        if 100.0 <= pos.x() <= 110.0 and 0.0 <= pos.y() <= 5.0:
            return 1
        return None

    def _registrar_historico(self):
        self.historico += 1

    def set_ferramenta_ativa(self, ferramenta):
        self.ferramenta_ativa = ferramenta

    def update(self):
        self.atualizou = True


@unittest.skipIf(FerramentaCopiarGraduacao is None, "PySide6 nao disponivel neste ambiente")
class CopiarGraduacaoToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dialogo_exibe_opcoes_de_copia_graduacao(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaCopiarGraduacao()
        dialog = ferramenta._obter_dialog(canvas)

        opcoes = [dialog.cmb_modo.itemText(i) for i in range(dialog.cmb_modo.count())]

        self.assertEqual(
            opcoes,
            [
                "1 ponto graduado",
                "Vários pontos de controle",
                "Todos os pontos de controle",
            ],
        )
        self.assertEqual(dialog.cmb_modo.currentText(), "1 ponto graduado")

    def test_copia_ponto_e_cola_em_outro_molde_sem_usar_tabela(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaCopiarGraduacao()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0))))
        self.assertEqual(ferramenta._origem, (0, 1))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(105.0, 2.0))))
        self.assertEqual(canvas._selecionados, {1})
        self.assertNotIn("graduacao_tabela", canvas.cena.elementos[1])
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 0.0))))

        valores = canvas.cena.elementos[1]["graduacao_tabela"]["pontos"]["1"]["valores"]
        self.assertEqual(valores["P"], {"dx": -1.0, "dy": 2.0})
        self.assertEqual(valores["G"], {"dx": 3.0, "dy": -4.0})
        self.assertEqual(canvas._selecionados, {1})
        self.assertEqual(canvas.historico, 1)

    def test_colar_apenas_dx_preserva_dy_do_destino(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        canvas.cena.elementos[1]["graduacao_tabela"] = {
            "pontos": {"1": {"valores": {"P": {"dx": 9.0, "dy": 8.0}}}}
        }
        ferramenta = FerramentaCopiarGraduacao()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.chk_apenas_dx.setChecked(True)

        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0)))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(105.0, 2.0)))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 0.0)))

        valores = canvas.cena.elementos[1]["graduacao_tabela"]["pontos"]["1"]["valores"]
        self.assertEqual(valores["P"], {"dx": -1.0, "dy": 8.0})

    def test_varios_pontos_seleciona_um_a_um_no_sentido_horario_e_cola_mesma_sequencia(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaCopiarGraduacao()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.cmb_modo.setCurrentText("Vários pontos de controle")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(0.0, 0.0))))
        self.assertEqual(ferramenta._faixa_preview_indices, [0])
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(10.0, 0.0))))
        self.assertEqual(ferramenta._faixa_preview_indices, [0])
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(10.0, 5.0))))
        self.assertEqual(ferramenta._faixa_preview_indices, [0, 2])
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(10.0, 0.0))))
        self.assertEqual(ferramenta._faixa_preview_indices, [0, 2, 1])
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0))))
        self.assertEqual(ferramenta._indices_copiados, [0, 2, 1])

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(105.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(100.0, 0.0))))

        pontos = canvas.cena.elementos[1]["graduacao_tabela"]["pontos"]
        self.assertEqual(pontos["0"]["valores"]["P"], {"dx": -0.5, "dy": 0.5})
        self.assertEqual(pontos["1"]["valores"]["P"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos["2"]["valores"]["P"], {"dx": -1.0, "dy": 2.0})

    def test_clique_direito_fecha_destino_e_depois_origem(self):
        canvas = _FakeCanvas()
        canvas._selecionados = {0}
        ferramenta = FerramentaCopiarGraduacao()
        ferramenta.on_activate(canvas)
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0)))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(105.0, 2.0)))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 0.0)))

        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 0.0), button=Qt.RightButton))
        self.assertEqual(canvas._selecionados, {0})
        self.assertIsNone(canvas.ferramenta_ativa)

        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0), button=Qt.RightButton))
        self.assertEqual(canvas.ferramenta_ativa, "selecionar")


if __name__ == "__main__":
    unittest.main()
