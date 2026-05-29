from __future__ import annotations

from math import cos, radians, sin, sqrt

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF

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


def _set_qpoint(elemento: dict, ponto: QPointF) -> None:
    p = (float(ponto.x()), float(ponto.y()))
    elemento["posicao"] = p
    elemento["ponto"] = p
    elemento["origem"] = p


def _cor(valor, padrao: str = "#ffffff") -> QColor:
    c = QColor(str(valor or ""))
    return c if c.isValid() else QColor(padrao)


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


def _fonte_texto(canvas: VisualizacaoCanvas, elemento: dict) -> QFont:
    zoom = max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.01)
    altura_px = max(10, min(900, int(round(_texto_cm(elemento, canvas) * zoom))))
    familia = str(elemento.get("fonte_texto") or elemento.get("fonte") or "Arial")
    fonte = QFont(familia)
    fonte.setPixelSize(altura_px)
    fonte.setBold(bool(elemento.get("negrito", False)))
    fonte.setItalic(bool(elemento.get("italico", False)))
    fonte.setStyleStrategy(QFont.PreferAntialias)
    return fonte


def _texto_rect_base_tela(canvas: VisualizacaoCanvas, elemento: dict) -> QRectF:
    texto = str(elemento.get("texto") or elemento.get("conteudo") or "").strip("\n")
    if not texto:
        return QRectF()
    pos_tela = canvas._cena_para_tela(_texto_posicao(elemento))
    fonte = _fonte_texto(canvas, elemento)
    metricas = QFontMetrics(fonte)
    linhas = texto.splitlines() or [texto]
    zoom = max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.01)
    entre_linhas_px = max(float(metricas.height()), _espaco_linha_cm(elemento, canvas) * zoom)
    largura = max(metricas.horizontalAdvance(linha) for linha in linhas) + 12
    altura_total = entre_linhas_px * len(linhas) + 8
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
    return QRectF(x, y, float(largura), float(altura_total))


def _texto_rect_local(canvas: VisualizacaoCanvas, elemento: dict) -> QRectF:
    rect = _texto_rect_base_tela(canvas, elemento)
    if not rect.isValid():
        return QRectF()
    pos_tela = canvas._cena_para_tela(_texto_posicao(elemento))
    return QRectF(rect.x() - pos_tela.x(), rect.y() - pos_tela.y(), rect.width(), rect.height())


def _rotacionar_ponto_local(pos_tela: QPointF, p: QPointF, angulo: float) -> QPointF:
    a = radians(float(angulo or 0.0))
    c = cos(a)
    s = sin(a)
    # Mesmo sentido usado no painter.rotate(-angulo)
    x = p.x() * c + p.y() * s
    y = -p.x() * s + p.y() * c
    return QPointF(pos_tela.x() + x, pos_tela.y() + y)


def texto_poligono_tela(canvas: VisualizacaoCanvas, elemento: dict, margem: float = 0.0) -> QPolygonF:
    rect = _texto_rect_local(canvas, elemento).adjusted(-margem, -margem, margem, margem)
    if not rect.isValid():
        return QPolygonF()
    pos_tela = canvas._cena_para_tela(_texto_posicao(elemento))
    angulo = float(elemento.get("angulo", 0.0) or 0.0)
    pontos = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
    return QPolygonF([_rotacionar_ponto_local(pos_tela, p, angulo) for p in pontos])


def texto_rect_tela(canvas: VisualizacaoCanvas, elemento: dict) -> QRectF:
    poligono = texto_poligono_tela(canvas, elemento, 0.0)
    return poligono.boundingRect() if not poligono.isEmpty() else QRectF()


def _ponto_em_texto(canvas: VisualizacaoCanvas, elemento: dict, pos_tela: QPointF, margem: float = 6.0) -> bool:
    rect = _texto_rect_local(canvas, elemento).adjusted(-margem, -margem, margem, margem)
    if not rect.isValid():
        return False
    pos_anchor = canvas._cena_para_tela(_texto_posicao(elemento))
    dx = float(pos_tela.x() - pos_anchor.x())
    dy = float(pos_tela.y() - pos_anchor.y())
    # Inverte a rotação usada para desenhar o texto.
    a = radians(float(elemento.get("angulo", 0.0) or 0.0))
    c = cos(a)
    s = sin(a)
    local = QPointF(dx * c - dy * s, dx * s + dy * c)
    return rect.contains(local)


