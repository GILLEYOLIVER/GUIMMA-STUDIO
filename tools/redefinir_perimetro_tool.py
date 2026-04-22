from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from tools.medicao_utils import comprimento_total_elemento, selecionar_segmento_mais_proximo
from tools.tool_base import FerramentaBase


class RedefinirPerimetroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Redefinir perímetro")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(255)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel { color:#111111; }
            QComboBox, QLineEdit {
                background:#ffffff; color:#111111;
                border:1px solid #b5bcc3; min-height:22px;
            }
            QPushButton {
                background:#f7f7f7; color:#111111;
                border:1px solid #b7bec5; min-height:22px;
            }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        form = QFormLayout()
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Manter extremos", "Uni-direcional", "Bi-direcional"])
        self.ed_de = QLineEdit("0")
        self.ed_de.setReadOnly(True)
        self.ed_para = QLineEdit("10")
        form.addRow("Modo", self.cmb_modo)
        form.addRow("De (cm)", self.ed_de)
        form.addRow("Para (cm)", self.ed_para)
        lay.addLayout(form)
        rod = QHBoxLayout()
        self.btn_aplicar = QPushButton("Aplicar")
        rod.addStretch(1)
        rod.addWidget(self.btn_aplicar)
        lay.addLayout(rod)


class Ferramenta(FerramentaBase):
    id_ferramenta = "redefinir_perimetro"
    nome = "Redefinir Perimetro"
    usa_painel_auxiliar = False

    _dialog_por_canvas: dict[int, RedefinirPerimetroDialog] = {}
    _idx_por_canvas: dict[int, int] = {}
    _preview_ativo_por_canvas: dict[int, bool] = {}
    _snapshot_por_canvas: dict[int, dict] = {}

    def on_activate(self, canvas):
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText("Redefinir perímetro: clique em um contorno para carregar o valor atual.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._preview_ativo_por_canvas.pop(id(canvas), None)
        self._snapshot_por_canvas.pop(id(canvas), None)

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        chave = id(canvas)
        if self._preview_ativo_por_canvas.get(chave):
            canvas._registrar_historico()
            self._preview_ativo_por_canvas[chave] = False
            self._snapshot_por_canvas.pop(chave, None)
            if getattr(canvas, "lbl_status", None) is not None:
                canvas.lbl_status.setText("Redefinição de perímetro confirmada.")
            event.accept()
            return True
        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if info is None:
            return True
        idx = int(info["elemento_idx"])
        self._idx_por_canvas[id(canvas)] = idx
        per = comprimento_total_elemento(canvas.cena.elementos[idx])
        dialog = self._obter_dialog(canvas)
        dialog.ed_de.setText(canvas.formatar_valor_unidade(per))
        self._snapshot_por_canvas[chave] = dict(canvas.cena.elementos[idx])
        self._preview_ativo_por_canvas[chave] = True
        self._aplicar_preview(canvas)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText("Prévia aplicada. Clique esquerdo novamente para confirmar.")
        canvas.update()
        event.accept()
        return True

    def _obter_dialog(self, canvas) -> RedefinirPerimetroDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = RedefinirPerimetroDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.btn_aplicar.clicked.connect(lambda: self._aplicar(canvas))
            dialog.ed_para.returnPressed.connect(lambda: self._aplicar(canvas))
            dialog.ed_para.editingFinished.connect(lambda: self._aplicar_preview(canvas))
            dialog.cmb_modo.currentTextChanged.connect(lambda _txt: self._aplicar_preview(canvas))
        return dialog

    def _aplicar(self, canvas):
        self._aplicar_preview(canvas)
        self._preview_ativo_por_canvas[id(canvas)] = True

    def _aplicar_preview(self, canvas):
        chave = id(canvas)
        idx = self._idx_por_canvas.get(chave)
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        snapshot = self._snapshot_por_canvas.get(chave)
        if not snapshot:
            self._snapshot_por_canvas[chave] = dict(canvas.cena.elementos[idx])
            snapshot = self._snapshot_por_canvas[chave]
        dialog = self._obter_dialog(canvas)
        try:
            alvo = float(str(dialog.ed_para.text()).replace(",", "."))
        except Exception:
            return
        atual = comprimento_total_elemento(snapshot)
        if atual <= 1e-9 or alvo <= 1e-9:
            return
        fator = alvo / atual
        modo = dialog.cmb_modo.currentText().strip().lower()
        el = dict(snapshot)
        if el.get("tipo") == "polyline":
            pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if not pts:
                return
            if "bi" in modo:
                cx = sum(p.x() for p in pts) / len(pts)
                cy = sum(p.y() for p in pts) / len(pts)
                p0 = QPointF(cx, cy)
            else:
                p0 = pts[0]
            novos_qt = [QPointF(p0.x() + ((p.x() - p0.x()) * fator), p0.y() + ((p.y() - p0.y()) * fator)) for p in pts]
            if "manter" in modo and len(novos_qt) >= 2:
                d_ini = QPointF(pts[0].x() - novos_qt[0].x(), pts[0].y() - novos_qt[0].y())
                d_fim = QPointF(pts[-1].x() - novos_qt[-1].x(), pts[-1].y() - novos_qt[-1].y())
                ajustados = []
                total = max(1, len(novos_qt) - 1)
                for i, p in enumerate(novos_qt):
                    t = i / total
                    dx = d_ini.x() + ((d_fim.x() - d_ini.x()) * t)
                    dy = d_ini.y() + ((d_fim.y() - d_ini.y()) * t)
                    ajustados.append(QPointF(p.x() + dx, p.y() + dy))
                novos_qt = ajustados
            novos = [(p.x(), p.y()) for p in novos_qt]
            el["pontos"] = novos
        elif el.get("tipo") == "bezier_quadratica":
            p0 = QPointF(*el.get("p0", (0.0, 0.0)))
            if "bi" in modo:
                p2 = QPointF(*el.get("p2", (0.0, 0.0)))
                p0 = QPointF((p0.x() + p2.x()) / 2.0, (p0.y() + p2.y()) / 2.0)
            for chave_p in ("p0", "p1", "p2"):
                p = QPointF(*el.get(chave_p, (0.0, 0.0)))
                el[chave_p] = (p0.x() + ((p.x() - p0.x()) * fator), p0.y() + ((p.y() - p0.y()) * fator))
            if "manter" in modo:
                el["p0"] = snapshot.get("p0", el["p0"])
                el["p2"] = snapshot.get("p2", el["p2"])
        canvas.cena.elementos[idx] = el
        novo_per = comprimento_total_elemento(el)
        dialog.ed_de.setText(canvas.formatar_valor_unidade(novo_per))
        canvas.update()
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(f"Prévia perímetro: {canvas.formatar_valor_unidade(novo_per)} ({getattr(canvas, '_unidade_sigla', 'cm')}) | clique esquerdo confirma")
