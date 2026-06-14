from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.transformar_em_elementos_tool import Ferramenta


class TransformarEmElementosToolTestCase(unittest.TestCase):
    def test_converte_molde_e_vinculados_em_polylines_comuns(self):
        canvas = SimpleNamespace(
            cena=SimpleNamespace(
                elementos=[
                    {
                        "id": "molde-1",
                        "tipo": "polyline",
                        "molde": True,
                        "molde_id": "m1",
                        "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                        "cor": "#ff00aa",
                        "estilo": "solid",
                        "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                        "pontos_graduacao": [{"x": 0.0, "y": 0.0}],
                        "graduacao_tabela": {"pontos": {"0": {"valores": {}}}},
                        "graduacao_tamanhos": [{"tamanho": "M", "base": True}],
                        "mostrar_fio": True,
                        "fio_origem": (1.0, 1.0),
                        "fio_fim": (9.0, 1.0),
                        "nome_molde": "Frente",
                        "subtipo_audaces": "contorno",
                        "metadados": {"molde_id": "m1", "subtipo_audaces": "contorno"},
                    },
                    {
                        "tipo": "polyline",
                        "molde": False,
                        "pontos": [(1.0, 1.0), (9.0, 1.0)],
                        "subtipo_audaces": "costura",
                        "molde_linha_vinculada": True,
                        "molde_id": "m1",
                        "costura_de_molde_id": "m1",
                        "costura_segmentos": [0],
                        "tipo_costura": "Costura",
                        "posicao_costura": "Selecionar",
                        "metadados": {
                            "tipo_ferramenta": "costura",
                            "subtipo_audaces": "costura",
                            "molde_id": "m1",
                            "costura_de_molde_id": "m1",
                        },
                    },
                    {
                        "tipo": "polyline",
                        "molde": False,
                        "pontos": [(2.0, 2.0), (8.0, 2.0)],
                        "subtipo_audaces": "linha_interna",
                        "molde_linha_vinculada": True,
                        "molde_id": "m1",
                    },
                    {
                        "tipo": "polyline",
                        "molde": False,
                        "pontos": [(20.0, 0.0), (30.0, 0.0)],
                        "molde_id": "outro",
                    },
                ]
            )
        )

        indices = Ferramenta.converter_molde_em_linhas(canvas, 0)

        self.assertEqual(indices, [0, 1, 2])
        principal, costura, interna, outro = canvas.cena.elementos
        self.assertFalse(principal["molde"])
        self.assertEqual(principal["tipo"], "polyline")
        self.assertEqual(principal["pontos"][1], (10.0, 0.0))
        self.assertEqual(principal["cor"], "#ff00aa")
        for chave in (
            "molde_id",
            "controle_cantos",
            "pontos_graduacao",
            "graduacao_tabela",
            "graduacao_tamanhos",
            "fio_origem",
            "fio_fim",
            "nome_molde",
            "subtipo_audaces",
            "metadados",
        ):
            self.assertNotIn(chave, principal)

        for elemento in (costura, interna):
            self.assertFalse(elemento["molde"])
            self.assertTrue(elemento["selecionavel_individual"])
            self.assertNotIn("molde_id", elemento)
            self.assertNotIn("costura_de_molde_id", elemento)
            self.assertNotIn("molde_linha_vinculada", elemento)
            self.assertNotIn("subtipo_audaces", elemento)
            self.assertNotIn("tipo_costura", elemento)
            self.assertNotIn("posicao_costura", elemento)
        self.assertEqual(outro["molde_id"], "outro")

    def test_ribbon_mostra_converter_em_linha_em_producao(self):
        mapa = json.loads(
            (Path(__file__).resolve().parents[1] / "ui" / "tool_pages_map.json").read_text(encoding="utf-8")
        )
        producao = next(tab for tab in mapa["tabs"] if tab["id"] == "producao")
        complementar = next(group for group in producao["groups"] if group["title"] == "Complementar moldes")

        self.assertIn("transformar_em_elementos", complementar["tools"])
        self.assertEqual(mapa["tools"]["transformar_em_elementos"]["title"], "Converter em linha")


if __name__ == "__main__":
    unittest.main()
