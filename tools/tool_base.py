from __future__ import annotations


class FerramentaBase:
    id_ferramenta = "base"
    nome = "Ferramenta Base"

    def ativar(self) -> str:
        return f"{self.nome} ativada"
