from __future__ import annotations

from math import hypot

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QLabel

from tools.movimento_utils import limpar_cache_runtime_elemento
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class LinhasAuxiliaresDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:linhas_auxiliares"
        self.setWindowTitle("Linhas auxiliares")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(205)
        self.setStyleSheet(
            """
            QDialog { background:#f4f8fb; color:#111111; }
            QLabel { color:#111111; }
            QComboBox {
                background:#ffffff;
                color:#111111;
                border:1px solid #8aa1b4;
                min-height:20px;
            }
            """
        )

        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)
        titulo = QLabel("Linhas auxiliares")
        titulo.setStyleSheet("font-weight:600; color:#66727c;")
        layout.addRow(titulo)

        self.cmb_acao = QComboBox()
        self.cmb_acao.addItems(["Adicionar", "Remover"])
        layout.addRow("Acao", self.cmb_acao)

        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Manual"])
        layout.addRow("Modo", self.cmb_modo)


class Ferramenta(FerramentaBase):
    id_ferramenta = "linhas_auxiliares"
    nome = "Inserir ou remover"
    usa_painel_auxiliar = False
    descricao_painel = "Insere ou remove linhas auxiliares internas do molde."

    _dialog_por_canvas: dict[int, LinhasAuxiliaresDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._linha_idx: int | None = None
        self._linha_base_idx: int | None = None
        self._linha_preview: list[QPointF] | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._molde_idx = self._molde_selecionado(canvas)
        self._linha_idx = None
        self._linha_base_idx = None
        self._linha_preview = None
        dialog = self._obter_dialog(canvas)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Linhas auxiliares: selecione o molde.")
        if canvas is not None:
            canvas.update()

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._molde_idx = None
        self._linha_idx = None
        self._linha_base_idx = None
        self._linha_preview = None
        if canvas is not None:
            canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._limpar_estado(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = self._pos_cena(canvas, event.position())
        acao = self._acao_atual(canvas)
        alvo_molde = self._molde_em_ponto(canvas, pos)
        if alvo_molde is not None and (self._molde_idx is None or self._molde_idx != alvo_molde):
            self._selecionar_molde(canvas, alvo_molde)
            self._status(canvas, "Molde selecionado. Agora clique na linha auxiliar.")
            event.accept()
            return True

        if self._molde_idx is None:
            self._status(canvas, "Linhas auxiliares: selecione um molde primeiro.")
            event.accept()
            return True

        if acao == "Remover":
            return self._processar_remocao(canvas, event, pos)
        return self._processar_adicao(canvas, event, pos)

    def on_paint_overlay(self, canvas, painter):
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return
        molde = canvas.cena.elementos[self._molde_idx]
        if not isinstance(molde, dict):
            return
        base = self._pontos_molde(molde)
        if len(base) >= 2:
            painter.save()
            pen = QPen(QColor("#ff4040"), 2.0, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath(canvas._cena_para_tela(base[0]))
            for ponto in base[1:]:
                path.lineTo(canvas._cena_para_tela(ponto))
            if len(base) > 2:
                path.closeSubpath()
            painter.drawPath(path)
            painter.restore()
        if self._linha_preview:
            self._desenhar_linha_preview(canvas, painter, self._linha_preview)

    def _processar_adicao(self, canvas, event, pos: QPointF) -> bool:
        if self._linha_idx is not None and self._linha_preview:
            self._adicionar_linha(canvas)
            event.accept()
            return True
        candidato = self._linha_solta_em_ponto(canvas, pos)
        if candidato is None:
            self._status(canvas, "Clique em uma linha interna para adicionar ao molde.")
            event.accept()
            return True
        idx, pontos = candidato
        self._linha_idx = idx
        self._linha_base_idx = None
        self._linha_preview = pontos
        self._status(canvas, "Linha selecionada. Clique novamente para confirmar.")
        canvas.update()
        event.accept()
        return True

    def _processar_remocao(self, canvas, event, pos: QPointF) -> bool:
        if self._linha_base_idx is not None and self._linha_preview:
            self._remover_linha(canvas)
            event.accept()
            return True
        candidato = self._linha_base_em_ponto(canvas, pos)
        if candidato is None:
            self._status(canvas, "Clique em uma linha auxiliar do molde para remover.")
            event.accept()
            return True
        idx, pontos = candidato
        self._linha_idx = None
        self._linha_base_idx = idx
        self._linha_preview = pontos
        self._status(canvas, "Linha selecionada. Clique novamente para remover.")
        canvas.update()
        event.accept()
        return True

    def _adicionar_linha(self, canvas) -> None:
        if self._molde_idx is None or self._linha_idx is None or not self._linha_preview:
            return
        if not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return
        if not (0 <= self._linha_idx < len(canvas.cena.elementos)):
            return
        molde = canvas.cena.elementos[self._molde_idx]
        origem = canvas.cena.elementos[self._linha_idx]
        if not isinstance(molde, dict) or not isinstance(origem, dict):
            return
        pontos = [(float(p.x()), float(p.y())) for p in self._linha_preview]
        if len(pontos) < 2:
            return
        linha = {
            "tipo": "linha_auxiliar",
            "pontos": pontos,
            "cor": str(molde.get("cor") or origem.get("cor") or "#ffffff"),
            "estilo": "solid",
            "controle_extremos": True,
            "graduavel": True,
            "origem": "linhas_auxiliares_tool",
        }
        molde.setdefault("linhas_auxiliares_base", []).append(linha)
        molde["mostrar_linhas_auxiliares"] = True
        limpar_cache_runtime_elemento(molde)
        del canvas.cena.elementos[self._linha_idx]
        if self._linha_idx < self._molde_idx:
            self._molde_idx -= 1
        canvas._selecionados = {self._molde_idx}
        canvas._registrar_historico()
        self._limpar_linha(canvas)
        self._status(canvas, "Linha auxiliar adicionada ao molde.")

    def _remover_linha(self, canvas) -> None:
        if self._molde_idx is None or self._linha_base_idx is None:
            return
        if not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return
        molde = canvas.cena.elementos[self._molde_idx]
        linhas = molde.get("linhas_auxiliares_base") if isinstance(molde, dict) else None
        if not isinstance(linhas, list) or not (0 <= self._linha_base_idx < len(linhas)):
            return
        del linhas[self._linha_base_idx]
        limpar_cache_runtime_elemento(molde)
        canvas._selecionados = {self._molde_idx}
        canvas._registrar_historico()
        self._limpar_linha(canvas)
        self._status(canvas, "Linha auxiliar removida do molde.")

    def _obter_dialog(self, canvas) -> LinhasAuxiliaresDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = LinhasAuxiliaresDialog(parent)
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
            dialog.cmb_acao.currentTextChanged.connect(lambda _texto: self._limpar_linha(canvas))
            self._dialog_por_canvas[chave] = dialog
        if not restaurar_posicao(dialog, dialog._chave_posicao):
            if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
                dialog.move(canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True))
        return dialog

    def _acao_atual(self, canvas) -> str:
        dialog = self._obter_dialog(canvas)
        return str(dialog.cmb_acao.currentText() or "Adicionar")

    def _molde_selecionado(self, canvas) -> int | None:
        for idx in sorted(getattr(canvas, "_selecionados", set()) or []):
            try:
                idx_int = int(idx)
            except Exception:
                continue
            if 0 <= idx_int < len(canvas.cena.elementos) and canvas.cena.elementos[idx_int].get("molde"):
                return idx_int
        return None

    def _molde_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
            el = canvas.cena.elementos[idx]
            if not isinstance(el, dict) or not el.get("molde"):
                continue
            if self._ponto_dentro_poligono(pos, self._pontos_molde(el)):
                return idx
        return None

    def _selecionar_molde(self, canvas, idx: int) -> None:
        self._molde_idx = idx
        self._linha_idx = None
        self._linha_base_idx = None
        self._linha_preview = None
        canvas._selecionados = {idx}
        canvas.update()

    def _linha_solta_em_ponto(self, canvas, pos: QPointF) -> tuple[int, list[QPointF]] | None:
        tolerancia = self._tolerancia(canvas)
        melhor: tuple[float, int, list[QPointF]] | None = None
        for idx in range(len(canvas.cena.elementos) - 1, -1, -1):
            if idx == self._molde_idx:
                continue
            el = canvas.cena.elementos[idx]
            if not self._elemento_linha_auxiliar_candidato(el):
                continue
            if not self._linha_pertence_ao_molde(canvas, el):
                continue
            pontos = self._pontos_elemento(el)
            if len(pontos) < 2:
                continue
            dist = self._distancia_linha(pos, pontos)
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, idx, pontos)
        if melhor is None:
            return None
        return melhor[1], melhor[2]

    def _linha_base_em_ponto(self, canvas, pos: QPointF) -> tuple[int, list[QPointF]] | None:
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return None
        molde = canvas.cena.elementos[self._molde_idx]
        linhas = molde.get("linhas_auxiliares_base") if isinstance(molde, dict) else None
        if not isinstance(linhas, list):
            return None
        tolerancia = self._tolerancia(canvas)
        melhor: tuple[float, int, list[QPointF]] | None = None
        for idx, linha in enumerate(linhas):
            origem = linha.get("pontos") if isinstance(linha, dict) else linha
            pontos = self._pontos_de_lista(origem)
            if len(pontos) < 2:
                continue
            dist = self._distancia_linha(pos, pontos)
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, idx, pontos)
        if melhor is None:
            return None
        return melhor[1], melhor[2]

    def _elemento_linha_auxiliar_candidato(self, el) -> bool:
        if not isinstance(el, dict) or el.get("molde") or el.get("tipo") != "polyline":
            return False
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        subtipo = str(el.get("subtipo_audaces") or metadados.get("subtipo_audaces") or "").strip()
        return bool(
            subtipo == "linha_interna"
            or el.get("molde_linha_vinculada")
            or el.get("linha_auxiliar")
            or not el.get("fechado", False)
        )

    def _linha_pertence_ao_molde(self, canvas, el: dict) -> bool:
        if self._molde_idx is None or not (0 <= self._molde_idx < len(canvas.cena.elementos)):
            return False
        molde = canvas.cena.elementos[self._molde_idx]
        molde_id = str(molde.get("molde_id") or molde.get("id") or "").strip()
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        linha_id = str(el.get("molde_id") or metadados.get("molde_id") or "").strip()
        if molde_id and linha_id:
            return molde_id == linha_id
        pontos = self._pontos_elemento(el)
        if not pontos:
            return False
        centro = QPointF(
            sum(p.x() for p in pontos) / len(pontos),
            sum(p.y() for p in pontos) / len(pontos),
        )
        return self._ponto_dentro_poligono(centro, self._pontos_molde(molde))

    @staticmethod
    def _pos_cena(canvas, pos) -> QPointF:
        if hasattr(canvas, "_tela_para_cena"):
            return QPointF(canvas._tela_para_cena(pos))
        return QPointF(pos)

    @staticmethod
    def _pontos_de_lista(origem) -> list[QPointF]:
        pontos: list[QPointF] = []
        if not isinstance(origem, list):
            return pontos
        for item in origem:
            try:
                if isinstance(item, dict):
                    pontos.append(QPointF(float(item.get("x", 0.0)), float(item.get("y", 0.0))))
                elif isinstance(item, (tuple, list)) and len(item) >= 2:
                    pontos.append(QPointF(float(item[0]), float(item[1])))
            except Exception:
                continue
        return pontos

    def _pontos_elemento(self, el: dict) -> list[QPointF]:
        return self._pontos_de_lista(el.get("pontos") if isinstance(el, dict) else None)

    def _pontos_molde(self, el: dict) -> list[QPointF]:
        pontos = self._pontos_elemento(el)
        if len(pontos) > 1 and self._dist(pontos[0], pontos[-1]) <= 1e-7:
            pontos = pontos[:-1]
        return pontos

    @staticmethod
    def _ponto_dentro_poligono(pos: QPointF, pontos: list[QPointF]) -> bool:
        if len(pontos) < 3:
            return False
        path = QPainterPath(pontos[0])
        for ponto in pontos[1:]:
            path.lineTo(ponto)
        path.closeSubpath()
        return path.contains(pos)

    def _distancia_linha(self, pos: QPointF, pontos: list[QPointF]) -> float:
        return min(
            self._distancia_segmento(pos, a, b)
            for a, b in zip(pontos, pontos[1:])
        )

    @staticmethod
    def _distancia_segmento(p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-12:
            return Ferramenta._dist(p, a)
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return Ferramenta._dist(p, proj)

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _tolerancia(canvas) -> float:
        return max(0.05, 10.0 / max(float(getattr(canvas, "zoom", 1.0) or 1.0), 0.001))

    def _desenhar_linha_preview(self, canvas, painter, pontos: list[QPointF]) -> None:
        painter.save()
        try:
            pen = QPen(QColor("#ff00d4"), 2.0, Qt.SolidLine)
            painter.setPen(pen)
            for a, b in zip(pontos, pontos[1:]):
                painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
            painter.setBrush(QColor("#ff00d4"))
            for pt in (pontos[0], pontos[-1]):
                tela = canvas._cena_para_tela(pt)
                painter.drawEllipse(tela, 4, 4)
        finally:
            painter.restore()

    def _limpar_estado(self, canvas) -> None:
        self._molde_idx = None
        self._limpar_linha(canvas)
        self._status(canvas, "Linhas auxiliares: selecione o molde.")

    def _limpar_linha(self, canvas) -> None:
        self._linha_idx = None
        self._linha_base_idx = None
        self._linha_preview = None
        if canvas is not None:
            canvas.update()

    @staticmethod
    def _status(canvas, texto: str) -> None:
        lbl = getattr(canvas, "lbl_status", None)
        if lbl is not None and hasattr(lbl, "setText"):
            lbl.setText(texto)
