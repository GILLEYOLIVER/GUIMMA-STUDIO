from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    _bbox_visual_molde = None
    _converter_ponto_visual_entre_moldes = None
else:
    from tools.propriedades_tool import _bbox_visual_molde, _converter_ponto_visual_entre_moldes


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


if __name__ == "__main__":
    unittest.main()
