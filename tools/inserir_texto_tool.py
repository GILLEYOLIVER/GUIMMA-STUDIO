from __future__ import annotations

from copy import deepcopy
from time import monotonic

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QValidator
from PySide6.QtWidgets import (
    QApplication,
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
from core.formatacao import formatar_numero, normalizar_decimal_ponto, numero_decimal_ponto
from tools.medicao_utils import mensagem_status
from tools.texto_config import ALTURA_TEXTO_PADRAO_CM, ESPACO_LINHAS_PADRAO_CM, configurar_texto_canvas
from tools.tool_base import FerramentaBase
from tools.unidades import SUFIXOS_MEDIDA, unidade_canvas, valor_cena_para_unidade, valor_unidade_para_cena


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
        texto = formatar_numero(valor, 2)
        if not texto or texto == "-":
            texto = "0"
        return texto

    def textFromValue(self, value: float) -> str:  # noqa: N802
        texto = self._formatar_numero(value)
        return f"{texto}{self._sufixo_limpo}" if self._sufixo_limpo else texto

    def valueFromText(self, text: str) -> float:  # noqa: N802
        return numero_decimal_ponto(str(text or "").lower(), float(self.value()), SUFIXOS_MEDIDA + ("°", "º"))

    def validate(self, text: str, pos: int):  # noqa: N802
        try:
            texto = normalizar_decimal_ponto(str(text or "").lower(), SUFIXOS_MEDIDA + ("°", "º"))
        except Exception:
            return QValidator.Invalid, text, pos
        if texto in {"", "+", "-", "0.", "+0.", "-0."}:
            return QValidator.Intermediate, text, pos
        try:
            float(texto)
        except Exception:
            return QValidator.Invalid, text, pos
        return QValidator.Acceptable, text, pos


class MedidaCmSpinBox(NumeroLimpoSpinBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, " cm")

    def set_unidade(self, sigla: str) -> None:
        self._sufixo_limpo = f" {str(sigla or 'cm')}"
        self.lineEdit().setPlaceholderText(str(sigla or "cm"))


class AnguloSpinBox(NumeroLimpoSpinBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, "°")
        self.setSingleStep(1.0)


class TextoDialog(QDialog):
    def __init__(self, canvas, ferramenta, parent: QWidget | None = None):
        super().__init__(parent)
        self.canvas = canvas
        self.ferramenta = ferramenta
        self._unidade_sigla, self._unidade_fator = unidade_canvas(canvas)
        self._fechando_por_codigo = False
        self._atualizando_estilo_caixa = False
        self._fonte_previa_combo = "Arial"

        self.setWindowTitle("Criar texto")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFocusPolicy(Qt.StrongFocus)  # Mantém o foco no diálogo
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
        self.spin_altura.set_unidade(self._unidade_sigla)
        self.spin_altura.setValue(valor_cena_para_unidade(canvas, float(getattr(canvas, "_texto_altura_cm", ALTURA_TEXTO_PADRAO_CM))))

        self.spin_espaco = MedidaCmSpinBox(self)
        self.spin_espaco.setRange(0.2, 200.0)
        self.spin_espaco.set_unidade(self._unidade_sigla)
        self.spin_espaco.setValue(valor_cena_para_unidade(canvas, float(getattr(canvas, "_texto_espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM))))

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
        self.lbl_altura = QLabel(f"Altura ({self._unidade_sigla})")
        self.lbl_espaco = QLabel(f"Espaço entre linhas ({self._unidade_sigla})")
        layout.addWidget(self.lbl_altura, 1, 4)
        layout.addWidget(self.combo_fonte, 2, 0, 1, 2)
        layout.addWidget(self.spin_angulo, 2, 2, 1, 2)
        layout.addWidget(self.spin_altura, 2, 4, 1, 2)
        layout.addWidget(self.lbl_espaco, 3, 0)
        layout.addWidget(QLabel("Referência"), 3, 2)
        layout.addWidget(QLabel("Justificação"), 3, 4)
        layout.addWidget(self.spin_espaco, 4, 0, 1, 2)
        layout.addWidget(self.combo_referencia, 4, 2, 1, 2)
        layout.addWidget(self.combo_justificacao, 4, 4, 1, 2)
        layout.addWidget(botoes, 5, 0, 1, 6)
        layout.setRowStretch(0, 1)

        self.txt_texto.textChanged.connect(self._alterou_configuracao)
        self.combo_fonte.currentTextChanged.connect(self._fonte_alterada)
        try:
            self.combo_fonte.textHighlighted.connect(self._fonte_destacada)
        except Exception:
            try:
                self.combo_fonte.highlighted.connect(self._fonte_destacada_indice)
            except Exception:
                pass
        self.combo_referencia.currentTextChanged.connect(self._alterou_configuracao)
        self.combo_justificacao.currentTextChanged.connect(self._alterou_configuracao)
        self.spin_angulo.valueChanged.connect(self._alterou_configuracao)
        self.spin_altura.valueChanged.connect(self._alterou_configuracao)
        self.spin_espaco.valueChanged.connect(self._alterou_configuracao)

        self._aplicar_fonte_na_caixa()

    def _fonte_em_uso(self) -> str:
        return str(self._fonte_previa_combo or self.combo_fonte.currentText() or "Arial")

    def valores(self) -> dict:
        return {
            "texto": self.txt_texto.toPlainText(),
            "fonte_texto": self._fonte_em_uso(),
            "angulo": float(self.spin_angulo.value()),
            "altura_cm": valor_unidade_para_cena(self.canvas, float(self.spin_altura.value())),
            "espaco_linhas_cm": valor_unidade_para_cena(self.canvas, float(self.spin_espaco.value())),
            "referencia": self.combo_referencia.currentText(),
            "justificacao": self.combo_justificacao.currentText(),
        }

    def set_unidade(self, sigla: str, fator: float) -> None:
        fator_antigo = max(1e-9, float(getattr(self, "_unidade_fator", 1.0)))
        altura_cena = float(self.spin_altura.value()) * fator_antigo
        espaco_cena = float(self.spin_espaco.value()) * fator_antigo
        self._unidade_sigla = str(sigla or "cm")
        self._unidade_fator = max(1e-9, float(fator or 1.0))
        self.spin_altura.set_unidade(self._unidade_sigla)
        self.spin_espaco.set_unidade(self._unidade_sigla)
        self.lbl_altura.setText(f"Altura ({self._unidade_sigla})")
        self.lbl_espaco.setText(f"Espaço entre linhas ({self._unidade_sigla})")
        self.spin_altura.blockSignals(True)
        self.spin_espaco.blockSignals(True)
        try:
            self.spin_altura.setValue(float(altura_cena) / self._unidade_fator)
            self.spin_espaco.setValue(float(espaco_cena) / self._unidade_fator)
        finally:
            self.spin_altura.blockSignals(False)
            self.spin_espaco.blockSignals(False)

    def _fonte_alterada(self, fonte: str | None = None):
        self._fonte_previa_combo = str(fonte or self.combo_fonte.currentText() or "Arial")
        self._aplicar_fonte_na_caixa(self._fonte_previa_combo)
        self._alterou_configuracao()

    def _fonte_destacada(self, fonte: str):
        self._fonte_previa_combo = str(fonte or self.combo_fonte.currentText() or "Arial")
        self._aplicar_fonte_na_caixa(self._fonte_previa_combo)
        self._alterou_configuracao()

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

    def _alterou_configuracao(self, *args):
        self.ferramenta._dialogo_alterado(self.canvas)

    def accept(self):
        self._fechando_por_codigo = True
        self.ferramenta._ok_dialogo_fecha_mantendo_texto_na_mao(self.canvas)
        super().accept()

    def reject(self):
        self._fechando_por_codigo = True
        self.ferramenta._cancelar_tudo(self.canvas)
        super().reject()

    def closeEvent(self, event):
        if not self._fechando_por_codigo:
            self.ferramenta._cancelar_tudo(self.canvas)
        super().closeEvent(event)


class _EventFilter(QObject):
    """Filtro de eventos auxiliar para manter o foco no diálogo."""
    def __init__(self, ferramenta):
        super().__init__()
        self.ferramenta = ferramenta

    def eventFilter(self, obj, event):
        return self.ferramenta._event_filter(obj, event)


class Ferramenta(FerramentaBase):
    id_ferramenta = "inserir_texto"
    nome = "Inserir Texto"
    descricao_painel = ""
    usa_painel_auxiliar = False
    gerencia_coordenadas_operacao = True

    _dialog_por_canvas: dict[int, TextoDialog] = {}
    _preview_idx_por_canvas: dict[int, int] = {}
    _cursor_por_canvas: dict[int, QPointF] = {}
    _timer_por_canvas: dict[int, QTimer] = {}
    _valores_pos_ok_por_canvas: dict[int, dict] = {}
    _modo_pos_ok_por_canvas: dict[int, bool] = {}
    _ultima_abertura_por_canvas: dict[int, float] = {}
    _event_filter_instalado = False
    _event_filter_obj = None

    def __init__(self):
        super().__init__()
        self._dialogo_aberto = False

    def _forcar_foco_dialogo(self):
        """Força o foco para o diálogo de texto ativo."""
        for dialog in self._dialog_por_canvas.values():
            if dialog and not dialog.isHidden():
                dialog.raise_()
                dialog.activateWindow()
                dialog.txt_texto.setFocus(Qt.OtherFocusReason)
                return

    def _event_filter(self, obj, event):
        """Filtro global para manter o foco no diálogo."""
        if not any(dlg and not dlg.isHidden() for dlg in self._dialog_por_canvas.values()):
            return False
        if event.type() == QEvent.FocusIn:
            dialog_atual = None
            for dlg in self._dialog_por_canvas.values():
                if dlg and (obj is dlg or obj.parent() == dlg or obj in dlg.findChildren(QWidget)):
                    dialog_atual = dlg
                    break
            if dialog_atual is None:
                QTimer.singleShot(5, self._forcar_foco_dialogo)
        return False

    def on_activate(self, canvas):
        configurar_texto_canvas(canvas)
        aplicar_patch_texto_nativo_canvas()
        self._limpar_estado_antigo_texto_em_maos(canvas)
        self._modo_pos_ok_por_canvas[id(canvas)] = False
        self._cursor_por_canvas[id(canvas)] = self._centro_canvas(canvas)
        try:
            canvas.setMouseTracking(True)
        except Exception:
            pass
        self._iniciar_timer_mouse(canvas)
        self._abrir_dialogo(canvas)
        self._criar_ou_atualizar_previa(canvas)
        msg = "Inserir texto: digite na caixa e clique no canvas para soltar uma cópia."
        self.set_status(msg)
        mensagem_status(canvas, msg)
        canvas.update()

    def on_unidade_medida_alterada(self, canvas):
        dialog = self._dialogo(canvas)
        if dialog is not None:
            dialog.set_unidade(*unidade_canvas(canvas))
            self._dialogo_alterado(canvas)

        # Impede o canvas de receber foco
        canvas.setFocusPolicy(Qt.NoFocus)

        # Instala o filtro de eventos global
        if not self._event_filter_instalado:
            app = QApplication.instance()
            if app:
                self._event_filter_obj = _EventFilter(self)
                app.installEventFilter(self._event_filter_obj)
                self._event_filter_instalado = True

    def on_deactivate(self, canvas):
        self._parar_timer_mouse(canvas)
        self._remover_previa(canvas)
        dialog = self._dialog_por_canvas.pop(id(canvas), None)
        if dialog is not None:
            try:
                dialog._fechando_por_codigo = True
                dialog.hide()
                dialog.deleteLater()
            except Exception:
                pass
        self._cursor_por_canvas.pop(id(canvas), None)
        self._valores_pos_ok_por_canvas.pop(id(canvas), None)
        self._modo_pos_ok_por_canvas.pop(id(canvas), None)

        # Restaura a política de foco do canvas
        canvas.setFocusPolicy(Qt.ClickFocus)

        # Remove o filtro se não houver mais diálogos
        if not self._dialog_por_canvas and self._event_filter_instalado:
            app = QApplication.instance()
            if app and self._event_filter_obj:
                app.removeEventFilter(self._event_filter_obj)
                self._event_filter_obj = None
                self._event_filter_instalado = False
        return None

    def _limpar_estado_antigo_texto_em_maos(self, canvas) -> None:
        for nome, valor in (("_texto_em_maos_idx", None), ("_texto_em_maos_cancelavel", False)):
            try:
                setattr(canvas, nome, valor)
            except Exception:
                pass

    def _iniciar_timer_mouse(self, canvas) -> None:
        chave = id(canvas)
        timer = self._timer_por_canvas.get(chave)
        if timer is not None and timer.isActive():
            return
        timer = QTimer(canvas)
        timer.setInterval(25)
        timer.timeout.connect(lambda canvas_ref=canvas: self._atualizar_previa_pelo_mouse_global(canvas_ref))
        timer.start()
        self._timer_por_canvas[chave] = timer

    def _parar_timer_mouse(self, canvas) -> None:
        timer = self._timer_por_canvas.pop(id(canvas), None)
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass

    def _atualizar_previa_pelo_mouse_global(self, canvas) -> None:
        if self._dialogo(canvas) is None and not self._modo_pos_ok_por_canvas.get(id(canvas), False):
            return
        try:
            local = canvas.mapFromGlobal(QCursor.pos())
            x = float(local.x())
            y = float(local.y())
            if 0.0 <= x <= float(canvas.width()) and 0.0 <= y <= float(canvas.height()):
                self._cursor_por_canvas[id(canvas)] = canvas._tela_para_cena(QPointF(x, y))
                self._criar_ou_atualizar_previa(canvas)
        except Exception:
            pass

    def _abrir_dialogo(self, canvas) -> TextoDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = TextoDialog(canvas, self, parent)
            self._dialog_por_canvas[chave] = dialog
            self._ultima_abertura_por_canvas[chave] = monotonic()
        dialog.set_unidade(*unidade_canvas(canvas))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _dialogo(self, canvas) -> TextoDialog | None:
        return self._dialog_por_canvas.get(id(canvas))

    def _valores_atuais(self, canvas) -> dict:
        dialog = self._dialogo(canvas)
        if dialog is not None:
            return dialog.valores()
        return dict(self._valores_pos_ok_por_canvas.get(id(canvas), {}))

    def _dialogo_alterado(self, canvas) -> None:
        if self._dialogo(canvas) is None:
            return
        self._criar_ou_atualizar_previa(canvas)

    def _posicao_cursor_canvas(self, canvas) -> QPointF:
        return self._cursor_por_canvas.get(id(canvas), self._centro_canvas(canvas))

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
            "altura_cm": float(valores.get("altura_cm", ALTURA_TEXTO_PADRAO_CM) or ALTURA_TEXTO_PADRAO_CM),
            "texto_espaco_linhas_cm": float(valores.get("espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM) or ESPACO_LINHAS_PADRAO_CM),
            "espaco_linhas_cm": float(valores.get("espaco_linhas_cm", ESPACO_LINHAS_PADRAO_CM) or ESPACO_LINHAS_PADRAO_CM),
            "texto_espessura": espessura,
            "espessura": espessura,
            "referencia": str(valores.get("referencia") or "Centro centro"),
            "justificacao": str(valores.get("justificacao") or "Centro"),
            "cor": cor,
            "cor_texto": cor,
        }

    def _preview_idx(self, canvas) -> int | None:
        idx = self._preview_idx_por_canvas.get(id(canvas))
        if idx is None:
            return None
        try:
            idx = int(idx)
            if 0 <= idx < len(canvas.cena.elementos):
                elemento = canvas.cena.elementos[idx]
                if isinstance(elemento, dict) and elemento.get("__texto_previa_ao_vivo"):
                    return idx
        except Exception:
            pass
        self._preview_idx_por_canvas.pop(id(canvas), None)
        return None

    def _remover_previa(self, canvas) -> None:
        idx = self._preview_idx(canvas)
        if idx is not None:
            try:
                canvas.cena.elementos.pop(idx)
            except Exception:
                pass
        self._preview_idx_por_canvas.pop(id(canvas), None)
        try:
            canvas._selecionados.clear()
        except Exception:
            pass
        canvas.update()

    def _criar_ou_atualizar_previa(self, canvas) -> None:
        valores = self._valores_atuais(canvas)
        texto = str(valores.get("texto") or "").strip("\n")
        if not texto.strip():
            self._remover_previa(canvas)
            return

        cor_texto = self._cor_atual_para_texto(canvas)
        posicao = self._posicao_cursor_canvas(canvas)
        elemento = self._criar_elemento_texto_nativo(canvas, valores, posicao, cor_texto)
        if elemento is None:
            self._remover_previa(canvas)
            return
        elemento["__texto_previa_ao_vivo"] = True

        idx = self._preview_idx(canvas)
        if idx is None:
            canvas.cena.elementos.append(elemento)
            idx = len(canvas.cena.elementos) - 1
            self._preview_idx_por_canvas[id(canvas)] = idx
        else:
            canvas.cena.elementos[idx] = elemento

        canvas._selecionados = {idx}
        canvas.update()

    def _fixar_previa_como_copia_e_manter_caixa(self, canvas) -> bool:
        self._criar_ou_atualizar_previa(canvas)
        idx = self._preview_idx(canvas)
        if idx is None:
            mensagem_status(canvas, "Inserir texto: digite o texto antes de posicionar.")
            return True

        cor_texto = self._cor_atual_para_texto(canvas)
        cor_fundo = self._cor_fundo_canvas(canvas)
        if self._cores_iguais_ou_muito_parecidas(cor_texto, cor_fundo):
            self._remover_previa(canvas)
            self._alertar_cor_invisivel(canvas, cor_texto, cor_fundo)
            return True

        try:
            fixo = deepcopy(canvas.cena.elementos[idx])
            fixo.pop("__texto_previa_ao_vivo", None)
            canvas.cena.elementos[idx] = fixo
        except Exception:
            return True

        self._preview_idx_por_canvas.pop(id(canvas), None)
        canvas._selecionados = {idx}
        try:
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
        except Exception:
            pass
        try:
            if hasattr(canvas, "_emitir_elementos_alterados"):
                canvas._emitir_elementos_alterados()
        except Exception:
            pass

        self._criar_ou_atualizar_previa(canvas)
        mensagem_status(canvas, "Texto inserido. Continue escrevendo ou clique em outro ponto para inserir nova cópia.")
        canvas.update()
        return True

    def _ok_dialogo_fecha_mantendo_texto_na_mao(self, canvas) -> None:
        dialog = self._dialogo(canvas)
        if dialog is not None:
            self._valores_pos_ok_por_canvas[id(canvas)] = dialog.valores()
        self._criar_ou_atualizar_previa(canvas)
        self._dialog_por_canvas.pop(id(canvas), None)
        self._modo_pos_ok_por_canvas[id(canvas)] = True
        self._iniciar_timer_mouse(canvas)
        mensagem_status(canvas, "Texto na mão: clique esquerdo para posicionar e finalizar.")
        canvas.update()

    def _finalizar_previa_pos_ok(self, canvas) -> bool:
        self._criar_ou_atualizar_previa(canvas)
        idx = self._preview_idx(canvas)
        if idx is None:
            self._modo_pos_ok_por_canvas.pop(id(canvas), None)
            self._parar_timer_mouse(canvas)
            self._voltar_para_selecionar(canvas)
            return True

        try:
            canvas.cena.elementos[idx].pop("__texto_previa_ao_vivo", None)
        except Exception:
            pass
        self._preview_idx_por_canvas.pop(id(canvas), None)
        self._modo_pos_ok_por_canvas.pop(id(canvas), None)
        self._valores_pos_ok_por_canvas.pop(id(canvas), None)
        canvas._selecionados = {idx}
        try:
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
        except Exception:
            pass
        try:
            if hasattr(canvas, "_emitir_elementos_alterados"):
                canvas._emitir_elementos_alterados()
        except Exception:
            pass
        self._parar_timer_mouse(canvas)
        mensagem_status(canvas, "Texto inserido. Ferramenta finalizada.")
        canvas.update()
        self._voltar_para_selecionar(canvas)
        return True

    def _voltar_para_selecionar(self, canvas) -> None:
        try:
            canvas._ativar_ferramenta_janela_principal("selecionar")
            return
        except Exception:
            pass
        try:
            janela = canvas.window()
            if hasattr(janela, "ativar_ferramenta"):
                janela.ativar_ferramenta("selecionar")
        except Exception:
            pass

    def _cancelar_tudo(self, canvas) -> None:
        self._remover_previa(canvas)
        self._dialog_por_canvas.pop(id(canvas), None)
        self._cursor_por_canvas.pop(id(canvas), None)
        self._valores_pos_ok_por_canvas.pop(id(canvas), None)
        self._modo_pos_ok_por_canvas.pop(id(canvas), None)
        self._parar_timer_mouse(canvas)
        mensagem_status(canvas, "Inserir texto cancelado.")
        canvas.update()

    def _centro_canvas(self, canvas) -> QPointF:
        try:
            return canvas._tela_para_cena(QPointF(float(canvas.width()) / 2.0, float(canvas.height()) / 2.0))
        except Exception:
            return QPointF(0.0, 0.0)

    def on_mouse_move(self, canvas, event) -> bool:
        if self._dialogo(canvas) is None and not self._modo_pos_ok_por_canvas.get(id(canvas), False):
            return False
        try:
            self._cursor_por_canvas[id(canvas)] = canvas._ponto_com_snap(event.position())
        except Exception:
            try:
                self._cursor_por_canvas[id(canvas)] = canvas._tela_para_cena(event.position())
            except Exception:
                self._cursor_por_canvas[id(canvas)] = self._centro_canvas(canvas)
        self._criar_ou_atualizar_previa(canvas)
        event.accept()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._remover_previa(canvas)
            if self._modo_pos_ok_por_canvas.get(id(canvas), False):
                self._modo_pos_ok_por_canvas.pop(id(canvas), None)
                self._valores_pos_ok_por_canvas.pop(id(canvas), None)
                self._parar_timer_mouse(canvas)
                self._voltar_para_selecionar(canvas)
                mensagem_status(canvas, "Inserção de texto cancelada.")
            else:
                mensagem_status(canvas, "Prévia de texto cancelada. A caixa continua aberta.")
            event.accept()
            return True

        if event.button() != Qt.LeftButton:
            return False

        try:
            self._cursor_por_canvas[id(canvas)] = canvas._ponto_com_snap(event.position())
        except Exception:
            self._cursor_por_canvas[id(canvas)] = self._centro_canvas(canvas)

        if self._modo_pos_ok_por_canvas.get(id(canvas), False):
            event.accept()
            return self._finalizar_previa_pos_ok(canvas)

        if self._dialogo(canvas) is None:
            self._abrir_dialogo(canvas)
            self._criar_ou_atualizar_previa(canvas)
            event.accept()
            return True

        event.accept()
        resultado = self._fixar_previa_como_copia_e_manter_caixa(canvas)
        # Força o foco de volta para o diálogo após o clique
        self._forcar_foco_dialogo()
        return resultado
