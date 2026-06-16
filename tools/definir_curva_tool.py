from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QSpinBox

from core.formatacao import numero_decimal_ponto
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class Ferramenta(FerramentaBase):
    id_ferramenta = "definir_curva"
    nome = "Definir curva"
    usa_painel_auxiliar = False
    _dlg_global: QDialog | None = None
    _edt_pontos_global: QLineEdit | QSpinBox | None = None
    _canvas_preview_global = None
    _preview_signal_conectado = False

    def __init__(self):
        super().__init__()
        self._dlg: QDialog | None = type(self)._dlg_global
        self._edt_pontos: QLineEdit | QSpinBox | None = type(self)._edt_pontos_global
        self._inicio: tuple[int, int, QPointF] | None = None
        self._hover: tuple[int, int, QPointF] | None = None

    def on_activate(self, canvas) -> None:
        self._inicio = None
        self._hover = None
        type(self)._canvas_preview_global = canvas
        self._abrir_dialogo(canvas)
        self.set_status("Clique no primeiro ponto do trecho.")
        canvas.update()

    def on_deactivate(self, canvas) -> None:
        if self._dlg:
            self._dlg.hide()
        if type(self)._canvas_preview_global is canvas:
            type(self)._canvas_preview_global = None
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
        self._desenhar_preview_trecho(canvas, painter)
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
                cls._preview_signal_conectado = False
        if cls._dlg_global is None:
            cls._dlg_global = QDialog(canvas)
            cls._dlg_global.setObjectName("guimma_definir_curva_dialog")
            cls._dlg_global.setWindowTitle("Pontos auxiliares")
            cls._dlg_global.setWindowFlags(Qt.Tool)
            layout = QFormLayout(cls._dlg_global)
            cls._edt_pontos_global = QSpinBox()
            cls._edt_pontos_global.setRange(2, 99)
            cls._edt_pontos_global.setValue(2)
            cls._edt_pontos_global.setToolTip("2 deixa o trecho reto com um auxiliar no meio; 3 ou mais mantém curva.")
            layout.addRow("Auxiliares", cls._edt_pontos_global)
            cls._dlg_global.setFixedWidth(205)
            instalar_memoria_posicao(cls._dlg_global, "dialog:definir_curva")
            cls._preview_signal_conectado = False
        self._dlg = cls._dlg_global
        self._edt_pontos = cls._edt_pontos_global
        cls._canvas_preview_global = canvas
        if self._edt_pontos is not None and hasattr(self._edt_pontos, "setKeyboardTracking"):
            self._edt_pontos.setKeyboardTracking(True)
        if self._edt_pontos is not None and hasattr(self._edt_pontos, "valueChanged") and not cls._preview_signal_conectado:
            self._edt_pontos.valueChanged.connect(lambda *_args: Ferramenta._atualizar_preview_global())
            cls._preview_signal_conectado = True
        if not self._dlg.isVisible():
            self._dlg.show()
        self._reposicionar_dialogo(canvas)

    @classmethod
    def _atualizar_preview_global(cls) -> None:
        canvas = cls._canvas_preview_global
        if canvas is not None and hasattr(canvas, "update"):
            canvas.update()

    def _reposicionar_dialogo(self, canvas) -> None:
        if not self._dlg:
            return
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos = canvas.calcular_posicao_painel_auxiliar(self._dlg.width(), self._dlg.height(), abaixo_coordenadas=True)
            restaurar_posicao(self._dlg, "dialog:definir_curva", fallback=canvas.mapToGlobal(pos))

    def _ler_quantidade(self) -> int:
        if self._edt_pontos is not None and hasattr(self._edt_pontos, "value"):
            interpretar = getattr(self._edt_pontos, "interpretText", None)
            if callable(interpretar):
                interpretar()
            valor = int(self._edt_pontos.value())
            valor = max(2, min(valor, 99))
            self._edt_pontos.setValue(valor)
            return valor
        texto = self._edt_pontos.text() if self._edt_pontos else "2"
        valor = int(numero_decimal_ponto(texto, 2.0))
        valor = max(2, min(valor, 99))
        if self._edt_pontos:
            self._edt_pontos.setText(str(valor))
        return valor

    def _ler_quantidade_preview(self) -> int:
        try:
            if self._edt_pontos is not None and hasattr(self._edt_pontos, "value"):
                return max(2, min(int(self._edt_pontos.value()), 99))
            texto = self._edt_pontos.text() if self._edt_pontos else "2"
            return max(2, min(int(numero_decimal_ponto(texto, 2.0)), 99))
        except Exception:
            return 2

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
            pontos_clique = self._pontos_clique_molde(el, pontos) if el.get("molde") else list(enumerate(pontos))
            for ponto_idx, ponto in pontos_clique:
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
        passo = self._passo_trecho_horario(pontos, inicio_idx, fim_idx, fechado)
        trecho = self._trecho_indices(pontos, inicio_idx, fim_idx, fechado, passo=passo)
        if len(trecho) < 2:
            self.set_status("Trecho inválido.")
            return False

        quantidade = self._ler_quantidade()
        inicio = QPointF(trecho[0])
        fim = QPointF(trecho[-1])
        auxiliares_novos = self._auxiliares_para_quantidade(trecho, quantidade)
        controles_trecho = [inicio, *auxiliares_novos, fim]
        novo_trecho = self._amostrar_trecho_visual(controles_trecho, quantidade)
        novos_pontos = self._substituir_trecho(pontos, inicio_idx, fim_idx, novo_trecho, fechado, passo=passo)
        el["pontos"] = [(float(p.x()), float(p.y())) for p in novos_pontos]
        if fechado and el["pontos"][0] != el["pontos"][-1]:
            el["pontos"].append(el["pontos"][0])
        el["fechado"] = fechado

        if el.get("molde"):
            self._atualizar_auxiliares_molde(el, trecho, auxiliares_novos)
            el["pontos_tracado_real"] = True
        elif el.get("curva_suave") or el.get("curva_editavel") or el.get("pontos_controle_curva"):
            controles = [(float(p.x()), float(p.y())) for p in controles_trecho]
            el["pontos_controle_curva"] = controles
            el["pontos_principais"] = controles
            el["pontos_controle"] = controles
            el["curva_suave"] = quantidade >= 3

        return True

    def _preview_trecho(self, canvas) -> dict | None:
        if self._inicio is None or self._hover is None:
            return None
        idx_inicio, ponto_inicio_idx, _ponto_inicio = self._inicio
        idx_fim, ponto_fim_idx, _ponto_fim = self._hover
        if idx_inicio != idx_fim or ponto_inicio_idx == ponto_fim_idx:
            return None
        if not (0 <= idx_inicio < len(canvas.cena.elementos)):
            return None
        el = canvas.cena.elementos[idx_inicio]
        pontos = self._pontos_base(el)
        if len(pontos) < 2:
            return None
        fechado = self._fechado(el, pontos)
        if not (0 <= ponto_inicio_idx < len(pontos) and 0 <= ponto_fim_idx < len(pontos)):
            return None
        passo = self._passo_trecho_horario(pontos, ponto_inicio_idx, ponto_fim_idx, fechado)
        trecho = self._trecho_indices(pontos, ponto_inicio_idx, ponto_fim_idx, fechado, passo=passo)
        if len(trecho) < 2:
            return None
        quantidade = self._ler_quantidade_preview()
        auxiliares = self._auxiliares_para_quantidade(trecho, quantidade)
        controles = [QPointF(trecho[0]), *auxiliares, QPointF(trecho[-1])]
        amostras = self._amostrar_trecho_visual(controles, quantidade)
        return {
            "trecho": trecho,
            "auxiliares": auxiliares,
            "amostras": amostras,
            "controles": controles,
            "quantidade": quantidade,
        }

    def _desenhar_preview_trecho(self, canvas, painter: QPainter) -> None:
        preview = self._preview_trecho(canvas)
        if not preview:
            return
        amostras = preview.get("amostras") or []
        auxiliares = preview.get("auxiliares") or []
        trecho = preview.get("trecho") or []

        if len(trecho) >= 2:
            pen_antigo = QPen(QColor(255, 138, 0, 150), 1.2, Qt.DashLine)
            pen_antigo.setCapStyle(Qt.RoundCap)
            pen_antigo.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen_antigo)
            painter.setBrush(Qt.NoBrush)
            self._desenhar_caminho_pontos(canvas, painter, trecho)

        if len(amostras) >= 2:
            pen_novo = QPen(QColor("#00d6ff"), 3.0)
            pen_novo.setCapStyle(Qt.RoundCap)
            pen_novo.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen_novo)
            painter.setBrush(Qt.NoBrush)
            self._desenhar_caminho_pontos(canvas, painter, amostras)

        for idx, ponto in enumerate(auxiliares, start=1):
            tela = canvas._cena_para_tela(ponto)
            painter.setPen(QPen(QColor("#ffffff"), 1.1))
            painter.setBrush(QColor("#ff3b30"))
            painter.drawEllipse(int(tela.x() - 4), int(tela.y() - 4), 8, 8)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(tela.x() + 7), int(tela.y() - 7), str(idx))

    def _desenhar_caminho_pontos(self, canvas, painter: QPainter, pontos: list[QPointF]) -> None:
        if len(pontos) < 2:
            return
        path = QPainterPath(canvas._cena_para_tela(pontos[0]))
        for ponto in pontos[1:]:
            path.lineTo(canvas._cena_para_tela(ponto))
        painter.drawPath(path)

    def _auxiliares_para_quantidade(self, trecho: list[QPointF], quantidade: int) -> list[QPointF]:
        if len(trecho) < 2:
            return []
        inicio = QPointF(trecho[0])
        fim = QPointF(trecho[-1])
        if quantidade <= 2:
            return [QPointF((inicio.x() + fim.x()) / 2.0, (inicio.y() + fim.y()) / 2.0)]
        return [
            self._ponto_no_trecho_por_fracao(trecho, i / (quantidade + 1))
            for i in range(1, quantidade + 1)
        ]

    def _amostrar_trecho_visual(self, controles: list[QPointF], quantidade: int) -> list[QPointF]:
        pts = [QPointF(p) for p in controles]
        if len(pts) <= 3 or quantidade <= 2:
            return pts
        saida: list[QPointF] = []
        total = len(pts)
        intervalos = max(1, total - 1)
        amostras = max(6, min(36, int(420 / intervalos)))
        for i in range(intervalos):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2] if i + 2 < total else p2
            if i == 0:
                saida.append(QPointF(p1))
            for s in range(1, amostras + 1):
                saida.append(self._catmull_rom_centripeta(p0, p1, p2, p3, s / float(amostras)))
        return self._limitar_trecho_ao_envelope_controles(saida, pts)

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

    def _pontos_clique_molde(self, el: dict, pontos: list[QPointF]) -> list[tuple[int, QPointF]]:
        controles: list[QPointF] = []
        for chave in ("controle_cantos", "pontos_controle_principais", "pontos_graduacao"):
            origem = el.get(chave)
            if not isinstance(origem, list) or not origem:
                continue
            controles = [p for p in (self._ponto_qt(item) for item in origem) if p is not None]
            break
        if len(controles) > 1 and self._dist(controles[0], controles[-1]) <= 1e-7:
            controles = controles[:-1]
        if not controles:
            return list(enumerate(pontos))
        saida: list[tuple[int, QPointF]] = []
        usados: set[int] = set()
        for controle in controles:
            idx = self._indice_ponto_mais_proximo(pontos, controle, usados=usados)
            if idx is None:
                continue
            usados.add(idx)
            saida.append((idx, QPointF(controle)))
        return saida

    def _indice_ponto_mais_proximo(
        self,
        pontos: list[QPointF],
        alvo: QPointF,
        *,
        usados: set[int] | None = None,
    ) -> int | None:
        if not pontos:
            return None
        usados = usados or set()
        candidatos = [
            (self._dist(ponto, alvo), idx)
            for idx, ponto in enumerate(pontos)
            if idx not in usados
        ]
        if not candidatos:
            candidatos = [(self._dist(ponto, alvo), idx) for idx, ponto in enumerate(pontos)]
        return min(candidatos, key=lambda item: item[0])[1] if candidatos else None

    def _fechado(self, el: dict, pontos: list[QPointF]) -> bool:
        if bool(el.get("fechado")):
            return True
        raw = [p for p in (self._ponto_qt(item) for item in el.get("pontos", []) or []) if p is not None]
        return len(raw) >= 3 and self._dist(raw[0], raw[-1]) <= 1e-7

    def _passo_trecho_horario(self, pontos: list[QPointF], inicio: int, fim: int, fechado: bool) -> int:
        if not fechado:
            return 1 if inicio <= fim else -1
        return 1 if self._contorno_horario_tela(pontos) else -1

    def _contorno_horario_tela(self, pontos: list[QPointF]) -> bool:
        if len(pontos) < 3:
            return True
        area = 0.0
        for atual, prox in zip(pontos, [*pontos[1:], pontos[0]]):
            area += (atual.x() * prox.y()) - (atual.y() * prox.x())
        return area >= 0.0

    def _trecho_indices(self, pontos: list[QPointF], inicio: int, fim: int, fechado: bool, *, passo: int | None = None) -> list[QPointF]:
        if not fechado:
            passo_local = 1 if inicio <= fim else -1
            return [QPointF(pontos[i]) for i in range(inicio, fim + passo_local, passo_local)]
        passo_local = 1 if passo is None or passo >= 0 else -1
        saida = [QPointF(pontos[inicio])]
        i = inicio
        while i != fim:
            i = (i + passo_local) % len(pontos)
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
        *,
        passo: int | None = None,
    ) -> list[QPointF]:
        if not fechado:
            if inicio <= fim:
                return [*pontos[:inicio], *novo_trecho, *pontos[fim + 1 :]]
            return [*pontos[:fim], *reversed(novo_trecho), *pontos[inicio + 1 :]]
        if passo is not None and passo < 0:
            return self._substituir_arco_fechado(pontos, fim, inicio, list(reversed(novo_trecho)))
        return self._substituir_arco_fechado(pontos, inicio, fim, novo_trecho)

    def _substituir_arco_fechado(
        self,
        pontos: list[QPointF],
        inicio: int,
        fim: int,
        novo_trecho: list[QPointF],
    ) -> list[QPointF]:
        if inicio <= fim:
            return [*pontos[:inicio], *novo_trecho, *pontos[fim + 1 :]]
        return [QPointF(novo_trecho[-1]), *pontos[fim + 1 : inicio], *novo_trecho[:-1]]

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

    def _catmull_rom_centripeta(self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        def tj(ti: float, a: QPointF, b: QPointF) -> float:
            return ti + max(self._dist(a, b), 1e-6) ** 0.5

        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        t = t1 + max(0.0, min(1.0, t)) * (t2 - t1)

        def interp(a: QPointF, b: QPointF, ta: float, tb: float) -> QPointF:
            den = max(tb - ta, 1e-9)
            return QPointF(
                ((tb - t) / den) * a.x() + ((t - ta) / den) * b.x(),
                ((tb - t) / den) * a.y() + ((t - ta) / den) * b.y(),
            )

        a1 = interp(p0, p1, t0, t1)
        a2 = interp(p1, p2, t1, t2)
        a3 = interp(p2, p3, t2, t3)
        b1 = interp(a1, a2, t0, t2)
        b2 = interp(a2, a3, t1, t3)
        return interp(b1, b2, t1, t2)

    def _limitar_trecho_ao_envelope_controles(self, pontos: list[QPointF], controles: list[QPointF]) -> list[QPointF]:
        if len(pontos) < 3 or len(controles) < 2:
            return pontos
        xs = [p.x() for p in controles]
        ys = [p.y() for p in controles]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        margem_x = max(0.001, (max_x - min_x) * 0.015)
        margem_y = max(0.001, (max_y - min_y) * 0.015)
        controles_assinatura = {(round(p.x(), 7), round(p.y(), 7)) for p in controles}
        saida: list[QPointF] = []
        for ponto in pontos:
            assinatura = (round(ponto.x(), 7), round(ponto.y(), 7))
            if assinatura in controles_assinatura:
                saida.append(QPointF(ponto))
                continue
            saida.append(
                QPointF(
                    max(min_x - margem_x, min(max_x + margem_x, ponto.x())),
                    max(min_y - margem_y, min(max_y + margem_y, ponto.y())),
                )
            )
        return saida
