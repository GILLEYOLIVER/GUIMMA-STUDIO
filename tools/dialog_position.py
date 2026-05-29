from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QLabel, QWidget


def _texto_widget(widget: QWidget) -> str:
    partes: list[str] = []
    try:
        nome = str(widget.objectName() or "")
        if nome:
            partes.append(nome)
    except Exception:
        pass
    try:
        for label in widget.findChildren(QLabel):
            texto = str(label.text() or "").strip()
            if texto:
                partes.append(texto)
    except Exception:
        pass
    return " ".join(partes).lower()


def _pontuar_caixa_coordenadas(widget: QWidget) -> int:
    texto = _texto_widget(widget)
    pontos = 0
    if "coorden" in texto:
        pontos += 8
    if "dx" in texto:
        pontos += 3
    if "dy" in texto:
        pontos += 3
    if "ângulo" in texto or "angulo" in texto:
        pontos += 3
    if "distância" in texto or "distancia" in texto:
        pontos += 3
    if "aplicar" in texto:
        pontos += 1
    if "limpar" in texto:
        pontos += 1
    try:
        largura = int(widget.width())
        altura = int(widget.height())
        if 140 <= largura <= 420 and 45 <= altura <= 180:
            pontos += 2
        elif largura > 700 or altura > 300:
            pontos -= 8
    except Exception:
        pass
    return pontos


def _achar_caixa_coordenadas(canvas) -> QWidget | None:
    janela = None
    try:
        janela = canvas.window()
    except Exception:
        janela = None
    candidatos: list[QWidget] = []
    for raiz in (janela, canvas):
        if raiz is None:
            continue
        try:
            candidatos.extend(raiz.findChildren(QWidget))
        except Exception:
            pass
    melhor: QWidget | None = None
    melhor_pontos = 0
    melhor_area = 10**12
    for widget in candidatos:
        try:
            if not widget.isVisible() or widget.width() <= 0 or widget.height() <= 0:
                continue
        except Exception:
            continue
        pontos = _pontuar_caixa_coordenadas(widget)
        if pontos <= 0:
            continue
        try:
            area = int(widget.width()) * int(widget.height())
        except Exception:
            area = 10**12
        if pontos > melhor_pontos or (pontos == melhor_pontos and area < melhor_area):
            melhor = widget
            melhor_pontos = pontos
            melhor_area = area
    return melhor if melhor_pontos >= 6 else None


def posicionar_dialogo_abaixo_coordenadas(dialogo, canvas, margem: int = 8) -> None:
    try:
        dialogo.adjustSize()
    except Exception:
        pass
    try:
        caixa = _achar_caixa_coordenadas(canvas)
        if caixa is not None:
            origem = caixa.mapToGlobal(QPoint(0, 0))
            x = origem.x() + int(caixa.width()) - int(dialogo.width())
            y = origem.y() + int(caixa.height()) + int(margem)
        else:
            origem = canvas.mapToGlobal(QPoint(0, 0))
            x = origem.x() + int(canvas.width()) - int(dialogo.width()) - int(margem)
            y = origem.y() + int(margem)
        tela = QApplication.screenAt(QPoint(x, y)) or QApplication.primaryScreen()
        if tela is not None:
            area = tela.availableGeometry()
            x = max(area.left(), min(x, area.right() - int(dialogo.width())))
            y = max(area.top(), min(y, area.bottom() - int(dialogo.height())))
        dialogo.move(int(x), int(y))
    except Exception:
        pass
