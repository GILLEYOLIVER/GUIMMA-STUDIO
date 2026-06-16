from __future__ import annotations

from shiboken6 import isValid


def qobject_valido(obj) -> bool:
    if obj is None:
        return False
    try:
        return bool(isValid(obj))
    except RuntimeError:
        return False
    except Exception:
        return False


def esconder_se_valido(obj) -> None:
    if not qobject_valido(obj):
        return
    try:
        obj.hide()
    except RuntimeError:
        return


def limpar_global_ao_destruir(obj, cls, attr: str) -> None:
    if not qobject_valido(obj):
        return
    try:
        obj.destroyed.connect(lambda *_args: setattr(cls, attr, None))
    except Exception:
        pass
