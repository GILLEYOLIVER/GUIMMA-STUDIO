from __future__ import annotations

from copy import deepcopy

try:
    from PySide6.QtGui import QIcon, QImage, QPainterPath, QPixmap
except Exception:  # pragma: no cover - fallback para ambientes sem Qt
    QIcon = QImage = QPainterPath = QPixmap = None


_CHAVES_QT_RUNTIME = {"pixmap", "qimage", "qpixmap", "imagem_qt", "_pixmap_cache"}
_TIPOS_QT_RUNTIME = tuple(
    tipo for tipo in (QPainterPath, QPixmap, QImage, QIcon) if tipo is not None
)


def copiar_elemento_sem_runtime(elemento: dict) -> dict:
    """Copia dados persistentes do elemento e descarta caches/objetos Qt."""
    if not isinstance(elemento, dict):
        return {}
    limpo: dict = {}
    for chave, valor in elemento.items():
        nome_chave = str(chave)
        if nome_chave.startswith("_"):
            continue
        if nome_chave.lower() in _CHAVES_QT_RUNTIME:
            continue
        if _TIPOS_QT_RUNTIME and isinstance(valor, _TIPOS_QT_RUNTIME):
            continue
        try:
            limpo[chave] = deepcopy(valor)
        except Exception:
            continue
    return limpo
