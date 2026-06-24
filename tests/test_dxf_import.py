from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from formats import dxf_import as dxf_import_module
from formats.dxf_import import detectar_tamanhos_matriz_dxf, importar_dxf_para_elementos


def _dxf_entities(entidades: list[str]) -> str:
    return "\n".join(["0", "SECTION", "2", "ENTITIES", *entidades, "0", "ENDSEC", "0", "EOF"])


def _line(x1, y1, x2, y2) -> list[str]:
    return ["0", "LINE", "10", str(x1), "20", str(y1), "11", str(x2), "21", str(y2)]


def _contorno_linhas(pontos: list[tuple[float, float]]) -> list[str]:
    entidades: list[str] = []
    for (x1, y1), (x2, y2) in zip(pontos, pontos[1:]):
        entidades.extend(_line(x1, y1, x2, y2))
    return entidades


def _text(texto, x, y) -> list[str]:
    return ["0", "TEXT", "8", "0", "10", str(x), "20", str(y), "40", "1", "1", str(texto)]


class DxfImportTestCase(unittest.TestCase):
    def _importar_texto(
        self,
        texto: str,
        *,
        agrupar_matriz: bool = False,
        tamanho_base: str = "P",
        grade_tamanhos: list[dict] | None = None,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "molde.dxf"
            caminho.write_text(texto, encoding="utf-8")
            return importar_dxf_para_elementos(
                str(caminho),
                agrupar_matriz=agrupar_matriz,
                tamanho_base=tamanho_base,
                grade_tamanhos=grade_tamanhos,
            )

    def test_linhas_conectadas_viram_polyline_continua_sem_micro_vertices_colineares(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 5, 0),
                *_line(5, 0, 10, 0),
                *_line(10, 0, 10, 4),
                *_line(10, 4, 0, 4),
                *_line(0, 4, 0, 0),
            ]
        )

        elementos = self._importar_texto(texto)

        self.assertEqual(len(elementos), 1)
        self.assertEqual(
            elementos[0]["pontos"],
            [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0), (0.0, 0.0)],
        )
        self.assertTrue(elementos[0]["fechado"])

    def test_lwpolyline_fechada_nao_e_quebrada_em_segmentos(self):
        texto = _dxf_entities(
            [
                "0",
                "LWPOLYLINE",
                "70",
                "1",
                "10",
                "0",
                "20",
                "0",
                "10",
                "4",
                "20",
                "0",
                "10",
                "4",
                "20",
                "3",
                "10",
                "0",
                "20",
                "3",
            ]
        )

        elementos = self._importar_texto(texto)

        self.assertEqual(len(elementos), 1)
        self.assertEqual(len(elementos[0]["pontos"]), 5)
        self.assertEqual(elementos[0]["pontos"][0], elementos[0]["pontos"][-1])

    def test_matriz_com_textos_gera_molde_base_p_graduado(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("FRENTE 1X", 26, 2),
            ]
        )

        elementos = self._importar_texto(texto, agrupar_matriz=True)

        self.assertEqual(len(elementos), 1)
        molde = elementos[0]
        self.assertTrue(molde.get("molde"))
        self.assertEqual(molde.get("nome_molde"), "FRENTE 1X")
        self.assertEqual(molde.get("tamanho_base"), "P")
        self.assertTrue(molde.get("mostrar_controles"))
        self.assertTrue(molde.get("mostrar_controles_permanente"))
        self.assertTrue(molde.get("molde_pronto"))
        self.assertTrue(molde.get("graduacao_preferir_tabela_dxdy"))
        self.assertFalse(molde.get("graduacao_renderizar_por_tabela_derivada"))
        self.assertTrue(molde.get("mostrar_fio"))
        self.assertIn("fio_origem", molde)
        self.assertIn("fio_fim", molde)
        self.assertFalse(molde.get("mostrar_numeros"))
        self.assertFalse(molde.get("graduacao_preservar_cores_importadas"))
        self.assertTrue(molde.get("graduacao_cores_sinteticas"))
        self.assertEqual(molde["metadados"].get("graduacao_cores_origem"), "sintetica_guimma")
        self.assertEqual([g["tamanho"] for g in molde.get("graduacao_contornos_importados", [])], ["PP", "P"])
        self.assertEqual(molde["pontos"], [(20.0, 0.0), (32.0, 0.0), (32.0, 6.0), (20.0, 6.0), (20.0, 0.0)])
        pontos_grade = molde["graduacao_tabela"]["pontos"]
        self.assertEqual(len(pontos_grade), 4)
        self.assertEqual(pontos_grade["0"]["valores"]["P"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos_grade["0"]["valores"]["PP"], {"dx": 1.0, "dy": 0.5})
        self.assertEqual(molde["graduacao_pontos"], pontos_grade)

    def test_matriz_agrupada_usa_tamanho_base_informado(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("FRENTE 1X", 26, 2),
                *_line(40, 0, 54, 0),
                *_line(54, 0, 54, 7),
                *_line(54, 7, 40, 7),
                *_line(40, 7, 40, 0),
                *_text("FRENTE 1X", 47, 2),
            ]
        )

        elementos = self._importar_texto(texto, agrupar_matriz=True, tamanho_base="M")

        molde = elementos[0]
        self.assertEqual(molde.get("tamanho_base"), "M")
        self.assertEqual(molde.get("graduacao_grade_nome"), "P-M-G(M)")
        self.assertEqual([g["tamanho"] for g in molde.get("graduacao_contornos_importados", [])], ["P", "M", "G"])
        self.assertEqual(molde["pontos"], [(20.0, 0.0), (32.0, 0.0), (32.0, 6.0), (20.0, 6.0), (20.0, 0.0)])
        pontos_grade = molde["graduacao_tabela"]["pontos"]
        self.assertEqual(pontos_grade["0"]["valores"]["M"], {"dx": 0.0, "dy": 0.0})
        self.assertEqual(pontos_grade["0"]["valores"]["P"], {"dx": 1.0, "dy": 0.5})
        self.assertEqual(pontos_grade["0"]["valores"]["G"], {"dx": -1.0, "dy": -0.5})

    def test_matriz_agrupada_normaliza_grade_global_e_extrapola_tamanho_faltante(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("FRENTE 1X", 26, 2),
                *_line(40, 0, 54, 0),
                *_line(54, 0, 54, 7),
                *_line(54, 7, 40, 7),
                *_line(40, 7, 40, 0),
                *_text("FRENTE 1X", 47, 2),
                *_line(0, 20, 10, 20),
                *_line(10, 20, 10, 25),
                *_line(10, 25, 0, 25),
                *_line(0, 25, 0, 20),
                *_text("COSTAS 1X", 5, 22),
                *_line(20, 20, 32, 20),
                *_line(32, 20, 32, 26),
                *_line(32, 26, 20, 26),
                *_line(20, 26, 20, 20),
                *_text("COSTAS 1X", 26, 22),
            ]
        )

        elementos = self._importar_texto(texto, agrupar_matriz=True, tamanho_base="M")

        por_nome = {el["nome_molde"]: el for el in elementos if el.get("molde")}
        self.assertEqual(
            [linha["tamanho"] for linha in por_nome["FRENTE 1X"]["graduacao_tamanhos"]],
            ["P", "M", "G"],
        )
        self.assertEqual(
            [linha["tamanho"] for linha in por_nome["COSTAS 1X"]["graduacao_tamanhos"]],
            ["P", "M", "G"],
        )
        costas_grade = por_nome["COSTAS 1X"]["graduacao_tabela"]["pontos"]
        self.assertEqual(costas_grade["0"]["valores"]["G"], {"dx": -1.0, "dy": -0.5})
        contorno_g = next(item for item in por_nome["COSTAS 1X"]["graduacao_contornos_importados"] if item["tamanho"] == "G")
        self.assertTrue(contorno_g["gerado_por_tabela_dxf"])

    def test_matriz_agrupada_preserva_controles_e_linha_auxiliar_da_base(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_line(3, 0, 5, 2),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_line(24, 0, 26, 2),
                *_line(26, 2, 28, 0),
                *_text("FRENTE 1X", 26, 2),
            ]
        )

        elementos = self._importar_texto(texto, agrupar_matriz=True)

        moldes = [el for el in elementos if el.get("molde")]
        auxiliares = [el for el in elementos if el.get("subtipo_audaces") == "linha_interna"]
        self.assertEqual(len(moldes), 1)
        self.assertEqual(len(auxiliares), 0)
        molde = moldes[0]
        linhas_base = molde["linhas_auxiliares_base"]
        self.assertEqual(len(linhas_base), 1)
        self.assertEqual(linhas_base[0]["pontos"], [(24.0, 0.0), (26.0, 2.0), (28.0, 0.0)])
        self.assertTrue(linhas_base[0]["aplicar_todos_tamanhos"])
        self.assertTrue(molde["mostrar_linhas_auxiliares"])
        self.assertEqual(molde["linhas_auxiliares_importadas"], 1)
        self.assertGreaterEqual(len(molde["controle_cantos"]), 4)
        self.assertEqual(len(molde["controle_cantos"]), len(molde["pontos_controle_principais"]))
        self.assertEqual(
            len(molde["controle_cantos"]),
            len(molde["graduacao_tabela"]["pontos"]),
        )

    def test_matriz_agrupada_converte_cruz_interna_em_pique_configurado(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_line(4.5, 2.5, 5.5, 2.5),
                *_line(5.0, 2.0, 5.0, 3.0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_line(25.4, 3.0, 26.6, 3.0),
                *_line(26.0, 2.4, 26.0, 3.6),
                *_text("FRENTE 1X", 26, 2),
            ]
        )

        molde = next(el for el in self._importar_texto(texto, agrupar_matriz=True) if el.get("molde"))

        self.assertEqual(molde.get("linhas_auxiliares_importadas"), 0)
        piques = molde.get("piques_config") or []
        self.assertEqual(len(piques), 1)
        self.assertEqual(piques[0]["tipo"], "M+ - marca +")
        self.assertFalse(piques[0]["sobre_contorno"])
        self.assertTrue(piques[0]["aplicar_todos_tamanhos"])
        self.assertEqual(len(piques[0]["segmentos"]), 2)

    def test_matriz_agrupada_separa_cantos_de_auxiliares_e_reduz_excesso(self):
        menor_topo = [(i * 0.5, 0.45 * math.sin(math.pi * i / 20.0)) for i in range(21)]
        menor = [*menor_topo, (10, 5), (0, 5), menor_topo[0]]
        base_topo = [(20 + i * 0.6, 0.55 * math.sin(math.pi * i / 20.0)) for i in range(21)]
        base = [*base_topo, (32, 6), (20, 6), base_topo[0]]
        texto = _dxf_entities(
            [
                *_contorno_linhas(menor),
                *_text("FRENTE 1X", 5, 2),
                *_contorno_linhas(base),
                *_text("FRENTE 1X", 26, 2),
            ]
        )

        molde = self._importar_texto(texto, agrupar_matriz=True)[0]

        cantos = {tuple(p) for p in molde["controle_cantos"]}
        auxiliares = {tuple(p) for p in molde["controle_auxiliares"]}
        self.assertIn((20.0, 0.0), cantos)
        self.assertIn((32.0, 6.0), cantos)
        self.assertNotIn(tuple(base_topo[10]), cantos)
        self.assertTrue(auxiliares)
        pontos_grade = {tuple(cfg["ponto"]) for cfg in molde["graduacao_tabela"]["pontos"].values()}
        self.assertEqual(pontos_grade, cantos)
        self.assertFalse(auxiliares & pontos_grade)
        self.assertEqual(len(molde["pontos_controle_principais"]), len(cantos))
        self.assertEqual(len(molde["pontos_auxiliares"]), len(auxiliares))

    def test_matriz_agrupada_contorno_suave_usa_extremos_como_principais(self):
        menor = [
            (5.0 + 4.0 * math.cos(2.0 * math.pi * i / 40.0), 2.0 + 1.5 * math.sin(2.0 * math.pi * i / 40.0))
            for i in range(40)
        ]
        menor.append(menor[0])
        base = [
            (25.0 + 5.0 * math.cos(2.0 * math.pi * i / 48.0), 3.0 + 2.0 * math.sin(2.0 * math.pi * i / 48.0))
            for i in range(48)
        ]
        base.append(base[0])
        texto = _dxf_entities(
            [
                *_contorno_linhas(menor),
                *_text("LEVANTA MAG 2X", 5, 2),
                *_contorno_linhas(base),
                *_text("LEVANTA MAG 2X", 25, 3),
            ]
        )

        molde = self._importar_texto(texto, agrupar_matriz=True)[0]

        self.assertGreaterEqual(len(molde["controle_cantos"]), 4)
        self.assertLess(len(molde["controle_cantos"]), len(molde["pontos"]) // 2)
        self.assertEqual(len(molde["graduacao_tabela"]["pontos"]), len(molde["controle_cantos"]))

    def test_matriz_agrupada_ignora_duplicata_refletida_e_marca_par(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("COSTAS 2X", 5, 2),
                *_line(20, 0, 30, 0),
                *_line(30, 0, 30, 5),
                *_line(30, 5, 20, 5),
                *_line(20, 5, 20, 0),
                *_text("COSTAS 2X", 25, 2),
                *_line(40, 0, 52, 0),
                *_line(52, 0, 52, 6),
                *_line(52, 6, 40, 6),
                *_line(40, 6, 40, 0),
                *_text("COSTAS 2X", 46, 2),
                *_line(65, 0, 77, 0),
                *_line(77, 0, 77, 6),
                *_line(77, 6, 65, 6),
                *_line(65, 6, 65, 0),
                *_text("COSTAS 2X", 71, 2),
            ]
        )

        moldes = [el for el in self._importar_texto(texto, agrupar_matriz=True) if el.get("molde")]

        self.assertEqual(len(moldes), 1)
        molde = moldes[0]
        self.assertTrue(molde.get("par"))
        self.assertEqual(molde.get("qtd_modelo"), 1)
        self.assertEqual(molde.get("duplicatas_refletidas_ignoradas_dxf"), 2)
        self.assertEqual(molde["metadados"]["pares_refletidos_ignorados_dxf"], 2)
        self.assertEqual([g["tamanho"] for g in molde.get("graduacao_contornos_importados", [])], ["PP", "P"])

    def test_matriz_agrupada_preserva_contornos_reais_importados(self):
        base = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)]
        contorno_m = [
            (-1.0, -1.0),
            (5.0, -1.8),
            (11.0, -1.0),
            (11.0, 9.0),
            (-1.0, 9.0),
            (-1.0, -1.0),
        ]
        tabela = {
            "modo": "dx_dy",
            "pontos": {
                str(idx): {
                    "indice": idx,
                    "ponto": ponto,
                    "valores": {
                        "P": {"dx": 0.0, "dy": 0.0},
                        "M": {"dx": 100.0, "dy": 100.0},
                        "G": {"dx": -2.0, "dy": -2.0},
                    },
                }
                for idx, ponto in enumerate(base[:-1])
            },
        }

        contornos = dxf_import_module._graduacao_contornos_dxf_de_tabela(
            base,
            ["P", "M", "G"],
            {"P": "#00d000", "M": "#0080ff", "G": "#ffffff"},
            "P",
            tabela,
            [
                {"tamanho": "P", "base": True, "pontos": base},
                {"tamanho": "M", "base": False, "pontos": contorno_m},
            ],
        )

        m = next(item for item in contornos if item["tamanho"] == "M")
        g = next(item for item in contornos if item["tamanho"] == "G")
        self.assertEqual(m["pontos"], contorno_m)
        self.assertFalse(m.get("gerado_por_tabela_dxf"))
        self.assertTrue(g.get("gerado_por_tabela_dxf"))

    def test_matriz_agrupada_usa_nomes_cores_e_sobrepoe_contornos(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("FRENTE 1X", 26, 2),
            ]
        )
        grade = [
            {"ativo": True, "tamanho": "34", "cor": "#00e6d0"},
            {"ativo": True, "tamanho": "36", "cor": "#d7df00"},
            {"ativo": True, "tamanho": "38", "cor": "#0000ff"},
        ]

        molde = self._importar_texto(
            texto,
            agrupar_matriz=True,
            tamanho_base="36",
            grade_tamanhos=grade,
        )[0]

        self.assertEqual(molde["tamanho_base"], "36")
        self.assertEqual(molde["cor"], "#d7df00")
        self.assertEqual(
            molde["graduacao_tamanhos"],
            [
                {"tamanho": "34", "ativo": True, "base": False, "cor": "#00e6d0"},
                {"tamanho": "36", "ativo": True, "base": True, "cor": "#d7df00"},
            ],
        )
        contornos = molde["graduacao_contornos_importados"]
        self.assertEqual([(c["tamanho"], c["cor"], c["base"]) for c in contornos], [("34", "#00e6d0", False), ("36", "#d7df00", True)])
        centros = []
        for contorno in contornos:
            xs = [x for x, _ in contorno["pontos"]]
            ys = [y for _, y in contorno["pontos"]]
            centros.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
        self.assertEqual(centros[0], centros[1])

    def test_detectar_tamanhos_matriz_dxf_retorna_somente_tamanhos_existentes(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("FRENTE 1X", 26, 2),
            ]
        )
        grade = [
            {"ativo": True, "tamanho": "PP", "cor": "#00e6d0"},
            {"ativo": True, "tamanho": "P", "cor": "#d7df00"},
            {"ativo": True, "tamanho": "M", "cor": "#0000ff"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "molde.dxf"
            caminho.write_text(texto, encoding="utf-8")

            detectados = detectar_tamanhos_matriz_dxf(str(caminho), grade_tamanhos=grade)

        self.assertEqual([linha["tamanho"] for linha in detectados], ["PP", "P"])

    def test_matriz_agrupada_usa_xml_e_emf_associados_para_grade_e_propriedades(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("FRENTE 1X", 26, 2),
            ]
        )
        xml = """<?xml version="1.0" encoding="iso-8859-1"?>
<DATA_FILE_AUDACES>
  <MODEL NAME_M="6414 TESTE">
    <PATTERNS>
      <PATTERN NAME_P="FRENTE 1X" DESC_P="Frente teste" NAME_FAB="Malha" QT_MOD="2" ROT_P="1" FOLD_HOR="2" FOLD_VER="2" NOTCHS_P="3">
        <SIZES_P BASE_NAME="P">
          <SIZE_P NAME_SP="PP" PER_SP="120" AREA_SP="200" WIDTH_SP="10" HEIGHT_SP="5" />
          <SIZE_P NAME_SP="P" PER_SP="130" AREA_SP="250" WIDTH_SP="12" HEIGHT_SP="6" />
          <SIZE_P NAME_SP="M" PER_SP="140" AREA_SP="310" WIDTH_SP="14" HEIGHT_SP="7" />
        </SIZES_P>
      </PATTERN>
    </PATTERNS>
  </MODEL>
</DATA_FILE_AUDACES>
"""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "6414 B.dxf"
            caminho.write_text(texto, encoding="utf-8")
            caminho.with_suffix(".xml").write_text(xml, encoding="iso-8859-1")
            caminho.with_suffix(".emf").write_bytes(b"EMF")

            detectados = detectar_tamanhos_matriz_dxf(str(caminho))
            elementos = importar_dxf_para_elementos(str(caminho), agrupar_matriz=True)

        self.assertEqual([linha["tamanho"] for linha in detectados], ["PP", "P"])
        self.assertEqual([linha["tamanho"] for linha in detectados if linha.get("base")], ["P"])
        molde = next(el for el in elementos if el.get("molde"))
        self.assertEqual([linha["tamanho"] for linha in molde["graduacao_tamanhos"]], ["PP", "P"])
        self.assertEqual([linha["tamanho"] for linha in molde["graduacao_tamanhos"] if linha.get("base")], ["P"])
        self.assertEqual(molde["quantidade"], 2)
        self.assertEqual(molde["tecido"], "Malha")
        self.assertEqual(molde["descricao_molde"], "Frente teste")
        self.assertEqual(molde["rotacao_audaces"], 1)
        self.assertEqual(molde["dobra_horizontal_audaces"], 2)
        self.assertEqual(molde["dobra_vertical_audaces"], 2)
        self.assertEqual(molde["piques_audaces"], 3)
        self.assertIn("P", molde["graduacao_dimensoes_xml"])
        self.assertTrue(molde["metadados"]["audaces_xml_enriquecido"])
        self.assertTrue(str(molde["metadados"]["audaces_xml_path"]).endswith("6414 B.xml"))
        self.assertTrue(str(molde["metadados"]["audaces_emf_path"]).endswith("6414 B.emf"))

    def test_matriz_agrupada_xml_usa_apenas_tamanhos_posicionados_e_nao_extrapola(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("FRENTE 1X", 26, 2),
            ]
        )
        xml = """<?xml version="1.0" encoding="iso-8859-1"?>
<DATA_FILE_AUDACES>
  <MODEL NAME_M="6414 TESTE">
    <PATTERNS>
      <PATTERN NAME_P="FRENTE 1X">
        <SIZES_P BASE_NAME="P">
          <SIZE_P NAME_SP="PP" QUANT_PLACED="0" QUANT_SP="0" />
          <SIZE_P NAME_SP="P" QUANT_PLACED="0" QUANT_SP="0" />
          <SIZE_P NAME_SP="M" QUANT_PLACED="1" QUANT_SP="1" />
          <SIZE_P NAME_SP="G" QUANT_PLACED="1" QUANT_SP="1" />
        </SIZES_P>
      </PATTERN>
    </PATTERNS>
  </MODEL>
</DATA_FILE_AUDACES>
"""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "6414 B.dxf"
            caminho.write_text(texto, encoding="utf-8")
            caminho.with_suffix(".xml").write_text(xml, encoding="iso-8859-1")

            detectados = detectar_tamanhos_matriz_dxf(str(caminho))
            elementos = importar_dxf_para_elementos(str(caminho), agrupar_matriz=True)

        self.assertEqual([linha["tamanho"] for linha in detectados], ["M", "G"])
        self.assertEqual([linha["tamanho"] for linha in detectados if linha.get("base")], ["M"])
        molde = next(el for el in elementos if el.get("molde"))
        self.assertEqual([linha["tamanho"] for linha in molde["graduacao_tamanhos"]], ["M", "G"])
        contornos = molde["graduacao_contornos_importados"]
        self.assertEqual([contorno["tamanho"] for contorno in contornos], ["M", "G"])
        self.assertFalse(any(contorno.get("gerado_por_tabela_dxf") for contorno in contornos))

    def test_agrupamento_prefere_texto_central_e_nao_mistura_nomes(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 100, 0),
                *_line(100, 0, 100, 50),
                *_line(100, 50, 0, 50),
                *_line(0, 50, 0, 0),
                *_text("COSTAS 2X", 10, 10),
                *_text("SAIA 2X", 50, 25),
                *_line(120, 0, 224, 0),
                *_line(224, 0, 224, 52),
                *_line(224, 52, 120, 52),
                *_line(120, 52, 120, 0),
                *_text("COSTAS 2X", 132, 10),
                *_text("SAIA 2X", 172, 26),
                *_line(0, 80, 20, 80),
                *_line(20, 80, 20, 95),
                *_line(20, 95, 0, 95),
                *_line(0, 95, 0, 80),
                *_text("COSTAS 2X", 10, 87),
                *_line(30, 80, 52, 80),
                *_line(52, 80, 52, 96),
                *_line(52, 96, 30, 96),
                *_line(30, 96, 30, 80),
                *_text("COSTAS 2X", 41, 88),
            ]
        )

        elementos = self._importar_texto(texto, agrupar_matriz=True)

        por_nome = {el["nome_molde"]: el for el in elementos}
        self.assertEqual(set(por_nome), {"SAIA 2X", "COSTAS 2X"})
        self.assertTrue(all((max(x for x, _ in g["pontos"]) - min(x for x, _ in g["pontos"])) >= 100 for g in por_nome["SAIA 2X"]["graduacao_contornos_importados"]))
        self.assertTrue(all((max(x for x, _ in g["pontos"]) - min(x for x, _ in g["pontos"])) <= 25 for g in por_nome["COSTAS 2X"]["graduacao_contornos_importados"]))

    def test_alinhamento_corrige_contorno_de_cabeca_para_baixo(self):
        base = [(0, 0), (10, 0), (10, 4), (6, 4), (6, 8), (0, 8), (0, 0)]
        bbox = dxf_import_module._bbox(base)
        cx, cy = dxf_import_module._centro_bbox(bbox)
        origem_rotacionada = [(-(x - cx) + 100, -(y - cy) + 50) for x, y in base]

        alinhado = dxf_import_module._alinhar_pontos_ao_base(origem_rotacionada, base)

        self.assertEqual(alinhado, [(float(x), float(y)) for x, y in base])

    def test_alinhamento_reordena_inicio_do_contorno_antes_da_tabela(self):
        base = [(20.0, 0.0), (32.0, 0.0), (32.0, 6.0), (20.0, 6.0), (20.0, 0.0)]
        menor_com_inicio_em_outro_canto = [(10.0, 5.0), (0.0, 5.0), (0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]

        alinhado = dxf_import_module._alinhar_pontos_ao_base(menor_com_inicio_em_outro_canto, base)

        self.assertEqual(alinhado, [(21.0, 0.5), (31.0, 0.5), (31.0, 5.5), (21.0, 5.5), (21.0, 0.5)])

    def test_matriz_fecha_polyline_aberta_com_gap_pequeno(self):
        texto = _dxf_entities(
            [
                *_contorno_linhas([(0, 0), (18, 0), (18, 5), (0, 5), (0, 0.25)]),
                *_text("BABADIO MANG 2X", 9, 2),
                *_contorno_linhas([(24, 0), (44, 0), (44, 6), (24, 6), (24, 0.25)]),
                *_text("BABADIO MANG 2X", 34, 2),
            ]
        )

        elementos = self._importar_texto(texto, agrupar_matriz=True)

        moldes = [el for el in elementos if el.get("molde")]
        self.assertEqual(len(moldes), 1)
        molde = moldes[0]
        self.assertEqual(molde.get("nome_molde"), "BABADIO MANG 2X")
        self.assertEqual([c["tamanho"] for c in molde["graduacao_contornos_importados"]], ["PP", "P"])
        self.assertTrue(any((c.get("pontos") or [])[0] == (c.get("pontos") or [])[-1] for c in molde["graduacao_contornos_importados"]))

    def test_matriz_mantem_peca_unitaria_quando_xml_confirma_nome(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 20, 0),
                *_line(20, 0, 20, 4),
                *_line(20, 4, 0, 4),
                *_line(0, 4, 0, 0),
                *_text("ROLITE GOLA 2X", 10, 2),
            ]
        )
        xml = """<?xml version="1.0" encoding="iso-8859-1"?>
<DATA_FILE_AUDACES>
  <MODEL NAME_M="6414 TESTE">
    <PATTERNS>
      <PATTERN NAME_P="ROLITE GOLA 2X">
        <SIZES_P BASE_NAME="M">
          <SIZE_P NAME_SP="M" QUANT_PLACED="1" QUANT_SP="1" />
          <SIZE_P NAME_SP="G" QUANT_PLACED="1" QUANT_SP="1" />
          <SIZE_P NAME_SP="GG" QUANT_PLACED="1" QUANT_SP="1" />
        </SIZES_P>
      </PATTERN>
    </PATTERNS>
  </MODEL>
</DATA_FILE_AUDACES>
"""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "6414 B.dxf"
            caminho.write_text(texto, encoding="utf-8")
            caminho.with_suffix(".xml").write_text(xml, encoding="iso-8859-1")

            elementos = importar_dxf_para_elementos(str(caminho), agrupar_matriz=True)

        moldes = [el for el in elementos if el.get("molde")]
        self.assertEqual(len(moldes), 1)
        molde = moldes[0]
        self.assertEqual(molde.get("nome_molde"), "ROLITE GOLA 2X")
        self.assertEqual([linha["tamanho"] for linha in molde["graduacao_tamanhos"]], ["M", "G", "GG"])
        self.assertEqual([c["tamanho"] for c in molde["graduacao_contornos_importados"]], ["M", "G", "GG"])
        self.assertEqual(sum(1 for c in molde["graduacao_contornos_importados"] if not c.get("gerado_por_tabela_dxf")), 1)

    def test_matriz_ignora_texto_e_xml_marcados_com_reflexao(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("COSTAS 2X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("COSTAS 2X", 26, 2),
                *_line(50, 0, 62, 0),
                *_line(62, 0, 62, 6),
                *_line(62, 6, 50, 6),
                *_line(50, 6, 50, 0),
                *_text("COSTAS 2X #", 56, 2),
            ]
        )
        xml = """<?xml version="1.0" encoding="iso-8859-1"?>
<DATA_FILE_AUDACES>
  <MODEL NAME_M="6414 TESTE">
    <PATTERNS>
      <PATTERN NAME_P="COSTAS 2X">
        <SIZES_P BASE_NAME="P">
          <SIZE_P NAME_SP="PP" QUANT_PLACED="1" QUANT_SP="1" />
          <SIZE_P NAME_SP="P" QUANT_PLACED="1" QUANT_SP="1" />
        </SIZES_P>
      </PATTERN>
      <PATTERN NAME_P="COSTAS 2X #">
        <SIZES_P BASE_NAME="P">
          <SIZE_P NAME_SP="PP" QUANT_PLACED="1" QUANT_SP="1" />
          <SIZE_P NAME_SP="P" QUANT_PLACED="1" QUANT_SP="1" />
        </SIZES_P>
      </PATTERN>
    </PATTERNS>
  </MODEL>
</DATA_FILE_AUDACES>
"""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "6414 B.dxf"
            caminho.write_text(texto, encoding="utf-8")
            caminho.with_suffix(".xml").write_text(xml, encoding="iso-8859-1")

            elementos = importar_dxf_para_elementos(str(caminho), agrupar_matriz=True)

        nomes = [el.get("nome_molde") for el in elementos if el.get("molde")]
        self.assertEqual(nomes, ["COSTAS 2X"])
        molde = next(el for el in elementos if el.get("molde"))
        self.assertNotIn("#", molde.get("nome_molde", ""))

    def test_importacao_dxf_padrao_preserva_matriz_sem_agrupar(self):
        texto = _dxf_entities(
            [
                *_line(0, 0, 10, 0),
                *_line(10, 0, 10, 5),
                *_line(10, 5, 0, 5),
                *_line(0, 5, 0, 0),
                *_text("FRENTE 1X", 5, 2),
                *_line(20, 0, 32, 0),
                *_line(32, 0, 32, 6),
                *_line(32, 6, 20, 6),
                *_line(20, 6, 20, 0),
                *_text("FRENTE 1X", 26, 2),
            ]
        )

        elementos = self._importar_texto(texto)

        self.assertEqual(len(elementos), 4)
        self.assertFalse(any(el.get("molde") for el in elementos))
        self.assertEqual([el["texto"] for el in elementos if el.get("tipo") == "texto"], ["FRENTE 1X", "FRENTE 1X"])


if __name__ == "__main__":
    unittest.main()
