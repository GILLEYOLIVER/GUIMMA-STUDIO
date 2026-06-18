from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSettings, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractSpinBox, QCheckBox, QComboBox, QDialog, QLineEdit, QRadioButton, QSlider, QWidget


def _settings() -> QSettings:
    return QSettings("GUIMMA", "GUIMMA-STUDIO")


def _grupo(chave: str) -> str:
    chave_limpa = "".join(c if c.isalnum() or c in "._:-" else "_" for c in str(chave))
    return f"caixas_flutuantes/{chave_limpa}"


def _grupo_estado(chave: str) -> str:
    chave_limpa = "".join(c if c.isalnum() or c in "._:-" else "_" for c in str(chave))
    return f"caixas_flutuantes_estado/{chave_limpa}"


def _valor_bool(valor) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    return str(valor).strip().lower() in {"1", "true", "sim", "yes", "on"}


def _widgets_com_estado(widget: QWidget):
    suportados = (QLineEdit, QComboBox, QCheckBox, QRadioButton, QAbstractSpinBox, QSlider)
    return [filho for filho in widget.findChildren(QWidget) if isinstance(filho, suportados)]


def _chave_widget_estado(filho: QWidget, contador: dict[str, int]) -> str:
    nome = str(filho.objectName() or "").strip()
    if nome:
        return f"{filho.__class__.__name__}:{nome}"
    classe = filho.__class__.__name__
    indice = contador.get(classe, 0)
    contador[classe] = indice + 1
    return f"{classe}:{indice}"


def restaurar_estado(widget: QWidget, chave: str) -> None:
    if widget is None:
        return
    cfg = _settings()
    cfg.beginGroup(_grupo_estado(chave))
    contador: dict[str, int] = {}
    setattr(widget, "_guimma_restaurando_estado", True)
    try:
        for filho in _widgets_com_estado(widget):
            chave_filho = _chave_widget_estado(filho, contador)
            if isinstance(filho, QLineEdit):
                valor = cfg.value(f"{chave_filho}/texto", None)
                if valor is not None:
                    filho.setText(str(valor))
            elif isinstance(filho, QComboBox):
                texto = cfg.value(f"{chave_filho}/texto", None)
                indice_salvo = cfg.value(f"{chave_filho}/indice", None)
                aplicado = False
                if texto is not None:
                    indice = filho.findText(str(texto))
                    if indice >= 0:
                        filho.setCurrentIndex(indice)
                        aplicado = True
                if not aplicado and indice_salvo is not None:
                    try:
                        indice = int(float(indice_salvo))
                    except (TypeError, ValueError):
                        indice = -1
                    if 0 <= indice < filho.count():
                        filho.setCurrentIndex(indice)
            elif isinstance(filho, (QCheckBox, QRadioButton)):
                valor = cfg.value(f"{chave_filho}/marcado", None)
                if valor is not None:
                    filho.setChecked(_valor_bool(valor))
            elif isinstance(filho, QSlider):
                valor = cfg.value(f"{chave_filho}/valor", None)
                if valor is not None:
                    try:
                        filho.setValue(int(float(valor)))
                    except (TypeError, ValueError):
                        pass
            elif isinstance(filho, QAbstractSpinBox) and hasattr(filho, "value") and hasattr(filho, "setValue"):
                valor = cfg.value(f"{chave_filho}/valor", None)
                if valor is not None:
                    try:
                        atual = filho.value()
                        novo = int(float(valor)) if isinstance(atual, int) and not isinstance(atual, bool) else float(valor)
                        filho.setValue(novo)
                    except (TypeError, ValueError):
                        pass
    finally:
        setattr(widget, "_guimma_restaurando_estado", False)
        cfg.endGroup()


def salvar_estado(widget: QWidget, chave: str) -> None:
    if widget is None or getattr(widget, "_guimma_restaurando_estado", False):
        return
    cfg = _settings()
    cfg.beginGroup(_grupo_estado(chave))
    contador: dict[str, int] = {}
    for filho in _widgets_com_estado(widget):
        chave_filho = _chave_widget_estado(filho, contador)
        if isinstance(filho, QLineEdit):
            cfg.setValue(f"{chave_filho}/texto", filho.text())
        elif isinstance(filho, QComboBox):
            cfg.setValue(f"{chave_filho}/texto", filho.currentText())
            cfg.setValue(f"{chave_filho}/indice", filho.currentIndex())
        elif isinstance(filho, (QCheckBox, QRadioButton)):
            cfg.setValue(f"{chave_filho}/marcado", filho.isChecked())
        elif isinstance(filho, QSlider):
            cfg.setValue(f"{chave_filho}/valor", filho.value())
        elif isinstance(filho, QAbstractSpinBox) and hasattr(filho, "value"):
            cfg.setValue(f"{chave_filho}/valor", filho.value())
    cfg.endGroup()
    cfg.sync()


