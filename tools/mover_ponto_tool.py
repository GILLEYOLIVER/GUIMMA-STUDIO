from __future__ import annotations

from tools.manipular_pontos_tool import Ferramenta as FerramentaBaseMoverPontos


class Ferramenta(FerramentaBaseMoverPontos):
    id_ferramenta = "mover_ponto"
    nome = "Mover Ponto"
    _dlg_global = None
    _edt_dx_global = None
    _edt_dy_global = None
    _cmb_n_pontos_global = None
    _chk_discreto_global = None
