from __future__ import annotations

from copy import deepcopy
from math import atan2, ceil, cos, pi, sin, sqrt
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

from core.formatacao import formatar_numero
from core.graduacao import aplicar_grade_graduacao_referencia_canvas
from core.geometry.engine import internal_angle, point_segment_distance, polyline_perimeter
from core.geometry_bridge_accelerated import (
    compose_closed_contour,
    create_mold_payload,
    extract_local_enclosing_contour,
    extract_smallest_enclosing_contour,
    polyline_from_element,
)
from tools.tool_base import FerramentaBase
from tools.movimento_utils import mover_elemento_por_delta
from ui.posicao_janelas import ajustar_para_area, instalar_memoria_posicao


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
    _log_extracao_habilitado = os.environ.get("GUIMMA_EXTRACAO_LOG", "0").strip().lower() not in {"0", "false", "off", "no"}

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
        self._origem_arrasto_molde: QPointF | None = None
        self._angulo_arrasto_molde: float | None = None
        self._guia_arrasto_angular: tuple[QPointF, QPointF, float] | None = None
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
        self._origem_arrasto_molde = None
        self._angulo_arrasto_molde = None
        self._guia_arrasto_angular = None
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
        self._origem_arrasto_molde = None
        self._angulo_arrasto_molde = None
        self._guia_arrasto_angular = None
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
            if self._contornos_auto_coords:
                event.accept()
                return True
            pos_tela_exata = self._posicao_tela_exata_no_canvas(canvas, event.position())
            pos_cena = canvas._tela_para_cena(pos_tela_exata)
            self._ultima_pos_cena = QPointF(pos_cena)
            if self._deve_recalcular_hover(pos_cena):
                if self._deve_usar_hover_rapido(canvas):
                    candidatos = []
                elif self._cfg.get("modo") == "Manual":
                    candidatos = self._detectar_candidatos_linha_manual(canvas, pos_cena, leve=True)
                else:
                    candidatos = self._detectar_candidatos_contorno(canvas, pos_cena, leve=True)
                self._contorno_hover_preview = self._preview_de_contorno(candidatos[0]) if candidatos else []
                self._ultimo_hover_tempo = monotonic()
                self._ultimo_hover_pos = QPointF(pos_cena)
                canvas.update()
            event.accept()
            return True
        pos_real = canvas._tela_para_cena(self._posicao_tela_exata_no_canvas(canvas, event.position()))
        self._ultima_pos_cena = QPointF(pos_real)
        pos = self._posicao_arrasto_com_restricao(canvas, QPointF(pos_real))
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
        if self._arrastando_molde and self._guia_arrasto_angular is not None:
            self._desenhar_guia_arrasto_angular(canvas, painter)

    def _desenhar_contorno(self, canvas, painter, pontos: list[QPointF], cor: QColor, esp: float):
        if len(pontos) < 2:
            return
        for a, b in zip(pontos, pontos[1:]):
            canvas._desenhar_segmento(painter, a, b, cor=cor.name(), espessura=esp)

    def _desenhar_guia_arrasto_angular(self, canvas, painter: QPainter) -> None:
        if self._guia_arrasto_angular is None:
            return
        origem, destino, angulo = self._guia_arrasto_angular
        canvas._desenhar_segmento(painter, origem, destino, cor="#d000d0", espessura=1.0)
        try:
            destino_tela = canvas._cena_para_tela(destino)
        except Exception:
            return
        painter.save()
        painter.setPen(QPen(QColor("#d000d0"), 1))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(destino_tela + QPointF(4.0, -4.0), f"{angulo:g}°")
        painter.restore()

    def _preview_de_contorno(self, contorno: list[tuple[float, float]]) -> list[QPointF]:
        pontos = self._normalizar_pontos_contorno(contorno)
        max_preview = 260
        if len(pontos) > max_preview:
            passo = max(1, int(ceil(len(pontos) / max_preview)))
            base = pontos[:-1] if self._dist_tuple(pontos[0], pontos[-1]) <= 1e-6 else pontos
            pontos = base[::passo]
            if pontos and self._dist_tuple(pontos[0], pontos[-1]) > 1e-6:
                pontos.append(pontos[0])
        return [QPointF(float(x), float(y)) for x, y in pontos]

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

    def _deve_usar_hover_rapido(self, canvas) -> bool:
        total = len(getattr(getattr(canvas, "cena", None), "elementos", []) or [])
        if total > 80:
            return True
        zoom = float(getattr(canvas, "zoom", 1.0) or 1.0)
        return total > 40 and zoom < 0.45

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
                ponto_emenda = self._referencia_emenda_contorno(pontos_base)
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
                "ponto_emenda_referencia": ponto_emenda,
            }
            self._enriquecer_metadados_molde(novo)
            canvas.cena.elementos.append(novo)
            novos_indices.append(len(canvas.cena.elementos) - 1)
            criou = True
        if novos_indices:
            self._idx_selecionado = novos_indices[-1]
            self._selecoes_manuais = set(novos_indices)
            canvas._selecionados = set()
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
            emendas_origem = self._coletar_emendas_fechamento_no_contorno(canvas, payload["pontos"])
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
                "pontos_emenda_referencia": emendas_origem,
            }
        )
        self._enriquecer_metadados_molde(novo, canvas)
        canvas.cena.elementos.append(novo)
        self._idx_selecionado = len(canvas.cena.elementos) - 1
        self._selecoes_manuais = {self._idx_selecionado}
        canvas._selecionados = set()
        self._molde_criado = True
        return True

    def _criar_molde_de_contorno_extraido(self, canvas, pontos: list[tuple[float, float]], limpar_estado: bool = True) -> bool:
        try:
            pontos = self._normalizar_pontos_contorno(pontos)
            payload = create_mold_payload({"tipo": "polyline", "pontos": pontos})
            emendas_origem = self._coletar_emendas_fechamento_no_contorno(canvas, payload["pontos"])
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
            "pontos_emenda_referencia": emendas_origem,
            "pontos_controle_referencia": self._coletar_pontos_controle_existentes(canvas, payload["pontos"]),
            "pontos_interseccao_referencia": self._coletar_interseccoes_no_contorno(canvas, payload["pontos"]),
        }
        self._enriquecer_metadados_molde(novo, canvas)
        canvas.cena.elementos.append(novo)
        self._idx_selecionado = len(canvas.cena.elementos) - 1
        self._selecoes_manuais = {self._idx_selecionado}
        canvas._selecionados = set()
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

    def _enriquecer_metadados_molde(self, molde: dict, canvas=None):
        pontos = self._normalizar_pontos_contorno(molde.get("pontos", []))
        if len(pontos) < 4:
            return

        base = pontos[:-1]
        layout_visual = self._layout_visual_interno(base, str(molde.get("nome_molde") or ""))

        molde["pontos"] = pontos
        self._aplicar_estilo_atual_molde(molde)
        molde.setdefault("molde_id", str(uuid4()))
        self._aplicar_layout_visual_interno_molde(molde, base, layout_visual)
        molde.setdefault("numero_altura_cm", 0.7)
        molde.setdefault("mostrar_nome", True)
        molde.setdefault("mostrar_fio", True)
        molde.setdefault("mostrar_numeros", True)
        molde.setdefault("mostrar_controles", True)
        molde.setdefault("molde_pronto", True)
        molde.setdefault("permitir_alteracoes_encaixe", True)
        aplicar_grade_graduacao_referencia_canvas(molde, canvas or self._canvas, sobrescrever=True)

        refs_emenda = self._referencias_emenda_molde(molde, pontos)
        refs_controle = list(molde.get("pontos_controle_referencia", []) or [])
        refs_interseccao = list(molde.get("pontos_interseccao_referencia", []) or [])
        refs_explicitas = bool(refs_controle or refs_interseccao)

        if bool(molde.get("preservar_todos_vertices_controle")):
            indices_cantos = list(range(len(base)))
        elif refs_explicitas:
            indices_cantos = []
        else:
            indices_por_angulo = self._indices_por_angulo(base)
            if refs_emenda and not indices_por_angulo and self._eh_forma_fechada_suave(base):
                indices_cantos = []
            else:
                indices_cantos = indices_por_angulo or self._indices_controles_principais(base)
        for ref in refs_emenda:
            if not isinstance(ref, (list, tuple)) or len(ref) != 2:
                continue
            idx_ref = self._indice_mais_proximo_no_contorno((float(ref[0]), float(ref[1])), base)
            if idx_ref is not None:
                indices_cantos.append(idx_ref)
        for ref in refs_controle:
            if not isinstance(ref, (list, tuple)) or len(ref) != 2:
                continue
            idx_ref = self._indice_mais_proximo_no_contorno((float(ref[0]), float(ref[1])), base)
            if idx_ref is not None:
                indices_cantos.append(idx_ref)
        for ref in refs_interseccao:
            if not isinstance(ref, (list, tuple)) or len(ref) != 2:
                continue
            idx_ref = self._indice_mais_proximo_no_contorno((float(ref[0]), float(ref[1])), base)
            if idx_ref is not None:
                indices_cantos.append(idx_ref)
        indices_cantos = sorted({int(i) % len(base) for i in indices_cantos if 0 <= int(i) < len(base)})
        cantos = [base[i] for i in indices_cantos]
        cantos = self._ordenar_controles_principais_extraidos(cantos)
        molde["controle_cantos"] = [(float(x), float(y)) for x, y in cantos]

        usar_auxiliares = bool(self._cfg.get("usar_auxiliares", True))
        if usar_auxiliares and len(indices_cantos) >= 1:
            auxiliares = self._calcular_auxiliares_no_contorno(base, indices_cantos)
        else:
            auxiliares = []

        molde["controle_auxiliares"] = [(float(x), float(y)) for x, y in auxiliares]
        molde["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in molde["controle_cantos"]]
        molde["pontos_graduacao"] = [{"x": float(x), "y": float(y)} for x, y in base]
        molde["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in molde["controle_auxiliares"]]

    def _aplicar_estilo_atual_molde(self, molde: dict) -> None:
        canvas = getattr(self, "_canvas", None)
        esp_padrao = max(1.0, float(getattr(canvas, "_linha_espessura", molde.get("espessura", 1.0)) or 1.0))
        molde["espessura"] = max(1.0, float(molde.get("espessura", esp_padrao) or esp_padrao))
        molde["espessura_graduacao"] = max(
            1.0,
            float(molde.get("espessura_graduacao", molde.get("espessura", esp_padrao)) or esp_padrao),
        )
        molde.setdefault("estilo", getattr(canvas, "_linha_estilo", "solid"))
        molde.setdefault("amplitude", getattr(canvas, "_linha_amplitude", 1.0))

    def _ordenar_controles_principais_extraidos(self, cantos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(cantos) != 2:
            return cantos
        return sorted(cantos, key=lambda pt: (float(pt[0]), float(pt[1])))

    def _referencia_emenda_contorno(self, pontos: list[tuple[float, float]] | list) -> tuple[float, float] | None:
        contorno = self._normalizar_pontos_contorno(pontos)
        if not contorno:
            return None
        x, y = contorno[0]
        return (float(x), float(y))

    def _coletar_emendas_fechamento_no_contorno(self, canvas, contorno: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if not contorno or not hasattr(canvas, "cena"):
            return []
        contorno_ref = self._normalizar_pontos_contorno(contorno)
        if len(contorno_ref) < 4:
            return []
        emendas: list[tuple[float, float]] = []
        for el in getattr(canvas.cena, "elementos", []) or []:
            if not isinstance(el, dict) or el.get("molde") or el.get("tipo") != "polyline":
                continue
            pontos_raw = self._pontos_elemento_como_tuplas(el.get("pontos", []) or [])
            if len(pontos_raw) < 3:
                continue
            fechado = self._dist_tuple(pontos_raw[0], pontos_raw[-1]) <= max(0.15, self.TOLERANCIA_FECHAMENTO_CM)
            if not fechado and not bool(el.get("fechado")):
                continue
            pontos_el = self._normalizar_pontos_contorno(pontos_raw)
            if not self._contorno_origem_corresponde_ao_extraido(pontos_el, contorno_ref):
                continue
            emenda = (float(pontos_raw[0][0]), float(pontos_raw[0][1]))
            if self._ponto_no_contorno(emenda, contorno_ref, tol=0.18):
                emendas.append(emenda)
        return self._deduplicar_pontos(emendas, tol=1e-4)

    def _contorno_origem_corresponde_ao_extraido(
        self,
        origem: list[tuple[float, float]],
        extraido: list[tuple[float, float]],
    ) -> bool:
        origem = self._normalizar_pontos_contorno(origem)
        extraido = self._normalizar_pontos_contorno(extraido)
        if len(origem) < 4 or len(extraido) < 4:
            return False
        per_origem = max(1e-9, self._perimetro_contorno(origem))
        per_extraido = max(1e-9, self._perimetro_contorno(extraido))
        if abs(per_origem - per_extraido) / max(per_origem, per_extraido) > 0.08:
            return False
        area_origem = max(1e-9, abs(self._area_contorno(origem)))
        area_extraido = max(1e-9, abs(self._area_contorno(extraido)))
        if abs(area_origem - area_extraido) / max(area_origem, area_extraido) > 0.08:
            return False
        tolerancia = max(0.12, per_extraido * 0.002)
        pontos = origem[:-1]
        if not pontos:
            return False
        acertos = sum(1 for pt in pontos if self._ponto_no_contorno(pt, extraido, tol=tolerancia))
        return acertos >= max(3, int(round(len(pontos) * 0.65)))

    @staticmethod
    def _pontos_elemento_como_tuplas(pontos: list) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []
        for item in pontos:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                try:
                    saida.append((float(item[0]), float(item[1])))
                except Exception:
                    continue
        return saida

    def _referencias_emenda_molde(self, molde: dict, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        refs: list[tuple[float, float]] = []

        def adicionar(valor) -> None:
            if isinstance(valor, (list, tuple)) and len(valor) == 2:
                try:
                    refs.append((float(valor[0]), float(valor[1])))
                except Exception:
                    pass

        adicionar(molde.get("ponto_emenda_referencia"))
        for valor in molde.get("pontos_emenda_referencia", []) or []:
            adicionar(valor)
        return self._deduplicar_pontos(refs, tol=1e-4)

    def _layout_visual_interno(self, base: list[tuple[float, float]], nome: str) -> dict:
        bbox = self._bbox_tuple(base)
        faixas = self._faixas_horizontais_internas(base)
        ponto_texto, altura_texto = self._layout_nome_interno(base, faixas, nome, bbox)
        fio_origem, fio_fim = self._layout_fio_interno(base, faixas, ponto_texto, altura_texto, bbox)
        comprimento_fio = self._dist_tuple(fio_origem, fio_fim)
        return {
            "ponto_texto": ponto_texto,
            "texto_nome_altura_cm": altura_texto,
            "fio_origem": fio_origem,
            "fio_fim": fio_fim,
            "tam_fio": max(0.15, min(0.8, comprimento_fio * 0.12)),
        }

    def _aplicar_layout_visual_interno_molde(self, molde: dict, base: list[tuple[float, float]], layout: dict) -> None:
        ponto_texto = layout["ponto_texto"]
        altura_nome = float(layout["texto_nome_altura_cm"])
        fio_origem = layout["fio_origem"]
        fio_fim = layout["fio_fim"]

        molde["ponto_texto"] = (float(ponto_texto[0]), float(ponto_texto[1]))
        molde["ponto_texto_nome"] = molde["ponto_texto"]
        molde["nome_posicao"] = molde["ponto_texto"]
        molde["nome_centro"] = molde["ponto_texto"]
        molde["texto_nome_altura_cm"] = altura_nome
        molde["referencia_texto_nome"] = "Livre"
        molde["alinhamento_texto_nome"] = "Centro"
        molde.setdefault("texto_nome_angulo", 0.0)

        if not self._segmento_interno_poligono(fio_origem, fio_fim, base):
            fio_origem, fio_fim = self._layout_fio_interno(
                base,
                self._faixas_horizontais_internas(base),
                ponto_texto,
                altura_nome,
                self._bbox_tuple(base),
            )
        molde["fio_origem"] = (float(fio_origem[0]), float(fio_origem[1]))
        molde["fio_fim"] = (float(fio_fim[0]), float(fio_fim[1]))
        molde["fio_angulo"] = 0.0
        molde["tam_fio"] = layout["tam_fio"]
        molde["tamanho_fio"] = layout["tam_fio"]
        molde["fonte_fio"] = layout["tam_fio"]

    def _layout_nome_interno(
        self,
        base: list[tuple[float, float]],
        faixas: list[dict],
        nome: str,
        bbox: tuple[float, float, float, float],
    ) -> tuple[tuple[float, float], float]:
        texto = str(nome or "K").strip() or "K"
        min_x, min_y, max_x, max_y = bbox
        cy = (min_y + max_y) / 2.0
        altura_bbox = max(0.1, max_y - min_y)
        melhor: tuple[tuple[float, float], float, float] | None = None
        for faixa in sorted(faixas, key=lambda f: (abs(float(f["y"]) - cy), -float(f["largura"]))):
            largura_util = max(0.0, float(faixa["largura"]) - (2.0 * self._margem_faixa(float(faixa["largura"]))))
            altura = min(3.0, altura_bbox * 0.32, self._altura_texto_maxima_por_largura(texto, largura_util))
            altura = max(0.18, altura)
            centro = ((float(faixa["x1"]) + float(faixa["x2"])) / 2.0, float(faixa["y"]))
            for passo in range(18):
                fator = 1.0 - (passo * 0.055)
                altura_teste = max(0.16, altura * fator)
                if self._texto_nome_cabe_no_poligono(base, centro, texto, altura_teste):
                    score = (altura_teste * 100.0) + float(faixa["largura"]) - (abs(float(faixa["y"]) - cy) * 0.5)
                    if melhor is None or score > melhor[2]:
                        melhor = (centro, altura_teste, score)
                    break
        if melhor is not None:
            return melhor[0], melhor[1]
        centro = self._ponto_interno_fallback(base, bbox)
        return centro, max(0.16, min(0.45, altura_bbox * 0.08))

    def _layout_fio_interno(
        self,
        base: list[tuple[float, float]],
        faixas: list[dict],
        ponto_texto: tuple[float, float],
        altura_texto: float,
        bbox: tuple[float, float, float, float],
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        min_x, min_y, max_x, max_y = bbox
        altura_bbox = max(0.1, max_y - min_y)
        desejado = float(ponto_texto[1]) + max(altura_texto * 1.45, altura_bbox * 0.08)
        candidatos = sorted(
            faixas,
            key=lambda f: (-(float(f["largura"])), abs(float(f["y"]) - desejado)),
        )
        for faixa in candidatos:
            largura = float(faixa["largura"])
            if largura <= 0.12:
                continue
            margem = self._margem_faixa(largura)
            reserva_rotulo = max(0.25, min(1.2, largura * 0.18))
            x1 = float(faixa["x1"]) + margem
            x2 = float(faixa["x2"]) - margem - reserva_rotulo
            if x2 - x1 < max(0.18, largura * 0.28):
                x2 = float(faixa["x2"]) - margem
            if x2 <= x1:
                continue
            p1 = (x1, float(faixa["y"]))
            p2 = (x2, float(faixa["y"]))
            if self._segmento_interno_poligono(p1, p2, base):
                return p1, p2
        centro = self._ponto_interno_fallback(base, bbox)
        comprimento = max(0.1, min(1.0, (max_x - min_x) * 0.12))
        p1 = (centro[0] - comprimento / 2.0, centro[1])
        p2 = (centro[0] + comprimento / 2.0, centro[1])
        return (p1, p2) if self._segmento_interno_poligono(p1, p2, base) else (centro, centro)

    def _faixas_horizontais_internas(self, base: list[tuple[float, float]], amostras: int = 45) -> list[dict]:
        if len(base) < 3:
            return []
        min_x, min_y, max_x, max_y = self._bbox_tuple(base)
        altura = max_y - min_y
        if altura <= 1e-9:
            return []
        margem_y = max(0.01, altura * 0.025)
        y0 = min_y + margem_y
        y1 = max_y - margem_y
        if y1 <= y0:
            y0, y1 = min_y, max_y
        valores_y = []
        total = max(5, int(amostras))
        for idx in range(total):
            t = idx / max(1, total - 1)
            valores_y.append(y0 + ((y1 - y0) * t))
        valores_y.append((min_y + max_y) / 2.0)

        faixas: list[dict] = []
        vistos: set[tuple[int, int, int]] = set()
        for y in valores_y:
            for x_inicio, x_fim in self._intervalos_horizontais_poligono(base, y):
                largura = x_fim - x_inicio
                if largura <= 0.05:
                    continue
                centro = ((x_inicio + x_fim) / 2.0, y)
                if not self._ponto_dentro_poligono_coords(centro, base):
                    continue
                chave = (round(y * 1000), round(x_inicio * 1000), round(x_fim * 1000))
                if chave in vistos:
                    continue
                vistos.add(chave)
                faixas.append({"y": float(y), "x1": float(x_inicio), "x2": float(x_fim), "largura": float(largura)})
        return faixas

    def _intervalos_horizontais_poligono(self, base: list[tuple[float, float]], y: float) -> list[tuple[float, float]]:
        poly = list(base)
        if self._dist_tuple(poly[0], poly[-1]) > 1e-6:
            poly.append(poly[0])
        xs: list[float] = []
        for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
            if abs(y2 - y1) <= 1e-12:
                continue
            if (y1 <= y < y2) or (y2 <= y < y1):
                t = (y - y1) / (y2 - y1)
                xs.append(x1 + ((x2 - x1) * t))
        xs.sort()
        limpos: list[float] = []
        for x in xs:
            if not limpos or abs(x - limpos[-1]) > 1e-7:
                limpos.append(float(x))
        return [(limpos[i], limpos[i + 1]) for i in range(0, len(limpos) - 1, 2)]

    def _texto_nome_cabe_no_poligono(
        self,
        base: list[tuple[float, float]],
        centro: tuple[float, float],
        texto: str,
        altura_cm: float,
    ) -> bool:
        largura, altura = self._dimensoes_texto_aproximadas(texto, altura_cm)
        cx, cy = centro
        margem = max(0.02, altura_cm * 0.08)
        meia_larg = (largura / 2.0) + margem
        meia_alt = (altura / 2.0) + margem
        pontos = [
            (cx - meia_larg, cy - meia_alt),
            (cx + meia_larg, cy - meia_alt),
            (cx + meia_larg, cy + meia_alt),
            (cx - meia_larg, cy + meia_alt),
            (cx, cy),
            (cx - meia_larg, cy),
            (cx + meia_larg, cy),
            (cx, cy - meia_alt),
            (cx, cy + meia_alt),
        ]
        return all(self._ponto_dentro_poligono_coords(p, base) for p in pontos)

    @staticmethod
    def _dimensoes_texto_aproximadas(texto: str, altura_cm: float) -> tuple[float, float]:
        linhas = str(texto or "K").splitlines() or ["K"]
        caracteres = max(1, max(len(linha) for linha in linhas))
        altura = max(0.01, float(altura_cm)) * max(1, len(linhas)) * 1.15
        largura = max(float(altura_cm), caracteres * float(altura_cm) * 0.72)
        return largura, altura

    def _altura_texto_maxima_por_largura(self, texto: str, largura_util: float) -> float:
        linhas = str(texto or "K").splitlines() or ["K"]
        caracteres = max(1, max(len(linha) for linha in linhas))
        return max(0.16, float(largura_util) / max(1.0, caracteres * 0.72))

    def _segmento_interno_poligono(
        self,
        inicio: tuple[float, float],
        fim: tuple[float, float],
        base: list[tuple[float, float]],
    ) -> bool:
        for passo in range(11):
            t = passo / 10.0
            ponto = (
                float(inicio[0]) + ((float(fim[0]) - float(inicio[0])) * t),
                float(inicio[1]) + ((float(fim[1]) - float(inicio[1])) * t),
            )
            if not self._ponto_dentro_poligono_coords(ponto, base):
                return False
        return True

    def _ponto_interno_fallback(
        self,
        base: list[tuple[float, float]],
        bbox: tuple[float, float, float, float],
    ) -> tuple[float, float]:
        min_x, min_y, max_x, max_y = bbox
        centro = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
        if self._ponto_dentro_poligono_coords(centro, base):
            return centro
        for faixa in sorted(self._faixas_horizontais_internas(base), key=lambda f: -float(f["largura"])):
            return ((float(faixa["x1"]) + float(faixa["x2"])) / 2.0, float(faixa["y"]))
        return (float(base[0][0]), float(base[0][1])) if base else (0.0, 0.0)

    @staticmethod
    def _bbox_tuple(base: list[tuple[float, float]]) -> tuple[float, float, float, float]:
        xs = [float(x) for x, _ in base]
        ys = [float(y) for _, y in base]
        return min(xs), min(ys), max(xs), max(ys)

    @staticmethod
    def _margem_faixa(largura: float) -> float:
        return max(0.08, min(0.75, float(largura) * 0.10))

    def _coletar_pontos_controle_existentes(self, canvas, contorno: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if not contorno:
            return []
        pontos_ref: list[tuple[float, float]] = []
        for el in canvas.cena.elementos:
            if not el.get("molde"):
                continue
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

    def _indice_mais_proximo_no_contorno(
        self,
        ponto: tuple[float, float],
        base: list[tuple[float, float]],
        tol: float = 0.12,
    ) -> int | None:
        if not base:
            return None
        melhor = min(range(len(base)), key=lambda i: self._dist_tuple(ponto, base[i]))
        return melhor if self._dist_tuple(ponto, base[melhor]) <= tol else None

    def _coletar_interseccoes_no_contorno(self, canvas, contorno: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(contorno) < 2:
            return []
        xs = [x for x, _ in contorno]
        ys = [y for _, y in contorno]
        min_x, max_x = min(xs) - 0.2, max(xs) + 0.2
        min_y, max_y = min(ys) - 0.2, max(ys) + 0.2

        segmentos: list[tuple[tuple[float, float], tuple[float, float], int]] = []
        for el_idx, el in enumerate(canvas.cena.elementos):
            pts = polyline_from_element(el)
            for a, b in zip(pts, pts[1:]):
                seg_min_x = min(a[0], b[0])
                seg_max_x = max(a[0], b[0])
                seg_min_y = min(a[1], b[1])
                seg_max_y = max(a[1], b[1])
                if seg_max_x < min_x or seg_min_x > max_x or seg_max_y < min_y or seg_min_y > max_y:
                    continue
                segmentos.append((a, b, el_idx))

        inters: list[tuple[float, float]] = self._coletar_vertices_origem_no_contorno(canvas, contorno)
        inters.extend(self._coletar_encontros_linhas_no_contorno(segmentos, contorno))

        for i in range(len(segmentos)):
            a, b, origem_a = segmentos[i]
            for j in range(i + 1, len(segmentos)):
                c, d, origem_b = segmentos[j]
                if origem_a == origem_b:
                    continue
                pt = self._intersecao_segmentos(a, b, c, d, tol=1e-7)
                if pt is None:
                    continue
                if self._ponto_no_contorno(pt, contorno, tol=0.08):
                    inters.append(pt)
        inters = self._deduplicar_pontos(inters, tol=1e-4)
        return self._filtrar_referencias_colineares_no_contorno(inters, contorno)

    def _filtrar_referencias_colineares_no_contorno(
        self,
        referencias: list[tuple[float, float]],
        contorno: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        if not referencias:
            return []
        base = self._normalizar_pontos_contorno(contorno)
        if len(base) >= 2 and self._dist_tuple(base[0], base[-1]) <= 1e-6:
            base = base[:-1]
        if len(base) < 3:
            return referencias
        saida: list[tuple[float, float]] = []
        for ref in referencias:
            idx = self._indice_mais_proximo_no_contorno(ref, base, tol=0.08)
            if idx is None:
                saida.append(ref)
                continue
            anterior = base[idx - 1]
            atual = base[idx]
            proximo = base[(idx + 1) % len(base)]
            if self._dist_tuple(anterior, atual) <= 1e-7 or self._dist_tuple(atual, proximo) <= 1e-7:
                continue
            if self._desvio_angular_vertice(anterior, atual, proximo) < 6.0:
                continue
            saida.append(ref)
        return self._deduplicar_pontos(saida, tol=1e-4)

    def _coletar_vertices_origem_no_contorno(self, canvas, contorno: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(contorno) < 2 or not hasattr(canvas, "cena"):
            return []
        vertices: list[tuple[float, float]] = []
        for el in getattr(canvas.cena, "elementos", []) or []:
            if not isinstance(el, dict) or el.get("molde"):
                continue
            pontos = self._vertices_reais_elemento(el)
            if not pontos:
                continue
            for idx, ponto in enumerate(pontos):
                if not self._ponto_no_contorno(ponto, contorno, tol=0.08):
                    continue
                if self._vertice_origem_e_canto_real(el, pontos, idx):
                    vertices.append(ponto)
        return self._deduplicar_pontos(vertices, tol=1e-4)

    def _vertices_reais_elemento(self, elemento: dict) -> list[tuple[float, float]]:
        tipo = str(elemento.get("tipo") or "").strip()
        if tipo == "bezier_quadratica":
            pontos: list[tuple[float, float]] = []
            for chave in ("p0", "p2"):
                valor = elemento.get(chave)
                if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                    try:
                        pontos.append((float(valor[0]), float(valor[1])))
                    except (TypeError, ValueError):
                        pass
            return pontos
        return self._pontos_elemento_como_tuplas(elemento.get("pontos", []) or [])

    def _vertice_origem_e_canto_real(self, elemento: dict, pontos: list[tuple[float, float]], idx: int) -> bool:
        if not (0 <= int(idx) < len(pontos)):
            return False
        if len(pontos) <= 2:
            return True
        fechado = self._dist_tuple(pontos[0], pontos[-1]) <= max(0.001, self.TOLERANCIA_FECHAMENTO_CM)
        ultimo_real = len(pontos) - 2 if fechado else len(pontos) - 1
        idx = int(idx)
        if idx == 0:
            return True
        if not fechado and idx == ultimo_real:
            return True
        if idx > ultimo_real:
            return False
        if self._elemento_origem_curva_suave(elemento) or self._sequencia_origem_parece_curva_suave(pontos):
            return False
        anterior = pontos[idx - 1]
        atual = pontos[idx]
        proximo = pontos[idx + 1]
        if self._dist_tuple(anterior, atual) <= 1e-7 or self._dist_tuple(atual, proximo) <= 1e-7:
            return False
        return self._desvio_angular_vertice(anterior, atual, proximo) >= 10.0

    @staticmethod
    def _elemento_origem_curva_suave(elemento: dict) -> bool:
        return (
            bool(elemento.get("curva_suave"))
            or bool(elemento.get("pontos_tracado_real"))
            or str(elemento.get("renderizacao") or "").strip().lower() == "curva_suave"
        )

    def _sequencia_origem_parece_curva_suave(self, pontos: list[tuple[float, float]]) -> bool:
        if len(pontos) < 12:
            return False
        fechado = self._dist_tuple(pontos[0], pontos[-1]) <= max(0.001, self.TOLERANCIA_FECHAMENTO_CM)
        base = pontos[:-1] if fechado else pontos
        if len(base) < 12:
            return False
        desvios: list[float] = []
        inicio = 0 if fechado else 1
        fim = len(base) if fechado else len(base) - 1
        for idx in range(inicio, fim):
            anterior = base[idx - 1]
            atual = base[idx]
            proximo = base[(idx + 1) % len(base)]
            if self._dist_tuple(anterior, atual) <= 1e-7 or self._dist_tuple(atual, proximo) <= 1e-7:
                continue
            desvios.append(self._desvio_angular_vertice(anterior, atual, proximo))
        if len(desvios) < 8:
            return False
        suaves = sum(1 for desvio in desvios if desvio <= 14.0)
        return (suaves / float(len(desvios))) >= 0.85 and max(desvios) <= 28.0

    def _desvio_angular_vertice(
        self,
        anterior: tuple[float, float],
        atual: tuple[float, float],
        proximo: tuple[float, float],
    ) -> float:
        angulo = self._angulo_interno(QPointF(*anterior), QPointF(*atual), QPointF(*proximo))
        return abs(180.0 - float(angulo))

    def _coletar_encontros_linhas_no_contorno(
        self,
        segmentos: list[tuple],
        contorno: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        grupos: dict[tuple[int, int], list[tuple[tuple[float, float], tuple[float, float], int | None]]] = {}
        tol = 1e-4
        for item in segmentos:
            if len(item) >= 3:
                a, b, origem_idx = item[0], item[1], int(item[2])
            else:
                a, b = item[0], item[1]
                origem_idx = None
            if self._dist_tuple(a, b) <= 1e-7:
                continue
            for ponto, vizinho in ((a, b), (b, a)):
                chave = (round(float(ponto[0]) / tol), round(float(ponto[1]) / tol))
                grupos.setdefault(chave, []).append(
                    ((float(ponto[0]), float(ponto[1])), (float(vizinho[0]), float(vizinho[1])), origem_idx)
                )

        encontros: list[tuple[float, float]] = []
        for itens in grupos.values():
            if len(itens) < 2:
                continue
            px = sum(p[0] for p, _vizinho, _origem in itens) / len(itens)
            py = sum(p[1] for p, _vizinho, _origem in itens) / len(itens)
            ponto = (px, py)
            if not self._ponto_no_contorno(ponto, contorno, tol=0.08):
                continue
            origens = {origem for _p, _vizinho, origem in itens if origem is not None}
            if len(origens) == 1:
                continue
            direcoes: list[tuple[float, float]] = []
            for origem_ponto, vizinho, _origem_idx in itens:
                dx = float(vizinho[0]) - float(origem_ponto[0])
                dy = float(vizinho[1]) - float(origem_ponto[1])
                comp = sqrt((dx * dx) + (dy * dy))
                if comp > 1e-7:
                    direcoes.append((dx / comp, dy / comp))
            if len(direcoes) < 2:
                continue
            tem_encontro_real = False
            for i in range(len(direcoes)):
                for j in range(i + 1, len(direcoes)):
                    dot = (direcoes[i][0] * direcoes[j][0]) + (direcoes[i][1] * direcoes[j][1])
                    if dot >= -0.8660254038:
                        tem_encontro_real = True
                        break
                if tem_encontro_real:
                    break
            if tem_encontro_real:
                encontros.append(ponto)
        return self._deduplicar_pontos(encontros, tol=1e-4)

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
        self._origem_arrasto_molde = None
        self._angulo_arrasto_molde = None
        self._guia_arrasto_angular = None
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
        self._origem_arrasto_molde = QPointF(pos)
        self._angulo_arrasto_molde = None
        self._guia_arrasto_angular = None

    def _posicao_arrasto_com_restricao(self, canvas, pos: QPointF) -> QPointF:
        if not bool(getattr(canvas, "snap_ativo", False)):
            self._angulo_arrasto_molde = None
            self._guia_arrasto_angular = None
            return QPointF(pos)
        origem = self._origem_arrasto_molde or self._ultimo_pos_arrasto
        if origem is None:
            self._angulo_arrasto_molde = None
            self._guia_arrasto_angular = None
            return QPointF(pos)
        dx_total = pos.x() - origem.x()
        dy_total = pos.y() - origem.y()
        raio = sqrt((dx_total * dx_total) + (dy_total * dy_total))
        if raio <= 1e-9:
            self._angulo_arrasto_molde = None
            self._guia_arrasto_angular = None
            return QPointF(origem)

        angulo = (atan2(dy_total, dx_total) * 180.0 / pi) % 360.0
        angulos_ima = tuple(float(a) for a in range(0, 360, 15))
        alvo = min(angulos_ima, key=lambda a: min(abs(angulo - a), 360.0 - abs(angulo - a)))
        diferenca = min(abs(angulo - alvo), 360.0 - abs(angulo - alvo))
        tolerancia = 4.0
        if diferenca > tolerancia:
            self._angulo_arrasto_molde = None
            self._guia_arrasto_angular = None
            return QPointF(pos)

        rad = alvo * pi / 180.0
        destino = QPointF(origem.x() + (cos(rad) * raio), origem.y() + (sin(rad) * raio))
        self._angulo_arrasto_molde = alvo
        self._guia_arrasto_angular = (QPointF(origem), QPointF(destino), alvo)
        return destino

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
        self._origem_arrasto_molde = None
        self._angulo_arrasto_molde = None
        self._guia_arrasto_angular = None
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
        self._origem_arrasto_molde = None
        self._angulo_arrasto_molde = None
        self._guia_arrasto_angular = None
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
        candidatos_rapidos = self._contornos_fechados_sob_cursor_rapido(canvas, ponto)
        for cont in candidatos_rapidos:
            self._adicionar_candidato_contorno(candidatos, ponto, cont)
        if candidatos:
            candidatos.sort(key=lambda c: (self._distancia_ponto_contorno(ponto, c), abs(self._area_contorno(c))))
            return candidatos

        total_elementos = len(getattr(canvas.cena, "elementos", []) or [])
        raio = max(12.0, min(canvas.width(), canvas.height()) / max(canvas.zoom, 1e-6) * (0.25 if leve else 0.45))
        if total_elementos > 160:
            raio = min(raio, 38.0 if leve else 55.0)
        elementos = self._elementos_proximos_para_extracao(canvas.cena.elementos, ponto, raio * 1.8)
        if not elementos:
            elementos = [] if total_elementos > 160 else list(canvas.cena.elementos)
        if total_elementos > 160 and len(elementos) > 80:
            elementos = sorted(elementos, key=lambda el: self._distancia_elemento_ao_ponto(el, ponto))[:80]
        tentativas = [
            lambda: extract_local_enclosing_contour(elementos, ponto, search_radius=raio, tol=0.01),
            lambda: extract_smallest_enclosing_contour(elementos, ponto, search_radius=raio, tol=0.01),
        ]
        if not leve and total_elementos <= 160:
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

    def _contornos_fechados_sob_cursor_rapido(self, canvas, ponto: tuple[float, float]) -> list[list[tuple[float, float]]]:
        tolerancia = self._tolerancia_clique_linha(canvas)
        saida: list[list[tuple[float, float]]] = []
        for el in reversed(getattr(canvas.cena, "elementos", []) or []):
            if not isinstance(el, dict) or el.get("tipo") != "polyline":
                continue
            pontos = self._normalizar_pontos_contorno(el.get("pontos", []) or [])
            if len(pontos) < 4:
                continue
            if self._dist_tuple(pontos[0], pontos[-1]) > 1e-6:
                continue
            xs = [x for x, _y in pontos]
            ys = [y for _x, y in pontos]
            if (
                ponto[0] < min(xs) - tolerancia
                or ponto[0] > max(xs) + tolerancia
                or ponto[1] < min(ys) - tolerancia
                or ponto[1] > max(ys) + tolerancia
            ):
                continue
            if (
                self._distancia_ponto_contorno(ponto, pontos) <= tolerancia
                or self._ponto_dentro_poligono_coords(ponto, pontos)
            ):
                saida.append(pontos)
        return saida[:8]

    def _distancia_elemento_ao_ponto(self, el: dict, ponto: tuple[float, float]) -> float:
        pts = polyline_from_element(el)
        if len(pts) < 2:
            return float("inf")
        menor = float("inf")
        for a, b in zip(pts, pts[1:]):
            menor = min(menor, point_segment_distance(ponto, a, b))
        return menor

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
            f"pré-filtro local: elementos_locais={len(elementos_locais)} raio_max={formatar_numero(raio_max_local, 2)} zoom={formatar_numero(canvas.zoom, 4)}"
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
                mover_elemento_por_delta(el, dx, dy)

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
            instalar_memoria_posicao(dialog, "dialog:extrair_molde")
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
            self._dialog.move(ajustar_para_area(self._dialog, canvas.mapToGlobal(destino_local)))

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

        candidatos = self._indices_por_angulo(base)
        if candidatos:
            return candidatos
        if self._eh_forma_fechada_suave(base):
            return [self._indice_principal_curva_fechada(base)]
        return [0]

    def _quantidade_minima_controles_principais(self, base: list[tuple[float, float]]) -> int:
        if len(base) <= 4:
            return len(base)
        perimetro = sum(self._dist_tuple(a, b) for a, b in zip(base, [*base[1:], base[0]]))
        por_perimetro = int(round(perimetro / 12.0))
        por_vertices = int(round(len(base) / 10.0))
        return max(6, min(18, por_perimetro, por_vertices if por_vertices > 0 else 6, len(base)))

    def _mesclar_indices_controle(
        self,
        base: list[tuple[float, float]],
        primeiros: list[int],
        extras: list[int],
    ) -> list[int]:
        n = len(base)
        usados: set[int] = set()
        saida: list[int] = []
        for idx in [*primeiros, *extras]:
            idx = int(idx) % n
            if idx in usados:
                continue
            usados.add(idx)
            saida.append(idx)
        return sorted(saida)

    def _indices_por_angulo(self, base: list[tuple[float, float]]) -> list[int]:
        n = len(base)
        if n < 3:
            return list(range(n))
        limite = 110.0 if self._cfg.get("detectar_piques", True) else 106.0
        perimetro = 0.0
        for i in range(n):
            perimetro += self._dist_tuple(base[i], base[(i + 1) % n])
        dist_min = max(0.35, min(1.2, perimetro * 0.015))

        angulos: list[float] = []
        for i in range(n):
            a = QPointF(*base[i - 1])
            b = QPointF(*base[i])
            c = QPointF(*base[(i + 1) % n])
            angulos.append(self._angulo_interno(a, b, c))

        raw: list[int] = []
        for i, ang in enumerate(angulos):
            anterior = angulos[i - 1]
            proximo = angulos[(i + 1) % n]
            muito_fechado = ang <= 108.0
            minimo_local = ang <= anterior + 2.0 and ang <= proximo + 2.0
            if ang <= limite and (muito_fechado or minimo_local):
                raw.append(i)
        if not raw:
            return []

        saida: list[int] = []
        for idx in raw:
            if not saida:
                saida.append(idx)
                continue
            ultimo = saida[-1]
            muito_fechados = angulos[idx] <= 108.0 and angulos[ultimo] <= 108.0
            if not muito_fechados and self._dist_tuple(base[ultimo], base[idx]) < dist_min:
                if angulos[idx] < angulos[ultimo]:
                    saida[-1] = idx
                continue
            saida.append(idx)
        if len(saida) >= 2 and self._dist_tuple(base[saida[0]], base[saida[-1]]) < dist_min:
            if angulos[saida[0]] <= 108.0 and angulos[saida[-1]] <= 108.0:
                return saida
            if angulos[saida[0]] <= angulos[saida[-1]]:
                saida.pop()
            else:
                saida.pop(0)
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

    def _eh_forma_fechada_suave(self, base: list[tuple[float, float]]) -> bool:
        if len(base) < 8:
            return False
        xs = [x for x, _ in base]
        ys = [y for _, y in base]
        largura = max(xs) - min(xs)
        altura = max(ys) - min(ys)
        if largura <= 1e-6 or altura <= 1e-6:
            return False
        razao = max(largura, altura) / max(min(largura, altura), 1e-6)
        if razao > 3.5:
            return False

        angulos = []
        for i in range(len(base)):
            a = QPointF(*base[i - 1])
            b = QPointF(*base[i])
            c = QPointF(*base[(i + 1) % len(base)])
            angulos.append(self._angulo_interno(a, b, c))
        cantos_duros = sum(1 for ang in angulos if ang < 96.0)
        return cantos_duros <= 1

    def _indice_principal_curva_fechada(self, base: list[tuple[float, float]]) -> int:
        if not base:
            return 0
        if len(base) < 3:
            return 0
        angulos = []
        for i in range(len(base)):
            a = QPointF(*base[i - 1])
            b = QPointF(*base[i])
            c = QPointF(*base[(i + 1) % len(base)])
            angulos.append(self._angulo_interno(a, b, c))
        menor = min(angulos)
        if menor < 128.0:
            return int(angulos.index(menor))
        xs = [x for x, _ in base]
        max_x = max(xs)
        candidatos = [i for i, (x, _y) in enumerate(base) if abs(x - max_x) <= 1e-6]
        if candidatos:
            cy = sum(y for _x, y in base) / len(base)
            return int(min(candidatos, key=lambda i: abs(base[i][1] - cy)))
        return 0

    def _indices_quatro_extremos(self, base: list[tuple[float, float]]) -> list[int]:
        xs = [x for x, _ in base]
        ys = [y for _, y in base]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        alvos = [
            (min(xs), cy),
            (cx, min(ys)),
            (max(xs), cy),
            (cx, max(ys)),
        ]
        usados: set[int] = set()
        indices: list[int] = []
        for ax, ay in alvos:
            melhor = min(
                range(len(base)),
                key=lambda i: ((base[i][0] - ax) ** 2 + (base[i][1] - ay) ** 2) + (1e9 if i in usados else 0.0),
            )
            usados.add(melhor)
            indices.append(melhor)
        return sorted(indices)

    def _calcular_auxiliares_no_contorno(self, base: list[tuple[float, float]], indices_cantos: list[int]) -> list[tuple[float, float]]:
        n = len(base)
        indices_ordenados = sorted({int(i) for i in indices_cantos if 0 <= int(i) < n})
        if not indices_ordenados:
            return []
        if len(indices_ordenados) == 1:
            inicio = indices_ordenados[0]
            trecho = [base[(inicio + passo) % n] for passo in range(n + 1)]
            return self._deduplicar_pontos(self._auxiliares_para_contorno_curvo_fechado(trecho), tol=1e-4)
        aux: list[tuple[float, float]] = []
        for pos, inicio in enumerate(indices_ordenados):
            fim = indices_ordenados[(pos + 1) % len(indices_ordenados)]
            trecho = self._pontos_intervalo_contorno(base, inicio, fim)
            if len(trecho) < 2:
                continue
            selecionados = self._auxiliares_para_trecho_curvo(trecho)
            aux.extend(selecionados)

        return self._deduplicar_pontos(aux, tol=1e-4)

    def _pontos_intervalo_contorno(self, base: list[tuple[float, float]], inicio: int, fim: int) -> list[tuple[float, float]]:
        n = len(base)
        if n <= 0:
            return []
        pontos = [base[int(inicio) % n]]
        atual = int(inicio) % n
        destino = int(fim) % n
        while atual != destino:
            atual = (atual + 1) % n
            pontos.append(base[atual])
            if len(pontos) > n + 1:
                break
        return pontos

    def _auxiliares_para_trecho_curvo(self, trecho: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(trecho) < 2:
            return []
        if self._trecho_praticamente_reto(trecho):
            return [self._ponto_medio_tuple(trecho[0], trecho[-1])]
        perimetro = sum(self._dist_tuple(a, b) for a, b in zip(trecho, trecho[1:]))
        tolerancia = self._tolerancia_simplificacao_curva(trecho, fechado=False)
        indices = [idx for idx in self._simplificar_indices_rdp(trecho, tolerancia) if 0 < idx < len(trecho) - 1]
        max_aux = max(2, min(10, int(round(perimetro / 5.0)) + 1))
        min_aux = 1 if perimetro < 8.0 else 2
        indices = self._reduzir_indices_por_curva(trecho, indices, max_aux)
        auxiliares = [trecho[idx] for idx in indices]
        auxiliares = self._completar_auxiliares_por_fracao(trecho, auxiliares, min_aux)
        return self._deduplicar_pontos(auxiliares, tol=1e-4)

    def _trecho_praticamente_reto(self, trecho: list[tuple[float, float]]) -> bool:
        if len(trecho) <= 2:
            return True
        a = (float(trecho[0][0]), float(trecho[0][1]))
        b = (float(trecho[-1][0]), float(trecho[-1][1]))
        comprimento = self._dist_tuple(a, b)
        if comprimento <= 1e-9:
            return False
        limite = max(0.02, comprimento * 0.002)
        for item in trecho[1:-1]:
            p = (float(item[0]), float(item[1]))
            if self._distancia_ponto_segmento_tuple(p, a, b) > limite:
                return False
        return True

    def _auxiliares_para_contorno_curvo_fechado(self, trecho: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(trecho) < 2:
            return []
        perimetro = sum(self._dist_tuple(a, b) for a, b in zip(trecho, trecho[1:]))
        total = max(1, len(trecho) - 1)
        if total < 3:
            return []
        meio = max(1, total // 2)
        tolerancia = self._tolerancia_simplificacao_curva(trecho, fechado=True)
        indices: set[int] = set()
        for inicio, fim in ((0, meio), (meio, total)):
            subtrecho = trecho[inicio : fim + 1]
            for idx_local in self._simplificar_indices_rdp(subtrecho, tolerancia):
                idx = inicio + idx_local
                if 0 < idx < total:
                    indices.add(idx)
        min_aux = max(8, min(18, int(round(perimetro / 5.0))))
        max_aux = max(min_aux, min(36, int(round(perimetro / 2.8)), total - 1))
        indices_ordenados = self._reduzir_indices_por_curva(trecho, sorted(indices), max_aux)
        auxiliares = [trecho[idx] for idx in indices_ordenados]
        auxiliares = self._completar_auxiliares_por_fracao(trecho, auxiliares, min_aux)
        if len(auxiliares) > max_aux:
            indices_aux = [
                self._indice_mais_proximo_no_contorno(aux, trecho[:-1], tol=max(0.12, tolerancia * 2.0))
                for aux in auxiliares
            ]
            indices_aux = [idx for idx in indices_aux if idx is not None]
            auxiliares = [trecho[idx] for idx in self._reduzir_indices_por_curva(trecho, indices_aux, max_aux)]
        return self._deduplicar_pontos(auxiliares, tol=1e-4)

    def _tolerancia_simplificacao_curva(self, trecho: list[tuple[float, float]], fechado: bool) -> float:
        xs = [float(x) for x, _y in trecho]
        ys = [float(y) for _x, y in trecho]
        largura = max(xs) - min(xs) if xs else 0.0
        altura = max(ys) - min(ys) if ys else 0.0
        diagonal = sqrt((largura * largura) + (altura * altura))
        perimetro = sum(self._dist_tuple(a, b) for a, b in zip(trecho, trecho[1:]))
        base = max(diagonal * (0.018 if fechado else 0.024), perimetro * (0.006 if fechado else 0.010))
        limite_superior = 0.55 if fechado else 0.75
        return max(0.08, min(limite_superior, base))

    def _simplificar_indices_rdp(self, pontos: list[tuple[float, float]], tolerancia: float) -> list[int]:
        if len(pontos) <= 2:
            return list(range(len(pontos)))
        manter: set[int] = {0, len(pontos) - 1}

        def visitar(inicio: int, fim: int) -> None:
            if fim <= inicio + 1:
                return
            a = pontos[inicio]
            b = pontos[fim]
            melhor_idx = None
            melhor_dist = -1.0
            for idx in range(inicio + 1, fim):
                dist = self._distancia_ponto_segmento_tuple(pontos[idx], a, b)
                if dist > melhor_dist:
                    melhor_dist = dist
                    melhor_idx = idx
            if melhor_idx is not None and melhor_dist > tolerancia:
                manter.add(melhor_idx)
                visitar(inicio, melhor_idx)
                visitar(melhor_idx, fim)

        visitar(0, len(pontos) - 1)
        return sorted(manter)

    def _reduzir_indices_por_curva(
        self,
        trecho: list[tuple[float, float]],
        indices: list[int],
        maximo: int,
    ) -> list[int]:
        unicos = sorted({int(idx) for idx in indices if 0 < int(idx) < len(trecho) - 1})
        if len(unicos) <= maximo:
            return unicos
        pontuados = sorted(
            ((self._pontuacao_curvatura_indice(trecho, idx), idx) for idx in unicos),
            key=lambda item: (-item[0], item[1]),
        )
        return sorted(idx for _score, idx in pontuados[:maximo])

    def _pontuacao_curvatura_indice(self, trecho: list[tuple[float, float]], idx: int) -> float:
        if not (0 < idx < len(trecho) - 1):
            return 0.0
        a = QPointF(*trecho[idx - 1])
        b = QPointF(*trecho[idx])
        c = QPointF(*trecho[idx + 1])
        angulo = self._angulo_interno(a, b, c)
        desvio = self._distancia_ponto_segmento_tuple(trecho[idx], trecho[idx - 1], trecho[idx + 1])
        return max(0.0, 180.0 - angulo) + (desvio * 12.0)

    def _completar_auxiliares_por_fracao(
        self,
        trecho: list[tuple[float, float]],
        auxiliares: list[tuple[float, float]],
        minimo: int,
    ) -> list[tuple[float, float]]:
        saida = list(auxiliares)
        if minimo <= 0:
            return saida
        passo = 1
        while len(saida) < minimo and passo <= minimo * 3:
            ponto = self._ponto_no_trecho_por_fracao(trecho, passo / float(minimo + 1))
            if not any(self._dist_tuple(ponto, existente) <= 0.20 for existente in saida):
                saida.append(ponto)
            passo += 1
        return self._deduplicar_pontos(saida, tol=1e-4)

    def _ponto_no_trecho_por_fracao(self, trecho: list[tuple[float, float]], fracao: float) -> tuple[float, float]:
        if len(trecho) == 1:
            return (float(trecho[0][0]), float(trecho[0][1]))
        comprimentos = [self._dist_tuple(a, b) for a, b in zip(trecho, trecho[1:])]
        total = sum(comprimentos)
        if total <= 1e-9:
            return self._ponto_medio_tuple(trecho[0], trecho[-1])
        alvo = max(0.0, min(1.0, float(fracao))) * total
        acumulado = 0.0
        for (a, b), comp in zip(zip(trecho, trecho[1:]), comprimentos):
            if acumulado + comp >= alvo or comp <= 1e-9:
                t = 0.0 if comp <= 1e-9 else (alvo - acumulado) / comp
                return (
                    float(a[0]) + ((float(b[0]) - float(a[0])) * t),
                    float(a[1]) + ((float(b[1]) - float(a[1])) * t),
                )
            acumulado += comp
        return (float(trecho[-1][0]), float(trecho[-1][1]))

    def _ponto_medio_tuple(
        self,
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> tuple[float, float]:
        return ((float(a[0]) + float(b[0])) / 2.0, (float(a[1]) + float(b[1])) / 2.0)

    def _distancia_ponto_segmento_tuple(
        self,
        ponto: tuple[float, float],
        inicio: tuple[float, float],
        fim: tuple[float, float],
    ) -> float:
        ax, ay = float(inicio[0]), float(inicio[1])
        bx, by = float(fim[0]), float(fim[1])
        px, py = float(ponto[0]), float(ponto[1])
        abx = bx - ax
        aby = by - ay
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-12:
            return self._dist_tuple((ax, ay), (px, py))
        t = max(0.0, min(1.0, (((px - ax) * abx) + ((py - ay) * aby)) / denom))
        proj = (ax + (abx * t), ay + (aby * t))
        return self._dist_tuple(proj, (px, py))

    def _indices_internos_intervalo_contorno(self, inicio: int, fim: int, total: int) -> list[int]:
        if total <= 0:
            return []
        indices: list[int] = []
        atual = int(inicio) % total
        destino = int(fim) % total
        while True:
            atual = (atual + 1) % total
            if atual == destino:
                break
            indices.append(atual)
            if len(indices) >= total:
                break
        return indices

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
