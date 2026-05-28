from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from tools.texto_config import aplicar_fonte_texto, configurar_texto_canvas, espaco_linhas_cm


_PATCH_TEXTO_APLICADO = False


def _qpoint(valor) -> QPointF:
    if isinstance(valor, QPointF):
        return QPointF(valor)
    if isinstance(valor, (list, tuple)) and len(valor) >= 2:
        try:
            return QPointF(float(valor[0]), float(valor[1]))
        except Exception:
            return QPointF(0.0, 0.0)
    return QPointF(0.0, 0.0)


def _cor_segura(valor, fallback: str = "#ffffff") -> QColor:
    cor = QColor(str(valor or fallback))
    if not cor.isValid():
        cor = QColor(fallback)
    return cor


def _cor_texto_visivel(elemento: dict) -> QColor:
    # Usa a cor salva da seleção de linha, mas garante cor válida.
    return _cor_segura(elemento.get("cor_texto") or elemento.get("cor") or "#ffffff")


def _cor_contorno_contraste(cor: QColor) -> QColor:
    brilho = (0.299 * cor.red()) + (0.587 * cor.green()) + (0.114 * cor.blue())
    return QColor("#ffffff") if brilho < 90 else QColor("#000000")


def _alinhar_flag(justificacao: str):
    just = str(justificacao or "Esquerda").strip().lower()
    if "cent" in just:
        return Qt.AlignHCenter
    if "dire" in just or "right" in just:
        return Qt.AlignRight
    return Qt.AlignLeft


def _posicao_texto(elemento: dict) -> QPointF:
    return _qpoint(elemento.get("posicao") or elemento.get("ponto") or elemento.get("origem"))


def desenhar_texto_elemento(canvas, painter: QPainter, elemento: dict) -> None:
    texto = str(elemento.get("texto") or elemento.get("conteudo") or "").strip("\n")
    if not texto:
        return

    pos = _posicao_texto(elemento)
    tela = canvas._cena_para_tela(pos)
    cor = _cor_texto_visivel(elemento)
    contorno = _cor_contorno_contraste(cor)
    linhas = texto.splitlines() or [texto]
    zoom = max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.01)
    line_height_px = max(12.0, espaco_linhas_cm(canvas, elemento) * zoom)

    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        aplicar_fonte_texto(painter, canvas, elemento, negrito=False)
        fonte = QFont(painter.font())
        fonte.setBold(False)
        painter.setFont(fonte)
        metrics = painter.fontMetrics()
        largura = max(metrics.horizontalAdvance(linha) for linha in linhas) + 10
        altura = max(float(metrics.height()), line_height_px) * len(linhas) + 8

        ref = str(elemento.get("referencia") or "Topo esquerda").lower()
        x = float(tela.x())
        y = float(tela.y())
        if "centro" in ref:
            x -= largura / 2.0
        elif "direita" in ref:
            x -= largura
        if "baixo" in ref or "inferior" in ref:
            y -= altura
        elif "meio" in ref or ("centro" in ref and "topo" not in ref and "baixo" not in ref):
            y -= altura / 2.0

        rect = QRectF(x, y, largura, altura)
        angulo = float(elemento.get("angulo", 0.0) or 0.0)
        if abs(angulo) > 1e-6:
            painter.translate(tela)
            painter.rotate(-angulo)
            rect = QRectF(rect.x() - tela.x(), rect.y() - tela.y(), rect.width(), rect.height())

        flags = _alinhar_flag(str(elemento.get("justificacao") or "Esquerda")) | Qt.AlignVCenter

        # Halo/contorno para o texto aparecer mesmo se a cor escolhida for preta no canvas preto.
        for i, linha in enumerate(linhas):
            linha_rect = QRectF(rect.x(), rect.y() + i * line_height_px, rect.width(), max(float(metrics.height()), line_height_px))
            painter.setPen(QPen(contorno, 3.0))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                r = QRectF(linha_rect.x() + dx, linha_rect.y() + dy, linha_rect.width(), linha_rect.height())
                painter.drawText(r, flags, linha)
            painter.setPen(QPen(cor, 1.0))
            painter.drawText(linha_rect, flags, linha)
    finally:
        painter.restore()


def aplicar_patch_canvas_textos(canvas) -> None:
    global _PATCH_TEXTO_APLICADO
    cls = canvas.__class__
    if getattr(cls, "_guimma_patch_textos_persistentes_v2", False):
        return

    original_paint = cls.paintEvent

    def paintEvent_com_textos(self, event):  # noqa: N802
        original_paint(self, event)
        try:
            configurar_texto_canvas(self)
            painter = QPainter(self)
            try:
                for elemento in list(getattr(getattr(self, "cena", None), "elementos", []) or []):
                    if isinstance(elemento, dict) and str(elemento.get("tipo") or "").lower() == "texto":
                        desenhar_texto_elemento(self, painter, elemento)
            finally:
                painter.end()
        except Exception as exc:
            try:
                if getattr(self, "lbl_status", None) is not None:
                    self.lbl_status.setText(f"Falha ao desenhar texto: {type(exc).__name__}: {exc}")
            except Exception:
                pass

    cls.paintEvent = paintEvent_com_textos
    cls._guimma_patch_textos_persistentes_v2 = True
    _PATCH_TEXTO_APLICADO = True
