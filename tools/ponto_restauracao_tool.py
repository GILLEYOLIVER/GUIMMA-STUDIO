from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from time import monotonic

from tools.tool_base import FerramentaBase


_STORE_ATTR = "_guimma_pontos_restauracao_moldes"
_LAST_ATTR = "_guimma_ultimo_ponto_restauracao"
_DEBOUNCE_ATTR = "_guimma_ponto_restauracao_ultimo_disparo"


class Ferramenta(FerramentaBase):
    id_ferramenta = "ponto_restauracao"
    nome = "Ponto de Restauração"
    descricao_painel = "Cria uma cópia interna do molde selecionado para restauração posterior."

    def ativar(self):
        return "Selecione um molde e acione Ponto de Restauração."

    def on_activate(self, canvas):
        if self._chamada_duplicada(canvas):
            return None

        indices = self._indices_moldes_alvo(canvas)
        if not indices:
            self._status(canvas, "Selecione um molde para criar o ponto de restauração.")
            return None

        store = getattr(canvas, _STORE_ATTR, None)
        if not isinstance(store, dict):
            store = {}
            setattr(canvas, _STORE_ATTR, store)

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        salvos = []
        for idx in indices:
            elemento = self._elemento(canvas, idx)
            if not isinstance(elemento, dict) or not elemento.get("molde"):
                continue
            copia = self._copiar_elemento_limpo(canvas, elemento)
            nome = str(copia.get("nome_molde") or copia.get("nome") or f"Molde {idx + 1}").strip()
            store[int(idx)] = {
                "indice_original": int(idx),
                "nome": nome,
                "criado_em": agora,
                "snapshot": copia,
            }
            salvos.append(int(idx))

        if not salvos:
            self._status(canvas, "Nenhum molde válido encontrado para criar ponto de restauração.")
            return None

        setattr(canvas, _LAST_ATTR, list(salvos))
        self._piscar_moldes_salvos(canvas, salvos)
        if len(salvos) == 1:
            nome = store[salvos[0]].get("nome") or f"Molde {salvos[0] + 1}"
            self._status(canvas, f"Ponto de restauração criado para: {nome}.")
        else:
            self._status(canvas, f"Ponto de restauração criado para {len(salvos)} moldes.")
        return None

    def _chamada_duplicada(self, canvas) -> bool:
        agora = monotonic()
        ultimo = float(getattr(canvas, _DEBOUNCE_ATTR, 0.0) or 0.0)
        setattr(canvas, _DEBOUNCE_ATTR, agora)
        return (agora - ultimo) < 0.35

    def _indices_moldes_alvo(self, canvas) -> list[int]:
        elementos = list(getattr(getattr(canvas, "cena", None), "elementos", []) or [])
        selecionados = getattr(canvas, "_selecionados", set()) or set()
        indices = []
        try:
            candidatos = sorted(int(i) for i in selecionados)
        except Exception:
            candidatos = []

        for idx in candidatos:
            if 0 <= idx < len(elementos):
                el = elementos[idx]
                if isinstance(el, dict) and el.get("molde"):
                    indices.append(idx)

        if indices:
            return indices

        # Ajuda no caso de haver somente um molde no documento: evita exigir seleção manual.
        moldes = [idx for idx, el in enumerate(elementos) if isinstance(el, dict) and el.get("molde")]
        if len(moldes) == 1:
            try:
                canvas._selecionados = {moldes[0]}
            except Exception:
                pass
            return moldes
        return []

    def _elemento(self, canvas, idx: int) -> dict | None:
        elementos = getattr(getattr(canvas, "cena", None), "elementos", []) or []
        if 0 <= idx < len(elementos):
            return elementos[idx]
        return None

    def _copiar_elemento_limpo(self, canvas, elemento: dict) -> dict:
        try:
            if hasattr(canvas, "_elemento_serializavel"):
                return canvas._elemento_serializavel(elemento)
        except Exception:
            pass
        return deepcopy(elemento)

    def _piscar_moldes_salvos(self, canvas, indices: list[int]):
        try:
            if hasattr(canvas, "piscar_ponto_restauracao"):
                canvas.piscar_ponto_restauracao(indices)
        except Exception:
            pass

    def _status(self, canvas, mensagem: str):
        try:
            self.set_status(mensagem)
            return
        except Exception:
            pass
        try:
            janela = canvas.window() if hasattr(canvas, "window") else None
            lbl = getattr(janela, "lbl_status", None) if janela is not None else None
            if lbl is not None and hasattr(lbl, "setText"):
                lbl.setText(mensagem)
                return
        except Exception:
            pass
        try:
            lbl = getattr(canvas, "lbl_status", None)
            if lbl is not None and hasattr(lbl, "setText"):
                lbl.setText(mensagem)
        except Exception:
            pass
