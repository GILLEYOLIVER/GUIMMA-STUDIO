from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, degrees, hypot, isfinite, radians, sin
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.formatacao import formatar_numero
from tools.movimento_utils import rotacionar_elemento_por_funcao
from tools.preview_original_utils import desenhar_elementos_originais
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class GirarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:girar"
        self.setWindowTitle("Girar")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(260)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QComboBox, QDoubleSpinBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            QPushButton { background:#f7f7f7; color:#111111; border:1px solid #b7bec5; min-height:24px; }
            QPushButton:hover { background:#ffffff; }
            """
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.sp_angulo = QDoubleSpinBox()
        self.sp_angulo.setObjectName("angulo")
        self.sp_angulo.setRange(-3600.0, 3600.0)
        self.sp_angulo.setDecimals(2)
        self.sp_angulo.setSingleStep(5.0)
        self.sp_angulo.setValue(90.0)
        self.cmb_modo = QComboBox()
        self.cmb_modo.setObjectName("modo")
        self.cmb_modo.addItems(["Ângulo", "Girar em 2 pontos"])
        self.cmb_pivo = QComboBox()
        self.cmb_pivo.setObjectName("pivo")
        self.cmb_pivo.addItems(["Centro da seleção", "Último clique", "Origem 0,0"])
        form.addRow("Modo", self.cmb_modo)
        self.chk_copia = QCheckBox("Criar cópia girada")
        self.chk_copia.setObjectName("criar_copia")
        self.chk_copia.setChecked(False)
        form.addRow("Ângulo (graus)", self.sp_angulo)
        form.addRow("Pivô", self.cmb_pivo)
        raiz.addLayout(form)
        raiz.addWidget(self.chk_copia)
        linha = QHBoxLayout()
        for valor in (-90, 90, 180):
            btn = QPushButton(str(valor))
            btn.clicked.connect(lambda _=False, v=valor: self.sp_angulo.setValue(float(v)))
            linha.addWidget(btn)
        raiz.addLayout(linha)


class Ferramenta(FerramentaBase):
    id_ferramenta = "girar"
    nome = "Girar"
    usa_painel_auxiliar = False
    descricao_painel = "Gira elementos selecionados por ângulo, preservando controles, piques e fio."

    _dialog_por_canvas: dict[int, GirarDialog] = {}
    ANGULOS_PRINCIPAIS = (0.0, 30.0, 45.0, 60.0, 90.0, 120.0, 135.0, 150.0, 180.0, 210.0, 225.0, 240.0, 270.0, 300.0, 315.0, 330.0)
    TOLERANCIA_IMA_ANGULAR_GRAUS = 1.5

    def __init__(self):
        super().__init__()
        self._ultimo_clique: QPointF | None = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False
        self._estado_2p = "pivo"
        self._pivo_2p: QPointF | None = None
        self._referencia_2p: QPointF | None = None
        self._preview_2p: QPointF | None = None
        self._angulo_preview_2p = 0.0
        self._snapshot_2p: list[tuple[int, dict]] = []

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._ultimo_clique = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False
        self._resetar_2p()
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Girar: clique esquerdo seleciona/pivo. Clique esquerdo novamente aplica. Direito fecha.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            self._restaurar_snapshot_2p(canvas)
            dialog.hide()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            dialog = self._obter_dialog(canvas)
            if dialog.cmb_modo.currentText() == "Girar em 2 pontos" and self._estado_2p != "pivo":
                self._cancelar_2p(canvas)
                event.accept()
                return True
            if self._operacao_finalizada and not self._direito_confirma_fechamento:
                self._direito_confirma_fechamento = True
                self._status(canvas, "Operação finalizada. Clique direito novamente fecha a ferramenta.")
            else:
                self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        dialog = self._obter_dialog(canvas)
        if dialog.cmb_modo.currentText() == "Girar em 2 pontos":
            return self._mouse_press_2p(canvas, event)
        pos = canvas._ponto_com_snap(event.position())
        self._ultimo_clique = QPointF(pos)
        selecionados = set(getattr(canvas, "_selecionados", set()) or set())
        if not getattr(canvas, "_selecionados", set()):
            candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
            if candidatos:
                canvas._selecionados = {int(candidatos[0])}
                canvas.update()
                self._operacao_finalizada = False
                self._direito_confirma_fechamento = False
                self._status(canvas, "Elemento selecionado. Ajuste a caixa e clique esquerdo novamente para girar.")
                event.accept()
                return True
        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        if candidatos and int(candidatos[0]) not in selecionados:
            canvas._selecionados = {int(candidatos[0])}
            canvas.update()
            self._operacao_finalizada = False
            self._direito_confirma_fechamento = False
            self._status(canvas, "Elemento selecionado. Clique esquerdo novamente para girar.")
            event.accept()
            return True
        self._aplicar(canvas)
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._aplicar(canvas)
            event.accept()
            return True
        return False

    def on_mouse_move(self, canvas, event) -> bool:
        dialog = self._obter_dialog(canvas)
        if dialog.cmb_modo.currentText() != "Girar em 2 pontos":
            return False
        if self._estado_2p == "referencia" and self._pivo_2p is not None:
            pos = canvas._ponto_com_snap(event.position())
            self._preview_2p = self._ajustar_ponto_angular_2p(self._pivo_2p, pos, canvas)
            canvas.update()
            event.accept()
            return True
        if self._estado_2p != "girando" or self._pivo_2p is None or self._referencia_2p is None:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._preview_2p = QPointF(pos)
        self._aplicar_preview_2p(canvas, pos)
        canvas.update()
        event.accept()
        return True

    def _obter_dialog(self, canvas) -> GirarDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = GirarDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.cmb_modo.currentTextChanged.connect(lambda _texto, c=canvas: self._modo_alterado(c))
        return dialog

    def _restaurar_dialog(self, canvas, dialog: GirarDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _aplicar(self, canvas) -> None:
        indices = self._indices_selecionados(canvas)
        if not indices:
            self._status(canvas, "Girar: selecione ao menos um elemento.")
            return
        dialog = self._obter_dialog(canvas)
        pivo = self._pivo(canvas, indices, dialog.cmb_pivo.currentText())
        if pivo is None:
            self._status(canvas, "Girar: não foi possível calcular o pivô.")
            return
        ang = float(dialog.sp_angulo.value())
        copiar = dialog.chk_copia.isChecked()
        novos_indices: list[int] = []
        for idx in indices:
            el = canvas.cena.elementos[idx]
            alvo = deepcopy(el) if copiar else el
            self._girar_elemento(alvo, pivo, ang)
            if copiar:
                alvo["id"] = str(uuid4())
                if alvo.get("molde"):
                    alvo["molde_id"] = str(uuid4())
                    alvo["nome_molde"] = f"{str(alvo.get('nome_molde') or 'Molde')} girado"
                canvas.cena.elementos.append(alvo)
                novos_indices.append(len(canvas.cena.elementos) - 1)
            else:
                novos_indices.append(idx)
        if copiar:
            canvas._selecionados = {
                idx for idx in novos_indices
                if 0 <= idx < len(canvas.cena.elementos) and not canvas.cena.elementos[idx].get("molde")
            }
        else:
            canvas._selecionados = set(novos_indices)
        canvas._registrar_historico()
        canvas.update()
        self._operacao_finalizada = True
        self._direito_confirma_fechamento = False
        self._status(canvas, f"Giro de {ang:g}° aplicado em {len(indices)} elemento(s). Clique esquerdo continua; direito fecha.")

    def _mouse_press_2p(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._ultimo_clique = QPointF(pos)
        indices = self._indices_selecionados(canvas)
        if not indices:
            candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
            if candidatos:
                canvas._selecionados = {int(candidatos[0])}
                indices = self._indices_selecionados(canvas)
        if not indices:
            self._status(canvas, "Girar em 2 pontos: selecione um molde ou elemento primeiro.")
            event.accept()
            return True

        if self._estado_2p == "pivo":
            self._pivo_2p = QPointF(pos)
            self._referencia_2p = None
            self._preview_2p = None
            self._snapshot_2p = []
            self._estado_2p = "referencia"
            self._status(canvas, "Pivô marcado. Clique no segundo ponto de referência.")
            canvas.update()
            event.accept()
            return True

        if self._estado_2p == "referencia":
            pos = self._ajustar_ponto_angular_2p(self._pivo_2p, pos, canvas)
            if self._pivo_2p is None or self._dist(self._pivo_2p, pos) <= 1e-6:
                self._status(canvas, "Girar em 2 pontos: escolha um segundo ponto diferente do pivô.")
                event.accept()
                return True
            self._referencia_2p = QPointF(pos)
            self._preview_2p = QPointF(pos)
            self._snapshot_2p = [(idx, deepcopy(canvas.cena.elementos[idx])) for idx in indices]
            self._estado_2p = "girando"
            self._status(canvas, "Mova para girar livremente. Há imã leve em 0, 30, 45, 60, 90... Clique para confirmar.")
            canvas.update()
            event.accept()
            return True

        if self._estado_2p == "girando":
            self._aplicar_preview_2p(canvas, pos)
            angulo_aplicado = self._angulo_preview_2p
            canvas._registrar_historico()
            self._snapshot_2p = []
            self._resetar_2p()
            self._operacao_finalizada = True
            self._direito_confirma_fechamento = False
            self._status(canvas, f"Giro em 2 pontos aplicado: {angulo_aplicado:g}°.")
            canvas.update()
            event.accept()
            return True

        return False

    def _aplicar_preview_2p(self, canvas, pos: QPointF) -> None:
        if self._pivo_2p is None or self._referencia_2p is None or not self._snapshot_2p:
            return
        ang_ref = self._angulo_entre(self._pivo_2p, self._referencia_2p)
        ang_atual = self._angulo_com_ima_principal(self._angulo_entre(self._pivo_2p, pos), canvas)
        delta = self._delta_angular(ang_ref, ang_atual)
        self._angulo_preview_2p = delta
        for idx, original in self._snapshot_2p:
            if 0 <= idx < len(canvas.cena.elementos):
                el = deepcopy(original)
                self._girar_elemento(el, self._pivo_2p, -delta)
                canvas.cena.elementos[idx] = el

    def _ajustar_ponto_angular_2p(self, origem: QPointF | None, pos: QPointF, canvas=None) -> QPointF:
        if origem is None:
            return QPointF(pos)
        comprimento = self._dist(origem, pos)
        if comprimento <= 1e-6:
            return QPointF(pos)
        angulo_mouse = self._angulo_entre(origem, pos)
        angulo = self._angulo_com_ima_principal(angulo_mouse, canvas)
        if self._distancia_angular_abs(angulo_mouse, angulo) <= 1e-9:
            return QPointF(pos)
        return self._destino_polar(origem, comprimento, angulo)

    def _indices_selecionados(self, canvas) -> list[int]:
        indices = [int(i) for i in sorted(getattr(canvas, "_selecionados", set()) or []) if 0 <= int(i) < len(canvas.cena.elementos)]
        if hasattr(canvas, "_indices_transformacao_com_vinculados"):
            return list(canvas._indices_transformacao_com_vinculados(indices))
        return indices

    def _modo_alterado(self, canvas) -> None:
        self._restaurar_snapshot_2p(canvas)
        self._resetar_2p()
        if canvas is not None:
            canvas.update()

    def _resetar_2p(self) -> None:
        self._estado_2p = "pivo"
        self._pivo_2p = None
        self._referencia_2p = None
        self._preview_2p = None
        self._angulo_preview_2p = 0.0
        self._snapshot_2p = []

    def _cancelar_2p(self, canvas) -> None:
        self._restaurar_snapshot_2p(canvas)
        self._resetar_2p()
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False
        canvas.update()
        self._status(canvas, "Girar em 2 pontos cancelado. Clique no pivô para recomeçar.")

    def _restaurar_snapshot_2p(self, canvas) -> None:
        for idx, original in self._snapshot_2p:
            if 0 <= idx < len(canvas.cena.elementos):
                canvas.cena.elementos[idx] = deepcopy(original)
        self._snapshot_2p = []

    def _fechar(self, canvas) -> None:
        self._restaurar_snapshot_2p(canvas)
        self._resetar_2p()
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Girar finalizada. Voltando para Selecionar.")

    def _pivo(self, canvas, indices: list[int], modo: str) -> QPointF | None:
        if modo == "Último clique" and self._ultimo_clique is not None:
            return QPointF(self._ultimo_clique)
        if modo == "Origem 0,0":
            return QPointF(0.0, 0.0)
        pts = []
        for idx in indices:
            pts.extend(self._todos_pontos(canvas.cena.elementos[idx]))
        if not pts:
            return None
        return QPointF((min(x for x, _ in pts) + max(x for x, _ in pts)) / 2.0, (min(y for _, y in pts) + max(y for _, y in pts)) / 2.0)

    def on_paint_overlay(self, canvas, painter):
        dialog = self._obter_dialog(canvas)
        if dialog.cmb_modo.currentText() != "Girar em 2 pontos":
            return
        if self._pivo_2p is None:
            return
        if self._estado_2p == "girando" and self._snapshot_2p:
            desenhar_elementos_originais(canvas, painter, self._snapshot_2p)
        painter.save()
        pivo_tela = canvas._cena_para_tela(self._pivo_2p)
        painter.setPen(QPen(QColor("#24b26b"), 2.0))
        painter.setBrush(QColor(36, 178, 107, 80))
        painter.drawEllipse(pivo_tela, 5, 5)
        painter.setPen(QColor("#ffffff"))
        font = QFont("Arial", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(int(pivo_tela.x() + 6), int(pivo_tela.y() - 6), "1")

        referencia_guia = self._referencia_2p
        if referencia_guia is None and self._estado_2p == "referencia":
            referencia_guia = self._preview_2p
        if referencia_guia is not None:
            ref_tela = canvas._cena_para_tela(referencia_guia)
            painter.setPen(QPen(QColor("#8fe1ff"), 2.0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(pivo_tela, ref_tela)
            painter.drawEllipse(ref_tela, 5, 5)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(ref_tela.x() + 6), int(ref_tela.y() - 6), "2")

        if self._estado_2p == "girando" and self._referencia_2p is not None and self._preview_2p is not None:
            self._desenhar_preview_2p(canvas, painter)
        painter.restore()

    def _desenhar_preview_2p(self, canvas, painter) -> None:
        if self._pivo_2p is None or self._referencia_2p is None:
            return
        comp = self._dist(self._pivo_2p, self._referencia_2p)
        if comp <= 0.0001:
            return
        ang_ref = self._angulo_entre(self._pivo_2p, self._referencia_2p)
        ang_destino = (ang_ref + self._angulo_preview_2p) % 360.0
        destino = self._destino_polar(self._pivo_2p, comp, ang_destino)
        pivo_tela = canvas._cena_para_tela(self._pivo_2p)
        destino_tela = canvas._cena_para_tela(destino)

        painter.setPen(QPen(QColor("#ff7ee6"), 1.2, Qt.DotLine))
        painter.setBrush(Qt.NoBrush)
        ref = QPointF(self._pivo_2p.x() + comp, self._pivo_2p.y())
        painter.drawLine(pivo_tela, canvas._cena_para_tela(ref))
        passos = max(18, int(abs(self._angulo_preview_2p) / 3.0))
        pontos_arco = []
        for i in range(passos + 1):
            t = i / max(passos, 1)
            ang = ang_ref + (self._angulo_preview_2p * t)
            pontos_arco.append(canvas._cena_para_tela(self._destino_polar(self._pivo_2p, comp, ang)))
        for a, b in zip(pontos_arco, pontos_arco[1:]):
            painter.drawLine(a, b)

        painter.setPen(QPen(QColor("#8fe1ff"), 2.0, Qt.DashLine))
        painter.drawLine(pivo_tela, destino_tela)
        painter.setPen(QPen(QColor("#ffd400"), 2.0))
        painter.drawEllipse(destino_tela, 7, 7)
        painter.drawLine(QPointF(destino_tela.x() - 9, destino_tela.y()), QPointF(destino_tela.x() + 9, destino_tela.y()))
        painter.drawLine(QPointF(destino_tela.x(), destino_tela.y() - 9), QPointF(destino_tela.x(), destino_tela.y() + 9))

        meio = QPointF((pivo_tela.x() + destino_tela.x()) / 2.0, (pivo_tela.y() + destino_tela.y()) / 2.0)
        texto = f"{formatar_numero(comp, 2)}  |  {formatar_numero(self._angulo_preview_2p, 1)}°"
        font = QFont("Arial", 8)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        largura = metrics.horizontalAdvance(texto)
        painter.fillRect(int(meio.x() - (largura / 2) - 6), int(meio.y() - 11), largura + 12, 20, QColor(8, 18, 28, 215))
        painter.setPen(QColor("#ffd47d"))
        painter.drawText(int(meio.x() - (largura / 2)), int(meio.y() + 4), texto)

    def _girar_elemento(self, el: dict, pivo: QPointF, angulo: float) -> None:
        a = radians(angulo)
        ca, sa = cos(a), sin(a)

        def rot(p):
            x, y = float(p[0]), float(p[1])
            dx, dy = x - pivo.x(), y - pivo.y()
            return (pivo.x() + (dx * ca) - (dy * sa), pivo.y() + (dx * sa) + (dy * ca))

        rotacionar_elemento_por_funcao(el, rot)
        if "fio_angulo" in el:
            try:
                el["fio_angulo"] = float(el.get("fio_angulo") or 0.0) + float(angulo)
            except Exception:
                pass
        if self._eh_ponto(el.get("fio_origem")) and self._eh_ponto(el.get("fio_fim")):
            fo, ff = el["fio_origem"], el["fio_fim"]
            el["fio_angulo"] = degrees(atan2(float(ff[1]) - float(fo[1]), float(ff[0]) - float(fo[0])))
        el.setdefault("metadados", {})["ultima_transformacao"] = f"girar_{angulo:g}"

    @staticmethod
    def _destino_polar(origem: QPointF, comprimento: float, angulo: float) -> QPointF:
        rad = radians(angulo)
        return QPointF(origem.x() + (cos(rad) * comprimento), origem.y() - (sin(rad) * comprimento))

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _angulo_entre(p1: QPointF, p2: QPointF) -> float:
        ang = degrees(atan2(-(p2.y() - p1.y()), p2.x() - p1.x()))
        return ang if ang >= 0 else ang + 360.0

    def _angulo_principal_mais_proximo(self, angulo: float) -> float:
        normalizado = float(angulo) % 360.0
        return min(
            self.ANGULOS_PRINCIPAIS,
            key=lambda alvo: min(abs(normalizado - alvo), 360.0 - abs(normalizado - alvo)),
        )

    def _angulo_com_ima_principal(self, angulo: float, canvas=None) -> float:
        normalizado = float(angulo) % 360.0
        alvo = self._angulo_principal_mais_proximo(normalizado)
        forcar = bool(getattr(canvas, "_tecla_w_trava_principal", False)) if canvas is not None else False
        if forcar or self._distancia_angular_abs(normalizado, alvo) <= self.TOLERANCIA_IMA_ANGULAR_GRAUS:
            return alvo
        return normalizado

    @staticmethod
    def _delta_angular(origem: float, destino: float) -> float:
        return ((float(destino) - float(origem) + 180.0) % 360.0) - 180.0

    @staticmethod
    def _distancia_angular_abs(a: float, b: float) -> float:
        return abs(((float(a) - float(b) + 180.0) % 360.0) - 180.0)

    def _todos_pontos(self, el: dict) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for chave in (
            "pontos",
            "controle_cantos",
            "controle_auxiliares",
            "pontos_controle_referencia",
            "marcacoes_no_perimetro",
        ):
            for p in el.get(chave, []) if isinstance(el.get(chave), list) else []:
                if self._eh_ponto(p):
                    pts.append((float(p[0]), float(p[1])))
        for chave in ("fio_origem", "fio_fim", "p0", "p1", "p2"):
            if self._eh_ponto(el.get(chave)):
                pts.append((float(el[chave][0]), float(el[chave][1])))
        return pts

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
