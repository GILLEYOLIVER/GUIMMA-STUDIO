from __future__ import annotations

from tools._selecao_instantanea import FerramentaSelecaoInstantanea


class Ferramenta(FerramentaSelecaoInstantanea):
    id_ferramenta = "selecionar_tudo"
    nome = "Selecionar Tudo"
    metodo_canvas = "selecionar_tudo"
    mensagem_status = "Selecionado tudo: {total} elemento(s)."
