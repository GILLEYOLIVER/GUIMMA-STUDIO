from __future__ import annotations

from tools.tool_base import FerramentaBase


class FerramentaReta(FerramentaBase):
    id_ferramenta = "reta"
    nome = "Reta"


class FerramentaRetangulo(FerramentaBase):
    id_ferramenta = "retangulo"
    nome = "Retangulo"


class FerramentaPorAngulo(FerramentaBase):
    id_ferramenta = "por_angulo"
    nome = "Por Angulo"


class FerramentaCurva(FerramentaBase):
    id_ferramenta = "curva"
    nome = "Curva"


class FerramentaEstenderReta(FerramentaBase):
    id_ferramenta = "estender_reta"
    nome = "Estender reta"


class FerramentaEstenderAteElemento(FerramentaBase):
    id_ferramenta = "estender_ate_elemento"
    nome = "Estender até elemento"


class FerramentaEstenderDuasRetas(FerramentaBase):
    id_ferramenta = "estender_duas_retas"
    nome = "Estender duas retas"
