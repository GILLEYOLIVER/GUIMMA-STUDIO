from __future__ import annotations

from math import acos, sqrt

from PySide6.QtCore import QPointF, Qt
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
    descricao_painel = "Extrai metadados de molde: graduação, piques e linhas auxiliares."

    def __init__(self):
        super().__init__()
        self._dialog: QDialog | None = None
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
        self._abrir_config(canvas)
        self.set_status("Configuração pronta. Clique no molde/contorno para extrair dados.")

    def on_deactivate(self, canvas):
        if self._dialog:
            self._dialog.hide()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        candidatos = canvas._indices_elementos_em_ponto(pos)
        if candidatos:
            canvas._selecionados = {candidatos[0]}
        if not canvas._selecionados:
            self.set_status("Selecione um contorno para extrair molde.")
            return False
        alterou = False
        for idx in sorted(canvas._selecionados):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 3:
                continue
            metadados = self._extrair_metadados(pontos)
            el["molde"] = True
            el["extracao_molde"] = metadados
            if self._cfg["compor_contornos"] and pontos[0] != pontos[-1]:
                pontos.append(QPointF(pontos[0]))
                el["pontos"] = [(p.x(), p.y()) for p in pontos]
            if self._cfg["quebrar_auxiliares"]:
                el["pontos"] = self._remover_segmentos_auxiliares([(p.x(), p.y()) for p in pontos], metadados)
            alterou = True
        if alterou:
            canvas._registrar_historico()
            canvas.update()
            self.set_status("Extração concluída: graduação/piques detectados.")
            event.accept()
            return True
        self.set_status("Nada extraído para a seleção atual.")
        return False

    def _abrir_config(self, canvas):
        if self._dialog is None:
            self._dialog = QDialog(canvas)
            self._dialog.setWindowTitle("Definir contorno")
            self._dialog.setWindowFlags(Qt.Tool)
            self._dialog.setModal(False)
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
