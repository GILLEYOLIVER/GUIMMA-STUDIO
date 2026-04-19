from __future__ import annotations

from PySide6.QtCore import Qt

LINE_STYLES: list[tuple[str, str]] = [
    ("solid", "Contínua"),
    ("dash", "Tracejada"),
    ("dot", "Pontilhada"),
    ("dashdot", "Traço-ponto"),
    ("dashdotdot", "Traço-ponto-ponto"),
    ("longdash", "Traço longo"),
    ("shortdash", "Traço curto"),
    ("center", "Centro"),
    ("border", "Borda"),
    ("dense_dot", "Ponto denso"),
    ("iso_long_short", "ISO longo-curto"),
    ("iso_long_double_short", "ISO longo-2 curtos"),
    ("dash_space", "Traço espaçado"),
    ("dash_dot_dense", "Traço-ponto denso"),
    ("dot_sparse", "Ponto espaçado"),
    ("center_dense", "Centro denso"),
    ("phantom", "Fantasma"),
    ("chain", "Corrente"),
    ("zigzag_soft", "Zigue-zague suave"),
    ("zigzag_strong", "Zigue-zague forte"),
    ("wave_soft", "Ondulada suave"),
    ("wave_strong", "Ondulada forte"),
    ("dash_half_moon", "Traço-meia lua"),
    ("dash_half_moon_alt", "Traço meia lua"),
    ("half_moon", "Meia lua"),
]

GEOMETRIC_LINE_STYLES: set[str] = {
    "zigzag_soft",
    "zigzag_strong",
    "wave_soft",
    "wave_strong",
    "dash_half_moon",
    "dash_half_moon_alt",
    "half_moon",
}

_QT_STYLES: dict[str, Qt.PenStyle] = {
    "solid": Qt.SolidLine,
    "dash": Qt.DashLine,
    "dot": Qt.DotLine,
    "dashdot": Qt.DashDotLine,
    "dashdotdot": Qt.DashDotDotLine,
}

_DASH_PATTERNS: dict[str, list[float]] = {
    "longdash": [10, 4],
    "shortdash": [4, 2],
    "center": [12, 3, 2, 3],
    "border": [12, 3, 2, 3, 2, 3],
    "dense_dot": [1, 2],
    "iso_long_short": [12, 2, 3, 2],
    "iso_long_double_short": [12, 2, 3, 2, 3, 2],
    "dash_space": [8, 6],
    "dash_dot_dense": [8, 2, 1, 2],
    "dot_sparse": [1, 4],
    "center_dense": [8, 2, 2, 2],
    "phantom": [14, 3, 2, 3, 2, 3],
    "chain": [10, 2, 2, 2, 2, 2],
    "zigzag_soft": [6, 2, 2, 2],
    "zigzag_strong": [10, 2, 1, 2, 1, 2],
}


def pen_style_for_line(estilo: str) -> Qt.PenStyle:
    if estilo in _DASH_PATTERNS:
        return Qt.CustomDashLine
    return _QT_STYLES.get(estilo, Qt.SolidLine)


def dash_pattern_for_line(estilo: str) -> list[float] | None:
    return _DASH_PATTERNS.get(estilo)


def is_geometric_line_style(estilo: str) -> bool:
    return estilo in GEOMETRIC_LINE_STYLES
