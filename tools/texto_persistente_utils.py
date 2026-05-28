from __future__ import annotations

from math import radians

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen

from tools.texto_config import aplicar_fonte_texto, cor_texto, configurar_texto_canvas, espaco_linhas_cm


_PATCH_TEXTO_APLICADO = False


def _qpoint(valor) -> QPointF:
    if isinstance(valor, QPointF):
        return QPointF(valor)
    if isinstance(valor, (list, tuple)) and len(valor) >= 2:
        return QPointF(float(valor[0]), float(valor[1]))
    return QPointF(0.0, 0.0)


def _alinhar_flag(justificacao: str):
    just = str(justificacao or "Esquerda").strip().lower()
    if "cent" in just:
        return Qt.AlignHCenter
    if "dire" in just or "right" in just:
        return Qt.AlignRight
    return Qt.AlignLeft


def _desenhar_texto(canvas, painter: QPainter, elemento: dict) -> None:
    texto = str(elemento.get("texto") or elemento.get("conteudo") or "").strip("\n")
    if not texto:
        return
    pos = _qpoint(elemento.get("posicao") or elemento.get("ponto") or elemento.get("origem"))
    tela = canvas._cena_para_tela(pos)
    cor = cor_texto(canvas, elemento)
    altura_cm = float(elemento.get("texto_altura_cm", elemento.get("altura_cm", getattr(canvas, "_texto_altura_cm", 2.0))))
    espaco_cm = espaco_linhas_cm(canvas, elemento)
    zoom = max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.01)
    line_height_px = max(8.0, espaco_cm * zoom)
    linhas = texto.splitlines() or [texto]

    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        aplicar_fonte_texto(painter, canvas, {"texto_altura_cm": altura_cm}, negrito=False)
        painter.setPen(QPen(cor, 1.0))
        metrics = painter.fontMetrics()
        largura = max(metrics.horizontalAdvance(linha) for linha in linhas) + 8
        altura = max(metrics.height(), line_height_px) * len(linhas) + 6
        ref = str(elemento.get("referencia") or "Topo esquerda").lower()
        x = tela.x()
        y = tela.y()
        if "centro" in ref:
            x -= largura / 2.0
        elif "direita" in ref:
            x -= largura
        if "meio" in ref or "centro" in ref:
            y -= altura / 2.0
        elif "baixo" in ref or "inferior" in ref:
            y -= altura
        rect = QRectF(x, y, largura, altura)
        angulo = float(elemento.get("angulo", 0.0) or 0.0)
        if abs(angulo) > 1e-6:
            painter.translate(tela)
            painter.rotate(-angulo)
            rect = QRectF(rect.x() - tela.x(), rect.y() - tela.y(), rect.width(), rect.height())
        flags = _alinhar_flag(str(elemento.get("justificacao") or "Esquerda")) | Qt.AlignVCenter
        for i, linha in enumerate(linhas):
            linha_rect = QRectF(rect.x(), rect.y() + i * line_height_px, rect.width(), max(metrics.height(), line_height_px))
            painter.drawText(linha_rect, flags, linha)
    finally:
        painter.restore()


def aplicar_patch_canvas_textos(canvas) -> None:
    global _PATCH_TEXTO_APLICADO
    cls = canvas.__class__
    if getattr(cls, "_guimma_patch_textos_persistentes", False):
        return
    original_paint = cls.paintEvent

    def paintEvent_com_textos(self, event):  # noqa: N802
        original_paint(self, event)
        try:
            configurar_texto_canvas(self)
            painter = QPainter(self)
            for elemento in list(getattr(getattr(self, "cena", None), "elementos", []) or []):
                if isinstance(elemento, dict) and elemento.get("tipo") == "texto":
                    _desenhar_texto(self, painter, elemento)
            painter.end()
        except Exception:
            pass

    cls.paintEvent = paintEvent_com_textos
    cls._guimma_patch_textos_persistentes = True
    _PATCH_TEXTO_APLICADO = True
