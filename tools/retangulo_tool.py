from __future__ import annotations

from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "retangulo"
    nome = "Retangulo"
    descricao_painel = "Clique em dois cantos para criar retângulo. RMB cancela a prévia."

    def __init__(self):
        super().__init__()
        self._inicio: QPointF | None = None
        self._preview: QPointF | None = None
        self._criar_molde = True

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._inicio = None
        self._preview = None
        self._criar_molde = bool(getattr(canvas, "_retangulo_criar_molde", True))
        self.set_status("Clique no primeiro canto do retângulo.")

    def set_criar_molde(self, criar: bool):
        self._criar_molde = bool(criar)

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.LeftButton:
            pos = canvas._ponto_com_snap(event.position())
            if self._inicio is None:
                self._inicio = pos
                self._preview = pos
            else:
                self._preview = pos
                self._finalizar(canvas)
            canvas.update()
            event.accept()
            return True
        if event.button() == Qt.RightButton:
            self._inicio = None
            self._preview = None
            canvas.update()
            event.accept()
            return True
        return False

    def on_mouse_move(self, canvas, event) -> bool:
        if self._inicio is None:
            return False
        self._preview = canvas._ponto_com_snap(event.position())
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_preview(canvas, painter)
        self._desenhar_info_moldes(canvas, painter)

    def _desenhar_preview(self, canvas, painter):
        if not self._inicio or not self._preview:
            return
        p1 = self._inicio
        p3 = self._preview
        p2 = QPointF(p3.x(), p1.y())
        p4 = QPointF(p1.x(), p3.y())
        canvas._desenhar_polilinha(
            painter,
            [p1, p2, p3, p4, p1],
            cor=canvas._linha_cor,
            espessura=canvas._linha_espessura,
            estilo=canvas._linha_estilo,
            amplitude=canvas._linha_amplitude,
        )

    def _pontos_auxiliares_segmento(self, inicio: QPointF, fim: QPointF) -> list[QPointF]:
        return [
            QPointF(inicio.x() + ((fim.x() - inicio.x()) * t), inicio.y() + ((fim.y() - inicio.y()) * t))
            for t in (0.33, 0.66)
        ]

    def _finalizar(self, canvas):
        if not self._inicio or not self._preview:
            return
        p1 = self._inicio
        p3 = self._preview
        if abs(p1.x() - p3.x()) < 0.0001 or abs(p1.y() - p3.y()) < 0.0001:
            self._inicio = None
            self._preview = None
            return
        p2 = QPointF(p3.x(), p1.y())
        p4 = QPointF(p1.x(), p3.y())
        cantos = [p1, p2, p3, p4]
        if self._criar_molde:
            pontos_fechados: list[QPointF] = []
            for idx, inicio in enumerate(cantos):
                fim = cantos[(idx + 1) % len(cantos)]
                pontos_fechados.append(inicio)
                pontos_fechados.extend(self._pontos_auxiliares_segmento(inicio, fim))
            pontos_fechados.append(cantos[0])
            canvas.cena.elementos.append(
                {
                    "tipo": "polyline",
                    "pontos": [(pt.x(), pt.y()) for pt in pontos_fechados],
                    "cor": canvas._linha_cor,
                    "espessura": canvas._linha_espessura,
                    "estilo": canvas._linha_estilo,
                    "amplitude": canvas._linha_amplitude,
                    "fase_inicio": 0.0,
                    "molde": True,
                    "molde_id": str(uuid4()),
                    "fio_angulo": 0.0,
                    "controle_cantos": [(pt.x(), pt.y()) for pt in cantos],
                }
            )
            canvas._selecionados = {len(canvas.cena.elementos) - 1}
        else:
            pontos = [p1, p2, p3, p4, p1]
            fase = 0.0
            for inicio, fim in zip(pontos, pontos[1:]):
                comprimento = sqrt((fim.x() - inicio.x()) ** 2 + (fim.y() - inicio.y()) ** 2)
                canvas.cena.elementos.append(
                    {
                        "tipo": "polyline",
                        "pontos": [(inicio.x(), inicio.y()), (fim.x(), fim.y())],
                        "cor": canvas._linha_cor,
                        "espessura": canvas._linha_espessura,
                        "estilo": canvas._linha_estilo,
                        "amplitude": canvas._linha_amplitude,
                        "fase_inicio": fase,
                    }
                )
                fase += comprimento
        canvas._registrar_historico()
        self._inicio = None
        self._preview = None

    def _desenhar_info_moldes(self, canvas, painter):
        for el in canvas.cena.elementos:
            if not el.get("molde"):
                continue
            controles = [QPointF(float(x), float(y)) for x, y in el.get("controle_cantos", [])]
            if not controles:
                continue
            painter.setPen(QPen(QColor("#ffffff"), 1))
            for i, pt in enumerate(controles, start=1):
                pt_tela = canvas._cena_para_tela(pt)
                painter.drawText(int(pt_tela.x() + 4), int(pt_tela.y() - 6), str(i))
                painter.drawRect(int(pt_tela.x() - 3), int(pt_tela.y() - 3), 6, 6)
            xs = [p.x() for p in controles]
            ys = [p.y() for p in controles]
            y_meio = (min(ys) + max(ys)) / 2.0
            x1 = min(xs) + ((max(xs) - min(xs)) * 0.25)
            x2 = min(xs) + ((max(xs) - min(xs)) * 0.75)
            origem_fio = QPointF(x1, y_meio)
            fim_fio = QPointF(x2, y_meio)
            canvas._desenhar_segmento(painter, origem_fio, fim_fio, cor="#ffffff", espessura=1.0)
            painter.drawText(int(canvas._cena_para_tela(fim_fio).x() + 6), int(canvas._cena_para_tela(fim_fio).y() + 4), "0°")
