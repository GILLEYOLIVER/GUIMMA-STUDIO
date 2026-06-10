from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class Ferramenta(FerramentaBase):
    id_ferramenta = "definir_curva"
    nome = "Definir curva"
    usa_painel_auxiliar = False
    _dlg_global: QDialog | None = None
    _edt_pontos_global: QLineEdit | None = None

    def __init__(self):
        super().__init__()
        self._dlg: QDialog | None = type(self)._dlg_global
        self._edt_pontos: QLineEdit | None = type(self)._edt_pontos_global
        self._inicio: tuple[int, int, QPointF] | None = None
        self._hover: tuple[int, int, QPointF] | None = None

    def on_activate(self, canvas) -> None:
        self._inicio = None
        self._hover = None
        self._abrir_dialogo(canvas)
        self.set_status("Clique no primeiro ponto do trecho.")
        canvas.update()

    def on_deactivate(self, canvas) -> None:
        if self._dlg:
            self._dlg.hide()
        self._inicio = None
        self._hover = None
        canvas.update()

    def on_canvas_resize(self, canvas) -> None:
        self._reposicionar_dialogo(canvas)

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_cena(canvas, event)
        self._hover = self._ponto_contorno_em_posicao(canvas, pos)
        canvas.update()
        event.accept()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._inicio = None
            self.set_status("Seleção cancelada. Clique no primeiro ponto do trecho.")
            canvas.update()
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = self._posicao_cena(canvas, event)
        alvo = self._ponto_contorno_em_posicao(canvas, pos)
        if alvo is None:
            self.set_status("Nenhum ponto do contorno encontrado.")
            return False

        if self._inicio is None:
            self._inicio = alvo
            self._hover = alvo
            self.set_status("Ponto inicial definido. Clique no ponto final do trecho.")
            canvas.update()
            event.accept()
            return True

        idx_inicio, ponto_inicio_idx, _ponto_inicio = self._inicio
        idx_fim, ponto_fim_idx, _ponto_fim = alvo
        if idx_inicio != idx_fim:
            self.set_status("O ponto final precisa estar no mesmo elemento.")
            event.accept()
            return True
        if ponto_inicio_idx == ponto_fim_idx:
            self.set_status("Escolha um ponto final diferente do inicial.")
            event.accept()
            return True

        if self._aplicar_trecho(canvas, idx_inicio, ponto_inicio_idx, ponto_fim_idx):
            if hasattr(canvas, "_registrar_historico"):
                canvas._registrar_historico()
            self.set_status("Trecho atualizado.")
            self._inicio = None
            self._hover = None
            canvas.update()
            event.accept()
            return True

        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._inicio is not None:
            self._desenhar_marcador(canvas, painter, self._inicio[2], QColor("#0b7fb8"), 6)
        if self._hover is not None:
            self._desenhar_marcador(canvas, painter, self._hover[2], QColor("#ff8a00"), 5)
        painter.restore()

    def set_status(self, texto: str):
        try:
            if self._dlg is not None:
                self._dlg.setToolTip(texto)
        except Exception:
            pass

    def _abrir_dialogo(self, canvas) -> None:
        cls = type(self)
        if cls._dlg_global is not None:
            try:
                cls._dlg_global.isVisible()
            except RuntimeError:
                cls._dlg_global = None
                cls._edt_pontos_global = None
        if cls._dlg_global is None:
            cls._dlg_global = QDialog(canvas)
            cls._dlg_global.setObjectName("guimma_definir_curva_dialog")
            cls._dlg_global.setWindowTitle("Nº pontos")
            cls._dlg_global.setWindowFlags(Qt.Tool)
            layout = QFormLayout(cls._dlg_global)
            cls._edt_pontos_global = QLineEdit("2")
            cls._edt_pontos_global.setSelectAllEnabled(True)
            layout.addRow("Nº pontos", cls._edt_pontos_global)
            cls._dlg_global.setFixedWidth(205)
            instalar_memoria_posicao(cls._dlg_global, "dialog:definir_curva")
        self._dlg = cls._dlg_global
        self._edt_pontos = cls._edt_pontos_global
        if not self._dlg.isVisible():
            self._dlg.show()
        self._reposicionar_dialogo(canvas)

    def _reposicionar_dialogo(self, canvas) -> None:
        if not self._dlg:
            return
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos = canvas.calcular_posicao_painel_auxiliar(self._dlg.width(), self._dlg.height(), abaixo_coordenadas=True)
            restaurar_posicao(self._dlg, "dialog:definir_curva", fallback=canvas.mapToGlobal(pos))

    def _ler_quantidade(self) -> int:
        texto = self._edt_pontos.text() if self._edt_pontos else "2"
        try:
            valor = int(float(str(texto).replace(",", ".")))
        except Exception:
            valor = 2
        valor = max(2, min(valor, 99))
        if self._edt_pontos:
            self._edt_pontos.setText(str(valor))
        return valor

    def _posicao_cena(self, canvas, event) -> QPointF:
        try:
            return canvas._ponto_com_snap(event.position())
        except Exception:
            if hasattr(canvas, "_tela_para_cena"):
                return canvas._tela_para_cena(event.position())
            return QPointF(event.position())

    def _ponto_contorno_em_posicao(self, canvas, pos: QPointF) -> tuple[int, int, QPointF] | None:
        tolerancia = 12.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor: tuple[float, int, int, QPointF] | None = None
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if not isinstance(el, dict) or el.get("tipo") != "polyline":
                continue
            pontos = self._pontos_base(el)
            for ponto_idx, ponto in enumerate(pontos):
                dist = self._dist(ponto, pos)
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, ponto_idx, ponto)
        if melhor is None:
            return None
        _dist, idx, ponto_idx, ponto = melhor
        return idx, ponto_idx, QPointF(ponto)

    def _aplicar_trecho(self, canvas, idx: int, inicio_idx: int, fim_idx: int) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        pontos = self._pontos_base(el)
        if len(pontos) < 2:
            self.set_status("Elemento sem pontos suficientes.")
            return False
        fechado = self._fechado(el, pontos)
        inicio_idx = max(0, min(inicio_idx, len(pontos) - 1))
        fim_idx = max(0, min(fim_idx, len(pontos) - 1))
        trecho = self._trecho_indices(pontos, inicio_idx, fim_idx, fechado)
        if len(trecho) < 2:
            self.set_status("Trecho inválido.")
            return False

        quantidade = self._ler_quantidade()
        inicio = QPointF(trecho[0])
        fim = QPointF(trecho[-1])
        auxiliares_novos: list[QPointF] = []
        if quantidade >= 3:
            auxiliares_novos = [
                self._ponto_no_trecho_por_fracao(trecho, i / (quantidade + 1))
                for i in range(1, quantidade + 1)
            ]
        novo_trecho = [inicio, *auxiliares_novos, fim]
        novos_pontos = self._substituir_trecho(pontos, inicio_idx, fim_idx, novo_trecho, fechado)
        el["pontos"] = [(float(p.x()), float(p.y())) for p in novos_pontos]
        if fechado and el["pontos"][0] != el["pontos"][-1]:
            el["pontos"].append(el["pontos"][0])
        el["fechado"] = fechado

        if el.get("molde"):
            self._atualizar_auxiliares_molde(el, trecho, auxiliares_novos)
        elif el.get("curva_suave") or el.get("curva_editavel") or el.get("pontos_controle_curva"):
            controles = [(float(p.x()), float(p.y())) for p in novos_pontos]
            el["pontos_controle_curva"] = controles
            el["pontos_principais"] = controles
            el["pontos_controle"] = controles
            el["curva_suave"] = quantidade >= 3

        return True

    def _atualizar_auxiliares_molde(self, el: dict, trecho: list[QPointF], auxiliares_novos: list[QPointF]) -> None:
        antigos = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        mantidos = [p for p in antigos if not self._ponto_no_trecho(p, trecho)]
        todos_aux = [*mantidos, *auxiliares_novos]
        el["controle_auxiliares"] = [(float(p.x()), float(p.y())) for p in todos_aux]
        el["pontos_auxiliares"] = [{"x": float(p.x()), "y": float(p.y())} for p in todos_aux]

        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        el["controle_cantos"] = [(float(p.x()), float(p.y())) for p in cantos]
        el["pontos_controle_principais"] = [{"x": float(p.x()), "y": float(p.y())} for p in cantos]

    def _pontos_base(self, el: dict) -> list[QPointF]:
        pontos = [p for p in (self._ponto_qt(item) for item in el.get("pontos", []) or []) if p is not None]
        if len(pontos) >= 2 and self._dist(pontos[0], pontos[-1]) <= 1e-7:
            pontos = pontos[:-1]
        return pontos

    def _fechado(self, el: dict, pontos: list[QPointF]) -> bool:
        if bool(el.get("fechado")):
            return True
        raw = [p for p in (self._ponto_qt(item) for item in el.get("pontos", []) or []) if p is not None]
        return len(raw) >= 3 and self._dist(raw[0], raw[-1]) <= 1e-7

    def _trecho_indices(self, pontos: list[QPointF], inicio: int, fim: int, fechado: bool) -> list[QPointF]:
        if not fechado:
            passo = 1 if inicio <= fim else -1
            return [QPointF(pontos[i]) for i in range(inicio, fim + passo, passo)]
        saida = [QPointF(pontos[inicio])]
        i = inicio
        while i != fim:
            i = (i + 1) % len(pontos)
            saida.append(QPointF(pontos[i]))
            if len(saida) > len(pontos) + 1:
                break
        return saida

    def _substituir_trecho(
        self,
        pontos: list[QPointF],
        inicio: int,
        fim: int,
        novo_trecho: list[QPointF],
        fechado: bool,
    ) -> list[QPointF]:
        if not fechado:
            if inicio <= fim:
                return [*pontos[:inicio], *novo_trecho, *pontos[fim + 1 :]]
            return [*pontos[:fim], *reversed(novo_trecho), *pontos[inicio + 1 :]]
        if inicio <= fim:
            return [*pontos[:inicio], *novo_trecho, *pontos[fim + 1 :]]
        return [*novo_trecho, *pontos[fim + 1 : inicio]]

    def _ponto_no_trecho_por_fracao(self, pontos: list[QPointF], fracao: float) -> QPointF:
        total = sum(self._dist(a, b) for a, b in zip(pontos, pontos[1:]))
        if total <= 1e-9:
            return QPointF(pontos[0])
        alvo = total * max(0.0, min(1.0, fracao))
        acumulado = 0.0
        for a, b in zip(pontos, pontos[1:]):
            dist = self._dist(a, b)
            if dist <= 1e-9:
                continue
            if acumulado + dist >= alvo:
                t = (alvo - acumulado) / dist
                return QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
            acumulado += dist
        return QPointF(pontos[-1])

    def _ponto_no_trecho(self, ponto: QPointF, trecho: list[QPointF]) -> bool:
        if len(trecho) < 2:
            return False
        tol = 1e-5
        for a, b in zip(trecho, trecho[1:]):
            if self._dist_ponto_segmento(ponto, a, b) <= tol:
                return True
        return False

    def _desenhar_marcador(self, canvas, painter: QPainter, ponto: QPointF, cor: QColor, raio: int) -> None:
        tela = canvas._cena_para_tela(ponto)
        painter.setPen(QPen(QColor("#ffffff"), 1.2))
        painter.setBrush(cor)
        painter.drawEllipse(int(tela.x() - raio), int(tela.y() - raio), raio * 2, raio * 2)

    @staticmethod
    def _ponto_qt(valor) -> QPointF | None:
        try:
            if isinstance(valor, QPointF):
                return QPointF(valor)
            if isinstance(valor, dict):
                return QPointF(float(valor["x"]), float(valor["y"]))
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return QPointF(float(valor[0]), float(valor[1]))
        except Exception:
            return None
        return None

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

    def _dist_ponto_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        vx = b.x() - a.x()
        vy = b.y() - a.y()
        wx = p.x() - a.x()
        wy = p.y() - a.y()
        denom = vx * vx + vy * vy
        if denom <= 1e-12:
            return self._dist(p, a)
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
        proj = QPointF(a.x() + vx * t, a.y() + vy * t)
        return self._dist(p, proj)
