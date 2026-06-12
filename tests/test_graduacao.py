from __future__ import annotations

import unittest

from core.graduacao import grade_graduacao_padrao


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


if __name__ == "__main__":
    unittest.main()
