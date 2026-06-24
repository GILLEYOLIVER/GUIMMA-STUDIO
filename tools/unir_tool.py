from __future__ import annotations

from copy import deepcopy
from math import hypot, isfinite
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QVBoxLayout

from tools.movimento_utils import mover_elemento_por_delta
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


EPS = 1e-7


class UnirDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:unir"
        self.setWindowTitle("Unir moldes")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(210)
        self.setStyleSheet(
            """
            QDialog { background:#f2f2f2; color:#111111; }
            QCheckBox { color:#111111; font-size:11px; }
            QComboBox {
                background:#ffffff; color:#111111;
                border:1px solid #aeb4ba; min-height:21px;
                padding-left:3px;
            }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(6)
        self.chk_apenas_mover = QCheckBox("Apenas mover")
        self.chk_apenas_mover.setChecked(False)
        raiz.addWidget(self.chk_apenas_mover)

        linha = QFrame()
        linha.setFrameShape(QFrame.HLine)
        linha.setStyleSheet("color:#aeb4ba;")
        raiz.addWidget(linha)

        form = QFormLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        self.chk_unir_tamanhos = QCheckBox("Unir tamanhos")
        self.chk_unir_tamanhos.setChecked(True)
        self.cmb_tamanhos = QComboBox()
        form.addRow(self.chk_unir_tamanhos, self.cmb_tamanhos)
        self.cmb_giro = QComboBox()
        self.cmb_giro.addItems(["Igual tamanho", "Igual base"])
        form.addRow("Giro tamanho", self.cmb_giro)
        raiz.addLayout(form)


class Ferramenta(FerramentaBase):
    id_ferramenta = "unir"
    nome = "Unir"
    usa_painel_auxiliar = False
    descricao_painel = "Une moldes cortados, mantendo graduacao, piques e pontos de controle."

    _dialog_por_canvas: dict[int, UnirDialog] = {}

    def __init__(self):
        super().__init__()
        self._primeiro_idx: int | None = None
        self._segundo_idx: int | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._primeiro_idx = None
        self._segundo_idx = None
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        self._preencher_tamanhos_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Unir: clique no primeiro molde, clique no segundo e clique novamente para unir.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._primeiro_idx = None
        self._segundo_idx = None
        if canvas is not None and hasattr(canvas, "update"):
            canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._primeiro_idx is not None or self._segundo_idx is not None:
                self._primeiro_idx = None
                self._segundo_idx = None
                canvas.update()
                self._status(canvas, "Uniao cancelada. Clique no primeiro molde para recomecar.")
                event.accept()
                return True
            if hasattr(canvas, "set_ferramenta_ativa"):
                canvas.set_ferramenta_ativa("selecionar")
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = self._pos_cena(canvas, event.position())
        if self._primeiro_idx is None:
            idx = self._molde_em_posicao(canvas, pos)
            if idx is None:
                self._status(canvas, "Unir: clique em um molde.")
                event.accept()
                return True
            self._primeiro_idx = idx
            canvas._selecionados = {idx}
            self._preencher_tamanhos_dialog(canvas, self._obter_dialog(canvas))
            self._status(canvas, "Primeiro molde selecionado. Clique no molde que sera unido.")
            canvas.update()
            event.accept()
            return True

        if self._segundo_idx is None:
            idx = self._molde_em_posicao(canvas, pos, ignorar={self._primeiro_idx})
            if idx is None:
                self._status(canvas, "Unir: clique em outro molde.")
                event.accept()
                return True
            self._segundo_idx = idx
            canvas._selecionados = {self._primeiro_idx, idx}
            self._status(canvas, "Segundo molde selecionado. Clique novamente para confirmar.")
            canvas.update()
            event.accept()
            return True

        if self._unir_indices(canvas, self._primeiro_idx, self._segundo_idx):
            self._primeiro_idx = None
            self._segundo_idx = None
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        painter.save()
        try:
            for idx, cor in ((self._primeiro_idx, QColor("#ffd400")), (self._segundo_idx, QColor("#00e6ff"))):
                if idx is not None and 0 <= idx < len(canvas.cena.elementos):
                    self._desenhar_contorno(canvas, painter, canvas.cena.elementos[idx], cor)
        finally:
            painter.restore()

    def _unir_indices(self, canvas, idx_a: int, idx_b: int) -> bool:
        if idx_a == idx_b or not (0 <= idx_a < len(canvas.cena.elementos)) or not (0 <= idx_b < len(canvas.cena.elementos)):
            return False
        dialog = self._obter_dialog(canvas)
        if dialog.chk_apenas_mover.isChecked():
            return self._apenas_mover(canvas, idx_a, idx_b)
        if self._restaurar_corte_original(canvas, idx_a, idx_b):
            return True
        return self._unir_contornos_fallback(canvas, idx_a, idx_b)

    def _restaurar_corte_original(self, canvas, idx_a: int, idx_b: int) -> bool:
        a = canvas.cena.elementos[idx_a]
        b = canvas.cena.elementos[idx_b]
        meta_a = a.get("metadados") if isinstance(a.get("metadados"), dict) else {}
        meta_b = b.get("metadados") if isinstance(b.get("metadados"), dict) else {}
        corte_a = str(meta_a.get("corte_id") or "")
        corte_b = str(meta_b.get("corte_id") or "")
        if not corte_a or corte_a != corte_b:
            return False
        original = meta_a.get("molde_original_antes_corte") or meta_b.get("molde_original_antes_corte")
        if not isinstance(original, dict):
            return False
        restaurado = deepcopy(original)
        restaurado.setdefault("metadados", {})["unido_por"] = "unir_moldes"
        restaurado["metadados"]["corte_id_unido"] = corte_a
        restaurado["metadados"]["costura_descontada_uniao"] = True
        ids_partes = {
            str(a.get("molde_id") or a.get("id") or "").strip(),
            str(b.get("molde_id") or b.get("id") or "").strip(),
        }
        ids_partes.discard("")
        manter = min(idx_a, idx_b)
        remover = max(idx_a, idx_b)
        canvas.cena.elementos[manter] = restaurado
        canvas.cena.elementos.pop(remover)
        if ids_partes:
            canvas.cena.elementos = [
                el
                for el in canvas.cena.elementos
                if not self._costura_de_uma_das_partes(el, ids_partes)
            ]
        canvas._selecionados = {manter}
        self._registrar(canvas)
        canvas.update()
        self._status(canvas, "Moldes unidos: base, graduacao, piques e controles restaurados.")
        return True

    @staticmethod
    def _costura_de_uma_das_partes(el: dict, ids_partes: set[str]) -> bool:
        if not isinstance(el, dict):
            return False
        metadados = el.get("metadados") if isinstance(el.get("metadados"), dict) else {}
        subtipo = str(el.get("subtipo_audaces") or metadados.get("subtipo_audaces") or "").strip()
        costura_id = str(el.get("costura_de_molde_id") or metadados.get("costura_de_molde_id") or "").strip()
        return subtipo == "costura" and costura_id in ids_partes

    def _apenas_mover(self, canvas, idx_a: int, idx_b: int) -> bool:
        a = canvas.cena.elementos[idx_a]
        b = canvas.cena.elementos[idx_b]
        pa, pb = self._pontos_mais_proximos(a, b)
        if pa is None or pb is None:
            self._status(canvas, "Unir: nao foi possivel achar pontos para alinhar.")
            return False
        dx, dy = pa.x() - pb.x(), pa.y() - pb.y()
        mover_elemento_por_delta(b, dx, dy)
        canvas._selecionados = {idx_a, idx_b}
        self._registrar(canvas)
        canvas.update()
        self._status(canvas, "Segundo molde movido ate o primeiro.")
        return True

    def _unir_contornos_fallback(self, canvas, idx_a: int, idx_b: int) -> bool:
        a = canvas.cena.elementos[idx_a]
        b = canvas.cena.elementos[idx_b]
        pts_a = self._pontos_base(a)
        pts_b = self._pontos_base(b)
        if len(pts_a) < 2 or len(pts_b) < 2:
            return False
        ia, ib = self._indices_pontos_mais_proximos(pts_a, pts_b)
        seq_a = pts_a[ia:] + pts_a[:ia]
        seq_b = pts_b[ib:] + pts_b[:ib]
        pontos = self._limpar_repetidos([*seq_a, *seq_b])
        if len(pontos) < 3:
            return False
        unido = deepcopy(a)
        unido["id"] = str(uuid4())
        unido["molde_id"] = str(uuid4())
        unido["pontos"] = [*pontos, pontos[0]]
        controles = self._controles_unidos_fallback(a, b, pontos)
        unido["controle_cantos"] = controles
        unido["controle_auxiliares"] = []
        unido["pontos_controle_principais"] = [{"x": x, "y": y} for x, y in controles]
        unido["pontos_auxiliares"] = []
        unido["fechado"] = True
        unido["molde"] = True
        unido.setdefault("metadados", {})["unido_por"] = "unir_moldes_fallback"
        unido["metadados"]["costura_descontada_uniao"] = True
        self._mesclar_piques(unido, a, b)
        manter = min(idx_a, idx_b)
        remover = max(idx_a, idx_b)
        canvas.cena.elementos[manter] = unido
        canvas.cena.elementos.pop(remover)
        canvas._selecionados = {manter}
        self._registrar(canvas)
        canvas.update()
        self._status(canvas, "Moldes unidos por contorno aproximado. Revise a geometria.")
        return True

    def _controles_unidos_fallback(
        self,
        a: dict,
        b: dict,
        contorno: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        controles: list[tuple[float, float]] = []

        def adicionar(valor) -> None:
            ponto = self._ponto_controle_tuple(valor)
            if ponto is None:
                return
            if not any(self._dist_tuple(ponto, atual) <= EPS for atual in controles):
                controles.append(ponto)

        for origem in (a, b):
            for chave in ("controle_cantos", "pontos_controle_principais"):
                for item in origem.get(chave) or []:
                    adicionar(item)

        if not controles:
            for ponto in self._controles_por_quinas(contorno):
                adicionar(ponto)

        return self._ordenar_no_contorno(controles, contorno)

    def _controles_por_quinas(self, pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(pontos) <= 4:
            return pontos[:]
        saida: list[tuple[float, float]] = []
        total = len(pontos)
        for idx, atual in enumerate(pontos):
            ant = pontos[(idx - 1) % total]
            prox = pontos[(idx + 1) % total]
            v1 = (atual[0] - ant[0], atual[1] - ant[1])
            v2 = (prox[0] - atual[0], prox[1] - atual[1])
            n1 = hypot(v1[0], v1[1])
            n2 = hypot(v2[0], v2[1])
            if n1 <= EPS or n2 <= EPS:
                continue
            cos_ang = ((v1[0] * v2[0]) + (v1[1] * v2[1])) / (n1 * n2)
            if cos_ang < 0.985:
                saida.append(atual)
        if saida:
            return self._limpar_repetidos(saida)
        passo = max(1, len(pontos) // 8)
        return [pontos[i] for i in range(0, len(pontos), passo)][:8]

    def _ordenar_no_contorno(
        self,
        pontos: list[tuple[float, float]],
        contorno: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        return sorted(pontos, key=lambda ponto: self._parametro_no_contorno(ponto, contorno))

    def _parametro_no_contorno(self, ponto: tuple[float, float], contorno: list[tuple[float, float]]) -> float:
        if len(contorno) < 2:
            return 0.0
        acumulado = 0.0
        melhor_dist = float("inf")
        melhor_param = 0.0
        pts = [*contorno, contorno[0]]
        for a, b in zip(pts, pts[1:]):
            ax, ay = float(a[0]), float(a[1])
            bx, by = float(b[0]), float(b[1])
            vx, vy = bx - ax, by - ay
            tam = hypot(vx, vy)
            if tam <= EPS:
                continue
            den = (vx * vx) + (vy * vy)
            t = max(0.0, min(1.0, (((ponto[0] - ax) * vx) + ((ponto[1] - ay) * vy)) / den))
            proj = (ax + (vx * t), ay + (vy * t))
            dist = self._dist_tuple(ponto, proj)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_param = acumulado + (tam * t)
            acumulado += tam
        return melhor_param

    def _obter_dialog(self, canvas) -> UnirDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        try:
            parent_atual = dialog.parentWidget() if dialog is not None else None
        except RuntimeError:
            dialog = None
            parent_atual = None
        if dialog is None or parent_atual is not parent:
            dialog = UnirDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        return dialog

    def _restaurar_dialog(self, canvas, dialog: UnirDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True))
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _preencher_tamanhos_dialog(self, canvas, dialog: UnirDialog) -> None:
        atual = dialog.cmb_tamanhos.currentText()
        tamanhos = []
        for idx in (self._primeiro_idx, self._segundo_idx):
            if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
                continue
            for linha in canvas.cena.elementos[idx].get("graduacao_tamanhos", []) or []:
                nome = str(linha.get("tamanho") or linha.get("nome") or "").strip() if isinstance(linha, dict) else ""
                if nome and nome not in tamanhos:
                    tamanhos.append(nome)
        dialog.cmb_tamanhos.blockSignals(True)
        dialog.cmb_tamanhos.clear()
        dialog.cmb_tamanhos.addItems(tamanhos)
        if atual in tamanhos:
            dialog.cmb_tamanhos.setCurrentText(atual)
        dialog.cmb_tamanhos.blockSignals(False)

    def _molde_em_posicao(self, canvas, pos: QPointF, ignorar: set[int] | None = None) -> int | None:
        ignorar = set(ignorar or set())
        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        for idx in candidatos:
            idx = int(idx)
            if idx not in ignorar and 0 <= idx < len(canvas.cena.elementos) and self._eh_molde(canvas.cena.elementos[idx]):
                return idx
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if idx in ignorar or not self._eh_molde(el):
                continue
            if self._ponto_em_poligono((pos.x(), pos.y()), self._pontos_base(el)):
                return idx
        return None

    @staticmethod
    def _eh_molde(el: dict) -> bool:
        return isinstance(el, dict) and el.get("tipo") == "polyline" and bool(el.get("molde")) and len(Ferramenta._pontos_base(el)) >= 3

    @staticmethod
    def _pontos_base(el: dict) -> list[tuple[float, float]]:
        pts = [(float(x), float(y)) for x, y in el.get("pontos", []) if Ferramenta._eh_ponto((x, y))]
        if len(pts) > 1 and Ferramenta._dist_tuple(pts[0], pts[-1]) <= EPS:
            pts = pts[:-1]
        return pts

    def _pontos_mais_proximos(self, a: dict, b: dict) -> tuple[QPointF | None, QPointF | None]:
        pts_a = self._pontos_base(a)
        pts_b = self._pontos_base(b)
        if not pts_a or not pts_b:
            return None, None
        ia, ib = self._indices_pontos_mais_proximos(pts_a, pts_b)
        return QPointF(*pts_a[ia]), QPointF(*pts_b[ib])

    @staticmethod
    def _indices_pontos_mais_proximos(pts_a: list[tuple[float, float]], pts_b: list[tuple[float, float]]) -> tuple[int, int]:
        melhor = (float("inf"), 0, 0)
        for ia, a in enumerate(pts_a):
            for ib, b in enumerate(pts_b):
                dist = Ferramenta._dist_tuple(a, b)
                if dist < melhor[0]:
                    melhor = (dist, ia, ib)
        return melhor[1], melhor[2]

    @staticmethod
    def _limpar_repetidos(pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []
        for p in pontos:
            if not saida or Ferramenta._dist_tuple(saida[-1], p) > EPS:
                saida.append((float(p[0]), float(p[1])))
        if len(saida) > 1 and Ferramenta._dist_tuple(saida[0], saida[-1]) <= EPS:
            saida.pop()
        return saida

    @staticmethod
    def _mesclar_piques(destino: dict, a: dict, b: dict) -> None:
        configs = []
        for origem in (a, b):
            configs.extend(deepcopy([cfg for cfg in origem.get("piques_config", []) or [] if isinstance(cfg, dict)]))
        if configs:
            destino["piques_config"] = configs
            destino["mostrar_piques"] = True

    @staticmethod
    def _ponto_em_poligono(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
        if len(poly) < 3:
            return False
        x, y = float(pt[0]), float(pt[1])
        dentro = False
        pts = [*poly, poly[0]]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if (y1 > y) != (y2 > y):
                xin = (x2 - x1) * (y - y1) / ((y2 - y1) or EPS) + x1
                if x < xin:
                    dentro = not dentro
        return dentro

    @staticmethod
    def _pos_cena(canvas, pos) -> QPointF:
        if hasattr(canvas, "_tela_para_cena"):
            return QPointF(canvas._tela_para_cena(pos))
        if hasattr(canvas, "_ponto_com_snap"):
            return QPointF(canvas._ponto_com_snap(pos))
        return QPointF(pos)

    @staticmethod
    def _eh_ponto(p) -> bool:
        try:
            return isinstance(p, (list, tuple)) and len(p) >= 2 and isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    @staticmethod
    def _ponto_controle_tuple(valor) -> tuple[float, float] | None:
        if Ferramenta._eh_ponto(valor):
            return (float(valor[0]), float(valor[1]))
        if isinstance(valor, dict):
            try:
                return (float(valor["x"]), float(valor["y"]))
            except Exception:
                return None
        return None

    @staticmethod
    def _dist_tuple(a: tuple[float, float], b: tuple[float, float]) -> float:
        return hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))

    def _desenhar_contorno(self, canvas, painter, el: dict, cor: QColor) -> None:
        pts = [canvas._cena_para_tela(QPointF(float(x), float(y))) for x, y in el.get("pontos", []) if self._eh_ponto((x, y))]
        if len(pts) < 2:
            return
        painter.setPen(QPen(cor, 1.4, Qt.DashLine))
        for a, b in zip(pts, pts[1:]):
            painter.drawLine(a, b)

    @staticmethod
    def _registrar(canvas) -> None:
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        elif hasattr(canvas, "elementos_alterados"):
            canvas.elementos_alterados.emit()

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.setToolTip(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
