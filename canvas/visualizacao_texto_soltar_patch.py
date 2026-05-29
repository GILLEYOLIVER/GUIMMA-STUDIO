from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from canvas.visualizacao import VisualizacaoCanvas


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


def _posicao_cena_do_evento(canvas, event) -> QPointF:
    try:
        return canvas._tela_para_cena(event.position())
    except Exception:
        try:
            return canvas._tela_para_cena(QPointF(float(event.x()), float(event.y())))
        except Exception:
            return QPointF(0.0, 0.0)


def _mover_texto_para_evento(canvas, idx: int, event) -> None:
    ponto = _posicao_cena_do_evento(canvas, event)
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


def _confirmar_texto_em_maos(canvas, idx: int, event) -> None:
    _mover_texto_para_evento(canvas, idx, event)
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


def aplicar_patch_soltar_texto_em_maos() -> None:
    if getattr(VisualizacaoCanvas, "_guimma_soltar_texto_em_maos_v1", False):
        return

    original_press = VisualizacaoCanvas.mousePressEvent
    original_move = VisualizacaoCanvas.mouseMoveEvent
    original_double = VisualizacaoCanvas.mouseDoubleClickEvent

    def mousePressEvent_soltar_texto(self, event):  # noqa: N802
        idx = _indice_texto_em_maos(self)
        if idx is not None:
            if event.button() == Qt.LeftButton:
                _confirmar_texto_em_maos(self, idx, event)
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
                _mover_texto_para_evento(self, idx, event)
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
                _confirmar_texto_em_maos(self, idx, event)
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
    VisualizacaoCanvas._guimma_soltar_texto_em_maos_v1 = True


aplicar_patch_soltar_texto_em_maos()
