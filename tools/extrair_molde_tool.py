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
    descricao_painel = "Automático: LMB seleciona, RMB extrai, LMB cria. Manual: LMB marca partes."

    def __init__(self):
        super().__init__()
        self._dialog: QDialog | None = None
        self._idx_selecionado: int | None = None
        self._selecoes_manuais: set[int] = set()
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
        self._selecoes_manuais.clear()
        self._contorno_extraido = None
        self._molde_criado = False
        self._abrir_config(canvas)
        self.set_status("Defina modo e siga: LMB seleciona | RMB extrai | LMB cria molde")

    def on_deactivate(self, canvas):
        if self._dialog:
            self._dialog.hide()
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contorno_extraido = None
        self._molde_criado = False

    def on_mouse_press(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        modo_manual = self._cfg.get("modo") == "Manual"

        if event.button() == Qt.LeftButton:
            if self._contorno_extraido and not self._molde_criado:
                ok = self._criar_molde(canvas)
                self.set_status("Molde criado com sucesso." if ok else "Falha ao criar molde.")
                canvas.update()
                event.accept()
                return ok

            candidatos = canvas._indices_elementos_em_ponto(pos)
            if not candidatos:
                candidatos = self._indices_polylines_contem_ponto(canvas, pos)
            if not candidatos and canvas._selecionados:
                candidatos = sorted(
                    [idx for idx in canvas._selecionados if 0 <= idx < len(canvas.cena.elementos) and canvas.cena.elementos[idx].get("tipo") == "polyline"],
                    reverse=True,
                )
            if not candidatos:
                self.set_status("Clique na borda ou dentro do contorno (ou pré-selecione) para continuar.")
                return False
            idx = candidatos[0]
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                self.set_status("Selecione polyline para extrair molde.")
                return False

            if modo_manual:
                if idx in self._selecoes_manuais:
                    self._selecoes_manuais.remove(idx)
                else:
                    self._selecoes_manuais.add(idx)
                canvas._selecionados = set(self._selecoes_manuais)
                self._idx_selecionado = next(iter(self._selecoes_manuais), None)
                self._contorno_extraido = None
                self._molde_criado = False
                self.set_status(f"Manual: {len(self._selecoes_manuais)} parte(s) selecionada(s). RMB para extrair.")
                canvas.update()
                event.accept()
                return True

            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if not self._eh_fechado(pontos):
                self.set_status("Contorno está aberto. Feche-o antes de extrair.")
                return False
            self._idx_selecionado = idx
            self._selecoes_manuais = {idx}
            canvas._selecionados = {idx}
            self._contorno_extraido = None
            self._molde_criado = False
            self.set_status("Contorno selecionado. RMB para extrair traçado exato.")
            canvas.update()
            event.accept()
            return True

        if event.button() != Qt.RightButton:
            return False

        if modo_manual:
            if not self._selecoes_manuais:
                self.set_status("Manual: selecione partes com LMB antes de extrair.")
                return False
            idx = next(iter(self._selecoes_manuais))
            el = canvas.cena.elementos[idx]
            self._idx_selecionado = idx
            self._contorno_extraido = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            self._molde_criado = False
            self.set_status("Manual: extração pronta. LMB para criar molde(s).")
            canvas.update()
            event.accept()
            return True

        if self._idx_selecionado is None:
            self.set_status("Selecione um contorno fechado antes de extrair.")
            return False
        el = canvas.cena.elementos[self._idx_selecionado]
        self._contorno_extraido = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        metadados = self._extrair_metadados(self._contorno_extraido)
        el["extracao_molde"] = metadados
        if self._cfg["quebrar_auxiliares"]:
            el["pontos"] = self._remover_segmentos_auxiliares([(p.x(), p.y()) for p in self._contorno_extraido], metadados)
            self._contorno_extraido = [QPointF(float(x), float(y)) for x, y in el["pontos"]]
        self._molde_criado = False
        canvas._registrar_historico()
        self.set_status("Traçado extraído. LMB para criar molde.")
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter: QPainter):
        for idx in self._selecoes_manuais:
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                if el.get("tipo") == "polyline":
                    pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                    self._desenhar_contorno(canvas, painter, pts, QColor("#ff2fff"), 2.0)
        if self._contorno_extraido:
            self._desenhar_contorno(canvas, painter, self._contorno_extraido, QColor("#ff2a2a"), 2.0)
        if self._molde_criado and self._idx_selecionado is not None and 0 <= self._idx_selecionado < len(canvas.cena.elementos):
            self._desenhar_controles_molde(canvas, painter, canvas.cena.elementos[self._idx_selecionado])

    def _desenhar_contorno(self, canvas, painter, pontos: list[QPointF], cor: QColor, esp: float):
        if len(pontos) < 2:
            return
        for a, b in zip(pontos, pontos[1:]):
            canvas._desenhar_segmento(painter, a, b, cor=cor.name(), espessura=esp)

    def _indices_polylines_contem_ponto(self, canvas, pos: QPointF) -> list[int]:
        candidatos: list[int] = []
        for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 3:
                continue
            if not self._eh_fechado(pontos):
                continue
            if self._ponto_dentro_poligono(pos, pontos):
                candidatos.append(idx)
        return candidatos

    def _ponto_dentro_poligono(self, pt: QPointF, pontos: list[QPointF]) -> bool:
        poligono = pontos if pontos and self._dist(pontos[0], pontos[-1]) <= 0.001 else [*pontos, pontos[0]]
        inside = False
        j = len(poligono) - 1
        x = pt.x()
        y = pt.y()
        for i in range(len(poligono)):
            xi, yi = poligono[i].x(), poligono[i].y()
            xj, yj = poligono[j].x(), poligono[j].y()
            intercepta = ((yi > y) != (yj > y)) and (x < ((xj - xi) * (y - yi) / max((yj - yi), 1e-12)) + xi)
            if intercepta:
                inside = not inside
            j = i
        return inside

    def _criar_molde(self, canvas) -> bool:
        if not self._selecoes_manuais:
            return False
        idxs = sorted(self._selecoes_manuais)
        criou = False
        for idx in idxs:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if not self._eh_fechado(pontos):
                pontos.append(QPointF(pontos[0]))
                el["pontos"] = [(p.x(), p.y()) for p in pontos]
            principais = self._ordenar_principais_horario(pontos[:-1])
            auxiliares = []
            for i in range(len(principais)):
                a = principais[i]
                b = principais[(i + 1) % len(principais)]
                aux = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
                auxiliares.append({"x": aux.x(), "y": aux.y(), "oculto": True})

            el["molde"] = True
            el["nome_molde"] = self._proximo_nome_molde(canvas)
            el["controle_cantos"] = [(p.x(), p.y()) for p in principais]
            el["pontos_controle_principais"] = [{"indice": i + 1, "x": p.x(), "y": p.y()} for i, p in enumerate(principais)]
            el["pontos_auxiliares"] = auxiliares
            criou = True
        self._molde_criado = criou
        if criou:
            canvas._registrar_historico()
        return criou

    def _proximo_nome_molde(self, canvas) -> str:
        maior = 0
        for el in canvas.cena.elementos:
            nome = str(el.get("nome_molde", ""))
            if nome.startswith("K") and nome[1:].isdigit():
                maior = max(maior, int(nome[1:]))
        return f"K{maior + 1}"

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
