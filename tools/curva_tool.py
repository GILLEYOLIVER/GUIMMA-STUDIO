from __future__ import annotations

from math import cos, pi, sin, sqrt
from typing import List, Optional

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from core.geometry.engine import (
    polyline_perimeter,
    quadratic_bezier_control_for_point,
    quadratic_bezier_parameter_for_point,
    sample_quadratic_bezier_through_point,
)
from core.formatacao import formatar_numero
from tools.medicao_utils import mensagem_status
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import restaurar_posicao, salvar_posicao


class _PainelCurva(QFrame):
    OBJETO = "PainelCurvaRetasECurvas"

    def __init__(self, ferramenta: "Ferramenta", canvas):
        super().__init__(canvas)
        self.ferramenta = ferramenta
        self.setObjectName(self.OBJETO)
        self.setWindowFlags(Qt.Widget)
        self.setFixedWidth(136)
        self._drag_offset: QPoint | None = None
        self._chave_posicao = "painel:curva"
        self.setStyleSheet(
            """
            QFrame#PainelCurvaRetasECurvas {
                background:#f8fafc;
                border:1px solid #cfd8e3;
                border-radius:2px;
            }
            QLabel {
                color:#1f2937;
                font-size:11px;
                padding:2px 4px;
            }
            QPushButton {
                background:#f3f4f6;
                border:1px solid #d1d5db;
                color:#111827;
                min-height:20px;
                font-size:11px;
                padding:1px 6px;
            }
            QPushButton:hover { background:#e0f2fe; border-color:#7dd3fc; }
            QPushButton:disabled { color:#9ca3af; background:#f8fafc; }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 4)
        layout.setSpacing(2)
        self.titulo = QLabel("Retas e curvas")
        layout.addWidget(self.titulo)
        self.btn_desfazer = QPushButton("Desfaz ponto")
        self.btn_desfazer.clicked.connect(self._desfazer)
        layout.addWidget(self.btn_desfazer)

    def atualizar(self, quantidade: int):
        self.btn_desfazer.setEnabled(quantidade > 0)

    def _desfazer(self):
        self.ferramenta.desfazer_ultimo_ponto()

    def _limitar(self, pos: QPoint) -> QPoint:
        parent = self.parentWidget()
        if parent is None:
            return pos
        margem = 8
        area = QRect(margem, margem, max(1, parent.width() - margem * 2), max(1, parent.height() - margem * 2))
        x = max(area.left(), min(pos.x(), area.right() - self.width()))
        y = max(area.top(), min(pos.y(), area.bottom() - self.height()))
        return QPoint(int(x), int(y))

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() <= 22:
            self._drag_offset = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(self._limitar(self.pos() + event.position().toPoint() - self._drag_offset))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            salvar_posicao(self, self._chave_posicao)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):  # noqa: N802
        salvar_posicao(self, self._chave_posicao)
        super().hideEvent(event)


class Ferramenta(FerramentaBase):
    """
    Ferramenta de curva profissional para CAD de modelagem de roupas.

    - Spline cúbica natural (suave por pontos de controle)
    - Fechamento explícito com indicador visual
    - Snap a nós, bordas e pontos médios
    - Visual estilo CAD: círculos para nós, losango para nó ativo
    - Amostragem adaptativa ao zoom
    - Finalização por Enter, botão direito ou fechamento automático
    """

    id_ferramenta = "curva"
    nome = "Curva"
    usa_painel_auxiliar = False
    descricao_painel = (
        "Curva suave por pontos de controle (spline cúbica). "
        "Clique esquerdo adiciona nós. Botão direito ou Enter finaliza. "
        "ESC cancela. Para fechar, clique no primeiro nó (indicador visual)."
    )

    COR_PREVIEW = "#ff00ff"
    COR_NO = "#ff4fd8"
    COR_NO_ATIVO = "#ffaa00"
    COR_SNAP = "#7df9ff"
    COR_FECHAR = "#00ff88"

    def __init__(self):
        super().__init__()
        self._canvas = None
        self._painel_curva: _PainelCurva | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._canvas = canvas
        self._garantir_estado(canvas)
        self._resetar(canvas, manter_elementos=True)
        self._mostrar_painel(canvas)
        self._set_status(canvas)
        canvas.update()

    def on_deactivate(self, canvas):
        self._ocultar_painel()
        self._canvas = None
        self._resetar(canvas, manter_elementos=True)
        try:
            canvas.update()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # ESTADO
    # -------------------------------------------------------------------------
    def _garantir_estado(self, canvas):
        if not hasattr(canvas, "_curva_np_nos"):
            canvas._curva_np_nos = []
        if not hasattr(canvas, "_curva_np_cursor"):
            canvas._curva_np_cursor = None
        if not hasattr(canvas, "_curva_np_preview"):
            canvas._curva_np_preview = []
        if not hasattr(canvas, "_curva_snap_preview"):
            canvas._curva_snap_preview = None
        if not hasattr(canvas, "_curva_estado"):
            canvas._curva_estado = "parada"
        if not hasattr(canvas, "_curva_fechando"):
            canvas._curva_fechando = False
        if not hasattr(canvas, "_curva_np_curva_confirmada"):
            canvas._curva_np_curva_confirmada = []
        if not hasattr(canvas, "_curva_np_perimetro_confirmado"):
            canvas._curva_np_perimetro_confirmado = 0.0
        if not hasattr(canvas, "_curva_ajustar_circulo"):
            canvas._curva_ajustar_circulo = False

    def _resetar(self, canvas, manter_elementos=True):
        canvas._curva_estado = "parada"
        canvas._curva_np_nos = []
        canvas._curva_np_cursor = None
        canvas._curva_np_preview = []
        canvas._curva_snap_preview = None
        canvas._curva_fechando = False
        canvas._curva_ajustar_circulo = False
        canvas._curva_np_curva_confirmada = []
        canvas._curva_np_perimetro_confirmado = 0.0
        self._atualizar_painel(canvas)

        if not manter_elementos and hasattr(canvas, "_resetar_estado_curva"):
            try:
                canvas._resetar_estado_curva()
            except Exception:
                pass

    def _set_status(self, canvas):
        if not canvas._curva_np_nos:
            self._status(canvas, "Curva: indique pontos.")
        else:
            msg = f"Curva: {len(canvas._curva_np_nos)} ponto(s). "
            if len(canvas._curva_np_nos) >= 3:
                msg += "Clique no primeiro nó para fechar. "
            msg += "Botão direito ou Enter finaliza. ESC cancela."
            self._status(canvas, msg)

    def _status(self, canvas, texto: str):
        self.set_status(texto)
        mensagem_status(canvas, texto)

    def _mostrar_painel(self, canvas):
        painel = None
        try:
            existentes = canvas.findChildren(QFrame, _PainelCurva.OBJETO)
            painel = existentes[0] if existentes else None
        except Exception:
            painel = None
        if painel is None:
            painel = _PainelCurva(self, canvas)
        else:
            painel.ferramenta = self
        self._painel_curva = painel
        try:
            if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
                destino = canvas.calcular_posicao_painel_auxiliar(painel.width(), painel.height(), abaixo_coordenadas=True)
            else:
                margem = 14
                destino = QPoint(max(margem, canvas.width() - painel.width() - margem), max(margem, int(canvas.height() * 0.28)))
            if not restaurar_posicao(painel, painel._chave_posicao, fallback=painel._limitar(destino)):
                salvar_posicao(painel, painel._chave_posicao)
        except Exception:
            pass
        self._atualizar_painel(canvas)
        painel.show()
        painel.raise_()

    def _ocultar_painel(self):
        if self._painel_curva is not None:
            self._painel_curva.hide()

    def _atualizar_painel(self, canvas):
        painel = self._painel_curva
        if painel is None:
            return
        try:
            painel.atualizar(len(getattr(canvas, "_curva_np_nos", []) or []))
        except Exception:
            pass

    def desfazer_ultimo_ponto(self):
        canvas = self._canvas
        if canvas is None:
            return
        self._garantir_estado(canvas)
        if not canvas._curva_np_nos:
            self._status(canvas, "Curva: nenhum ponto para desfazer.")
            self._atualizar_painel(canvas)
            return
        canvas._curva_np_nos.pop()
        canvas._curva_fechando = False
        cursor = getattr(canvas, "_curva_np_cursor", None)
        self._atualizar_curva_confirmada(canvas)
        canvas._curva_np_preview = self._gerar_preview_profissional(canvas, cursor=cursor, fechado=False)
        self._atualizar_status_metricas(canvas, canvas._curva_np_preview or canvas._curva_np_curva_confirmada)
        self._atualizar_painel(canvas)
        canvas.update()

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    def _snap(self, canvas, pos: QPointF) -> QPointF:
        if hasattr(canvas, "_ponto_com_snap"):
            try:
                ponto = canvas._ponto_com_snap(pos)
                canvas._curva_snap_preview = getattr(canvas, "_snap_resultado", None)
                return ponto
            except Exception:
                pass
        canvas._curva_snap_preview = None
        return QPointF(pos)

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return sqrt(dx * dx + dy * dy)

    @staticmethod
    def _dist2(a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return dx * dx + dy * dy

    def _remover_repetidos(self, pontos: List[QPointF], tolerancia: float = 0.01) -> List[QPointF]:
        if not pontos:
            return []
        resultado = [QPointF(pontos[0])]
        tol2 = tolerancia * tolerancia
        for p in pontos[1:]:
            if self._dist2(resultado[-1], p) > tol2:
                resultado.append(QPointF(p))
        return resultado

    def _tolerancia_snap_cena(self, canvas) -> float:
        try:
            zoom = max(float(getattr(canvas, "zoom", 1.0)), 0.001)
            if hasattr(canvas, "_tolerancia_snap_px"):
                return float(canvas._tolerancia_snap_px()) / zoom
            return 10.0 / zoom
        except Exception:
            return 10.0

    def _pode_fechar(self, canvas, ponto: QPointF | None) -> bool:
        """Verifica se o ponto está próximo ao primeiro nó e há nós suficientes."""
        if ponto is None:
            return False
        nos = getattr(canvas, "_curva_np_nos", [])
        if len(nos) < 3:
            return False
        primeiro = QPointF(nos[0])
        return self._dist(primeiro, ponto) <= self._tolerancia_snap_cena(canvas)

    def _obter_ponto_fechamento(self, canvas, ponto: QPointF) -> QPointF | None:
        """Retorna o primeiro nó se estiver próximo, senão None."""
        if self._pode_fechar(canvas, ponto):
            return QPointF(canvas._curva_np_nos[0])
        return None

    # -------------------------------------------------------------------------
    # SPLINE CÚBICA NATURAL
    # -------------------------------------------------------------------------
    def _parametros_por_corda(self, pontos: List[QPointF]) -> List[float]:
        if not pontos:
            return []
        t = [0.0]
        for i in range(1, len(pontos)):
            d = self._dist(pontos[i - 1], pontos[i])
            if d < 1e-6:
                d = 1e-6
            t.append(t[-1] + d)
        return t

    def _resolver_segundas_derivadas(self, valores: List[float], t: List[float]) -> List[float]:
        n = len(valores)
        if n <= 2:
            return [0.0] * n

        m = n - 2
        a = [0.0] * m
        b = [0.0] * m
        c = [0.0] * m
        d = [0.0] * m

        for j in range(m):
            i = j + 1
            h_prev = t[i] - t[i - 1]
            h_next = t[i + 1] - t[i]

            if h_prev < 1e-9:
                h_prev = 1e-9
            if h_next < 1e-9:
                h_next = 1e-9

            a[j] = h_prev
            b[j] = 2.0 * (h_prev + h_next)
            c[j] = h_next
            d[j] = 6.0 * (
                    ((valores[i + 1] - valores[i]) / h_next)
                    - ((valores[i] - valores[i - 1]) / h_prev)
            )

        # Thomas algorithm
        for i in range(1, m):
            w = a[i] / b[i - 1]
            b[i] -= w * c[i - 1]
            d[i] -= w * d[i - 1]

        internos = [0.0] * m
        internos[-1] = d[-1] / b[-1]

        for i in range(m - 2, -1, -1):
            internos[i] = (d[i] - c[i] * internos[i + 1]) / b[i]

        return [0.0] + internos + [0.0]

    def _avaliar_spline(
            self,
            ti: float,
            tj: float,
            yi: float,
            yj: float,
            mi: float,
            mj: float,
            u: float,
    ) -> float:
        h = tj - ti
        if h < 1e-9:
            return yi

        a = (tj - u) / h
        b = (u - ti) / h

        return (
                a * yi
                + b * yj
                + (((a ** 3) - a) * mi + ((b ** 3) - b) * mj) * (h * h) / 6.0
        )

    def _amostras_por_trecho(self, canvas, a: QPointF, b: QPointF) -> int:
        """Amostragem leve para manter a criação e o zoom fluidos."""
        d = self._dist(a, b)
        return max(8, min(22, int(d * 0.10) + 8))

    def _catmull_rom(self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        t2 = t * t
        t3 = t2 * t
        x = 0.5 * (
            (2.0 * p1.x())
            + (-p0.x() + p2.x()) * t
            + (2.0 * p0.x() - 5.0 * p1.x() + 4.0 * p2.x() - p3.x()) * t2
            + (-p0.x() + 3.0 * p1.x() - 3.0 * p2.x() + p3.x()) * t3
        )
        y = 0.5 * (
            (2.0 * p1.y())
            + (-p0.y() + p2.y()) * t
            + (2.0 * p0.y() - 5.0 * p1.y() + 4.0 * p2.y() - p3.y()) * t2
            + (-p0.y() + 3.0 * p1.y() - 3.0 * p2.y() + p3.y()) * t3
        )
        return QPointF(x, y)

    def _catmull_rom_centripeta(self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        def tj(ti: float, a: QPointF, b: QPointF) -> float:
            return ti + max(self._dist(a, b), 1e-6) ** 0.5

        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        t = t1 + max(0.0, min(1.0, t)) * (t2 - t1)

        def interp(a: QPointF, b: QPointF, ta: float, tb: float) -> QPointF:
            den = max(tb - ta, 1e-9)
            return QPointF(
                ((tb - t) / den) * a.x() + ((t - ta) / den) * b.x(),
                ((tb - t) / den) * a.y() + ((t - ta) / den) * b.y(),
            )

        a1 = interp(p0, p1, t0, t1)
        a2 = interp(p1, p2, t1, t2)
        a3 = interp(p2, p3, t2, t3)
        b1 = interp(a1, a2, t0, t2)
        b2 = interp(a2, a3, t1, t3)
        return interp(b1, b2, t1, t2)

    def _controle_quadratico_por_ponto_medio(self, p0: QPointF, pmedio: QPointF, p2: QPointF) -> QPointF:
        x, y = quadratic_bezier_control_for_point(
            (float(p0.x()), float(p0.y())),
            (float(pmedio.x()), float(pmedio.y())),
            (float(p2.x()), float(p2.y())),
        )
        return QPointF(x, y)

    def _parametro_parabola_3p(self, p0: QPointF, pmedio: QPointF, p2: QPointF) -> float:
        return quadratic_bezier_parameter_for_point(
            (float(p0.x()), float(p0.y())),
            (float(pmedio.x()), float(pmedio.y())),
            (float(p2.x()), float(p2.y())),
        )

    def _ponto_bezier_quadratico(self, p0: QPointF, p1: QPointF, p2: QPointF, t: float) -> QPointF:
        u = 1.0 - t
        return QPointF(
            (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x()),
            (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y()),
        )

    def _gerar_parabola_3p(self, canvas, pontos: List[QPointF]) -> List[QPointF]:
        pts = self._remover_repetidos([QPointF(p) for p in pontos], tolerancia=0.001)
        if len(pts) != 3:
            return self._gerar_spline(canvas, pts, fechado=False)
        p0, pmedio, p2 = pts
        segmentos = max(
            96,
            min(192, (self._amostras_por_trecho(canvas, p0, pmedio) + self._amostras_por_trecho(canvas, pmedio, p2)) * 3),
        )
        if segmentos % 2:
            segmentos += 1
        curva = [
            QPointF(x, y)
            for x, y in sample_quadratic_bezier_through_point(
                (float(p0.x()), float(p0.y())),
                (float(pmedio.x()), float(pmedio.y())),
                (float(p2.x()), float(p2.y())),
                segmentos,
            )
        ]
        return self._remover_repetidos(curva, tolerancia=0.001)

    def _gerar_spline(self, canvas, pontos: List[QPointF], fechado: bool = False) -> List[QPointF]:
        """
        Gera o traçado editável a partir dos pontos de controle.

        Catmull-Rom passa pelos nós clicados, é local (mover um ponto afeta
        principalmente seus vizinhos) e é bem mais leve que recalcular spline
        natural global a cada movimento do mouse.
        """
        pts = self._remover_repetidos([QPointF(p) for p in pontos], tolerancia=0.001)

        if len(pts) <= 1:
            return []
        if len(pts) == 2:
            return [QPointF(pts[0]), QPointF(pts[1])]
        if fechado:
            return self._gerar_spline_fechada_suave(canvas, pts)

        resultado: List[QPointF] = []
        total = len(pts)
        limite = total - 1
        for i in range(limite):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2] if i + 2 < total else p2
            if i == 0:
                resultado.append(QPointF(p1))
            amostras = self._amostras_por_trecho(canvas, p1, p2)
            for s in range(1, amostras + 1):
                resultado.append(self._catmull_rom_centripeta(p0, p1, p2, p3, s / float(amostras)))

        return self._remover_repetidos(resultado, tolerancia=0.001)

    def _gerar_spline_fechada_suave(self, canvas, pts: List[QPointF]) -> List[QPointF]:
        pts = self._remover_repetidos([QPointF(p) for p in pts], tolerancia=0.001)
        if len(pts) >= 2 and self._dist2(pts[0], pts[-1]) <= 0.001 * 0.001:
            pts.pop()
        if len(pts) < 3:
            return self._gerar_spline(canvas, pts, fechado=False)

        resultado: List[QPointF] = []
        total = len(pts)
        for i in range(total):
            p0 = pts[(i - 1) % total]
            p1 = pts[i]
            p2 = pts[(i + 1) % total]
            p3 = pts[(i + 2) % total]
            if i == 0:
                resultado.append(QPointF(p1))
            amostras = self._amostras_por_trecho(canvas, p1, p2)
            for s in range(1, amostras + 1):
                resultado.append(self._catmull_rom_centripeta(p0, p1, p2, p3, s / float(amostras)))

        if resultado:
            resultado[-1] = QPointF(resultado[0])
        return self._remover_repetidos(resultado, tolerancia=0.001)

    # -------------------------------------------------------------------------
    # COMPORTAMENTO CAD/MODELAGEM
    # -------------------------------------------------------------------------
    def _modo_curva_atual(self, canvas) -> str:
        modo = str(getattr(canvas, "_modo_curva", "np") or "np").strip().lower()
        if modo in {"espelhada", "espelhadas", "curvas_espelhadas", "mirror", "mirrored"}:
            return "espelhada"
        if modo in {"2", "2p", "2 pontos", "curva por 2 pontos"}:
            return "2p"
        if modo in {"3", "3p", "3 pontos", "curva por 3 pontos"}:
            return "3p"
        if modo in {"suave", "curva suave", "spline"}:
            return "suave"
        return "np"

    def _espelhar_pontos(self, pontos: List[QPointF], eixo_x: float) -> List[QPointF]:
        return [QPointF((2.0 * eixo_x) - p.x(), p.y()) for p in pontos]

    def _resolver_3x3(self, matriz: list[list[float]], vetor: list[float]) -> tuple[float, float, float] | None:
        m = [list(linha) + [float(vetor[i])] for i, linha in enumerate(matriz)]
        for col in range(3):
            pivo = max(range(col, 3), key=lambda i: abs(m[i][col]))
            if abs(m[pivo][col]) <= 1e-9:
                return None
            if pivo != col:
                m[col], m[pivo] = m[pivo], m[col]
            div = m[col][col]
            for j in range(col, 4):
                m[col][j] /= div
            for i in range(3):
                if i == col:
                    continue
                fator = m[i][col]
                for j in range(col, 4):
                    m[i][j] -= fator * m[col][j]
        return m[0][3], m[1][3], m[2][3]

    def _ajustar_circulo(self, pontos: List[QPointF]) -> tuple[QPointF, float, float] | None:
        pts = self._remover_repetidos([QPointF(p) for p in pontos], tolerancia=0.001)
        if len(pts) >= 2 and self._dist2(pts[0], pts[-1]) <= 0.0001:
            pts.pop()
        if len(pts) < 4:
            return None

        sx = sy = s1 = sx2 = sy2 = sxy = sxz = syz = sz = 0.0
        for p in pts:
            x = float(p.x())
            y = float(p.y())
            z = x * x + y * y
            sx += x
            sy += y
            s1 += 1.0
            sx2 += x * x
            sy2 += y * y
            sxy += x * y
            sxz += x * z
            syz += y * z
            sz += z

        solucao = self._resolver_3x3(
            [[sx2, sxy, sx], [sxy, sy2, sy], [sx, sy, s1]],
            [-sxz, -syz, -sz],
        )
        if solucao is None:
            return None

        d, e, f = solucao
        centro = QPointF(-d / 2.0, -e / 2.0)
        raio2 = (centro.x() * centro.x()) + (centro.y() * centro.y()) - f
        if raio2 <= 1e-9:
            return None
        raio = sqrt(raio2)
        desvios = [abs(self._dist(centro, p) - raio) for p in pts]
        desvio_relativo = max(desvios) / max(raio, 1e-9)
        return centro, raio, desvio_relativo

    def _gerar_circulo_ajustado(self, canvas, pontos: List[QPointF]) -> List[QPointF]:
        ajuste = self._ajustar_circulo(pontos)
        if ajuste is None:
            return []
        centro, raio, desvio = ajuste
        if desvio > 0.18:
            return []
        segmentos = 160
        curva = [
            QPointF(
                centro.x() + cos((2.0 * pi * i) / segmentos) * raio,
                centro.y() + sin((2.0 * pi * i) / segmentos) * raio,
            )
            for i in range(segmentos + 1)
        ]
        curva[-1] = QPointF(curva[0])
        return curva

    def _trecho_temporario_por_nos(self, canvas, nos: List[QPointF], cursor: QPointF) -> List[QPointF]:
        if not nos:
            return [QPointF(cursor)]

        ultimo = QPointF(nos[-1])
        if self._dist2(ultimo, cursor) <= 1e-8:
            return [ultimo]

        if len(nos) == 1:
            return [ultimo, QPointF(cursor)]

        anterior = QPointF(nos[-2])

        vx = ultimo.x() - anterior.x()
        vy = ultimo.y() - anterior.y()
        controle1 = QPointF(ultimo.x() + vx * 0.35, ultimo.y() + vy * 0.35)
        controle2 = QPointF(cursor.x() - (cursor.x() - ultimo.x()) * 0.22,
                            cursor.y() - (cursor.y() - ultimo.y()) * 0.22)

        dist = self._dist(ultimo, cursor)
        amostras = max(8, min(26, int(dist * 0.14) + 8))
        pontos: List[QPointF] = []
        for i in range(amostras + 1):
            t = i / float(amostras)
            u = 1.0 - t
            x = (
                (u ** 3) * ultimo.x()
                + 3.0 * (u ** 2) * t * controle1.x()
                + 3.0 * u * (t ** 2) * controle2.x()
                + (t ** 3) * cursor.x()
            )
            y = (
                (u ** 3) * ultimo.y()
                + 3.0 * (u ** 2) * t * controle1.y()
                + 3.0 * u * (t ** 2) * controle2.y()
                + (t ** 3) * cursor.y()
            )
            pontos.append(QPointF(x, y))
        pontos[0] = QPointF(ultimo)
        pontos[-1] = QPointF(cursor)
        return self._remover_repetidos(pontos, tolerancia=0.001)

    def _gerar_curva_incremental(self, canvas, pontos: List[QPointF]) -> List[QPointF]:
        nos = self._remover_repetidos([QPointF(p) for p in pontos], tolerancia=0.001)
        if len(nos) <= 1:
            return list(nos)
        if len(nos) == 2:
            return [QPointF(nos[0]), QPointF(nos[1])]

        curva = self._gerar_parabola_3p(canvas, nos[:3])
        for indice in range(3, len(nos)):
            trecho = self._trecho_temporario_por_nos(canvas, nos[:indice], nos[indice])
            if trecho:
                curva = self._remover_repetidos([*curva, *trecho[1:]], tolerancia=0.001)
        return curva

    def _curva_dos_nos_confirmados(self, canvas, fechado: bool = False) -> List[QPointF]:
        nos = self._remover_repetidos([QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])], tolerancia=0.001)
        if len(nos) <= 1:
            return nos
        if len(nos) == 2:
            return [QPointF(nos[0]), QPointF(nos[1])]
        circulo = self._gerar_circulo_ajustado(canvas, nos)
        if fechado and circulo:
            return circulo
        return self._gerar_spline(canvas, nos, fechado)

    def _atualizar_curva_confirmada(self, canvas) -> List[QPointF]:
        nos = self._remover_repetidos([QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])], tolerancia=0.001)
        if len(nos) <= 1:
            curva = list(nos)
        elif len(nos) == 2:
            curva = [QPointF(nos[0]), QPointF(nos[1])]
        elif self._modo_curva_atual(canvas) == "3p" and len(nos) == 3:
            curva = self._gerar_parabola_3p(canvas, nos)
        elif len(nos) >= 3:
            curva = self._gerar_spline(canvas, nos, fechado=False)
        else:
            curva = self._gerar_spline(canvas, nos, fechado=False)
        canvas._curva_np_curva_confirmada = curva
        canvas._curva_np_perimetro_confirmado = self._comprimento_polyline(curva)
        return curva

    def _comprimento_polyline(self, pontos: List[QPointF]) -> float:
        if len(pontos) < 2:
            return 0.0
        return float(polyline_perimeter([(float(p.x()), float(p.y())) for p in pontos]))

    def _formatar_valor(self, canvas, valor: float) -> str:
        if hasattr(canvas, "formatar_valor_unidade"):
            try:
                return canvas.formatar_valor_unidade(valor)
            except Exception:
                pass
        return formatar_numero(valor, 2)

    def _atualizar_status_metricas(self, canvas, pontos: List[QPointF] | None = None):
        pontos = pontos if pontos is not None else getattr(canvas, "_curva_np_preview", [])
        perimetro = self._comprimento_polyline(pontos or [])
        unidade = getattr(canvas, "_unidade_sigla", "cm")
        txt = f"Curva: pontos {len(getattr(canvas, '_curva_np_nos', []) or [])} | perímetro {self._formatar_valor(canvas, perimetro)} ({unidade})"
        if getattr(canvas, "_curva_fechando", False):
            txt += " | fechar curva"
        self._status(canvas, txt)

    def _trecho_temporario_cursor(self, canvas, cursor: QPointF) -> List[QPointF]:
        """Desenha somente o trecho temporário até o cursor.

        A regra principal observada no vídeo: o que já foi clicado não fica
        deformando enquanto o mouse se move. Só o trecho novo acompanha o cursor.
        """
        nos = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]
        return self._trecho_temporario_por_nos(canvas, nos, cursor)

    def _gerar_preview_profissional(self, canvas, cursor: QPointF | None = None, fechado: bool = False) -> List[QPointF]:
        """Mostra exatamente o traçado que será gravado se o usuário clicar."""
        nos = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]
        if not nos:
            return []

        base = list(nos)
        if cursor is not None and not fechado and self._dist2(QPointF(base[-1]), cursor) > 0.0001:
            base.append(QPointF(cursor))
        if len(base) <= 2:
            return [QPointF(p) for p in base]
        if fechado and getattr(canvas, "_curva_ajustar_circulo", False):
            circulo = self._gerar_circulo_ajustado(canvas, base)
            if circulo:
                return circulo
        if self._modo_curva_atual(canvas) == "3p" and len(base) == 3 and not fechado:
            return self._gerar_parabola_3p(canvas, base)
        return self._gerar_spline(canvas, base, fechado=fechado)

    # -------------------------------------------------------------------------
    # PREVIEW E FINALIZAÇÃO
    # -------------------------------------------------------------------------
    def _pontos_preview(self, canvas) -> List[QPointF]:
        """Retorna a lista de pontos para o preview (nós + cursor)."""
        pontos = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]
        cursor = getattr(canvas, "_curva_np_cursor", None)
        if cursor is not None:
            if not pontos:
                pontos.append(QPointF(cursor))
            else:
                if self._dist2(pontos[-1], cursor) > 0.0001:
                    pontos.append(QPointF(cursor))
        return pontos

    def _cor_preview(self, canvas) -> str:
        cor = str(getattr(canvas, "_linha_cor", self.COR_PREVIEW))
        return cor if QColor(cor).isValid() else self.COR_PREVIEW

    def _espessura(self, canvas) -> float:
        try:
            return max(1.0, float(getattr(canvas, "_linha_espessura", 1.0)))
        except Exception:
            return 1.0

    def _append_elemento_polyline(
            self,
            canvas,
            pontos: List[QPointF],
            curva_suave: bool = False,
            pontos_principais: Optional[List[QPointF]] = None,
            fechado: bool = False,
            curva_espelhada: bool = False,
            eixo_espelho_x: float | None = None,
            tipo_curva: str = "spline_catmull_rom",
    ):
        if not hasattr(canvas, "cena") or not hasattr(canvas.cena, "elementos"):
            return
        if len(pontos) < 2:
            return

        pts_salvos = [(p.x(), p.y()) for p in pontos]
        principais = [(p.x(), p.y()) for p in (pontos_principais or pontos)]

        elemento = {
            "tipo": "polyline",
            "pontos": pts_salvos,
            "cor": getattr(canvas, "_linha_cor", "#ffffff"),
            "espessura": getattr(canvas, "_linha_espessura", 1.0),
            "estilo": getattr(canvas, "_linha_estilo", "solid"),
            "amplitude": getattr(canvas, "_linha_amplitude", 1.0),
            "fase_inicio": 0.0,
            "fechado": fechado,
        }

        if curva_suave and len(principais) > 2:
            elemento["curva_editavel"] = True
            elemento["curva_suave"] = True
            elemento["tipo_curva"] = tipo_curva
            elemento["renderizacao"] = "polyline"
            elemento["pontos_tracado_real"] = True
            elemento["pontos_principais"] = list(principais)
            elemento["pontos_controle_curva"] = list(principais)
            elemento["pontos_controle_principais"] = list(principais)
            elemento["pontos_controle"] = list(principais)

        if curva_espelhada:
            elemento["curva_espelhada"] = True
            if eixo_espelho_x is not None:
                elemento["eixo_espelho_x"] = float(eixo_espelho_x)

        canvas.cena.elementos.append(elemento)

    def _registrar_historico(self, canvas):
        if hasattr(canvas, "_registrar_historico"):
            try:
                canvas._registrar_historico()
            except Exception:
                pass

    def _finalizar_np(self, canvas, fechado: bool = False) -> bool:
        """Finaliza a curva atual e adiciona ao canvas."""
        pontos_base = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]
        pontos_base = self._remover_repetidos(pontos_base, tolerancia=0.001)

        if len(pontos_base) < 2:
            return False

        pontos_controle = [QPointF(p) for p in pontos_base]
        if fechado and len(pontos_controle) >= 3 and self._dist(pontos_controle[0], pontos_controle[-1]) <= 0.001:
            pontos_controle.pop()

        # Gerar spline
        if len(pontos_controle) == 2:
            curva = [QPointF(pontos_controle[0]), QPointF(pontos_controle[1])]
            tipo_curva = "linha_2p"
        elif self._modo_curva_atual(canvas) == "3p" and len(pontos_controle) == 3 and not fechado:
            curva = self._gerar_parabola_3p(canvas, pontos_controle)
            tipo_curva = "parabola_3p"
        elif fechado and len(pontos_controle) >= 4 and getattr(canvas, "_curva_ajustar_circulo", False) and (circulo := self._gerar_circulo_ajustado(canvas, pontos_controle)):
            curva = circulo
            tipo_curva = "circulo_ajustado"
        elif len(pontos_controle) >= 3 and not fechado:
            curva = self._gerar_spline(canvas, pontos_controle, fechado=False)
            tipo_curva = "spline_livre"
        else:
            curva = self._gerar_spline(canvas, pontos_controle, fechado)
            tipo_curva = "spline_catmull_rom"

        # Garantir fechamento visual
        if fechado and curva:
            if self._dist(curva[0], curva[-1]) > 0.01:
                curva.append(QPointF(curva[0]))
            else:
                curva[-1] = QPointF(curva[0])

        self._append_elemento_polyline(
            canvas,
            curva,
            curva_suave=len(pontos_controle) > 2,
            pontos_principais=pontos_controle,
            fechado=fechado,
            tipo_curva=tipo_curva,
        )

        if self._modo_curva_atual(canvas) == "espelhada" and pontos_controle:
            eixo_x = pontos_controle[0].x()
            curva_espelho = self._espelhar_pontos(curva, eixo_x)
            principais_espelho = self._espelhar_pontos(pontos_controle, eixo_x)
            self._append_elemento_polyline(
                canvas,
                curva_espelho,
                curva_suave=len(principais_espelho) > 2,
                pontos_principais=principais_espelho,
                fechado=fechado,
                curva_espelhada=True,
                eixo_espelho_x=eixo_x,
            )

        self._registrar_historico(canvas)
        return True

    # -------------------------------------------------------------------------
    # EVENTOS
    # -------------------------------------------------------------------------
    def on_key_press(self, canvas, event) -> bool:
        self._garantir_estado(canvas)

        if event.key() == Qt.Key_Escape:
            self._resetar(canvas, manter_elementos=True)
            self._status(canvas, "Curva cancelada.")
            canvas.update()
            event.accept()
            return True

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            fechado = getattr(canvas, "_curva_fechando", False)
            if self._finalizar_np(canvas, fechado):
                self._resetar(canvas, manter_elementos=True)
                self._status(canvas, "Curva finalizada.")
            else:
                self._resetar(canvas, manter_elementos=True)
                self._status(canvas, "Curva encerrada (menos de 2 pontos).")
            canvas.update()
            event.accept()
            return True

        return False

    def on_mouse_press(self, canvas, event) -> bool:
        self._garantir_estado(canvas)
        pos = self._snap(canvas, event.position())

        # Botão direito finaliza
        if event.button() == Qt.RightButton:
            fechado = getattr(canvas, "_curva_fechando", False)
            if self._finalizar_np(canvas, fechado):
                self._resetar(canvas, manter_elementos=True)
                self._status(canvas, "Curva finalizada.")
            else:
                self._resetar(canvas, manter_elementos=True)
                self._status(canvas, "Curva encerrada (menos de 2 pontos).")
            canvas.update()
            event.accept()
            return True

        # Botão esquerdo adiciona nó
        if event.button() != Qt.LeftButton:
            return False

        if canvas._curva_estado == "parada":
            canvas._curva_estado = "np_continuo"

        # Verificar fechamento: se clicar no primeiro nó (com 3+ nós), fechar
        ponto_fechamento = self._obter_ponto_fechamento(canvas, pos)
        if ponto_fechamento is not None:
            try:
                canvas._curva_ajustar_circulo = bool(event.modifiers() & Qt.ShiftModifier)
            except Exception:
                canvas._curva_ajustar_circulo = False
            # Fecha a curva imediatamente
            circulo_perfeito = bool(getattr(canvas, "_curva_ajustar_circulo", False))
            if self._finalizar_np(canvas, fechado=True):
                self._resetar(canvas, manter_elementos=True)
                self._status(canvas, "Círculo perfeito finalizado." if circulo_perfeito else "Curva fechada e finalizada.")
            else:
                self._resetar(canvas, manter_elementos=True)
                self._status(canvas, "Erro ao fechar curva.")
            canvas.update()
            event.accept()
            return True

        # Adicionar nó normal
        if not canvas._curva_np_nos:
            canvas._curva_np_nos.append(QPointF(pos))
        else:
            ultimo = canvas._curva_np_nos[-1]
            if self._dist2(ultimo, pos) > 0.0001:
                canvas._curva_np_nos.append(QPointF(pos))

        canvas._curva_np_cursor = QPointF(pos)
        canvas._curva_fechando = False
        self._atualizar_curva_confirmada(canvas)
        self._atualizar_painel(canvas)

        modo = self._modo_curva_atual(canvas)
        if (modo == "2p" and len(canvas._curva_np_nos) >= 2) or (modo == "3p" and len(canvas._curva_np_nos) >= 3):
            ok = self._finalizar_np(canvas, fechado=False)
            self._resetar(canvas, manter_elementos=True)
            self._status(canvas, "Curva finalizada." if ok else "Curva encerrada.")
        else:
            canvas._curva_np_preview = self._gerar_preview_profissional(canvas, cursor=None, fechado=False)
            self._atualizar_status_metricas(canvas, canvas._curva_np_preview or canvas._curva_np_curva_confirmada)

        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        self._garantir_estado(canvas)
        pos = self._snap(canvas, event.position())

        # Atualizar estado de fechamento
        fechando = False
        if len(canvas._curva_np_nos) >= 3:
            ponto_fechamento = self._obter_ponto_fechamento(canvas, pos)
            if ponto_fechamento is not None:
                pos = ponto_fechamento
                fechando = True

        canvas._curva_fechando = fechando
        try:
            canvas._curva_ajustar_circulo = bool(fechando and (event.modifiers() & Qt.ShiftModifier))
        except Exception:
            canvas._curva_ajustar_circulo = False

        # Atualizar cursor e preview
        if canvas._curva_np_nos:
            canvas._curva_np_cursor = QPointF(pos)
            canvas._curva_np_preview = self._gerar_preview_profissional(canvas, cursor=pos, fechado=fechando)
            self._atualizar_status_metricas(canvas, canvas._curva_np_preview)

            canvas.update()
            event.accept()
            return True

        return False

    def on_mouse_release(self, canvas, event) -> bool:
        return False

    # -------------------------------------------------------------------------
    # DESENHO
    # -------------------------------------------------------------------------
    def on_paint_overlay(self, canvas, painter):
        self._garantir_estado(canvas)

        pontos_preview = self._pontos_preview(canvas)
        if not pontos_preview:
            return

        # Desenhar nós (círculos)
        nos = getattr(canvas, "_curva_np_nos", [])
        for i, p in enumerate(nos):
            cor = self.COR_NO
            # Primeiro nó destaque se estiver fechando
            if i == 0 and getattr(canvas, "_curva_fechando", False):
                cor = self.COR_FECHAR
            self._desenhar_no_circulo(canvas, painter, QPointF(p), cor)

        # Se só um ponto, desenha ele e sai
        if len(pontos_preview) == 1:
            self._desenhar_no_circulo(canvas, painter, pontos_preview[0], self.COR_NO)
            return

        # Desenhar curva preview
        curva_preview = getattr(canvas, "_curva_np_preview", [])
        if not curva_preview:
            cursor = getattr(canvas, "_curva_np_cursor", None)
            curva_preview = self._gerar_preview_profissional(canvas, cursor=cursor, fechado=getattr(canvas, "_curva_fechando", False))
        if curva_preview:
            self._desenhar_polyline(
                canvas,
                painter,
                curva_preview,
                self._cor_preview(canvas),
                self._espessura(canvas),
            )

            if self._modo_curva_atual(canvas) == "espelhada" and getattr(canvas, "_curva_np_nos", []):
                eixo_x = QPointF(canvas._curva_np_nos[0]).x()
                curva_espelho = self._espelhar_pontos(curva_preview, eixo_x)
                self._desenhar_polyline(canvas, painter, curva_espelho, "#8b5cf6", self._espessura(canvas))
                ys = [p.y() for p in curva_preview + curva_espelho]
                if ys:
                    p1 = QPointF(eixo_x, min(ys) - 5.0)
                    p2 = QPointF(eixo_x, max(ys) + 5.0)
                    self._desenhar_polyline(canvas, painter, [p1, p2], "#38bdf8", 1.0)

        # Desenhar nó ativo (penúltimo ponto da lista de preview)
        if len(pontos_preview) >= 2:
            no_ativo = pontos_preview[-2]
            self._desenhar_no_losango(canvas, painter, no_ativo, self.COR_NO_ATIVO)
            self._desenhar_texto(canvas, painter, no_ativo, "nó", self.COR_NO_ATIVO)

        # Indicador de fechamento
        if getattr(canvas, "_curva_fechando", False) and len(nos) >= 3:
            primeiro = QPointF(nos[0])
            self._desenhar_texto(canvas, painter, primeiro, "fechar", self.COR_FECHAR)

        # Desenhar snap preview
        snap_res = getattr(canvas, "_curva_snap_preview", None)
        if snap_res is not None and getattr(snap_res, "ponto", None) is not None:
            self._desenhar_snap(canvas, painter, snap_res.ponto, self.COR_SNAP)

    def _desenhar_no_circulo(self, canvas, painter, ponto: QPointF, cor: str, raio: float = 4.0):
        """Desenha um nó como círculo (estilo CAD)."""
        if ponto is None:
            return

        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        pen = QPen(QColor(cor), 1.2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(tela.x() - raio, tela.y() - raio, raio * 2, raio * 2))

    def _desenhar_no_losango(self, canvas, painter, ponto: QPointF, cor: str, raio: float = 5.0):
        """Desenha o nó ativo como losango."""
        if ponto is None:
            return

        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        pen = QPen(QColor(cor), 1.2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        pontos = [
            QPointF(tela.x(), tela.y() - raio),
            QPointF(tela.x() + raio, tela.y()),
            QPointF(tela.x(), tela.y() + raio),
            QPointF(tela.x() - raio, tela.y()),
        ]
        painter.drawPolygon(QPolygonF(pontos))

    def _desenhar_snap(self, canvas, painter, ponto: QPointF, cor: str):
        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        pen = QPen(QColor(cor), 1.3, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(tela.x() - 5.0, tela.y() - 5.0, 10.0, 10.0))
        painter.drawLine(QPointF(tela.x() - 7.0, tela.y()), QPointF(tela.x() + 7.0, tela.y()))
        painter.drawLine(QPointF(tela.x(), tela.y() - 7.0), QPointF(tela.x(), tela.y() + 7.0))

    def _desenhar_texto(self, canvas, painter, ponto: QPointF, texto: str, cor: str):
        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        painter.setPen(QPen(QColor(cor), 1.0))
        painter.drawText(int(tela.x() + 6), int(tela.y() - 6), texto)

    def _desenhar_polyline(self, canvas, painter, pontos: List[QPointF], cor: str, espessura: float):
        if len(pontos) < 2:
            return

        pontos_tela = []
        for p in pontos:
            if hasattr(canvas, "_cena_para_tela"):
                pontos_tela.append(canvas._cena_para_tela(p))
            else:
                pontos_tela.append(QPointF(p))

        pen = QPen(QColor(cor), espessura, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(QPolygonF(pontos_tela))
