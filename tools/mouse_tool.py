from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, degrees, hypot, radians, sin

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QDialog, QGridLayout, QLabel, QVBoxLayout

from core.graduacao import aplicar_grade_graduacao_referencia_canvas
from tools.tool_base import FerramentaBase


MODOS_MOUSE = ["Incremental", "Absoluto", "Proporcional"]


class GraduarMouseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Graduar via mouse")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedSize(200, 64)
        self.setObjectName("GraduarMouseDialog")

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(4)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)

        grid.addWidget(QLabel("Modo"), 0, 0)
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(MODOS_MOUSE)
        self.cmb_modo.setCurrentText("Incremental")
        grid.addWidget(self.cmb_modo, 0, 1)
        raiz.addLayout(grid)

        self.setStyleSheet(
            """
            QDialog#GraduarMouseDialog {
                background: #f4f4f4;
                color: #111111;
            }
            QLabel, QComboBox {
                color: #111111;
                font-size: 11px;
            }
            QComboBox {
                min-height: 18px;
                background: #ffffff;
                border: 1px solid #9a9a9a;
            }
            """
        )

    def modo(self) -> str:
        texto = str(self.cmb_modo.currentText() or "").strip()
        return texto if texto in MODOS_MOUSE else "Incremental"


class Ferramenta(FerramentaBase):
    id_ferramenta = "mouse"
    nome = "Mouse"
    descricao_painel = "Graduação manual por arraste no canvas."

    _dialog_por_canvas: dict[int, GraduarMouseDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._hover_ponto_idx: int | None = None
        self._ponto_idx: int | None = None
        self._arrastando = False
        self._origem_arrasto = QPointF()
        self._ultimo_delta = QPointF()
        self._proporcional_etapa: str | None = None
        self._delta_menor = QPointF()
        self._delta_maior = QPointF()

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._molde_idx = self._molde_selecionado(canvas)
        self._hover_ponto_idx = None
        self._ponto_idx = None
        self._arrastando = False
        self._ultimo_delta = QPointF()
        self._proporcional_etapa = None
        self._delta_menor = QPointF()
        self._delta_maior = QPointF()
        if self._molde_idx is not None and hasattr(canvas, "_selecionados"):
            canvas._selecionados = {self._molde_idx}
        dialog = self._obter_dialog(canvas)
        self._posicionar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(
            canvas,
            "Graduar via mouse: clique no molde e arraste um ponto para graduar.",
        )
        if hasattr(canvas, "update"):
            canvas.update()

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._arrastando = False
        self._proporcional_etapa = None
        self._hover_ponto_idx = None
        if canvas is not None and hasattr(canvas, "update"):
            canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = self._pos_evento(canvas, event)
        if self._processar_clique_proporcional(canvas, pos):
            event.accept()
            return True
        alvo = self._molde_e_ponto_em_posicao(canvas, pos)
        molde_idx = alvo[0] if alvo is not None else self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            self._status(canvas, "Graduar via mouse: clique sobre um molde.")
            event.accept()
            return True
        self._selecionar_molde(canvas, int(molde_idx))
        if alvo is None:
            self._status(canvas, "Graduar via mouse: molde selecionado; clique e arraste um ponto.")
            event.accept()
            return True
        self._ponto_idx = int(alvo[1])
        self._hover_ponto_idx = int(alvo[1])
        self._origem_arrasto = QPointF(pos)
        self._ultimo_delta = QPointF(0.0, 0.0)
        if self._modo_atual(canvas) == "Proporcional":
            self._proporcional_etapa = "menor"
            self._delta_menor = QPointF()
            self._delta_maior = QPointF()
            self._status(canvas, "Proporcional: estique o menor tamanho e clique para deixar.")
            if hasattr(canvas, "update"):
                canvas.update()
            event.accept()
            return True
        self._arrastando = True
        self._status(canvas, "Graduar via mouse: arraste para definir a graduação.")
        if hasattr(canvas, "update"):
            canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._pos_evento(canvas, event)
        if self._proporcional_etapa is not None and self._molde_idx is not None and self._ponto_idx is not None:
            delta = self._delta_angular(self._origem_arrasto, pos)
            if self._proporcional_etapa == "menor":
                self._delta_menor = delta
            elif self._proporcional_etapa == "maior":
                self._delta_maior = delta
            self._aplicar_delta(canvas, registrar_historico=False)
            if hasattr(canvas, "update"):
                canvas.update()
            return True
        if self._arrastando and self._molde_idx is not None and self._ponto_idx is not None:
            self._ultimo_delta = QPointF(pos.x() - self._origem_arrasto.x(), pos.y() - self._origem_arrasto.y())
            self._aplicar_delta(canvas, registrar_historico=False)
            if hasattr(canvas, "update"):
                canvas.update()
            return True

        molde = self._molde_atual(canvas)
        hover = self._ponto_hover(molde, pos, canvas) if molde is not None else None
        if hover == self._hover_ponto_idx:
            return False
        self._hover_ponto_idx = hover
        if hasattr(canvas, "update"):
            canvas.update()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if self._proporcional_etapa is not None:
            return False
        if not self._arrastando:
            return False
        self._ultimo_delta = QPointF(self._pos_evento(canvas, event) - self._origem_arrasto)
        self._aplicar_delta(canvas, registrar_historico=True)
        self._arrastando = False
        self._status(canvas, "Graduação via mouse aplicada.")
        if hasattr(canvas, "update"):
            canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._molde_idx is None or not (0 <= int(self._molde_idx) < len(canvas.cena.elementos)):
            return
        molde = canvas.cena.elementos[int(self._molde_idx)]
        pontos = self._pontos_contorno(molde)
        if not pontos:
            return
        hover_idx = self._hover_ponto_idx if self._hover_ponto_idx is not None and 0 <= int(self._hover_ponto_idx) < len(pontos) else None
        ponto_idx = self._ponto_idx if self._ponto_idx is not None and 0 <= int(self._ponto_idx) < len(pontos) else None

        painter.save()
        fonte = QFont("Arial", 8)
        fonte.setBold(True)
        painter.setFont(fonte)
        for idx, ponto in enumerate(pontos):
            if idx in {hover_idx, ponto_idx}:
                continue
            tela = canvas._cena_para_tela(ponto)
            self._desenhar_marcador(canvas, painter, tela, "#00a8b8", raio=5, losango=True)
        for idx, cor in ((ponto_idx, "#ff2020"), (hover_idx, "#00d6ff")):
            if idx is None:
                continue
            tela = canvas._cena_para_tela(pontos[int(idx)])
            painter.setPen(QPen(QColor(cor), 2.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(tela, 11, 11)
            self._desenhar_marcador(canvas, painter, tela, cor, raio=5, losango=True)
            painter.setPen(QColor("#d7d000"))
            painter.drawText(int(tela.x() + 8), int(tela.y() - 8), str(int(idx) + 1))
        if self._arrastando and ponto_idx is not None:
            origem = canvas._cena_para_tela(pontos[int(ponto_idx)])
            destino = canvas._cena_para_tela(QPointF(pontos[int(ponto_idx)].x() + self._ultimo_delta.x(), pontos[int(ponto_idx)].y() + self._ultimo_delta.y()))
            painter.setPen(QPen(QColor("#ff2020"), 1.4, Qt.DashLine))
            painter.drawLine(origem, destino)
        if self._proporcional_etapa is not None and ponto_idx is not None:
            origem_cena = pontos[int(ponto_idx)]
            origem = canvas._cena_para_tela(origem_cena)
            for delta, cor in ((self._delta_menor, "#ff00ff"), (self._delta_maior, "#00ff00")):
                if hypot(delta.x(), delta.y()) <= 1e-7:
                    continue
                destino = canvas._cena_para_tela(QPointF(origem_cena.x() + delta.x(), origem_cena.y() + delta.y()))
                painter.setPen(QPen(QColor(cor), 1.6, Qt.DashLine))
                painter.drawLine(origem, destino)
        painter.restore()

    def _processar_clique_proporcional(self, canvas, pos: QPointF) -> bool:
        if self._modo_atual(canvas) != "Proporcional":
            return False
        if self._proporcional_etapa is None:
            return False
        if self._molde_idx is None or self._ponto_idx is None:
            self._proporcional_etapa = None
            return False
        delta = self._delta_angular(self._origem_arrasto, pos)
        if self._proporcional_etapa == "menor":
            self._delta_menor = delta
            self._proporcional_etapa = "maior"
            self._aplicar_delta(canvas, registrar_historico=False)
            self._status(canvas, "Proporcional: estique o maior tamanho e clique para deixar.")
            if hasattr(canvas, "update"):
                canvas.update()
            return True
        if self._proporcional_etapa == "maior":
            self._delta_maior = delta
            self._proporcional_etapa = "confirmar"
            self._aplicar_delta(canvas, registrar_historico=False)
            self._status(canvas, "Proporcional: clique esquerdo para gravar a graduação.")
            if hasattr(canvas, "update"):
                canvas.update()
            return True
        if self._proporcional_etapa == "confirmar":
            self._aplicar_delta(canvas, registrar_historico=True)
            self._proporcional_etapa = None
            self._status(canvas, "Graduação proporcional aplicada.")
            if hasattr(canvas, "update"):
                canvas.update()
            return True
        return False

    def _aplicar_delta(self, canvas, *, registrar_historico: bool) -> bool:
        molde = self._molde_atual(canvas)
        if molde is None or self._ponto_idx is None:
            return False
        self._garantir_grade(canvas, molde)
        tamanhos = self._tamanhos_molde(molde)
        pontos = self._pontos_contorno(molde)
        if not tamanhos or not (0 <= int(self._ponto_idx) < len(pontos)):
            return False
        modo = self._obter_dialog(canvas).modo()
        if modo == "Proporcional":
            valores = self._valores_proporcionais_duplos(tamanhos, self._delta_menor, self._delta_maior)
        else:
            valores = self._valores_por_modo(tamanhos, float(self._ultimo_delta.x()), float(self._ultimo_delta.y()), modo)
        tabela = molde.setdefault("graduacao_tabela", {})
        tabela["modo"] = "dx_dy"
        pontos_cfg = tabela.setdefault("pontos", {})
        chave = str(int(self._ponto_idx))
        pontos_cfg[chave] = {
            "indice": int(self._ponto_idx),
            "numero": int(self._ponto_idx) + 1,
            "ponto": (float(pontos[int(self._ponto_idx)].x()), float(pontos[int(self._ponto_idx)].y())),
            "valores": deepcopy(valores),
        }
        molde["graduacao_pontos"] = deepcopy(pontos_cfg)
        molde["graduacao_tamanhos_ativos"] = [
            str(linha.get("tamanho") or linha.get("nome") or "").strip()
            for linha in tamanhos
            if str(linha.get("tamanho") or linha.get("nome") or "").strip()
        ]
        molde["mostrar_graduacao"] = True
        self._limpar_cache_graduacao(molde)
        if registrar_historico and hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        elif registrar_historico and hasattr(canvas, "elementos_alterados"):
            canvas.elementos_alterados.emit()
        return True

    def _modo_atual(self, canvas) -> str:
        return self._obter_dialog(canvas).modo()

    @staticmethod
    def _valores_por_modo(tamanhos: list[dict], dx: float, dy: float, modo: str) -> dict:
        base_idx = next((idx for idx, linha in enumerate(tamanhos) if linha.get("base")), len(tamanhos) // 2)
        max_abaixo = max(1, base_idx)
        max_acima = max(1, len(tamanhos) - base_idx - 1)
        valores = {}
        for idx, linha in enumerate(tamanhos):
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if not nome:
                continue
            if idx == base_idx:
                fator = 0.0
            elif modo == "Absoluto":
                fator = 1.0
            elif modo == "Proporcional":
                fator = -((base_idx - idx) / max_abaixo) if idx < base_idx else (idx - base_idx) / max_acima
            else:
                fator = float(idx - base_idx)
            valores[nome] = {"dx": float(dx) * fator, "dy": float(dy) * fator}
        return valores

    @staticmethod
    def _valores_proporcionais_duplos(tamanhos: list[dict], delta_menor: QPointF, delta_maior: QPointF) -> dict:
        base_idx = next((idx for idx, linha in enumerate(tamanhos) if linha.get("base")), len(tamanhos) // 2)
        max_abaixo = max(1, base_idx)
        max_acima = max(1, len(tamanhos) - base_idx - 1)
        valores = {}
        for idx, linha in enumerate(tamanhos):
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if not nome:
                continue
            if idx < base_idx:
                fator = (base_idx - idx) / max_abaixo
                valores[nome] = {"dx": float(delta_menor.x()) * fator, "dy": float(delta_menor.y()) * fator}
            elif idx > base_idx:
                fator = (idx - base_idx) / max_acima
                valores[nome] = {"dx": float(delta_maior.x()) * fator, "dy": float(delta_maior.y()) * fator}
            else:
                valores[nome] = {"dx": 0.0, "dy": 0.0}
        return valores

    @staticmethod
    def _delta_angular(origem: QPointF, destino: QPointF) -> QPointF:
        dx = float(destino.x() - origem.x())
        dy = float(destino.y() - origem.y())
        distancia = hypot(dx, dy)
        if distancia <= 1e-9:
            return QPointF(0.0, 0.0)
        angulo = degrees(atan2(dy, dx))
        padroes = [0, 30, 45, 60, 90, 120, 135, 150, 180, -150, -135, -120, -90, -60, -45, -30]
        alvo = min(padroes, key=lambda valor: abs(((angulo - valor + 180) % 360) - 180))
        rad = radians(alvo)
        return QPointF(
            Ferramenta._zero_se_proximo(cos(rad) * distancia),
            Ferramenta._zero_se_proximo(sin(rad) * distancia),
        )

    @staticmethod
    def _zero_se_proximo(valor: float) -> float:
        valor = float(valor)
        return 0.0 if abs(valor) <= 1e-9 else valor

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

    def _selecionar_molde(self, canvas, molde_idx: int) -> None:
        self._molde_idx = int(molde_idx)
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(molde_idx)}
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

    def _molde_e_ponto_em_posicao(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        candidatos = []
        for molde_idx, molde in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if not self._eh_molde(molde):
                continue
            ponto_idx = self._ponto_hover(molde, pos, canvas)
            if ponto_idx is not None:
                candidatos.append((molde_idx, int(ponto_idx)))
        if not candidatos:
            return None
        if self._molde_idx is not None:
            for molde_idx, ponto_idx in candidatos:
                if int(molde_idx) == int(self._molde_idx):
                    return molde_idx, ponto_idx
        return candidatos[0]

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

    def _ponto_hover(self, molde: dict | None, pos: QPointF, canvas) -> int | None:
        pontos = self._pontos_contorno(molde)
        if not pontos:
            return None
        tolerancia = max(0.35, 10.0 / max(float(getattr(canvas, "zoom", 1.0) or 1.0), 1e-6))
        melhor_idx = None
        melhor_dist = tolerancia
        for idx, ponto in enumerate(pontos):
            dist = hypot(float(ponto.x() - pos.x()), float(ponto.y() - pos.y()))
            if dist <= melhor_dist:
                melhor_dist = dist
                melhor_idx = idx
        return melhor_idx

    @staticmethod
    def _pontos_contorno(molde: dict | None) -> list[QPointF]:
        if not isinstance(molde, dict) or not molde.get("molde"):
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

    @classmethod
    def _ponto_dentro_bbox(cls, molde: dict, pos: QPointF) -> bool:
        pontos = cls._pontos_contorno(molde)
        if not pontos:
            return False
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        return min(xs) <= pos.x() <= max(xs) and min(ys) <= pos.y() <= max(ys)

    @staticmethod
    def _eh_molde(elemento) -> bool:
        return isinstance(elemento, dict) and bool(elemento.get("molde"))

    @staticmethod
    def _pos_evento(canvas, event) -> QPointF:
        return canvas._ponto_com_snap(event.position()) if hasattr(canvas, "_ponto_com_snap") else QPointF(event.position())

    def _obter_dialog(self, canvas) -> GraduarMouseDialog:
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
            dialog = GraduarMouseDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        return dialog

    @staticmethod
    def _posicionar_dialog(canvas, dialog: QDialog) -> None:
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            dialog.move(canvas.mapToGlobal(pos_local))
        elif hasattr(canvas, "mapToGlobal"):
            dialog.move(canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92)))

    def _fechar(self, canvas) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._arrastando = False
        self._proporcional_etapa = None
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        if hasattr(canvas, "update"):
            canvas.update()

    @staticmethod
    def _limpar_cache_graduacao(molde: dict) -> None:
        for chave in (
            "_runtime_graduacao_contornos_cache",
            "_runtime_graduacao_caminhos_cache",
            "_runtime_base_graduacao_lista_cache",
        ):
            molde.pop(chave, None)

    def _desenhar_marcador(self, canvas, painter, tela: QPointF, cor: str, *, raio: int = 5, losango: bool = False) -> None:
        desenhar = getattr(canvas, "_desenhar_marcador_ponto_tela", None)
        if callable(desenhar):
            forma = "Losango" if losango else "Circulo"
            desenhar(painter, tela, cor, forma, raio)
            return
        cor_qt = QColor(cor)
        painter.setPen(QPen(cor_qt, 1.3))
        painter.setBrush(Qt.NoBrush)
        if losango:
            path = QPainterPath(QPointF(tela.x(), tela.y() - raio))
            path.lineTo(QPointF(tela.x() + raio, tela.y()))
            path.lineTo(QPointF(tela.x(), tela.y() + raio))
            path.lineTo(QPointF(tela.x() - raio, tela.y()))
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawEllipse(tela, raio, raio)

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
