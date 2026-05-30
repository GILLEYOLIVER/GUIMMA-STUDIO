from __future__ import annotations

from math import sqrt
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QAbstractSpinBox, QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QLabel, QVBoxLayout

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class MedidaSpinBox(QDoubleSpinBox):
    def textFromValue(self, value: float) -> str:  # noqa: N802 - assinatura Qt
        texto = f"{value:.3f}".rstrip("0").rstrip(".")
        if not texto:
            texto = "0"
        return texto.replace(".", self.locale().decimalPoint())


class ElementoParaleloDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:elemento_paralelo"
        self.setWindowTitle("Elemento paralelo")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(305)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QDoubleSpinBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            """
        )
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.sp_distancia = MedidaSpinBox()
        self.sp_distancia.setRange(0.001, 999999.0)
        self.sp_distancia.setDecimals(3)
        self.sp_distancia.setSingleStep(0.1)
        self.sp_distancia.setValue(2.0)
        self.sp_distancia.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_distancia_2 = QCheckBox("Distância paralela 2 (cm)")
        self.sp_distancia_2 = MedidaSpinBox()
        self.sp_distancia_2.setRange(0.001, 999999.0)
        self.sp_distancia_2.setDecimals(3)
        self.sp_distancia_2.setSingleStep(0.1)
        self.sp_distancia_2.setValue(1.0)
        self.sp_distancia_2.setEnabled(False)
        self.sp_distancia_2.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chk_linha_auxiliar = QCheckBox("Inserir elemento como linha auxiliar")
        form.addRow("Distância paralela (cm)", self.sp_distancia)
        form.addRow(self.chk_distancia_2, self.sp_distancia_2)
        raiz.addLayout(form)
        raiz.addWidget(self.chk_linha_auxiliar)
        self.chk_distancia_2.toggled.connect(self.sp_distancia_2.setEnabled)


class Ferramenta(FerramentaBase):
    id_ferramenta = "elemento_paralelo"
    nome = "Elemento Paralelo"
    usa_painel_auxiliar = False
    descricao_painel = "Cria linha/contorno paralelo por clique ou pela seleção."

    _dialog_por_canvas: dict[int, ElementoParaleloDialog] = {}

    def __init__(self):
        super().__init__()
        self._preview: list[QPointF] = []
        self._preview_2: list[QPointF] = []
        self._hover_info: dict | None = None
        self._fase = "selecionar"
        self._alvo_idx: int | None = None
        self._segmento_inicio: int | None = None
        self._segmento_hover: int | None = None
        self._direcao_selecao: int | None = None
        self._segmentos_selecionados: set[int] = set()
        self._segmentos_visitados: set[int] = set()
        self._selecao_contorno_completo = False
        self._realce_segmentos: list[tuple[QPointF, QPointF]] = []
        self._ultima_posicao_mouse: QPointF | None = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._limpar_estado()
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Elemento paralelo: clique no perimetro para iniciar a selecao.")

    def on_deactivate(self, canvas):
        self._limpar_estado()
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        if canvas is not None:
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        self._ultima_posicao_mouse = QPointF(pos)
        if self._fase == "posicionar":
            self._atualizar_preview(canvas, pos)
        else:
            self._atualizar_selecao_hover(canvas, pos)
        canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._fase in {"selecionar", "posicionar"} and (self._alvo_idx is not None or self._preview or self._realce_segmentos):
                self._limpar_estado()
                self._limpar_selecao_canvas(canvas)
                self._operacao_finalizada = True
                self._direito_confirma_fechamento = True
                self._status(canvas, "Operacao finalizada. Clique direito novamente fecha a ferramenta.")
                canvas.update()
            elif self._operacao_finalizada and not self._direito_confirma_fechamento:
                self._direito_confirma_fechamento = True
                self._status(canvas, "Operacao finalizada. Clique direito novamente fecha a ferramenta.")
            else:
                self._fechar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._ultima_posicao_mouse = QPointF(pos)
        if self._fase == "finalizado":
            self._limpar_estado()
            self._limpar_selecao_canvas(canvas)
        if self._fase == "selecionar" and self._alvo_idx is None:
            if not self._iniciar_selecao(canvas, pos):
                self._status(canvas, "Clique sobre uma linha do molde para selecionar o trecho.")
                return False
            event.accept()
            return True
        if self._fase == "selecionar":
            self._fase = "posicionar"
            self._atualizar_preview(canvas, pos)
            self._status(canvas, "Trecho fixado. Mova para dentro ou fora para escolher o lado; clique esquerdo confirma.")
            canvas.update()
            event.accept()
            return True
        if self._fase == "posicionar":
            self._atualizar_preview(canvas, pos)
            if not self._confirmar_paralela(canvas):
                self._status(canvas, "Nao foi possivel criar a paralela desse trecho.")
                return False
        event.accept()
        return True

    def _obter_dialog(self, canvas) -> ElementoParaleloDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = ElementoParaleloDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.sp_distancia.valueChanged.connect(lambda _v: self._redesenhar(canvas))
            dialog.sp_distancia_2.valueChanged.connect(lambda _v: self._redesenhar(canvas))
            dialog.chk_distancia_2.toggled.connect(lambda _ativo: self._redesenhar(canvas))
        return dialog

    def _restaurar_dialog(self, canvas, dialog: ElementoParaleloDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _aplicar_selecao(self, canvas) -> None:
        indices = [int(i) for i in sorted(getattr(canvas, "_selecionados", set()) or []) if 0 <= int(i) < len(canvas.cena.elementos)]
        if not indices:
            self._status(canvas, "Elemento paralelo: selecione um contorno ou clique em um segmento.")
            return
        criou = 0
        for idx in indices:
            el = canvas.cena.elementos[idx]
            pts = self._pontos_poly(el)
            if len(pts) < 2:
                continue
            paralelo = self._offset_polyline(pts, self._distancia_cena(canvas), fechar=self._fechado(pts))
            if paralelo:
                self._criar_elemento(canvas, paralelo, {"elemento_idx": idx})
                criou += 1
        self._limpar_selecao_canvas(canvas)
        if criou:
            self._status(canvas, f"Criado(s) {criou} elemento(s) paralelo(s).")
        else:
            self._status(canvas, "Não foi possível criar paralelo da seleção.")

    def _redesenhar(self, canvas) -> None:
        if self._fase == "posicionar" and self._ultima_posicao_mouse is not None:
            self._atualizar_preview(canvas, self._ultima_posicao_mouse)
        canvas.update()

    def _limpar_estado(self) -> None:
        self._preview = []
        self._preview_2 = []
        self._hover_info = None
        self._fase = "selecionar"
        self._alvo_idx = None
        self._segmento_inicio = None
        self._segmento_hover = None
        self._direcao_selecao = None
        self._segmentos_selecionados = set()
        self._segmentos_visitados = set()
        self._selecao_contorno_completo = False
        self._realce_segmentos = []
        self._ultima_posicao_mouse = None

    def _limpar_selecao_canvas(self, canvas) -> None:
        if hasattr(canvas, "_selecionados"):
            try:
                canvas._selecionados.clear()
            except Exception:
                canvas._selecionados = set()

    def _iniciar_selecao(self, canvas, pos: QPointF) -> bool:
        info = self._segmento_mais_proximo(canvas, pos)
        if not info:
            return False
        self._alvo_idx = int(info["elemento_idx"])
        self._segmento_inicio = int(info["segmento_idx"])
        self._segmento_hover = int(info["segmento_idx"])
        self._direcao_selecao = None
        self._segmentos_selecionados = {int(info["segmento_idx"])}
        self._segmentos_visitados = {int(info["segmento_idx"])}
        self._selecao_contorno_completo = False
        canvas._selecionados = {self._alvo_idx}
        self._atualizar_realce(canvas)
        self._status(canvas, "Trecho iniciado. Mova pelo perimetro para acrescentar partes; clique esquerdo mostra a paralela.")
        canvas.update()
        return True

    def _atualizar_selecao_hover(self, canvas, pos: QPointF) -> None:
        info = self._segmento_mais_proximo(canvas, pos)
        self._hover_info = info
        if self._alvo_idx is None or self._segmento_inicio is None:
            self._realce_segmentos = []
            if info:
                self._realce_segmentos = [(info["segmento_inicio"], info["segmento_fim"])]
            return
        if not info or int(info["elemento_idx"]) != self._alvo_idx:
            return
        self._segmento_hover = int(info["segmento_idx"])
        total = self._total_segmentos(canvas, self._alvo_idx)
        if total <= 0:
            return
        if self._segmento_hover != self._segmento_inicio and self._direcao_selecao is None:
            frente = (self._segmento_hover - self._segmento_inicio) % total
            tras = (self._segmento_inicio - self._segmento_hover) % total
            self._direcao_selecao = 1 if frente <= tras else -1
        direcao = self._direcao_selecao or 1
        intervalo = self._segmentos_intervalo(self._segmento_inicio, self._segmento_hover, total, direcao)
        self._segmentos_visitados.update(intervalo)
        cobertura_atual = max(len(self._segmentos_visitados), len(intervalo))
        if cobertura_atual >= self._limite_contorno_completo(total):
            self._selecao_contorno_completo = True
            self._segmentos_selecionados = set(range(total))
        else:
            self._segmentos_selecionados = intervalo
        self._atualizar_realce(canvas)

    def _atualizar_preview(self, canvas, pos: QPointF) -> None:
        dialog = self._obter_dialog(canvas)
        self._preview = []
        self._preview_2 = []
        if self._alvo_idx is None or not self._segmentos_selecionados:
            return
        distancia = self._distancia_cena(canvas)
        caminho = self._caminho_segmentos(canvas, self._alvo_idx)
        if len(caminho) < 2:
            return
        lado = self._lado_mouse(caminho, pos)
        self._preview = self._offset_preview_contorno_fechado(canvas, self._alvo_idx, distancia, lado)
        if not self._preview:
            self._preview = self._offset_polyline_lado(caminho, distancia, lado)
        if dialog.chk_distancia_2.isChecked():
            distancia_2 = self._distancia_cena_2(canvas)
            self._preview_2 = self._offset_preview_contorno_fechado(canvas, self._alvo_idx, distancia_2, lado)
            if not self._preview_2:
                self._preview_2 = self._offset_polyline_lado(caminho, distancia_2, lado)
        self._hover_info = {"elemento_idx": self._alvo_idx}

    def _confirmar_paralela(self, canvas) -> bool:
        if len(self._preview) < 2:
            return False
        if self._preview_2:
            self._criar_elemento(canvas, self._preview, self._hover_info, registrar=False)
            self._criar_elemento(canvas, self._preview_2, self._hover_info, registrar=False)
            canvas._registrar_historico()
        else:
            self._criar_elemento(canvas, self._preview, self._hover_info)
        self._fase = "finalizado"
        self._preview = []
        self._preview_2 = []
        self._realce_segmentos = []
        self._limpar_selecao_canvas(canvas)
        self._status(canvas, "Elemento paralelo criado. Nada ficou selecionado. Clique esquerdo inicia outro; direito finaliza.")
        canvas.update()
        return True

    def _criar_elemento(self, canvas, pontos: list[QPointF], info: dict | None, registrar: bool = True) -> None:
        if len(pontos) < 2:
            return
        dialog = self._obter_dialog(canvas)
        origem = canvas.cena.elementos[int(info["elemento_idx"])] if info and "elemento_idx" in info and 0 <= int(info["elemento_idx"]) < len(canvas.cena.elementos) else {}
        auxiliar = bool(dialog.chk_linha_auxiliar.isChecked())
        novo = {
            "tipo": "polyline",
            "pontos": [(p.x(), p.y()) for p in pontos],
            "cor": origem.get("cor", getattr(canvas, "_linha_cor", "#ffffff")),
            "espessura": origem.get("espessura", getattr(canvas, "_linha_espessura", 1.0)),
            "estilo": origem.get("estilo", getattr(canvas, "_linha_estilo", "solid")),
            "id": str(uuid4()),
            "subtipo_audaces": "linha_interna" if auxiliar else "paralela",
            "linha_auxiliar": auxiliar,
            "metadados": {"tipo_ferramenta": self.id_ferramenta, "origem_idx": info.get("elemento_idx") if info else None},
        }
        canvas.cena.elementos.append(novo)
        self._limpar_selecao_canvas(canvas)
        if registrar:
            canvas._registrar_historico()
            self._limpar_selecao_canvas(canvas)
            canvas.update()
        self._operacao_finalizada = True
        self._direito_confirma_fechamento = False
        self._status(canvas, "Elemento paralelo criado. Clique esquerdo continua; direito fecha.")

    def _fechar(self, canvas) -> None:
        self._limpar_selecao_canvas(canvas)
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Elemento Paralelo finalizada. Voltando para Selecionar.")

    def on_paint_overlay(self, canvas, painter):
        if len(self._preview) < 2 and len(self._preview_2) < 2 and not self._realce_segmentos:
            return
        painter.save()
        if self._realce_segmentos:
            pen_realce = QPen(QColor("#ff2d2d"), 2.2, Qt.SolidLine)
            pen_realce.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_realce)
            for a, b in self._realce_segmentos:
                painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        for pontos, cor in ((self._preview, "#00d2ff"), (self._preview_2, "#7fdcff")):
            if len(pontos) < 2:
                continue
            pen = QPen(QColor(cor), 2.0, Qt.SolidLine)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            for a, b in zip(pontos, pontos[1:]):
                painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def _distancia_cena(self, canvas) -> float:
        valor = float(self._obter_dialog(canvas).sp_distancia.value())
        if hasattr(canvas, "converter_para_cena"):
            try:
                return float(canvas.converter_para_cena(valor))
            except Exception:
                pass
        return valor * max(1e-9, float(getattr(canvas, "_unidade_fator", 1.0)))

    def _distancia_cena_2(self, canvas) -> float:
        valor = float(self._obter_dialog(canvas).sp_distancia_2.value())
        if hasattr(canvas, "converter_para_cena"):
            try:
                return float(canvas.converter_para_cena(valor))
            except Exception:
                pass
        return valor * max(1e-9, float(getattr(canvas, "_unidade_fator", 1.0)))

    def _segmento_mais_proximo(self, canvas, pos: QPointF) -> dict | None:
        tolerancia = 10.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor = None
        for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
            el = canvas.cena.elementos[idx]
            pts = self._pontos_poly(el)
            if len(pts) < 2:
                continue
            for seg_idx, (a, b) in enumerate(zip(pts, pts[1:])):
                proj, dist = self._projetar_ponto_segmento(a, b, pos)
                if dist <= tolerancia and (melhor is None or dist < melhor["dist"]):
                    melhor = {
                        "elemento_idx": idx,
                        "segmento_idx": seg_idx,
                        "segmento_inicio": a,
                        "segmento_fim": b,
                        "dist": dist,
                        "proj": proj,
                    }
        return melhor

    def _total_segmentos(self, canvas, idx: int) -> int:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return 0
        return max(0, len(self._pontos_poly(canvas.cena.elementos[idx])) - 1)

    def _segmentos_intervalo(self, inicio: int, fim: int, total: int, direcao: int) -> set[int]:
        if total <= 0:
            return set()
        if direcao >= 0:
            qtd = (fim - inicio) % total
            return {(inicio + i) % total for i in range(qtd + 1)}
        qtd = (inicio - fim) % total
        return {(inicio - i) % total for i in range(qtd + 1)}

    @staticmethod
    def _limite_contorno_completo(total: int) -> int:
        if total <= 4:
            return total
        return max(4, int(total * 0.82))

    def _segmentos_ordenados(self, total: int) -> list[int]:
        if self._segmento_inicio is None or self._segmento_hover is None or total <= 0:
            return []
        direcao = self._direcao_selecao or 1
        if self._selecao_contorno_completo:
            return [(self._segmento_inicio + (i * direcao)) % total for i in range(total)]
        if direcao >= 0:
            qtd = (self._segmento_hover - self._segmento_inicio) % total
            return [(self._segmento_inicio + i) % total for i in range(qtd + 1)]
        qtd = (self._segmento_inicio - self._segmento_hover) % total
        return [(self._segmento_inicio - i) % total for i in range(qtd + 1)]

    def _atualizar_realce(self, canvas) -> None:
        self._realce_segmentos = []
        if self._alvo_idx is None or not (0 <= self._alvo_idx < len(canvas.cena.elementos)):
            return
        pts = self._pontos_poly(canvas.cena.elementos[self._alvo_idx])
        for seg_idx in sorted(self._segmentos_selecionados):
            if 0 <= seg_idx < len(pts) - 1:
                self._realce_segmentos.append((pts[seg_idx], pts[seg_idx + 1]))

    def _caminho_segmentos(self, canvas, idx: int) -> list[QPointF]:
        pts = self._pontos_poly(canvas.cena.elementos[idx]) if 0 <= idx < len(canvas.cena.elementos) else []
        total = max(0, len(pts) - 1)
        ordenados = self._segmentos_ordenados(total)
        if not ordenados:
            return []
        if (self._direcao_selecao or 1) >= 0:
            caminho = [QPointF(pts[ordenados[0]])]
            for seg_idx in ordenados:
                caminho.append(QPointF(pts[seg_idx + 1]))
            return caminho
        caminho = [QPointF(pts[ordenados[0] + 1])]
        for seg_idx in ordenados:
            caminho.append(QPointF(pts[seg_idx]))
        return caminho

    def _offset_preview_contorno_fechado(self, canvas, idx: int, distancia: float, lado_caminho: float) -> list[QPointF]:
        if not self._selecao_contorno_completo:
            return []
        if not (0 <= idx < len(canvas.cena.elementos)):
            return []
        pts = self._pontos_poly(canvas.cena.elementos[idx])
        if not self._fechado(pts):
            return []
        base = pts[:-1]
        total = len(base)
        ordenados = self._segmentos_ordenados(total)
        if total < 2 or not ordenados:
            return []
        direcao = self._direcao_selecao or 1
        lado_contorno = lado_caminho if direcao >= 0 else -lado_caminho
        vertices_offset = self._offset_vertices_contorno(base, distancia, lado_contorno)
        if len(vertices_offset) != total:
            return []
        if direcao >= 0:
            pontos = [QPointF(vertices_offset[ordenados[0]])]
            for seg_idx in ordenados:
                pontos.append(QPointF(vertices_offset[(seg_idx + 1) % total]))
        else:
            pontos = [QPointF(vertices_offset[(ordenados[0] + 1) % total])]
            for seg_idx in ordenados:
                pontos.append(QPointF(vertices_offset[seg_idx]))
        if self._selecao_contorno_completo and pontos:
            pontos.append(QPointF(pontos[0]))
        return self._deduplicar_qpoints(pontos)

    def _lado_mouse(self, pts: list[QPointF], pos: QPointF) -> float:
        melhor = None
        for a, b in zip(pts, pts[1:]):
            _proj, dist = self._projetar_ponto_segmento(a, b, pos)
            if melhor is None or dist < melhor[0]:
                melhor = (dist, a, b)
        if melhor is None:
            return 1.0
        _dist, a, b = melhor
        nx, ny = self._normal_segmento(a, b)
        mx = (a.x() + b.x()) / 2.0
        my = (a.y() + b.y()) / 2.0
        return 1.0 if ((pos.x() - mx) * nx + (pos.y() - my) * ny) >= 0 else -1.0

    def _offset_polyline_lado(self, pts: list[QPointF], distancia: float, lado: float) -> list[QPointF]:
        if len(pts) < 2:
            return []
        linhas = []
        for a, b in zip(pts, pts[1:]):
            nx, ny = self._normal_segmento(a, b)
            nx *= lado
            ny *= lado
            linhas.append((QPointF(a.x() + nx * distancia, a.y() + ny * distancia), QPointF(b.x() + nx * distancia, b.y() + ny * distancia)))
        out = [linhas[0][0]]
        for i in range(1, len(linhas)):
            out.extend(self._pontos_juncao_offset(pts[i], linhas[i - 1], linhas[i], abs(distancia)))
        out.append(linhas[-1][1])
        return self._deduplicar_qpoints(out)

    def _offset_vertices_contorno(self, base: list[QPointF], distancia: float, lado: float) -> list[QPointF]:
        linhas = []
        n = len(base)
        for i in range(n):
            a, b = base[i], base[(i + 1) % n]
            nx, ny = self._normal_segmento(a, b)
            nx *= lado
            ny *= lado
            linhas.append((QPointF(a.x() + nx * distancia, a.y() + ny * distancia), QPointF(b.x() + nx * distancia, b.y() + ny * distancia)))
        out = []
        for i in range(n):
            inter = self._intersecao_linhas(linhas[(i - 1) % n][0], linhas[(i - 1) % n][1], linhas[i][0], linhas[i][1])
            out.append(inter if inter is not None else linhas[i][0])
        return out

    def _pontos_juncao_offset(
        self,
        vertice_original: QPointF,
        linha_anterior: tuple[QPointF, QPointF],
        linha_atual: tuple[QPointF, QPointF],
        distancia: float,
    ) -> list[QPointF]:
        angulo = self._angulo_entre_segmentos(linha_anterior[0], linha_anterior[1], linha_atual[0], linha_atual[1])
        if angulo < 0.35:
            return [self._media_pontos(linha_anterior[1], linha_atual[0])]

        inter = self._intersecao_linhas(linha_anterior[0], linha_anterior[1], linha_atual[0], linha_atual[1])
        if inter is not None:
            tamanho_ref = max(
                distancia * 4.0,
                min(self._dist(linha_anterior[0], linha_anterior[1]), self._dist(linha_atual[0], linha_atual[1])) * 1.6,
            )
            if self._dist(inter, linha_anterior[1]) > tamanho_ref or self._dist(inter, linha_atual[0]) > tamanho_ref:
                return [self._media_pontos(linha_anterior[1], linha_atual[0])]
            return [inter]

        # Linhas paralelas nao possuem ponto unico de encontro; nesse caso, a
        # ponte reta fecha o trecho sem inverter a ordem da paralela.
        return self._ponte_canto_reta(linha_anterior[1], linha_atual[0], distancia)

    def _ponte_canto_reta(self, inicio: QPointF, fim: QPointF, distancia: float) -> list[QPointF]:
        if self._dist(inicio, fim) <= max(1e-6, distancia * 0.08):
            return [QPointF(fim)]
        return [QPointF(inicio), QPointF(fim)]

    @staticmethod
    def _deduplicar_qpoints(pontos: list[QPointF]) -> list[QPointF]:
        out: list[QPointF] = []
        for p in pontos:
            if out and Ferramenta._dist(out[-1], p) <= 1e-7:
                continue
            out.append(QPointF(p))
        return out

    def _pontos_poly(self, el: dict) -> list[QPointF]:
        if el.get("tipo") != "polyline":
            return []
        return [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]

    def _offset_polyline(self, pts: list[QPointF], distancia: float, fechar: bool) -> list[QPointF]:
        if len(pts) < 2:
            return []
        base = pts[:-1] if fechar and self._dist(pts[0], pts[-1]) <= 1e-6 else pts[:]
        if len(base) < 2:
            return []
        if not fechar:
            out = []
            for i, p in enumerate(base):
                if i == 0:
                    nx, ny = self._normal_segmento(base[0], base[1])
                elif i == len(base) - 1:
                    nx, ny = self._normal_segmento(base[-2], base[-1])
                else:
                    n1 = self._normal_segmento(base[i - 1], base[i])
                    n2 = self._normal_segmento(base[i], base[i + 1])
                    nx, ny = self._normalizar(n1[0] + n2[0], n1[1] + n2[1])
                out.append(QPointF(p.x() + nx * distancia, p.y() + ny * distancia))
            return out
        sentido = 1.0 if self._area(base) < 0 else -1.0
        linhas = []
        n = len(base)
        for i in range(n):
            a, b = base[i], base[(i + 1) % n]
            nx, ny = self._normal_segmento(a, b)
            nx, ny = nx * sentido, ny * sentido
            linhas.append((QPointF(a.x() + nx * distancia, a.y() + ny * distancia), QPointF(b.x() + nx * distancia, b.y() + ny * distancia)))
        out = []
        for i in range(n):
            inter = self._intersecao_linhas(linhas[(i - 1) % n][0], linhas[(i - 1) % n][1], linhas[i][0], linhas[i][1])
            out.append(inter if inter is not None else linhas[i][0])
        out.append(QPointF(out[0]))
        return out

    @staticmethod
    def _projetar_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> tuple[QPointF, float]:
        abx, aby = b.x() - a.x(), b.y() - a.y()
        apx, apy = p.x() - a.x(), p.y() - a.y()
        den = abx * abx + aby * aby
        if den <= 1e-9:
            proj = QPointF(a)
        else:
            t = max(0.0, min(1.0, (apx * abx + apy * aby) / den))
            proj = QPointF(a.x() + abx * t, a.y() + aby * t)
        return proj, sqrt((proj.x() - p.x()) ** 2 + (proj.y() - p.y()) ** 2)

    @staticmethod
    def _normal_segmento(a: QPointF, b: QPointF) -> tuple[float, float]:
        dx, dy = b.x() - a.x(), b.y() - a.y()
        comp = sqrt(dx * dx + dy * dy) or 1.0
        return -dy / comp, dx / comp

    @staticmethod
    def _normalizar(x: float, y: float) -> tuple[float, float]:
        d = sqrt(x * x + y * y) or 1.0
        return x / d, y / d

    @staticmethod
    def _media_pontos(a: QPointF, b: QPointF) -> QPointF:
        return QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)

    @staticmethod
    def _angulo_entre_segmentos(a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF) -> float:
        from math import acos

        ax, ay = a2.x() - a1.x(), a2.y() - a1.y()
        bx, by = b2.x() - b1.x(), b2.y() - b1.y()
        da = sqrt(ax * ax + ay * ay)
        db = sqrt(bx * bx + by * by)
        if da <= 1e-9 or db <= 1e-9:
            return 0.0
        cosv = max(-1.0, min(1.0, ((ax * bx) + (ay * by)) / (da * db)))
        return acos(cosv)

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

    @staticmethod
    def _fechado(pts: list[QPointF]) -> bool:
        return len(pts) >= 3 and Ferramenta._dist(pts[0], pts[-1]) <= 1e-6

    @staticmethod
    def _area(pts: list[QPointF]) -> float:
        return sum((a.x() * b.y()) - (b.x() * a.y()) for a, b in zip(pts, pts[1:] + pts[:1])) / 2.0

    @staticmethod
    def _intersecao_linhas(a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF) -> QPointF | None:
        x1, y1, x2, y2 = a1.x(), a1.y(), a2.x(), a2.y()
        x3, y3, x4, y4 = b1.x(), b1.y(), b2.x(), b2.y()
        den = ((x1 - x2) * (y3 - y4)) - ((y1 - y2) * (x3 - x4))
        if abs(den) <= 1e-9:
            return None
        px = (((x1 * y2) - (y1 * x2)) * (x3 - x4) - (x1 - x2) * ((x3 * y4) - (y3 * x4))) / den
        py = (((x1 * y2) - (y1 * x2)) * (y3 - y4) - (y1 - y2) * ((x3 * y4) - (y3 * x4))) / den
        return QPointF(px, py)

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
