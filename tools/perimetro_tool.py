from __future__ import annotations

from tools.cota_perimetro_tool import Ferramenta as FerramentaCotaPerimetro


class Ferramenta(FerramentaCotaPerimetro):
    id_ferramenta = "perimetro"
    nome = "Perímetro"
    descricao_painel = "Clique em uma linha/curva para medir o perímetro de ponto a ponto."
