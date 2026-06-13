from __future__ import annotations

from tools._selecao_instantanea import FerramentaSelecaoInstantanea


class Ferramenta(FerramentaSelecaoInstantanea):
    id_ferramenta = "selecionar_moldes"
    nome = "Selecionar Moldes"
    metodo_canvas = "selecionar_moldes"
    mensagem_status = "Selecionado(s) {total} molde(s)."
