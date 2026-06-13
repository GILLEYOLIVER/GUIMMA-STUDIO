from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    FerramentaCostura = None
    FerramentaRemoverCostura = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from tools.costura_tool import Ferramenta as FerramentaCostura
    from tools.remover_costura_tool import Ferramenta as FerramentaRemoverCostura


@unittest.skipIf(FerramentaRemoverCostura is None, "PySide6 nao disponivel neste ambiente")
class RemoverCosturaToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    class _CenaFake:
        def __init__(self, elementos):
            self.elementos = elementos

    class _CanvasFake:
        def __init__(self, elementos):
            self.cena = RemoverCosturaToolTestCase._CenaFake(elementos)
            self.zoom = 10.0
            self.historico = 0
            self.atualizacoes = 0

        def _registrar_historico(self):
            self.historico += 1

        def update(self):
            self.atualizacoes += 1

    def _costura_tool(self):
        ferramenta = FerramentaCostura()
        ferramenta._tipo_operacao = lambda _canvas: "Costura"
        ferramenta._larguras_atuais = lambda _canvas: (1.0, 1.0, False)
        ferramenta._acabamentos_atuais = lambda _canvas: ("Canto reto", "Canto reto")
        return ferramenta

    def _molde_quadrado(self):
        return {
            "tipo": "polyline",
            "molde": True,
            "molde_id": "m1",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
        }

    def _molde_quadrado_graduado(self):
        molde = self._molde_quadrado()
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
                    "P": {"dx": -5.0, "dy": 0.0},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 5.0, "dy": 0.0},
                },
            }
            for idx, ponto in enumerate(molde["pontos"][:-1])
        }
        molde["graduacao_tabela"] = {"modo": "dx_dy", "pontos": valores}
        molde["graduacao_pontos"] = valores.copy()
        return molde

    def _molde_curvo_com_pontos_principais(self):
        return {
            "tipo": "polyline",
            "molde": True,
            "molde_id": "m1",
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

    def test_remover_selecionar_remove_trecho_principal_da_costura(self):
        canvas = self._CanvasFake([self._molde_quadrado()])
        costura = self._costura_tool()
        self.assertTrue(costura._aplicar_em_indices(canvas, [0]))
        ferramenta = FerramentaRemoverCostura()

        removidos = ferramenta._remover_segmento_costura_molde(canvas, "m1", 1, 1)

        self.assertEqual(removidos, 1)
        costura_el = next(el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura")
        self.assertTrue(costura_el["costura_parcial"])
        self.assertNotIn(1, costura_el["costura_segmentos"])
        self.assertEqual(set(costura_el["costura_segmentos"]), {0, 2, 3})

    def test_remover_ultimo_trecho_apaga_costura_vinculada(self):
        canvas = self._CanvasFake([self._molde_quadrado()])
        costura = self._costura_tool()
        self.assertTrue(costura._aplicar_segmentos(canvas, 0, {1}, [1]))
        ferramenta = FerramentaRemoverCostura()

        removidos = ferramenta._remover_segmento_costura_molde(canvas, "m1", 1, 1)

        self.assertEqual(removidos, 1)
        self.assertFalse(any(el.get("subtipo_audaces") == "costura" for el in canvas.cena.elementos))

    def test_detectar_trecho_curvo_usa_pontos_principais_e_nao_pedacinhos(self):
        canvas = self._CanvasFake([self._molde_curvo_com_pontos_principais()])
        costura = self._costura_tool()
        self.assertTrue(costura._aplicar_segmentos(canvas, 0, {2}, [2]))
        ferramenta = FerramentaRemoverCostura()
        costura_el = next(el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura")
        pontos_trecho = ferramenta._pontos_costura_segmento(canvas, canvas.cena.elementos[0], costura_el, 2)
        pos = QPointF(pontos_trecho[len(pontos_trecho) // 2])

        alvo = ferramenta._detectar_alvo_segmento(canvas, pos)

        self.assertIsNotNone(alvo)
        self.assertEqual(alvo["segmento"], 2)

    def test_remover_trecho_base_reflete_para_costuras_graduadas(self):
        canvas = self._CanvasFake([self._molde_quadrado_graduado()])
        costura = self._costura_tool()
        self.assertTrue(costura._aplicar_em_indices(canvas, [0]))
        ferramenta = FerramentaRemoverCostura()
        base_idx = next(
            idx
            for idx, el in enumerate(canvas.cena.elementos)
            if el.get("subtipo_audaces") == "costura" and not el.get("costura_graduacao")
        )

        removidos = ferramenta._remover_segmento_costura_molde(canvas, "m1", base_idx, 1)

        self.assertEqual(removidos, 1)
        costuras = [el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura"]
        self.assertEqual(len(costuras), 3)
        self.assertEqual(sorted(el.get("graduacao_tamanho") or "M" for el in costuras), ["G", "M", "P"])
        for el in costuras:
            self.assertTrue(el["costura_parcial"])
            self.assertNotIn(1, el["costura_segmentos"])
            self.assertEqual(set(el["costura_segmentos"]), {0, 2, 3})

    def test_detector_de_remocao_ignora_costura_graduada(self):
        canvas = self._CanvasFake([self._molde_quadrado_graduado()])
        canvas.zoom = 20.0
        costura = self._costura_tool()
        self.assertTrue(costura._aplicar_em_indices(canvas, [0]))
        ferramenta = FerramentaRemoverCostura()
        graduada = next(el for el in canvas.cena.elementos if el.get("costura_graduacao"))
        pontos = [QPointF(float(x), float(y)) for x, y in graduada["pontos"]]
        pos = QPointF(pontos[3].x(), (pontos[3].y() + pontos[0].y()) / 2.0)

        alvo = ferramenta._detectar_alvo_segmento(canvas, pos)

        self.assertIsNone(alvo)

    def test_realce_de_remocao_mostra_apenas_costura_base(self):
        canvas = self._CanvasFake([self._molde_quadrado_graduado()])
        costura = self._costura_tool()
        self.assertTrue(costura._aplicar_em_indices(canvas, [0]))
        ferramenta = FerramentaRemoverCostura()
        base_idx, base_costura = next(
            (idx, el)
            for idx, el in enumerate(canvas.cena.elementos)
            if el.get("subtipo_audaces") == "costura" and not el.get("costura_graduacao")
        )
        pontos = ferramenta._pontos_costura_segmento(canvas, canvas.cena.elementos[0], base_costura, 1)
        pos = QPointF(pontos[len(pontos) // 2])

        alvo = ferramenta._detectar_alvo_segmento(canvas, pos)
        self.assertIsNotNone(alvo)
        self.assertEqual(alvo["indice"], base_idx)
        ferramenta._preparar_realce(canvas, alvo)

        self.assertEqual(len(ferramenta._realce_polylines), 1)
        self.assertEqual(ferramenta._realce_segmentos, [])


if __name__ == "__main__":
    unittest.main()
