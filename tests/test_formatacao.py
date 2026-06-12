from __future__ import annotations

from core.formatacao import formatar_numero, normalizar_decimal_ponto, numero_decimal_ponto, texto_decimal_ponto_aceitavel


def test_formatar_numero_remove_zeros_desnecessarios():
    assert formatar_numero(25, 2) == "25"
    assert formatar_numero(25.2, 2) == "25.2"
    assert formatar_numero(25.06, 2) == "25.06"
    assert formatar_numero(-0.0, 2) == "0"


def test_decimal_ponto_completa_zero_antes_do_ponto():
    assert normalizar_decimal_ponto(".5") == "0.5"
    assert normalizar_decimal_ponto("-.5") == "-0.5"
    assert normalizar_decimal_ponto("+.9") == "+0.9"
    assert numero_decimal_ponto(".1") == 0.1


def test_decimal_ponto_nao_aceita_virgula():
    assert numero_decimal_ponto(",5", 7.0) == 7.0
    assert texto_decimal_ponto_aceitavel(",5") is False
