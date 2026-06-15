from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QWidget = None
    QPointF = None
    Qt = None
    FerramentaDobrar = None
    FerramentaDesdobrar = None
    FerramentaManipularPontos = None
    DesdobrarDialog = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.dobrar_tool import DobrarDialog, Ferramenta as FerramentaDobrar
    from tools.desdobrar_tool import DesdobrarDialog, Ferramenta as FerramentaDesdobrar
    from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)],
                    "pontos_controle_referencia": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)],
                }
            ]
        )
        self._selecionados = {0}
        self.zoom = 10.0
        self.historico = 0
        self.lbl_status = None

    def _registrar_historico(self):
        self.historico += 1

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _indice_molde_em_ponto(self, pos):
        return 0

    def update(self):
        pass


class _FakeEvent:
    def __init__(self, pos):
        self._pos = QPointF(pos)
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def position(self):
        return QPointF(self._pos)

    def accept(self):
        self.accepted = True


@unittest.skipIf(FerramentaDobrar is None, "PySide6 nao disponivel neste ambiente")
class DobrarToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_manter_dimensoes_inicia_marcado(self):
        dialog = DobrarDialog()
        self.assertTrue(dialog.chk_manter_dimensoes.isChecked())
        self.assertEqual(dialog.chk_manter_dimensoes.text(), "Preservar original para desdobrar")
        self.assertEqual([dialog.cmb_modo.itemText(i) for i in range(dialog.cmb_modo.count())], ["Horizontal", "Vertical", "Linha"])
        self.assertFalse(dialog.chk_fio_meio.isChecked())
        dialog.deleteLater()

    def test_desdobrar_dialog_fluxo_padrao(self):
        dialog = DesdobrarDialog()
        self.assertTrue(dialog.chk_automatico.isChecked())
        self.assertTrue(dialog.chk_copiar_contorno_dobrado.isChecked())
        self.assertTrue(dialog.chk_fio_meio.isChecked())
        self.assertTrue(hasattr(dialog, "chk_inserir_pique"))
        self.assertFalse(dialog.chk_inserir_pique.isChecked())
        self.assertGreaterEqual(dialog.minimumWidth(), 390)
        self.assertEqual(dialog.chk_copiar_contorno_dobrado.text(), "Espelhar lado visível e deixar os lados idênticos")
        dialog.deleteLater()

    def test_desdobrar_curva_do_perimetro_usa_eixo_reto_e_lados_identicos(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (4.0, 2.0),
                    (10.0, 0.0),
                    (10.0, 5.0),
                    (0.0, 5.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                "pontos_controle_referencia": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
            }
        )
        ferramenta = FerramentaDesdobrar()
        dialog = DesdobrarDialog(canvas)
        dialog.chk_copiar_contorno_dobrado.setChecked(False)
        ferramenta._dialog_por_canvas[id(canvas)] = dialog

        linha = ferramenta._linha_do_proprio_molde_em_ponto(canvas, 0, QPointF(4.0, 2.0))
        self.assertIsNotNone(linha)
        self.assertEqual(linha["origem_desdobrar"], "perimetro_principal")
        self.assertGreater(len(ferramenta._pontos_para_hit_linha(linha)), 2)
        preview_linha = ferramenta._pontos_para_preview_linha(linha)
        self.assertEqual([(p.x(), p.y()) for p in preview_linha], [(0.0, 0.0), (10.0, 0.0)])
        self.assertTrue(ferramenta._deve_espelhar_contorno_identico(canvas, linha, linha))

        resultado = ferramenta._preview_desdobrar(canvas, 0, linha)
        pontos = {(round(p.x(), 6), round(p.y(), 6)) for p in resultado}

        self.assertIn((4.0, 2.0), pontos)
        self.assertIn((4.0, -2.0), pontos)
        dialog.deleteLater()

    def test_desdobrar_primeiro_clique_na_curva_do_molde_prepara_preview(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [
                    (0.0, 0.0),
                    (4.0, 2.0),
                    (10.0, 0.0),
                    (10.0, 5.0),
                    (0.0, 5.0),
                    (0.0, 0.0),
                ],
                "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                "pontos_controle_referencia": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
            }
        )
        ferramenta = FerramentaDesdobrar()
        dialog = DesdobrarDialog(canvas)
        ferramenta._dialog_por_canvas[id(canvas)] = dialog

        evento = _FakeEvent(QPointF(4.0, 2.0))
        self.assertTrue(ferramenta.on_mouse_press(canvas, evento))

        self.assertTrue(evento.accepted)
        self.assertEqual(ferramenta._molde_idx, 0)
        self.assertIsNotNone(ferramenta._confirmar_ref)
        self.assertEqual(ferramenta._confirmar_ref["origem_desdobrar"], "perimetro_principal")
        dialog.deleteLater()

    def test_dobra_meio_respeita_ponto_medio_da_reta_maior(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDobrar()

        self.assertEqual(ferramenta._eixo(canvas, [0], "Horizontal"), ("h", 4.0))
        self.assertEqual(ferramenta._eixo(canvas, [0], "Vertical"), ("v", 5.0))

    def test_dobrar_mantem_contorno_pontilhado_fechado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDobrar()
        ferramenta._dialog_por_canvas[id(canvas)] = DobrarDialog(canvas)
        ferramenta._dialog_por_canvas[id(canvas)].chk_manter_dimensoes.setChecked(True)
        ferramenta._lado_preview = 1

        ferramenta._aplicar(canvas, "Horizontal")

        molde = canvas.cena.elementos[0]
        registros = molde.get("contornos_dobra_original")
        self.assertIsInstance(registros, list)
        self.assertTrue(registros)
        pontilhado = registros[-1].get("contorno_pontilhado")
        self.assertGreaterEqual(len(pontilhado), 4)
        self.assertEqual(pontilhado[0], pontilhado[-1])
        self.assertTrue(molde["molde_dobrado"])
        self.assertEqual(canvas.historico, 1)

    def test_manipular_pontos_edita_contorno_pontilhado_da_dobra(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde["contornos_dobra_original"] = [
            {
                "contorno_pontilhado": [(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 0.0)],
                "metade_movida": [(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 0.0)],
            }
        ]
        ferramenta = FerramentaManipularPontos()

        ferramenta._atualizar_dobra_pontilhada(canvas, (0, 0, 1), QPointF(6.0, 1.0))

        registro = molde["contornos_dobra_original"][0]
        self.assertEqual(registro["contorno_pontilhado"][1], (6.0, 1.0))
        self.assertEqual(registro["metade_movida"][1], (6.0, 1.0))


if __name__ == "__main__":
    unittest.main()
