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


def _qcolor(valor, fallback: str = "#ffffff") -> QColor:
    cor = QColor(str(valor or fallback))
    return cor if cor.isValid() else QColor(fallback)


def _texto_cor(elemento: dict) -> QColor:
    return _qcolor(elemento.get("cor_texto") or elemento.get("cor") or "#ffffff")


def _cor_halo(cor: QColor) -> QColor:
    brilho = (0.299 * cor.red()) + (0.587 * cor.green()) + (0.114 * cor.blue())
    return QColor("#000000") if brilho > 145 else QColor("#ffffff")


def _flag_alinhamento(justificacao: str):
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
    cor = _texto_cor(elemento)
    halo = _cor_halo(cor)
    linhas = texto.splitlines() or [texto]
    zoom = max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.01)
    line_height_px = max(12.0, espaco_linhas_cm(canvas, elemento) * zoom)
    espessura = max(1.0, float(elemento.get("texto_espessura", elemento.get("espessura", 1.0)) or 1.0))

    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        aplicar_fonte_texto(painter, canvas, elemento, negrito=False)
        fonte = QFont(painter.font())
        fonte.setBold(False)
        fonte.setStyleStrategy(QFont.PreferAntialias)
        painter.setFont(fonte)
        metrics = painter.fontMetrics()
        largura = max(metrics.horizontalAdvance(linha) for linha in linhas) + 12
        altura_linha = max(float(metrics.height()), line_height_px)
        altura_total = altura_linha * len(linhas) + 8

        ref = str(elemento.get("referencia") or "Topo esquerda").lower()
        x = float(tela.x())
        y = float(tela.y())
        if "centro" in ref:
            x -= largura / 2.0
        elif "direita" in ref:
            x -= largura
        if "baixo" in ref or "inferior" in ref:
            y -= altura_total
        elif "meio" in ref or ("centro" in ref and "topo" not in ref and "baixo" not in ref):
            y -= altura_total / 2.0

        rect_base = QRectF(x, y, largura, altura_total)
        angulo = float(elemento.get("angulo", 0.0) or 0.0)
        if abs(angulo) > 1e-6:
            painter.translate(tela)
            painter.rotate(-angulo)
            rect_base = QRectF(rect_base.x() - tela.x(), rect_base.y() - tela.y(), rect_base.width(), rect_base.height())

        flags = _flag_alinhamento(str(elemento.get("justificacao") or "Esquerda")) | Qt.AlignVCenter

        # Texto nativo real: usa drawText normal, não transforma em blocos/linhas.
        # O halo acompanha a espessura do ribbon apenas para dar leitura sobre fundo escuro.
        halo_offset = max(1, int(round(espessura)))
        for i, linha in enumerate(linhas):
            linha_rect = QRectF(rect_base.x(), rect_base.y() + i * altura_linha, rect_base.width(), altura_linha)
            painter.setPen(QPen(halo, max(1.0, espessura + 1.0)))
            for dx, dy in ((-halo_offset, 0), (halo_offset, 0), (0, -halo_offset), (0, halo_offset)):
                r = QRectF(linha_rect.x() + dx, linha_rect.y() + dy, linha_rect.width(), linha_rect.height())
                painter.drawText(r, flags, linha)
            painter.setPen(QPen(cor, 1.0))
            painter.drawText(linha_rect, flags, linha)
    finally:
        painter.restore()


def aplicar_patch_canvas_textos(canvas) -> None:
    global _PATCH_TEXTO_APLICADO
    cls = canvas.__class__
    if getattr(cls, "_guimma_patch_textos_nativos_v3", False):
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
    cls._guimma_patch_textos_nativos_v3 = True
    _PATCH_TEXTO_APLICADO = True
