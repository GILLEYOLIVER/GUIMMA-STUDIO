from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CenaDocumento:
    """Representa o estado de desenho exibido no canvas."""

    largura: int = 2400
    altura: int = 1600
    grid_ativo: bool = True
    guias_ativas: bool = True
    elementos: list[dict] = field(default_factory=list)