def posicao_salva(chave: str) -> QPoint | None:
    cfg = _settings()
    cfg.beginGroup(_grupo(chave))
    x = cfg.value("x", None)
    y = cfg.value("y", None)
    cfg.endGroup()
    if x is None or y is None:
        return None
    try:
        return QPoint(int(float(x)), int(float(y)))
    except (TypeError, ValueError):
        return None


def salvar_posicao(widget: QWidget, chave: str) -> None:
    if widget is None:
        return
    salvar_estado(widget, chave)
    pos = widget.pos()
    cfg = _settings()
    cfg.beginGroup(_grupo(chave))
    cfg.setValue("x", int(pos.x()))
    cfg.setValue("y", int(pos.y()))
    cfg.endGroup()
    cfg.sync()


def _normalizar_qpoint(pos) -> QPoint:
    return QPoint(int(pos.x()), int(pos.y()))


def _mover_widget(widget: QWidget, pos: QPoint) -> None:
    destino = _normalizar_qpoint(pos)
    widget._guimma_ultima_posicao_programatica = QPoint(destino)  # type: ignore[attr-defined]
    widget.move(destino)


def _registrar_fallback_inicial(widget: QWidget, fallback: QPoint) -> None:
    widget._guimma_fallback_inicial = _normalizar_qpoint(fallback)  # type: ignore[attr-defined]

    def _aplicar():
        try:
            if getattr(widget, "_guimma_posicao_movida_usuario", False):
                return
            pos = getattr(widget, "_guimma_fallback_inicial", None)
            if isinstance(pos, QPoint):
                _mover_widget(widget, ajustar_para_area(widget, pos))
                widget._guimma_posicao_inicial_aplicada = True  # type: ignore[attr-defined]
        except RuntimeError:
            pass

    QTimer.singleShot(0, _aplicar)


def ajustar_para_area(widget: QWidget, pos: QPoint, margem: int = 8) -> QPoint:
    parent = widget.parentWidget()
    if parent is not None:
        if widget.isWindow():
            janela = parent.window() if parent.window() is not None else parent
            area = janela.frameGeometry().adjusted(margem, margem, -margem, -margem)
            if not area.isValid() or area.width() <= 0 or area.height() <= 0:
                canto = parent.mapToGlobal(parent.rect().topLeft())
                area = QRect(canto, parent.rect().size()).adjusted(margem, margem, -margem, -margem)
        else:
            area = parent.rect().adjusted(margem, margem, -margem, -margem)
    else:
        tela = widget.screen() or QGuiApplication.primaryScreen()
        area = tela.availableGeometry() if tela is not None else QRect(pos.x(), pos.y(), widget.width(), widget.height())

    largura_util = max(0, area.width() - widget.width())
    altura_util = max(0, area.height() - widget.height())
    x = area.left() + max(0, min(pos.x() - area.left(), largura_util))
    y = area.top() + max(0, min(pos.y() - area.top(), altura_util))
    return QPoint(int(x), int(y))


def _tela_para_widget(widget: QWidget, fallback: QPoint | None = None):
    try:
        if widget.windowHandle() is not None:
            tela = widget.windowHandle().screen()
            if tela is not None:
                return tela
    except Exception:
        pass
    try:
        tela = widget.screen()
        if tela is not None:
            return tela
    except Exception:
        pass
    try:
        parent = widget.parentWidget()
        if parent is not None and hasattr(parent, "mapToGlobal"):
            centro = parent.mapToGlobal(parent.rect().center())
            tela = QGuiApplication.screenAt(centro)
            if tela is not None:
                return tela
    except Exception:
        pass
    if fallback is not None:
        try:
            tela = QGuiApplication.screenAt(fallback)
            if tela is not None:
                return tela
        except Exception:
            pass
    return QGuiApplication.primaryScreen()


def centralizar_widget_na_tela(widget: QWidget, fallback: QPoint | None = None, margem: int = 16) -> None:
    if widget is None:
        return
    try:
        widget.adjustSize()
    except Exception:
        pass
    tela = _tela_para_widget(widget, fallback)
    if tela is None:
        return
    area = tela.availableGeometry()
    margem = max(0, int(margem))
    largura_max = max(120, area.width() - margem * 2)
    altura_max = max(90, area.height() - margem * 2)
    if widget.width() > largura_max or widget.height() > altura_max:
        widget.resize(min(widget.width(), largura_max), min(widget.height(), altura_max))
    geo = widget.frameGeometry()
    if not geo.isValid() or geo.width() <= 0 or geo.height() <= 0:
        geo = QRect(0, 0, max(1, widget.width()), max(1, widget.height()))
    geo.moveCenter(area.center())
    if geo.left() < area.left() + margem:
        geo.moveLeft(area.left() + margem)
    if geo.top() < area.top() + margem:
        geo.moveTop(area.top() + margem)
    if geo.right() > area.right() - margem:
        geo.moveRight(area.right() - margem)
    if geo.bottom() > area.bottom() - margem:
        geo.moveBottom(area.bottom() - margem)
    widget.move(geo.topLeft())


