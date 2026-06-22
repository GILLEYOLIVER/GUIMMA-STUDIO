from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen


def desenhar_elementos_originais(canvas, painter, elementos) -> None:
    if painter is None or not elementos:
        return

    painter.save()
    try:
        pen = QPen(QColor(255, 255, 255, 175), 1.25, Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for el in _iter_elementos(elementos):
            if _ignorar_preview_original(el):
                continue
            _desenhar_pontos(canvas, painter, el.get("pontos", []) or [])
            _desenhar_linha_simples(canvas, painter, el)
            _desenhar_controles(canvas, painter, el)
    finally:
        painter.restore()


def _iter_elementos(elementos) -> Iterable[dict]:
    if isinstance(elementos, dict):
        fonte = elementos.values()
    else:
        fonte = elementos
    for item in fonte:
        el = item
        if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], dict):
            el = item[1]
        if isinstance(el, dict):
            yield el


def _ignorar_preview_original(el: dict) -> bool:
    if not isinstance(el, dict) or not el.get("molde"):
        return False
    if isinstance(el.get("graduacao_contornos_importados"), list) and el.get("graduacao_contornos_importados"):
        return True
    if isinstance(el.get("graduacao_contornos_regularizados_preview"), list) and el.get("graduacao_contornos_regularizados_preview"):
        return True
    metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
    return bool(metadados.get("importado_como_molde_real")) and bool(el.get("graduacao_tamanhos"))


def _desenhar_pontos(canvas, painter, pontos) -> None:
    pts: list[QPointF] = []
    for item in pontos:
        pt = _ponto_qt(item)
        if pt is not None:
            pts.append(pt)
    if len(pts) < 2:
        return
    for a, b in zip(pts, pts[1:]):
        painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))


def _desenhar_linha_simples(canvas, painter, el: dict) -> None:
    p0 = _ponto_qt(el.get("p0"))
    p1 = _ponto_qt(el.get("p1"))
    if p0 is not None and p1 is not None:
        painter.drawLine(canvas._cena_para_tela(p0), canvas._cena_para_tela(p1))


def _desenhar_controles(canvas, painter, el: dict) -> None:
    grupos: list[tuple[list, int]] = []
    cantos = el.get("controle_cantos") if isinstance(el.get("controle_cantos"), list) else []
    principais = el.get("pontos_controle_principais") if isinstance(el.get("pontos_controle_principais"), list) else []
    auxiliares = el.get("controle_auxiliares") if isinstance(el.get("controle_auxiliares"), list) else []

    if cantos:
        grupos.append((cantos, 4))
    elif principais:
        grupos.append((principais, 4))
    if auxiliares:
        grupos.append((auxiliares, 3))

    for valores, raio in grupos:
        for item in valores:
            pt = _ponto_qt(item)
            if pt is None:
                continue
            tela = canvas._cena_para_tela(pt)
            painter.drawLine(QPointF(tela.x(), tela.y() - raio), QPointF(tela.x() + raio, tela.y()))
            painter.drawLine(QPointF(tela.x() + raio, tela.y()), QPointF(tela.x(), tela.y() + raio))
            painter.drawLine(QPointF(tela.x(), tela.y() + raio), QPointF(tela.x() - raio, tela.y()))
            painter.drawLine(QPointF(tela.x() - raio, tela.y()), QPointF(tela.x(), tela.y() - raio))


def _ponto_qt(p) -> QPointF | None:
    try:
        if isinstance(p, QPointF):
            return QPointF(p)
        if isinstance(p, dict):
            return QPointF(float(p["x"]), float(p["y"]))
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            return QPointF(float(p[0]), float(p[1]))
    except Exception:
        return None
    return None
