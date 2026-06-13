from __future__ import annotations

from tools._selecao_instantanea import FerramentaSelecaoInstantanea


class Ferramenta(FerramentaSelecaoInstantanea):
    id_ferramenta = "inverter_moldes"
    nome = "Inverter Moldes"
    metodo_canvas = "inverter_selecao_moldes"
    mensagem_status = "Seleção de moldes invertida: {total} molde(s) selecionado(s)."
