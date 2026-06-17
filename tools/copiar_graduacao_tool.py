from __future__ import annotations

from copy import deepcopy
from math import hypot

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QGridLayout, QLabel, QVBoxLayout

from tools.tool_base import FerramentaBase


MODOS_COPIAR_GRADUACAO = [
    "1 ponto graduado",
    "Vários pontos de controle",
    "Todos os pontos de controle",
]


class CopiarGraduacaoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Copiar graduação")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedSize(215, 114)
        self.setObjectName("CopiarGraduacaoDialog")

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(4)

        grade = QGridLayout()
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setHorizontalSpacing(6)
        grade.setVerticalSpacing(4)

        grade.addWidget(QLabel("Copiar:"), 0, 0)
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(MODOS_COPIAR_GRADUACAO)
        grade.addWidget(self.cmb_modo, 0, 1, 1, 3)

        self.chk_apenas_dx = QCheckBox("Apenas DX")
        self.chk_apenas_dy = QCheckBox("Apenas DY")
        self.chk_inverte_dx = QCheckBox("Inverte Dx")
        self.chk_inverte_dy = QCheckBox("Inverte Dy")
        grade.addWidget(self.chk_apenas_dx, 1, 0, 1, 2)
        grade.addWidget(self.chk_apenas_dy, 1, 2, 1, 2)
        grade.addWidget(self.chk_inverte_dx, 2, 0, 1, 2)
        grade.addWidget(self.chk_inverte_dy, 2, 2, 1, 2)

        raiz.addLayout(grade)
        self.setStyleSheet(
            """
            QDialog#CopiarGraduacaoDialog {
                background: #f4f4f4;
                color: #111111;
            }
            QLabel, QCheckBox, QComboBox {
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

    def opcoes(self) -> dict[str, object]:
        return {
            "modo": self.cmb_modo.currentText(),
            "apenas_dx": bool(self.chk_apenas_dx.isChecked()),
            "apenas_dy": bool(self.chk_apenas_dy.isChecked()),
            "inverte_dx": bool(self.chk_inverte_dx.isChecked()),
            "inverte_dy": bool(self.chk_inverte_dy.isChecked()),
        }


class Ferramenta(FerramentaBase):
    id_ferramenta = "copiar_graduacao"
    nome = "Copiar graduação"
    descricao_painel = "Copia a graduação de um ponto e cola em outro ponto de molde."

    _dialog_por_canvas: dict[int, CopiarGraduacaoDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._hover_ponto_idx: int | None = None
        self._ponto_idx: int | None = None
        self._origem: tuple[int, int] | None = None
        self._graduacao_copiada: dict | None = None
        self._graduacoes_copiadas_por_ponto: dict[int, dict] | None = None
        self._indices_copiados: list[int] = []
        self._grade_copiada: dict | None = None
        self._modo_copiado: str = MODOS_COPIAR_GRADUACAO[0]
        self._faixa_inicio: tuple[int, int] | None = None
        self._faixa_preview_indices: list[int] = []
        self._aguardando_soltar_origem = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._molde_idx = self._molde_selecionado(canvas)
        self._hover_ponto_idx = None
        self._ponto_idx = None
        self._origem = None
        self._graduacao_copiada = None
        self._graduacoes_copiadas_por_ponto = None
        self._indices_copiados = []
        self._grade_copiada = None
        self._modo_copiado = MODOS_COPIAR_GRADUACAO[0]
        self._faixa_inicio = None
        self._faixa_preview_indices = []
        self._aguardando_soltar_origem = False
        if self._molde_idx is not None and hasattr(canvas, "_selecionados"):
            canvas._selecionados = {self._molde_idx}
        dialog = self._obter_dialog(canvas)
        self._posicionar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(
            canvas,
            "Copiar graduação: selecione o ponto graduado de origem."
            if self._molde_idx is not None
            else "Copiar graduação: clique no molde de origem.",
        )
        if hasattr(canvas, "update"):
            canvas.update()

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._hover_ponto_idx = None
        if canvas is not None and hasattr(canvas, "update"):
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position()) if hasattr(canvas, "_ponto_com_snap") else QPointF(event.position())
        alvo = self._molde_e_ponto_em_posicao(canvas, pos)
        hover = None
        if alvo is not None and (self._molde_idx is None or int(alvo[0]) == int(self._molde_idx)):
            hover = int(alvo[1])
        if (
            hover is not None
            and self._faixa_inicio is not None
            and not self._tem_graduacao_copiada()
            and int(self._faixa_inicio[0]) == int(self._molde_idx)
            and self._modo_opcoes(self._dialog_atual_opcoes(canvas)) == MODOS_COPIAR_GRADUACAO[1]
        ):
            molde = canvas.cena.elementos[int(self._molde_idx)]
            total = len(self._pontos_contorno(molde))
            self._adicionar_indice_varios_pontos(int(hover), total)
        if hover == self._hover_ponto_idx:
            return False
        self._hover_ponto_idx = hover
        if hasattr(canvas, "update"):
            canvas.update()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._clique_direito(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position()) if hasattr(canvas, "_ponto_com_snap") else QPointF(event.position())
        alvo = self._molde_e_ponto_em_posicao(canvas, pos)
        molde_idx = alvo[0] if alvo is not None else self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            self._status(canvas, "Copiar graduação: clique sobre um molde.")
            event.accept()
            return True

        if self._molde_idx is None or int(molde_idx) != int(self._molde_idx):
            self._selecionar_molde(canvas, int(molde_idx))
            self._ponto_idx = None
            self._status(
                canvas,
                "Copiar graduação: escolha o ponto de destino."
                if self._tem_graduacao_copiada()
                else "Copiar graduação: escolha o ponto graduado de origem.",
            )
            event.accept()
            return True

        if alvo is None:
            self._selecionar_molde(canvas, int(molde_idx))
            event.accept()
            return True

        ponto_idx = int(alvo[1])
        if not self._tem_graduacao_copiada():
            if self._modo_opcoes(self._dialog_atual_opcoes(canvas)) == MODOS_COPIAR_GRADUACAO[1]:
                self._processar_clique_varios_pontos(canvas, int(molde_idx), ponto_idx)
                event.accept()
                return True
            self._copiar_origem(canvas, int(molde_idx), ponto_idx)
        else:
            self._colar_destino(canvas, int(molde_idx), ponto_idx)
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        moldes = []
        if self._origem is not None:
            moldes.append((int(self._origem[0]), int(self._origem[1]), "origem"))
        if self._molde_idx is not None:
            moldes.append((int(self._molde_idx), self._ponto_idx, "atual"))

        desenhados = set()
        for molde_idx, ponto_idx, papel in moldes:
            if molde_idx in desenhados:
                continue
            desenhados.add(molde_idx)
            if not (0 <= molde_idx < len(canvas.cena.elementos)):
                continue
            molde = canvas.cena.elementos[molde_idx]
            pontos = self._pontos_contorno(molde)
            if not pontos:
                continue
            self._desenhar_overlay_molde(canvas, painter, molde, pontos, molde_idx, ponto_idx, papel)

    def _desenhar_overlay_molde(self, canvas, painter, molde, pontos, molde_idx: int, ponto_idx: int | None, papel: str):
        hover_idx = self._hover_ponto_idx if molde_idx == self._molde_idx else None
        painter.save()
        fonte = QFont("Arial", 8)
        fonte.setBold(True)
        painter.setFont(fonte)
        for idx, ponto in enumerate(pontos):
            tela = canvas._cena_para_tela(ponto)
            self._desenhar_ponto(canvas, painter, tela, raio=4, cor="#ffdd00")
            painter.setPen(QColor("#d7d000"))
            painter.drawText(int(tela.x() + 8), int(tela.y() - 8), str(idx + 1))

        marcados = set()
        if isinstance(ponto_idx, int):
            marcados.add(ponto_idx)
        if self._origem is not None and int(self._origem[0]) == molde_idx:
            marcados.add(int(self._origem[1]))
        if self._faixa_inicio is not None and int(self._faixa_inicio[0]) == molde_idx:
            marcados.update(int(idx) for idx in self._faixa_preview_indices)
        if self._origem is not None and int(self._origem[0]) == molde_idx:
            marcados.update(int(idx) for idx in self._indices_copiados)

        for idx in sorted(marcados):
            if not (0 <= idx < len(pontos)):
                continue
            tela = canvas._cena_para_tela(pontos[idx])
            cor = QColor("#ff2020" if papel == "origem" or (self._origem and self._origem == (molde_idx, idx)) else "#00a6ff")
            painter.setPen(QPen(cor, 2.4))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(tela, 13, 13)
            self._desenhar_ponto(canvas, painter, tela, raio=5, cor=cor.name())

        if hover_idx is not None and 0 <= int(hover_idx) < len(pontos):
            tela = canvas._cena_para_tela(pontos[int(hover_idx)])
            painter.setPen(QPen(QColor("#ff2020"), 2.4))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(tela.x() - 10), int(tela.y() - 10), 20, 20)
        painter.restore()

    def _desenhar_ponto(self, canvas, painter, tela: QPointF, *, raio: int, cor: str):
        desenhar = getattr(canvas, "_desenhar_marcador_ponto_tela", None)
        if callable(desenhar):
            desenhar(painter, tela, cor, "Losango", raio)
            return
        qcor = QColor(cor)
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.setBrush(qcor)
        path = QPainterPath(QPointF(tela.x(), tela.y() - raio))
        path.lineTo(QPointF(tela.x() + raio, tela.y()))
        path.lineTo(QPointF(tela.x(), tela.y() + raio))
        path.lineTo(QPointF(tela.x() - raio, tela.y()))
        path.closeSubpath()
        painter.drawPath(path)

    def _processar_clique_varios_pontos(self, canvas, molde_idx: int, ponto_idx: int) -> None:
        molde = canvas.cena.elementos[molde_idx]
        total = len(self._pontos_contorno(molde))
        if total <= 0:
            return
        if self._faixa_inicio is None or int(self._faixa_inicio[0]) != int(molde_idx):
            self._faixa_inicio = (int(molde_idx), int(ponto_idx))
            self._faixa_preview_indices = [int(ponto_idx)]
            self._ponto_idx = int(ponto_idx)
            self._selecionar_molde(canvas, molde_idx)
            self._status(canvas, "Copiar graduação: selecione os pontos um a um no sentido horário; clique em um selecionado para copiar.")
            return
        if self._adicionar_indice_varios_pontos(int(ponto_idx), total):
            self._status(canvas, "Copiar graduação: ponto adicionado. Continue no sentido horário ou clique em um selecionado para copiar.")
            return
        if int(ponto_idx) not in self._faixa_preview_indices:
            self._status(canvas, "Copiar graduação: siga para o próximo ponto no sentido horário.")
            return
        self._copiar_origem(
            canvas,
            molde_idx,
            int(self._faixa_inicio[1]),
            indices_selecionados=list(self._faixa_preview_indices),
        )

    def _adicionar_indice_varios_pontos(self, ponto_idx: int, total: int) -> bool:
        total = int(total)
        if total <= 0 or not self._faixa_preview_indices:
            return False
        ponto_idx = int(ponto_idx) % total
        if ponto_idx in self._faixa_preview_indices:
            return False
        proximo = (int(self._faixa_preview_indices[-1]) - 1) % total
        if ponto_idx != proximo or len(self._faixa_preview_indices) >= total:
            return False
        self._faixa_preview_indices.append(ponto_idx)
        self._ponto_idx = ponto_idx
        return True

    def _copiar_origem(
        self,
        canvas,
        molde_idx: int,
        ponto_idx: int,
        *,
        indices_selecionados: list[int] | None = None,
    ) -> None:
        molde = canvas.cena.elementos[molde_idx]
        modo = self._modo_opcoes(self._dialog_atual_opcoes(canvas))
        pontos = self._pontos_contorno(molde)
        if modo == MODOS_COPIAR_GRADUACAO[2]:
            indices = self._todos_indices_horario(ponto_idx, len(pontos))
            valores_por_ponto = self._valores_pontos_indices(molde, indices, incluir_zeros=True)
        elif modo == MODOS_COPIAR_GRADUACAO[1]:
            indices = list(indices_selecionados or [int(ponto_idx)])
            valores_por_ponto = self._valores_pontos_indices(molde, indices, incluir_zeros=True)
        else:
            indices = [int(ponto_idx)]
            valores = self._valores_ponto(molde, ponto_idx)
            valores_por_ponto = {int(ponto_idx): valores} if valores else {}
        if not valores_por_ponto:
            self._status(canvas, "Copiar graduação: este ponto não possui graduação.")
            return
        self._modo_copiado = modo
        self._indices_copiados = [int(idx) for idx in indices if int(idx) in valores_por_ponto]
        self._graduacoes_copiadas_por_ponto = {
            int(idx): deepcopy(valores)
            for idx, valores in valores_por_ponto.items()
            if isinstance(valores, dict) and valores
        }
        self._graduacao_copiada = deepcopy(
            self._graduacoes_copiadas_por_ponto.get(int(ponto_idx))
            or next(iter(self._graduacoes_copiadas_por_ponto.values()))
        )
        self._grade_copiada = self._snapshot_grade_molde(molde)
        self._origem = (int(molde_idx), int(ponto_idx))
        self._ponto_idx = int(ponto_idx)
        self._faixa_inicio = None
        self._faixa_preview_indices = []
        self._selecionar_molde(canvas, molde_idx)
        self._status(canvas, "Copiar graduação: clique no molde de destino.")

    def _colar_destino(self, canvas, molde_idx: int, ponto_idx: int) -> None:
        if not self._tem_graduacao_copiada():
            return
        self._selecionar_molde(canvas, molde_idx)
        self._ponto_idx = int(ponto_idx)
        molde = canvas.cena.elementos[molde_idx]
        self._garantir_grade_destino(molde)
        pontos = self._pontos_contorno(molde)
        if not (0 <= ponto_idx < len(pontos)):
            return
        tabela = molde.setdefault("graduacao_tabela", {})
        tabela["modo"] = "dx_dy"
        pontos_cfg = tabela.setdefault("pontos", {})
        opcoes = self._dialog_atual_opcoes(canvas)
        total_colados = 0
        if self._modo_copiado == MODOS_COPIAR_GRADUACAO[0]:
            valores = self._valores_filtrados_para_colar(molde, ponto_idx, opcoes=opcoes)
            self._definir_valores_ponto(pontos_cfg, pontos, int(ponto_idx), valores)
            total_colados = 1
        else:
            for deslocamento, idx_origem in enumerate(self._indices_copiados):
                if deslocamento >= len(pontos):
                    continue
                idx_destino = (int(ponto_idx) + int(deslocamento)) % len(pontos)
                valores_origem = (self._graduacoes_copiadas_por_ponto or {}).get(int(idx_origem))
                if not isinstance(valores_origem, dict):
                    continue
                valores = self._valores_filtrados_para_colar(
                    molde,
                    idx_destino,
                    valores_copiados=valores_origem,
                    opcoes=opcoes,
                )
                self._definir_valores_ponto(pontos_cfg, pontos, idx_destino, valores)
                total_colados += 1
        if total_colados <= 0:
            self._status(canvas, "Copiar graduação: nenhum ponto compatível para colar.")
            return
        molde["graduacao_pontos"] = deepcopy(pontos_cfg)
        molde["mostrar_graduacao"] = True
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        elif hasattr(canvas, "elementos_alterados"):
            canvas.elementos_alterados.emit()
        self._status(canvas, "Copiar graduação: graduação colada. Escolha outro ponto ou clique direito para finalizar.")
        if hasattr(canvas, "update"):
            canvas.update()

    @staticmethod
    def _definir_valores_ponto(pontos_cfg: dict, pontos: list[QPointF], ponto_idx: int, valores: dict) -> None:
        pontos_cfg[str(ponto_idx)] = {
            "indice": int(ponto_idx),
            "numero": int(ponto_idx) + 1,
            "ponto": (float(pontos[ponto_idx].x()), float(pontos[ponto_idx].y())),
            "valores": valores,
        }

    def _valores_filtrados_para_colar(
        self,
        molde: dict,
        ponto_idx: int,
        *,
        valores_copiados: dict | None = None,
        opcoes: dict[str, object] | None = None,
    ) -> dict:
        valores_destino = self._valores_ponto(molde, ponto_idx)
        opcoes = opcoes or self._dialog_atual_opcoes()
        apenas_dx = opcoes.get("apenas_dx", False) and not opcoes.get("apenas_dy", False)
        apenas_dy = opcoes.get("apenas_dy", False) and not opcoes.get("apenas_dx", False)
        saida = deepcopy(valores_destino) if isinstance(valores_destino, dict) else {}
        for tamanho, valor in (valores_copiados or self._graduacao_copiada or {}).items():
            if not isinstance(valor, dict):
                continue
            atual = dict(saida.get(tamanho) or {})
            dx = self._float(valor.get("dx", 0.0))
            dy = self._float(valor.get("dy", 0.0))
            if opcoes.get("inverte_dx", False):
                dx = -dx
            if opcoes.get("inverte_dy", False):
                dy = -dy
            if apenas_dx:
                atual["dx"] = dx
                atual.setdefault("dy", self._float(atual.get("dy", 0.0)))
            elif apenas_dy:
                atual.setdefault("dx", self._float(atual.get("dx", 0.0)))
                atual["dy"] = dy
            else:
                atual["dx"] = dx
                atual["dy"] = dy
            saida[tamanho] = atual
        return saida

    def _dialog_atual_opcoes(self, canvas=None) -> dict[str, object]:
        if canvas is not None:
            dialog = self._dialog_por_canvas.get(id(canvas))
            if isinstance(dialog, CopiarGraduacaoDialog):
                try:
                    return dialog.opcoes()
                except RuntimeError:
                    self._dialog_por_canvas.pop(id(canvas), None)
        removidos = []
        for chave, dialog in self._dialog_por_canvas.items():
            if isinstance(dialog, CopiarGraduacaoDialog):
                try:
                    return dialog.opcoes()
                except RuntimeError:
                    removidos.append(chave)
        for chave in removidos:
            self._dialog_por_canvas.pop(chave, None)
        return {}

    @staticmethod
    def _modo_opcoes(opcoes: dict[str, object]) -> str:
        modo = str(opcoes.get("modo") or "").strip()
        return modo if modo in MODOS_COPIAR_GRADUACAO else MODOS_COPIAR_GRADUACAO[0]

    def _tem_graduacao_copiada(self) -> bool:
        return self._graduacao_copiada is not None or bool(self._graduacoes_copiadas_por_ponto)

    @staticmethod
    def _snapshot_grade_molde(molde: dict) -> dict:
        return {
            "graduacao_grade_nome": deepcopy(molde.get("graduacao_grade_nome")),
            "graduacao_tamanhos": deepcopy(molde.get("graduacao_tamanhos")),
            "graduacao_tamanhos_ativos": deepcopy(molde.get("graduacao_tamanhos_ativos")),
        }

    def _garantir_grade_destino(self, molde: dict) -> None:
        if not isinstance(molde, dict) or not isinstance(self._grade_copiada, dict):
            return
        if not isinstance(molde.get("graduacao_tamanhos"), list) and isinstance(self._grade_copiada.get("graduacao_tamanhos"), list):
            molde["graduacao_tamanhos"] = deepcopy(self._grade_copiada["graduacao_tamanhos"])
        if not isinstance(molde.get("graduacao_tamanhos_ativos"), list) and isinstance(self._grade_copiada.get("graduacao_tamanhos_ativos"), list):
            molde["graduacao_tamanhos_ativos"] = deepcopy(self._grade_copiada["graduacao_tamanhos_ativos"])
        if not str(molde.get("graduacao_grade_nome") or "").strip() and self._grade_copiada.get("graduacao_grade_nome"):
            molde["graduacao_grade_nome"] = deepcopy(self._grade_copiada["graduacao_grade_nome"])

    def _clique_direito(self, canvas) -> None:
        if self._tem_graduacao_copiada() and self._origem is not None and not self._aguardando_soltar_origem:
            self._aguardando_soltar_origem = True
            self._molde_idx = int(self._origem[0])
            self._ponto_idx = int(self._origem[1])
            if hasattr(canvas, "_selecionados"):
                canvas._selecionados = {self._molde_idx}
            self._status(canvas, "Copiar graduação: destino finalizado. Clique direito novamente para soltar a origem.")
            if hasattr(canvas, "update"):
                canvas.update()
            return
        self._fechar(canvas)

    def _fechar(self, canvas) -> None:
        self._graduacao_copiada = None
        self._graduacoes_copiadas_por_ponto = None
        self._indices_copiados = []
        self._grade_copiada = None
        self._origem = None
        self._ponto_idx = None
        self._hover_ponto_idx = None
        self._faixa_inicio = None
        self._faixa_preview_indices = []
        self._aguardando_soltar_origem = False
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        if hasattr(canvas, "update"):
            canvas.update()

    def _selecionar_molde(self, canvas, molde_idx: int) -> None:
        self._molde_idx = int(molde_idx)
        self._hover_ponto_idx = None
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(molde_idx)}
        if hasattr(canvas, "update"):
            canvas.update()

    def _molde_selecionado(self, canvas) -> int | None:
        for idx in sorted(getattr(canvas, "_selecionados", set()) or []):
            if 0 <= int(idx) < len(canvas.cena.elementos) and self._eh_molde(canvas.cena.elementos[int(idx)]):
                return int(idx)
        return None

    def _molde_e_ponto_em_posicao(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        melhor: tuple[float, int, int] | None = None
        tolerancia = max(0.18, 24.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        for idx, molde in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if not self._eh_molde(molde):
                continue
            pontos = self._pontos_contorno(molde)
            if not pontos:
                continue
            dist, ponto_idx = min((self._dist(ponto, pos), p_idx) for p_idx, ponto in enumerate(pontos))
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, int(idx), int(ponto_idx))
        return (melhor[1], melhor[2]) if melhor is not None else None

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
    def _pontos_contorno(molde: dict | None) -> list[QPointF]:
        if not isinstance(molde, dict):
            return []
        origem = molde.get("controle_cantos") or molde.get("pontos") or []
        pontos: list[QPointF] = []
        for item in origem:
            try:
                pontos.append(QPointF(float(item[0]), float(item[1])))
            except Exception:
                continue
        if len(pontos) > 1 and pontos[0] == pontos[-1]:
            pontos = pontos[:-1]
        return pontos

    def _valores_ponto(self, molde: dict | None, ponto_idx: int | None) -> dict:
        if not isinstance(molde, dict) or ponto_idx is None:
            return {}
        pontos = self._pontos_contorno(molde)
        ponto = pontos[int(ponto_idx)] if 0 <= int(ponto_idx) < len(pontos) else None
        for pontos_cfg in self._fontes_pontos_graduacao(molde):
            dados = pontos_cfg.get(str(ponto_idx)) if isinstance(pontos_cfg, dict) else None
            if not isinstance(dados, dict) and ponto is not None:
                dados = self._dados_por_ponto(pontos_cfg, ponto)
            valores = dados.get("valores") if isinstance(dados, dict) else None
            if isinstance(valores, dict) and valores:
                return deepcopy(valores)
        return {}

    def _valores_pontos_indices(self, molde: dict | None, indices: list[int], *, incluir_zeros: bool) -> dict[int, dict]:
        zeros = self._valores_zerados_grade(molde) if incluir_zeros else {}
        saida: dict[int, dict] = {}
        total = len(self._pontos_contorno(molde))
        for idx in indices:
            idx_int = int(idx)
            if not (0 <= idx_int < total):
                continue
            valores = self._valores_ponto(molde, idx_int)
            if valores:
                saida[idx_int] = valores
            elif zeros:
                saida[idx_int] = deepcopy(zeros)
        return saida

    @staticmethod
    def _valores_zerados_grade(molde: dict | None) -> dict:
        linhas = molde.get("graduacao_tamanhos") if isinstance(molde, dict) else None
        if not isinstance(linhas, list):
            return {}
        saida = {}
        for linha in linhas:
            if not isinstance(linha, dict) or not linha.get("ativo", True):
                continue
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if nome:
                saida[nome] = {"dx": 0.0, "dy": 0.0}
        return saida

    @staticmethod
    def _indices_horario(inicio: int, fim: int, total: int) -> list[int]:
        total = int(total)
        if total <= 0:
            return []
        atual = int(inicio) % total
        fim = int(fim) % total
        indices = [atual]
        while atual != fim:
            atual = (atual - 1) % total
            indices.append(atual)
            if len(indices) > total:
                break
        return indices

    @classmethod
    def _todos_indices_horario(cls, inicio: int, total: int) -> list[int]:
        total = int(total)
        if total <= 0:
            return []
        inicio = int(inicio) % total
        return cls._indices_horario(inicio, (inicio + 1) % total, total)

    @staticmethod
    def _fontes_pontos_graduacao(molde: dict) -> list[dict]:
        fontes = []
        tabela = molde.get("graduacao_tabela")
        pontos = tabela.get("pontos") if isinstance(tabela, dict) else None
        if isinstance(pontos, dict):
            fontes.append(pontos)
        legado = molde.get("graduacao_pontos")
        if isinstance(legado, dict) and legado is not pontos:
            fontes.append(legado)
        return fontes

    def _dados_por_ponto(self, pontos_cfg: dict, ponto: QPointF) -> dict | None:
        melhor = None
        for dados in pontos_cfg.values():
            if not isinstance(dados, dict):
                continue
            bruto = dados.get("ponto")
            if not isinstance(bruto, (list, tuple)) or len(bruto) < 2:
                continue
            try:
                dist = self._dist(QPointF(float(bruto[0]), float(bruto[1])), ponto)
            except Exception:
                continue
            if dist <= 1e-5 and (melhor is None or dist < melhor[0]):
                melhor = (dist, dados)
        return melhor[1] if melhor else None

    @staticmethod
    def _eh_molde(elemento) -> bool:
        return isinstance(elemento, dict) and bool(elemento.get("molde"))

    @staticmethod
    def _ponto_dentro_bbox(molde: dict, pos: QPointF) -> bool:
        pontos = Ferramenta._pontos_contorno(molde)
        if not pontos:
            return False
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        return min(xs) <= pos.x() <= max(xs) and min(ys) <= pos.y() <= max(ys)

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _float(valor) -> float:
        try:
            return float(valor)
        except (TypeError, ValueError):
            return 0.0

    def _obter_dialog(self, canvas) -> CopiarGraduacaoDialog:
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
            dialog = CopiarGraduacaoDialog(parent)
            self._dialog_por_canvas[chave] = dialog
        return dialog

    @staticmethod
    def _posicionar_dialog(canvas, dialog: QDialog) -> None:
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            dialog.move(canvas.mapToGlobal(pos_local))
        elif hasattr(canvas, "mapToGlobal"):
            dialog.move(canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 120)))

    def _status(self, canvas, texto: str):
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
