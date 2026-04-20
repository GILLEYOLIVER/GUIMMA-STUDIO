from __future__ import annotations

from math import atan2, cos, degrees, radians, sin, sqrt
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QDoubleSpinBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)

from tools.tool_base import FerramentaBase

if TYPE_CHECKING:
    from canvas.visualizacao import VisualizacaoCanvas


class RetaToolUI(QFrame):
    modo_changed = Signal(str)
    valor_changed = Signal(float, float)
    delta_changed = Signal(float, float)
    fechado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle("Reta - Opções")

        self.setStyleSheet("""
            QFrame {
                background: #2c3e50;
                border-radius: 8px;
                color: white;
                font-size: 12px;
            }
            QLabel { color: #ecf0f1; }
            QDoubleSpinBox, QLineEdit {
                background: #34495e;
                border: 1px solid #1abc9c;
                border-radius: 4px;
                padding: 4px 6px;
                color: white;
            }
            QDoubleSpinBox:focus, QLineEdit:focus { border: 1px solid #e67e22; }
            QPushButton, QToolButton {
                background: #1abc9c;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover, QToolButton:hover { background: #16a085; }
            QPushButton:checked, QToolButton:checked { background: #e67e22; }
            QPushButton#closeBtn {
                background: #e74c3c;
                padding: 2px 6px;
                font-size: 14px;
            }
            QPushButton#closeBtn:hover { background: #c0392b; }
            #mouseCoord {
                background: #1a252f;
                border: 1px solid #1abc9c;
                border-radius: 4px;
                padding: 4px;
                font-family: monospace;
                font-size: 11px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Cabeçalho
        header = QHBoxLayout()
        titulo = QLabel("<b>FERRAMENTA RETA</b>")
        titulo.setStyleSheet("color: #1abc9c; font-size: 13px;")
        header.addWidget(titulo, 1)

        self.btn_fechar = QPushButton("✕")
        self.btn_fechar.setObjectName("closeBtn")
        self.btn_fechar.setFixedSize(24, 24)
        self.btn_fechar.setCursor(Qt.PointingHandCursor)
        self.btn_fechar.clicked.connect(self.fechar)
        header.addWidget(self.btn_fechar)
        layout.addLayout(header)

        # Coordenadas do mouse
        lbl_mouse = QLabel("📍 POSIÇÃO DO MOUSE:")
        lbl_mouse.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(lbl_mouse)

        self.mouse_coord_label = QLabel("X: 0.00 cm  |  Y: 0.00 cm")
        self.mouse_coord_label.setObjectName("mouseCoord")
        self.mouse_coord_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.mouse_coord_label)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #34495e; max-height: 1px;")
        layout.addWidget(sep)

        # Modos de desenho
        lbl_modo = QLabel("MODO DE DESENHO:")
        lbl_modo.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(lbl_modo)

        grid_modos = QGridLayout()
        grid_modos.setSpacing(4)

        self.btn_livre = QPushButton("📏 Livre")
        self.btn_livre.setCheckable(True)
        self.btn_livre.setChecked(True)

        self.btn_comprimento = QPushButton("📐 Compr.")
        self.btn_comprimento.setCheckable(True)

        self.btn_angulo = QPushButton("↺ Ângulo")
        self.btn_angulo.setCheckable(True)

        self.btn_comp_ang = QPushButton("⚡ Comp+Âng")
        self.btn_comp_ang.setCheckable(True)

        self.btn_paralela = QPushButton("‖ Paralela")
        self.btn_paralela.setCheckable(True)

        self.btn_perpendicular = QPushButton("⟂ Perp.")
        self.btn_perpendicular.setCheckable(True)

        self.btn_horizontal = QPushButton("— Horizontal")
        self.btn_horizontal.setCheckable(True)

        self.btn_vertical = QPushButton("| Vertical")
        self.btn_vertical.setCheckable(True)

        for btn in (self.btn_livre, self.btn_comprimento, self.btn_angulo,
                    self.btn_comp_ang, self.btn_paralela, self.btn_perpendicular,
                    self.btn_horizontal, self.btn_vertical):
            btn.setCursor(Qt.PointingHandCursor)

        grid_modos.addWidget(self.btn_livre, 0, 0)
        grid_modos.addWidget(self.btn_comprimento, 0, 1)
        grid_modos.addWidget(self.btn_angulo, 0, 2)
        grid_modos.addWidget(self.btn_comp_ang, 1, 0)
        grid_modos.addWidget(self.btn_paralela, 1, 1)
        grid_modos.addWidget(self.btn_perpendicular, 1, 2)
        grid_modos.addWidget(self.btn_horizontal, 2, 0)
        grid_modos.addWidget(self.btn_vertical, 2, 1)
        layout.addLayout(grid_modos)

        # Separador
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background-color: #34495e; max-height: 1px;")
        layout.addWidget(sep2)

        # Entrada de valores
        lbl_entrada = QLabel("DESENHAR POR VALORES:")
        lbl_entrada.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_entrada)

        valores_layout = QGridLayout()
        valores_layout.setSpacing(4)

        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setRange(-10000, 10000)
        self.spin_dx.setValue(10.0)
        self.spin_dx.setSuffix(" cm")
        self.spin_dx.setDecimals(2)

        self.spin_dy = QDoubleSpinBox()
        self.spin_dy.setRange(-10000, 10000)
        self.spin_dy.setValue(0.0)
        self.spin_dy.setSuffix(" cm")
        self.spin_dy.setDecimals(2)

        self.spin_comprimento = QDoubleSpinBox()
        self.spin_comprimento.setRange(0.01, 10000.0)
        self.spin_comprimento.setValue(10.0)
        self.spin_comprimento.setSuffix(" cm")
        self.spin_comprimento.setDecimals(2)

        self.spin_angulo = QDoubleSpinBox()
        self.spin_angulo.setRange(-360, 360)
        self.spin_angulo.setValue(0.0)
        self.spin_angulo.setSuffix("°")
        self.spin_angulo.setDecimals(1)

        valores_layout.addWidget(QLabel("ΔX:"), 0, 0)
        valores_layout.addWidget(self.spin_dx, 0, 1)
        valores_layout.addWidget(QLabel("ΔY:"), 1, 0)
        valores_layout.addWidget(self.spin_dy, 1, 1)
        valores_layout.addWidget(QLabel("Comp.:"), 2, 0)
        valores_layout.addWidget(self.spin_comprimento, 2, 1)
        valores_layout.addWidget(QLabel("Ângulo:"), 3, 0)
        valores_layout.addWidget(self.spin_angulo, 3, 1)

        self.btn_aplicar = QPushButton("✓ Aplicar Valores")
        self.btn_aplicar.clicked.connect(self._aplicar_valores)
        valores_layout.addWidget(self.btn_aplicar, 4, 0, 1, 2)
        layout.addLayout(valores_layout)

        # Dicas
        dicas = QLabel(
            "💡 Dicas:\n"
            "• Clique esquerdo: marca ponto\n"
            "• Clique direito: termina desenho\n"
            "• Shift: trava ângulos de 15°\n"
            "• W: trava eixos X/Y\n"
            "• Após terminar, clique direito novamente para sair"
        )
        dicas.setStyleSheet("color: #7f8c8d; font-size: 10px; margin-top: 6px;")
        dicas.setWordWrap(True)
        layout.addWidget(dicas)

        self.modo_atual = "livre"
        self._conectar_sinais()

    def _conectar_sinais(self):
        self.btn_livre.toggled.connect(lambda ch: ch and self._set_modo("livre"))
        self.btn_comprimento.toggled.connect(lambda ch: ch and self._set_modo("comprimento"))
        self.btn_angulo.toggled.connect(lambda ch: ch and self._set_modo("angulo"))
        self.btn_comp_ang.toggled.connect(lambda ch: ch and self._set_modo("comp_ang"))
        self.btn_paralela.toggled.connect(lambda ch: ch and self._set_modo("paralela"))
        self.btn_perpendicular.toggled.connect(lambda ch: ch and self._set_modo("perpendicular"))
        self.btn_horizontal.toggled.connect(lambda ch: ch and self._set_modo("horizontal"))
        self.btn_vertical.toggled.connect(lambda ch: ch and self._set_modo("vertical"))

    def _set_modo(self, modo: str):
        self.modo_atual = modo
        self.modo_changed.emit(modo)

    def _aplicar_valores(self):
        if self.modo_atual in ("comprimento", "comp_ang"):
            comp = self.spin_comprimento.value()
            ang = self.spin_angulo.value()
            self.valor_changed.emit(comp, ang)
        else:
            dx = self.spin_dx.value()
            dy = self.spin_dy.value()
            self.delta_changed.emit(dx, dy)

    def atualizar_coordenadas_mouse(self, x: float, y: float):
        self.mouse_coord_label.setText(f"X: {x:.2f} cm  |  Y: {y:.2f} cm")

    def showEvent(self, event):
        cursor = QApplication.cursor().pos()
        self.move(cursor.x() + 30, cursor.y() + 30)
        super().showEvent(event)

    def fechar(self):
        self.hide()
        self.fechado.emit()


class Ferramenta(FerramentaBase):
    id_ferramenta = "reta"
    nome = "Reta"

    # Ângulos principais para snap (0, 45, 90, 135, 180, 225, 270, 315)
    ANGULOS_PRINCIPAIS = [0, 45, 90, 135, 180, 225, 270, 315]

    def __init__(self):
        super().__init__()
        self.modo = "livre"
        self.comprimento_fixo = 10.0
        self.angulo_fixo = 0.0
        self.reta_referencia = None
        self.ui_flutuante = None
        self.canvas = None
        self.tecla_shift = False
        self.tecla_w = False

        # Estados da ferramenta
        self._desenhando = False  # True quando está desenhando (pontos sendo adicionados)
        self._terminado = False  # True quando o desenho foi terminado (primeiro clique direito)
        self._pontos_atuais = []  # Lista de pontos do desenho atual

    def ativar(self) -> str:
        self.criar_interface()
        self._resetar_estado()
        return "Reta ativada. Clique esquerdo para começar. Clique direito para terminar."

    def desativar(self):
        if self.ui_flutuante:
            self.ui_flutuante.fechar()
            self.ui_flutuante = None
        self._resetar_estado()
        super().desativar()

    def criar_interface(self):
        if self.ui_flutuante is None:
            self.ui_flutuante = RetaToolUI()
            self.ui_flutuante.modo_changed.connect(self._definir_modo)
            self.ui_flutuante.valor_changed.connect(self._aplicar_valores_polar)
            self.ui_flutuante.delta_changed.connect(self._aplicar_valores_delta)
            self.ui_flutuante.fechado.connect(self._ui_fechado)
        self.ui_flutuante.show()

    def _ui_fechado(self):
        self.ui_flutuante = None

    def _definir_modo(self, modo: str):
        self.modo = modo
        if not self._desenhando:
            self._resetar_estado()
        if self.canvas:
            self.canvas.update()

    def _aplicar_valores_polar(self, comprimento: float, angulo: float):
        self.comprimento_fixo = comprimento
        self.angulo_fixo = angulo
        if self._desenhando and self._pontos_atuais:
            origem = self._pontos_atuais[-1]
            rad = radians(angulo)
            dx = cos(rad) * comprimento
            dy = sin(rad) * comprimento
            destino = QPointF(origem.x() + dx, origem.y() + dy)
            self._adicionar_ponto(destino)

    def _aplicar_valores_delta(self, dx: float, dy: float):
        if self._desenhando and self._pontos_atuais:
            origem = self._pontos_atuais[-1]
            destino = QPointF(origem.x() + dx, origem.y() + dy)
            self._adicionar_ponto(destino)

    def _resetar_estado(self):
        """Reseta completamente o estado da ferramenta"""
        self._desenhando = False
        self._terminado = False
        self._pontos_atuais = []
        self.reta_referencia = None
        if self.canvas:
            self.canvas._pontos_reta = []
            self.canvas._preview_reta = None
            self.canvas._guia_fechamento = None
            self.canvas._guias_alinhamento = []
            self.canvas._destacar_reta_temporaria = None
            self.canvas.update()

    def _travar_angulo_principal(self, ponto_anterior: QPointF, ponto_atual: QPointF) -> QPointF:
        """
        Trava o ângulo nos principais (0°, 45°, 90°, 135°, etc.)
        Retorna o ponto travado
        """
        dx = ponto_atual.x() - ponto_anterior.x()
        dy = ponto_atual.y() - ponto_anterior.y()

        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return ponto_atual

        # Calcula o ângulo em graus
        angulo = degrees(atan2(dy, dx))
        # Normaliza para 0-360
        angulo = angulo % 360

        # Encontra o ângulo principal mais próximo
        angulo_mais_proximo = min(self.ANGULOS_PRINCIPAIS, key=lambda a: min(abs(angulo - a), 360 - abs(angulo - a)))

        # Tolerância de 7.5 graus (metade de 15)
        diferenca = min(abs(angulo - angulo_mais_proximo), 360 - abs(angulo - angulo_mais_proximo))

        if diferenca <= 7.5:
            # Trava no ângulo principal
            comprimento = sqrt(dx * dx + dy * dy)
            rad = radians(angulo_mais_proximo)
            novo_dx = cos(rad) * comprimento
            novo_dy = sin(rad) * comprimento
            return QPointF(ponto_anterior.x() + novo_dx, ponto_anterior.y() + novo_dy)

        return ponto_atual

    def _aplicar_restricoes(self, ponto_anterior: QPointF, ponto: QPointF) -> QPointF:
        """Aplica todas as restrições baseadas no modo e teclas pressionadas"""
        resultado = ponto

        # Prioridade: W > Shift > Modos
        if self.tecla_w:
            # Trava nos eixos X/Y (horizontal/vertical)
            dx = resultado.x() - ponto_anterior.x()
            dy = resultado.y() - ponto_anterior.y()
            if abs(dx) > abs(dy):
                resultado = QPointF(resultado.x(), ponto_anterior.y())
            else:
                resultado = QPointF(ponto_anterior.x(), resultado.y())

        elif self.tecla_shift:
            # Trava nos ângulos principais (0,45,90,135,180,225,270,315)
            resultado = self._travar_angulo_principal(ponto_anterior, resultado)

        elif self.modo == "horizontal":
            resultado = QPointF(resultado.x(), ponto_anterior.y())

        elif self.modo == "vertical":
            resultado = QPointF(ponto_anterior.x(), resultado.y())

        elif self.modo == "comprimento":
            vetor = resultado - ponto_anterior
            if vetor.length() > 0:
                ang = atan2(vetor.y(), vetor.x())
                dx = cos(ang) * self.comprimento_fixo
                dy = sin(ang) * self.comprimento_fixo
                resultado = QPointF(ponto_anterior.x() + dx, ponto_anterior.y() + dy)

        elif self.modo == "angulo":
            vetor = resultado - ponto_anterior
            if vetor.length() > 0:
                comp = vetor.length()
                rad = radians(self.angulo_fixo)
                dx = cos(rad) * comp
                dy = sin(rad) * comp
                resultado = QPointF(ponto_anterior.x() + dx, ponto_anterior.y() + dy)

        elif self.modo == "comp_ang":
            rad = radians(self.angulo_fixo)
            dx = cos(rad) * self.comprimento_fixo
            dy = sin(rad) * self.comprimento_fixo
            resultado = QPointF(ponto_anterior.x() + dx, ponto_anterior.y() + dy)

        return resultado

    def _adicionar_ponto(self, ponto: QPointF):
        """Adiciona um ponto ao desenho atual"""
        self._pontos_atuais.append(ponto)
        self.canvas._pontos_reta = self._pontos_atuais.copy()
        self.canvas.update()

        if self.canvas.lbl_status:
            if len(self._pontos_atuais) == 1:
                self.canvas.lbl_status.setText(
                    "📌 Ponto inicial. Clique esquerdo para continuar, direito para terminar.")
            else:
                comp = self._distancia(self._pontos_atuais[-2], self._pontos_atuais[-1])
                ang = self._angulo_entre(self._pontos_atuais[-2], self._pontos_atuais[-1])
                self.canvas.lbl_status.setText(
                    f"📌 Ponto {len(self._pontos_atuais)} | Seg: {comp:.2f} cm | Âng: {ang:.0f}°")

    def _finalizar_desenho(self):
        """Finaliza o desenho atual e cria as retas (primeiro clique direito)"""
        if len(self._pontos_atuais) < 2:
            self._resetar_estado()
            return

        # Cria as retas usando o método existente do canvas
        self.canvas._pontos_reta = self._pontos_atuais.copy()
        self.canvas._finalizar_reta_atual()
        self.canvas._registrar_historico()

        comp_total = 0
        for i in range(len(self._pontos_atuais) - 1):
            comp_total += self._distancia(self._pontos_atuais[i], self._pontos_atuais[i + 1])

        if self.canvas.lbl_status:
            self.canvas.lbl_status.setText(
                f"✅ Desenho finalizado! {len(self._pontos_atuais)} pontos, {comp_total:.2f} cm total. "
                f"Clique direito novamente para sair da ferramenta."
            )

        # Marca como terminado, mas NÃO sai da ferramenta ainda
        self._desenhando = False
        self._terminado = True
        self._pontos_atuais = []
        self.canvas._pontos_reta = []
        self.canvas.update()

    def _sair_da_ferramenta(self):
        """Sai completamente da ferramenta e volta para selecionar (segundo clique direito)"""
        self._resetar_estado()
        if self.canvas:
            self.canvas.ferramenta_padrao_solicitada.emit("selecionar")
            if self.canvas.lbl_status:
                self.canvas.lbl_status.setText("🔧 Ferramenta Selecionar ativada")

    def on_mouse_press(self, canvas: VisualizacaoCanvas, event) -> bool:
        self.canvas = canvas
        pos = canvas._ponto_com_snap(event.position())

        if event.button() == Qt.LeftButton:
            # Se está terminado, ignora clique esquerdo (apenas direito sai)
            if self._terminado:
                return True

            # Se não está desenhando, começa um novo desenho
            if not self._desenhando:
                self._resetar_estado()
                self._desenhando = True
                self._terminado = False
                self._adicionar_ponto(pos)
            else:
                # Está desenhando, adiciona um novo ponto com restrições
                ponto_anterior = self._pontos_atuais[-1]
                novo_ponto = self._aplicar_restricoes(ponto_anterior, pos)

                # Aplica snaps finais
                novo_ponto = canvas._snap_angular(ponto_anterior, novo_ponto,
                                                  travar_principais=self.tecla_w)
                novo_ponto = canvas._aplicar_guia_fechamento(ponto_anterior, novo_ponto)
                novo_ponto = canvas._aplicar_guias_alinhamento(ponto_anterior, novo_ponto)

                self._adicionar_ponto(novo_ponto)

            return True

        elif event.button() == Qt.RightButton:
            # Primeiro clique direito: finaliza o desenho
            if self._desenhando:
                self._finalizar_desenho()
            # Segundo clique direito: sai da ferramenta
            elif self._terminado:
                self._sair_da_ferramenta()
            return True

        return False

    def on_mouse_move(self, canvas: VisualizacaoCanvas, event) -> bool:
        self.canvas = canvas

        pos_com_snap = canvas._ponto_com_snap(event.position())
        pos_real = canvas._tela_para_cena(event.position())

        # Atualiza coordenadas do mouse na UI
        if self.ui_flutuante:
            self.ui_flutuante.atualizar_coordenadas_mouse(pos_real.x(), pos_real.y())

        # Se está desenhando, mostra preview do próximo segmento com restrições
        if self._desenhando and self._pontos_atuais:
            ponto_anterior = self._pontos_atuais[-1]
            preview = self._aplicar_restricoes(ponto_anterior, pos_com_snap)

            canvas._preview_reta = preview

            # Atualiza status
            if canvas.lbl_status:
                comp = self._distancia(ponto_anterior, preview)
                ang = self._angulo_entre(ponto_anterior, preview)

                trava_info = ""
                if self.tecla_w:
                    trava_info = " | 🔒 W: Eixos X/Y"
                elif self.tecla_shift:
                    trava_info = " | 🔒 Shift: 45°"
                elif self.modo in ("horizontal", "vertical"):
                    trava_info = f" | Modo: {self.modo}"
                elif self.modo in ("comprimento", "angulo", "comp_ang"):
                    trava_info = f" | Modo: {self.modo}"

                canvas.lbl_status.setText(
                    f"Desenhando | Próx: {comp:.2f} cm | Âng: {ang:.0f}° | "
                    f"Pontos: {len(self._pontos_atuais)}{trava_info}"
                )
        else:
            canvas._preview_reta = None

            # Destaca reta para modos paralela/perpendicular
            if self.modo in ("paralela", "perpendicular") and not self._desenhando and not self._terminado:
                canvas._destacar_reta_temporaria = self._encontrar_reta_sob_cursor(canvas, pos_com_snap)
            else:
                canvas._destacar_reta_temporaria = None

            if canvas.lbl_status:
                if self._terminado:
                    canvas.lbl_status.setText("✅ Desenho finalizado! Clique direito para sair da ferramenta.")
                else:
                    snap_info = f" | Snap: {canvas._snap_resultado.tipo}" if canvas._snap_resultado else ""
                    canvas.lbl_status.setText(f"Posição: X: {pos_real.x():.2f} | Y: {pos_real.y():.2f}{snap_info}")

        canvas.update()
        return False

    def on_key_press(self, canvas: VisualizacaoCanvas, event) -> bool:
        key = event.key()
        if key == Qt.Key_Shift:
            self.tecla_shift = True
            self.tecla_w = False
            if canvas.lbl_status:
                canvas.lbl_status.setText("🔒 Shift: travando ângulos de 45° (0,45,90,135...)")
        elif key == Qt.Key_W:
            self.tecla_w = True
            self.tecla_shift = False
            canvas._tecla_w_trava_principal = True
            if canvas.lbl_status:
                canvas.lbl_status.setText("🔒 W: travando eixos X/Y (horizontal/vertical)")
        elif key == Qt.Key_Escape:
            if self._desenhando:
                self._resetar_estado()
                if canvas.lbl_status:
                    canvas.lbl_status.setText("❌ Desenho cancelado")
            elif self._terminado:
                self._sair_da_ferramenta()
            else:
                self._resetar_estado()
            canvas.update()
        return False

    def on_key_release(self, canvas: VisualizacaoCanvas, event) -> bool:
        key = event.key()
        if key == Qt.Key_Shift:
            self.tecla_shift = False
            if canvas.lbl_status and not self.tecla_w:
                canvas.lbl_status.setText("✅ Shift liberado")
        elif key == Qt.Key_W:
            self.tecla_w = False
            canvas._tecla_w_trava_principal = False
            if canvas.lbl_status:
                canvas.lbl_status.setText("✅ W liberado")
        return False

    def on_paint_overlay(self, canvas: VisualizacaoCanvas, painter: QPainter):
        # Desenha os pontos já marcados
        if self._pontos_atuais:
            for i, ponto in enumerate(self._pontos_atuais):
                pt_tela = canvas._cena_para_tela(ponto)
                cor = QColor("#1abc9c") if i == 0 else QColor("#3498db")
                painter.setPen(QPen(cor, 2))
                painter.setBrush(QColor(cor.red(), cor.green(), cor.blue(), 100))
                painter.drawEllipse(pt_tela, 6, 6)

                # Número do ponto
                painter.setPen(QColor("#ffffff"))
                font = QFont("Arial", 8)
                painter.setFont(font)
                painter.drawText(int(pt_tela.x() - 8), int(pt_tela.y() - 8), str(i + 1))

        # Desenha as linhas já definidas
        if len(self._pontos_atuais) >= 2:
            pen = QPen(QColor("#1abc9c"), 2, Qt.SolidLine)
            painter.setPen(pen)
            for i in range(len(self._pontos_atuais) - 1):
                painter.drawLine(
                    canvas._cena_para_tela(self._pontos_atuais[i]),
                    canvas._cena_para_tela(self._pontos_atuais[i + 1])
                )

        # Desenha preview do próximo segmento
        if self._desenhando and self._pontos_atuais and canvas._preview_reta:
            pen = QPen(QColor("#00aaff"), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(
                canvas._cena_para_tela(self._pontos_atuais[-1]),
                canvas._cena_para_tela(canvas._preview_reta)
            )

            # Informações do preview
            comp = self._distancia(self._pontos_atuais[-1], canvas._preview_reta)
            ang = self._angulo_entre(self._pontos_atuais[-1], canvas._preview_reta)
            mid = (self._pontos_atuais[-1] + canvas._preview_reta) / 2
            mid_tela = canvas._cena_para_tela(mid)

            painter.setPen(QColor("#ffffff"))
            font = QFont("Arial", 8)
            painter.setFont(font)
            texto = f"{comp:.1f} cm | {ang:.0f}°"
            metrics = QFontMetrics(font)
            tw = metrics.horizontalAdvance(texto)
            painter.fillRect(
                int(mid_tela.x() - tw / 2 - 4),
                int(mid_tela.y() - 8),
                tw + 8, 16,
                QColor(0, 0, 0, 180)
            )
            painter.setPen(QColor("#ffaa44"))
            painter.drawText(
                int(mid_tela.x() - tw / 2),
                int(mid_tela.y() + 4),
                texto
            )

            # Desenha círculo de ângulo para indicar trava
            if self.tecla_shift:
                # Desenha círculo tracejado ao redor do ponto anterior
                raio = 20 / canvas.zoom
                centro = canvas._cena_para_tela(self._pontos_atuais[-1])
                pen = QPen(QColor("#ff6600"), 1, Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(centro, raio, raio)

        # Reta de referência destacada
        if self.reta_referencia and self.modo in ("paralela", "perpendicular"):
            pen = QPen(QColor("#ffaa00"), 3, Qt.DashDotLine)
            painter.setPen(pen)
            painter.drawLine(
                canvas._cena_para_tela(self.reta_referencia[0]),
                canvas._cena_para_tela(self.reta_referencia[1])
            )

        # Indicador de snap
        if canvas._snap_ativo and canvas._snap_resultado:
            snap_pt = canvas._snap_resultado.ponto
            snap_tela = canvas._cena_para_tela(snap_pt)
            pen = QPen(QColor("#ff6600"), 2)
            painter.setPen(pen)
            painter.setBrush(QColor(255, 102, 0, 80))
            painter.drawEllipse(snap_tela, 8, 8)

    # ========== Métodos auxiliares ==========

    def _encontrar_reta_sob_cursor(self, canvas: VisualizacaoCanvas, pos: QPointF):
        tol = 10.0 / canvas.zoom
        melhor_dist = tol
        melhor_reta = None

        for el in canvas.cena.elementos:
            if el.get("tipo") == "polyline":
                pontos = el.get("pontos", [])
                if len(pontos) >= 2:
                    p1 = QPointF(pontos[0][0], pontos[0][1])
                    p2 = QPointF(pontos[1][0], pontos[1][1])
                    dist = self._distancia_ponto_reta(p1, p2, pos)
                    if dist < melhor_dist:
                        melhor_dist = dist
                        melhor_reta = (p1, p2)

        return melhor_reta

    def _distancia_ponto_reta(self, a: QPointF, b: QPointF, p: QPointF) -> float:
        if (b - a).length() < 0.001:
            return (p - a).length()
        numer = abs((b.x() - a.x()) * (a.y() - p.y()) - (a.x() - p.x()) * (b.y() - a.y()))
        denom = sqrt((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2)
        return numer / denom

    def _distancia(self, p1: QPointF, p2: QPointF) -> float:
        return sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2)

    def _angulo_entre(self, p1: QPointF, p2: QPointF) -> float:
        ang = degrees(atan2(p2.y() - p1.y(), p2.x() - p1.x()))
        return ang if ang >= 0 else ang + 360