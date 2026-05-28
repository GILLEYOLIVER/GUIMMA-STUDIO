from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from canvas.visualizacao import VisualizacaoCanvas


_PATCH_APLICADO = False


def _qpoint(valor) -> QPointF:
    if isinstance(valor, QPointF):
        return QPointF(valor)
    if isinstance(valor, (list, tuple)) and len(valor) >= 2:
        try:
            return QPointF(float(valor[0]), float(valor[1]))
        except Exception:
            return QPointF(0.0, 0.0)
    return QPointF(0.0, 0.0)


def _cor(valor, padrao: str = "#ffffff") -> QColor:
    c = QColor(str(valor or ""))
    if c.isValid():
        return c
    return QColor(padrao)


def _texto_posicao(elemento: dict) -> QPointF:
    return _qpoint(elemento.get("posicao") or elemento.get("ponto") or elemento.get("origem"))


def _texto_cm(elemento: dict, canvas) -> float:
    for chave in ("texto_altura_cm", "altura_cm", "altura_texto_cm", "tamanho_texto_cm"):
        if chave in elemento:
            try:
                return max(0.2, float(str(elemento.get(chave)).replace(",", ".").replace("cm", "").strip()))
            except Exception:
                pass
    try:
        return max(0.2, float(getattr(canvas, "_texto_altura_cm", 2.0)))
    except Exception:
        return 2.0


def _espaco_linha_cm(elemento: dict, canvas) -> float:
    for chave in ("texto_espaco_linhas_cm", "espaco_linhas_cm", "entre_linhas_cm"):
        if chave in elemento:
            try:
                return max(0.2, float(str(elemento.get(chave)).replace(",", ".").replace("cm", "").strip()))
            except Exception:
                pass
    try:
        return max(0.2, float(getattr(canvas, "_texto_espaco_linhas_cm", 3.0)))
    except Exception:
        return 3.0


def _cor_halo(cor_texto: QColor) -> QColor:
    brilho = (0.299 * cor_texto.red()) + (0.587 * cor_texto.green()) + (0.114 * cor_texto.blue())
    return QColor("#000000") if brilho > 145 else QColor("#ffffff")


def _flags_justificacao(justificacao: str):
    just = str(justificacao or "Esquerda").strip().lower()
    if "cent" in just:
        return Qt.AlignHCenter
    if "dire" in just or "right" in just:
        return Qt.AlignRight
    return Qt.AlignLeft


def desenhar_texto_nativo(canvas: VisualizacaoCanvas, painter: QPainter, elemento: dict) -> None:
    texto = str(elemento.get("texto") or elemento.get("conteudo") or "").strip("\n")
    if not texto:
        return

    pos_cena = _texto_posicao(elemento)
    pos_tela = canvas._cena_para_tela(pos_cena)
    cor_texto = _cor(elemento.get("cor_texto") or elemento.get("cor") or getattr(canvas, "_linha_cor", "#ffffff"), "#ffffff")
    cor_halo = _cor_halo(cor_texto)
    zoom = max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.01)
    altura_px = max(10, min(900, int(round(_texto_cm(elemento, canvas) * zoom))))
    entre_linhas_px = max(float(altura_px), _espaco_linha_cm(elemento, canvas) * zoom)
    espessura = max(1.0, float(elemento.get("texto_espessura", elemento.get("espessura", getattr(canvas, "_linha_espessura", 1.0))) or 1.0))

    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fonte = QFont("Arial")
        fonte.setPixelSize(altura_px)
        fonte.setBold(False)
        fonte.setStyleStrategy(QFont.PreferAntialias)
        painter.setFont(fonte)
        metricas = painter.fontMetrics()
        linhas = texto.splitlines() or [texto]
        largura = max(metricas.horizontalAdvance(l) for l in linhas) + 12
        altura_linha = max(float(metricas.height()), entre_linhas_px)
        altura_total = altura_linha * len(linhas) + 8

        x = float(pos_tela.x())
        y = float(pos_tela.y())
        referencia = str(elemento.get("referencia") or "Topo esquerda").lower()
        if "centro" in referencia:
            x -= largura / 2.0
        elif "direita" in referencia:
            x -= largura
        if "baixo" in referencia or "inferior" in referencia:
            y -= altura_total
        elif "meio" in referencia or ("centro" in referencia and "topo" not in referencia and "baixo" not in referencia):
            y -= altura_total / 2.0

        rect_base = QRectF(x, y, largura, altura_total)
        angulo = float(elemento.get("angulo", 0.0) or 0.0)
        if abs(angulo) > 1e-6:
            painter.translate(pos_tela)
            painter.rotate(-angulo)
            rect_base = QRectF(rect_base.x() - pos_tela.x(), rect_base.y() - pos_tela.y(), rect_base.width(), rect_base.height())

        flags = _flags_justificacao(str(elemento.get("justificacao") or "Esquerda")) | Qt.AlignVCenter
        halo_offset = max(1, int(round(espessura)))
        painter.setBrush(Qt.NoBrush)
        for i, linha in enumerate(linhas):
            rect_linha = QRectF(rect_base.x(), rect_base.y() + i * altura_linha, rect_base.width(), altura_linha)
            # Halo fino apenas para legibilidade, sem transformar em vetor.
            painter.setPen(QPen(cor_halo, max(1.0, espessura + 1.0)))
            for dx, dy in ((-halo_offset, 0), (halo_offset, 0), (0, -halo_offset), (0, halo_offset)):
                painter.drawText(QRectF(rect_linha.x() + dx, rect_linha.y() + dy, rect_linha.width(), rect_linha.height()), flags, linha)
            painter.setPen(QPen(cor_texto, 1.0))
            painter.drawText(rect_linha, flags, linha)
    finally:
        painter.restore()


def aplicar_patch_texto_nativo_canvas() -> None:
    global _PATCH_APLICADO
    if _PATCH_APLICADO or getattr(VisualizacaoCanvas, "_guimma_texto_nativo_canvas", False):
        return

    original_paint = VisualizacaoCanvas.paintEvent

    def paintEvent_com_texto(self, event):  # noqa: N802
        original_paint(self, event)
        try:
            painter = QPainter(self)
            try:
                for elemento in list(getattr(getattr(self, "cena", None), "elementos", []) or []):
                    if isinstance(elemento, dict) and str(elemento.get("tipo") or "").lower() == "texto":
                        desenhar_texto_nativo(self, painter, elemento)
            finally:
                painter.end()
        except Exception as exc:
            try:
                if getattr(self, "lbl_status", None) is not None:
                    self.lbl_status.setText(f"Falha ao desenhar texto nativo: {type(exc).__name__}: {exc}")
            except Exception:
                pass

    VisualizacaoCanvas.paintEvent = paintEvent_com_texto
    VisualizacaoCanvas._guimma_texto_nativo_canvas = True
    _PATCH_APLICADO = True


# Aplica automaticamente ao importar este módulo.
aplicar_patch_texto_nativo_canvas()
