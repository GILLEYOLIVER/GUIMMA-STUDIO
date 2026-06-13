from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, radians, sin, sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from core.formatacao import numero_decimal_ponto
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


TIPOS_PIQUE = [
    "I - forma I",
    "T - forma T",
    "V1 - forma V direito",
    "V2 - forma V esquerdo",
    "V - forma V",
    "MX - marca X",
    "M+ - marca +",
    "MX2 - marca X2",
    "M+2 - marca +2",
    "Botão - forma de botão",
    "U - forma U",
    "Pence - Pence interna",
]


class InserirPiqueDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InserirPiqueDialog")
        self.setWindowTitle("Inserir pique")
        self.setWindowFlags(Qt.Tool)
        self.setFixedWidth(242)
        self._sincronizando_medidas = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(6)

        topo = QGridLayout()
        topo.setHorizontalSpacing(6)
        topo.setVerticalSpacing(4)
        self.edt_largura = QLineEdit("0.3")
        self.edt_altura = QLineEdit("0.3")
        self.edt_angulo = QLineEdit("0")
        for edt in (self.edt_largura, self.edt_altura, self.edt_angulo):
            edt.setFixedWidth(66)

        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(TIPOS_PIQUE)
        self.cmb_tipo.setCurrentText("T - forma T")
        self.cmb_tipo.setMinimumWidth(138)
        self.cmb_tipo.setMaxVisibleItems(12)

        topo.addWidget(QLabel("Largura (cm)"), 0, 0)
        topo.addWidget(QLabel("Pique"), 0, 1)
        topo.addWidget(self.edt_largura, 1, 0)
        topo.addWidget(self.cmb_tipo, 1, 1)
        topo.addWidget(QLabel("Altura (cm)"), 2, 0)
        topo.addWidget(self.edt_altura, 3, 0)
        topo.addWidget(QLabel("Ângulo"), 4, 0)

        ang_row = QHBoxLayout()
        ang_row.setContentsMargins(0, 0, 0, 0)
        ang_row.setSpacing(2)
        ang_row.addWidget(self.edt_angulo)
        ang_row.addWidget(QLabel("°"))
        topo.addLayout(ang_row, 5, 0)

        self.preview = _PiquePreview(self)
        topo.addWidget(self.preview, 2, 1, 4, 1)
        raiz.addLayout(topo)

        ref = QGridLayout()
        ref.setHorizontalSpacing(6)
        self.cmb_referencia = QComboBox()
        self.cmb_referencia.addItems(["Ponto mais próximo", "Segmento mais próximo", "Ponto selecionado"])
        ref.addWidget(QLabel("Referência:"), 0, 0)
        ref.addWidget(self.cmb_referencia, 0, 1)
        raiz.addLayout(ref)

        self.chk_sobre_contorno = QCheckBox("Pique sobre o contorno")
        self.chk_sobre_contorno.setChecked(True)
        self.chk_ponto_controle = QCheckBox("Adicionar ponto de controle")
        self.chk_ponto_controle.setChecked(True)
        self.chk_manter_distancia = QCheckBox("Manter distância nos tamanhos")
        self.chk_dx = QCheckBox("Dx (cm)")
        self.edt_dx = QLineEdit("0")
        self.edt_dx.setEnabled(False)
        self.chk_dy = QCheckBox("Dy (cm)")
        self.edt_dy = QLineEdit("0")
        self.edt_dy.setEnabled(False)

        raiz.addWidget(self.chk_sobre_contorno)
        raiz.addWidget(self.chk_ponto_controle)
        raiz.addWidget(self.chk_manter_distancia)

        delta = QGridLayout()
        delta.setHorizontalSpacing(6)
        delta.addWidget(self.chk_dx, 0, 0)
        delta.addWidget(self.edt_dx, 0, 1)
        delta.addWidget(self.chk_dy, 1, 0)
        delta.addWidget(self.edt_dy, 1, 1)
        raiz.addLayout(delta)

        costura = QGridLayout()
        self.cmb_costura = QComboBox()
        self.cmb_costura.addItems(["Projetado", "Estendido", "Medir"])
        self.cmb_costura.setCurrentText("Estendido")
        costura.addWidget(QLabel("Pique na costura"), 0, 0)
        costura.addWidget(self.cmb_costura, 0, 1)
        raiz.addLayout(costura)

        self.lbl_status = QLabel("Clique no contorno para inserir.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color:#4c5d6f; font-size:11px;")
        raiz.addWidget(self.lbl_status)

        self.cmb_tipo.currentTextChanged.connect(self.preview.set_tipo)
        self.edt_largura.textChanged.connect(self._largura_alterada)
        self.edt_altura.textChanged.connect(self._altura_alterada)
        self.chk_manter_distancia.toggled.connect(self._manter_distancia_alterado)
        self.chk_dx.toggled.connect(self.edt_dx.setEnabled)
        self.chk_dy.toggled.connect(self.edt_dy.setEnabled)
        self.preview.set_tipo(self.cmb_tipo.currentText())

        self.setStyleSheet(
            """
            QDialog#InserirPiqueDialog { background:#eef7f9; }
            QLabel { color:#16202a; font-size:11px; }
            QLineEdit, QComboBox {
                background:#ffffff;
                border:1px solid #aeb8c2;
                min-height:19px;
                font-size:11px;
            }
            QCheckBox { font-size:11px; color:#16202a; }
            """
        )

    def largura(self) -> float:
        return self._float(self.edt_largura.text(), 0.3)

    def altura(self) -> float:
        return self._float(self.edt_altura.text(), 0.3)

    def angulo(self) -> float:
        return self._float(self.edt_angulo.text(), 0.0)

    def dx(self) -> float:
        return self._float(self.edt_dx.text(), 0.0) if self.chk_dx.isChecked() else 0.0

    def dy(self) -> float:
        return self._float(self.edt_dy.text(), 0.0) if self.chk_dy.isChecked() else 0.0

    def _largura_alterada(self, texto: str) -> None:
        if not self._sincronizando_medidas and self.chk_manter_distancia.isChecked():
            self._copiar_medida(self.edt_altura, texto)
        self.preview.set_medidas(self.largura(), self.altura())

    def _altura_alterada(self, texto: str) -> None:
        if not self._sincronizando_medidas and self.chk_manter_distancia.isChecked():
            self._copiar_medida(self.edt_largura, texto)
        self.preview.set_medidas(self.largura(), self.altura())

    def _manter_distancia_alterado(self, ativo: bool) -> None:
        if ativo:
            self._copiar_medida(self.edt_altura, self.edt_largura.text())
        self.preview.set_medidas(self.largura(), self.altura())

    def _copiar_medida(self, destino: QLineEdit, texto: str) -> None:
        self._sincronizando_medidas = True
        try:
            destino.setText(str(texto))
        finally:
            self._sincronizando_medidas = False

    @staticmethod
    def _float(texto: str, padrao: float) -> float:
        return numero_decimal_ponto(texto, padrao)


