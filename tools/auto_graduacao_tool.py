from __future__ import annotations

from copy import deepcopy
from math import hypot

from PySide6.QtCore import QPoint, QPointF, Qt, QSignalBlocker
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QComboBox, QDialog, QGridLayout, QLabel, QLineEdit, QVBoxLayout

from core.formatacao import numero_decimal_ponto
from core.graduacao import aplicar_grade_graduacao_referencia_canvas
from tools.tool_base import FerramentaBase
from tools.unidades import valor_unidade_para_cena


TODOS_TAMANHOS = "Todos os tamanhos"


class AutoGraduacaoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto graduação")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedSize(250, 108)
        self._ferramenta = None
        self._canvas = None
        self._bloquear = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 6, 6, 6)
        raiz.setSpacing(4)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        self.ed_dx = QLineEdit("5")
        self.ed_dy = QLineEdit("1")
        for campo in (self.ed_dx, self.ed_dy):
            campo.setValidator(QDoubleValidator(-999999.0, 999999.0, 3, self))
            campo.editingFinished.connect(self._notificar_alteracao)

        self.cmb_tamanho = QComboBox()
        self.cmb_tamanho.currentTextChanged.connect(self._notificar_alteracao)

        grid.addWidget(QLabel("Diferença de DX (cm)"), 0, 0)
        grid.addWidget(self.ed_dx, 0, 1)
        grid.addWidget(QLabel("Diferença de DY (cm)"), 1, 0)
        grid.addWidget(self.ed_dy, 1, 1)
        grid.addWidget(QLabel("Aplicar no tamanho"), 2, 0)
        grid.addWidget(self.cmb_tamanho, 2, 1)
        raiz.addLayout(grid)

    def conectar(self, ferramenta, canvas) -> None:
        self._ferramenta = ferramenta
        self._canvas = canvas

    def definir_tamanhos(self, tamanhos: list[dict]) -> None:
        atual = self.cmb_tamanho.currentData()
        with QSignalBlocker(self.cmb_tamanho):
            self.cmb_tamanho.clear()
            self.cmb_tamanho.addItem(TODOS_TAMANHOS, "")
            for linha in tamanhos:
                if not isinstance(linha, dict) or not linha.get("ativo", True):
                    continue
                nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
                if nome:
                    self.cmb_tamanho.addItem(nome, nome)
            idx = self.cmb_tamanho.findData(atual)
            self.cmb_tamanho.setCurrentIndex(idx if idx >= 0 else 0)
            self.cmb_tamanho.setEnabled(self.cmb_tamanho.count() > 1)

    def valores(self) -> tuple[float, float, str]:
        dx = numero_decimal_ponto(self.ed_dx.text(), 0.0)
        dy = numero_decimal_ponto(self.ed_dy.text(), 0.0)
        tamanho = str(self.cmb_tamanho.currentData() or "").strip()
        return dx, dy, tamanho

    def _notificar_alteracao(self):
        if self._bloquear or self._ferramenta is None or self._canvas is None:
            return
        self._ferramenta.aplicar_auto(self._canvas)


