from __future__ import annotations

from copy import deepcopy
import os


CORES_GRADUACAO_PADRAO = {
    "menor": "#ffff00",
    "base": "#2b7cd3",
    "maior": "#ff8c00",
}


def idioma_graduacao_atual() -> str:
    idioma_env = os.environ.get("GUIMMA_IDIOMA", "").strip().lower()
    if idioma_env:
        return idioma_env
    try:
        from PySide6.QtCore import QLocale

        locale = QLocale.system()
        nome = str(locale.name() or "").lower()
        if nome:
            return nome
    except Exception:
        pass
    return "pt"


def grade_graduacao_padrao(idioma: str | None = None) -> tuple[str, list[dict]]:
    texto = str(idioma if idioma is not None else idioma_graduacao_atual()).strip().lower()
    espanhol = texto.startswith("es") or "spanish" in texto or "espan" in texto
    nomes = ("S", "M", "L") if espanhol else ("P", "M", "G")
    grade_nome = "S-L(M)" if espanhol else "P-G(M)"
    linhas = [
        {"ativo": True, "tamanho": nomes[0], "cor": CORES_GRADUACAO_PADRAO["menor"], "base": False},
        {"ativo": True, "tamanho": nomes[1], "cor": CORES_GRADUACAO_PADRAO["base"], "base": True},
        {"ativo": True, "tamanho": nomes[2], "cor": CORES_GRADUACAO_PADRAO["maior"], "base": False},
    ]
    return grade_nome, linhas


def aplicar_grade_graduacao_padrao(molde: dict, *, sobrescrever: bool = False, idioma: str | None = None) -> None:
    if not isinstance(molde, dict):
        return
    linhas_existentes = molde.get("graduacao_tamanhos")
    if not sobrescrever and isinstance(linhas_existentes, list) and linhas_existentes:
        return
    grade_nome, linhas = grade_graduacao_padrao(idioma)
    molde["graduacao_grade_nome"] = grade_nome
    molde["graduacao_tamanhos"] = deepcopy(linhas)
    molde["graduacao_tamanhos_ativos"] = [linha["tamanho"] for linha in linhas if linha.get("ativo", True)]


def grade_graduacao_referencia_canvas(canvas, ignorar_molde: dict | None = None) -> tuple[str, list[dict], list[str]] | None:
    cena = getattr(canvas, "cena", None)
    elementos = getattr(cena, "elementos", None)
    if not isinstance(elementos, list):
        return None
    for elemento in elementos:
        if not isinstance(elemento, dict) or not elemento.get("molde"):
            continue
        if ignorar_molde is not None and elemento is ignorar_molde:
            continue
        linhas = elemento.get("graduacao_tamanhos")
        if not isinstance(linhas, list) or not linhas:
            continue
        linhas_ref = [deepcopy(linha) for linha in linhas if isinstance(linha, dict)]
        if not linhas_ref:
            continue
        ativos = elemento.get("graduacao_tamanhos_ativos")
        if not isinstance(ativos, list):
            ativos = [
                str(linha.get("tamanho") or linha.get("nome") or "")
                for linha in linhas_ref
                if linha.get("ativo", True) and str(linha.get("tamanho") or linha.get("nome") or "").strip()
            ]
        return str(elemento.get("graduacao_grade_nome") or "").strip(), linhas_ref, [str(a) for a in ativos]
    return None


def aplicar_grade_graduacao_referencia_canvas(
    molde: dict,
    canvas,
    *,
    sobrescrever: bool = False,
    idioma: str | None = None,
) -> None:
    if not isinstance(molde, dict):
        return
    linhas_existentes = molde.get("graduacao_tamanhos")
    if not sobrescrever and isinstance(linhas_existentes, list) and linhas_existentes:
        return
    referencia = grade_graduacao_referencia_canvas(canvas, ignorar_molde=molde)
    if referencia is None:
        aplicar_grade_graduacao_padrao(molde, sobrescrever=sobrescrever, idioma=idioma)
        return
    grade_nome, linhas, ativos = referencia
    molde["graduacao_grade_nome"] = grade_nome
    molde["graduacao_tamanhos"] = deepcopy(linhas)
    molde["graduacao_tamanhos_ativos"] = list(ativos)
