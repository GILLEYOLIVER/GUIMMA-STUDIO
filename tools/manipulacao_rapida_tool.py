from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, radians, sin, sqrt
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from tools.movimento_utils import mover_elemento_por_delta
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


LISTAS_PONTOS = (
    "pontos",
    "controle_cantos",
    "controle_auxiliares",
    "marcacoes_no_perimetro",
    "distancias_no_perimetro",
    "marcacoes_perimetro",
    "pontos_principais",
    "pontos_controle_curva",
    "pontos_controle_principais",
    "pontos_controle",
    "controle_pontos",
    "pontos_auxiliares",
)

PONTOS_SOLTOS = (
    "p0",
    "p1",
    "p2",
    "pos",
    "ponto_texto",
    "ponto_texto_nome",
    "ponto_texto_descricao",
    "ponto_texto_observacoes",
    "nome_posicao",
    "nome_centro",
    "fio_origem",
    "fio_fim",
    "seta_origem",
    "seta_fim",
)


class ManipulacaoRapidaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:manipulacao_rapida"
        self.setWindowTitle("Manipulação rápida")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setMinimumWidth(360)
        self.setStyleSheet(
            """
            QDialog { background:#f2f2f2; color:#111111; }
            QLabel, QCheckBox, QGroupBox { color:#111111; font-size:12px; }
            QGroupBox { border:1px solid #d2d2d2; margin-top:8px; padding-top:8px; }
            QGroupBox::title { subcontrol-origin: margin; left:8px; padding:0 4px; }
            QLineEdit { background:#ffffff; color:#111111; border:1px solid #b8b8b8; min-height:22px; padding-left:4px; }
            QPushButton { background:#fbfbfb; color:#111111; border:1px solid #b9c0c7; min-height:26px; padding:3px 8px; }
            QPushButton:hover { background:#e7f2ff; border-color:#4796d8; }
            QPushButton:pressed { background:#cfe7ff; }
            """
        )
        self._montar_ui()

    def _montar_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(6)

        dica = QLabel("Ações rápidas para organizar, corrigir e preparar elementos/moldes.")
        dica.setWordWrap(True)
        raiz.addWidget(dica)

        grupo_alvo = QGroupBox("Alvo")
        lay_alvo = QVBoxLayout(grupo_alvo)
        self.chk_aplicar_todos_se_nada = QCheckBox("Se nada estiver selecionado, aplicar em todos")
        self.chk_aplicar_todos_se_nada.setChecked(False)
        lay_alvo.addWidget(self.chk_aplicar_todos_se_nada)
        raiz.addWidget(grupo_alvo)

        grupo_param = QGroupBox("Parâmetros")
        grid = QGridLayout(grupo_param)
        grid.addWidget(QLabel("Deslocamento da cópia (cm)"), 0, 0)
        self.ed_deslocamento = QLineEdit("5")
        grid.addWidget(self.ed_deslocamento, 0, 1)
        grid.addWidget(QLabel("Fechar abertura até (cm)"), 1, 0)
        self.ed_folga = QLineEdit("0.2")
        grid.addWidget(self.ed_folga, 1, 1)
        grid.addWidget(QLabel("Girar seleção (graus)"), 2, 0)
        self.ed_angulo = QLineEdit("90")
        grid.addWidget(self.ed_angulo, 2, 1)
        raiz.addWidget(grupo_param)

        grupo_selecao = QGroupBox("Seleção")
        grid_sel = QGridLayout(grupo_selecao)
        self.btn_sel_tudo = QPushButton("Selecionar tudo")
        self.btn_sel_moldes = QPushButton("Selecionar moldes")
        self.btn_sel_curvas = QPushButton("Selecionar curvas")
        self.btn_limpar = QPushButton("Limpar seleção")
        grid_sel.addWidget(self.btn_sel_tudo, 0, 0)
        grid_sel.addWidget(self.btn_sel_moldes, 0, 1)
        grid_sel.addWidget(self.btn_sel_curvas, 1, 0)
        grid_sel.addWidget(self.btn_limpar, 1, 1)
        raiz.addWidget(grupo_selecao)

        grupo_acoes = QGroupBox("Ações rápidas")
        grid_acoes = QGridLayout(grupo_acoes)
        self.btn_centralizar = QPushButton("Centralizar nome/fio")
        self.btn_curvas = QPushButton("Preparar curvas editáveis")
        self.btn_limpar_pontos = QPushButton("Limpar pontos duplicados")
        self.btn_fechar = QPushButton("Fechar pequenas aberturas")
        self.btn_duplicar = QPushButton("Duplicar + deslocar")
        self.btn_espelhar_h = QPushButton("Espelhar H")
        self.btn_espelhar_v = QPushButton("Espelhar V")
        self.btn_girar = QPushButton("Girar")
        self.btn_frente = QPushButton("Trazer para frente")
        self.btn_tras = QPushButton("Enviar para trás")
        botoes = [
            self.btn_centralizar,
            self.btn_curvas,
            self.btn_limpar_pontos,
            self.btn_fechar,
            self.btn_duplicar,
            self.btn_espelhar_h,
            self.btn_espelhar_v,
            self.btn_girar,
            self.btn_frente,
            self.btn_tras,
        ]
        for i, botao in enumerate(botoes):
            grid_acoes.addWidget(botao, i // 2, i % 2)
        raiz.addWidget(grupo_acoes)

        linha = QHBoxLayout()
        self.lbl_status = QLabel("Pronto.")
        self.lbl_status.setWordWrap(True)
        linha.addWidget(self.lbl_status, 1)
        self.btn_fechar_dialog = QPushButton("Fechar")
        linha.addWidget(self.btn_fechar_dialog)
        raiz.addLayout(linha)

    def valor_float(self, campo: QLineEdit, padrao: float) -> float:
        try:
            return float(campo.text().strip().replace(",", "."))
        except Exception:
            campo.setText(self._fmt(padrao))
            return float(padrao)

    @staticmethod
    def _fmt(valor: float) -> str:
        texto = f"{float(valor):.4f}".rstrip("0").rstrip(".")
        return texto or "0"


class Ferramenta(FerramentaBase):
    id_ferramenta = "manipulacao_rapida"
    nome = "Manipulação Rápida"
    usa_painel_auxiliar = False
    descricao_painel = "Organiza, corrige e prepara moldes/elementos com ações rápidas."

    _dialog_por_canvas: dict[int, ManipulacaoRapidaDialog] = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        dialog = self._obter_dialog(canvas)
        self._conectar_botoes(canvas, dialog)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._status(canvas, "Manipulação rápida ativa. Escolha uma ação no painel.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog:
            dialog.hide()

    def _obter_dialog(self, canvas) -> ManipulacaoRapidaDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = ManipulacaoRapidaDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        return dialog

    def _restaurar_dialog(self, canvas, dialog: ManipulacaoRapidaDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 30), 90))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _conectar_botoes(self, canvas, dialog: ManipulacaoRapidaDialog) -> None:
        if getattr(dialog, "_conectado_canvas", None) == id(canvas):
            return
        dialog._conectado_canvas = id(canvas)
        dialog.btn_sel_tudo.clicked.connect(lambda: self._selecionar_tudo(canvas))
        dialog.btn_sel_moldes.clicked.connect(lambda: self._selecionar_moldes(canvas))
        dialog.btn_sel_curvas.clicked.connect(lambda: self._selecionar_curvas(canvas))
        dialog.btn_limpar.clicked.connect(lambda: self._limpar_selecao(canvas))
        dialog.btn_centralizar.clicked.connect(lambda: self._centralizar_nome_fio(canvas, dialog))
        dialog.btn_curvas.clicked.connect(lambda: self._preparar_curvas_editaveis(canvas, dialog))
        dialog.btn_limpar_pontos.clicked.connect(lambda: self._limpar_pontos_duplicados(canvas, dialog))
        dialog.btn_fechar.clicked.connect(lambda: self._fechar_pequenas_aberturas(canvas, dialog))
        dialog.btn_duplicar.clicked.connect(lambda: self._duplicar_deslocar(canvas, dialog))
        dialog.btn_espelhar_h.clicked.connect(lambda: self._espelhar(canvas, dialog, horizontal=True))
        dialog.btn_espelhar_v.clicked.connect(lambda: self._espelhar(canvas, dialog, horizontal=False))
        dialog.btn_girar.clicked.connect(lambda: self._girar(canvas, dialog))
        dialog.btn_frente.clicked.connect(lambda: self._trazer_frente(canvas, dialog))
        dialog.btn_tras.clicked.connect(lambda: self._enviar_tras(canvas, dialog))
        dialog.btn_fechar_dialog.clicked.connect(dialog.hide)

    def _indices_alvo(self, canvas, dialog: ManipulacaoRapidaDialog) -> list[int]:
        selecionados = sorted(int(i) for i in getattr(canvas, "_selecionados", set()) if 0 <= int(i) < len(canvas.cena.elementos))
        if selecionados:
            return selecionados
        if dialog.chk_aplicar_todos_se_nada.isChecked():
            return list(range(len(canvas.cena.elementos)))
        return []

    def _selecionar_tudo(self, canvas):
        canvas._selecionados = set(range(len(canvas.cena.elementos)))
        canvas.update()
        self._status(canvas, f"Selecionado tudo: {len(canvas._selecionados)} elemento(s).")

    def _selecionar_moldes(self, canvas):
        canvas._selecionados = {i for i, el in enumerate(canvas.cena.elementos) if isinstance(el, dict) and el.get("molde")}
        canvas.update()
        self._status(canvas, f"Selecionado(s) {len(canvas._selecionados)} molde(s).")

    def _selecionar_curvas(self, canvas):
        canvas._selecionados = {
            i for i, el in enumerate(canvas.cena.elementos)
            if isinstance(el, dict) and self._eh_curva(el)
        }
        canvas.update()
        self._status(canvas, f"Selecionada(s) {len(canvas._selecionados)} curva(s).")

    def _limpar_selecao(self, canvas):
        canvas._selecionados.clear()
        canvas.update()
        self._status(canvas, "Seleção limpa.")

    def _centralizar_nome_fio(self, canvas, dialog: ManipulacaoRapidaDialog):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione um molde/elemento ou marque aplicar em todos.", dialog)
            return
        alterados = 0
        for idx in indices:
            el = canvas.cena.elementos[idx]
            bbox = self._bbox_elemento(el)
            if not bbox:
                continue
            min_x, min_y, max_x, max_y = bbox
            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0
            largura = max_x - min_x
            altura = max_y - min_y
            el["ponto_texto"] = (cx, cy)
            el["ponto_texto_nome"] = (cx, cy)
            el["nome_posicao"] = (cx, cy)
            el["nome_centro"] = (cx, cy)
            tamanho_fio = max(min(largura, altura) * 0.55, max(largura, altura) * 0.25, 0.1)
            el["fio_origem"] = (cx - tamanho_fio / 2.0, cy)
            el["fio_fim"] = (cx + tamanho_fio / 2.0, cy)
            el["seta_origem"] = el["fio_origem"]
            el["seta_fim"] = el["fio_fim"]
            el["fio_angulo"] = 0.0
            el["mostrar_fio"] = True
            alterados += 1
        self._registrar(canvas)
        self._status(canvas, f"Nome e fio centralizados em {alterados} elemento(s).", dialog)

    def _preparar_curvas_editaveis(self, canvas, dialog: ManipulacaoRapidaDialog):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione as curvas ou marque aplicar em todos.", dialog)
            return
        alteradas = 0
        for idx in indices:
            el = canvas.cena.elementos[idx]
            if not isinstance(el, dict) or el.get("tipo") != "polyline":
                continue
            pontos = self._pontos_elemento(el)
            if len(pontos) < 3:
                continue
            el["curva_suave"] = True
            el["suavizar"] = True
            el["renderizacao"] = "curva_suave"
            el["tipo_curva"] = "spline_catmull_rom"
            el["pontos_controle_curva"] = [(p.x(), p.y()) for p in pontos]
            el["pontos_controle_principais"] = [(p.x(), p.y()) for p in pontos]
            el.setdefault("subtipo_audaces", "curva_predefinida")
            el.setdefault("metadados", {})
            if isinstance(el["metadados"], dict):
                el["metadados"].setdefault("editavel", True)
            alteradas += 1
        self._registrar(canvas)
        self._status(canvas, f"Preparada(s) {alteradas} curva(s) para edição.", dialog)

    def _limpar_pontos_duplicados(self, canvas, dialog: ManipulacaoRapidaDialog):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione os elementos para limpar pontos.", dialog)
            return
        alterados = 0
        tolerancia = self._comprimento_cena(canvas, 0.01)
        for idx in indices:
            el = canvas.cena.elementos[idx]
            if not isinstance(el, dict):
                continue
            for chave in LISTAS_PONTOS:
                if isinstance(el.get(chave), list):
                    nova = self._deduplicar_lista_pontos(el.get(chave), tolerancia)
                    if len(nova) != len(el.get(chave)):
                        el[chave] = nova
                        alterados += 1
        self._registrar(canvas)
        self._status(canvas, f"Pontos duplicados limpos em {alterados} lista(s).", dialog)

    def _fechar_pequenas_aberturas(self, canvas, dialog: ManipulacaoRapidaDialog):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione linhas/curvas para fechar pequenas aberturas.", dialog)
            return
        folga = self._comprimento_cena(canvas, max(0.0, dialog.valor_float(dialog.ed_folga, 0.2)))
        fechadas = 0
        for idx in indices:
            el = canvas.cena.elementos[idx]
            if not isinstance(el, dict):
                continue
            pontos = self._pontos_elemento(el)
            if len(pontos) < 3:
                continue
            if self._dist(pontos[0], pontos[-1]) <= folga:
                primeiro = self._ponto_para_original(el.get("pontos", [])[0], pontos[0])
                el["pontos"][-1] = primeiro
                el["fechado"] = True
                fechadas += 1
        self._registrar(canvas)
        self._status(canvas, f"Fechada(s) {fechadas} abertura(s).", dialog)

    def _duplicar_deslocar(self, canvas, dialog: ManipulacaoRapidaDialog):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione os elementos para duplicar.", dialog)
            return
        desloc = self._comprimento_cena(canvas, dialog.valor_float(dialog.ed_deslocamento, 5.0))
        novos = []
        for idx in indices:
            el = deepcopy(canvas.cena.elementos[idx])
            el["id"] = str(uuid4())
            mover_elemento_por_delta(el, desloc, desloc)
            novos.append(el)
        inicio = len(canvas.cena.elementos)
        canvas.cena.elementos.extend(novos)
        canvas._selecionados = set(range(inicio, inicio + len(novos)))
        self._registrar(canvas)
        self._status(canvas, f"Duplicado(s) {len(novos)} elemento(s).", dialog)

    def _espelhar(self, canvas, dialog: ManipulacaoRapidaDialog, horizontal: bool):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione os elementos para espelhar.", dialog)
            return
        bbox = self._bbox_indices(canvas, indices)
        if not bbox:
            return
        min_x, min_y, max_x, max_y = bbox
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        for idx in indices:
            el = canvas.cena.elementos[idx]
            self._transformar_elemento(el, lambda p: QPointF((2 * cx) - p.x(), p.y()) if horizontal else QPointF(p.x(), (2 * cy) - p.y()))
            if horizontal:
                el["espelhado_horizontal"] = not bool(el.get("espelhado_horizontal", False))
            else:
                el["espelhado_vertical"] = not bool(el.get("espelhado_vertical", False))
        self._registrar(canvas)
        self._status(canvas, f"Espelhado(s) {len(indices)} elemento(s) {'horizontalmente' if horizontal else 'verticalmente'}.", dialog)

    def _girar(self, canvas, dialog: ManipulacaoRapidaDialog):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione os elementos para girar.", dialog)
            return
        angulo = dialog.valor_float(dialog.ed_angulo, 90.0)
        bbox = self._bbox_indices(canvas, indices)
        if not bbox:
            return
        min_x, min_y, max_x, max_y = bbox
        centro = QPointF((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
        a = radians(angulo)
        ca = cos(a)
        sa = sin(a)
        for idx in indices:
            el = canvas.cena.elementos[idx]
            self._transformar_elemento(el, lambda p, c=centro: QPointF(c.x() + ((p.x() - c.x()) * ca) - ((p.y() - c.y()) * sa), c.y() + ((p.x() - c.x()) * sa) + ((p.y() - c.y()) * ca)))
            try:
                el["fio_angulo"] = (float(el.get("fio_angulo") or 0.0) + angulo) % 360.0
            except Exception:
                pass
        self._registrar(canvas)
        self._status(canvas, f"Girado(s) {len(indices)} elemento(s) em {angulo:g}°.", dialog)

    def _trazer_frente(self, canvas, dialog: ManipulacaoRapidaDialog):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione os elementos para trazer à frente.", dialog)
            return
        elementos = canvas.cena.elementos
        selecionados = [elementos[i] for i in indices]
        restantes = [el for i, el in enumerate(elementos) if i not in set(indices)]
        canvas.cena.elementos = restantes + selecionados
        inicio = len(restantes)
        canvas._selecionados = set(range(inicio, inicio + len(selecionados)))
        self._registrar(canvas)
        self._status(canvas, f"{len(selecionados)} elemento(s) enviado(s) para frente.", dialog)

    def _enviar_tras(self, canvas, dialog: ManipulacaoRapidaDialog):
        indices = self._indices_alvo(canvas, dialog)
        if not indices:
            self._status(canvas, "Selecione os elementos para enviar para trás.", dialog)
            return
        elementos = canvas.cena.elementos
        selecionados = [elementos[i] for i in indices]
        restantes = [el for i, el in enumerate(elementos) if i not in set(indices)]
        canvas.cena.elementos = selecionados + restantes
        canvas._selecionados = set(range(len(selecionados)))
        self._registrar(canvas)
        self._status(canvas, f"{len(selecionados)} elemento(s) enviado(s) para trás.", dialog)

    def _registrar(self, canvas):
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        canvas.update()

    def _status(self, canvas, texto: str, dialog: ManipulacaoRapidaDialog | None = None):
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
        if dialog is not None:
            dialog.lbl_status.setText(texto)

    def _comprimento_cena(self, canvas, valor_cm: float) -> float:
        if hasattr(canvas, "converter_para_cena"):
            try:
                return float(canvas.converter_para_cena(valor_cm))
            except Exception:
                pass
        return float(valor_cm) * max(1e-9, float(getattr(canvas, "_unidade_fator", 1.0)))

    @staticmethod
    def _eh_curva(el: dict) -> bool:
        if not isinstance(el, dict):
            return False
        return bool(
            el.get("curva_suave")
            or el.get("suavizar")
            or str(el.get("tipo_curva") or "").lower().startswith("spline")
            or str(el.get("renderizacao") or "").lower() == "curva_suave"
            or str(el.get("subtipo_audaces") or "").lower() == "curva_predefinida"
            or str(el.get("nome_curva_predefinida") or "").strip()
        )

    def _bbox_indices(self, canvas, indices: list[int]):
        pontos: list[QPointF] = []
        for idx in indices:
            if 0 <= idx < len(canvas.cena.elementos):
                pontos.extend(self._todos_pontos(canvas.cena.elementos[idx]))
        if not pontos:
            return None
        return min(p.x() for p in pontos), min(p.y() for p in pontos), max(p.x() for p in pontos), max(p.y() for p in pontos)

    def _bbox_elemento(self, el: dict):
        pontos = self._todos_pontos(el)
        if not pontos:
            return None
        return min(p.x() for p in pontos), min(p.y() for p in pontos), max(p.x() for p in pontos), max(p.y() for p in pontos)

    def _todos_pontos(self, el: dict) -> list[QPointF]:
        pontos: list[QPointF] = []
        if not isinstance(el, dict):
            return pontos
        for chave in LISTAS_PONTOS:
            valor = el.get(chave)
            if isinstance(valor, list):
                for item in valor:
                    pt = self._qpoint(item)
                    if pt is not None:
                        pontos.append(pt)
            elif isinstance(valor, dict):
                for item in valor.values():
                    pt = self._qpoint(item)
                    if pt is not None:
                        pontos.append(pt)
        for chave in PONTOS_SOLTOS:
            pt = self._qpoint(el.get(chave))
            if pt is not None:
                pontos.append(pt)
        return pontos

    def _pontos_elemento(self, el: dict) -> list[QPointF]:
        pontos = []
        for item in el.get("pontos", []) or []:
            pt = self._qpoint(item)
            if pt is not None:
                pontos.append(pt)
        return pontos

    @staticmethod
    def _qpoint(valor) -> QPointF | None:
        try:
            if isinstance(valor, dict) and "x" in valor and "y" in valor:
                return QPointF(float(valor.get("x", 0.0)), float(valor.get("y", 0.0)))
            if isinstance(valor, (tuple, list)) and len(valor) >= 2:
                return QPointF(float(valor[0]), float(valor[1]))
        except Exception:
            return None
        return None

    @staticmethod
    def _ponto_para_original(original, ponto: QPointF):
        if isinstance(original, dict):
            novo = dict(original)
            novo["x"] = ponto.x()
            novo["y"] = ponto.y()
            return novo
        if isinstance(original, list):
            return [ponto.x(), ponto.y(), *original[2:]]
        if isinstance(original, tuple):
            return (ponto.x(), ponto.y(), *original[2:])
        return (ponto.x(), ponto.y())

    def _transformar_elemento(self, el: dict, fn):
        if not isinstance(el, dict):
            return
        for chave in LISTAS_PONTOS:
            if chave in el:
                el[chave] = self._transformar_lista_ou_mapa(el.get(chave), fn)
        for chave in PONTOS_SOLTOS:
            if chave in el:
                el[chave] = self._transformar_ponto(el.get(chave), fn)

    def _transformar_lista_ou_mapa(self, valor, fn):
        if isinstance(valor, list):
            return [self._transformar_ponto(item, fn) for item in valor]
        if isinstance(valor, tuple):
            return tuple(self._transformar_ponto(item, fn) for item in valor)
        if isinstance(valor, dict):
            return {k: self._transformar_ponto(v, fn) for k, v in valor.items()}
        return valor

    def _transformar_ponto(self, valor, fn):
        pt = self._qpoint(valor)
        if pt is None:
            return valor
        novo = fn(pt)
        return self._ponto_para_original(valor, novo)

    def _deduplicar_lista_pontos(self, valores: list, tolerancia: float) -> list:
        saida = []
        ultimo: QPointF | None = None
        for item in valores:
            pt = self._qpoint(item)
            if pt is None:
                saida.append(item)
                continue
            if ultimo is not None and self._dist(ultimo, pt) <= tolerancia:
                continue
            saida.append(item)
            ultimo = pt
        return saida

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt(((a.x() - b.x()) ** 2) + ((a.y() - b.y()) ** 2))
