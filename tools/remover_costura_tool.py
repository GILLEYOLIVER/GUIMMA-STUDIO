from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from tools.costura_tool import Ferramenta as FerramentaCostura
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import restaurar_posicao, salvar_posicao


class RemoverCosturaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:remover_costura"
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

    def moveEvent(self, event):
        salvar_posicao(self, self._chave_posicao)
        super().moveEvent(event)

    def hideEvent(self, event):
        salvar_posicao(self, self._chave_posicao)
        super().hideEvent(event)

    def closeEvent(self, event):
        salvar_posicao(self, self._chave_posicao)
        super().closeEvent(event)


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
        self._costura_helper = FerramentaCostura()

    def on_activate(self, canvas):
        dialog = self._obter_dialog(canvas)
        dialog.adjustSize()
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        restaurar_posicao(dialog, "dialog:remover_costura", fallback=fallback)
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
            if self._eh_costura_graduacao(el):
                continue
            molde_id = self._molde_id_costura(el)
            molde = self._molde_por_id(canvas, molde_id)
            if not isinstance(molde, dict):
                continue
            alvo_geom = self._costura_helper._alvo_geometrico_costura_sincronizada(molde, el)
            if not isinstance(alvo_geom, dict):
                continue
            total = self._costura_helper._total_segmentos_elemento(alvo_geom)
            for seg_idx in self._segmentos_ativos_costura(el, total):
                pontos = self._pontos_costura_segmento(canvas, molde, el, seg_idx)
                dist = self._distancia_ponto_polyline(pos, pontos)
                if dist <= tolerancia and (melhor is None or dist < melhor["dist"]):
                    melhor = {
                        "tipo": "segmento",
                        "indice": idx,
                        "segmento": seg_idx,
                        "dist": dist,
                        "molde_id": molde_id,
                    }
        if melhor is None:
            return None
        return {
            "tipo": "segmento",
            "indice": melhor["indice"],
            "segmento": melhor["segmento"],
            "molde_id": melhor.get("molde_id", ""),
        }

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
        molde_id = str(alvo.get("molde_id") or "")
        molde = self._molde_por_id(canvas, molde_id)
        if isinstance(molde, dict) and 0 <= idx < len(canvas.cena.elementos):
            costura = canvas.cena.elementos[idx]
            if self._eh_costura(costura) and not self._eh_costura_graduacao(costura):
                pontos = self._pontos_costura_segmento(canvas, molde, costura, seg_idx)
                if len(pontos) >= 2:
                    self._realce_polylines.append(pontos)
        if not self._realce_polylines and 0 <= idx < len(canvas.cena.elementos):
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
            molde_id = str(alvo.get("molde_id") or "")
            removidos = self._remover_segmento_costura_molde(canvas, molde_id, int(alvo["indice"]), int(alvo["segmento"]))
        if removidos:
            canvas._registrar_historico()
            self._limpar_realce(canvas, atualizar=False)
            canvas.update()
            self.set_status("Costura removida. Clique em outra costura para continuar.")
        else:
            self.set_status("Nao foi possivel remover essa costura.")

    def _remover_segmento_costura_molde(self, canvas, molde_id: str, idx_fallback: int, seg_idx: int) -> int:
        if not molde_id:
            return 1 if self._remover_segmento_legado(canvas, idx_fallback, seg_idx) else 0
        alterados = 0
        remover_indices: list[int] = []
        molde = self._molde_por_id(canvas, molde_id)
        if not isinstance(molde, dict):
            return 0

        costuras_base = [
            (idx, el)
            for idx, el in self._costuras_do_molde(canvas, molde_id)
            if not self._eh_costura_graduacao(el)
        ]
        if 0 <= idx_fallback < len(canvas.cena.elementos):
            costuras_fallback = [(idx, el) for idx, el in costuras_base if idx == idx_fallback]
            if costuras_fallback:
                costuras_base = costuras_fallback

        for idx, el in costuras_base:
            alvo_geom = self._costura_helper._alvo_geometrico_costura_sincronizada(molde, el)
            if not isinstance(alvo_geom, dict):
                continue
            total = self._costura_helper._total_segmentos_elemento(alvo_geom)
            if total <= 0:
                continue
            ativos = set(self._segmentos_ativos_costura(el, total))
            seg = int(seg_idx) % total
            if seg not in ativos:
                continue
            ativos.remove(seg)
            if not ativos:
                remover_indices.append(idx)
                alterados += 1
                continue
            base = self._costura_helper._base_interativa_elemento(alvo_geom)
            ordem = self._costura_helper._ordenar_segmentos_contiguos(base, ativos) or self._costura_helper._ordenar_segmentos_horario(base, ativos)
            el["costura_segmentos"] = [int(s) for s in ordem]
            el["costura_parcial"] = len(ativos) < total
            metadados = el.get("metadados")
            if isinstance(metadados, dict):
                metadados["costura_segmentos"] = [int(s) for s in ordem]
                metadados["costura_parcial"] = bool(el["costura_parcial"])
            alterados += 1

        for idx in sorted(set(remover_indices), reverse=True):
            if 0 <= idx < len(canvas.cena.elementos):
                del canvas.cena.elementos[idx]
        if alterados:
            self._costura_helper.sincronizar_costuras_graduacao_do_molde(canvas, molde_id)
            self._costura_helper.sincronizar_costuras_vinculadas(canvas)
        return alterados

    def _remover_segmento_legado(self, canvas, idx: int, seg_idx: int) -> bool:
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

    def _costuras_do_molde(self, canvas, molde_id: str) -> list[tuple[int, dict]]:
        alvo = str(molde_id or "").strip()
        if not alvo:
            return []
        return [
            (idx, el)
            for idx, el in enumerate(canvas.cena.elementos)
            if self._eh_costura(el) and self._molde_id_costura(el) == alvo
        ]

    def _molde_por_id(self, canvas, molde_id: str) -> dict | None:
        alvo = str(molde_id or "").strip()
        if not alvo:
            return None
        for el in canvas.cena.elementos:
            if isinstance(el, dict) and el.get("molde"):
                atual = str(el.get("molde_id") or el.get("id") or "").strip()
                if atual == alvo:
                    return el
        return None

    def _molde_id_costura(self, costura: dict) -> str:
        metadados = costura.get("metadados") if isinstance(costura.get("metadados"), dict) else {}
        return str(
            costura.get("costura_de_molde_id")
            or metadados.get("costura_de_molde_id")
            or costura.get("molde_id")
            or metadados.get("molde_id")
            or ""
        ).strip()

    def _segmentos_ativos_costura(self, costura: dict, total: int) -> list[int]:
        if total <= 0:
            return []
        segmentos = costura.get("costura_segmentos")
        ativos: list[int] = []
        if isinstance(segmentos, list) and segmentos:
            for item in segmentos:
                try:
                    seg = int(item) % total
                except Exception:
                    continue
                if seg not in ativos:
                    ativos.append(seg)
        if ativos:
            return ativos
        if costura.get("costura_parcial"):
            return []
        return list(range(total))

    def _pontos_costura_segmento(self, canvas, molde: dict, costura: dict, seg_idx: int) -> list[QPointF]:
        temporaria = dict(costura)
        temporaria["costura_segmentos"] = [int(seg_idx)]
        temporaria["costura_parcial"] = True
        pontos = self._costura_helper._gerar_pontos_costura_sincronizada(canvas, molde, temporaria)
        return [QPointF(float(x), float(y)) for x, y in pontos]

    def _distancia_ponto_polyline(self, pos: QPointF, pontos: list[QPointF]) -> float:
        if len(pontos) < 2:
            return float("inf")
        return min(self._distancia_ponto_segmento(a, b, pos) for a, b in zip(pontos, pontos[1:]))

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

    def _eh_costura_graduacao(self, el: dict) -> bool:
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        return bool(
            el.get("costura_graduacao")
            or metadados.get("costura_graduacao")
            or el.get("graduacao_tamanho")
            or metadados.get("graduacao_tamanho")
        )

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
