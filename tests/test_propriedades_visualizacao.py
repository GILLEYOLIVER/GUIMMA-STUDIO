from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    _bbox_visual_molde = None
    _converter_ponto_visual_entre_moldes = None
    PropriedadesMoldesDialog = None
else:
    from tools.propriedades_tool import PropriedadesMoldesDialog, _bbox_visual_molde, _converter_ponto_visual_entre_moldes


@unittest.skipIf(_bbox_visual_molde is None, "PySide6 não disponível neste ambiente")
class PropriedadesVisualizacaoTestCase(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
