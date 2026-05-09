from __future__ import annotations

from math import atan2, cos, degrees, hypot, isfinite, radians, sin

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout

from canvas.snap import SnapResult
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class SentidoFioDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:sentido_fio"
        self.setWindowTitle("Sentido do fio")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(240)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QComboBox, QDoubleSpinBox {
                background:#ffffff;
                color:#111111;
                border:1px solid #8796a4;
                min-height:20px;
            }
            """
        )

        raiz = QFormLayout(self)
        raiz.setContentsMargins(6, 8, 6, 6)
        raiz.setHorizontalSpacing(6)
        raiz.setVerticalSpacing(4)

        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(
            [
                "Pontos do mouse",
                "Pontos do molde",
                "Por selecao",
                "Alinhar molde",
                "Horizontal",
                "Vertical",
                "Posicionar fio",
            ]
        )
        raiz.addRow("Modo", self.cmb_modo)

        linha_angulo = QHBoxLayout()
        linha_angulo.setContentsMargins(0, 0, 0, 0)
        self.chk_usar_angulo = QCheckBox("Travar angulo")
        self.chk_usar_angulo.setChecked(False)
        self.sp_angulo = QDoubleSpinBox()
        self.sp_angulo.setRange(-3600.0, 3600.0)
        self.sp_angulo.setDecimals(2)
        self.sp_angulo.setSingleStep(5.0)
        self.sp_angulo.setSuffix(" deg")
        self.sp_angulo.setValue(0.0)
        linha_angulo.addWidget(self.chk_usar_angulo, 0)
        linha_angulo.addWidget(self.sp_angulo, 1)
        raiz.addRow(linha_angulo)

        self.chk_girar_molde = QCheckBox("Girar molde")
        self.chk_girar_molde.setChecked(False)
        raiz.addRow(self.chk_girar_molde)


class Ferramenta(FerramentaBase):
    id_ferramenta = "sentido_fio"
    nome = "Sentido Fio"
    usa_painel_auxiliar = False
    descricao_painel = "Define o sentido do fio do molde com dois pontos e angulo opcional."

    _dialog_por_canvas: dict[int, SentidoFioDialog] = {}
    ANGULOS_PRINCIPAIS = (0.0, 30.0, 45.0, 60.0, 90.0, 120.0, 135.0, 150.0, 180.0, 210.0, 225.0, 240.0, 270.0, 300.0, 315.0, 330.0)

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._inicio: QPointF | None = None
        self._fim_preview: QPointF | None = None
        self._angulo_preview: float | None = None
        self._snapshot_fio: dict | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._molde_idx = self._molde_selecionado(canvas)
        self._inicio = None
        self._fim_preview = None
        self._snapshot_fio = None
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        self._atualizar_controles_dialog(dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Sentido do fio: clique no molde para selecionar ou clique o inicio do fio.")

    def on_deactivate(self, canvas):
        self._restaurar_snapshot_fio(canvas)
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._inicio = None
        self._fim_preview = None
        self._angulo_preview = None
        if canvas is not None:
            canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._restaurar_snapshot_fio(canvas)
            self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = self._ponto_com_snap_fio(canvas, event.position())
        alvo = self._molde_em_ponto(canvas, pos)
        if alvo is not None and (self._molde_idx is None or alvo != self._molde_idx):
            self._selecionar_molde(canvas, alvo)
            self._inicio = None
            self._fim_preview = None
            self._angulo_preview = None
            self._snapshot_fio = None
            self._status(canvas, "Molde selecionado. Clique para marcar o inicio do fio.")
            event.accept()
            return True

        if self._molde_idx is None:
            self._status(canvas, "Sentido do fio: selecione um molde primeiro.")
            event.accept()
            return True

        if self._inicio is None:
            self._inicio = QPointF(pos)
            self._fim_preview = QPointF(pos)
            self._angulo_preview = None
            self._snapshot_fio = self._capturar_snapshot_fio(canvas, self._molde_idx)
            self._status(canvas, "Inicio marcado. Mova o mouse no sentido desejado e clique para aplicar.")
            canvas.update()
            event.accept()
            return True

        fim, angulo = self._ponto_final_com_config(canvas, self._inicio, pos)
        if self._dist(self._inicio, fim) <= 1e-6:
            self._status(canvas, "Sentido do fio: informe um segundo ponto diferente do inicio.")
            event.accept()
            return True
        self._aplicar(canvas, self._molde_idx, self._inicio, fim, angulo)
        self._inicio = None
        self._fim_preview = None
        self._angulo_preview = None
        self._snapshot_fio = None
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._inicio is None:
            return False
        pos = self._ponto_com_snap_fio(canvas, event.position())
        self._fim_preview, self._angulo_preview = self._ponto_final_com_config(canvas, self._inicio, pos)
        if self._molde_idx is not None:
            self._aplicar_preview_no_molde(canvas, self._molde_idx, self._inicio, self._fim_preview, self._angulo_preview)
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_realce_molde(canvas, painter)
        if self._inicio is None or self._fim_preview is None:
            return

        p0 = canvas._cena_para_tela(self._inicio)
        p1 = canvas._cena_para_tela(self._fim_preview)
        ang = self._normalizar_angulo(
            self._angulo_preview if self._angulo_preview is not None else self._angulo(self._inicio, self._fim_preview)
        )
        comp = self._dist(self._inicio, self._fim_preview)

        painter.save()
        self._desenhar_guia_angular_fio(canvas, painter, self._inicio, comp, ang)
        self._desenhar_referencia_360(canvas, painter)

        pen = QPen(QColor("#8fe1ff"), 2.0, Qt.DashLine)
        pen.setDashPattern([3.0, 2.0])
        painter.setPen(pen)
        painter.setBrush(QColor(255, 0, 212, 24))
        painter.drawLine(p0, p1)
        painter.drawLine(QPointF(p0.x() - 5, p0.y()), QPointF(p0.x() + 5, p0.y()))
        painter.drawLine(QPointF(p0.x(), p0.y() - 5), QPointF(p0.x(), p0.y() + 5))
        painter.setPen(QPen(QColor("#ffd400"), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(p1, 7, 7)
        painter.drawLine(QPointF(p1.x() - 9, p1.y()), QPointF(p1.x() + 9, p1.y()))
        painter.drawLine(QPointF(p1.x(), p1.y() - 9), QPointF(p1.x(), p1.y() + 9))

        meio = QPointF((p0.x() + p1.x()) / 2.0, (p0.y() + p1.y()) / 2.0)
        texto = f"{comp:.2f}  |  {ang:.1f} deg"
        font = QFont("Arial", 8)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        largura = metrics.horizontalAdvance(texto)
        painter.fillRect(
            int(meio.x() - (largura / 2) - 6), int(meio.y() - 11), largura + 12, 20, QColor(8, 18, 28, 215)
        )
        painter.setPen(QColor("#ffd47d"))
        painter.drawText(int(meio.x() - (largura / 2)), int(meio.y() + 4), texto)
        painter.restore()

    def obter_candidatos_snap(self, canvas, cursor: QPointF, incluir_fio: bool = True):
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return []
        el = canvas.cena.elementos[self._molde_idx]
        candidatos: list[SnapResult] = []
        tol = self._tolerancia_snap_cena(canvas)
        for ponto in self._pontos_snap_molde(el, incluir_fio=incluir_fio):
            self._adicionar_snap(candidatos, cursor, ponto, "nó", self._molde_idx, tol)
        for a, b in self._segmentos_snap_molde(el, incluir_fio=incluir_fio):
            proj = canvas._snap_manager._projetar_em_segmento(cursor, a, b)
            meio = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
            self._adicionar_snap(candidatos, cursor, proj, "borda", self._molde_idx, tol)
            self._adicionar_snap(candidatos, cursor, meio, "ponto médio", self._molde_idx, tol)
        return candidatos

    def _obter_dialog(self, canvas) -> SentidoFioDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = SentidoFioDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
            dialog.cmb_modo.currentTextChanged.connect(lambda _texto, c=canvas: c.update())
            dialog.chk_usar_angulo.toggled.connect(lambda _marcado, c=canvas: c.update())
            dialog.sp_angulo.valueChanged.connect(lambda _valor, c=canvas: c.update())
            dialog.chk_girar_molde.toggled.connect(lambda _marcado, c=canvas: c.update())
        return dialog

    def _restaurar_dialog(self, canvas, dialog: SentidoFioDialog) -> None:
        fallback = None
        if hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 80))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _ponto_final_com_config(self, canvas, inicio: QPointF, pos_mouse: QPointF) -> tuple[QPointF, float]:
        """
        Calcula o ponto final e o angulo do sentido do fio.
        """
        dialog = self._obter_dialog(canvas)
        modo = dialog.cmb_modo.currentText()

        dx = pos_mouse.x() - inicio.x()
        dy = pos_mouse.y() - inicio.y()
        comp = hypot(dx, dy)

        if comp <= 1e-9:
            return QPointF(pos_mouse), 0.0

        if modo == "Horizontal":
            angulo = 0.0 if dx >= 0 else 180.0
            fim = QPointF(inicio.x() + dx, inicio.y())
            return fim, angulo

        if modo == "Vertical":
            angulo = 90.0 if dy <= 0 else 270.0
            fim = QPointF(inicio.x(), inicio.y() + dy)
            return fim, angulo

        girar_por_fio = dialog.chk_girar_molde.isChecked() and modo in {"Pontos do mouse", "Pontos do molde"}
        if dialog.chk_usar_angulo.isChecked() and not girar_por_fio and modo != "Pontos do molde":
            angulo = self._normalizar_angulo(float(dialog.sp_angulo.value()))
            ang = radians(angulo)
            fim = QPointF(
                inicio.x() + (cos(ang) * comp),
                inicio.y() - (sin(ang) * comp),
            )
            return fim, angulo

        angulo = self._normalizar_angulo(degrees(atan2(-dy, dx)))
        return QPointF(pos_mouse), angulo

    def _aplicar(self, canvas, idx: int, inicio: QPointF, fim: QPointF, angulo_novo: float) -> None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            self._status(canvas, "Sentido do fio: o elemento selecionado nao e molde.")
            return

        dialog = self._obter_dialog(canvas)
        angulo_novo = self._normalizar_angulo(angulo_novo)
        if dialog.chk_girar_molde.isChecked():
            if dialog.cmb_modo.currentText() in {"Pontos do mouse", "Pontos do molde"}:
                angulo_giro = -angulo_novo
                fim_rotacionado = self._rotacionar_ponto(fim, inicio, angulo_giro)
                fim = QPointF(float(fim_rotacionado[0]), float(fim_rotacionado[1]))
                self._girar_molde(el, inicio, angulo_giro)
                angulo_novo = 0.0
            else:
                angulo_antigo = self._angulo_fio_snapshot(canvas, idx)
                self._girar_molde(el, inicio, angulo_novo - angulo_antigo)

        el["fio_origem"] = (float(inicio.x()), float(inicio.y()))
        el["fio_fim"] = (float(fim.x()), float(fim.y()))
        el["fio_angulo"] = self._normalizar_angulo(angulo_novo)
        el["mostrar_fio"] = True
        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self._status(canvas, f"Sentido do fio aplicado em {self._normalizar_angulo(angulo_novo):g} deg.")

    def _aplicar_preview_no_molde(self, canvas, idx: int, inicio: QPointF, fim: QPointF, angulo: float) -> None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            return
        el["fio_origem"] = (float(inicio.x()), float(inicio.y()))
        el["fio_fim"] = (float(fim.x()), float(fim.y()))
        el["fio_angulo"] = self._normalizar_angulo(angulo)
        el["mostrar_fio"] = True
        canvas._selecionados = {idx}

    def _molde_selecionado(self, canvas) -> int | None:
        for idx in sorted(getattr(canvas, "_selecionados", set()) or []):
            if 0 <= int(idx) < len(canvas.cena.elementos) and canvas.cena.elementos[int(idx)].get("molde"):
                return int(idx)
        return None

    def _molde_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
            el = canvas.cena.elementos[idx]
            if not el.get("molde") or el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 3:
                continue
            path = QPainterPath(pontos[0])
            for pt in pontos[1:]:
                path.lineTo(pt)
            path.closeSubpath()
            if path.contains(pos):
                return idx
        return None

    def _selecionar_molde(self, canvas, idx: int) -> None:
        self._molde_idx = idx
        canvas._selecionados = {idx}
        canvas.update()

    def _ponto_com_snap_fio(self, canvas, pos_tela: QPointF) -> QPointF:
        dialog = self._obter_dialog(canvas)
        modo = dialog.cmb_modo.currentText()
        cursor = canvas._tela_para_cena(pos_tela)
        if modo in {"Pontos do mouse", "Pontos do molde"}:
            if not self._snap_angular_ativo(canvas):
                canvas._snap_resultado = None
                canvas._snap_candidatos = []
                canvas._snap_indice = 0
                return cursor

            arrastando_fim = self._inicio is not None
            local = self._snap_local_molde(canvas, cursor, incluir_fio=not arrastando_fim)
            if arrastando_fim and local is not None:
                tol_inicio = max(2.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001), 1e-4)
                if self._dist(local, self._inicio) <= tol_inicio:
                    return cursor
            return local if local is not None else cursor

        pos = canvas._ponto_com_snap(pos_tela)
        return pos

    def _snap_local_molde(self, canvas, cursor: QPointF, incluir_fio: bool = True) -> QPointF | None:
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return None
        candidatos = self.obter_candidatos_snap(canvas, cursor, incluir_fio=incluir_fio)
        if not candidatos:
            return None
        candidatos.sort(key=lambda c: (c.distancia, 0 if c.tipo in {"nó", "fio"} else 1))
        snap = candidatos[0]
        canvas._snap_resultado = snap
        canvas._snap_candidatos = candidatos
        canvas._snap_indice = 0
        return snap.ponto

    def _desenhar_realce_molde(self, canvas, painter) -> None:
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[self._molde_idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", []) if self._eh_ponto((x, y))]
        if len(pontos) < 2:
            return
        painter.save()
        painter.setBrush(Qt.NoBrush)
        pen = QPen(QColor("#1e9bff"), 1.4, Qt.DashLine)
        pen.setDashPattern([4.0, 3.0])
        painter.setPen(pen)
        path = QPainterPath(canvas._cena_para_tela(pontos[0]))
        for ponto in pontos[1:]:
            path.lineTo(canvas._cena_para_tela(ponto))
        painter.drawPath(path)
        for ponto in self._pontos_realce_principais_molde(el):
            tela = canvas._cena_para_tela(ponto)
            painter.drawRect(QRectF(tela.x() - 3.0, tela.y() - 3.0, 6.0, 6.0))
        painter.restore()

    def _desenhar_guia_angular_fio(
        self, canvas, painter, origem: QPointF, comprimento: float, angulo_graus: float
    ) -> None:
        if comprimento <= 0.0001:
            return

        origem_tela = canvas._cena_para_tela(origem)
        painter.setPen(QPen(QColor("#ff7ee6"), 1.2, Qt.DotLine))
        painter.setBrush(Qt.NoBrush)

        raio_origem = max(5.0, 5.0 * float(getattr(canvas, "zoom", 1.0)) * 0.05)
        painter.drawEllipse(origem_tela, raio_origem, raio_origem)

        ref = QPointF(origem.x() + comprimento, origem.y())
        painter.drawLine(origem_tela, canvas._cena_para_tela(ref))

        passos = max(18, int(max(1.0, angulo_graus) / 3.0))
        pontos_arco: list[QPointF] = []
        for i in range(passos + 1):
            t = i / max(passos, 1)
            a = angulo_graus * t
            rad = radians(a)
            px = origem.x() + (comprimento * cos(rad))
            py = origem.y() - (comprimento * sin(rad))
            pontos_arco.append(canvas._cena_para_tela(QPointF(px, py)))

        for i in range(len(pontos_arco) - 1):
            painter.drawLine(pontos_arco[i], pontos_arco[i + 1])

    def _desenhar_referencia_360(self, canvas, painter) -> None:
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[self._molde_idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", []) if self._eh_ponto((x, y))]
        if len(pontos) < 2:
            return

        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        largura = max(xs) - min(xs)
        altura = max(ys) - min(ys)
        if largura <= 0.0001 or altura <= 0.0001:
            return

        p1 = canvas._cena_para_tela(QPointF(min(xs) + (largura * 0.52), min(ys) + (altura * 0.24)))
        p2 = canvas._cena_para_tela(QPointF(min(xs) + (largura * 0.82), min(ys) + (altura * 0.24)))
        painter.setPen(QPen(QColor("#ffffff"), 1.1))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(p1, p2)
        self._desenhar_ponta_referencia_360(painter, p1, -1.0)
        self._desenhar_ponta_referencia_360(painter, p2, 1.0)

        font = QFont("Arial", 7)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(int(p2.x() + 6), int(p2.y() + 4), "360°")

    @staticmethod
    def _desenhar_ponta_referencia_360(painter, ponta: QPointF, direcao: float) -> None:
        tamanho = 6.0
        painter.drawLine(ponta, QPointF(ponta.x() - (direcao * tamanho), ponta.y() - 2.5))
        painter.drawLine(ponta, QPointF(ponta.x() - (direcao * tamanho), ponta.y() + 2.5))

    def _pontos_snap_molde(self, el: dict, incluir_fio: bool = True) -> list[QPointF]:
        pontos: list[QPointF] = []
        for chave in ("pontos", "controle_cantos", "controle_auxiliares"):
            if isinstance(el.get(chave), list):
                for p in el.get(chave, []):
                    if self._eh_ponto(p):
                        pontos.append(QPointF(float(p[0]), float(p[1])))
        chaves_extra = ["ponto_texto", "seta_origem", "seta_fim"]
        if incluir_fio:
            chaves_extra.extend(["fio_origem", "fio_fim"])
        for chave in chaves_extra:
            p = el.get(chave)
            if self._eh_ponto(p):
                pontos.append(QPointF(float(p[0]), float(p[1])))
        return pontos

    def _pontos_realce_principais_molde(self, el: dict) -> list[QPointF]:
        pontos: list[QPointF] = []

        for chave in ("controle_cantos", "pontos_controle_principais"):
            if not isinstance(el.get(chave), list):
                continue
            for p in el.get(chave, []):
                ponto = self._ponto_qt(p)
                if ponto is not None:
                    pontos.append(ponto)

        if not pontos:
            base = [self._ponto_qt(p) for p in el.get("pontos", [])]
            pontos = [p for p in base if p is not None]
            if len(pontos) > 8:
                pontos = [pontos[0], pontos[-1]]

        return self._remover_pontos_duplicados(pontos)

    def _segmentos_snap_molde(self, el: dict, incluir_fio: bool = True) -> list[tuple[QPointF, QPointF]]:
        segmentos: list[tuple[QPointF, QPointF]] = []
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", []) if self._eh_ponto((x, y))]
        segmentos.extend((a, b) for a, b in zip(pontos, pontos[1:]))
        fio_origem = el.get("fio_origem")
        fio_fim = el.get("fio_fim")
        if incluir_fio and self._eh_ponto(fio_origem) and self._eh_ponto(fio_fim):
            segmentos.append((
                QPointF(float(fio_origem[0]), float(fio_origem[1])),
                QPointF(float(fio_fim[0]), float(fio_fim[1])),
            ))
        return segmentos

    def _adicionar_snap(
        self,
        candidatos: list[SnapResult],
        cursor: QPointF,
        ponto: QPointF,
        tipo: str,
        elemento_idx: int,
        tolerancia: float,
    ) -> None:
        dist = self._dist(cursor, ponto)
        if dist <= tolerancia:
            candidatos.append(SnapResult(ponto=QPointF(ponto), tipo=tipo, distancia=dist, elemento_idx=elemento_idx))

    @staticmethod
    def _tolerancia_snap_cena(canvas) -> float:
        if hasattr(canvas, "_tolerancia_snap_px"):
            return float(canvas._tolerancia_snap_px()) / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        return 10.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)

    @staticmethod
    def _snap_angular_ativo(canvas) -> bool:
        if hasattr(canvas, "snap_ativo"):
            try:
                return bool(canvas.snap_ativo())
            except Exception:
                pass
        return bool(getattr(canvas, "_snap_ativo", True))

    def _fechar(self, canvas) -> None:
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Sentido Fio finalizada. Voltando para Selecionar.")

    def _capturar_snapshot_fio(self, canvas, idx: int | None) -> dict | None:
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return None
        el = canvas.cena.elementos[idx]
        return {
            "idx": idx,
            "fio_origem": el.get("fio_origem"),
            "fio_fim": el.get("fio_fim"),
            "fio_angulo": el.get("fio_angulo"),
            "mostrar_fio": el.get("mostrar_fio"),
        }

    def _restaurar_snapshot_fio(self, canvas) -> None:
        snap = self._snapshot_fio
        self._snapshot_fio = None
        if not snap:
            return
        idx = int(snap.get("idx", -1))
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        for chave in ("fio_origem", "fio_fim", "fio_angulo", "mostrar_fio"):
            if snap.get(chave) is None:
                el.pop(chave, None)
            else:
                el[chave] = snap.get(chave)
        canvas.update()

    def _girar_molde(self, el: dict, pivo: QPointF, angulo: float) -> None:
        def rot(p):
            return self._rotacionar_ponto(p, pivo, angulo)

        for chave in (
            "pontos",
            "controle_cantos",
            "controle_auxiliares",
            "pontos_controle_referencia",
            "marcacoes_no_perimetro",
            "distancias_no_perimetro",
            "marcacoes_perimetro",
        ):
            if isinstance(el.get(chave), list):
                el[chave] = [rot(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]
        for chave in ("ponto_texto", "seta_origem", "seta_fim", "fio_origem", "fio_fim"):
            if self._eh_ponto(el.get(chave)):
                el[chave] = rot(el[chave])

    @staticmethod
    def _rotacionar_ponto(p, pivo: QPointF, angulo: float) -> tuple[float, float]:
        a = radians(angulo)
        ca, sa = cos(a), sin(a)
        if isinstance(p, QPointF):
            x, y = float(p.x()), float(p.y())
        else:
            x, y = float(p[0]), float(p[1])
        dx, dy = x - pivo.x(), y - pivo.y()
        return (pivo.x() + (dx * ca) + (dy * sa), pivo.y() - (dx * sa) + (dy * ca))

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    def _ponto_qt(self, p) -> QPointF | None:
        if isinstance(p, dict):
            try:
                return QPointF(float(p["x"]), float(p["y"]))
            except Exception:
                return None
        if self._eh_ponto(p):
            return QPointF(float(p[0]), float(p[1]))
        return None

    @staticmethod
    def _remover_pontos_duplicados(pontos: list[QPointF]) -> list[QPointF]:
        unicos: list[QPointF] = []
        vistos: set[tuple[float, float]] = set()
        for ponto in pontos:
            chave = (round(float(ponto.x()), 6), round(float(ponto.y()), 6))
            if chave in vistos:
                continue
            vistos.add(chave)
            unicos.append(ponto)
        return unicos

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _angulo(inicio: QPointF, fim: QPointF) -> float:
        ang = degrees(atan2(-(fim.y() - inicio.y()), fim.x() - inicio.x()))
        return ang if ang >= 0 else ang + 360.0

    @staticmethod
    def _normalizar_angulo(angulo: float) -> float:
        valor = float(angulo) % 360.0
        return 0.0 if abs(valor - 360.0) <= 1e-9 else valor

    def _atualizar_controles_dialog(self, dialog: SentidoFioDialog) -> None:
        dialog.sp_angulo.setSingleStep(15.0)
        dialog.sp_angulo.setDecimals(0)

    def _angulo_principal_mais_proximo(self, angulo: float) -> float:
        normalizado = self._normalizar_angulo(angulo)
        return min(
            self.ANGULOS_PRINCIPAIS,
            key=lambda alvo: min(abs(normalizado - alvo), 360.0 - abs(normalizado - alvo)),
        )

    def _angulo_fio_snapshot(self, canvas, idx: int) -> float:
        snap = self._snapshot_fio
        if snap and int(snap.get("idx", -1)) == int(idx):
            origem = snap.get("fio_origem")
            fim = snap.get("fio_fim")
            if self._eh_ponto(origem) and self._eh_ponto(fim):
                return self._angulo(QPointF(float(origem[0]), float(origem[1])), QPointF(float(fim[0]), float(fim[1])))
            try:
                return float(snap.get("fio_angulo") or 0.0)
            except Exception:
                return 0.0
        if 0 <= idx < len(canvas.cena.elementos):
            return self._angulo_fio_atual(canvas.cena.elementos[idx])
        return 0.0

    def _angulo_fio_atual(self, el: dict) -> float:
        origem = el.get("fio_origem")
        fim = el.get("fio_fim")
        if self._eh_ponto(origem) and self._eh_ponto(fim):
            return self._angulo(QPointF(float(origem[0]), float(origem[1])), QPointF(float(fim[0]), float(fim[1])))
        try:
            return float(el.get("fio_angulo") or 0.0)
        except Exception:
            return 0.0

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
