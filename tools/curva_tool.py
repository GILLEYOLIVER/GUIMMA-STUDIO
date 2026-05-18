from __future__ import annotations

from math import sqrt
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen, QPolygonF

from tools.tool_base import FerramentaBase


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
        if not hasattr(canvas, "_curva_fechando"):
            canvas._curva_fechando = False

    def _resetar(self, canvas, manter_elementos=True):
        canvas._curva_estado = "parada"
        canvas._curva_np_nos = []
        canvas._curva_np_cursor = None
        canvas._curva_np_preview = []
        canvas._curva_snap_preview = None
        canvas._curva_fechando = False

        if not manter_elementos and hasattr(canvas, "_resetar_estado_curva"):
            try:
                canvas._resetar_estado_curva()
            except Exception:
                pass

    def _set_status(self, canvas):
        if not canvas._curva_np_nos:
            self.set_status("Curva: clique para adicionar o primeiro nó.")
        else:
            msg = "Curva: continue clicando para adicionar nós. "
            if len(canvas._curva_np_nos) >= 3:
                msg += "Clique no primeiro nó para fechar. "
            msg += "Botão direito ou Enter finaliza. ESC cancela."
            self.set_status(msg)

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
        """Amostragem moderada e independente do zoom.

        Em ferramenta CAD/modelagem, a curva precisa ficar suave, mas não pode
        gravar centenas de pontos quando o zoom está alto.
        """
        d = self._dist(a, b)
        return max(12, min(34, int(d * 0.16) + 12))

    def _gerar_spline(self, canvas, pontos: List[QPointF], fechado: bool = False) -> List[QPointF]:
        """
        Gera uma spline cúbica natural a partir dos pontos de controle.
        Se fechado, a curva é fechada suavemente.
        """
        pts = self._remover_repetidos([QPointF(p) for p in pontos], tolerancia=0.001)

        if len(pts) <= 1:
            return []
        if len(pts) == 2:
            return [QPointF(pts[0]), QPointF(pts[1])]

        # Para curvas fechadas, adicionamos o primeiro ponto ao final para suavidade
        if fechado and len(pts) >= 3:
            pts_fechado = pts + [pts[0]]
        else:
            pts_fechado = pts

        t = self._parametros_por_corda(pts_fechado)
        xs = [p.x() for p in pts_fechado]
        ys = [p.y() for p in pts_fechado]

        mx = self._resolver_segundas_derivadas(xs, t)
        my = self._resolver_segundas_derivadas(ys, t)

        resultado: List[QPointF] = []

        num_segmentos = len(pts_fechado) - 1

        for i in range(num_segmentos):
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

            amostras = self._amostras_por_trecho(canvas, pts_fechado[i], pts_fechado[i + 1])

            if i == 0:
                resultado.append(QPointF(pts_fechado[i]))

            for s in range(1, amostras + 1):
                u = ti + ((tj - ti) * (s / float(amostras)))
                x = self._avaliar_spline(ti, tj, xi, xj, mxi, mxj, u)
                y = self._avaliar_spline(ti, tj, yi, yj, myi, myj, u)
                resultado.append(QPointF(x, y))

        if fechado and resultado:
            if self._dist(resultado[0], resultado[-1]) > 0.001:
                resultado.append(QPointF(resultado[0]))
            else:
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

    def _curva_dos_nos_confirmados(self, canvas, fechado: bool = False) -> List[QPointF]:
        nos = self._remover_repetidos([QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])], tolerancia=0.001)
        if len(nos) <= 1:
            return nos
        if len(nos) == 2:
            return [QPointF(nos[0]), QPointF(nos[1])]
        return self._gerar_spline(canvas, nos, fechado)

    def _trecho_temporario_cursor(self, canvas, cursor: QPointF) -> List[QPointF]:
        """Desenha somente o trecho temporário até o cursor.

        A regra principal observada no vídeo: o que já foi clicado não fica
        deformando enquanto o mouse se move. Só o trecho novo acompanha o cursor.
        """
        nos = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]
        if not nos:
            return [QPointF(cursor)]

        ultimo = QPointF(nos[-1])
        if self._dist2(ultimo, cursor) <= 1e-8:
            return [ultimo]

        if len(nos) == 1:
            return [ultimo, QPointF(cursor)]

        anterior = QPointF(nos[-2])

        # Tangência de saída baseada no último trecho confirmado, suave e curta.
        vx = ultimo.x() - anterior.x()
        vy = ultimo.y() - anterior.y()
        controle1 = QPointF(ultimo.x() + vx * 0.35, ultimo.y() + vy * 0.35)

        # Chegada no cursor com tangência leve na direção do próprio trecho.
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

    def _gerar_preview_profissional(self, canvas, cursor: QPointF | None = None, fechado: bool = False) -> List[QPointF]:
        """Preview igual ao comportamento do vídeo.

        - nós confirmados viram uma curva estável;
        - o mouse só cria um trecho temporário;
        - ao fechar, calcula o contorno fechado completo.
        """
        nos = [QPointF(p) for p in getattr(canvas, "_curva_np_nos", [])]
        if not nos:
            return []

        if fechado:
            base = list(nos)
            if cursor is not None and self._dist2(base[-1], cursor) > 0.0001:
                base.append(QPointF(cursor))
            return self._gerar_spline(canvas, base, fechado=True)

        curva_fixa = self._curva_dos_nos_confirmados(canvas, fechado=False)

        if cursor is None:
            return curva_fixa

        if self._dist2(QPointF(nos[-1]), cursor) <= 0.0001:
            return curva_fixa

        trecho = self._trecho_temporario_cursor(canvas, cursor)
        if curva_fixa and trecho and self._dist2(curva_fixa[-1], trecho[0]) <= 1e-8:
            return self._remover_repetidos(curva_fixa + trecho[1:], tolerancia=0.001)
        return self._remover_repetidos(curva_fixa + trecho, tolerancia=0.001)

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
            elemento["tipo_curva"] = "spline_natural"
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

        # Se fechado, garantir que o último ponto seja igual ao primeiro
        if fechado and len(pontos_base) >= 3:
            pontos_base[-1] = QPointF(pontos_base[0])

        # Gerar spline
        if len(pontos_base) == 2:
            curva = [QPointF(pontos_base[0]), QPointF(pontos_base[1])]
        else:
            curva = self._gerar_spline(canvas, pontos_base, fechado)

        # Garantir fechamento visual
        if fechado and curva:
            if self._dist(curva[0], curva[-1]) > 0.01:
                curva.append(QPointF(curva[0]))
            else:
                curva[-1] = QPointF(curva[0])

        self._append_elemento_polyline(
            canvas,
            curva,
            curva_suave=len(pontos_base) > 2,
            pontos_principais=pontos_base,
            fechado=fechado,
        )

        if self._modo_curva_atual(canvas) == "espelhada" and pontos_base:
            eixo_x = pontos_base[0].x()
            curva_espelho = self._espelhar_pontos(curva, eixo_x)
            principais_espelho = self._espelhar_pontos(pontos_base, eixo_x)
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
            self.set_status("Curva cancelada.")
            canvas.update()
            event.accept()
            return True

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            fechado = getattr(canvas, "_curva_fechando", False)
            if self._finalizar_np(canvas, fechado):
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Curva finalizada.")
            else:
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Curva encerrada (menos de 2 pontos).")
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
                self.set_status("Curva finalizada.")
            else:
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Curva encerrada (menos de 2 pontos).")
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
            # Fecha a curva imediatamente
            if self._finalizar_np(canvas, fechado=True):
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Curva fechada e finalizada.")
            else:
                self._resetar(canvas, manter_elementos=True)
                self.set_status("Erro ao fechar curva.")
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

        modo = self._modo_curva_atual(canvas)
        if (modo == "2p" and len(canvas._curva_np_nos) >= 2) or (modo == "3p" and len(canvas._curva_np_nos) >= 3):
            ok = self._finalizar_np(canvas, fechado=False)
            self._resetar(canvas, manter_elementos=True)
            self.set_status("Curva finalizada." if ok else "Curva encerrada.")
        else:
            canvas._curva_np_preview = self._gerar_preview_profissional(canvas, cursor=None, fechado=False)
            self._set_status(canvas)

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

        # Atualizar cursor e preview
        if canvas._curva_np_nos:
            canvas._curva_np_cursor = QPointF(pos)
            canvas._curva_np_preview = self._gerar_preview_profissional(canvas, cursor=pos, fechado=fechando)

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