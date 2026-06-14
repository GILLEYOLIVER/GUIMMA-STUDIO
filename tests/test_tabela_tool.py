from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaTabela = None
    QApplication = None
    QPointF = None

    class _QtIndisponivel:
        NoModifier = 0
        LeftButton = 1
        ControlModifier = 2

    class QWidget:
        pass

    class _SignalIndisponivel:
        def connect(self, *_args, **_kwargs):
            return None

        def emit(self, *_args, **_kwargs):
            return None

    def Signal(*_args, **_kwargs):
        return _SignalIndisponivel()

    Qt = _QtIndisponivel()
else:
    from PySide6.QtCore import QPointF, Qt, Signal
    from PySide6.QtWidgets import QApplication, QWidget

    from canvas.visualizacao import VisualizacaoCanvas
    from tools.tabela_tool import Ferramenta as FerramentaTabela


class _FakeMouseEvent:
    def __init__(self, pos: QPointF, *, modifiers=Qt.NoModifier, button=Qt.LeftButton):
        self._pos = QPointF(pos)
        self._modifiers = modifiers
        self._button = button
        self.accepted = False

    def button(self):
        return self._button

    def position(self):
        return QPointF(self._pos)

    def modifiers(self):
        return self._modifiers

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
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                    "graduacao_tamanhos": [
                        {"ativo": True, "tamanho": "P", "cor": "#c87575", "base": False},
                        {"ativo": True, "tamanho": "M", "cor": "#ffff00", "base": True},
                        {"ativo": True, "tamanho": "G", "cor": "#5d95b7", "base": False},
                    ],
                }
            ]
        )
        self._selecionados = {0}
        self.zoom = 1.0
        self.historico = 0
        self.atualizou = False
        self.ferramenta_ativa = None
        self.lbl_status = None
        self.resposta_definir_grade = True
        self.confirmacoes_definir_grade = []

    def _indice_molde_em_ponto(self, pos):
        return 0 if 0.0 <= pos.x() <= 10.0 and 0.0 <= pos.y() <= 5.0 else None

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizou = True

    def set_ferramenta_ativa(self, nome):
        self.ferramenta_ativa = nome

    def confirmar_definir_grade_molde_separado(self, molde):
        self.confirmacoes_definir_grade.append(molde)
        return self.resposta_definir_grade