def indice_texto_em_ponto(canvas: VisualizacaoCanvas, pos_tela: QPointF) -> int | None:
    elementos = list(getattr(getattr(canvas, "cena", None), "elementos", []) or [])
    for idx in range(len(elementos) - 1, -1, -1):
        elemento = elementos[idx]
        if not isinstance(elemento, dict) or str(elemento.get("tipo") or "").lower() != "texto":
            continue
        if _ponto_em_texto(canvas, elemento, pos_tela, 6.0):
            return idx
    return None


def indices_texto_em_retangulo(canvas: VisualizacaoCanvas, inicio_cena: QPointF, fim_cena: QPointF) -> set[int]:
    p1 = canvas._cena_para_tela(inicio_cena)
    p2 = canvas._cena_para_tela(fim_cena)
    rect = QRectF(min(p1.x(), p2.x()), min(p1.y(), p2.y()), abs(p2.x() - p1.x()), abs(p2.y() - p1.y())).normalized()
    selecionados: set[int] = set()
    if rect.width() < 3 and rect.height() < 3:
        return selecionados
    for idx, elemento in enumerate(list(getattr(getattr(canvas, "cena", None), "elementos", []) or [])):
        if not isinstance(elemento, dict) or str(elemento.get("tipo") or "").lower() != "texto":
            continue
        rect_texto = texto_poligono_tela(canvas, elemento, 5.0).boundingRect()
        if rect_texto.isValid() and rect.intersects(rect_texto):
            selecionados.add(idx)
    return selecionados


def desenhar_selecao_texto(canvas: VisualizacaoCanvas, painter: QPainter, elemento: dict) -> None:
    rect = _texto_rect_local(canvas, elemento).adjusted(-5, -5, 5, 5)
    if not rect.isValid():
        return
    pos_tela = canvas._cena_para_tela(_texto_posicao(elemento))
    angulo = float(elemento.get("angulo", 0.0) or 0.0)
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(pos_tela)
        painter.rotate(-angulo)
        cor_borda = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        cor_fundo = QColor(cor_borda)
        cor_fundo.setAlpha(42)
        painter.setBrush(cor_fundo)
        pen = QPen(cor_borda, 1.2, Qt.DashLine)
        pen.setDashPattern([3.5, 2.5])
        painter.setPen(pen)
        painter.drawRect(rect)
    finally:
        painter.restore()


def desenhar_texto_nativo(canvas: VisualizacaoCanvas, painter: QPainter, elemento: dict) -> None:
    texto = str(elemento.get("texto") or elemento.get("conteudo") or "").strip("\n")
    if not texto:
        return

    rect_base = _texto_rect_base_tela(canvas, elemento)
    if not rect_base.isValid():
        return
    pos_tela = canvas._cena_para_tela(_texto_posicao(elemento))
    cor_texto = _cor(elemento.get("cor_texto") or elemento.get("cor") or getattr(canvas, "_linha_cor", "#ffffff"), "#ffffff")
    cor_halo = _cor_halo(cor_texto)
    fonte = _fonte_texto(canvas, elemento)
    metricas = QFontMetrics(fonte)
    linhas = texto.splitlines() or [texto]
    zoom = max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.01)
    altura_linha = max(float(metricas.height()), _espaco_linha_cm(elemento, canvas) * zoom)
    espessura = max(1.0, float(elemento.get("texto_espessura", elemento.get("espessura", getattr(canvas, "_linha_espessura", 1.0))) or 1.0))

    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(fonte)
        rect = QRectF(rect_base)
        angulo = float(elemento.get("angulo", 0.0) or 0.0)
        if abs(angulo) > 1e-6:
            painter.translate(pos_tela)
            painter.rotate(-angulo)
            rect = QRectF(rect.x() - pos_tela.x(), rect.y() - pos_tela.y(), rect.width(), rect.height())

        flags = _flags_justificacao(str(elemento.get("justificacao") or "Esquerda")) | Qt.AlignVCenter
        halo_offset = max(1, int(round(espessura)))
        painter.setBrush(Qt.NoBrush)
        for i, linha in enumerate(linhas):
            rect_linha = QRectF(rect.x(), rect.y() + i * altura_linha, rect.width(), altura_linha)
            painter.setPen(QPen(cor_halo, max(1.0, espessura + 1.0)))
            for dx, dy in ((-halo_offset, 0), (halo_offset, 0), (0, -halo_offset), (0, halo_offset)):
                painter.drawText(QRectF(rect_linha.x() + dx, rect_linha.y() + dy, rect_linha.width(), rect_linha.height()), flags, linha)
            painter.setPen(QPen(cor_texto, 1.0))
            painter.drawText(rect_linha, flags, linha)
    finally:
        painter.restore()


