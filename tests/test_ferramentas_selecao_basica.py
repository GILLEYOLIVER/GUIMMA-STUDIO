from __future__ import annotations

import unittest
from types import SimpleNamespace

from tools.inverter_moldes_tool import Ferramenta as FerramentaInverterMoldes
from tools.inverter_selecao_tool import Ferramenta as FerramentaInverterSelecao
from tools.selecionar_moldes_tool import Ferramenta as FerramentaSelecionarMoldes
from tools.selecionar_tudo_tool import Ferramenta as FerramentaSelecionarTudo
from ui.janela_principal import GuimmaStudioMainWindow


class _Signal:
    def __init__(self):
        self.emitidos: list[str] = []

    def emit(self, valor: str):
        self.emitidos.append(valor)


class _Label:
    def __init__(self):
        self.texto = ""

    def setText(self, texto: str):  # noqa: N802
        self.texto = texto


class _CanvasSelecao:
    def __init__(self):
        self.cena = SimpleNamespace(
            elementos=[
                {"molde": True, "nome": "A"},
                {"molde": False, "nome": "Linha"},
                {"molde": True, "nome": "B"},
            ]
        )
        self._selecionados: set[int] = set()
        self.ferramenta_padrao_solicitada = _Signal()
        self.lbl_status = _Label()
        self.atualizacoes = 0

    def update(self):
        self.atualizacoes += 1

    def findChildren(self, _tipo):  # noqa: N802
        return []

    def selecionar_tudo(self):
        self._selecionados = set(range(len(self.cena.elementos)))
        self.update()

    def selecionar_moldes(self):
        self._selecionados = {idx for idx, el in enumerate(self.cena.elementos) if el.get("molde")}
        self.update()

    def inverter_selecao(self):
        total = set(range(len(self.cena.elementos)))
        self._selecionados = total - set(self._selecionados)
        self.update()

    def inverter_selecao_moldes(self):
        moldes = {idx for idx, el in enumerate(self.cena.elementos) if el.get("molde")}
        self._selecionados = moldes - (set(self._selecionados) & moldes)
        self.update()


class FerramentasSelecaoBasicaTestCase(unittest.TestCase):
    def test_selecionar_tudo_executa_e_volta_para_selecionar(self):
        canvas = _CanvasSelecao()

        FerramentaSelecionarTudo().on_activate(canvas)

        self.assertEqual(canvas._selecionados, {0, 1, 2})
        self.assertEqual(canvas.ferramenta_padrao_solicitada.emitidos, ["selecionar"])
        self.assertIn("3 elemento", canvas.lbl_status.texto)

    def test_selecionar_moldes_seleciona_apenas_moldes(self):
        canvas = _CanvasSelecao()

        FerramentaSelecionarMoldes().on_activate(canvas)

        self.assertEqual(canvas._selecionados, {0, 2})
        self.assertEqual(canvas.ferramenta_padrao_solicitada.emitidos, ["selecionar"])
        self.assertIn("2 molde", canvas.lbl_status.texto)

    def test_inverter_selecao_inverte_todos_elementos(self):
        canvas = _CanvasSelecao()
        canvas._selecionados = {1}

        FerramentaInverterSelecao().on_activate(canvas)

        self.assertEqual(canvas._selecionados, {0, 2})
        self.assertEqual(canvas.ferramenta_padrao_solicitada.emitidos, ["selecionar"])
        self.assertIn("2 elemento", canvas.lbl_status.texto)

    def test_inverter_moldes_inverte_somente_moldes(self):
        canvas = _CanvasSelecao()
        canvas._selecionados = {0, 1}

        FerramentaInverterMoldes().on_activate(canvas)

        self.assertEqual(canvas._selecionados, {2})
        self.assertEqual(canvas.ferramenta_padrao_solicitada.emitidos, ["selecionar"])
        self.assertIn("1 molde", canvas.lbl_status.texto)

    def test_janela_trata_botoes_selecao_como_acoes_diretas(self):
        canvas = _CanvasSelecao()
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        janela.lbl_status = _Label()
        janela._area_documento_atual = lambda: SimpleNamespace(canvas=canvas)
        ferramentas_ativas: list[str] = []
        janela._ativar_ferramenta_global = lambda tool_id: ferramentas_ativas.append(tool_id)

        executado = GuimmaStudioMainWindow._executar_acao_edicao_ribbon(janela, "selecionar_moldes")

        self.assertTrue(executado)
        self.assertEqual(canvas._selecionados, {0, 2})
        self.assertEqual(ferramentas_ativas, ["selecionar"])
        self.assertIn("2 molde", janela.lbl_status.texto)


if __name__ == "__main__":
    unittest.main()
