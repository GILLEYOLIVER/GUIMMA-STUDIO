"""Domínio geométrico compartilhado (base para ponte Python <-> motor)."""

from core.geometry.engine import build_mold_from_shape, build_shape_from_polyline, point_in_polygon
from core.geometry.model import GeoNode, GeoSegment, GeoShape

__all__ = [
    "GeoNode",
    "GeoSegment",
    "GeoShape",
    "build_shape_from_polyline",
    "build_mold_from_shape",
    "point_in_polygon",
]
