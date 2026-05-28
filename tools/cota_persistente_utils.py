from __future__ import annotations

from math import atan2, cos, sin, sqrt

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from tools.texto_config import aplicar_fonte_texto, cor_texto


_PATCH_APLICADO = False


def _qpoint(valor) -> QPointF:
    if isinstance(valor, QPointF):
        return QPointF(valor)
    if isinstance(valor, (list, tuple)) and len(valor) >= 2:
        return QPointF(float(valor[0]), float(valor[1]))
    return QPointF(0.0, 0.0)


def serializar_cota(cota: dict, canvas) -> dict:
    cor = QColor(getattr(canvas, "_linha_cor", "#ffffff"))
    if not cor.isValid():
        cor = QColor("#ffffff")
    return {
        "tipo": "cota_perimetro",
        "pontos": [(float(p.x()), float(p.y())) for p in cota.get("pontos", [])],
        "ancora": (float(_qpoint(cota.get("ancora")).x()), float(_qpoint(cota.get("ancora")).y())),
        "label_pos": (float(_qpoint(cota.get("label_pos")).x()), float(_qpoint(cota.get("label_pos")).y())),
        "valor": float(cota.get("valor", 0.0)),
        "cor": cor.name(),
        "texto_altura_cm": float(getattr(canvas, "_texto_altura_cm", 2.0)),
        "texto_espaco_linhas_cm": float(getattr(canvas, "_texto_espaco_linhas_cm", 3.0)),
    }


def desenhar_seta(painter: QPainter, inicio: QPointF, fim: QPointF, cor: QColor) -> None:
    painter.drawLine(inicio, fim)
    dx = inicio.x() - fim.x()
    dy = inicio.y() - fim.y()
    dist = sqrt((dx * dx) + (dy * dy))
    if dist <= 1e-6:
        return
    ang = atan2(dy, dx)
    tam = 16.0
    abertura = 0.55
    p1 = QPointF(fim.x() + cos(ang - abertura) * tam, fim.y() + sin(ang - abertura) * tam)
    p2 = QPointF(fim.x() + cos(ang + abertura) * tam, fim.y() + sin(ang + abertura) * tam)
    painter.drawLine(fim, p1)
    painter.drawLine(fim, p2)


def formatar_medida(canvas, valor: float) -> str:
    if hasattr(canvas, "formatar_distancia"):
        try:
            return canvas.formatar_distancia(valor)
        except Exception:
            pass
    if hasattr(canvas, "formatar_valor_unidade"):
        unidade = getattr(canvas, "_unidade_sigla", "cm")
        return f"{canvas.formatar_valor_unidade(valor)} {unidade}"
    return f"{valor:.2f} cm"


def desenhar_cota_perimetro(canvas, painter: QPainter, elemento: dict) -> None:
    ancora = _qpoint(elemento.get("ancora"))
    label_pos = _qpoint(elemento.get("label_pos"))
    valor = float(elemento.get("valor", 0.0))
    texto = formatar_medida(canvas, valor)
    cor = cor_texto(canvas, elemento)

    p_ancora = canvas._cena_para_tela(ancora)
    p_label = canvas._cena_para_tela(label_pos)

    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(cor, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        desenhar_seta(painter, p_label, p_ancora, cor)

        aplicar_fonte_texto(painter, canvas, elemento, negrito=True)
        metrics = painter.fontMetrics()
        largura = metrics.horizontalAdvance(texto) + 16
        altura = metrics.height() + 8
        rect = QRectF(p_label.x() - largura / 2.0, p_label.y() - altura / 2.0, largura, altura)
        painter.setPen(QPen(cor, 1.0))
        painter.drawText(rect, Qt.AlignCenter, texto)
    finally:
        painter.restore()


def aplicar_patch_canvas_cotas(canvas) -> None:
    global _PATCH_APLICADO
    cls = canvas.__class__
    if getattr(cls, "_guimma_patch_cota_perimetro_persistente", False):
        return
    original_paint = cls.paintEvent

    def paintEvent_com_cotas(self, event):  # noqa: N802
        original_paint(self, event)
        try:
            painter = QPainter(self)
            for elemento in list(getattr(getattr(self, "cena", None), "elementos", []) or []):
                if isinstance(elemento, dict) and elemento.get("tipo") == "cota_perimetro":
                    desenhar_cota_perimetro(self, painter, elemento)
            painter.end()
        except Exception:
            pass

    cls.paintEvent = paintEvent_com_cotas
    cls._guimma_patch_cota_perimetro_persistente = True
