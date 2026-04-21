from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

NodeType = Literal["corner", "smooth", "symmetric"]
SegmentType = Literal["line", "bezier", "spline", "arc"]


def _next_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


@dataclass(slots=True)
class GeoNode:
    x: float
    y: float
    node_type: NodeType = "corner"
    id: str = field(default_factory=lambda: _next_id("node"))


@dataclass(slots=True)
class GeoSegment:
    start_node_id: str
    end_node_id: str
    segment_type: SegmentType = "line"
    controls: list[tuple[float, float]] = field(default_factory=list)
    id: str = field(default_factory=lambda: _next_id("seg"))


@dataclass(slots=True)
class GeoShape:
    nodes: list[GeoNode]
    segments: list[GeoSegment]
    closed: bool = False
    id: str = field(default_factory=lambda: _next_id("shape"))

    def node_map(self) -> dict[str, GeoNode]:
        return {n.id: n for n in self.nodes}
