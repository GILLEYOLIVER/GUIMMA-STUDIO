from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    VisualizacaoCanvas = None
    CenaDocumento = None
else:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
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

    def test_cache_bbox_invalida_quando_pontos_sao_substituidos(self):
        canvas = VisualizacaoCanvas(CenaDocumento())
        canvas.resize(800, 600)
        canvas.zoom = 10.0
        canvas.origem_cena = QPointF(0.0, 0.0)
        elemento = {"tipo": "polyline", "pontos": [(1.0, 1.0), (2.0, 2.0)]}

        self.assertTrue(canvas._elemento_visivel_no_viewport(elemento))
        elemento["pontos"] = [(500.0, 500.0), (510.0, 510.0)]

        self.assertFalse(canvas._elemento_visivel_no_viewport(elemento))

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


if __name__ == "__main__":
    unittest.main()
