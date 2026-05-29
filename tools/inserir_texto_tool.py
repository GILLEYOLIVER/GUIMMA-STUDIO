from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QTextEdit,
    QWidget,
)

from canvas.visualizacao_texto_nativo_patch import aplicar_patch_texto_nativo_canvas
from tools.medicao_utils import mensagem_status
from tools.texto_config import ALTURA_TEXTO_PADRAO_CM, ESPACO_LINHAS_PADRAO_CM, configurar_texto_canvas
from tools.tool_base import FerramentaBase


FONTES_TEXTO = [
    "Arial",
    "Calibri",
    "Times New Roman",
    "Verdana",
    "Tahoma",
    "Georgia",
    "Courier New",
    "Segoe UI",
    "Trebuchet MS",
    "Century Gothic",
    "Consolas",
    "Lucida Sans Unicode",
]


class NumeroLimpoSpinBox(QDoubleSpinBox):
    def __init__(self, parent: QWidget | None = None, sufixo: str = ""):
        super().__init__(parent)
        self._sufixo_limpo = sufixo
        self.setDecimals(2)
        self.setSingleStep(0.1)

    def _formatar_numero(self, value: float) -> str:
        valor = round(float(value), 2)
        texto = f"{valor:.2f}".rstrip("0").rstrip(".")
        if texto.startswith("0.") and valor > 0:
            texto = texto[1:]
        elif texto.startswith("-0."):
            texto = "-" + texto[2:]
        if not texto or texto == "-":
            texto = "0"
        return texto

    def textFromValue(self, value: float) -> str:  # noqa: N802
        texto = self._formatar_numero(value)
        return f"{texto}{self._sufixo_limpo}" if self._sufixo_limpo else texto

    def valueFromText(self, text: str) -> float:  # noqa: N802
        texto = str(text or "").lower().replace("cm", "").replace("°", "").replace("º", "").strip().replace(",", ".")
        if texto.startswith("."):
            texto = "0" + texto
        elif texto.startswith("-."):
            texto = "-0" + texto[1:]
        try:
            return float(texto)
        except Exception:
            return float(self.value())

    def validate(self, text: str, pos: int):  # noqa: N802
        texto = str(text or "").lower().replace("cm", "").replace("°", "").replace("º", "").strip().replace(",", ".")
        if texto in {"", ".", "-", "-."}:
            return QValidator.Intermediate, text, pos
        if texto.startswith("."):
            texto = "0" + texto
        elif texto.startswith("-."):
            texto = "-0" + texto[1:]
        try:
            float(texto)
        except Exception:
            return QValidator.Invalid, text, pos
        return QValidator.Acceptable, text, pos


class MedidaCmSpinBox(NumeroLimpoSpinBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, " cm")


class AnguloSpinBox(NumeroLimpoSpinBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, "°")
        self.setSingleStep(1.0)


