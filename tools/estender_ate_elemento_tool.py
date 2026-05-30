from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QDialog

from core.geometry.engine import quadratic_bezier_control_for_point
from tools.tool_base import FerramentaBase


@dataclass
class _OrigemExtensao:
    elemento_idx: int
    ponto_movel_idx: int
    ponto_ancora_idx: int
    ponto_original: QPointF
    ponto_ancora: QPointF
    distancia: float


@dataclass
class _AlvoElemento:
    elemento_idx: int
    segmento_idx: int
    a: QPointF
    b: QPointF
    ponto_intersecao: QPointF | None
    distancia: float


class Ferramenta(FerramentaBase):
    id_ferramenta = "estender_ate_elemento"
    nome = "Estender até elemento"
    usa_painel_auxiliar = True
    descricao_painel = (
        "1) Clique na reta de origem para escolher a ponta mais próxima. "
        "2) Clique no elemento alvo. A reta será prolongada até a interseção. "
        "Botão direito cancela."
    )
    gerencia_coordenadas_operacao = True

    def __init__(self):
        super().__init__()
        self._hover_origem: _OrigemExtensao | None = None
        self._origem: _OrigemExtensao | None = None
        self._hover_alvo: _AlvoElemento | None = None
        self._preview: QPointF | None = None

    def on_activate(self, canvas) -> None:
        self._ocultar_janela_auxiliar_antiga(canvas)
        super().on_activate(canvas)
        self._hover_origem = None
        self._origem = None
        self._hover_alvo = None
        self._preview = None
        self._status(canvas, "Estender até elemento: clique na reta de origem; depois clique no elemento alvo.")
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        canvas.update()

    def on_deactivate(self, canvas) -> None:
        self._hover_origem = None
        self._origem = None
        self._hover_alvo = None
        self._preview = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        super().on_deactivate(canvas)
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._tela_para_cena(event.position())
        if self._origem is None:
            self._hover_origem = self._reta_origem_mais_proxima(canvas, pos)
            self._hover_alvo = None
            self._preview = None
            canvas.update()
            return False

        permitir_encurtar = bool(event.modifiers() & Qt.ShiftModifier)
        self._hover_alvo = self._elemento_alvo_mais_proximo(
            canvas,
            pos,
            ignorar_idx=self._origem.elemento_idx,
            permitir_encurtar=permitir_encurtar,
        )
        self._preview = self._hover_alvo.ponto_intersecao if self._hover_alvo else None
        if self._preview is not None and hasattr(canvas, "atualizar_operacao_coordenadas"):
            canvas.atualizar_operacao_coordenadas(self._preview)
        canvas.update()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._origem is not None or self._hover_origem is not None or self._hover_alvo is not None:
                self._limpar_estado(canvas)
                self._status(canvas, "Estender até elemento: operação cancelada. Clique novamente ou use dois cliques direitos para sair.")
                event.accept()
                return True
            return False

        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._tela_para_cena(event.position())
        if self._origem is None:
            origem = self._reta_origem_mais_proxima(canvas, pos)
            if origem is None:
                self._status(canvas, "Estender até elemento: clique sobre uma reta aberta de construção.")
                return False
            self._origem = origem
            self._hover_origem = origem
            self._hover_alvo = None
            self._preview = QPointF(origem.ponto_original)
            if hasattr(canvas, "iniciar_operacao_coordenadas"):
                canvas.iniciar_operacao_coordenadas(origem.ponto_ancora)
            self._status(canvas, "Reta de origem escolhida. Agora clique no elemento alvo.")
            canvas.update()
            event.accept()
            return True

        permitir_encurtar = bool(event.modifiers() & Qt.ShiftModifier)
        alvo = self._elemento_alvo_mais_proximo(
            canvas,
            pos,
            ignorar_idx=self._origem.elemento_idx,
            permitir_encurtar=permitir_encurtar,
        )
        if alvo is None:
            self._status(canvas, "Estender até elemento: nenhum elemento alvo encontrado no clique.")
            return False
        if alvo.ponto_intersecao is None:
            self._status(canvas, "Estender até elemento: a reta não encontra esse elemento no sentido da extensão.")
            return False

        aplicado = self._aplicar_extensao(canvas, self._origem, alvo.ponto_intersecao)
        if aplicado:
            self._status(canvas, "Reta estendida até o elemento alvo. Nada ficou selecionado.")
        else:
            self._status(canvas, "Estender até elemento: nenhuma alteração aplicada.")
        if hasattr(canvas, "finalizar_operacao_coordenadas"):
            canvas.finalizar_operacao_coordenadas(alvo.ponto_intersecao)
        self._origem = None
        self._hover_origem = None
        self._hover_alvo = None
        self._preview = None
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados.clear()
        canvas.update()
        event.accept()
        return True

    def desfazer_etapa(self, canvas) -> bool:
        if self._origem is None and self._hover_origem is None and self._hover_alvo is None:
            return False
        self._limpar_estado(canvas)
        self._status(canvas, "Estender até elemento: etapa atual desfeita.")
        return True

    def origem_coordenadas(self, canvas) -> QPointF:
        if self._origem is not None:
            return QPointF(self._origem.ponto_ancora)
        if self._hover_origem is not None:
            return QPointF(self._hover_origem.ponto_ancora)
        return QPointF(0.0, 0.0)

    def on_paint_overlay(self, canvas, painter: QPainter) -> None:
        origem = self._origem or self._hover_origem
        if origem is None:
            return

        p_ancora = QPointF(origem.ponto_ancora)
        p_original = QPointF(origem.ponto_original)
        p_preview = QPointF(self._preview) if self._preview is not None else p_original

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        cor_azul = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        if not cor_azul.isValid():
            cor_azul = QColor("#2da8ff")
        cor_alvo = QColor("#ffb000")

        pen_origem = QPen(cor_azul, 2.2, Qt.SolidLine)
        pen_origem.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_origem)
        painter.drawLine(canvas._cena_para_tela(p_ancora), canvas._cena_para_tela(p_original))

        if self._origem is not None:
            pen_preview = QPen(cor_azul.lighter(130), 2.8, Qt.DashLine)
            pen_preview.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_preview)
            painter.drawLine(canvas._cena_para_tela(p_ancora), canvas._cena_para_tela(p_preview))

        alvo = self._hover_alvo
        if alvo is not None:
            pen_alvo = QPen(cor_alvo, 2.0, Qt.SolidLine)
            pen_alvo.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_alvo)
            painter.drawLine(canvas._cena_para_tela(alvo.a), canvas._cena_para_tela(alvo.b))

        self._desenhar_ponto(painter, canvas._cena_para_tela(p_ancora), QColor("#ffffff"), 4.0)
        self._desenhar_ponto(painter, canvas._cena_para_tela(p_original), QColor("#ff3030"), 5.0)
        if self._preview is not None and self._origem is not None:
            self._desenhar_ponto(painter, canvas._cena_para_tela(self._preview), QColor("#ff3030"), 5.0)
            self._desenhar_rotulo(canvas, painter, self._preview, "interseção")

        painter.restore()

    def _limpar_estado(self, canvas) -> None:
        self._hover_origem = None
        self._origem = None
        self._hover_alvo = None
        self._preview = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        canvas.update()

    def _reta_origem_mais_proxima(self, canvas, pos: QPointF) -> _OrigemExtensao | None:
        tolerancia = max(8.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001), 0.08)
        melhor: _OrigemExtensao | None = None
        candidatos = sorted(getattr(canvas, "_selecionados", set()) or []) or list(range(len(canvas.cena.elementos)))

        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            elemento = canvas.cena.elementos[idx]
            if not self._elemento_origem_editavel(elemento):
                continue
            pontos = self._pontos_polyline(elemento)
            if len(pontos) < 2:
                continue
            for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
                _proj, dist = self._projetar_no_segmento(a, b, pos)
                if dist > tolerancia:
                    continue
                origem = self._origem_para_segmento(idx, seg_idx, pontos, a, b, pos, dist)
                if origem is not None and (melhor is None or origem.distancia < melhor.distancia):
                    melhor = origem
        return melhor

    def _origem_para_segmento(
        self,
        elemento_idx: int,
        segmento_idx: int,
        pontos: list[QPointF],
        a: QPointF,
        b: QPointF,
        pos: QPointF,
        distancia: float,
    ) -> _OrigemExtensao | None:
        total = len(pontos)
        if total == 2:
            if self._distancia(pos, a) <= self._distancia(pos, b):
                movel_idx, ancora_idx = 0, 1
                movel, ancora = a, b
            else:
                movel_idx, ancora_idx = 1, 0
                movel, ancora = b, a
        elif segmento_idx == 0:
            movel_idx, ancora_idx = 0, 1
            movel, ancora = pontos[0], pontos[1]
        elif segmento_idx == total - 2:
            movel_idx, ancora_idx = total - 1, total - 2
            movel, ancora = pontos[-1], pontos[-2]
        else:
            return None

        if self._distancia(movel, ancora) <= 1e-7:
            return None
        return _OrigemExtensao(
            elemento_idx=elemento_idx,
            ponto_movel_idx=movel_idx,
            ponto_ancora_idx=ancora_idx,
            ponto_original=QPointF(movel),
            ponto_ancora=QPointF(ancora),
            distancia=distancia,
        )

    def _elemento_alvo_mais_proximo(
        self,
        canvas,
        pos: QPointF,
        ignorar_idx: int,
        permitir_encurtar: bool,
    ) -> _AlvoElemento | None:
        if self._origem is None:
            return None
        tolerancia = max(10.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001), 0.10)
        melhor: _AlvoElemento | None = None

        for idx, elemento in enumerate(canvas.cena.elementos):
            if idx == ignorar_idx or not isinstance(elemento, dict):
                continue
            segmentos = self._segmentos_elemento_alvo(elemento)
            if not segmentos:
                continue
            for seg_idx, (a, b) in enumerate(segmentos):
                _proj, dist = self._projetar_no_segmento(a, b, pos)
                if dist > tolerancia:
                    continue
                intersecao = self._intersecao_origem_com_segmento(self._origem, a, b, permitir_encurtar)
                alvo = _AlvoElemento(idx, seg_idx, QPointF(a), QPointF(b), intersecao, dist)
                if melhor is None:
                    melhor = alvo
                    continue
                melhor_tem_intersecao = melhor.ponto_intersecao is not None
                alvo_tem_intersecao = alvo.ponto_intersecao is not None
                if alvo_tem_intersecao and not melhor_tem_intersecao:
                    melhor = alvo
                elif alvo_tem_intersecao == melhor_tem_intersecao and dist < melhor.distancia:
                    melhor = alvo
        return melhor

    def _intersecao_origem_com_segmento(
        self,
        origem: _OrigemExtensao,
        a: QPointF,
        b: QPointF,
        permitir_encurtar: bool,
    ) -> QPointF | None:
        ax, ay = origem.ponto_ancora.x(), origem.ponto_ancora.y()
        ox, oy = origem.ponto_original.x(), origem.ponto_original.y()
        dx, dy = ox - ax, oy - ay
        comprimento = sqrt((dx * dx) + (dy * dy))
        if comprimento <= 1e-9:
            return None
        ux, uy = dx / comprimento, dy / comprimento
        vx, vy = b.x() - a.x(), b.y() - a.y()
        wx, wy = a.x() - ax, a.y() - ay
        den = self._cross(ux, uy, vx, vy)
        minimo_t = 0.001 if permitir_encurtar else comprimento

        if abs(den) <= 1e-9:
            if abs(self._cross(wx, wy, ux, uy)) > 1e-7:
                return None
            t1 = ((a.x() - ax) * ux) + ((a.y() - ay) * uy)
            t2 = ((b.x() - ax) * ux) + ((b.y() - ay) * uy)
            t_min, t_max = sorted((t1, t2))
            if t_max < minimo_t - 1e-7:
                return None
            t = max(t_min, minimo_t)
            if t > t_max + 1e-7:
                return None
            return QPointF(ax + (ux * t), ay + (uy * t))

        t = self._cross(wx, wy, vx, vy) / den
        u = self._cross(wx, wy, ux, uy) / den
        if t < minimo_t - 1e-7:
            return None
        if u < -1e-7 or u > 1.0 + 1e-7:
            return None
        return QPointF(ax + (ux * t), ay + (uy * t))

    def _aplicar_extensao(self, canvas, origem: _OrigemExtensao, novo_ponto: QPointF) -> bool:
        if origem.elemento_idx < 0 or origem.elemento_idx >= len(canvas.cena.elementos):
            return False
        elemento = canvas.cena.elementos[origem.elemento_idx]
        if not self._elemento_origem_editavel(elemento):
            return False
        pontos = self._pontos_polyline(elemento)
        if not (0 <= origem.ponto_movel_idx < len(pontos)):
            return False
        if self._distancia(pontos[origem.ponto_movel_idx], novo_ponto) <= 1e-6:
            return False
        pontos[origem.ponto_movel_idx] = QPointF(novo_ponto)
        elemento["pontos"] = [(float(p.x()), float(p.y())) for p in pontos]
        elemento.setdefault("metadados", {})["ultima_ferramenta"] = self.id_ferramenta
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados.clear()
        return True

    def _segmentos_elemento_alvo(self, elemento: dict) -> list[tuple[QPointF, QPointF]]:
        tipo = str(elemento.get("tipo") or "")
        if tipo == "bezier_quadratica":
            try:
                return self._segmentos_bezier(
                    QPointF(float(elemento["p0"][0]), float(elemento["p0"][1])),
                    QPointF(float(elemento["p1"][0]), float(elemento["p1"][1])),
                    QPointF(float(elemento["p2"][0]), float(elemento["p2"][1])),
                )
            except Exception:
                return []
        if tipo != "polyline":
            return []
        pontos = self._pontos_polyline(elemento)
        if len(pontos) < 2:
            return []
        if str(elemento.get("tipo_curva") or "").strip().lower() == "parabola_3p" and len(pontos) >= 3:
            p0, pmedio, p2 = pontos[0], pontos[1], pontos[2]
            try:
                cx, cy = quadratic_bezier_control_for_point(
                    (float(p0.x()), float(p0.y())),
                    (float(pmedio.x()), float(pmedio.y())),
                    (float(p2.x()), float(p2.y())),
                )
                return self._segmentos_bezier(p0, QPointF(cx, cy), p2)
            except Exception:
                pass
        return [(QPointF(a), QPointF(b)) for a, b in zip(pontos, pontos[1:])]

    @staticmethod
    def _segmentos_bezier(p0: QPointF, p1: QPointF, p2: QPointF, passos: int = 48) -> list[tuple[QPointF, QPointF]]:
        pontos: list[QPointF] = []
        n = max(8, int(passos))
        for i in range(n + 1):
            t = i / n
            mt = 1.0 - t
            x = (mt * mt * p0.x()) + (2.0 * mt * t * p1.x()) + (t * t * p2.x())
            y = (mt * mt * p0.y()) + (2.0 * mt * t * p1.y()) + (t * t * p2.y())
            pontos.append(QPointF(x, y))
        return [(pontos[i], pontos[i + 1]) for i in range(len(pontos) - 1)]

    @staticmethod
    def _elemento_origem_editavel(elemento: dict) -> bool:
        if not isinstance(elemento, dict):
            return False
        if elemento.get("tipo") != "polyline":
            return False
        if bool(elemento.get("molde")):
            return False
        pontos = elemento.get("pontos") or []
        if len(pontos) < 2:
            return False
        try:
            primeiro = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            ultimo = QPointF(float(pontos[-1][0]), float(pontos[-1][1]))
            if len(pontos) > 2 and Ferramenta._distancia(primeiro, ultimo) <= 1e-7:
                return False
        except Exception:
            return False
        return True

    @staticmethod
    def _pontos_polyline(elemento: dict) -> list[QPointF]:
        pontos: list[QPointF] = []
        for item in elemento.get("pontos", []) or []:
            try:
                if isinstance(item, dict):
                    pontos.append(QPointF(float(item.get("x", 0.0)), float(item.get("y", 0.0))))
                else:
                    pontos.append(QPointF(float(item[0]), float(item[1])))
            except Exception:
                continue
        return pontos

    @staticmethod
    def _projetar_no_segmento(a: QPointF, b: QPointF, p: QPointF) -> tuple[QPointF, float]:
        abx, aby = b.x() - a.x(), b.y() - a.y()
        apx, apy = p.x() - a.x(), p.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            proj = QPointF(a)
        else:
            t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / den))
            proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return proj, Ferramenta._distancia(proj, p)

    @staticmethod
    def _distancia(a: QPointF, b: QPointF) -> float:
        return sqrt(((a.x() - b.x()) ** 2) + ((a.y() - b.y()) ** 2))

    @staticmethod
    def _cross(ax: float, ay: float, bx: float, by: float) -> float:
        return (ax * by) - (ay * bx)

    @staticmethod
    def _desenhar_ponto(painter: QPainter, ponto_tela: QPointF, cor: QColor, raio: float) -> None:
        painter.save()
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.setBrush(cor)
        painter.drawEllipse(ponto_tela, raio, raio)
        painter.restore()

    def _desenhar_rotulo(self, canvas, painter: QPainter, ponto_cena: QPointF, texto: str) -> None:
        ponto_tela = canvas._cena_para_tela(ponto_cena)
        fonte = painter.font()
        fonte.setBold(True)
        fonte.setPointSize(max(8, fonte.pointSize()))
        painter.setFont(fonte)
        metrics = QFontMetrics(fonte)
        largura = metrics.horizontalAdvance(texto) + 12
        altura = metrics.height() + 6
        x = ponto_tela.x() + 10
        y = ponto_tela.y() - altura - 10
        if x + largura > canvas.width() - 4:
            x = ponto_tela.x() - largura - 10
        if y < 4:
            y = ponto_tela.y() + 12
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.drawRoundedRect(int(x), int(y), int(largura), int(altura), 4, 4)
        painter.setPen(QPen(QColor("#2da8ff"), 1.0))
        painter.drawText(int(x + 6), int(y + 3), int(largura - 12), int(altura - 6), Qt.AlignCenter, texto)
        painter.restore()

    def _ocultar_janela_auxiliar_antiga(self, canvas) -> None:
        """Remove a janela separada antiga para ficar apenas o painel interno do canvas."""
        janela_principal = None
        try:
            janela_principal = canvas.window() if canvas is not None and hasattr(canvas, "window") else None
        except Exception:
            janela_principal = None

        app = QApplication.instance()
        filtro_removido = False
        if app is not None and janela_principal is not None:
            try:
                app.removeEventFilter(janela_principal)
                filtro_removido = True
            except Exception:
                filtro_removido = False

        try:
            dialogos: list[QDialog] = []
            caixas = getattr(janela_principal, "_janelas_aux_instrucao", None) if janela_principal is not None else None
            if isinstance(caixas, dict):
                dialogo = caixas.get(self.id_ferramenta)
                if isinstance(dialogo, QDialog):
                    dialogos.append(dialogo)
            if app is not None:
                for widget in app.topLevelWidgets():
                    if isinstance(widget, QDialog) and widget.windowTitle() == f"{self.nome} - Auxiliar":
                        dialogos.append(widget)
            for dialogo in dict.fromkeys(dialogos):
                try:
                    dialogo.hide()
                except Exception:
                    pass
        finally:
            if app is not None and janela_principal is not None and filtro_removido:
                try:
                    app.installEventFilter(janela_principal)
                except Exception:
                    pass

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
