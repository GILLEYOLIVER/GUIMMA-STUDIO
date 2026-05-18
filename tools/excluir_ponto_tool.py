from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "excluir_ponto"
    nome = "Excluir Ponto"
    descricao_painel = "Remove pontos de contorno mantendo geometria mínima válida."

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self.set_status("Clique sobre um vértice para excluir.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        alvo = self._vertice_em_ponto(canvas, pos)
        if alvo is None:
            self.set_status("Nenhum vértice encontrado para exclusão.")
            return False
        idx, p_idx = alvo
        el = canvas.cena.elementos[idx]
        pontos = list(el.get("pontos", []))
        if len(pontos) <= 2:
            self.set_status("Elemento com poucos pontos: não é possível excluir.")
            return False

        fechado = (
            len(pontos) >= 3
            and abs(pontos[0][0] - pontos[-1][0]) < 1e-9
            and abs(pontos[0][1] - pontos[-1][1]) < 1e-9
        )
        if fechado and p_idx in {0, len(pontos) - 1}:
            ponto_removido = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            pontos.pop(0)
            if pontos:
                pontos[-1] = pontos[0]
        else:
            ponto_removido = QPointF(float(pontos[p_idx][0]), float(pontos[p_idx][1]))
            pontos.pop(p_idx)
            if fechado and pontos:
                pontos[-1] = pontos[0]

        if len(pontos) < 2:
            self.set_status("Exclusão cancelada para evitar geometria inválida.")
            return False

        el["pontos"] = pontos
        self._sincronizar_controles_apos_exclusao(canvas, el, ponto_removido)
        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self.set_status("Ponto excluído com sucesso.")
        event.accept()
        return True

    def _vertice_em_ponto(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int] | None = None
        melhor_d = tolerancia
        for idx, el in enumerate(canvas.cena.elementos):
            if el.get("tipo") != "polyline":
                continue
            for p_idx, (x, y) in enumerate(el.get("pontos", [])):
                d = canvas._dist(QPointF(float(x), float(y)), pos)
                if d <= melhor_d:
                    melhor_d = d
                    melhor = (idx, p_idx)
        return melhor

    def _sincronizar_controles_apos_exclusao(self, canvas, el: dict, removido: QPointF) -> None:
        if not el.get("molde"):
            self._sincronizar_curva_livre(el, removido)
            return

        tolerancia = 10.0 / max(canvas.zoom, 0.001)
        for chave in ("controle_cantos", "controle_auxiliares"):
            controles = []
            for item in el.get(chave, []) or []:
                pt = self._ponto_qt(item)
                if pt is None:
                    continue
                if canvas._dist(pt, removido) <= tolerancia:
                    continue
                controles.append((pt.x(), pt.y()))
            el[chave] = controles

        el["pontos_controle_principais"] = [
            {"x": float(x), "y": float(y)}
            for x, y in el.get("controle_cantos", []) or []
        ]
        el["pontos_auxiliares"] = [
            {"x": float(x), "y": float(y)}
            for x, y in el.get("controle_auxiliares", []) or []
        ]

    def _sincronizar_curva_livre(self, el: dict, removido: QPointF) -> None:
        if not (
            el.get("curva_suave")
            or el.get("curva_editavel")
            or el.get("pontos_controle_curva")
            or el.get("pontos_principais")
        ):
            return
        tolerancia = 1e-6
        for chave in ("pontos_controle_curva", "pontos_principais", "pontos_controle"):
            origem = el.get(chave)
            if not isinstance(origem, list):
                continue
            filtrados = []
            for item in origem:
                pt = self._ponto_qt(item)
                if pt is None:
                    continue
                if ((pt.x() - removido.x()) ** 2 + (pt.y() - removido.y()) ** 2) ** 0.5 <= tolerancia:
                    continue
                filtrados.append((pt.x(), pt.y()))
            el[chave] = filtrados

    @staticmethod
    def _ponto_qt(p) -> QPointF | None:
        try:
            if isinstance(p, QPointF):
                return QPointF(p)
            if isinstance(p, dict):
                return QPointF(float(p["x"]), float(p["y"]))
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                return QPointF(float(p[0]), float(p[1]))
        except Exception:
            return None
        return None