def transladar_texto_elemento(elemento: dict, dx: float, dy: float) -> None:
    if not isinstance(elemento, dict) or str(elemento.get("tipo") or "").lower() != "texto":
        return
    p = _texto_posicao(elemento)
    _set_qpoint(elemento, QPointF(p.x() + dx, p.y() + dy))


def _texto_mao_idx(canvas) -> int | None:
    idx = getattr(canvas, "_texto_em_maos_idx", None)
    try:
        idx_int = int(idx)
    except Exception:
        return None
    if 0 <= idx_int < len(getattr(getattr(canvas, "cena", None), "elementos", []) or []):
        el = canvas.cena.elementos[idx_int]
        if isinstance(el, dict) and str(el.get("tipo") or "").lower() == "texto":
            return idx_int
    return None


def aplicar_patch_texto_nativo_canvas() -> None:
    global _PATCH_APLICADO
    if _PATCH_APLICADO or getattr(VisualizacaoCanvas, "_guimma_texto_nativo_canvas_v7", False):
        return

    original_paint = VisualizacaoCanvas.paintEvent
    original_press = VisualizacaoCanvas.mousePressEvent
    original_move = VisualizacaoCanvas.mouseMoveEvent
    original_release = VisualizacaoCanvas.mouseReleaseEvent
    original_double = VisualizacaoCanvas.mouseDoubleClickEvent
    original_transladar = getattr(VisualizacaoCanvas, "_transladar_elemento", None)

    def paintEvent_com_texto(self, event):  # noqa: N802
        original_paint(self, event)
        try:
            painter = QPainter(self)
            try:
                for idx, elemento in enumerate(list(getattr(getattr(self, "cena", None), "elementos", []) or [])):
                    if isinstance(elemento, dict) and str(elemento.get("tipo") or "").lower() == "texto":
                        if idx in getattr(self, "_selecionados", set()):
                            desenhar_selecao_texto(self, painter, elemento)
                        desenhar_texto_nativo(self, painter, elemento)
            finally:
                painter.end()
        except Exception as exc:
            try:
                if getattr(self, "lbl_status", None) is not None:
                    self.lbl_status.setText(f"Falha ao desenhar texto nativo: {type(exc).__name__}: {exc}")
            except Exception:
                pass

    def mousePressEvent_com_texto(self, event):  # noqa: N802
        idx_mao = _texto_mao_idx(self)
        if idx_mao is not None:
            if event.button() == Qt.LeftButton:
                self._texto_em_maos_idx = None
                self._texto_em_maos_cancelavel = False
                self._selecionados = {idx_mao}
                if hasattr(self, "_registrar_historico"):
                    self._registrar_historico()
                self.update()
                event.accept()
                return
            if event.button() == Qt.RightButton:
                try:
                    self.cena.elementos.pop(idx_mao)
                except Exception:
                    pass
                self._texto_em_maos_idx = None
                self._texto_em_maos_cancelavel = False
                self._selecionados.clear()
                self.update()
                event.accept()
                return

        if event.button() == Qt.LeftButton:
            idx = indice_texto_em_ponto(self, event.position())
            if idx is not None:
                if event.modifiers() & Qt.ControlModifier or event.modifiers() & Qt.ShiftModifier:
                    if idx in self._selecionados:
                        self._selecionados.remove(idx)
                    else:
                        self._selecionados.add(idx)
                else:
                    self._selecionados = {idx}
                self._texto_drag_idx = idx
                self._texto_drag_inicio_cena = self._tela_para_cena(event.position())
                self._texto_drag_inicio_pos = _texto_posicao(self.cena.elementos[idx])
                self._texto_drag_moveu = False
                self.update()
                event.accept()
                return
        original_press(self, event)

    def mouseMoveEvent_com_texto(self, event):  # noqa: N802
        idx_mao = _texto_mao_idx(self)
        if idx_mao is not None:
            _set_qpoint(self.cena.elementos[idx_mao], self._tela_para_cena(event.position()))
            self._selecionados = {idx_mao}
            self.update()
            event.accept()
            return

        idx = getattr(self, "_texto_drag_idx", None)
        if idx is not None and event.buttons() & Qt.LeftButton:
            try:
                idx_int = int(idx)
                if 0 <= idx_int < len(self.cena.elementos):
                    atual = self._tela_para_cena(event.position())
                    inicio = getattr(self, "_texto_drag_inicio_cena", atual)
                    inicio_pos = getattr(self, "_texto_drag_inicio_pos", _texto_posicao(self.cena.elementos[idx_int]))
                    dx = atual.x() - inicio.x()
                    dy = atual.y() - inicio.y()
                    _set_qpoint(self.cena.elementos[idx_int], QPointF(inicio_pos.x() + dx, inicio_pos.y() + dy))
                    self._texto_drag_moveu = True
                    self.update()
                    event.accept()
                    return
            except Exception:
                pass
        original_move(self, event)

    def mouseReleaseEvent_com_texto(self, event):  # noqa: N802
        idx = getattr(self, "_texto_drag_idx", None)
        if idx is not None and event.button() == Qt.LeftButton:
            try:
                if getattr(self, "_texto_drag_moveu", False) and hasattr(self, "_registrar_historico"):
                    self._registrar_historico()
                self._texto_drag_idx = None
                self._texto_drag_inicio_cena = None
                self._texto_drag_inicio_pos = None
                self._texto_drag_moveu = False
                self.update()
                event.accept()
                return
            except Exception:
                pass

        runtime = getattr(self, "_runtime_tool", None)
        inicio_caixa = getattr(runtime, "_inicio_caixa", None)
        fim_caixa = getattr(runtime, "_fim_caixa", None)
        original_release(self, event)
        if event.button() == Qt.LeftButton and isinstance(inicio_caixa, QPointF) and isinstance(fim_caixa, QPointF):
            if sqrt((fim_caixa.x() - inicio_caixa.x()) ** 2 + (fim_caixa.y() - inicio_caixa.y()) ** 2) > (4.0 / max(float(getattr(self, "zoom", 1.0) or 1.0), 0.001)):
                textos = indices_texto_em_retangulo(self, inicio_caixa, fim_caixa)
                if textos:
                    self._selecionados |= textos
                    self.update()
                    event.accept()
                    return

    def mouseDoubleClickEvent_com_texto(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            idx = indice_texto_em_ponto(self, event.position())
            if idx is not None:
                self._selecionados = {idx}
                self.update()
                try:
                    self._ativar_ferramenta_janela_principal("editar_texto")
                except Exception:
                    pass
                event.accept()
                return
        original_double(self, event)

    def _transladar_elemento_com_texto(self, elemento: dict, dx: float, dy: float):
        if isinstance(elemento, dict) and str(elemento.get("tipo") or "").lower() == "texto":
            transladar_texto_elemento(elemento, dx, dy)
            return
        if original_transladar is not None:
            return original_transladar(self, elemento, dx, dy)

    VisualizacaoCanvas.paintEvent = paintEvent_com_texto
    VisualizacaoCanvas.mousePressEvent = mousePressEvent_com_texto
    VisualizacaoCanvas.mouseMoveEvent = mouseMoveEvent_com_texto
    VisualizacaoCanvas.mouseReleaseEvent = mouseReleaseEvent_com_texto
    VisualizacaoCanvas.mouseDoubleClickEvent = mouseDoubleClickEvent_com_texto
    if original_transladar is not None:
        VisualizacaoCanvas._transladar_elemento = _transladar_elemento_com_texto
    VisualizacaoCanvas._guimma_texto_nativo_canvas_v7 = True
    _PATCH_APLICADO = True


aplicar_patch_texto_nativo_canvas()
