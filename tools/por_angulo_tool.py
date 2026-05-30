from __future__ import annotations

from math import cos, radians, sin, sqrt

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
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
from ui.posicao_janelas import restaurar_posicao, salvar_posicao


class _PainelPorAngulo(QFrame):
    def __init__(self, ferramenta: "Ferramenta", parent: QWidget | None = None):
        super().__init__(parent)
        self.ferramenta = ferramenta
        self.setObjectName("PainelPorAngulo")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setFixedWidth(300)
        self._margem_canvas = 12
        self._drag_offset_local: QPoint | None = None
        self._chave_posicao = "painel:por_angulo"

        self.setStyleSheet(
            """
            QFrame#PainelPorAngulo {
                background: #f5f7fa;
                border: 1px solid #c8d2dc;
                border-radius: 10px;
                color: #16202a;
            }
            QLabel#titulo { color: #0f4f86; font-size: 13px; font-weight: 700; }
            QLabel#descricao { color: #4c5d6f; font-size: 11px; }
            QLabel#status {
                background: #ffffff;
                border: 1px solid #d6dee6;
                border-radius: 6px;
                padding: 6px;
                color: #1f2d3a;
                font-size: 11px;
            }
            QLabel#rotuloCampo { color:#1f2d3a; font-size: 11px; font-weight: 600; }
            QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #c8d2dc;
                border-radius: 5px;
                padding: 3px;
                min-height: 22px;
                color:#17212b;
            }
            QCheckBox { color:#1f2d3a; font-size: 11px; }
            QPushButton#fechar {
                background: #ffffff;
                border: 1px solid #c8d2dc;
                border-radius: 4px;
                color: #41566b;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                font-weight: 700;
            }
            QPushButton#fechar:hover { background: #e9eef4; border-color: #aebdcb; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        cabecalho = QHBoxLayout()
        cabecalho.setContentsMargins(0, 0, 0, 0)
        titulo = QLabel("Por Ângulo")
        titulo.setObjectName("titulo")
        cabecalho.addWidget(titulo, 1)
        btn_fechar = QPushButton("×")
        btn_fechar.setObjectName("fechar")
        btn_fechar.setToolTip("Fechar painel")
        btn_fechar.clicked.connect(self.hide)
        cabecalho.addWidget(btn_fechar, 0, Qt.AlignRight)
        layout.addLayout(cabecalho)

        descricao = QLabel("Clique o ponto inicial. A reta será criada no ângulo informado.")
        descricao.setObjectName("descricao")
        descricao.setWordWrap(True)
        layout.addWidget(descricao)

        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)

        lbl_ang = QLabel("Ângulo")
        lbl_ang.setObjectName("rotuloCampo")
        self.spn_angulo = QDoubleSpinBox()
        self.spn_angulo.setRange(-3600.0, 3600.0)
        self.spn_angulo.setDecimals(2)
        self.spn_angulo.setSingleStep(1.0)
        self.spn_angulo.setSuffix("°")
        self.spn_angulo.setKeyboardTracking(False)

        lbl_comp = QLabel("Comprimento")
        lbl_comp.setObjectName("rotuloCampo")
        self.spn_comprimento = QDoubleSpinBox()
        self.spn_comprimento.setRange(0.001, 100000.0)
        self.spn_comprimento.setDecimals(3)
        self.spn_comprimento.setSingleStep(1.0)
        self.spn_comprimento.setKeyboardTracking(False)

        grid.addWidget(lbl_ang, 0, 0)
        grid.addWidget(self.spn_angulo, 0, 1)
        grid.addWidget(lbl_comp, 1, 0)
        grid.addWidget(self.spn_comprimento, 1, 1)
        layout.addLayout(grid)

        self.chk_comprimento_fixo = QCheckBox("Usar comprimento fixo")
        layout.addWidget(self.chk_comprimento_fixo)

        self.status_lbl = QLabel("Ferramenta pronta.")
        self.status_lbl.setObjectName("status")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.status_lbl.setMinimumHeight(62)
        layout.addWidget(self.status_lbl)

        self.spn_angulo.valueChanged.connect(self._alterou_config)
        self.spn_comprimento.valueChanged.connect(self._alterou_config)
        self.chk_comprimento_fixo.toggled.connect(self._alterou_config)

    def carregar(self, angulo: float, comprimento: float, fixo: bool, unidade: str) -> None:
        self.spn_angulo.blockSignals(True)
        self.spn_comprimento.blockSignals(True)
        self.chk_comprimento_fixo.blockSignals(True)
        try:
            self.spn_angulo.setValue(float(angulo))
            self.spn_comprimento.setValue(max(0.001, float(comprimento)))
            self.chk_comprimento_fixo.setChecked(bool(fixo))
            self.spn_comprimento.setSuffix(f" {unidade or 'cm'}")
        finally:
            self.spn_angulo.blockSignals(False)
            self.spn_comprimento.blockSignals(False)
            self.chk_comprimento_fixo.blockSignals(False)

    def atualizar_status(self, texto: str) -> None:
        self.status_lbl.setText(str(texto or ""))

    def _alterou_config(self, *_args) -> None:
        self.ferramenta._config_por_painel_alterada()

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

    def reposicionar_no_canto_superior_direito(self) -> None:
        parent = self.parentWidget()
        if parent is not None and hasattr(parent, "calcular_posicao_painel_auxiliar"):
            destino = parent.calcular_posicao_painel_auxiliar(self.width(), self.height(), abaixo_coordenadas=True)
            if not restaurar_posicao(self, self._chave_posicao, fallback=self._ajustar_para_canvas(destino)):
                salvar_posicao(self, self._chave_posicao)
            return
        if not restaurar_posicao(self, self._chave_posicao, fallback=self._ajustar_para_canvas(QPoint(10_000, 0))):
            salvar_posicao(self, self._chave_posicao)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() <= 56:
            self._drag_offset_local = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset_local is not None and event.buttons() & Qt.LeftButton:
            destino = self.pos() + event.position().toPoint() - self._drag_offset_local
            self.move(self._ajustar_para_canvas(destino))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._drag_offset_local is not None:
            self._drag_offset_local = None
            salvar_posicao(self, self._chave_posicao)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        salvar_posicao(self, self._chave_posicao)
        super().hideEvent(event)


class Ferramenta(FerramentaBase):
    id_ferramenta = "por_angulo"
    nome = "Por Ângulo"
    usa_painel_auxiliar = False
    descricao_painel = "Cria uma reta a partir de um ponto inicial com ângulo informado."
    gerencia_coordenadas_operacao = True

    def __init__(self):
        super().__init__()
        self._painel: _PainelPorAngulo | None = None
        self._canvas = None
        self._origem: QPointF | None = None
        self._preview: QPointF | None = None
        self._angulo = 0.0
        self._comprimento = 10.0
        self._comprimento_fixo = False

    def on_activate(self, canvas) -> None:
        super().on_activate(canvas)
        self._canvas = canvas
        cfg = self.carregar_preferencias_ferramenta(
            canvas,
            {"angulo": 0.0, "comprimento": 10.0, "comprimento_fixo": False},
        )
        self._angulo = float(cfg.get("angulo", 0.0) or 0.0)
        self._comprimento = max(0.001, float(cfg.get("comprimento", 10.0) or 10.0))
        self._comprimento_fixo = bool(cfg.get("comprimento_fixo", False))
        self._origem = None
        self._preview = None
        self._mostrar_painel(canvas)
        self._status(canvas, "Por Ângulo: clique o ponto inicial da reta.")
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        canvas.update()

    def on_deactivate(self, canvas) -> None:
        self._origem = None
        self._preview = None
        painel = getattr(self, "_painel", None)
        if painel is not None:
            painel.hide()
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        super().on_deactivate(canvas)
        if canvas is not None:
            canvas.update()

    def on_canvas_resize(self, canvas) -> None:
        painel = getattr(self, "_painel", None)
        if painel is not None and painel.isVisible():
            painel.reposicionar_no_canto_superior_direito()

    def on_mouse_move(self, canvas, event) -> bool:
        if self._origem is None:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._preview = self._destino_por_angulo(canvas, self._origem, pos)
        if hasattr(canvas, "atualizar_operacao_coordenadas"):
            canvas.atualizar_operacao_coordenadas(self._preview)
        canvas.update()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._origem is not None:
                self._origem = None
                self._preview = None
                if hasattr(canvas, "cancelar_operacao_coordenadas"):
                    canvas.cancelar_operacao_coordenadas(limpar_preview=True)
                self._status(canvas, "Por Ângulo: operação cancelada. Clique novo ponto inicial ou use dois cliques direitos para sair.")
                canvas.update()
                event.accept()
                return True
            return False

        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        if self._origem is None:
            self._origem = QPointF(pos)
            self._preview = self._destino_por_angulo(canvas, self._origem, pos)
            if hasattr(canvas, "iniciar_operacao_coordenadas"):
                canvas.iniciar_operacao_coordenadas(self._origem)
            self._status(canvas, "Ponto inicial definido. Mova o mouse e clique para criar a reta no ângulo informado.")
            canvas.update()
            event.accept()
            return True

        destino = self._destino_por_angulo(canvas, self._origem, pos)
        if self._adicionar_reta(canvas, self._origem, destino):
            self._status(canvas, "Reta por ângulo criada. Nada ficou selecionado.")
        else:
            self._status(canvas, "Por Ângulo: reta pequena demais para criar.")
        if hasattr(canvas, "finalizar_operacao_coordenadas"):
            canvas.finalizar_operacao_coordenadas(destino)
        self._origem = None
        self._preview = None
        canvas.update()
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        if event.key() == Qt.Key_Escape:
            self._origem = None
            self._preview = None
            if hasattr(canvas, "cancelar_operacao_coordenadas"):
                canvas.cancelar_operacao_coordenadas(limpar_preview=True)
            self._status(canvas, "Por Ângulo: operação cancelada.")
            canvas.update()
            event.accept()
            return True
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self._origem is not None and self._preview is not None:
            if self._adicionar_reta(canvas, self._origem, self._preview):
                self._status(canvas, "Reta por ângulo criada. Nada ficou selecionado.")
            self._origem = None
            self._preview = None
            if hasattr(canvas, "finalizar_operacao_coordenadas"):
                canvas.finalizar_operacao_coordenadas(self._preview)
            canvas.update()
            event.accept()
            return True
        return False

    def desfazer_etapa(self, canvas) -> bool:
        if self._origem is None and self._preview is None:
            return False
        self._origem = None
        self._preview = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        self._status(canvas, "Por Ângulo: etapa atual desfeita.")
        canvas.update()
        return True

    def origem_coordenadas(self, canvas) -> QPointF:
        return QPointF(self._origem) if self._origem is not None else QPointF(0.0, 0.0)

    def on_paint_overlay(self, canvas, painter: QPainter) -> None:
        if self._origem is None:
            return
        destino = self._preview or self._destino_por_angulo(canvas, self._origem, self._origem)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        cor = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        if not cor.isValid():
            cor = QColor("#2da8ff")
        pen = QPen(cor, 2.4, Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(canvas._cena_para_tela(self._origem), canvas._cena_para_tela(destino))
        self._desenhar_ponto(painter, canvas._cena_para_tela(self._origem), QColor("#ffffff"), 4.0)
        self._desenhar_ponto(painter, canvas._cena_para_tela(destino), QColor("#ff3030"), 5.0)
        self._desenhar_rotulo_medida(canvas, painter, self._origem, destino)
        painter.restore()

    def _mostrar_painel(self, canvas) -> None:
        parent = canvas if canvas is not None else None
        if parent is not None:
            for painel_existente in parent.findChildren(QFrame):
                if painel_existente is not getattr(self, "_painel", None) and painel_existente.objectName() in {"PainelFerramentaBasico", "PainelPorAngulo"}:
                    painel_existente.hide()
        painel = getattr(self, "_painel", None)
        if painel is None:
            self._painel = _PainelPorAngulo(self, parent=parent)
            painel = self._painel
        elif parent is not None and painel.parentWidget() is not parent:
            painel.setParent(parent)
        unidade = str(getattr(canvas, "_unidade_sigla", "cm") or "cm")
        painel.carregar(self._angulo, self._comprimento, self._comprimento_fixo, unidade)
        painel.show()
        painel.raise_()
        painel.reposicionar_no_canto_superior_direito()

    def _config_por_painel_alterada(self) -> None:
        painel = getattr(self, "_painel", None)
        if painel is None:
            return
        self._angulo = float(painel.spn_angulo.value())
        self._comprimento = max(0.001, float(painel.spn_comprimento.value()))
        self._comprimento_fixo = bool(painel.chk_comprimento_fixo.isChecked())
        canvas = self._canvas
        if canvas is not None:
            self.salvar_preferencias_ferramenta(canvas, {
                "angulo": self._angulo,
                "comprimento": self._comprimento,
                "comprimento_fixo": self._comprimento_fixo,
            })
            if self._origem is not None:
                cursor = getattr(canvas, "_cursor_tela", QPointF(0.0, 0.0))
                try:
                    pos = canvas._ponto_com_snap(cursor)
                except Exception:
                    pos = self._origem
                self._preview = self._destino_por_angulo(canvas, self._origem, pos)
                if hasattr(canvas, "atualizar_operacao_coordenadas"):
                    canvas.atualizar_operacao_coordenadas(self._preview)
            canvas.update()

    def _destino_por_angulo(self, canvas, origem: QPointF, cursor: QPointF) -> QPointF:
        angulo = float(self._angulo)
        rad = radians(angulo)
        ux = cos(rad)
        uy = -sin(rad)
        if self._comprimento_fixo:
            comprimento_cena = self._comprimento_para_cena(canvas, self._comprimento)
        else:
            dx = cursor.x() - origem.x()
            dy = cursor.y() - origem.y()
            comprimento_cena = (dx * ux) + (dy * uy)
            if comprimento_cena <= 0.001:
                comprimento_cena = self._comprimento_para_cena(canvas, self._comprimento)
        return QPointF(origem.x() + (ux * comprimento_cena), origem.y() + (uy * comprimento_cena))

    def _comprimento_para_cena(self, canvas, valor: float) -> float:
        try:
            return float(canvas.converter_para_cena(valor))
        except Exception:
            return float(valor)

    def _comprimento_de_cena(self, canvas, valor: float) -> float:
        try:
            return float(canvas.converter_de_cena(valor))
        except Exception:
            return float(valor)

    def _adicionar_reta(self, canvas, origem: QPointF, destino: QPointF) -> bool:
        comprimento = self._distancia(origem, destino)
        if comprimento <= 1e-6:
            return False
        canvas.cena.elementos.append({
            "tipo": "polyline",
            "pontos": [(float(origem.x()), float(origem.y())), (float(destino.x()), float(destino.y()))],
            "cor": getattr(canvas, "_linha_cor", "#ffffff"),
            "espessura": float(getattr(canvas, "_linha_espessura", 1.0) or 1.0),
            "estilo": str(getattr(canvas, "_linha_estilo", "solid") or "solid"),
            "amplitude": float(getattr(canvas, "_linha_amplitude", 1.0) or 1.0),
            "fase_inicio": 0.0,
            "metadados": {"criado_por": self.id_ferramenta, "angulo": float(self._angulo)},
        })
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados.clear()
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados.clear()
        return True

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

    def _desenhar_rotulo_medida(self, canvas, painter: QPainter, origem: QPointF, destino: QPointF) -> None:
        meio = QPointF((origem.x() + destino.x()) / 2.0, (origem.y() + destino.y()) / 2.0)
        meio_tela = canvas._cena_para_tela(meio)
        comprimento = self._distancia(origem, destino)
        comp_u = self._comprimento_de_cena(canvas, comprimento)
        unidade = str(getattr(canvas, "_unidade_sigla", "cm") or "cm")
        texto = f"{self._angulo:.2f}°  |  {comp_u:.2f} {unidade}"
        fonte = painter.font()
        fonte.setBold(True)
        fonte.setPointSize(max(8, fonte.pointSize()))
        painter.setFont(fonte)
        metrics = QFontMetrics(fonte)
        largura = metrics.horizontalAdvance(texto) + 12
        altura = metrics.height() + 6
        x = meio_tela.x() + 10
        y = meio_tela.y() - altura - 10
        if x + largura > canvas.width() - 4:
            x = meio_tela.x() - largura - 10
        if y < 4:
            y = meio_tela.y() + 12
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.drawRoundedRect(int(x), int(y), int(largura), int(altura), 4, 4)
        painter.setPen(QPen(QColor("#2da8ff"), 1.0))
        painter.drawText(int(x + 6), int(y + 3), int(largura - 12), int(altura - 6), Qt.AlignCenter, texto)
        painter.restore()

    def _status(self, canvas, texto: str) -> None:
        painel = getattr(self, "_painel", None)
        if painel is not None:
            painel.atualizar_status(texto)
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
