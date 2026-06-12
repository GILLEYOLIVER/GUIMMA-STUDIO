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
    PropriedadesMoldesDialog = None
else:
    from tools.propriedades_tool import (
        FLAGS_VISUALIZACAO_MOLDE,
        MoldeRef,
        PropriedadesMoldesDialog,
        _bbox_visual_molde,
        _converter_ponto_visual_entre_moldes,
    )


@unittest.skipIf(_bbox_visual_molde is None, "PySide6 não disponível neste ambiente")
class PropriedadesVisualizacaoTestCase(unittest.TestCase):
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
