from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QDialog

from tools.tool_base import FerramentaBase


@dataclass
class _AlvoExtensao:
    elemento_idx: int
    segmento_idx: int
    ponto_movel_idx: int
    ponto_ancora_idx: int
    ponto_original: QPointF
    ponto_ancora: QPointF
    ponto_segmento: QPointF
    distancia: float


class Ferramenta(FerramentaBase):
    id_ferramenta = "estender_reta"
    nome = "Estender reta"
    usa_painel_auxiliar = True
    descricao_painel = (
        "Clique em uma reta para escolher a ponta mais próxima. "
        "Mova o mouse para indicar o novo comprimento e clique novamente para confirmar. "
        "Shift permite encurtar; botão direito cancela."
    )
    gerencia_coordenadas_operacao = True

    def __init__(self):
        super().__init__()
        self._hover: _AlvoExtensao | None = None
        self._alvo: _AlvoExtensao | None = None
        self._preview: QPointF | None = None

    def on_activate(self, canvas) -> None:
        self._ocultar_janela_auxiliar_antiga(canvas)
        super().on_activate(canvas)
        self._hover = None
        self._alvo = None
        self._preview = None
        self._status(
            canvas,
            "Estender reta: clique em uma reta; mova o mouse e clique novamente para confirmar. Botão direito cancela.",
        )
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        canvas.update()

    def on_deactivate(self, canvas) -> None:
        self._hover = None
        self._alvo = None
        self._preview = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        super().on_deactivate(canvas)
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        if self._alvo is not None:
            destino = canvas._ponto_com_snap(event.position())
            self._preview = self._projetar_destino(self._alvo, destino, permitir_encurtar=bool(event.modifiers() & Qt.ShiftModifier))
            if hasattr(canvas, "atualizar_operacao_coordenadas"):
                canvas.atualizar_operacao_coordenadas(self._preview)
            canvas.update()
            return True

        pos = canvas._tela_para_cena(event.position())
        self._hover = self._reta_mais_proxima(canvas, pos)
        canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._alvo is not None or self._hover is not None:
                self._limpar_estado(canvas)
                self._status(canvas, "Estender reta: operação cancelada. Clique em outra reta ou use dois cliques direitos para sair.")
                event.accept()
                return True
            return False

        if event.button() != Qt.LeftButton:
            return False

        if self._alvo is None:
            pos = canvas._tela_para_cena(event.position())
            alvo = self._reta_mais_proxima(canvas, pos)
            if alvo is None:
                self._status(canvas, "Estender reta: clique exatamente sobre uma reta aberta de construção.")
                return False
            self._alvo = alvo
            self._hover = alvo
            self._preview = QPointF(alvo.ponto_original)
            if hasattr(canvas, "iniciar_operacao_coordenadas"):
                canvas.iniciar_operacao_coordenadas(alvo.ponto_ancora)
            self._status(canvas, "Ponta escolhida. Mova o mouse no sentido da reta e clique para confirmar.")
            canvas.update()
            event.accept()
            return True

        destino = canvas._ponto_com_snap(event.position())
        novo_ponto = self._projetar_destino(
            self._alvo,
            destino,
            permitir_encurtar=bool(event.modifiers() & Qt.ShiftModifier),
        )
        aplicado = self._aplicar_extensao(canvas, self._alvo, novo_ponto)
        if aplicado:
            self._status(canvas, "Reta estendida. Clique em outra reta para continuar ou botão direito para sair.")
        else:
            self._status(canvas, "Estender reta: nenhuma alteração aplicada.")
        if hasattr(canvas, "finalizar_operacao_coordenadas"):
            canvas.finalizar_operacao_coordenadas(novo_ponto)
        self._alvo = None
        self._preview = None
        self._hover = None
        canvas.update()
        event.accept()
        return True

    def desfazer_etapa(self, canvas) -> bool:
        if self._alvo is None and self._hover is None and self._preview is None:
            return False
        self._limpar_estado(canvas)
        self._status(canvas, "Estender reta: etapa atual desfeita.")
        return True

    def origem_coordenadas(self, canvas) -> QPointF:
        if self._alvo is not None:
            return QPointF(self._alvo.ponto_ancora)
        if self._hover is not None:
            return QPointF(self._hover.ponto_ancora)
        return QPointF(0.0, 0.0)

    def on_paint_overlay(self, canvas, painter: QPainter) -> None:
        alvo = self._alvo or self._hover
        if alvo is None:
            return

        p_ancora = QPointF(alvo.ponto_ancora)
        p_original = QPointF(alvo.ponto_original)
        p_preview = QPointF(self._preview) if self._preview is not None else p_original

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        cor_azul = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        if not cor_azul.isValid():
            cor_azul = QColor("#2da8ff")

        pen_base = QPen(cor_azul, 2.2, Qt.SolidLine)
        pen_base.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_base)
        painter.drawLine(canvas._cena_para_tela(p_ancora), canvas._cena_para_tela(p_original))

        if self._alvo is not None:
            pen_preview = QPen(cor_azul.lighter(130), 2.8, Qt.DashLine)
            pen_preview.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_preview)
            painter.drawLine(canvas._cena_para_tela(p_ancora), canvas._cena_para_tela(p_preview))

        self._desenhar_ponto(painter, canvas._cena_para_tela(p_ancora), QColor("#ffffff"), 4.0)
        self._desenhar_ponto(painter, canvas._cena_para_tela(p_original), QColor("#ff3030"), 5.0)
        if self._alvo is not None:
            self._desenhar_ponto(painter, canvas._cena_para_tela(p_preview), QColor("#ff3030"), 5.0)
            self._desenhar_rotulo(canvas, painter, p_preview, "nova ponta")

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

    def _limpar_estado(self, canvas) -> None:
        self._hover = None
        self._alvo = None
        self._preview = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        canvas.update()

    def _reta_mais_proxima(self, canvas, pos: QPointF) -> _AlvoExtensao | None:
        tolerancia = max(8.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001), 0.08)
        melhor: _AlvoExtensao | None = None
        candidatos = sorted(getattr(canvas, "_selecionados", set()) or []) or list(range(len(canvas.cena.elementos)))

        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            elemento = canvas.cena.elementos[idx]
            if not self._elemento_editavel(elemento):
                continue
            pontos = self._pontos_polyline(elemento)
            if len(pontos) < 2:
                continue

            for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
                alvo = self._alvo_para_segmento(idx, seg_idx, pontos, a, b, pos)
                if alvo is None or alvo.distancia > tolerancia:
                    continue
                if melhor is None or alvo.distancia < melhor.distancia:
                    melhor = alvo
        return melhor

    def _alvo_para_segmento(
        self,
        elemento_idx: int,
        segmento_idx: int,
        pontos: list[QPointF],
        a: QPointF,
        b: QPointF,
        pos: QPointF,
    ) -> _AlvoExtensao | None:
        proj, dist = self._projetar_no_segmento(a, b, pos)
        total = len(pontos)

        if total == 2:
            dist_a = self._distancia(pos, a)
            dist_b = self._distancia(pos, b)
            if dist_a <= dist_b:
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

        return _AlvoExtensao(
            elemento_idx=elemento_idx,
            segmento_idx=segmento_idx,
            ponto_movel_idx=movel_idx,
            ponto_ancora_idx=ancora_idx,
            ponto_original=QPointF(movel),
            ponto_ancora=QPointF(ancora),
            ponto_segmento=proj,
            distancia=dist,
        )

    def _aplicar_extensao(self, canvas, alvo: _AlvoExtensao, novo_ponto: QPointF) -> bool:
        if alvo.elemento_idx < 0 or alvo.elemento_idx >= len(canvas.cena.elementos):
            return False
        elemento = canvas.cena.elementos[alvo.elemento_idx]
        if not self._elemento_editavel(elemento):
            return False
        pontos = self._pontos_polyline(elemento)
        if not (0 <= alvo.ponto_movel_idx < len(pontos)):
            return False

        antigo = pontos[alvo.ponto_movel_idx]
        if self._distancia(antigo, novo_ponto) <= 1e-6:
            return False

        pontos[alvo.ponto_movel_idx] = QPointF(novo_ponto)
        elemento["pontos"] = [(float(p.x()), float(p.y())) for p in pontos]
        elemento.setdefault("metadados", {})["ultima_ferramenta"] = self.id_ferramenta
        canvas._selecionados = {alvo.elemento_idx}
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        return True

    def _projetar_destino(self, alvo: _AlvoExtensao, destino: QPointF, permitir_encurtar: bool = False) -> QPointF:
        ax, ay = alvo.ponto_ancora.x(), alvo.ponto_ancora.y()
        ox, oy = alvo.ponto_original.x(), alvo.ponto_original.y()
        vx, vy = ox - ax, oy - ay
        comprimento = sqrt((vx * vx) + (vy * vy))
        if comprimento <= 1e-9:
            return QPointF(alvo.ponto_original)

        ux, uy = vx / comprimento, vy / comprimento
        wx, wy = destino.x() - ax, destino.y() - ay
        t = (wx * ux) + (wy * uy)
        if permitir_encurtar:
            t = max(0.001, t)
        else:
            t = max(comprimento, t)
        return QPointF(ax + (ux * t), ay + (uy * t))

    @staticmethod
    def _elemento_editavel(elemento: dict) -> bool:
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

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
