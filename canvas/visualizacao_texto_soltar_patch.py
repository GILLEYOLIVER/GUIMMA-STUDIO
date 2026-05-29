from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication, QWidget

from canvas.visualizacao import VisualizacaoCanvas


_FILTRO_GLOBAL = None


def _elementos(canvas):
    return list(getattr(getattr(canvas, "cena", None), "elementos", []) or [])


def _eh_texto(elemento) -> bool:
    return isinstance(elemento, dict) and str(elemento.get("tipo") or "").lower() == "texto"


def _indice_texto_em_maos(canvas) -> int | None:
    elementos = _elementos(canvas)

    try:
        idx = int(getattr(canvas, "_texto_em_maos_idx", None))
        if 0 <= idx < len(elementos) and _eh_texto(elementos[idx]):
            return idx
    except Exception:
        pass

    if not bool(getattr(canvas, "_texto_em_maos_cancelavel", False)):
        return None

    try:
        for idx in sorted(getattr(canvas, "_selecionados", set()) or set(), reverse=True):
            idx_int = int(idx)
            if 0 <= idx_int < len(elementos) and _eh_texto(elementos[idx_int]):
                canvas._texto_em_maos_idx = idx_int
                return idx_int
    except Exception:
        pass

    for idx in range(len(elementos) - 1, -1, -1):
        elemento = elementos[idx]
        if _eh_texto(elemento) and elemento.get("__texto_previa_ao_vivo"):
            canvas._texto_em_maos_idx = idx
            return idx

    return None


def _canvas_do_widget(widget) -> VisualizacaoCanvas | None:
    atual = widget
    while atual is not None:
        if isinstance(atual, VisualizacaoCanvas):
            return atual
        try:
            atual = atual.parentWidget()
        except Exception:
            return None
    return None


def _posicao_cena_do_evento(canvas, event, watched=None) -> QPointF:
    try:
        global_pos = event.globalPosition().toPoint()
        local = canvas.mapFromGlobal(global_pos)
        return canvas._tela_para_cena(QPointF(float(local.x()), float(local.y())))
    except Exception:
        pass
    try:
        if watched is not None and isinstance(watched, QWidget) and watched is not canvas:
            p = watched.mapTo(canvas, QPoint(int(event.position().x()), int(event.position().y())))
            return canvas._tela_para_cena(QPointF(float(p.x()), float(p.y())))
    except Exception:
        pass
    try:
        return canvas._tela_para_cena(event.position())
    except Exception:
        try:
            return canvas._tela_para_cena(QPointF(float(event.x()), float(event.y())))
        except Exception:
            return QPointF(0.0, 0.0)


def _mover_texto_para_evento(canvas, idx: int, event, watched=None) -> None:
    ponto = _posicao_cena_do_evento(canvas, event, watched)
    p = (float(ponto.x()), float(ponto.y()))
    elemento = canvas.cena.elementos[idx]
    if not isinstance(elemento, dict):
        return
    elemento["posicao"] = p
    elemento["ponto"] = p
    elemento["origem"] = p


def _limpar_estado_texto_em_maos(canvas) -> None:
    canvas._texto_em_maos_idx = None
    canvas._texto_em_maos_cancelavel = False
    for nome in ("_texto_drag_idx", "_texto_drag_inicio_cena", "_texto_drag_inicio_pos"):
        try:
            setattr(canvas, nome, None)
        except Exception:
            pass
    try:
        canvas._texto_drag_moveu = False
    except Exception:
        pass


def _confirmar_texto_em_maos(canvas, idx: int, event, watched=None) -> None:
    _mover_texto_para_evento(canvas, idx, event, watched)
    try:
        canvas.cena.elementos[idx].pop("__texto_previa_ao_vivo", None)
    except Exception:
        pass
    _limpar_estado_texto_em_maos(canvas)
    canvas._selecionados = {idx}
    try:
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
    except Exception:
        pass
    try:
        if hasattr(canvas, "_emitir_elementos_alterados"):
            canvas._emitir_elementos_alterados()
    except Exception:
        pass
    try:
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText("Texto posicionado.")
    except Exception:
        pass
    canvas.update()


def _cancelar_texto_em_maos(canvas, idx: int) -> None:
    try:
        canvas.cena.elementos.pop(idx)
    except Exception:
        pass
    _limpar_estado_texto_em_maos(canvas)
    try:
        canvas._selecionados.clear()
    except Exception:
        pass
    try:
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText("Texto cancelado.")
    except Exception:
        pass
    canvas.update()


class _FiltroGlobalSoltarTexto(QObject):
    def eventFilter(self, watched, event):  # noqa: N802
        tipo = event.type()
        if tipo not in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.MouseMove):
            return False
        canvas = _canvas_do_widget(watched)
        if canvas is None:
            return False
        idx = _indice_texto_em_maos(canvas)
        if idx is None:
            return False
        if tipo == QEvent.MouseMove:
            try:
                _mover_texto_para_evento(canvas, idx, event, watched)
                canvas._selecionados = {idx}
                canvas.update()
                return False
            except Exception:
                return False
        try:
            botao = event.button()
        except Exception:
            return False
        if botao == Qt.LeftButton:
            _confirmar_texto_em_maos(canvas, idx, event, watched)
            event.accept()
            return True
        if botao == Qt.RightButton:
            _cancelar_texto_em_maos(canvas, idx)
            event.accept()
            return True
        return False


def aplicar_patch_soltar_texto_em_maos() -> None:
    global _FILTRO_GLOBAL
    if getattr(VisualizacaoCanvas, "_guimma_soltar_texto_em_maos_v2", False):
        return

    original_press = VisualizacaoCanvas.mousePressEvent
    original_move = VisualizacaoCanvas.mouseMoveEvent
    original_double = VisualizacaoCanvas.mouseDoubleClickEvent

    def mousePressEvent_soltar_texto(self, event):  # noqa: N802
        idx = _indice_texto_em_maos(self)
        if idx is not None:
            if event.button() == Qt.LeftButton:
                _confirmar_texto_em_maos(self, idx, event, self)
                event.accept()
                return
            if event.button() == Qt.RightButton:
                _cancelar_texto_em_maos(self, idx)
                event.accept()
                return
        original_press(self, event)

    def mouseMoveEvent_soltar_texto(self, event):  # noqa: N802
        idx = _indice_texto_em_maos(self)
        if idx is not None:
            try:
                _mover_texto_para_evento(self, idx, event, self)
                self._selecionados = {idx}
                self.update()
                event.accept()
                return
            except Exception:
                pass
        original_move(self, event)

    def mouseDoubleClickEvent_soltar_texto(self, event):  # noqa: N802
        idx = _indice_texto_em_maos(self)
        if idx is not None:
            if event.button() == Qt.LeftButton:
                _confirmar_texto_em_maos(self, idx, event, self)
                event.accept()
                return
            if event.button() == Qt.RightButton:
                _cancelar_texto_em_maos(self, idx)
                event.accept()
                return
        original_double(self, event)

    VisualizacaoCanvas.mousePressEvent = mousePressEvent_soltar_texto
    VisualizacaoCanvas.mouseMoveEvent = mouseMoveEvent_soltar_texto
    VisualizacaoCanvas.mouseDoubleClickEvent = mouseDoubleClickEvent_soltar_texto

    app = QApplication.instance()
    if app is not None:
        _FILTRO_GLOBAL = _FiltroGlobalSoltarTexto(app)
        app.installEventFilter(_FILTRO_GLOBAL)

    VisualizacaoCanvas._guimma_soltar_texto_em_maos_v2 = True


aplicar_patch_soltar_texto_em_maos()
