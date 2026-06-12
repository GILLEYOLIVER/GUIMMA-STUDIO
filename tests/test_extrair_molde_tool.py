from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from math import atan2, cos, pi, sin
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
        self._linha_espessura = 5.0
        self._linha_estilo = "solid"
        self._linha_amplitude = 1.0

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

    def test_enriquecer_molde_usa_espessura_atual_e_todos_pontos_como_graduaveis(self):
        ferramenta = FerramentaExtrairMolde()
        ferramenta._canvas = _FakeCanvasCriacaoMolde()
        pontos = [(0.0, 0.0), (4.0, 0.5), (8.0, 0.0), (8.0, 4.0), (0.0, 4.0), (0.0, 0.0)]
        molde = {"tipo": "molde", "pontos": pontos, "preservar_todos_vertices_controle": True}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertEqual(molde["espessura"], 5.0)
        self.assertEqual(molde["espessura_graduacao"], 5.0)
        self.assertEqual(
            molde["pontos_graduacao"],
            [{"x": float(x), "y": float(y)} for x, y in pontos[:-1]],
        )

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

    def test_arraste_molde_com_snap_ativo_imanta_angulos_proximos(self):
        ferramenta = FerramentaExtrairMolde()
        canvas = SimpleNamespace(snap_ativo=True)
        ferramenta._origem_arrasto_molde = QPointF(0.0, 0.0)
        ferramenta._ultimo_pos_arrasto = QPointF(0.0, 0.0)

        pos = ferramenta._posicao_arrasto_com_restricao(canvas, QPointF(8.0, 0.4))

        self.assertAlmostEqual(pos.x(), 8.009993757800315)
        self.assertAlmostEqual(pos.y(), 0.0)
        self.assertEqual(ferramenta._angulo_arrasto_molde, 0.0)
        self.assertIsNotNone(ferramenta._guia_arrasto_angular)

        livre = ferramenta._posicao_arrasto_com_restricao(canvas, QPointF(8.0, 3.0))
        self.assertEqual(livre, QPointF(8.0, 3.0))
        self.assertIsNone(ferramenta._angulo_arrasto_molde)
        self.assertIsNone(ferramenta._guia_arrasto_angular)

        pos_45 = ferramenta._posicao_arrasto_com_restricao(canvas, QPointF(7.0, 8.0))
        angulo = (atan2(pos_45.y(), pos_45.x()) * 180.0 / pi) % 360.0
        self.assertAlmostEqual(angulo, 45.0)
        self.assertEqual(ferramenta._angulo_arrasto_molde, 45.0)

    def test_arraste_molde_sem_snap_permanece_livre(self):
        ferramenta = FerramentaExtrairMolde()
        canvas = SimpleNamespace(snap_ativo=False)
        ferramenta._origem_arrasto_molde = QPointF(0.0, 0.0)
        ferramenta._ultimo_pos_arrasto = QPointF(0.0, 0.0)

        self.assertEqual(ferramenta._posicao_arrasto_com_restricao(canvas, QPointF(5.0, 2.0)), QPointF(5.0, 2.0))
        self.assertIsNone(ferramenta._angulo_arrasto_molde)
        self.assertIsNone(ferramenta._guia_arrasto_angular)

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

    def test_emenda_do_fechamento_vira_ponto_principal_ao_extrair(self):
        ferramenta = FerramentaExtrairMolde()
        contorno = [
            (1.0, 3.0),
            (4.0, 5.0),
            (8.0, 4.0),
            (11.0, 0.0),
            (8.0, -4.0),
            (4.0, -5.0),
            (1.0, -3.0),
            (1.0, 3.0),
        ]
        molde = {"tipo": "molde", "pontos": contorno, "ponto_emenda_referencia": (1.0, 3.0)}

        ferramenta._enriquecer_metadados_molde(molde)

        self.assertIn((1.0, 3.0), molde["controle_cantos"])

    def test_extracao_usa_emenda_do_desenho_original_mesmo_com_contorno_rotacionado(self):
        ferramenta = FerramentaExtrairMolde()
        base = [
            (cos(pi + ((2.0 * pi * i) / 48.0)) * 5.0, sin(pi + ((2.0 * pi * i) / 48.0)) * 3.0)
            for i in range(48)
        ]
        desenho_original = [*base, base[0]]
        contorno_extraido = [*base[18:], *base[:18], base[18]]
        canvas = _FakeCanvasCriacaoMolde()
        canvas.cena.elementos = [{"tipo": "polyline", "pontos": desenho_original, "fechado": True}]

        self.assertTrue(ferramenta._criar_molde_de_contorno_extraido(canvas, contorno_extraido))

        molde = canvas.cena.elementos[-1]
        emenda = base[0]
        self.assertEqual(len(molde["controle_cantos"]), 1)
        self.assertTrue(
            any(
                ((x - emenda[0]) ** 2 + (y - emenda[1]) ** 2) ** 0.5 <= 1e-4
                for x, y in molde["controle_cantos"]
            )
        )
        self.assertFalse(
            any(
                ((x - 5.0) ** 2 + (y - 0.0) ** 2) ** 0.5 <= 1e-4
                for x, y in molde["controle_cantos"]
            )
        )

    def test_nome_e_fio_nascem_dentro_de_molde_concavo(self):
        ferramenta = FerramentaExtrairMolde()
        contorno = [
            (0.0, 0.0),
            (12.0, 0.0),
            (12.0, 3.0),
            (4.0, 3.0),
            (4.0, 7.0),
            (12.0, 7.0),
            (12.0, 10.0),
            (0.0, 10.0),
            (0.0, 0.0),
        ]
        molde = {"tipo": "molde", "pontos": contorno, "nome_molde": "K123456789"}

        ferramenta._enriquecer_metadados_molde(molde)

        ponto_texto = tuple(molde["ponto_texto"])
        self.assertTrue(ferramenta._ponto_dentro_poligono_coords(ponto_texto, contorno))
        self.assertEqual(molde["referencia_texto_nome"], "Livre")
        self.assertLess(molde["texto_nome_altura_cm"], 3.0)

        x1, y1 = molde["fio_origem"]
        x2, y2 = molde["fio_fim"]
        for passo in range(7):
            t = passo / 6.0
            ponto = (x1 + ((x2 - x1) * t), y1 + ((y2 - y1) * t))
            self.assertTrue(ferramenta._ponto_dentro_poligono_coords(ponto, contorno))

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
