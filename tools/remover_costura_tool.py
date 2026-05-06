from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from tools.tool_base import FerramentaBase


class RemoverCosturaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Remover Costura")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(290)
        self.setStyleSheet(
            """
            QDialog { background:#f2f2f2; color:#111111; }
            QLabel { color:#111111; font-size:11px; }
            QComboBox {
                background:#ffffff; color:#111111;
                border:1px solid #aeb4ba; min-height:22px;
                padding-left:3px;
            }
            QPushButton {
                background:#f7f7f7; color:#111111;
                border:1px solid #b7b7b7; min-height:24px;
                padding:2px 14px;
            }
            QPushButton:hover { background:#ffffff; }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(7, 7, 7, 7)
        raiz.setSpacing(6)

        linha = QHBoxLayout()
        linha.addWidget(QLabel("Remover"), 0)
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Todo molde", "Selecionar"])
        linha.addWidget(self.cmb_modo, 1)
        raiz.addLayout(linha)

        self.lbl_status = QLabel("Clique em uma costura para realcar. Clique novamente para remover.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setMinimumHeight(44)
        raiz.addWidget(self.lbl_status)

        rodape = QHBoxLayout()
        self.btn_limpar = QPushButton("Limpar")
        self.btn_remover = QPushButton("Remover")
        rodape.addWidget(self.btn_limpar)
        rodape.addStretch(1)
        rodape.addWidget(self.btn_remover)
        raiz.addLayout(rodape)

    def atualizar_status(self, texto: str) -> None:
        self.lbl_status.setText(texto)


class Ferramenta(FerramentaBase):
    id_ferramenta = "remover_costura"
    nome = "Remover Costura"
    usa_painel_auxiliar = False

    _dialog_por_canvas: dict[int, RemoverCosturaDialog] = {}

    def __init__(self):
        super().__init__()
        self._alvo_pendente: dict | None = None
        self._realce_polylines: list[list[QPointF]] = []
        self._realce_segmentos: list[tuple[QPointF, QPointF]] = []

    def on_activate(self, canvas):
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self.set_status("Clique em uma costura para realcar. Clique novamente para remover.")

    def on_deactivate(self, canvas):
        self._limpar_realce(canvas, atualizar=False)
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if canvas is not None:
            canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        alvo = self._detectar_alvo(canvas, pos)
        if alvo is None:
            self._limpar_realce(canvas)
            self.set_status("Nenhuma costura encontrada nesse ponto.")
            event.accept()
            return True
        if self._mesmo_alvo(alvo, self._alvo_pendente):
            self._remover_alvo(canvas, alvo)
            event.accept()
            return True
        self._alvo_pendente = alvo
        self._preparar_realce(canvas, alvo)
        if alvo["tipo"] == "todo_molde":
            self.set_status("Costura do molde realcada em azul. Clique novamente para remover.")
        else:
            self.set_status("Trecho de costura realcado em azul. Clique novamente para remover.")
        canvas.update()
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        if event.key() == Qt.Key_Escape:
            self._limpar_realce(canvas)
            self.set_status("Selecao limpa. Clique em uma costura para realcar.")
            return True
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._alvo_pendente is not None:
                self._remover_alvo(canvas, self._alvo_pendente)
            return True
        return False

    def on_paint_overlay(self, canvas, painter):
        painter.save()
        pen = QPen(QColor("#1f9cff"), 2.4, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        for pontos in self._realce_polylines:
            for a, b in zip(pontos, pontos[1:]):
                painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        for a, b in self._realce_segmentos:
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def set_status(self, texto: str):
        for dialog in self._dialog_por_canvas.values():
            if dialog is not None and dialog.isVisible():
                dialog.atualizar_status(texto)

    def _obter_dialog(self, canvas) -> RemoverCosturaDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = RemoverCosturaDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.cmb_modo.currentTextChanged.connect(lambda _txt: self._limpar_realce(canvas))
            dialog.btn_limpar.clicked.connect(lambda: self._limpar_realce(canvas))
            dialog.btn_remover.clicked.connect(lambda: self._remover_alvo(canvas, self._alvo_pendente))
        return dialog

    def _modo(self, canvas) -> str:
        dialog = self._obter_dialog(canvas)
        return dialog.cmb_modo.currentText()

    def _detectar_alvo(self, canvas, pos: QPointF) -> dict | None:
        if self._modo(canvas) == "Todo molde":
            return self._detectar_alvo_todo_molde(canvas, pos)
        return self._detectar_alvo_segmento(canvas, pos)

    def _detectar_alvo_todo_molde(self, canvas, pos: QPointF) -> dict | None:
        idx_costura = self._indice_costura_proxima(canvas, pos)
        molde_id = ""
        if idx_costura is not None:
            costura = canvas.cena.elementos[idx_costura]
            molde_id = str(costura.get("costura_de_molde_id") or costura.get("molde_id") or "")
        if not molde_id:
            for idx in canvas._indices_elementos_em_ponto(pos):
                if 0 <= idx < len(canvas.cena.elementos):
                    el = canvas.cena.elementos[idx]
                    if el.get("molde") or str(el.get("molde_id") or ""):
                        molde_id = str(el.get("molde_id") or el.get("id") or "")
                        break
        if not molde_id and idx_costura is not None:
            return {"tipo": "todo_molde", "indices": [idx_costura], "molde_id": ""}
        indices = [
            idx for idx, el in enumerate(canvas.cena.elementos)
            if self._eh_costura(el)
            and str(el.get("costura_de_molde_id") or el.get("molde_id") or "") == molde_id
        ]
        if not indices:
            return None
        return {"tipo": "todo_molde", "indices": indices, "molde_id": molde_id}

    def _detectar_alvo_segmento(self, canvas, pos: QPointF) -> dict | None:
        melhor = None
        tolerancia = self._tolerancia(canvas)
        for idx, el in enumerate(canvas.cena.elementos):
            if not self._eh_costura(el):
                continue
            pontos = self._pontos_qt(el)
            for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
                dist = self._distancia_ponto_segmento(a, b, pos)
                if dist <= tolerancia and (melhor is None or dist < melhor["dist"]):
                    melhor = {"tipo": "segmento", "indice": idx, "segmento": seg_idx, "dist": dist}
        if melhor is None:
            return None
        return {"tipo": "segmento", "indice": melhor["indice"], "segmento": melhor["segmento"]}

    def _indice_costura_proxima(self, canvas, pos: QPointF) -> int | None:
        alvo = self._detectar_alvo_segmento(canvas, pos)
        if alvo is None:
            return None
        return int(alvo["indice"])

    def _preparar_realce(self, canvas, alvo: dict) -> None:
        self._realce_polylines = []
        self._realce_segmentos = []
        if alvo["tipo"] == "todo_molde":
            for idx in alvo.get("indices", []):
                if 0 <= idx < len(canvas.cena.elementos):
                    pontos = self._pontos_qt(canvas.cena.elementos[idx])
                    if len(pontos) >= 2:
                        self._realce_polylines.append(pontos)
            return
        idx = int(alvo["indice"])
        seg_idx = int(alvo["segmento"])
        if 0 <= idx < len(canvas.cena.elementos):
            pontos = self._pontos_qt(canvas.cena.elementos[idx])
            if 0 <= seg_idx < len(pontos) - 1:
                self._realce_segmentos.append((pontos[seg_idx], pontos[seg_idx + 1]))

    def _remover_alvo(self, canvas, alvo: dict | None) -> None:
        if alvo is None:
            self.set_status("Nenhuma costura realcada para remover.")
            return
        if alvo["tipo"] == "todo_molde":
            indices = sorted([int(i) for i in alvo.get("indices", [])], reverse=True)
            for idx in indices:
                if 0 <= idx < len(canvas.cena.elementos):
                    del canvas.cena.elementos[idx]
            removidos = len(indices)
        else:
            removidos = 1 if self._remover_segmento(canvas, int(alvo["indice"]), int(alvo["segmento"])) else 0
        if removidos:
            canvas._registrar_historico()
            self._limpar_realce(canvas, atualizar=False)
            canvas.update()
            self.set_status("Costura removida. Clique em outra costura para continuar.")
        else:
            self.set_status("Nao foi possivel remover essa costura.")

    def _remover_segmento(self, canvas, idx: int, seg_idx: int) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        pontos = self._pontos_tuple(el)
        if not (0 <= seg_idx < len(pontos) - 1):
            return False
        fechado = len(pontos) >= 4 and self._dist_tuple(pontos[0], pontos[-1]) <= 1e-6
        if fechado:
            base = pontos[:-1]
            n = len(base)
            if n <= 2:
                del canvas.cena.elementos[idx]
                return True
            novos = [base[(seg_idx + 1 + offset) % n] for offset in range(n - 1)]
            el["pontos"] = novos
            return True
        if len(pontos) <= 2:
            del canvas.cena.elementos[idx]
            return True
        del pontos[seg_idx + 1]
        el["pontos"] = pontos
        return True

    def _limpar_realce(self, canvas, atualizar: bool = True) -> None:
        self._alvo_pendente = None
        self._realce_polylines = []
        self._realce_segmentos = []
        if atualizar and canvas is not None:
            canvas.update()

    def _mesmo_alvo(self, a: dict | None, b: dict | None) -> bool:
        if a is None or b is None or a.get("tipo") != b.get("tipo"):
            return False
        if a["tipo"] == "todo_molde":
            return sorted(a.get("indices", [])) == sorted(b.get("indices", []))
        return a.get("indice") == b.get("indice") and a.get("segmento") == b.get("segmento")

    def _eh_costura(self, el: dict) -> bool:
        subtipo = str(el.get("subtipo_audaces") or el.get("metadados", {}).get("subtipo_audaces") or "")
        return el.get("tipo") == "polyline" and (subtipo == "costura" or bool(el.get("costura_de_molde_id")))

    def _pontos_qt(self, el: dict) -> list[QPointF]:
        return [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]

    def _pontos_tuple(self, el: dict) -> list[tuple[float, float]]:
        return [(float(x), float(y)) for x, y in el.get("pontos", [])]

    def _tolerancia(self, canvas) -> float:
        return 9.0 / max(float(getattr(canvas, "zoom", 1.0)), 1e-6)

    @staticmethod
    def _dist_tuple(a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt(((a[0] - b[0]) ** 2) + ((a[1] - b[1]) ** 2))

    @staticmethod
    def _distancia_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-9:
            return sqrt(((p.x() - a.x()) ** 2) + ((p.y() - a.y()) ** 2))
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return sqrt(((p.x() - proj.x()) ** 2) + ((p.y() - proj.y()) ** 2))
