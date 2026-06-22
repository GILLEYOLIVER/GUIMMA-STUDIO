from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    VisualizacaoCanvas = None
    CenaDocumento = None
else:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from canvas.cena import CenaDocumento
    from canvas.snap import SnapResult
    from canvas.visualizacao import VisualizacaoCanvas


@unittest.skipIf(VisualizacaoCanvas is None, "PySide6 nao disponivel neste ambiente")
class VisualizacaoControlesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_selecao_molde_usa_controles_oficiais_mesmo_com_um_controle(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        base = [
            QPointF(0.0, 0.0),
            QPointF(1.0, 0.0),
            QPointF(2.0, 0.0),
            QPointF(3.0, 0.0),
        ]
        molde = {"controle_cantos": [(10.0, 5.0)]}

        controles = canvas._pontos_controle_selecao_molde(base, molde)

        self.assertEqual(len(controles), 1)
        self.assertEqual((controles[0].x(), controles[0].y()), (10.0, 5.0))

    def test_selecao_molde_mostra_todos_controles_oficiais_importados(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        base = [QPointF(float(i), 0.0) for i in range(8)]
        molde = {
            "controle_cantos": [
                (10.0, 5.0),
                (11.0, 5.0),
                (12.0, 5.0),
                (13.0, 5.0),
                (14.0, 5.0),
            ]
        }

        controles = canvas._pontos_controle_selecao_molde(base, molde)

        self.assertEqual(
            [(p.x(), p.y()) for p in controles],
            [(10.0, 5.0), (11.0, 5.0), (12.0, 5.0), (13.0, 5.0), (14.0, 5.0)],
        )

    def test_selecao_molde_mostra_auxiliares_sem_duplicar_principais(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        principais = [QPointF(10.0, 5.0), QPointF(11.0, 5.0)]
        molde = {
            "controle_auxiliares": [(10.0, 5.0), (10.5, 5.2)],
            "pontos_auxiliares": [{"x": 10.5, "y": 5.2}, {"x": 10.75, "y": 5.4}],
        }

        auxiliares = canvas._pontos_auxiliares_selecao_molde(molde, principais)

        self.assertEqual([(p.x(), p.y()) for p in auxiliares], [(10.5, 5.2), (10.75, 5.4)])

    def test_controles_audaces_aparecem_apenas_na_base_nao_na_graduacao(self):
        molde = {
            "tipo": "polyline",
            "molde": True,
            "origem": "audaces_emf_xml",
            "mostrar_controles": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
            "controle_cantos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)],
            "controle_auxiliares": [(5.0, 0.0), (10.0, 4.0)],
            "graduacao_contornos_importados": [
                {
                    "tamanho": "M",
                    "cor": "#0080ff",
                    "pontos": [(-1.0, -1.0), (11.0, -1.0), (11.0, 9.0), (-1.0, 9.0), (-1.0, -1.0)],
                },
                {
                    "tamanho": "G",
                    "cor": "#ffffff",
                    "pontos": [(-2.0, -2.0), (12.0, -2.0), (12.0, 10.0), (-2.0, 10.0), (-2.0, -2.0)],
                },
            ],
        }
        canvas = VisualizacaoCanvas(CenaDocumento(elementos=[molde]))
        canvas._elemento_visivel_no_viewport = lambda _el: True
        canvas._elemento_oculto_por_visualizacao_molde = lambda _el: False
        chamadas = []

        def registrar(_painter, ponto, _cor, _forma, _raio):
            chamadas.append((round(ponto.x(), 3), round(ponto.y(), 3)))

        canvas._desenhar_marcador_ponto_tela = registrar

        canvas._desenhar_controles_audaces_finais(object())

        self.assertEqual(len(chamadas), 6)
        self.assertEqual(
            chamadas,
            [
                (0.0, 0.0),
                (10.0, 0.0),
                (10.0, 8.0),
                (0.0, 8.0),
                (5.0, 0.0),
                (10.0, 4.0),
            ],
        )

    def test_residuo_importado_some_quando_graduacao_global_oculta(self):
        molde = {
            "tipo": "polyline",
            "molde": True,
            "molde_id": "emf-001",
            "mostrar_graduacao": False,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
        }
        residuo = {
            "tipo": "polyline",
            "origem": "audaces_emf",
            "subtipo_audaces": "linha_interna",
            "ocultar_quando_graduacao_oculta": True,
            "pontos": [(1.0, 1.0), (2.0, 2.0)],
            "metadados": {"ocultar_graduacao_molde_id": "emf-001"},
        }
        canvas = VisualizacaoCanvas(CenaDocumento(elementos=[molde, residuo]))

        self.assertTrue(canvas._elemento_oculto_por_visualizacao_molde(residuo))

        molde["mostrar_graduacao"] = True
        canvas._runtime_indice_vinculos = None

        self.assertFalse(canvas._elemento_oculto_por_visualizacao_molde(residuo))

    def test_selecao_molde_antigo_sem_controles_mantem_fallback_visual(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        base = [
            QPointF(0.0, 0.0),
            QPointF(1.0, 0.0),
            QPointF(2.0, 0.0),
            QPointF(3.0, 0.0),
            QPointF(4.0, 0.0),
        ]

        controles = canvas._pontos_controle_selecao_molde(base, {})

        self.assertEqual([(p.x(), p.y()) for p in controles], [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])

    def test_dobra_inativa_nao_mantem_sombra_visual(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {
            "tipo": "polyline",
            "molde": True,
            "molde_dobrado": False,
            "estado_dobra": {
                "ativo": False,
                "contorno_lado_oculto": [(0.0, 0.0), (10.0, 0.0)],
                "contorno_lado_dobrado": [(0.0, 0.0), (10.0, 0.0)],
            },
        }

        self.assertFalse(canvas._molde_tem_referencia_dobra_original(molde))
        self.assertIsNone(canvas._registro_dobra_visual_atual(molde))

    def test_numeracao_de_controles_segue_sentido_horario_na_tela(self):
        cantos = [
            QPointF(0.0, 4.0),
            QPointF(10.0, 4.0),
            QPointF(10.0, 0.0),
            QPointF(0.0, 0.0),
        ]

        ordenados = VisualizacaoCanvas._cantos_para_numeracao_horaria_tela(cantos)

        self.assertEqual(
            [(p.x(), p.y()) for p in ordenados],
            [(0.0, 4.0), (0.0, 0.0), (10.0, 0.0), (10.0, 4.0)],
        )

    def test_numeracao_de_controles_mantem_horario_visual_existente(self):
        cantos = [
            QPointF(0.0, 4.0),
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 4.0),
        ]

        ordenados = VisualizacaoCanvas._cantos_para_numeracao_horaria_tela(cantos)

        self.assertEqual(
            [(p.x(), p.y()) for p in ordenados],
            [(0.0, 4.0), (0.0, 0.0), (10.0, 0.0), (10.0, 4.0)],
        )

    def test_numeracao_de_dois_controles_usa_leitura_visual(self):
        cantos = [
            QPointF(10.0, 4.0),
            QPointF(0.0, 4.0),
        ]

        ordenados = VisualizacaoCanvas._cantos_para_numeracao_horaria_tela(cantos)

        self.assertEqual([(p.x(), p.y()) for p in ordenados], [(0.0, 4.0), (10.0, 4.0)])

    def test_numeracao_de_dois_controles_verticais_usa_cima_para_baixo(self):
        cantos = [
            QPointF(3.0, 8.0),
            QPointF(3.0, 2.0),
        ]

        ordenados = VisualizacaoCanvas._cantos_para_numeracao_horaria_tela(cantos)

        self.assertEqual([(p.x(), p.y()) for p in ordenados], [(3.0, 2.0), (3.0, 8.0)])

    def test_cor_de_preenchimento_do_molde_usa_cor_visual_escolhida(self):
        cor = VisualizacaoCanvas._cor_preenchimento_molde({"cor": "#ffff00"})

        self.assertEqual(cor.name(), QColor("#ffff00").name())

    def test_cor_de_preenchimento_do_molde_tem_fallback_visivel(self):
        cor = VisualizacaoCanvas._cor_preenchimento_molde({"cor": "cor-invalida"})

        self.assertEqual(cor.name(), QColor("#ffffff").name())

    def test_cor_linha_molde_respeita_cor_do_tecido_quando_ativo(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas._mostrar_cor_tecidos = True
        canvas._cores_tecidos = {"1": "#ffffff", "2": "#00b050"}

        cor = canvas._cor_linha_elemento({"molde": True, "tecido": "1", "cor": "#ff0000"})

        self.assertEqual(cor, QColor("#ffffff").name())

    def test_cor_linha_molde_usa_cor_propria_quando_tecido_desativado(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas._mostrar_cor_tecidos = False
        canvas._cores_tecidos = {"1": "#ffffff"}

        cor = canvas._cor_linha_elemento({"molde": True, "tecido": "1", "cor": "#ff0000"})

        self.assertEqual(cor, QColor("#ff0000").name())

    def test_config_cores_moldes_respeita_mostrar_conforme_ferramentas(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.set_config_cores_moldes({"fio": {"ativo": True, "cor": "#ff0000"}}, usar_cores_ferramentas=True)

        self.assertEqual(canvas._config_cor_molde("fio", "#ffffff"), "#ffffff")

        canvas.set_config_cores_moldes({"fio": {"ativo": True, "cor": "#ff0000"}}, usar_cores_ferramentas=False)

        self.assertEqual(canvas._config_cor_molde("fio", "#ffffff"), QColor("#ff0000").name())

    def test_config_cores_moldes_preserva_forma_dos_pontos(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.set_config_cores_moldes(
            {"ponto_controle": {"ativo": True, "cor": "#00ff00", "forma": "Quadrado preenchido"}}
        )

        cor, forma = canvas._config_ponto_molde("ponto_controle", "#000000", "Losango")

        self.assertEqual(cor, QColor("#00ff00").name())
        self.assertEqual(forma, "Quadrado preenchido")

    def test_flags_visualizacao_do_molde_ocultam_costura_e_linha_vinculada(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.cena.elementos = [
            {
                "tipo": "polyline",
                "molde": True,
                "molde_id": "m1",
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
                "mostrar_costura": False,
                "mostrar_linhas_auxiliares": False,
            },
            {"tipo": "polyline", "subtipo_audaces": "costura", "costura_de_molde_id": "m1", "pontos": []},
            {"tipo": "polyline", "subtipo_audaces": "linha_interna", "molde_id": "m1", "pontos": []},
            {"tipo": "polyline", "subtipo_audaces": "linha_interna", "molde_id": "outro", "pontos": []},
        ]

        self.assertTrue(canvas._elemento_oculto_por_visualizacao_molde(canvas.cena.elementos[1]))
        self.assertTrue(canvas._elemento_oculto_por_visualizacao_molde(canvas.cena.elementos[2]))
        self.assertFalse(canvas._elemento_oculto_por_visualizacao_molde(canvas.cena.elementos[3]))

    def test_costura_de_graduacao_some_quando_graduacao_do_molde_esta_oculta(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.cena.elementos = [
            {
                "tipo": "polyline",
                "molde": True,
                "molde_id": "m1",
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
                "mostrar_costura": True,
                "mostrar_graduacao": False,
            },
            {"tipo": "polyline", "subtipo_audaces": "costura", "costura_de_molde_id": "m1", "pontos": []},
            {
                "tipo": "polyline",
                "subtipo_audaces": "costura",
                "costura_de_molde_id": "m1",
                "costura_graduacao": True,
                "graduacao_tamanho": "G",
                "pontos": [],
            },
        ]

        self.assertFalse(canvas._elemento_oculto_por_visualizacao_molde(canvas.cena.elementos[1]))
        self.assertTrue(canvas._elemento_oculto_por_visualizacao_molde(canvas.cena.elementos[2]))

    def test_costura_dependente_cria_costura_para_tamanho_novo_graduado(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {
            "tipo": "polyline",
            "molde": True,
            "molde_id": "m1",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "cor": "#111111", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#222222", "base": True},
                {"ativo": True, "tamanho": "G", "cor": "#333333", "base": False},
                {"ativo": True, "tamanho": "GG", "cor": "#444444", "base": False},
            ],
            "graduacao_tabela": {
                "modo": "dx_dy",
                "pontos": {
                    str(idx): {
                        "indice": idx,
                        "ponto": ponto,
                        "valores": {
                            "P": {"dx": -1.0, "dy": 0.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 2.0, "dy": 0.0},
                            "GG": {"dx": 4.0, "dy": 0.0},
                        },
                    }
                    for idx, ponto in enumerate([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])
                },
            },
        }
        costura_base = {
            "tipo": "polyline",
            "subtipo_audaces": "costura",
            "costura_de_molde_id": "m1",
            "molde_id": "m1",
            "costura_segmentos": [0, 1, 2, 3],
            "costura_parcial": False,
            "pontos": [(-1.0, -1.0), (11.0, -1.0), (11.0, 11.0), (-1.0, 11.0), (-1.0, -1.0)],
        }
        canvas.cena.elementos = [molde, costura_base]

        self.assertTrue(canvas._sincronizar_costuras_dependentes())

        graduadas = {
            str(el.get("graduacao_tamanho")): el
            for el in canvas.cena.elementos
            if isinstance(el, dict) and el.get("costura_graduacao")
        }
        self.assertEqual(set(graduadas), {"P", "G", "GG"})
        self.assertTrue(all(len(el.get("pontos", [])) >= 4 for el in graduadas.values()))

    def test_clique_em_costura_vinculada_seleciona_molde_dono(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        canvas.cena.elementos = [
            {
                "tipo": "polyline",
                "molde": True,
                "molde_id": "m1",
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 0.0)],
            },
            {
                "tipo": "polyline",
                "subtipo_audaces": "costura",
                "costura_de_molde_id": "m1",
                "molde_id": "m1",
                "pontos": [(0.0, -1.0), (10.0, -1.0)],
            },
        ]

        indices = canvas._indices_elementos_em_ponto(QPointF(5.0, -1.0))

        self.assertEqual(indices, [0])
        self.assertEqual(canvas._indices_transformacao_com_vinculados({1}), [0, 1])

    def test_indice_costuras_vinculadas_atualiza_quando_cena_muda(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.cena.elementos = [
            {"tipo": "polyline", "molde": True, "molde_id": "m1", "pontos": []},
            {"tipo": "polyline", "subtipo_audaces": "costura", "costura_de_molde_id": "m1", "pontos": []},
        ]

        self.assertEqual(canvas._indices_costuras_vinculadas(0), [1])
        self.assertEqual(canvas._indice_molde_dono_costura(1), 0)

        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "subtipo_audaces": "costura",
                "metadados": {"costura_de_molde_id": "m1", "subtipo_audaces": "costura"},
                "pontos": [],
            }
        )

        self.assertEqual(canvas._indices_costuras_vinculadas(0), [1, 2])
        self.assertEqual(canvas._indice_molde_dono_costura(2), 0)

    def test_linhas_auxiliares_vinculadas_ficam_ocultas_quando_flag_nao_existe(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.cena.elementos = [
            {"tipo": "polyline", "molde": True, "molde_id": "m1", "pontos": []},
            {"tipo": "polyline", "subtipo_audaces": "costura", "costura_de_molde_id": "m1", "pontos": []},
            {"tipo": "polyline", "subtipo_audaces": "linha_interna", "molde_id": "m1", "pontos": []},
        ]

        self.assertFalse(canvas._elemento_oculto_por_visualizacao_molde(canvas.cena.elementos[1]))
        self.assertTrue(canvas._elemento_oculto_por_visualizacao_molde(canvas.cena.elementos[2]))

    def test_colar_buffer_de_outro_arquivo_preserva_grade_diferente(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(400, 300)
        canvas.zoom = 10.0
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "molde": True,
                "nome_molde": "K1",
                "pontos": [(0.0, 0.0), (10.0, 0.0)],
                "graduacao_grade_nome": "P-G(M)",
                "graduacao_tamanhos": [
                    {"ativo": True, "tamanho": "P", "base": False},
                    {"ativo": True, "tamanho": "M", "base": True},
                    {"ativo": True, "tamanho": "G", "base": False},
                ],
            }
        )
        canvas.definir_buffer_copia(
            {
                "versao": 2,
                "origem": "GUIMMA_STUDIO",
                "elementos": [
                    {
                        "tipo": "polyline",
                        "molde": True,
                        "nome_molde": "K2",
                        "pontos": [(20.0, 0.0), (30.0, 0.0)],
                        "graduacao_grade_nome": "36-44(40)",
                        "graduacao_tamanhos": [
                            {"ativo": True, "tamanho": "36", "base": False},
                            {"ativo": True, "tamanho": "40", "base": True},
                            {"ativo": True, "tamanho": "44", "base": False},
                        ],
                    }
                ],
            }
        )

        canvas.colar()

        self.assertEqual(len(canvas.cena.elementos), 2)
        colado = canvas.cena.elementos[1]
        self.assertEqual(colado["graduacao_grade_nome"], "36-44(40)")
        self.assertEqual([linha["tamanho"] for linha in colado["graduacao_tamanhos"]], ["36", "40", "44"])

    def test_copiar_em_um_canvas_e_colar_em_outro_preserva_configuracoes(self):
        VisualizacaoCanvas._buffer_copia_compartilhado = None
        origem = VisualizacaoCanvas(CenaDocumento())
        destino = VisualizacaoCanvas(CenaDocumento())
        destino.resize(400, 300)
        destino.zoom = 10.0
        molde = {
            "tipo": "polyline",
            "molde": True,
            "nome_molde": "K2",
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "fio_origem": [1.0, 0.0],
            "fio_fim": [9.0, 0.0],
            "graduacao_grade_nome": "36-44(40)",
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "36", "base": False},
                {"ativo": True, "tamanho": "40", "base": True},
                {"ativo": True, "tamanho": "44", "base": False},
            ],
        }
        origem.cena.elementos.append(molde)
        origem._selecionados = {0}

        origem.copiar()
        destino.colar()

        self.assertEqual(len(destino.cena.elementos), 1)
        colado = destino.cena.elementos[0]
        self.assertEqual(colado["nome_molde"], "K2")
        self.assertEqual(colado["graduacao_grade_nome"], "36-44(40)")
        self.assertEqual([linha["tamanho"] for linha in colado["graduacao_tamanhos"]], ["36", "40", "44"])
        self.assertIn("fio_origem", colado)
        self.assertIn("fio_fim", colado)
        self.assertEqual(destino._selecionados, {0})

    def test_cor_graduacao_usa_config_por_lado_da_base(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.set_config_cores_moldes(
            {
                "tamanhos_menores": {"ativo": True, "cor": "#111111"},
                "tamanho_base": {"ativo": True, "cor": "#222222"},
                "tamanhos_maiores": {"ativo": True, "cor": "#333333"},
            }
        )
        molde = {
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
            ]
        }

        self.assertEqual(canvas._cor_tamanho_graduacao(molde, "P", "#ffffff"), QColor("#111111").name())
        self.assertEqual(canvas._cor_tamanho_base_graduacao(molde), QColor("#222222").name())
        self.assertEqual(canvas._cor_tamanho_graduacao(molde, "G", "#ffffff"), QColor("#333333").name())

    def test_graduacao_usa_pontos_controle_como_referencia_de_interpolacao(self):
        contorno = [
            QPointF(0.0, 0.0),
            QPointF(2.0, 0.0),
            QPointF(4.0, 0.0),
            QPointF(6.0, 0.0),
            QPointF(8.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 10.0),
            QPointF(0.0, 10.0),
        ]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(p.x(), p.y()) for p in contorno] + [(0.0, 0.0)],
            "pontos_controle": [
                (0.0, 0.0),
                (10.0, 0.0),
                (10.0, 10.0),
                (0.0, 10.0),
                (4.0, 0.0),
            ],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "M", "base": True},
                {"ativo": True, "tamanho": "G", "base": False},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "4": {
                        "indice": 4,
                        "ponto": (4.0, 0.0),
                        "valores": {"G": {"dx": 0.0, "dy": -2.0}},
                    }
                }
            },
        }

        deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
            molde["graduacao_tabela"]["pontos"],
            "G",
            len(contorno),
            contorno=contorno,
            referencias=VisualizacaoCanvas._pontos_referencia_graduacao(molde),
        )

        self.assertLess(deslocamentos[2][1], -1.9)
        self.assertLess(deslocamentos[1][1], 0.0)
        self.assertLess(deslocamentos[3][1], 0.0)

    def test_graduacao_ignora_referencias_desalinhadas_do_contorno_atual(self):
        contorno = [
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 5.0),
            QPointF(0.0, 5.0),
        ]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(p.x(), p.y()) for p in contorno] + [(0.0, 0.0)],
            "pontos_controle_principais": [
                {"x": -80.0, "y": -60.0},
                {"x": -40.0, "y": -50.0},
                {"x": 70.0, "y": -45.0},
            ],
            "pontos_graduacao": [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 5.0},
                {"x": 0.0, "y": 5.0},
            ],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "M", "base": True},
                {"ativo": True, "tamanho": "G", "base": False},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "1": {
                        "indice": 1,
                        "ponto": (-40.0, -50.0),
                        "valores": {"G": {"dx": 0.0, "dy": -2.0}},
                    }
                }
            },
        }

        referencias = VisualizacaoCanvas._pontos_referencia_graduacao(molde, contorno=contorno)
        deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
            molde["graduacao_tabela"]["pontos"],
            "G",
            len(contorno),
            contorno=contorno,
            referencias=referencias,
        )

        self.assertEqual([(p.x(), p.y()) for p in referencias], [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)])
        self.assertEqual(deslocamentos[1], (0.0, -2.0))
        self.assertEqual(deslocamentos[0], (0.0, 0.0))
        self.assertEqual(deslocamentos[2], (0.0, 0.0))

    def test_graduacao_interpola_por_comprimento_do_contorno(self):
        contorno = [
            QPointF(0.0, 0.0),
            QPointF(1.0, 0.0),
            QPointF(2.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 10.0),
            QPointF(0.0, 10.0),
        ]
        pontos_cfg = {
            "3": {
                "ponto": (10.0, 0.0),
                "valores": {"G": {"dx": 0.0, "dy": -10.0}},
            }
        }
        referencias = [contorno[0], contorno[3], contorno[4], contorno[5]]

        deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
            pontos_cfg,
            "G",
            len(contorno),
            contorno=contorno,
            referencias=referencias,
        )

        self.assertAlmostEqual(deslocamentos[1][1], -1.0)
        self.assertAlmostEqual(deslocamentos[2][1], -2.0)
        self.assertEqual(deslocamentos[3], (0.0, -10.0))
        self.assertEqual(deslocamentos[4], (0.0, 0.0))

    def test_graduacao_com_referencias_incompletas_nao_puxa_lado_oposto(self):
        contorno = [
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 5.0),
            QPointF(0.0, 5.0),
        ]
        pontos_cfg = {
            "0": {
                "ponto": (10.0, 0.0),
                "valores": {"G": {"dx": 2.0, "dy": -2.0}},
            }
        }
        referencias_incompletas = [contorno[1], contorno[2]]

        deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
            pontos_cfg,
            "G",
            len(contorno),
            contorno=contorno,
            referencias=referencias_incompletas,
        )

        self.assertEqual(deslocamentos[1], (2.0, -2.0))
        self.assertEqual(deslocamentos[2], (0.0, 0.0))
        self.assertEqual(deslocamentos[0], (0.0, 0.0))
        self.assertEqual(deslocamentos[3], (0.0, 0.0))

    def test_opacidade_imagens_global_fica_limitada_entre_zero_e_um(self):
        canvas = VisualizacaoCanvas(CenaDocumento())

        canvas.set_opacidade_imagens(1.7)
        self.assertEqual(canvas._opacidade_imagens, 1.0)

        canvas.set_opacidade_imagens(-0.2)
        self.assertEqual(canvas._opacidade_imagens, 0.0)

        canvas.set_opacidade_imagens(0.35)
        self.assertEqual(canvas._opacidade_imagens, 0.35)

    def test_polilinha_fechada_nao_herda_brush_preenchido(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        image = QImage(140, 100, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        try:
            painter.setBrush(QColor("#ff00ff"))
            canvas._desenhar_polilinha(
                painter,
                [
                    QPointF(2.0, 2.0),
                    QPointF(10.0, 2.0),
                    QPointF(10.0, 7.0),
                    QPointF(2.0, 7.0),
                    QPointF(2.0, 2.0),
                ],
                cor="#ffffff",
                espessura=1.0,
                estilo="solid",
            )
        finally:
            painter.end()

        self.assertEqual(image.pixelColor(60, 45).alpha(), 0)

    def test_elemento_fora_do_viewport_nao_precisa_ser_desenhado(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(800, 600)
        canvas.zoom = 10.0
        canvas.origem_cena = QPointF(0.0, 0.0)

        self.assertTrue(canvas._elemento_visivel_no_viewport({"tipo": "polyline", "pontos": [(1.0, 1.0), (2.0, 2.0)]}))
        self.assertFalse(canvas._elemento_visivel_no_viewport({"tipo": "polyline", "pontos": [(500.0, 500.0), (510.0, 510.0)]}))

    def test_selecao_por_ponto_pega_linha_solta_sobre_molde(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        canvas.cena.elementos.extend(
            [
                {
                    "tipo": "polyline",
                    "molde": True,
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                },
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (10.0, 0.0)],
                    "cor": "#ff0000",
                },
            ]
        )

        indices = canvas._indices_elementos_em_ponto(QPointF(5.0, 0.0))

        self.assertGreaterEqual(len(indices), 2)
        self.assertEqual(indices[0], 1)

    def test_selecao_por_ponto_pega_desenho_solto_com_tipo_generico(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        canvas.cena.elementos.append(
            {
                "tipo": "desenho_livre",
                "pontos": [(0.0, 0.0), (10.0, 0.0)],
                "cor": "#ff0000",
            }
        )

        indices = canvas._indices_elementos_em_ponto(QPointF(5.0, 0.0))

        self.assertEqual(indices, [0])

    def test_hit_test_ignora_segmentos_fora_do_bbox(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        distante = {"tipo": "polyline", "pontos": [(1000.0, 1000.0), (1010.0, 1000.0)]}
        perto = {"tipo": "polyline", "pontos": [(0.0, 0.0), (10.0, 0.0)]}
        canvas.cena.elementos.extend([distante, perto])
        original = canvas._pontos_hit_teste_elemento
        chamadas = []

        def contar(elemento):
            chamadas.append(elemento)
            return original(elemento)

        canvas._pontos_hit_teste_elemento = contar

        indices = canvas._indices_elementos_em_ponto(QPointF(5.0, 0.0))

        self.assertEqual(indices, [1])
        self.assertIn(perto, chamadas)
        self.assertNotIn(distante, chamadas)

    def test_indice_espacial_filtra_elementos_fora_do_viewport(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(200, 200)
        canvas.zoom = 10.0
        canvas.origem_cena = QPointF(0.0, 0.0)
        canvas.cena.elementos = [
            {"tipo": "polyline", "pontos": [(1.0, 1.0), (2.0, 1.0)]},
            {"tipo": "polyline", "pontos": [(1000.0, 1000.0), (1010.0, 1000.0)]},
        ]

        indices = canvas._indices_elementos_visiveis_viewport()

        self.assertEqual(indices, [0])

    def test_indice_espacial_hit_test_nao_varre_elementos_distantes(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        for idx in range(100):
            x = 1000.0 + (idx * 10.0)
            canvas.cena.elementos.append({"tipo": "polyline", "pontos": [(x, 1000.0), (x + 1.0, 1000.0)]})
        perto = {"tipo": "polyline", "pontos": [(0.0, 0.0), (10.0, 0.0)]}
        canvas.cena.elementos.append(perto)
        original = canvas._pontos_hit_teste_elemento
        chamadas = []

        def contar(elemento):
            chamadas.append(elemento)
            return original(elemento)

        canvas._pontos_hit_teste_elemento = contar

        indices = canvas._indices_elementos_em_ponto(QPointF(5.0, 0.0))

        self.assertEqual(indices, [100])
        self.assertEqual(chamadas, [perto])

    def test_cache_bbox_invalida_quando_pontos_sao_substituidos(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(800, 600)
        canvas.zoom = 10.0
        canvas.origem_cena = QPointF(0.0, 0.0)
        elemento = {"tipo": "polyline", "pontos": [(1.0, 1.0), (2.0, 2.0)]}

        self.assertTrue(canvas._elemento_visivel_no_viewport(elemento))
        elemento["pontos"] = [(500.0, 500.0), (510.0, 510.0)]

        self.assertFalse(canvas._elemento_visivel_no_viewport(elemento))

    def test_cache_pontos_render_invalida_quando_pontos_mudam(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        elemento = {"tipo": "polyline", "pontos": [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]}

        pontos_1 = canvas._pontos_render_elemento(elemento)
        pontos_2 = canvas._pontos_render_elemento(elemento)

        self.assertIs(pontos_1, pontos_2)

        elemento["pontos"][1] = (3.0, 0.0)
        pontos_3 = canvas._pontos_render_elemento(elemento)

        self.assertIsNot(pontos_1, pontos_3)
        self.assertEqual(pontos_3[1], QPointF(3.0, 0.0))

    def test_cache_path_polilinha_invalida_quando_view_muda(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        elemento = {"tipo": "polyline", "pontos": [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]}
        pontos = canvas._pontos_render_elemento(elemento)

        path_1 = canvas._path_polilinha_tela(pontos, elemento)
        path_2 = canvas._path_polilinha_tela(pontos, elemento)

        self.assertIs(path_1, path_2)

        canvas.zoom = 20.0
        path_3 = canvas._path_polilinha_tela(pontos, elemento)

        self.assertIsNot(path_1, path_3)

    def test_cache_path_curva_suave_invalida_quando_view_muda(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        elemento = {
            "tipo": "polyline",
            "curva_suave": True,
            "pontos": [(0.0, 0.0), (2.0, 1.0), (4.0, 0.0), (6.0, 1.0)],
        }
        pontos = canvas._pontos_curva_suave_elemento(elemento)

        path_1 = canvas._path_curva_suave_tela(pontos, False, elemento)
        path_2 = canvas._path_curva_suave_tela(pontos, False, elemento)

        self.assertIs(path_1, path_2)

        canvas.origem_cena = QPointF(1.0, 0.0)
        path_3 = canvas._path_curva_suave_tela(pontos, False, elemento)

        self.assertIsNot(path_1, path_3)

    def test_cache_layout_numeros_invalida_quando_zoom_muda(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        metrics = QFontMetrics(canvas.font())
        itens = [(QPointF(0.0, 0.0), "1", True), (QPointF(10.0, 0.0), "2", True)]

        layout_1 = canvas._layout_numeros_molde_canvas(metrics, itens, QPointF(5.0, 0.0), 8.0)
        layout_2 = canvas._layout_numeros_molde_canvas(metrics, itens, QPointF(5.0, 0.0), 8.0)

        self.assertIs(layout_1, layout_2)

        canvas.zoom = 20.0
        layout_3 = canvas._layout_numeros_molde_canvas(metrics, itens, QPointF(5.0, 0.0), 8.0)

        self.assertIsNot(layout_1, layout_3)

    def test_finalizar_zoom_interativo_restaura_renderizacao_completa(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas._zoom_interativo = True

        canvas._finalizar_zoom_interativo()

        self.assertFalse(canvas._zoom_interativo)

    def test_zoom_interativo_nao_oculta_overlays_do_canvas(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(240, 160)
        canvas.zoom = 8.0
        canvas._grid_visivel = False
        canvas._zoom_interativo = True
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "molde": True,
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                "nome_molde": "K1",
                "fio_origem": (2.0, 1.0),
                "fio_fim": (8.0, 1.0),
            }
        )
        chamadas = []

        class _Ferramenta:
            def on_paint_overlay(self, _canvas, _painter):
                chamadas.append(("runtime", None))

        canvas._desenhar_overlays_moldes = lambda _painter, visiveis=None: chamadas.append(("overlays", set(visiveis or set())))
        canvas._runtime_tool = _Ferramenta()

        image = QImage(240, 160, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        try:
            canvas.render(painter, QPoint(0, 0))
        finally:
            painter.end()

        self.assertIn(("overlays", {0}), chamadas)
        self.assertIn(("runtime", None), chamadas)

    def test_espessura_aplica_em_molde_selecionado_e_tamanhos_graduados(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "cor": "#ffff00",
            "espessura": 1.0,
            "espessura_graduacao": 1.0,
        }
        canvas.cena.elementos.append(molde)
        canvas._selecionados = {0}

        alterou = canvas.aplicar_estilo_linha_selecionados({"espessura": 4.0})

        self.assertTrue(alterou)
        self.assertEqual(molde["espessura"], 4.0)
        self.assertEqual(molde["espessura_graduacao"], 4.0)
        self.assertEqual(molde["cor"], "#ffff00")

    def test_graduacao_herda_espessura_do_molde_quando_nao_tem_espessura_propria(self):
        self.assertEqual(VisualizacaoCanvas._espessura_graduacao_molde({"espessura": 6.0}), 6.0)
        self.assertEqual(
            VisualizacaoCanvas._espessura_graduacao_molde({"espessura": 6.0, "espessura_graduacao": 3.0}),
            3.0,
        )

    def test_graduacao_redesenha_tamanho_base_por_ultimo(self):
        class _Painter:
            def save(self):
                pass

            def restore(self):
                pass

        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
            ],
        }
        base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 5.0), QPointF(0.0, 5.0)]
        contorno = base + [QPointF(base[0])]
        chamadas = []

        canvas._contornos_graduacao_tabela = lambda _el, _base: [
            ("P", "#ffff00", contorno),
            ("G", "#ff8c00", contorno),
        ]
        canvas._desenhar_polilinha = lambda _painter, _pontos, **kwargs: chamadas.append(kwargs["cor"])

        canvas._desenhar_graduacao_tabela_molde(_Painter(), molde, base)

        self.assertEqual(chamadas, ["#ffff00", "#ff8c00", "#2b7cd3"])

    def test_estilo_em_selecionado_nao_altera_cor_de_molde(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "cor": "#ffff00",
        }
        canvas.cena.elementos.append(molde)
        canvas._selecionados = {0}

        alterou = canvas.aplicar_estilo_linha_selecionados({"cor": "#ff0000", "espessura": 3.0})

        self.assertTrue(alterou)
        self.assertEqual(molde["cor"], "#ffff00")
        self.assertEqual(molde["espessura"], 3.0)
        self.assertEqual(molde["espessura_graduacao"], 3.0)

    def test_espessura_aplica_em_linha_selecionada(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        linha = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "espessura": 1.0,
        }
        canvas.cena.elementos.append(linha)
        canvas._selecionados = {0}

        alterou = canvas.aplicar_estilo_linha_selecionados({"espessura": 5.0})

        self.assertTrue(alterou)
        self.assertEqual(linha["espessura"], 5.0)
        self.assertNotIn("espessura_graduacao", linha)

    def test_alternar_graduacao_altera_visualizacao_dos_moldes(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
        }
        canvas.cena.elementos.append(molde)

        self.assertTrue(canvas.set_graduacao_visivel(False))
        self.assertFalse(molde["mostrar_graduacao"])
        self.assertTrue(canvas.set_graduacao_visivel(True))
        self.assertTrue(molde["mostrar_graduacao"])

    def test_alternar_graduacao_apenas_em_molde_selecionado(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde_1 = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
        }
        molde_2 = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(20.0, 0.0), (30.0, 0.0), (30.0, 5.0), (20.0, 0.0)],
        }
        canvas.cena.elementos.extend([molde_1, molde_2])
        canvas._selecionados = {0}

        self.assertTrue(canvas.set_graduacao_visivel(False, apenas_selecionados=True))

        self.assertFalse(molde_1["mostrar_graduacao"])
        self.assertNotIn("mostrar_graduacao", molde_2)

        self.assertTrue(canvas.set_graduacao_visivel(False))
        self.assertFalse(molde_2["mostrar_graduacao"])

    def test_alternar_costura_altera_visualizacao_dos_moldes(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
        }
        canvas.cena.elementos.append(molde)

        self.assertTrue(canvas.set_costura_visivel(False))
        self.assertFalse(molde["mostrar_costura"])
        self.assertTrue(canvas.set_costura_visivel(True))
        self.assertTrue(molde["mostrar_costura"])

    def test_snap_sobre_graduacao_visivel_nao_deve_sobrepor_tamanhos(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        valores_g = {
            str(idx): {"valores": {"M": {"dx": 0.0, "dy": 0.0}, "G": {"dx": 1.0, "dy": 0.0}}}
            for idx in range(4)
        }
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "molde": True,
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
                "graduacao_tamanhos": [
                    {"ativo": True, "tamanho": "M", "base": True},
                    {"ativo": True, "tamanho": "G", "base": False},
                ],
                "graduacao_tabela": {"pontos": valores_g},
            }
        )

        sobre_tamanho = SnapResult(QPointF(11.0, 2.5), "borda", 0.0, 0)
        sobre_base = SnapResult(QPointF(0.0, 2.5), "borda", 0.0, 0)

        self.assertTrue(canvas._snap_sobre_graduacao_visivel(sobre_tamanho))
        self.assertFalse(canvas._snap_sobre_graduacao_visivel(sobre_base))

    def test_zoom_interativo_mantem_graduacao_visivel(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "molde": True,
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                "graduacao_tamanhos": [
                    {"ativo": True, "tamanho": "M", "base": True},
                    {"ativo": True, "tamanho": "G", "base": False},
                ],
                "graduacao_tabela": {"pontos": {"0": {"valores": {"G": {"dx": 1.0, "dy": 0.0}}}}},
            }
        )
        chamadas = []
        canvas._desenhar_graduacao_tabela_molde = lambda painter, el, base: chamadas.append((el, base))

        canvas._desenhar_graduacao_moldes_visiveis(object(), {0})

        self.assertEqual(len(chamadas), 1)
        self.assertIs(chamadas[0][0], canvas.cena.elementos[0])

    def test_paint_nao_desenha_graduacao_duas_vezes_fora_do_overlay(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(220, 160)
        canvas._grid_visivel = False
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "molde": True,
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                "graduacao_tamanhos": [
                    {"ativo": True, "tamanho": "P", "base": True},
                    {"ativo": True, "tamanho": "M", "base": False},
                ],
                "graduacao_contornos_importados": [
                    {"tamanho": "P", "base": True, "pontos": [(0.0, 0.0), (10.0, 0.0), (0.0, 0.0)]},
                    {"tamanho": "M", "base": False, "pontos": [(1.0, 0.0), (11.0, 0.0), (1.0, 0.0)]},
                ],
            }
        )
        chamadas = []
        canvas._desenhar_graduacao_moldes_visiveis = lambda _painter, _visiveis=None: chamadas.append("direto")
        canvas._desenhar_overlays_moldes = lambda _painter, _visiveis=None: chamadas.append("overlay")

        image = QImage(220, 160, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        try:
            canvas.render(painter, QPoint(0, 0))
        finally:
            painter.end()

        self.assertEqual(chamadas, ["overlay"])

    def test_rascunho_propriedades_oculta_elemento_real_correspondente(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.cena.elementos.extend(
            [
                {"tipo": "polyline", "molde": True, "nome_molde": "K1"},
                {"tipo": "polyline", "molde": True, "nome_molde": "K1 - G"},
            ]
        )
        canvas.set_visualizacao_rascunho(
            [
                {
                    "tipo": "polyline",
                    "molde": True,
                    "nome_molde": "K1 - G",
                    "_indice_visualizacao_rascunho": 1,
                }
            ]
        )

        self.assertEqual(canvas._indices_ocultos_por_visualizacao_rascunho(), {1})
        self.assertIs(canvas._visualizacao_rascunho_por_indice()[1], canvas._visualizacao_rascunho_elementos[0])

    def test_caminho_grade_liga_ponto_base_ao_tamanho_graduado(self):
        base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 5.0)]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": False, "cor": "#00ff00"},
                {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "1": {
                        "ponto": (10.0, 0.0),
                        "valores": {
                            "P": {"dx": 0.0, "dy": 1.0},
                            "G": {"dx": 0.0, "dy": -1.0},
                        },
                    }
                }
            },
        }

        caminhos = VisualizacaoCanvas._caminhos_graduacao_tabela(molde, base)

        self.assertEqual(len(caminhos), 2)
        self.assertEqual(caminhos[0][0], "P")
        self.assertEqual(caminhos[0][2], QPointF(10.0, 0.0))
        self.assertEqual(caminhos[0][3], QPointF(10.0, 1.0))
        self.assertEqual(caminhos[1][0], "G")
        self.assertEqual(caminhos[1][2], QPointF(10.0, 0.0))
        self.assertEqual(caminhos[1][3], QPointF(10.0, -1.0))

    def test_sombra_local_anterior_usa_cor_de_cada_tamanho(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        chamadas = []
        canvas._desenhar_polilinha = lambda _painter, _pontos, **kwargs: chamadas.append(kwargs)
        canvas._config_cor_molde = lambda _chave, _padrao: "#999999"
        base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 5.0)]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": False, "cor": "#00ff00"},
                {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "1": {
                        "ponto": (10.0, 0.0),
                        "valores": {
                            "P": {"dx": 0.0, "dy": 1.0},
                            "G": {"dx": 0.0, "dy": -1.0},
                        },
                    }
                }
            },
        }

        canvas._desenhar_caminhos_graduacao_molde(None, molde, base)

        self.assertEqual([chamada["cor"] for chamada in chamadas], ["#00ff00", "#ff0000"])
        self.assertEqual({chamada["estilo"] for chamada in chamadas}, {"dash"})

    def test_rascunho_temporario_graduado_usa_cores_dos_tamanhos(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        chamadas = []
        canvas._desenhar_polilinha = lambda _painter, _pontos, **kwargs: chamadas.append(kwargs)
        canvas._config_cor_molde = lambda _chave, padrao: padrao
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": False, "cor": "#00ff00"},
                {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "ponto": (0.0, 0.0),
                        "valores": {
                            "P": {"dx": -1.0, "dy": 0.0},
                            "G": {"dx": 1.0, "dy": 0.0},
                        },
                    }
                }
            },
        }
        pontos = [QPointF(x, y) for x, y in molde["pontos"]]

        self.assertTrue(canvas._desenhar_rascunho_graduacao_colorida(None, molde, pontos, 1.0))

        self.assertIn("#00ff00", [chamada["cor"] for chamada in chamadas])
        self.assertIn("#ff0000", [chamada["cor"] for chamada in chamadas])
        self.assertNotIn("#9a9a9a", [chamada["cor"] for chamada in chamadas])

    def test_rascunho_por_indice_no_desenho_principal_nao_usa_contorno_branco(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        chamadas = []
        canvas._desenhar_polilinha = lambda _painter, _pontos, **kwargs: chamadas.append(kwargs)
        canvas._desenhar_preenchimento_molde = lambda *_args, **_kwargs: None
        canvas._desenhar_marcacoes_piques_elemento = lambda *_args, **_kwargs: None
        canvas._elemento_visivel_no_viewport = lambda _elemento: True
        canvas._indices_elementos_visiveis_viewport = lambda: [0]
        canvas._config_cor_molde = lambda _chave, padrao: padrao
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": False, "cor": "#00ff00"},
                {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "ponto": (0.0, 0.0),
                        "valores": {
                            "P": {"dx": -1.0, "dy": 0.0},
                            "G": {"dx": 1.0, "dy": 0.0},
                        },
                    }
                }
            },
        }
        canvas.cena.elementos = [dict(molde)]
        rascunho = dict(molde)
        rascunho["_indice_visualizacao_rascunho"] = 0
        canvas.set_visualizacao_rascunho([rascunho])

        canvas.paintEvent(None)

        cores = [chamada["cor"] for chamada in chamadas]
        self.assertEqual(cores[:2], ["#00ff00", "#ff0000"])
        self.assertNotIn("#9a9a9a", cores[:2])
        self.assertNotIn("#ffffff", cores[:2])

    def test_cache_graduacao_reaproveita_e_invalida_quando_tabela_muda(self):
        base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 5.0)]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "1": {
                        "ponto": (10.0, 0.0),
                        "valores": {"G": {"dx": 1.0, "dy": 0.0}},
                    }
                }
            },
        }

        contornos_1 = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)
        contornos_2 = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)
        caminhos_1 = VisualizacaoCanvas._caminhos_graduacao_tabela(molde, base)
        caminhos_2 = VisualizacaoCanvas._caminhos_graduacao_tabela(molde, base)

        self.assertIs(contornos_1, contornos_2)
        self.assertIs(caminhos_1, caminhos_2)

        molde["graduacao_tabela"]["pontos"]["1"]["valores"]["G"]["dx"] = 2.0
        contornos_3 = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)
        caminhos_3 = VisualizacaoCanvas._caminhos_graduacao_tabela(molde, base)

        self.assertIsNot(contornos_1, contornos_3)
        self.assertIsNot(caminhos_1, caminhos_3)
        self.assertEqual(contornos_3[0][2][1], QPointF(12.0, 0.0))
        self.assertEqual(caminhos_3[0][3], QPointF(12.0, 0.0))

    def test_cache_deslocamentos_piques_graduados_invalida_quando_tabela_muda(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "1": {
                        "ponto": (10.0, 0.0),
                        "valores": {"G": {"dx": 1.0, "dy": 0.0}},
                    }
                }
            },
        }
        base = canvas._base_contorno_graduacao(molde)
        linhas = canvas._linhas_graduacao_nao_base(molde)

        deslocamentos_1 = canvas._deslocamentos_piques_graduados_configurados(molde, base, linhas)
        deslocamentos_2 = canvas._deslocamentos_piques_graduados_configurados(molde, base, linhas)

        self.assertIs(deslocamentos_1, deslocamentos_2)

        molde["graduacao_tabela"]["pontos"]["1"]["valores"]["G"]["dx"] = 2.0
        deslocamentos_3 = canvas._deslocamentos_piques_graduados_configurados(molde, base, linhas)

        self.assertIsNot(deslocamentos_1, deslocamentos_3)
        self.assertEqual(deslocamentos_3["G"][1], (2.0, 0.0))

    def test_caminho_grade_usa_apenas_pontos_principais_em_curva_amostrada(self):
        base = [
            QPointF(0.0, 0.0),
            QPointF(2.0, 0.4),
            QPointF(4.0, 0.8),
            QPointF(6.0, 0.4),
            QPointF(8.0, 0.0),
        ]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 4.0, "y": 0.8},
                {"x": 8.0, "y": 0.0},
            ],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
            ],
            "graduacao_tabela": {
                "pontos": {
                    "0": {"ponto": (0.0, 0.0), "valores": {"G": {"dx": 0.0, "dy": 1.0}}},
                    "2": {"ponto": (8.0, 0.0), "valores": {"G": {"dx": 0.0, "dy": -1.0}}},
                }
            },
        }

        caminhos = VisualizacaoCanvas._caminhos_graduacao_tabela(molde, base)

        origens = [(origem.x(), origem.y()) for _nome, _cor, origem, _destino in caminhos]
        self.assertEqual(origens, [(0.0, 0.0), (8.0, 0.0)])

    def test_snap_gruda_no_ponto_do_tamanho_graduado(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 100.0
        canvas.resize(800, 600)
        canvas.cena.elementos = [
            {
                "tipo": "polyline",
                "molde": True,
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                "graduacao_tamanhos": [
                    {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                    {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
                ],
                "graduacao_tabela": {
                    "pontos": {
                        "1": {
                            "ponto": (10.0, 0.0),
                            "valores": {"G": {"dx": 0.0, "dy": 8.0}},
                        }
                    }
                },
            }
        ]

        ponto = canvas._ponto_com_snap(QPointF(1002.0, 801.0))

        self.assertEqual(canvas._snap_resultado.tipo, "graduação")
        self.assertEqual(ponto, QPointF(10.0, 8.0))

    def test_snap_gruda_na_borda_do_tamanho_graduado(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 100.0
        canvas.resize(800, 600)
        canvas.cena.elementos = [
            {
                "tipo": "polyline",
                "molde": True,
                "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
                "graduacao_tamanhos": [
                    {"ativo": True, "tamanho": "M", "base": True, "cor": "#ffffff"},
                    {"ativo": True, "tamanho": "G", "base": False, "cor": "#ff0000"},
                ],
                "graduacao_tabela": {
                    "pontos": {
                        "1": {
                            "ponto": (10.0, 0.0),
                            "valores": {"G": {"dx": 0.0, "dy": 8.0}},
                        }
                    }
                },
            }
        ]

        ponto = canvas._ponto_com_snap(QPointF(500.0, 400.0))

        self.assertEqual(canvas._snap_resultado.tipo, "borda graduação")
        self.assertAlmostEqual(ponto.x(), 5.0, places=3)
        self.assertAlmostEqual(ponto.y(), 4.0, places=3)

    def test_pique_da_base_aparece_nos_tamanhos_graduados(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        chamadas = []
        canvas._desenhar_segmento = lambda _painter, a, b, **kwargs: chamadas.append((QPointF(a), QPointF(b), kwargs))
        valores = {}
        pontos = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]
        for idx, ponto in enumerate(pontos):
            valores[str(idx)] = {
                "indice": idx,
                "ponto": ponto,
                "valores": {
                    "P": {"dx": 0.0, "dy": -2.0},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 0.0, "dy": 2.0},
                },
            }
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": pontos + [(0.0, 0.0)],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": False},
                {"ativo": True, "tamanho": "M", "base": True},
                {"ativo": True, "tamanho": "G", "base": False},
            ],
            "graduacao_tabela": {"pontos": valores},
            "piques_config": [
                {
                    "ponto": (5.0, 0.0),
                    "sobre_contorno": True,
                    "segmentos": [((5.0, 0.0), (5.0, 1.0))],
                }
            ],
        }

        canvas._desenhar_piques_configurados(object(), molde, "#ff00ff")

        segmentos = [((a.x(), a.y()), (b.x(), b.y())) for a, b, _kwargs in chamadas]
        self.assertIn(((5.0, 0.0), (5.0, 1.0)), segmentos)
        self.assertIn(((5.0, -2.0), (5.0, -1.0)), segmentos)
        self.assertIn(((5.0, 2.0), (5.0, 3.0)), segmentos)

    def test_graduacao_importada_preserva_faixas_sem_spline_visual(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        chamadas_suaves = []
        chamadas_retas = []
        canvas._desenhar_polilinha_suavizada = (
            lambda _painter, pontos, **kwargs: chamadas_suaves.append((len(pontos), kwargs))
        )
        canvas._desenhar_polilinha = lambda *args, **kwargs: chamadas_retas.append((args, kwargs))
        painter = SimpleNamespace(save=lambda: None, restore=lambda: None)
        molde = {
            "tipo": "polyline",
            "molde": True,
            "render_smooth": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": True, "cor": "#00d000"},
                {"ativo": True, "tamanho": "M", "base": False, "cor": "#0080ff"},
            ],
            "graduacao_contornos_importados": [
                {
                    "tamanho": "P",
                    "base": True,
                    "cor": "#00d000",
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
                },
                {
                    "tamanho": "M",
                    "base": False,
                    "cor": "#0080ff",
                    "pontos": [(-1.0, -1.0), (11.0, -1.0), (11.0, 9.0), (-1.0, 9.0), (-1.0, -1.0)],
                },
            ],
        }

        canvas._desenhar_graduacao_tabela_molde(painter, molde, canvas._base_graduacao_elemento(molde))

        self.assertEqual(len(chamadas_suaves), 1)
        self.assertEqual(len(chamadas_retas), 1)
        _args, kwargs_grade = chamadas_retas[0]
        self.assertEqual(kwargs_grade.get("cor"), "#0080ff")
        self.assertEqual(kwargs_grade.get("cache_key"), ("graduacao", "M"))
        self.assertIs(kwargs_grade.get("elemento"), molde)

    def test_graduacao_importada_pode_preferir_tabela_editavel(self):
        base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 8.0), QPointF(0.0, 8.0), QPointF(0.0, 0.0)]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(p.x(), p.y()) for p in base],
            "graduacao_preferir_tabela_dxdy": True,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": True, "cor": "#00d000"},
                {"ativo": True, "tamanho": "M", "base": False, "cor": "#0080ff"},
            ],
            "graduacao_tabela": {
                "modo": "dx_dy",
                "pontos": {
                    "0": {"indice": 0, "ponto": (0.0, 0.0), "valores": {"M": {"dx": 1.0, "dy": 2.0}}},
                    "1": {"indice": 1, "ponto": (10.0, 0.0), "valores": {"M": {"dx": 1.0, "dy": 2.0}}},
                    "2": {"indice": 2, "ponto": (10.0, 8.0), "valores": {"M": {"dx": 1.0, "dy": 2.0}}},
                    "3": {"indice": 3, "ponto": (0.0, 8.0), "valores": {"M": {"dx": 1.0, "dy": 2.0}}},
                },
            },
            "graduacao_contornos_importados": [
                {
                    "tamanho": "M",
                    "base": False,
                    "cor": "#0080ff",
                    "pontos": [(40.0, 0.0), (50.0, 0.0), (50.0, 8.0), (40.0, 8.0), (40.0, 0.0)],
                }
            ],
        }

        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)

        self.assertEqual(len(contornos), 1)
        _nome, _cor, pontos = contornos[0]
        self.assertEqual((pontos[0].x(), pontos[0].y()), (1.0, 2.0))
        molde["graduacao_tabela"]["pontos"]["0"]["valores"]["M"]["dx"] = 3.0
        contornos_editados = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)
        self.assertEqual((contornos_editados[0][2][0].x(), contornos_editados[0][2][0].y()), (3.0, 2.0))

    def test_dxf_agrupado_filtra_tabela_antiga_para_pontos_principais(self):
        base = [
            QPointF(0.0, 0.0),
            QPointF(2.0, 0.4),
            QPointF(4.0, 0.8),
            QPointF(6.0, 0.4),
            QPointF(8.0, 0.0),
            QPointF(8.0, 5.0),
            QPointF(0.0, 5.0),
            QPointF(0.0, 0.0),
        ]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "origem": "dxf_matriz_graduada",
            "pontos": [(p.x(), p.y()) for p in base],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 8.0, "y": 0.0},
                {"x": 8.0, "y": 5.0},
                {"x": 0.0, "y": 5.0},
            ],
            "graduacao_preferir_tabela_dxdy": True,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": True, "cor": "#00d000"},
                {"ativo": True, "tamanho": "M", "base": False, "cor": "#0080ff"},
            ],
            "graduacao_tabela": {
                "modo": "dx_dy",
                "pontos": {
                    "0": {"indice": 0, "ponto": (0.0, 0.0), "valores": {"M": {"dx": 0.0, "dy": 0.0}}},
                    "1": {"indice": 1, "ponto": (2.0, 0.4), "valores": {"M": {"dx": 100.0, "dy": 100.0}}},
                    "2": {"indice": 2, "ponto": (4.0, 0.8), "valores": {"M": {"dx": 100.0, "dy": 100.0}}},
                    "3": {"indice": 3, "ponto": (6.0, 0.4), "valores": {"M": {"dx": 100.0, "dy": 100.0}}},
                    "4": {"indice": 4, "ponto": (8.0, 0.0), "valores": {"M": {"dx": 1.0, "dy": 0.0}}},
                    "5": {"indice": 5, "ponto": (8.0, 5.0), "valores": {"M": {"dx": 1.0, "dy": 1.0}}},
                    "6": {"indice": 6, "ponto": (0.0, 5.0), "valores": {"M": {"dx": 0.0, "dy": 1.0}}},
                },
            },
        }

        referencias = VisualizacaoCanvas._pontos_referencia_graduacao(molde)
        pontos_cfg = VisualizacaoCanvas._pontos_cfg_graduacao(molde)
        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base[:-1])

        self.assertEqual(referencias, [QPointF(0.0, 0.0), QPointF(8.0, 0.0), QPointF(8.0, 5.0), QPointF(0.0, 5.0)])
        self.assertEqual(sorted(pontos_cfg), ["0", "1", "2", "3"])
        self.assertEqual(len(contornos), 1)
        _nome, _cor, pontos = contornos[0]
        self.assertLess(max(p.x() for p in pontos), 12.0)
        self.assertLess(max(p.y() for p in pontos), 8.0)

    def test_graduacao_importada_com_tabela_nao_editada_preserva_contorno_real(self):
        base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 8.0), QPointF(0.0, 8.0), QPointF(0.0, 0.0)]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(p.x(), p.y()) for p in base],
            "graduacao_preferir_tabela_dxdy": False,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": True, "cor": "#00d000"},
                {"ativo": True, "tamanho": "M", "base": False, "cor": "#0080ff"},
            ],
            "graduacao_tabela": {
                "modo": "dx_dy",
                "pontos": {
                    "0": {"indice": 0, "ponto": (0.0, 0.0), "valores": {"M": {"dx": 99.0, "dy": 99.0}}},
                    "1": {"indice": 1, "ponto": (10.0, 0.0), "valores": {"M": {"dx": 99.0, "dy": 99.0}}},
                },
            },
            "graduacao_contornos_importados": [
                {
                    "tamanho": "M",
                    "base": False,
                    "cor": "#0080ff",
                    "pontos": [(-1.0, -1.0), (11.0, -1.0), (11.0, 9.0), (-1.0, 9.0), (-1.0, -1.0)],
                }
            ],
        }

        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)

        self.assertEqual(len(contornos), 1)
        _nome, _cor, pontos = contornos[0]
        self.assertEqual((pontos[0].x(), pontos[0].y()), (-1.0, -1.0))

    def test_dxf_agrupado_preferindo_tabela_reflete_edicao_da_base(self):
        base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 8.0), QPointF(0.0, 8.0)]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "origem": "dxf_matriz_graduada",
            "pontos": [(p.x(), p.y()) for p in base],
            "controle_cantos": [(p.x(), p.y()) for p in base],
            "graduacao_preferir_tabela_dxdy": True,
            "graduacao_tabela_apenas_pontos_principais": True,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": True, "cor": "#ffff00"},
                {"ativo": True, "tamanho": "M", "base": False, "cor": "#0000ff"},
            ],
            "graduacao_tabela": {
                "modo": "dx_dy",
                "pontos": {
                    str(idx): {
                        "indice": idx,
                        "ponto": (p.x(), p.y()),
                        "valores": {"M": {"dx": 1.0, "dy": 0.5}},
                    }
                    for idx, p in enumerate(base)
                },
            },
            "graduacao_contornos_importados": [
                {
                    "tamanho": "M",
                    "base": False,
                    "cor": "#0000ff",
                    "pontos": [(100.0, 100.0), (110.0, 100.0), (110.0, 108.0), (100.0, 108.0)],
                }
            ],
        }

        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)
        self.assertEqual((contornos[0][2][0].x(), contornos[0][2][0].y()), (1.0, 0.5))

        base_editada = [QPointF(0.5, 0.25), *base[1:]]
        contornos_editados = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base_editada)

        self.assertEqual((contornos_editados[0][2][0].x(), contornos_editados[0][2][0].y()), (1.5, 0.75))

    def test_graduacao_importada_simplifica_faixas_durante_zoom_interativo(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas._zoom_interativo = True
        chamadas_suaves = []
        chamadas_retas = []
        canvas._desenhar_polilinha_suavizada = (
            lambda _painter, pontos, **kwargs: chamadas_suaves.append((len(pontos), kwargs))
        )
        canvas._desenhar_polilinha = lambda *args, **kwargs: chamadas_retas.append((args, kwargs))
        painter = SimpleNamespace(save=lambda: None, restore=lambda: None)
        molde = {
            "tipo": "polyline",
            "molde": True,
            "render_smooth": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": True, "cor": "#00d000"},
                {"ativo": True, "tamanho": "M", "base": False, "cor": "#0080ff"},
            ],
            "graduacao_contornos_importados": [
                {
                    "tamanho": "P",
                    "base": True,
                    "cor": "#00d000",
                    "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
                },
                {
                    "tamanho": "M",
                    "base": False,
                    "cor": "#0080ff",
                    "pontos": [(-1.0, -1.0), (11.0, -1.0), (11.0, 9.0), (-1.0, 9.0), (-1.0, -1.0)],
                },
            ],
        }

        canvas._desenhar_graduacao_tabela_molde(painter, molde, canvas._base_graduacao_elemento(molde))

        self.assertEqual(len(chamadas_suaves), 1)
        self.assertEqual(len(chamadas_retas), 1)
        _args, kwargs_grade = chamadas_retas[0]
        self.assertEqual(kwargs_grade.get("cor"), "#0080ff")
        self.assertEqual(kwargs_grade.get("cache_key"), ("graduacao", "M"))

    def test_suavizacao_visual_nao_trava_vertices_de_curva_importada(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        pontos = [
            QPointF(10.0, 0.0),
            QPointF(8.66, 5.0),
            QPointF(5.0, 8.66),
            QPointF(0.0, 10.0),
            QPointF(-5.0, 8.66),
            QPointF(-8.66, 5.0),
            QPointF(-10.0, 0.0),
            QPointF(-8.66, -5.0),
            QPointF(-5.0, -8.66),
            QPointF(0.0, -10.0),
            QPointF(5.0, -8.66),
            QPointF(8.66, -5.0),
            QPointF(10.0, 0.0),
        ]
        elemento = {
            "origem": "audaces_emf",
            "controle_cantos": [(p.x(), p.y()) for p in pontos[:-1]],
        }

        preservados = canvas._pontos_preservados_suavizacao(elemento, pontos)

        self.assertEqual(preservados, [])

    def test_suavizacao_visual_preserva_quinas_fortes(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        pontos = [
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 8.0),
            QPointF(0.0, 8.0),
            QPointF(0.0, 0.0),
        ]
        elemento = {
            "origem": "audaces_emf",
            "controle_cantos": [(p.x(), p.y()) for p in pontos[:-1]],
        }

        preservados = canvas._pontos_preservados_suavizacao(elemento, pontos)

        self.assertEqual(len(preservados), 8)

    def test_graduacao_regularizada_tem_prioridade_sobre_contorno_bruto_importado(self):
        base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 8.0), QPointF(0.0, 8.0), QPointF(0.0, 0.0)]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
            "graduacao_renderizar_regularizada": True,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": True, "cor": "#00d000"},
                {"ativo": True, "tamanho": "M", "base": False, "cor": "#0080ff"},
            ],
            "graduacao_contornos_importados": [
                {
                    "tamanho": "M",
                    "base": False,
                    "cor": "#0080ff",
                    "pontos": [(40.0, 0.0), (50.0, 0.0), (50.0, 8.0), (40.0, 8.0), (40.0, 0.0)],
                }
            ],
            "graduacao_contornos_regularizados_preview": [
                {
                    "tamanho": "M",
                    "base": False,
                    "cor": "#0080ff",
                    "pontos": [(20.0, 0.0), (30.0, 0.0), (30.0, 8.0), (20.0, 8.0), (20.0, 0.0)],
                }
            ],
        }

        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)

        self.assertEqual(len(contornos), 1)
        _nome, _cor, pontos = contornos[0]
        self.assertEqual(pontos[0].x(), 20.0)

    def test_graduacao_derivada_preserva_topologia_da_base_com_v(self):
        base = [
            QPointF(0.0, 0.0),
            QPointF(4.0, 0.0),
            QPointF(5.0, 2.0),
            QPointF(6.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 8.0),
            QPointF(0.0, 8.0),
            QPointF(0.0, 0.0),
        ]
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(p.x(), p.y()) for p in base],
            "graduacao_renderizar_por_tabela_derivada": True,
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "P", "base": True, "cor": "#00d000"},
                {"ativo": True, "tamanho": "M", "base": False, "cor": "#0080ff"},
            ],
            "graduacao_tabela_derivada": {
                "modo": "dx_dy",
                "base": "P",
                "pontos": {
                    "0": {"indice": 0, "ponto": (0.0, 0.0), "valores": {"M": {"dx": 1.0, "dy": 1.0}}},
                    "1": {"indice": 2, "ponto": (5.0, 2.0), "valores": {"M": {"dx": 1.0, "dy": 1.0}}},
                    "2": {"indice": 5, "ponto": (10.0, 8.0), "valores": {"M": {"dx": 1.0, "dy": 1.0}}},
                },
            },
            "graduacao_contornos_importados": [
                {
                    "tamanho": "M",
                    "base": False,
                    "cor": "#0080ff",
                    "pontos": [(-1.0, -1.0), (11.0, -1.0), (11.0, 9.0), (-1.0, 9.0), (-1.0, -1.0)],
                }
            ],
        }

        contornos = VisualizacaoCanvas._contornos_graduacao_tabela(molde, base)

        self.assertEqual(len(contornos), 1)
        _nome, _cor, pontos_m = contornos[0]
        self.assertEqual(len(pontos_m), len(base))
        self.assertTrue(any(abs(p.x() - 6.0) < 1e-6 and abs(p.y() - 3.0) < 1e-6 for p in pontos_m))

    def test_hit_test_em_contorno_importado_seleciona_molde_dono(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.zoom = 10.0
        molde = {
            "tipo": "polyline",
            "molde": True,
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            "graduacao_contornos_importados": [
                {
                    "tamanho": "M",
                    "base": False,
                    "pontos": [(20.0, 0.0), (30.0, 0.0), (30.0, 10.0), (20.0, 10.0), (20.0, 0.0)],
                }
            ],
        }
        canvas.cena.elementos = [molde]

        self.assertEqual(canvas._indices_elementos_em_ponto(QPointF(25.0, 0.0)), [0])

    def test_suavizacao_preserva_quina_importada_acima_de_90_graus(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        pontos = [
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(14.0, 8.0),
            QPointF(20.0, 8.0),
            QPointF(20.0, 12.0),
            QPointF(0.0, 12.0),
            QPointF(0.0, 0.0),
        ]

        quinas = canvas._quinas_contorno_para_suavizacao(pontos)

        self.assertIn((10.0, 0.0), [(p.x(), p.y()) for p in quinas])


if __name__ == "__main__":
    unittest.main()
