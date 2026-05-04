from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen, QPolygonF

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "curva"
    nome = "Curva"
    usa_painel_auxiliar = False
    descricao_painel = (
        "Curva por nós com spline suave. "
        "Clique esquerdo cria nós. Botão direito finaliza. ESC cancela."
    )

    COR_PREVIEW = "#ff00ff"
    COR_NO = "#ff4fd8"
    COR_SNAP = "#7df9ff"

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._garantir_estado(canvas)
        self._resetar(canvas, manter_elementos=True)
        self._set_status(canvas)
        canvas.update()

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

    def _resetar(self, canvas, manter_elementos=True):
        canvas._curva_estado = "parada"
        canvas._curva_np_nos = []
        canvas._curva_np_cursor = None
        canvas._curva_np_preview = []
        canvas._curva_snap_preview = None

        if not manter_elementos and hasattr(canvas, "_resetar_estado_curva"):
            try:
                canvas._resetar_estado_curva()
            except Exception:
                pass

    def _set_status(self, canvas):
        if not canvas._curva_np_nos:
            self.set_status("Curva: clique no primeiro nó.")
        else:
            self.set_status(
                "Curva: continue clicando para criar nós. "
                "Botão direito finaliza. ESC cancela."
            )

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    def _snap(self, canvas, pos):
        if hasattr(canvas, "_ponto_com_snap"):
            try:
                ponto = canvas._ponto_com_snap(pos)
                canvas._curva_snap_preview = getattr(canvas, "_snap_resultado", None)
                return ponto
            except Exception:
                pass
        canvas._curva_snap_preview = None
        return QPointF(pos)

    def _dist(self, a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return sqrt((dx * dx) + (dy * dy))

    def _dist2(self, a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return (dx * dx) + (dy * dy)

    def _remover_repetidos(self, pontos: list[QPointF], tolerancia: float = 0.01) -> list[QPointF]:
        if not pontos:
            return []
        resultado = [QPointF(pontos[0])]
        tol2 = tolerancia * tolerancia
        for p in pontos[1:]:
            if self._dist2(resultado[-1], p) > tol2:
                resultado.append(QPointF(p))
        return resultado

    def _pontos_preview(self, canvas) -> list[QPointF]:
        pontos = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]

        if canvas._curva_np_cursor is not None:
            if not pontos:
                pontos.append(QPointF(canvas._curva_np_cursor))
            else:
                atual = QPointF(canvas._curva_np_cursor)
                if self._dist2(pontos[-1], atual) > 0.0001:
                    pontos.append(atual)

        return pontos

    def _cor_preview(self, canvas) -> str:
        cor = str(getattr(canvas, "_linha_cor", self.COR_PREVIEW))
        if QColor(cor).isValid():
            return cor
        return self.COR_PREVIEW

    def _espessura(self, canvas) -> float:
        try:
            return max(1.0, float(getattr(canvas, "_linha_espessura", 1.0)))
        except Exception:
            return 1.0

    def _tolerancia_snap_cena(self, canvas) -> float:
        if hasattr(canvas, "_tolerancia_snap_px"):
            try:
                return float(canvas._tolerancia_snap_px()) / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
            except Exception:
                pass
        return 10.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)

    def _fechamento_proximo(self, canvas, ponto: QPointF | None) -> bool:
        if ponto is None:
            return False
        nos = getattr(canvas, "_curva_np_nos", [])
        if len(nos) < 3:
            return False
        primeiro = QPointF(nos[0])
        return self._dist(primeiro, ponto) <= self._tolerancia_snap_cena(canvas)

    def _normalizar_fechamento(self, canvas, pontos_base: list[QPointF]) -> tuple[list[QPointF], bool]:
        pontos = [QPointF(p) for p in pontos_base]
        if len(pontos) < 3:
            return pontos, False

        primeiro = QPointF(pontos[0])
        ultimo = QPointF(pontos[-1])
        fechado = self._dist(primeiro, ultimo) <= self._tolerancia_snap_cena(canvas)

        if fechado:
            pontos[-1] = QPointF(primeiro)
        return pontos, fechado

    def _criar_snap_result(self, canvas, cursor: QPointF, ponto: QPointF, tipo: str):
        resultado_cls = None
        if hasattr(canvas, "_snap_resultado") and canvas._snap_resultado is not None:
            resultado_cls = type(canvas._snap_resultado)
        if resultado_cls is None:
            try:
                from canvas.snap import SnapResult as resultado_cls
            except Exception:
                resultado_cls = None
        distancia = self._dist(cursor, ponto)
        if resultado_cls is not None:
            return resultado_cls(ponto=QPointF(ponto), tipo=tipo, distancia=distancia, elemento_idx=None)
        return None

    def obter_candidatos_snap(self, canvas, cursor: QPointF):
        self._garantir_estado(canvas)
        candidatos = []
        tol_cena = self._tolerancia_snap_cena(canvas)
        nos = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]

        if not nos:
            return candidatos

        primeiro = QPointF(nos[0])
        resultado = self._criar_snap_result(canvas, cursor, primeiro, "nó")
        if resultado is not None and resultado.distancia <= tol_cena:
            candidatos.append(resultado)

        for ponto in nos[1:]:
            resultado = self._criar_snap_result(canvas, cursor, ponto, "nó")
            if resultado is not None and resultado.distancia <= tol_cena:
                candidatos.append(resultado)

        for inicio, fim in zip(nos, nos[1:]):
            proj = canvas._snap_manager._projetar_em_segmento(cursor, inicio, fim)
            resultado_borda = self._criar_snap_result(canvas, cursor, proj, "borda")
            if resultado_borda is not None and resultado_borda.distancia <= tol_cena:
                candidatos.append(resultado_borda)
            meio = QPointF((inicio.x() + fim.x()) / 2.0, (inicio.y() + fim.y()) / 2.0)
            resultado_meio = self._criar_snap_result(canvas, cursor, meio, "ponto médio")
            if resultado_meio is not None and resultado_meio.distancia <= tol_cena:
                candidatos.append(resultado_meio)

        cursor_curva = getattr(canvas, "_curva_np_cursor", None)
        if cursor_curva is not None and nos:
            ultimo = QPointF(nos[-1])
            atual = QPointF(cursor_curva)
            proj = canvas._snap_manager._projetar_em_segmento(cursor, ultimo, atual)
            resultado_borda = self._criar_snap_result(canvas, cursor, proj, "borda")
            if resultado_borda is not None and resultado_borda.distancia <= tol_cena:
                candidatos.append(resultado_borda)

        preview = [QPointF(p) for p in getattr(canvas, "_curva_np_preview", [])]
        for inicio, fim in zip(preview, preview[1:]):
            proj = canvas._snap_manager._projetar_em_segmento(cursor, inicio, fim)
            resultado_borda = self._criar_snap_result(canvas, cursor, proj, "borda")
            if resultado_borda is not None and resultado_borda.distancia <= tol_cena:
                candidatos.append(resultado_borda)

        return candidatos

    # -------------------------------------------------------------------------
    # SPLINE CÚBICA NATURAL
    # -------------------------------------------------------------------------
    def _parametros_por_corda(self, pontos: list[QPointF]) -> list[float]:
        if not pontos:
            return []
        t = [0.0]
        for i in range(1, len(pontos)):
            d = self._dist(pontos[i - 1], pontos[i])
            if d < 1e-6:
                d = 1e-6
            t.append(t[-1] + d)
        return t

    def _resolver_segundas_derivadas(self, valores: list[float], t: list[float]) -> list[float]:
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

        # Thomas
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

    def _amostras_por_trecho(self, a: QPointF, b: QPointF) -> int:
        d = self._dist(a, b)
        return max(16, min(90, int(d * 0.28) + 16))

    def _gerar_curva(self, pontos_base: list[QPointF]) -> list[QPointF]:
        pontos = self._remover_repetidos([QPointF(p) for p in pontos_base], tolerancia=0.001)

        if len(pontos) <= 1:
            return pontos

        if len(pontos) == 2:
            return [QPointF(pontos[0]), QPointF(pontos[1])]

        t = self._parametros_por_corda(pontos)
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]

        mx = self._resolver_segundas_derivadas(xs, t)
        my = self._resolver_segundas_derivadas(ys, t)

        resultado: list[QPointF] = []

        for i in range(len(pontos) - 1):
            ti = t[i]
            tj = t[i + 1]
            xi = xs[i]
            xj = xs[i + 1]
            yi = ys[i]
            yj = ys[i + 1]
            mxi = mx[i]
            mxj = mx[i + 1]
            myi = my[i]
            myj = my[i + 1]

            amostras = self._amostras_por_trecho(pontos[i], pontos[i + 1])

            trecho: list[QPointF] = []
            for s in range(amostras):
                u = ti + ((tj - ti) * (s / float(amostras)))
                x = self._avaliar_spline(ti, tj, xi, xj, mxi, mxj, u)
                y = self._avaliar_spline(ti, tj, yi, yj, myi, myj, u)
                trecho.append(QPointF(x, y))

            trecho.append(QPointF(pontos[i + 1]))

            if not resultado:
                resultado.extend(trecho)
            else:
                if self._dist2(resultado[-1], trecho[0]) < 1e-8:
                    resultado.extend(trecho[1:])
                else:
                    resultado.extend(trecho)

        return self._remover_repetidos(resultado, tolerancia=0.001)

    # -------------------------------------------------------------------------
    # CENA / HISTÓRICO
    # -------------------------------------------------------------------------
    def _append_elemento_polyline(self, canvas, pontos: list[QPointF]):
        if not hasattr(canvas, "cena") or not hasattr(canvas.cena, "elementos"):
            return
        if len(pontos) < 2:
            return

        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "pontos": [(p.x(), p.y()) for p in pontos],
                "cor": getattr(canvas, "_linha_cor", "#ffffff"),
                "espessura": getattr(canvas, "_linha_espessura", 1.0),
                "estilo": getattr(canvas, "_linha_estilo", "solid"),
                "amplitude": getattr(canvas, "_linha_amplitude", 1.0),
                "fase_inicio": 0.0,
            }
        )

    def _registrar_historico(self, canvas):
        if hasattr(canvas, "_registrar_historico"):
            try:
                canvas._registrar_historico()
            except Exception:
                pass

    def _finalizar_np(self, canvas) -> bool:
        pontos_base = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]
        pontos_base = self._remover_repetidos(pontos_base, tolerancia=0.001)
        pontos_base, fechado = self._normalizar_fechamento(canvas, pontos_base)

        if len(pontos_base) < 2:
            return False

        curva = self._gerar_curva(pontos_base)
        curva = self._remover_repetidos(curva, tolerancia=0.01)

        if fechado and curva:
            if self._dist(curva[0], curva[-1]) > 0.01:
                curva.append(QPointF(curva[0]))
            else:
                curva[-1] = QPointF(curva[0])

        if len(curva) < 2:
            return False

        self._append_elemento_polyline(canvas, curva)
        self._registrar_historico(canvas)
        return True

    # -------------------------------------------------------------------------
    # EVENTOS
    # -------------------------------------------------------------------------
    def on_key_press(self, canvas, event) -> bool:
        self._garantir_estado(canvas)

        if event.key() == Qt.Key_Escape:
            self._resetar(canvas, manter_elementos=True)
            self.set_status("Curva cancelada.")
            canvas.update()
            event.accept()
            return True

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._finalizar_np(canvas):
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Curva finalizada.")
            else:
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Curva encerrada.")
            canvas.update()
            event.accept()
            return True

        return False

    def on_mouse_press(self, canvas, event) -> bool:
        self._garantir_estado(canvas)
        pos = self._snap(canvas, event.position())

        if event.button() == Qt.RightButton:
            if self._finalizar_np(canvas):
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Curva finalizada.")
            else:
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Curva encerrada.")
            canvas.update()
            event.accept()
            return True

        if event.button() != Qt.LeftButton:
            return False

        if canvas._curva_estado == "parada":
            canvas._curva_estado = "np_continuo"

        if canvas._curva_np_nos and self._fechamento_proximo(canvas, pos):
            pos = QPointF(canvas._curva_np_nos[0])

        if not canvas._curva_np_nos:
            canvas._curva_np_nos.append(QPointF(pos))
        else:
            ultimo = canvas._curva_np_nos[-1]
            if self._dist2(ultimo, pos) > 0.0001:
                canvas._curva_np_nos.append(QPointF(pos))

        canvas._curva_np_cursor = QPointF(pos)
        self._set_status(canvas)
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        self._garantir_estado(canvas)
        pos = self._snap(canvas, event.position())

        if canvas._curva_np_nos and self._fechamento_proximo(canvas, pos):
            pos = QPointF(canvas._curva_np_nos[0])

        if canvas._curva_np_nos:
            canvas._curva_np_cursor = QPointF(pos)
            pontos_preview = self._pontos_preview(canvas)
            canvas._curva_np_preview = self._gerar_curva(pontos_preview) if len(pontos_preview) >= 2 else pontos_preview
            canvas.update()
            event.accept()
            return True

        return False

    def on_mouse_release(self, canvas, event) -> bool:
        return False

    # -------------------------------------------------------------------------
    # DESENHO
    # -------------------------------------------------------------------------
    def _desenhar_marca_x(self, canvas, painter, ponto: QPointF, cor: str):
        if ponto is None:
            return

        if hasattr(canvas, "_desenhar_marca_x"):
            try:
                canvas._desenhar_marca_x(painter, ponto, cor=cor)
                return
            except Exception:
                pass

        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        pen = QPen(QColor(cor), 1.0, Qt.SolidLine)
        painter.setPen(pen)
        x = tela.x()
        y = tela.y()
        painter.drawLine(QPointF(x - 5, y - 5), QPointF(x + 5, y + 5))
        painter.drawLine(QPointF(x - 5, y + 5), QPointF(x + 5, y - 5))

    def _desenhar_no_quadrado(self, canvas, painter, ponto: QPointF, cor: str):
        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        pen = QPen(QColor(cor), 1.2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(tela.x() - 4.0, tela.y() - 4.0, 8.0, 8.0))

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

    def _desenhar_polyline(self, canvas, painter, pontos: list[QPointF], cor: str, espessura: float):
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

    def on_paint_overlay(self, canvas, painter):
        self._garantir_estado(canvas)

        pontos_preview = self._pontos_preview(canvas)
        if not pontos_preview:
            return

        for p in getattr(canvas, "_curva_np_nos", []):
            self._desenhar_marca_x(canvas, painter, QPointF(p), self.COR_NO)

        if len(pontos_preview) == 1:
            self._desenhar_marca_x(canvas, painter, pontos_preview[0], self.COR_NO)
            return

        curva_preview = self._gerar_curva(pontos_preview)
        self._desenhar_polyline(
            canvas,
            painter,
            curva_preview,
            self._cor_preview(canvas),
            self._espessura(canvas),
        )

        no_ativo = pontos_preview[-2]
        self._desenhar_no_quadrado(canvas, painter, no_ativo, self.COR_NO)
        self._desenhar_texto(canvas, painter, no_ativo, "nó", self.COR_NO)

        snap_res = getattr(canvas, "_curva_snap_preview", None)
        if snap_res is not None and getattr(snap_res, "ponto", None) is not None:
            self._desenhar_snap(canvas, painter, snap_res.ponto, self.COR_SNAP)
