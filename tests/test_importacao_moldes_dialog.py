from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    GuimmaStudioMainWindow = None
else:
    from ui.janela_principal import GuimmaStudioMainWindow


@unittest.skipIf(GuimmaStudioMainWindow is None, "PySide6 nao disponivel neste ambiente")
class ImportacaoMoldesDialogTestCase(unittest.TestCase):
    def test_preparar_elementos_aplica_unidade_e_metadados(self):
        elementos = [{"tipo": "polyline", "pontos": [(10.0, 20.0), (30.0, 40.0)], "cor": "#ff5a00"}]
        opcoes = {
            "unidade": "mm",
            "origem": "Gerber",
            "tipo_filtro": "Arquivos DXF (*.dxf)",
            "importar_linha_costura": True,
            "usar_contorno_corte_como_base": False,
        }

        preparados = GuimmaStudioMainWindow._preparar_elementos_importacao_moldes(
            GuimmaStudioMainWindow,
            elementos,
            opcoes,
        )

        self.assertEqual(preparados[0]["pontos"], [(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(preparados[0]["unidade_origem"], "mm")
        self.assertEqual(preparados[0]["origem_importacao"], "Gerber")
        self.assertEqual(preparados[0]["subtipo_importacao"], "costura")
        self.assertTrue(preparados[0]["importar_linha_costura"])
        self.assertFalse(preparados[0]["usar_contorno_corte_como_base"])
        self.assertEqual(elementos[0]["pontos"], [(10.0, 20.0), (30.0, 40.0)])

    def test_preparar_elementos_converte_polegada_para_centimetro(self):
        elementos = [{"tipo": "polyline", "pontos": [(1, 2)]}]
        opcoes = {"unidade": "pol", "origem": "AutoCad"}

        preparados = GuimmaStudioMainWindow._preparar_elementos_importacao_moldes(
            GuimmaStudioMainWindow,
            elementos,
            opcoes,
        )

        self.assertEqual(preparados[0]["pontos"], [(2.54, 5.08)])
        self.assertEqual(preparados[0]["subtipo_importacao"], "contorno_corte")

    def test_origem_inicial_do_menu_sobrescreve_preferencia_salva(self):
        fake = SimpleNamespace(
            projeto_atual=SimpleNamespace(
                preferencias_usuario={
                    "importacao_moldes": {
                        "unidade": "cm",
                        "origem": "Gerber",
                    }
                }
            )
        )
        fake._origens_importacao_moldes = lambda: GuimmaStudioMainWindow._origens_importacao_moldes(fake)

        opcoes = GuimmaStudioMainWindow._opcoes_importacao_moldes_padrao(fake, origem_inicial="Lectra")

        self.assertEqual(opcoes["origem"], "Lectra")


if __name__ == "__main__":
    unittest.main()
