from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    _bbox_visual_molde = None
    _converter_ponto_visual_entre_moldes = None
    FLAGS_VISUALIZACAO_MOLDE = ()
    MoldeRef = None
    NumeroLimpoDoubleSpinBox = None
    PreviewMoldeWidget = None
    PropriedadesMoldesDialog = None
    QApplication = None
    QComboBox = None
    QLabel = None
    QLineEdit = None
    QPointF = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit

    from tools.propriedades_tool import (
        FLAGS_VISUALIZACAO_MOLDE,
        MoldeRef,
        NumeroLimpoDoubleSpinBox,
        PreviewMoldeWidget,
        PropriedadesMoldesDialog,
        _bbox_visual_molde,
        _converter_ponto_visual_entre_moldes,
    )


@unittest.skipIf(_bbox_visual_molde is None, "PySide6 não disponível neste ambiente")
class PropriedadesVisualizacaoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    class _CheckFake:
        def __init__(self, marcado: bool = False):
            self._marcado = bool(marcado)

        def isChecked(self) -> bool:
            return self._marcado

        def setChecked(self, marcado: bool):
            self._marcado = bool(marcado)

    def test_converte_posicao_visual_proporcionalmente_entre_moldes(self):
        origem = {
            "pontos": [(100.0, 200.0), (300.0, 200.0), (300.0, 300.0), (100.0, 300.0)],
        }
        destino = {
            "pontos": [(10.0, 20.0), (30.0, 20.0), (30.0, 60.0), (10.0, 60.0)],
        }

        convertido = _converter_ponto_visual_entre_moldes(
            [150.0, 225.0],
            _bbox_visual_molde(origem),
            _bbox_visual_molde(destino),
        )

        self.assertEqual(convertido, [15.0, 30.0])

    def test_mantem_deslocamento_externo_do_texto_ao_aplicar_todos(self):
        origem = {
            "pontos": [(100.0, 200.0), (300.0, 200.0), (300.0, 300.0), (100.0, 300.0)],
        }
        destino = {
            "pontos": [(10.0, 20.0), (30.0, 20.0), (30.0, 60.0), (10.0, 60.0)],
        }

        convertido = _converter_ponto_visual_entre_moldes(
            [50.0, 350.0],
            _bbox_visual_molde(origem),
            _bbox_visual_molde(destino),
        )

        self.assertEqual(convertido, [5.0, 80.0])

    def test_config_visual_numeros_nao_forca_exibicao(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.cmb_elementos_molde = SimpleNamespace(currentText=lambda: "Números")
        dialog.ed_altura_texto = SimpleNamespace(value=lambda: 0.42)
        molde = {"mostrar_numeros": False}

        PropriedadesMoldesDialog._salvar_config_visual_molde(dialog, molde)

        self.assertFalse(molde["mostrar_numeros"])
        self.assertEqual(molde["numero_altura_cm"], 0.42)

    def test_config_visual_numeros_aceita_rotulo_sem_acento(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.cmb_elementos_molde = SimpleNamespace(currentText=lambda: "Numeros")
        dialog.ed_altura_texto = SimpleNamespace(value=lambda: 1.35)
        molde = {"mostrar_numeros": True}

        PropriedadesMoldesDialog._salvar_config_visual_molde(dialog, molde)

        self.assertEqual(molde["numero_altura_cm"], 1.35)

    def test_config_visual_texto_e_fio_nao_forcam_checkbox_ligada(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.ed_altura_texto = SimpleNamespace(value=lambda: 2.4)
        dialog.ed_angulo_texto = SimpleNamespace(value=lambda: 15.0)
        dialog.ed_espaco_linhas = SimpleNamespace(value=lambda: 0.5)
        dialog.ed_referencia = SimpleNamespace(currentText=lambda: "Livre")
        dialog.ed_alinhamento = SimpleNamespace(currentText=lambda: "Direita")
        dialog.cmb_elementos_molde = SimpleNamespace(currentText=lambda: "Nome")
        molde = {"mostrar_nome": False}

        PropriedadesMoldesDialog._salvar_config_visual_molde(dialog, molde)

        self.assertFalse(molde["mostrar_nome"])
        self.assertEqual(molde["texto_nome_altura_cm"], 2.4)
        self.assertEqual(molde["texto_nome_angulo"], 15.0)
        self.assertEqual(molde["alinhamento_texto_nome"], "Direita")

        dialog.cmb_elementos_molde = SimpleNamespace(currentText=lambda: "Fio")
        molde_fio = {"mostrar_fio": False}

        PropriedadesMoldesDialog._salvar_config_visual_molde(dialog, molde_fio)

        self.assertFalse(molde_fio["mostrar_fio"])

    def test_aplicar_visualizacao_em_lote_nao_forca_texto_ou_fio_visivel(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog._salvar_margens_no_molde = lambda *args, **kwargs: None
        molde = {"mostrar_nome": False, "mostrar_fio": False}
        dados = {
            "bbox_origem": None,
            "cor": "#ffffff",
            "margens": {},
            "textos": {},
            "fio": {},
            "numeros": {},
            "visual_observacoes": False,
            "mostrar_nome": False,
            "mostrar_fio": False,
            "chave_visual": "nome",
            "texto_altura_cm": 3.2,
            "texto_angulo": 5.0,
            "espaco_linhas": 0.33,
            "referencia_texto": "Livre",
            "alinhamento_texto": "Centro",
        }

        PropriedadesMoldesDialog._aplicar_visualizacao_em_molde(dialog, molde, dados)

        self.assertFalse(molde["mostrar_nome"])
        self.assertFalse(molde["mostrar_fio"])
        self.assertEqual(molde["texto_nome_altura_cm"], 3.2)

    def test_carregar_elemento_visual_preenche_campos_do_elemento_correto(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.cmb_elementos_molde = QComboBox()
        dialog.cmb_elementos_molde.addItems(["Nenhum", "Nome", "Descrição", "Observações", "Fio", "Números"])
        dialog.ed_referencia = QComboBox()
        dialog.ed_referencia.addItems(["Livre", "Centro centro", "Abaixo direita"])
        dialog.ed_alinhamento = QComboBox()
        dialog.ed_alinhamento.addItems(["Esquerda", "Centro", "Direita"])
        dialog.ed_angulo_texto = NumeroLimpoDoubleSpinBox()
        dialog.ed_altura_texto = NumeroLimpoDoubleSpinBox()
        dialog.ed_espaco_linhas = NumeroLimpoDoubleSpinBox()
        dialog.ed_nome_visualizacao = QLineEdit()
        dialog.lbl_nome_visualizacao = QLabel()
        molde = {
            "nome_molde": "K2",
            "descricao": "DESC",
            "texto_nome_altura_cm": 9.0,
            "texto_descricao_altura_cm": 1.25,
            "texto_descricao_angulo": 12.0,
            "espaco_linhas_texto_descricao": 0.75,
            "referencia_texto_descricao": "Abaixo direita",
            "alinhamento_texto_descricao": "Direita",
        }

        PropriedadesMoldesDialog._carregar_controles_visual_elemento(dialog, molde, "Descrição")

        self.assertEqual(dialog.ed_nome_visualizacao.text(), "DESC")
        self.assertEqual(dialog.ed_referencia.currentText(), "Abaixo direita")
        self.assertEqual(dialog.ed_alinhamento.currentText(), "Direita")
        self.assertEqual(dialog.ed_altura_texto.value(), 1.25)
        self.assertEqual(dialog.ed_angulo_texto.value(), 12.0)
        self.assertEqual(dialog.ed_espaco_linhas.value(), 0.75)

    def test_sincronizar_graduacao_propriedades_fica_no_rascunho(self):
        class _SignalFake:
            def __init__(self):
                self.emissoes = 0

            def emit(self):
                self.emissoes += 1

        class _CanvasFake:
            def __init__(self):
                self.elementos_alterados = _SignalFake()
                self.updates = 0

            def update(self):
                self.updates += 1

        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog._suspender_auto_aplicar = False
        dialog.canvas = _CanvasFake()
        dialog.cmb_grade_tamanhos = QComboBox()
        dialog.cmb_grade_tamanhos.addItem("P-G(M)")
        dialog._graduacao_linhas = [
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
        ]
        rascunho = {}
        real = {}
        dialog._moldes_alvo_graduacao = lambda: [rascunho]
        dialog._moldes_reais_alvo_graduacao = lambda: [real]
        dialog._sincronizar_valores_graduacao_tamanhos = lambda *args, **kwargs: None

        PropriedadesMoldesDialog._sincronizar_gradacao_no_molde(dialog)

        self.assertEqual(rascunho["graduacao_grade_nome"], "P-G(M)")
        self.assertIn("graduacao_tamanhos", rascunho)
        self.assertNotIn("graduacao_grade_nome", real)
        self.assertEqual(dialog.canvas.elementos_alterados.emissoes, 0)
        self.assertEqual(dialog.canvas.updates, 0)

    def test_flags_visualizacao_sao_lidos_e_aplicados_no_molde(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        for attr, _chave, padrao in FLAGS_VISUALIZACAO_MOLDE:
            setattr(dialog, attr, self._CheckFake(not padrao))

        flags = PropriedadesMoldesDialog._ler_flags_visualizacao_formulario(dialog)
        molde = {}
        PropriedadesMoldesDialog._aplicar_flags_visualizacao_molde(molde, flags)

        for _attr, chave, padrao in FLAGS_VISUALIZACAO_MOLDE:
            self.assertEqual(flags[chave], not padrao)
            self.assertEqual(molde[chave], not padrao)

    def test_preencher_flags_visualizacao_respeita_defaults_antigos(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        checks = {}
        for attr, _chave, _padrao in FLAGS_VISUALIZACAO_MOLDE:
            checks[attr] = self._CheckFake(False)
            setattr(dialog, attr, checks[attr])

        PropriedadesMoldesDialog._preencher_flags_visualizacao(dialog, {"mostrar_graduacao": False, "visual_tecido": True})

        self.assertFalse(checks["chk_graduacao"].isChecked())
        self.assertTrue(checks["chk_tecido_visual"].isChecked())
        self.assertTrue(checks["chk_mostrar_nome"].isChecked())
        self.assertTrue(checks["chk_pique"].isChecked())
        self.assertFalse(checks["chk_modelo"].isChecked())

    def test_preview_graduacao_respeita_checkbox_visualizacao(self):
        from canvas.visualizacao import VisualizacaoCanvas

        class _PainterFake:
            def __init__(self):
                self.paths = 0

            def save(self):
                pass

            def restore(self):
                pass

            def setPen(self, _pen):
                pass

            def drawPath(self, _path):
                self.paths += 1

        original = VisualizacaoCanvas._contornos_graduacao_tabela
        VisualizacaoCanvas._contornos_graduacao_tabela = staticmethod(
            lambda _molde, _base: [("G", "#ffcc00", [QPointF(0.0, 0.0), QPointF(10.0, 0.0)])]
        )
        try:
            preview = PreviewMoldeWidget.__new__(PreviewMoldeWidget)
            base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0)]
            mapear = lambda ponto: QPointF(ponto)

            preview._molde = {"mostrar_graduacao": False}
            painter = _PainterFake()
            PreviewMoldeWidget._desenhar_graduacao(preview, painter, base, mapear)
            self.assertEqual(painter.paths, 0)

            preview._molde = {"mostrar_graduacao": True}
            painter = _PainterFake()
            PreviewMoldeWidget._desenhar_graduacao(preview, painter, base, mapear)
            self.assertEqual(painter.paths, 1)
        finally:
            VisualizacaoCanvas._contornos_graduacao_tabela = staticmethod(original)

    def test_novo_tamanho_usa_proporcao_da_graduacao_existente(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        molde = {
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "valores": {
                            "P": {"dx": -1.0, "dy": 1.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 1.0, "dy": -1.0},
                        }
                    }
                }
            },
            "graduacao_pontos": {
                "0": {
                    "valores": {
                        "P": {"dx": -1.0, "dy": 1.0},
                        "M": {"dx": 0.0, "dy": 0.0},
                        "G": {"dx": 1.0, "dy": -1.0},
                    }
                }
            },
        }
        novas_linhas = [
            {"ativo": True, "tamanho": "PP", "base": False},
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
            {"ativo": True, "tamanho": "GG", "base": False},
        ]

        PropriedadesMoldesDialog._sincronizar_valores_graduacao_tamanhos(dialog, molde, novas_linhas)

        valores = molde["graduacao_tabela"]["pontos"]["0"]["valores"]
        self.assertEqual(valores["PP"], {"dx": -2.0, "dy": 2.0})
        self.assertEqual(valores["GG"], {"dx": 2.0, "dy": -2.0})
        self.assertEqual(molde["graduacao_pontos"]["0"]["valores"]["PP"], {"dx": -2.0, "dy": 2.0})

    def test_trocar_grade_mantem_graduacao_por_posicao(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        linhas_antigas = [
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
        ]
        molde = {
            "graduacao_tamanhos": linhas_antigas,
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "valores": {
                            "P": {"dx": -1.0, "dy": 1.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 1.0, "dy": -1.0},
                        }
                    }
                }
            },
        }
        novas_linhas = [
            {"ativo": True, "tamanho": "S", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "L", "base": False},
        ]

        PropriedadesMoldesDialog._sincronizar_valores_graduacao_tamanhos(
            dialog,
            molde,
            novas_linhas,
            linhas_antigas=linhas_antigas,
        )

        valores = molde["graduacao_tabela"]["pontos"]["0"]["valores"]
        self.assertEqual(valores["S"], {"dx": -1.0, "dy": 1.0})
        self.assertEqual(valores["L"], {"dx": 1.0, "dy": -1.0})

    def test_aplicar_grade_preserva_cores_dos_tamanhos_existentes(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog._graduacao_linhas = [
            {"ativo": True, "tamanho": "P", "cor": "#c87575", "base": False},
            {"ativo": True, "tamanho": "M", "cor": "#d60b0b", "base": True},
            {"ativo": True, "tamanho": "G", "cor": "#5d95b7", "base": False},
        ]
        dialog._renderizar_tabela_graduacao = lambda: None
        dialog._sincronizar_gradacao_no_molde = lambda: None
        dialog._gerar_cor_aleatoria = lambda: "#123456"

        PropriedadesMoldesDialog._aplicar_grade_tamanhos(dialog, "P-G(M)")

        cores = {linha["tamanho"]: linha["cor"] for linha in dialog._graduacao_linhas}
        self.assertEqual(cores, {"P": "#c87575", "M": "#d60b0b", "G": "#5d95b7"})

    def test_propriedades_define_conflito_quando_grade_difere_do_modelo(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        base = {
            "graduacao_grade_nome": "P-G(M)",
            "graduacao_tamanhos": [
                {"tamanho": "P"},
                {"tamanho": "M"},
                {"tamanho": "G"},
            ],
        }
        diferente = {
            "graduacao_grade_nome": "36-44(40)",
            "graduacao_tamanhos": [
                {"tamanho": "36"},
                {"tamanho": "40"},
                {"tamanho": "44"},
            ],
        }
        igual = {
            "graduacao_grade_nome": "P-G(M)",
            "graduacao_tamanhos": [
                {"tamanho": "P"},
                {"tamanho": "M"},
                {"tamanho": "G"},
            ],
        }
        dialog._refs = [
            MoldeRef(indice=0, nome="K1", dados=base),
            MoldeRef(indice=1, nome="K2", dados=diferente),
            MoldeRef(indice=2, nome="K3", dados=igual),
        ]

        PropriedadesMoldesDialog._atualizar_conflitos_grade_modelo(dialog)

        self.assertFalse(base["conflito_grade_modelo"])
        self.assertTrue(diferente["conflito_grade_modelo"])
        self.assertEqual(diferente["grade_modelo_referencia"], "P-G(M)|P/M/G")
        self.assertFalse(igual["conflito_grade_modelo"])
        self.assertEqual(diferente["graduacao_grade_nome"], "36-44(40)")


if __name__ == "__main__":
    unittest.main()
