from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, degrees, isfinite, radians, sin
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

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
        self.sp_angulo.setRange(-3600.0, 3600.0)
        self.sp_angulo.setDecimals(2)
        self.sp_angulo.setSingleStep(5.0)
        self.sp_angulo.setValue(90.0)
        self.cmb_pivo = QComboBox()
        self.cmb_pivo.addItems(["Centro da seleção", "Último clique", "Origem 0,0"])
        self.chk_copia = QCheckBox("Criar cópia girada")
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
        rod = QHBoxLayout()
        rod.addStretch(1)
        self.btn_aplicar = QPushButton("Aplicar")
        rod.addWidget(self.btn_aplicar)
        raiz.addLayout(rod)


class Ferramenta(FerramentaBase):
    id_ferramenta = "girar"
    nome = "Girar"
    usa_painel_auxiliar = False
    descricao_painel = "Gira elementos selecionados por ângulo, preservando controles, piques e fio."

    _dialog_por_canvas: dict[int, GirarDialog] = {}

    def __init__(self):
        super().__init__()
        self._ultimo_clique: QPointF | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._ultimo_clique = None
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Girar: selecione elementos, defina ângulo e aplique. Clique no canvas define pivô opcional.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._ultimo_clique = QPointF(pos)
        if not getattr(canvas, "_selecionados", set()):
            candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
            if candidatos:
                canvas._selecionados = {int(candidatos[0])}
                canvas.update()
                self._status(canvas, "Elemento selecionado. Clique em Aplicar para girar.")
                event.accept()
                return True
        self._status(canvas, "Pivô marcado. Clique em Aplicar ou pressione Enter.")
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._aplicar(canvas)
            event.accept()
            return True
        return False

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
            dialog.btn_aplicar.clicked.connect(lambda: self._aplicar(canvas))
        return dialog

    def _restaurar_dialog(self, canvas, dialog: GirarDialog) -> None:
        fallback = None
        if hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _aplicar(self, canvas) -> None:
        indices = [int(i) for i in sorted(getattr(canvas, "_selecionados", set()) or []) if 0 <= int(i) < len(canvas.cena.elementos)]
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
        canvas._selecionados = set(novos_indices)
        canvas._registrar_historico()
        canvas.update()
        self._status(canvas, f"Giro de {ang:g}° aplicado em {len(indices)} elemento(s).")

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

    def _girar_elemento(self, el: dict, pivo: QPointF, angulo: float) -> None:
        a = radians(angulo)
        ca, sa = cos(a), sin(a)

        def rot(p):
            x, y = float(p[0]), float(p[1])
            dx, dy = x - pivo.x(), y - pivo.y()
            return (pivo.x() + (dx * ca) - (dy * sa), pivo.y() + (dx * sa) + (dy * ca))

        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro", "distancias_no_perimetro", "marcacoes_perimetro"):
            if isinstance(el.get(chave), list):
                el[chave] = [rot(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]
        for chave in ("fio_origem", "fio_fim", "p0", "p1", "p2"):
            if self._eh_ponto(el.get(chave)):
                el[chave] = rot(el[chave])
        for chave in ("pontos_controle_principais", "pontos_auxiliares"):
            if isinstance(el.get(chave), list):
                for item in el[chave]:
                    if isinstance(item, dict) and "x" in item and "y" in item:
                        x, y = rot((item["x"], item["y"]))
                        item["x"] = x
                        item["y"] = y
        if "fio_angulo" in el:
            try:
                el["fio_angulo"] = float(el.get("fio_angulo") or 0.0) + float(angulo)
            except Exception:
                pass
        if self._eh_ponto(el.get("fio_origem")) and self._eh_ponto(el.get("fio_fim")):
            fo, ff = el["fio_origem"], el["fio_fim"]
            el["fio_angulo"] = degrees(atan2(float(ff[1]) - float(fo[1]), float(ff[0]) - float(fo[0])))
        el.setdefault("metadados", {})["ultima_transformacao"] = f"girar_{angulo:g}"

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

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
