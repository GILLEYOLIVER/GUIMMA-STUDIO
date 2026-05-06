from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, pi, sin, sqrt
import os
from time import monotonic
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from core.geometry.engine import internal_angle, point_segment_distance, polyline_perimeter
from core.geometry_bridge import (
    compose_closed_contour,
    create_mold_payload,
    extract_local_enclosing_contour,
    extract_smallest_enclosing_contour,
    polyline_from_element,
)
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "extrair_molde"
    nome = "Extrair Molde"
    usa_painel_auxiliar = False
    descricao_painel = "LMB soma partes ao molde. Tab alterna candidatos. RMB/Enter extrai. LMB solta e continua. Duplo clique encerra."
    TOLERANCIA_FECHAMENTO_CM = 0.10

    _dialog_global: QDialog | None = None
    _cmb_modo_global: QComboBox | None = None
    _chk_grad_global: QCheckBox | None = None
    _chk_piques_global: QCheckBox | None = None
    _chk_aux_global: QCheckBox | None = None
    _chk_compor_global: QCheckBox | None = None
    _chk_usar_global: QCheckBox | None = None
    _chk_quebrar_global: QCheckBox | None = None
    _chk_converter_global: QCheckBox | None = None
    _cfg_global = {
        "modo": "Automático",
        "detectar_graduacoes": True,
        "detectar_piques": True,
        "detectar_auxiliares": False,
        "compor_contornos": True,
        "usar_auxiliares": True,
        "quebrar_auxiliares": True,
        "converter_auxiliares": True,
    }
    _log_extracao_habilitado = os.environ.get("GUIMMA_EXTRACAO_LOG", "1").strip().lower() not in {"0", "false", "off", "no"}

    @classmethod
    def _limpar_referencias_ui_global(cls):
        cls._dialog_global = None
        cls._cmb_modo_global = None
        cls._chk_grad_global = None
        cls._chk_piques_global = None
        cls._chk_aux_global = None
        cls._chk_compor_global = None
        cls._chk_usar_global = None
        cls._chk_quebrar_global = None
        cls._chk_converter_global = None

    @classmethod
    def _ui_global_disponivel(cls) -> bool:
        widgets = (
            cls._dialog_global,
            cls._cmb_modo_global,
            cls._chk_grad_global,
            cls._chk_piques_global,
            cls._chk_aux_global,
            cls._chk_compor_global,
            cls._chk_usar_global,
            cls._chk_quebrar_global,
            cls._chk_converter_global,
        )
        if any(widget is None for widget in widgets):
            return False
        if not all(isValid(widget) for widget in widgets):
            cls._limpar_referencias_ui_global()
            return False
        return True

    def __init__(self):
        super().__init__()
        self._canvas = None
        self._dialog: QDialog | None = None
        self._idx_selecionado: int | None = None
        self._selecoes_manuais: set[int] = set()
        self._contornos_extraidos_preview: list[list[QPointF]] = []
        self._contornos_auto_coords: list[list[tuple[float, float]]] = []
        self._contornos_preparados: dict[int, list[tuple[float, float]]] = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._arrastando_molde = False
        self._ultimo_pos_arrasto: QPointF | None = None
        self._snapshot_cancelamento: dict[int, dict] = {}
        self._indices_molde_em_arraste: set[int] = set()
        self._cfg = dict(type(self)._cfg_global)
        self._ultimo_clique_falho = None
        self._contorno_hover_preview: list[QPointF] = []
        self._contornos_candidatos: list[list[tuple[float, float]]] = []
        self._indice_candidato_atual: int = 0
        self._ultimo_hover_tempo: float = 0.0
        self._ultimo_hover_pos: QPointF | None = None
        self._ultima_pos_cena: QPointF | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._canvas = canvas
        cfg_mem = self.carregar_preferencias_ferramenta(canvas, type(self)._cfg_global)
        type(self)._cfg_global = dict(cfg_mem)
        self._cfg = dict(cfg_mem)
        self._cfg["modo"] = "Automático"
        type(self)._cfg_global["modo"] = "Automático"
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contornos_extraidos_preview = []
        self._contornos_auto_coords = []
        self._contornos_preparados = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._indices_molde_em_arraste = set()
        self._ultimo_clique_falho = None
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        self._ultimo_hover_tempo = 0.0
        self._ultimo_hover_pos = None
        self._ultima_pos_cena = None
        self._sincronizar_cfg_da_ui()
        self._abrir_config(canvas)
        self.set_status("Clique esquerdo soma partes ao molde. Direito/Enter extrai. Depois solte com esquerdo; duplo clique encerra.")

    def on_deactivate(self, canvas):
        super().on_deactivate(canvas)
        self._sincronizar_cfg_da_ui()
        self.salvar_preferencias_ferramenta(canvas, type(self)._cfg_global)
        self._canvas = None
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contornos_extraidos_preview = []
        self._contornos_auto_coords = []
        self._contornos_preparados = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._indices_molde_em_arraste = set()
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        self._ultimo_hover_tempo = 0.0
        self._ultimo_hover_pos = None
        self._ultima_pos_cena = None
        if self._dialog is not None and isValid(self._dialog):
            self._dialog.hide()

    def on_canvas_resize(self, canvas) -> None:
        self._reposicionar_dialog_config(canvas)

    def on_mouse_press(self, canvas, event) -> bool:
        pos_tela_exata = self._posicao_tela_exata_no_canvas(canvas, event.position())
        pos = canvas._ponto_com_snap(pos_tela_exata)
        self._sincronizar_cfg_da_ui()
        pos_clique = canvas._tela_para_cena(pos_tela_exata)
        self._ultima_pos_cena = QPointF(pos_clique)

        if self._arrastando_molde:
            if event.button() == Qt.LeftButton:
                self._finalizar_posicionamento(
                    canvas,
                    "Molde solto. Clique esquerdo seleciona outra parte; duplo clique encerra a ferramenta.",
                )
                event.accept()
                return True
            if event.button() == Qt.RightButton:
                self._cancelar_arraste_molde(canvas)
                canvas.update()
                event.accept()
                return True
            return False

        if self._molde_posicionado:
            if event.button() == Qt.LeftButton:
                self._limpar_estado_extracao(canvas, "Ferramenta finalizada. Voltando para Selecionar.")
                canvas.set_ferramenta_ativa("selecionar")
                canvas.update()
                event.accept()
                return True
            if event.button() == Qt.RightButton:
                self.set_status("Molde finalizado. Clique esquerdo para encerrar a ferramenta.")
                event.accept()
                return True
            return False

        if event.button() == Qt.LeftButton:
            if self._cfg.get("modo") == "Manual":
                candidatos = self._detectar_candidatos_linha_manual(canvas, pos_clique)
            else:
                candidatos = self._detectar_candidatos_contorno(canvas, pos_clique)
            if not candidatos:
                if self._cfg.get("modo") == "Manual":
                    self.set_status("Manual: clique sobre uma linha do contorno do molde.")
                    self._ultimo_clique_falho = QPointF(pos_clique)
                    canvas.update()
                else:
                    self._mostrar_aviso_sem_molde(canvas, pos_clique)
                event.accept()
                return True
            self._contornos_candidatos = candidatos
            self._indice_candidato_atual = 0
            contorno = candidatos[0]
            if self._perimetro_contorno(contorno) < self.TOLERANCIA_FECHAMENTO_CM:
                self._mostrar_aviso_sem_molde(canvas, pos_clique)
                event.accept()
                return True
            adicionar = True
            self._fixar_contorno(canvas, contorno, adicionar=adicionar)
            self._selecoes_manuais.clear()
            self._idx_selecionado = None
            canvas._selecionados = set()
            self._molde_criado = False
            self._molde_posicionado = False
            self._ultimo_clique_falho = None
            total = len(self._contornos_candidatos)
            if len(self._contornos_auto_coords) > 1:
                self.set_status("Parte adicionada ao molde. Clique esquerdo soma outra; direito/Enter extrai o conjunto.")
            elif total > 1:
                self.set_status(f"Candidato 1/{total}. Tab alterna, Direito/Enter extrai.")
            else:
                self.set_status("Parte selecionada. Clique esquerdo soma outra; direito/Enter extrai.")
            canvas.update()
            event.accept()
            return True

        if event.button() == Qt.RightButton:
            if self._molde_posicionado:
                self._limpar_estado_extracao(canvas, "Ferramenta finalizada. Voltando para Selecionar.")
                canvas.set_ferramenta_ativa("selecionar")
                canvas.update()
                event.accept()
                return True
            if not self._contornos_auto_coords and not self._selecoes_manuais:
                self.set_status("Selecione primeiro uma area/contorno com clique esquerdo.")
                event.accept()
                return True
            if self._extrair_e_iniciar_arraste(canvas, pos):
                event.accept()
                return True
            self._mostrar_aviso_sem_molde(canvas)
            return False

        return False

        if self._arrastando_molde:
            if event.button() == Qt.LeftButton:
                self._finalizar_posicionamento(canvas, "Molde finalizado. Clique direito no canvas para encerrar ou clique esquerdo em outra área para extrair outro molde.")
                event.accept()
                return True
            if event.button() == Qt.RightButton:
                self._cancelar_arraste_molde(canvas)
                canvas.update()
                event.accept()
                return True
            return False

        if event.button() == Qt.LeftButton:
            pos_clique = canvas._tela_para_cena(pos_tela_exata)
            if self._cfg.get("modo") == "Manual":
                contorno = self._detectar_contorno_fechado(canvas, pos_clique)
                if not contorno or self._perimetro_contorno(contorno) < self.TOLERANCIA_FECHAMENTO_CM:
                    self.set_status("Manual: clique dentro de uma área fechada para detectar o contorno.")
                    event.accept()
                    return True

                ja_selecionado = any(self._contornos_equivalentes(contorno, c) for c in self._contornos_auto_coords)
                if not ja_selecionado:
                    self._contornos_auto_coords = [contorno]
                    self._contornos_extraidos_preview = [[QPointF(float(x), float(y)) for x, y in contorno]]
                    self._selecoes_manuais.clear()
                    self._contornos_preparados = {}
                    self._idx_selecionado = None
                    canvas._selecionados = set()
                    self._molde_criado = False
                    self._molde_posicionado = False
                    self.set_status("Manual: contorno detectado em azul. Clique esquerdo novamente para extrair.")
                    canvas.update()
                    event.accept()
                    return True

                ok = self._criar_molde(canvas)
                if not ok:
                    self._mostrar_aviso_sem_molde(canvas, pos_clique)
                    return False
                self._ultimo_clique_falho = None
                self._iniciar_arraste_molde(canvas, pos)
                self.set_status("Molde em mãos: mova o mouse. Clique esquerdo solta, clique direito cancela.")
                canvas.update()
                event.accept()
                return True

            # Para extrair molde por área, usar o ponto real do clique (sem snap),
            # evitando capturar regiões distantes por aproximação de snap.
            contorno = self._detectar_contorno_fechado(canvas, pos_clique)
            if not contorno:
                self._mostrar_aviso_sem_molde(canvas, pos_clique)
                return True
            if self._perimetro_contorno(contorno) < self.TOLERANCIA_FECHAMENTO_CM:
                self._mostrar_aviso_sem_molde(canvas, pos_clique)
                return True
            if event.modifiers() & Qt.ShiftModifier and self._contornos_auto_coords:
                self._contornos_auto_coords.append(contorno)
                self._contornos_extraidos_preview.append([QPointF(float(x), float(y)) for x, y in contorno])
                self.set_status("Área adicionada à composição. Direito/Enter extrai o conjunto.")
            else:
                self._contornos_auto_coords = [contorno]
                self._contornos_extraidos_preview = [[QPointF(float(x), float(y)) for x, y in contorno]]
                self.set_status("Contorno selecionado. Clique direito ou Enter para extrair.")
            self._selecoes_manuais.clear()
            self._contornos_preparados = {}
            self._idx_selecionado = None
            canvas._selecionados = set()
            self._molde_criado = False
            self._molde_posicionado = False
            self._ultimo_clique_falho = None
            self.set_status("Contorno selecionado. Clique direito ou Enter para extrair.")
            canvas.update()
            event.accept()
            return True

        if event.button() != Qt.RightButton:
            return False

        if self._molde_posicionado:
            self._limpar_estado_extracao(canvas, "Ferramenta finalizada. Voltando para Selecionar.")
            canvas.set_ferramenta_ativa("selecionar")
            canvas.update()
            event.accept()
            return True

        if self._cfg.get("modo") == "Manual" and self._contornos_auto_coords and not self._molde_criado:
            self._contornos_auto_coords = []
            self._contornos_extraidos_preview = []
            self.set_status("Manual: contorno removido. Clique esquerdo para detectar novamente.")
            canvas.update()
            event.accept()
            return True

        if not self._contornos_auto_coords and not self._selecoes_manuais:
            self.set_status("Selecione primeiro uma área/contorno com clique esquerdo.")
            event.accept()
            return True

        ok = self._criar_molde(canvas)
        if not ok:
            self._mostrar_aviso_sem_molde(canvas)
            return False
        self._iniciar_arraste_molde(canvas, pos)
        self.set_status("Molde em mãos: mova o mouse. Clique esquerdo solta, clique direito cancela.")
        canvas.update()
        event.accept()
        return True


    def on_key_press(self, canvas, event) -> bool:
        key = event.key()
        if key == Qt.Key_Escape:
            if self._arrastando_molde:
                self._cancelar_arraste_molde(canvas)
            elif self._contornos_auto_coords or self._contorno_hover_preview:
                self._contornos_auto_coords = []
                self._contornos_extraidos_preview = []
                self._contorno_hover_preview = []
                self._contornos_candidatos = []
                self._indice_candidato_atual = 0
                self.set_status("Preview limpo. Clique esquerdo para selecionar novamente.")
            else:
                self._limpar_estado_extracao(canvas, "Ferramenta finalizada. Voltando para Selecionar.")
                canvas.set_ferramenta_ativa("selecionar")
            canvas.update()
            event.accept()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._contornos_auto_coords and not self._arrastando_molde:
                ok = self._criar_molde(canvas)
                if ok:
                    self._iniciar_arraste_molde(canvas, canvas._ponto_com_snap(canvas._cursor_tela))
                    self.set_status("Molde em mãos: mova o mouse. Clique esquerdo solta, clique direito cancela.")
                    canvas.update()
                event.accept()
                return True
        if key == Qt.Key_Tab and self._contornos_candidatos:
            self._indice_candidato_atual = (self._indice_candidato_atual + 1) % len(self._contornos_candidatos)
            cont = self._contornos_candidatos[self._indice_candidato_atual]
            self._contornos_auto_coords = [cont]
            self._contornos_extraidos_preview = [[QPointF(float(x), float(y)) for x, y in cont]]
            self.set_status(f"Candidato {self._indice_candidato_atual + 1}/{len(self._contornos_candidatos)}. Tab alterna, Direito/Enter extrai.")
            canvas.update()
            event.accept()
            return True
        if key == Qt.Key_Backspace and len(self._contornos_auto_coords) > 1:
            self._contornos_auto_coords.pop()
            if self._contornos_extraidos_preview:
                self._contornos_extraidos_preview.pop()
            self.set_status("Última área removida da composição.")
            canvas.update()
            event.accept()
            return True
        return False

    def on_mouse_move(self, canvas, event) -> bool:
        if not self._arrastando_molde:
            pos_tela_exata = self._posicao_tela_exata_no_canvas(canvas, event.position())
            pos_cena = canvas._tela_para_cena(pos_tela_exata)
            self._ultima_pos_cena = QPointF(pos_cena)
            if self._deve_recalcular_hover(pos_cena):
                if self._cfg.get("modo") == "Manual":
                    candidatos = self._detectar_candidatos_linha_manual(canvas, pos_cena, leve=True)
                else:
                    candidatos = self._detectar_candidatos_contorno(canvas, pos_cena, leve=True)
                self._contorno_hover_preview = self._preview_de_contorno(candidatos[0]) if candidatos else []
                self._ultimo_hover_tempo = monotonic()
                self._ultimo_hover_pos = QPointF(pos_cena)
                canvas.update()
            event.accept()
            return True
        pos = canvas._ponto_com_snap(self._posicao_tela_exata_no_canvas(canvas, event.position()))
        self._ultima_pos_cena = QPointF(pos)
        if self._ultimo_pos_arrasto is None:
            self._ultimo_pos_arrasto = pos
            return True
        dx = pos.x() - self._ultimo_pos_arrasto.x()
        dy = pos.y() - self._ultimo_pos_arrasto.y()
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            self._aplicar_delta_selecionados(canvas, dx, dy)
            self._ultimo_pos_arrasto = pos
            canvas.update()
        event.accept()
        return True

    def on_mouse_double_click(self, canvas, event) -> bool:
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            if self._arrastando_molde:
                self._finalizar_posicionamento(canvas, "Molde solto.")
            self._limpar_estado_extracao(canvas, "Ferramenta finalizada. Voltando para Selecionar.")
            canvas.set_ferramenta_ativa("selecionar")
            canvas.update()
            event.accept()
            return True
        return False

    def on_key_press(self, canvas, event) -> bool:
        key = event.key()
        if key == Qt.Key_Escape:
            if self._arrastando_molde:
                self._cancelar_arraste_molde(canvas)
            elif self._contornos_auto_coords or self._contornos_extraidos_preview or self._contorno_hover_preview:
                self._limpar_previews(canvas, "Preview limpo. Clique esquerdo para selecionar novamente.")
            else:
                self._limpar_estado_extracao(canvas, "Ferramenta finalizada. Voltando para Selecionar.")
                canvas.set_ferramenta_ativa("selecionar")
            canvas.update()
            event.accept()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._contornos_auto_coords and not self._arrastando_molde:
                pos = self._posicao_arraste_inicial(canvas)
                if self._extrair_e_iniciar_arraste(canvas, pos):
                    event.accept()
                    return True
            event.accept()
            return True
        if key == Qt.Key_Tab:
            if self._contornos_candidatos:
                self._alternar_candidato(canvas)
                event.accept()
                return True
            return False
        if key == Qt.Key_Backspace:
            if len(self._contornos_auto_coords) > 1:
                self._contornos_auto_coords.pop()
                self._contornos_extraidos_preview = [self._preview_de_contorno(c) for c in self._contornos_auto_coords]
                self.set_status("Ultima area removida da composicao. Direito/Enter extrai o conjunto.")
                canvas.update()
                event.accept()
                return True
            return False
        return False

    def _posicao_tela_exata_no_canvas(self, canvas, pos_evento: QPointF) -> QPointF:
        """
        Usa a posição mais fiel possível do cursor no momento do evento e
        restringe ao retângulo útil do canvas para evitar deslocamentos fora da área.
        """
        pos = QPointF(pos_evento)
        try:
            pos_global = canvas.mapFromGlobal(QCursor.pos())
            if 0 <= pos_global.x() < canvas.width() and 0 <= pos_global.y() < canvas.height():
                pos = QPointF(float(pos_global.x()), float(pos_global.y()))
        except Exception:
            pass
        x = min(max(pos.x(), 0.0), max(0.0, float(canvas.width()) - 1e-6))
        y = min(max(pos.y(), 0.0), max(0.0, float(canvas.height()) - 1e-6))
        return QPointF(x, y)

    def on_paint_overlay(self, canvas, painter: QPainter):
        if self._contorno_hover_preview and not self._arrastando_molde:
            self._desenhar_contorno(canvas, painter, self._contorno_hover_preview, QColor("#8ed8ff"), 1.2)
        for idx in self._selecoes_manuais:
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                if el.get("tipo") == "polyline":
                    pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                    self._desenhar_contorno(canvas, painter, pts, QColor("#ff2fff"), 2.0)
        total_fixados = len(self._contornos_extraidos_preview)
        for idx, cont in enumerate(self._contornos_extraidos_preview):
            cor = QColor("#745cff") if total_fixados > 1 and idx % 2 else QColor("#0078ff")
            self._desenhar_contorno(canvas, painter, cont, cor, 2.4)
        if self._molde_criado and self._idx_selecionado is not None and 0 <= self._idx_selecionado < len(canvas.cena.elementos):
            self._desenhar_controles_molde(canvas, painter, canvas.cena.elementos[self._idx_selecionado])
        if self._ultimo_clique_falho is not None:
            pt = self._ultimo_clique_falho
            r = 1.8
            canvas._desenhar_segmento(
                painter,
                QPointF(pt.x() - r, pt.y() - r),
                QPointF(pt.x() + r, pt.y() + r),
                cor="#ff7a00",
                espessura=1.5,
            )
            canvas._desenhar_segmento(
                painter,
                QPointF(pt.x() - r, pt.y() + r),
                QPointF(pt.x() + r, pt.y() - r),
                cor="#ff7a00",
                espessura=1.5,
            )

    def _desenhar_contorno(self, canvas, painter, pontos: list[QPointF], cor: QColor, esp: float):
        if len(pontos) < 2:
            return
        for a, b in zip(pontos, pontos[1:]):
            canvas._desenhar_segmento(painter, a, b, cor=cor.name(), espessura=esp)

    def _preview_de_contorno(self, contorno: list[tuple[float, float]]) -> list[QPointF]:
        return [QPointF(float(x), float(y)) for x, y in contorno]

    def _fixar_contorno(self, canvas, contorno: list[tuple[float, float]], adicionar: bool) -> None:
        contorno = self._normalizar_pontos_contorno(contorno)
        if adicionar:
            if any(self._contornos_equivalentes(contorno, existente, tol=1e-4) for existente in self._contornos_auto_coords):
                self._contorno_hover_preview = []
                self._contornos_preparados = {}
                return
            self._contornos_auto_coords.append(contorno)
        else:
            self._contornos_auto_coords = [contorno]
        self._contornos_extraidos_preview = [self._preview_de_contorno(c) for c in self._contornos_auto_coords]
        self._contorno_hover_preview = []
        self._contornos_preparados = {}

    def _limpar_previews(self, canvas, msg: str) -> None:
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        self._contornos_auto_coords = []
        self._contornos_extraidos_preview = []
        self._contornos_preparados = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        canvas._selecionados = set()
        self.set_status(msg)

    def _posicao_arraste_inicial(self, canvas) -> QPointF:
        if self._ultima_pos_cena is not None:
            return QPointF(self._ultima_pos_cena)
        pontos = [pt for cont in self._contornos_auto_coords for pt in cont[:-1]]
        if pontos:
            x = sum(float(px) for px, _ in pontos) / len(pontos)
            y = sum(float(py) for _, py in pontos) / len(pontos)
            return QPointF(x, y)
        return QPointF(0.0, 0.0)

    def _extrair_e_iniciar_arraste(self, canvas, pos: QPointF) -> bool:
        ok = self._criar_molde(canvas)
        if not ok:
            return False
        self._ultimo_clique_falho = None
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        self._iniciar_arraste_molde(canvas, pos)
        self.set_status("Molde em maos: mova o mouse. Clique esquerdo solta, clique direito cancela.")
        canvas.update()
        return True

    def _alternar_candidato(self, canvas) -> None:
        total = len(self._contornos_candidatos)
        if total <= 0:
            return
        self._indice_candidato_atual = (self._indice_candidato_atual + 1) % total
        contorno = self._contornos_candidatos[self._indice_candidato_atual]
        contorno = self._normalizar_pontos_contorno(contorno)
        if self._contornos_auto_coords:
            self._contornos_auto_coords[-1] = contorno
            self._contornos_extraidos_preview = [self._preview_de_contorno(c) for c in self._contornos_auto_coords]
            self._contorno_hover_preview = []
            self._contornos_preparados = {}
        else:
            self._fixar_contorno(canvas, contorno, adicionar=False)
        self.set_status(f"Candidato {self._indice_candidato_atual + 1}/{total}. Tab alterna, Direito/Enter extrai.")
        canvas.update()

    def _deve_recalcular_hover(self, pos: QPointF) -> bool:
        if self._arrastando_molde:
            return False
        agora = monotonic()
        if self._ultimo_hover_pos is None:
            return True
        if (agora - self._ultimo_hover_tempo) < 0.08:
            return False
        dx = pos.x() - self._ultimo_hover_pos.x()
        dy = pos.y() - self._ultimo_hover_pos.y()
        return sqrt((dx * dx) + (dy * dy)) >= 0.15

    def _detectar_candidatos_contorno(
        self,
        canvas,
        pos: QPointF,
        leve: bool = False,
    ) -> list[list[tuple[float, float]]]:
        ponto = (pos.x(), pos.y())
        candidatos: list[list[tuple[float, float]]] = []
        raio = max(12.0, min(canvas.width(), canvas.height()) / max(canvas.zoom, 1e-6) * (0.25 if leve else 0.45))
        elementos_locais = self._elementos_proximos_para_extracao(canvas.cena.elementos, ponto, raio * 1.8)
        if not elementos_locais:
            elementos_locais = list(canvas.cena.elementos)
        tentativas = [
            lambda: extract_local_enclosing_contour(elementos_locais, ponto, search_radius=raio, tol=0.01),
            lambda: extract_smallest_enclosing_contour(elementos_locais, ponto, search_radius=raio, tol=0.01),
        ]
        if not leve:
            tentativas.append(lambda: self._detectar_contorno_fechado(canvas, pos))
        for tentativa in tentativas:
            try:
                contorno = tentativa()
            except Exception:
                contorno = None
            if contorno:
                self._adicionar_candidato_contorno(candidatos, ponto, contorno)
        for idx in self._indices_polylines_contem_ponto(canvas, pos):
            if 0 <= idx < len(canvas.cena.elementos):
                contorno = self._normalizar_pontos_contorno(canvas.cena.elementos[idx].get("pontos", []))
                self._adicionar_candidato_contorno(candidatos, ponto, contorno)
        candidatos.sort(key=lambda c: (abs(self._area_contorno(c)), self._perimetro_contorno(c)))
        return candidatos

    def _adicionar_candidato_contorno(
        self,
        candidatos: list[list[tuple[float, float]]],
        ponto: tuple[float, float],
        contorno: list[tuple[float, float]],
    ) -> None:
        contorno = self._normalizar_pontos_contorno(contorno)
        if len(contorno) < 4:
            return
        if not self._ponto_dentro_poligono_coords(ponto, contorno):
            return
        if abs(self._area_contorno(contorno)) <= 1e-8:
            return
        if any(self._contornos_equivalentes(contorno, existente, tol=1e-4) for existente in candidatos):
            return
        candidatos.append(contorno)

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

    def _escolher_melhor_candidato(self, canvas, candidatos: list[int]) -> int:
        """Escolhe o menor contorno válido sob o ponto (comportamento esperado para 'face interna')."""
        melhor_idx = candidatos[0]
        melhor_area = float("inf")
        for idx in candidatos:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in canvas.cena.elementos[idx].get("pontos", [])]
            area = self._area_poligono(pontos)
            if 1e-6 < area < melhor_area:
                melhor_area = area
                melhor_idx = idx
        return melhor_idx

    def _ponto_dentro_poligono(self, pt: QPointF, pontos: list[QPointF]) -> bool:
        polygon = [(p.x(), p.y()) for p in pontos]
        return self._ponto_dentro_poligono_coords((pt.x(), pt.y()), polygon)

    def _criar_molde(self, canvas) -> bool:
        if self._contornos_auto_coords:
            if len(self._contornos_auto_coords) > 1:
                contorno_unificado = self._unificar_contornos_extraidos(self._contornos_auto_coords)
                if contorno_unificado:
                    criou_unificado = self._criar_molde_de_contorno_extraido(canvas, contorno_unificado, limpar_estado=False)
                    if criou_unificado:
                        self.set_status("Partes selecionadas unificadas em um único molde.")
                        self._contornos_auto_coords = []
                        self._contornos_extraidos_preview = []
                        return True
            criou_algum = False
            for cont in self._contornos_auto_coords:
                criou_algum = self._criar_molde_de_contorno_extraido(canvas, cont, limpar_estado=False) or criou_algum
            if criou_algum:
                self._contornos_auto_coords = []
                self._contornos_extraidos_preview = []
            return criou_algum
        if not self._selecoes_manuais:
            return False
        idxs = sorted(self._selecoes_manuais)
        if len(idxs) > 1 and (self._cfg.get("compor_contornos") or self._cfg.get("modo") == "Manual"):
            return self._criar_molde_composto(canvas, idxs)
        criou = False
        novos_indices: list[int] = []
        for idx in idxs:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            try:
                pontos_base = self._contornos_preparados.get(idx, el.get("pontos", []))
                pontos_base = self._normalizar_pontos_contorno(pontos_base)
                payload = create_mold_payload({"tipo": "polyline", "pontos": pontos_base})
            except ValueError as exc:
                self.set_status(f"Contorno inválido no elemento {idx + 1}: {exc}")
                continue
            pontos_auxiliares: list[dict] = []
            novo = {
                "tipo": "polyline",
                "pontos": payload["pontos"],
                "molde": True,
                "nome_molde": self._proximo_nome_molde(canvas),
                "shape_id": payload["shape_id"],
                "node_ids": payload["node_ids"],
                "segment_ids": payload["segment_ids"],
                "controle_cantos": payload["controle_cantos"],
                "pontos_controle_principais": [],
                "pontos_auxiliares": pontos_auxiliares,
                "origem_contorno": idx,
            }
            self._enriquecer_metadados_molde(novo)
            canvas.cena.elementos.append(novo)
            novos_indices.append(len(canvas.cena.elementos) - 1)
            criou = True
        if novos_indices:
            self._idx_selecionado = novos_indices[-1]
            self._selecoes_manuais = set(novos_indices)
            canvas._selecionados = set(novos_indices)
        self._molde_criado = criou
        return criou

    def _criar_molde_composto(self, canvas, idxs: list[int]) -> bool:
        elementos = [canvas.cena.elementos[idx] for idx in idxs if 0 <= idx < len(canvas.cena.elementos)]
        elementos = [el for el in elementos if el.get("tipo") == "polyline"]
        if not elementos:
            return False
        try:
            elementos_para_compor = []
            for idx, el in zip(idxs, elementos):
                pontos = self._contornos_preparados.get(idx)
                if pontos:
                    elementos_para_compor.append({"tipo": "polyline", "pontos": pontos})
                else:
                    elementos_para_compor.append(el)
            pontos = compose_closed_contour(elementos_para_compor)
            pontos = self._normalizar_pontos_contorno(pontos)
            novo = {"tipo": "polyline", "pontos": pontos}
            payload = create_mold_payload(novo)
        except ValueError as exc:
            self.set_status(f"Falha ao compor contorno: {exc}")
            return False

        novo.update(
            {
                "pontos": payload["pontos"],
                "molde": True,
                "nome_molde": self._proximo_nome_molde(canvas),
                "shape_id": payload["shape_id"],
                "node_ids": payload["node_ids"],
                "segment_ids": payload["segment_ids"],
                "controle_cantos": payload["controle_cantos"],
                "pontos_controle_principais": [],
                "pontos_auxiliares": [],
                "origens_contorno": idxs,
            }
        )
        self._enriquecer_metadados_molde(novo)
        canvas.cena.elementos.append(novo)
        self._idx_selecionado = len(canvas.cena.elementos) - 1
        self._selecoes_manuais = {self._idx_selecionado}
        canvas._selecionados = {self._idx_selecionado}
        self._molde_criado = True
        return True

    def _criar_molde_de_contorno_extraido(self, canvas, pontos: list[tuple[float, float]], limpar_estado: bool = True) -> bool:
        try:
            pontos = self._normalizar_pontos_contorno(pontos)
            payload = create_mold_payload({"tipo": "polyline", "pontos": pontos})
        except ValueError as exc:
            self.set_status(f"Contorno detectado inválido: {exc}")
            return False
        novo = {
            "tipo": "polyline",
            "pontos": payload["pontos"],
            "molde": True,
            "nome_molde": self._proximo_nome_molde(canvas),
            "shape_id": payload["shape_id"],
            "node_ids": payload["node_ids"],
            "segment_ids": payload["segment_ids"],
            "controle_cantos": payload["controle_cantos"],
            "pontos_controle_principais": [],
            "pontos_auxiliares": [],
            "origem_extracao": "face_auto" if self._cfg.get("modo") == "Automático" else "contorno",
            "pontos_controle_referencia": self._coletar_pontos_controle_existentes(canvas, payload["pontos"]),
            "pontos_interseccao_referencia": self._coletar_interseccoes_no_contorno(canvas, payload["pontos"]),
        }
        self._enriquecer_metadados_molde(novo)
        canvas.cena.elementos.append(novo)
        self._idx_selecionado = len(canvas.cena.elementos) - 1
        self._selecoes_manuais = {self._idx_selecionado}
        canvas._selecionados = {self._idx_selecionado}
        self._molde_criado = True
        if limpar_estado:
            self._contornos_auto_coords = []
            self._contornos_extraidos_preview = []
        return True

    def _unificar_contornos_extraidos(self, contornos: list[list[tuple[float, float]]]) -> list[tuple[float, float]] | None:
        """
        Tenta unificar múltiplos fechamentos selecionados em um único contorno.
        Estratégia:
          1) coleta todos os segmentos dos contornos selecionados;
          2) remove segmentos internos compartilhados (aparecem duas vezes);
          3) recompõe o perímetro externo restante.
        """
        if len(contornos) < 2:
            return contornos[0] if contornos else None

        tol = 1e-4

        def _kpt(p: tuple[float, float]) -> tuple[int, int]:
            return (round(float(p[0]) / tol), round(float(p[1]) / tol))

        segmentos: dict[tuple[tuple[int, int], tuple[int, int]], dict] = {}
        for cont in contornos:
            if len(cont) < 2:
                continue
            for a, b in zip(cont, cont[1:]):
                ka = _kpt(a)
                kb = _kpt(b)
                if ka == kb:
                    continue
                chave = (ka, kb) if ka <= kb else (kb, ka)
                info = segmentos.setdefault(chave, {"count": 0, "segmento": (a, b)})
                info["count"] += 1

        elementos_borda: list[dict] = []
        for info in segmentos.values():
            if info["count"] % 2 == 1:
                a, b = info["segmento"]
                elementos_borda.append({"tipo": "polyline", "pontos": [a, b]})

        if not elementos_borda:
            return None

        try:
            return compose_closed_contour(elementos_borda, tol=1e-3)
        except ValueError:
            return None

    def _extrair_indice(self, canvas, idx: int):
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        metadados = self._extrair_metadados(pontos)
        if self._cfg["quebrar_auxiliares"]:
            limpo = self._remover_segmentos_auxiliares([(p.x(), p.y()) for p in pontos], metadados)
            pontos = [QPointF(float(x), float(y)) for x, y in limpo]
        # Manter o contorno fiel: a opção de conversão não deve destruir o perímetro extraído.
        pontos = [QPointF(float(x), float(y)) for x, y in self._normalizar_pontos_contorno([(p.x(), p.y()) for p in pontos])]
        self._contornos_extraidos_preview = [pontos]
        self._contornos_preparados[idx] = [(p.x(), p.y()) for p in pontos]
        self._molde_criado = False

    def _enriquecer_metadados_molde(self, molde: dict):
        pontos = self._normalizar_pontos_contorno(molde.get("pontos", []))
        if len(pontos) < 4:
            return

        base = pontos[:-1]
        xs = [x for x, _ in base]
        ys = [y for _, y in base]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)

        molde["pontos"] = pontos
        molde.setdefault("molde_id", str(uuid4()))
        molde.setdefault("fio_angulo", 0.0)

        largura = max(xs) - min(xs)
        margem = largura * 0.20
        molde.setdefault("fio_origem", (min(xs) + margem, cy))
        molde.setdefault("fio_fim", (max(xs) - margem, cy))
        molde.setdefault("mostrar_nome", True)
        molde.setdefault("mostrar_fio", True)
        molde.setdefault("mostrar_controles", True)
        molde.setdefault("molde_pronto", True)
        molde.setdefault("permitir_alteracoes_encaixe", True)

        if bool(molde.get("preservar_todos_vertices_controle")):
            cantos = list(base)
            indices_cantos = list(range(len(base)))
        else:
            indices_cantos = self._indices_controles_principais(base)
            cantos = [base[i] for i in indices_cantos]
        for ref in molde.get("pontos_controle_referencia", []) or []:
            if not isinstance(ref, (list, tuple)) or len(ref) != 2:
                continue
            cantos.append((float(ref[0]), float(ref[1])))
        for ref in molde.get("pontos_interseccao_referencia", []) or []:
            if not isinstance(ref, (list, tuple)) or len(ref) != 2:
                continue
            cantos.append((float(ref[0]), float(ref[1])))
        cantos = self._deduplicar_pontos(cantos, tol=1e-4)
        molde["controle_cantos"] = [(float(x), float(y)) for x, y in cantos]

        usar_auxiliares = bool(self._cfg.get("usar_auxiliares", True))
        if usar_auxiliares and len(indices_cantos) >= 2:
            auxiliares = self._calcular_auxiliares_no_contorno(base, indices_cantos)
        else:
            auxiliares = []

        molde["controle_auxiliares"] = [(float(x), float(y)) for x, y in auxiliares]
        molde["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in molde["controle_cantos"]]
        molde["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in molde["controle_auxiliares"]]

    def _coletar_pontos_controle_existentes(self, canvas, contorno: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if not contorno:
            return []
        pontos_ref: list[tuple[float, float]] = []
        for el in canvas.cena.elementos:
            candidatos: list[tuple[float, float]] = []
            for x, y in el.get("controle_cantos", []) or []:
                candidatos.append((float(x), float(y)))
            for p in el.get("pontos_controle_principais", []) or []:
                if isinstance(p, dict):
                    candidatos.append((float(p.get("x", 0.0)), float(p.get("y", 0.0))))
            for pt in candidatos:
                if self._ponto_no_contorno(pt, contorno, tol=0.08):
                    pontos_ref.append(pt)
        return self._deduplicar_pontos(pontos_ref, tol=1e-4)

    def _ponto_no_contorno(self, ponto: tuple[float, float], contorno: list[tuple[float, float]], tol: float) -> bool:
        px, py = ponto
        for a, b in zip(contorno, contorno[1:]):
            if self._ponto_no_segmento((px, py), a, b, tol):
                return True
        return False

    def _deduplicar_pontos(self, pontos: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []
        for x, y in pontos:
            if not any(abs(x - sx) <= tol and abs(y - sy) <= tol for sx, sy in saida):
                saida.append((float(x), float(y)))
        return saida

    def _coletar_interseccoes_no_contorno(self, canvas, contorno: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(contorno) < 2:
            return []
        xs = [x for x, _ in contorno]
        ys = [y for _, y in contorno]
        min_x, max_x = min(xs) - 0.2, max(xs) + 0.2
        min_y, max_y = min(ys) - 0.2, max(ys) + 0.2

        segmentos: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for el in canvas.cena.elementos:
            pts = polyline_from_element(el)
            for a, b in zip(pts, pts[1:]):
                seg_min_x = min(a[0], b[0])
                seg_max_x = max(a[0], b[0])
                seg_min_y = min(a[1], b[1])
                seg_max_y = max(a[1], b[1])
                if seg_max_x < min_x or seg_min_x > max_x or seg_max_y < min_y or seg_min_y > max_y:
                    continue
                segmentos.append((a, b))

        inters: list[tuple[float, float]] = []
        for i in range(len(segmentos)):
            a, b = segmentos[i]
            for j in range(i + 1, len(segmentos)):
                c, d = segmentos[j]
                pt = self._intersecao_segmentos(a, b, c, d, tol=1e-7)
                if pt is None:
                    continue
                if self._ponto_no_contorno(pt, contorno, tol=0.08):
                    inters.append(pt)
        return self._deduplicar_pontos(inters, tol=1e-4)

    def _intersecao_segmentos(
        self,
        a: tuple[float, float],
        b: tuple[float, float],
        c: tuple[float, float],
        d: tuple[float, float],
        tol: float,
    ) -> tuple[float, float] | None:
        ax, ay = a
        bx, by = b
        cx, cy = c
        dx, dy = d
        r = (bx - ax, by - ay)
        s = (dx - cx, dy - cy)
        rxs = (r[0] * s[1]) - (r[1] * s[0])
        q_p = (cx - ax, cy - ay)
        if abs(rxs) <= tol:
            return None
        t = ((q_p[0] * s[1]) - (q_p[1] * s[0])) / rxs
        u = ((q_p[0] * r[1]) - (q_p[1] * r[0])) / rxs
        # Considera apenas interseções internas aos segmentos para evitar
        # transformar todos os vértices da aproximação da curva em "cruzamentos".
        if tol < t < (1.0 - tol) and tol < u < (1.0 - tol):
            return (ax + t * r[0], ay + t * r[1])
        return None

    def _finalizar_posicionamento(self, canvas, msg: str):
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._indices_molde_em_arraste = set()
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        self._ultimo_hover_pos = None
        self._molde_posicionado = False
        self._molde_criado = False
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contornos_extraidos_preview = []
        self._contornos_auto_coords = []
        self._contornos_preparados = {}
        canvas._selecionados = set()
        if self._dialog is None or not isValid(self._dialog):
            self._abrir_config(canvas)
        else:
            if not self._dialog.isVisible():
                self._dialog.show()
            self._reposicionar_dialog_config(canvas)
            self._dialog.raise_()
        canvas._registrar_historico()
        self.set_status(msg)
        canvas.update()

    def _iniciar_arraste_molde(self, canvas, pos: QPointF):
        self._snapshot_cancelamento = {idx: deepcopy(canvas.cena.elementos[idx]) for idx in self._selecoes_manuais if 0 <= idx < len(canvas.cena.elementos)}
        self._indices_molde_em_arraste = set(self._selecoes_manuais)
        self._arrastando_molde = True
        self._ultimo_pos_arrasto = QPointF(pos)

    def _cancelar_arraste_molde(self, canvas):
        for idx in sorted(self._indices_molde_em_arraste, reverse=True):
            if 0 <= idx < len(canvas.cena.elementos):
                canvas.cena.elementos.pop(idx)
        self._indices_molde_em_arraste = set()
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        self._ultimo_hover_pos = None
        if self._dialog is not None and isValid(self._dialog):
            self._dialog.hide()
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contornos_extraidos_preview = []
        self._contornos_auto_coords = []
        self._contornos_preparados = {}
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        canvas._selecionados = set()
        self.set_status("Extração cancelada. Clique esquerdo para selecionar novamente.")

    def _limpar_estado_extracao(self, canvas, msg: str):
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contornos_extraidos_preview = []
        self._contornos_auto_coords = []
        self._contornos_preparados = {}
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        self._ultimo_hover_pos = None
        self._molde_criado = False
        self._molde_posicionado = False
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._indices_molde_em_arraste = set()
        self._contorno_hover_preview = []
        self._contornos_candidatos = []
        self._indice_candidato_atual = 0
        self._ultimo_hover_pos = None
        if self._dialog is not None and isValid(self._dialog):
            self._dialog.hide()
        canvas._selecionados = set()
        self.set_status(msg)

    def _mostrar_aviso_sem_molde(self, canvas, pos_clique: QPointF | None = None):
        self._limpar_estado_extracao(canvas, "Não foi possível encontrar molde!")
        self._ultimo_clique_falho = QPointF(pos_clique) if pos_clique is not None else None
        QMessageBox.warning(canvas, "Atenção", "Não foi possível encontrar molde!")
        canvas.update()

    def _perimetro_contorno(self, contorno: list[tuple[float, float]]) -> float:
        return polyline_perimeter(contorno)

    def _detectar_candidatos_contorno(
        self,
        canvas,
        pos: QPointF,
        leve: bool = False,
    ) -> list[list[tuple[float, float]]]:
        ponto = (pos.x(), pos.y())
        candidatos: list[list[tuple[float, float]]] = []
        raio = max(12.0, min(canvas.width(), canvas.height()) / max(canvas.zoom, 1e-6) * (0.25 if leve else 0.45))
        elementos = self._elementos_proximos_para_extracao(canvas.cena.elementos, ponto, raio * 1.8)
        if not elementos:
            elementos = list(canvas.cena.elementos)
        tentativas = [
            lambda: extract_local_enclosing_contour(elementos, ponto, search_radius=raio, tol=0.01),
            lambda: extract_smallest_enclosing_contour(elementos, ponto, search_radius=raio, tol=0.01),
        ]
        if not leve:
            tentativas.append(lambda: self._detectar_contorno_fechado(canvas, pos))
        for tentativa in tentativas:
            try:
                cont = tentativa()
            except Exception:
                cont = None
            if cont:
                self._adicionar_candidato_contorno(candidatos, ponto, cont)
        for idx in self._indices_polylines_contem_ponto(canvas, pos):
            if 0 <= idx < len(canvas.cena.elementos):
                cont = self._normalizar_pontos_contorno(canvas.cena.elementos[idx].get("pontos", []))
                self._adicionar_candidato_contorno(candidatos, ponto, cont)
        candidatos.sort(key=lambda c: (abs(self._area_contorno(c)), self._perimetro_contorno(c)))
        return candidatos

    def _detectar_candidatos_linha_manual(
        self,
        canvas,
        pos: QPointF,
        leve: bool = False,
    ) -> list[list[tuple[float, float]]]:
        candidatos = self._detectar_candidatos_contorno(canvas, pos, leve=leve)
        ponto = (pos.x(), pos.y())
        tolerancia = self._tolerancia_clique_linha(canvas)
        filtrados = [
            cont
            for cont in candidatos
            if self._distancia_ponto_contorno(ponto, cont) <= tolerancia
        ]
        if filtrados:
            return filtrados

        for cont in self._contornos_fechados_proximos_da_linha(canvas, ponto, tolerancia):
            self._adicionar_candidato_contorno(filtrados, ponto, cont)
        filtrados.sort(key=lambda c: (self._distancia_ponto_contorno(ponto, c), abs(self._area_contorno(c))))
        return filtrados

    def _tolerancia_clique_linha(self, canvas) -> float:
        return max(0.12, 8.0 / max(float(getattr(canvas, "zoom", 1.0)), 1e-6))

    def _contornos_fechados_proximos_da_linha(
        self,
        canvas,
        ponto: tuple[float, float],
        tolerancia: float,
    ) -> list[list[tuple[float, float]]]:
        saida: list[list[tuple[float, float]]] = []
        for el in canvas.cena.elementos:
            if el.get("tipo") != "polyline":
                continue
            cont = self._normalizar_pontos_contorno(el.get("pontos", []))
            if len(cont) < 4:
                continue
            if self._dist_tuple(cont[0], cont[-1]) > 1e-6:
                continue
            if self._distancia_ponto_contorno(ponto, cont) <= tolerancia:
                saida.append(cont)
        return saida

    def _detectar_contorno_fechado(self, canvas, pos: QPointF) -> list[tuple[float, float]] | None:
        ponto = (pos.x(), pos.y())
        inicio_busca = monotonic()
        limite_tempo_s = 2.2
        tentativas_local = 0
        tentativas_fallback = 0
        total_elementos = len(canvas.cena.elementos)
        self._log_extracao(f"início busca ponto={ponto} elementos={total_elementos}")

        # Caminho rápido principal: considera fechamentos por elementos locais,
        # incluindo curvas internas que dividem uma polyline fechada maior.
        # usa grafo planar local no raio de 20 cm, retornando a menor face válida.
        pontos_teste = [ponto]
        desloc = max(0.01, self.TOLERANCIA_FECHAMENTO_CM * 0.5)
        for dx, dy in ((desloc, 0.0), (-desloc, 0.0), (0.0, desloc), (0.0, -desloc)):
            pontos_teste.append((ponto[0] + dx, ponto[1] + dy))
        raio_base = max(20.0, min(canvas.width(), canvas.height()) / max(canvas.zoom, 1e-6) * 0.45)
        raios_busca = [20.0, raio_base, raio_base * 1.7]
        raios_ordenados: list[float] = []
        for r in raios_busca:
            if not any(abs(r - ex) <= 1e-6 for ex in raios_ordenados):
                raios_ordenados.append(r)
        raio_max_local = max(raios_ordenados) if raios_ordenados else 20.0
        elementos_locais = self._elementos_proximos_para_extracao(canvas.cena.elementos, ponto, raio_max_local * 1.8)
        if not elementos_locais:
            elementos_locais = list(canvas.cena.elementos)
        self._log_extracao(
            f"pré-filtro local: elementos_locais={len(elementos_locais)} raio_max={raio_max_local:.2f} zoom={canvas.zoom:.4f}"
        )

        # Micro-faces: tentativa dedicada para fechamentos muito pequenos.
        # Estratégia de "onda local": expande raios curtos e pequenas perturbações
        # do ponto de clique para capturar faces mínimas.
        micro_sementes = [ponto]
        micro_d = max(0.002, self.TOLERANCIA_FECHAMENTO_CM * 0.08)
        for dx, dy in (
            (micro_d, 0.0), (-micro_d, 0.0), (0.0, micro_d), (0.0, -micro_d),
            (micro_d, micro_d), (micro_d, -micro_d), (-micro_d, micro_d), (-micro_d, -micro_d),
        ):
            micro_sementes.append((ponto[0] + dx, ponto[1] + dy))
        melhor_micro: list[tuple[float, float]] | None = None
        melhor_micro_area = float("inf")
        for raio_micro in (2.0, 4.0, 8.0):
            for tol_micro in (0.0005, 0.001, 0.002, 0.005):
                for semente in micro_sementes:
                    if (monotonic() - inicio_busca) > limite_tempo_s:
                        return melhor_micro
                    tentativas_local += 1
                    cont_micro = extract_smallest_enclosing_contour(
                        elementos_locais,
                        semente,
                        tol=tol_micro,
                        search_radius=raio_micro,
                    )
                    if not cont_micro:
                        continue
                    if not self._ponto_dentro_poligono_coords(ponto, cont_micro):
                        continue
                    area_micro = abs(self._area_contorno(cont_micro))
                    if area_micro <= 1e-10:
                        continue
                    if area_micro < melhor_micro_area:
                        melhor_micro = cont_micro
                        melhor_micro_area = area_micro
        if melhor_micro is not None:
            self._log_extracao(
                f"sucesso micro-face em {(monotonic()-inicio_busca):.3f}s area={melhor_micro_area:.8f}"
            )
            return melhor_micro
        for raio_local in raios_ordenados:
            for tol_local in (0.005, 0.01, 0.02):
                for pt in pontos_teste:
                    tentativas_local += 1
                    if (monotonic() - inicio_busca) > limite_tempo_s:
                        self._log_extracao(
                            f"timeout local após {tentativas_local} tentativas em {(monotonic()-inicio_busca):.3f}s"
                        )
                        return None
                    contorno_local = extract_local_enclosing_contour(
                        elementos_locais,
                        pt,
                        search_radius=raio_local,
                        tol=tol_local,
                    )
                    if contorno_local and self._ponto_dentro_poligono_coords(ponto, contorno_local):
                        self._log_extracao(
                            f"sucesso local em {(monotonic()-inicio_busca):.3f}s tentativas_local={tentativas_local}"
                        )
                        return contorno_local

        # Fallback: quando não houver face local válida, usa polyline fechada já existente.
        candidatos = self._indices_polylines_contem_ponto(canvas, pos)
        if candidatos:
            melhor_idx = self._escolher_melhor_candidato(canvas, candidatos)
            if 0 <= melhor_idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[melhor_idx]
                pontos_el = self._normalizar_pontos_contorno(el.get("pontos", []))
                if len(pontos_el) >= 4:
                    return pontos_el

        melhor: list[tuple[float, float]] | None = None
        melhor_dist = float("inf")
        melhor_area = float("inf")
        raio_busca = max(0.02, self.TOLERANCIA_FECHAMENTO_CM * 2.0)

        sementes = [ponto]
        for fator in (1.0, 1.8):
            r = raio_busca * fator
            for dx, dy in ((r, 0.0), (-r, 0.0), (0.0, r), (0.0, -r), (r, r), (r, -r), (-r, r), (-r, -r)):
                sementes.append((ponto[0] + dx, ponto[1] + dy))

        raio_cena_base = max(4.0, min(canvas.width(), canvas.height()) / max(canvas.zoom, 1e-6) * 0.35)
        estrategias = [
            {"tolerancias": (0.001, 0.01), "sementes": sementes[:5], "search_radius": raio_cena_base},
            {"tolerancias": (0.03, self.TOLERANCIA_FECHAMENTO_CM), "sementes": sementes, "search_radius": raio_cena_base * 1.6},
            {"tolerancias": (0.20,), "sementes": sementes, "search_radius": raio_max_local * 2.2},
        ]

        for etapa in estrategias:
            encontrou_na_etapa = False
            for tol in etapa["tolerancias"]:
                for semente in etapa["sementes"]:
                    tentativas_fallback += 1
                    if (monotonic() - inicio_busca) > limite_tempo_s:
                        self._log_extracao(
                            f"timeout fallback após {tentativas_fallback} tentativas em {(monotonic()-inicio_busca):.3f}s"
                        )
                        return melhor
                    contorno = extract_smallest_enclosing_contour(
                        elementos_locais,
                        semente,
                        tol=tol,
                        search_radius=etapa["search_radius"],
                    )
                    if not contorno:
                        continue
                    if not self._ponto_dentro_poligono_coords(ponto, contorno):
                        continue
                    area = abs(self._area_contorno(contorno))
                    if area <= 1e-8:
                        continue
                    dist_contorno = self._distancia_ponto_contorno(ponto, contorno)
                    if (dist_contorno < melhor_dist - 1e-6) or (
                        abs(dist_contorno - melhor_dist) <= 1e-6 and area < melhor_area
                    ):
                        melhor = contorno
                        melhor_dist = dist_contorno
                        melhor_area = area
                        encontrou_na_etapa = True
            if encontrou_na_etapa and melhor is not None:
                self._log_extracao(
                    f"sucesso fallback em {(monotonic()-inicio_busca):.3f}s tentativas_fallback={tentativas_fallback}"
                )
                return melhor
        self._log_extracao(
            f"fim sem contorno em {(monotonic()-inicio_busca):.3f}s "
            f"tentativas_local={tentativas_local} tentativas_fallback={tentativas_fallback}"
        )
        return melhor

    def _elementos_proximos_para_extracao(
        self,
        elementos: list[dict],
        ponto: tuple[float, float],
        raio: float,
    ) -> list[dict]:
        px, py = ponto
        min_x, max_x = px - raio, px + raio
        min_y, max_y = py - raio, py + raio
        filtrados: list[dict] = []
        for el in elementos:
            pts = polyline_from_element(el)
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if max(xs) < min_x or min(xs) > max_x or max(ys) < min_y or min(ys) > max_y:
                continue
            filtrados.append(el)
        return filtrados

    def _log_extracao(self, msg: str):
        if not self._log_extracao_habilitado:
            return
        print(f"[extrair_molde][perf] {msg}")

    def _contornos_equivalentes(
        self,
        a: list[tuple[float, float]],
        b: list[tuple[float, float]],
        tol: float = 1e-5,
    ) -> bool:
        na = self._normalizar_pontos_contorno(a)
        nb = self._normalizar_pontos_contorno(b)
        if len(na) != len(nb):
            return False
        if len(na) < 2:
            return False
        ba = na[:-1]
        bb = nb[:-1]
        if len(ba) != len(bb):
            return False
        n = len(ba)
        for shift in range(n):
            ok = True
            for i in range(n):
                ax, ay = ba[i]
                bx, by = bb[(i + shift) % n]
                if abs(ax - bx) > tol or abs(ay - by) > tol:
                    ok = False
                    break
            if ok:
                return True
        return False

    def _ponto_dentro_poligono_coords(self, pt: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
        if len(polygon) < 3:
            return False
        poly = list(polygon)
        if self._dist_tuple(poly[0], poly[-1]) > 1e-6:
            poly.append(poly[0])
        x, y = pt
        inside = False
        for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
            # Conta ponto no contorno como "dentro" para melhorar UX do clique.
            if self._ponto_no_segmento((x, y), (x1, y1), (x2, y2), tol=1e-6):
                return True
            cruza = (y1 > y) != (y2 > y)
            if not cruza:
                continue
            y_delta = y2 - y1
            if abs(y_delta) <= 1e-12:
                continue
            x_intersec = ((x2 - x1) * (y - y1) / y_delta) + x1
            if x <= x_intersec:
                inside = not inside
        return inside

    def _ponto_no_segmento(
        self,
        p: tuple[float, float],
        a: tuple[float, float],
        b: tuple[float, float],
        tol: float,
    ) -> bool:
        px, py = p
        ax, ay = a
        bx, by = b
        abx = bx - ax
        aby = by - ay
        apx = px - ax
        apy = py - ay
        cruz = abs((abx * apy) - (aby * apx))
        if cruz > tol:
            return False
        dot = (apx * abx) + (apy * aby)
        if dot < -tol:
            return False
        ab2 = (abx * abx) + (aby * aby)
        if dot - ab2 > tol:
            return False
        return True

    def _area_contorno(self, contorno: list[tuple[float, float]]) -> float:
        if len(contorno) < 3:
            return 0.0
        acc = 0.0
        for (ax, ay), (bx, by) in zip(contorno, contorno[1:]):
            acc += (ax * by) - (bx * ay)
        return 0.5 * acc

    def _distancia_ponto_contorno(self, ponto: tuple[float, float], contorno: list[tuple[float, float]]) -> float:
        px, py = ponto
        menor = float("inf")
        for (ax, ay), (bx, by) in zip(contorno, contorno[1:]):
            dist = point_segment_distance((px, py), (ax, ay), (bx, by))
            if dist < menor:
                menor = dist
        return menor

    def _aplicar_delta_selecionados(self, canvas, dx: float, dy: float):
        for idx in sorted(self._selecoes_manuais):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                el["pontos"] = [(x + dx, y + dy) for x, y in el.get("pontos", [])]
                if "controle_cantos" in el:
                    el["controle_cantos"] = self._mover_pontos_controle(el.get("controle_cantos", []), dx, dy)
                if "controle_auxiliares" in el:
                    el["controle_auxiliares"] = self._mover_pontos_controle(el.get("controle_auxiliares", []), dx, dy)
                if "pontos_controle_principais" in el:
                    el["pontos_controle_principais"] = self._mover_pontos_controle(el.get("pontos_controle_principais", []), dx, dy)
                if "pontos_auxiliares" in el:
                    el["pontos_auxiliares"] = self._mover_pontos_controle(el.get("pontos_auxiliares", []), dx, dy)
                if "fio_origem" in el:
                    fx, fy = el.get("fio_origem", (0.0, 0.0))
                    el["fio_origem"] = (float(fx) + dx, float(fy) + dy)
                if "fio_fim" in el:
                    fx, fy = el.get("fio_fim", (0.0, 0.0))
                    el["fio_fim"] = (float(fx) + dx, float(fy) + dy)

    def _mover_pontos_controle(self, valor, dx: float, dy: float):
        if isinstance(valor, dict):
            movido = {}
            for chave, ponto in valor.items():
                movido[chave] = self._mover_ponto_controle(ponto, dx, dy)
            return movido
        if isinstance(valor, list):
            return [self._mover_ponto_controle(p, dx, dy) for p in valor]
        return valor

    def _mover_ponto_controle(self, ponto, dx: float, dy: float):
        if isinstance(ponto, dict):
            novo = dict(ponto)
            novo["x"] = float(novo.get("x", 0.0)) + dx
            novo["y"] = float(novo.get("y", 0.0)) + dy
            return novo
        if isinstance(ponto, (list, tuple)) and len(ponto) >= 2:
            movido = (float(ponto[0]) + dx, float(ponto[1]) + dy)
            if isinstance(ponto, list):
                return [*movido, *ponto[2:]]
            return (*movido, *ponto[2:])
        return ponto

    def _restaurar_snapshot(self, canvas):
        for idx, el in self._snapshot_cancelamento.items():
            if 0 <= idx < len(canvas.cena.elementos):
                canvas.cena.elementos[idx] = deepcopy(el)

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
        if not principais:
            principais = [QPointF(float(x), float(y)) for x, y in el.get("controle_cantos", [])]
        if not auxiliares:
            auxiliares = [QPointF(float(x), float(y)) for x, y in el.get("controle_auxiliares", [])]
        if not principais:
            return
        cx = sum(p.x() for p in principais) / len(principais)
        cy = sum(p.y() for p in principais) / len(principais)
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        for i, pt in enumerate(principais, start=1):
            tela = canvas._cena_para_tela(pt)
            painter.setPen(QPen(QColor("#ffffff"), 1.2))
            painter.setBrush(QColor("#101010"))
            painter.drawRect(int(tela.x() - 4), int(tela.y() - 4), 8, 8)
            painter.setPen(QColor("#ffffff"))
            dx = pt.x() - cx
            dy = pt.y() - cy
            mod = max(1e-6, sqrt((dx * dx) + (dy * dy)))
            off_x = (dx / mod) * 10.0
            off_y = (dy / mod) * 10.0
            painter.drawText(int(tela.x() + off_x), int(tela.y() + off_y), str(i))
        painter.setPen(QPen(QColor("#ff2a2a"), 1))
        painter.setBrush(QColor("#ff2a2a"))
        for pt in auxiliares:
            tela = canvas._cena_para_tela(pt)
            painter.drawEllipse(tela, 2.0, 2.0)

    def _eh_fechado(self, pontos: list[QPointF]) -> bool:
        return len(pontos) >= 3 and self._dist(pontos[0], pontos[-1]) <= 0.001

    def _abrir_config(self, canvas):
        cls = type(self)
        if not cls._ui_global_disponivel():
            dialog = QDialog(canvas)
            dialog.setObjectName("guimma_extrair_molde_config")
            dialog.setWindowTitle("Definir contorno")
            dialog.setWindowFlags(Qt.Tool)
            dialog.setModal(False)
            dialog.setFixedWidth(262)
            dialog.setStyleSheet(
                """
                QDialog {
                    background: #ffffff;
                    color: #111111;
                }
                QLabel {
                    color: #111111;
                    font-size: 12px;
                }
                QWidget#painelDefinirContorno {
                    background: #ffffff;
                }
                QComboBox {
                    background: #ffffff;
                    color: #111111;
                    border: 1px solid #7db5dd;
                    border-radius: 0px;
                    min-height: 22px;
                    padding: 0 22px 0 6px;
                }
                QComboBox:hover { border: 1px solid #5ca0d1; }
                QComboBox:focus { border: 1px solid #4b90c3; }
                QComboBox::drop-down {
                    width: 20px;
                    border-left: 1px solid #7db5dd;
                    background: #d8edf9;
                }
                QCheckBox {
                    color: #111111;
                    font-size: 12px;
                    spacing: 6px;
                    padding: 1px 0;
                }
                QCheckBox::indicator { width: 12px; height: 12px; }
                QFrame#linhaSeparadora {
                    background: #b7b7b7;
                    min-height: 1px;
                    max-height: 1px;
                    border: none;
                }
                """
            )

            lay = QVBoxLayout(dialog)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(4)

            painel = QWidget(dialog)
            painel.setObjectName("painelDefinirContorno")
            painel_lay = QVBoxLayout(painel)
            painel_lay.setContentsMargins(0, 0, 0, 0)
            painel_lay.setSpacing(4)
            lay.addWidget(painel)

            painel_lay.addWidget(QLabel("Modo"))

            cls._cmb_modo_global = QComboBox()
            cls._cmb_modo_global.addItems(["Automático", "Manual"])
            cls._cmb_modo_global.setFixedWidth(140)
            painel_lay.addWidget(cls._cmb_modo_global, 0, Qt.AlignRight)

            cls._chk_grad_global = QCheckBox("Detectar graduações")
            cls._chk_piques_global = QCheckBox("Detectar piques")
            cls._chk_aux_global = QCheckBox("Detectar linhas auxiliares")
            cls._chk_compor_global = QCheckBox("Compor contornos")
            cls._chk_usar_global = QCheckBox("Usar linhas auxiliares")
            cls._chk_quebrar_global = QCheckBox("Quebrar linhas auxiliares")
            cls._chk_converter_global = QCheckBox("Converter primitivas em linhas auxiliares")

            painel_lay.addWidget(cls._chk_grad_global)
            painel_lay.addWidget(cls._chk_piques_global)
            painel_lay.addWidget(cls._chk_aux_global)

            separador = QFrame()
            separador.setObjectName("linhaSeparadora")
            painel_lay.addWidget(separador)

            for chk in (cls._chk_compor_global, cls._chk_usar_global, cls._chk_quebrar_global, cls._chk_converter_global):
                painel_lay.addWidget(chk)

            cls._cmb_modo_global.currentTextChanged.connect(self._salvar_cfg_global)
            for chk in (
                cls._chk_grad_global, cls._chk_piques_global, cls._chk_aux_global,
                cls._chk_compor_global, cls._chk_usar_global, cls._chk_quebrar_global, cls._chk_converter_global,
            ):
                chk.toggled.connect(self._salvar_cfg_global)

            cls._dialog_global = dialog
            dialog.destroyed.connect(lambda *_: type(self)._limpar_referencias_ui_global())
            self._aplicar_cfg_na_ui()
        else:
            self._aplicar_cfg_na_ui()

        self._dialog = cls._dialog_global
        self.cmb_modo = cls._cmb_modo_global
        self.chk_grad = cls._chk_grad_global
        self.chk_piques = cls._chk_piques_global
        self.chk_aux = cls._chk_aux_global
        self.chk_compor = cls._chk_compor_global
        self.chk_usar = cls._chk_usar_global
        self.chk_quebrar = cls._chk_quebrar_global
        self.chk_converter = cls._chk_converter_global

        if self._dialog and not self._dialog.isVisible():
            self._dialog.adjustSize()
            self._dialog.show()
        elif self._dialog:
            self._dialog.raise_()
            self._dialog.activateWindow()
        self._reposicionar_dialog_config(canvas)

    def _reposicionar_dialog_config(self, canvas):
        if not self._dialog or not isValid(self._dialog):
            return
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            destino_local = canvas.calcular_posicao_painel_auxiliar(
                self._dialog.width(),
                self._dialog.height(),
                abaixo_coordenadas=True,
            )
            self._dialog.move(canvas.mapToGlobal(destino_local))

    def _salvar_cfg(self, *_):
        self._salvar_cfg_global()
        self._sincronizar_cfg_da_ui()
        canvas = getattr(self, "_canvas", None)
        if canvas is not None:
            self.salvar_preferencias_ferramenta(canvas, type(self)._cfg_global)

    @classmethod
    def _salvar_cfg_global(cls, *_):
        if not cls._ui_global_disponivel():
            return
        cls._cfg_global.update(
            {
                "modo": cls._cmb_modo_global.currentText(),
                "detectar_graduacoes": cls._chk_grad_global.isChecked() if cls._chk_grad_global else True,
                "detectar_piques": cls._chk_piques_global.isChecked() if cls._chk_piques_global else True,
                "detectar_auxiliares": cls._chk_aux_global.isChecked() if cls._chk_aux_global else False,
                "compor_contornos": cls._chk_compor_global.isChecked() if cls._chk_compor_global else True,
                "usar_auxiliares": cls._chk_usar_global.isChecked() if cls._chk_usar_global else True,
                "quebrar_auxiliares": cls._chk_quebrar_global.isChecked() if cls._chk_quebrar_global else True,
                "converter_auxiliares": cls._chk_converter_global.isChecked() if cls._chk_converter_global else True,
            }
        )

    def _aplicar_cfg_na_ui(self):
        cls = type(self)
        if not cls._ui_global_disponivel():
            return
        cls._cmb_modo_global.setCurrentText(str(self._cfg.get("modo", cls._cfg_global["modo"])))
        cls._chk_grad_global.setChecked(bool(self._cfg.get("detectar_graduacoes", cls._cfg_global["detectar_graduacoes"])))
        cls._chk_piques_global.setChecked(bool(self._cfg.get("detectar_piques", cls._cfg_global["detectar_piques"])))
        cls._chk_aux_global.setChecked(bool(self._cfg.get("detectar_auxiliares", cls._cfg_global["detectar_auxiliares"])))
        cls._chk_compor_global.setChecked(bool(self._cfg.get("compor_contornos", cls._cfg_global["compor_contornos"])))
        cls._chk_usar_global.setChecked(bool(self._cfg.get("usar_auxiliares", cls._cfg_global["usar_auxiliares"])))
        cls._chk_quebrar_global.setChecked(bool(self._cfg.get("quebrar_auxiliares", cls._cfg_global["quebrar_auxiliares"])))
        cls._chk_converter_global.setChecked(bool(self._cfg.get("converter_auxiliares", cls._cfg_global["converter_auxiliares"])))
        cls._salvar_cfg_global()

    def _sincronizar_cfg_da_ui(self):
        type(self)._salvar_cfg_global()
        self._cfg = dict(type(self)._cfg_global)

    def _normalizar_pontos_contorno(self, pontos: list[tuple[float, float]] | list) -> list[tuple[float, float]]:
        coords: list[tuple[float, float]] = []
        for x, y in pontos:
            pt = (float(x), float(y))
            if not coords or self._dist_tuple(coords[-1], pt) > 1e-6:
                coords.append(pt)
        if len(coords) < 2:
            return coords
        if self._dist_tuple(coords[0], coords[-1]) > 1e-6:
            coords.append(coords[0])
        if len(coords) >= 3 and self._dist_tuple(coords[-2], coords[-1]) <= 1e-6:
            coords.pop(-1)
            if self._dist_tuple(coords[0], coords[-1]) > 1e-6:
                coords.append(coords[0])
        return coords

    def _indices_controles_principais(self, base: list[tuple[float, float]]) -> list[int]:
        if len(base) <= 4:
            return list(range(len(base)))
        if self._eh_quase_circulo(base):
            return self._indices_para_circulo(base)

        candidatos = self._indices_por_angulo(base)
        if len(candidatos) < 4:
            candidatos = self._indices_por_amostragem(base, 4)
        return candidatos

    def _indices_por_angulo(self, base: list[tuple[float, float]]) -> list[int]:
        n = len(base)
        if n < 3:
            return list(range(n))
        saida: list[int] = []
        limite = 132.0 if self._cfg.get("detectar_piques", True) else 125.0
        perimetro = 0.0
        for i in range(n):
            perimetro += self._dist_tuple(base[i], base[(i + 1) % n])
        dist_min = max(1.5, perimetro * 0.06)

        for i in range(n):
            a = QPointF(*base[i - 1])
            b = QPointF(*base[i])
            c = QPointF(*base[(i + 1) % n])
            ang = self._angulo_interno(a, b, c)
            if ang <= limite:
                if not saida or self._dist_tuple(base[saida[-1]], base[i]) >= dist_min:
                    saida.append(i)

        if len(saida) >= 2 and self._dist_tuple(base[saida[0]], base[saida[-1]]) < dist_min:
            saida.pop()
        return saida

    def _indices_por_amostragem(self, base: list[tuple[float, float]], quantidade: int, indices_originais: list[int] | None = None) -> list[int]:
        if not base:
            return []
        qtd = max(4, min(int(quantidade), len(base)))
        passo = len(base) / float(qtd)
        saida: list[int] = []
        usados = set()
        for i in range(qtd):
            idx_local = int(round(i * passo)) % len(base)
            while idx_local in usados and len(usados) < len(base):
                idx_local = (idx_local + 1) % len(base)
            usados.add(idx_local)
            idx_real = indices_originais[idx_local] if indices_originais is not None else idx_local
            saida.append(idx_real)
        return saida

    def _eh_quase_circulo(self, base: list[tuple[float, float]]) -> bool:
        if len(base) < 8:
            return False
        xs = [x for x, _ in base]
        ys = [y for _, y in base]
        largura = max(xs) - min(xs)
        altura = max(ys) - min(ys)
        if largura <= 1e-6 or altura <= 1e-6:
            return False
        proporcao = largura / max(altura, 1e-6)
        if not 0.8 <= proporcao <= 1.25:
            return False
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        raios = [sqrt((x - cx) ** 2 + (y - cy) ** 2) for x, y in base]
        media = sum(raios) / len(raios)
        if media <= 1e-6:
            return False
        variacao = max(raios) - min(raios)
        cantos_agudos = 0
        for i in range(len(base)):
            a = QPointF(*base[i - 1])
            b = QPointF(*base[i])
            c = QPointF(*base[(i + 1) % len(base)])
            if self._angulo_interno(a, b, c) < 120.0:
                cantos_agudos += 1
        return (variacao / media) <= 0.20 and cantos_agudos <= 2

    def _indices_para_circulo(self, base: list[tuple[float, float]]) -> list[int]:
        xs = [x for x, _ in base]
        ys = [y for _, y in base]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        alvos = [
            (cx, min(ys)),
            (max(xs), cy),
            (cx, max(ys)),
            (min(xs), cy),
        ]
        indices: list[int] = []
        usados = set()
        for ax, ay in alvos:
            melhor_idx = min(range(len(base)), key=lambda i: ((base[i][0] - ax) ** 2 + (base[i][1] - ay) ** 2) + (1e6 if i in usados else 0.0))
            usados.add(melhor_idx)
            indices.append(melhor_idx)
        return indices

    def _calcular_auxiliares_no_contorno(self, base: list[tuple[float, float]], indices_cantos: list[int]) -> list[tuple[float, float]]:
        if len(indices_cantos) < 2:
            return []
        n = len(base)
        cantos_set = set(indices_cantos)
        aux: list[tuple[float, float]] = []
        perimetro = 0.0
        for i in range(n):
            perimetro += self._dist_tuple(base[i], base[(i + 1) % n])
        dist_min = max(0.8, perimetro * 0.03)
        ultimo_idx: int | None = None
        for i in range(n):
            if i in cantos_set:
                continue
            a = QPointF(*base[i - 1])
            b = QPointF(*base[i])
            c = QPointF(*base[(i + 1) % n])
            ang = self._angulo_interno(a, b, c)
            if ang < 132.0:
                continue
            if ultimo_idx is not None and self._dist_tuple(base[ultimo_idx], base[i]) < dist_min:
                continue
            aux.append((float(base[i][0]), float(base[i][1])))
            ultimo_idx = i
        return aux

    def _dist_tuple(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)

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

    def _area_poligono(self, pontos: list[QPointF]) -> float:
        if len(pontos) < 3:
            return 0.0
        poly = pontos if self._dist(pontos[0], pontos[-1]) <= 0.001 else [*pontos, pontos[0]]
        area2 = 0.0
        for a, b in zip(poly, poly[1:]):
            area2 += (a.x() * b.y()) - (b.x() * a.y())
        return abs(area2) * 0.5

    def _angulo_interno(self, a: QPointF, b: QPointF, c: QPointF) -> float:
        return internal_angle((a.x(), a.y()), (b.x(), b.y()), (c.x(), c.y()))
