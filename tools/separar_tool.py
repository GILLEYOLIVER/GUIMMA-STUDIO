from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, hypot, pi, sin
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QDialog, QVBoxLayout

from canvas.visualizacao import VisualizacaoCanvas
from tools.movimento_utils import mover_elemento_por_delta
from tools.tool_base import FerramentaBase


class SepararTamanhosDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SepararTamanhosDialog")
        self.setWindowTitle("Separar tamanhos do molde")
        self.setWindowFlags(Qt.Tool)
        self.setFixedWidth(230)
        self._guimma_ignorar_patch_posicao = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.chk_todos = QCheckBox("Separar todos os tamanhos")
        self.chk_todos.setChecked(False)
        layout.addWidget(self.chk_todos)

        self.setStyleSheet(
            """
            QDialog#SepararTamanhosDialog { background:#f2f2f2; color:#111; }
            QCheckBox { color:#111; font-size:11px; spacing:5px; }
            """
        )

    def separar_todos(self) -> bool:
        return bool(self.chk_todos.isChecked())


class Ferramenta(FerramentaBase):
    id_ferramenta = "separar"
    nome = "Separar"
    descricao_painel = "Destaca um tamanho graduado e cria uma cópia separada do molde."

    def __init__(self):
        super().__init__()
        self._hover: dict | None = None
        self._hover_pos: QPointF | None = None
        self._arrastando_idx: int | None = None
        self._arrastando_indices: list[int] = []
        self._ultimo_pos_arrasto: QPointF | None = None
        self._origem_arrasto: QPointF | None = None
        self._guia_angular: tuple[QPointF, QPointF, float] | None = None
        self._dialog: SepararTamanhosDialog | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover = None
        self._hover_pos = None
        self._arrastando_idx = None
        self._arrastando_indices = []
        self._ultimo_pos_arrasto = None
        self._origem_arrasto = None
        self._guia_angular = None
        self._abrir_dialogo(canvas)
        self._status(canvas, "Separar Tamanhos: passe sobre um tamanho e clique para retirar uma cópia.")
        if hasattr(canvas, "update"):
            canvas.update()

    def on_deactivate(self, canvas):
        self._esconder_dialogo()
        self._hover = None
        self._hover_pos = None
        self._arrastando_idx = None
        self._arrastando_indices = []
        self._ultimo_pos_arrasto = None
        self._origem_arrasto = None
        self._guia_angular = None
        if hasattr(canvas, "update"):
            canvas.update()

    def on_canvas_resize(self, canvas) -> None:
        self._reposicionar_dialogo(canvas)

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._pos_cena(canvas, event.position())
        if self._arrastando_indices:
            self._arrastar_copia(canvas, pos)
            event.accept()
            return True
        self._hover = self._candidato_em_posicao(canvas, pos)
        self._hover_pos = QPointF(pos) if self._hover is not None else None
        if hasattr(canvas, "update"):
            canvas.update()
        event.accept()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        pos = self._pos_cena(canvas, event.position())
        if self._arrastando_indices:
            if event.button() == Qt.LeftButton:
                self._finalizar_arraste(canvas)
                event.accept()
                return True
            if event.button() == Qt.RightButton:
                self._cancelar_arraste(canvas)
                event.accept()
                return True
            return False

        if event.button() != Qt.LeftButton:
            return False
        candidatos = self._candidatos_do_clique(canvas, pos)
        if not candidatos:
            if self._separar_todos_marcado():
                self._status(canvas, "Separar Tamanhos: clique dentro do molde ou sobre uma linha de tamanho.")
            else:
                self._status(canvas, "Separar Tamanhos: clique sobre a linha do tamanho desejado.")
            event.accept()
            return True
        indices = [idx for item in candidatos if (idx := self._criar_copia_tamanho(canvas, item)) is not None]
        if not indices:
            self._status(canvas, "Separar Tamanhos: não foi possível criar a cópia desse tamanho.")
            event.accept()
            return True
        self._hover = None
        self._hover_pos = None
        self._arrastando_indices = indices
        self._arrastando_idx = indices[-1]
        self._ultimo_pos_arrasto = QPointF(pos)
        self._origem_arrasto = QPointF(pos)
        self._guia_angular = None
        canvas._selecionados = set(indices)
        if len(indices) == 1:
            self._status(canvas, "Tamanho em mãos: mova o mouse e clique esquerdo para soltar. Direito cancela.")
        else:
            self._status(canvas, "Tamanhos em mãos: mova o mouse e clique esquerdo para soltar. Direito cancela.")
        canvas.update()
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        if event.key() == Qt.Key_Escape:
            if self._arrastando_indices:
                self._cancelar_arraste(canvas)
            else:
                self._hover = None
                self._hover_pos = None
                canvas.set_ferramenta_ativa("selecionar")
                canvas.update()
            event.accept()
            return True
        return False

    def on_paint_overlay(self, canvas, painter: QPainter):
        if self._hover is not None:
            self._desenhar_contorno(canvas, painter, self._hover["pontos"], QColor("#2da8ff"), 2.6)
            self._desenhar_rotulo(
                canvas,
                painter,
                self._hover["pontos"],
                str(self._hover["nome_tamanho"]),
                self._hover_pos,
            )
        if self._guia_angular is not None:
            origem, destino, angulo = self._guia_angular
            canvas._desenhar_segmento(painter, origem, destino, cor="#2da8ff", espessura=1.0)
            try:
                destino_tela = canvas._cena_para_tela(destino)
            except Exception:
                return
            painter.save()
            painter.setPen(QPen(QColor("#2da8ff"), 1))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(destino_tela + QPointF(4.0, -4.0), f"{angulo:g}°")
            painter.restore()

    def _abrir_dialogo(self, canvas) -> None:
        if not self._dialogo_valido():
            self._dialog = SepararTamanhosDialog(canvas)
        if self._dialog.parentWidget() is not canvas:
            self._dialog.setParent(canvas)
        if not self._dialog.isVisible():
            self._dialog.show()
        self._reposicionar_dialogo(canvas)

    def _reposicionar_dialogo(self, canvas) -> None:
        if not self._dialogo_valido():
            return
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos = canvas.calcular_posicao_painel_auxiliar(self._dialog.width(), self._dialog.height(), abaixo_coordenadas=True)
            self._dialog.move(canvas.mapToGlobal(pos))

    def _esconder_dialogo(self) -> None:
        if self._dialogo_valido():
            self._dialog.hide()

    def _dialogo_valido(self) -> bool:
        if self._dialog is None:
            return False
        try:
            self._dialog.isVisible()
            return True
        except RuntimeError:
            self._dialog = None
            return False

    def _separar_todos_marcado(self) -> bool:
        return bool(self._dialogo_valido() and self._dialog.separar_todos())

    def _candidatos_para_separar(self, canvas, candidato: dict) -> list[dict]:
        if not self._separar_todos_marcado():
            return [candidato]
        molde_idx = int(candidato.get("molde_idx", -1))
        return self._candidatos_do_molde(canvas, molde_idx)

    def _candidatos_do_clique(self, canvas, pos: QPointF) -> list[dict]:
        candidato = self._candidato_em_posicao(canvas, pos)
        if candidato is not None:
            return self._candidatos_para_separar(canvas, candidato)
        if not self._separar_todos_marcado():
            return []
        molde_idx = self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            return []
        return self._candidatos_do_molde(canvas, molde_idx)

    def _candidatos_do_molde(self, canvas, molde_idx: int) -> list[dict]:
        return [
            item
            for item in self._candidatos_tamanhos(canvas)
            if int(item.get("molde_idx", -2)) == molde_idx
        ]

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            try:
                idx = canvas._indice_molde_em_ponto(pos)
                if idx is not None:
                    return int(idx)
            except Exception:
                pass
        selecionados = list(getattr(canvas, "_selecionados", set()) or [])
        indices = selecionados + [
            idx for idx in range(len(getattr(canvas.cena, "elementos", []) or []))
            if idx not in selecionados
        ]
        for idx in indices:
            elementos = getattr(canvas.cena, "elementos", []) or []
            if not (0 <= idx < len(elementos)):
                continue
            molde = elementos[idx]
            if isinstance(molde, dict) and molde.get("molde") and self._ponto_dentro_molde(molde, pos):
                return idx
        return None

    def _ponto_dentro_molde(self, molde: dict, pos: QPointF) -> bool:
        pontos = self._pontos_base_molde(molde)
        if len(pontos) >= 3 and self._ponto_dentro_poligono(pos, pontos):
            return True
        return self._ponto_dentro_bbox(pontos, pos)

    @staticmethod
    def _ponto_dentro_poligono(pos: QPointF, pontos: list[QPointF]) -> bool:
        dentro = False
        j = len(pontos) - 1
        x = pos.x()
        y = pos.y()
        for i, pi in enumerate(pontos):
            pj = pontos[j]
            cruza = (pi.y() > y) != (pj.y() > y)
            if cruza:
                denom = pj.y() - pi.y()
                if abs(denom) > 1e-12:
                    x_inter = ((pj.x() - pi.x()) * (y - pi.y()) / denom) + pi.x()
                    if x < x_inter:
                        dentro = not dentro
            j = i
        return dentro

    @staticmethod
    def _ponto_dentro_bbox(pontos: list[QPointF], pos: QPointF) -> bool:
        if not pontos:
            return False
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        return min(xs) <= pos.x() <= max(xs) and min(ys) <= pos.y() <= max(ys)

    def _candidato_em_posicao(self, canvas, pos: QPointF) -> dict | None:
        melhor: tuple[float, dict] | None = None
        tolerancia = max(0.18, 14.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        for candidato in self._candidatos_tamanhos(canvas):
            dist = self._distancia_contorno(candidato["pontos"], pos)
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, candidato)
        return melhor[1] if melhor is not None else None

    def _candidatos_tamanhos(self, canvas) -> list[dict]:
        candidatos: list[dict] = []
        for idx, molde in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if not isinstance(molde, dict) or not molde.get("molde"):
                continue
            base = self._pontos_base_molde(molde)
            if len(base) < 2:
                continue
            controles_base = self._controles_base_molde(molde)
            auxiliares_base = self._auxiliares_base_molde(molde)
            linhas = self._linhas_tamanhos(molde)
            base_linha = self._linha_base(linhas)
            if base_linha is not None:
                candidatos.append(
                    {
                        "molde_idx": idx,
                        "nome_tamanho": self._nome_tamanho(base_linha),
                        "cor": str(base_linha.get("cor") or molde.get("cor") or "#ffffff"),
                        "pontos": self._fechar_contorno(base),
                        "controles": [QPointF(p) for p in controles_base],
                        "auxiliares": [QPointF(p) for p in auxiliares_base],
                    }
                )
            for nome, cor, pontos in VisualizacaoCanvas._contornos_graduacao_tabela(molde, base):
                pontos_tamanho = [QPointF(p) for p in pontos]
                candidatos.append(
                    {
                        "molde_idx": idx,
                        "nome_tamanho": str(nome),
                        "cor": str(cor),
                        "pontos": pontos_tamanho,
                        "controles": self._pontos_para_contorno_tamanho(base, pontos_tamanho, controles_base),
                        "auxiliares": self._pontos_para_contorno_tamanho(base, pontos_tamanho, auxiliares_base),
                    }
                )
        return candidatos

    def _criar_copia_tamanho(self, canvas, candidato: dict) -> int | None:
        idx_origem = int(candidato["molde_idx"])
        if not (0 <= idx_origem < len(canvas.cena.elementos)):
            return None
        origem = canvas.cena.elementos[idx_origem]
        if not isinstance(origem, dict):
            return None
        pontos = [QPointF(p) for p in candidato["pontos"]]
        if len(pontos) > 1 and self._dist(pontos[0], pontos[-1]) > 1e-7:
            pontos.append(QPointF(pontos[0]))
        if len(pontos) < 3:
            return None

        nome_origem = str(origem.get("nome_molde") or f"K{idx_origem + 1}").strip() or f"K{idx_origem + 1}"
        nome_tamanho = str(candidato.get("nome_tamanho") or "").strip()
        novo = deepcopy(origem)
        for chave in list(novo.keys()):
            if str(chave).startswith("graduacao_"):
                novo.pop(chave, None)
        novo["molde"] = True
        novo["molde_id"] = str(uuid4())
        novo["shape_id"] = str(uuid4())
        novo["nome_molde"] = f"{nome_origem} - {nome_tamanho}" if nome_tamanho else nome_origem
        novo["tamanho_extraido"] = nome_tamanho
        novo["origem_extracao"] = "separar_tamanho"
        novo["mostrar_graduacao"] = False
        novo["pontos_tracado_real"] = True
        novo["pontos"] = [(float(p.x()), float(p.y())) for p in pontos]
        sem_fechamento = pontos[:-1] if len(pontos) > 1 and self._dist(pontos[0], pontos[-1]) <= 1e-7 else pontos
        controles = [self._ponto_qt(p) for p in candidato.get("controles", []) or []]
        controles = [p for p in controles if p is not None]
        if not controles:
            controles = [QPointF(p) for p in sem_fechamento]
        auxiliares = [self._ponto_qt(p) for p in candidato.get("auxiliares", []) or []]
        auxiliares = [p for p in auxiliares if p is not None]
        novo["controle_cantos"] = [(float(p.x()), float(p.y())) for p in controles]
        novo["pontos_controle_principais"] = [{"x": float(p.x()), "y": float(p.y())} for p in controles]
        novo["pontos_graduacao"] = [{"x": float(p.x()), "y": float(p.y())} for p in controles]
        novo["controle_auxiliares"] = [(float(p.x()), float(p.y())) for p in auxiliares]
        novo["pontos_auxiliares"] = [{"x": float(p.x()), "y": float(p.y())} for p in auxiliares]
        novo["cor"] = str(candidato.get("cor") or novo.get("cor") or "#ffffff")
        self._reposicionar_textos_e_fio(novo, sem_fechamento)

        canvas.cena.elementos.append(novo)
        return len(canvas.cena.elementos) - 1

    def _arrastar_copia(self, canvas, pos: QPointF) -> None:
        indices = [idx for idx in self._arrastando_indices if 0 <= idx < len(canvas.cena.elementos)]
        if not indices:
            return
        pos_restrita = self._posicao_arrasto_com_ima(canvas, pos)
        if self._ultimo_pos_arrasto is None:
            self._ultimo_pos_arrasto = QPointF(pos_restrita)
            return
        dx = pos_restrita.x() - self._ultimo_pos_arrasto.x()
        dy = pos_restrita.y() - self._ultimo_pos_arrasto.y()
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            for idx in indices:
                mover_elemento_por_delta(canvas.cena.elementos[idx], dx, dy)
            self._ultimo_pos_arrasto = QPointF(pos_restrita)
            canvas.update()

    def _posicao_arrasto_com_ima(self, canvas, pos: QPointF) -> QPointF:
        snap_ativo = bool(getattr(canvas, "_snap_ativo", getattr(canvas, "snap_ativo", True)))
        if callable(getattr(canvas, "snap_ativo", None)):
            snap_ativo = bool(canvas.snap_ativo())
        if not snap_ativo:
            self._guia_angular = None
            return QPointF(pos)
        origem = self._origem_arrasto or self._ultimo_pos_arrasto
        if origem is None:
            self._guia_angular = None
            return QPointF(pos)
        dx = pos.x() - origem.x()
        dy = pos.y() - origem.y()
        raio = hypot(dx, dy)
        if raio <= 1e-9:
            self._guia_angular = None
            return QPointF(origem)
        angulo = (atan2(dy, dx) * 180.0 / pi) % 360.0
        alvos = tuple(float(a) for a in range(0, 360, 15))
        alvo = min(alvos, key=lambda a: min(abs(angulo - a), 360.0 - abs(angulo - a)))
        diferenca = min(abs(angulo - alvo), 360.0 - abs(angulo - alvo))
        if diferenca > 4.0:
            self._guia_angular = None
            return QPointF(pos)
        rad = alvo * pi / 180.0
        destino = QPointF(origem.x() + cos(rad) * raio, origem.y() + sin(rad) * raio)
        self._guia_angular = (QPointF(origem), QPointF(destino), alvo)
        return destino

    def _finalizar_arraste(self, canvas) -> None:
        self._arrastando_idx = None
        self._arrastando_indices = []
        self._ultimo_pos_arrasto = None
        self._origem_arrasto = None
        self._guia_angular = None
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        self._status(canvas, "Tamanho separado.")
        canvas.update()

    def _cancelar_arraste(self, canvas) -> None:
        for idx in sorted(self._arrastando_indices, reverse=True):
            if 0 <= idx < len(canvas.cena.elementos):
                canvas.cena.elementos.pop(idx)
        canvas._selecionados = set()
        self._arrastando_idx = None
        self._arrastando_indices = []
        self._ultimo_pos_arrasto = None
        self._origem_arrasto = None
        self._guia_angular = None
        self._status(canvas, "Separação cancelada.")
        canvas.update()

    def _reposicionar_textos_e_fio(self, molde: dict, pontos: list[QPointF]) -> None:
        if not pontos:
            return
        min_x = min(p.x() for p in pontos)
        max_x = max(p.x() for p in pontos)
        min_y = min(p.y() for p in pontos)
        max_y = max(p.y() for p in pontos)
        centro = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
        largura = max(0.1, max_x - min_x)
        y_fio = centro[1]
        fio_inicio = (centro[0] - largura * 0.25, y_fio)
        fio_fim = (centro[0] + largura * 0.25, y_fio)
        for chave in ("ponto_texto", "ponto_texto_nome", "nome_posicao", "nome_centro"):
            molde[chave] = centro
        molde["fio_origem"] = fio_inicio
        molde["fio_fim"] = fio_fim
        molde["fio_angulo"] = 0.0

    def _desenhar_contorno(self, canvas, painter: QPainter, pontos: list[QPointF], cor: QColor, esp: float) -> None:
        if len(pontos) < 2:
            return
        if hasattr(canvas, "_desenhar_polilinha"):
            canvas._desenhar_polilinha(painter, pontos, cor=cor.name(), espessura=esp, estilo="solid")
            return
        painter.save()
        painter.setPen(QPen(cor, esp))
        for a, b in zip(pontos, pontos[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def _desenhar_rotulo(
        self,
        canvas,
        painter: QPainter,
        pontos: list[QPointF],
        texto: str,
        pos_cursor: QPointF | None = None,
    ) -> None:
        if not pontos or not texto:
            return
        ancora = QPointF(pos_cursor) if pos_cursor is not None else QPointF(
            min(p.x() for p in pontos),
            min(p.y() for p in pontos),
        )
        try:
            tela = canvas._cena_para_tela(ancora)
        except Exception:
            return
        painter.save()
        painter.setPen(QPen(QColor("#2da8ff"), 1))
        painter.setFont(QFont("Arial", 11, QFont.Bold))
        painter.drawText(tela + QPointF(12.0, -12.0), texto)
        painter.restore()

    def _linhas_tamanhos(self, molde: dict) -> list[dict]:
        linhas = molde.get("graduacao_tamanhos")
        if not isinstance(linhas, list):
            return []
        return [dict(linha) for linha in linhas if isinstance(linha, dict) and linha.get("ativo", True)]

    def _linha_base(self, linhas: list[dict]) -> dict | None:
        if not linhas:
            return None
        return next((linha for linha in linhas if linha.get("base")), linhas[len(linhas) // 2])

    @staticmethod
    def _nome_tamanho(linha: dict) -> str:
        return str(linha.get("tamanho") or linha.get("nome") or "").strip()

    def _pontos_base_molde(self, molde: dict) -> list[QPointF]:
        origem = None
        for chave in (
            "pontos",
            "curva_pontos",
            "vertices",
            "pontos_molde",
            "pontos_tracado",
            "pontos_controle_curva",
            "pontos_controle",
            "pontos_graduacao",
            "pontos_controle_principais",
            "controle_cantos",
        ):
            valor = molde.get(chave)
            if isinstance(valor, list) and valor:
                origem = valor
                break
        pontos = [self._ponto_qt(p) for p in origem or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) > 1 and self._dist(pontos[0], pontos[-1]) <= 1e-7:
            pontos.pop()
        return pontos

    def _controles_base_molde(self, molde: dict) -> list[QPointF]:
        origem = None
        for chave in ("pontos_controle_principais", "controle_cantos", "pontos_graduacao"):
            valor = molde.get(chave)
            if isinstance(valor, list) and valor:
                origem = valor
                break
        pontos = [self._ponto_qt(p) for p in origem or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) > 1 and self._dist(pontos[0], pontos[-1]) <= 1e-7:
            pontos.pop()
        return pontos

    def _auxiliares_base_molde(self, molde: dict) -> list[QPointF]:
        origem = None
        for chave in ("controle_auxiliares", "pontos_auxiliares"):
            valor = molde.get(chave)
            if isinstance(valor, list) and valor:
                origem = valor
                break
        pontos = [self._ponto_qt(p) for p in origem or []]
        return [p for p in pontos if p is not None]

    def _pontos_para_contorno_tamanho(
        self,
        base: list[QPointF],
        pontos_tamanho: list[QPointF],
        pontos_base: list[QPointF],
    ) -> list[QPointF]:
        base_aberta = self._abrir_contorno(base)
        tamanho_aberto = self._abrir_contorno(pontos_tamanho)
        if not base_aberta or len(base_aberta) != len(tamanho_aberto):
            return [QPointF(p) for p in pontos_base]
        return [
            self._mapear_ponto_para_contorno_tamanho(ponto, base_aberta, tamanho_aberto)
            for ponto in pontos_base
        ]

    def _mapear_ponto_para_contorno_tamanho(
        self,
        ponto: QPointF,
        base: list[QPointF],
        tamanho: list[QPointF],
    ) -> QPointF:
        if not base or len(base) != len(tamanho):
            return QPointF(ponto)
        if len(base) == 1:
            return QPointF(tamanho[0])

        melhor: tuple[float, int, int, float] | None = None
        total = len(base)
        for idx in range(total):
            prox = (idx + 1) % total
            distancia, t = self._distancia_e_parametro_segmento(ponto, base[idx], base[prox])
            if melhor is None or distancia < melhor[0]:
                melhor = (distancia, idx, prox, t)
        if melhor is None:
            return QPointF(ponto)
        _distancia, idx, prox, t = melhor
        origem = tamanho[idx]
        destino = tamanho[prox]
        return QPointF(
            origem.x() + ((destino.x() - origem.x()) * t),
            origem.y() + ((destino.y() - origem.y()) * t),
        )

    def _fechar_contorno(self, pontos: list[QPointF]) -> list[QPointF]:
        saida = [QPointF(p) for p in pontos]
        if len(saida) > 1 and self._dist(saida[0], saida[-1]) > 1e-7:
            saida.append(QPointF(saida[0]))
        return saida

    def _abrir_contorno(self, pontos: list[QPointF]) -> list[QPointF]:
        saida = [QPointF(p) for p in pontos]
        if len(saida) > 1 and self._dist(saida[0], saida[-1]) <= 1e-7:
            saida.pop()
        return saida

    def _distancia_contorno(self, pontos: list[QPointF], pos: QPointF) -> float:
        if len(pontos) < 2:
            return float("inf")
        return min(self._distancia_segmento(pos, a, b) for a, b in zip(pontos, pontos[1:]))

    @staticmethod
    def _distancia_segmento(p: QPointF, a: QPointF, b: QPointF) -> float:
        distancia, _t = Ferramenta._distancia_e_parametro_segmento(p, a, b)
        return distancia

    @staticmethod
    def _distancia_e_parametro_segmento(p: QPointF, a: QPointF, b: QPointF) -> tuple[float, float]:
        ax, ay = a.x(), a.y()
        bx, by = b.x(), b.y()
        px, py = p.x(), p.y()
        dx = bx - ax
        dy = by - ay
        denom = (dx * dx) + (dy * dy)
        if denom <= 1e-12:
            return hypot(px - ax, py - ay), 0.0
        t = max(0.0, min(1.0, (((px - ax) * dx) + ((py - ay) * dy)) / denom))
        return hypot(px - (ax + dx * t), py - (ay + dy * t)), t

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
        return hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _pos_cena(canvas, pos) -> QPointF:
        ponto = QPointF(pos)
        if hasattr(canvas, "_tela_para_cena"):
            try:
                return QPointF(canvas._tela_para_cena(ponto))
            except Exception:
                pass
        return ponto

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
