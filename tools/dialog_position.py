from __future__ import annotations

from PySide6.QtCore import QPoint, QRect
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


def _tela_para_referencia(dialogo, referencia=None):
    try:
        if referencia is not None and hasattr(referencia, "windowHandle") and referencia.windowHandle() is not None:
            tela = referencia.windowHandle().screen()
            if tela is not None:
                return tela
    except Exception:
        pass
    try:
        if referencia is not None and hasattr(referencia, "screen"):
            tela = referencia.screen()
            if tela is not None:
                return tela
    except Exception:
        pass
    try:
        if referencia is not None and hasattr(referencia, "mapToGlobal") and hasattr(referencia, "rect"):
            centro = referencia.mapToGlobal(referencia.rect().center())
            tela = QApplication.screenAt(centro)
            if tela is not None:
                return tela
    except Exception:
        pass
    try:
        if dialogo.windowHandle() is not None:
            tela = dialogo.windowHandle().screen()
            if tela is not None:
                return tela
    except Exception:
        pass
    try:
        tela = dialogo.screen()
        if tela is not None:
            return tela
    except Exception:
        pass
    return QApplication.primaryScreen()


def centralizar_dialogo_na_tela(dialogo, referencia=None, margem: int = 16) -> None:
    try:
        dialogo.adjustSize()
    except Exception:
        pass
    try:
        tela = _tela_para_referencia(dialogo, referencia)
        if tela is None:
            return
        area = tela.availableGeometry()
        margem = max(0, int(margem))
        largura_max = max(120, area.width() - margem * 2)
        altura_max = max(90, area.height() - margem * 2)
        if int(dialogo.width()) > largura_max or int(dialogo.height()) > altura_max:
            dialogo.resize(min(int(dialogo.width()), largura_max), min(int(dialogo.height()), altura_max))

        geo = dialogo.frameGeometry()
        if not geo.isValid() or geo.width() <= 0 or geo.height() <= 0:
            geo = QRect(0, 0, max(1, int(dialogo.width())), max(1, int(dialogo.height())))
        geo.moveCenter(area.center())
        if geo.left() < area.left() + margem:
            geo.moveLeft(area.left() + margem)
        if geo.top() < area.top() + margem:
            geo.moveTop(area.top() + margem)
        if geo.right() > area.right() - margem:
            geo.moveRight(area.right() - margem)
        if geo.bottom() > area.bottom() - margem:
            geo.moveBottom(area.bottom() - margem)
        dialogo.move(geo.topLeft())
    except Exception:
        pass
