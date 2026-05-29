from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QTextEdit,
)

from tools.tool_base import FerramentaBase
from tools.inserir_texto_tool import AnguloSpinBox, FONTES_TEXTO, MedidaCmSpinBox, NumeroLimpoSpinBox


class EditarTextoDialog(QDialog):
    def __init__(self, elemento: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar texto")
        self.setModal(True)
        self.resize(560, 390)
        self.elemento = elemento
        self.canvas = parent
        self._original = deepcopy(elemento)
        self._aceito = False
        self._atualizando = False

        self.txt_texto = QTextEdit(self)
        self.txt_texto.setPlainText(str(elemento.get("texto") or elemento.get("conteudo") or ""))

        self.combo_fonte = QComboBox(self)
        self.combo_fonte.addItems(FONTES_TEXTO)
        fonte_atual = str(elemento.get("fonte_texto") or elemento.get("fonte") or "Arial")
        self.combo_fonte.setCurrentText(fonte_atual if fonte_atual in FONTES_TEXTO else "Arial")

        self.spin_angulo = AnguloSpinBox(self)
        self.spin_angulo.setRange(-360.0, 360.0)
        self.spin_angulo.setValue(float(elemento.get("angulo", 0.0) or 0.0))

        self.spin_altura = MedidaCmSpinBox(self)
        self.spin_altura.setRange(0.2, 200.0)
        self.spin_altura.setValue(float(elemento.get("texto_altura_cm", elemento.get("altura_cm", 2.0)) or 2.0))

        self.spin_espaco = MedidaCmSpinBox(self)
        self.spin_espaco.setRange(0.2, 200.0)
        self.spin_espaco.setValue(float(elemento.get("texto_espaco_linhas_cm", elemento.get("espaco_linhas_cm", 3.0)) or 3.0))

        self.spin_espessura = NumeroLimpoSpinBox(self)
        self.spin_espessura.setRange(1.0, 50.0)
        self.spin_espessura.setValue(float(elemento.get("texto_espessura", elemento.get("espessura", 1.0)) or 1.0))

        self.combo_referencia = QComboBox(self)
        self.combo_referencia.addItems([
            "Topo esquerda", "Topo centro", "Topo direita",
            "Centro esquerda", "Centro centro", "Centro direita",
            "Baixo esquerda", "Baixo centro", "Baixo direita",
        ])
        ref = str(elemento.get("referencia") or "Centro centro")
        self.combo_referencia.setCurrentText(ref if self.combo_referencia.findText(ref) >= 0 else "Centro centro")

        self.combo_justificacao = QComboBox(self)
        self.combo_justificacao.addItems(["Esquerda", "Centro", "Direita"])
        just = str(elemento.get("justificacao") or "Centro")
        self.combo_justificacao.setCurrentText(just if self.combo_justificacao.findText(just) >= 0 else "Centro")

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout = QGridLayout(self)
        layout.addWidget(self.txt_texto, 0, 0, 1, 6)
        layout.addWidget(QLabel("Fonte"), 1, 0)
        layout.addWidget(QLabel("Ângulo"), 1, 2)
        layout.addWidget(QLabel("Altura"), 1, 4)
        layout.addWidget(self.combo_fonte, 2, 0, 1, 2)
        layout.addWidget(self.spin_angulo, 2, 2, 1, 2)
        layout.addWidget(self.spin_altura, 2, 4, 1, 2)
        layout.addWidget(QLabel("Espaço linhas"), 3, 0)
        layout.addWidget(QLabel("Referência"), 3, 2)
        layout.addWidget(QLabel("Justificação"), 3, 4)
        layout.addWidget(self.spin_espaco, 4, 0, 1, 2)
        layout.addWidget(self.combo_referencia, 4, 2, 1, 2)
        layout.addWidget(self.combo_justificacao, 4, 4, 1, 2)
        layout.addWidget(QLabel("Espessura"), 5, 0)
        layout.addWidget(self.spin_espessura, 5, 1, 1, 2)
        layout.addWidget(botoes, 6, 0, 1, 6)
        layout.setRowStretch(0, 1)

        self._conectar_atualizacao_ao_vivo()
        self._aplicar_fonte_caixa()

    def _conectar_atualizacao_ao_vivo(self) -> None:
        self.txt_texto.textChanged.connect(self._atualizar_ao_vivo)
        self.combo_fonte.currentTextChanged.connect(self._atualizar_ao_vivo)
        try:
            self.combo_fonte.textHighlighted.connect(self._fonte_destacada)
        except Exception:
            try:
                self.combo_fonte.highlighted.connect(self._fonte_destacada_indice)
            except Exception:
                pass
        self.spin_angulo.valueChanged.connect(self._atualizar_ao_vivo)
        self.spin_altura.valueChanged.connect(self._atualizar_ao_vivo)
        self.spin_espaco.valueChanged.connect(self._atualizar_ao_vivo)
        self.spin_espessura.valueChanged.connect(self._atualizar_ao_vivo)
        self.combo_referencia.currentTextChanged.connect(self._atualizar_ao_vivo)
        self.combo_justificacao.currentTextChanged.connect(self._atualizar_ao_vivo)

    def _fonte_destacada(self, fonte: str) -> None:
        if fonte and self.combo_fonte.currentText() != fonte:
            self.combo_fonte.setCurrentText(fonte)
        self._atualizar_ao_vivo()

    def _fonte_destacada_indice(self, indice: int) -> None:
        if 0 <= int(indice) < self.combo_fonte.count():
            self._fonte_destacada(self.combo_fonte.itemText(int(indice)))

    def _aplicar_fonte_caixa(self) -> None:
        fonte = self.combo_fonte.currentText() or "Arial"
        self.txt_texto.setStyleSheet(f'QTextEdit {{ font-family: "{fonte}"; font-size: 12pt; }}')

    def _atualizar_canvas(self) -> None:
        try:
            if self.canvas is not None:
                self.canvas.update()
        except Exception:
            pass

    def _atualizar_ao_vivo(self, *args) -> None:
        if self._atualizando:
            return
        self._atualizando = True
        try:
            self.aplicar()
            self._aplicar_fonte_caixa()
            self._atualizar_canvas()
        finally:
            self._atualizando = False

    def _restaurar_original(self) -> None:
        self.elemento.clear()
        self.elemento.update(deepcopy(self._original))
        self._atualizar_canvas()

    def aplicar(self) -> None:
        texto = self.txt_texto.toPlainText().strip("\n")
        fonte = self.combo_fonte.currentText()
        self.elemento["texto"] = texto
        self.elemento["conteudo"] = texto
        self.elemento["fonte_texto"] = fonte
        self.elemento["fonte"] = fonte
        self.elemento["angulo"] = float(self.spin_angulo.value())
        self.elemento["texto_altura_cm"] = float(self.spin_altura.value())
        self.elemento["altura_cm"] = float(self.spin_altura.value())
        self.elemento["texto_espaco_linhas_cm"] = float(self.spin_espaco.value())
        self.elemento["espaco_linhas_cm"] = float(self.spin_espaco.value())
        self.elemento["texto_espessura"] = float(self.spin_espessura.value())
        self.elemento["espessura"] = float(self.spin_espessura.value())
        self.elemento["referencia"] = self.combo_referencia.currentText()
        self.elemento["justificacao"] = self.combo_justificacao.currentText()

    def accept(self) -> None:
        self._aceito = True
        self.aplicar()
        self._atualizar_canvas()
        super().accept()

    def reject(self) -> None:
        self._aceito = False
        self._restaurar_original()
        super().reject()

    def closeEvent(self, event) -> None:
        if not self._aceito:
            self._restaurar_original()
        super().closeEvent(event)


def _cor_atual_canvas(canvas) -> str | None:
    cor = QColor(str(getattr(canvas, "_linha_cor", "") or ""))
    if cor.isValid():
        return cor.name()
    return None


class Ferramenta(FerramentaBase):
    id_ferramenta = "editar_texto"
    nome = "Editar Texto"
    descricao_painel = ""
    usa_painel_auxiliar = False
    gerencia_coordenadas_operacao = True

    def on_activate(self, canvas):
        if getattr(canvas, "_editar_texto_dialogo_ativo", False):
            return None
        idx = self._indice_texto_alvo(canvas)
        if idx is None:
            QMessageBox.information(canvas, "Editar Texto", "Selecione um texto no canvas para editar.")
            return None
        self._abrir_dialogo(canvas, idx)
        return None

    def _indice_texto_alvo(self, canvas) -> int | None:
        selecionados = list(getattr(canvas, "_selecionados", set()) or [])
        for idx in selecionados:
            try:
                elemento = canvas.cena.elementos[int(idx)]
            except Exception:
                continue
            if isinstance(elemento, dict) and str(elemento.get("tipo") or "").lower() == "texto":
                return int(idx)
        return None

    def _abrir_dialogo(self, canvas, idx: int) -> None:
        if getattr(canvas, "_editar_texto_dialogo_ativo", False):
            return
        canvas._editar_texto_dialogo_ativo = True
        try:
            elemento = canvas.cena.elementos[idx]
            dlg = EditarTextoDialog(elemento, canvas)
            if dlg.exec() == QDialog.Accepted:
                dlg.aplicar()
                cor = _cor_atual_canvas(canvas)
                if cor:
                    elemento["cor"] = cor
                    elemento["cor_texto"] = cor
                if hasattr(canvas, "_registrar_historico"):
                    canvas._registrar_historico()
                if hasattr(canvas, "_emitir_elementos_alterados"):
                    canvas._emitir_elementos_alterados()
                canvas.update()
        finally:
            canvas._editar_texto_dialogo_ativo = False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        idx = self._indice_texto_alvo(canvas)
        if idx is not None:
            self._abrir_dialogo(canvas, idx)
            event.accept()
            return True
        return False
