from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractSpinBox, QCheckBox, QComboBox, QLineEdit, QRadioButton, QSlider, QWidget


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


def ajustar_para_area(widget: QWidget, pos: QPoint, margem: int = 8) -> QPoint:
    parent = widget.parentWidget()
    if parent is not None and not widget.isWindow():
        area = parent.rect().adjusted(margem, margem, -margem, -margem)
    else:
        tela = widget.screen() or QGuiApplication.primaryScreen()
        area = tela.availableGeometry() if tela is not None else QRect(pos.x(), pos.y(), widget.width(), widget.height())

    largura_util = max(0, area.width() - widget.width())
    altura_util = max(0, area.height() - widget.height())
    x = area.left() + max(0, min(pos.x() - area.left(), largura_util))
    y = area.top() + max(0, min(pos.y() - area.top(), altura_util))
    return QPoint(int(x), int(y))


def restaurar_posicao(widget: QWidget, chave: str, fallback: QPoint | None = None) -> bool:
    restaurar_estado(widget, chave)
    pos = posicao_salva(chave)
    if pos is not None:
        widget.move(ajustar_para_area(widget, pos))
        return True
    if fallback is not None:
        widget.move(ajustar_para_area(widget, fallback))
    return False


class _FiltroMemoriaPosicao(QObject):
    def __init__(self, widget: QWidget, chave: str):
        super().__init__(widget)
        self._widget = widget
        self._chave = chave

    def eventFilter(self, obj, event):
        if obj is self._widget and event.type() in (QEvent.Move, QEvent.Hide, QEvent.Close):
            salvar_posicao(self._widget, self._chave)
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
