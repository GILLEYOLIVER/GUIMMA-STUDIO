from __future__ import annotations

from math import acos, atan2, sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "extrair_molde"
    nome = "Extrair Molde"
    descricao_painel = "LMB seleciona, RMB extrai contorno, LMB cria molde com controles."

    def __init__(self):
        super().__init__()
        self._dialog: QDialog | None = None
        self._idx_selecionado: int | None = None
        self._contorno_extraido: list[QPointF] | None = None
        self._molde_criado = False
        self._cfg = {
            "modo": "Automático",
            "detectar_graduacoes": True,
            "detectar_piques": True,
            "detectar_auxiliares": False,
            "compor_contornos": True,
            "usar_auxiliares": True,
            "quebrar_auxiliares": True,
            "converter_auxiliares": True,
        }

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._idx_selecionado = None
        self._contorno_extraido = None
        self._molde_criado = False
        self._abrir_config(canvas)
        self.set_status("LMB: seleciona contorno fechado | RMB: extrai | LMB: cria molde")

    def on_deactivate(self, canvas):
        if self._dialog:
            self._dialog.hide()
        self._idx_selecionado = None
        self._contorno_extraido = None
        self._molde_criado = False

    def on_mouse_press(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())

        if event.button() == Qt.LeftButton:
            if self._idx_selecionado is not None and self._contorno_extraido and not self._molde_criado:
                ok = self._criar_molde(canvas, self._idx_selecionado)
                self.set_status("Molde criado com sucesso." if ok else "Falha ao criar molde.")
                canvas.update()
                event.accept()
                return ok

            candidatos = canvas._indices_elementos_em_ponto(pos)
            if not candidatos:
                self.set_status("Selecione um contorno fechado.")
                return False
            idx = candidatos[0]
            if idx < 0 or idx >= len(canvas.cena.elementos):
                return False

            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                self.set_status("A extração atual funciona em polyline fechada.")
                return False
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if not self._eh_fechado(pontos):
                self.set_status("Contorno está aberto. Feche-o antes de extrair.")
                return False

            self._idx_selecionado = idx
            self._contorno_extraido = None
            self._molde_criado = False
            canvas._selecionados = {idx}
            self.set_status("Contorno selecionado. RMB para extrair o traçado exato.")
            canvas.update()
            event.accept()
            return True

        if event.button() != Qt.RightButton:
            return False
        if self._idx_selecionado is None:
            self.set_status("Selecione um contorno fechado antes de extrair.")
            return False

        el = canvas.cena.elementos[self._idx_selecionado]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        self._contorno_extraido = [QPointF(p) for p in pontos]
        metadados = self._extrair_metadados(self._contorno_extraido)
        el["extracao_molde"] = metadados
        if self._cfg["quebrar_auxiliares"]:
            el["pontos"] = self._remover_segmentos_auxiliares([(p.x(), p.y()) for p in self._contorno_extraido], metadados)
            self._contorno_extraido = [QPointF(float(x), float(y)) for x, y in el["pontos"]]
        self._molde_criado = False
        canvas._registrar_historico()
        self.set_status("Traçado extraído. Agora clique esquerdo para criar o molde.")
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter: QPainter):
        if self._idx_selecionado is None:
            return
        if self._idx_selecionado < 0 or self._idx_selecionado >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[self._idx_selecionado]
        if el.get("tipo") != "polyline":
            return

        base = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        self._desenhar_contorno(canvas, painter, base, QColor("#ff2fff"), 2.0)
        if self._contorno_extraido:
            self._desenhar_contorno(canvas, painter, self._contorno_extraido, QColor("#ff2a2a"), 2.0)
        if self._molde_criado:
            self._desenhar_controles_molde(canvas, painter, el)

    def _desenhar_contorno(self, canvas, painter, pontos: list[QPointF], cor: QColor, esp: float):
        if len(pontos) < 2:
            return
        for a, b in zip(pontos, pontos[1:]):
            canvas._desenhar_segmento(painter, a, b, cor=cor.name(), espessura=esp)

    def _criar_molde(self, canvas, idx: int) -> bool:
        el = canvas.cena.elementos[idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if not self._eh_fechado(pontos):
            return False
        principais = self._ordenar_principais_horario(pontos[:-1])
        auxiliares = []
        for i in range(len(principais)):
            a = principais[i]
            b = principais[(i + 1) % len(principais)]
            aux = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
            auxiliares.append({"x": aux.x(), "y": aux.y(), "oculto": True})

        el["molde"] = True
        el["controle_cantos"] = [(p.x(), p.y()) for p in principais]
        el["pontos_controle_principais"] = [{"indice": i + 1, "x": p.x(), "y": p.y()} for i, p in enumerate(principais)]
        el["pontos_auxiliares"] = auxiliares
        self._molde_criado = True
        canvas._registrar_historico()
        return True

    def _desenhar_controles_molde(self, canvas, painter, el: dict):
        principais = [QPointF(float(p["x"]), float(p["y"])) for p in el.get("pontos_controle_principais", [])]
        auxiliares = [QPointF(float(p["x"]), float(p["y"])) for p in el.get("pontos_auxiliares", [])]
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        for i, pt in enumerate(principais, start=1):
            tela = canvas._cena_para_tela(pt)
            painter.setPen(QPen(QColor("#ffffff"), 1.2))
            painter.setBrush(QColor("#101010"))
            painter.drawRect(int(tela.x() - 4), int(tela.y() - 4), 8, 8)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(tela.x() - 6), int(tela.y() - 8), str(i))
        painter.setPen(QPen(QColor("#ff2a2a"), 1))
        painter.setBrush(QColor("#ff2a2a"))
        for pt in auxiliares:
            tela = canvas._cena_para_tela(pt)
            painter.drawEllipse(tela, 2.0, 2.0)

    def _eh_fechado(self, pontos: list[QPointF]) -> bool:
        return len(pontos) >= 3 and self._dist(pontos[0], pontos[-1]) <= 0.001

    def _ordenar_principais_horario(self, pontos: list[QPointF]) -> list[QPointF]:
        area2 = 0.0
        for a, b in zip(pontos, pontos[1:] + [pontos[0]]):
            area2 += (b.x() - a.x()) * (b.y() + a.y())
        if area2 > 0:
            pontos = list(reversed(pontos))
        centro = QPointF(sum(p.x() for p in pontos) / len(pontos), sum(p.y() for p in pontos) / len(pontos))
        return sorted(pontos, key=lambda p: atan2(p.y() - centro.y(), p.x() - centro.x()), reverse=True)

    def _abrir_config(self, canvas):
        if self._dialog is None:
            self._dialog = QDialog(canvas)
            self._dialog.setWindowTitle("Definir contorno")
            self._dialog.setWindowFlags(Qt.Tool)
            self._dialog.setModal(False)
            self._dialog.setStyleSheet(
                """
                QDialog {
                    background: #f1f4f8;
                    color: #111111;
                }
                QLabel, QCheckBox, QPushButton, QComboBox {
                    color: #111111;
                }
                QComboBox, QPushButton {
                    background: #ffffff;
                    border: 1px solid #b9c4cf;
                    border-radius: 4px;
                    min-height: 24px;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1px solid #4f5d6c;
                    background: #ffffff;
                }
                QCheckBox::indicator:checked {
                    border: 1px solid #145f9b;
                    background: #cfe7fb;
                }
                """
            )
            lay = QVBoxLayout(self._dialog)
            form = QFormLayout()
            self.cmb_modo = QComboBox()
            self.cmb_modo.addItems(["Automático", "Manual"])
            self.cmb_modo.setCurrentText(str(self._cfg["modo"]))
            form.addRow("Modo", self.cmb_modo)
            lay.addLayout(form)

            self.chk_grad = QCheckBox("Detectar graduações")
            self.chk_grad.setChecked(bool(self._cfg["detectar_graduacoes"]))
            self.chk_piques = QCheckBox("Detectar piques")
            self.chk_piques.setChecked(bool(self._cfg["detectar_piques"]))
            self.chk_aux = QCheckBox("Detectar linhas auxiliares")
            self.chk_aux.setChecked(bool(self._cfg["detectar_auxiliares"]))
            self.chk_compor = QCheckBox("Compor contornos")
            self.chk_compor.setChecked(bool(self._cfg["compor_contornos"]))
            self.chk_usar = QCheckBox("Usar linhas auxiliares")
            self.chk_usar.setChecked(bool(self._cfg["usar_auxiliares"]))
            self.chk_quebrar = QCheckBox("Quebrar linhas auxiliares")
            self.chk_quebrar.setChecked(bool(self._cfg["quebrar_auxiliares"]))
            self.chk_converter = QCheckBox("Converter primitivas em linhas auxiliares")
            self.chk_converter.setChecked(bool(self._cfg["converter_auxiliares"]))
            for chk in (self.chk_grad, self.chk_piques, self.chk_aux, self.chk_compor, self.chk_usar, self.chk_quebrar, self.chk_converter):
                lay.addWidget(chk)

            rod = QHBoxLayout()
            btn_aplicar = QPushButton("Aplicar")
            btn_aplicar.clicked.connect(self._salvar_cfg)
            rod.addStretch(1)
            rod.addWidget(btn_aplicar)
            lay.addLayout(rod)
            lay.addWidget(QLabel(""))
        self._dialog.show()
        self._dialog.raise_()

    def _salvar_cfg(self):
        self._cfg.update(
            {
                "modo": self.cmb_modo.currentText(),
                "detectar_graduacoes": self.chk_grad.isChecked(),
                "detectar_piques": self.chk_piques.isChecked(),
                "detectar_auxiliares": self.chk_aux.isChecked(),
                "compor_contornos": self.chk_compor.isChecked(),
                "usar_auxiliares": self.chk_usar.isChecked(),
                "quebrar_auxiliares": self.chk_quebrar.isChecked(),
                "converter_auxiliares": self.chk_converter.isChecked(),
            }
        )

    def _extrair_metadados(self, pontos: list[QPointF]) -> dict:
        segmentos = [self._dist(a, b) for a, b in zip(pontos, pontos[1:])]
        graduacoes = []
        if self._cfg["detectar_graduacoes"]:
            for i in range(len(segmentos) - 1):
                if abs(segmentos[i] - segmentos[i + 1]) <= 0.35:
                    graduacoes.append({"seg": i, "prox_seg": i + 1, "medida": round((segmentos[i] + segmentos[i + 1]) / 2.0, 2)})
        piques = []
        if self._cfg["detectar_piques"]:
            for i in range(1, len(pontos) - 1):
                ang = self._angulo_interno(pontos[i - 1], pontos[i], pontos[i + 1])
                if ang < 72.0:
                    piques.append({"indice": i, "angulo": round(ang, 1), "ponto": (pontos[i].x(), pontos[i].y())})
        auxiliares = []
        if self._cfg["detectar_auxiliares"]:
            for i, d in enumerate(segmentos):
                if d < 1.8:
                    auxiliares.append(i)
        return {"graduacoes": graduacoes, "piques": piques, "segmentos_auxiliares": auxiliares}

    def _remover_segmentos_auxiliares(self, pontos: list[tuple[float, float]], metadados: dict) -> list[tuple[float, float]]:
        aux = set(metadados.get("segmentos_auxiliares", []))
        if not aux or len(pontos) <= 3:
            return pontos
        saida = [pontos[0]]
        for i in range(1, len(pontos) - 1):
            if (i - 1) in aux:
                continue
            saida.append(pontos[i])
        saida.append(pontos[-1])
        return saida if len(saida) >= 2 else pontos

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return sqrt((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2)

    def _angulo_interno(self, a: QPointF, b: QPointF, c: QPointF) -> float:
        bax, bay = a.x() - b.x(), a.y() - b.y()
        bcx, bcy = c.x() - b.x(), c.y() - b.y()
        na = sqrt((bax * bax) + (bay * bay))
        nb = sqrt((bcx * bcx) + (bcy * bcy))
        if na <= 1e-9 or nb <= 1e-9:
            return 180.0
        cosv = max(-1.0, min(1.0, ((bax * bcx) + (bay * bcy)) / (na * nb)))
        return acos(cosv) * (180.0 / 3.141592653589793)
