from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaAjusteAutomatico = None
else:
    from tools.ajuste_automatico_tool import Ferramenta as FerramentaAjusteAutomatico


@unittest.skipIf(FerramentaAjusteAutomatico is None, "PySide6 não disponível neste ambiente")
class AjusteAutomaticoToolTestCase(unittest.TestCase):
    def _opcoes_padrao(self) -> dict:
        return {
            "ajustar_textos": True,
            "texto_min": 0.2,
            "texto_max": 1.0,
            "orientacao_manual": True,
            "orientacao": 90,
            "ajustar_numeros": True,
            "numero_min": 0.2,
            "numero_max": 0.8,
            "auto_fio": True,
            "fio_min": 0.5,
            "fio_max": 3.0,
            "centralizar": True,
        }

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

        ferramenta._ajustar_molde(molde, self._opcoes_padrao())

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
        self.assertTrue(molde["mostrar_numeros"])
        self.assertGreaterEqual(molde["numero_altura_cm"], 0.2)
        self.assertLessEqual(molde["numero_altura_cm"], 0.8)

    def test_sem_molde_selecionado_aplica_em_todos_os_moldes(self):
        ferramenta = FerramentaAjusteAutomatico()
        canvas = SimpleNamespace(
            cena=SimpleNamespace(
                elementos=[
                    {
                        "tipo": "polyline",
                        "molde": True,
                        "nome_molde": "K1",
                        "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0), (0.0, 0.0)],
                    },
                    {
                        "tipo": "polyline",
                        "molde": True,
                        "nome_molde": "K2",
                        "pontos": [(20.0, 0.0), (30.0, 0.0), (30.0, 6.0), (20.0, 6.0), (20.0, 0.0)],
                    },
                    {
                        "tipo": "linha",
                        "pontos": [(0.0, 0.0), (1.0, 1.0)],
                    },
                ]
            ),
            _selecionados=set(),
            historico=0,
            atualizado=False,
        )
        canvas._registrar_historico = lambda: setattr(canvas, "historico", canvas.historico + 1)
        canvas.update = lambda: setattr(canvas, "atualizado", True)

        quantidade = ferramenta.aplicar(canvas, self._opcoes_padrao())

        self.assertEqual(quantidade, 2)
        self.assertTrue(canvas.atualizado)
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.cena.elementos[0]["mostrar_numeros"])
        self.assertTrue(canvas.cena.elementos[1]["mostrar_numeros"])
        self.assertNotIn("mostrar_numeros", canvas.cena.elementos[2])


if __name__ == "__main__":
    unittest.main()