@unittest.skipIf(FerramentaTabela is None, "PySide6 não disponível neste ambiente")
class TabelaToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_aplicar_salva_dx_dy_por_tamanho_no_ponto_do_contorno(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        ferramenta.selecionar_ponto(canvas, 1)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.tbl.item(0, 1).setText("-0.5")
        dialog.tbl.item(0, 2).setText("0.25")
        dialog.tbl.item(2, 1).setText("0.5")
        dialog.tbl.item(2, 2).setText("-0.25")

        ferramenta.aplicar_dialog(canvas)

        molde = canvas.cena.elementos[0]
        ponto = molde["graduacao_tabela"]["pontos"]["1"]
        self.assertEqual(ponto["numero"], 2)
        self.assertEqual(ponto["ponto"], (10.0, 0.0))
        self.assertEqual(ponto["valores"]["P"], {"dx": -0.5, "dy": 0.25})
        self.assertEqual(ponto["valores"]["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(ponto["valores"]["G"], {"dx": 0.5, "dy": -0.25})
        self.assertTrue(molde["mostrar_graduacao"])
        self.assertTrue(canvas.atualizou)
        self.assertEqual(canvas.historico, 1)

    def test_aplicar_tabela_reativa_graduacao_oculta_no_canvas(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde["mostrar_graduacao"] = False
        canvas.atualizou = False
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        ferramenta.selecionar_ponto(canvas, 1)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.tbl.item(2, 2).setText("-1")
        canvas.atualizou = False

        ferramenta.aplicar_dialog(canvas)

        self.assertTrue(molde["mostrar_graduacao"])
        self.assertTrue(canvas.atualizou)

    def test_selecionar_ponto_carrega_graduacao_salva_na_coordenada(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde["controle_cantos"] = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)]
        molde["graduacao_tabela"] = {
            "pontos": {
                "7": {
                    "indice": 7,
                    "numero": 8,
                    "ponto": (5.0, 0.0),
                    "valores": {
                        "P": {"dx": -0.7, "dy": 0.2},
                        "M": {"dx": 0.0, "dy": 0.0},
                        "G": {"dx": 1.1, "dy": -0.4},
                    },
                }
            }
        }
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        ferramenta.selecionar_ponto(canvas, 1)

        dialog = ferramenta._obter_dialog(canvas)
        self.assertEqual(dialog.tbl.item(0, 1).text(), "-0.7")
        self.assertEqual(dialog.tbl.item(0, 2).text(), "0.2")
        self.assertEqual(dialog.tbl.item(1, 1).text(), "0")
        self.assertEqual(dialog.tbl.item(1, 2).text(), "0")
        self.assertEqual(dialog.tbl.item(2, 1).text(), "1.1")
        self.assertEqual(dialog.tbl.item(2, 2).text(), "-0.4")

    def test_ponto_sem_graduacao_salva_nao_mostra_valor_interpolado(self):
        ferramenta = FerramentaTabela()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 0.0)],
            "pontos_controle_curva": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": False},
                {"ativo": True, "tamanho": "M", "base": True},
                {"ativo": True, "tamanho": "G", "base": False},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "ponto": (0.0, 0.0),
                        "valores": {
                            "P": {"dx": -1.0, "dy": 0.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 1.0, "dy": 0.0},
                        },
                    },
                    "2": {
                        "ponto": (10.0, 10.0),
                        "valores": {
                            "P": {"dx": -2.0, "dy": 1.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 2.0, "dy": -1.0},
                        },
                    },
                }
            },
        }

        self.assertEqual(ferramenta._valores_ponto(molde, 1), {})

    def test_overlay_usa_config_de_ponto_graduado_e_nao_graduado(self):
        ferramenta = FerramentaTabela()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 0.0)],
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "ponto": (0.0, 0.0),
                        "valores": {"M": {"dx": 0.0, "dy": 0.0}, "G": {"dx": 1.0, "dy": 0.0}},
                    }
                }
            },
        }

        self.assertEqual(ferramenta._chave_config_ponto_overlay(molde, 0), "ponto_controle")
        self.assertEqual(ferramenta._chave_config_ponto_overlay(molde, 1), "ponto_nao_graduado")

    def test_pontos_contorno_remove_fechamento_duplicado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()

        pontos = ferramenta._pontos_contorno(canvas.cena.elementos[0])

        self.assertEqual(len(pontos), 3)
        self.assertEqual(pontos[0], QPointF(0.0, 0.0))
        self.assertEqual(pontos[-1], QPointF(10.0, 5.0))

    def test_pontos_contorno_prioriza_controles_principais_de_molde_extraido(self):
        ferramenta = FerramentaTabela()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
            "controle_cantos": [(0.0, 0.0), (10.0, 5.0)],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 3.0, "y": 1.0},
                {"x": 6.0, "y": 2.0},
                {"x": 10.0, "y": 5.0},
            ],
        }

        pontos = ferramenta._pontos_contorno(molde)

        self.assertEqual(len(pontos), 4)
        self.assertEqual(pontos[1], QPointF(3.0, 1.0))
        self.assertEqual(pontos[2], QPointF(6.0, 2.0))

    def test_pontos_contorno_nao_usa_amostras_de_curva_quando_ha_pontos_principais(self):
        ferramenta = FerramentaTabela()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (2.0, 0.4), (4.0, 0.8), (6.0, 0.4), (8.0, 0.0), (0.0, 0.0)],
            "pontos_graduacao": [
                {"x": 0.0, "y": 0.0},
                {"x": 2.0, "y": 0.4},
                {"x": 4.0, "y": 0.8},
                {"x": 6.0, "y": 0.4},
                {"x": 8.0, "y": 0.0},
            ],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 8.0, "y": 0.0},
            ],
        }

        pontos = ferramenta._pontos_contorno(molde)

        self.assertEqual(pontos, [QPointF(0.0, 0.0), QPointF(8.0, 0.0)])

    def test_pontos_contorno_ignora_controles_desalinhados_do_molde_movido(self):
        ferramenta = FerramentaTabela()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(20.0, 10.0), (30.0, 10.0), (30.0, 15.0), (20.0, 10.0)],
            "pontos_graduacao": [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 5.0},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "1": {
                        "ponto": (10.0, 0.0),
                        "valores": {"G": {"dx": 1.0, "dy": -0.5}},
                    }
                }
            },
        }

        pontos = ferramenta._pontos_contorno(molde)
        valores = ferramenta._valores_ponto(molde, 1)

        self.assertEqual(pontos, [QPointF(20.0, 10.0), QPointF(30.0, 10.0), QPointF(30.0, 15.0)])
        self.assertEqual(valores["G"], {"dx": 1.0, "dy": -0.5})

    def test_pontos_contorno_ignora_controle_parcialmente_fora_do_molde(self):
        ferramenta = FerramentaTabela()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 5.0},
                {"x": 0.0, "y": 5.0},
            ],
            "pontos_graduacao": [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 5.0},
            ],
        }

        pontos = ferramenta._pontos_contorno(molde)

        self.assertEqual(pontos, [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 5.0)])

    def test_pontos_contorno_ignora_desenho_livre_sem_molde(self):
        ferramenta = FerramentaTabela()
        desenho_livre = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
            "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
        }

        self.assertEqual(ferramenta._pontos_contorno(desenho_livre), [])

    def test_seta_para_cima_distribui_dy_negativo_a_partir_da_base(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.setValue(1.0)

        dialog.btn_cima.click()

        valores = dialog.valores()
        self.assertEqual(valores["P"], {"dx": 0.0, "dy": 1.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 0.0, "dy": -1.0})

    def test_incremento_abre_limpo_e_formata_sem_zeros_sobrando(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        self.assertEqual(dialog.sp_incremento.text().strip(), "")
        for valor, texto in ((1.0, "1 cm"), (1.1, "1.1 cm"), (1.78, "1.78 cm"), (1.99, "1.99 cm"), (2.0, "2 cm")):
            dialog.sp_incremento.setValue(valor)
            self.assertEqual(dialog.sp_incremento.text(), texto)

    def test_tamanho_base_preserva_cor_e_realca_apenas_valores_dx_dy(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        item_tamanho = dialog.tbl.item(1, 0)
        self.assertEqual(item_tamanho.background().color().name().lower(), "#ffff00")
        self.assertEqual(item_tamanho.foreground().color().name().lower(), "#111111")
        self.assertTrue(item_tamanho.font().bold())
        for col in (1, 2):
            item = dialog.tbl.item(1, col)
            self.assertEqual(item.background().color().name().lower(), "#2b7cd3")
            self.assertEqual(item.foreground().color().name().lower(), "#ffffff")
            self.assertTrue(item.font().bold())

    def test_seta_de_um_eixo_preserva_graduacao_do_outro_eixo(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.setValue(1.0)

        dialog.btn_cima.click()
        dialog.btn_dir.click()

        valores = dialog.valores()
        self.assertEqual(valores["P"], {"dx": -1.0, "dy": 1.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 1.0, "dy": -1.0})

    def test_seta_confirma_valor_digitado_antes_de_graduar(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.lineEdit().setText("2 cm")

        dialog.btn_dir.click()

        valores = dialog.valores()
        self.assertEqual(valores["P"], {"dx": -2.0, "dy": 0.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 2.0, "dy": 0.0})

    def test_seta_incremental_com_base_maior_cria_apenas_para_dentro(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.definir_tamanhos(
            [
                {"ativo": True, "tamanho": "P", "cor": "#c87575", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#d60b0b", "base": False},
                {"ativo": True, "tamanho": "G", "cor": "#5d95b7", "base": True},
            ],
            {},
        )
        dialog.sp_incremento.setValue(1.0)

        dialog.btn_cima.click()

        valores = dialog.valores()
        self.assertEqual(valores["P"], {"dx": 0.0, "dy": 2.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 1.0})
        self.assertEqual(valores["G"], {"dx": 0.0, "dy": 0.0})

    def test_incremental_aplica_degrau_por_distancia_da_base(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.definir_tamanhos(
            [
                {"ativo": True, "tamanho": "NOVO_SUP_2", "cor": "#4f8a68", "base": False},
                {"ativo": True, "tamanho": "NOVO_SUP_1", "cor": "#b58de8", "base": False},
                {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
                {"ativo": True, "tamanho": "NOVO_INF_3", "cor": "#4f8a68", "base": False},
                {"ativo": True, "tamanho": "NOVO_INF_4", "cor": "#80ff00", "base": False},
            ],
            {},
        )
        dialog.sp_incremento.lineEdit().setText("1")

        dialog.btn_dir.click()
        dialog.btn_baixo.click()

        valores = dialog.valores()
        self.assertEqual(valores["NOVO_SUP_2"], {"dx": -3.0, "dy": -3.0})
        self.assertEqual(valores["NOVO_SUP_1"], {"dx": -2.0, "dy": -2.0})
        self.assertEqual(valores["P"], {"dx": -1.0, "dy": -1.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(valores["G"], {"dx": 1.0, "dy": 1.0})
        self.assertEqual(valores["NOVO_INF_3"], {"dx": 2.0, "dy": 2.0})
        self.assertEqual(valores["NOVO_INF_4"], {"dx": 3.0, "dy": 3.0})

    def test_aba_distancia_angulo_reflete_dx_dy_da_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.lineEdit().setText("2")

        dialog.btn_dir.click()
        dialog.btn_baixo.click()

        self.assertEqual(dialog.tbl_polar.item(0, 1).text(), "2.83")
        self.assertEqual(dialog.tbl_polar.item(0, 2).text(), "225")
        self.assertEqual(dialog.tbl_polar.item(1, 1).text(), "0")
        self.assertEqual(dialog.tbl_polar.item(1, 2).text(), "0")
        self.assertEqual(dialog.tbl_polar.item(2, 1).text(), "2.83")
        self.assertEqual(dialog.tbl_polar.item(2, 2).text(), "45")

    def test_editar_distancia_angulo_recalcula_dx_dy(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        dialog.tbl_polar.item(2, 1).setText("2.828")
        dialog.tbl_polar.item(2, 2).setText("45")

        valores = dialog.valores()
        self.assertAlmostEqual(valores["G"]["dx"], 2.0, places=3)
        self.assertAlmostEqual(valores["G"]["dy"], 2.0, places=3)

    def test_aba_perimetro_mostra_base_e_tamanho_graduado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        ferramenta.selecionar_ponto(canvas, 1)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.tbl.item(2, 1).setText("2")
        ferramenta.aplicar_dialog(canvas)

        perimetro_base = 10.0 + 5.0 + (125.0 ** 0.5)
        perimetro_g = 12.0 + (29.0 ** 0.5) + (125.0 ** 0.5)
        self.assertEqual(dialog.tbl_perimetro.item(1, 0).text(), "M")
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(1, 1).text()), perimetro_base, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(1, 2).text()), 0.0, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(1, 3).text()), perimetro_base, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(1, 4).text()), 0.0, places=2)
        self.assertEqual(dialog.tbl_perimetro.item(2, 0).text(), "G")
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(2, 1).text()), perimetro_g, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(2, 2).text()), perimetro_g - perimetro_base, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(2, 3).text()), perimetro_base, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(2, 4).text()), 0.0, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(2, 5).text()), perimetro_g, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(2, 6).text()), perimetro_g - perimetro_base, places=2)

    def test_aba_perimetro_indica_eixo_dx_dy_ou_dy(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        ferramenta.selecionar_ponto(canvas, 0)
        dialog.tbl.item(0, 2).setText("1")
        dialog.tbl.item(2, 1).setText("1")
        dialog.tbl.item(2, 2).setText("1")
        ferramenta.aplicar_dialog(canvas)

        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(0, 2).text()), 0.0, places=2)
        self.assertNotAlmostEqual(float(dialog.tbl_perimetro.item(0, 4).text()), 0.0, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(1, 2).text()), 0.0, places=2)
        self.assertAlmostEqual(float(dialog.tbl_perimetro.item(1, 4).text()), 0.0, places=2)
        self.assertNotAlmostEqual(float(dialog.tbl_perimetro.item(2, 2).text()), 0.0, places=2)
        self.assertNotAlmostEqual(float(dialog.tbl_perimetro.item(2, 4).text()), 0.0, places=2)

    def test_canvas_monta_contornos_graduados_com_dx_dy_da_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        ferramenta.selecionar_ponto(canvas, 1)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.setValue(1.0)
        dialog.btn_cima.click()
        ferramenta.aplicar_dialog(canvas)

        molde = canvas.cena.elementos[0]
        base = ferramenta._pontos_contorno(molde)
        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)

        nomes = [nome for nome, _cor, _pontos in contornos]
        self.assertEqual(nomes, ["P", "G"])
        contorno_p = contornos[0][2]
        contorno_g = contornos[1][2]
        self.assertEqual(contorno_p[0], QPointF(0.0, 0.0))
        self.assertEqual(contorno_p[1], QPointF(10.0, 1.0))
        self.assertEqual(contorno_p[2], QPointF(10.0, 5.0))
        self.assertEqual(contorno_g[0], QPointF(0.0, 0.0))
        self.assertEqual(contorno_g[1], QPointF(10.0, -1.0))
        self.assertEqual(contorno_g[2], QPointF(10.0, 5.0))
        self.assertEqual(contorno_g[-1], contorno_g[0])

    def test_molde_novo_graduado_na_tabela_nao_depende_de_propriedades(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde.pop("graduacao_tamanhos", None)
        molde.pop("graduacao_tamanhos_ativos", None)
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.setValue(1.0)
        ferramenta.selecionar_ponto(canvas, 0)

        dialog.btn_cima.click()

        base = ferramenta._pontos_contorno(molde)
        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)
        self.assertEqual([nome for nome, _cor, _pontos in contornos], ["P", "G"])
        self.assertEqual(contornos[0][2][0], QPointF(0.0, 1.0))
        self.assertEqual(contornos[0][2][1], QPointF(10.0, 0.0))
        self.assertEqual(contornos[1][2][0], QPointF(0.0, -1.0))
        self.assertEqual(contornos[1][2][1], QPointF(10.0, 0.0))
        self.assertIn("graduacao_tamanhos", molde)
        self.assertEqual(molde["graduacao_tamanhos_ativos"], ["P", "M", "G"])
        self.assertEqual(molde["graduacao_tabela"]["pontos"]["0"]["valores"]["P"]["dy"], 1.0)
        self.assertEqual(molde["graduacao_tabela"]["pontos"]["0"]["valores"]["G"]["dy"], -1.0)

    def test_abrir_tabela_inicializa_grade_no_molde_novo(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde.pop("graduacao_tamanhos", None)
        molde.pop("graduacao_tamanhos_ativos", None)

        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        self.assertEqual([linha["tamanho"] for linha in molde["graduacao_tamanhos"]], ["P", "M", "G"])
        self.assertEqual([linha["cor"] for linha in molde["graduacao_tamanhos"]], ["#ffff00", "#2b7cd3", "#ff8c00"])
        self.assertEqual(molde["graduacao_tamanhos_ativos"], ["P", "M", "G"])
        self.assertTrue(molde["graduacao_tamanhos"][1]["base"])

    def test_tabela_sincroniza_grade_de_molde_extraido_sem_valores(self):
        canvas = _FakeCanvas()
        referencia = canvas.cena.elementos[0]
        referencia["graduacao_grade_nome"] = "P-G(M)"
        extraido = {
            "tipo": "polyline",
            "molde": True,
            "origem_extracao": "contorno",
            "pontos": [(20.0, 0.0), (30.0, 0.0), (30.0, 5.0), (20.0, 0.0)],
            "controle_cantos": [(20.0, 0.0), (30.0, 0.0), (30.0, 5.0)],
            "graduacao_grade_nome": "36-46(40)",
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "36", "cor": "#9678bd", "base": False},
                {"ativo": True, "tamanho": "40", "cor": "#4f8a68", "base": True},
                {"ativo": True, "tamanho": "46", "cor": "#b7d7a8", "base": False},
            ],
            "graduacao_tamanhos_ativos": ["36", "40", "46"],
        }
        canvas.cena.elementos.append(extraido)
        ferramenta = FerramentaTabela()

        self.assertTrue(ferramenta._preparar_molde_para_tabela(canvas, 1))

        self.assertEqual(extraido["graduacao_grade_nome"], "P-G(M)")
        self.assertEqual([linha["tamanho"] for linha in extraido["graduacao_tamanhos"]], ["P", "M", "G"])
        self.assertEqual(extraido["graduacao_tamanhos_ativos"], ["P", "M", "G"])

    def test_molde_separado_sem_grade_pergunta_e_define_tamanho_extraido_como_base(self):
        canvas = _FakeCanvas()
        molde = canvas.cena.elementos[0]
        molde["origem_extracao"] = "separar_tamanho"
        molde["tamanho_extraido"] = "G"
        molde["nome_molde"] = "K1 - G"
        molde["cor"] = "#ff8c00"
        molde.pop("graduacao_tamanhos", None)
        molde.pop("graduacao_tamanhos_ativos", None)
        molde.pop("graduacao_grade_nome", None)

        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        self.assertEqual(canvas.confirmacoes_definir_grade, [molde])
        self.assertEqual([linha["tamanho"] for linha in molde["graduacao_tamanhos"]], ["P", "M", "G"])
        self.assertEqual([linha["base"] for linha in molde["graduacao_tamanhos"]], [False, False, True])
        self.assertEqual(molde["graduacao_grade_nome"], "P-G(G)")
        self.assertEqual(molde["graduacao_tamanhos_ativos"], ["P", "M", "G"])
        self.assertTrue(molde["mostrar_graduacao"])

        ferramenta.selecionar_ponto(canvas, 1)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.sp_incremento.setValue(1.0)
        dialog.btn_cima.click()
        ferramenta.aplicar_dialog(canvas)

        valores = molde["graduacao_tabela"]["pontos"]["1"]["valores"]
        self.assertEqual(valores["P"], {"dx": 0.0, "dy": 2.0})
        self.assertEqual(valores["M"], {"dx": 0.0, "dy": 1.0})
        self.assertEqual(valores["G"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(canvas.historico, 1)

    def test_molde_separado_sem_grade_recusado_nao_inicializa_grade(self):
        canvas = _FakeCanvas()
        canvas.resposta_definir_grade = False
        molde = canvas.cena.elementos[0]
        molde["origem_extracao"] = "separar_tamanho"
        molde["tamanho_extraido"] = "G"
        molde.pop("graduacao_tamanhos", None)
        molde.pop("graduacao_tamanhos_ativos", None)
        molde.pop("graduacao_grade_nome", None)

        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        self.assertEqual(canvas.confirmacoes_definir_grade, [molde])
        self.assertIsNone(ferramenta._molde_idx)
        self.assertNotIn("graduacao_tamanhos", molde)
        self.assertNotIn("graduacao_tabela", molde)

    def test_abrir_tabela_reconhece_molde_sem_selecao_e_mostra_tamanhos_reais(self):
        canvas = _FakeCanvas()
        canvas._selecionados.clear()
        molde = canvas.cena.elementos[0]
        molde["graduacao_tamanhos"] = [
            {"ativo": True, "tamanho": "36", "cor": "#a7cf62", "base": False},
            {"ativo": True, "tamanho": "38", "cor": "#d953d8", "base": False},
            {"ativo": True, "tamanho": "40", "cor": "#ffff00", "base": True},
            {"ativo": True, "tamanho": "42", "cor": "#334a46", "base": False},
        ]

        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        self.assertIsNone(ferramenta._molde_idx)
        self.assertEqual(canvas._selecionados, set())
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(5.0, 2.5))))
        self.assertEqual(ferramenta._molde_idx, 0)
        self.assertEqual(canvas._selecionados, {0})
        self.assertIsNone(ferramenta._ponto_idx)
        self.assertEqual(dialog.cmb_ponto.currentText(), "1")
        self.assertEqual([dialog.tbl.item(row, 0).text() for row in range(dialog.tbl.rowCount())], ["36", "38", "40", "42"])
        self.assertEqual(dialog.tbl.item(2, 0).background().color().name().lower(), "#ffff00")

    def test_visualizacao_nao_propaga_um_ponto_para_o_contorno_todo(self):
        pontos_cfg = {
            "1": {
                "valores": {
                    "G": {"dx": 2.0, "dy": -1.0},
                }
            }
        }

        deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(pontos_cfg, "G", 4)

        self.assertEqual(deslocamentos, [(0.0, 0.0), (2.0, -1.0), (0.0, 0.0), (0.0, 0.0)])

    def test_canvas_mapeia_graduacao_de_ponto_principal_para_contorno_curvo_extraido(self):
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [
                (0.0, 0.0),
                (2.0, 0.4),
                (4.0, 0.8),
                (6.0, 0.4),
                (8.0, 0.0),
                (8.0, -4.0),
                (0.0, -4.0),
                (0.0, 0.0),
            ],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 4.0, "y": 0.8},
                {"x": 8.0, "y": 0.0},
                {"x": 8.0, "y": -4.0},
                {"x": 0.0, "y": -4.0},
            ],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "1": {
                        "indice": 1,
                        "numero": 2,
                        "ponto": (4.0, 0.8),
                        "valores": {
                            "P": {"dx": 0.0, "dy": -1.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 0.0, "dy": 1.0},
                        },
                    }
                }
            },
        }
        base = [QPointF(x, y) for x, y in molde["pontos"][:-1]]

        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)

        self.assertEqual([nome for nome, _cor, _pontos in contornos], ["P", "G"])
        contorno_p = next(pontos for nome, _cor, pontos in contornos if nome == "P")
        contorno_g = next(pontos for nome, _cor, pontos in contornos if nome == "G")
        self.assertEqual(contorno_p[2], QPointF(4.0, -0.2))
        self.assertEqual(contorno_g[2], QPointF(4.0, 1.8))

    def test_canvas_mapeia_graduacao_antiga_sem_coordenada_para_ponto_principal(self):
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [
                (0.0, 0.0),
                (2.0, 0.4),
                (4.0, 0.8),
                (6.0, 0.4),
                (8.0, 0.0),
                (8.0, -4.0),
                (0.0, -4.0),
                (0.0, 0.0),
            ],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 4.0, "y": 0.8},
                {"x": 8.0, "y": 0.0},
                {"x": 8.0, "y": -4.0},
                {"x": 0.0, "y": -4.0},
            ],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "1": {
                        "indice": 1,
                        "numero": 2,
                        "valores": {
                            "P": {"dx": 0.0, "dy": -1.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 0.0, "dy": 1.0},
                        },
                    }
                }
            },
        }
        base = [QPointF(x, y) for x, y in molde["pontos"][:-1]]

        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)

        contorno_g = next(pontos for nome, _cor, pontos in contornos if nome == "G")
        self.assertEqual(contorno_g[2], QPointF(4.0, 1.8))

    def test_ctrl_click_graduar_varios_pontos_sem_fechar_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        ev_p1 = _FakeMouseEvent(QPointF(0.0, 0.0))
        ev_p2 = _FakeMouseEvent(QPointF(10.0, 0.0), modifiers=Qt.ControlModifier)
        self.assertTrue(ferramenta.on_mouse_press(canvas, ev_p1))
        self.assertTrue(ferramenta.on_mouse_press(canvas, ev_p2))
        dialog.sp_incremento.setValue(1.0)
        dialog.btn_dir.click()
        ferramenta.aplicar_dialog(canvas)

        pontos = canvas.cena.elementos[0]["graduacao_tabela"]["pontos"]
        self.assertEqual(set(pontos.keys()), {"0", "1"})
        self.assertEqual(pontos["0"]["valores"]["P"], {"dx": -1.0, "dy": 0.0})
        self.assertEqual(pontos["1"]["valores"]["G"], {"dx": 1.0, "dy": 0.0})
        self.assertTrue(dialog.isVisible())
        self.assertEqual(ferramenta._pontos_selecionados, {0, 1})

    def test_ctrl_click_com_botao_direito_acumula_ponto_sem_fechar_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(0.0, 0.0)))
        event = _FakeMouseEvent(QPointF(10.0, 0.0), modifiers=Qt.ControlModifier, button=Qt.RightButton)
        self.assertTrue(ferramenta.on_mouse_press(canvas, event))

        self.assertTrue(dialog.isVisible())
        self.assertEqual(ferramenta._pontos_selecionados, {0, 1})
        self.assertTrue(event.accepted)

    def test_clique_normal_substitui_pontos_selecionados_da_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(0.0, 0.0)))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 0.0), modifiers=Qt.ControlModifier))
        ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(10.0, 5.0)))

        self.assertEqual(ferramenta._pontos_selecionados, {2})
        self.assertEqual(ferramenta._ponto_idx, 2)

    def test_hover_realca_ponto_sem_alterar_selecao_da_tabela(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        selecionados_antes = set(ferramenta._pontos_selecionados)
        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(10.0, 0.02))))

        self.assertEqual(ferramenta._hover_ponto_idx, 1)
        self.assertEqual(ferramenta._pontos_selecionados, selecionados_antes)
        self.assertIsNone(ferramenta._ponto_idx)

    def test_hover_sai_quando_cursor_afasta_do_ponto(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(10.0, 0.02)))
        self.assertEqual(ferramenta._hover_ponto_idx, 1)
        ferramenta.on_mouse_move(canvas, _FakeMouseEvent(QPointF(5.0, 2.5)))

        self.assertIsNone(ferramenta._hover_ponto_idx)

    def test_clique_em_ponto_de_outro_molde_troca_alvo_da_tabela(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(
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
            }
        )
        canvas._indice_molde_em_ponto = lambda _pos: 0
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 0.0))))
        self.assertIsNone(ferramenta._ponto_idx)
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 0.0))))
        dialog.tbl.item(2, 1).setText("2")
        ferramenta.aplicar_dialog(canvas)

        self.assertEqual(ferramenta._molde_idx, 1)
        self.assertEqual(ferramenta._ponto_idx, 1)
        self.assertEqual(canvas._selecionados, {1})
        self.assertNotIn("graduacao_tabela", canvas.cena.elementos[0])
        ponto = canvas.cena.elementos[1]["graduacao_tabela"]["pontos"]["1"]
        self.assertEqual(ponto["ponto"], (110.0, 0.0))
        self.assertEqual(ponto["valores"]["G"], {"dx": 2.0, "dy": 0.0})

    def test_clique_no_corpo_de_outro_molde_troca_alvo_da_tabela(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "molde": True,
                "pontos": [(100.0, 0.0), (120.0, 0.0), (120.0, 10.0), (100.0, 10.0), (100.0, 0.0)],
                "controle_cantos": [(100.0, 0.0), (120.0, 0.0), (120.0, 10.0), (100.0, 10.0), (100.0, 0.0)],
                "graduacao_tamanhos": [
                    {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                    {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                    {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
                ],
            }
        )
        canvas._indice_molde_em_ponto = lambda _pos: 0
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 5.0))))

        self.assertEqual(ferramenta._molde_idx, 1)
        self.assertEqual(canvas._selecionados, {1})
        self.assertIsNone(ferramenta._ponto_idx)

    def test_clique_em_desenho_livre_nao_troca_molde_da_tabela(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "pontos": [(100.0, 0.0), (110.0, 0.0), (110.0, 5.0)],
                "controle_cantos": [(100.0, 0.0), (110.0, 0.0), (110.0, 5.0)],
            }
        )
        canvas._indice_molde_em_ponto = lambda _pos: 1
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 0.0))))

        self.assertEqual(ferramenta._molde_idx, 0)
        self.assertEqual(canvas._selecionados, {0})

    def test_copiar_graduacao_e_colar_em_ponto_de_outro_molde(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos.append(
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
            }
        )
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        ferramenta.selecionar_ponto(canvas, 1)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.tbl.item(0, 1).setText("-1")
        dialog.tbl.item(2, 2).setText("1.5")
        ferramenta.aplicar_dialog(canvas)

        self.assertEqual(dialog.btn_copiar_graduacao.text(), "Copiar graduação")
        dialog.btn_copiar_graduacao.click()
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeMouseEvent(QPointF(110.0, 0.0))))

        destino = canvas.cena.elementos[1]["graduacao_tabela"]["pontos"]["1"]["valores"]
        self.assertEqual(destino["P"], {"dx": -1.0, "dy": 0.0})
        self.assertEqual(destino["G"], {"dx": 0.0, "dy": 1.5})
        self.assertFalse(ferramenta._modo_copia_graduacao)

    def test_janela_fecha_quando_molde_sai_do_canvas(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaTabela()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        self.assertTrue(dialog.isVisible())

        canvas.cena.elementos.clear()
        canvas._selecionados.clear()
        canvas.elementos_alterados.emit()

        self.assertFalse(dialog.isVisible())
        self.assertIsNone(ferramenta._molde_idx)


if __name__ == "__main__":
    unittest.main()
