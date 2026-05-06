from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget


def _settings() -> QSettings:
    return QSettings("GUIMMA", "GUIMMA-STUDIO")


def _grupo(chave: str) -> str:
    chave_limpa = "".join(c if c.isalnum() or c in "._:-" else "_" for c in str(chave))
    return f"caixas_flutuantes/{chave_limpa}"


def posicao_salva(chave: str) -> QPoint | None:
    cfg = _settings()
    cfg.beginGroup(_grupo(chave))
    x = cfg.value("x", None)
    y = cfg.value("y", None)
    cfg.endGroup()
    if x is None or y is None:
        return None
    try:
        return QPoint(int(float(x)), int(float(y)))
    except (TypeError, ValueError):
        return None


def salvar_posicao(widget: QWidget, chave: str) -> None:
    if widget is None:
        return
    pos = widget.pos()
    cfg = _settings()
    cfg.beginGroup(_grupo(chave))
    cfg.setValue("x", int(pos.x()))
    cfg.setValue("y", int(pos.y()))
    cfg.endGroup()


def ajustar_para_area(widget: QWidget, pos: QPoint, margem: int = 8) -> QPoint:
    parent = widget.parentWidget()
    if parent is not None and not widget.isWindow():
        area = parent.rect().adjusted(margem, margem, -margem, -margem)
    else:
        tela = widget.screen() or QGuiApplication.primaryScreen()
        area = tela.availableGeometry() if tela is not None else QRect(pos.x(), pos.y(), widget.width(), widget.height())

    largura_util = max(0, area.width() - widget.width())
    altura_util = max(0, area.height() - widget.height())
    x = area.left() + max(0, min(pos.x() - area.left(), largura_util))
    y = area.top() + max(0, min(pos.y() - area.top(), altura_util))
    return QPoint(int(x), int(y))


def restaurar_posicao(widget: QWidget, chave: str, fallback: QPoint | None = None) -> bool:
    pos = posicao_salva(chave)
    if pos is None:
        if fallback is not None:
            widget.move(ajustar_para_area(widget, fallback))
        return False
    widget.move(ajustar_para_area(widget, pos))
    return True


class _FiltroMemoriaPosicao(QObject):
    def __init__(self, widget: QWidget, chave: str):
        super().__init__(widget)
        self._widget = widget
        self._chave = chave

    def eventFilter(self, obj, event):
        if obj is self._widget and event.type() in (QEvent.Move, QEvent.Hide, QEvent.Close):
            salvar_posicao(self._widget, self._chave)
        return super().eventFilter(obj, event)


def instalar_memoria_posicao(widget: QWidget, chave: str) -> None:
    if widget is None or getattr(widget, "_guimma_memoria_posicao_instalada", False):
        return
    filtro = _FiltroMemoriaPosicao(widget, chave)
    widget.installEventFilter(filtro)
    widget._guimma_memoria_posicao_instalada = True  # type: ignore[attr-defined]
    widget._guimma_memoria_posicao_filtro = filtro  # type: ignore[attr-defined]
