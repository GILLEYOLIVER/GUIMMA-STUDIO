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
    import tools.desdobrar_tool as desdobrar_tool_module
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

    def modifiers(self):
        return Qt.NoModifier


@unittest.skipIf(FerramentaDobrar is None, "PySide6 nao disponivel neste ambiente")
class DobrarToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_manter_dimensoes_inicia_marcado(self):
        dialog = DobrarDialog()
        self.assertTrue(dialog.chk_manter_dimensoes.isChecked())
        self.assertEqual(dialog.chk_manter_dimensoes.text(), "Preservar original para desdobrar")
        self.assertEqual([dialog.cmb_modo.itemText(i) for i in range(dialog.cmb_modo.count())], ["Horizontal", "Vertical", "Elemento", "Linha"])
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

    def test_desdobrar_borda_de_dobra_monta_lado_externo_sem_caixa(self):
        ferramenta = FerramentaDesdobrar()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
            "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
        }

        resultado = ferramenta._resultado_desdobrar_copia_exata(molde, ("v", 0.0))
        pontos = [(round(p.x(), 6), round(p.y(), 6)) for p in resultado]

        self.assertIn((10.0, 0.0), pontos)
        self.assertIn((10.0, 5.0), pontos)
        self.assertIn((-10.0, 0.0), pontos)
        self.assertIn((-10.0, 5.0), pontos)
        self.assertEqual(pontos[0], pontos[-1])
        self.assertLessEqual(max(y for _x, y in pontos), 5.0)
        self.assertGreaterEqual(min(y for _x, y in pontos), 0.0)
        self.assertLessEqual(max(x for x, _y in pontos), 10.0)
        self.assertGreaterEqual(min(x for x, _y in pontos), -10.0)

    def test_desdobrar_tenta_motor_cpp_antes_do_fallback_python(self):
        chamadas = []
        original = desdobrar_tool_module.unfold_mirrored_contour_cpp

        def fake_cpp(points, axis_kind, axis_value=0.0, axis_p1=(0.0, 0.0), axis_p2=(1.0, 0.0), tolerance=1e-7):
            chamadas.append((list(points), axis_kind, axis_value, axis_p1, axis_p2, tolerance))
            return [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (-2.0, 1.0), (-2.0, 0.0), (0.0, 0.0)]

        desdobrar_tool_module.unfold_mirrored_contour_cpp = fake_cpp
        self.addCleanup(setattr, desdobrar_tool_module, "unfold_mirrored_contour_cpp", original)
        ferramenta = FerramentaDesdobrar()

        resultado = ferramenta._desdobrar_contorno_por_eixo(
            [QPointF(0.0, 0.0), QPointF(2.0, 0.0), QPointF(2.0, 1.0), QPointF(0.0, 1.0)],
            ("v", 0.0),
        )

        self.assertTrue(chamadas)
        self.assertEqual([(p.x(), p.y()) for p in resultado], [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (-2.0, 1.0), (-2.0, 0.0), (0.0, 0.0)])

    def test_desdobrar_nao_aplica_resultado_explodido_no_pos_processamento(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDesdobrar()
        dialog = DesdobrarDialog(canvas)
        dialog.chk_copiar_contorno_dobrado.setChecked(False)
        ferramenta._dialog_por_canvas[id(canvas)] = dialog
        molde = canvas.cena.elementos[0]
        pontos_originais = list(molde["pontos"])
        controles_originais = list(molde["controle_cantos"])

        def pos_processamento_explodido(_molde, _contorno, _eixo):
            return [
                QPointF(0.0, 0.0),
                QPointF(100000.0, 0.0),
                QPointF(100000.0, 100000.0),
                QPointF(0.0, 100000.0),
                QPointF(0.0, 0.0),
            ]

        ferramenta._garantir_pontos_controle_no_desdobrado = pos_processamento_explodido
        linha = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (0.0, 8.0)],
            "origem_desdobrar": "manual",
        }

        ferramenta._aplicar_desdobrar(canvas, 0, linha)

        self.assertEqual(molde["pontos"], pontos_originais)
        self.assertEqual(molde["controle_cantos"], controles_originais)
        self.assertEqual(canvas.historico, 0)
        dialog.deleteLater()

    def test_desdobrar_nao_restaura_contorno_original_explodido(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDesdobrar()
        dialog = DesdobrarDialog(canvas)
        ferramenta._dialog_por_canvas[id(canvas)] = dialog
        molde = canvas.cena.elementos[0]
        pontos_originais = list(molde["pontos"])
        molde["contornos_dobra_original"] = [
            {
                "pontos": [
                    (0.0, 0.0),
                    (50000.0, 0.0),
                    (50000.0, 50000.0),
                    (0.0, 50000.0),
                    (0.0, 0.0),
                ],
                "contorno_dobrado": list(pontos_originais),
                "eixo": {"tipo": "v", "valor": 0.0},
            }
        ]
        linha = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (0.0, 8.0)],
            "origem_desdobrar": "dobra_original",
        }

        restaurou = ferramenta._restaurar_dobra_original(canvas, 0, molde, linha, ("v", 0.0))

        self.assertFalse(restaurou)
        self.assertEqual(molde["pontos"], pontos_originais)
        self.assertEqual(canvas.historico, 0)
        dialog.deleteLater()

    def test_desdobrar_limpa_sombra_estado_e_auxiliares_da_dobra(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaDesdobrar()
        dialog = DesdobrarDialog(canvas)
        ferramenta._dialog_por_canvas[id(canvas)] = dialog
        molde = canvas.cena.elementos[0]
        molde.update(
            {
                "molde_dobrado": True,
                "dobra_eixo": {"tipo": "v", "valor": 0.0},
                "mostrar_contorno_dobra_original": True,
                "estado_dobra": {
                    "ativo": True,
                    "contorno_lado_dobrado": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 0.0)],
                },
                "contornos_dobra_original": [
                    {
                        "contorno_pontilhado": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 0.0)],
                        "eixo": {"tipo": "v", "valor": 0.0},
                    }
                ],
                "controle_auxiliares": [(5.0, 0.0)],
                "pontos_auxiliares": [{"x": 5.0, "y": 0.0}],
            }
        )
        linha = {"tipo": "polyline", "pontos": [(0.0, 0.0), (0.0, 8.0)], "origem_desdobrar": "manual"}

        ferramenta._aplicar_desdobrar(canvas, 0, linha)

        self.assertFalse(molde["molde_dobrado"])
        for chave in (
            "estado_dobra",
            "contornos_dobra_original",
            "mostrar_contorno_dobra_original",
            "dobra_eixo",
            "controle_auxiliares",
            "pontos_auxiliares",
        ):
            self.assertNotIn(chave, molde)
        self.assertEqual(canvas.historico, 1)
        dialog.deleteLater()

    def test_desdobrar_nao_promove_amostras_de_curva_para_controles(self):
        ferramenta = FerramentaDesdobrar()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
            "pontos_controle_referencia": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
        }
        topo = [QPointF(i / 10.0, (i % 5) * 0.01) for i in range(0, 101)]
        direita = [QPointF(10.0, y / 10.0) for y in range(1, 51)]
        fundo = [QPointF(10.0 - (i / 10.0), 5.0 + (i % 5) * 0.01) for i in range(1, 101)]
        esquerda = [QPointF(0.0, 5.0 - (y / 10.0)) for y in range(1, 50)]
        contorno = topo + direita + fundo + esquerda + [QPointF(0.0, 0.0)]

        controles = ferramenta._controles_resultado_desdobrar(molde, contorno, ("v", 0.0))
        pontos = {(round(p.x(), 6), round(p.y(), 6)) for p in controles}

        self.assertLessEqual(len(controles), 8)
        self.assertIn((0.0, 0.0), pontos)
        self.assertIn((10.0, 0.0), pontos)
        self.assertIn((10.0, 5.0), pontos)

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

    def test_dobra_horizontal_usa_centro_do_molde(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0].update(
            {
                "pontos": [(0.0, -2.0), (30.0, -1.0), (12.0, 10.0), (0.0, 8.0), (0.0, -2.0)],
                "controle_cantos": [(0.0, -2.0), (30.0, -1.0), (12.0, 10.0), (0.0, 8.0)],
                "pontos_controle_referencia": [(0.0, -2.0), (30.0, -1.0), (12.0, 10.0), (0.0, 8.0)],
            }
        )
        ferramenta = FerramentaDobrar()

        self.assertEqual(ferramenta._eixo(canvas, [0], "Horizontal"), ("h", 4.0))

    def test_dobrar_contorno_fica_no_lado_escolhido(self):
        ferramenta = FerramentaDobrar()
        pontos = [
            QPointF(-5.0, -4.0),
            QPointF(4.0, -4.0),
            QPointF(6.0, 5.0),
            QPointF(-5.0, 4.0),
            QPointF(-5.0, -4.0),
        ]

        resultado = ferramenta._pontos_dobrados_preview(pontos, ("h", 0.0), -1, fechado=True)

        self.assertGreaterEqual(len(resultado), 4)
        self.assertTrue(all(p.y() <= 1e-6 for p in resultado))
        self.assertEqual(resultado[0], resultado[-1])

    def test_dobrar_modo_elemento_usa_linha_interna_como_eixo(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "molde": False,
                "pontos": [(-5.0, 4.0), (15.0, 4.0)],
            }
        )
        ferramenta = FerramentaDobrar()
        dialog = DobrarDialog(canvas)
        dialog.cmb_modo.setCurrentText("Elemento")
        ferramenta._dialog_por_canvas[id(canvas)] = dialog

        ref = ferramenta._elemento_dobra_em_ponto(canvas, [0], QPointF(5.0, 4.0))
        ferramenta._elemento_ref = ref
        eixo = ferramenta._eixo(canvas, [0], "Elemento")

        self.assertEqual(ref, 1)
        self.assertIsNotNone(eixo)
        self.assertEqual(eixo[0], "line")
        self.assertEqual((eixo[1].x(), eixo[1].y()), (-5.0, 4.0))
        self.assertEqual((eixo[2].x(), eixo[2].y()), (15.0, 4.0))

        ferramenta._lado_preview = ferramenta._calcular_lado_preview(canvas, QPointF(5.0, 1.0))
        ferramenta._aplicar(canvas, "Elemento")

        serializado = canvas.cena.elementos[0]["dobra_eixo"]
        self.assertEqual(serializado["tipo"], "line")
        self.assertEqual(serializado["p1"], (-5.0, 4.0))
        self.assertEqual(serializado["p2"], (15.0, 4.0))
        pontos_dobrados = [QPointF(x, y) for x, y in canvas.cena.elementos[0]["pontos"]]
        self.assertTrue(all(p.y() <= 4.000001 for p in pontos_dobrados))
        self.assertEqual(canvas.historico, 1)
        self.assertIsNone(ferramenta._elemento_ref)
        dialog.deleteLater()

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

    def test_dobrar_nao_promove_amostras_de_curva_para_controles(self):
        ferramenta = FerramentaDobrar()
        topo = [(-10.0 + (i / 5.0), (i % 5) * 0.01) for i in range(0, 101)]
        direita = [(10.0, y / 10.0) for y in range(1, 51)]
        fundo = [(10.0 - (i / 5.0), 5.0 + (i % 5) * 0.01) for i in range(1, 101)]
        esquerda = [(-10.0, 5.0 - (y / 10.0)) for y in range(1, 50)]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": topo + direita + fundo + esquerda + [topo[0]],
            "controle_cantos": [(-10.0, 0.0), (10.0, 0.0), (10.0, 5.0), (-10.0, 5.0)],
            "pontos_controle_referencia": [(-10.0, 0.0), (10.0, 0.0), (10.0, 5.0), (-10.0, 5.0)],
        }
        total_amostras = len(molde["pontos"])

        ferramenta._dobrar_elemento(molde, ("v", 0.0), 1)

        self.assertLess(len(molde["controle_cantos"]), total_amostras)
        self.assertLessEqual(len(molde["controle_cantos"]), 2)
        self.assertLessEqual(len(molde["pontos_controle_referencia"]), 2)

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
