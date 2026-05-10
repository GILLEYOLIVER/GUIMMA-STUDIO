from __future__ import annotations

from math import atan2, cos, degrees, isfinite, radians, sin, sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "selecionar"
    nome = "Selecionar"
    usa_painel_auxiliar = False
    descricao_painel = "Selecione elementos com clique, caixa de seleção e ciclo com botão direito."
    EIXOS_FIO = (0.0, 270.0, 180.0, 90.0)

    def __init__(self):
        super().__init__()
        self._inicio_caixa: QPointF | None = None
        self._fim_caixa: QPointF | None = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto: QPointF | None = None
        self._movido = False
        self._hover_idx: int | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._inicio_caixa = None
        self._fim_caixa = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto = None
        self._movido = False
        self._hover_idx = None
        self.set_status("Clique para selecionar. Arraste para seleção por área. RMB cicla sobrepostos.")

    def on_mouse_press(self, canvas, event) -> bool:
        pos_sem_snap = canvas._tela_para_cena(event.position())
        pos = canvas._ponto_com_snap(event.position())
        if event.button() == Qt.RightButton:
            if canvas._selecionar_proximo_em_ponto(pos):
                self.set_status("Elemento alternado com botão direito.")
                event.accept()
                return True
            if canvas._snap_resultado and canvas._snap_resultado.elemento_idx is not None:
                idx_snap = int(canvas._snap_resultado.elemento_idx)
                if 0 <= idx_snap < len(canvas.cena.elementos):
                    canvas._selecionados = {idx_snap}
                    self.set_status("Elemento alternado via snap.")
                    canvas.update()
                    event.accept()
                    return True
            return False
        if event.button() != Qt.LeftButton:
            return False

        indices = canvas._indices_elementos_em_ponto(pos)
        if not indices and canvas._snap_resultado and canvas._snap_resultado.elemento_idx is not None:
            idx_snap = int(canvas._snap_resultado.elemento_idx)
            if 0 <= idx_snap < len(canvas.cena.elementos):
                indices = [idx_snap]
        if indices:
            selecionado = indices[0]
            if event.modifiers() & Qt.ShiftModifier:
                if selecionado in canvas._selecionados:
                    canvas._selecionados.remove(selecionado)
                else:
                    canvas._selecionados.add(selecionado)
                self._arrastando_selecao = False
                self._ultimo_ponto_arrasto = None
            else:
                if selecionado not in canvas._selecionados:
                    canvas._selecionados = {selecionado}
                # Inicia arraste já no primeiro clique pressionado sobre o elemento
                # para evitar exigir um segundo clique para mover.
                self._arrastando_selecao = True
                self._ultimo_ponto_arrasto = pos_sem_snap
                self._movido = False
            self._inicio_caixa = None
            self._fim_caixa = None
            self.set_status(f"{len(canvas._selecionados)} elemento(s) selecionado(s).")
            canvas.update()
            event.accept()
            return True

        if not (event.modifiers() & Qt.ShiftModifier):
            canvas._selecionados.clear()
        self._inicio_caixa = pos_sem_snap
        self._fim_caixa = pos_sem_snap
        self.set_status("Arraste para selecionar por área.")
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos_sem_snap = canvas._tela_para_cena(event.position())
        pos = canvas._ponto_com_snap(event.position())
        self._hover_idx = (canvas._indices_elementos_em_ponto(pos) or [None])[0]
        if self._arrastando_selecao and self._ultimo_ponto_arrasto is not None:
            dx = pos_sem_snap.x() - self._ultimo_ponto_arrasto.x()
            dy = pos_sem_snap.y() - self._ultimo_ponto_arrasto.y()
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                self._mover_selecionados(canvas, dx, dy)
                self._ultimo_ponto_arrasto = pos_sem_snap
                self._movido = True
            snap_info = f" | Snap: {canvas._snap_resultado.tipo}" if canvas._snap_resultado else ""
            self.set_status(f"Movendo seleção ({len(canvas._selecionados)} elemento(s)){snap_info}")
            canvas.update()
            event.accept()
            return True
        if self._inicio_caixa is None:
            if canvas.lbl_status:
                snap_info = f" | Snap: {canvas._snap_resultado.tipo}" if canvas._snap_resultado else ""
                canvas.lbl_status.setText(f"Selecionar | X {pos.x():.2f} Y {pos.y():.2f}{snap_info}")
                self.set_status(f"Cursor X {pos.x():.2f} Y {pos.y():.2f}{snap_info}")
            canvas.update()
            return True
        self._fim_caixa = pos_sem_snap
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() == Qt.LeftButton and self._arrastando_selecao:
            self._arrastando_selecao = False
            self._ultimo_ponto_arrasto = None
            if self._movido:
                canvas._registrar_historico()
                self.set_status(f"Movimento concluído ({len(canvas._selecionados)} elemento(s)).")
            self._movido = False
            canvas.update()
            event.accept()
            return True
        if event.button() != Qt.LeftButton or self._inicio_caixa is None or self._fim_caixa is None:
            return False
        x1 = min(self._inicio_caixa.x(), self._fim_caixa.x())
        y1 = min(self._inicio_caixa.y(), self._fim_caixa.y())
        x2 = max(self._inicio_caixa.x(), self._fim_caixa.x())
        y2 = max(self._inicio_caixa.y(), self._fim_caixa.y())

        if sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) > (4.0 / max(canvas.zoom, 0.001)):
            selecionados_area: set[int] = set()
            for idx, el in enumerate(canvas.cena.elementos):
                if el.get("tipo") == "polyline":
                    pontos = [QPointF(float(px), float(py)) for px, py in el.get("pontos", [])]
                elif el.get("tipo") == "bezier_quadratica":
                    p0 = QPointF(*el["p0"])
                    p1 = QPointF(*el["p1"])
                    p2 = QPointF(*el["p2"])
                    pontos = canvas._amostrar_bezier_quadratica(p0, p1, p2, segmentos=24)
                else:
                    pontos = []
                if pontos and all(x1 <= p.x() <= x2 and y1 <= p.y() <= y2 for p in pontos):
                    selecionados_area.add(idx)
            if event.modifiers() & Qt.ShiftModifier:
                canvas._selecionados |= selecionados_area
            else:
                canvas._selecionados = selecionados_area
            self.set_status(f"Seleção por área: {len(canvas._selecionados)} elemento(s).")

        self._inicio_caixa = None
        self._fim_caixa = None
        canvas.update()
        event.accept()
        return True

    def on_mouse_double_click(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        if not self._rotacao_duplo_clique_ativa(canvas):
            return False

        pos = canvas._tela_para_cena(event.position())
        idx = canvas._indice_molde_em_ponto(pos) if hasattr(canvas, "_indice_molde_em_ponto") else None
        if idx is None:
            pos_snap = canvas._ponto_com_snap(event.position())
            idx = canvas._indice_molde_em_ponto(pos_snap) if hasattr(canvas, "_indice_molde_em_ponto") else None
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return False

        molde = canvas.cena.elementos[idx]
        if not molde.get("molde"):
            return False

        angulo_atual = self._angulo_fio_atual(molde)
        angulo_alvo = self._proximo_eixo_fio(angulo_atual)
        delta = self._delta_angular(angulo_atual, angulo_alvo)
        pivo = self._pivo_rotacao_fio(molde)
        self._girar_molde_para_fio(molde, pivo, delta)
        molde["fio_angulo"] = angulo_alvo
        molde["mostrar_fio"] = True

        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto = None
        self._movido = False
        canvas._selecionados = {idx}
        canvas._registrar_historico()
        canvas.update()
        self.set_status(f"Molde girado: fio alinhado em {int(angulo_alvo)}°.")
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_realce_elementos(canvas, painter)
        if self._inicio_caixa is None or self._fim_caixa is None:
            return
        p1 = canvas._cena_para_tela(self._inicio_caixa)
        p2 = canvas._cena_para_tela(self._fim_caixa)
        x = min(p1.x(), p2.x())
        y = min(p1.y(), p2.y())
        w = abs(p2.x() - p1.x())
        h = abs(p2.y() - p1.y())
        painter.setPen(QPen(QColor("#33c1ff"), 1, Qt.DashLine))
        painter.setBrush(QColor(40, 160, 255, 40))
        painter.drawRect(int(x), int(y), int(w), int(h))

    def _desenhar_realce_elementos(self, canvas, painter):
        idxs = set(canvas._selecionados)
        if self._hover_idx is not None:
            idxs.add(self._hover_idx)
        for idx in idxs:
            if idx is None or idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            pontos: list[QPointF] = []
            if el.get("tipo") == "polyline":
                pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                if hasattr(canvas, "_pontos_costuras_vinculadas"):
                    pontos.extend(canvas._pontos_costuras_vinculadas(el))
            elif el.get("tipo") == "bezier_quadratica":
                pontos = [QPointF(*el["p0"]), QPointF(*el["p1"]), QPointF(*el["p2"])]
            if not pontos:
                continue
            margem = 0.5
            min_x = min(p.x() for p in pontos) - margem
            max_x = max(p.x() for p in pontos) + margem
            min_y = min(p.y() for p in pontos) - margem
            max_y = max(p.y() for p in pontos) + margem
            p1 = canvas._cena_para_tela(QPointF(min_x, min_y))
            p2 = canvas._cena_para_tela(QPointF(max_x, max_y))
            x = min(p1.x(), p2.x())
            y = min(p1.y(), p2.y())
            w = abs(p2.x() - p1.x())
            h = abs(p2.y() - p1.y())
            painter.setPen(QPen(QColor("#33c1ff"), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(x), int(y), int(w), int(h))

    def _mover_selecionados(self, canvas, dx: float, dy: float):
        for idx in self._indices_para_mover(canvas):
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                el["pontos"] = [(x + dx, y + dy) for x, y in el.get("pontos", [])]
                if "controle_cantos" in el:
                    el["controle_cantos"] = [(x + dx, y + dy) for x, y in el.get("controle_cantos", [])]
                if "controle_auxiliares" in el:
                    el["controle_auxiliares"] = [(x + dx, y + dy) for x, y in el.get("controle_auxiliares", [])]
                if "fio_origem" in el:
                    fx, fy = el.get("fio_origem", (0.0, 0.0))
                    el["fio_origem"] = (float(fx) + dx, float(fy) + dy)
                if "fio_fim" in el:
                    fx, fy = el.get("fio_fim", (0.0, 0.0))
                    el["fio_fim"] = (float(fx) + dx, float(fy) + dy)
                if "marcacoes_no_perimetro" in el:
                    el["marcacoes_no_perimetro"] = [(x + dx, y + dy) for x, y in el.get("marcacoes_no_perimetro", [])]
                if "pontos_controle_principais" in el:
                    for pt in el.get("pontos_controle_principais", []):
                        if isinstance(pt, dict) and "x" in pt and "y" in pt:
                            pt["x"] = float(pt["x"]) + dx
                            pt["y"] = float(pt["y"]) + dy
                if "pontos_auxiliares" in el:
                    for pt in el.get("pontos_auxiliares", []):
                        if isinstance(pt, dict) and "x" in pt and "y" in pt:
                            pt["x"] = float(pt["x"]) + dx
                            pt["y"] = float(pt["y"]) + dy
            elif el.get("tipo") == "bezier_quadratica":
                for chave in ("p0", "p1", "p2"):
                    x, y = el[chave]
                    el[chave] = (x + dx, y + dy)

    def _indices_para_mover(self, canvas) -> list[int]:
        indices = set(int(idx) for idx in getattr(canvas, "_selecionados", set()))
        if hasattr(canvas, "_indices_costuras_vinculadas"):
            for idx in list(indices):
                if 0 <= idx < len(canvas.cena.elementos):
                    el = canvas.cena.elementos[idx]
                    if el.get("molde"):
                        indices.update(canvas._indices_costuras_vinculadas(idx))
        return sorted(indices)

    def _girar_molde_para_fio(self, el: dict, pivo: QPointF, angulo: float) -> None:
        a = radians(angulo)
        ca, sa = cos(a), sin(a)

        def rot(p):
            x, y = float(p[0]), float(p[1])
            dx, dy = x - pivo.x(), y - pivo.y()
            return (pivo.x() + (dx * ca) + (dy * sa), pivo.y() - (dx * sa) + (dy * ca))

        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro", "distancias_no_perimetro", "marcacoes_perimetro"):
            if isinstance(el.get(chave), list):
                el[chave] = [rot(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]
        for chave in ("ponto_texto", "seta_origem", "seta_fim", "fio_origem", "fio_fim"):
            if self._eh_ponto(el.get(chave)):
                el[chave] = rot(el[chave])
        for chave in ("pontos_controle_principais", "pontos_auxiliares"):
            if isinstance(el.get(chave), list):
                for item in el[chave]:
                    if isinstance(item, dict) and "x" in item and "y" in item:
                        x, y = rot((item["x"], item["y"]))
                        item["x"] = x
                        item["y"] = y

    def _pivo_rotacao_fio(self, el: dict) -> QPointF:
        fio_origem = el.get("fio_origem")
        if self._eh_ponto(fio_origem):
            return QPointF(float(fio_origem[0]), float(fio_origem[1]))

        pontos = self._todos_pontos_elemento(el)
        if pontos:
            return QPointF(
                (min(x for x, _ in pontos) + max(x for x, _ in pontos)) / 2.0,
                (min(y for _, y in pontos) + max(y for _, y in pontos)) / 2.0,
            )
        return QPointF(0.0, 0.0)

    def _todos_pontos_elemento(self, el: dict) -> list[tuple[float, float]]:
        pontos: list[tuple[float, float]] = []
        for chave in ("pontos", "controle_cantos", "controle_auxiliares", "marcacoes_no_perimetro"):
            if isinstance(el.get(chave), list):
                for p in el.get(chave, []):
                    if self._eh_ponto(p):
                        pontos.append((float(p[0]), float(p[1])))
        for chave in ("fio_origem", "fio_fim", "ponto_texto", "seta_origem", "seta_fim"):
            if self._eh_ponto(el.get(chave)):
                p = el[chave]
                pontos.append((float(p[0]), float(p[1])))
        return pontos

    def _angulo_fio_atual(self, el: dict) -> float:
        origem = el.get("fio_origem")
        fim = el.get("fio_fim")
        if self._eh_ponto(origem) and self._eh_ponto(fim):
            return self._normalizar_angulo(
                degrees(atan2(-(float(fim[1]) - float(origem[1])), float(fim[0]) - float(origem[0])))
            )
        try:
            return self._normalizar_angulo(float(el.get("fio_angulo") or 0.0))
        except Exception:
            return 0.0

    def _proximo_eixo_fio(self, angulo_atual: float) -> float:
        atual = self._normalizar_angulo(angulo_atual)
        for idx, eixo in enumerate(self.EIXOS_FIO):
            if self._distancia_angular(atual, eixo) <= 1e-6:
                return self.EIXOS_FIO[(idx + 1) % len(self.EIXOS_FIO)]
        return self.EIXOS_FIO[0]

    @staticmethod
    def _delta_angular(origem: float, destino: float) -> float:
        return ((float(destino) - float(origem) + 180.0) % 360.0) - 180.0

    @staticmethod
    def _distancia_angular(a: float, b: float) -> float:
        return abs(((float(a) - float(b) + 180.0) % 360.0) - 180.0)

    @staticmethod
    def _normalizar_angulo(angulo: float) -> float:
        valor = float(angulo) % 360.0
        return 0.0 if abs(valor - 360.0) <= 1e-9 else valor

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    @staticmethod
    def _rotacao_duplo_clique_ativa(canvas) -> bool:
        janela = canvas.window() if hasattr(canvas, "window") else None
        opcoes = getattr(janela, "_opcoes_app", {}) if janela is not None else {}
        return bool(opcoes.get("rotacionar_duplo_clique", True))