def restaurar_posicao(
    widget: QWidget,
    chave: str,
    fallback: QPoint | None = None,
    preferir_fallback_inicial: bool = True,
) -> bool:
    restaurar_estado(widget, chave)
    if fallback is None and isinstance(widget, QDialog):
        parent = widget.parentWidget()
        if (
            parent is not None
            and hasattr(parent, "calcular_posicao_painel_auxiliar")
            and hasattr(parent, "mapToGlobal")
        ):
            try:
                widget.adjustSize()
                pos_local = parent.calcular_posicao_painel_auxiliar(
                    widget.width(),
                    widget.height(),
                    abaixo_coordenadas=True,
                )
                fallback = parent.mapToGlobal(pos_local)
            except Exception:
                fallback = None
    if fallback is not None and preferir_fallback_inicial:
        _registrar_fallback_inicial(widget, fallback)
        _mover_widget(widget, ajustar_para_area(widget, fallback))
        widget._guimma_posicao_inicial_aplicada = True  # type: ignore[attr-defined]
        return False
    if fallback is not None and not getattr(widget, "_guimma_posicao_movida_usuario", False):
        _registrar_fallback_inicial(widget, fallback)
        _mover_widget(widget, ajustar_para_area(widget, fallback))
        widget._guimma_posicao_inicial_aplicada = True  # type: ignore[attr-defined]
        return False
    pos = posicao_salva(chave)
    if pos is not None:
        _mover_widget(widget, ajustar_para_area(widget, pos))
        widget._guimma_posicao_inicial_aplicada = True  # type: ignore[attr-defined]
        return True
    if fallback is not None:
        _registrar_fallback_inicial(widget, fallback)
        _mover_widget(widget, ajustar_para_area(widget, fallback))
        widget._guimma_posicao_inicial_aplicada = True  # type: ignore[attr-defined]
        return False
    if isinstance(widget, QDialog):
        centralizar_widget_na_tela(widget)
        widget._guimma_posicao_inicial_aplicada = True  # type: ignore[attr-defined]
    return False


class _FiltroMemoriaPosicao(QObject):
    def __init__(self, widget: QWidget, chave: str):
        super().__init__(widget)
        self._widget = widget
        self._chave = chave

    def eventFilter(self, obj, event):
        widget = getattr(self, "_widget", None)
        chave = getattr(self, "_chave", "")
        if widget is not None and obj is widget and event.type() in (QEvent.Show, QEvent.Move, QEvent.Hide, QEvent.Close):
            try:
                if event.type() == QEvent.Show:
                    fallback = getattr(widget, "_guimma_fallback_inicial", None)
                    if isinstance(fallback, QPoint) and not getattr(widget, "_guimma_posicao_movida_usuario", False):
                        _registrar_fallback_inicial(widget, fallback)
                    return super().eventFilter(obj, event)
                if event.type() == QEvent.Move:
                    programatica = getattr(widget, "_guimma_ultima_posicao_programatica", None)
                    if isinstance(programatica, QPoint) and widget.pos() == programatica:
                        return super().eventFilter(obj, event)
                    widget._guimma_posicao_movida_usuario = True  # type: ignore[attr-defined]
                salvar_posicao(widget, chave)
            except RuntimeError:
                pass
        return super().eventFilter(obj, event)


def _conectar_sinal_salvamento(filho: QWidget, chave: str) -> None:
    chaves = getattr(filho, "_guimma_memoria_estado_chaves", set())
    if chave in chaves:
        return
    chaves = set(chaves)
    chaves.add(chave)
    filho._guimma_memoria_estado_chaves = chaves  # type: ignore[attr-defined]

    def _salvar(*_args):
        raiz = filho.window()
        salvar_estado(raiz, chave)

    if isinstance(filho, QLineEdit):
        filho.textChanged.connect(_salvar)
    elif isinstance(filho, QComboBox):
        filho.currentIndexChanged.connect(_salvar)
    elif isinstance(filho, (QCheckBox, QRadioButton)):
        filho.toggled.connect(_salvar)
    elif isinstance(filho, QSlider):
        filho.valueChanged.connect(_salvar)
    elif isinstance(filho, QAbstractSpinBox):
        sinal = getattr(filho, "valueChanged", None)
        if sinal is not None:
            sinal.connect(_salvar)
        filho.editingFinished.connect(_salvar)


def instalar_memoria_posicao(widget: QWidget, chave: str) -> None:
    if widget is None or getattr(widget, "_guimma_memoria_posicao_instalada", False):
        return
    filtro = _FiltroMemoriaPosicao(widget, chave)
    widget.installEventFilter(filtro)
    for filho in _widgets_com_estado(widget):
        _conectar_sinal_salvamento(filho, chave)
    widget._guimma_memoria_posicao_instalada = True  # type: ignore[attr-defined]
    widget._guimma_memoria_posicao_chave = chave  # type: ignore[attr-defined]
    widget._guimma_memoria_posicao_filtro = filtro  # type: ignore[attr-defined]
