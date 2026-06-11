from __future__ import annotations

from math import atan2, degrees, sqrt

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.formatacao import formatar_numero
from tools.medicao_utils import mensagem_status
from tools.tool_base import FerramentaBase


class CompararDistanciaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Distancia entre pontos (cm)")
        self.resize(830, 420)
        self.setMinimumSize(720, 360)
        self._tamanhos: list[dict] = []
        self._medida_atual: list[dict] = []
        self._selecoes_mais: list[list[dict]] = []
        self._selecoes_menos: list[list[dict]] = []
        self._construir_ui()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.tabs = QTabWidget()
        self.tbl_distancias = self._criar_tabela()
        self.tbl_detalhes = self._criar_tabela()
        self.tabs.addTab(self._envolver_tabela(self.tbl_distancias), "Distancias")
        self.tabs.addTab(self._envolver_tabela(self.tbl_detalhes), "Distancia / DX / DY")
        layout.addWidget(self.tabs, 1)

        botoes = QHBoxLayout()
        self.btn_adicionar = QPushButton("Adicionar")
        self.btn_subtrair = QPushButton("Subtrair")
        self.btn_limpar = QPushButton("Limpar")
        self.btn_incluir = QPushButton("Incluir medida")
        self.btn_imprimir = QPushButton("Imprimir")
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(["Distancia", "DX", "DY", "Dif. Dist.", "Dif. DX", "Dif. DY"])
        for botao in (self.btn_adicionar, self.btn_subtrair, self.btn_limpar, self.btn_incluir, self.btn_imprimir):
            botoes.addWidget(botao)
        botoes.addWidget(self.cmb_tipo)
        layout.addLayout(botoes)

        self.btn_adicionar.clicked.connect(self.adicionar_atual)
        self.btn_subtrair.clicked.connect(self.subtrair_atual)
        self.btn_limpar.clicked.connect(self.limpar)
        self.btn_incluir.clicked.connect(self.incluir_medida)
        self.btn_imprimir.clicked.connect(self.imprimir)
        self._renderizar_distancias()
        self._renderizar_detalhes()

    @staticmethod
    def _criar_tabela() -> QTableWidget:
        tabela = QTableWidget(0, 0)
        tabela.verticalHeader().setVisible(False)
        tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        tabela.setSelectionMode(QTableWidget.NoSelection)
        tabela.setStyleSheet(
            """
            QTableWidget { background:#ffffff; gridline-color:#d7d7d7; color:#000000; }
            QHeaderView::section { background:#ffffff; color:#000000; border:1px solid #d7d7d7; padding:4px; }
            """
        )
        return tabela

    @staticmethod
    def _envolver_tabela(tabela: QTableWidget) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabela)
        return widget

    def definir_tamanhos(self, tamanhos: list[dict]):
        self._tamanhos = [dict(t) for t in tamanhos] if tamanhos else self._tamanhos_padrao()
        self._renderizar_distancias()
        self._renderizar_detalhes()

    def receber_medida(self, medida: dict):
        if not self._tamanhos:
            self._tamanhos = self._tamanhos_padrao()
        self._medida_atual = [
            self._medida_para_tamanho(medida, idx, tamanho)
            for idx, tamanho in enumerate(self._tamanhos)
        ]
        self._renderizar_detalhes()
        self.tabs.setCurrentIndex(1)
        self.show()
        self.raise_()
        self.activateWindow()

    def adicionar_atual(self):
        if not self._medida_atual:
            return
        self._selecoes_mais.append([dict(m) for m in self._medida_atual])
        self._renderizar_distancias()
        self.tabs.setCurrentIndex(0)

    def subtrair_atual(self):
        if not self._medida_atual:
            return
        self._selecoes_menos.append([dict(m) for m in self._medida_atual])
        self._renderizar_distancias()
        self.tabs.setCurrentIndex(0)

    def limpar(self):
        self._medida_atual.clear()
        self._selecoes_mais.clear()
        self._selecoes_menos.clear()
        self._renderizar_distancias()
        self._renderizar_detalhes()

    def incluir_medida(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Medidas do modelo")
        dialog.resize(480, 260)
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget()
        tabela = self._criar_tabela()
        tamanhos = self._tamanhos or self._tamanhos_padrao()
        headers = ["Medida (cm)"] + [str(t.get("nome") or "") for t in tamanhos] + ["Formula"]
        tabela.setColumnCount(len(headers))
        tabela.setHorizontalHeaderLabels(headers)
        tabela.setRowCount(1)
        tabela.setItem(0, 0, QTableWidgetItem("Medida 1"))
        for col in range(1, len(headers) - 1):
            tabela.setItem(0, col, QTableWidgetItem("0"))
        tabela.setItem(0, len(headers) - 1, QTableWidgetItem("c * 1.0"))
        tabs.addTab(self._envolver_tabela(tabela), "Avancado")
        layout.addWidget(tabs)
        rodape = QHBoxLayout()
        btn_fechar = QPushButton("Fechar")
        btn_fechar.clicked.connect(dialog.accept)
        rodape.addStretch(1)
        rodape.addWidget(btn_fechar)
        layout.addLayout(rodape)
        dialog.exec()

    def imprimir(self):
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Imprimir")
        if dialog.exec() != QDialog.Accepted:
            return
        painter = QPainter(printer)
        try:
            rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            margem = 80
            x = rect.left() + margem
            y = rect.top() + margem
            largura = rect.width() - (margem * 2)
            painter.setPen(QPen(QColor("#000000"), 1))
            fonte = painter.font()
            fonte.setPointSize(14)
            fonte.setBold(True)
            painter.setFont(fonte)
            titulo = "Distancia entre pontos (cm)"
            fm = QFontMetrics(fonte)
            painter.drawText(int(x + ((largura - fm.horizontalAdvance(titulo)) / 2)), int(y + 30), titulo)
            y += 90
            self._desenhar_tabela_impressao(painter, x, y, largura)
        finally:
            painter.end()

    def _desenhar_tabela_impressao(self, painter: QPainter, x: float, y: float, largura: float):
        headers, linhas = self._dados_tabela_distancias()
        if not headers:
            return
        altura_linha = 30
        col_w = largura / len(headers)
        fonte = painter.font()
        fonte.setPointSize(8)
        fonte.setBold(True)
        painter.setFont(fonte)
        for col, header in enumerate(headers):
            rect = QRectF(x + (col * col_w), y, col_w, altura_linha)
            painter.drawRect(rect)
            painter.drawText(rect, Qt.AlignCenter, header)
        fonte.setBold(False)
        painter.setFont(fonte)
        for row, dados in enumerate(linhas, start=1):
            for col, valor in enumerate(dados):
                rect = QRectF(x + (col * col_w), y + (row * altura_linha), col_w, altura_linha)
                painter.drawRect(rect)
                painter.drawText(rect, Qt.AlignCenter, str(valor))

    def _renderizar_detalhes(self):
        headers = ["Tamanho", "Distancia", "DX", "DY", "Dif. Dist.", "Dif. DX", "Dif. DY", "Angulo"]
        self.tbl_detalhes.setColumnCount(len(headers))
        self.tbl_detalhes.setHorizontalHeaderLabels(headers)
        linhas = self._medida_atual
        self.tbl_detalhes.setRowCount(len(linhas))
        base = self._linha_base(linhas)
        for row, medida in enumerate(linhas):
            valores = [
                medida["nome"],
                self._fmt(medida["distancia"]),
                self._fmt(medida["dx"]),
                self._fmt(medida["dy"]),
                self._fmt(medida["distancia"] - base.get("distancia", medida["distancia"])),
                self._fmt(medida["dx"] - base.get("dx", medida["dx"])),
                self._fmt(medida["dy"] - base.get("dy", medida["dy"])),
                self._fmt(medida["angulo"]),
            ]
            self._popular_linha(self.tbl_detalhes, row, valores, medida.get("cor"))
        self.tbl_detalhes.resizeColumnsToContents()

    def _renderizar_distancias(self):
        headers, linhas = self._dados_tabela_distancias()
        self.tbl_distancias.setColumnCount(len(headers))
        self.tbl_distancias.setHorizontalHeaderLabels(headers)
        self.tbl_distancias.setRowCount(len(linhas))
        for row, valores in enumerate(linhas):
            self._popular_linha(self.tbl_distancias, row, valores, self._cor_tamanho(valores[0]))
        self.tbl_distancias.resizeColumnsToContents()

    def _dados_tabela_distancias(self) -> tuple[list[str], list[list[str]]]:
        tamanhos = self._tamanhos or self._tamanhos_padrao()
        headers = ["Tamanho"]
        headers.extend(f"Selecao {i}" for i in range(1, len(self._selecoes_mais) + 1))
        headers.append("Total (+)")
        headers.extend(f"Selecao {i}" for i in range(1, len(self._selecoes_menos) + 1))
        headers.append("Total (-)")
        headers.append("Total")
        linhas: list[list[str]] = []
        for idx, tamanho in enumerate(tamanhos):
            nome = str(tamanho.get("nome") or "")
            mais = [self._valor_selecao(sel, idx) for sel in self._selecoes_mais]
            menos = [self._valor_selecao(sel, idx) for sel in self._selecoes_menos]
            total_mais = sum(mais)
            total_menos = sum(menos)
            linha = [nome]
            linha.extend(self._fmt(v) for v in mais)
            linha.append(self._fmt(total_mais))
            linha.extend(self._fmt(v) for v in menos)
            linha.append(self._fmt(total_menos))
            linha.append(self._fmt(total_mais - total_menos))
            linhas.append(linha)
        return headers, linhas

    def _popular_linha(self, tabela: QTableWidget, row: int, valores: list[str], cor: str | None = None):
        for col, valor in enumerate(valores):
            item = QTableWidgetItem(str(valor))
            item.setTextAlignment(Qt.AlignCenter)
            if col == 0 and cor:
                item.setBackground(QColor(cor))
            tabela.setItem(row, col, item)

    def _medida_para_tamanho(self, medida: dict, idx: int, tamanho: dict) -> dict:
        fator = float(tamanho.get("fator", 0.0) or 0.0)
        dx = float(medida.get("dx", 0.0)) + (fator * 0.42)
        dy = float(medida.get("dy", 0.0)) + (fator * 0.12)
        distancia = sqrt((dx * dx) + (dy * dy))
        angulo = degrees(atan2(-dy, dx)) % 360.0
        return {
            "nome": str(tamanho.get("nome") or f"T{idx + 1}"),
            "cor": str(tamanho.get("cor") or ""),
            "distancia": distancia,
            "dx": dx,
            "dy": dy,
            "angulo": angulo,
        }

    @staticmethod
    def _linha_base(linhas: list[dict]) -> dict:
        for linha in linhas:
            if str(linha.get("nome") or "").strip().upper() in {"P (B)", "M", "BASE"}:
                return linha
        return linhas[0] if linhas else {}

    @staticmethod
    def _valor_selecao(selecao: list[dict], idx: int) -> float:
        if not selecao:
            return 0.0
        idx = max(0, min(idx, len(selecao) - 1))
        return float(selecao[idx].get("distancia", 0.0) or 0.0)

    def _cor_tamanho(self, nome: str) -> str | None:
        for tamanho in self._tamanhos or self._tamanhos_padrao():
            if str(tamanho.get("nome") or "") == str(nome):
                return str(tamanho.get("cor") or "")
        return None

    @staticmethod
    def _fmt(valor: float) -> str:
        return formatar_numero(valor, 2)

    @staticmethod
    def _tamanhos_padrao() -> list[dict]:
        return [
            {"nome": "PP", "cor": "#00f5c8", "fator": 1.0},
            {"nome": "P (B)", "cor": "#f2f000", "fator": 0.0},
            {"nome": "M", "cor": "#0000ff", "fator": -1.0},
            {"nome": "G", "cor": "#ffffff", "fator": -2.0},
            {"nome": "GG", "cor": "#10aee8", "fator": -3.0},
            {"nome": "G1", "cor": "#008000", "fator": -4.0},
            {"nome": "G2", "cor": "#9cff00", "fator": -5.0},
        ]


class Ferramenta(FerramentaBase):
    id_ferramenta = "comparar_distancia"
    nome = "Comparar Distancia"
    descricao_painel = "Compare distancias entre pontos ou locais no perimetro."

    _dialog_por_canvas: dict[int, CompararDistanciaDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._ponto_inicio: QPointF | None = None
        self._ponto_preview: QPointF | None = None
        self._ponto_final: QPointF | None = None
        self._medidas: list[tuple[QPointF, QPointF]] = []
        self._dialog: CompararDistanciaDialog | None = None
        self._tamanhos_ativos: list[dict] = []

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._resetar_fluxo()
        self._dialog = self._obter_dialog(canvas)
        self._dialog.definir_tamanhos(self._tamanhos_do_canvas(canvas, None))
        self._dialog.show()
        self._dialog.raise_()
        self._status(canvas, "Comparar distancia: clique no molde inicial.")
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._voltar_etapa(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        if self._molde_idx is None:
            molde_idx = self._molde_em_posicao(canvas, pos)
            if molde_idx is None:
                self._status(canvas, "Comparar distancia: clique sobre o molde inicial.")
                event.accept()
                return True
            self._molde_idx = molde_idx
            self._tamanhos_ativos = self._tamanhos_do_canvas(canvas, molde_idx)
            if self._dialog is not None:
                self._dialog.definir_tamanhos(self._tamanhos_ativos)
            self._ponto_inicio = None
            self._ponto_preview = None
            self._ponto_final = None
            canvas._selecionados = {molde_idx}
            self._status(canvas, "Molde inicial realcado. Clique no ponto ou local do perimetro.")
            canvas.update()
            event.accept()
            return True

        if self._ponto_inicio is None:
            ponto = self._ponto_no_perimetro(canvas, self._molde_idx, pos)
            if ponto is None:
                self._status(canvas, "Comparar distancia: indique um ponto no perimetro do molde realcado.")
                event.accept()
                return True
            self._ponto_inicio = ponto
            self._ponto_preview = ponto
            self._ponto_final = None
            self._status(canvas, "Ponto inicial cravado. Mova o mouse ate o destino e clique para finalizar.")
            canvas.update()
            event.accept()
            return True

        destino = self._ponto_destino(canvas, pos)
        self._ponto_final = destino
        self._medidas.append((QPointF(self._ponto_inicio), QPointF(destino)))
        self._registrar_medida_dialog(canvas, self._ponto_inicio, destino)
        self._status_medida(canvas, self._ponto_inicio, destino, final=True)
        self._molde_idx = None
        self._ponto_inicio = None
        self._ponto_preview = None
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if self._molde_idx is None:
            return False
        if self._ponto_inicio is None:
            self._ponto_preview = self._ponto_no_perimetro(canvas, self._molde_idx, pos)
            canvas.update()
            return True
        self._ponto_preview = self._ponto_destino(canvas, pos)
        self._status_medida(canvas, self._ponto_inicio, self._ponto_preview, final=False)
        canvas.update()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_medidas_finalizadas(canvas, painter)
        if self._molde_idx is not None:
            self._desenhar_realce_molde(canvas, painter, self._molde_idx)
        if self._ponto_inicio is not None:
            self._desenhar_alvo(canvas, painter, self._ponto_inicio, "#ff2a2a")
        elif self._ponto_preview is not None:
            self._desenhar_alvo(canvas, painter, self._ponto_preview, "#ff2a2a")
        if self._ponto_inicio is not None and self._ponto_preview is not None:
            self._desenhar_linha_medida(canvas, painter, self._ponto_inicio, self._ponto_preview, preview=True)

    def _voltar_etapa(self, canvas):
        if self._ponto_inicio is not None:
            self._ponto_inicio = None
            self._ponto_preview = None
            self._ponto_final = None
            self._status(canvas, "Etapa cancelada. Clique em outro ponto do perimetro.")
        elif self._molde_idx is not None:
            self._molde_idx = None
            self._ponto_preview = None
            self._ponto_final = None
            self._status(canvas, "Etapa cancelada. Clique no molde inicial.")
        elif self._medidas:
            self._medidas.pop()
            self._status(canvas, "Ultima comparacao removida. Clique no molde inicial.")
        else:
            self._status(canvas, "Comparar distancia: clique no molde inicial.")
        canvas.update()

    def _resetar_fluxo(self):
        self._molde_idx = None
        self._ponto_inicio = None
        self._ponto_preview = None
        self._ponto_final = None
        self._medidas.clear()

    def _obter_dialog(self, canvas) -> CompararDistanciaDialog:
        chave = id(canvas)
        dialog = self._dialog_por_canvas.get(chave)
        parent = canvas.window() if hasattr(canvas, "window") else None
        if dialog is None:
            dialog = CompararDistanciaDialog(parent)
            dialog.destroyed.connect(lambda *_: self._dialog_por_canvas.pop(chave, None))
            self._dialog_por_canvas[chave] = dialog
        return dialog

    def _registrar_medida_dialog(self, canvas, inicio: QPointF, fim: QPointF):
        if self._dialog is None:
            self._dialog = self._obter_dialog(canvas)
        dx = fim.x() - inicio.x()
        dy = fim.y() - inicio.y()
        self._dialog.definir_tamanhos(self._tamanhos_ativos or self._tamanhos_do_canvas(canvas, self._molde_idx))
        self._dialog.receber_medida({"dx": dx, "dy": dy})

    def _tamanhos_do_canvas(self, canvas, molde_idx: int | None) -> list[dict]:
        molde = None
        if molde_idx is not None and 0 <= molde_idx < len(canvas.cena.elementos):
            candidato = canvas.cena.elementos[molde_idx]
            if isinstance(candidato, dict):
                molde = candidato
        linhas = molde.get("graduacao_tamanhos") if isinstance(molde, dict) else []
        saida: list[dict] = []
        ativos = [l for l in linhas if isinstance(l, dict) and l.get("ativo", True)] if isinstance(linhas, list) else []
        base_idx = next((i for i, l in enumerate(ativos) if l.get("base")), len(ativos) // 2 if ativos else 0)
        for idx, linha in enumerate(ativos):
            nome = str(linha.get("tamanho") or "").strip()
            if not nome:
                continue
            saida.append({"nome": nome, "cor": str(linha.get("cor") or ""), "fator": idx - base_idx})
        return saida or CompararDistanciaDialog._tamanhos_padrao()

    def _status(self, canvas, texto: str):
        self.set_status(texto)
        mensagem_status(canvas, texto)

    def _status_medida(self, canvas, inicio: QPointF, fim: QPointF, *, final: bool):
        dx = fim.x() - inicio.x()
        dy = fim.y() - inicio.y()
        distancia = sqrt((dx * dx) + (dy * dy))
        angulo = degrees(atan2(-dy, dx)) % 360.0
        prefixo = "Comparacao finalizada" if final else "Comparacao previa"
        texto = (
            f"{prefixo}: distancia {canvas.formatar_valor_unidade(distancia)} "
            f"| DX {canvas.formatar_valor_unidade(dx)} | DY {canvas.formatar_valor_unidade(dy)} "
            f"| angulo {formatar_numero(angulo, 1)}"
        )
        self._status(canvas, texto)

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        molde_idx = canvas._indice_molde_em_ponto(pos)
        if molde_idx is not None:
            return molde_idx
        melhor: tuple[float, int] | None = None
        tolerancia = max(0.1, 18.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.01))
        for idx, el in enumerate(canvas.cena.elementos):
            if not isinstance(el, dict) or not el.get("molde"):
                continue
            pontos_molde = canvas._pontos_render_elemento(el)
            if self._ponto_dentro_poligono(pos, pontos_molde):
                return idx
            ponto = self._ponto_no_perimetro(canvas, idx, pos)
            if ponto is None:
                continue
            dist = self._dist(pos, ponto)
            if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                melhor = (dist, idx)
        return melhor[1] if melhor is not None else None

    def _ponto_destino(self, canvas, pos: QPointF) -> QPointF:
        molde_idx = self._molde_em_posicao(canvas, pos)
        if molde_idx is not None:
            ponto = self._ponto_no_perimetro(canvas, molde_idx, pos)
            if ponto is not None:
                return ponto
        return QPointF(pos)

    def _ponto_no_perimetro(self, canvas, molde_idx: int, pos: QPointF) -> QPointF | None:
        if molde_idx < 0 or molde_idx >= len(canvas.cena.elementos):
            return None
        pontos = canvas._pontos_render_elemento(canvas.cena.elementos[molde_idx])
        if len(pontos) < 2:
            return None
        melhor_ponto: QPointF | None = None
        melhor_dist = float("inf")
        for a, b in zip(pontos, pontos[1:]):
            ponto = self._projetar_ponto_segmento(a, b, pos)
            dist = self._dist(pos, ponto)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_ponto = ponto
        return melhor_ponto

    def _desenhar_realce_molde(self, canvas, painter, molde_idx: int):
        if molde_idx < 0 or molde_idx >= len(canvas.cena.elementos):
            return
        pontos = canvas._pontos_render_elemento(canvas.cena.elementos[molde_idx])
        if len(pontos) < 2:
            return
        painter.save()
        canvas._desenhar_polilinha(painter, pontos, cor="#ff2020", espessura=2.2)
        painter.restore()

    def _desenhar_medidas_finalizadas(self, canvas, painter):
        for inicio, fim in self._medidas[-6:]:
            self._desenhar_linha_medida(canvas, painter, inicio, fim, preview=False)

    def _desenhar_linha_medida(self, canvas, painter, inicio: QPointF, fim: QPointF, *, preview: bool):
        cor = "#ff2020" if preview else "#e02020"
        estilo = Qt.DashLine if preview else Qt.SolidLine
        p0 = canvas._cena_para_tela(inicio)
        p1 = canvas._cena_para_tela(fim)
        painter.save()
        painter.setPen(QPen(QColor(cor), 2.0, estilo))
        painter.drawLine(p0, p1)
        self._desenhar_alvo(canvas, painter, inicio, cor)
        self._desenhar_alvo(canvas, painter, fim, cor)
        distancia = self._dist(inicio, fim)
        texto = canvas.formatar_valor_unidade(distancia)
        meio = QPointF((p0.x() + p1.x()) / 2.0, (p0.y() + p1.y()) / 2.0)
        metrics = QFontMetrics(painter.font())
        largura = metrics.horizontalAdvance(texto) + 10
        altura = metrics.height() + 6
        rect = QRectF(meio.x() + 8, meio.y() - altura - 4, largura, altura)
        painter.fillRect(rect, QColor(0, 0, 0, 190))
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.drawText(rect, Qt.AlignCenter, texto)
        painter.restore()

    def _desenhar_alvo(self, canvas, painter, ponto: QPointF, cor: str):
        tela = canvas._cena_para_tela(ponto)
        painter.save()
        painter.setPen(QPen(QColor(cor), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(tela.x() - 7.0, tela.y() - 7.0, 14.0, 14.0))
        painter.drawLine(QPointF(tela.x() - 10.0, tela.y()), QPointF(tela.x() + 10.0, tela.y()))
        painter.drawLine(QPointF(tela.x(), tela.y() - 10.0), QPointF(tela.x(), tela.y() + 10.0))
        painter.restore()

    @staticmethod
    def _projetar_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> QPointF:
        vx = b.x() - a.x()
        vy = b.y() - a.y()
        den = (vx * vx) + (vy * vy)
        if den <= 1e-12:
            return QPointF(a)
        t = ((p.x() - a.x()) * vx + (p.y() - a.y()) * vy) / den
        t = max(0.0, min(1.0, t))
        return QPointF(a.x() + (vx * t), a.y() + (vy * t))

    @staticmethod
    def _ponto_dentro_poligono(ponto: QPointF, pontos: list[QPointF]) -> bool:
        if len(pontos) < 3:
            return False
        base = pontos[:-1] if pontos[0] == pontos[-1] else pontos
        dentro = False
        j = len(base) - 1
        px = ponto.x()
        py = ponto.y()
        for i, atual in enumerate(base):
            anterior = base[j]
            yi = atual.y()
            yj = anterior.y()
            cruza = (yi > py) != (yj > py)
            if cruza:
                xi = atual.x()
                xj = anterior.x()
                den = yj - yi
                if abs(den) <= 1e-12:
                    j = i
                    continue
                x_inter = ((xj - xi) * (py - yi) / den) + xi
                if px < x_inter:
                    dentro = not dentro
            j = i
        return dentro

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)