class TextoDialog(QDialog):
    def __init__(self, canvas, ferramenta, posicao_previa: QPointF, cor_texto: str, espessura: float, parent: QWidget | None = None):
        super().__init__(parent)
        self.canvas = canvas
        self.ferramenta = ferramenta
        self._posicao_previa = QPointF(posicao_previa)
        self._cor_texto = str(cor_texto or "#ffffff")
        self._espessura = max(1.0, float(espessura or 1.0))
        self._preview_idx: int | None = None
        self._aceito = False
        self._atualizando_estilo_caixa = False
        self._fonte_previa_combo = "Arial"

        self.setWindowTitle("Criar texto")
        self.setModal(True)
        self.resize(560, 390)
        configurar_texto_canvas(canvas)

        self.txt_texto = QTextEdit(self)
        self.txt_texto.setPlainText("Texto")
        self.txt_texto.selectAll()

        self.combo_fonte = QComboBox(self)
        self.combo_fonte.addItems(FONTES_TEXTO)
        fonte_atual = str(getattr(canvas, "_texto_fonte", "Arial") or "Arial")
        self.combo_fonte.setCurrentText(fonte_atual if fonte_atual in FONTES_TEXTO else "Arial")
        self._fonte_previa_combo = self.combo_fonte.currentText() or "Arial"

        self.spin_angulo = AnguloSpinBox(self)
        self.spin_angulo.setRange(-360.0, 360.0)
        self.spin_angulo.setValue(0.0)

        self.spin_altura = MedidaCmSpinBox(self)
        self.spin_altura.setRange(0.2, 200.0)
        self.spin_altura.setValue(float(getattr(canvas, "_texto_altura_cm", ALTURA_TEXTO_PADRAO_CM)))

        self.spin_espaco = MedidaCmSpinBox(self)
        self.spin_espaco.setRange(0.2, 200.0)
        self.spin_espaco.setValue(float(getattr(canvas, "_texto_espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM)))

        self.combo_referencia = QComboBox(self)
        self.combo_referencia.addItems([
            "Topo esquerda", "Topo centro", "Topo direita",
            "Centro esquerda", "Centro centro", "Centro direita",
            "Baixo esquerda", "Baixo centro", "Baixo direita",
        ])
        self.combo_referencia.setCurrentText("Centro centro")

        self.combo_justificacao = QComboBox(self)
        self.combo_justificacao.addItems(["Esquerda", "Centro", "Direita"])
        self.combo_justificacao.setCurrentText("Centro")

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout = QGridLayout(self)
        layout.addWidget(self.txt_texto, 0, 0, 1, 6)
        layout.addWidget(QLabel("Fonte"), 1, 0)
        layout.addWidget(QLabel("Ângulo"), 1, 2)
        layout.addWidget(QLabel("Altura (cm)"), 1, 4)
        layout.addWidget(self.combo_fonte, 2, 0, 1, 2)
        layout.addWidget(self.spin_angulo, 2, 2, 1, 2)
        layout.addWidget(self.spin_altura, 2, 4, 1, 2)
        layout.addWidget(QLabel("Espaço entre linhas (cm)"), 3, 0)
        layout.addWidget(QLabel("Referência"), 3, 2)
        layout.addWidget(QLabel("Justificação"), 3, 4)
        layout.addWidget(self.spin_espaco, 4, 0, 1, 2)
        layout.addWidget(self.combo_referencia, 4, 2, 1, 2)
        layout.addWidget(self.combo_justificacao, 4, 4, 1, 2)
        layout.addWidget(botoes, 5, 0, 1, 6)
        layout.setRowStretch(0, 1)

        self.txt_texto.textChanged.connect(self._atualizar_previa_ao_vivo)
        self.combo_fonte.currentTextChanged.connect(self._fonte_alterada)
        try:
            self.combo_fonte.textHighlighted.connect(self._fonte_destacada)
        except Exception:
            try:
                self.combo_fonte.highlighted.connect(self._fonte_destacada_indice)
            except Exception:
                pass
        self.combo_referencia.currentTextChanged.connect(self._atualizar_previa_ao_vivo)
        self.combo_justificacao.currentTextChanged.connect(self._atualizar_previa_ao_vivo)
        self.spin_angulo.valueChanged.connect(self._atualizar_previa_ao_vivo)
        self.spin_altura.valueChanged.connect(self._atualizar_previa_ao_vivo)
        self.spin_espaco.valueChanged.connect(self._atualizar_previa_ao_vivo)

        self._aplicar_fonte_na_caixa()
        QTimer.singleShot(0, self._atualizar_previa_ao_vivo)

    def _fonte_em_uso(self) -> str:
        return str(self._fonte_previa_combo or self.combo_fonte.currentText() or "Arial")

    def valores(self) -> dict:
        return {
            "texto": self.txt_texto.toPlainText(),
            "fonte_texto": self._fonte_em_uso(),
            "angulo": float(self.spin_angulo.value()),
            "altura_cm": float(self.spin_altura.value()),
            "espaco_linhas_cm": float(self.spin_espaco.value()),
            "referencia": self.combo_referencia.currentText(),
            "justificacao": self.combo_justificacao.currentText(),
        }

    def indice_previa(self) -> int | None:
        if self._preview_idx is None:
            return None
        try:
            idx = int(self._preview_idx)
            if 0 <= idx < len(self.canvas.cena.elementos):
                el = self.canvas.cena.elementos[idx]
                if isinstance(el, dict) and str(el.get("tipo") or "").lower() == "texto":
                    return idx
        except Exception:
            pass
        return None

    def _fonte_alterada(self, fonte: str | None = None):
        self._fonte_previa_combo = str(fonte or self.combo_fonte.currentText() or "Arial")
        self._aplicar_fonte_na_caixa(self._fonte_previa_combo)
        self._atualizar_previa_ao_vivo()

    def _fonte_destacada(self, fonte: str):
        self._fonte_previa_combo = str(fonte or self.combo_fonte.currentText() or "Arial")
        self._aplicar_fonte_na_caixa(self._fonte_previa_combo)
        self._atualizar_previa_ao_vivo()

    def _fonte_destacada_indice(self, indice: int):
        if 0 <= int(indice) < self.combo_fonte.count():
            self._fonte_destacada(self.combo_fonte.itemText(int(indice)))

    def _aplicar_fonte_na_caixa(self, fonte: str | None = None):
        if self._atualizando_estilo_caixa:
            return
        self._atualizando_estilo_caixa = True
        try:
            fonte_final = str(fonte or self._fonte_em_uso() or "Arial")
            self.txt_texto.setStyleSheet(f'QTextEdit {{ font-family: "{fonte_final}"; font-size: 12pt; }}')
        finally:
            self._atualizando_estilo_caixa = False

    def _atualizar_previa_ao_vivo(self):
        texto = self.txt_texto.toPlainText().strip("\n")
        if not texto.strip():
            self._remover_previa()
            return
        valores = self.valores()
        elemento = self.ferramenta._criar_elemento_texto_nativo(self.canvas, valores, self._posicao_previa, self._cor_texto)
        if elemento is None:
            self._remover_previa()
            return
        elemento["__texto_previa_ao_vivo"] = True
        elemento["texto_espessura"] = self._espessura
        elemento["espessura"] = self._espessura
        idx = self.indice_previa()
        if idx is None:
            self.canvas.cena.elementos.append(elemento)
            idx = len(self.canvas.cena.elementos) - 1
            self._preview_idx = idx
        else:
            pos_atual = self.canvas.cena.elementos[idx].get("posicao")
            if pos_atual:
                elemento["posicao"] = pos_atual
                elemento["ponto"] = pos_atual
                elemento["origem"] = pos_atual
            self.canvas.cena.elementos[idx] = elemento
        self.canvas._selecionados = {idx}
        self.canvas.update()

    def _remover_previa(self):
        idx = self.indice_previa()
        if idx is not None:
            try:
                self.canvas.cena.elementos.pop(idx)
            except Exception:
                pass
        self._preview_idx = None
        try:
            self.canvas._selecionados.clear()
        except Exception:
            pass
        self.canvas.update()

    def accept(self):
        self._fonte_previa_combo = self.combo_fonte.currentText() or self._fonte_previa_combo or "Arial"
        self._atualizar_previa_ao_vivo()
        self._aceito = True
        super().accept()

    def reject(self):
        self._aceito = False
        self._remover_previa()
        super().reject()

    def closeEvent(self, event):
        if not self._aceito:
            self._remover_previa()
        super().closeEvent(event)


class Ferramenta(FerramentaBase):
    id_ferramenta = "inserir_texto"
    nome = "Inserir Texto"
    descricao_painel = ""
    usa_painel_auxiliar = False
    gerencia_coordenadas_operacao = True

    def __init__(self):
        super().__init__()
        self._dialogo_aberto = False

    def on_activate(self, canvas):
        configurar_texto_canvas(canvas)
        aplicar_patch_texto_nativo_canvas()
        self._dialogo_aberto = False
        QTimer.singleShot(0, lambda: self._abrir_dialogo_e_inserir(canvas))

    def on_deactivate(self, canvas):
        self._dialogo_aberto = False
        return None

    def _abrir_dialogo_e_inserir(self, canvas, forcar: bool = False) -> None:
        agora = monotonic()
        if getattr(canvas, "_inserir_texto_dialogo_ativo", False):
            return
        if not forcar and agora - float(getattr(canvas, "_inserir_texto_ultima_abertura", 0.0) or 0.0) < 0.8:
            return

        self._dialogo_aberto = True
        canvas._inserir_texto_dialogo_ativo = True
        canvas._inserir_texto_ultima_abertura = agora
        try:
            cor_texto = self._cor_atual_para_texto(canvas)
            cor_fundo = self._cor_fundo_canvas(canvas)
            espessura = self._espessura_atual_texto(canvas)
            dlg = TextoDialog(canvas, self, self._centro_canvas(canvas), cor_texto, espessura, canvas)
            if dlg.exec() == QDialog.Accepted:
                idx = dlg.indice_previa()
                if self._cores_iguais_ou_muito_parecidas(cor_texto, cor_fundo):
                    dlg._remover_previa()
                    self._alertar_cor_invisivel(canvas, cor_texto, cor_fundo)
                    texto = "Texto não inserido: cor igual ou muito parecida com o fundo."
                elif idx is not None:
                    canvas.cena.elementos[idx].pop("__texto_previa_ao_vivo", None)
                    canvas._selecionados = {idx}
                    canvas._texto_em_maos_idx = idx
                    canvas._texto_em_maos_cancelavel = True
                    canvas._texto_fonte = dlg.valores().get("fonte_texto") or "Arial"
                    texto = "Texto em mãos: mova o mouse para posicionar, clique esquerdo para soltar ou direito para cancelar."
                else:
                    texto = "Inserir Texto: nenhum texto informado."
            else:
                texto = "Inserir Texto cancelado."
        finally:
            self._dialogo_aberto = False
            canvas._inserir_texto_dialogo_ativo = False
            canvas._inserir_texto_ultima_abertura = monotonic()

        self.set_status(texto)
        mensagem_status(canvas, texto)
        canvas.update()

    def _centro_canvas(self, canvas) -> QPointF:
        try:
            return canvas._tela_para_cena(QPointF(float(canvas.width()) / 2.0, float(canvas.height()) / 2.0))
        except Exception:
            return QPointF(0.0, 0.0)

    def _cor_valida(self, valor, fallback: str = "#ffffff") -> QColor:
        cor = QColor(str(valor or ""))
        return cor if cor.isValid() else QColor(fallback)

    def _cor_fundo_canvas(self, canvas) -> str:
        candidatos: list[object] = []
        cores_canvas = getattr(canvas, "_cores_canvas", None)
        if isinstance(cores_canvas, dict):
            candidatos.append(cores_canvas.get("fundo"))
        janela = None
        try:
            janela = canvas.window()
        except Exception:
            janela = None
        if janela is not None:
            cores_global = getattr(janela, "_cores_canvas_global", None)
            if isinstance(cores_global, dict):
                candidatos.append(cores_global.get("fundo"))
        candidatos.append("#000000")
        for valor in candidatos:
            cor = QColor(str(valor or ""))
            if cor.isValid():
                return cor.name()
        return "#000000"

    def _cores_iguais_ou_muito_parecidas(self, cor_a: str, cor_b: str) -> bool:
        a = self._cor_valida(cor_a, "#ffffff")
        b = self._cor_valida(cor_b, "#000000")
        distancia = abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
        return distancia <= 45

    def _alertar_cor_invisivel(self, canvas, cor_texto: str, cor_fundo: str) -> None:
        QMessageBox.warning(
            canvas,
            "Cor do texto invisível",
            "A cor escolhida para o texto está igual ou muito parecida com a cor do fundo do canvas.\n\n"
            f"Cor do texto: {cor_texto}\nCor do fundo: {cor_fundo}\n\n"
            "Escolha outra cor em Cor antes de inserir o texto.",
        )

    def _controles_cor(self, janela) -> list[QWidget]:
        try:
            widgets = list(janela.findChildren(QWidget))
        except Exception:
            return []
        return [w for w in widgets if w.__class__.__name__ == "ColorControlWidget" and hasattr(w, "valor")]

    def _cores_dos_controles_cor(self, janela) -> list[str]:
        cores: list[str] = []
        controles = self._controles_cor(janela)
        controles.sort(key=lambda w: 0 if (w.isVisible() and not w.isHidden()) else 1)
        for widget in controles:
            try:
                valor = widget.valor()
                if isinstance(valor, dict):
                    cor = QColor(str(valor.get("cor") or ""))
                    if cor.isValid():
                        cores.append(cor.name())
            except Exception:
                pass
        return cores

    def _espessura_atual_texto(self, canvas) -> float:
        candidatos: list[object] = []
        janela = None
        try:
            janela = canvas.window()
        except Exception:
            janela = None
        if janela is not None:
            for widget in self._controles_cor(janela):
                try:
                    valor = widget.valor()
                    if isinstance(valor, dict):
                        candidatos.append(valor.get("espessura"))
                except Exception:
                    pass
            estilo_janela = getattr(janela, "_estilo_desenho_atual", None)
            if isinstance(estilo_janela, dict):
                candidatos.append(estilo_janela.get("espessura"))
        candidatos.append(getattr(canvas, "_linha_espessura", None))
        for valor in candidatos:
            try:
                return max(1.0, float(valor))
            except Exception:
                continue
        return 1.0

    def _cor_atual_para_texto(self, canvas) -> str:
        candidatos: list[object] = []
        janela = None
        try:
            janela = canvas.window()
        except Exception:
            janela = None
        if janela is not None:
            candidatos.extend(self._cores_dos_controles_cor(janela))
        candidatos.append(getattr(canvas, "_linha_cor", None))
        if janela is not None:
            estilo_janela = getattr(janela, "_estilo_desenho_atual", None)
            if isinstance(estilo_janela, dict):
                candidatos.append(estilo_janela.get("cor"))
        cores_canvas = getattr(canvas, "_cores_canvas", None)
        if isinstance(cores_canvas, dict):
            candidatos.append(cores_canvas.get("desenho"))
        for valor in candidatos:
            cor = QColor(str(valor or ""))
            if cor.isValid():
                return cor.name()
        return "#ffffff"

    def _criar_elemento_texto_nativo(self, canvas, valores: dict, pos: QPointF, cor: str) -> dict | None:
        texto = str(valores.get("texto") or "").strip("\n")
        if not texto.strip():
            return None
        espessura = self._espessura_atual_texto(canvas)
        try:
            canvas._linha_cor = cor
            canvas._linha_espessura = espessura
        except Exception:
            pass
        return {
            "tipo": "texto",
            "texto": texto,
            "fonte_texto": str(valores.get("fonte_texto") or "Arial"),
            "fonte": str(valores.get("fonte_texto") or "Arial"),
            "posicao": (float(pos.x()), float(pos.y())),
            "ponto": (float(pos.x()), float(pos.y())),
            "origem": (float(pos.x()), float(pos.y())),
            "angulo": float(valores.get("angulo", 0.0) or 0.0),
            "texto_altura_cm": float(valores.get("altura_cm", ALTURA_TEXTO_PADRAO_CM) or ALTURA_TEXTO_PADRAO_CM),
            "texto_espaco_linhas_cm": float(valores.get("espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM) or ESPACO_LINHAS_PADRAO_CM),
            "texto_espessura": espessura,
            "referencia": str(valores.get("referencia") or "Centro centro"),
            "justificacao": str(valores.get("justificacao") or "Centro"),
            "cor": cor,
            "cor_texto": cor,
        }

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        self._abrir_dialogo_e_inserir(canvas, forcar=True)
        event.accept()
        return True
