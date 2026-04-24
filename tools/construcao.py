from __future__ import annotations

from tools.tool_base import FerramentaBase


class FerramentaReta(FerramentaBase):
    id_ferramenta = "reta"
    nome = "Reta"
    usa_painel_auxiliar = False


class FerramentaRetangulo(FerramentaBase):
    id_ferramenta = "retangulo"
    nome = "Retangulo"
    usa_painel_auxiliar = False


class FerramentaPorAngulo(FerramentaBase):
    id_ferramenta = "por_angulo"
    nome = "Por Angulo"
    usa_painel_auxiliar = False


class FerramentaCurva(FerramentaBase):
    id_ferramenta = "curva"
    nome = "Curva"
    usa_painel_auxiliar = False


class FerramentaEstenderReta(FerramentaBase):
    id_ferramenta = "estender_reta"
    nome = "Estender reta"
    usa_painel_auxiliar = False


class FerramentaEstenderAteElemento(FerramentaBase):
    id_ferramenta = "estender_ate_elemento"
    nome = "Estender até elemento"
    usa_painel_auxiliar = False


class FerramentaEstenderDuasRetas(FerramentaBase):
    id_ferramenta = "estender_duas_retas"
    nome = "Estender duas retas"
    usa_painel_auxiliar = False
