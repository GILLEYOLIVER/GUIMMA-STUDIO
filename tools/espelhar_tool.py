from __future__ import annotations

from copy import deepcopy
from math import isfinite
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QLabel, QVBoxLayout

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class EspelharDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:espelhar"
        self.setWindowTitle("Espelhar")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(260)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QComboBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            """
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(6)
        form = QFormLayout()
        self.cmb_eixo = QComboBox()
        self.cmb_eixo.addItems(["Vertical", "Horizontal"])
        self.cmb_referencia = QComboBox()
        self.cmb_referencia.addItems(["Centro da seleção", "Último clique", "Origem 0,0"])
        self.chk_copia = QCheckBox("Criar cópia espelhada")
        self.chk_copia.setChecked(True)
        self.chk_inverter_reflexo = QCheckBox("Atualizar flags refletido/dobra")
        self.chk_inverter_reflexo.setChecked(True)
        form.addRow("Eixo", self.cmb_eixo)
        form.addRow("Referência", self.cmb_referencia)
        raiz.addLayout(form)
        raiz.addWidget(self.chk_copia)
        raiz.addWidget(self.chk_inverter_reflexo)


class Ferramenta(FerramentaBase):
    id_ferramenta = "espelhar"
    nome = "Espelhar"
    usa_painel_auxiliar = False
    descricao_painel = "Espelha elementos selecionados. Clique em um elemento para selecionar; Enter/Aplicar executa."

    _dialog_por_canvas: dict[int, EspelharDialog] = {}

    def __init__(self):
        super().__init__()
        self._ultimo_clique: QPointF | None = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._ultimo_clique = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Espelhar: clique esquerdo seleciona/referencia. Clique esquerdo novamente aplica. Direito fecha.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._operacao_finalizada and not self._direito_confirma_fechamento:
                self._direito_confirma_fechamento = True
                self._status(canvas, "Operação finalizada. Clique direito novamente fecha a ferramenta.")
            else:
                self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
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
                self._status(canvas, "Elemento selecionado. Ajuste a caixa e clique esquerdo novamente para espelhar.")
                event.accept()
                return True
        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        if candidatos and int(candidatos[0]) not in selecionados:
            canvas._selecionados = {int(candidatos[0])}
            canvas.update()
            self._operacao_finalizada = False
            self._direito_confirma_fechamento = False
            self._status(canvas, "Elemento selecionado. Clique esquerdo novamente para espelhar.")
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

    def _obter_dialog(self, canvas) -> EspelharDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = EspelharDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
        return dialog

    def _restaurar_dialog(self, canvas, dialog: EspelharDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _aplicar(self, canvas) -> None:
        indices = self._indices_validos(canvas)
        if not indices:
            self._status(canvas, "Espelhar: selecione ao menos um elemento.")
            return
        dialog = self._obter_dialog(canvas)
        eixo = dialog.cmb_eixo.currentText()
        copiar = dialog.chk_copia.isChecked()
        ref = self._referencia(canvas, indices, dialog.cmb_referencia.currentText())
        if ref is None:
            self._status(canvas, "Espelhar: não foi possível calcular a referência.")
            return
        novos_indices: list[int] = []
        for idx in indices:
            el = canvas.cena.elementos[idx]
            alvo = deepcopy(el) if copiar else el
            self._espelhar_elemento(alvo, eixo, ref, dialog.chk_inverter_reflexo.isChecked())
            if copiar:
                alvo["id"] = str(uuid4())
                if alvo.get("molde"):
                    alvo["molde_id"] = str(uuid4())
                    alvo["nome_molde"] = self._nome_copia(str(alvo.get("nome_molde") or "Molde"))
                canvas.cena.elementos.append(alvo)
                novos_indices.append(len(canvas.cena.elementos) - 1)
            else:
                novos_indices.append(idx)
        canvas._selecionados = set(novos_indices)
        canvas._registrar_historico()
        canvas.update()
        self._operacao_finalizada = True
        self._direito_confirma_fechamento = False
        self._status(canvas, f"Espelho {'copiado' if copiar else 'aplicado'} em {len(indices)} elemento(s). Clique esquerdo continua; direito fecha.")

    def _fechar(self, canvas) -> None:
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Espelhar finalizada. Voltando para Selecionar.")

    def _indices_validos(self, canvas) -> list[int]:
        return [int(i) for i in sorted(getattr(canvas, "_selecionados", set()) or []) if 0 <= int(i) < len(canvas.cena.elementos)]

    def _referencia(self, canvas, indices: list[int], modo: str) -> QPointF | None:
        if modo == "Último clique" and self._ultimo_clique is not None:
            return QPointF(self._ultimo_clique)
        if modo == "Origem 0,0":
            return QPointF(0.0, 0.0)
        bbox = self._bbox_indices(canvas, indices)
        if bbox is None:
            return None
        min_x, min_y, max_x, max_y = bbox
        return QPointF((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    def _bbox_indices(self, canvas, indices: list[int]) -> tuple[float, float, float, float] | None:
        pts: list[tuple[float, float]] = []
        for idx in indices:
            pts.extend(self._todos_pontos(canvas.cena.elementos[idx]))
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def _espelhar_elemento(self, el: dict, eixo: str, ref: QPointF, atualizar_flags: bool) -> None:
        def conv(p):
            x, y = float(p[0]), float(p[1])
            if eixo == "Vertical":
                x = (2.0 * ref.x()) - x
            else:
                y = (2.0 * ref.y()) - y
            return (x, y)

        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro", "distancias_no_perimetro", "marcacoes_perimetro"):
            if isinstance(el.get(chave), list):
                el[chave] = [conv(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]
        for chave in ("fio_origem", "fio_fim", "p0", "p1", "p2"):
            if self._eh_ponto(el.get(chave)):
                el[chave] = conv(el[chave])
        for chave in ("pontos_controle_principais", "pontos_auxiliares"):
            if isinstance(el.get(chave), list):
                for item in el[chave]:
                    if isinstance(item, dict) and "x" in item and "y" in item:
                        x, y = conv((item["x"], item["y"]))
                        item["x"] = x
                        item["y"] = y
        if atualizar_flags:
            if eixo == "Vertical":
                el["refletido_horizontal"] = not bool(el.get("refletido_horizontal", False))
                if "chk_reflete_h" in el:
                    el["chk_reflete_h"] = not bool(el.get("chk_reflete_h", False))
            else:
                el["refletido_vertical"] = not bool(el.get("refletido_vertical", False))
                if "chk_reflete_v" in el:
                    el["chk_reflete_v"] = not bool(el.get("chk_reflete_v", False))
        el.setdefault("metadados", {})["ultima_transformacao"] = f"espelhar_{eixo.lower()}"

    def _todos_pontos(self, el: dict) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro"):
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

    @staticmethod
    def _nome_copia(nome: str) -> str:
        nome = nome.strip() or "Molde"
        return nome if nome.lower().endswith("espelhado") else f"{nome} espelhado"

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
