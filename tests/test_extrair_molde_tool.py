from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from math import cos, pi, sin
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaExtrairMolde = None
    QApplication = None
    QPointF = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from tools.extrair_molde_tool import Ferramenta as FerramentaExtrairMolde


class _FakeEvent:
    def __init__(self, pos):
        self._pos = pos
        self.accepted = False

    def position(self):
        return self._pos

    def accept(self):
        self.accepted = True


class _FakeCanvasExtracao:
    def __init__(self):
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (10.0, 0.0)],
                    "controle_cantos": [(0.0, 0.0)],
                    "controle_auxiliares": [],
                    "pontos_controle_principais": [{"x": 0.0, "y": 0.0}],
                    "pontos_auxiliares": [],
                }
            ]
        )
        self._selecionados = {0}
        self.snap_usado = 0
        self.atualizou = False

    def width(self):
        return 200

    def height(self):
        return 200

    def mapFromGlobal(self, _pos):
        raise RuntimeError("sem cursor global no teste")

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _ponto_com_snap(self, _pos):
        self.snap_usado += 1
        return QPointF(999.0, 999.0)

    def update(self):
        self.atualizou = True


class _FakeCanvasCriacaoMolde:
    def __init__(self):
        self.cena = SimpleNamespace(elementos=[])
        self._selecionados = {99}

    def _registrar_historico(self):
        pass

    def update(self):
        pass


