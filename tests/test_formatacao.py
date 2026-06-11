from __future__ import annotations

from core.formatacao import formatar_numero


def test_formatar_numero_remove_zeros_desnecessarios():
    assert formatar_numero(25, 2) == "25"
    assert formatar_numero(25.2, 2) == "25.2"
    assert formatar_numero(25.06, 2) == "25.06"
    assert formatar_numero(-0.0, 2) == "0"

