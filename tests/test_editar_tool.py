import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    FerramentaEditar = None
else:
    from PySide6.QtCore import QPointF

    from tools.editar_tool import Ferramenta as FerramentaEditar


class _FakeCanvas:
    def __init__(self):
        self.cena = SimpleNamespace(
            elementos=[
                {
                    "tipo": "polyline",
                    "pontos": [(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)],
                    "pontos_controle_curva": [(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)],
                    "curva_suave": True,
                    "curva_editavel": True,
                    "pontos_tracado_real": True,
                }
            ]
        )
        self._selecionados = set()
        self.historico = 0
        self.atualizado = False

    def _registrar_historico(self):
        self.historico += 1

    def update(self):
        self.atualizado = True


@unittest.skipIf(FerramentaEditar is None, "PySide6 nao disponivel neste ambiente")
class EditarToolTestCase(unittest.TestCase):
    def test_metadados_da_ferramenta(self):
        ferramenta = FerramentaEditar()

        self.assertEqual(ferramenta.id_ferramenta, "editar")
        self.assertEqual(ferramenta.nome, "Editar")

    def test_suavidade_altera_amostragem_da_curva(self):
        ferramenta = FerramentaEditar()

        ferramenta.definir_suavidade(0, registrar=False)
        baixa = ferramenta._amostras_desenho(3)
        ferramenta.definir_suavidade(10, registrar=False)
        alta = ferramenta._amostras_desenho(3)

        self.assertGreater(alta, baixa)

    def test_remover_ponto_controle_preserva_minimo_de_dois_pontos(self):
        ferramenta = FerramentaEditar()
        canvas = _FakeCanvas()

        removido = ferramenta._remover_ponto_controle(canvas, 0, 1)

        self.assertTrue(removido)
        self.assertEqual(canvas.historico, 1)
        self.assertTrue(canvas.atualizado)
        self.assertEqual(canvas._selecionados, {0})
        self.assertEqual(len(canvas.cena.elementos[0]["pontos_controle_curva"]), 2)
        self.assertEqual(canvas.cena.elementos[0]["tipo_linha"], "reta")
        self.assertEqual(len(canvas.cena.elementos[0]["alcas_editar_segmento"]), 2)

    def test_nao_remove_quando_restariam_menos_de_dois_pontos(self):
        ferramenta = FerramentaEditar()
        canvas = _FakeCanvas()
        canvas.cena.elementos[0]["pontos_controle_curva"] = [(0.0, 0.0), (10.0, 0.0)]

        removido = ferramenta._remover_ponto_controle(canvas, 0, 0)

        self.assertFalse(removido)
        self.assertEqual(canvas.historico, 0)
        self.assertEqual(len(canvas.cena.elementos[0]["pontos_controle_curva"]), 2)

    def test_cria_alcas_bezier_por_ponto_de_controle(self):
        ferramenta = FerramentaEditar()
        canvas = _FakeCanvas()
        el = canvas.cena.elementos[0]
        pontos = ferramenta._pontos_controle_do_elemento(el)

        alcas = ferramenta._garantir_alcas_bezier(el, pontos)

        self.assertEqual(len(alcas), 3)
        self.assertIsNotNone(alcas[0]["proximo"])
        self.assertIsNotNone(alcas[1]["anterior"])
        self.assertIsNotNone(alcas[1]["proximo"])
        self.assertIsNotNone(alcas[2]["anterior"])

    def test_arrastar_alca_recalcula_tracado_com_bezier(self):
        ferramenta = FerramentaEditar()
        canvas = _FakeCanvas()
        el = canvas.cena.elementos[0]
        pontos = ferramenta._pontos_controle_do_elemento(el)
        alcas = ferramenta._garantir_alcas_bezier(el, pontos)
        alcas[1]["anterior"] = (4.0, 8.0)
        ferramenta._salvar_alcas_bezier(el, alcas)

        ferramenta._aplicar_bezier_no_elemento(el, pontos)

        self.assertEqual(el["tipo_curva"], "bezier_alcas")
        self.assertGreater(len(el["pontos"]), len(pontos))
        self.assertEqual(el["pontos"][0], (0.0, 0.0))
        self.assertEqual(el["pontos"][-1], (10.0, 0.0))

    def test_mover_ponto_principal_move_as_alcas_do_mesmo_ponto(self):
        ferramenta = FerramentaEditar()
        canvas = _FakeCanvas()
        el = canvas.cena.elementos[0]
        pontos = ferramenta._pontos_controle_do_elemento(el)
        alcas = ferramenta._garantir_alcas_bezier(el, pontos)
        antes = QPointF(*alcas[1]["anterior"])

        ferramenta._deslocar_alcas_do_ponto(el, 1, 2.0, -1.0)

        depois = QPointF(*el["alcas_editar_segmento"][1]["anterior"])
        self.assertEqual(depois, QPointF(antes.x() + 2.0, antes.y() - 1.0))


if __name__ == "__main__":
    unittest.main()