class Ferramenta(FerramentaBase):
    id_ferramenta = "auto_graduacao"
    nome = "Auto graduação"
    descricao_painel = "Cria graduação automática por diferença de DX e DY."

    _dialog_por_canvas: dict[int, AutoGraduacaoDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._molde_idx = self._molde_selecionado(canvas)
        if self._molde_idx is not None and hasattr(canvas, "_selecionados"):
            canvas._selecionados = {self._molde_idx}
        dialog = self._obter_dialog(canvas)
        dialog.conectar(self, canvas)
        self._atualizar_dialog(canvas)
        self._posicionar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(
            canvas,
            "Auto graduação: ajuste DX/DY ou clique em um molde para aplicar.",
        )
        if hasattr(canvas, "update"):
            canvas.update()

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position()) if hasattr(canvas, "_ponto_com_snap") else QPointF(event.position())
        molde_idx = self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            self._status(canvas, "Auto graduação: clique sobre um molde.")
            event.accept()
            return True
        self._selecionar_molde(canvas, int(molde_idx))
        self.aplicar_auto(canvas)
        event.accept()
        return True

    def aplicar_auto(self, canvas) -> bool:
        molde = self._molde_atual(canvas)
        if molde is None:
            self._status(canvas, "Auto graduação: selecione um molde.")
            return False
        dialog = self._obter_dialog(canvas)
        dx_unidade, dy_unidade, tamanho_alvo = dialog.valores()
        dx = valor_unidade_para_cena(canvas, dx_unidade)
        dy = valor_unidade_para_cena(canvas, dy_unidade)
        alterou = self._aplicar_auto_molde(canvas, molde, dx, dy, tamanho_alvo)
        self._atualizar_dialog(canvas)
        if alterou:
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
            elif hasattr(canvas, "elementos_alterados"):
                canvas.elementos_alterados.emit()
            self._status(canvas, "Auto graduação aplicada.")
        if hasattr(canvas, "update"):
            canvas.update()
        return alterou

    def _aplicar_auto_molde(self, canvas, molde: dict, dx: float, dy: float, tamanho_alvo: str = "") -> bool:
        if not isinstance(molde, dict):
            return False
        self._garantir_grade(canvas, molde)
        tamanhos = self._tamanhos_molde(molde)
        pontos = self._pontos_contorno(molde)
        if not tamanhos or not pontos:
            return False
        base_idx = next((idx for idx, linha in enumerate(tamanhos) if linha.get("base")), len(tamanhos) // 2)
        nomes = [str(linha.get("tamanho") or linha.get("nome") or "").strip() for linha in tamanhos]
        if tamanho_alvo and tamanho_alvo not in nomes:
            return False

        tabela = molde.setdefault("graduacao_tabela", {})
        tabela["modo"] = "dx_dy"
        pontos_cfg = tabela.setdefault("pontos", {})
        for ponto_idx, ponto in enumerate(pontos):
            cfg = pontos_cfg.get(str(ponto_idx))
            valores = deepcopy(cfg.get("valores")) if isinstance(cfg, dict) and isinstance(cfg.get("valores"), dict) else {}
            for idx, nome in enumerate(nomes):
                if not nome or (tamanho_alvo and nome != tamanho_alvo):
                    continue
                fator = idx - base_idx
                valores[nome] = {"dx": float(dx) * fator, "dy": float(dy) * fator}
            pontos_cfg[str(ponto_idx)] = {
                "indice": int(ponto_idx),
                "numero": int(ponto_idx) + 1,
                "ponto": (float(ponto.x()), float(ponto.y())),
                "valores": valores,
            }
        molde["graduacao_pontos"] = deepcopy(pontos_cfg)
        molde["graduacao_tamanhos_ativos"] = [nome for nome in nomes if nome]
        molde["mostrar_graduacao"] = True
        return True

    def _garantir_grade(self, canvas, molde: dict) -> None:
        linhas = molde.get("graduacao_tamanhos")
        if isinstance(linhas, list) and linhas:
            return
        aplicar_grade_graduacao_referencia_canvas(molde, canvas, sobrescrever=False)

    @staticmethod
    def _tamanhos_molde(molde: dict | None) -> list[dict]:
        linhas = molde.get("graduacao_tamanhos") if isinstance(molde, dict) else None
        if not isinstance(linhas, list):
            return []
        return [dict(linha) for linha in linhas if isinstance(linha, dict) and linha.get("ativo", True)]

    def _atualizar_dialog(self, canvas) -> None:
        dialog = self._obter_dialog(canvas)
        dialog.definir_tamanhos(self._tamanhos_molde(self._molde_atual(canvas)))

    def _selecionar_molde(self, canvas, molde_idx: int) -> None:
        self._molde_idx = int(molde_idx)
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(molde_idx)}
        self._atualizar_dialog(canvas)
        if hasattr(canvas, "update"):
            canvas.update()

    def _molde_atual(self, canvas) -> dict | None:
        if self._molde_idx is None or not (0 <= int(self._molde_idx) < len(canvas.cena.elementos)):
            return None
        molde = canvas.cena.elementos[int(self._molde_idx)]
        return molde if self._eh_molde(molde) else None

    def _molde_selecionado(self, canvas) -> int | None:
        for idx in sorted(getattr(canvas, "_selecionados", set()) or []):
            if 0 <= int(idx) < len(canvas.cena.elementos) and self._eh_molde(canvas.cena.elementos[int(idx)]):
                return int(idx)
        return None

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None and 0 <= int(idx) < len(canvas.cena.elementos):
                if self._eh_molde(canvas.cena.elementos[int(idx)]):
                    return int(idx)
        for idx, molde in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if self._eh_molde(molde) and self._ponto_dentro_bbox(molde, pos):
                return int(idx)
        return None

    @staticmethod
    def _eh_molde(elemento) -> bool:
        return isinstance(elemento, dict) and bool(elemento.get("molde"))

    @classmethod
    def _ponto_dentro_bbox(cls, molde: dict, pos: QPointF) -> bool:
        pontos = cls._pontos_contorno(molde)
        if not pontos:
            return False
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        return min(xs) <= pos.x() <= max(xs) and min(ys) <= pos.y() <= max(ys)

    @staticmethod
    def _pontos_contorno(molde: dict | None) -> list[QPointF]:
        if not isinstance(molde, dict):
            return []
        origem = (
            molde.get("pontos_controle_principais")
            or molde.get("controle_cantos")
            or molde.get("pontos_controle")
            or molde.get("pontos")
            or []
        )
        pontos: list[QPointF] = []
        for item in origem:
            try:
                if isinstance(item, dict):
                    pontos.append(QPointF(float(item.get("x")), float(item.get("y"))))
                else:
                    pontos.append(QPointF(float(item[0]), float(item[1])))
            except Exception:
                continue
        if len(pontos) > 1 and hypot(pontos[0].x() - pontos[-1].x(), pontos[0].y() - pontos[-1].y()) <= 1e-7:
            pontos.pop()
        return pontos

    def _obter_dialog(self, canvas) -> AutoGraduacaoDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        precisa_recriar = dialog is None
        if dialog is not None:
            try:
                precisa_recriar = dialog.parentWidget() is not parent
            except RuntimeError:
                precisa_recriar = True
                self._dialog_por_canvas.pop(chave, None)
        if precisa_recriar:
            dialog = AutoGraduacaoDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        return dialog

    @staticmethod
    def _posicionar_dialog(canvas, dialog: QDialog) -> None:
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            dialog.move(canvas.mapToGlobal(pos_local))
        elif hasattr(canvas, "mapToGlobal"):
            dialog.move(canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 120)))

    def _fechar(self, canvas) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        if hasattr(canvas, "update"):
            canvas.update()

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
