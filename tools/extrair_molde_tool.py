from __future__ import annotations

from copy import deepcopy
from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QVBoxLayout,
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
        self._cfg = {
            "modo": "Automático",
            "detectar_graduacoes": True,
            "detectar_piques": True,
            "detectar_auxiliares": False,
            "compor_contornos": True,
            "usar_auxiliares": True,
            "quebrar_auxiliares": True,
            "converter_auxiliares": True,
        }

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
        self._abrir_config(canvas)
        self.set_status("Defina modo. LMB seleciona contorno(s), RMB pega molde, LMB solta, RMB cancela.")

    def on_deactivate(self, canvas):
        super().on_deactivate(canvas)
        if self._dialog:
            self._dialog.hide()
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

    def on_mouse_press(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        modo_manual = self._cfg.get("modo") == "Manual"

        if self._arrastando_molde:
            if event.button() == Qt.LeftButton:
                self._finalizar_posicionamento(canvas, "Molde solto com sucesso. RMB para limpar área e soltar ferramenta.")
                event.accept()
                return True
            if event.button() == Qt.RightButton:
                self._finalizar_posicionamento(canvas, "Molde confirmado. RMB novamente para limpar área e soltar ferramenta.")
                canvas.update()
                event.accept()
                return True
            return False

        if event.button() == Qt.LeftButton:
            if not modo_manual:
                contorno = extract_smallest_enclosing_contour(canvas.cena.elementos, (pos.x(), pos.y()))
                if contorno:
                    self._contorno_auto_coords = contorno
                    self._contorno_extraido = [QPointF(float(x), float(y)) for x, y in contorno]
                    self._selecoes_manuais.clear()
                    self._contornos_preparados = {}
                    self._idx_selecionado = None
                    canvas._selecionados = set()
                    self._molde_criado = False
                    self._molde_posicionado = False
                    self.set_status("Contorno da face detectado. RMB para pegar molde.")
                    canvas.update()
                    event.accept()
                    return True
            candidatos = canvas._indices_elementos_em_ponto(pos)
            if not candidatos:
                candidatos = self._indices_polylines_contem_ponto(canvas, pos)
            if not candidatos and canvas._selecionados:
                candidatos = sorted(
                    [idx for idx in canvas._selecionados if 0 <= idx < len(canvas.cena.elementos) and canvas.cena.elementos[idx].get("tipo") == "polyline"],
                    reverse=True,
                )
            if not candidatos:
                self.set_status("Clique na borda ou dentro do contorno (ou pré-selecione) para continuar.")
                return False
            idx = self._escolher_melhor_candidato(canvas, candidatos)
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                self.set_status("Selecione polyline para extrair molde.")
                return False

            if modo_manual:
                if idx in self._selecoes_manuais:
                    self._selecoes_manuais.remove(idx)
                else:
                    self._selecoes_manuais.add(idx)
                canvas._selecionados = set(self._selecoes_manuais)
                self._idx_selecionado = next(iter(self._selecoes_manuais), None)
                self._contorno_extraido = None
                self._contorno_auto_coords = None
                self._contornos_preparados.pop(idx, None)
                self._molde_criado = False
                self._molde_posicionado = False
                if self._selecoes_manuais:
                    self.set_status(f"Manual: {len(self._selecoes_manuais)} parte(s) selecionada(s). RMB para validar/extrair.")
                else:
                    self.set_status("Manual: nenhuma parte selecionada.")
                canvas.update()
                event.accept()
                return True

            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if not self._eh_fechado(pontos):
                self.set_status("O contorno não está completo.")
                return False
            if event.modifiers() & Qt.ShiftModifier:
                self._selecoes_manuais.add(idx)
            else:
                self._selecoes_manuais = {idx}
            self._idx_selecionado = idx
            canvas._selecionados = set(self._selecoes_manuais)
            self._contorno_extraido = pontos
            self._contorno_auto_coords = [(p.x(), p.y()) for p in pontos]
            self._molde_criado = False
            self._molde_posicionado = False
            self.set_status("Contorno validado e realçado. RMB para pegar molde.")
            canvas.update()
            event.accept()
            return True

        if event.button() != Qt.RightButton:
            return False

        if self._molde_posicionado:
            canvas._selecionados = set()
            self._selecoes_manuais.clear()
            self._contorno_extraido = None
            self._contorno_auto_coords = None
            self._contornos_preparados = {}
            self._idx_selecionado = None
            self._molde_criado = False
            self._molde_posicionado = False
            self.set_status("Área limpa. Ferramenta solta.")
            canvas.ferramenta_padrao_solicitada.emit("selecionar")
            canvas.update()
            event.accept()
            return True

        if not self._selecoes_manuais and not self._contorno_auto_coords:
            self.set_status("Nenhum contorno selecionado. RMB novamente para voltar ao Selecionar.")
            canvas.ferramenta_padrao_solicitada.emit("selecionar")
            event.accept()
            return True

        if self._selecoes_manuais:
            for idx in sorted(self._selecoes_manuais):
                self._extrair_indice(canvas, idx)
        ok = self._criar_molde(canvas)
        if not ok:
            if self._cfg.get("modo") == "Manual":
                self.set_status("Falha ao criar molde: contorno manual ainda não fechou ou está inválido.")
            else:
                self.set_status("Falha ao criar molde.")
            return False
        self._iniciar_arraste_molde(canvas, pos)
        self.set_status("Molde em mãos: mova o mouse, LMB ou RMB confirma posicionamento.")
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
            self._desenhar_contorno(canvas, painter, self._contorno_extraido, QColor("#ff2a2a"), 2.0)
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
        self._contorno_extraido = pontos
        self._contornos_preparados[idx] = [(p.x(), p.y()) for p in pontos]
        self._molde_criado = False

    def _enriquecer_metadados_molde(self, molde: dict):
        pontos = [(float(x), float(y)) for x, y in molde.get("pontos", [])]
        if len(pontos) < 2:
            return
        if pontos[0] == pontos[-1]:
            base = pontos[:-1]
        else:
            base = pontos
        if not base:
            return
        xs = [x for x, _ in base]
        ys = [y for _, y in base]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        min_y = min(ys)
        max_y = max(ys)
        molde.setdefault("molde_id", str(uuid4()))
        molde.setdefault("fio_angulo", 0.0)
        largura = max(xs) - min(xs)
        margem = largura * 0.20
        molde.setdefault("fio_origem", (min(xs) + margem, cy))
        molde.setdefault("fio_fim", (max(xs) - margem, cy))
        molde.setdefault("mostrar_nome", True)
        molde.setdefault("mostrar_fio", True)
        molde.setdefault("mostrar_controles", True)
        if not molde.get("controle_cantos"):
            molde["controle_cantos"] = [(x, y) for x, y in base]
        cantos = [(float(x), float(y)) for x, y in molde.get("controle_cantos", [])]
        if len(cantos) >= 2 and not molde.get("controle_auxiliares"):
            auxiliares: list[tuple[float, float]] = []
            for i in range(len(cantos)):
                j = (i + 1) % len(cantos)
                ax, ay = cantos[i]
                bx, by = cantos[j]
                auxiliares.append(((ax + bx) / 2.0, (ay + by) / 2.0))
            molde["controle_auxiliares"] = auxiliares
        if not molde.get("pontos_controle_principais"):
            molde["pontos_controle_principais"] = [{"x": float(x), "y": float(y)} for x, y in cantos]
        if not molde.get("pontos_auxiliares"):
            molde["pontos_auxiliares"] = [
                {"x": float(x), "y": float(y)} for x, y in molde.get("controle_auxiliares", [])
            ]

    def _finalizar_posicionamento(self, canvas, msg: str):
        self._arrastando_molde = False
        self._ultimo_pos_arrasto = None
        self._snapshot_cancelamento = {}
        self._molde_posicionado = True
        canvas._registrar_historico()
        self.set_status(msg)
        canvas.update()

    def _iniciar_arraste_molde(self, canvas, pos: QPointF):
        self._snapshot_cancelamento = {idx: deepcopy(canvas.cena.elementos[idx]) for idx in self._selecoes_manuais if 0 <= idx < len(canvas.cena.elementos)}
        self._arrastando_molde = True
        self._ultimo_pos_arrasto = QPointF(pos)

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
        if self._dialog is None:
            self._dialog = QDialog(canvas)
            self._dialog.setWindowTitle("Definir contorno")
            self._dialog.setWindowFlags(Qt.Tool)
            self._dialog.setModal(False)
            self._dialog.setStyleSheet(
                """
                QDialog {
                    background: #f1f4f8;
                    color: #111111;
                }
                QLabel, QCheckBox, QComboBox {
                    color: #111111;
                }
                QComboBox {
                    background: #ffffff;
                    border: 1px solid #b9c4cf;
                    border-radius: 4px;
                    min-height: 24px;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1px solid #4f5d6c;
                    background: #ffffff;
                }
                QCheckBox::indicator:checked {
                    border: 1px solid #145f9b;
                    background: #2f7cf6;
                }
                """
            )
            lay = QVBoxLayout(self._dialog)
            form = QFormLayout()
            self.cmb_modo = QComboBox()
            self.cmb_modo.addItems(["Automático", "Manual"])
            self.cmb_modo.setCurrentText(str(self._cfg["modo"]))
            form.addRow("Modo", self.cmb_modo)
            lay.addLayout(form)

            self.chk_grad = QCheckBox("Detectar graduações")
            self.chk_grad.setChecked(bool(self._cfg["detectar_graduacoes"]))
            self.chk_piques = QCheckBox("Detectar piques")
            self.chk_piques.setChecked(bool(self._cfg["detectar_piques"]))
            self.chk_aux = QCheckBox("Detectar linhas auxiliares")
            self.chk_aux.setChecked(bool(self._cfg["detectar_auxiliares"]))
            self.chk_compor = QCheckBox("Compor contornos")
            self.chk_compor.setChecked(bool(self._cfg["compor_contornos"]))
            self.chk_usar = QCheckBox("Usar linhas auxiliares")
            self.chk_usar.setChecked(bool(self._cfg["usar_auxiliares"]))
            self.chk_quebrar = QCheckBox("Quebrar linhas auxiliares")
            self.chk_quebrar.setChecked(bool(self._cfg["quebrar_auxiliares"]))
            self.chk_converter = QCheckBox("Converter primitivas em linhas auxiliares")
            self.chk_converter.setChecked(bool(self._cfg["converter_auxiliares"]))
            for chk in (self.chk_grad, self.chk_piques, self.chk_aux, self.chk_compor, self.chk_usar, self.chk_quebrar, self.chk_converter):
                lay.addWidget(chk)
            lay.addWidget(QLabel(""))
            self.cmb_modo.currentTextChanged.connect(self._salvar_cfg)
            for chk in (self.chk_grad, self.chk_piques, self.chk_aux, self.chk_compor, self.chk_usar, self.chk_quebrar, self.chk_converter):
                chk.toggled.connect(self._salvar_cfg)
        self._dialog.show()
        self._dialog.raise_()

    def _salvar_cfg(self, *_):
        self._cfg.update(
            {
                "modo": self.cmb_modo.currentText(),
                "detectar_graduacoes": self.chk_grad.isChecked(),
                "detectar_piques": self.chk_piques.isChecked(),
                "detectar_auxiliares": self.chk_aux.isChecked(),
                "compor_contornos": self.chk_compor.isChecked(),
                "usar_auxiliares": self.chk_usar.isChecked(),
                "quebrar_auxiliares": self.chk_quebrar.isChecked(),
                "converter_auxiliares": self.chk_converter.isChecked(),
            }
        )

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