@unittest.skipIf(FerramentaExtrairMolde is None, "PySide6 não disponível neste ambiente")
class ExtrairMoldeToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_enriquecer_molde_reto_insere_um_auxiliar_por_trecho(self):
        ferramenta = FerramentaExtrairMolde()
        molde = {
            "tipo": "molde",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0), (0.0, 0.0)],
            "preservar_todos_vertices_controle": True,
        }

        ferramenta._enriquecer_metadados_molde(molde)

        auxiliares = molde["controle_auxiliares"]
        self.assertEqual(len(auxiliares), 4)
        self.assertIn((5.0, 0.0), auxiliares)
        self.assertIn((10.0, 2.0), auxiliares)
        self.assertIn((5.0, 4.0), auxiliares)
        self.assertIn((0.0, 2.0), auxiliares)
        self.assertEqual(molde["pontos_auxiliares"], [{"x": x, "y": y} for x, y in auxiliares])

    def test_auxiliares_detectados_na_curva_preservam_trecho_sem_ponto_extra(self):
        ferramenta = FerramentaExtrairMolde()
        base = [
            (0.0, 0.0),
            (5.0, 0.0),
            (10.0, 0.0),
            (10.0, 4.0),
            (0.0, 4.0),
        ]

        auxiliares = ferramenta._calcular_auxiliares_no_contorno(base, [0, 2, 3, 4])

        self.assertIn((5.0, 0.0), auxiliares)
        self.assertIn((10.0, 2.0), auxiliares)
        self.assertIn((5.0, 4.0), auxiliares)
        self.assertIn((0.0, 2.0), auxiliares)
        self.assertEqual(len(auxiliares), 4)

    def test_contorno_quase_circular_usa_um_principal_e_varios_auxiliares(self):
        ferramenta = FerramentaExtrairMolde()
        pontos = [
            (10.0 + cos((2.0 * pi * i) / 48.0) * 5.0, 8.0 + sin((2.0 * pi * i) / 48.0) * 4.4)
            for i in range(48)
        ]
        molde = {"tipo": "molde", "pontos": [*pontos, pontos[0]]}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertEqual(len(molde["controle_cantos"]), 1)
        self.assertGreaterEqual(len(molde["controle_auxiliares"]), 8)
        self.assertLessEqual(len(molde["controle_auxiliares"]), 24)

    def test_contorno_oval_largo_usa_um_principal_e_varios_auxiliares(self):
        ferramenta = FerramentaExtrairMolde()
        pontos = [
            (20.0 + cos((2.0 * pi * i) / 72.0) * 12.0, 10.0 + sin((2.0 * pi * i) / 72.0) * 5.0)
            for i in range(72)
        ]
        molde = {"tipo": "molde", "pontos": [*pontos, pontos[0]]}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertEqual(len(molde["controle_cantos"]), 1)
        self.assertGreaterEqual(len(molde["controle_auxiliares"]), 8)
        self.assertLessEqual(len(molde["controle_auxiliares"]), 24)

    def test_contorno_curvo_com_uma_ponta_usa_a_ponta_como_principal(self):
        ferramenta = FerramentaExtrairMolde()
        pontos = [
            (10.0, 0.0),
            (6.0, 3.0),
            (0.0, 5.0),
            (-7.0, 3.0),
            (-9.0, 0.0),
            (-7.0, -3.0),
            (0.0, -5.0),
            (6.0, -3.0),
        ]
        molde = {"tipo": "molde", "pontos": [*pontos, pontos[0]]}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertEqual(molde["controle_cantos"], [(10.0, 0.0)])
        self.assertGreaterEqual(len(molde["controle_auxiliares"]), 8)
        self.assertLessEqual(len(molde["controle_auxiliares"]), 24)

    def test_contorno_curvo_com_duas_pontas_numera_esquerda_antes_da_direita(self):
        ferramenta = FerramentaExtrairMolde()
        pontos = [
            (10.0, 0.0),
            (7.0, 2.4),
            (2.0, 3.5),
            (-4.0, 3.1),
            (-10.0, 0.0),
            (-4.0, -3.1),
            (2.0, -3.5),
            (7.0, -2.4),
        ]
        molde = {"tipo": "molde", "pontos": [*pontos, pontos[0]]}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertEqual(molde["controle_cantos"], [(-10.0, 0.0), (10.0, 0.0)])
        self.assertEqual(
            molde["pontos_controle_principais"],
            [{"x": -10.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
        )

    def test_trecho_curvo_longo_recebe_mais_auxiliares_para_definicao(self):
        ferramenta = FerramentaExtrairMolde()
        trecho = [(float(x), (float(x) - 5.0) ** 2 * 0.18) for x in range(11)]

        auxiliares = ferramenta._auxiliares_para_trecho_curvo(trecho)

        self.assertGreaterEqual(len(auxiliares), 2)
        self.assertLessEqual(len(auxiliares), 6)

    def test_contorno_com_muitas_quinas_cria_principal_por_quina_e_um_auxiliar_por_trecho(self):
        ferramenta = FerramentaExtrairMolde()
        pontos = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 4.0),
            (6.0, 4.0),
            (6.0, 8.0),
            (0.0, 8.0),
        ]
        molde = {"tipo": "molde", "pontos": [*pontos, pontos[0]]}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertEqual(len(molde["controle_cantos"]), 6)
        self.assertEqual(len(molde["controle_auxiliares"]), 6)

    def test_encontro_de_linhas_no_contorno_vira_ponto_principal(self):
        ferramenta = FerramentaExtrairMolde()
        canvas = SimpleNamespace(
            cena=SimpleNamespace(
                elementos=[
                    {"tipo": "polyline", "pontos": [(0.0, 0.0), (10.0, 0.0)]},
                    {"tipo": "polyline", "pontos": [(10.0, 0.0), (10.0, 8.0)]},
                    {"tipo": "polyline", "pontos": [(10.0, 8.0), (0.0, 8.0), (0.0, 0.0)]},
                ]
            )
        )
        contorno = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)]

        encontros = ferramenta._coletar_interseccoes_no_contorno(canvas, contorno)

        self.assertIn((10.0, 0.0), encontros)
        molde = {"tipo": "molde", "pontos": contorno, "pontos_interseccao_referencia": encontros}
        ferramenta._enriquecer_metadados_molde(molde)
        self.assertIn((10.0, 0.0), molde["controle_cantos"])

    def test_emenda_colinear_de_trechos_distintos_vira_principal_sem_vertices_internos(self):
        ferramenta = FerramentaExtrairMolde()
        canvas = SimpleNamespace(
            cena=SimpleNamespace(
                elementos=[
                    {"tipo": "polyline", "pontos": [(0.0, 0.0), (5.0, 0.0)]},
                    {"tipo": "polyline", "pontos": [(5.0, 0.0), (10.0, 0.0)]},
                    {"tipo": "polyline", "pontos": [(10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)]},
                ]
            )
        )
        contorno = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)]

        encontros = ferramenta._coletar_interseccoes_no_contorno(canvas, contorno)
        molde = {"tipo": "molde", "pontos": contorno, "pontos_interseccao_referencia": encontros}
        ferramenta._enriquecer_metadados_molde(molde)

        self.assertIn((5.0, 0.0), encontros)
        self.assertEqual(molde["controle_cantos"], [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)])
        self.assertIn((2.5, 0.0), molde["controle_auxiliares"])

    def test_controles_da_curva_de_origem_nao_viram_principais_na_extracao(self):
        ferramenta = FerramentaExtrairMolde()
        contorno = [
            (0.0, 0.0),
            (4.0, -2.0),
            (8.0, 0.0),
            (10.0, 5.0),
            (5.0, 8.0),
            (0.0, 5.0),
            (0.0, 0.0),
        ]
        canvas = SimpleNamespace(
            cena=SimpleNamespace(
                elementos=[
                    {
                        "tipo": "polyline",
                        "pontos": contorno,
                        "curva_suave": True,
                        "pontos_tracado_real": True,
                        "pontos_controle_principais": [
                            {"x": 4.0, "y": -2.0},
                            {"x": 10.0, "y": 5.0},
                        ],
                    }
                ]
            )
        )

        refs = ferramenta._coletar_pontos_controle_existentes(canvas, contorno)

        self.assertEqual(refs, [])

    def test_referencia_de_emenda_suprime_principais_inferidos_por_curvatura(self):
        ferramenta = FerramentaExtrairMolde()
        contorno = [
            (0.0, 0.0),
            (4.0, -2.0),
            (8.0, 0.0),
            (10.0, 5.0),
            (5.0, 8.0),
            (0.0, 5.0),
            (0.0, 0.0),
        ]
        molde = {"tipo": "molde", "pontos": contorno, "pontos_interseccao_referencia": [(8.0, 0.0)]}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertEqual(molde["controle_cantos"], [(8.0, 0.0)])
        self.assertIn((4.0, -2.0), molde["controle_auxiliares"])

    def test_arraste_do_molde_extraido_nao_usa_snap_para_evitar_tremor(self):
        canvas = _FakeCanvasExtracao()
        ferramenta = FerramentaExtrairMolde()
        ferramenta._arrastando_molde = True
        ferramenta._ultimo_pos_arrasto = QPointF(0.0, 0.0)
        ferramenta._selecoes_manuais = {0}

        self.assertTrue(ferramenta.on_mouse_move(canvas, _FakeEvent(QPointF(10.0, 0.0))))

        self.assertEqual(canvas.snap_usado, 0)
        self.assertEqual(canvas.cena.elementos[0]["pontos"], [(10.0, 0.0), (20.0, 0.0)])
        self.assertTrue(canvas.atualizou)

    def test_molde_extraido_por_contorno_nasce_sem_selecao_no_canvas(self):
        canvas = _FakeCanvasCriacaoMolde()
        ferramenta = FerramentaExtrairMolde()

        ok = ferramenta._criar_molde_de_contorno_extraido(
            canvas,
            [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
        )

        self.assertTrue(ok)
        self.assertEqual(len(canvas.cena.elementos), 1)
        self.assertEqual(canvas._selecionados, set())
        self.assertEqual(ferramenta._selecoes_manuais, {0})

    def test_molde_composto_nasce_sem_selecao_no_canvas(self):
        canvas = _FakeCanvasCriacaoMolde()
        canvas.cena.elementos = [
            {"tipo": "polyline", "pontos": [(0.0, 0.0), (10.0, 0.0)]},
            {"tipo": "polyline", "pontos": [(10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)]},
        ]
        ferramenta = FerramentaExtrairMolde()

        ok = ferramenta._criar_molde_composto(canvas, [0, 1])

        self.assertTrue(ok)
        self.assertEqual(canvas._selecionados, set())
        self.assertEqual(ferramenta._selecoes_manuais, {2})


if __name__ == "__main__":
    unittest.main()
