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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        form = QFormLayout()
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Uni-direcional"])
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

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if info is None:
            return True
        idx = int(info["elemento_idx"])
        self._idx_por_canvas[id(canvas)] = idx
        per = comprimento_total_elemento(canvas.cena.elementos[idx])
        dialog = self._obter_dialog(canvas)
        dialog.ed_de.setText(canvas.formatar_valor_unidade(per))
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(f"Perímetro atual: {canvas.formatar_valor_unidade(per)} ({getattr(canvas, '_unidade_sigla', 'cm')})")
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
        return dialog

    def _aplicar(self, canvas):
        chave = id(canvas)
        idx = self._idx_por_canvas.get(chave)
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        dialog = self._obter_dialog(canvas)
        try:
            alvo = float(str(dialog.ed_para.text()).replace(",", "."))
        except Exception:
            return
        el = canvas.cena.elementos[idx]
        atual = comprimento_total_elemento(el)
        if atual <= 1e-9 or alvo <= 1e-9:
            return
        fator = alvo / atual
        if el.get("tipo") == "polyline":
            pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if not pts:
                return
            p0 = pts[0]
            novos = [(p0.x() + ((p.x() - p0.x()) * fator), p0.y() + ((p.y() - p0.y()) * fator)) for p in pts]
            el["pontos"] = novos
        elif el.get("tipo") == "bezier_quadratica":
            p0 = QPointF(*el.get("p0", (0.0, 0.0)))
            for chave_p in ("p1", "p2"):
                p = QPointF(*el.get(chave_p, (0.0, 0.0)))
                el[chave_p] = (p0.x() + ((p.x() - p0.x()) * fator), p0.y() + ((p.y() - p0.y()) * fator))
        novo_per = comprimento_total_elemento(el)
        dialog.ed_de.setText(canvas.formatar_valor_unidade(novo_per))
        canvas._registrar_historico()
        canvas.update()
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(f"Perímetro redefinido para: {canvas.formatar_valor_unidade(novo_per)} ({getattr(canvas, '_unidade_sigla', 'cm')})")
