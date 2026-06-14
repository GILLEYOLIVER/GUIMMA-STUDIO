from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.graduacao import aplicar_grade_graduacao_referencia_canvas, grade_graduacao_padrao


class GraduacaoPadraoTestCase(unittest.TestCase):
    def test_grade_padrao_portugues(self):
        grade, linhas = grade_graduacao_padrao("pt_BR")

        self.assertEqual(grade, "P-G(M)")
        self.assertEqual([linha["tamanho"] for linha in linhas], ["P", "M", "G"])
        self.assertEqual([linha["cor"] for linha in linhas], ["#ffff00", "#2b7cd3", "#ff8c00"])
        self.assertTrue(linhas[1]["base"])

    def test_grade_padrao_espanhol(self):
        grade, linhas = grade_graduacao_padrao("es_ES")

        self.assertEqual(grade, "S-L(M)")
        self.assertEqual([linha["tamanho"] for linha in linhas], ["S", "M", "L"])
        self.assertEqual([linha["cor"] for linha in linhas], ["#ffff00", "#2b7cd3", "#ff8c00"])
        self.assertTrue(linhas[1]["base"])

    def test_grade_referencia_mantem_primeira_grade_do_modelo_em_empate(self):
        grade_numerica = [
            {"ativo": True, "tamanho": "36", "cor": "#9678bd", "base": False},
            {"ativo": True, "tamanho": "38", "cor": "#c1d336", "base": False},
            {"ativo": True, "tamanho": "40", "cor": "#4f8a68", "base": True},
            {"ativo": True, "tamanho": "42", "cor": "#b58de8", "base": False},
            {"ativo": True, "tamanho": "44", "cor": "#c4b07c", "base": False},
            {"ativo": True, "tamanho": "46", "cor": "#b7d7a8", "base": False},
        ]
        canvas = SimpleNamespace(
            cena=SimpleNamespace(
                elementos=[
                    {
                        "molde": True,
                        "graduacao_grade_nome": "P-G(M)",
                        "graduacao_tamanhos": grade_graduacao_padrao("pt_BR")[1],
                        "graduacao_tamanhos_ativos": ["P", "M", "G"],
                    },
                    {
                        "molde": True,
                        "graduacao_grade_nome": "36-46(40)",
                        "graduacao_tamanhos": grade_numerica,
                        "graduacao_tamanhos_ativos": ["36", "38", "40", "42", "44", "46"],
                        "graduacao_tabela": {
                            "pontos": {
                                "0": {"valores": {"36": {"dx": -1.0, "dy": 0.0}, "46": {"dx": 1.0, "dy": 0.0}}}
                            }
                        },
                    },
                ]
            )
        )
        novo = {"molde": True}

        aplicar_grade_graduacao_referencia_canvas(novo, canvas, sobrescrever=True)

        self.assertEqual(novo["graduacao_grade_nome"], "P-G(M)")
        self.assertEqual([linha["tamanho"] for linha in novo["graduacao_tamanhos"]], ["P", "M", "G"])
        self.assertEqual(novo["graduacao_tamanhos_ativos"], ["P", "M", "G"])

    def test_grade_referencia_prefere_grade_predominante_do_arquivo(self):
        grade_numerica = [
            {"ativo": True, "tamanho": "36", "cor": "#9678bd", "base": False},
            {"ativo": True, "tamanho": "38", "cor": "#c1d336", "base": False},
            {"ativo": True, "tamanho": "40", "cor": "#4f8a68", "base": True},
            {"ativo": True, "tamanho": "42", "cor": "#b58de8", "base": False},
            {"ativo": True, "tamanho": "44", "cor": "#c4b07c", "base": False},
            {"ativo": True, "tamanho": "46", "cor": "#b7d7a8", "base": False},
        ]
        canvas = SimpleNamespace(
            cena=SimpleNamespace(
                elementos=[
                    {
                        "molde": True,
                        "graduacao_grade_nome": "P-G(M)",
                        "graduacao_tamanhos": grade_graduacao_padrao("pt_BR")[1],
                        "graduacao_tamanhos_ativos": ["P", "M", "G"],
                    },
                    {
                        "molde": True,
                        "graduacao_grade_nome": "36-46(40)",
                        "graduacao_tamanhos": grade_numerica,
                        "graduacao_tamanhos_ativos": ["36", "38", "40", "42", "44", "46"],
                    },
                    {
                        "molde": True,
                        "graduacao_grade_nome": "36-46(40)",
                        "graduacao_tamanhos": grade_numerica,
                        "graduacao_tamanhos_ativos": ["36", "38", "40", "42", "44", "46"],
                    },
                ]
            )
        )
        novo = {"molde": True}

        aplicar_grade_graduacao_referencia_canvas(novo, canvas, sobrescrever=True)

        self.assertEqual(novo["graduacao_grade_nome"], "36-46(40)")
        self.assertEqual([linha["tamanho"] for linha in novo["graduacao_tamanhos"]], ["36", "38", "40", "42", "44", "46"])


if __name__ == "__main__":
    unittest.main()
