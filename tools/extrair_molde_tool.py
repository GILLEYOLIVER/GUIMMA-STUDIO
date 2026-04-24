from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, pi, sin, sqrt
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
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

from core.geometry.engine import internal_angle
from core.geometry_bridge import (
    compose_closed_contour,
    create_mold_payload,
    element_contains_point,
    extract_smallest_enclosing_contour,
)
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "extrair_molde"
    nome = "Extrair Molde"
    descricao_painel = "LMB seleciona/valida contorno. RMB pega molde. LMB solta, RMB cancela/volta Selecionar."
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

    def __init__(self):
        super().__init__()
        self._dialog: QDialog | None = None
        self._idx_selecionado: int | None = None
        self._selecoes_manuais: set[int] = set()
        self._contorno_extraido: list[QPointF] | None = None
        self._contorno_auto_coords: list[tuple[float, float]] | None = None
        self._contornos_preparados: dict[int, list[tuple[float, float]]] = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._arrastando_molde = False
        self._ultimo_pos_arrasto: QPointF | None = None
        self._snapshot_cancelamento: dict[int, dict] = {}
        self._indices_molde_em_arraste: set[int] = set()
        self._cfg = dict(type(self)._cfg_global)

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contorno_extraido = None
        self._contorno_auto_coords = None
        self._contornos_preparados = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._indices_molde_em_arraste = set()
        self._sincronizar_cfg_da_ui()
        self._abrir_config(canvas)
        self.set_status("Defina modo. LMB seleciona contorno(s), RMB pega molde, LMB solta, RMB cancela.")

    def on_deactivate(self, canvas):
        super().on_deactivate(canvas)
        self._sincronizar_cfg_da_ui()
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contorno_extraido = None
        self._contorno_auto_coords = None
        self._contornos_preparados = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._indices_molde_em_arraste = set()

    def on_mouse_press(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._sincronizar_cfg_da_ui()

        if self._arrastando_molde:
            if event.button() == Qt.LeftButton:
                self._finalizar_posicionamento(canvas, "Molde solto com sucesso.")
                event.accept()
                return True
            if event.button() == Qt.RightButton:
                self._cancelar_arraste_molde(canvas)
                canvas.update()
                event.accept()
                return True
            return False

        if event.button() == Qt.LeftButton:
            contorno = extract_smallest_enclosing_contour(
                canvas.cena.elementos,
                (pos.x(), pos.y()),
                tol=self.TOLERANCIA_FECHAMENTO_CM,
            )
            if not contorno:
                self._mostrar_aviso_sem_molde(canvas)
                return True
            if self._perimetro_contorno(contorno) < self.TOLERANCIA_FECHAMENTO_CM:
                self._mostrar_aviso_sem_molde(canvas)
                return True
            self._contorno_auto_coords = contorno
            self._contorno_extraido = [QPointF(float(x), float(y)) for x, y in contorno]
            self._selecoes_manuais.clear()
            self._contornos_preparados = {}
            self._idx_selecionado = None
            canvas._selecionados = set()
            self._molde_criado = False
            self._molde_posicionado = False
            self.set_status("Perímetro fechado detectado. RMB para extrair e arrastar molde.")
            canvas.update()
            event.accept()
            return True

        if event.button() != Qt.RightButton:
            return False

        if self._molde_posicionado:
            self._limpar_estado_extracao(canvas, "Extração reiniciada.")
            canvas.update()
            event.accept()
            return True

        if not self._contorno_auto_coords:
            self.set_status("Selecione primeiro uma área fechada com clique esquerdo.")
            event.accept()
            return True

        ok = self._criar_molde(canvas)
        if not ok:
            self._mostrar_aviso_sem_molde(canvas)
            return False
        self._iniciar_arraste_molde(canvas, pos)
        self.set_status("Molde em mãos: mova o mouse. LMB confirma/solta, RMB cancela.")
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if not self._arrastando_molde:
            return False
        pos = canvas._ponto_com_snap(event.position())
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

    def on_paint_overlay(self, canvas, painter: QPainter):
        for idx in self._selecoes_manuais:
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                if el.get("tipo") == "polyline":
                    pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                    self._desenhar_contorno(canvas, painter, pts, QColor("#ff2fff"), 2.0)
        if self._contorno_extraido:
            self._desenhar_contorno(canvas, painter, self._contorno_extraido, QColor("#33a6ff"), 2.2)
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
        return element_contains_point({"pontos": polygon}, (pt.x(), pt.y()))

    def _criar_molde(self, canvas) -> bool:
        if self._contorno_auto_coords:
            return self._criar_molde_de_contorno_extraido(canvas, self._contorno_auto_coords)
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

    def _criar_molde_de_contorno_extraido(self, canvas, pontos: list[tuple[float, float]]) -> bool:
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
        }
        self._enriquecer_metadados_molde(novo)
        canvas.cena.elementos.append(novo)
        self._idx_selecionado = len(canvas.cena.elementos) - 1
        self._selecoes_manuais = {self._idx_selecionado}
        canvas._selecionados = {self._idx_selecionado}
        self._molde_criado = True
        self._contorno_auto_coords = None
        return True

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
        self._contorno_extraido = pontos
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

        indices_cantos = self._indices_controles_principais(base)
        cantos = [base[i] for i in indices_cantos]
        molde["controle_cantos"] = [(float(x), float(y)) for x, y in cantos]

        usar_auxiliares = bool(self._cfg.get("usar_auxiliares", True))
        if usar_auxiliares and len(indices_cantos) >= 2:
            auxiliares = self._calcular_auxiliares_no_contorno(base, indices_cantos)
        else:
            auxiliares = []

        molde["controle_auxiliares"] = [(float(x), float(y)) for x, y in auxiliares]
        molde["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in molde["controle_cantos"]]
        molde["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in molde["controle_auxiliares"]]

    def _finalizar_posicionamento(self, canvas, msg: str):
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._indices_molde_em_arraste = set()
        self._molde_posicionado = True
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
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contorno_extraido = None
        self._contorno_auto_coords = None
        self._contornos_preparados = {}
        canvas._selecionados = set()
        self.set_status("Extração cancelada. Clique esquerdo para selecionar novamente.")

    def _limpar_estado_extracao(self, canvas, msg: str):
        self._idx_selecionado = None
        self._selecoes_manuais.clear()
        self._contorno_extraido = None
        self._contorno_auto_coords = None
        self._contornos_preparados = {}
        self._molde_criado = False
        self._molde_posicionado = False
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._indices_molde_em_arraste = set()
        canvas._selecionados = set()
        self.set_status(msg)

    def _mostrar_aviso_sem_molde(self, canvas):
        self._limpar_estado_extracao(canvas, "Não foi possível encontrar molde!")
        QMessageBox.warning(canvas, "Atenção", "Não foi possível encontrar molde!")

    def _perimetro_contorno(self, contorno: list[tuple[float, float]]) -> float:
        if len(contorno) < 2:
            return 0.0
        total = 0.0
        for (ax, ay), (bx, by) in zip(contorno, contorno[1:]):
            dx = bx - ax
            dy = by - ay
            total += sqrt((dx * dx) + (dy * dy))
        return total

    def _aplicar_delta_selecionados(self, canvas, dx: float, dy: float):
        for idx in sorted(self._selecoes_manuais):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                el["pontos"] = [(x + dx, y + dy) for x, y in el.get("pontos", [])]
                if "controle_cantos" in el:
                    el["controle_cantos"] = [(x + dx, y + dy) for x, y in el.get("controle_cantos", [])]
                if "controle_auxiliares" in el:
                    el["controle_auxiliares"] = [(x + dx, y + dy) for x, y in el.get("controle_auxiliares", [])]
                if "pontos_controle_principais" in el:
                    for p in el["pontos_controle_principais"]:
                        p["x"] = float(p.get("x", 0.0)) + dx
                        p["y"] = float(p.get("y", 0.0)) + dy
                if "pontos_auxiliares" in el:
                    for p in el["pontos_auxiliares"]:
                        p["x"] = float(p.get("x", 0.0)) + dx
                        p["y"] = float(p.get("y", 0.0)) + dy
                if "fio_origem" in el:
                    fx, fy = el.get("fio_origem", (0.0, 0.0))
                    el["fio_origem"] = (float(fx) + dx, float(fy) + dy)
                if "fio_fim" in el:
                    fx, fy = el.get("fio_fim", (0.0, 0.0))
                    el["fio_fim"] = (float(fx) + dx, float(fy) + dy)

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
        if cls._dialog_global is None:
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

    def _salvar_cfg(self, *_):
        self._salvar_cfg_global()
        self._sincronizar_cfg_da_ui()

    @classmethod
    def _salvar_cfg_global(cls, *_):
        if cls._cmb_modo_global is None:
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
        if cls._cmb_modo_global is None:
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
            candidatos = self._indices_por_amostragem(base, 6)
        elif len(candidatos) > 8:
            candidatos = self._indices_por_amostragem([base[i] for i in candidatos], 8, indices_originais=candidatos)
        return candidatos

    def _indices_por_angulo(self, base: list[tuple[float, float]]) -> list[int]:
        n = len(base)
        if n < 3:
            return list(range(n))
        saida: list[int] = []
        limite = 150.0 if self._cfg.get("detectar_piques", True) else 135.0
        perimetro = 0.0
        for i in range(n):
            perimetro += self._dist_tuple(base[i], base[(i + 1) % n])
        dist_min = max(1.5, perimetro * 0.06)

        for i in range(n):
            a = QPointF(*base[i - 1])
            b = QPointF(*base[i])
            c = QPointF(*base[(i + 1) % n])
            ang = self._angulo_interno(a, b, c)
            if ang <= limite or not saida:
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
        aux: list[tuple[float, float]] = []
        for pos, idx_a in enumerate(indices_cantos):
            idx_b = indices_cantos[(pos + 1) % len(indices_cantos)]
            caminho = [idx_a]
            i = idx_a
            while i != idx_b:
                i = (i + 1) % n
                caminho.append(i)
                if len(caminho) > n + 1:
                    break
            meio_idx = caminho[len(caminho) // 2]
            aux.append((float(base[meio_idx][0]), float(base[meio_idx][1])))
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