class _PiquePreview(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tipo = "T - forma T"
        self._largura = 0.3
        self._altura = 0.3
        self.setMinimumSize(138, 82)
        self.setFrameShape(QFrame.Box)
        self.setStyleSheet("background:#ffffff; border:1px solid #2b2b2b;")

    def set_tipo(self, tipo: str) -> None:
        self._tipo = str(tipo)
        self.update()

    def set_medidas(self, largura: float, altura: float) -> None:
        self._largura = max(0.01, float(largura))
        self._altura = max(0.01, float(altura))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#111111"), 1.2))
        cx = self.width() / 2
        top = 14
        bottom = self.height() - 12
        half = max(10.0, min(42.0, self._largura * 90.0))
        tipo = self._tipo.split(" - ", 1)[0]
        if tipo.startswith("T"):
            painter.drawLine(QPointF(cx - half, top), QPointF(cx + half, top))
            painter.drawLine(QPointF(cx, top), QPointF(cx, bottom))
        elif tipo.startswith("I"):
            painter.drawLine(QPointF(cx, top), QPointF(cx, bottom))
        elif tipo.startswith("V"):
            painter.drawLine(QPointF(cx, bottom), QPointF(cx - half, top))
            painter.drawLine(QPointF(cx, bottom), QPointF(cx + half, top))
        elif tipo.startswith("MX"):
            painter.drawLine(QPointF(cx - half, top), QPointF(cx + half, bottom))
            painter.drawLine(QPointF(cx + half, top), QPointF(cx - half, bottom))
        elif tipo.startswith("M+"):
            painter.drawLine(QPointF(cx - half, (top + bottom) / 2), QPointF(cx + half, (top + bottom) / 2))
            painter.drawLine(QPointF(cx, top), QPointF(cx, bottom))
        elif tipo.startswith("U"):
            painter.drawLine(QPointF(cx - half, top), QPointF(cx - half, bottom - 10))
            painter.drawLine(QPointF(cx + half, top), QPointF(cx + half, bottom - 10))
            painter.drawArc(int(cx - half), int(bottom - 20), int(half * 2), 20, 180 * 16, 180 * 16)
        else:
            painter.drawEllipse(QPointF(cx, (top + bottom) / 2), 9, 9)


class Ferramenta(FerramentaBase):
    id_ferramenta = "inserir_pique"
    nome = "Inserir Pique"
    usa_painel_auxiliar = False
    _dialog_global: InserirPiqueDialog | None = None

    def __init__(self):
        super().__init__()
        self._dialog: InserirPiqueDialog | None = type(self)._dialog_global
        self._hover: tuple[int, QPointF] | None = None
        self._molde_idx: int | None = None

    def on_activate(self, canvas):
        self._hover = None
        self._molde_idx = None
        self._abrir_dialogo(canvas)
        self.set_status("Clique esquerdo seleciona o molde. Depois clique para inserir piques. Direito finaliza.")

    def on_deactivate(self, canvas):
        if self._dialog:
            self._dialog.hide()
        self._hover = None
        self._molde_idx = None
        canvas.update()

    def on_canvas_resize(self, canvas) -> None:
        self._reposicionar_dialogo(canvas)

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_cena(canvas, event)
        if self._molde_idx is not None and self._dialog is not None and not self._dialog.chk_sobre_contorno.isChecked():
            self._hover = (self._molde_idx, pos)
        else:
            indices = {self._molde_idx} if self._molde_idx is not None else None
            self._hover = self._alvo_no_contorno(canvas, pos, indices=indices)
        canvas.update()
        event.accept()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._finalizar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = self._posicao_cena(canvas, event)
        if self._molde_idx is None:
            alvo = self._alvo_no_contorno(canvas, pos)
            if alvo is None:
                self.set_status("Clique sobre o contorno do molde que recebera os piques.")
                return False
            idx, ponto = alvo
            self._selecionar_molde(canvas, idx)
            self._hover = (idx, ponto)
            self.set_status("Molde selecionado. Clique esquerdo insere piques; direito finaliza.")
            canvas.update()
            event.accept()
            return True

        if self._dialog is not None and not self._dialog.chk_sobre_contorno.isChecked():
            alvo = (self._molde_idx, pos)
        else:
            alvo = self._alvo_no_contorno(canvas, pos, indices={self._molde_idx})
        if alvo is None:
            self.set_status("Clique no contorno do molde selecionado para inserir o pique.")
            return False
        idx, ponto = alvo
        if self._aplicar_pique(canvas, idx, ponto):
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
            canvas.update()
            event.accept()
            return True
        return False

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_molde_selecionado(canvas, painter)
        if self._hover is None:
            return
        self._desenhar_preview_pique(canvas, painter)

    def _selecionar_molde(self, canvas, idx: int) -> None:
        self._molde_idx = int(idx)
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(idx)}

    def _finalizar(self, canvas) -> None:
        self._hover = None
        self._molde_idx = None
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        else:
            canvas.update()
        self.set_status("Ferramenta Inserir Pique finalizada.")

    def _desenhar_molde_selecionado(self, canvas, painter) -> None:
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[self._molde_idx]
        pontos = [self._ponto_qt(p) for p in el.get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) < 2:
            return
        cor_realce = self._cor_realce_canvas(canvas)
        if hasattr(canvas, "_desenhar_polilinha"):
            canvas._desenhar_polilinha(painter, pontos, cor=cor_realce, espessura=2.2)
            if hasattr(canvas, "_desenhar_marcacoes_piques_elemento"):
                cor_molde = str(el.get("cor") or "#ffffff")
                canvas._desenhar_marcacoes_piques_elemento(painter, el, cor_molde)
            return
        painter.save()
        painter.setPen(QPen(QColor(cor_realce), 2))
        for a, b in zip(pontos, pontos[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def _desenhar_preview_pique(self, canvas, painter) -> None:
        if self._dialog is None or self._hover is None:
            return
        idx, ponto = self._hover
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        ponto_final = QPointF(ponto.x() + self._dialog.dx(), ponto.y() - self._dialog.dy())
        sobre_contorno = bool(self._dialog.chk_sobre_contorno.isChecked())
        info_segmento = self._segmento_mais_proximo_elemento(el, ponto) if sobre_contorno else None
        segmento = (info_segmento[1], info_segmento[2]) if info_segmento is not None else None
        segmentos = self._segmentos_pique(
            el,
            ponto_final,
            segmento,
            self._dialog.cmb_tipo.currentText(),
            self._dialog.largura(),
            self._dialog.altura(),
            self._dialog.angulo(),
            sobre_contorno=sobre_contorno,
        )
        if not sobre_contorno and not self._segmentos_pique_dentro_molde(el, segmentos):
            cor = "#ff4fa3"
        else:
            cor = self._cor_realce_canvas(canvas)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        for a, b in segmentos:
            pa = QPointF(float(a[0]), float(a[1]))
            pb = QPointF(float(b[0]), float(b[1]))
            if hasattr(canvas, "_desenhar_segmento"):
                canvas._desenhar_segmento(painter, pa, pb, cor=cor, espessura=2.2)
            else:
                painter.setPen(QPen(QColor(cor), 2))
                painter.drawLine(canvas._cena_para_tela(pa), canvas._cena_para_tela(pb))
        painter.restore()

    def set_status(self, texto: str):
        if self._dialog is not None:
            self._dialog.lbl_status.setText(texto)

    def _abrir_dialogo(self, canvas) -> None:
        cls = type(self)
        if cls._dialog_global is None:
            cls._dialog_global = InserirPiqueDialog(canvas)
            instalar_memoria_posicao(cls._dialog_global, "dialog:inserir_pique")
        self._dialog = cls._dialog_global
        if self._dialog.parentWidget() is not canvas:
            self._dialog.setParent(canvas)
        if not self._dialog.isVisible():
            self._dialog.show()
        self._reposicionar_dialogo(canvas)

    def _reposicionar_dialogo(self, canvas) -> None:
        if not self._dialog:
            return
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos = canvas.calcular_posicao_painel_auxiliar(self._dialog.width(), self._dialog.height(), abaixo_coordenadas=True)
            restaurar_posicao(self._dialog, "dialog:inserir_pique", fallback=canvas.mapToGlobal(pos))

    def _aplicar_pique(self, canvas, idx: int, ponto: QPointF) -> bool:
        if self._dialog is None or not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        ponto_final = QPointF(ponto.x() + self._dialog.dx(), ponto.y() - self._dialog.dy())
        marcacoes = list(el.get("marcacoes_no_perimetro", []) or [])
        tupla = (float(ponto_final.x()), float(ponto_final.y()))
        sobre_contorno = bool(self._dialog.chk_sobre_contorno.isChecked())
        if sobre_contorno and not any(self._dist_tuple(tupla, item) <= 1e-6 for item in marcacoes):
            marcacoes.append(tupla)
        el["marcacoes_no_perimetro"] = marcacoes
        info_segmento = self._segmento_mais_proximo_elemento(el, ponto) if sobre_contorno else None
        segmento = (info_segmento[1], info_segmento[2]) if info_segmento is not None else None
        segmentos_pique = self._segmentos_pique(
            el,
            QPointF(ponto_final),
            segmento,
            self._dialog.cmb_tipo.currentText(),
            self._dialog.largura(),
            self._dialog.altura(),
            self._dialog.angulo(),
            sobre_contorno=sobre_contorno,
        )
        if not sobre_contorno and not self._segmentos_pique_dentro_molde(el, segmentos_pique):
            self.set_status("Pique interno fora do molde. Ajuste largura, altura, angulo ou clique em outro trecho.")
            return False
        ponto_controle = QPointF(ponto_final)

        config = {
            "ponto": tupla,
            "ponto_controle": (float(ponto_controle.x()), float(ponto_controle.y())),
            "tipo": self._dialog.cmb_tipo.currentText(),
            "largura_cm": self._dialog.largura(),
            "altura_cm": self._dialog.altura(),
            "angulo": self._dialog.angulo(),
            "referencia": self._dialog.cmb_referencia.currentText(),
            "sobre_contorno": sobre_contorno,
            "adicionar_ponto_controle": bool(self._dialog.chk_ponto_controle.isChecked()),
            "manter_distancia_tamanhos": bool(self._dialog.chk_manter_distancia.isChecked()),
            "dx_cm": self._dialog.dx(),
            "dy_cm": self._dialog.dy(),
            "pique_na_costura": self._dialog.cmb_costura.currentText(),
            "segmentos": segmentos_pique,
        }
        configs = [cfg for cfg in (el.get("piques_config", []) or []) if isinstance(cfg, dict)]
        configs.append(config)
        el["piques_config"] = configs
        el["mostrar_piques"] = True

        if self._dialog.chk_ponto_controle.isChecked() and el.get("molde"):
            if sobre_contorno and info_segmento is not None:
                self._inserir_ponto_no_contorno(el, ponto_controle, info_segmento[0])
                self._adicionar_ponto_controle_principal(el, ponto_controle, info_segmento[0])
            else:
                self._adicionar_ponto_controle_auxiliar(el, ponto_controle)
        self.set_status(f"Pique inserido: {config['tipo']}.")
        return True

    def _segmentos_pique(
        self,
        el: dict,
        ponto: QPointF,
        segmento: tuple[QPointF, QPointF] | None,
        tipo: str,
        largura: float,
        altura: float,
        angulo_extra: float = 0.0,
        sobre_contorno: bool = True,
    ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        largura = max(0.01, abs(float(largura)))
        altura = max(0.01, abs(float(altura)))
        normal, tangente = self._base_pique(el, ponto, segmento, sobre_contorno)
        if not sobre_contorno and abs(float(angulo_extra)) > 1e-9:
            normal, tangente = self._rotacionar_base(normal, tangente, float(angulo_extra))

        def mapear(x: float, y: float) -> tuple[float, float]:
            px = ponto.x() + (normal.x() * x) + (tangente.x() * y)
            py = ponto.y() + (normal.y() * x) + (tangente.y() * y)
            return (float(px), float(py))

        meia_largura = largura / 2.0
        meia_altura = altura / 2.0
        codigo = str(tipo or "").split(" - ", 1)[0].strip().upper()
        locais: list[tuple[tuple[float, float], tuple[float, float]]]
        if codigo.startswith("T"):
            locais = [((0.0, 0.0), (altura, 0.0)), ((altura, -meia_largura), (altura, meia_largura))]
        elif codigo.startswith("I"):
            locais = [((0.0, 0.0), (altura, 0.0))]
        elif codigo == "V1":
            locais = [((0.0, -meia_altura), (0.0, meia_altura)), ((0.0, -meia_altura), (largura, meia_altura))]
        elif codigo == "V2":
            locais = [((0.0, -meia_altura), (0.0, meia_altura)), ((0.0, meia_altura), (largura, -meia_altura))]
        elif codigo.startswith("V"):
            locais = [((0.0, -meia_altura), (largura, 0.0)), ((largura, 0.0), (0.0, meia_altura))]
        elif codigo.startswith("MX"):
            locais = [((-meia_largura, -meia_altura), (meia_largura, meia_altura)), ((meia_largura, -meia_altura), (-meia_largura, meia_altura))]
        elif codigo.startswith("M+"):
            locais = [((-meia_largura, 0.0), (meia_largura, 0.0)), ((0.0, -meia_altura), (0.0, meia_altura))]
        elif codigo.startswith("U"):
            locais = [((0.0, -meia_largura), (altura, -meia_largura)), ((0.0, meia_largura), (altura, meia_largura)), ((altura, -meia_largura), (altura, meia_largura))]
        else:
            locais = [((0.0, -meia_altura), (0.0, meia_altura))]
        return [(mapear(a[0], a[1]), mapear(b[0], b[1])) for a, b in locais]

    @staticmethod
    def _centro_segmentos_pique(segmentos: list[tuple[tuple[float, float], tuple[float, float]]], fallback: QPointF) -> QPointF:
        pontos: list[tuple[float, float]] = []
        for segmento in segmentos:
            try:
                pontos.append((float(segmento[0][0]), float(segmento[0][1])))
                pontos.append((float(segmento[1][0]), float(segmento[1][1])))
            except Exception:
                continue
        if not pontos:
            return QPointF(fallback)
        return QPointF(sum(x for x, _y in pontos) / len(pontos), sum(y for _x, y in pontos) / len(pontos))

    def _segmentos_pique_dentro_molde(self, el: dict, segmentos: list[tuple[tuple[float, float], tuple[float, float]]]) -> bool:
        poligono = [self._tupla_ponto(p) for p in el.get("pontos", []) or []]
        poligono = [p for p in poligono if p is not None]
        if len(poligono) < 3:
            return False
        for a, b in segmentos:
            for passo in range(7):
                t = passo / 6.0
                ponto = (float(a[0]) + ((float(b[0]) - float(a[0])) * t), float(a[1]) + ((float(b[1]) - float(a[1])) * t))
                if not self._ponto_dentro_ou_na_borda(ponto, poligono):
                    return False
        return True

    def _ponto_dentro_ou_na_borda(self, ponto: tuple[float, float], poligono: list[tuple[float, float]], tol: float = 1e-6) -> bool:
        px, py = ponto
        pts = list(poligono)
        if self._dist_tuple(pts[0], pts[-1]) > tol:
            pts.append(pts[0])
        for a, b in zip(pts, pts[1:]):
            if self._dist_ponto_segmento_tuple(ponto, a, b) <= tol:
                return True
        dentro = False
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            cruza = (yi > py) != (yj > py)
            if cruza:
                den = yj - yi
                if abs(den) <= 1e-12:
                    den = 1e-12
                x_inter = ((xj - xi) * (py - yi) / den) + xi
                if px < x_inter:
                    dentro = not dentro
            j = i
        return dentro

    @staticmethod
    def _dist_ponto_segmento_tuple(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        px, py = p
        ax, ay = a
        bx, by = b
        vx = bx - ax
        vy = by - ay
        denom = (vx * vx) + (vy * vy)
        if denom <= 1e-12:
            return sqrt(((px - ax) ** 2) + ((py - ay) ** 2))
        t = ((px - ax) * vx + (py - ay) * vy) / denom
        t = max(0.0, min(1.0, t))
        qx = ax + (vx * t)
        qy = ay + (vy * t)
        return sqrt(((px - qx) ** 2) + ((py - qy) ** 2))

    def _segmento_mais_proximo_elemento(self, el: dict, ponto: QPointF) -> tuple[int, QPointF, QPointF] | None:
        pontos = [self._ponto_qt(p) for p in el.get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) < 2:
            return None
        melhor: tuple[float, int, QPointF, QPointF] | None = None
        for seg_idx, (a, b) in enumerate(zip(pontos, pontos[1:])):
            proj = self._projetar_ponto_segmento(ponto, a, b)
            dist = self._dist(ponto, proj)
            if melhor is None or dist < melhor[0]:
                melhor = (dist, seg_idx, a, b)
        if melhor is None:
            return None
        return int(melhor[1]), QPointF(melhor[2]), QPointF(melhor[3])

    @staticmethod
    def _tangente_segmento(segmento: tuple[QPointF, QPointF] | None) -> QPointF:
        if segmento is None:
            return QPointF(0.0, 1.0)
        a, b = segmento
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-9:
            return QPointF(0.0, 1.0)
        return QPointF(dx / comp, dy / comp)

    def _base_pique(
        self,
        el: dict,
        ponto: QPointF,
        segmento: tuple[QPointF, QPointF] | None,
        sobre_contorno: bool,
    ) -> tuple[QPointF, QPointF]:
        tangente = self._tangente_segmento(segmento)
        normal = QPointF(-tangente.y(), tangente.x())
        if not sobre_contorno:
            return normal, tangente
        normal_canto = self._normal_interna_canto(el, ponto)
        if normal_canto is not None:
            tangente_canto = QPointF(-normal_canto.y(), normal_canto.x())
            return normal_canto, tangente_canto
        if segmento is not None:
            normal_fora = self._normal_orientada_para_fora(el, ponto, normal)
            normal = QPointF(-normal_fora.x(), -normal_fora.y())
        return normal, tangente

    def _normal_interna_canto(self, el: dict, ponto: QPointF) -> QPointF | None:
        pontos = [self._ponto_qt(item) for item in el.get("pontos", []) or []]
        pontos = [pt for pt in pontos if pt is not None]
        if len(pontos) < 3:
            return None
        fechado = self._dist(pontos[0], pontos[-1]) <= 1e-6
        base = pontos[:-1] if fechado else pontos
        if len(base) < 3:
            return None
        vertice_idx = None
        for idx, pt in enumerate(base):
            if self._dist(pt, ponto) <= 1e-6:
                vertice_idx = idx
                break
        if vertice_idx is None:
            return None
        if not fechado and (vertice_idx == 0 or vertice_idx == len(base) - 1):
            return None
        anterior = base[(vertice_idx - 1) % len(base)]
        atual = base[vertice_idx]
        proximo = base[(vertice_idx + 1) % len(base)]
        n_anterior = self._normal_interna_segmento(el, atual, (anterior, atual))
        n_proximo = self._normal_interna_segmento(el, atual, (atual, proximo))
        soma = QPointF(n_anterior.x() + n_proximo.x(), n_anterior.y() + n_proximo.y())
        return self._normalizar_vetor(soma)

    def _normal_interna_segmento(self, el: dict, ponto: QPointF, segmento: tuple[QPointF, QPointF]) -> QPointF:
        tangente = self._tangente_segmento(segmento)
        normal = QPointF(-tangente.y(), tangente.x())
        normal_fora = self._normal_orientada_para_fora(el, ponto, normal)
        return QPointF(-normal_fora.x(), -normal_fora.y())

    @staticmethod
    def _normalizar_vetor(vetor: QPointF) -> QPointF | None:
        comp = sqrt((vetor.x() * vetor.x()) + (vetor.y() * vetor.y()))
        if comp <= 1e-9:
            return None
        return QPointF(vetor.x() / comp, vetor.y() / comp)

    def _normal_orientada_para_fora(self, el: dict, ponto: QPointF, normal: QPointF) -> QPointF:
        pontos = [self._tupla_ponto(p) for p in el.get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) < 3:
            return normal
        cx = sum(x for x, _y in pontos) / len(pontos)
        cy = sum(y for _x, y in pontos) / len(pontos)
        vx = ponto.x() - cx
        vy = ponto.y() - cy
        if (normal.x() * vx + normal.y() * vy) < 0.0:
            return QPointF(-normal.x(), -normal.y())
        return normal

    @staticmethod
    def _rotacionar_base(normal: QPointF, tangente: QPointF, angulo_graus: float) -> tuple[QPointF, QPointF]:
        rad = radians(angulo_graus)
        c = cos(rad)
        s = sin(rad)
        n = QPointF((normal.x() * c) + (tangente.x() * s), (normal.y() * c) + (tangente.y() * s))
        t = QPointF((tangente.x() * c) - (normal.x() * s), (tangente.y() * c) - (normal.y() * s))
        return n, t

    def _adicionar_ponto_controle_auxiliar(self, el: dict, ponto: QPointF) -> None:
        novo = (float(ponto.x()), float(ponto.y()))
        auxiliares = []
        for item in el.get("controle_auxiliares", []) or []:
            pt = self._tupla_ponto(item)
            if pt is not None:
                auxiliares.append(pt)
        if not any(self._dist_tuple(novo, item) <= 1e-6 for item in auxiliares):
            auxiliares.append(novo)
        el["controle_auxiliares"] = auxiliares
        el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]

    def _adicionar_ponto_controle_principal(self, el: dict, ponto: QPointF, seg_idx: int) -> None:
        novo = (float(ponto.x()), float(ponto.y()))
        cantos = [pt for pt in (self._tupla_ponto(item) for item in el.get("controle_cantos", []) or []) if pt is not None]
        if not cantos:
            pontos = [pt for pt in (self._tupla_ponto(item) for item in el.get("pontos", []) or []) if pt is not None]
            if len(pontos) >= 2 and self._dist_tuple(pontos[0], pontos[-1]) <= 1e-6:
                pontos = pontos[:-1]
            cantos = [pt for pt in pontos if self._dist_tuple(pt, novo) > 1e-6]
        if not any(self._dist_tuple(novo, item) <= 1e-6 for item in cantos):
            inserir_em = self._indice_insercao_canto(el, novo, seg_idx, cantos)
            cantos.insert(inserir_em, novo)
        el["controle_cantos"] = cantos
        el["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in cantos]

    def _indice_insercao_canto(self, el: dict, novo: tuple[float, float], seg_idx: int, cantos: list[tuple[float, float]]) -> int:
        pontos = [pt for pt in (self._tupla_ponto(item) for item in el.get("pontos", []) or []) if pt is not None]
        if len(pontos) >= 2 and self._dist_tuple(pontos[0], pontos[-1]) <= 1e-6:
            pontos = pontos[:-1]
        if not pontos:
            return len(cantos)
        novo_idx = self._indice_ponto_mais_proximo(pontos, novo)
        if novo_idx is None:
            novo_idx = max(0, min(int(seg_idx) + 1, len(pontos) - 1))
        inserir_em = 0
        for i, canto in enumerate(cantos):
            canto_idx = self._indice_ponto_mais_proximo(pontos, canto)
            if canto_idx is not None and canto_idx <= novo_idx:
                inserir_em = i + 1
        return max(0, min(len(cantos), inserir_em))

    def _indice_ponto_mais_proximo(self, pontos: list[tuple[float, float]], alvo: tuple[float, float]) -> int | None:
        if not pontos:
            return None
        melhor_idx = 0
        melhor_dist = float("inf")
        for idx, ponto in enumerate(pontos):
            dist = self._dist_tuple(ponto, alvo)
            if dist < melhor_dist:
                melhor_idx = idx
                melhor_dist = dist
        return melhor_idx

    def _inserir_ponto_no_contorno(self, el: dict, ponto: QPointF, seg_idx: int) -> None:
        pontos = [self._tupla_ponto(item) for item in el.get("pontos", []) or []]
        pontos = [item for item in pontos if item is not None]
        seg_idx = int(seg_idx)
        if len(pontos) < 2 or not (0 <= seg_idx < len(pontos) - 1):
            return
        novo = (float(ponto.x()), float(ponto.y()))
        if any(self._dist_tuple(item, novo) <= 1e-6 for item in pontos):
            return
        novo_idx = seg_idx + 1
        pontos_depois = list(pontos)
        pontos_depois.insert(novo_idx, novo)
        self._inserir_ponto_graduacao_no_contorno(el, pontos, pontos_depois, seg_idx, novo_idx, novo)
        el["pontos"] = pontos_depois

    def _inserir_ponto_graduacao_no_contorno(
        self,
        el: dict,
        pontos_antes: list[tuple[float, float]],
        pontos_depois: list[tuple[float, float]],
        seg_idx: int,
        novo_idx: int,
        novo: tuple[float, float],
    ) -> None:
        pontos_cfg = self._pontos_config_graduacao(el)
        if not pontos_cfg:
            return
        base_antes = self._contorno_sem_fechamento(pontos_antes)
        base_depois = self._contorno_sem_fechamento(pontos_depois)
        if len(base_antes) < 2 or not (0 <= novo_idx < len(base_depois)):
            return
        try:
            from canvas.visualizacao import VisualizacaoCanvas
        except Exception:
            return

        fechado = len(pontos_antes) > 2 and self._dist_tuple(pontos_antes[0], pontos_antes[-1]) <= 1e-6
        origem_idx = max(0, min(seg_idx, len(base_antes) - 1))
        destino_idx = (origem_idx + 1) % len(base_antes) if fechado else min(origem_idx + 1, len(base_antes) - 1)
        origem = QPointF(*base_antes[origem_idx])
        destino = QPointF(*base_antes[destino_idx])
        fator = self._fracao_no_segmento(QPointF(*novo), origem, destino)
        referencias = VisualizacaoCanvas._pontos_referencia_graduacao(el)
        nomes_tamanhos = self._nomes_tamanhos_graduacao(el, pontos_cfg)
        if not nomes_tamanhos:
            return

        contorno_antes = [QPointF(x, y) for x, y in base_antes]
        valores_novo: dict[str, dict[str, float]] = {}
        for nome in nomes_tamanhos:
            deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
                pontos_cfg,
                nome,
                len(contorno_antes),
                contorno=contorno_antes,
                referencias=referencias,
            )
            if deslocamentos and len(deslocamentos) == len(contorno_antes):
                dx_a, dy_a = deslocamentos[origem_idx]
                dx_b, dy_b = deslocamentos[destino_idx]
            else:
                dx_a = dy_a = dx_b = dy_b = 0.0
            valores_novo[nome] = {
                "dx": float(dx_a + ((dx_b - dx_a) * fator)),
                "dy": float(dy_a + ((dy_b - dy_a) * fator)),
            }

        pontos_remapeados = self._remapear_graduacao_apos_insercao(pontos_cfg, base_antes, base_depois, novo_idx)
        pontos_remapeados[str(novo_idx)] = {
            "indice": int(novo_idx),
            "numero": int(novo_idx) + 1,
            "ponto": (float(novo[0]), float(novo[1])),
            "valores": valores_novo,
        }
        pontos_ordenados = self._ordenar_pontos_graduacao(pontos_remapeados)
        tabela = el.setdefault("graduacao_tabela", {})
        if isinstance(tabela, dict):
            tabela["modo"] = "dx_dy"
            tabela["pontos"] = pontos_ordenados
        el["graduacao_pontos"] = deepcopy(pontos_ordenados)

    def _pontos_config_graduacao(self, el: dict) -> dict:
        tabela = el.get("graduacao_tabela") if isinstance(el.get("graduacao_tabela"), dict) else None
        if isinstance(tabela, dict) and isinstance(tabela.get("pontos"), dict):
            return tabela.get("pontos") or {}
        legado = el.get("graduacao_pontos")
        return legado if isinstance(legado, dict) else {}

    def _nomes_tamanhos_graduacao(self, el: dict, pontos_cfg: dict) -> list[str]:
        nomes: list[str] = []
        for linha in el.get("graduacao_tamanhos", []) or []:
            if not isinstance(linha, dict) or not linha.get("ativo", True):
                continue
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if nome and nome not in nomes:
                nomes.append(nome)
        for cfg in pontos_cfg.values():
            valores = cfg.get("valores") if isinstance(cfg, dict) else None
            if not isinstance(valores, dict):
                continue
            for nome in valores:
                texto = str(nome or "").strip()
                if texto and texto not in nomes:
                    nomes.append(texto)
        return nomes

    def _remapear_graduacao_apos_insercao(
        self,
        pontos_cfg: dict,
        base_antes: list[tuple[float, float]],
        base_depois: list[tuple[float, float]],
        novo_idx: int,
    ) -> dict:
        saida: dict[str, dict] = {}
        for chave, cfg in pontos_cfg.items():
            if not isinstance(cfg, dict):
                continue
            antigo_idx = self._indice_graduacao_cfg(cfg, chave, base_antes)
            if antigo_idx is None or not (0 <= antigo_idx < len(base_antes)):
                continue
            indice = antigo_idx + 1 if antigo_idx >= novo_idx else antigo_idx
            if not (0 <= indice < len(base_depois)):
                continue
            novo_cfg = deepcopy(cfg)
            novo_cfg["indice"] = int(indice)
            novo_cfg["numero"] = int(indice) + 1
            novo_cfg["ponto"] = (float(base_depois[indice][0]), float(base_depois[indice][1]))
            saida[str(indice)] = novo_cfg
        return saida

    def _indice_graduacao_cfg(self, cfg: dict, chave: str, base: list[tuple[float, float]]) -> int | None:
        ponto_cfg = self._tupla_ponto(cfg.get("ponto")) if isinstance(cfg, dict) else None
        if ponto_cfg is not None:
            return self._indice_ponto_mais_proximo(base, ponto_cfg)
        try:
            return int(cfg.get("indice", chave))
        except Exception:
            return None

    @staticmethod
    def _ordenar_pontos_graduacao(pontos_cfg: dict) -> dict:
        def chave_ordem(item) -> int:
            try:
                return int(item[0])
            except Exception:
                return 0

        return {str(chave): valor for chave, valor in sorted(pontos_cfg.items(), key=chave_ordem)}

    def _contorno_sem_fechamento(self, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        contorno = list(pontos)
        if len(contorno) > 1 and self._dist_tuple(contorno[0], contorno[-1]) <= 1e-6:
            contorno = contorno[:-1]
        return contorno

    @staticmethod
    def _fracao_no_segmento(ponto: QPointF, origem: QPointF, destino: QPointF) -> float:
        vx = destino.x() - origem.x()
        vy = destino.y() - origem.y()
        denom = (vx * vx) + (vy * vy)
        if denom <= 1e-12:
            return 0.0
        t = ((ponto.x() - origem.x()) * vx + (ponto.y() - origem.y()) * vy) / denom
        return max(0.0, min(1.0, float(t)))

    @staticmethod
    def _cor_realce_canvas(canvas) -> str:
        try:
            cor = str(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
            return cor if QColor(cor).isValid() else "#2da8ff"
        except Exception:
            return "#2da8ff"

    def _alvo_no_contorno(self, canvas, pos: QPointF, indices: set[int] | None = None) -> tuple[int, QPointF] | None:
        tolerancia = 14.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor: tuple[float, int, QPointF] | None = None
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if indices is not None and idx not in indices:
                continue
            if not isinstance(el, dict) or el.get("tipo") != "polyline" or not el.get("molde"):
                continue
            pontos = [self._ponto_qt(p) for p in el.get("pontos", []) or []]
            pontos = [p for p in pontos if p is not None]
            if len(pontos) < 2:
                continue
            for a, b in zip(pontos, pontos[1:]):
                proj = self._projetar_ponto_segmento(pos, a, b)
                dist = self._dist(pos, proj)
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, proj)
        if melhor is None:
            return None
        _dist, idx, ponto = melhor
        return idx, ponto

    def _posicao_cena(self, canvas, event) -> QPointF:
        try:
            return canvas._ponto_com_snap(event.position())
        except Exception:
            if hasattr(canvas, "_tela_para_cena"):
                return canvas._tela_para_cena(event.position())
            return QPointF(event.position())

    @staticmethod
    def _ponto_qt(valor) -> QPointF | None:
        try:
            if isinstance(valor, QPointF):
                return QPointF(valor)
            if isinstance(valor, dict):
                return QPointF(float(valor["x"]), float(valor["y"]))
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return QPointF(float(valor[0]), float(valor[1]))
        except Exception:
            return None
        return None

    @staticmethod
    def _tupla_ponto(valor) -> tuple[float, float] | None:
        try:
            if isinstance(valor, QPointF):
                return float(valor.x()), float(valor.y())
            if isinstance(valor, dict):
                return float(valor["x"]), float(valor["y"])
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return float(valor[0]), float(valor[1])
        except Exception:
            return None
        return None

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

    @staticmethod
    def _dist_tuple(a, b) -> float:
        pa = Ferramenta._tupla_ponto(a)
        pb = Ferramenta._tupla_ponto(b)
        if pa is None or pb is None:
            return float("inf")
        return sqrt((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2)

    @staticmethod
    def _projetar_ponto_segmento(p: QPointF, a: QPointF, b: QPointF) -> QPointF:
        vx = b.x() - a.x()
        vy = b.y() - a.y()
        denom = vx * vx + vy * vy
        if denom <= 1e-12:
            return QPointF(a)
        t = ((p.x() - a.x()) * vx + (p.y() - a.y()) * vy) / denom
        t = max(0.0, min(1.0, t))
        return QPointF(a.x() + vx * t, a.y() + vy * t)
