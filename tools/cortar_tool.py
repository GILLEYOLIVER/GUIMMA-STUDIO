from __future__ import annotations

from copy import deepcopy
from math import hypot, isfinite
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QLabel,
    QVBoxLayout,
)

from core.formatacao import formatar_numero, numero_decimal_ponto
from tools.costura_tool import Ferramenta as FerramentaCostura
from tools.elemento_runtime_utils import copiar_elemento_sem_runtime
from tools.inserir_pique_tool import Ferramenta as FerramentaInserirPique
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


EPS = 1e-7


class NumeroLimpoSpinBox(QDoubleSpinBox):
    def textFromValue(self, value: float) -> str:  # noqa: N802
        return formatar_numero(value, 2)

    def valueFromText(self, text: str) -> float:  # noqa: N802
        return numero_decimal_ponto(str(text or "").strip(), float(self.value()))


class CortarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:cortar"
        self.setWindowTitle("Cortar molde")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(240)
        self.setStyleSheet(
            """
            QDialog { background:#f2f2f2; color:#111111; }
            QLabel, QCheckBox { color:#111111; font-size:11px; }
            QComboBox, QDoubleSpinBox {
                background:#ffffff; color:#111111;
                border:1px solid #aeb4ba; min-height:21px;
                padding-left:3px;
            }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(5)
        form = QFormLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)

        self.cmb_contorno = QComboBox()
        self.cmb_contorno.addItems(["Automatico", "Manual"])
        self.cmb_contorno.setCurrentText("Manual")
        form.addRow("Contorno", self.cmb_contorno)
        raiz.addLayout(form)

        self.chk_manter_distancias = QCheckBox("Manter distancias")
        self.chk_manter_distancias.setChecked(False)
        raiz.addWidget(self.chk_manter_distancias)

        linha = QFrame()
        linha.setFrameShape(QFrame.HLine)
        linha.setStyleSheet("color:#aeb4ba;")
        raiz.addWidget(linha)

        form2 = QFormLayout()
        form2.setHorizontalSpacing(8)
        form2.setVerticalSpacing(4)
        self.chk_costura = QCheckBox("Costura (cm)")
        self.chk_costura.setChecked(True)
        self.sp_costura = NumeroLimpoSpinBox()
        self.sp_costura.setRange(0.0, 9999.0)
        self.sp_costura.setDecimals(2)
        self.sp_costura.setSingleStep(0.1)
        self.sp_costura.setValue(1.0)
        self.sp_costura.setButtonSymbols(QAbstractSpinBox.NoButtons)
        form2.addRow(self.chk_costura, self.sp_costura)

        self.chk_manter_base = QCheckBox("Manter base")
        self.chk_manter_base.setChecked(True)
        form2.addRow(self.chk_manter_base)

        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Linha", "Reta"])
        form2.addRow("Modo", self.cmb_modo)

        self.chk_pique = QCheckBox("Pique")
        self.chk_pique.setChecked(True)
        self.cmb_pique = QComboBox()
        self.cmb_pique.addItems(["I", "T", "V", "V1", "V2", "MX", "M+", "MX2", "M+2", "Botao"])
        self.cmb_pique.setCurrentText("T")
        form2.addRow(self.chk_pique, self.cmb_pique)
        raiz.addLayout(form2)

    def costura_cm(self) -> float:
        return float(self.sp_costura.value()) if self.chk_costura.isChecked() else 0.0


class Ferramenta(FerramentaBase):
    id_ferramenta = "cortar"
    nome = "Cortar"
    usa_painel_auxiliar = False
    descricao_painel = "Corta moldes por uma linha de corte, preservando base, controles, piques e graduacao."

    _dialog_por_canvas: dict[int, CortarDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._linha_idx: int | None = None
        self._hover_linha: tuple[int, int, QPointF] | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._limpar_estado()
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Cortar: clique no molde, clique na linha de corte e clique novamente para cortar.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._limpar_estado()
        if canvas is not None and hasattr(canvas, "update"):
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._pos_cena(canvas, event.position())
        self._hover_linha = self._linha_proxima(canvas, pos)
        if hasattr(canvas, "update"):
            canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._molde_idx is not None or self._linha_idx is not None:
                self._limpar_estado()
                self._status(canvas, "Corte cancelado. Clique no molde para recomecar.")
                canvas.update()
                event.accept()
                return True
            if hasattr(canvas, "set_ferramenta_ativa"):
                canvas.set_ferramenta_ativa("selecionar")
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = self._pos_cena(canvas, event.position())
        if self._molde_idx is None:
            idx = self._molde_em_posicao(canvas, pos)
            if idx is None:
                self._status(canvas, "Cortar: clique em um molde fechado.")
                event.accept()
                return True
            self._molde_idx = idx
            canvas._selecionados = {idx}
            self._status(canvas, "Molde selecionado. Clique na linha que indica onde cortar.")
            canvas.update()
            event.accept()
            return True

        if self._linha_idx is None:
            alvo_linha = self._linha_proxima(canvas, pos)
            if alvo_linha is None:
                self._status(canvas, "Cortar: clique em uma linha de corte.")
                event.accept()
                return True
            self._linha_idx = alvo_linha[0]
            canvas._selecionados = {self._molde_idx, self._linha_idx}
            self._status(canvas, "Linha selecionada. Clique novamente para confirmar o corte.")
            canvas.update()
            event.accept()
            return True

        if self._aplicar_corte_linha(canvas, self._molde_idx, self._linha_idx):
            self._limpar_estado()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        painter.save()
        try:
            if self._molde_idx is not None and 0 <= self._molde_idx < len(canvas.cena.elementos):
                self._desenhar_contorno_realce(canvas, painter, canvas.cena.elementos[self._molde_idx], QColor("#ffd400"))
            idx_linha = self._linha_idx
            if idx_linha is None and self._hover_linha is not None:
                idx_linha = self._hover_linha[0]
            if idx_linha is not None and 0 <= idx_linha < len(canvas.cena.elementos):
                self._desenhar_linha_realce(canvas, painter, canvas.cena.elementos[idx_linha], QColor("#ff00ff"))
        finally:
            painter.restore()

    def _aplicar_corte_linha(self, canvas, molde_idx: int, linha_idx: int) -> bool:
        if not (0 <= molde_idx < len(canvas.cena.elementos)) or not (0 <= linha_idx < len(canvas.cena.elementos)):
            return False
        molde = canvas.cena.elementos[molde_idx]
        linha = canvas.cena.elementos[linha_idx]
        p0, p1 = self._linha_corte(linha)
        if p0 is None or p1 is None:
            self._status(canvas, "Cortar: linha de corte invalida.")
            return False

        dialog = self._obter_dialog(canvas)
        modo = str(dialog.cmb_modo.currentText() or "Linha")
        if modo == "Reta":
            resultado = self._dividir_molde_por_linha(molde, p0, p1)
        else:
            resultado = self._dividir_molde_por_caminho(molde, linha)
        if resultado is None:
            self._status(canvas, "Cortar: a linha precisa atravessar o molde em dois pontos.")
            return False

        lado_a, lado_b = resultado
        corte_id = str(uuid4())
        original = copiar_elemento_sem_runtime(molde)
        novo_a = self._criar_molde_cortado(original, lado_a, "A", corte_id, dialog)
        novo_b = self._criar_molde_cortado(original, lado_b, "B", corte_id, dialog)
        if novo_a is None or novo_b is None:
            self._status(canvas, "Cortar: geometria resultante invalida.")
            return False

        canvas.cena.elementos[molde_idx] = novo_a
        canvas.cena.elementos.insert(molde_idx + 1, novo_b)
        canvas.cena.elementos.extend(self._costuras_corte(canvas, [novo_a, novo_b], dialog.costura_cm()))
        canvas._selecionados = {molde_idx, molde_idx + 1}
        self._registrar(canvas)
        canvas.update()
        self._status(canvas, "Molde cortado em duas partes com graduacao e controles preservados.")
        return True

    def _dividir_molde_por_linha(self, molde: dict, a: QPointF, b: QPointF) -> tuple[list[dict], list[dict]] | None:
        pontos = self._pontos_base(molde)
        if len(pontos) < 3:
            return None
        poligono = [
            {"ponto": ponto, "tag": {"tipo": "vertice", "idx": idx}}
            for idx, ponto in enumerate(pontos)
        ]
        lado_pos = self._clip_halfplane(poligono, a, b, 1.0)
        lado_neg = self._clip_halfplane(poligono, a, b, -1.0)
        lado_pos = self._normalizar_poligono(lado_pos)
        lado_neg = self._normalizar_poligono(lado_neg)
        if len(lado_pos) < 3 or len(lado_neg) < 3:
            return None
        if abs(self._area(lado_pos)) <= EPS or abs(self._area(lado_neg)) <= EPS:
            return None
        return lado_pos, lado_neg

    def _dividir_molde_por_caminho(self, molde: dict, linha: dict) -> tuple[list[dict], list[dict]] | None:
        base = self._pontos_base(molde)
        caminho = self._pontos_linha(linha)
        if len(base) < 3 or len(caminho) < 2:
            return None

        intersecoes = self._intersecoes_caminho_poligono(caminho, base)
        if len(intersecoes) < 2:
            return None
        entrada = intersecoes[0]
        saida = intersecoes[-1]
        if self._dist_tuple(entrada["ponto"], saida["ponto"]) <= EPS:
            return None

        corte_ab = self._caminho_entre_intersecoes(caminho, entrada, saida, molde)
        if len(corte_ab) < 2:
            return None
        corte_ba = [deepcopy(item) for item in reversed(corte_ab)]
        borda_ab = self._caminho_borda(base, entrada, saida)
        borda_ba = self._caminho_borda(base, saida, entrada)

        lado_a = self._normalizar_poligono([*borda_ab, *corte_ba[1:-1]])
        lado_b = self._normalizar_poligono([*borda_ba, *corte_ab[1:-1]])
        if len(lado_a) < 3 or len(lado_b) < 3:
            return None
        if abs(self._area(lado_a)) <= EPS or abs(self._area(lado_b)) <= EPS:
            return None
        return lado_a, lado_b

    def _intersecoes_caminho_poligono(
        self,
        caminho: list[tuple[float, float]],
        poligono: list[tuple[float, float]],
    ) -> list[dict]:
        intersecoes: list[dict] = []
        total = len(poligono)
        for caminho_idx, (a, b) in enumerate(zip(caminho, caminho[1:])):
            for edge_idx in range(total):
                c = poligono[edge_idx]
                d = poligono[(edge_idx + 1) % total]
                inter = self._intersecao_segmentos(a, b, c, d)
                if inter is None:
                    continue
                ponto, t_caminho, t_aresta = inter
                if any(self._dist_tuple(ponto, item["ponto"]) <= EPS for item in intersecoes):
                    continue
                tag = {"tipo": "intersec", "edge": int(edge_idx), "t": float(t_aresta)}
                intersecoes.append(
                    {
                        "ponto": ponto,
                        "tag": tag,
                        "caminho_idx": int(caminho_idx),
                        "t_caminho": float(t_caminho),
                        "param": float(caminho_idx) + float(t_caminho),
                    }
                )
        intersecoes.sort(key=lambda item: float(item["param"]))
        return intersecoes

    def _caminho_entre_intersecoes(
        self,
        caminho: list[tuple[float, float]],
        entrada: dict,
        saida: dict,
        molde: dict,
    ) -> list[dict]:
        p0 = entrada["ponto"]
        p1 = saida["ponto"]
        param0 = float(entrada["param"])
        param1 = float(saida["param"])
        tag0 = deepcopy(entrada["tag"])
        tag1 = deepcopy(saida["tag"])
        valores0 = self._valores_graduacao_tag(molde, tag0)
        valores1 = self._valores_graduacao_tag(molde, tag1)
        itens: list[dict] = [{"ponto": p0, "tag": tag0}]
        for idx in range(int(entrada["caminho_idx"]) + 1, int(saida["caminho_idx"]) + 1):
            if not (0 <= idx < len(caminho)):
                continue
            param = float(idx)
            if not (param0 + EPS < param < param1 - EPS):
                continue
            ponto = caminho[idx]
            u = (param - param0) / max(EPS, param1 - param0)
            itens.append(
                {
                    "ponto": ponto,
                    "tag": {
                        "tipo": "corte_linha",
                        "u": float(u),
                        "valores": self._interpolar_valores({"valores": valores0}, {"valores": valores1}, u),
                    },
                }
            )
        itens.append({"ponto": p1, "tag": tag1})
        return itens

    def _caminho_borda(self, poligono: list[tuple[float, float]], inicio: dict, fim: dict) -> list[dict]:
        total = len(poligono)
        edge_inicio = int((inicio.get("tag") or {}).get("edge", 0)) % total
        edge_fim = int((fim.get("tag") or {}).get("edge", 0)) % total
        itens: list[dict] = [{"ponto": inicio["ponto"], "tag": deepcopy(inicio["tag"])}]
        idx = (edge_inicio + 1) % total
        limite = (edge_fim + 1) % total
        guard = 0
        while idx != limite and guard <= total:
            itens.append({"ponto": poligono[idx], "tag": {"tipo": "vertice", "idx": int(idx)}})
            idx = (idx + 1) % total
            guard += 1
        itens.append({"ponto": fim["ponto"], "tag": deepcopy(fim["tag"])})
        return itens

    def _clip_halfplane(self, poligono: list[dict], a: QPointF, b: QPointF, lado: float) -> list[dict]:
        if not poligono:
            return []
        saida: list[dict] = []
        total = len(poligono)
        for i in range(total):
            atual = poligono[i]
            prox = poligono[(i + 1) % total]
            pa = atual["ponto"]
            pb = prox["ponto"]
            da = lado * self._lado_linha(a, b, pa)
            db = lado * self._lado_linha(a, b, pb)
            dentro_a = da >= -EPS
            dentro_b = db >= -EPS
            if dentro_a and dentro_b:
                saida.append(deepcopy(prox))
            elif dentro_a and not dentro_b:
                inter = self._intersecao_aresta_linha(pa, pb, a, b, i)
                if inter is not None:
                    saida.append(inter)
            elif not dentro_a and dentro_b:
                inter = self._intersecao_aresta_linha(pa, pb, a, b, i)
                if inter is not None:
                    saida.append(inter)
                saida.append(deepcopy(prox))
        return saida

    def _criar_molde_cortado(self, original: dict, itens: list[dict], sufixo: str, corte_id: str, dialog: CortarDialog) -> dict | None:
        itens = self._normalizar_poligono(itens)
        if len(itens) < 3:
            return None
        pontos_abertos = [(float(item["ponto"].x()), float(item["ponto"].y())) for item in itens]
        pontos = [*pontos_abertos, pontos_abertos[0]]
        novo = deepcopy(original)
        novo["id"] = str(uuid4())
        novo["molde_id"] = str(uuid4())
        novo["pontos"] = pontos
        novo["fechado"] = True
        novo["molde"] = True
        nome = str(original.get("nome_molde") or "Molde").strip() or "Molde"
        novo["nome_molde"] = f"{nome} {sufixo}"
        controles = self._controles_cortados(original, itens, pontos_abertos)
        novo["controle_cantos"] = controles
        novo["controle_auxiliares"] = []
        novo["pontos_controle_principais"] = [{"x": x, "y": y} for x, y in controles]
        novo["pontos_auxiliares"] = []
        novo["mostrar_controles"] = True
        self._aplicar_graduacao_cortada(novo, original, itens)
        self._filtrar_piques(novo, original, pontos_abertos)
        if dialog.chk_pique.isChecked():
            self._adicionar_piques_corte(novo, itens, dialog.cmb_pique.currentText())
        self._aplicar_costura_corte(novo, itens, dialog.costura_cm())
        metadados = novo.setdefault("metadados", {})
        metadados["origem_corte"] = "cortar_molde"
        metadados["corte_id"] = corte_id
        metadados["lado_corte"] = sufixo
        metadados["molde_original_antes_corte"] = deepcopy(original)
        metadados["manter_distancias_corte"] = bool(dialog.chk_manter_distancias.isChecked())
        metadados["manter_base_corte"] = bool(dialog.chk_manter_base.isChecked())
        metadados["modo_corte"] = dialog.cmb_modo.currentText()
        metadados["costura_corte_cm"] = dialog.costura_cm()
        return novo

    def _aplicar_costura_corte(self, novo: dict, itens: list[dict], margem_cm: float) -> None:
        margem = max(0.0, float(margem_cm or 0.0))
        metadados = novo.setdefault("metadados", {})
        for chave in ("margens_molde", "margens", "margem_cm_por_elemento"):
            novo.pop(chave, None)
        novo.pop("mostrar_margem", None)
        if margem <= EPS:
            metadados.pop("costura_corte_segmentos", None)
            return

        segmentos = self._segmentos_linha_corte(itens)
        if not segmentos:
            metadados.pop("costura_corte_segmentos", None)
            return

        metadados["costura_corte_segmentos"] = [int(seg_idx) for seg_idx in segmentos]

    def _costuras_corte(self, canvas, moldes: list[dict], margem_cm: float) -> list[dict]:
        margem = max(0.0, float(margem_cm or 0.0))
        if margem <= EPS:
            return []
        helper = FerramentaCostura()
        helper._margem_cm = margem
        helper._larguras_atuais = lambda _canvas: (margem, margem, False)  # type: ignore[method-assign]
        helper._acabamentos_atuais = lambda _canvas: ("Canto reto", "Canto reto")  # type: ignore[method-assign]
        saida: list[dict] = []
        for molde in moldes:
            metadados = molde.get("metadados") if isinstance(molde.get("metadados"), dict) else {}
            segmentos = {int(item) for item in metadados.get("costura_corte_segmentos", []) or []}
            segmentos = {idx for idx in segmentos if idx >= 0}
            if not segmentos:
                continue
            pontos = helper._pontos_fechados(molde)
            if len(pontos) < 4:
                continue
            base_interativa = helper._base_interativa_elemento(molde)
            ordem = helper._ordenar_segmentos_contiguos(base_interativa, segmentos) or sorted(segmentos)
            costura = helper._gerar_costura_segmentos_atual(canvas, pontos, segmentos, ordem, None)
            if len(costura) < 2:
                continue
            molde_id = str(molde.get("molde_id") or molde.get("id") or "")
            if not molde_id:
                molde_id = str(uuid4())
                molde["molde_id"] = molde_id
            el = helper._elemento_costura(canvas, costura, molde, molde_id)
            el["costura_segmentos"] = [int(s) for s in ordem]
            el["costura_parcial"] = True
            el.setdefault("metadados", {})["origem_corte"] = "cortar_molde"
            el["metadados"]["costura_segmentos"] = [int(s) for s in ordem]
            el["metadados"]["costura_parcial"] = True
            saida.append(el)
        return saida

    def _segmentos_linha_corte(self, itens: list[dict]) -> list[int]:
        segmentos: list[int] = []
        total = len(itens)
        if total < 2:
            return segmentos
        for idx, atual in enumerate(itens):
            prox = itens[(idx + 1) % total]
            tag_a = atual.get("tag") or {}
            tag_b = prox.get("tag") or {}
            if tag_a.get("tipo") != "intersec" or tag_b.get("tipo") != "intersec":
                tipos_corte = {"intersec", "corte_linha"}
                if tag_a.get("tipo") not in tipos_corte or tag_b.get("tipo") not in tipos_corte:
                    continue
            pa = atual["ponto"]
            pb = prox["ponto"]
            ponto_a = (float(pa.x()), float(pa.y()))
            ponto_b = (float(pb.x()), float(pb.y()))
            if self._dist_tuple(ponto_a, ponto_b) > EPS:
                segmentos.append(int(idx))
        return segmentos

    def _controles_cortados(
        self,
        original: dict,
        itens: list[dict],
        pontos_abertos: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        controles: list[tuple[float, float]] = []

        def adicionar(ponto: tuple[float, float]) -> None:
            pt = (float(ponto[0]), float(ponto[1]))
            if not any(self._dist_tuple(pt, atual) <= EPS for atual in controles):
                controles.append(pt)

        for ponto in self._controles_originais(original):
            if self._ponto_em_poligono(ponto, pontos_abertos):
                adicionar(ponto)

        for item in itens:
            tag = item.get("tag") or {}
            if tag.get("tipo") == "intersec":
                p = item["ponto"]
                adicionar((float(p.x()), float(p.y())))

        if not controles:
            for ponto in self._controles_por_quinas(pontos_abertos):
                adicionar(ponto)

        return self._ordenar_no_contorno(controles, pontos_abertos)

    def _controles_originais(self, original: dict) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []

        def adicionar(valor) -> None:
            ponto = self._ponto_controle_tuple(valor)
            if ponto is None:
                return
            if not any(self._dist_tuple(ponto, atual) <= EPS for atual in saida):
                saida.append(ponto)

        for chave in ("controle_cantos", "pontos_controle_principais"):
            for item in original.get(chave) or []:
                adicionar(item)
        return saida

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
        return sorted(
            self._limpar_repetidos(pontos),
            key=lambda ponto: self._parametro_no_contorno(ponto, contorno),
        )

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

    def _aplicar_graduacao_cortada(self, novo: dict, original: dict, itens: list[dict]) -> None:
        tabela = original.get("graduacao_tabela") if isinstance(original.get("graduacao_tabela"), dict) else None
        pontos_cfg = tabela.get("pontos") if isinstance(tabela, dict) and isinstance(tabela.get("pontos"), dict) else None
        if not pontos_cfg:
            return
        cfg_novo: dict[str, dict] = {}
        for idx, item in enumerate(itens):
            ponto = item["ponto"]
            cfg_novo[str(idx)] = {
                "indice": idx,
                "numero": idx + 1,
                "ponto": (float(ponto.x()), float(ponto.y())),
                "valores": self._valores_graduacao_tag(original, item.get("tag") or {}),
            }
        nova_tabela = deepcopy(tabela)
        nova_tabela["modo"] = "dx_dy"
        nova_tabela["pontos"] = cfg_novo
        novo["graduacao_tabela"] = nova_tabela
        novo["graduacao_pontos"] = deepcopy(cfg_novo)
        novo["graduacao_tabela_apenas_pontos_principais"] = True
        novo["graduacao_preferir_tabela_dxdy"] = True
        novo["graduacao_renderizar_por_tabela_derivada"] = False

    def _valores_graduacao_tag(self, original: dict, tag: dict) -> dict:
        pontos_cfg = ((original.get("graduacao_tabela") or {}).get("pontos") or {}) if isinstance(original.get("graduacao_tabela"), dict) else {}
        base = self._pontos_base(original)
        total = len(base)
        if total <= 0:
            return {}
        if tag.get("tipo") == "intersec":
            i = int(tag.get("edge", 0)) % total
            j = (i + 1) % total
            t = max(0.0, min(1.0, float(tag.get("t", 0.0))))
            return self._interpolar_valores(pontos_cfg.get(str(i), {}), pontos_cfg.get(str(j), {}), t)
        if tag.get("tipo") == "corte_linha" and isinstance(tag.get("valores"), dict):
            return deepcopy(tag.get("valores") or {})
        idx = int(tag.get("idx", 0)) % total
        cfg = pontos_cfg.get(str(idx), {})
        valores = cfg.get("valores") if isinstance(cfg, dict) and isinstance(cfg.get("valores"), dict) else {}
        return deepcopy(valores)

    @staticmethod
    def _interpolar_valores(cfg_a: dict, cfg_b: dict, t: float) -> dict:
        valores_a = cfg_a.get("valores") if isinstance(cfg_a, dict) and isinstance(cfg_a.get("valores"), dict) else {}
        valores_b = cfg_b.get("valores") if isinstance(cfg_b, dict) and isinstance(cfg_b.get("valores"), dict) else {}
        saida = {}
        for tamanho in sorted(set(valores_a) | set(valores_b)):
            va = valores_a.get(tamanho) if isinstance(valores_a.get(tamanho), dict) else {}
            vb = valores_b.get(tamanho) if isinstance(valores_b.get(tamanho), dict) else {}
            ax, ay = float(va.get("dx", 0.0) or 0.0), float(va.get("dy", 0.0) or 0.0)
            bx, by = float(vb.get("dx", 0.0) or 0.0), float(vb.get("dy", 0.0) or 0.0)
            saida[tamanho] = {"dx": ax + ((bx - ax) * t), "dy": ay + ((by - ay) * t)}
        return saida

    def _filtrar_piques(self, novo: dict, original: dict, pontos: list[tuple[float, float]]) -> None:
        if not isinstance(original.get("piques_config"), list):
            return
        filtrados = []
        for cfg in original.get("piques_config") or []:
            if not isinstance(cfg, dict):
                continue
            ponto = self._ponto_cfg_pique(cfg)
            if ponto is None or self._ponto_em_poligono((ponto.x(), ponto.y()), pontos):
                filtrados.append(deepcopy(cfg))
        novo["piques_config"] = filtrados
        novo["mostrar_piques"] = bool(filtrados)

    def _adicionar_piques_corte(self, novo: dict, itens: list[dict], tipo: str) -> None:
        pontos = []
        for item in itens:
            tag = item.get("tag") or {}
            if tag.get("tipo") == "intersec":
                p = item["ponto"]
                pontos.append((float(p.x()), float(p.y())))
        unicos: list[tuple[float, float]] = []
        for p in pontos:
            if not any(self._dist_tuple(p, q) <= EPS for q in unicos):
                unicos.append(p)
        if not unicos:
            return
        configs = [cfg for cfg in (novo.get("piques_config") or []) if isinstance(cfg, dict)]
        controles = [pt for pt in (novo.get("pontos_controle_pique") or []) if self._eh_ponto(pt)]
        principais = [pt for pt in (novo.get("pontos_controle_principais") or []) if isinstance(pt, dict)]
        cantos = [pt for pt in (novo.get("controle_cantos") or []) if self._eh_ponto(pt)]
        helper = FerramentaInserirPique()
        tipo_cfg = self._tipo_pique_completo(tipo)
        for x, y in unicos:
            ponto_qt = QPointF(float(x), float(y))
            info_segmento = helper._segmento_mais_proximo_elemento(novo, ponto_qt)
            segmento = (info_segmento[1], info_segmento[2]) if info_segmento is not None else None
            segmentos_pique = helper._segmentos_pique(
                novo,
                ponto_qt,
                segmento,
                tipo_cfg,
                0.3,
                0.3,
                0.0,
                sobre_contorno=True,
            )
            cfg = {
                "tipo": tipo_cfg,
                "ponto": (x, y),
                "ponto_controle": (x, y),
                "largura_cm": 0.3,
                "altura_cm": 0.3,
                "angulo": 0.0,
                "referencia": "Segmento mais proximo",
                "sobre_contorno": True,
                "adicionar_ponto_controle": True,
                "manter_distancia_tamanhos": False,
                "dx_cm": 0.0,
                "dy_cm": 0.0,
                "pique_na_costura": "Estendido",
                "segmentos": segmentos_pique,
            }
            configs.append(cfg)
            if not any(self._dist_tuple((x, y), pt) <= EPS for pt in controles):
                controles.append((x, y))
            if not any(self._dist_tuple((x, y), pt) <= EPS for pt in cantos):
                cantos.append((x, y))
            if not any(self._ponto_controle_tuple(pt) is not None and self._dist_tuple((x, y), self._ponto_controle_tuple(pt)) <= EPS for pt in principais):
                principais.append({"x": x, "y": y, "origem": "pique", "divide_costura": False})
        novo["piques_config"] = configs
        novo["pontos_controle_pique"] = controles
        novo["controle_cantos"] = self._ordenar_no_contorno(cantos, self._pontos_base(novo))
        novo["pontos_controle_principais"] = principais
        novo["mostrar_piques"] = True

    @staticmethod
    def _tipo_pique_completo(tipo: str) -> str:
        codigo = str(tipo or "T").split(" - ", 1)[0].strip()
        mapa = {
            "I": "I - forma I",
            "T": "T - forma T",
            "V": "V - forma V",
            "V1": "V1 - forma V direito",
            "V2": "V2 - forma V esquerdo",
            "MX": "MX - marca X",
            "M+": "M+ - marca +",
            "MX2": "MX2 - marca X2",
            "M+2": "M+2 - marca +2",
            "Botao": "Botao - forma de botao",
        }
        return mapa.get(codigo, "T - forma T")

    def _obter_dialog(self, canvas) -> CortarDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        try:
            parent_atual = dialog.parentWidget() if dialog is not None else None
        except RuntimeError:
            dialog = None
            parent_atual = None
        if dialog is None or parent_atual is not parent:
            dialog = CortarDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        return dialog

    def _restaurar_dialog(self, canvas, dialog: CortarDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True))
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        for idx in candidatos:
            if self._eh_molde_fechado(canvas.cena.elementos[int(idx)]):
                return int(idx)
        for idx in sorted(getattr(canvas, "_selecionados", set()) or []):
            if 0 <= int(idx) < len(canvas.cena.elementos) and self._eh_molde_fechado(canvas.cena.elementos[int(idx)]):
                return int(idx)
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if self._eh_molde_fechado(el) and self._ponto_em_poligono((pos.x(), pos.y()), self._pontos_base(el)):
                return idx
        return None

    def _linha_proxima(self, canvas, pos: QPointF) -> tuple[int, int, QPointF] | None:
        tolerancia = 10.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor = None
        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        candidatos = list(dict.fromkeys([*candidatos, *range(len(canvas.cena.elementos))]))
        for idx in candidatos:
            idx = int(idx)
            if idx == self._molde_idx or not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline" or el.get("molde"):
                continue
            pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", []) if self._eh_ponto((x, y))]
            for seg_idx, (a, b) in enumerate(zip(pts, pts[1:])):
                proj, dist = self._projetar_ponto_segmento(a, b, pos)
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, seg_idx, proj)
        if melhor is None:
            return None
        return melhor[1], melhor[2], melhor[3]

    @staticmethod
    def _linha_corte(el: dict) -> tuple[QPointF | None, QPointF | None]:
        pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", []) if Ferramenta._eh_ponto((x, y))]
        if len(pts) < 2:
            return None, None
        inicio = pts[0]
        fim = next((p for p in reversed(pts) if Ferramenta._dist_qp(inicio, p) > EPS), None)
        return (inicio, fim) if fim is not None else (None, None)

    @staticmethod
    def _pontos_linha(el: dict) -> list[tuple[float, float]]:
        pontos: list[tuple[float, float]] = []
        for item in el.get("pontos", []) or []:
            if not Ferramenta._eh_ponto(item):
                continue
            ponto = (float(item[0]), float(item[1]))
            if pontos and Ferramenta._dist_tuple(pontos[-1], ponto) <= EPS:
                continue
            pontos.append(ponto)
        return pontos

    @staticmethod
    def _pontos_base(el: dict) -> list[tuple[float, float]]:
        pts = [(float(x), float(y)) for x, y in el.get("pontos", []) if Ferramenta._eh_ponto((x, y))]
        if len(pts) > 1 and Ferramenta._dist_tuple(pts[0], pts[-1]) <= EPS:
            pts = pts[:-1]
        return pts

    @staticmethod
    def _eh_molde_fechado(el: dict) -> bool:
        return isinstance(el, dict) and el.get("tipo") == "polyline" and bool(el.get("molde")) and len(Ferramenta._pontos_base(el)) >= 3

    @staticmethod
    def _pos_cena(canvas, pos) -> QPointF:
        if hasattr(canvas, "_tela_para_cena"):
            return QPointF(canvas._tela_para_cena(pos))
        if hasattr(canvas, "_ponto_com_snap"):
            return QPointF(canvas._ponto_com_snap(pos))
        return QPointF(pos)

    @staticmethod
    def _lado_linha(a: QPointF, b: QPointF, p: tuple[float, float] | QPointF) -> float:
        px, py = (p.x(), p.y()) if isinstance(p, QPointF) else (float(p[0]), float(p[1]))
        return (b.x() - a.x()) * (py - a.y()) - (b.y() - a.y()) * (px - a.x())

    @staticmethod
    def _intersecao_aresta_linha(pa: tuple[float, float], pb: tuple[float, float], a: QPointF, b: QPointF, edge_idx: int) -> dict | None:
        ax, ay = float(pa[0]), float(pa[1])
        bx, by = float(pb[0]), float(pb[1])
        rx, ry = bx - ax, by - ay
        sx, sy = b.x() - a.x(), b.y() - a.y()
        den = (rx * sy) - (ry * sx)
        if abs(den) <= EPS:
            return None
        qpx, qpy = a.x() - ax, a.y() - ay
        t = ((qpx * sy) - (qpy * sx)) / den
        t = max(0.0, min(1.0, t))
        return {"ponto": (ax + (rx * t), ay + (ry * t)), "tag": {"tipo": "intersec", "edge": int(edge_idx), "t": float(t)}}

    @staticmethod
    def _intersecao_segmentos(
        a: tuple[float, float],
        b: tuple[float, float],
        c: tuple[float, float],
        d: tuple[float, float],
    ) -> tuple[tuple[float, float], float, float] | None:
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        cx, cy = float(c[0]), float(c[1])
        dx, dy = float(d[0]), float(d[1])
        rx, ry = bx - ax, by - ay
        sx, sy = dx - cx, dy - cy
        den = (rx * sy) - (ry * sx)
        if abs(den) <= EPS:
            return None
        qpx, qpy = cx - ax, cy - ay
        t = ((qpx * sy) - (qpy * sx)) / den
        u = ((qpx * ry) - (qpy * rx)) / den
        if t < -EPS or t > 1.0 + EPS or u < -EPS or u > 1.0 + EPS:
            return None
        t = max(0.0, min(1.0, t))
        u = max(0.0, min(1.0, u))
        return (ax + (rx * t), ay + (ry * t)), t, u

    @staticmethod
    def _normalizar_poligono(itens: list[dict]) -> list[dict]:
        saida: list[dict] = []
        for item in itens:
            p = item["ponto"]
            ponto = QPointF(float(p[0]), float(p[1])) if not isinstance(p, QPointF) else QPointF(p)
            if saida and Ferramenta._dist_qp(saida[-1]["ponto"], ponto) <= EPS:
                continue
            novo = deepcopy(item)
            novo["ponto"] = ponto
            saida.append(novo)
        if len(saida) > 1 and Ferramenta._dist_qp(saida[0]["ponto"], saida[-1]["ponto"]) <= EPS:
            saida.pop()
        return saida

    @staticmethod
    def _area(itens: list[dict]) -> float:
        pts = [item["ponto"] for item in itens]
        return sum(a.x() * b.y() - b.x() * a.y() for a, b in zip(pts, [*pts[1:], pts[0]])) / 2.0 if len(pts) >= 3 else 0.0

    @staticmethod
    def _projetar_ponto_segmento(a: QPointF, b: QPointF, p: QPointF) -> tuple[QPointF, float]:
        abx, aby = b.x() - a.x(), b.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= EPS:
            proj = QPointF(a)
        else:
            t = max(0.0, min(1.0, (((p.x() - a.x()) * abx) + ((p.y() - a.y()) * aby)) / den))
            proj = QPointF(a.x() + abx * t, a.y() + aby * t)
        return proj, hypot(proj.x() - p.x(), proj.y() - p.y())

    @staticmethod
    def _limpar_repetidos(pontos: list[tuple[float, float]]) -> list[tuple[float, float]]:
        saida: list[tuple[float, float]] = []
        for ponto in pontos:
            if not Ferramenta._eh_ponto(ponto):
                continue
            pt = (float(ponto[0]), float(ponto[1]))
            if not any(Ferramenta._dist_tuple(pt, existente) <= EPS for existente in saida):
                saida.append(pt)
        return saida

    @staticmethod
    def _ponto_em_poligono(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
        if len(poly) < 3:
            return False
        x, y = float(pt[0]), float(pt[1])
        dentro = False
        pts = [*poly, poly[0]]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if Ferramenta._distancia_ponto_segmento(pt, (x1, y1), (x2, y2)) <= EPS:
                return True
            if (y1 > y) != (y2 > y):
                xin = (x2 - x1) * (y - y1) / ((y2 - y1) or EPS) + x1
                if x < xin:
                    dentro = not dentro
        return dentro

    @staticmethod
    def _distancia_ponto_segmento(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        px, py = float(p[0]), float(p[1])
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        vx, vy = bx - ax, by - ay
        den = vx * vx + vy * vy
        if den <= EPS:
            return hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, (((px - ax) * vx) + ((py - ay) * vy)) / den))
        return hypot(px - (ax + vx * t), py - (ay + vy * t))

    @staticmethod
    def _ponto_cfg_pique(cfg: dict) -> QPointF | None:
        for chave in ("ponto", "ponto_controle", "pos"):
            valor = cfg.get(chave)
            if Ferramenta._eh_ponto(valor):
                return QPointF(float(valor[0]), float(valor[1]))
        return None

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
    def _eh_ponto(p) -> bool:
        try:
            return isinstance(p, (list, tuple)) and len(p) >= 2 and isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    @staticmethod
    def _dist_tuple(a: tuple[float, float], b: tuple[float, float]) -> float:
        return hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))

    @staticmethod
    def _dist_qp(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    def _desenhar_contorno_realce(self, canvas, painter, el: dict, cor: QColor) -> None:
        pts = [canvas._cena_para_tela(QPointF(float(x), float(y))) for x, y in el.get("pontos", []) if self._eh_ponto((x, y))]
        if len(pts) < 2:
            return
        painter.setPen(QPen(cor, 1.4, Qt.DashLine))
        for a, b in zip(pts, pts[1:]):
            painter.drawLine(a, b)

    def _desenhar_linha_realce(self, canvas, painter, el: dict, cor: QColor) -> None:
        p0, p1 = self._linha_corte(el)
        if p0 is None or p1 is None:
            return
        painter.setPen(QPen(cor, 2.0))
        painter.drawLine(canvas._cena_para_tela(p0), canvas._cena_para_tela(p1))

    def _limpar_estado(self) -> None:
        self._molde_idx = None
        self._linha_idx = None
        self._hover_linha = None

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
