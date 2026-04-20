from __future__ import annotations

from math import atan2, cos, degrees, radians, sin, sqrt
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tools.tool_base import FerramentaBase

if TYPE_CHECKING:
    from canvas.visualizacao import VisualizacaoCanvas


class RetaToolUI(QFrame):
    modo_changed = Signal(str)
    valor_changed = Signal(float, float)
    delta_changed = Signal(float, float)
    fechado = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle("Reta - Opções")
        self.setObjectName("RetaToolUI")
        self.setFixedWidth(324)
        self._drag_offset_local: QPoint | None = None
        self._margem_canvas = 12

        self._botoes_modo: dict[str, QPushButton] = {}
        self.modo_atual = "livre"

        self.setStyleSheet(
            """
            QFrame#RetaToolUI {
                background: #f5f7fa;
                border: 1px solid #c8d2dc;
                border-radius: 10px;
                color: #16202a;
            }
            QLabel#title {
                color: #0f4f86;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#section {
                color: #425466;
                font-size: 9px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QLabel#hint {
                color: #66788a;
                font-size: 9px;
            }
            QLabel#mouseCoord, QLabel#statusBox {
                background: #ffffff;
                border: 1px solid #d6dee6;
                border-radius: 6px;
                padding: 4px 6px;
                color: #1f2d3a;
            }
            QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #c6d0da;
                border-radius: 5px;
                padding: 3px 5px;
                min-height: 22px;
                color: #16202a;
            }
            QDoubleSpinBox:focus {
                border: 1px solid #0b8dd1;
            }
            QPushButton#modeButton {
                background: #ffffff;
                border: 1px solid #c6d0da;
                border-radius: 6px;
                padding: 3px 6px;
                color: #213140;
                font-size: 10px;
                font-weight: 600;
                min-height: 24px;
            }
            QPushButton#modeButton:hover {
                background: #eff6fc;
                border: 1px solid #8db8db;
            }
            QPushButton#modeButton:checked {
                background: #dfeffc;
                border: 1px solid #0b8dd1;
                color: #0f4f86;
            }
            QPushButton#applyButton {
                background: #0b7fb8;
                border: 1px solid #0a6e9f;
                border-radius: 6px;
                color: #ffffff;
                font-size: 10px;
                font-weight: 700;
                min-height: 26px;
            }
            QPushButton#applyButton:hover {
                background: #0d90cf;
            }
            QPushButton#closeButton {
                background: #ffffff;
                border: 1px solid #ccd6e0;
                border-radius: 8px;
                color: #4a5d70;
                min-width: 26px;
                max-width: 26px;
                min-height: 26px;
                max-height: 26px;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton#closeButton:hover {
                background: #eef3f8;
                color: #16324a;
            }
            QFrame#line {
                background: #d7dfe7;
                min-height: 1px;
                max-height: 1px;
                border: none;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(6)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(6)
        titulo = QLabel("Ferramenta Reta")
        titulo.setObjectName("title")
        topo.addWidget(titulo, 1)

        self.btn_fechar = QPushButton("✕")
        self.btn_fechar.setObjectName("closeButton")
        self.btn_fechar.setCursor(Qt.PointingHandCursor)
        self.btn_fechar.clicked.connect(self.fechar)
        topo.addWidget(self.btn_fechar)
        layout.addLayout(topo)

        subtitulo = QLabel("Desenho técnico com restrições, snap e medição dinâmica")
        subtitulo.setObjectName("hint")
        subtitulo.setWordWrap(True)
        layout.addWidget(subtitulo)

        layout.addWidget(self._linha())

        layout.addWidget(self._section_label("Cursor"))
        self.mouse_coord_label = QLabel("X 0.00 cm  |  Y 0.00 cm")
        self.mouse_coord_label.setObjectName("mouseCoord")
        self.mouse_coord_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.mouse_coord_label)

        self.status_label = QLabel("Pronto para iniciar")
        self.status_label.setObjectName("statusBox")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(self._linha())

        layout.addWidget(self._section_label("Modo de desenho"))
        grade_modos = QGridLayout()
        grade_modos.setContentsMargins(0, 0, 0, 0)
        grade_modos.setHorizontalSpacing(5)
        grade_modos.setVerticalSpacing(5)

        modos = [
            ("livre", "Livre"),
            ("comprimento", "Comprimento"),
            ("angulo", "Ângulo"),
            ("comp_ang", "Comp + Âng."),
            ("paralela", "Paralela"),
            ("perpendicular", "Perpendicular"),
            ("horizontal", "Horizontal"),
            ("vertical", "Vertical"),
        ]
        for idx, (modo_id, rotulo) in enumerate(modos):
            botao = QPushButton(rotulo)
            botao.setObjectName("modeButton")
            botao.setCheckable(True)
            botao.setCursor(Qt.PointingHandCursor)
            botao.clicked.connect(lambda _=False, m=modo_id: self._set_modo(m))
            self._botoes_modo[modo_id] = botao
            grade_modos.addWidget(botao, idx // 2, idx % 2)
        layout.addLayout(grade_modos)

        layout.addWidget(self._linha())
        layout.addWidget(self._section_label("Entrada precisa"))

        grade_valores = QGridLayout()
        grade_valores.setContentsMargins(0, 0, 0, 0)
        grade_valores.setHorizontalSpacing(6)
        grade_valores.setVerticalSpacing(5)

        self.spin_dx = self._criar_spin(-10000.0, 10000.0, 0.0, 2, " cm")
        self.spin_dy = self._criar_spin(-10000.0, 10000.0, 0.0, 2, " cm")
        self.spin_comprimento = self._criar_spin(0.01, 10000.0, 10.0, 2, " cm")
        self.spin_angulo = self._criar_spin(-360.0, 360.0, 0.0, 1, "°")

        grade_valores.addWidget(QLabel("ΔX"), 0, 0)
        grade_valores.addWidget(self.spin_dx, 0, 1)
        grade_valores.addWidget(QLabel("ΔY"), 0, 2)
        grade_valores.addWidget(self.spin_dy, 0, 3)
        grade_valores.addWidget(QLabel("Comprimento"), 1, 0)
        grade_valores.addWidget(self.spin_comprimento, 1, 1)
        grade_valores.addWidget(QLabel("Ângulo"), 1, 2)
        grade_valores.addWidget(self.spin_angulo, 1, 3)
        layout.addLayout(grade_valores)

        self.btn_aplicar = QPushButton("Aplicar ao próximo segmento")
        self.btn_aplicar.setObjectName("applyButton")
        self.btn_aplicar.setCursor(Qt.PointingHandCursor)
        self.btn_aplicar.clicked.connect(self._aplicar_valores)
        layout.addWidget(self.btn_aplicar)

        dicas = QLabel(
            "LMB adiciona ponto  •  RMB finaliza / sai  •  Shift trava 45°  •  W trava X/Y  •  Esc cancela"
        )
        dicas.setObjectName("hint")
        dicas.setWordWrap(True)
        layout.addWidget(dicas)

        self._set_modo("livre")

    def _section_label(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setObjectName("section")
        return lbl

    def _linha(self) -> QFrame:
        linha = QFrame()
        linha.setObjectName("line")
        linha.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return linha

    def _criar_spin(self, minimo: float, maximo: float, valor: float, decimais: int, sufixo: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimo, maximo)
        spin.setValue(valor)
        spin.setDecimals(decimais)
        spin.setSuffix(sufixo)
        spin.setButtonSymbols(QDoubleSpinBox.UpDownArrows)
        return spin

    def _set_modo(self, modo: str):
        self.modo_atual = modo
        for modo_id, botao in self._botoes_modo.items():
            botao.blockSignals(True)
            botao.setChecked(modo_id == modo)
            botao.blockSignals(False)
        self.modo_changed.emit(modo)
        self._atualizar_status_modo()

    def _atualizar_status_modo(self):
        textos = {
            "livre": "Modo livre ativo. Desenho contínuo ponto a ponto.",
            "comprimento": "Mantém o comprimento informado e segue a direção do cursor.",
            "angulo": "Mantém o ângulo informado e usa o comprimento do cursor.",
            "comp_ang": "Usa comprimento e ângulo fixos para cada novo segmento.",
            "paralela": "Selecione uma reta de referência e desenhe paralelo a ela.",
            "perpendicular": "Selecione uma reta de referência e desenhe perpendicular a ela.",
            "horizontal": "Restringe o próximo segmento ao eixo horizontal.",
            "vertical": "Restringe o próximo segmento ao eixo vertical.",
        }
        self.status_label.setText(textos.get(self.modo_atual, "Modo ativo."))

    def _aplicar_valores(self):
        if self.modo_atual in {"comprimento", "comp_ang", "angulo"}:
            self.valor_changed.emit(self.spin_comprimento.value(), self.spin_angulo.value())
        else:
            self.delta_changed.emit(self.spin_dx.value(), self.spin_dy.value())

    def atualizar_coordenadas_mouse(self, x: float, y: float):
        self.mouse_coord_label.setText(f"X {x:.2f} cm  |  Y {y:.2f} cm")

    def atualizar_status_operacao(self, texto: str):
        self.status_label.setText(texto)

    def showEvent(self, event):
        super().showEvent(event)
        self.reposicionar_no_canto_superior_direito()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._pode_iniciar_arraste(event):
            self._drag_offset_local = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset_local is not None and event.buttons() & Qt.LeftButton:
            destino = self.pos() + event.position().toPoint() - self._drag_offset_local
            self.move(self._ajustar_para_canvas(destino))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._drag_offset_local is not None:
            self._drag_offset_local = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _pode_iniciar_arraste(self, event: QMouseEvent) -> bool:
        if event.position().y() > 70:
            return False
        filho = self.childAt(event.position().toPoint())
        if isinstance(filho, (QDoubleSpinBox, QPushButton)) and filho is not self:
            return filho is self.btn_fechar
        return True

    def _retangulo_util_canvas(self) -> QRect:
        parent = self.parentWidget()
        if parent is None:
            return QRect(0, 0, max(self.width(), 1), max(self.height(), 1))
        return parent.rect().adjusted(self._margem_canvas, self._margem_canvas, -self._margem_canvas, -self._margem_canvas)

    def _ajustar_para_canvas(self, pos: QPoint) -> QPoint:
        area = self._retangulo_util_canvas()
        largura_util = max(0, area.width() - self.width())
        altura_util = max(0, area.height() - self.height())
        x = area.left() + max(0, min(pos.x() - area.left(), largura_util))
        y = area.top() + max(0, min(pos.y() - area.top(), altura_util))
        return QPoint(x, y)

    def reposicionar_no_canto_superior_direito(self):
        self.move(self._ajustar_para_canvas(QPoint(10_000, 0)))

    def _posicionar_canto_superior_direito(self):
        tela = self.screen() or QApplication.primaryScreen()
        if not tela:
            return
        area = tela.availableGeometry()
        margem = 12
        x = area.right() - self.width() - margem
        y = area.top() + margem
        self.move(max(area.left() + margem, x), y)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            destino = event.globalPosition() - self._drag_offset
            self.move(int(destino.x()), int(destino.y()))
            self._posicao_definida_manualmente = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def fechar(self):
        self.hide()
        self.fechado.emit()


class Ferramenta(FerramentaBase):
    id_ferramenta = "reta"
    nome = "Reta"

    ANGULOS_PRINCIPAIS = [0, 45, 90, 135, 180, 225, 270, 315]

    def __init__(self):
        super().__init__()
        self.modo = "livre"
        self.comprimento_fixo = 10.0
        self.angulo_fixo = 0.0
        self.reta_referencia: tuple[QPointF, QPointF] | None = None
        self.ui_flutuante: RetaToolUI | None = None
        self.canvas: VisualizacaoCanvas | None = None
        self.tecla_shift = False
        self.tecla_w = False
        self._desenhando = False
        self._terminado = False
        self._pontos_atuais: list[QPointF] = []
        self._aguardando_referencia = False

    def ativar(self) -> str:
        self.criar_interface()
        self._resetar_estado()
        if self.ui_flutuante:
            self.ui_flutuante.atualizar_status_operacao("Clique para começar ou informe valores precisos.")
        return "Reta ativada. Clique esquerdo para começar. Clique direito para terminar."

    def on_activate(self, canvas: VisualizacaoCanvas):
        self.canvas = canvas
        self.criar_interface()
        if self.ui_flutuante:
            self.ui_flutuante.raise_()
            self.ui_flutuante.reposicionar_no_canto_superior_direito()
            self.ui_flutuante.atualizar_status_operacao("Ferramenta pronta.")

    def desativar(self):
        if self.ui_flutuante:
            self.ui_flutuante.fechar()
            self.ui_flutuante.deleteLater()
            self.ui_flutuante = None
        self._resetar_estado()
        super().desativar()

    def criar_interface(self):
        parent = self.canvas if self.canvas is not None else None
        if self.ui_flutuante is None:
            self.ui_flutuante = RetaToolUI(parent)
            self.ui_flutuante.modo_changed.connect(self._definir_modo)
            self.ui_flutuante.valor_changed.connect(self._aplicar_valores_polar)
            self.ui_flutuante.delta_changed.connect(self._aplicar_valores_delta)
            self.ui_flutuante.fechado.connect(self._ui_fechado)
        elif parent is not None and self.ui_flutuante.parentWidget() is not parent:
            self.ui_flutuante.setParent(parent)
        self.ui_flutuante.show()
        self.ui_flutuante.raise_()
        self.ui_flutuante.reposicionar_no_canto_superior_direito()

    def _ui_fechado(self):
        self.ui_flutuante = None

    def _definir_modo(self, modo: str):
        self.modo = modo
        self.reta_referencia = None
        self._aguardando_referencia = modo in {"paralela", "perpendicular"}
        if self.canvas:
            self.canvas._destacar_reta_temporaria = None
            self.canvas.update()
        if self.ui_flutuante:
            if self._aguardando_referencia:
                self.ui_flutuante.atualizar_status_operacao("Selecione uma reta de referência no desenho.")
            else:
                self.ui_flutuante._atualizar_status_modo()

    def _aplicar_valores_polar(self, comprimento: float, angulo: float):
        self.comprimento_fixo = max(0.01, comprimento)
        self.angulo_fixo = angulo
        if self._desenhando and self._pontos_atuais:
            origem = self._pontos_atuais[-1]
            destino = self._destino_polar(origem, self.comprimento_fixo, self.angulo_fixo)
            destino = self._aplicar_restricoes(origem, destino)
            destino = self._aplicar_pos_processamento(origem, destino)
            self._adicionar_ponto(destino)

    def _aplicar_valores_delta(self, dx: float, dy: float):
        if self._desenhando and self._pontos_atuais:
            origem = self._pontos_atuais[-1]
            destino = QPointF(origem.x() + dx, origem.y() + dy)
            destino = self._aplicar_restricoes(origem, destino)
            destino = self._aplicar_pos_processamento(origem, destino)
            self._adicionar_ponto(destino)
        else:
            self.comprimento_fixo = sqrt((dx * dx) + (dy * dy)) or self.comprimento_fixo
            self.angulo_fixo = self._angulo_entre(QPointF(0.0, 0.0), QPointF(dx, dy)) if dx or dy else self.angulo_fixo

    def _resetar_estado(self):
        self._desenhando = False
        self._terminado = False
        self._pontos_atuais = []
        self.reta_referencia = None
        if self.modo not in {"paralela", "perpendicular"}:
            self._aguardando_referencia = False
        if self.canvas:
            self.canvas._pontos_reta = []
            self.canvas._preview_reta = None
            self.canvas._guia_fechamento = None
            self.canvas._guias_alinhamento = []
            self.canvas._destacar_reta_temporaria = None
            self.canvas.painel_coordenadas.atualizar_preview(None, None)
            self.canvas.update()

    def _destino_polar(self, origem: QPointF, comprimento: float, angulo: float) -> QPointF:
        rad = radians(angulo)
        return QPointF(origem.x() + (cos(rad) * comprimento), origem.y() + (sin(rad) * comprimento))

    def _angulo_referencia(self) -> float | None:
        if not self.reta_referencia:
            return None
        return self._angulo_entre(self.reta_referencia[0], self.reta_referencia[1])

    def _travar_angulo_principal(self, ponto_anterior: QPointF, ponto_atual: QPointF) -> QPointF:
        dx = ponto_atual.x() - ponto_anterior.x()
        dy = ponto_atual.y() - ponto_anterior.y()
        if abs(dx) < 0.0001 and abs(dy) < 0.0001:
            return ponto_atual
        angulo = degrees(atan2(dy, dx)) % 360.0
        angulo_mais_proximo = min(self.ANGULOS_PRINCIPAIS, key=lambda a: min(abs(angulo - a), 360 - abs(angulo - a)))
        diferenca = min(abs(angulo - angulo_mais_proximo), 360 - abs(angulo - angulo_mais_proximo))
        if diferenca <= 7.5:
            comprimento = sqrt((dx * dx) + (dy * dy))
            rad = radians(angulo_mais_proximo)
            return QPointF(ponto_anterior.x() + (cos(rad) * comprimento), ponto_anterior.y() + (sin(rad) * comprimento))
        return ponto_atual

    def _aplicar_modo_referencia(self, ponto_anterior: QPointF, ponto: QPointF) -> QPointF:
        ang_ref = self._angulo_referencia()
        if ang_ref is None:
            return ponto
        vetor = ponto - ponto_anterior
        comprimento_cursor = sqrt((vetor.x() * vetor.x()) + (vetor.y() * vetor.y()))
        if self.modo == "paralela":
            angulo = ang_ref
        else:
            angulo = (ang_ref + 90.0) % 360.0
        comprimento = self.comprimento_fixo if self.modo == "comp_ang" else comprimento_cursor
        if comprimento <= 0.0001:
            comprimento = max(self.comprimento_fixo, 0.01)
        rad = radians(angulo)
        return QPointF(ponto_anterior.x() + (cos(rad) * comprimento), ponto_anterior.y() + (sin(rad) * comprimento))

    def _aplicar_restricoes(self, ponto_anterior: QPointF, ponto: QPointF) -> QPointF:
        resultado = QPointF(ponto)

        if self.tecla_w:
            dx = resultado.x() - ponto_anterior.x()
            dy = resultado.y() - ponto_anterior.y()
            if abs(dx) >= abs(dy):
                return QPointF(resultado.x(), ponto_anterior.y())
            return QPointF(ponto_anterior.x(), resultado.y())

        if self.tecla_shift:
            return self._travar_angulo_principal(ponto_anterior, resultado)

        if self.modo == "horizontal":
            return QPointF(resultado.x(), ponto_anterior.y())

        if self.modo == "vertical":
            return QPointF(ponto_anterior.x(), resultado.y())

        if self.modo == "comprimento":
            vetor = resultado - ponto_anterior
            comprimento = sqrt((vetor.x() * vetor.x()) + (vetor.y() * vetor.y()))
            if comprimento > 0.0001:
                fator = self.comprimento_fixo / comprimento
                return QPointF(ponto_anterior.x() + (vetor.x() * fator), ponto_anterior.y() + (vetor.y() * fator))
            return resultado

        if self.modo == "angulo":
            vetor = resultado - ponto_anterior
            comprimento = sqrt((vetor.x() * vetor.x()) + (vetor.y() * vetor.y()))
            if comprimento > 0.0001:
                return self._destino_polar(ponto_anterior, comprimento, self.angulo_fixo)
            return resultado

        if self.modo == "comp_ang":
            return self._destino_polar(ponto_anterior, self.comprimento_fixo, self.angulo_fixo)

        if self.modo in {"paralela", "perpendicular"} and self.reta_referencia:
            return self._aplicar_modo_referencia(ponto_anterior, resultado)

        return resultado

    def _aplicar_pos_processamento(self, origem: QPointF, destino: QPointF) -> QPointF:
        if not self.canvas:
            return destino
        destino = self.canvas._snap_angular(origem, destino, travar_principais=self.tecla_w)
        destino = self.canvas._aplicar_guia_fechamento(origem, destino)
        destino = self.canvas._aplicar_guias_alinhamento(origem, destino)
        return destino

    def _adicionar_ponto(self, ponto: QPointF):
        if not self.canvas:
            return
        self._pontos_atuais.append(QPointF(ponto))
        self.canvas._pontos_reta = [QPointF(p) for p in self._pontos_atuais]
        self.canvas._preview_reta = QPointF(ponto)
        self.canvas.painel_coordenadas.atualizar_preview(
            self._pontos_atuais[-2] if len(self._pontos_atuais) >= 2 else None,
            self._pontos_atuais[-1] if len(self._pontos_atuais) >= 2 else None,
        )
        self._atualizar_feedback_apos_ponto()
        self.canvas.update()

    def _atualizar_feedback_apos_ponto(self):
        if not self.canvas:
            return
        if len(self._pontos_atuais) == 1:
            msg = "Ponto inicial definido. Continue com o próximo ponto ou clique direito para encerrar."
        else:
            comp = self._distancia(self._pontos_atuais[-2], self._pontos_atuais[-1])
            ang = self._angulo_entre(self._pontos_atuais[-2], self._pontos_atuais[-1])
            msg = f"Segmento inserido: {comp:.2f} cm | {ang:.1f}° | Pontos: {len(self._pontos_atuais)}"
        if self.canvas.lbl_status:
            self.canvas.lbl_status.setText(msg)
        if self.ui_flutuante:
            self.ui_flutuante.atualizar_status_operacao(msg)

    def _finalizar_desenho(self):
        if not self.canvas:
            return
        if len(self._pontos_atuais) < 2:
            self._resetar_estado()
            if self.canvas.lbl_status:
                self.canvas.lbl_status.setText("Reta cancelada. Defina ao menos dois pontos.")
            if self.ui_flutuante:
                self.ui_flutuante.atualizar_status_operacao("Reta cancelada. Defina ao menos dois pontos.")
            return

        pontos_finalizacao = [QPointF(p) for p in self._pontos_atuais]
        self.canvas._pontos_reta = pontos_finalizacao
        self.canvas._finalizar_reta_atual()
        self.canvas._registrar_historico()

        comprimento_total = sum(
            self._distancia(pontos_finalizacao[i], pontos_finalizacao[i + 1])
            for i in range(len(pontos_finalizacao) - 1)
        )
        msg = (
            f"Desenho finalizado com {len(pontos_finalizacao) - 1} segmento(s) | "
            f"Comprimento total {comprimento_total:.2f} cm. Clique direito novamente para sair."
        )
        self._desenhando = False
        self._terminado = True
        self._pontos_atuais = []
        self.canvas._pontos_reta = []
        self.canvas._preview_reta = None
        self.canvas.painel_coordenadas.atualizar_preview(None, None)
        if self.canvas.lbl_status:
            self.canvas.lbl_status.setText(msg)
        if self.ui_flutuante:
            self.ui_flutuante.atualizar_status_operacao(msg)
        self.canvas.update()

    def _sair_da_ferramenta(self):
        self._resetar_estado()
        if self.canvas:
            self.canvas.ferramenta_padrao_solicitada.emit("selecionar")
            if self.canvas.lbl_status:
                self.canvas.lbl_status.setText("Ferramenta Selecionar ativada")
        if self.ui_flutuante:
            self.ui_flutuante.atualizar_status_operacao("Ferramenta encerrada.")
            self.ui_flutuante.hide()

    def _selecionar_referencia_se_necessario(self, canvas: VisualizacaoCanvas, pos: QPointF) -> bool:
        if self.modo not in {"paralela", "perpendicular"}:
            return False
        if self.reta_referencia is not None:
            return False
        reta = self._encontrar_reta_sob_cursor(canvas, pos)
        if reta is None:
            if canvas.lbl_status:
                canvas.lbl_status.setText("Aproxime o cursor de uma reta para definir a referência.")
            if self.ui_flutuante:
                self.ui_flutuante.atualizar_status_operacao("Nenhuma reta de referência encontrada sob o cursor.")
            return True
        self.reta_referencia = reta
        self._aguardando_referencia = False
        msg = f"Referência definida para modo {self.modo}. Agora informe o ponto inicial."
        if canvas.lbl_status:
            canvas.lbl_status.setText(msg)
        if self.ui_flutuante:
            self.ui_flutuante.atualizar_status_operacao(msg)
        canvas._destacar_reta_temporaria = reta
        canvas.update()
        return True

    def on_mouse_press(self, canvas: VisualizacaoCanvas, event) -> bool:
        self.canvas = canvas
        pos = canvas._ponto_com_snap(event.position())

        if event.button() == Qt.LeftButton:
            if self._terminado:
                self._terminado = False
                self._desenhando = False
                self._pontos_atuais = []
                canvas._preview_reta = None

            if self._selecionar_referencia_se_necessario(canvas, pos):
                return True

            if not self._desenhando:
                self._desenhando = True
                self._terminado = False
                self._pontos_atuais = []
                self._adicionar_ponto(pos)
                return True

            ponto_anterior = self._pontos_atuais[-1]
            novo_ponto = self._aplicar_restricoes(ponto_anterior, pos)
            novo_ponto = self._aplicar_pos_processamento(ponto_anterior, novo_ponto)
            self._adicionar_ponto(novo_ponto)
            return True

        if event.button() == Qt.RightButton:
            if self._desenhando:
                self._finalizar_desenho()
            elif self._terminado:
                self._sair_da_ferramenta()
            else:
                self.reta_referencia = None
                self._aguardando_referencia = self.modo in {"paralela", "perpendicular"}
                canvas._destacar_reta_temporaria = None
                canvas.update()
            return True

        return False

    def on_mouse_move(self, canvas: VisualizacaoCanvas, event) -> bool:
        self.canvas = canvas
        pos_com_snap = canvas._ponto_com_snap(event.position())
        pos_real = canvas._tela_para_cena(event.position())

        if self.ui_flutuante:
            self.ui_flutuante.atualizar_coordenadas_mouse(pos_real.x(), pos_real.y())

        if self.modo in {"paralela", "perpendicular"} and not self.reta_referencia:
            canvas._destacar_reta_temporaria = self._encontrar_reta_sob_cursor(canvas, pos_com_snap)
        elif self.reta_referencia:
            canvas._destacar_reta_temporaria = self.reta_referencia
        else:
            canvas._destacar_reta_temporaria = None

        if self._desenhando and self._pontos_atuais:
            ponto_anterior = self._pontos_atuais[-1]
            preview = self._aplicar_restricoes(ponto_anterior, pos_com_snap)
            preview = self._aplicar_pos_processamento(ponto_anterior, preview)
            canvas._preview_reta = preview
            canvas.painel_coordenadas.atualizar_preview(ponto_anterior, preview)
            self._atualizar_status_preview(canvas, ponto_anterior, preview, pos_real)
        else:
            canvas._preview_reta = None
            canvas.painel_coordenadas.atualizar_preview(None, None)
            if canvas.lbl_status and not self._terminado:
                snap_info = f" | Snap: {canvas._snap_resultado.tipo}" if canvas._snap_resultado else ""
                if self.modo in {"paralela", "perpendicular"} and not self.reta_referencia:
                    canvas.lbl_status.setText(
                        f"Selecione uma referência | X: {pos_real.x():.2f} | Y: {pos_real.y():.2f}{snap_info}"
                    )
                else:
                    canvas.lbl_status.setText(f"Posição: X {pos_real.x():.2f} | Y {pos_real.y():.2f}{snap_info}")

        canvas.update()
        return False

    def _atualizar_status_preview(self, canvas: VisualizacaoCanvas, origem: QPointF, destino: QPointF, pos_real: QPointF):
        comp = self._distancia(origem, destino)
        ang = self._angulo_entre(origem, destino)
        trava_info = []
        if self.tecla_w:
            trava_info.append("W X/Y")
        elif self.tecla_shift:
            trava_info.append("Shift 45°")
        elif self.modo in {"horizontal", "vertical", "comprimento", "angulo", "comp_ang", "paralela", "perpendicular"}:
            trava_info.append(self.modo)
        if canvas._snap_resultado:
            trava_info.append(f"snap {canvas._snap_resultado.tipo}")
        sufixo = f" | {' | '.join(trava_info)}" if trava_info else ""
        texto = f"Prévia: {comp:.2f} cm | {ang:.1f}° | Cursor X {pos_real.x():.2f} Y {pos_real.y():.2f}{sufixo}"
        if canvas.lbl_status:
            canvas.lbl_status.setText(texto)
        if self.ui_flutuante:
            self.ui_flutuante.atualizar_status_operacao(texto)

    def on_key_press(self, canvas: VisualizacaoCanvas, event) -> bool:
        key = event.key()
        if key == Qt.Key_Shift and not event.isAutoRepeat():
            self.tecla_shift = True
            self.tecla_w = False
            if canvas.lbl_status:
                canvas.lbl_status.setText("Trava angular em 45° ativada")
            return False
        if key == Qt.Key_W and not event.isAutoRepeat():
            self.tecla_w = True
            self.tecla_shift = False
            canvas._tecla_w_trava_principal = True
            if canvas.lbl_status:
                canvas.lbl_status.setText("Trava ortogonal X/Y ativada")
            return False
        if key == Qt.Key_Escape:
            if self._desenhando or self._terminado:
                self._resetar_estado()
                if canvas.lbl_status:
                    canvas.lbl_status.setText("Desenho cancelado")
                if self.ui_flutuante:
                    self.ui_flutuante.atualizar_status_operacao("Desenho cancelado")
                canvas.update()
                return True
        return False

    def on_key_release(self, canvas: VisualizacaoCanvas, event) -> bool:
        key = event.key()
        if key == Qt.Key_Shift and not event.isAutoRepeat():
            self.tecla_shift = False
            if canvas.lbl_status and not self.tecla_w:
                canvas.lbl_status.setText("Trava angular liberada")
            return False
        if key == Qt.Key_W and not event.isAutoRepeat():
            self.tecla_w = False
            canvas._tecla_w_trava_principal = False
            if canvas.lbl_status:
                canvas.lbl_status.setText("Trava ortogonal liberada")
            return False
        return False

    def on_paint_overlay(self, canvas: VisualizacaoCanvas, painter: QPainter):
        if self._pontos_atuais:
            self._desenhar_vertices(canvas, painter)
            self._desenhar_segmentos_confirmados(canvas, painter)

        if self._desenhando and self._pontos_atuais and canvas._preview_reta:
            self._desenhar_preview(canvas, painter)

        if self.reta_referencia and self.modo in {"paralela", "perpendicular"}:
            pen = QPen(QColor("#ffb649"), max(2.0, 2.0 * canvas.zoom * 0.02), Qt.DashDotLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(
                canvas._cena_para_tela(self.reta_referencia[0]), canvas._cena_para_tela(self.reta_referencia[1])
            )

        if canvas._snap_ativo and canvas._snap_resultado:
            snap_tela = canvas._cena_para_tela(canvas._snap_resultado.ponto)
            painter.setPen(QPen(QColor("#ff8c2b"), 2))
            painter.setBrush(QColor(255, 140, 43, 55))
            painter.drawEllipse(snap_tela, 7, 7)

    def _desenhar_vertices(self, canvas: VisualizacaoCanvas, painter: QPainter):
        for i, ponto in enumerate(self._pontos_atuais):
            pt_tela = canvas._cena_para_tela(ponto)
            cor = QColor("#24b26b") if i == 0 else QColor("#2f88ff")
            painter.setPen(QPen(cor, 2))
            painter.setBrush(QColor(cor.red(), cor.green(), cor.blue(), 90))
            painter.drawEllipse(pt_tela, 5, 5)
            painter.setPen(QColor("#ffffff"))
            font = QFont("Arial", 8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(int(pt_tela.x() + 6), int(pt_tela.y() - 6), str(i + 1))

    def _desenhar_segmentos_confirmados(self, canvas: VisualizacaoCanvas, painter: QPainter):
        if len(self._pontos_atuais) < 2:
            return
        pen = QPen(QColor("#5ed0ff"), 2.0, Qt.SolidLine)
        painter.setPen(pen)
        for i in range(len(self._pontos_atuais) - 1):
            painter.drawLine(canvas._cena_para_tela(self._pontos_atuais[i]), canvas._cena_para_tela(self._pontos_atuais[i + 1]))

    def _desenhar_preview(self, canvas: VisualizacaoCanvas, painter: QPainter):
        origem = self._pontos_atuais[-1]
        destino = canvas._preview_reta
        if destino is None:
            return
        pen = QPen(QColor("#8fe1ff"), 2.0, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(canvas._cena_para_tela(origem), canvas._cena_para_tela(destino))

        comp = self._distancia(origem, destino)
        ang = self._angulo_entre(origem, destino)
        meio = QPointF((origem.x() + destino.x()) / 2.0, (origem.y() + destino.y()) / 2.0)
        meio_tela = canvas._cena_para_tela(meio)
        texto = f"{comp:.2f} cm  |  {ang:.1f}°"

        font = QFont("Arial", 8)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        largura = metrics.horizontalAdvance(texto)
        painter.fillRect(
            int(meio_tela.x() - (largura / 2) - 6), int(meio_tela.y() - 11), largura + 12, 20, QColor(8, 18, 28, 215)
        )
        painter.setPen(QColor("#ffd47d"))
        painter.drawText(int(meio_tela.x() - (largura / 2)), int(meio_tela.y() + 4), texto)

        if self.tecla_shift:
            raio = max(18.0, 18.0 * canvas.zoom * 0.04)
            painter.setPen(QPen(QColor("#ff9e3d"), 1.2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(canvas._cena_para_tela(origem), raio, raio)

        if self.tecla_w or self.modo in {"horizontal", "vertical"}:
            origem_tela = canvas._cena_para_tela(origem)
            destino_tela = canvas._cena_para_tela(destino)
            painter.setPen(QPen(QColor("#6bd3b5"), 1.2, Qt.DotLine))
            painter.drawLine(origem_tela.x(), origem_tela.y(), destino_tela.x(), origem_tela.y())
            painter.drawLine(origem_tela.x(), origem_tela.y(), origem_tela.x(), destino_tela.y())

    def _encontrar_reta_sob_cursor(self, canvas: VisualizacaoCanvas, pos: QPointF) -> tuple[QPointF, QPointF] | None:
        tolerancia = 10.0 / max(canvas.zoom, 0.001)
        melhor_dist = tolerancia
        melhor_reta = None
        for el in canvas.cena.elementos:
            if el.get("tipo") != "polyline":
                continue
            pontos = el.get("pontos", [])
            if len(pontos) < 2:
                continue
            for idx in range(len(pontos) - 1):
                p1 = QPointF(float(pontos[idx][0]), float(pontos[idx][1]))
                p2 = QPointF(float(pontos[idx + 1][0]), float(pontos[idx + 1][1]))
                dist = self._distancia_ponto_segmento(p1, p2, pos)
                if dist < melhor_dist:
                    melhor_dist = dist
                    melhor_reta = (p1, p2)
        return melhor_reta

    def _distancia_ponto_segmento(self, a: QPointF, b: QPointF, p: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 0.0001:
            return self._distancia(a, p)
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return self._distancia(proj, p)

    def _distancia(self, p1: QPointF, p2: QPointF) -> float:
        return sqrt(((p2.x() - p1.x()) ** 2) + ((p2.y() - p1.y()) ** 2))

    def _angulo_entre(self, p1: QPointF, p2: QPointF) -> float:
        ang = degrees(atan2(p2.y() - p1.y(), p2.x() - p1.x()))
        return ang if ang >= 0 else ang + 360.0
