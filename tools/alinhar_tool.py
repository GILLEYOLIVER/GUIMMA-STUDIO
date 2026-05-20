from __future__ import annotations

from math import isfinite

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QLabel, QVBoxLayout

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class AlinharDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:alinhar"
        self.setWindowTitle("Alinhar")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(280)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel { color:#111111; }
            QComboBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            """
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.cmb_operacao = QComboBox()
        self.cmb_operacao.addItems([
            "Esquerda", "Direita", "Topo", "Base", "Centro horizontal", "Centro vertical",
            "Distribuir horizontal", "Distribuir vertical", "Empilhar horizontal", "Empilhar vertical",
        ])
        self.cmb_referencia = QComboBox()
        self.cmb_referencia.addItems(["Seleção", "Primeiro selecionado", "Último selecionado", "Canvas/origem"])
        form.addRow("Operação", self.cmb_operacao)
        form.addRow("Referência", self.cmb_referencia)
        raiz.addLayout(form)


class Ferramenta(FerramentaBase):
    id_ferramenta = "alinhar"
    nome = "Alinhar"
    usa_painel_auxiliar = False
    descricao_painel = "Alinha ou distribui elementos selecionados."

    _dialog_por_canvas: dict[int, AlinharDialog] = {}

    def __init__(self):
        super().__init__()
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Alinhar: clique esquerdo seleciona. Clique esquerdo novamente aplica. Direito fecha.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._operacao_finalizada and not self._direito_confirma_fechamento:
                self._direito_confirma_fechamento = True
                self._status(canvas, "Operação finalizada. Clique direito novamente fecha a ferramenta.")
            else:
                self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        selecionados = set(getattr(canvas, "_selecionados", set()) or set())
        if candidatos and int(candidatos[0]) in selecionados and not (event.modifiers() & Qt.ShiftModifier) and len(selecionados) >= 2:
            self._aplicar(canvas)
            event.accept()
            return True
        if candidatos:
            idx = int(candidatos[0])
            if event.modifiers() & Qt.ShiftModifier:
                if idx in selecionados:
                    selecionados.remove(idx)
                else:
                    selecionados.add(idx)
            else:
                selecionados.add(idx)
            canvas._selecionados = selecionados
            canvas.update()
            self._operacao_finalizada = False
            self._direito_confirma_fechamento = False
            self._status(canvas, f"Selecionados: {len(selecionados)}. Clique esquerdo em selecionado/vazio aplica.")
            event.accept()
            return True
        if len(selecionados) >= 2:
            self._aplicar(canvas)
            event.accept()
            return True
        return False

    def on_key_press(self, canvas, event) -> bool:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._aplicar(canvas)
            event.accept()
            return True
        return False

    def _obter_dialog(self, canvas) -> AlinharDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = AlinharDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
        return dialog

    def _restaurar_dialog(self, canvas, dialog: AlinharDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _aplicar(self, canvas) -> None:
        indices = [int(i) for i in sorted(getattr(canvas, "_selecionados", set()) or []) if 0 <= int(i) < len(canvas.cena.elementos)]
        if len(indices) < 2:
            self._status(canvas, "Alinhar: selecione pelo menos dois elementos.")
            return
        dialog = self._obter_dialog(canvas)
        op = dialog.cmb_operacao.currentText()
        bboxes = {idx: self._bbox(canvas.cena.elementos[idx]) for idx in indices}
        bboxes = {idx: bb for idx, bb in bboxes.items() if bb is not None}
        if len(bboxes) < 2:
            self._status(canvas, "Alinhar: elementos sem geometria suficiente.")
            return
        if op.startswith("Distribuir") or op.startswith("Empilhar"):
            self._distribuir(canvas, list(bboxes), bboxes, op)
        else:
            ref = self._bbox_referencia(canvas, indices, bboxes, dialog.cmb_referencia.currentText())
            if ref is None:
                self._status(canvas, "Alinhar: referência inválida.")
                return
            self._alinhar(canvas, list(bboxes), bboxes, op, ref)
        canvas._registrar_historico()
        canvas.update()
        self._operacao_finalizada = True
        self._direito_confirma_fechamento = False
        self._status(canvas, f"{op} aplicado em {len(bboxes)} elemento(s). Clique esquerdo inicia nova seleção; direito fecha.")

    def _fechar(self, canvas) -> None:
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Alinhar finalizada. Voltando para Selecionar.")

    def _alinhar(self, canvas, indices: list[int], bboxes: dict[int, tuple[float, float, float, float]], op: str, ref: tuple[float, float, float, float]):
        rminx, rminy, rmaxx, rmaxy = ref
        rcx = (rminx + rmaxx) / 2.0
        rcy = (rminy + rmaxy) / 2.0
        for idx in indices:
            minx, miny, maxx, maxy = bboxes[idx]
            cx = (minx + maxx) / 2.0
            cy = (miny + maxy) / 2.0
            dx = dy = 0.0
            if op == "Esquerda":
                dx = rminx - minx
            elif op == "Direita":
                dx = rmaxx - maxx
            elif op == "Topo":
                dy = rminy - miny
            elif op == "Base":
                dy = rmaxy - maxy
            elif op == "Centro horizontal":
                dx = rcx - cx
            elif op == "Centro vertical":
                dy = rcy - cy
            self._mover_elemento(canvas.cena.elementos[idx], dx, dy)

    def _distribuir(self, canvas, indices: list[int], bboxes: dict[int, tuple[float, float, float, float]], op: str):
        horizontal = op.endswith("horizontal")
        if horizontal:
            ordenados = sorted(indices, key=lambda i: (bboxes[i][0] + bboxes[i][2]) / 2.0)
            inicio = min(bboxes[i][0] for i in ordenados)
            fim = max(bboxes[i][2] for i in ordenados)
            total_larguras = sum(bboxes[i][2] - bboxes[i][0] for i in ordenados)
            if op.startswith("Empilhar"):
                cursor = inicio
                for idx in ordenados:
                    minx, _, maxx, _ = bboxes[idx]
                    self._mover_elemento(canvas.cena.elementos[idx], cursor - minx, 0.0)
                    cursor += (maxx - minx)
            else:
                espaco = (fim - inicio - total_larguras) / max(1, len(ordenados) - 1)
                cursor = inicio
                for idx in ordenados:
                    minx, _, maxx, _ = bboxes[idx]
                    self._mover_elemento(canvas.cena.elementos[idx], cursor - minx, 0.0)
                    cursor += (maxx - minx) + espaco
        else:
            ordenados = sorted(indices, key=lambda i: (bboxes[i][1] + bboxes[i][3]) / 2.0)
            inicio = min(bboxes[i][1] for i in ordenados)
            fim = max(bboxes[i][3] for i in ordenados)
            total_alturas = sum(bboxes[i][3] - bboxes[i][1] for i in ordenados)
            if op.startswith("Empilhar"):
                cursor = inicio
                for idx in ordenados:
                    _, miny, _, maxy = bboxes[idx]
                    self._mover_elemento(canvas.cena.elementos[idx], 0.0, cursor - miny)
                    cursor += (maxy - miny)
            else:
                espaco = (fim - inicio - total_alturas) / max(1, len(ordenados) - 1)
                cursor = inicio
                for idx in ordenados:
                    _, miny, _, maxy = bboxes[idx]
                    self._mover_elemento(canvas.cena.elementos[idx], 0.0, cursor - miny)
                    cursor += (maxy - miny) + espaco

    def _bbox_referencia(self, canvas, indices: list[int], bboxes: dict[int, tuple[float, float, float, float]], modo: str):
        if modo == "Primeiro selecionado":
            return bboxes.get(indices[0])
        if modo == "Último selecionado":
            return bboxes.get(indices[-1])
        if modo == "Canvas/origem":
            return (0.0, 0.0, 0.0, 0.0)
        minx = min(bb[0] for bb in bboxes.values())
        miny = min(bb[1] for bb in bboxes.values())
        maxx = max(bb[2] for bb in bboxes.values())
        maxy = max(bb[3] for bb in bboxes.values())
        return minx, miny, maxx, maxy

    def _bbox(self, el: dict) -> tuple[float, float, float, float] | None:
        pts = self._todos_pontos(el)
        if not pts:
            return None
        return min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts)

    def _mover_elemento(self, el: dict, dx: float, dy: float) -> None:
        def mov(p):
            return (float(p[0]) + dx, float(p[1]) + dy)
        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro", "distancias_no_perimetro", "marcacoes_perimetro"):
            if isinstance(el.get(chave), list):
                el[chave] = [mov(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]
        for chave in ("fio_origem", "fio_fim", "p0", "p1", "p2"):
            if self._eh_ponto(el.get(chave)):
                el[chave] = mov(el[chave])
        for chave in ("pontos_controle_principais", "pontos_auxiliares"):
            if isinstance(el.get(chave), list):
                for item in el[chave]:
                    if isinstance(item, dict) and "x" in item and "y" in item:
                        item["x"] = float(item["x"]) + dx
                        item["y"] = float(item["y"]) + dy

    def _todos_pontos(self, el: dict) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro"):
            for p in el.get(chave, []) if isinstance(el.get(chave), list) else []:
                if self._eh_ponto(p):
                    pts.append((float(p[0]), float(p[1])))
        for chave in ("fio_origem", "fio_fim", "p0", "p1", "p2"):
            if self._eh_ponto(el.get(chave)):
                pts.append((float(el[chave][0]), float(el[chave][1])))
        return pts

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
