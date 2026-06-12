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
    from PySide6.QtCore import QPointF, Qt
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


if __name__ == "__main__":
    unittest.main()
