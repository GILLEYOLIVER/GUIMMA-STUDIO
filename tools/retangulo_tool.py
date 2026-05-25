from __future__ import annotations

from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPen

from core.geometry_bridge import create_mold_payload
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "retangulo"
    nome = "Retangulo"
    usa_painel_auxiliar = False
    gerencia_coordenadas_operacao = True
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
                if hasattr(canvas, "iniciar_operacao_coordenadas"):
                    canvas.iniciar_operacao_coordenadas(pos)
            else:
                self._preview = pos
                if hasattr(canvas, "finalizar_operacao_coordenadas"):
                    canvas.finalizar_operacao_coordenadas(pos)
                self._finalizar(canvas)
            canvas.update()
            event.accept()
            return True
        if event.button() == Qt.RightButton:
            self._inicio = None
            self._preview = None
            if hasattr(canvas, "cancelar_operacao_coordenadas"):
                canvas.cancelar_operacao_coordenadas(limpar_preview=True)
            canvas.update()
            event.accept()
            return True
        return False

    def on_mouse_move(self, canvas, event) -> bool:
        if self._inicio is None:
            return False
        self._preview = canvas._ponto_com_snap(event.position())
        if hasattr(canvas, "atualizar_operacao_coordenadas"):
            canvas.atualizar_operacao_coordenadas(self._preview)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_preview(canvas, painter)

    def _desenhar_preview(self, canvas, painter):
        if self._inicio is None or self._preview is None:
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
        self._desenhar_cota_preview(canvas, painter, p1, p2)
        self._desenhar_cota_preview(canvas, painter, p2, p3)

    def _desenhar_cota_preview(self, canvas, painter, inicio: QPointF, fim: QPointF):
        p1 = canvas._cena_para_tela(inicio)
        p2 = canvas._cena_para_tela(fim)
        dx = fim.x() - inicio.x()
        dy = fim.y() - inicio.y()
        comprimento = sqrt((dx * dx) + (dy * dy))
        if comprimento <= 1e-6:
            return
        horizontal = abs(dx) >= abs(dy)
        angulo_txt = "0.0°" if horizontal else "90.0°"
        texto = f"{canvas.formatar_distancia(comprimento)}  |  {angulo_txt}"
        cx = (p1.x() + p2.x()) / 2.0
        cy = (p1.y() + p2.y()) / 2.0

        pen = QPen(QColor("#67d9ff"), 1.0, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(p1, 5, 5)
        painter.drawEllipse(p2, 5, 5)

        fm = QFontMetrics(painter.font())
        tw = fm.horizontalAdvance(texto) + 12
        th = fm.height() + 4
        rx = int(cx - (tw / 2))
        ry = int(cy - th - 4) if horizontal else int(cy - (th / 2))
        if not horizontal:
            rx = int(cx + 8)
        painter.fillRect(rx, ry, tw, th, QColor(20, 20, 20, 210))
        painter.setPen(QPen(QColor("#ffd35a"), 1))
        painter.drawText(rx + 6, ry + th - 4, texto)

    def _pontos_auxiliares_segmento(self, inicio: QPointF, fim: QPointF) -> list[QPointF]:
        return [QPointF((inicio.x() + fim.x()) / 2.0, (inicio.y() + fim.y()) / 2.0)]

    def _pontos_auxiliares_entre_cantos(self, cantos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(cantos) < 2:
            return []
        auxiliares: list[tuple[float, float]] = []
        for i, atual in enumerate(cantos):
            proximo = cantos[(i + 1) % len(cantos)]
            auxiliares.append(((float(atual[0]) + float(proximo[0])) / 2.0, (float(atual[1]) + float(proximo[1])) / 2.0))
        return auxiliares

    def _cantos_horarios_retangulo(self, p1: QPointF, p3: QPointF) -> list[tuple[float, float]]:
        min_x = min(float(p1.x()), float(p3.x()))
        max_x = max(float(p1.x()), float(p3.x()))
        min_y = min(float(p1.y()), float(p3.y()))
        max_y = max(float(p1.y()), float(p3.y()))
        return [
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ]

    def _finalizar(self, canvas):
        if self._inicio is None or self._preview is None:
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
            pontos_fechados = [*cantos, cantos[0]]
            try:
                payload = create_mold_payload(
                    {"tipo": "polyline", "pontos": [(pt.x(), pt.y()) for pt in pontos_fechados]}
                )
            except ValueError:
                self._inicio = None
                self._preview = None
                return
            xs = [pt.x() for pt in cantos]
            ys = [pt.y() for pt in cantos]
            min_x, max_x = min(xs), max(xs)
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            largura = max_x - min_x
            altura = max(ys) - min(ys)
            margem = largura * 0.20
            y_fio = min(max(ys) - max(0.15, altura * 0.06), cy + max(0.25, altura * 0.08))
            controle_cantos = self._cantos_horarios_retangulo(p1, p3)
            controle_auxiliares = self._pontos_auxiliares_entre_cantos(controle_cantos)
            pontos = [*controle_cantos, controle_cantos[0]]
            canvas.cena.elementos.append(
                {
                    "tipo": "polyline",
                    "pontos": pontos,
                    "cor": canvas._linha_cor,
                    "espessura": canvas._linha_espessura,
                    "estilo": canvas._linha_estilo,
                    "amplitude": canvas._linha_amplitude,
                    "fase_inicio": 0.0,
                    "molde": True,
                    "molde_id": str(uuid4()),
                    "nome_molde": f"K{len(canvas.cena.elementos) + 1}",
                    "shape_id": payload["shape_id"],
                    "node_ids": payload["node_ids"],
                    "segment_ids": payload["segment_ids"],
                    "fio_angulo": 0.0,
                    "fio_origem": (min_x + margem, y_fio),
                    "fio_fim": (max_x - margem, y_fio),
                    "ponto_texto": (cx, cy),
                    "texto_nome_altura_cm": 3.0,
                    "numero_altura_cm": 0.7,
                    "mostrar_nome": True,
                    "mostrar_fio": True,
                    "mostrar_numeros": True,
                    "mostrar_controles": True,
                    "molde_pronto": True,
                    "permitir_alteracoes_encaixe": True,
                    "controle_cantos": controle_cantos,
                    "controle_auxiliares": controle_auxiliares,
                    "pontos_controle_principais": [{"x": float(x), "y": float(y)} for x, y in controle_cantos],
                    "pontos_auxiliares": [{"x": float(x), "y": float(y)} for x, y in controle_auxiliares],
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
