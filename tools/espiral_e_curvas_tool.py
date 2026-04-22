from __future__ import annotations

from math import cos, pi, sin

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from tools.tool_base import FerramentaBase


class InserirCurvaDialog(QDialog):
    OPCOES = [
        "Spiral",
        "Curva Francesa 1",
        "Curva Francesa 2",
        "Curva Francesa 3",
        "Curva Francesa 4",
        "Manga - cava frente",
        "Cava costas",
        "Gancho calça",
        "Lado saia",
        "Decote",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inserir curva")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(True)
        self.setFixedWidth(245)
        self._montar_ui()

    def _montar_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)

        self.cmb_curva = QComboBox()
        self.cmb_curva.addItems(self.OPCOES)
        self.cmb_curva.setCurrentText("Spiral")
        self.chk_criar_molde = QCheckBox("Criar moldes")
        self.sp_largura = QSpinBox()
        self.sp_largura.setRange(1, 9999)
        self.sp_largura.setValue(5)
        self.sp_perimetro = QSpinBox()
        self.sp_perimetro.setRange(1, 9999)
        self.sp_perimetro.setValue(60)

        form.addRow("Curva pré-definida", self.cmb_curva)
        form.addRow("", self.chk_criar_molde)
        form.addRow("Largura (cm)", self.sp_largura)
        form.addRow("Perímetro (cm)", self.sp_perimetro)
        lay.addLayout(form)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)

    def gerar_pontos(self) -> tuple[list[QPointF], bool]:
        largura = float(self.sp_largura.value())
        perimetro = float(self.sp_perimetro.value())
        nome = self.cmb_curva.currentText()
        if nome == "Spiral":
            pontos = _gerar_espiral(largura=largura, perimetro=perimetro)
        else:
            pontos = _gerar_curva_predefinida(nome=nome, largura=largura, perimetro=perimetro)
        return pontos, self.chk_criar_molde.isChecked()


def _gerar_espiral(largura: float, perimetro: float) -> list[QPointF]:
    raio_max = max(0.4, largura / 2.0)
    voltas = max(1.4, min(4.2, perimetro / max(largura * 3.2, 0.01)))
    segmentos = int(max(48, min(280, voltas * 70)))
    pts: list[QPointF] = []
    for i in range(segmentos + 1):
        t = i / max(segmentos, 1)
        ang = (2.0 * pi * voltas * t) - (pi / 2.0)
        raio = raio_max * t
        pts.append(QPointF(cos(ang) * raio, sin(ang) * raio))
    return pts


def _gerar_curva_predefinida(nome: str, largura: float, perimetro: float) -> list[QPointF]:
    w = max(1.0, largura)
    h = max(1.0, perimetro / 10.0)
    perfis = {
        "Curva Francesa 1": [(0.0, 0.0), (0.25, -0.05), (0.45, -0.2), (0.7, -0.62), (1.0, -1.0)],
        "Curva Francesa 2": [(0.0, 0.0), (0.2, -0.15), (0.4, -0.45), (0.7, -0.85), (1.0, -1.0)],
        "Curva Francesa 3": [(0.0, 0.0), (0.2, 0.05), (0.4, -0.2), (0.75, -0.8), (1.0, -1.0)],
        "Curva Francesa 4": [(0.0, 0.0), (0.18, -0.28), (0.35, -0.52), (0.66, -0.9), (1.0, -1.0)],
        "Manga - cava frente": [(0.0, 0.0), (0.18, -0.1), (0.4, -0.55), (0.72, -0.84), (1.0, -1.0)],
        "Cava costas": [(0.0, 0.0), (0.15, -0.08), (0.36, -0.42), (0.68, -0.8), (1.0, -1.0)],
        "Gancho calça": [(0.0, 0.0), (0.12, -0.12), (0.32, -0.5), (0.58, -0.9), (1.0, -1.0)],
        "Lado saia": [(0.0, 0.0), (0.18, -0.04), (0.45, -0.3), (0.78, -0.75), (1.0, -1.0)],
        "Decote": [(0.0, 0.0), (0.2, -0.22), (0.42, -0.58), (0.72, -0.86), (1.0, -1.0)],
    }
    base = perfis.get(nome, perfis["Curva Francesa 1"])
    pts: list[QPointF] = []
    for nx, ny in base:
        x = (nx - 0.5) * w
        y = (ny + 0.5) * h
        pts.append(QPointF(x, y))
    # Suaviza com interpolação linear para evitar poucos pontos.
    suavizada: list[QPointF] = []
    for a, b in zip(pts, pts[1:]):
        if not suavizada:
            suavizada.append(a)
        subdiv = 10
        for i in range(1, subdiv + 1):
            t = i / subdiv
            suavizada.append(QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t)))
    return suavizada


class Ferramenta(FerramentaBase):
    id_ferramenta = "espiral_e_curvas"
    nome = "Espiral e Curvas"
    descricao_painel = "Insere curvas pré-definidas (espiral, curvas francesas, cava, gancho, decote)."

    def on_activate(self, canvas):
        super().on_activate(canvas)
        dialog = InserirCurvaDialog(canvas.window() if hasattr(canvas, "window") else canvas)
        if dialog.exec() != QDialog.Accepted:
            self.set_status("Inserção de curva cancelada.")
            return
        pontos, criar_molde = dialog.gerar_pontos()
        if len(pontos) < 2:
            self.set_status("Não foi possível gerar a curva selecionada.")
            return

        centro = QPointF(
            canvas.origem_cena.x() + (canvas.width() / max(canvas.zoom, 0.001) / 2.0),
            canvas.origem_cena.y() + (canvas.height() / max(canvas.zoom, 0.001) / 2.0),
        )
        pontos_cena = [(centro.x() + p.x(), centro.y() + p.y()) for p in pontos]
        canvas.cena.elementos.append(
            {
                "tipo": "polyline",
                "pontos": pontos_cena,
                "cor": getattr(canvas, "_linha_cor", "#ffffff"),
                "espessura": float(getattr(canvas, "_linha_espessura", 1.0)),
                "estilo": str(getattr(canvas, "_linha_estilo", "solid")),
                "amplitude": float(getattr(canvas, "_linha_amplitude", 1.0)),
                "fase_inicio": 0.0,
                "molde": bool(criar_molde),
            }
        )
        canvas._registrar_historico()
        canvas.update()
        self.set_status(f"Curva \"{dialog.cmb_curva.currentText()}\" inserida.")
