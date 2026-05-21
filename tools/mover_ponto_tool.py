from __future__ import annotations

from tools.manipular_pontos_tool import Ferramenta as FerramentaManipularPontos


class Ferramenta(FerramentaManipularPontos):
    id_ferramenta = "mover_ponto"
    nome = "Mover Ponto"
    descricao_painel = "Mova 1 ponto ou varios pontos por arraste ou por deslocamento DX/DY."
    usar_caixa_passo = True
    arraste_por_clique = False
    _dlg_global = None
    _edt_dx_global = None
    _edt_dy_global = None
    _cmb_n_pontos_global = None
    _chk_discreto_global = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        if self._cmb_n_pontos is not None and self._cmb_n_pontos.count() >= 2:
            self._cmb_n_pontos.setItemText(0, "1 ponto")
            self._cmb_n_pontos.setItemText(1, "Varios pontos")
        self.set_status(
            "Mover Ponto: escolha 1 ponto ou varios pontos. DX negativo move para esquerda; DY negativo move para baixo."
        )

    def _modo_n_pontos(self) -> bool:
        if not self._cmb_n_pontos:
            return False
        return self._cmb_n_pontos.currentIndex() == 1
