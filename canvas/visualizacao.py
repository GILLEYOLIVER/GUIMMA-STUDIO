from __future__ import annotations

from copy import deepcopy

from math import atan2, cos, degrees, radians, sin, sqrt

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget

from canvas.cena import CenaDocumento
from canvas.snap import SnapManager, SnapResult
from core.line_styles import dash_pattern_for_line, is_geometric_line_style, pen_style_for_line


class PainelCoordenadas(QFrame):
    desfazer_ponto = Signal()
    aplicar = Signal(dict)
    alternado = Signal(bool)
    posicao_alterada = Signal(int, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PainelCoordenadas")
        self.setFixedSize(300, 120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(4)

        titulo = QLabel("(cm) Coordenadas")
        titulo.setStyleSheet("font-size: 10px; color: #7c7c7c;")
        topo.addWidget(titulo, 1)
        btn_fechar = QPushButton("✕")
        btn_fechar.setFixedSize(16, 16)
        btn_fechar.clicked.connect(lambda: self._alternar_visibilidade(False))
        topo.addWidget(btn_fechar, 0, Qt.AlignRight)
        layout.addLayout(topo)

        grade = QGridLayout()
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setHorizontalSpacing(6)
        grade.setVerticalSpacing(2)
        self.dx_input = QLineEdit()
        self.dy_input = QLineEdit()
        self.a_input = QLineEdit()
        self.d_input = QLineEdit()
        for field in (self.dx_input, self.dy_input, self.a_input, self.d_input):
            field.setFixedHeight(20)
            field.setStyleSheet("background:#f2f2f2; border:1px solid #a2a2a2;")
        self.dx_preview = QLabel("0")
        self.dy_preview = QLabel("0")
        self.a_preview = QLabel("0°")
        self.d_preview = QLabel("0")
        for lbl in (self.dx_preview, self.dy_preview, self.a_preview, self.d_preview):
            lbl.setStyleSheet("font-size:10px; color:#7c7c7c;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grade.addWidget(QLabel("Dx:"), 0, 0)
        grade.addWidget(self.dx_input, 0, 1)
        grade.addWidget(self.dx_preview, 0, 2)
        grade.addWidget(QLabel("Ângulo:"), 0, 3)
        grade.addWidget(self.a_input, 0, 4)
        grade.addWidget(self.a_preview, 0, 5)
        grade.addWidget(QLabel("Dy:"), 1, 0)
        grade.addWidget(self.dy_input, 1, 1)
        grade.addWidget(self.dy_preview, 1, 2)
        grade.addWidget(QLabel("Distância:"), 1, 3)
        grade.addWidget(self.d_input, 1, 4)
        grade.addWidget(self.d_preview, 1, 5)
        layout.addLayout(grade)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        botao_desfazer = QPushButton("Desfaz ponto")
        botao_desfazer.setFixedHeight(22)
        botao_desfazer.clicked.connect(self.desfazer_ponto.emit)
        row.addWidget(botao_desfazer)
        botao_limpar = QPushButton("Limpar")
        botao_limpar.setFixedHeight(22)
        botao_limpar.clicked.connect(self._limpar)
        row.addWidget(botao_limpar)
        botao_aplicar = QPushButton("Aplicar")
        botao_aplicar.setFixedHeight(22)
        botao_aplicar.clicked.connect(self._emitir_aplicar)
        row.addWidget(botao_aplicar)
        layout.addLayout(row)
        self._offset_arraste: QPointF | None = None

        self.setStyleSheet(
            """
            QFrame#PainelCoordenadas {
                background: #ebebeb;
                border: 1px solid #9a9a9a;
                border-radius: 8px;
                color: #1f1f1f;
            }
            QPushButton {
                background: #f6f6f6;
                border: 1px solid #9b9b9b;
                font-size: 10px;
                font-weight: 600;
                color: #111111;
            }
            QPushButton:hover { background: #ffffff; }
            QLabel { color: #1f1f1f; }
            QLineEdit { color: #1a1a1a; selection-background-color: #0b8dd1; }
            """
        )

    def _alternar_visibilidade(self, visivel: bool):
        if visivel:
            self.show()
        else:
            self.hide()
        self.alternado.emit(visivel)

    def definir_visivel(self, visivel: bool):
        self._alternar_visibilidade(visivel)

    def _limpar(self):
        for field in (self.dx_input, self.dy_input, self.a_input, self.d_input):
            field.clear()

    def _parse(self, txt: str) -> float | None:
        txt = txt.strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            return None

    def _emitir_aplicar(self):
        self.aplicar.emit(
            {
                "dx": self._parse(self.dx_input.text()),
                "dy": self._parse(self.dy_input.text()),
                "a": self._parse(self.a_input.text()),
                "d": self._parse(self.d_input.text()),
            }
        )

    def atualizar_preview(self, origem: QPointF | None, destino: QPointF | None):
        if not origem or not destino:
            self.dx_preview.setText("0")
            self.dy_preview.setText("0")
            self.a_preview.setText("0°")
            self.d_preview.setText("0")
            return
        dx = destino.x() - origem.x()
        dy = destino.y() - origem.y()
        ang = degrees(atan2(-dy, dx)) % 360.0
        dist = sqrt(dx * dx + dy * dy)
        self.dx_preview.setText(f"{dx:.2f}")
        self.dy_preview.setText(f"{dy:.2f}")
        self.a_preview.setText(f"{ang:.0f}°")
        self.d_preview.setText(f"{dist:.2f}")

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._offset_arraste = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._offset_arraste is not None and event.buttons() & Qt.LeftButton:
            destino = self.mapToParent(event.position().toPoint() - self._offset_arraste.toPoint())
            self.move(destino)
            self.posicao_alterada.emit(self.x(), self.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._offset_arraste = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class VisualizacaoCanvas(QWidget):
    zoom_changed = Signal(float)
    ferramenta_padrao_solicitada = Signal(str)
    snap_changed = Signal(bool)
    painel_coordenadas_changed = Signal(bool)
    painel_posicao_changed = Signal(int, int)

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.cena = cena
        self.zoom = 1.0
        self.origem_cena = QPointF(0.0, 0.0)
        self.ferramenta_ativa: str | None = None
        self._pontos_reta: list[QPointF] = []
        self._preview_reta: QPointF | None = None
        self._marcacoes_temporarias: list[QPointF] = []
        self._ponto_coordenada_aplicada: QPointF | None = None
        self._cursor_tela = QPointF(0.0, 0.0)
        self._historico_elementos: list[list[dict]] = [[]]
        self._indice_historico = 0
        self._buffer_copia: dict | None = None
        self._offset_colagem = 0
        self._selecionados: set[int] = set()
        self._inicio_selecao: QPointF | None = None
        self._fim_selecao: QPointF | None = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto: QPointF | None = None
        self._moveu_selecao = False
        self._painel_coordenadas_posicao: tuple[int, int] | None = None
        self._painel_coordenadas_visivel = True
        self._aguardando_retorno_selecao = False
        self._cliques_direito_reta = 0
        self._snap_manager = SnapManager()
        self._snap_ativo = True
        self._snap_resultado: SnapResult | None = None
        self._snap_candidatos: list[SnapResult] = []
        self._snap_indice = 0
        self._guia_fechamento: tuple[QPointF, QPointF] | None = None
        self._guias_alinhamento: list[tuple[QPointF, QPointF]] = []
        self._linha_cor = "#ff5a00"
        self._linha_estilo = "solid"
        self._linha_espessura = 1.0
        self._linha_amplitude = 1.0
        self._snap_angular_passo = 45.0
        self._snap_contextual_ativo = True
        self._tecla_w_trava_principal = False
        self._extensao_origem: tuple[int, bool] | None = None
        self._segmento_primeira_reta: tuple[int, int] | None = None
        self._curva_estado = "parada"
        self._curva_p0: QPointF | None = None
        self._curva_p2: QPointF | None = None
        self._curva_p1: QPointF | None = None
        self._curva_preview_fim: QPointF | None = None
        self._curva_pmedio: QPointF | None = None
        self._modo_curva = "2p"
        self._cliques_direito_curva = 0
        self._arrastando_alca_curva: tuple[int, str] | None = None

        self.setMinimumSize(100, 100)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.painel_coordenadas = PainelCoordenadas(self)
        self.painel_coordenadas.desfazer_ponto.connect(self._desfazer_ponto)
        self.painel_coordenadas.aplicar.connect(self._aplicar_coordenadas)
        self.painel_coordenadas.alternado.connect(self._set_painel_coordenadas_visivel)
        self.painel_coordenadas.posicao_alterada.connect(self._registrar_posicao_painel)
        self.painel_coordenadas.show()

    def set_zoom(self, zoom: float):
        # Faixa operacional de zoom: 0.025x (2,500%) até 5000.000x
        self.zoom = max(0.025, min(zoom, 5000.0))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def set_ferramenta_ativa(self, tool_id: str):
        self.ferramenta_ativa = tool_id
        self._aguardando_retorno_selecao = False
        self._cliques_direito_reta = 0
        self._snap_resultado = None
        self._snap_candidatos = []
        self._snap_indice = 0
        if tool_id in {"reta", "curva"}:
            if self._painel_coordenadas_visivel:
                self.painel_coordenadas.show()
            self._reposicionar_painel_coordenadas()
            if tool_id == "curva":
                self._pontos_reta.clear()
                self._preview_reta = None
                self._guia_fechamento = None
                self._guias_alinhamento = []
                self._cliques_direito_curva = 0
        else:
            self._pontos_reta.clear()
            self._preview_reta = None
            self._guia_fechamento = None
            self._guias_alinhamento = []
        if tool_id != "curva":
            self._resetar_estado_curva()
        if tool_id not in {"estender_reta", "estender_ate_elemento"}:
            self._extensao_origem = None
        if tool_id != "estender_duas_retas":
            self._segmento_primeira_reta = None
        self.update()

    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        cursor_tela = event.position()
        cursor_cena_antes = self._tela_para_cena(cursor_tela)
        delta = event.angleDelta().y()
        fator = 1.1 if delta > 0 else 0.9
        self.set_zoom(self.zoom * fator)
        self.origem_cena = QPointF(
            cursor_cena_antes.x() - (cursor_tela.x() / self.zoom),
            cursor_cena_antes.y() - (cursor_tela.y() / self.zoom),
        )
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if self.ferramenta_ativa == "curva":
            self._mouse_press_curva(event)
            return
        if self.ferramenta_ativa == "dividir_curva" and event.button() == Qt.LeftButton:
            self._dividir_segmento_em_clique(self._ponto_com_snap(event.position()))
            event.accept()
            return
        if self.ferramenta_ativa in {"estender_reta", "estender_ate_elemento"} and event.button() == Qt.LeftButton:
            self._processar_estender_reta(self._ponto_com_snap(event.position()), ate_elemento=self.ferramenta_ativa == "estender_ate_elemento")
            event.accept()
            return
        if self.ferramenta_ativa == "estender_duas_retas" and event.button() == Qt.LeftButton:
            self._processar_estender_duas_retas(self._ponto_com_snap(event.position()))
            event.accept()
            return
        if self.ferramenta_ativa not in {"reta", "curva"}:
            if event.button() == Qt.LeftButton:
                pos = self._ponto_com_snap(event.position())
                alca = self._alca_curva_em_ponto(pos)
                if alca is not None:
                    self._arrastando_alca_curva = alca
                    event.accept()
                    return
                idx = self._indice_elemento_em_ponto(pos)
                if idx is not None and idx in self._selecionados:
                    self._arrastando_selecao = True
                    self._ultimo_ponto_arrasto = pos
                    self._moveu_selecao = False
                    event.accept()
                    return
                self._arrastando_selecao = False
                self._inicio_selecao = pos
                self._fim_selecao = pos
                self._ultimo_ponto_arrasto = None
                self.update()
                event.accept()
                return
            if event.button() == Qt.RightButton:
                self._abrir_menu_contexto(event.globalPosition().toPoint())
                event.accept()
                return
            return super().mousePressEvent(event)

        pos = self._ponto_com_snap(event.position())
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self._aguardando_retorno_selecao = False
            self._cliques_direito_reta = 0
            if not self._pontos_reta:
                self._pontos_reta.append(pos)
            else:
                pos = self._snap_angular(
                    self._pontos_reta[-1],
                    pos,
                    travar_snap_exato=self._snap_resultado is not None,
                    travar_principais=self._tecla_w_trava_principal,
                )
                pos = self._aplicar_guia_fechamento(self._pontos_reta[-1], pos)
                pos = self._aplicar_guias_alinhamento(self._pontos_reta[-1], pos)
                self._pontos_reta.append(pos)
            self._preview_reta = pos
            if len(self._pontos_reta) >= 2:
                self.painel_coordenadas.atualizar_preview(self._pontos_reta[-2], self._pontos_reta[-1])
            self.update()
            event.accept()
            return

        if event.button() == Qt.RightButton:
            if self._cliques_direito_reta >= 2:
                self._pontos_reta.clear()
                self._preview_reta = None
                self._guia_fechamento = None
                self._guias_alinhamento = []
                self._aguardando_retorno_selecao = False
                self._cliques_direito_reta = 0
                self.ferramenta_padrao_solicitada.emit("selecionar")
                self.update()
                event.accept()
                return
            if self._cliques_direito_reta >= 1:
                self._pontos_reta.clear()
                self._preview_reta = None
                self._guia_fechamento = None
                self._guias_alinhamento = []
                self._aguardando_retorno_selecao = False
                self._cliques_direito_reta = 2
                self.update()
                event.accept()
                return
            self._finalizar_reta_atual()
            self._cliques_direito_reta = 1
            self.update()
            event.accept()
            return

        super().mousePressEvent(event)

    def _mouse_press_curva(self, event: QMouseEvent):
        pos = self._ponto_com_snap(event.position())
        if event.button() == Qt.RightButton:
            if self._cliques_direito_curva >= 2:
                self._resetar_estado_curva()
                self._cliques_direito_curva = 0
                self.ferramenta_padrao_solicitada.emit("selecionar")
                self.update()
                event.accept()
                return
            if self._cliques_direito_curva >= 1:
                self._resetar_estado_curva()
                self._cliques_direito_curva = 2
                self.update()
                event.accept()
                return
            if self._curva_pronta_para_finalizar():
                self._finalizar_curva()
            else:
                self._resetar_estado_curva()
            self._cliques_direito_curva = 1
            self.update()
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._cliques_direito_curva = 0
        if self._modo_curva == "3p":
            if self._curva_estado in {"parada", "aguardando_inicial"}:
                self._curva_p0 = pos
                self._curva_pmedio = None
                self._curva_p2 = None
                self._curva_p1 = None
                self._curva_preview_fim = None
                self._curva_estado = "aguardando_ponto2"
            elif self._curva_estado == "aguardando_ponto2":
                self._curva_pmedio = pos
                self._curva_estado = "aguardando_ponto3"
            elif self._curva_estado == "aguardando_ponto3":
                self._curva_p2 = pos
                self._curva_p1 = self._controle_para_tres_pontos(self._curva_p0, self._curva_pmedio, self._curva_p2)
                self._finalizar_curva()
            self.update()
            event.accept()
            return
        if self._curva_estado in {"parada", "aguardando_inicial"}:
            self._curva_p0 = pos
            self._curva_p2 = None
            self._curva_p1 = None
            self._curva_preview_fim = None
            self._curva_estado = "aguardando_final"
        elif self._curva_estado == "aguardando_final":
            self._curva_p2 = pos
            self._curva_p1 = QPointF((self._curva_p0.x() + self._curva_p2.x()) / 2.0, (self._curva_p0.y() + self._curva_p2.y()) / 2.0)
            self._curva_estado = "aguardando_controle"
        elif self._curva_estado == "aguardando_controle":
            self._curva_p1 = pos
            self._finalizar_curva()
        self.update()
        event.accept()

    def _resetar_estado_curva(self):
        self._curva_estado = "parada"
        self._curva_p0 = None
        self._curva_p2 = None
        self._curva_p1 = None
        self._curva_preview_fim = None
        self._curva_pmedio = None

    def _curva_pronta_para_finalizar(self) -> bool:
        if self._modo_curva == "3p":
            return bool(self._curva_p0 and self._curva_pmedio and self._curva_p2)
        return bool(self._curva_p0 and self._curva_p1 and self._curva_p2)

    def _controle_para_tres_pontos(self, p0: QPointF, pm: QPointF, p2: QPointF) -> QPointF:
        return QPointF((2.0 * pm.x()) - ((p0.x() + p2.x()) / 2.0), (2.0 * pm.y()) - ((p0.y() + p2.y()) / 2.0))

    def _dividir_segmento_em_clique(self, pos: QPointF):
        info = self._segmento_mais_proximo(pos)
        if not info:
            return
        idx, seg_idx, a, b, _ = info
        el = self.cena.elementos[idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pontos) < 2:
            return
        proj = self._projecao_em_segmento(pos, a, b)
        pontos.insert(seg_idx + 1, proj)
        el["pontos"] = [(p.x(), p.y()) for p in pontos]
        self._registrar_historico()
        self.update()

    def _processar_estender_reta(self, pos: QPointF, ate_elemento: bool = False):
        if self._extensao_origem is None:
            self._extensao_origem = self._endpoint_proximo(pos)
            return
        idx, inicio = self._extensao_origem
        self._extensao_origem = None
        el = self.cena.elementos[idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pontos) < 2:
            return
        i = 0 if inicio else len(pontos) - 1
        vizinho = pontos[1] if inicio else pontos[-2]
        novo_ponto = pos
        if ate_elemento:
            alvo = self._segmento_mais_proximo(pos)
            if alvo:
                _, _, a2, b2, _ = alvo
                inter = self._intersecao_linhas(vizinho, pontos[i], a2, b2)
                if inter is not None:
                    novo_ponto = inter
        pontos[i] = novo_ponto
        el["pontos"] = [(p.x(), p.y()) for p in pontos]
        self._registrar_historico()
        self.update()

    def _processar_estender_duas_retas(self, pos: QPointF):
        seg = self._segmento_mais_proximo(pos)
        if not seg:
            return
        idx, seg_idx, a, b, _ = seg
        if self._segmento_primeira_reta is None:
            self._segmento_primeira_reta = (idx, seg_idx)
            return
        idx1, seg1 = self._segmento_primeira_reta
        self._segmento_primeira_reta = None
        if idx1 == idx and seg1 == seg_idx:
            return
        dados1 = self._dados_segmento(idx1, seg1)
        dados2 = self._dados_segmento(idx, seg_idx)
        if not dados1 or not dados2:
            return
        a1, b1 = dados1
        a2, b2 = dados2
        inter = self._intersecao_linhas(a1, b1, a2, b2)
        if inter is None:
            return
        self._mover_ponto_segmento_para_intersecao(idx1, seg1, inter)
        self._mover_ponto_segmento_para_intersecao(idx, seg_idx, inter)
        self._registrar_historico()
        self.update()

    def _mover_ponto_segmento_para_intersecao(self, idx: int, seg_idx: int, inter: QPointF):
        el = self.cena.elementos[idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if seg_idx < 0 or seg_idx + 1 >= len(pontos):
            return
        i1, i2 = seg_idx, seg_idx + 1
        d1 = self._dist(pontos[i1], inter)
        d2 = self._dist(pontos[i2], inter)
        pontos[i1 if d1 <= d2 else i2] = inter
        el["pontos"] = [(p.x(), p.y()) for p in pontos]

    def _endpoint_proximo(self, pos: QPointF) -> tuple[int, bool] | None:
        tol = self._tolerancia_snap_px() / max(self.zoom, 0.001)
        melhor: tuple[int, bool] | None = None
        dist_melhor = float("inf")
        for idx, el in enumerate(self.cena.elementos):
            if el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 2:
                continue
            for inicio, ponto in ((True, pontos[0]), (False, pontos[-1])):
                d = self._dist(ponto, pos)
                if d < dist_melhor and d <= tol:
                    dist_melhor = d
                    melhor = (idx, inicio)
        return melhor

    def _segmento_mais_proximo(self, pos: QPointF) -> tuple[int, int, QPointF, QPointF, float] | None:
        tol = (self._tolerancia_snap_px() / max(self.zoom, 0.001)) * 1.2
        melhor: tuple[int, int, QPointF, QPointF, float] | None = None
        for idx, el in enumerate(self.cena.elementos):
            if el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
                proj = self._projecao_em_segmento(pos, a, b)
                d = self._dist(pos, proj)
                if d <= tol and (melhor is None or d < melhor[4]):
                    melhor = (idx, seg_idx, a, b, d)
        return melhor

    def _dados_segmento(self, idx: int, seg_idx: int) -> tuple[QPointF, QPointF] | None:
        if idx < 0 or idx >= len(self.cena.elementos):
            return None
        el = self.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return None
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if seg_idx < 0 or seg_idx + 1 >= len(pontos):
            return None
        return pontos[seg_idx], pontos[seg_idx + 1]

    def _projecao_em_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> QPointF:
        abx, aby = b.x() - a.x(), b.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 0.0000001:
            return QPointF(a)
        apx, apy = p.x() - a.x(), p.y() - a.y()
        t = ((apx * abx) + (apy * aby)) / denom
        t = max(0.0, min(1.0, t))
        return QPointF(a.x() + (abx * t), a.y() + (aby * t))

    def _intersecao_linhas(self, a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF) -> QPointF | None:
        x1, y1 = a1.x(), a1.y()
        x2, y2 = a2.x(), a2.y()
        x3, y3 = b1.x(), b1.y()
        x4, y4 = b2.x(), b2.y()
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) <= 0.0000001:
            return None
        px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
        py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
        return QPointF(px, py)

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

    def _finalizar_curva(self):
        if not (self._curva_p0 and self._curva_p1 and self._curva_p2):
            return
        self.cena.elementos.append(
            {
                "tipo": "bezier_quadratica",
                "p0": (self._curva_p0.x(), self._curva_p0.y()),
                "p1": (self._curva_p1.x(), self._curva_p1.y()),
                "p2": (self._curva_p2.x(), self._curva_p2.y()),
                "cor": self._linha_cor,
                "espessura": self._linha_espessura,
                "estilo": self._linha_estilo,
                "amplitude": self._linha_amplitude,
            }
        )
        self._selecionados = {len(self.cena.elementos) - 1}
        self._registrar_historico()
        self._resetar_estado_curva()

    def _atualizar_alca_curva(self, idx: int, alca: str, pos: QPointF):
        if idx < 0 or idx >= len(self.cena.elementos):
            return
        el = self.cena.elementos[idx]
        if el.get("tipo") != "bezier_quadratica":
            return
        if alca not in {"p0", "p1", "p2"}:
            return
        el[alca] = (pos.x(), pos.y())

    def mouseMoveEvent(self, event: QMouseEvent):  # noqa: N802
        self._cursor_tela = event.position()
        if self.ferramenta_ativa == "curva":
            pos = self._ponto_com_snap(event.position())
            if self._curva_estado == "aguardando_final":
                self._curva_preview_fim = pos
            elif self._curva_estado == "aguardando_controle":
                self._curva_p1 = pos
            elif self._curva_estado == "aguardando_ponto3" and self._curva_p0 and self._curva_pmedio:
                self._curva_preview_fim = pos
                self._curva_p2 = pos
                self._curva_p1 = self._controle_para_tres_pontos(self._curva_p0, self._curva_pmedio, self._curva_p2)
            self.update()
            event.accept()
            return
        if self.ferramenta_ativa == "reta":
            snap_pos = self._ponto_com_snap(event.position())
            if self._pontos_reta:
                self._preview_reta = self._snap_angular(
                    self._pontos_reta[-1],
                    snap_pos,
                    travar_snap_exato=self._snap_resultado is not None,
                    travar_principais=self._tecla_w_trava_principal,
                )
                self._preview_reta = self._aplicar_guia_fechamento(self._pontos_reta[-1], self._preview_reta)
                self._preview_reta = self._aplicar_guias_alinhamento(self._pontos_reta[-1], self._preview_reta)
                self.painel_coordenadas.atualizar_preview(self._pontos_reta[-1], self._preview_reta)
            else:
                self._guia_fechamento = None
                self._guias_alinhamento = []
            self.update()
            event.accept()
            return
        if self.ferramenta_ativa not in {"reta", "curva"}:
            pos = self._ponto_com_snap(event.position())
            if self._arrastando_alca_curva:
                idx, alca = self._arrastando_alca_curva
                self._atualizar_alca_curva(idx, alca, pos)
                self.update()
                event.accept()
                return
            if self._arrastando_selecao and self._ultimo_ponto_arrasto and self._selecionados:
                delta_x = pos.x() - self._ultimo_ponto_arrasto.x()
                delta_y = pos.y() - self._ultimo_ponto_arrasto.y()
                self._mover_selecionados(delta_x, delta_y)
                self._ultimo_ponto_arrasto = pos
                self._moveu_selecao = True
                self.update()
                event.accept()
                return
            if self._inicio_selecao:
                self._fim_selecao = pos
                self.update()
                event.accept()
                return
            # Em modo seleção, o snap precisa continuar visível/ativo também em hover.
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() == Qt.LeftButton and self._arrastando_alca_curva:
            self._arrastando_alca_curva = None
            self._registrar_historico()
            self.update()
            event.accept()
            return
        if self.ferramenta_ativa in {"reta", "curva"}:
            return super().mouseReleaseEvent(event)
        if event.button() != Qt.LeftButton:
            return super().mouseReleaseEvent(event)

        if self._arrastando_selecao:
            self._arrastando_selecao = False
            self._ultimo_ponto_arrasto = None
            if self._moveu_selecao:
                self._registrar_historico()
            self._moveu_selecao = False
            event.accept()
            return

        if self._inicio_selecao and self._fim_selecao:
            self._atualizar_selecao_por_caixa(self._inicio_selecao, self._fim_selecao)
        self._inicio_selecao = None
        self._fim_selecao = None
        self.update()
        event.accept()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._reposicionar_painel_coordenadas()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        painter.setRenderHint(QPainter.Antialiasing)

        for idx, elemento in enumerate(self.cena.elementos):
            cor = "#ffd54a" if idx in self._selecionados else elemento.get("cor", "#d0d0d0")
            if elemento.get("tipo") == "polyline":
                pontos = [QPointF(x, y) for x, y in elemento.get("pontos", [])]
                if len(pontos) < 2:
                    continue
                self._desenhar_polilinha(
                    painter,
                    pontos,
                    cor=cor,
                    espessura=float(elemento.get("espessura", 1.0)),
                    estilo=str(elemento.get("estilo", "solid")),
                    amplitude=float(elemento.get("amplitude", 1.0)),
                    fase_inicial=float(elemento.get("fase_inicio", 0.0)),
                )
            elif elemento.get("tipo") == "bezier_quadratica":
                self._desenhar_bezier_quadratica(
                    painter,
                    QPointF(*elemento["p0"]),
                    QPointF(*elemento["p1"]),
                    QPointF(*elemento["p2"]),
                    cor=cor,
                    espessura=float(elemento.get("espessura", 1.0)),
                    estilo=str(elemento.get("estilo", "solid")),
                    amplitude=float(elemento.get("amplitude", 1.0)),
                    destacar_controles=(idx in self._selecionados),
                )

        if self._pontos_reta:
            if self._preview_reta and self._preview_reta != self._pontos_reta[-1]:
                self._desenhar_guia_angular(painter, self._pontos_reta[-1], self._preview_reta)
            self._desenhar_polilinha(
                painter,
                self._pontos_reta,
                cor=self._linha_cor,
                espessura=self._linha_espessura,
                estilo=self._linha_estilo,
                amplitude=self._linha_amplitude,
            )
            if self._preview_reta and self._preview_reta != self._pontos_reta[-1]:
                self._desenhar_segmento(
                    painter,
                    self._pontos_reta[-1],
                    self._preview_reta,
                    tracejado=False,
                    cor=self._linha_cor,
                    espessura=self._linha_espessura,
                    estilo=self._linha_estilo,
                    amplitude=self._linha_amplitude,
                )
        if self._guia_fechamento:
            self._desenhar_segmento(
                painter,
                self._guia_fechamento[0],
                self._guia_fechamento[1],
                tracejado=True,
                cor="#ff43ff",
            )
        for inicio, fim in self._guias_alinhamento:
            self._desenhar_segmento(painter, inicio, fim, tracejado=True, cor="#5bd3ff")
        for marca in self._marcacoes_temporarias[-10:]:
            self._desenhar_marca_x(painter, marca)
        if self._pontos_reta and self._preview_reta:
            self._desenhar_label_angulo_cursor(painter, self._pontos_reta[-1], self._preview_reta)
        if self._inicio_selecao and self._fim_selecao:
            self._desenhar_caixa_selecao(painter, self._inicio_selecao, self._fim_selecao)
        if self._snap_resultado:
            self._desenhar_marcador_snap(painter, self._snap_resultado)
        self._desenhar_preview_curva(painter)

    def _desenhar_preview_curva(self, painter: QPainter):
        if self.ferramenta_ativa != "curva":
            return
        if self._curva_p0:
            self._desenhar_marca_x(painter, self._curva_p0, cor="#55e3ff")
        fim = self._curva_p2 or self._curva_preview_fim
        if self._curva_p0 and fim:
            self._desenhar_segmento(painter, self._curva_p0, fim, tracejado=True, cor="#4e92ff")
            self._desenhar_marca_x(painter, fim, cor="#55e3ff")
        if self._curva_p0 and self._curva_p1 and self._curva_p2:
            self._desenhar_bezier_quadratica(
                painter,
                self._curva_p0,
                self._curva_p1,
                self._curva_p2,
                cor=self._linha_cor,
                espessura=self._linha_espessura,
                estilo=self._linha_estilo,
                amplitude=self._linha_amplitude,
                destacar_controles=True,
            )
        if self._modo_curva == "3p" and self._curva_pmedio:
            self._desenhar_marca_x(painter, self._curva_pmedio, cor="#a8ff7d")

    def _desenhar_polilinha(
        self,
        painter: QPainter,
        pontos: list[QPointF],
        cor: str = "#ff5a00",
        espessura: float = 1.0,
        estilo: str = "solid",
        amplitude: float = 1.0,
        fase_inicial: float = 0.0,
    ):
        fase = fase_inicial
        for inicio, fim in zip(pontos, pontos[1:]):
            fase = self._desenhar_segmento(
                painter, inicio, fim, cor=cor, espessura=espessura, estilo=estilo, amplitude=amplitude, fase=fase
            )

    def _desenhar_bezier_quadratica(
        self,
        painter: QPainter,
        p0: QPointF,
        p1: QPointF,
        p2: QPointF,
        cor: str,
        espessura: float,
        estilo: str,
        amplitude: float,
        destacar_controles: bool = False,
    ):
        pontos = self._amostrar_bezier_quadratica(p0, p1, p2, segmentos=42)
        self._desenhar_polilinha(painter, pontos, cor=cor, espessura=espessura, estilo=estilo, amplitude=amplitude)
        if not destacar_controles:
            return
        self._desenhar_segmento(painter, p0, p1, tracejado=True, cor="#6fa8ff")
        self._desenhar_segmento(painter, p1, p2, tracejado=True, cor="#6fa8ff")
        self._desenhar_marca_x(painter, p0, cor="#7dffb3")
        self._desenhar_marca_x(painter, p1, cor="#ff7dd1")
        self._desenhar_marca_x(painter, p2, cor="#7dffb3")

    def _amostrar_bezier_quadratica(self, p0: QPointF, p1: QPointF, p2: QPointF, segmentos: int = 36) -> list[QPointF]:
        pontos: list[QPointF] = []
        n = max(8, int(segmentos))
        for i in range(n + 1):
            t = i / n
            u = 1.0 - t
            x = (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x())
            y = (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y())
            pontos.append(QPointF(x, y))
        return pontos

    def _desenhar_segmento(
        self,
        painter: QPainter,
        inicio: QPointF,
        fim: QPointF,
        tracejado: bool = False,
        cor: str = "#ff5a00",
        espessura: float = 1.0,
        estilo: str = "solid",
        amplitude: float = 1.0,
        fase: float = 0.0,
    ) -> float:
        comprimento = sqrt((fim.x() - inicio.x()) ** 2 + (fim.y() - inicio.y()) ** 2)
        if not tracejado and is_geometric_line_style(estilo):
            self._desenhar_segmento_geometrico(
                painter,
                inicio,
                fim,
                cor=cor,
                espessura=espessura,
                estilo=estilo,
                amplitude=max(0.2, float(amplitude)),
                fase=fase,
            )
            return fase + comprimento
        pen = QPen(QColor(cor), espessura)
        if tracejado:
            pen.setStyle(Qt.DotLine)
        else:
            self._aplicar_estilo_caneta(pen, estilo)
        painter.setPen(pen)
        painter.drawLine(self._cena_para_tela(inicio), self._cena_para_tela(fim))
        return fase + comprimento

    def _desenhar_segmento_geometrico(
        self,
        painter: QPainter,
        inicio: QPointF,
        fim: QPointF,
        cor: str,
        espessura: float,
        estilo: str,
        amplitude: float,
        fase: float,
    ):
        # Gera a forma em coordenadas de cena para que o padrão acompanhe o zoom
        # do desenho (sem deformar por depender de pixels de tela).
        p1 = QPointF(inicio)
        p2 = QPointF(fim)
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        comprimento = sqrt(dx * dx + dy * dy)
        if comprimento <= 0.001:
            return

        ux = dx / comprimento
        uy = dy / comprimento
        nx = -uy
        ny = ux
        amp = max(0.2, comprimento * 0.02) * amplitude
        passo = max(0.8, comprimento * 0.08)
        modo = "zigzag"
        if estilo == "zigzag_strong":
            amp, passo, modo = max(0.3, comprimento * 0.03) * amplitude, max(1.0, comprimento * 0.10), "zigzag"
        elif estilo == "wave_soft":
            amp, passo, modo = max(0.18, comprimento * 0.018) * amplitude, max(0.9, comprimento * 0.09), "wave"
        elif estilo == "wave_strong":
            amp, passo, modo = max(0.3, comprimento * 0.03) * amplitude, max(1.1, comprimento * 0.11), "wave"
        elif estilo == "half_moon":
            amp = max(0.25, comprimento * 0.02) * amplitude
            passo = max(1.1, comprimento * 0.12)
            ciclos = max(1, round(comprimento / passo))
            passo = comprimento / ciclos
            modo = "half_moon_full"
        elif estilo in {"dash_half_moon", "dash_half_moon_alt"}:
            amp = max(0.25, comprimento * 0.02) * amplitude
            passo = max(1.1, comprimento * 0.12)
            modo = "half_moon_dash"

        path = QPainterPath(self._cena_para_tela(p1))
        if modo == "zigzag":
            t = 0.0
            while t < comprimento:
                sentido = 1.0 if int((fase + t) / max(passo, 0.0001)) % 2 == 0 else -1.0
                px = p1.x() + (ux * t) + (nx * amp * sentido)
                py = p1.y() + (uy * t) + (ny * amp * sentido)
                path.lineTo(self._cena_para_tela(QPointF(px, py)))
                t += passo
            path.lineTo(self._cena_para_tela(p2))
        elif modo == "wave":
            periodos = max(1, int(comprimento / max(passo, 0.0001)))
            amostras = min(480, max(48, periodos * 24))
            for i in range(1, amostras + 1):
                t = (comprimento * i) / amostras
                seno = sin((2.0 * 3.14159265359 * (fase + t)) / passo)
                px = p1.x() + (ux * t) + (nx * amp * seno)
                py = p1.y() + (uy * t) + (ny * amp * seno)
                path.lineTo(self._cena_para_tela(QPointF(px, py)))
        elif modo == "half_moon_full":
            ciclos = max(1, round(comprimento / max(passo, 0.0001)))
            for ciclo in range(ciclos):
                base_inicio = passo * ciclo
                amostras_arco = min(120, max(14, int(passo * 8)))
                for i in range(1, amostras_arco + 1):
                    frac = i / amostras_arco
                    base_t = base_inicio + (passo * frac)
                    theta = (3.14159265359 * (fase + base_t)) / passo
                    altura = amp * abs(sin(theta))
                    px = p1.x() + (ux * base_t) + (nx * altura)
                    py = p1.y() + (uy * base_t) + (ny * altura)
                    path.lineTo(self._cena_para_tela(QPointF(px, py)))
        else:
            t = 0.0
            while t < comprimento:
                restante = comprimento - t
                if restante < (passo * 0.7):
                    fim_resto = QPointF(p1.x() + (ux * comprimento), p1.y() + (uy * comprimento))
                    path.lineTo(self._cena_para_tela(fim_resto))
                    break
                arco = min(passo, restante)
                amostras_arco = min(96, max(12, int(arco * 7)))
                for i in range(1, amostras_arco + 1):
                    frac = i / amostras_arco
                    base_t = t + (arco * frac)
                    theta = (3.14159265359 * (fase + base_t)) / passo
                    altura = amp * abs(sin(theta))
                    px = p1.x() + (ux * base_t) + (nx * altura)
                    py = p1.y() + (uy * base_t) + (ny * altura)
                    path.lineTo(self._cena_para_tela(QPointF(px, py)))
                if estilo != "half_moon":
                    gap = passo * (0.45 if estilo == "dash_half_moon" else 0.25)
                    t += arco + gap
                    if t < comprimento:
                        path.moveTo(self._cena_para_tela(QPointF(p1.x() + (ux * t), p1.y() + (uy * t))))
                else:
                    t += arco

        pen = QPen(QColor(cor), max(1.0, float(espessura)))
        pen.setStyle(Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(pen)
        painter.drawPath(path)

    def _aplicar_estilo_caneta(self, pen: QPen, estilo: str):
        pen.setStyle(pen_style_for_line(estilo))
        padrao = dash_pattern_for_line(estilo)
        if padrao:
            pen.setDashPattern(padrao)

    def _desenhar_label_angulo_cursor(self, painter: QPainter, origem: QPointF, destino: QPointF):
        dx = destino.x() - origem.x()
        dy = destino.y() - origem.y()
        if abs(dx) < 0.0001 and abs(dy) < 0.0001:
            return
        ang = degrees(atan2(-dy, dx)) % 360.0
        texto = f"{ang:.0f}°"
        metrics = QFontMetrics(painter.font())
        tw = metrics.horizontalAdvance(texto)
        th = metrics.height()
        candidatos = [
            (int(self._cursor_tela.x() + 14), int(self._cursor_tela.y() - 12)),
            (int(self._cursor_tela.x() + 14), int(self._cursor_tela.y() + th + 8)),
            (int(self._cursor_tela.x() - tw - 18), int(self._cursor_tela.y() - 12)),
            (int(self._cursor_tela.x() - tw - 18), int(self._cursor_tela.y() + th + 8)),
        ]
        snap_rect = self._retangulo_label_snap(painter, self._snap_resultado) if self._snap_resultado else None
        x, y = candidatos[0]
        for cx, cy in candidatos:
            ax, ay, aw, ah = cx - 4, cy - th, tw + 8, th + 4
            if cx < 0 or cy - th < 0 or cx + tw + 4 > self.width() or cy + 4 > self.height():
                continue
            if snap_rect and self._retangulos_intersectam((ax, ay, aw, ah), snap_rect):
                continue
            x, y = cx, cy
            break
        painter.fillRect(x - 4, y - th, tw + 8, th + 4, QColor(0, 0, 0, 180))
        painter.setPen(QPen(QColor("#ff6a00"), 1))
        painter.drawText(x, y, texto)

    def _abrir_menu_contexto(self, pos_global):
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu { background:#f5f6f8; color:#111111; border:1px solid #9da3aa; }
            QMenu::item { color:#111111; padding:4px 10px; }
            QMenu::item:selected { background:#dcecff; color:#111111; }
            QMenu::item:disabled { color:#5d636a; }
            QMenu::separator { height:1px; background:#9fa5ad; margin:4px 6px; }
            """
        )
        menu.addAction("Propriedades\tCtrl+Enter", lambda: None)
        menu.addAction("Variantes", lambda: None)
        menu.addAction("Informações modelo\tCtrl+M", lambda: None)
        menu.addSeparator()

        menu.addAction("Excluir\tDel", self.apagar_selecionados)
        ac_recortar = menu.addAction("Recortar\tCtrl+X", self._recortar_selecionados)
        ac_recortar.setEnabled(bool(self._selecionados))
        ac_copiar = menu.addAction("Copiar\tCtrl+C", self.copiar)
        ac_copiar.setEnabled(bool(self._selecionados or len(self._pontos_reta) >= 2 or self.cena.elementos))
        menu.addAction("Colar\tCtrl+V", self.colar)
        menu.addSeparator()

        menu.addAction("Selecionar tudo\tCtrl+T", self._selecionar_tudo)
        menu.addAction("Selecionar moldes", self._selecionar_tudo)
        menu.addAction("Inverter seleção", self._inverter_selecao)
        menu.addAction("Inverter seleção moldes", self._inverter_selecao)
        menu.addSeparator()

        menu.addAction("Cria ponto de restauração", self._registrar_historico)
        menu.addAction("Restaurar", self.desfazer_acao)
        menu.addAction("Restaura ponto de restauração com cópia", self.refazer_acao)
        menu.exec(pos_global)

    def _selecionar_tudo(self):
        self._selecionados = set(range(len(self.cena.elementos)))
        self.update()

    def _inverter_selecao(self):
        todos = set(range(len(self.cena.elementos)))
        self._selecionados = todos.difference(self._selecionados)
        self.update()

    def _recortar_selecionados(self):
        self.copiar()
        self.apagar_selecionados()

    def recortar(self):
        self._recortar_selecionados()

    def _desenhar_guia_angular(self, painter: QPainter, origem: QPointF, destino: QPointF):
        dx = destino.x() - origem.x()
        dy = destino.y() - origem.y()
        dist = sqrt(dx * dx + dy * dy)
        if dist <= 0.0001:
            return
        origem_tela = self._cena_para_tela(origem)
        raio_tela = dist * self.zoom
        pen_guia = QPen(QColor("#ff43ff"), 1)
        pen_guia.setStyle(Qt.DotLine)
        painter.setPen(pen_guia)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(origem_tela, raio_tela, raio_tela)
        eixo = QPointF(origem.x() + dist, origem.y())
        self._desenhar_segmento(painter, origem, eixo, tracejado=True, cor="#ff43ff")

    def _desfazer_ponto(self):
        if not self._pontos_reta:
            return
        self._pontos_reta.pop()
        if self._pontos_reta:
            self._preview_reta = self._pontos_reta[-1]
        else:
            self._preview_reta = None
            self._guia_fechamento = None
        self.update()

    def _finalizar_reta_atual(self):
        if len(self._pontos_reta) == 1:
            self._pontos_reta.clear()
            self._preview_reta = None
            self._guia_fechamento = None
            self._guias_alinhamento = []
            self._aguardando_retorno_selecao = False
            return

        if len(self._pontos_reta) >= 2:
            fase = 0.0
            for inicio, fim in zip(self._pontos_reta, self._pontos_reta[1:]):
                comprimento = sqrt((fim.x() - inicio.x()) ** 2 + (fim.y() - inicio.y()) ** 2)
                self.cena.elementos.append(
                    {
                        "tipo": "polyline",
                        "pontos": [(inicio.x(), inicio.y()), (fim.x(), fim.y())],
                        "cor": self._linha_cor,
                        "espessura": self._linha_espessura,
                        "estilo": self._linha_estilo,
                        "amplitude": self._linha_amplitude,
                        "fase_inicio": fase,
                    }
                )
                fase += comprimento
            self._registrar_historico()
            ultimo_ponto = self._pontos_reta[-1]
            self._pontos_reta = [ultimo_ponto]
            self._preview_reta = ultimo_ponto
            self._guia_fechamento = None
            self._guias_alinhamento = []
            self._aguardando_retorno_selecao = True

    def _reposicionar_painel_coordenadas(self):
        if not self.painel_coordenadas.isVisible():
            return
        if self._painel_coordenadas_posicao:
            self.painel_coordenadas.move(*self._painel_coordenadas_posicao)
            return
        x = max(8, self.width() - self.painel_coordenadas.width() - 12)
        y = 16
        self.painel_coordenadas.move(x, y)

    def _tela_para_cena(self, ponto: QPointF) -> QPointF:
        return QPointF((ponto.x() / self.zoom) + self.origem_cena.x(), (ponto.y() / self.zoom) + self.origem_cena.y())

    def _cena_para_tela(self, ponto: QPointF) -> QPointF:
        return QPointF((ponto.x() - self.origem_cena.x()) * self.zoom, (ponto.y() - self.origem_cena.y()) * self.zoom)

    def desfazer_acao(self):
        if self._pontos_reta:
            self._desfazer_ponto()
            return

        if self._indice_historico == 0:
            return
        self._indice_historico -= 1
        self.cena.elementos = deepcopy(self._historico_elementos[self._indice_historico])
        self.update()

    def refazer_acao(self):
        if self._indice_historico >= len(self._historico_elementos) - 1:
            return
        self._indice_historico += 1
        self.cena.elementos = deepcopy(self._historico_elementos[self._indice_historico])
        self.update()

    def copiar(self):
        if self._selecionados:
            self._buffer_copia = {
                "tipo": "multiplos",
                "elementos": [deepcopy(self.cena.elementos[idx]) for idx in sorted(self._selecionados)],
            }
            return
        if self._pontos_reta and len(self._pontos_reta) >= 2:
            self._buffer_copia = {
                "tipo": "polyline",
                "pontos": [(p.x(), p.y()) for p in self._pontos_reta],
                "cor": self._linha_cor,
                "espessura": self._linha_espessura,
                "estilo": self._linha_estilo,
                "amplitude": self._linha_amplitude,
                "fase_inicio": 0.0,
            }
            return

        if self.cena.elementos:
            self._buffer_copia = deepcopy(self.cena.elementos[-1])

    def colar(self):
        if not self._buffer_copia:
            return
        self._offset_colagem += 10
        self._selecionados.clear()
        if self._buffer_copia.get("tipo") == "multiplos":
            for item in self._buffer_copia.get("elementos", []):
                novo = deepcopy(item)
                if novo.get("tipo") == "polyline":
                    novo["pontos"] = [(x + self._offset_colagem, y + self._offset_colagem) for x, y in novo.get("pontos", [])]
                elif novo.get("tipo") == "bezier_quadratica":
                    for chave in ("p0", "p1", "p2"):
                        x, y = novo[chave]
                        novo[chave] = (x + self._offset_colagem, y + self._offset_colagem)
                self.cena.elementos.append(novo)
                self._selecionados.add(len(self.cena.elementos) - 1)
        else:
            novo = deepcopy(self._buffer_copia)
            if novo.get("tipo") == "polyline":
                novo["pontos"] = [(x + self._offset_colagem, y + self._offset_colagem) for x, y in novo.get("pontos", [])]
            elif novo.get("tipo") == "bezier_quadratica":
                for chave in ("p0", "p1", "p2"):
                    x, y = novo[chave]
                    novo[chave] = (x + self._offset_colagem, y + self._offset_colagem)
            self.cena.elementos.append(novo)
            self._selecionados.add(len(self.cena.elementos) - 1)
        self._registrar_historico()
        self.update()

    def apagar_selecionados(self):
        if not self._selecionados:
            return
        self.cena.elementos = [el for idx, el in enumerate(self.cena.elementos) if idx not in self._selecionados]
        self._selecionados.clear()
        self._registrar_historico()
        self.update()

    def _registrar_historico(self):
        snapshot = deepcopy(self.cena.elementos)
        if self._indice_historico < len(self._historico_elementos) - 1:
            self._historico_elementos = self._historico_elementos[: self._indice_historico + 1]
        self._historico_elementos.append(snapshot)
        if len(self._historico_elementos) > 200:
            self._historico_elementos.pop(0)
        self._indice_historico = len(self._historico_elementos) - 1

    def _retangulo_selecao(self, inicio: QPointF, fim: QPointF) -> tuple[float, float, float, float]:
        return min(inicio.x(), fim.x()), min(inicio.y(), fim.y()), max(inicio.x(), fim.x()), max(inicio.y(), fim.y())

    def _bbox_elemento(self, elemento: dict) -> tuple[float, float, float, float] | None:
        if elemento.get("tipo") == "polyline":
            pontos = elemento.get("pontos", [])
            if not pontos:
                return None
            xs = [p[0] for p in pontos]
            ys = [p[1] for p in pontos]
            return min(xs), min(ys), max(xs), max(ys)
        if elemento.get("tipo") == "bezier_quadratica":
            p0 = QPointF(*elemento["p0"])
            p1 = QPointF(*elemento["p1"])
            p2 = QPointF(*elemento["p2"])
            amostra = self._amostrar_bezier_quadratica(p0, p1, p2, segmentos=24)
            xs = [p.x() for p in amostra]
            ys = [p.y() for p in amostra]
            return min(xs), min(ys), max(xs), max(ys)
        return None

    def _atualizar_selecao_por_caixa(self, inicio: QPointF, fim: QPointF):
        x1, y1, x2, y2 = self._retangulo_selecao(inicio, fim)
        if abs(x2 - x1) < 1 and abs(y2 - y1) < 1:
            idx = None
            if self._snap_resultado and self._snap_resultado.elemento_idx is not None:
                idx = self._snap_resultado.elemento_idx
            if idx is None:
                idx = self._indice_elemento_em_ponto(inicio)
            self._selecionados = {idx} if idx is not None else set()
            return
        selecionados: set[int] = set()
        for idx, elemento in enumerate(self.cena.elementos):
            bbox = self._bbox_elemento(elemento)
            if not bbox:
                continue
            bx1, by1, bx2, by2 = bbox
            if bx1 >= x1 and bx2 <= x2 and by1 >= y1 and by2 <= y2:
                selecionados.add(idx)
        self._selecionados = selecionados

    def _indice_elemento_em_ponto(self, ponto: QPointF) -> int | None:
        tolerancia = 4 / max(self.zoom, 0.001)
        for idx in range(len(self.cena.elementos) - 1, -1, -1):
            bbox = self._bbox_elemento(self.cena.elementos[idx])
            if not bbox:
                continue
            x1, y1, x2, y2 = bbox
            if x1 - tolerancia <= ponto.x() <= x2 + tolerancia and y1 - tolerancia <= ponto.y() <= y2 + tolerancia:
                return idx
        return None

    def _alca_curva_em_ponto(self, ponto: QPointF) -> tuple[int, str] | None:
        tolerancia = 6 / max(self.zoom, 0.001)
        for idx in sorted(self._selecionados):
            if idx < 0 or idx >= len(self.cena.elementos):
                continue
            el = self.cena.elementos[idx]
            if el.get("tipo") != "bezier_quadratica":
                continue
            for alca in ("p0", "p1", "p2"):
                p = QPointF(*el[alca])
                if self._dist(p, ponto) <= tolerancia:
                    return idx, alca
        return None

    def _mover_selecionados(self, dx: float, dy: float):
        for idx in self._selecionados:
            el = self.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                el["pontos"] = [(x + dx, y + dy) for x, y in el.get("pontos", [])]
            elif el.get("tipo") == "bezier_quadratica":
                for chave in ("p0", "p1", "p2"):
                    x, y = el[chave]
                    el[chave] = (x + dx, y + dy)

    def _desenhar_caixa_selecao(self, painter: QPainter, inicio: QPointF, fim: QPointF):
        p1 = self._cena_para_tela(inicio)
        p2 = self._cena_para_tela(fim)
        x1, y1, x2, y2 = min(p1.x(), p2.x()), min(p1.y(), p2.y()), max(p1.x(), p2.x()), max(p1.y(), p2.y())
        painter.fillRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1), QColor(120, 0, 0, 80))
        painter.setPen(QPen(QColor("#ff3333"), 1))
        painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))

    def _desenhar_marcador_snap(self, painter: QPainter, snap: SnapResult):
        pt = self._cena_para_tela(snap.ponto)
        cor = QColor("#ff6a00")
        pen = QPen(cor, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(pt.x() - 5), int(pt.y() - 5), 10, 10)
        texto = snap.tipo
        metrics = QFontMetrics(painter.font())
        tw = metrics.horizontalAdvance(texto)
        th = metrics.height()

        offset_x = 10
        offset_y = -10
        tx = pt.x() + offset_x
        ty = pt.y() + offset_y
        if tx + tw + 8 > self.width():
            tx = pt.x() - tw - 14
        if ty - th < 0:
            ty = pt.y() + th + 8

        bg_x = int(tx - 4)
        bg_y = int(ty - th + 2)
        bg_w = int(tw + 8)
        bg_h = int(th + 4)
        painter.fillRect(bg_x, bg_y, bg_w, bg_h, QColor(0, 0, 0, 180))
        painter.setPen(QPen(cor, 1))
        painter.drawText(int(tx), int(ty), texto)

    def _retangulo_label_snap(self, painter: QPainter, snap: SnapResult | None) -> tuple[int, int, int, int] | None:
        if not snap:
            return None
        pt = self._cena_para_tela(snap.ponto)
        texto = snap.tipo
        metrics = QFontMetrics(painter.font())
        tw = metrics.horizontalAdvance(texto)
        th = metrics.height()
        tx = pt.x() + 10
        ty = pt.y() - 10
        if tx + tw + 8 > self.width():
            tx = pt.x() - tw - 14
        if ty - th < 0:
            ty = pt.y() + th + 8
        return int(tx - 4), int(ty - th + 2), int(tw + 8), int(th + 4)

    def _retangulos_intersectam(
        self,
        a: tuple[int, int, int, int],
        b: tuple[int, int, int, int],
    ) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax + aw < bx or bx + bw < ax or ay + ah < by or by + bh < ay)

    def set_snap_ativo(self, ativo: bool):
        self._snap_ativo = ativo
        if not ativo:
            self._snap_resultado = None
            self._snap_candidatos = []
            self._snap_indice = 0
        self.snap_changed.emit(ativo)
        self.update()

    def alternar_snap(self):
        self.set_snap_ativo(not self._snap_ativo)

    def snap_ativo(self) -> bool:
        return self._snap_ativo

    def _ponto_com_snap(self, pos_tela: QPointF) -> QPointF:
        pos_cena = self._tela_para_cena(pos_tela)
        self._snap_candidatos = self._snap_manager.calcular_candidatos(
            self.cena, pos_cena, self.zoom, tolerancia_px=self._tolerancia_snap_px()
        )
        tol_cena = self._tolerancia_snap_px() / max(self.zoom, 0.001)
        for idx, el in enumerate(self.cena.elementos):
            if el.get("tipo") != "bezier_quadratica":
                continue
            p0 = QPointF(*el["p0"])
            p1 = QPointF(*el["p1"])
            p2 = QPointF(*el["p2"])
            candidatos = [
                ("nó", p0),
                ("controle", p1),
                ("nó", p2),
                ("ponto médio", QPointF((p0.x() + p2.x()) / 2.0, (p0.y() + p2.y()) / 2.0)),
            ]
            for tipo, ponto in candidatos:
                dist = self._dist(pos_cena, ponto)
                if dist <= tol_cena:
                    self._snap_candidatos.append(SnapResult(ponto=ponto, tipo=tipo, distancia=dist, elemento_idx=idx))
        if self._ponto_coordenada_aplicada is not None:
            dist = sqrt(
                (pos_cena.x() - self._ponto_coordenada_aplicada.x()) ** 2
                + (pos_cena.y() - self._ponto_coordenada_aplicada.y()) ** 2
            )
            if dist <= tol_cena:
                self._snap_candidatos.insert(
                    0,
                    SnapResult(
                        ponto=QPointF(self._ponto_coordenada_aplicada),
                        tipo="coord",
                        distancia=dist,
                        elemento_idx=None,
                    ),
                )
        if self._snap_candidatos:
            candidatos_sem_grade = [c for c in self._snap_candidatos if c.tipo != "grade"]
            if candidatos_sem_grade:
                self._snap_candidatos = candidatos_sem_grade
        if self._snap_candidatos:
            self._snap_indice = min(self._snap_indice, len(self._snap_candidatos) - 1)
            self._snap_resultado = self._snap_candidatos[self._snap_indice]
        else:
            self._snap_resultado = None
            self._snap_indice = 0
        if self._snap_resultado:
            return self._snap_resultado.ponto
        return pos_cena

    def _tolerancia_snap_px(self) -> float:
        # 0,5 cm na tela (aprox.) usando DPI lógico da janela/canvas.
        dpi = float(self.logicalDpiX()) if self.logicalDpiX() > 0 else 96.0
        return (dpi / 2.54) * 0.5

    def leaveEvent(self, event):  # noqa: N802
        self._snap_resultado = None
        self._snap_candidatos = []
        self._snap_indice = 0
        self._tecla_w_trava_principal = False
        self.update()
        super().leaveEvent(event)

    def _registrar_posicao_painel(self, x: int, y: int):
        self._painel_coordenadas_posicao = (x, y)
        self.painel_posicao_changed.emit(x, y)

    def painel_auxiliar_posicao(self) -> tuple[int, int] | None:
        if self._painel_coordenadas_posicao:
            return self._painel_coordenadas_posicao
        if self.painel_coordenadas.isVisible():
            return self.painel_coordenadas.x(), self.painel_coordenadas.y()
        return None

    def set_painel_auxiliar_posicao(self, pos: tuple[int, int] | None):
        self._painel_coordenadas_posicao = pos
        if pos and self.painel_coordenadas.isVisible():
            self.painel_coordenadas.move(*pos)

    def painel_coordenadas_visivel(self) -> bool:
        return self._painel_coordenadas_visivel

    def definir_painel_coordenadas_visivel(self, visivel: bool):
        self._painel_coordenadas_visivel = visivel
        if visivel:
            self.painel_coordenadas.show()
            self._reposicionar_painel_coordenadas()
        else:
            self.painel_coordenadas.hide()
        self.painel_coordenadas_changed.emit(visivel)

    def _set_painel_coordenadas_visivel(self, visivel: bool):
        self._painel_coordenadas_visivel = visivel
        self.painel_coordenadas_changed.emit(visivel)

    def _snap_angular(
        self,
        origem: QPointF,
        destino: QPointF,
        travar_snap_exato: bool = False,
        travar_principais: bool = False,
        liberar_angular: bool | None = None,
    ) -> QPointF:
        # Compatibilidade com chamadas antigas que usavam `liberar_angular`.
        # Regra antiga: True = livre. Regra nova: W pressionado = trava principais.
        if liberar_angular is not None:
            travar_principais = not bool(liberar_angular)
        if not self._snap_ativo:
            return destino
        if travar_snap_exato and self._snap_resultado and self._snap_resultado.tipo in {"nó", "ponto médio", "centro", "borda", "coord", "interseção"}:
            return destino
        dx = destino.x() - origem.x()
        dy = destino.y() - origem.y()
        dist = sqrt(dx * dx + dy * dy)
        if dist <= 0.0001:
            return destino
        ang = degrees(atan2(-dy, dx))
        ang_principal = round(ang / 45.0) * 45.0
        if travar_principais:
            return QPointF(origem.x() + dist * cos(radians(ang_principal)), origem.y() - dist * sin(radians(ang_principal)))
        if self._snap_contextual_ativo and len(self._pontos_reta) >= 2:
            ang_contextual = self._snap_angular_contextual(origem, ang)
            if ang_contextual is not None:
                return QPointF(origem.x() + dist * cos(radians(ang_contextual)), origem.y() - dist * sin(radians(ang_contextual)))
        angulo_dist = self._dist_angular(ang, ang_principal)
        tolerancia_principal = max(1.8, min(5.0, self._snap_angular_passo * 0.12))
        if angulo_dist <= tolerancia_principal:
            return QPointF(origem.x() + dist * cos(radians(ang_principal)), origem.y() - dist * sin(radians(ang_principal)))
        return destino

    def _snap_angular_contextual(self, origem: QPointF, ang_atual: float) -> float | None:
        ponto_anterior = self._pontos_reta[-2]
        vx = origem.x() - ponto_anterior.x()
        vy = origem.y() - ponto_anterior.y()
        dist_ref = sqrt(vx * vx + vy * vy)
        if dist_ref <= 0.0001:
            return None
        ang_ref = degrees(atan2(-vy, vx))
        candidatos = [ang_ref, ang_ref + 180.0, ang_ref + 90.0, ang_ref - 90.0]
        melhor = min(candidatos, key=lambda ang: self._dist_angular(ang_atual, ang))
        if self._dist_angular(ang_atual, melhor) <= 5.0:
            return melhor
        return None

    def _dist_angular(self, a: float, b: float) -> float:
        diff = abs((a - b) % 360.0)
        return min(diff, 360.0 - diff)

    def _aplicar_guia_fechamento(self, origem: QPointF, destino: QPointF) -> QPointF:
        self._guia_fechamento = None
        if len(self._pontos_reta) < 2 or not self._snap_resultado:
            return destino

        if self._snap_resultado.tipo not in {"nó", "ponto médio", "centro", "borda", "coord", "interseção"}:
            return destino

        ponto_final = self._snap_resultado.ponto
        ponto_anterior = self._pontos_reta[-2]
        vec_ref = QPointF(origem.x() - ponto_anterior.x(), origem.y() - ponto_anterior.y())
        vec_cursor = QPointF(destino.x() - origem.x(), destino.y() - origem.y())
        mod_ref = sqrt(vec_ref.x() * vec_ref.x() + vec_ref.y() * vec_ref.y())
        mod_cursor = sqrt(vec_cursor.x() * vec_cursor.x() + vec_cursor.y() * vec_cursor.y())
        if mod_ref <= 0.0001 or mod_cursor <= 0.0001:
            return destino

        det = (vec_ref.x() * vec_cursor.y()) - (vec_ref.y() * vec_cursor.x())
        if abs(det) <= 0.0001:
            return destino

        delta = QPointF(origem.x() - ponto_final.x(), origem.y() - ponto_final.y())
        t = ((delta.x() * vec_cursor.y()) - (delta.y() * vec_cursor.x())) / det
        u = ((delta.x() * vec_ref.y()) - (delta.y() * vec_ref.x())) / det
        if u < 0:
            return destino

        intersecao = QPointF(ponto_final.x() + t * vec_ref.x(), ponto_final.y() + t * vec_ref.y())
        tolerancia_cena = self._tolerancia_snap_px() / max(self.zoom, 0.001)
        dist_intersecao = sqrt((intersecao.x() - destino.x()) ** 2 + (intersecao.y() - destino.y()) ** 2)
        if dist_intersecao > tolerancia_cena * 4:
            return destino

        self._guia_fechamento = (ponto_final, intersecao)

        if dist_intersecao <= tolerancia_cena:
            return intersecao
        return destino

    def _aplicar_guias_alinhamento(self, origem: QPointF, destino: QPointF) -> QPointF:
        self._guias_alinhamento = []
        if not self._snap_ativo:
            return destino
        if self._snap_resultado and self._snap_resultado.tipo in {"nó", "ponto médio", "centro", "borda", "coord", "interseção"}:
            return destino

        candidatos: list[QPointF] = []
        candidatos.extend(self._pontos_reta[:-1])
        for el in self.cena.elementos:
            if el.get("tipo") == "polyline":
                candidatos.extend(QPointF(float(x), float(y)) for x, y in el.get("pontos", []))
        if not candidatos:
            return destino

        tol = self._tolerancia_snap_px() / max(self.zoom, 0.001)
        melhor_x: QPointF | None = None
        melhor_y: QPointF | None = None
        dist_x = float("inf")
        dist_y = float("inf")
        for pt in candidatos:
            dx = abs(destino.x() - pt.x())
            dy = abs(destino.y() - pt.y())
            if dx <= tol and dx < dist_x:
                melhor_x = pt
                dist_x = dx
            if dy <= tol and dy < dist_y:
                melhor_y = pt
                dist_y = dy

        ajustado = QPointF(destino)
        if melhor_x:
            ajustado.setX(melhor_x.x())
            self._guias_alinhamento.append((QPointF(melhor_x.x(), melhor_x.y()), QPointF(melhor_x.x(), ajustado.y())))
        if melhor_y:
            ajustado.setY(melhor_y.y())
            self._guias_alinhamento.append((QPointF(melhor_y.x(), melhor_y.y()), QPointF(ajustado.x(), melhor_y.y())))
        return ajustado

    def _aplicar_coordenadas(self, payload: dict):
        origem = self._pontos_reta[-1] if self._pontos_reta else QPointF(0.0, 0.0)
        dx = payload.get("dx")
        dy = payload.get("dy")
        ang = payload.get("a")
        dist = payload.get("d")
        destino: QPointF | None = None
        if ang is not None and dist is not None:
            rad = radians(ang)
            destino = QPointF(origem.x() + (dist * cos(rad)), origem.y() - (dist * sin(rad)))
        elif dx is not None or dy is not None:
            destino = QPointF(origem.x() + float(dx or 0.0), origem.y() + float(dy or 0.0))
        if destino is None:
            return
        destino = self._snap_angular(origem, destino)
        self._ponto_coordenada_aplicada = destino
        self._marcacoes_temporarias.append(destino)
        self.painel_coordenadas.atualizar_preview(origem, destino)
        self.update()

    def elementos_para_salvar(self) -> list[dict]:
        elementos = deepcopy(self.cena.elementos)
        if len(self._pontos_reta) >= 2:
            fase = 0.0
            for inicio, fim in zip(self._pontos_reta, self._pontos_reta[1:]):
                comprimento = sqrt((fim.x() - inicio.x()) ** 2 + (fim.y() - inicio.y()) ** 2)
                elementos.append(
                    {
                        "tipo": "polyline",
                        "pontos": [(inicio.x(), inicio.y()), (fim.x(), fim.y())],
                        "cor": self._linha_cor,
                        "espessura": self._linha_espessura,
                        "estilo": self._linha_estilo,
                        "amplitude": self._linha_amplitude,
                        "fase_inicio": fase,
                    }
                )
                fase += comprimento
        return elementos

    def _desenhar_marca_x(self, painter: QPainter, ponto: QPointF, cor: str = "#ff5a00"):
        pt = self._cena_para_tela(ponto)
        pen = QPen(QColor(cor), 1)
        painter.setPen(pen)
        painter.drawLine(int(pt.x() - 5), int(pt.y() - 5), int(pt.x() + 5), int(pt.y() + 5))
        painter.drawLine(int(pt.x() - 5), int(pt.y() + 5), int(pt.x() + 5), int(pt.y() - 5))

    def set_estilo_linha(
        self, cor: str | None = None, estilo: str | None = None, espessura: float | None = None, amplitude: float | None = None
    ):
        if cor:
            self._linha_cor = cor
        if estilo:
            self._linha_estilo = estilo
        if espessura is not None:
            self._linha_espessura = max(1.0, float(espessura))
        if amplitude is not None:
            self._linha_amplitude = max(0.2, float(amplitude))
        self.update()

    def set_modo_curva(self, modo: str):
        self._modo_curva = "3p" if str(modo).lower().startswith("3") else "2p"
        self._resetar_estado_curva()

    def set_passo_snap_angular(self, passo: float):
        self._snap_angular_passo = max(1.0, float(passo))

    def set_snap_contextual_ativo(self, ativo: bool):
        self._snap_contextual_ativo = bool(ativo)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key_W and not event.isAutoRepeat():
            self._tecla_w_trava_principal = True
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key_W and not event.isAutoRepeat():
            self._tecla_w_trava_principal = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):  # noqa: N802
        self._tecla_w_trava_principal = False
        super().focusOutEvent(event)
