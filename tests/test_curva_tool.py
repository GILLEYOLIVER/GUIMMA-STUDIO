from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaCurva = None
    FerramentaManipularPontos = None
    QPointF = None
else:
    from PySide6.QtCore import QPointF

    from tools.curva_tool import Ferramenta as FerramentaCurva
    from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos


class _FakeCanvas:
    def __init__(self):
        self._modo_curva = "3p"
        self._curva_np_nos = []
        self._curva_np_curva_confirmada = []
        self._curva_np_perimetro_confirmado = 0.0
        self._linha_cor = "#ffffff"
        self._linha_espessura = 1.0
        self._linha_estilo = "solid"
        self._linha_amplitude = 1.0
        self.cena = SimpleNamespace(elementos=[])
        self.historico = 0

    def _registrar_historico(self):
        self.historico += 1


@unittest.skipIf(FerramentaCurva is None, "PySide6 nao disponivel neste ambiente")
class CurvaToolTestCase(unittest.TestCase):
    def test_modo_3p_gera_parabola_unica_passando_pelo_ponto_do_meio(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaCurva()
        pontos = [QPointF(0.0, 0.0), QPointF(5.0, -5.0), QPointF(10.0, 0.0)]

        curva = ferramenta._gerar_parabola_3p(canvas, pontos)

        meio = curva[len(curva) // 2]
        self.assertAlmostEqual(meio.x(), 5.0)
        self.assertAlmostEqual(meio.y(), -5.0)
        antes = curva[(len(curva) // 2) - 1]
        depois = curva[(len(curva) // 2) + 1]
        self.assertLess(antes.y(), 0.0)
        self.assertLess(depois.y(), 0.0)
        self.assertLess(abs(antes.y() - depois.y()), 1e-6)

    def test_modo_3p_assimetrico_preserva_ponto_intermediario_clicado(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaCurva()
        ponto_meio = QPointF(3.0, -5.0)
        pontos = [QPointF(0.0, 0.0), ponto_meio, QPointF(10.0, 0.0)]

        curva = ferramenta._gerar_parabola_3p(canvas, pontos)

        self.assertTrue(any(abs(p.x() - ponto_meio.x()) < 1e-7 and abs(p.y() - ponto_meio.y()) < 1e-7 for p in curva))
        self.assertNotAlmostEqual(ferramenta._parametro_parabola_3p(pontos[0], ponto_meio, pontos[2]), 0.5)

    def test_finalizar_3p_salva_tipo_parabola_e_tres_controles_clicados(self):
        canvas = _FakeCanvas()
        canvas._curva_np_nos = [QPointF(0.0, 0.0), QPointF(5.0, -5.0), QPointF(10.0, 0.0)]
        ferramenta = FerramentaCurva()

        self.assertTrue(ferramenta._finalizar_np(canvas, fechado=False))

        elemento = canvas.cena.elementos[0]
        self.assertEqual(elemento["tipo_curva"], "parabola_3p")
        self.assertEqual(elemento["pontos_principais"], [(0.0, 0.0), (5.0, -5.0), (10.0, 0.0)])
        self.assertIn((5.0, -5.0), elemento["pontos"])
        self.assertEqual(canvas.historico, 1)

    def test_modo_livre_com_tres_nos_salva_spline_livre(self):
        canvas = _FakeCanvas()
        canvas._modo_curva = "np"
        canvas._curva_np_nos = [QPointF(0.0, 0.0), QPointF(5.0, -5.0), QPointF(10.0, 0.0)]
        ferramenta = FerramentaCurva()

        self.assertTrue(ferramenta._finalizar_np(canvas, fechado=False))

        elemento = canvas.cena.elementos[0]
        self.assertEqual(elemento["tipo_curva"], "spline_livre")
        self.assertEqual(elemento["pontos_principais"], [(0.0, 0.0), (5.0, -5.0), (10.0, 0.0)])

    def test_preview_modo_livre_usa_mesma_curva_da_confirmacao(self):
        canvas = _FakeCanvas()
        canvas._modo_curva = "np"
        canvas._curva_np_nos = [QPointF(0.0, 0.0), QPointF(5.0, -5.0), QPointF(10.0, 0.0)]
        ferramenta = FerramentaCurva()
        quarto = QPointF(14.0, 4.0)

        preview = ferramenta._gerar_preview_profissional(canvas, cursor=quarto, fechado=False)
        curva_confirmada = ferramenta._gerar_spline(canvas, [*canvas._curva_np_nos, quarto], fechado=False)

        self.assertEqual([(p.x(), p.y()) for p in preview], [(p.x(), p.y()) for p in curva_confirmada])
        self.assertAlmostEqual(preview[-1].x(), 14.0)
        self.assertAlmostEqual(preview[-1].y(), 4.0)

    def test_quarto_clique_confirma_exatamente_o_preview_anterior(self):
        canvas = _FakeCanvas()
        canvas._modo_curva = "np"
        canvas._curva_np_nos = [QPointF(0.0, 0.0), QPointF(5.0, -5.0), QPointF(10.0, 0.0)]
        ferramenta = FerramentaCurva()
        ferramenta._atualizar_curva_confirmada(canvas)
        quarto = QPointF(14.0, 4.0)
        preview = ferramenta._gerar_preview_profissional(canvas, cursor=quarto, fechado=False)

        canvas._curva_np_nos.append(quarto)
        confirmada = ferramenta._atualizar_curva_confirmada(canvas)

        self.assertEqual([(p.x(), p.y()) for p in confirmada], [(p.x(), p.y()) for p in preview])

    def test_fechamento_livre_circular_ajusta_circulo_perfeito(self):
        canvas = _FakeCanvas()
        canvas._modo_curva = "np"
        canvas._curva_ajustar_circulo = True
        canvas._curva_np_nos = [
            QPointF(10.0, 0.0),
            QPointF(0.0, 10.0),
            QPointF(-10.0, 0.0),
            QPointF(0.0, -10.0),
        ]
        ferramenta = FerramentaCurva()

        self.assertTrue(ferramenta._finalizar_np(canvas, fechado=True))

        elemento = canvas.cena.elementos[0]
        self.assertEqual(elemento["tipo_curva"], "circulo_ajustado")
        self.assertTrue(elemento["fechado"])
        self.assertEqual(elemento["pontos"][0], elemento["pontos"][-1])
        raios = [((x * x) + (y * y)) ** 0.5 for x, y in elemento["pontos"][:-1]]
        self.assertLess(max(raios) - min(raios), 1e-6)

    def test_fechamento_livre_circular_sem_shift_nao_forca_circulo(self):
        canvas = _FakeCanvas()
        canvas._modo_curva = "np"
        canvas._curva_ajustar_circulo = False
        canvas._curva_np_nos = [
            QPointF(10.0, 0.0),
            QPointF(0.0, 10.0),
            QPointF(-10.0, 0.0),
            QPointF(0.0, -10.0),
        ]
        ferramenta = FerramentaCurva()

        self.assertTrue(ferramenta._finalizar_np(canvas, fechado=True))

        elemento = canvas.cena.elementos[0]
        self.assertEqual(elemento["tipo_curva"], "spline_catmull_rom")

    def test_manipular_parabola_3p_regenera_sem_voltar_para_catmull_rom(self):
        ferramenta = FerramentaManipularPontos()
        controles = [QPointF(0.0, 0.0), QPointF(5.0, -6.0), QPointF(10.0, 0.0)]

        pontos = ferramenta._gerar_tracado_curva_real(controles, tipo_curva="parabola_3p")

        self.assertEqual(pontos[0], (0.0, 0.0))
        self.assertEqual(pontos[len(pontos) // 2], (5.0, -6.0))
        self.assertEqual(pontos[-1], (10.0, 0.0))
        self.assertLess(abs(pontos[(len(pontos) // 2) - 1][1] - pontos[(len(pontos) // 2) + 1][1]), 1e-6)


if __name__ == "__main__":
    unittest.main()
