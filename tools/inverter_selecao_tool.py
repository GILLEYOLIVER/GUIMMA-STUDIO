from __future__ import annotations

from tools._selecao_instantanea import FerramentaSelecaoInstantanea


class Ferramenta(FerramentaSelecaoInstantanea):
    id_ferramenta = "inverter_selecao"
    nome = "Inverter Selecao"
    metodo_canvas = "inverter_selecao"
    mensagem_status = "Seleção invertida: {total} elemento(s) selecionado(s)."
