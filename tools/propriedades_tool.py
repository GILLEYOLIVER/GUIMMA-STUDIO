from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from pathlib import Path
from random import randint

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer, Signal, QSignalBlocker
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QToolButton,
    QMenu,
)

from tools.tool_base import FerramentaBase

ICONS_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"


@dataclass(slots=True)
class MoldeRef:
    indice: int
    nome: str
    dados: dict


class PreviewMoldeWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._molde: dict | None = None
        self._cores_tecidos: dict[str, str] = {}
        self._mostrar_cor_tecidos = False
        self.setMinimumHeight(270)
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._hand_active = False
        self._panning = False
        self._last_pan_pos = QPointF(0.0, 0.0)

    def set_molde(self, molde: dict | None):
        self._molde = molde
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self.update()

    def set_config_cores_tecidos(self, cores: dict[str, str], mostrar: bool):
        self._cores_tecidos = dict(cores)
        self._mostrar_cor_tecidos = bool(mostrar)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#000000"))
        info = self._dados_transformacao()
        if not info:
            painter.setPen(QPen(QColor("#9a9a9a"), 1))
            painter.drawText(self.rect(), Qt.AlignCenter, "Nenhum molde selecionado")
            return

        pontos = self._coletar_pontos(self._molde.get("pontos"))
        if len(pontos) < 2:
            return

        base = pontos[:-1] if len(pontos) >= 3 and pontos[0] == pontos[-1] else pontos
        if not base:
            return

        xs = [p.x() for p in base]
        ys = [p.y() for p in base]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura = max(1.0, max_x - min_x)
        altura = max(1.0, max_y - min_y)

        margem = 26.0
        area_w = max(1.0, self.width() - (margem * 2.0))
        area_h = max(1.0, self.height() - (margem * 2.0))
        escala = min(area_w / largura, area_h / altura)

        offset_x = (self.width() - (largura * escala)) / 2.0
        offset_y = (self.height() - (altura * escala)) / 2.0

        def mapear(pt: QPointF) -> QPointF:
            return QPointF(
                self._offset.x() + info["offset_x"] + ((pt.x() - info["min_x"]) * info["escala"] * self._zoom),
                self._offset.y() + info["offset_y"] + ((pt.y() - info["min_y"]) * info["escala"] * self._zoom),
            )

        cor_desenho = QColor(str(self._molde.get("cor") or "#ffffff"))
        if not cor_desenho.isValid():
            cor_desenho = QColor("#ffffff")
        if self._mostrar_cor_tecidos:
            tecido = str(self._molde.get("tecido") or "").strip()
            cor_tecido = self._cores_tecidos.get(tecido)
            if cor_tecido:
                cor_desenho = QColor(cor_tecido)
        pen = QPen(cor_desenho, 1.0)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        path = QPainterPath(mapear(base[0]))
        for pt in base[1:]:
            path.lineTo(mapear(pt))
        if len(base) >= 3:
            path.closeSubpath()

        if bool(self._molde.get("visual_preencher", False)):
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(cor_desenho)
            painter.drawPath(path)
            painter.restore()
            painter.setPen(pen)

        painter.drawPath(path)

        self._desenhar_margem(painter, base, mapear, cor_desenho)
        self._desenhar_fio(painter, base, mapear)
        self._desenhar_textos(painter, base, mapear, info["min_y"], info["max_y"])
        self._desenhar_controles(painter, mapear)

    def _dados_transformacao(self) -> dict | None:
        if not self._molde or self._molde.get("tipo") != "polyline":
            return None
        pontos_raw = self._molde.get("pontos", [])
        pontos = [QPointF(float(x), float(y)) for x, y in pontos_raw]
        if len(pontos) < 2:
            return None
        base = pontos[:-1] if len(pontos) >= 3 and pontos[0] == pontos[-1] else pontos
        if not base:
            return None

        pontos_enquadramento = list(base)
        if self._molde.get("mostrar_margem", False):
            margens = self._margens_por_segmento(self._molde, len(base))
            if margens:
                sentido = 1.0 if self._area_assinada_pontos(base) < 0.0 else -1.0
                for seg_idx, margem in margens.items():
                    pontos_offset = self._pontos_offset_segmento(base, seg_idx, margem, sentido)
                    if pontos_offset is not None:
                        pontos_enquadramento.extend((pontos_offset[2], pontos_offset[3]))

        xs = [p.x() for p in pontos_enquadramento]
        ys = [p.y() for p in pontos_enquadramento]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura = max(1.0, max_x - min_x)
        altura = max(1.0, max_y - min_y)

        margem = 26.0
        area_w = max(1.0, self.width() - (margem * 2.0))
        area_h = max(1.0, self.height() - (margem * 2.0))
        escala = min(area_w / largura, area_h / altura)
        offset_x = (self.width() - (largura * escala)) / 2.0
        offset_y = (self.height() - (altura * escala)) / 2.0
        return {
            "base": base,
            "min_x": min_x,
            "min_y": min_y,
            "max_y": max_y,
            "escala": escala,
            "offset_x": offset_x,
            "offset_y": offset_y,
        }

    def _aplicar_zoom(self, fator: float, anchor: QPointF | None = None):
        old_zoom = self._zoom
        new_zoom = max(0.2, min(20.0, self._zoom * fator))
        if abs(new_zoom - old_zoom) <= 1e-9:
            return

        info = self._dados_transformacao()
        if info is None:
            self._zoom = new_zoom
            self.update()
            return

        ponto_ancora = anchor or QPointF(self.width() / 2.0, self.height() / 2.0)
        rel_x = ponto_ancora.x() - self._offset.x() - info["offset_x"]
        rel_y = ponto_ancora.y() - self._offset.y() - info["offset_y"]
        escala = new_zoom / max(old_zoom, 1e-9)
        self._offset = QPointF(
            ponto_ancora.x() - info["offset_x"] - (rel_x * escala),
            ponto_ancora.y() - info["offset_y"] - (rel_y * escala),
        )
        self._zoom = new_zoom
        self.update()

    def _desenhar_fio(self, painter: QPainter, base: list[QPointF], mapear):
        if not self._molde.get("mostrar_fio", True):
            return
        fio_origem = self._molde.get("fio_origem")
        fio_fim = self._molde.get("fio_fim")
        xs = [p.x() for p in base]
        ys = [p.y() for p in base]
        p_fio_origem = self._ponto_xy(fio_origem)
        p_fio_fim = self._ponto_xy(fio_fim)
        if p_fio_origem and p_fio_fim:
            p1 = mapear(p_fio_origem)
            p2 = mapear(p_fio_fim)
        else:
            margem = (max(xs) - min(xs)) * 0.18
            altura = max(ys) - min(ys)
            centro_y = sum(ys) / len(ys)
            y_fio = min(max(ys) - max(0.15, altura * 0.06), centro_y + max(0.25, altura * 0.08))
            p1 = mapear(QPointF(min(xs) + margem, y_fio))
            p2 = mapear(QPointF(max(xs) - margem, y_fio))

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-6:
            return
        ux = dx / comp
        uy = dy / comp
        nx = -uy
        ny = ux
        recuo = min(16.0, max(7.0, comp * 0.045))
        a = QPointF(p1.x() + (ux * recuo), p1.y() + (uy * recuo))
        b = QPointF(p2.x() - (ux * recuo), p2.y() - (uy * recuo))
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.drawLine(a, b)
        self._desenhar_ponta(painter, p1, QPointF(-ux, -uy), QPointF(nx, ny), 9.0, 2.8)
        self._desenhar_ponta(painter, p2, QPointF(ux, uy), QPointF(nx, ny), 9.0, 2.8)

    def _desenhar_ponta(self, painter: QPainter, ponta: QPointF, direcao: QPointF, normal: QPointF, comprimento: float, meia: float):
        base = QPointF(ponta.x() - (direcao.x() * comprimento), ponta.y() - (direcao.y() * comprimento))
        e = QPointF(base.x() + (normal.x() * meia), base.y() + (normal.y() * meia))
        d = QPointF(base.x() - (normal.x() * meia), base.y() - (normal.y() * meia))
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        path = QPainterPath()
        path.moveTo(ponta)
        path.lineTo(e)
        path.lineTo(d)
        path.closeSubpath()
        painter.drawPath(path)
        painter.restore()

    def _desenhar_margem(self, painter: QPainter, base: list[QPointF], mapear, cor_molde: QColor):
        if not self._molde or not self._molde.get("mostrar_margem", False) or len(base) < 3:
            return
        margens = self._margens_por_segmento(self._molde, len(base))
        if not margens:
            return
        sentido = 1.0 if self._area_assinada_pontos(base) < 0.0 else -1.0
        painter.save()
        pen = QPen(QColor(cor_molde), 1.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        total = len(base)
        for seg_idx, margem in margens.items():
            if margem <= 0:
                continue
            pontos_offset = self._pontos_offset_segmento(base, seg_idx, margem, sentido)
            if pontos_offset is None:
                continue
            a, b, off_a, off_b = pontos_offset
            painter.drawLine(mapear(off_a), mapear(off_b))

            margem_anterior = float(margens.get((seg_idx - 1) % total, 0.0) or 0.0)
            if margem_anterior > 0:
                anterior = self._pontos_offset_segmento(base, (seg_idx - 1) % total, margem_anterior, sentido)
                if anterior is not None:
                    canto = QPainterPath(mapear(anterior[3]))
                    canto.quadTo(mapear(a), mapear(off_a))
                    painter.drawPath(canto)
            else:
                painter.drawLine(mapear(a), mapear(off_a))

            margem_proxima = float(margens.get((seg_idx + 1) % total, 0.0) or 0.0)
            if margem_proxima <= 0:
                painter.drawLine(mapear(off_b), mapear(b))
        painter.restore()

    def _margens_por_segmento(self, molde: dict, total_segmentos: int) -> dict[int, float]:
        margens: dict[int, float] = {}
        for dados in (molde.get("margens_molde"), molde.get("margens"), molde.get("margem_cm_por_elemento")):
            if isinstance(dados, list):
                for item in dados:
                    if not isinstance(item, dict):
                        continue
                    idx = self._indice_segmento_margem(str(item.get("elemento") or ""), total_segmentos)
                    valor = self._valor_margem_float(item.get("margem"))
                    if idx is not None and valor > 0:
                        margens[idx] = valor
            elif isinstance(dados, dict):
                for elemento, valor_raw in dados.items():
                    idx = self._indice_segmento_margem(str(elemento), total_segmentos)
                    valor = self._valor_margem_float(valor_raw)
                    if idx is not None and valor > 0:
                        margens[idx] = valor
        return margens

    @staticmethod
    def _valor_margem_float(valor) -> float:
        try:
            texto = str(valor).replace("cm", "").replace(",", ".").strip()
            return max(0.0, float(texto or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _indice_segmento_margem(elemento: str, total_segmentos: int) -> int | None:
        partes = str(elemento or "").replace(" ", "").split("-", 1)
        if len(partes) != 2 or total_segmentos <= 0:
            return None
        try:
            inicio = int(partes[0])
            fim = int(partes[1])
        except ValueError:
            return None
        esperado_fim = (inicio % total_segmentos) + 1
        if inicio < 1 or inicio > total_segmentos or fim != esperado_fim:
            return None
        return inicio - 1

    @staticmethod
    def _area_assinada_pontos(pontos: list[QPointF]) -> float:
        area = 0.0
        for a, b in zip(pontos, pontos[1:] + pontos[:1]):
            area += (a.x() * b.y()) - (b.x() * a.y())
        return area / 2.0

    @staticmethod
    def _pontos_offset_segmento(
        base: list[QPointF],
        seg_idx: int,
        margem: float,
        sentido: float,
    ) -> tuple[QPointF, QPointF, QPointF, QPointF] | None:
        total = len(base)
        a = base[seg_idx % total]
        b = base[(seg_idx + 1) % total]
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-9:
            return None
        nx = sentido * (-dy / comp)
        ny = sentido * (dx / comp)
        off_a = QPointF(a.x() + (nx * margem), a.y() + (ny * margem))
        off_b = QPointF(b.x() + (nx * margem), b.y() + (ny * margem))
        return a, b, off_a, off_b

    def _desenhar_textos(self, painter: QPainter, base: list[QPointF], mapear, min_y: float, max_y: float):
        cx = sum(p.x() for p in base) / len(base)
        cy = sum(p.y() for p in base) / len(base)
        painter.setPen(QPen(QColor("#ffffff"), 1.0))

        fonte = QFont(painter.font())
        fonte.setPointSize(9)
        painter.setFont(fonte)

        if self._molde.get("mostrar_nome", True):
            nome = str(self._molde.get("nome_molde") or "")
            if nome:
                ponto_texto = self._ponto_xy(self._molde.get("ponto_texto")) or QPointF(cx, cy)
                pos = mapear(ponto_texto)
                largura_molde_px = max(
                    80,
                    int(abs(
                        mapear(QPointF(max(p.x() for p in base), cy)).x()
                        - mapear(QPointF(min(p.x() for p in base), cy)).x()
                    ) - 12),
                )
                fonte_nome = QFont(fonte)
                tamanho = 9
                while tamanho >= 6:
                    fonte_nome.setPointSize(tamanho)
                    painter.setFont(fonte_nome)
                    metric = painter.fontMetrics()
                    if metric.horizontalAdvance(nome) <= largura_molde_px:
                        break
                    tamanho -= 1
                altura = max(18, painter.fontMetrics().height() + 4)
                painter.drawText(
                    int(pos.x() - (largura_molde_px / 2)),
                    int(pos.y() - (altura / 2)),
                    int(largura_molde_px),
                    int(altura),
                    Qt.AlignCenter,
                    nome,
                )
                painter.setFont(fonte)

        if self._molde.get("visual_descricao", False):
            descricao = str(self._molde.get("descricao") or "Descrição")
            pos = mapear(QPointF(cx, cy + ((max_y - min_y) * 0.18)))
            painter.drawText(int(pos.x() - 40), int(pos.y()), 120, 18, Qt.AlignCenter, descricao)

        if self._molde.get("visual_quantidade", False):
            qtd = str(self._molde.get("qtd_modelo", 1) or 1)
            sufixo = " ( Par)" if self._molde.get("par", False) else ""
            pos = mapear(QPointF(cx, cy + ((max_y - min_y) * 0.22)))
            painter.drawText(int(pos.x() - 50), int(pos.y() + 16), 140, 18, Qt.AlignCenter, f"Quantidade {qtd}{sufixo}")

    def _desenhar_controles(self, painter: QPainter, mapear):
        if not self._molde.get("mostrar_controles", True):
            return
        pontos = self._coletar_pontos(self._molde.get("controle_cantos"))
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        for i, pt in enumerate(pontos, start=1):
            tela = mapear(pt)
            painter.drawRect(int(tela.x() - 3), int(tela.y() - 3), 6, 6)
            if self._molde.get("mostrar_numeros", False):
                painter.drawText(int(tela.x() + 4), int(tela.y() - 6), str(i))

    def _coletar_pontos(self, dados) -> list[QPointF]:
        pontos: list[QPointF] = []
        if not isinstance(dados, (list, tuple)):
            return pontos
        for item in dados:
            ponto = self._ponto_xy(item)
            if ponto is not None:
                pontos.append(ponto)
        return pontos

    def _ponto_xy(self, valor) -> QPointF | None:
        if not isinstance(valor, (list, tuple)) or len(valor) < 2:
            return None
        try:
            return QPointF(float(valor[0]), float(valor[1]))
        except (TypeError, ValueError):
            return None

    def zoom_in(self):
        self._aplicar_zoom(1.1)

    def zoom_out(self):
        self._aplicar_zoom(1.0 / 1.1)

    def reset_view(self):
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self.update()

    def set_hand_active(self, ativo: bool):
        self._hand_active = bool(ativo)
        self.setCursor(Qt.OpenHandCursor if self._hand_active else Qt.ArrowCursor)

    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        delta = event.angleDelta().y()
        if delta > 0:
            self._aplicar_zoom(1.1, event.position())
        elif delta < 0:
            self._aplicar_zoom(1.0 / 1.1, event.position())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if self._hand_active and event.button() == Qt.LeftButton:
            self._panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):  # noqa: N802
        if self._panning and self._hand_active:
            atual = event.position()
            delta = atual - self._last_pan_pos
            self._offset = QPointF(self._offset.x() + delta.x(), self._offset.y() + delta.y())
            self._last_pan_pos = atual
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802
        if self._panning and event.button() == Qt.LeftButton:
            self._panning = False
            self.setCursor(Qt.OpenHandCursor if self._hand_active else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class LegendaStatusMoldeWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(
            """
            QFrame#LegendaStatusMolde {
                background: #ddebf7;
                border: 1px solid #aebfd0;
            }
            """
        )
        self.setObjectName("LegendaStatusMolde")
        self._timer_auto_close = QTimer(self)
        self._timer_auto_close.setSingleShot(True)
        self._timer_auto_close.setInterval(3000)
        self._timer_auto_close.timeout.connect(self._recolher)
        self._construir_ui()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(2)
        self.btn_toggle = QToolButton()
        self.btn_toggle.setText("Legenda de status do molde:")
        self.btn_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_toggle.setArrowType(Qt.RightArrow)
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.toggled.connect(self._alternar_painel)
        topo.addWidget(self.btn_toggle, 1)

        self.btn_fechar = QToolButton()
        self.btn_fechar.setText("X")
        self.btn_fechar.setFixedSize(16, 16)
        self.btn_fechar.clicked.connect(self._recolher)
        topo.addWidget(self.btn_fechar, 0, Qt.AlignRight)
        layout.addLayout(topo)

        self._conteudo = QWidget()
        conteudo_layout = QVBoxLayout(self._conteudo)
        conteudo_layout.setContentsMargins(2, 2, 2, 2)
        conteudo_layout.setSpacing(3)
        conteudo_layout.addWidget(self._linha_status("molde-pronto.svg", "Molde pronto"))
        conteudo_layout.addWidget(self._linha_status("molde-nao-pronto.svg", "Molde não pronto"))
        conteudo_layout.addWidget(self._linha_status("nome-molde-repetido.svg", "Nome do molde repetido"))
        conteudo_layout.addWidget(self._linha_status("grade-diferente-modelo.svg", "Grade diferente do modelo"))
        conteudo_layout.addWidget(self._linha_status("propriedades.svg", "Propriedades não editáveis no Audaces Encaixe"))
        layout.addWidget(self._conteudo)
        self._conteudo.hide()
        self.btn_fechar.hide()

    def _linha_status(self, icon_name: str, texto: str) -> QWidget:
        row = QWidget()
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(4)
        lbl_icon = QLabel()
        lbl_icon.setFixedSize(14, 14)
        icon_path = ICONS_DIR / icon_name
        if icon_path.exists():
            lbl_icon.setPixmap(QIcon(str(icon_path)).pixmap(13, 13))
        lbl_texto = QLabel(texto)
        lbl_texto.setStyleSheet("color:#000000;")
        row_l.addWidget(lbl_icon, 0, Qt.AlignTop)
        row_l.addWidget(lbl_texto, 1)
        return row

    def _alternar_painel(self, aberto: bool):
        self.btn_toggle.setArrowType(Qt.DownArrow if aberto else Qt.RightArrow)
        self._conteudo.setVisible(aberto)
        self.btn_fechar.setVisible(aberto)
        if aberto:
            self._timer_auto_close.start()
        else:
            self._timer_auto_close.stop()

    def _recolher(self):
        self._timer_auto_close.stop()
        self.btn_toggle.setChecked(False)


class PropriedadesMoldesDialog(QDialog):
    dados_aplicados = Signal()

    def __init__(self, canvas, parent: QWidget | None = None, mostrar_tab_ferramentas: bool = True):
        super().__init__(parent)
        self.canvas = canvas
        self._mostrar_tab_ferramentas = bool(mostrar_tab_ferramentas)
        self._refs: list[MoldeRef] = []
        self._itens_molde_por_indice: dict[int, QTreeWidgetItem] = {}
        self._combos_tecido_por_item: dict[int, QComboBox] = {}
        self._suspender_combo_tecido_arvore = False
        self._indice_atual: int | None = self._indice_molde_preferencial()
        self._cor_visual = "#ffffff"
        self._graduacao_linhas: list[dict] = []
        self._contador_novos_tamanhos = 0
        self._snapshot_moldes: dict[int, dict] = self._criar_snapshot_moldes()
        self._snapshot_mostrar_cor_tecidos = bool(getattr(self.canvas, "_mostrar_cor_tecidos", False))
        self._confirmado_ok = False
        self._suspender_auto_aplicar = False
        self._suspender_item_changed = False
        self._linha_gradacao_atual = 0
        self.setWindowTitle("Propriedades dos moldes")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.resize(1060, 780)
        self.setMinimumSize(1020, 740)
        self.setObjectName("PropriedadesMoldesDialog")
        self.setStyleSheet(self._stylesheet())
        self._construir_ui()
        self._conectar_auto_aplicacao()
        _log_propriedades_debug(f"PropriedadesMoldesDialog criado. canvas={type(canvas).__name__}; parent={type(parent).__name__ if parent is not None else None}; mostrar_tab_ferramentas={mostrar_tab_ferramentas}")
        try:
            self.recarregar_lista()
        except Exception as exc:
            _log_propriedades_debug(f"Falha ao carregar lista de moldes no __init__: {type(exc).__name__}: {exc}")
            print(f"Falha ao carregar lista de moldes: {type(exc).__name__}: {exc}")

    def _stylesheet(self) -> str:
        return """
        QDialog#PropriedadesMoldesDialog {
            background: #efefef;
            color: #101010;
        }
        QLabel, QCheckBox, QLineEdit, QTextEdit, QComboBox, QTreeWidget, QTableWidget {
            color: #111111;
            font-size: 12px;
        }
        QFrame#PanelLeft, QFrame#PanelRight {
            background: transparent;
        }
        QTreeWidget {
            background: #ffffff;
            border: 1px solid #9fa8b2;
            selection-background-color: #c9d7ea;
            selection-color: #111111;
        }
        QTreeWidget::item { height: 21px; }
        QTreeWidget::item:selected { background: #b9cfe1; color: #111111; }
        QTabWidget::pane {
            border: 1px solid #cfd4da;
            background: #ececec;
            top: -1px;
        }
        QTabWidget::tab-bar {
            left: 6px;
        }
        QTabBar::tab {
            background: #f0f0f0;
            border: 1px solid #cfd4da;
            border-bottom: none;
            padding: 3px 10px;
            min-width: 64px;
            margin-right: 2px;
            color: #000000;
        }
        QTabBar::tab:selected {
            background: #ececec;
            border-color: #cfd4da;
        }
        QTabBar::tab:hover { background: #f6f6f6; }
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget {
            background: #ffffff;
            border: 1px solid #b5bcc3;
            border-radius: 0px;
            selection-background-color: #2b7cd3;
            selection-color: #ffffff;
        }
        QComboBox { combobox-popup: 0; }
        QComboBox QAbstractItemView {
            background: #ffffff;
            color: #111111;
            border: 1px solid #b5bcc3;
            selection-background-color: #2b7cd3;
            selection-color: #ffffff;
            outline: 0;
        }
        QTextEdit { padding: 4px; }
        QGroupBox {
            border: 1px solid #c8c8c8;
            margin-top: 14px;
            background: #f5f5f5;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 6px;
            top: 1px;
            padding: 0 4px;
        }
        QPushButton {
            background: #f7f7f7;
            border: 1px solid #b7bec5;
            border-radius: 4px;
            padding: 3px 10px;
            min-height: 22px;
            color: #111111;
        }
        QPushButton:hover { background: #ffffff; }
        QPushButton#OkButton {
            color: #2f7d2f;
            min-width: 76px;
        }
        QPushButton#CancelButton {
            color: #b33b3b;
            min-width: 76px;
        }
        QPushButton#ApplyBlueButton {
            background: #d7e9f9;
            border-color: #b8d0ea;
            min-width: 150px;
        }
        QPushButton#PreviewToolButton {
            background: #ffffff;
            border: 1px solid #c4ccd5;
            border-radius: 7px;
            padding: 0px;
            color: #26384d;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton#PreviewToolButton:hover {
            background: #f2f7ff;
            border-color: #8fb7df;
        }
        QPushButton#PreviewToolButton:pressed, QPushButton#PreviewToolButton:checked {
            background: #dcecff;
            border-color: #5794d0;
            color: #0f4f89;
        }
        QToolButton {
            background: #f7f7f7;
            border: 1px solid #b7bec5;
            border-radius: 4px;
            padding: 2px 6px;
            color: #111111;
        }
        QToolButton:hover { background: #ffffff; border-color: #8aa9c8; }
        QToolButton:pressed { background: #e4eef8; }
        QToolButton:disabled {
            color: #777777;
            background: #ebebeb;
        }
        QToolButton#FabricManageButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #eef4fb);
            border: 1px solid #a9b9c9;
            border-radius: 5px;
            padding: 0px;
            color: #64748b;
            font-size: 15px;
            font-weight: 700;
        }
        QToolButton#FabricManageButton:hover {
            background: #ffffff;
            border-color: #6f9fd2;
            color: #2f6fae;
        }
        QToolButton#FabricManageButton:pressed {
            background: #dfeefa;
            border-color: #4f86c6;
        }
        QHeaderView::section {
            background: #f1f1f1;
            color: #111111;
            border: 1px solid #bfc6cc;
            padding: 3px;
            font-weight: 500;
        }
        QMenu {
            background: #ffffff;
            color: #111111;
            border: 1px solid #bfc6cc;
            padding: 4px;
        }
        QMenu::item {
            background: transparent;
            color: #111111;
            padding: 6px 22px 6px 12px;
            border-radius: 2px;
        }
        QMenu::item:selected {
            background: #d9ecff;
            color: #111111;
        }
        QMenu::separator {
            height: 1px;
            background: #d7d7d7;
            margin: 4px 8px;
        }
        """

    def _construir_ui(self):
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(10)

        painel_esq = QFrame()
        painel_esq.setObjectName("PanelLeft")
        painel_esq.setFixedWidth(205)
        lay_esq = QVBoxLayout(painel_esq)
        lay_esq.setContentsMargins(0, 0, 0, 0)
        lay_esq.setSpacing(8)

        self.arvore = QTreeWidget()
        self.arvore.setHeaderHidden(True)
        self.arvore.itemSelectionChanged.connect(self._quando_troca_selecao)
        self.arvore.itemChanged.connect(self._quando_item_editado)
        lay_esq.addWidget(self.arvore, 1)

        self.btn_excluir_molde = QPushButton("🗑 Excluir molde")
        self.btn_excluir_molde.clicked.connect(self._excluir_molde_atual)
        self.btn_excluir_molde.setFixedHeight(48)
        lay_esq.addWidget(self.btn_excluir_molde)

        self.legenda_status = LegendaStatusMoldeWidget()
        lay_esq.addWidget(self.legenda_status)

        painel_dir = QFrame()
        painel_dir.setObjectName("PanelRight")
        lay_dir = QVBoxLayout(painel_dir)
        lay_dir.setContentsMargins(0, 0, 0, 0)
        lay_dir.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.addTab(self._criar_tab_propriedades(), "Propriedades")
        self.tabs.addTab(self._criar_tab_graduacao(), "Graduação")
        self.tabs.addTab(self._criar_tab_visualizacao(), "Visualização")
        self.tabs.addTab(self._criar_tab_margem(), "Margem")
        self._idx_tab_cam = self.tabs.addTab(self._criar_tab_cam(), "Pontos de CAM")
        if hasattr(self.tabs, "setTabVisible"):
            self.tabs.setTabVisible(self._idx_tab_cam, False)
        else:
            self.tabs.setTabEnabled(self._idx_tab_cam, False)
        self._idx_tab_ferramentas = self.tabs.addTab(self._criar_tab_ferramentas(), "Ferramentas")
        self.set_exibir_tab_ferramentas(self._mostrar_tab_ferramentas)
        lay_dir.addWidget(self.tabs, 0)

        self.preview = PreviewMoldeWidget()
        lay_dir.addWidget(self.preview, 1)

        barra_preview = QHBoxLayout()
        barra_preview.setContentsMargins(0, 0, 0, 0)
        barra_preview.setSpacing(5)

        self.btn_preview_mao = self._criar_botao_preview("✋", "Mover visualização")
        self.btn_preview_mao.setCheckable(True)
        self.btn_preview_mao.toggled.connect(self.preview.set_hand_active)
        barra_preview.addWidget(self.btn_preview_mao, 0, Qt.AlignLeft)

        self.btn_preview_ajustar = self._criar_botao_preview("⌖", "Ajustar molde à área")
        self.btn_preview_ajustar.clicked.connect(self.preview.reset_view)
        barra_preview.addWidget(self.btn_preview_ajustar, 0, Qt.AlignLeft)

        self.btn_preview_zoom_mais = self._criar_botao_preview("+", "Aproximar")
        self.btn_preview_zoom_mais.clicked.connect(self.preview.zoom_in)
        barra_preview.addWidget(self.btn_preview_zoom_mais, 0, Qt.AlignLeft)

        self.btn_preview_zoom_menos = self._criar_botao_preview("−", "Afastar")
        self.btn_preview_zoom_menos.clicked.connect(self.preview.zoom_out)
        barra_preview.addWidget(self.btn_preview_zoom_menos, 0, Qt.AlignLeft)
        barra_preview.addStretch(1)
        lay_dir.addLayout(barra_preview)

        rodape = QHBoxLayout()
        rodape.setContentsMargins(0, 0, 0, 0)
        rodape.addStretch(1)
        self.btn_ok = QPushButton("✓ OK")
        self.btn_ok.setObjectName("OkButton")
        self.btn_ok.clicked.connect(self._ok)
        self.btn_cancelar = QPushButton("✕ Cancelar")
        self.btn_cancelar.setObjectName("CancelButton")
        self.btn_cancelar.clicked.connect(self.close)
        rodape.addWidget(self.btn_ok)
        rodape.addWidget(self.btn_cancelar)
        lay_dir.addLayout(rodape)

        raiz.addWidget(painel_esq, 0)
        raiz.addWidget(painel_dir, 1)
        self._atualizar_opcoes_tecido()
        self._ajustar_larguras_campos()
        self._atualizar_estado_faixa_giro()

    def _criar_botao_preview(self, texto: str, tooltip: str) -> QPushButton:
        botao = QPushButton(texto)
        botao.setObjectName("PreviewToolButton")
        botao.setToolTip(tooltip)
        botao.setFixedSize(30, 26)
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFocusPolicy(Qt.NoFocus)
        return botao

    def set_exibir_tab_ferramentas(self, exibir: bool):
        self._mostrar_tab_ferramentas = bool(exibir)
        if not hasattr(self, "tabs") or not hasattr(self, "_idx_tab_ferramentas"):
            return
        try:
            if hasattr(self.tabs, "setTabVisible"):
                self.tabs.setTabVisible(self._idx_tab_ferramentas, self._mostrar_tab_ferramentas)
            else:
                pagina = self.tabs.widget(self._idx_tab_ferramentas)
                if pagina is not None:
                    pagina.setVisible(self._mostrar_tab_ferramentas)
            if not self._mostrar_tab_ferramentas and self.tabs.currentIndex() == self._idx_tab_ferramentas:
                self.tabs.setCurrentIndex(0)
        except Exception:
            pass

    def _ajustar_larguras_campos(self):
        combos: list[QComboBox] = []
        for nome in (
            "cmb_aplicar_grade",
            "cmb_area_tamanho",
            "cmb_grade_tamanhos",
            "cmb_elementos_molde",
            "cmb_tipo_corte",
            "cmb_molde",
            "cmb_espelhar",
            "cmb_giro",
            "cmb_tipo_corte_cam",
            "ed_tecido",
        ):
            widget = getattr(self, nome, None)
            if isinstance(widget, QComboBox):
                combos.append(widget)
        for combo in combos:
            combo.setMinimumContentsLength(18)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            combo.setMinimumWidth(170)

    def _criar_tab_propriedades(self) -> QWidget:
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(6, 8, 6, 0)
        layout.setSpacing(8)

        topo = QFrame()
        grid = QGridLayout(topo)
        grid.setContentsMargins(8, 4, 8, 2)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        self.cmb_molde = QComboBox()
        self.cmb_molde.setEditable(True)
        self.cmb_molde.currentIndexChanged.connect(self._trocar_molde_pelo_combo)
        if self.cmb_molde.lineEdit() is not None:
            self.cmb_molde.lineEdit().textEdited.connect(self._renomear_molde_atual_instantaneo)

        self.cmb_tipo_corte = QComboBox()
        self.cmb_tipo_corte.addItems(["Completo", "Par", "Espelhado", "Único"])
        self.cmb_tipo_corte.hide()

        self.ed_descricao = QTextEdit()
        self.ed_descricao.setFixedHeight(72)

        grid.addWidget(QLabel("Molde"), 0, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        grid.addWidget(self.cmb_molde, 0, 1)
        grid.addWidget(QLabel("Descrição"), 1, 0, alignment=Qt.AlignLeft | Qt.AlignTop)
        grid.addWidget(self.ed_descricao, 1, 1)

        box = QGroupBox("Propriedades de encaixe")
        box_layout = QGridLayout(box)
        box_layout.setContentsMargins(10, 16, 10, 10)
        box_layout.setHorizontalSpacing(10)
        box_layout.setVerticalSpacing(7)
        box_layout.setColumnStretch(1, 1)
        box_layout.setColumnStretch(3, 1)

        self.chk_molde_pronto = QCheckBox("Molde pronto")
        self.chk_perm_alt = QCheckBox("Permitir alterações das propriedades no Audaces Encaixe")

        self.ed_tecido = QComboBox()
        self.ed_tecido.setEditable(True)
        self.ed_tecido.setInsertPolicy(QComboBox.NoInsert)
        self.ed_tecido.setMinimumWidth(120)
        self.ed_tecido.setMaximumWidth(120)
        self.btn_config_tecido = QToolButton()
        self.btn_config_tecido.setObjectName("FabricManageButton")
        self.btn_config_tecido.setText("⋯")
        self.btn_config_tecido.setFixedSize(28, 24)
        self.btn_config_tecido.setCursor(Qt.PointingHandCursor)
        self.btn_config_tecido.setToolTip("Abrir lista e configurações dos tecidos")
        self.btn_config_tecido.clicked.connect(self._abrir_config_cor_tecidos)
        self.ed_tecido.installEventFilter(self)
        self.ed_tecido.activated.connect(lambda *_: self._aplicar_tecido_formulario_confirmado())
        if self.ed_tecido.lineEdit() is not None:
            self.ed_tecido.lineEdit().editingFinished.connect(self._aplicar_tecido_formulario_confirmado)

        self.cmb_espelhar = QComboBox()
        self.cmb_espelhar.addItems(["Nenhum", "Horizontal", "Vertical"])
        self.sp_qtd_modelo = QSpinBox()
        self.sp_qtd_modelo.setRange(1, 999)
        self.cmb_giro = QComboBox()
        self.cmb_giro.addItems(["Sem giro", "Livre", "90 graus", "180 graus", "180 graus + faixa", "Faixa"])
        self.cmb_giro.currentTextChanged.connect(self._atualizar_estado_faixa_giro)
        self.ed_faixa_giro = QLineEdit("0")
        self.ed_faixa_giro.setMaximumWidth(96)
        self.ed_giro_inicial = QLineEdit("0")
        self.ed_giro_inicial.setMaximumWidth(78)

        self.chk_par = QCheckBox("Par")
        self.chk_dobra_v = QCheckBox("Dobra vertical")
        self.chk_dobra_h = QCheckBox("Dobra horizontal")
        self.chk_reflete_v = QCheckBox("Refletido vertical")
        self.chk_reflete_h = QCheckBox("Refletido horizontal")

        box_layout.addWidget(self.chk_molde_pronto, 0, 0, 1, 2)
        box_layout.addWidget(self.chk_perm_alt, 0, 3, 1, 4, alignment=Qt.AlignLeft)

        box_layout.addWidget(QLabel("Tecido"), 1, 0)
        box_layout.addWidget(self.ed_tecido, 1, 1, 1, 1)
        box_layout.addWidget(self.btn_config_tecido, 1, 2, alignment=Qt.AlignLeft)

        box_layout.addWidget(QLabel("Espelhar"), 2, 0)
        box_layout.addWidget(self.cmb_espelhar, 2, 1, 1, 2)

        box_layout.addWidget(QLabel("Quantidade por modelo"), 3, 0)
        box_layout.addWidget(self.sp_qtd_modelo, 3, 1, 1, 2)
        box_layout.addWidget(self.chk_par, 3, 3, 1, 3, alignment=Qt.AlignLeft)

        box_layout.addWidget(QLabel("Giro"), 4, 0)
        box_layout.addWidget(self.cmb_giro, 4, 1, 1, 2)
        box_layout.addWidget(self.chk_dobra_v, 4, 3, 1, 3, alignment=Qt.AlignLeft)

        box_layout.addWidget(QLabel("Faixa de giro"), 5, 0)
        faixa_layout = QHBoxLayout()
        faixa_layout.setContentsMargins(0, 0, 0, 0)
        faixa_layout.setSpacing(4)
        faixa_layout.addWidget(self.ed_faixa_giro)
        faixa_layout.addWidget(QLabel("°"))
        faixa_layout.addStretch(1)
        box_layout.addLayout(faixa_layout, 5, 1, 1, 2)
        box_layout.addWidget(self.chk_dobra_h, 5, 3, 1, 3, alignment=Qt.AlignLeft)

        lbl_conf_inicial = QLabel("Configuração inicial do molde")
        box_layout.addWidget(lbl_conf_inicial, 6, 0, 1, 4)

        box_layout.addWidget(QLabel("Giro inicial"), 7, 0)
        giro_layout = QHBoxLayout()
        giro_layout.setContentsMargins(0, 0, 0, 0)
        giro_layout.setSpacing(4)
        giro_layout.addWidget(self.ed_giro_inicial)
        giro_layout.addWidget(QLabel("°"))
        giro_layout.addStretch(1)
        box_layout.addLayout(giro_layout, 7, 1, 1, 2)

        reflexo_layout = QHBoxLayout()
        reflexo_layout.setContentsMargins(0, 0, 0, 0)
        reflexo_layout.setSpacing(10)
        reflexo_layout.addWidget(self.chk_reflete_v)
        reflexo_layout.addWidget(self.chk_reflete_h)
        reflexo_layout.addStretch(1)
        box_layout.addLayout(reflexo_layout, 7, 3, 1, 3)

        self.btn_aplicar_todos_prop = QPushButton("Aplicar todos")
        self.btn_aplicar_todos_prop.setObjectName("ApplyBlueButton")
        self.btn_aplicar_todos_prop.clicked.connect(self._aplicar_todos_moldes)
        self.btn_menu_aplicar_prop = QToolButton()
        self.btn_menu_aplicar_prop.setText("▾")
        self.btn_menu_aplicar_prop.setFixedWidth(18)
        self.btn_menu_aplicar_prop.setPopupMode(QToolButton.InstantPopup)
        self.menu_aplicar_prop = QMenu(self)
        self.menu_aplicar_prop.addAction("Aplicar todos", self._aplicar_todos_moldes)
        self.menu_aplicar_prop.addAction("Aplicar a todos com o mesmo tecido", self._aplicar_todos_com_mesmo_tecido)
        self.btn_menu_aplicar_prop.setMenu(self.menu_aplicar_prop)
        aplicar_layout = QHBoxLayout()
        aplicar_layout.setContentsMargins(0, 0, 0, 0)
        aplicar_layout.setSpacing(0)
        aplicar_layout.addWidget(self.btn_aplicar_todos_prop)
        aplicar_layout.addWidget(self.btn_menu_aplicar_prop)
        aplicar_layout.addStretch(1)
        box_layout.addLayout(aplicar_layout, 8, 0, 1, 3)

        layout.addWidget(topo)
        layout.addWidget(box)
        layout.addStretch(1)
        return aba

    def _trocar_molde_pelo_combo(self, index: int):
        if index < 0 or not hasattr(self, "cmb_molde"):
            return
        idx_molde = self.cmb_molde.itemData(index)
        if idx_molde is None:
            return
        raiz = self.arvore.topLevelItem(0)
        if raiz is None:
            return
        for item in self._iter_items(raiz):
            if item.data(0, Qt.UserRole) == idx_molde:
                with QSignalBlocker(self.arvore):
                    self.arvore.setCurrentItem(item)
                self._indice_atual = int(idx_molde)
                self._preencher_campos(self._molde_atual())
                break

    def _atualizar_combo_moldes(self):
        if not hasattr(self, "cmb_molde"):
            return
        atual = self._indice_atual
        with QSignalBlocker(self.cmb_molde):
            self.cmb_molde.clear()
            for ref in self._refs:
                self.cmb_molde.addItem(ref.nome or f"Molde {ref.indice + 1}", ref.indice)
            if atual is not None:
                pos = self.cmb_molde.findData(atual)
                if pos >= 0:
                    self.cmb_molde.setCurrentIndex(pos)
    def _criar_tab_graduacao(self) -> QWidget:
        aba = QWidget()
        layout = QHBoxLayout(aba)
        layout.setContentsMargins(14, 16, 14, 6)
        layout.setSpacing(12)

        quadro_esq = QFrame()
        grid_esq = QVBoxLayout(quadro_esq)
        grid_esq.setContentsMargins(0, 0, 0, 0)
        grid_esq.setSpacing(4)

        self.tbl_graduacao = QTableWidget(3, 3)
        self.tbl_graduacao.setHorizontalHeaderLabels(["Visão", "Tamanho", "Cor"])
        self.tbl_graduacao.verticalHeader().setVisible(False)
        self.tbl_graduacao.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_graduacao.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_graduacao.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_graduacao.setFixedWidth(230)
        self.tbl_graduacao.setFixedHeight(286)
        self.tbl_graduacao.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_graduacao.setSelectionBehavior(QTableWidget.SelectItems)
        self.tbl_graduacao.setSelectionMode(QTableWidget.NoSelection)
        self.tbl_graduacao.setStyleSheet(
            "QTableWidget::item:selected { background: transparent; color:#111111; }"
            "QTableWidget::item:selected:active { background: transparent; color:#111111; }"
            "QTableWidget::item:selected:!active { background: transparent; color:#111111; }"
        )
        self.tbl_graduacao.cellClicked.connect(self._on_tabela_graduacao_clicada)
        self._popular_tabela_graduacao()
        grid_esq.addWidget(self.tbl_graduacao)

        botoes = QHBoxLayout()
        self.btn_novo_cima = QPushButton("⬆ Novo")
        self.btn_base = QPushButton("Base")
        self.btn_novo_baixo = QPushButton("⬇ Novo")
        self.btn_excluir_tamanho = QPushButton("Excluir")
        self.btn_novo_cima.clicked.connect(self._adicionar_tamanho_acima)
        self.btn_base.clicked.connect(self._definir_tamanho_base)
        self.btn_novo_baixo.clicked.connect(self._adicionar_tamanho_abaixo)
        self.btn_excluir_tamanho.clicked.connect(self._excluir_tamanho_graduacao)
        for btn in (self.btn_novo_cima, self.btn_base, self.btn_novo_baixo, self.btn_excluir_tamanho):
            btn.setFixedHeight(24)
            botoes.addWidget(btn)
        grid_esq.addLayout(botoes)

        quadro_dir = QGroupBox()
        quadro_dir.setFixedWidth(320)
        form = QFormLayout(quadro_dir)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(8)
        self.cmb_aplicar_grade = QComboBox()
        self.cmb_aplicar_grade.addItems(["Ao modelo", "Ao molde"])
        self.cmb_aplicar_grade.setCurrentText("Ao molde")
        self.cmb_area_tamanho = QComboBox()
        self.cmb_area_tamanho.addItems(["Manter diferença", "Igual tamanho", "Tamanho intermediário"])
        self.cmb_grade_tamanhos = QComboBox()
        self.cmb_grade_tamanhos.addItems(["P-G(M)", "PP-GG(M)", "PP-XG(M)", "S-L(M)", "S-XL(M)", "1-3(2)", "1-4(2)", "1-5(3)", "2-12(6)", "36-50(40)"])
        self.cmb_grade_tamanhos.currentTextChanged.connect(self._aplicar_grade_tamanhos)
        form.addRow("Aplicar", self.cmb_aplicar_grade)
        form.addRow("Área do tamanho", self.cmb_area_tamanho)
        form.addRow("Grade de tamanhos", self.cmb_grade_tamanhos)

        layout.addWidget(quadro_esq, 0)
        layout.addWidget(quadro_dir, 0, Qt.AlignTop)
        layout.addStretch(1)
        return aba

    def _popular_tabela_graduacao(self):
        if not self._graduacao_linhas:
            grade_inicial = self.cmb_grade_tamanhos.currentText() if hasattr(self, "cmb_grade_tamanhos") else "P-G(M)"
            self._aplicar_grade_tamanhos(grade_inicial)
            return
        self._renderizar_tabela_graduacao()

    def _renderizar_tabela_graduacao(self):
        linhas = self._graduacao_linhas
        self.tbl_graduacao.setRowCount(len(linhas))
        for linha, dado in enumerate(linhas):
            item_v = QTableWidgetItem("✓" if dado.get("ativo", True) else "")
            item_v.setTextAlignment(Qt.AlignCenter)
            item_v.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_graduacao.setItem(linha, 0, item_v)

            item_t = QTableWidgetItem(str(dado.get("tamanho") or ""))
            item_t.setTextAlignment(Qt.AlignCenter)
            item_t.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if dado.get("base", False):
                item_t.setBackground(QColor("#2b7cd3"))
                item_t.setForeground(QColor("#ffffff"))
            self.tbl_graduacao.setItem(linha, 1, item_t)

            item_c = QTableWidgetItem("")
            item_c.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_c.setBackground(QColor(str(dado.get("cor") or "#ffffff")))
            self.tbl_graduacao.setItem(linha, 2, item_c)

        base_idx = next((i for i, d in enumerate(linhas) if d.get("base", False)), 0)
        if linhas:
            self.tbl_graduacao.setCurrentCell(base_idx, 1)

    def _aplicar_grade_tamanhos(self, grade_texto: str):
        tamanhos, base = self._extrair_tamanhos_grade(grade_texto)
        self._graduacao_linhas = []
        for tamanho in tamanhos:
            self._graduacao_linhas.append({
                "ativo": True,
                "tamanho": tamanho,
                "cor": self._gerar_cor_aleatoria(),
                "base": str(tamanho) == str(base),
            })
        if self._graduacao_linhas and not any(l.get("base") for l in self._graduacao_linhas):
            self._graduacao_linhas[len(self._graduacao_linhas) // 2]["base"] = True
        self._renderizar_tabela_graduacao()
        self._sincronizar_gradacao_no_molde()

    def _extrair_tamanhos_grade(self, grade_texto: str) -> tuple[list[str], str | None]:
        texto = str(grade_texto or "").strip()
        if not texto or "-" not in texto:
            return ["P", "M", "G"], "M"
        base = None
        if "(" in texto and ")" in texto:
            base = texto[texto.find("(") + 1:texto.find(")")].strip()
            texto = texto[:texto.find("(")].strip()
        inicio, fim = [p.strip() for p in texto.split("-", 1)]

        if inicio.isdigit() and fim.isdigit():
            n1, n2 = int(inicio), int(fim)
            passo = 2 if (n2 - n1) % 2 == 0 and abs(n2 - n1) >= 2 else 1
            vals = list(range(n1, n2 + 1, passo))
            return [str(v) for v in vals], base

        escalas = [
            ["PP", "P", "M", "G", "GG", "XG", "XXG"],
            ["XS", "S", "M", "L", "XL", "XXL"],
        ]
        for escala in escalas:
            if inicio in escala and fim in escala:
                a, b = escala.index(inicio), escala.index(fim)
                trecho = escala[min(a, b):max(a, b) + 1]
                return trecho, base
        return [inicio, "M", fim], base

    def _on_tabela_graduacao_clicada(self, linha: int, coluna: int):
        if not (0 <= linha < len(self._graduacao_linhas)):
            return
        self._linha_gradacao_atual = linha
        item = self._graduacao_linhas[linha]
        if coluna == 0:
            item["ativo"] = not bool(item.get("ativo", True))
            self._renderizar_tabela_graduacao()
        elif coluna == 2:
            cor_inicial = QColor(str(item.get("cor") or "#ffffff"))
            cor = self._selecionar_cor_clara(cor_inicial, "Cor do tamanho")
            if cor.isValid():
                item["cor"] = cor.name()
                self._renderizar_tabela_graduacao()
            if hasattr(self, "tbl_graduacao"):
                self.tbl_graduacao.clearSelection()
                self.tbl_graduacao.setCurrentCell(linha, 1)
        self._sincronizar_gradacao_no_molde()

    def _linha_selecionada_graduacao(self) -> int:
        row = int(getattr(self, "_linha_gradacao_atual", -1))
        if 0 <= row < len(self._graduacao_linhas):
            return row
        row = self.tbl_graduacao.currentRow()
        return row if 0 <= row < len(self._graduacao_linhas) else -1

    def _definir_tamanho_base(self):
        row = self._linha_selecionada_graduacao()
        if row < 0:
            return
        for idx, linha in enumerate(self._graduacao_linhas):
            linha["base"] = idx == row
        self._renderizar_tabela_graduacao()
        self._sincronizar_gradacao_no_molde()

    def _adicionar_tamanho_acima(self):
        if not self._graduacao_linhas:
            return
        novo = self._novo_tamanho_extremo(acima=True)
        self._graduacao_linhas.insert(0, {"ativo": True, "tamanho": novo, "cor": self._gerar_cor_aleatoria(), "base": False})
        self._renderizar_tabela_graduacao()
        self.tbl_graduacao.selectRow(0)
        self._sincronizar_gradacao_no_molde()

    def _adicionar_tamanho_abaixo(self):
        if not self._graduacao_linhas:
            return
        novo = self._novo_tamanho_extremo(acima=False)
        self._graduacao_linhas.append({"ativo": True, "tamanho": novo, "cor": self._gerar_cor_aleatoria(), "base": False})
        self._renderizar_tabela_graduacao()
        self.tbl_graduacao.selectRow(len(self._graduacao_linhas) - 1)
        self._sincronizar_gradacao_no_molde()

    def _excluir_tamanho_graduacao(self):
        row = self._linha_selecionada_graduacao()
        if row < 0 or len(self._graduacao_linhas) <= 1:
            return
        era_base = bool(self._graduacao_linhas[row].get("base"))
        del self._graduacao_linhas[row]
        if era_base:
            self._graduacao_linhas[min(row, len(self._graduacao_linhas) - 1)]["base"] = True
        self._renderizar_tabela_graduacao()
        self._sincronizar_gradacao_no_molde()

    def _novo_tamanho_extremo(self, acima: bool) -> str:
        tamanhos = [str(l.get("tamanho") or "") for l in self._graduacao_linhas]
        if tamanhos and all(t.isdigit() for t in tamanhos):
            nums = [int(t) for t in tamanhos]
            passo = abs(nums[1] - nums[0]) if len(nums) > 1 else 1
            passo = max(1, passo)
            return str(min(nums) - passo) if acima else str(max(nums) + passo)
        self._contador_novos_tamanhos += 1
        prefixo = "NOVO_SUP" if acima else "NOVO_INF"
        return f"{prefixo}_{self._contador_novos_tamanhos}"

    def _gerar_cor_aleatoria(self) -> str:
        return f"#{randint(40, 240):02x}{randint(40, 240):02x}{randint(40, 240):02x}"

    def _sincronizar_gradacao_no_molde(self):
        moldes_alvo = self._moldes_alvo_graduacao()
        if not moldes_alvo:
            return
        combo_grade = getattr(self, "cmb_grade_tamanhos", None)
        if not isinstance(combo_grade, QComboBox):
            return
        grade_nome = combo_grade.currentText().strip()
        linhas = [dict(l) for l in self._graduacao_linhas]
        ativos = [str(l.get("tamanho")) for l in self._graduacao_linhas if l.get("ativo", True)]
        for molde in moldes_alvo:
            molde["graduacao_grade_nome"] = grade_nome
            molde["graduacao_tamanhos"] = [dict(l) for l in linhas]
            molde["graduacao_tamanhos_ativos"] = list(ativos)

    def _moldes_alvo_graduacao(self) -> list[dict]:
        combo_aplicar = getattr(self, "cmb_aplicar_grade", None)
        modo_aplicar = combo_aplicar.currentText().strip().lower() if isinstance(combo_aplicar, QComboBox) else "ao molde"
        molde_atual = self._molde_atual()
        if molde_atual is None:
            return []
        if modo_aplicar == "ao molde":
            return [molde_atual]
        return [ref.dados for ref in self._refs if isinstance(ref.dados, dict)]

    def _atualizar_opcoes_tecido(self):
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", [])
        if not isinstance(elementos, list):
            elementos = []
        tecidos = {
            str(el.get("tecido") or "").strip()
            for el in elementos
            if isinstance(el, dict) and el.get("molde")
        }
        tecidos.update({
            str(chave).strip()
            for chave in getattr(self.canvas, "_cores_tecidos", {}).keys()
            if str(chave).strip()
        })
        tecidos.discard("")
        atual = self.ed_tecido.currentText().strip()
        self.ed_tecido.blockSignals(True)
        self.ed_tecido.clear()
        self.ed_tecido.addItems(sorted(tecidos))
        if atual:
            self.ed_tecido.setCurrentText(atual)
        elif self.ed_tecido.count() == 0:
            self.ed_tecido.setCurrentText("1")
        self.ed_tecido.blockSignals(False)

    def _criar_tab_visualizacao(self) -> QWidget:
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(12, 10, 12, 6)
        layout.setSpacing(8)

        topo = QGroupBox("Manipular")
        grid = QGridLayout(topo)
        grid.setContentsMargins(10, 14, 10, 8)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        self.cmb_elementos_molde = QComboBox()
        self.cmb_elementos_molde.addItems(["Nenhum", "Nome", "Descrição", "Observações", "Fio", "Números"])
        self.ed_referencia = QLineEdit()
        self.ed_alinhamento = QLineEdit()
        self.ed_angulo_texto = QLineEdit()
        self.ed_altura_texto = QLineEdit()
        self.ed_espaco_linhas = QLineEdit()
        for ed in (self.ed_referencia, self.ed_alinhamento, self.ed_angulo_texto, self.ed_altura_texto, self.ed_espaco_linhas):
            ed.setEnabled(False)

        grid.addWidget(QLabel("Elementos do molde"), 0, 0)
        grid.addWidget(self.cmb_elementos_molde, 0, 1)
        grid.addWidget(QLabel("Ângulo do texto"), 0, 2)
        grid.addWidget(self.ed_angulo_texto, 0, 3)
        grid.addWidget(QLabel("°"), 0, 4)
        grid.addWidget(QLabel("Referência"), 1, 0)
        grid.addWidget(self.ed_referencia, 1, 1)
        grid.addWidget(QLabel("Altura do texto (cm)"), 1, 2)
        grid.addWidget(self.ed_altura_texto, 1, 3, 1, 2)
        grid.addWidget(QLabel("Alinhamento"), 2, 0)
        grid.addWidget(self.ed_alinhamento, 2, 1)
        grid.addWidget(QLabel("Espaço entre linhas (cm)"), 2, 2)
        grid.addWidget(self.ed_espaco_linhas, 2, 3, 1, 2)

        box_vis = QGroupBox("Visualização")
        gvis = QGridLayout(box_vis)
        gvis.setContentsMargins(10, 14, 10, 8)
        gvis.setHorizontalSpacing(24)
        gvis.setVerticalSpacing(10)

        self.chk_mostrar_nome = QCheckBox("Nome")
        self.chk_preencher = QCheckBox("Preencher")
        self.chk_mostrar_fio = QCheckBox("Fio")
        self.chk_mostrar_numeros = QCheckBox("Números")
        self.chk_graduacao = QCheckBox("Graduação")
        self.chk_pique = QCheckBox("Pique")

        self.chk_visual_descricao = QCheckBox("Descrição")
        self.chk_linhas_aux = QCheckBox("Linhas auxiliares")
        self.chk_costura = QCheckBox("Costura")
        self.chk_caminho_grade = QCheckBox("Caminho grade")
        self.chk_perimetro_molde = QCheckBox("Perímetro molde")
        self.chk_margem_visual = QCheckBox("Margem")

        self.chk_modelo = QCheckBox("Modelo")
        self.chk_grade_tam = QCheckBox("Grade de tamanhos")
        self.chk_tecido_visual = QCheckBox("Tecido")
        self.chk_quantidade_visual = QCheckBox("Quantidade")
        self.chk_giro_visual = QCheckBox("Giro")

        self.chk_mostrar_nome.setChecked(True)
        self.chk_mostrar_fio.setChecked(True)
        self.chk_mostrar_numeros.setChecked(True)
        self.chk_pique.setChecked(True)
        self.chk_linhas_aux.setChecked(True)
        self.chk_quantidade_visual.setChecked(True)
        self.chk_margem_visual.setChecked(True)

        gvis.addWidget(self.chk_mostrar_nome, 0, 0)
        gvis.addWidget(self.chk_visual_descricao, 0, 2)
        gvis.addWidget(self.chk_modelo, 0, 4)
        gvis.addWidget(self.chk_preencher, 1, 0)
        gvis.addWidget(QLabel("-  Cor"), 1, 1)
        self.btn_cor_preenchimento = QPushButton("")
        self.btn_cor_preenchimento.setFixedSize(20, 20)
        self.btn_cor_preenchimento.setCursor(Qt.PointingHandCursor)
        self.btn_cor_preenchimento.setToolTip("Escolher cor de preenchimento do molde")
        self.btn_cor_preenchimento.clicked.connect(self._escolher_cor)
        self.btn_cor_preenchimento.setStyleSheet("background:#58dfe3; border:1px solid #8a939c; padding:0;")
        gvis.addWidget(self.btn_cor_preenchimento, 1, 2, alignment=Qt.AlignLeft)
        gvis.addWidget(self.chk_linhas_aux, 1, 3)
        gvis.addWidget(self.chk_grade_tam, 1, 5)
        gvis.addWidget(self.chk_mostrar_fio, 2, 0)
        gvis.addWidget(self.chk_costura, 2, 3)
        gvis.addWidget(self.chk_tecido_visual, 2, 5)
        gvis.addWidget(self.chk_mostrar_numeros, 3, 0)
        gvis.addWidget(self.chk_caminho_grade, 3, 3)
        gvis.addWidget(self.chk_quantidade_visual, 3, 5)
        gvis.addWidget(self.chk_graduacao, 4, 0)
        gvis.addWidget(self.chk_perimetro_molde, 4, 3)
        gvis.addWidget(self.chk_giro_visual, 4, 5)
        gvis.addWidget(self.chk_pique, 5, 0)
        gvis.addWidget(self.chk_margem_visual, 5, 3)
        for linha in range(6):
            gvis.setRowMinimumHeight(linha, 30)

        rodape = QHBoxLayout()
        self.btn_aplicar_visual = QPushButton("Aplicar todos")
        self.btn_aplicar_visual.setObjectName("ApplyBlueButton")
        self.btn_aplicar_visual.clicked.connect(self._aplicar)
        rodape.addWidget(self.btn_aplicar_visual, 0, Qt.AlignLeft)
        self.chk_mostrar_cor_tecidos = QCheckBox("Mostrar cor dos tecidos")
        self.chk_mostrar_cor_tecidos.toggled.connect(self._alternar_cor_tecidos_canvas)
        rodape.addWidget(self.chk_mostrar_cor_tecidos, 0, Qt.AlignLeft)
        self.btn_config_cor_tecidos = QPushButton("Configurar cor dos tecidos")
        self.btn_config_cor_tecidos.clicked.connect(self._abrir_config_cor_tecidos)
        rodape.addWidget(self.btn_config_cor_tecidos, 0, Qt.AlignLeft)
        rodape.addStretch(1)

        layout.addWidget(topo)
        layout.addWidget(box_vis)
        layout.addLayout(rodape)
        layout.addStretch(1)
        return aba

    def _criar_tab_margem(self) -> QWidget:
        aba = QWidget()
        layout = QHBoxLayout(aba)
        layout.setContentsMargins(14, 10, 14, 6)
        layout.setSpacing(12)

        self.tbl_margem = QTableWidget(8, 2)
        self.tbl_margem.setHorizontalHeaderLabels(["Elemento", "Margem(cm)"])
        self.tbl_margem.verticalHeader().setVisible(False)
        self.tbl_margem.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_margem.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_margem.setSelectionMode(QTableWidget.ExtendedSelection)
        self.tbl_margem.setSelectionBehavior(QTableWidget.SelectItems)
        self.tbl_margem.setEditTriggers(
            QTableWidget.DoubleClicked
            | QTableWidget.SelectedClicked
            | QTableWidget.EditKeyPressed
            | QTableWidget.AnyKeyPressed
        )
        self.tbl_margem.itemChanged.connect(self._quando_margem_item_alterado)
        self.tbl_margem.setFixedSize(215, 242)
        self._popular_tabela_margem()

        box = QGroupBox()
        box.setFixedWidth(450)
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 8, 8, 8)
        self.btn_aplicar_margem = QPushButton("Aplicar")
        self.btn_aplicar_margem.setFixedWidth(82)
        self.btn_aplicar_margem.clicked.connect(self._aplicar_margem_no_molde)
        v.addWidget(self.btn_aplicar_margem, 0, Qt.AlignLeft)
        v.addStretch(1)

        layout.addWidget(self.tbl_margem, 0, Qt.AlignTop)
        layout.addWidget(box, 0, Qt.AlignTop)
        layout.addStretch(1)
        return aba

    def _popular_tabela_margem(self):
        self._preencher_tabela_margem(self._molde_atual() if hasattr(self, "_indice_atual") else None)

    def _elementos_margem_do_molde(self, molde: dict | None) -> list[str]:
        if not isinstance(molde, dict):
            return []
        pontos_raw = molde.get("pontos")
        if not isinstance(pontos_raw, (list, tuple)):
            return []
        pontos: list[QPointF] = []
        for item in pontos_raw:
            ponto = self.preview._ponto_xy(item) if hasattr(self, "preview") else None
            if ponto is not None:
                pontos.append(ponto)
        if len(pontos) < 2:
            return []
        fechado = len(pontos) >= 3 and self._distancia_pontos_margem(pontos[0], pontos[-1]) <= 1e-6
        total = len(pontos) - 1 if fechado else len(pontos)
        if total < 2:
            return []
        if fechado:
            return [f"{i + 1}-{((i + 1) % total) + 1}" for i in range(total)]
        return [f"{i + 1}-{i + 2}" for i in range(total - 1)]

    def _preencher_tabela_margem(self, molde: dict | None):
        if not hasattr(self, "tbl_margem"):
            return
        self.tbl_margem.blockSignals(True)
        try:
            self.tbl_margem.clearContents()
            valores_salvos: dict[str, str] = {}
            if isinstance(molde, dict):
                for item in molde.get("margens_molde", []) or []:
                    if not isinstance(item, dict):
                        continue
                    elemento = str(item.get("elemento") or "").strip()
                    if elemento:
                        valores_salvos[elemento] = str(item.get("margem", 0) or 0)
                for dados in (molde.get("margens"), molde.get("margem_cm_por_elemento")):
                    if isinstance(dados, dict):
                        for elemento, valor in dados.items():
                            valores_salvos.setdefault(str(elemento), str(valor))

            elementos = self._elementos_margem_do_molde(molde)
            if not elementos and valores_salvos:
                elementos = list(valores_salvos.keys())

            self.tbl_margem.setRowCount(len(elementos))
            for row, elemento in enumerate(elementos):
                item_elemento = QTableWidgetItem(elemento)
                item_elemento.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.tbl_margem.setItem(row, 0, item_elemento)

                item_valor = QTableWidgetItem(str(valores_salvos.get(elemento, "0")))
                item_valor.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                self.tbl_margem.setItem(row, 1, item_valor)

            altura_linha = self.tbl_margem.verticalHeader().defaultSectionSize()
            altura = min(242, max(92, 31 + (len(elementos) * max(20, altura_linha))))
            self.tbl_margem.setFixedHeight(altura)
        finally:
            self.tbl_margem.blockSignals(False)

    def _quando_margem_item_alterado(self, item: QTableWidgetItem):
        if item is None or item.column() != 1:
            return
        linhas = self._linhas_margem_selecionadas()
        if len(linhas) <= 1 or item.row() not in linhas:
            self._atualizar_margem_em_tempo_real()
            return
        texto = item.text()
        self.tbl_margem.blockSignals(True)
        try:
            for row in linhas:
                if row == item.row():
                    continue
                item_valor = self.tbl_margem.item(row, 1)
                if item_valor is None:
                    item_valor = QTableWidgetItem()
                    self.tbl_margem.setItem(row, 1, item_valor)
                item_valor.setText(texto)
        finally:
            self.tbl_margem.blockSignals(False)
        self._atualizar_margem_em_tempo_real()

    def _linhas_margem_selecionadas(self) -> list[int]:
        if not hasattr(self, "tbl_margem"):
            return []
        linhas: set[int] = set()
        for faixa in self.tbl_margem.selectedRanges():
            for row in range(faixa.topRow(), faixa.bottomRow() + 1):
                linhas.add(row)
        for indice in self.tbl_margem.selectedIndexes():
            linhas.add(indice.row())
        return sorted(row for row in linhas if 0 <= row < self.tbl_margem.rowCount())

    def _margens_do_formulario(self) -> list[dict]:
        return [
            {"elemento": elemento, "margem": valor}
            for elemento, valor in self._coletar_margens_tabela().items()
        ]

    def _coletar_margens_tabela(self) -> dict[str, float]:
        margens: dict[str, float] = {}
        if not hasattr(self, "tbl_margem"):
            return margens
        for row in range(self.tbl_margem.rowCount()):
            item_elemento = self.tbl_margem.item(row, 0)
            item_margem = self.tbl_margem.item(row, 1)
            elemento = (item_elemento.text() if item_elemento else "").strip()
            texto = (item_margem.text() if item_margem else "0").replace("cm", "").replace(",", ".").strip()
            if not elemento:
                continue
            try:
                valor = float(texto or 0)
            except ValueError:
                valor = 0.0
            margens[elemento] = max(0.0, valor)
        return margens

    def _formatar_float_margem(self, valor: float) -> str:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            numero = 0.0
        if abs(numero - round(numero)) < 1e-9:
            return str(int(round(numero)))
        return (f"{numero:.3f}".rstrip("0").rstrip(".")).replace(".", ",")

    def _atualizar_margem_em_tempo_real(self):
        molde = self._molde_atual()
        if not molde or not hasattr(self, "tbl_margem"):
            return
        margens = self._coletar_margens_tabela()
        self._salvar_margens_no_molde(molde, margens)
        self._forcar_margem_no_canvas(molde, margens, bool(molde.get("mostrar_margem", False)))
        self.preview.set_molde(dict(molde))

    def _salvar_margens_no_molde(self, molde: dict, margens: dict[str, float]):
        tem_margem = any(float(v or 0) > 0 for v in margens.values())
        molde["margens_molde"] = [{"elemento": k, "margem": float(v)} for k, v in margens.items()]
        molde["margens"] = {k: self._formatar_float_margem(v) for k, v in margens.items()}
        molde["margem_cm_por_elemento"] = dict(molde["margens"])
        molde["mostrar_margem"] = tem_margem
        if hasattr(self, "chk_margem_visual"):
            with QSignalBlocker(self.chk_margem_visual):
                self.chk_margem_visual.setChecked(tem_margem)

    def _forcar_margem_no_canvas(self, molde: dict, margens: dict[str, float], tem_margem: bool):
        indice = self._indice_atual
        if indice is None:
            return
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", None)
        if isinstance(elementos, list) and 0 <= int(indice) < len(elementos):
            alvo = elementos[int(indice)]
            if isinstance(alvo, dict):
                self._salvar_margens_no_molde(alvo, margens)
                alvo["mostrar_margem"] = bool(tem_margem)

        cache = getattr(self.canvas, "_margens_visuais_forcadas", None)
        if not isinstance(cache, dict):
            cache = {}
        if tem_margem:
            cache[int(indice)] = {
                "margens": {k: self._formatar_float_margem(v) for k, v in margens.items()},
                "mostrar_margem": True,
            }
        else:
            cache.pop(int(indice), None)
        setattr(self.canvas, "_margens_visuais_forcadas", cache)
        self._remover_margens_visuais_soltas()
        if hasattr(self.canvas, "update"):
            self.canvas.update()
        if hasattr(self.canvas, "repaint"):
            self.canvas.repaint()

    def _remover_margens_visuais_soltas(self):
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", None)
        if isinstance(elementos, list):
            elementos[:] = [
                el for el in elementos
                if not (isinstance(el, dict) and el.get("guimma_margem_linha_canvas"))
            ]

    def _sincronizar_margem_visual_como_elemento(self, indice_molde: int, pontos_margem: list | None, tem_margem: bool):
        self._remover_margens_visuais_soltas()

    def _distancia_pontos_margem(self, a: QPointF, b: QPointF) -> float:
        return sqrt(((a.x() - b.x()) ** 2) + ((a.y() - b.y()) ** 2))

    def _criar_tab_cam(self) -> QWidget:
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(12, 10, 12, 6)
        layout.setSpacing(8)

        topo = QGroupBox()
        grid = QGridLayout(topo)
        grid.setContentsMargins(10, 14, 10, 8)
        grid.addWidget(QLabel("Tipo corte"), 0, 0)
        self.cmb_tipo_corte_cam = QComboBox()
        self.cmb_tipo_corte_cam.addItems(["Completo", "Par", "Espelhado", "Único"])
        grid.addWidget(self.cmb_tipo_corte_cam, 0, 1)
        self.btn_add_cam = QPushButton("Adicionar")
        self.btn_rem_cam = QPushButton("Remover")
        grid.addWidget(self.btn_add_cam, 0, 3)
        grid.addWidget(self.btn_rem_cam, 0, 4)
        grid.setColumnStretch(2, 1)

        layout.addWidget(topo)
        layout.addStretch(1)
        return aba

    def _criar_tab_ferramentas(self) -> QWidget:
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(12, 10, 12, 6)
        layout.setSpacing(8)

        box = QGroupBox("Elementos")
        grid = QGridLayout(box)
        grid.setContentsMargins(10, 14, 10, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        labels = ["Contorno", "Nome", "Descrição", "Observações", "Fio", "Costura"]
        cores = ["#ff5a12", "#6b8f1f", "#3f63d8", "#f0d100", "#9d00c7", "#d4d4d4"]
        self._ferramentas_linhas: list[tuple[QComboBox, QPushButton, QCheckBox]] = []
        for i, nome in enumerate(labels):
            lbl = QLabel(nome)
            cmb = QComboBox()
            cmb.addItems(["-", "1", "2", "3", "4", "5", "6", "7", "8"])
            cmb.setCurrentText(str(i + 1 if i < 5 else "-"))
            btn_cor = QPushButton("")
            btn_cor.setFixedSize(30, 22)
            btn_cor.setStyleSheet(f"background:{cores[i]}; border:1px solid #343434;")
            chk = QCheckBox("Usar")
            chk.setChecked(i < 5)
            if nome == "Costura":
                cmb.setEnabled(False)
                btn_cor.setEnabled(False)
                chk.setEnabled(False)
            grid.addWidget(lbl, i, 0)
            grid.addWidget(cmb, i, 1)
            grid.addWidget(btn_cor, i, 2)
            grid.addWidget(chk, i, 3)
            self._ferramentas_linhas.append((cmb, btn_cor, chk))

        self.btn_config_ferramentas = QPushButton("Configurar Ferramentas")
        self.btn_config_defaults = QPushButton("Configurar Defaults")
        self.btn_config_ferramentas.clicked.connect(self._abrir_config_ferramentas)
        self.btn_config_defaults.clicked.connect(self._abrir_config_defaults)
        grid.addWidget(self.btn_config_ferramentas, 0, 4, 1, 2)
        grid.addWidget(self.btn_config_defaults, 1, 4, 1, 2)

        self.cmb_extra1 = QComboBox()
        self.cmb_extra1.addItems(["-", "Piques sobre o contorno", "Piques internos", "Linhas auxiliares"])
        self.cmb_extra2 = QComboBox()
        self.cmb_extra2.addItems(["1", "2", "3", "4", "5", "6", "7", "8", "9"])
        self.cmb_extra2.setCurrentText("6")
        self.btn_cor_extra = QPushButton("")
        self.btn_cor_extra.setFixedSize(30, 22)
        self.btn_cor_extra.setStyleSheet("background:#19bdb7; border:1px solid #343434;")
        self.btn_cor_extra.clicked.connect(lambda: self._escolher_cor_ferramenta(self.btn_cor_extra))
        self.chk_extra = QCheckBox("Usar")
        self.chk_extra.setChecked(True)
        btn_aplicar = QPushButton("Aplicar todos")
        btn_aplicar.setObjectName("ApplyBlueButton")
        btn_aplicar.clicked.connect(self._aplicar)
        grid.addWidget(self.cmb_extra1, 6, 0, 1, 2)
        grid.addWidget(self.cmb_extra2, 6, 2)
        grid.addWidget(self.btn_cor_extra, 6, 3)
        grid.addWidget(self.chk_extra, 6, 4)
        grid.addWidget(btn_aplicar, 6, 5)
        self.lbl_aplicar_extra = QLabel("")
        grid.addWidget(self.lbl_aplicar_extra, 7, 0, 1, 6)
        self.cmb_extra1.currentIndexChanged.connect(self._atualizar_config_extra_ferramenta)
        self._atualizar_config_extra_ferramenta()

        layout.addWidget(box)
        layout.addStretch(1)
        return aba

    def _abrir_config_ferramentas(self):
        dialog = ConfigurarFerramentasDialog(self)
        dialog.exec()

    def _abrir_config_defaults(self):
        valores = []
        for cmb, btn_cor, chk in getattr(self, "_ferramentas_linhas", []):
            cor = self._cor_botao(btn_cor)
            valores.append(
                {
                    "indice": cmb.currentText(),
                    "cor": cor,
                    "usar": chk.isChecked(),
                }
            )
        dialog = ConfigurarDefaultsDialog(valores, self)
        if dialog.exec() != QDialog.Accepted:
            return
        novos = dialog.valores()
        for i, (cmb, btn_cor, chk) in enumerate(getattr(self, "_ferramentas_linhas", [])):
            if i >= len(novos):
                break
            dados = novos[i]
            if cmb.isEnabled() and dados.get("indice"):
                cmb.setCurrentText(str(dados["indice"]))
            if btn_cor.isEnabled() and dados.get("cor"):
                btn_cor.setStyleSheet(f"background:{dados['cor']}; border:1px solid #343434;")
            if chk.isEnabled():
                chk.setChecked(bool(dados.get("usar", False)))

    @staticmethod
    def _cor_botao(botao: QPushButton) -> str:
        estilo = botao.styleSheet() or ""
        for trecho in estilo.split(";"):
            if "background" in trecho and ":" in trecho:
                return trecho.split(":", 1)[1].strip()
        return botao.palette().button().color().name()

    def _escolher_cor_ferramenta(self, botao: QPushButton):
        cor_atual = QColor(self._cor_botao(botao))
        dialog = QColorDialog(cor_atual, self)
        dialog.setWindowTitle("Cor da ferramenta")
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        if dialog.exec() != QDialog.Accepted:
            return
        cor = dialog.selectedColor()
        if cor.isValid():
            botao.setStyleSheet(f"background:{cor.name()}; border:1px solid #343434;")

    def _atualizar_config_extra_ferramenta(self):
        mapa = {
            0: {"indice": "6", "cor": "#d6d6d6", "texto": "Aplique a todos os moldes as configurações de ferramentas", "usar": False},
            1: {"indice": "6", "cor": "#19bdb7", "texto": "Selecione os \"piques sobre o contorno\" para aplicar a todos.", "usar": True},
            2: {"indice": "7", "cor": "#d0d0d0", "texto": "Selecione os \"piques internos\" para aplicar a todos.", "usar": True},
            3: {"indice": "8", "cor": "#93ed2b", "texto": "Selecione as \"linhas auxiliares\" para aplicar a todos.", "usar": True},
        }
        dados = mapa.get(self.cmb_extra1.currentIndex(), mapa[0])
        if hasattr(self, "cmb_extra2"):
            self.cmb_extra2.setCurrentText(dados["indice"])
        if hasattr(self, "btn_cor_extra"):
            self.btn_cor_extra.setStyleSheet(f"background:{dados['cor']}; border:1px solid #343434;")
            self.btn_cor_extra.setEnabled(bool(dados.get("usar", True)))
        if hasattr(self, "chk_extra"):
            self.chk_extra.setChecked(bool(dados.get("usar", True)))
            self.chk_extra.setEnabled(self.cmb_extra1.currentIndex() != 0)
        if hasattr(self, "cmb_extra2"):
            self.cmb_extra2.setEnabled(self.cmb_extra1.currentIndex() != 0)
        if hasattr(self, "lbl_aplicar_extra"):
            self.lbl_aplicar_extra.setText(dados["texto"])

    def recarregar_lista(self):
        _log_propriedades_debug("recarregar_lista() iniciado")
        atual_idx = self._indice_atual
        self._refs = self._coletar_moldes()
        self._itens_molde_por_indice = {}
        self._combos_tecido_por_item = {}
        _log_propriedades_debug(f"recarregar_lista(): moldes encontrados={len(self._refs)}; indice_atual_anterior={atual_idx}")
        self._suspender_item_changed = True
        self._suspender_combo_tecido_arvore = True
        self.arvore.clear()
        raiz = QTreeWidgetItem(["Tecidos"])
        icone_tecido = QIcon(str(ICONS_DIR / "tecidos.svg"))
        raiz.setIcon(0, icone_tecido)
        raiz.setFlags(raiz.flags() & ~Qt.ItemIsEditable)
        raiz.setExpanded(True)
        self.arvore.addTopLevelItem(raiz)

        grupos: dict[str, list[MoldeRef]] = {}
        tecidos_disponiveis: set[str] = set(self._tecidos_disponiveis())
        for ref in self._refs:
            tecido = str(ref.dados.get("tecido") or "").strip()
            grupo = tecido if tecido else "1"
            tecidos_disponiveis.add(grupo)
            grupos.setdefault(grupo, []).append(ref)

        def _ord_tecido(valor: str):
            txt = str(valor).strip()
            return (0, int(txt)) if txt.isdigit() else (1, txt.lower())

        referencia_global = self._assinatura_grade_referencia_global()
        for grupo_nome in sorted(grupos.keys() or tecidos_disponiveis, key=_ord_tecido):
            itens = grupos.get(grupo_nome, [])
            pai = QTreeWidgetItem([grupo_nome])
            pai.setIcon(0, icone_tecido)
            pai.setFlags((pai.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable) & ~Qt.ItemIsEditable)
            try:
                pai.setData(0, Qt.UserRole + 1, grupo_nome)
            except Exception:
                pass
            raiz.addChild(pai)
            self._instalar_combo_tecido_item(pai, grupo_nome)
            for ref in itens:
                item = QTreeWidgetItem([ref.nome or f"Molde {ref.indice + 1}"])
                item.setData(0, Qt.UserRole, ref.indice)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                item.setIcon(0, self._icone_status_molde(ref, referencia_grade=referencia_global))
                pai.addChild(item)
                self._itens_molde_por_indice[int(ref.indice)] = item

        raiz.setExpanded(True)
        for i in range(raiz.childCount()):
            raiz.child(i).setExpanded(True)

        escolhido = None
        for item in self._iter_items(raiz):
            idx = item.data(0, Qt.UserRole)
            if idx is not None and idx == atual_idx:
                escolhido = item
                break
        if escolhido is None:
            for item in self._iter_items(raiz):
                if item.data(0, Qt.UserRole) is not None:
                    escolhido = item
                    break
        self._suspender_combo_tecido_arvore = False
        if escolhido:
            self.arvore.setCurrentItem(escolhido)
            self._indice_atual = int(escolhido.data(0, Qt.UserRole))
            self._atualizar_combo_moldes()
            _log_propriedades_debug(f"recarregar_lista(): item escolhido indice={self._indice_atual}")
            self._preencher_campos(self._molde_atual())
        else:
            self._indice_atual = None
            self._atualizar_combo_moldes()
            _log_propriedades_debug("recarregar_lista(): nenhum item escolhido; preenchendo campos vazios")
            self._preencher_campos(None)
        self._suspender_item_changed = False

    def _tecidos_disponiveis(self) -> list[str]:
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", [])
        tecidos: set[str] = set()
        if isinstance(elementos, list):
            for el in elementos:
                if isinstance(el, dict) and el.get("molde"):
                    tecido = str(el.get("tecido") or "").strip()
                    if tecido:
                        tecidos.add(tecido)
        for chave in getattr(self.canvas, "_cores_tecidos", {}).keys():
            tecido = str(chave or "").strip()
            if tecido:
                tecidos.add(tecido)
        if hasattr(self, "ed_tecido"):
            tecido_atual = self.ed_tecido.currentText().strip()
            if tecido_atual:
                tecidos.add(tecido_atual)
        if not tecidos:
            tecidos.add("1")

        def _ord_tecido(valor: str):
            txt = str(valor).strip()
            return (0, int(txt)) if txt.isdigit() else (1, txt.lower())

        return sorted(tecidos, key=_ord_tecido)

    def _instalar_combo_tecido_item(self, item: QTreeWidgetItem, tecido_atual: str):
        combo = QComboBox(self.arvore)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMinimumHeight(20)
        combo.installEventFilter(self)
        combo.setStyleSheet(
            "QComboBox { background:#ffffff; border:1px solid #c4ccd5; border-radius:4px; color:#111111; padding:1px 18px 1px 6px; }"
            "QComboBox:hover { border-color:#7fa7d7; }"
            "QComboBox::drop-down { width:18px; border-left:1px solid #d2dae2; background:#f4f8fc; border-top-right-radius:4px; border-bottom-right-radius:4px; }"
            "QComboBox::down-arrow { width:0px; height:0px; }"
            "QComboBox QAbstractItemView { background:#ffffff; color:#111111; border:1px solid #9fb4ca; selection-background-color:#d9ecff; selection-color:#111111; outline:0; }"
        )
        opcoes = self._tecidos_disponiveis()
        if tecido_atual and tecido_atual not in opcoes:
            opcoes.append(tecido_atual)
        combo.addItems(opcoes)
        combo.setCurrentText(str(tecido_atual or "1"))
        combo.activated.connect(lambda _=0, it=item, cb=combo: self._alterar_tecido_grupo_pela_arvore(it, cb.currentText()))
        if combo.lineEdit() is not None:
            combo.lineEdit().editingFinished.connect(
                lambda it=item, cb=combo: self._alterar_tecido_grupo_pela_arvore(it, cb.currentText())
            )
        self.arvore.setItemWidget(item, 0, combo)
        self._combos_tecido_por_item[id(item)] = combo

    def eventFilter(self, obj, event):  # noqa: N802
        if isinstance(obj, QComboBox) and event.type() == QEvent.Wheel:
            event.ignore()
            return True
        if isinstance(obj, QComboBox) and event.type() == QEvent.KeyPress:
            teclas_navegacao = {Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End}
            if event.key() in teclas_navegacao and not obj.view().isVisible():
                obj.showPopup()
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def _aplicar_tecido_formulario_confirmado(self):
        if self._suspender_auto_aplicar:
            return
        molde = self._molde_atual()
        if not molde:
            return
        novo_tecido = str(self.ed_tecido.currentText() or "").strip()
        if not novo_tecido:
            return
        tecido_atual = str(molde.get("tecido") or "").strip()
        if novo_tecido == tecido_atual:
            return
        self._aplicar_imediato_formulario()
        molde["grupo_molde"] = novo_tecido
        self._atualizar_opcoes_tecido()
        self.canvas.update()
        QTimer.singleShot(0, self.recarregar_lista)

    def _alterar_tecido_grupo_pela_arvore(self, item: QTreeWidgetItem, novo_tecido: str):
        if self._suspender_combo_tecido_arvore:
            return
        novo_tecido = str(novo_tecido or "").strip()
        if not novo_tecido:
            return
        try:
            tecido_antigo = str(item.data(0, Qt.UserRole + 1) or item.text(0) or "").strip()
        except Exception:
            tecido_antigo = str(item.text(0) or "").strip()
        if novo_tecido == tecido_antigo:
            return

        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", [])
        if not isinstance(elementos, list):
            return

        indices_afetados: list[int] = []
        for i in range(item.childCount()):
            filho = item.child(i)
            idx = filho.data(0, Qt.UserRole)
            if idx is None:
                continue
            idx_int = int(idx)
            if 0 <= idx_int < len(elementos):
                el = elementos[idx_int]
                if isinstance(el, dict) and el.get("molde"):
                    el["tecido"] = novo_tecido
                    el["grupo_molde"] = novo_tecido
                    indices_afetados.append(idx_int)

        try:
            item.setData(0, Qt.UserRole + 1, novo_tecido)
        except Exception:
            pass
        item.setText(0, novo_tecido)
        if self._indice_atual in indices_afetados and hasattr(self, "ed_tecido"):
            with QSignalBlocker(self.ed_tecido):
                self.ed_tecido.setCurrentText(novo_tecido)
            self.preview.set_molde(dict(self._molde_atual() or {}))
        self._atualizar_opcoes_tecido()
        self.canvas.update()
        self.recarregar_lista()

    def _renomear_molde_atual_instantaneo(self, texto: str):
        if self._suspender_auto_aplicar:
            return
        molde = self._molde_atual()
        if not molde:
            return
        novo_nome = str(texto or "").strip()
        if not novo_nome:
            return
        molde["nome_molde"] = novo_nome
        self._sincronizar_nome_molde_atual_sem_recarregar(novo_nome)
        self.preview.set_molde(dict(molde))
        self.canvas.update()

    def _sincronizar_nome_molde_atual_sem_recarregar(self, novo_nome: str | None = None):
        if self._indice_atual is None:
            return
        molde = self._molde_atual()
        if not molde:
            return
        nome = str(novo_nome if novo_nome is not None else molde.get("nome_molde") or f"Molde {self._indice_atual + 1}").strip()
        if not nome:
            return
        item = self._itens_molde_por_indice.get(int(self._indice_atual))
        if item is not None:
            self._suspender_item_changed = True
            item.setText(0, nome)
            self._suspender_item_changed = False
        for ref in self._refs:
            if int(ref.indice) == int(self._indice_atual):
                ref.nome = nome
                break
        if hasattr(self, "cmb_molde"):
            pos = self.cmb_molde.findData(self._indice_atual)
            if pos >= 0:
                with QSignalBlocker(self.cmb_molde):
                    self.cmb_molde.setItemText(pos, nome)

    def _assinatura_grade(self, molde: dict) -> str:
        nome = str(molde.get("graduacao_grade_nome") or "").strip()
        linhas = molde.get("graduacao_tamanhos")
        if not isinstance(linhas, list):
            return nome
        tags = [str(l.get("tamanho") or "") for l in linhas if isinstance(l, dict)]
        return f"{nome}|{'/'.join(tags)}"

    def _assinatura_grade_referencia_global(self) -> str:
        for ref in sorted(self._refs, key=lambda r: r.indice):
            dados = ref.dados if isinstance(ref.dados, dict) else {}
            assinatura = self._assinatura_grade(dados)
            if assinatura:
                return assinatura
        return ""

    def _icone_status_molde(self, ref: MoldeRef, referencia_grade: str | None = None) -> QIcon:
        dados = ref.dados if isinstance(ref.dados, dict) else {}
        pronto = bool(dados.get("molde_pronto", False))
        assinatura = self._assinatura_grade(dados)
        if not pronto:
            return QIcon(str(ICONS_DIR / "molde-nao-pronto.svg"))
        if referencia_grade and assinatura and assinatura != referencia_grade:
            return QIcon(str(ICONS_DIR / "grade-diferente-modelo.svg"))
        return QIcon(str(ICONS_DIR / "molde-pronto.svg"))

    def _iter_items(self, pai: QTreeWidgetItem):
        for i in range(pai.childCount()):
            child = pai.child(i)
            yield child
            yield from self._iter_items(child)

    def _coletar_moldes(self) -> list[MoldeRef]:
        refs: list[MoldeRef] = []
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", None)
        if not isinstance(elementos, list):
            return refs
        for idx, el in enumerate(elementos):
            if not isinstance(el, dict):
                continue
            if not el.get("molde"):
                continue
            refs.append(MoldeRef(indice=idx, nome=str(el.get("nome_molde") or f"K{idx + 1}"), dados=el))
        return refs

    def _indice_molde_preferencial(self) -> int | None:
        selecionados = getattr(self.canvas, "_selecionados", set())
        if not isinstance(selecionados, (set, list, tuple)):
            return None
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", None)
        if not isinstance(elementos, list):
            return None
        for idx in selecionados:
            if isinstance(idx, int) and 0 <= idx < len(elementos):
                el = elementos[idx]
                if isinstance(el, dict) and el.get("molde"):
                    return idx
        return None

    def _quando_troca_selecao(self):
        item = self.arvore.currentItem()
        if not item:
            self._indice_atual = None
            self._preencher_campos(None)
            return
        idx = item.data(0, Qt.UserRole)
        if idx is None:
            return
        self._indice_atual = int(idx)
        self._preencher_campos(self._molde_atual())

    def _quando_item_editado(self, item: QTreeWidgetItem, coluna: int):
        if self._suspender_item_changed or coluna != 0:
            return
        novo_nome = item.text(0).strip()
        if not novo_nome:
            return
        idx = item.data(0, Qt.UserRole)
        if idx is not None:
            cena = getattr(self.canvas, "cena", None)
            elementos = getattr(cena, "elementos", [])
            if isinstance(elementos, list) and 0 <= int(idx) < len(elementos):
                el = elementos[int(idx)]
                if isinstance(el, dict) and el.get("molde"):
                    el["nome_molde"] = novo_nome
                    if int(idx) == self._indice_atual and hasattr(self, "cmb_molde"):
                        with QSignalBlocker(self.cmb_molde):
                            self.cmb_molde.setCurrentText(novo_nome)
                    self._sincronizar_nome_molde_atual_sem_recarregar(novo_nome if int(idx) == self._indice_atual else None)
                    self._atualizar_combo_moldes()
                    self.preview.set_molde(dict(el))
                    self.canvas.update()
            return
        parent = item.parent()
        if parent is None:
            return
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", [])
        if not isinstance(elementos, list):
            return
        for i in range(item.childCount()):
            filho = item.child(i)
            idx_filho = filho.data(0, Qt.UserRole)
            if idx_filho is None:
                continue
            if 0 <= int(idx_filho) < len(elementos):
                el = elementos[int(idx_filho)]
                if isinstance(el, dict) and el.get("molde"):
                    el["tecido"] = novo_nome
                    el["grupo_molde"] = novo_nome
        self.canvas.update()

    def _molde_atual(self) -> dict | None:
        if self._indice_atual is None:
            _log_propriedades_debug("_molde_atual(): indice_atual é None")
            return None
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", None)
        if not isinstance(elementos, list):
            _log_propriedades_debug(f"_molde_atual(): elementos inválido: {type(elementos).__name__}")
            return None
        if 0 <= self._indice_atual < len(elementos):
            el = elementos[self._indice_atual]
            if isinstance(el, dict) and el.get("molde"):
                _log_propriedades_debug(f"_molde_atual(): molde válido encontrado no índice {self._indice_atual}")
                return el
            _log_propriedades_debug(f"_molde_atual(): elemento no índice {self._indice_atual} não é molde válido")
        else:
            _log_propriedades_debug(f"_molde_atual(): índice fora da faixa. indice={self._indice_atual}; total={len(elementos)}")
        return None

    def _int_seguro(self, valor, padrao: int) -> int:
        try:
            return int(valor)
        except (TypeError, ValueError):
            return int(padrao)

    def _atualizar_estado_faixa_giro(self, texto: str | None = None):
        valor = str(texto if texto is not None else self.cmb_giro.currentText()).strip().lower()
        ativo = valor in {"faixa", "180 graus + faixa"}
        self.ed_faixa_giro.setEnabled(ativo)
        if ativo:
            self.ed_faixa_giro.setStyleSheet("")
        else:
            self.ed_faixa_giro.setStyleSheet("background:#efefef; color:#7a7a7a;")
        self.ed_faixa_giro.repaint()

    def _preencher_campos(self, molde: dict | None):
        self._suspender_auto_aplicar = True
        self.preview.set_config_cores_tecidos(
            getattr(self.canvas, "_cores_tecidos", {}),
            bool(getattr(self.canvas, "_mostrar_cor_tecidos", False)),
        )
        self.preview.set_molde(molde)
        if molde is None:
            with QSignalBlocker(self.cmb_molde):
                self.cmb_molde.setCurrentIndex(-1)
            self._preencher_tabela_margem(None)
            self.ed_descricao.clear()
            self.ed_tecido.setCurrentText("1")
            self.sp_qtd_modelo.setValue(1)
            self.cmb_tipo_corte.setCurrentText("Completo")
            self.cmb_espelhar.setCurrentText("Nenhum")
            self.cmb_giro.setCurrentText("180 graus")
            self.ed_faixa_giro.setText("0")
            self.ed_giro_inicial.setText("0")
            self.chk_molde_pronto.setChecked(False)
            self.chk_perm_alt.setChecked(False)
            self.chk_par.setChecked(False)
            self.chk_dobra_v.setChecked(False)
            self.chk_dobra_h.setChecked(False)
            self.chk_reflete_v.setChecked(False)
            self.chk_reflete_h.setChecked(False)
            self._cor_visual = "#ffffff"
            self.btn_cor_preenchimento.setStyleSheet("background:#58dfe3; border:1px solid #8a939c; padding:0;")
            self._atualizar_estado_faixa_giro()
            self._suspender_auto_aplicar = False
            return

        pos_combo = self.cmb_molde.findData(self._indice_atual)
        if pos_combo >= 0:
            with QSignalBlocker(self.cmb_molde):
                self.cmb_molde.setCurrentIndex(pos_combo)
        self.ed_descricao.setPlainText(str(molde.get("descricao") or ""))
        tipo_corte = str(molde.get("tipo_corte") or "Completo")
        idx_tipo_corte = self.cmb_tipo_corte.findText(tipo_corte)
        self.cmb_tipo_corte.setCurrentIndex(idx_tipo_corte if idx_tipo_corte >= 0 else 0)
        self._atualizar_opcoes_tecido()
        self.ed_tecido.setCurrentText(str(molde.get("tecido") or "1"))
        self.sp_qtd_modelo.setValue(self._int_seguro(molde.get("qtd_modelo", 1) or 1, 1))
        self.chk_molde_pronto.setChecked(bool(molde.get("molde_pronto", False)))
        self.chk_perm_alt.setChecked(bool(molde.get("permitir_alteracoes_encaixe", False)))
        self.chk_par.setChecked(bool(molde.get("par", False)))
        self.chk_dobra_v.setChecked(bool(molde.get("dobra_vertical", False)))
        self.chk_dobra_h.setChecked(bool(molde.get("dobra_horizontal", False)))
        self.chk_reflete_v.setChecked(bool(molde.get("refletido_vertical", False)))
        self.chk_reflete_h.setChecked(bool(molde.get("refletido_horizontal", False)))
        self.ed_faixa_giro.setText(str(molde.get("faixa_giro", 0) or 0))
        self._atualizar_estado_faixa_giro()
        self.ed_giro_inicial.setText(str(molde.get("giro_inicial", 0) or 0))
        tipo_espelho = str(molde.get("espelhar") or "Nenhum")
        idx_espelho = self.cmb_espelhar.findText(tipo_espelho)
        self.cmb_espelhar.setCurrentIndex(idx_espelho if idx_espelho >= 0 else self.cmb_espelhar.findText("Nenhum"))
        tipo_giro = str(molde.get("giro") or "180 graus")
        idx_giro = self.cmb_giro.findText(tipo_giro)
        self.cmb_giro.setCurrentIndex(idx_giro if idx_giro >= 0 else 0)
        self.chk_mostrar_nome.setChecked(bool(molde.get("mostrar_nome", True)))
        self.chk_mostrar_fio.setChecked(bool(molde.get("mostrar_fio", True)))
        self.chk_mostrar_numeros.setChecked(bool(molde.get("mostrar_numeros", False)))
        self.chk_visual_descricao.setChecked(bool(molde.get("visual_descricao", False)))
        self.chk_quantidade_visual.setChecked(bool(molde.get("visual_quantidade", False)))
        self.chk_margem_visual.setChecked(bool(molde.get("mostrar_margem", False)))
        self._preencher_tabela_margem(molde)
        self.chk_preencher.setChecked(bool(molde.get("visual_preencher", False)))
        self.chk_mostrar_cor_tecidos.blockSignals(True)
        self.chk_mostrar_cor_tecidos.setChecked(bool(getattr(self.canvas, "_mostrar_cor_tecidos", False)))
        self.chk_mostrar_cor_tecidos.blockSignals(False)
        self._cor_visual = str(molde.get("cor") or "#ffffff")
        self.btn_cor_preenchimento.setStyleSheet(f"background:{self._cor_visual}; border:1px solid #8a939c; padding:0;")
        grade_nome = str(molde.get("graduacao_grade_nome") or "").strip()
        if grade_nome:
            i_grade = self.cmb_grade_tamanhos.findText(grade_nome)
            if i_grade >= 0:
                self.cmb_grade_tamanhos.blockSignals(True)
                self.cmb_grade_tamanhos.setCurrentIndex(i_grade)
                self.cmb_grade_tamanhos.blockSignals(False)
        linhas = molde.get("graduacao_tamanhos")
        if isinstance(linhas, list) and linhas:
            self._graduacao_linhas = [dict(l) for l in linhas]
            self._renderizar_tabela_graduacao()
        else:
            self._aplicar_grade_tamanhos(self.cmb_grade_tamanhos.currentText())
        self.preview.set_molde(dict(molde))
        self._suspender_auto_aplicar = False

    def _dados_encaixe_formulario(self) -> dict:
        return {
            "tecido": self.ed_tecido.currentText().strip(),
            "tipo_corte": self.cmb_tipo_corte.currentText().strip(),
            "espelhar": self.cmb_espelhar.currentText().strip(),
            "giro": self.cmb_giro.currentText().strip(),
            "faixa_giro": self.ed_faixa_giro.text().strip() or "0",
            "giro_inicial": self.ed_giro_inicial.text().strip() or "0",
            "qtd_modelo": int(self.sp_qtd_modelo.value()),
            "molde_pronto": self.chk_molde_pronto.isChecked(),
            "permitir_alteracoes_encaixe": self.chk_perm_alt.isChecked(),
            "par": self.chk_par.isChecked(),
            "dobra_vertical": self.chk_dobra_v.isChecked(),
            "dobra_horizontal": self.chk_dobra_h.isChecked(),
            "refletido_vertical": self.chk_reflete_v.isChecked(),
            "refletido_horizontal": self.chk_reflete_h.isChecked(),
        }

    def _aplicar_encaixe_em_molde(self, molde: dict, valores: dict):
        if not molde:
            return
        molde["tecido"] = valores["tecido"]
        molde["tipo_corte"] = valores["tipo_corte"]
        molde["espelhar"] = valores["espelhar"]
        molde["giro"] = valores["giro"]
        molde["faixa_giro"] = valores["faixa_giro"]
        molde["giro_inicial"] = valores["giro_inicial"]
        molde["qtd_modelo"] = valores["qtd_modelo"]
        molde["molde_pronto"] = valores["molde_pronto"]
        molde["permitir_alteracoes_encaixe"] = valores["permitir_alteracoes_encaixe"]
        molde["par"] = valores["par"]
        molde["dobra_vertical"] = valores["dobra_vertical"]
        molde["dobra_horizontal"] = valores["dobra_horizontal"]
        molde["refletido_vertical"] = valores["refletido_vertical"]
        molde["refletido_horizontal"] = valores["refletido_horizontal"]

    def _finalizar_aplicacao_em_lote(self):
        self.canvas.update()
        self.preview.set_molde(dict(self._molde_atual() or {}))
        self.recarregar_lista()

    def _aplicar_todos_moldes(self):
        if not self._refs:
            QMessageBox.information(self, "Propriedades", "Nenhum molde disponível.")
            return
        valores = self._dados_encaixe_formulario()
        for ref in self._refs:
            self._aplicar_encaixe_em_molde(ref.dados, valores)
        self._finalizar_aplicacao_em_lote()

    def _aplicar_todos_com_mesmo_tecido(self):
        molde_atual = self._molde_atual()
        if not molde_atual:
            QMessageBox.information(self, "Propriedades", "Selecione um molde.")
            return
        tecido_base = str(molde_atual.get("tecido") or "").strip()
        valores = self._dados_encaixe_formulario()
        aplicados = 0
        for ref in self._refs:
            tecido_ref = str(ref.dados.get("tecido") or "").strip()
            if tecido_ref == tecido_base:
                self._aplicar_encaixe_em_molde(ref.dados, valores)
                aplicados += 1
        if aplicados <= 0:
            QMessageBox.information(self, "Propriedades", "Nenhum molde com o mesmo tecido foi encontrado.")
            return
        self._finalizar_aplicacao_em_lote()

    def _aplicar_margem_no_molde(self):
        molde = self._molde_atual()
        if not molde:
            QMessageBox.information(self, "Margem", "Selecione um molde para aplicar a margem.")
            return
        margens = self._coletar_margens_tabela()
        self._salvar_margens_no_molde(molde, margens)
        self._forcar_margem_no_canvas(molde, margens, bool(molde.get("mostrar_margem", False)))
        if hasattr(self.canvas, "_registrar_historico"):
            self.canvas._registrar_historico()
        self.preview.set_molde(dict(molde))
        self._confirmado_ok = True
        self.dados_aplicados.emit()

    def _aplicar(self) -> bool:
        molde = self._molde_atual()
        if not molde:
            QMessageBox.information(self, "Propriedades", "Selecione um molde.")
            return False

        self._aplicar_formulario_no_molde(molde)
        self._sincronizar_gradacao_no_molde()
        self.canvas._mostrar_cor_tecidos = self.chk_mostrar_cor_tecidos.isChecked()

        self.canvas.update()
        if hasattr(self.canvas, "_registrar_historico"):
            self.canvas._registrar_historico()
        self.preview.set_molde(dict(molde))
        self.recarregar_lista()
        self._confirmado_ok = True
        self.dados_aplicados.emit()
        return True

    def _ok(self):
        if self._aplicar():
            self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._ok()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if not self._confirmado_ok:
            self._restaurar_snapshot_moldes()
        super().closeEvent(event)

    def _excluir_molde_atual(self):
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", None)
        if self._indice_atual is None or not isinstance(elementos, list):
            return
        if not (0 <= self._indice_atual < len(elementos)):
            return
        del elementos[self._indice_atual]
        if hasattr(self.canvas, "_registrar_historico"):
            self.canvas._registrar_historico()
        if hasattr(self.canvas, "update"):
            self.canvas.update()
        self._indice_atual = None
        self.recarregar_lista()

    def _escolher_cor(self):
        cor = self._selecionar_cor_clara(QColor(self._cor_visual), "Cor do molde")
        if not cor.isValid():
            return
        self._cor_visual = cor.name()
        self.btn_cor_preenchimento.setStyleSheet(f"background:{self._cor_visual}; border:1px solid #8a939c; padding:0;")
        self._aplicar_imediato_formulario()

    def _selecionar_cor_clara(self, cor_inicial: QColor, titulo: str) -> QColor:
        dialog = QColorDialog(cor_inicial, self)
        dialog.setWindowTitle(titulo)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        dialog.setStyleSheet(
            """
            QColorDialog {
                background: #f4f4f4;
                color: #101010;
            }
            QLabel, QPushButton, QSpinBox, QLineEdit {
                color: #101010;
                background: #ffffff;
            }
            """
        )
        if dialog.exec() == QDialog.Accepted:
            return dialog.selectedColor()
        return QColor()

    def _alternar_cor_tecidos_canvas(self, ativo: bool):
        janela = self.parent()
        if janela is not None and hasattr(janela, "aplicar_config_cores_tecidos_global"):
            janela.aplicar_config_cores_tecidos_global(mostrar=bool(ativo))
        else:
            self.canvas._mostrar_cor_tecidos = bool(ativo)
            self.canvas.update()
        self.preview.set_config_cores_tecidos(
            getattr(self.canvas, "_cores_tecidos", {}),
            bool(getattr(self.canvas, "_mostrar_cor_tecidos", False)),
        )

    def _criar_snapshot_moldes(self) -> dict[int, dict]:
        snapshot: dict[int, dict] = {}
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", [])
        if not isinstance(elementos, list):
            return snapshot
        for idx, el in enumerate(elementos):
            if isinstance(el, dict) and el.get("molde"):
                snapshot[idx] = deepcopy(el)
        return snapshot

    def _restaurar_snapshot_moldes(self):
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", [])
        if not isinstance(elementos, list):
            return
        elementos[:] = [
            el for el in elementos
            if not (isinstance(el, dict) and el.get("guimma_margem_linha_canvas"))
        ]
        for idx, el in self._snapshot_moldes.items():
            if 0 <= idx < len(elementos):
                elementos[idx] = deepcopy(el)
        if hasattr(self.canvas, "_margens_visuais_forcadas"):
            try:
                self.canvas._margens_visuais_forcadas = {}
            except Exception:
                pass
        self.canvas._mostrar_cor_tecidos = bool(self._snapshot_mostrar_cor_tecidos)
        self.canvas.update()

    def _aplicar_formulario_no_molde(self, molde: dict):
        nome_combo = self.cmb_molde.currentText().strip()
        molde["nome_molde"] = nome_combo or molde.get("nome_molde") or "N22"
        molde["descricao"] = self.ed_descricao.toPlainText().strip()
        molde["tecido"] = self.ed_tecido.currentText().strip()
        molde["tipo_corte"] = self.cmb_tipo_corte.currentText().strip()
        molde["espelhar"] = self.cmb_espelhar.currentText().strip()
        molde["giro"] = self.cmb_giro.currentText().strip()
        molde["faixa_giro"] = self.ed_faixa_giro.text().strip() or "0"
        molde["giro_inicial"] = self.ed_giro_inicial.text().strip() or "0"
        molde["qtd_modelo"] = int(self.sp_qtd_modelo.value())
        molde["molde_pronto"] = self.chk_molde_pronto.isChecked()
        molde["permitir_alteracoes_encaixe"] = self.chk_perm_alt.isChecked()
        molde["par"] = self.chk_par.isChecked()
        molde["dobra_vertical"] = self.chk_dobra_v.isChecked()
        molde["dobra_horizontal"] = self.chk_dobra_h.isChecked()
        molde["refletido_vertical"] = self.chk_reflete_v.isChecked()
        molde["refletido_horizontal"] = self.chk_reflete_h.isChecked()
        molde["mostrar_nome"] = self.chk_mostrar_nome.isChecked()
        molde["mostrar_fio"] = self.chk_mostrar_fio.isChecked()
        molde["mostrar_numeros"] = self.chk_mostrar_numeros.isChecked()
        molde["visual_descricao"] = self.chk_visual_descricao.isChecked()
        molde["visual_quantidade"] = self.chk_quantidade_visual.isChecked()
        margens = self._margens_do_formulario()
        molde["margens_molde"] = margens
        molde["margens"] = {item["elemento"]: item["margem"] for item in margens}
        molde["margem_cm_por_elemento"] = dict(molde["margens"])
        tem_margem = any(float(item.get("margem") or 0) > 0 for item in margens)
        molde["mostrar_margem"] = self.chk_margem_visual.isChecked() or tem_margem
        if tem_margem and not self.chk_margem_visual.isChecked():
            with QSignalBlocker(self.chk_margem_visual):
                self.chk_margem_visual.setChecked(True)
        molde["visual_preencher"] = self.chk_preencher.isChecked()
        molde["cor"] = self._cor_visual

    def _aplicar_imediato_formulario(self):
        if self._suspender_auto_aplicar:
            return
        molde = self._molde_atual()
        if not molde:
            return
        self._aplicar_formulario_no_molde(molde)
        self._sincronizar_nome_molde_atual_sem_recarregar(str(molde.get("nome_molde") or ""))
        self._sincronizar_gradacao_no_molde()
        self.canvas._mostrar_cor_tecidos = self.chk_mostrar_cor_tecidos.isChecked()
        self.preview.set_molde(dict(molde))
        self.canvas.update()

    def _conectar_auto_aplicacao(self):
        sinais = [
            self.cmb_molde.currentTextChanged,
            self.ed_descricao.textChanged,
            self.cmb_tipo_corte.currentTextChanged,
            self.cmb_espelhar.currentTextChanged,
            self.cmb_giro.currentTextChanged,
            self.ed_faixa_giro.textChanged,
            self.ed_giro_inicial.textChanged,
            self.sp_qtd_modelo.valueChanged,
            self.chk_molde_pronto.toggled,
            self.chk_perm_alt.toggled,
            self.chk_par.toggled,
            self.chk_dobra_v.toggled,
            self.chk_dobra_h.toggled,
            self.chk_reflete_v.toggled,
            self.chk_reflete_h.toggled,
            self.chk_mostrar_nome.toggled,
            self.chk_mostrar_fio.toggled,
            self.chk_mostrar_numeros.toggled,
            self.chk_visual_descricao.toggled,
            self.chk_quantidade_visual.toggled,
            self.chk_margem_visual.toggled,
            self.chk_preencher.toggled,
            self.chk_mostrar_cor_tecidos.toggled,
            self.cmb_grade_tamanhos.currentTextChanged,
            self.cmb_aplicar_grade.currentTextChanged,
        ]
        for sinal in sinais:
            sinal.connect(self._aplicar_imediato_formulario)

    def _abrir_config_cor_tecidos(self):
        cena = getattr(self.canvas, "cena", None)
        elementos = getattr(cena, "elementos", [])
        if not isinstance(elementos, list):
            elementos = []
        tecidos = sorted({
            str(el.get("tecido") or "").strip()
            for el in elementos
            if isinstance(el, dict) and el.get("molde") and str(el.get("tecido") or "").strip()
        })
        mapa = dict(getattr(self.canvas, "_cores_tecidos", {}))
        dialog = ConfigurarCoresTecidosDialog(tecidos, mapa, self)
        if dialog.exec() != QDialog.Accepted:
            return
        novo_mapa = dialog.cores_tecidos()
        janela = self.parent()
        if janela is not None and hasattr(janela, "aplicar_config_cores_tecidos_global"):
            janela.aplicar_config_cores_tecidos_global(mapa_cores=novo_mapa)
        else:
            self.canvas._cores_tecidos = novo_mapa
        self._atualizar_opcoes_tecido()
        if hasattr(self.canvas, "update"):
            self.canvas.update()
        self.preview.set_config_cores_tecidos(
            getattr(self.canvas, "_cores_tecidos", {}),
            bool(getattr(self.canvas, "_mostrar_cor_tecidos", False)),
        )

class ConfigurarFerramentasDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Ferramentas")
        self.resize(640, 520)
        self.setMinimumSize(580, 460)
        self.setStyleSheet(
            """
            QDialog { background: #efefef; color: #111111; }
            QLabel, QTableWidget { color: #111111; }
            QComboBox, QLineEdit {
                background: #ffffff;
                color: #111111;
                border: 1px solid #b5bcc3;
                min-height: 20px;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #b5bcc3;
                gridline-color: #d6dbe0;
            }
            QHeaderView::section {
                background: #f1f1f1;
                color: #111111;
                border: 1px solid #c2c8cf;
                padding: 3px;
            }
            """
        )
        self._construir_ui()

    def _construir_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Configure abaixo a cor e a descrição das ferramentas:"))

        self.tbl = QTableWidget(16, 4)
        self.tbl.setHorizontalHeaderLabels(["Ferramentas", "Descrição", "Tipo", "Cor"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.tbl.setColumnWidth(0, 90)
        self.tbl.setColumnWidth(2, 90)
        self.tbl.setColumnWidth(3, 58)
        self.tbl.cellClicked.connect(self._on_celula_clicada)
        lay.addWidget(self.tbl, 1)

        paleta = [
            "#f0d100", "#8d00c7", "#17bcc3", "#ffffff", "#93ed2b", "#768899", "#8a4d17", "#4f96c5",
            "#2ccb3b", "#0c12d6", "#f52ca6", "#f6b11c", "#d4d4d4", "#b8d99b", "#73e3cf", "#f1dfc4",
        ]
        for i in range(16):
            idx_ferramenta = 4 + i
            item_id = QTableWidgetItem(str(idx_ferramenta))
            item_id.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl.setItem(i, 0, item_id)
            self.tbl.setItem(i, 1, QTableWidgetItem(""))
            cmb = QComboBox()
            cmb.addItems(["Desenho"])
            self.tbl.setCellWidget(i, 2, cmb)
            item_cor = QTableWidgetItem("")
            item_cor.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_cor.setBackground(QColor(paleta[i]))
            self.tbl.setItem(i, 3, item_cor)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        ok = QPushButton("✓ OK")
        cancelar = QPushButton("✕ Cancelar")
        ok.clicked.connect(self.accept)
        cancelar.clicked.connect(self.reject)
        botoes.addWidget(ok)
        botoes.addWidget(cancelar)
        lay.addLayout(botoes)

    def _on_celula_clicada(self, row: int, col: int):
        if col != 3 or row < 0:
            return
        item = self.tbl.item(row, col)
        atual = item.background().color() if item is not None else QColor("#ffffff")
        dialog = QColorDialog(atual, self)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        dialog.setWindowTitle("Cor da ferramenta")
        if dialog.exec() != QDialog.Accepted:
            return
        cor = dialog.selectedColor()
        if item is not None and cor.isValid():
            item.setBackground(cor)


class ConfigurarDefaultsDialog(QDialog):
    def __init__(self, valores_iniciais: list[dict] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Ferramentas Padrão")
        self.resize(310, 430)
        self.setMinimumSize(290, 390)
        self._valores = valores_iniciais or []
        self._linhas: list[tuple[QComboBox, QPushButton, QCheckBox]] = []
        self.setStyleSheet(
            """
            QDialog { background: #efefef; color: #111111; }
            QLabel, QCheckBox { color: #111111; }
            QComboBox {
                background: #ffffff;
                color: #111111;
                border: 1px solid #b5bcc3;
                min-height: 20px;
                combobox-popup: 0;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #111111;
                border: 1px solid #b5bcc3;
                selection-background-color: #2b7cd3;
                selection-color: #ffffff;
            }
            QPushButton {
                background: #f7f7f7;
                border: 1px solid #b7bec5;
                border-radius: 4px;
                min-height: 20px;
                color: #111111;
            }
            """
        )
        self._construir_ui()

    def _construir_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel(""), 0, 0)
        grid.addWidget(QLabel(""), 0, 1)
        grid.addWidget(QLabel(""), 0, 2)
        grid.addWidget(QLabel("Usar"), 0, 3)

        nomes = [
            "Contorno",
            "Nome",
            "Descrição",
            "Observações",
            "Fio",
            "Piques sobre o contorno",
            "Piques internos",
            "Linhas auxiliares",
            "Costura",
        ]
        cores = ["#8f4514", "#557d1f", "#3f63d8", "#f0d100", "#0c12d6", "#19bdb7", "#d0d0d0", "#93ed2b", "#768899"]
        for i, nome in enumerate(nomes):
            lbl = QLabel(nome)
            cmb = QComboBox()
            cmb.addItems(["-", "1", "2", "3", "4", "5", "6", "7", "8", "9"])
            cmb.setCurrentText(str(i + 1))
            btn_cor = QPushButton("")
            btn_cor.setFixedSize(24, 20)
            btn_cor.setStyleSheet(f"background:{cores[i]}; border:1px solid #343434;")
            btn_cor.clicked.connect(lambda _=False, b=btn_cor: self._escolher_cor_botao(b))
            chk = QCheckBox("")
            chk.setChecked(True)
            grid.addWidget(lbl, i + 1, 0)
            grid.addWidget(cmb, i + 1, 1)
            grid.addWidget(btn_cor, i + 1, 2)
            grid.addWidget(chk, i + 1, 3, alignment=Qt.AlignCenter)
            self._linhas.append((cmb, btn_cor, chk))

        if self._valores:
            for i, dados in enumerate(self._valores):
                if i >= len(self._linhas):
                    break
                cmb, btn_cor, chk = self._linhas[i]
                if dados.get("indice"):
                    cmb.setCurrentText(str(dados["indice"]))
                if dados.get("cor"):
                    btn_cor.setStyleSheet(f"background:{dados['cor']}; border:1px solid #343434;")
                chk.setChecked(bool(dados.get("usar", True)))

        lay.addLayout(grid)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        ok = QPushButton("✓ OK")
        cancelar = QPushButton("✕ Cancelar")
        ok.clicked.connect(self.accept)
        cancelar.clicked.connect(self.reject)
        botoes.addWidget(ok)
        botoes.addWidget(cancelar)
        lay.addLayout(botoes)

    def _escolher_cor_botao(self, botao: QPushButton):
        dialog = QColorDialog(QColor(self._cor_botao(botao)), self)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        dialog.setWindowTitle("Cor padrão")
        if dialog.exec() != QDialog.Accepted:
            return
        cor = dialog.selectedColor()
        if cor.isValid():
            botao.setStyleSheet(f"background:{cor.name()}; border:1px solid #343434;")

    def valores(self) -> list[dict]:
        saida = []
        for cmb, btn_cor, chk in self._linhas:
            saida.append(
                {
                    "indice": cmb.currentText(),
                    "cor": self._cor_botao(btn_cor),
                    "usar": chk.isChecked(),
                }
            )
        return saida

    @staticmethod
    def _cor_botao(botao: QPushButton) -> str:
        estilo = botao.styleSheet() or ""
        for trecho in estilo.split(";"):
            if "background" in trecho and ":" in trecho:
                return trecho.split(":", 1)[1].strip()
        return botao.palette().button().color().name()


class ConfigurarCoresTecidosDialog(QDialog):
    def __init__(self, tecidos: list[str], mapa_cores: dict[str, str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Cores dos tecidos")
        self.resize(430, 520)
        self.setMinimumSize(400, 460)
        self.setStyleSheet(
            """
            QDialog { background: #efefef; color: #111111; }
            QLabel { color: #111111; }
            QPushButton, QComboBox, QLineEdit {
                background: #ffffff;
                color: #111111;
                border: 1px solid #b5bcc3;
                border-radius: 3px;
                min-height: 22px;
                padding: 2px 6px;
            }
            QComboBox { combobox-popup: 0; }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #111111;
                border: 1px solid #b5bcc3;
                selection-background-color: #2b7cd3;
                selection-color: #ffffff;
            }
            QTableWidget {
                background: #ffffff;
                color: #111111;
                border: 1px solid #b5bcc3;
                gridline-color: #d6dbe0;
            }
            QHeaderView::section {
                background: #f1f1f1;
                color: #111111;
                border: 1px solid #c2c8cf;
                padding: 3px;
            }
            """
        )
        self._mapa: dict[str, str] = dict(mapa_cores)
        self._contador_novos = 0
        self._linha_tecido_atual = -1
        self._construir_ui()
        self._popular_tecidos(tecidos)

    def _construir_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        topo = QHBoxLayout()
        self.btn_novo = QPushButton("Novo")
        self.btn_excluir = QPushButton("Excluir")
        self.btn_novo.clicked.connect(self._novo_tecido)
        self.btn_excluir.clicked.connect(self._excluir_tecido)
        topo.addWidget(self.btn_novo)
        topo.addWidget(self.btn_excluir)
        topo.addStretch(1)
        lay.addLayout(topo)

        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Tecido", "Cor"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tbl.setColumnWidth(1, 70)
        self.tbl.setSelectionMode(QTableWidget.NoSelection)
        self.tbl.setStyleSheet(
            "QTableWidget::item:selected { background: transparent; color:#111111; }"
            "QTableWidget::item:selected:active { background: transparent; color:#111111; }"
            "QTableWidget::item:selected:!active { background: transparent; color:#111111; }"
        )
        self.tbl.cellClicked.connect(self._on_cell_clicked)
        lay.addWidget(self.tbl, 1)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        ok = QPushButton("✓ OK")
        cancelar = QPushButton("✕ Cancelar")
        ok.clicked.connect(self.accept)
        cancelar.clicked.connect(self.reject)
        botoes.addWidget(ok)
        botoes.addWidget(cancelar)
        lay.addLayout(botoes)

    def _popular_tecidos(self, tecidos: list[str]):
        valores = list(dict.fromkeys([*tecidos, *self._mapa.keys()]))
        self.tbl.setRowCount(0)
        for tecido in valores:
            self._adicionar_linha(tecido, self._mapa.get(tecido) or self._cor_aleatoria())

    def _adicionar_linha(self, tecido: str, cor: str):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        item_t = QTableWidgetItem(tecido)
        item_t.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        self.tbl.setItem(row, 0, item_t)
        item_c = QTableWidgetItem("")
        item_c.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item_c.setBackground(QColor(cor))
        self.tbl.setItem(row, 1, item_c)

    def _novo_tecido(self):
        self._contador_novos += 1
        self._adicionar_linha(f"TECIDO_{self._contador_novos}", self._cor_aleatoria())

    def _excluir_tecido(self):
        row = int(getattr(self, "_linha_tecido_atual", -1))
        if row < 0:
            row = self.tbl.currentRow()
        if row >= 0:
            self.tbl.removeRow(row)
            self._linha_tecido_atual = -1

    def _on_cell_clicked(self, row: int, col: int):
        self._linha_tecido_atual = row
        if col != 1 or row < 0:
            return
        atual = self.tbl.item(row, 1)
        dialog = QColorDialog(atual.background().color(), self)
        dialog.setWindowTitle("Cor do tecido")
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        dialog.setStyleSheet("QColorDialog { background:#f4f4f4; color:#101010; }")
        cor = dialog.selectedColor() if dialog.exec() == QDialog.Accepted else QColor()
        if cor.isValid():
            atual.setBackground(cor)

    def cores_tecidos(self) -> dict[str, str]:
        mapa: dict[str, str] = {}
        for row in range(self.tbl.rowCount()):
            nome_item = self.tbl.item(row, 0)
            cor_item = self.tbl.item(row, 1)
            if not nome_item or not cor_item:
                continue
            nome = nome_item.text().strip()
            if not nome:
                continue
            mapa[nome] = cor_item.background().color().name()
        return mapa

    def _cor_aleatoria(self) -> str:
        return f"#{randint(40, 240):02x}{randint(40, 240):02x}{randint(40, 240):02x}"


def _log_propriedades_debug(mensagem: str):
    try:
        caminho = Path.home() / "guimma_propriedades_debug.log"
        linha = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [propriedades_tool] {mensagem}"
        print(linha)
        with caminho.open("a", encoding="utf-8") as arq:
            arq.write(linha + "\n")
    except Exception as exc:
        print(f"[propriedades_tool][log-falhou] {type(exc).__name__}: {exc}")


class Ferramenta(FerramentaBase):
    id_ferramenta = "propriedades"
    nome = "Propriedades"
    descricao_painel = "Abre a janela de propriedades dos moldes selecionados."

    _dialog_por_canvas: dict[int, PropriedadesMoldesDialog] = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        _log_propriedades_debug(f"on_activate() chamado. canvas={type(canvas).__name__}; window={type(canvas.window()).__name__ if hasattr(canvas, 'window') and canvas.window() is not None else None}")
        try:
            dialog = self._obter_dialog(canvas)
            _log_propriedades_debug(f"Dialog obtido: {dialog}; visível_antes={dialog.isVisible() if dialog is not None else None}")
            dialog._indice_atual = dialog._indice_molde_preferencial()
            dialog.recarregar_lista()
            _log_propriedades_debug(f"Após recarregar_lista: indice_atual={dialog._indice_atual}; refs={len(getattr(dialog, '_refs', []))}")
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            _log_propriedades_debug(f"Dialog visível_depois={dialog.isVisible()}; geometria={dialog.geometry().getRect()}")
            if dialog._indice_atual is None:
                self.set_status("Nenhum molde disponível. Crie ou extraia um molde primeiro.")
            else:
                self.set_status("Janela de propriedades do molde aberta.")
        except Exception as exc:
            _log_propriedades_debug(f"Falha ao abrir Propriedades: {type(exc).__name__}: {exc}")
            print(f"Falha ao abrir Propriedades: {type(exc).__name__}: {exc}")
            try:
                QMessageBox.critical(
                    canvas.window() if hasattr(canvas, "window") else None,
                    "Erro ao abrir propriedades",
                    f"{type(exc).__name__}: {exc}",
                )
            except Exception as exc2:
                _log_propriedades_debug(f"Falha ao mostrar QMessageBox: {type(exc2).__name__}: {exc2}")

    def ativar(self):
        return "Use on_activate(canvas) para abrir a janela de propriedades."

    def _obter_dialog(self, canvas) -> PropriedadesMoldesDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else None
        opcoes = getattr(parent, "_opcoes_app", {}) if parent is not None else {}
        exibir_tab_ferramentas = bool(opcoes.get("usar_ferramentas_moldes", False))
        parent_nome = type(parent).__name__ if parent is not None else None
        dialog_parent_nome = None
        try:
            dialog_parent = dialog.parentWidget() if dialog is not None else None
            dialog_parent_nome = type(dialog_parent).__name__ if dialog_parent is not None else None
        except Exception:
            dialog_parent = None
        _log_propriedades_debug(
            f"_obter_dialog(): chave_canvas={chave}; dialog_existente={dialog is not None}; parent={parent_nome}; dialog_parent={dialog_parent_nome}; exibir_tab_ferramentas={exibir_tab_ferramentas}"
        )

        precisa_recriar = False
        if dialog is None:
            precisa_recriar = True
        else:
            try:
                if dialog.parentWidget() is not parent:
                    _log_propriedades_debug(
                        "_obter_dialog(): parent do dialog mudou; recriando janela para evitar ficar presa ao widget antigo."
                    )
                    try:
                        dialog.hide()
                    except Exception:
                        pass
                    try:
                        dialog.close()
                    except Exception:
                        pass
                    try:
                        dialog.deleteLater()
                    except Exception:
                        pass
                    self._dialog_por_canvas.pop(chave, None)
                    dialog = None
                    precisa_recriar = True
            except Exception as exc:
                _log_propriedades_debug(
                    f"_obter_dialog(): falha ao validar dialog existente; recriando. erro={type(exc).__name__}: {exc}"
                )
                self._dialog_por_canvas.pop(chave, None)
                dialog = None
                precisa_recriar = True

        if not precisa_recriar and dialog is not None:
            dialog.set_exibir_tab_ferramentas(exibir_tab_ferramentas)
            try:
                if dialog.parentWidget() is None and parent is not None:
                    dialog.setParent(parent)
            except Exception:
                pass
            return dialog

        dialog = PropriedadesMoldesDialog(canvas, parent, mostrar_tab_ferramentas=exibir_tab_ferramentas)
        dialog.dados_aplicados.connect(lambda: self.set_status("Propriedades do molde aplicadas."))
        dialog.destroyed.connect(lambda *_: self._dialog_por_canvas.pop(chave, None))
        self._dialog_por_canvas[chave] = dialog
        _log_propriedades_debug(
            f"_obter_dialog(): novo dialog criado e armazenado para chave={chave}; parent={parent_nome}"
        )
        return dialog
