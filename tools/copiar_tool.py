from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

try:
    from PySide6.QtCore import QTimer
except Exception:  # pragma: no cover - fallback apenas para ambientes sem Qt
    QTimer = None

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "copiar"
    nome = "Copiar"
    usa_painel_auxiliar = False
    descricao_painel = "Copia os elementos selecionados e volta para Selecionar."

    def on_activate(self, canvas):
        total = self._copiar_selecao(canvas)
        if total > 0:
            self._status(canvas, f"Copiado: {total} elemento(s). Use Colar para inserir uma cópia.")
        else:
            self._status(canvas, "Copiar: selecione um molde ou elemento antes de copiar.")
        self._voltar_para_selecionar(canvas)

    def on_mouse_press(self, canvas, event) -> bool:
        total = self._copiar_selecao(canvas)
        if total > 0:
            self._status(canvas, f"Copiado: {total} elemento(s).")
        else:
            self._status(canvas, "Copiar: nada selecionado.")
        self._voltar_para_selecionar(canvas)
        try:
            event.accept()
        except Exception:
            pass
        return True

    def _copiar_selecao(self, canvas) -> int:
        if canvas is None or not hasattr(canvas, "cena"):
            return 0

        selecionados = sorted(int(i) for i in (getattr(canvas, "_selecionados", set()) or set()))
        selecionados = [i for i in selecionados if 0 <= i < len(canvas.cena.elementos)]
        if not selecionados:
            return 0

        indices = self._indices_com_vinculos(canvas, selecionados)
        elementos = [deepcopy(canvas.cena.elementos[i]) for i in indices]
        bbox = self._bbox_elementos(elementos)

        buffer = {
            "versao": 2,
            "origem": "GUIMMA_STUDIO",
            "ferramenta": self.id_ferramenta,
            "indices_origem": indices,
            "bbox": bbox,
            "elementos": elementos,
        }
        if hasattr(canvas, "definir_buffer_copia"):
            canvas.definir_buffer_copia(buffer)
        else:
            canvas._buffer_copia = buffer
        canvas._offset_colagem = 0
        return len(elementos)

    def _indices_com_vinculos(self, canvas, selecionados: list[int]) -> list[int]:
        """Inclui costuras/linhas vinculadas quando o molde é copiado.

        A costura faz parte do molde. Portanto, ao copiar um molde, as linhas
        vinculadas a ele precisam ir junto para que a cópia não nasça incompleta.
        """
        indices = set(selecionados)
        for idx in list(selecionados):
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if bool(el.get("molde")) and hasattr(canvas, "_indices_costuras_vinculadas"):
                try:
                    indices.update(int(i) for i in canvas._indices_costuras_vinculadas(idx))
                except Exception:
                    pass
            molde_id = self._molde_id(el)
            if molde_id and bool(el.get("molde")):
                for j, outro in enumerate(canvas.cena.elementos):
                    if j in indices:
                        continue
                    if self._linha_vinculada_ao_molde(outro, molde_id):
                        indices.add(j)
        return sorted(i for i in indices if 0 <= i < len(canvas.cena.elementos))

    @staticmethod
    def _molde_id(elemento: dict) -> str:
        return str(elemento.get("molde_id") or elemento.get("id") or "").strip()

    @staticmethod
    def _linha_vinculada_ao_molde(elemento: dict, molde_id: str) -> bool:
        if not molde_id:
            return False
        if str(elemento.get("costura_de_molde_id") or "").strip() == molde_id:
            return True
        if bool(elemento.get("molde_linha_vinculada")) and str(elemento.get("molde_id") or "").strip() == molde_id:
            return True
        return False

    def _bbox_elementos(self, elementos: list[dict]) -> tuple[float, float, float, float] | None:
        pontos: list[tuple[float, float]] = []
        for el in elementos:
            pontos.extend(self._coletar_pontos(el))
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return (min(xs), min(ys), max(xs), max(ys))

    def _coletar_pontos(self, valor) -> list[tuple[float, float]]:
        pontos: list[tuple[float, float]] = []
        if isinstance(valor, dict):
            if "x" in valor and "y" in valor:
                try:
                    pontos.append((float(valor["x"]), float(valor["y"])))
                except Exception:
                    pass
            for item in valor.values():
                pontos.extend(self._coletar_pontos(item))
        elif isinstance(valor, (list, tuple)):
            if len(valor) >= 2 and self._numero(valor[0]) and self._numero(valor[1]):
                try:
                    pontos.append((float(valor[0]), float(valor[1])))
                except Exception:
                    pass
            else:
                for item in valor:
                    pontos.extend(self._coletar_pontos(item))
        return pontos

    @staticmethod
    def _numero(valor) -> bool:
        try:
            float(valor)
            return True
        except Exception:
            return False

    def _status(self, canvas, texto: str) -> None:
        try:
            if getattr(canvas, "lbl_status", None) is not None:
                canvas.lbl_status.setText(texto)
                return
        except Exception:
            pass
        try:
            self.set_status(texto)
        except Exception:
            pass

    def _voltar_para_selecionar(self, canvas) -> None:
        def aplicar():
            try:
                if hasattr(canvas, "ferramenta_padrao_solicitada"):
                    canvas.ferramenta_padrao_solicitada.emit("selecionar")
                elif hasattr(canvas, "set_ferramenta_ativa"):
                    canvas.set_ferramenta_ativa("selecionar")
            except Exception:
                pass

        if QTimer is not None:
            QTimer.singleShot(0, aplicar)
        else:
            aplicar()
