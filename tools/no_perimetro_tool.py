from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from tools.medicao_utils import mensagem_status, selecionar_segmento_mais_proximo, segmentos_de_elemento
from tools.tool_base import FerramentaBase


class PontosNoPerimetroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pontos no elemento")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(270)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        grid = QGridLayout()
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Perímetro (cm)"])
        self.ed_passo = QLineEdit("2")
        grid.addWidget(self.cmb_modo, 0, 0)
        grid.addWidget(self.ed_passo, 0, 1)
        lay.addLayout(grid)

        self.chk_dividir = QCheckBox("Dividir elemento")
        self.chk_dividir.setChecked(True)
        lay.addWidget(self.chk_dividir)

        self.chk_colocar = QCheckBox("Colocar ponto")
        self.chk_colocar.setChecked(True)
        lay.addWidget(self.chk_colocar)

        self.chk_manter = QCheckBox("Manter distâncias nos moldes")
        self.chk_manter.setChecked(True)
        lay.addWidget(self.chk_manter)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_aplicar = QPushButton("Aplicar")
        btn_row.addWidget(self.btn_aplicar)
        lay.addLayout(btn_row)

    def passo_unidade(self) -> float:
        try:
            return max(0.001, float(self.ed_passo.text().replace(",", ".").strip()))
        except Exception:
            return 2.0


class Ferramenta(FerramentaBase):
    id_ferramenta = "no_perimetro"
    nome = "No Perimetro"
    descricao_painel = "Clique no contorno para marcar pontos por distância no perímetro."

    def __init__(self):
        super().__init__()
        self._idx_destaque: int | None = None
        self._pontos_preview: list[QPointF] = []
        self._dialog_por_canvas: dict[int, PontosNoPerimetroDialog] = {}

    def _obter_dialog(self, canvas) -> PontosNoPerimetroDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = PontosNoPerimetroDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        if not hasattr(dialog, "_callbacks_ligados"):
            dialog._callbacks_ligados = set()  # type: ignore[attr-defined]
        if chave not in dialog._callbacks_ligados:  # type: ignore[attr-defined]
            dialog.btn_aplicar.clicked.connect(lambda _=False, c=canvas: self._aplicar_ultimo(c))
            dialog._callbacks_ligados.add(chave)  # type: ignore[attr-defined]
        return dialog

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._idx_destaque = None
        self._pontos_preview = []
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        texto = "No perímetro: clique em uma linha/curva para distribuir pontos por distância."
        self.set_status(texto)
        mensagem_status(canvas, texto)

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

    def _pontos_por_distancia(self, segmentos: list[tuple[QPointF, QPointF]], passo: float) -> list[QPointF]:
        if passo <= 1e-9:
            return []
        total = sum(self._dist(a, b) for a, b in segmentos)
        if total <= passo:
            return []
        alvos = []
        d = passo
        while d < total - 1e-9:
            alvos.append(d)
            d += passo
        if not alvos:
            return []

        pontos: list[QPointF] = []
        acumulado = 0.0
        cursor_alvo = 0
        for a, b in segmentos:
            seg_len = self._dist(a, b)
            if seg_len <= 1e-9:
                continue
            while cursor_alvo < len(alvos) and acumulado + seg_len >= alvos[cursor_alvo] - 1e-9:
                t = (alvos[cursor_alvo] - acumulado) / seg_len
                t = max(0.0, min(1.0, t))
                pontos.append(QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t)))
                cursor_alvo += 1
            acumulado += seg_len
        return pontos

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        info = selecionar_segmento_mais_proximo(canvas, pos)
        if info is None:
            self._idx_destaque = None
            self._pontos_preview = []
            texto = "Nenhum contorno encontrado para perímetro."
            self.set_status(texto)
            mensagem_status(canvas, texto)
            canvas.update()
            event.accept()
            return True

        self._idx_destaque = int(info["elemento_idx"])
        el = canvas.cena.elementos[self._idx_destaque]
        dialog = self._obter_dialog(canvas)
        passo_cena = dialog.passo_unidade() * max(1e-9, float(getattr(canvas, "_unidade_fator", 1.0)))
        self._pontos_preview = self._pontos_por_distancia(segmentos_de_elemento(el), passo_cena)
        self._aplicar_ultimo(canvas)
        event.accept()
        return True

    def _aplicar_ultimo(self, canvas):
        if self._idx_destaque is None or not (0 <= self._idx_destaque < len(canvas.cena.elementos)):
            return
        dialog = self._obter_dialog(canvas)
        el = canvas.cena.elementos[self._idx_destaque]
        passo_cena = dialog.passo_unidade() * max(1e-9, float(getattr(canvas, "_unidade_fator", 1.0)))
        self._pontos_preview = self._pontos_por_distancia(segmentos_de_elemento(el), passo_cena)

        if dialog.chk_dividir.isChecked() and el.get("tipo") == "polyline" and dialog.chk_colocar.isChecked():
            orig = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            novos = self._inserir_pontos_em_polyline(orig, self._pontos_preview)
            el["pontos"] = [(p.x(), p.y()) for p in novos]

        qtd = len(self._pontos_preview)
        per = canvas.formatar_valor_unidade(sum(self._dist(a, b) for a, b in segmentos_de_elemento(el)))
        unidade = getattr(canvas, "_unidade_sigla", "cm")
        txt = f"Perímetro P: {per} ({unidade}) | pontos: {qtd}"
        self.set_status(txt)
        mensagem_status(canvas, txt)
        canvas.update()

    def _inserir_pontos_em_polyline(self, pontos_orig: list[QPointF], inserir: list[QPointF]) -> list[QPointF]:
        if len(pontos_orig) < 2 or not inserir:
            return pontos_orig
        restantes = list(inserir)
        saida: list[QPointF] = [QPointF(pontos_orig[0])]
        for a, b in zip(pontos_orig, pontos_orig[1:]):
            seg_len = self._dist(a, b)
            if seg_len <= 1e-9:
                if self._dist(saida[-1], b) > 1e-9:
                    saida.append(QPointF(b))
                continue
            dentro = []
            novos_restantes = []
            for p in restantes:
                d1 = self._dist(a, p)
                d2 = self._dist(p, b)
                if abs((d1 + d2) - seg_len) <= 1e-3:
                    dentro.append((d1, p))
                else:
                    novos_restantes.append(p)
            restantes = novos_restantes
            for _, p in sorted(dentro, key=lambda item: item[0]):
                if self._dist(saida[-1], p) > 1e-6:
                    saida.append(QPointF(p))
            if self._dist(saida[-1], b) > 1e-9:
                saida.append(QPointF(b))
        return saida

    def on_paint_overlay(self, canvas, painter):
        idx = self._idx_destaque
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") == "polyline":
            pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            for a, b in zip(pts, pts[1:]):
                canvas._desenhar_segmento(painter, a, b, cor="#2f8bff", espessura=2.0)
        elif el.get("tipo") == "bezier_quadratica":
            canvas._desenhar_bezier_quadratica(
                painter,
                QPointF(*el.get("p0", (0.0, 0.0))),
                QPointF(*el.get("p1", (0.0, 0.0))),
                QPointF(*el.get("p2", (0.0, 0.0))),
                cor="#2f8bff",
                espessura=2.0,
                estilo="solid",
                amplitude=1.0,
                destacar_controles=False,
            )
        for p in self._pontos_preview:
            canvas._desenhar_marca_x(painter, p, cor="#ff2f2f", tamanho_px=5)
