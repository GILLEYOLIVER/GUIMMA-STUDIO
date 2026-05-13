from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaAjusteAutomatico = None
else:
    from tools.ajuste_automatico_tool import Ferramenta as FerramentaAjusteAutomatico


@unittest.skipIf(FerramentaAjusteAutomatico is None, "PySide6 não disponível neste ambiente")
class AjusteAutomaticoToolTestCase(unittest.TestCase):
    def test_auto_ajuste_configura_nome_descricao_observacoes_e_fio(self):
        ferramenta = FerramentaAjusteAutomatico()
        molde = {
            "tipo": "polyline",
            "molde": True,
            "nome_molde": "K1",
            "descricao": "Frente",
            "observacoes": "Cortar uma vez",
            "pontos": [(0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
        }

        ferramenta._ajustar_molde(
            molde,
            {
                "ajustar_textos": True,
                "texto_min": 0.2,
                "texto_max": 1.0,
                "orientacao_manual": True,
                "orientacao": 90,
                "auto_fio": True,
                "fio_min": 0.5,
                "fio_max": 3.0,
                "centralizar": True,
            },
        )

        for chave in ("nome", "descricao", "observacoes"):
            self.assertIn(f"ponto_texto_{chave}", molde)
            self.assertEqual(molde[f"referencia_texto_{chave}"], "Livre")
            self.assertEqual(molde[f"alinhamento_texto_{chave}"], "Centro")
            self.assertEqual(molde[f"texto_{chave}_angulo"], 90.0)
            self.assertGreater(molde[f"texto_{chave}_altura_cm"], 0.0)

        self.assertEqual(molde["ponto_texto"], molde["ponto_texto_nome"])
        self.assertTrue(molde["mostrar_nome"])
        self.assertTrue(molde["visual_descricao"])
        self.assertTrue(molde["visual_observacoes"])
        self.assertIn("fio_origem", molde)
        self.assertIn("fio_fim", molde)
        self.assertEqual(molde["fio_angulo"], 90.0)
        self.assertTrue(molde["mostrar_fio"])


if __name__ == "__main__":
    unittest.main()
