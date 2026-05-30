from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QDialog

from tools.tool_base import FerramentaBase


@dataclass
class _RetaEscolhida:
    elemento_idx: int
    segmento_idx: int
    a: QPointF
    b: QPointF
    distancia: float


class Ferramenta(FerramentaBase):
    id_ferramenta = "estender_duas_retas"
    nome = "Estender duas retas"
    usa_painel_auxiliar = True
    descricao_painel = (
        "Clique na primeira reta e depois na segunda. "
        "As duas serão ajustadas até a interseção. "
        "Botão direito cancela."
    )
    gerencia_coordenadas_operacao = True

    def __init__(self):
        super().__init__()
        self._primeira: _RetaEscolhida | None = None
        self._hover_primeira: _RetaEscolhida | None = None
        self._hover_segunda: _RetaEscolhida | None = None
        self._preview_intersecao: QPointF | None = None

    def on_activate(self, canvas) -> None:
        self._ocultar_janela_auxiliar_antiga(canvas)
        super().on_activate(canvas)
        self._primeira = None
        self._hover_primeira = None
        self._hover_segunda = None
        self._preview_intersecao = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        self._status(canvas, "Estender duas retas: clique na primeira reta.")
        canvas.update()

    def on_deactivate(self, canvas) -> None:
        self._primeira = None
        self._hover_primeira = None
        self._hover_segunda = None
        self._preview_intersecao = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        super().on_deactivate(canvas)
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._tela_para_cena(event.position())
        if self._primeira is None:
            self._hover_primeira = self._reta_mais_proxima(canvas, pos)
            self._hover_segunda = None
            self._preview_intersecao = None
            canvas.update()
            return False

        self._hover_segunda = self._reta_mais_proxima(canvas, pos, ignorar_idx=self._primeira.elemento_idx)
        self._preview_intersecao = None
        if self._hover_segunda is not None:
            self._preview_intersecao = self._intersecao_linhas(self._primeira.a, self._primeira.b, self._hover_segunda.a, self._hover_segunda.b)
            if self._preview_intersecao is not None and hasattr(canvas, "atualizar_operacao_coordenadas"):
                canvas.atualizar_operacao_coordenadas(self._preview_intersecao)
        canvas.update()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._primeira is not None or self._hover_primeira is not None or self._hover_segunda is not None:
                self._limpar_estado(canvas)
                self._status(canvas, "Estender duas retas: operação cancelada. Clique novamente ou use dois cliques direitos para sair.")
                event.accept()
                return True
            return False

        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._tela_para_cena(event.position())
        if self._primeira is None:
            reta = self._reta_mais_proxima(canvas, pos)
            if reta is None:
                self._status(canvas, "Estender duas retas: clique sobre uma reta aberta de construção.")
                return False
            self._primeira = reta
            self._hover_primeira = reta
            self._hover_segunda = None
            self._preview_intersecao = None
            if hasattr(canvas, "iniciar_operacao_coordenadas"):
                canvas.iniciar_operacao_coordenadas(self._ponto_medio(reta.a, reta.b))
            self._status(canvas, "Primeira reta escolhida. Agora clique na segunda reta.")
            canvas.update()
            event.accept()
            return True

        segunda = self._reta_mais_proxima(canvas, pos, ignorar_idx=self._primeira.elemento_idx)
        if segunda is None:
            self._status(canvas, "Estender duas retas: clique sobre a segunda reta.")
            return False

        intersecao = self._intersecao_linhas(self._primeira.a, self._primeira.b, segunda.a, segunda.b)
        if intersecao is None:
            self._status(canvas, "Estender duas retas: as retas são paralelas e não possuem interseção.")
            return False

        aplicado = self._aplicar_intersecao(canvas, self._primeira, segunda, intersecao)
        if aplicado:
            self._status(canvas, "Duas retas estendidas até a interseção. Nada ficou selecionado.")
        else:
            self._status(canvas, "Estender duas retas: nenhuma alteração aplicada.")
        if hasattr(canvas, "finalizar_operacao_coordenadas"):
            canvas.finalizar_operacao_coordenadas(intersecao)
        self._primeira = None
        self._hover_primeira = None
        self._hover_segunda = None
        self._preview_intersecao = None
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados.clear()
        canvas.update()
        event.accept()
        return True

    def desfazer_etapa(self, canvas) -> bool:
        if self._primeira is None and self._hover_primeira is None and self._hover_segunda is None:
            return False
        self._limpar_estado(canvas)
        self._status(canvas, "Estender duas retas: etapa atual desfeita.")
        return True

    def origem_coordenadas(self, canvas) -> QPointF:
        if self._preview_intersecao is not None:
            return QPointF(self._preview_intersecao)
        if self._primeira is not None:
            return self._ponto_medio(self._primeira.a, self._primeira.b)
        if self._hover_primeira is not None:
            return self._ponto_medio(self._hover_primeira.a, self._hover_primeira.b)
        return QPointF(0.0, 0.0)

    def on_paint_overlay(self, canvas, painter: QPainter) -> None:
        primeira = self._primeira or self._hover_primeira
        if primeira is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        cor_azul = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        if not cor_azul.isValid():
            cor_azul = QColor("#2da8ff")
        cor_laranja = QColor("#ffb000")

        self._desenhar_segmento(canvas, painter, primeira.a, primeira.b, cor_azul, 2.3, Qt.SolidLine)
        self._desenhar_ponto(painter, canvas._cena_para_tela(primeira.a), QColor("#ffffff"), 4.0)
        self._desenhar_ponto(painter, canvas._cena_para_tela(primeira.b), QColor("#ffffff"), 4.0)

        segunda = self._hover_segunda
        if segunda is not None:
            self._desenhar_segmento(canvas, painter, segunda.a, segunda.b, cor_laranja, 2.2, Qt.SolidLine)
            self._desenhar_ponto(painter, canvas._cena_para_tela(segunda.a), QColor("#ffffff"), 4.0)
            self._desenhar_ponto(painter, canvas._cena_para_tela(segunda.b), QColor("#ffffff"), 4.0)

        intersecao = self._preview_intersecao
        if intersecao is not None and self._primeira is not None and segunda is not None:
            p1 = self._endpoint_para_intersecao(canvas, primeira, intersecao)
            p2 = self._endpoint_para_intersecao(canvas, segunda, intersecao)
            if p1 is not None:
                self._desenhar_segmento(canvas, painter, p1, intersecao, cor_azul.lighter(130), 2.5, Qt.DashLine)
            if p2 is not None:
                self._desenhar_segmento(canvas, painter, p2, intersecao, cor_laranja.lighter(120), 2.5, Qt.DashLine)
            self._desenhar_ponto(painter, canvas._cena_para_tela(intersecao), QColor("#ff3030"), 5.0)
            self._desenhar_rotulo(canvas, painter, intersecao, "interseção")

        painter.restore()

    def _limpar_estado(self, canvas) -> None:
        self._primeira = None
        self._hover_primeira = None
        self._hover_segunda = None
        self._preview_intersecao = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        canvas.update()

    def _reta_mais_proxima(self, canvas, pos: QPointF, ignorar_idx: int | None = None) -> _RetaEscolhida | None:
        tolerancia = max(8.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001), 0.08)
        melhor: _RetaEscolhida | None = None
        for idx, elemento in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if ignorar_idx is not None and idx == ignorar_idx:
                continue
            if not self._elemento_reta_editavel(elemento):
                continue
            pontos = self._pontos_polyline(elemento)
            if len(pontos) < 2:
                continue
            for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
                if len(pontos) > 2 and seg_idx not in (0, len(pontos) - 2):
                    continue
                _proj, dist = self._projetar_no_segmento(a, b, pos)
                if dist > tolerancia:
                    continue
                reta = _RetaEscolhida(idx, seg_idx, QPointF(a), QPointF(b), dist)
                if melhor is None or reta.distancia < melhor.distancia:
                    melhor = reta
        return melhor

    def _aplicar_intersecao(self, canvas, primeira: _RetaEscolhida, segunda: _RetaEscolhida, intersecao: QPointF) -> bool:
        alterou = False
        for reta in (primeira, segunda):
            if not (0 <= reta.elemento_idx < len(canvas.cena.elementos)):
                continue
            elemento = canvas.cena.elementos[reta.elemento_idx]
            pontos = self._pontos_polyline(elemento)
            idx_movel = self._indice_endpoint_para_intersecao(pontos, reta.segmento_idx, intersecao)
            if idx_movel is None or not (0 <= idx_movel < len(pontos)):
                continue
            if self._distancia(pontos[idx_movel], intersecao) <= 1e-6:
                continue
            pontos[idx_movel] = QPointF(intersecao)
            elemento["pontos"] = [(float(p.x()), float(p.y())) for p in pontos]
            elemento.setdefault("metadados", {})["ultima_ferramenta"] = self.id_ferramenta
            alterou = True
        if alterou:
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
            if hasattr(canvas, "_selecionados"):
                canvas._selecionados.clear()
        return alterou

    def _endpoint_para_intersecao(self, canvas, reta: _RetaEscolhida, intersecao: QPointF) -> QPointF | None:
        if not (0 <= reta.elemento_idx < len(canvas.cena.elementos)):
            return None
        pontos = self._pontos_polyline(canvas.cena.elementos[reta.elemento_idx])
        idx = self._indice_endpoint_para_intersecao(pontos, reta.segmento_idx, intersecao)
        if idx is None or not (0 <= idx < len(pontos)):
            return None
        return QPointF(pontos[idx])

    def _indice_endpoint_para_intersecao(self, pontos: list[QPointF], segmento_idx: int, intersecao: QPointF) -> int | None:
        if len(pontos) < 2:
            return None
        if len(pontos) == 2:
            d0 = self._distancia(pontos[0], intersecao)
            d1 = self._distancia(pontos[1], intersecao)
            return 0 if d0 <= d1 else 1
        if segmento_idx == 0:
            return 0
        if segmento_idx == len(pontos) - 2:
            return len(pontos) - 1
        return None

    @staticmethod
    def _intersecao_linhas(a1: QPointF, b1: QPointF, a2: QPointF, b2: QPointF) -> QPointF | None:
        x1, y1 = a1.x(), a1.y()
        x2, y2 = b1.x(), b1.y()
        x3, y3 = a2.x(), a2.y()
        x4, y4 = b2.x(), b2.y()
        den = ((x1 - x2) * (y3 - y4)) - ((y1 - y2) * (x3 - x4))
        if abs(den) <= 1e-9:
            return None
        px = (((x1 * y2) - (y1 * x2)) * (x3 - x4) - (x1 - x2) * ((x3 * y4) - (y3 * x4))) / den
        py = (((x1 * y2) - (y1 * x2)) * (y3 - y4) - (y1 - y2) * ((x3 * y4) - (y3 * x4))) / den
        return QPointF(px, py)

    @staticmethod
    def _elemento_reta_editavel(elemento: dict) -> bool:
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
    def _ponto_medio(a: QPointF, b: QPointF) -> QPointF:
        return QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)

    @staticmethod
    def _distancia(a: QPointF, b: QPointF) -> float:
        return sqrt(((a.x() - b.x()) ** 2) + ((a.y() - b.y()) ** 2))

    @staticmethod
    def _desenhar_segmento(canvas, painter: QPainter, a: QPointF, b: QPointF, cor: QColor, espessura: float, estilo) -> None:
        pen = QPen(cor, espessura, estilo)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))

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
            vistos: set[int] = set()
            for dialogo in dialogos:
                if id(dialogo) in vistos:
                    continue
                vistos.add(id(dialogo))
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
