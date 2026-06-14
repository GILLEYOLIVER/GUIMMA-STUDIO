from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    FerramentaCostura = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from tools.costura_tool import CosturaDialog, Ferramenta as FerramentaCostura


@unittest.skipIf(FerramentaCostura is None, "PySide6 nao disponivel neste ambiente")
class CosturaToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    class _CenaFake:
        def __init__(self, elementos):
            self.elementos = elementos

    class _CanvasFake:
        def __init__(self, elementos):
            self.cena = CosturaToolTestCase._CenaFake(elementos)
            self.historico = 0
            self.atualizacoes = 0

        def _registrar_historico(self):
            self.historico += 1

        def update(self):
            self.atualizacoes += 1

        def _cena_para_tela(self, ponto):
            return QPointF(ponto)

    def _elemento_molde_curvo(self):
        return {
            "tipo": "polyline",
            "molde": True,
            "pontos": [
                (0.0, 0.0),
                (10.0, 0.0),
                (10.0, 10.0),
                (8.0, 11.0),
                (5.0, 12.0),
                (2.0, 11.0),
                (0.0, 10.0),
                (0.0, 0.0),
            ],
            "controle_cantos": [
                (0.0, 0.0),
                (10.0, 0.0),
                (10.0, 10.0),
                (0.0, 10.0),
            ],
            "pontos_controle_principais": [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 10.0},
                {"x": 0.0, "y": 10.0},
            ],
        }

    def _elemento_quadrado(self):
        return {
            "tipo": "polyline",
            "molde": True,
            "molde_id": "m1",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
        }

    def _elemento_quadrado_graduado(self):
        molde = self._elemento_quadrado()
        molde["graduacao_tamanhos"] = [
            {"ativo": True, "tamanho": "P", "cor": "#111111", "base": False},
            {"ativo": True, "tamanho": "M", "cor": "#222222", "base": True},
            {"ativo": True, "tamanho": "G", "cor": "#333333", "base": False},
        ]
        valores = {
            str(idx): {
                "indice": idx,
                "numero": idx + 1,
                "ponto": ponto,
                "valores": {
                    "P": {"dx": -1.0, "dy": 0.0},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 2.0, "dy": 0.0},
                },
            }
            for idx, ponto in enumerate(molde["pontos"][:-1])
        }
        molde["graduacao_tabela"] = {"modo": "dx_dy", "pontos": valores}
        molde["graduacao_pontos"] = valores.copy()
        return molde

    def _costura_existente(self, segmentos):
        return {
            "tipo": "polyline",
            "subtipo_audaces": "costura",
            "costura_de_molde_id": "m1",
            "molde_id": "m1",
            "costura_segmentos": list(segmentos),
            "costura_parcial": True,
            "pontos": [(-99.0, -99.0), (-98.0, -98.0)],
        }

    def _preparar_ferramenta_sem_dialog(self):
        ferramenta = FerramentaCostura()
        ferramenta._tipo_operacao = lambda _canvas: "Costura"
        ferramenta._larguras_atuais = lambda _canvas: (1.0, 1.0, False)
        ferramenta._acabamentos_atuais = lambda _canvas: ("Canto reto", "Canto reto")
        return ferramenta

    def test_dialog_acabamento_tem_opcoes_visuais_da_referencia(self):
        dialog = CosturaDialog()
        self.addCleanup(dialog.close)
        esperados = [
            "Canto reto",
            "V aberto",
            "V fechado",
            "Degrau",
            "45 graus",
            "90 graus",
            "90 graus invertido",
        ]

        self.assertEqual(CosturaDialog.nomes_acabamentos(), esperados)
        self.assertEqual([dialog.cmb_acab_ini.itemData(i) for i in range(dialog.cmb_acab_ini.count())], esperados)
        self.assertEqual([dialog.cmb_acab_fim.itemData(i) for i in range(dialog.cmb_acab_fim.count())], esperados)
        self.assertFalse(dialog.cmb_acab_ini.itemIcon(0).isNull())

    def test_acabamento_90_graus_invertido_gera_degrau_oposto(self):
        ferramenta = FerramentaCostura()

        pontos = ferramenta._pontos_acabamento_livre(
            (0.0, 0.0),
            (0.0, 1.0),
            (1.0, 0.0),
            1.0,
            "90 graus invertido",
            inicio=True,
        )

        self.assertEqual(pontos, [(0.0, 0.0), (0.0, 1.0), (-1.0, 1.0)])

    def test_segmentos_seguem_perimetro_real_em_molde_concavo(self):
        ferramenta = FerramentaCostura()
        base = [(0, 0), (6, 0), (6, 1), (2, 1), (2, 4), (6, 4), (6, 5), (0, 5)]

        ordem = ferramenta._segmentos_horarios(base, 1, 5)

        self.assertEqual(ordem, [1, 2, 3, 4, 5])

    def test_costura_parcial_em_canto_reto_fecha_inicio_e_fim(self):
        ferramenta = FerramentaCostura()
        pontos = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]

        costura = ferramenta._gerar_costura_segmentos_variavel(
            pontos,
            [1],
            1.0,
            1.0,
            "Canto reto",
            "Canto reto",
        )

        self.assertEqual(costura, [(10, 0), (11.0, 0.0), (11.0, 10.0), (10, 10)])

    def test_costura_total_em_canto_reto_e_contorno_fechado_sem_chanfro(self):
        ferramenta = FerramentaCostura()
        pontos = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]

        costura = ferramenta._gerar_costura(pontos, 1.0)

        self.assertEqual(costura, [(-1.0, -1.0), (11.0, -1.0), (11.0, 11.0), (-1.0, 11.0), (-1.0, -1.0)])

    def test_molde_curvo_usa_trechos_entre_pontos_principais(self):
        ferramenta = FerramentaCostura()
        elemento = self._elemento_molde_curvo()

        trechos = ferramenta._segmentos_interativos_elemento(elemento)

        self.assertEqual(len(trechos), 4)
        self.assertGreater(len(trechos[2]), 2)
        self.assertEqual(trechos[2][0], (10.0, 10.0))
        self.assertEqual(trechos[2][-1], (0.0, 10.0))

    def test_molde_curvo_tolera_controle_principal_levemente_fora_da_amostragem(self):
        ferramenta = FerramentaCostura()
        elemento = self._elemento_molde_curvo()
        elemento["controle_cantos"][2] = (10.0, 10.5)
        elemento["pontos_controle_principais"][2] = {"x": 10.0, "y": 10.5}

        trechos = ferramenta._segmentos_interativos_elemento(elemento)

        self.assertEqual(len(trechos), 4)
        self.assertEqual(trechos[1][-1], (10.0, 10.5))
        self.assertEqual(trechos[2][0], (10.0, 10.5))

    def test_costura_principal_parcial_canto_reto_fecha_inicio_e_fim(self):
        ferramenta = FerramentaCostura()
        elemento = self._elemento_quadrado()
        elemento["controle_cantos"] = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        elemento["pontos_controle_principais"] = [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 10.0},
            {"x": 0.0, "y": 10.0},
        ]
        contorno = ferramenta._contorno_principal_elemento(elemento)
        self.assertIsNotNone(contorno)
        controles, _indices, trechos = contorno

        costura = ferramenta._gerar_costura_principal_por_ordem(
            controles,
            trechos,
            [1],
            1.0,
            1.0,
            False,
            selecao_total=False,
        )

        self.assertEqual(costura, [(10.0, 0.0), (11.0, 0.0), (11.0, 10.0), (10.0, 10.0)])

    def test_costura_principal_total_curva_fechada_sem_espinhos(self):
        ferramenta = FerramentaCostura()
        elemento = self._elemento_molde_curvo()
        contorno = ferramenta._contorno_principal_elemento(elemento)
        self.assertIsNotNone(contorno)
        controles, _indices, trechos = contorno

        costura = ferramenta._gerar_costura_principal_por_ordem(
            controles,
            trechos,
            [0, 1, 2, 3],
            1.0,
            1.0,
            False,
            selecao_total=True,
        )

        self.assertEqual(costura[0], costura[-1])
        self.assertGreater(len(costura), 5)
        xs = [p[0] for p in costura]
        ys = [p[1] for p in costura]
        self.assertGreaterEqual(min(xs), -2.0)
        self.assertLessEqual(max(xs), 12.0)
        self.assertGreaterEqual(min(ys), -2.0)
        self.assertLessEqual(max(ys), 13.5)

    def test_costura_por_trecho_separado_adiciona_sem_apagar_trecho_existente(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        canvas = self._CanvasFake([self._elemento_quadrado(), self._costura_existente([0])])

        self.assertTrue(ferramenta._aplicar_segmentos(canvas, 0, {2}, [2]))

        costuras = [el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura"]
        self.assertEqual(sorted(tuple(el.get("costura_segmentos", [])) for el in costuras), [(0,), (2,)])
        self.assertEqual(canvas.historico, 1)
        self.assertEqual(canvas.atualizacoes, 1)

    def test_costura_por_trecho_adjacente_mescla_e_fecha_canto_comum(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        canvas = self._CanvasFake([self._elemento_quadrado(), self._costura_existente([0])])

        self.assertTrue(ferramenta._aplicar_segmentos(canvas, 0, {1}, [1]))

        costuras = [el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura"]
        self.assertEqual(len(costuras), 1)
        self.assertEqual(costuras[0].get("costura_segmentos"), [0, 1])
        self.assertNotIn((10.0, 0.0), costuras[0].get("pontos", [])[1:-1])

    def test_costura_por_trecho_substitui_apenas_trecho_sobreposto(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        canvas = self._CanvasFake([self._elemento_quadrado(), self._costura_existente([1])])

        self.assertTrue(ferramenta._aplicar_segmentos(canvas, 0, {1}, [1]))

        costuras = [el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura"]
        self.assertEqual(len(costuras), 1)
        self.assertEqual(costuras[0].get("costura_segmentos"), [1])
        self.assertNotEqual(costuras[0].get("pontos"), [(-99.0, -99.0), (-98.0, -98.0)])

    def test_costura_total_cria_costura_para_todos_tamanhos_graduados(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        canvas = self._CanvasFake([self._elemento_quadrado_graduado()])

        self.assertTrue(ferramenta._aplicar_em_indices(canvas, [0]))

        costuras = [el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura"]
        self.assertEqual(len(costuras), 3)
        self.assertEqual(sorted(el.get("graduacao_tamanho") or "M" for el in costuras), ["G", "M", "P"])
        graduadas = {el["graduacao_tamanho"]: el for el in costuras if el.get("costura_graduacao")}
        self.assertEqual(set(graduadas), {"P", "G"})
        self.assertEqual(graduadas["P"]["pontos"][0], (-2.0, -1.0))
        self.assertEqual(graduadas["G"]["pontos"][0], (1.0, -1.0))

    def test_costura_por_trecho_cria_costura_para_todos_tamanhos_graduados(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        canvas = self._CanvasFake([self._elemento_quadrado_graduado()])

        self.assertTrue(ferramenta._aplicar_segmentos(canvas, 0, {1}, [1]))

        costuras = [el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura"]
        self.assertEqual(len(costuras), 3)
        self.assertTrue(all(el.get("costura_parcial") for el in costuras))
        self.assertTrue(all(el.get("costura_segmentos") == [1] for el in costuras))
        graduadas = {el["graduacao_tamanho"]: el for el in costuras if el.get("costura_graduacao")}
        self.assertEqual(graduadas["P"]["pontos"], [(9.0, 0.0), (10.0, 0.0), (10.0, 10.0), (9.0, 10.0)])
        self.assertEqual(graduadas["G"]["pontos"], [(12.0, 0.0), (13.0, 0.0), (13.0, 10.0), (12.0, 10.0)])

    def test_costura_total_recalcula_quando_perimetro_do_molde_muda(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        canvas = self._CanvasFake([self._elemento_quadrado()])
        self.assertTrue(ferramenta._aplicar_em_indices(canvas, [0]))
        molde = canvas.cena.elementos[0]
        molde["pontos"] = [(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0), (0.0, 0.0)]

        self.assertTrue(ferramenta.sincronizar_costuras_vinculadas(canvas))

        costura = next(el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura")
        self.assertEqual(costura["pontos"], [(-1.0, -1.0), (21.0, -1.0), (21.0, 11.0), (-1.0, 11.0), (-1.0, -1.0)])

    def test_costura_por_trecho_recalcula_quando_perimetro_do_molde_muda(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        canvas = self._CanvasFake([self._elemento_quadrado()])
        self.assertTrue(ferramenta._aplicar_segmentos(canvas, 0, {1}, [1]))
        molde = canvas.cena.elementos[0]
        molde["pontos"] = [(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0), (0.0, 0.0)]

        self.assertTrue(ferramenta.sincronizar_costuras_vinculadas(canvas))

        costura = next(el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura")
        self.assertEqual(costura["pontos"], [(20.0, 0.0), (21.0, 0.0), (21.0, 10.0), (20.0, 10.0)])

    def test_inserir_costura_preserva_perimetro_do_molde_e_limpa_preview(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        molde = self._elemento_quadrado()
        pontos_originais = list(molde["pontos"])
        canvas = self._CanvasFake([molde])
        ferramenta._preview = [object(), object()]
        ferramenta._preview_conectores = [(object(), object())]
        ferramenta._preview_idx = 0
        ferramenta._hover_segmento = (0, 0)
        ferramenta._realce_segmentos = [(object(), object())]

        self.assertTrue(ferramenta._aplicar_segmentos(canvas, 0, {1}, [1]))

        self.assertEqual(canvas.cena.elementos[0]["pontos"], pontos_originais)
        self.assertEqual(ferramenta._preview, [])
        self.assertEqual(ferramenta._preview_conectores, [])
        self.assertIsNone(ferramenta._preview_idx)
        self.assertIsNone(ferramenta._hover_segmento)
        self.assertEqual(ferramenta._realce_segmentos, [])

    def test_costura_importada_do_audaces_nao_some_ao_inserir_nova_costura(self):
        ferramenta = self._preparar_ferramenta_sem_dialog()
        costura_importada = {
            "tipo": "polyline",
            "subtipo_audaces": "costura",
            "molde_id": "m1",
            "costura_de_molde_id": "m1",
            "origem": "audaces_emf",
            "metadados": {"origem": "audaces_emf", "subtipo_audaces": "costura"},
            "pontos": [(1.0, 1.0), (9.0, 1.0), (9.0, 9.0), (1.0, 9.0), (1.0, 1.0)],
        }
        canvas = self._CanvasFake([self._elemento_quadrado(), costura_importada])

        self.assertTrue(ferramenta._aplicar_em_indices(canvas, [0]))

        self.assertIn(costura_importada, canvas.cena.elementos)
        costuras_novas = [
            el
            for el in canvas.cena.elementos
            if el is not costura_importada and el.get("metadados", {}).get("tipo_ferramenta") == ferramenta.id_ferramenta
        ]
        self.assertEqual(len(costuras_novas), 1)


if __name__ == "__main__":
    unittest.main()
