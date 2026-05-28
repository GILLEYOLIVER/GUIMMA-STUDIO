from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPainter


ALTURA_TEXTO_PADRAO_CM = 2.0
ESPACO_LINHAS_PADRAO_CM = 3.0


def _float_seguro(valor, padrao: float) -> float:
    try:
        return float(str(valor).replace(",", ".").replace("cm", "").strip())
    except Exception:
        return float(padrao)


def altura_texto_cm(canvas, elemento: dict | None = None) -> float:
    if isinstance(elemento, dict):
        for chave in ("texto_altura_cm", "altura_cm", "altura_texto_cm", "tamanho_texto_cm"):
            if chave in elemento:
                return max(0.2, _float_seguro(elemento.get(chave), ALTURA_TEXTO_PADRAO_CM))
    return max(0.2, _float_seguro(getattr(canvas, "_texto_altura_cm", ALTURA_TEXTO_PADRAO_CM), ALTURA_TEXTO_PADRAO_CM))


def espaco_linhas_cm(canvas, elemento: dict | None = None) -> float:
    if isinstance(elemento, dict):
        for chave in ("texto_espaco_linhas_cm", "espaco_linhas_cm", "entre_linhas_cm"):
            if chave in elemento:
                return max(0.2, _float_seguro(elemento.get(chave), ESPACO_LINHAS_PADRAO_CM))
    return max(0.2, _float_seguro(getattr(canvas, "_texto_espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM), ESPACO_LINHAS_PADRAO_CM))


def configurar_texto_canvas(canvas, altura_cm: float | None = None, espaco_linhas_cm_valor: float | None = None) -> None:
    if altura_cm is not None:
        canvas._texto_altura_cm = max(0.2, _float_seguro(altura_cm, ALTURA_TEXTO_PADRAO_CM))
    elif not hasattr(canvas, "_texto_altura_cm"):
        canvas._texto_altura_cm = ALTURA_TEXTO_PADRAO_CM
    if espaco_linhas_cm_valor is not None:
        canvas._texto_espaco_linhas_cm = max(0.2, _float_seguro(espaco_linhas_cm_valor, ESPACO_LINHAS_PADRAO_CM))
    elif not hasattr(canvas, "_texto_espaco_linhas_cm"):
        canvas._texto_espaco_linhas_cm = ESPACO_LINHAS_PADRAO_CM


def cor_texto(canvas, elemento: dict | None = None) -> QColor:
    valor = None
    if isinstance(elemento, dict):
        valor = elemento.get("cor_texto") or elemento.get("cor")
    if not valor:
        valor = getattr(canvas, "_linha_cor", "#ffffff")
    cor = QColor(str(valor or "#ffffff"))
    return cor if cor.isValid() else QColor("#ffffff")


def tamanho_texto_px(canvas, elemento: dict | None = None, minimo_px: int = 14, maximo_px: int = 260) -> int:
    altura = altura_texto_cm(canvas, elemento)
    zoom = max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.01)
    return int(max(minimo_px, min(maximo_px, altura * zoom)))


def aplicar_fonte_texto(painter: QPainter, canvas, elemento: dict | None = None, negrito: bool = False) -> QFont:
    fonte = QFont(painter.font())
    fonte.setPixelSize(tamanho_texto_px(canvas, elemento))
    fonte.setBold(bool(negrito))
    painter.setFont(fonte)
    return fonte
