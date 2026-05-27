from __future__ import annotations

from copy import deepcopy
from math import isfinite
from time import perf_counter
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QVBoxLayout

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class EspelharDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:espelhar"
        self.setWindowTitle("Espelhar")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(260)
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QLabel, QCheckBox { color:#111111; }
            QComboBox { background:#ffffff; color:#111111; border:1px solid #b5bcc3; min-height:22px; }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(6)

        form = QFormLayout()

        self.cmb_eixo = QComboBox()
        self.cmb_eixo.addItems(["Vertical", "Horizontal"])

        self.cmb_referencia = QComboBox()
        self.cmb_referencia.addItems(["Centro da seleção", "Último clique", "Origem 0,0"])

        self.chk_copia = QCheckBox("Criar cópia espelhada")
        self.chk_copia.setChecked(True)

        # Nome simples para o usuário, mantendo a mesma finalidade técnica antiga:
        # atualizar as marcações internas de reflexo/dobra do molde.
        self.chk_inverter_reflexo = QCheckBox("Marcar como espelhado/dobra")
        self.chk_inverter_reflexo.setChecked(True)

        form.addRow("Eixo", self.cmb_eixo)
        form.addRow("Referência", self.cmb_referencia)
        raiz.addLayout(form)
        raiz.addWidget(self.chk_copia)
        raiz.addWidget(self.chk_inverter_reflexo)


class Ferramenta(FerramentaBase):
    id_ferramenta = "espelhar"
    nome = "Espelhar"
    usa_painel_auxiliar = False
    descricao_painel = "Clique em um molde/elemento para espelhar, arraste e clique para soltar. Direito fecha."

    _dialog_por_canvas: dict[int, EspelharDialog] = {}

    def __init__(self):
        super().__init__()
        self._ultimo_clique: QPointF | None = None
        self._canvas_ativo = None
        self._timer_animacao: QTimer | None = None
        self._ctx_arraste: dict | None = None
        self._ignorando_sinal_dialog = False

    # ---------------------------------------------------------------------
    # Ciclo da ferramenta
    # ---------------------------------------------------------------------
    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._canvas_ativo = canvas
        self._ultimo_clique = None
        self._parar_animacao()
        self._ctx_arraste = None

        dialog = self._obter_dialog(canvas)
        dialog._canvas_ativo = canvas  # type: ignore[attr-defined]
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()

        self._status(
            canvas,
            "Espelhar: clique esquerdo no molde/elemento para espelhar e segurar. "
            "Clique esquerdo solta. Clique direito fecha.",
        )

    def on_deactivate(self, canvas):
        self._cancelar_arraste(canvas, silencioso=True)
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()

    # ---------------------------------------------------------------------
    # Eventos
    # ---------------------------------------------------------------------
    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._ctx_arraste is not None:
                self._cancelar_arraste(canvas, silencioso=True)
            self._fechar(canvas)
            event.accept()
            return True

        if event.button() != Qt.LeftButton:
            return False

        pos = self._posicao_canvas(canvas, event)
        self._ultimo_clique = QPointF(pos)

        if self._ctx_arraste is not None:
            self._confirmar_arraste(canvas, pos)
            event.accept()
            return True

        self._iniciar_espelhamento(canvas, pos)
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._ctx_arraste is None:
            return False

        pos = self._posicao_canvas(canvas, event)
        self._ctx_arraste["mouse_atual"] = QPointF(pos)

        if not bool(self._ctx_arraste.get("animando", False)):
            self._atualizar_posicao_arraste(canvas)

        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        if event.key() in (Qt.Key_Escape,):
            if self._ctx_arraste is not None:
                self._cancelar_arraste(canvas, silencioso=False)
                event.accept()
                return True
            self._fechar(canvas)
            event.accept()
            return True

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._ctx_arraste is not None:
                pos = self._ctx_arraste.get("mouse_atual") or self._ctx_arraste.get("mouse_inicio") or QPointF(0, 0)
                self._confirmar_arraste(canvas, QPointF(pos))
                event.accept()
                return True
            return False

        return False

    # ---------------------------------------------------------------------
    # Dialog
    # ---------------------------------------------------------------------
    def _obter_dialog(self, canvas) -> EspelharDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)

        if dialog is None or dialog.parentWidget() is not parent:
            dialog = EspelharDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)

        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.cmb_eixo.currentTextChanged.connect(lambda *_args, d=dialog: self._on_configuracao_alterada(d))
            dialog.cmb_referencia.currentTextChanged.connect(lambda *_args, d=dialog: self._on_configuracao_alterada(d))
            dialog.chk_inverter_reflexo.toggled.connect(lambda *_args, d=dialog: self._on_configuracao_alterada(d))

        return dialog

    def _restaurar_dialog(self, canvas, dialog: EspelharDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos_local)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _on_configuracao_alterada(self, dialog: EspelharDialog) -> None:
        if self._ignorando_sinal_dialog:
            return

        canvas = getattr(dialog, "_canvas_ativo", None) or self._canvas_ativo
        if canvas is None or self._ctx_arraste is None:
            return

        self._recalcular_molde_seguro(canvas, reiniciar_ancora=True)

    # ---------------------------------------------------------------------
    # Fluxo principal
    # ---------------------------------------------------------------------
    def _iniciar_espelhamento(self, canvas, pos: QPointF) -> None:
        dialog = self._obter_dialog(canvas)

        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        if candidatos:
            indices = [int(candidatos[0])]
        else:
            indices = self._indices_validos(canvas)

        if not indices:
            canvas._selecionados = set()
            canvas.update()
            self._status(canvas, "Espelhar: clique diretamente em um molde ou elemento.")
            return

        copiar = bool(dialog.chk_copia.isChecked())
        eixo = dialog.cmb_eixo.currentText()
        referencia_modo = dialog.cmb_referencia.currentText()
        atualizar_marcacao = bool(dialog.chk_inverter_reflexo.isChecked())
        ref = self._referencia_de_elementos(canvas, indices, referencia_modo, pos)

        if ref is None:
            self._status(canvas, "Espelhar: não foi possível calcular a referência.")
            return

        originais = [deepcopy(canvas.cena.elementos[idx]) for idx in indices]
        templates: list[dict] = []
        alvos_indices: list[int] = []
        animacoes: list[dict] = []

        for idx, original in zip(indices, originais):
            template = deepcopy(original)

            if copiar:
                template["id"] = str(uuid4())
                if template.get("molde"):
                    template["molde_id"] = str(uuid4())
                    template["nome_molde"] = self._nome_copia(str(template.get("nome_molde") or "Molde"))

                canvas.cena.elementos.append(deepcopy(template))
                alvo_idx = len(canvas.cena.elementos) - 1
            else:
                canvas.cena.elementos[idx] = deepcopy(template)
                alvo_idx = idx

            templates.append(template)
            alvos_indices.append(alvo_idx)

        self._ctx_arraste = {
            "canvas": canvas,
            "indices_origem": list(indices),
            "originais": originais,
            "templates": templates,
            "alvos_indices": alvos_indices,
            "copiar": copiar,
            "eixo": eixo,
            "referencia_modo": referencia_modo,
            "referencia": QPointF(ref),
            "atualizar_marcacao": atualizar_marcacao,
            "mouse_inicio": QPointF(pos),
            "mouse_atual": QPointF(pos),
            "base_espelhados": [],
            "animando": True,
            "historico_registrado": False,
        }

        base_espelhados = self._criar_bases_espelhadas(canvas)
        self._ctx_arraste["base_espelhados"] = base_espelhados

        for alvo_idx, template, fim in zip(alvos_indices, templates, base_espelhados):
            animacoes.append({"idx": alvo_idx, "inicio": deepcopy(template), "fim": deepcopy(fim)})

        canvas._selecionados = set(alvos_indices)
        canvas.update()
        self._iniciar_animacao_espelho(canvas, animacoes)

    def _iniciar_animacao_espelho(self, canvas, animacoes: list[dict]) -> None:
        ctx = self._ctx_arraste
        if not ctx:
            return

        ctx["animacoes"] = animacoes
        ctx["inicio_tempo"] = perf_counter()
        ctx["duracao_ms"] = 380
        ctx["animando"] = True

        self._parar_animacao()
        parent = canvas if hasattr(canvas, "deleteLater") else None
        timer = QTimer(parent)
        timer.setInterval(16)
        timer.timeout.connect(lambda: self._atualizar_animacao_espelho(canvas))
        self._timer_animacao = timer
        timer.start()

        angulo = 0 if ctx.get("eixo") == "Vertical" else 90
        self._status(canvas, f"Espelhando e segurando na mão ({angulo}°). Mova o mouse e clique para soltar.")

    def _atualizar_animacao_espelho(self, canvas) -> None:
        ctx = self._ctx_arraste
        if not ctx:
            return

        duracao = max(1.0, float(ctx.get("duracao_ms", 380))) / 1000.0
        progresso = min(1.0, max(0.0, (perf_counter() - float(ctx.get("inicio_tempo", perf_counter()))) / duracao))
        t = self._ease_out_cubic(progresso)

        for item in ctx.get("animacoes", []):
            idx = int(item["idx"])
            if 0 <= idx < len(canvas.cena.elementos):
                canvas.cena.elementos[idx] = self._interpolar_elemento(item["inicio"], item["fim"], t)

        canvas._selecionados = set(ctx.get("alvos_indices", []))
        canvas.update()

        if progresso >= 1.0:
            self._parar_animacao()
            ctx["animando"] = False
            self._aplicar_bases_no_canvas(canvas)
            self._atualizar_posicao_arraste(canvas)
            self._status(canvas, "Molde espelhado na mão. Mova e clique esquerdo para soltar; direito fecha.")

    def _recalcular_molde_seguro(self, canvas, reiniciar_ancora: bool = False) -> None:
        ctx = self._ctx_arraste
        if not ctx:
            return

        dialog = self._obter_dialog(canvas)
        eixo = dialog.cmb_eixo.currentText()
        referencia_modo = dialog.cmb_referencia.currentText()
        atualizar_marcacao = bool(dialog.chk_inverter_reflexo.isChecked())
        mouse_atual = QPointF(ctx.get("mouse_atual") or ctx.get("mouse_inicio") or QPointF(0, 0))

        ref = self._referencia_das_copias_originais(ctx.get("originais", []), referencia_modo, QPointF(ctx.get("mouse_inicio") or mouse_atual))
        if ref is None:
            return

        ctx["eixo"] = eixo
        ctx["referencia_modo"] = referencia_modo
        ctx["referencia"] = QPointF(ref)
        ctx["atualizar_marcacao"] = atualizar_marcacao
        ctx["base_espelhados"] = self._criar_bases_espelhadas(canvas)

        if reiniciar_ancora:
            ctx["mouse_inicio"] = QPointF(mouse_atual)
            ctx["mouse_atual"] = QPointF(mouse_atual)

        if bool(ctx.get("animando", False)):
            animacoes: list[dict] = []
            for alvo_idx, template, fim in zip(ctx.get("alvos_indices", []), ctx.get("templates", []), ctx.get("base_espelhados", [])):
                animacoes.append({"idx": int(alvo_idx), "inicio": deepcopy(template), "fim": deepcopy(fim)})
            ctx["animacoes"] = animacoes
            ctx["inicio_tempo"] = perf_counter()
        else:
            self._aplicar_bases_no_canvas(canvas)
            self._atualizar_posicao_arraste(canvas)

        angulo = 0 if eixo == "Vertical" else 90
        self._status(canvas, f"Configuração atualizada. O molde na mão agora obedece {angulo}°.")

    def _criar_bases_espelhadas(self, canvas) -> list[dict]:
        ctx = self._ctx_arraste
        if not ctx:
            return []

        eixo = str(ctx.get("eixo") or "Vertical")
        ref = QPointF(ctx.get("referencia") or QPointF(0, 0))
        atualizar_marcacao = bool(ctx.get("atualizar_marcacao", True))

        bases: list[dict] = []
        for template in ctx.get("templates", []):
            item = deepcopy(template)
            self._espelhar_elemento(item, eixo, ref, atualizar_marcacao)
            bases.append(item)
        return bases

    def _aplicar_bases_no_canvas(self, canvas) -> None:
        ctx = self._ctx_arraste
        if not ctx:
            return

        for idx, base in zip(ctx.get("alvos_indices", []), ctx.get("base_espelhados", [])):
            idx = int(idx)
            if 0 <= idx < len(canvas.cena.elementos):
                canvas.cena.elementos[idx] = deepcopy(base)

        canvas._selecionados = set(ctx.get("alvos_indices", []))
        canvas.update()

    def _atualizar_posicao_arraste(self, canvas) -> None:
        ctx = self._ctx_arraste
        if not ctx:
            return

        mouse_inicio = QPointF(ctx.get("mouse_inicio") or QPointF(0, 0))
        mouse_atual = QPointF(ctx.get("mouse_atual") or mouse_inicio)
        eixo = str(ctx.get("eixo") or "Vertical")

        dx = mouse_atual.x() - mouse_inicio.x()
        dy = mouse_atual.y() - mouse_inicio.y()

        # Regra solicitada:
        # - Eixo vertical: o molde segurado anda só em 0° / horizontal.
        # - Eixo horizontal: o molde segurado anda só em 90° / vertical.
        if eixo == "Vertical":
            dy = 0.0
        else:
            dx = 0.0

        for idx, base in zip(ctx.get("alvos_indices", []), ctx.get("base_espelhados", [])):
            idx = int(idx)
            if 0 <= idx < len(canvas.cena.elementos):
                canvas.cena.elementos[idx] = self._transladar_elemento(base, dx, dy)

        canvas._selecionados = set(ctx.get("alvos_indices", []))
        canvas.update()

    def _confirmar_arraste(self, canvas, pos: QPointF) -> None:
        ctx = self._ctx_arraste
        if not ctx:
            return

        ctx["mouse_atual"] = QPointF(pos)
        if bool(ctx.get("animando", False)):
            self._parar_animacao()
            ctx["animando"] = False
            self._aplicar_bases_no_canvas(canvas)

        self._atualizar_posicao_arraste(canvas)

        if not bool(ctx.get("historico_registrado", False)):
            canvas._registrar_historico()
            ctx["historico_registrado"] = True

        canvas._selecionados = set()
        canvas.update()
        self._ctx_arraste = None

        self._status(canvas, "Molde espelhado solto. Clique em outro molde/elemento para espelhar; direito fecha.")

    def _cancelar_arraste(self, canvas, silencioso: bool) -> None:
        ctx = self._ctx_arraste
        if not ctx:
            return

        self._parar_animacao()

        copiar = bool(ctx.get("copiar", True))
        alvos = [int(i) for i in ctx.get("alvos_indices", [])]
        originais = list(ctx.get("originais", []))
        indices_origem = [int(i) for i in ctx.get("indices_origem", [])]

        if copiar:
            for idx in sorted(alvos, reverse=True):
                if 0 <= idx < len(canvas.cena.elementos):
                    del canvas.cena.elementos[idx]
        else:
            for idx, original in zip(indices_origem, originais):
                if 0 <= idx < len(canvas.cena.elementos):
                    canvas.cena.elementos[idx] = deepcopy(original)

        canvas._selecionados = set()
        canvas.update()
        self._ctx_arraste = None

        if not silencioso:
            self._status(canvas, "Espelhamento cancelado.")

    def _fechar(self, canvas) -> None:
        self._parar_animacao()
        canvas._selecionados = set()
        canvas.update()
        canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Espelhar finalizada. Voltando para Selecionar.")

    def _parar_animacao(self) -> None:
        timer = self._timer_animacao
        self._timer_animacao = None
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except RuntimeError:
                pass

    # ---------------------------------------------------------------------
    # Referências e seleção
    # ---------------------------------------------------------------------
    def _indices_validos(self, canvas) -> list[int]:
        return [
            int(i)
            for i in sorted(getattr(canvas, "_selecionados", set()) or [])
            if 0 <= int(i) < len(canvas.cena.elementos)
        ]

    def _referencia_de_elementos(self, canvas, indices: list[int], modo: str, ultimo_clique: QPointF) -> QPointF | None:
        if modo == "Último clique":
            return QPointF(ultimo_clique)
        if modo == "Origem 0,0":
            return QPointF(0.0, 0.0)
        elementos = [canvas.cena.elementos[idx] for idx in indices if 0 <= idx < len(canvas.cena.elementos)]
        return self._referencia_das_copias_originais(elementos, modo, ultimo_clique)

    def _referencia_das_copias_originais(self, elementos: list[dict], modo: str, ultimo_clique: QPointF) -> QPointF | None:
        if modo == "Último clique":
            return QPointF(ultimo_clique)
        if modo == "Origem 0,0":
            return QPointF(0.0, 0.0)

        pts: list[tuple[float, float]] = []
        for el in elementos:
            pts.extend(self._todos_pontos(el))
        if not pts:
            return None

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    def _posicao_canvas(self, canvas, event) -> QPointF:
        try:
            pos_evento = event.position()
        except AttributeError:
            pos_evento = event.pos()

        if hasattr(canvas, "_ponto_com_snap"):
            return QPointF(canvas._ponto_com_snap(pos_evento))
        return QPointF(pos_evento)

    # ---------------------------------------------------------------------
    # Transformações geométricas
    # ---------------------------------------------------------------------
    def _espelhar_elemento(self, el: dict, eixo: str, ref: QPointF, atualizar_marcacao: bool) -> None:
        def conv(p):
            x, y = float(p[0]), float(p[1])
            if eixo == "Vertical":
                x = (2.0 * ref.x()) - x
            else:
                y = (2.0 * ref.y()) - y
            return (x, y)

        chaves_lista_pontos = (
            "pontos",
            "controle_cantos",
            "controle_auxiliares",
            "marcacoes_no_perimetro",
            "distancias_no_perimetro",
            "marcacoes_perimetro",
            "pontos_margem",
            "margem_pontos",
            "linha_costura",
            "linha_margem",
        )
        for chave in chaves_lista_pontos:
            if isinstance(el.get(chave), list):
                el[chave] = [conv(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]

        chaves_ponto = (
            "fio_origem",
            "fio_fim",
            "p0",
            "p1",
            "p2",
            "inicio",
            "fim",
            "origem",
            "centro",
            "nome_posicao",
            "posicao_nome",
            "texto_posicao",
            "posicao_texto",
            "rotulo_posicao",
            "posicao_rotulo",
        )
        for chave in chaves_ponto:
            if self._eh_ponto(el.get(chave)):
                el[chave] = conv(el[chave])

        for chave in ("pontos_controle_principais", "pontos_auxiliares"):
            if isinstance(el.get(chave), list):
                for item in el[chave]:
                    if isinstance(item, dict) and "x" in item and "y" in item:
                        x, y = conv((item["x"], item["y"]))
                        item["x"] = x
                        item["y"] = y

        if atualizar_marcacao:
            self._atualizar_marcacao_espelho(el, eixo)

        metadados = el.setdefault("metadados", {})
        metadados["ultima_transformacao"] = f"espelhar_{eixo.lower()}"
        metadados["eixo_espelho"] = eixo.lower()
        metadados["eixo_movimento_espelho"] = "horizontal" if eixo == "Vertical" else "vertical"
        metadados["angulo_movimento_espelho"] = 0.0 if eixo == "Vertical" else 90.0

    def _atualizar_marcacao_espelho(self, el: dict, eixo: str) -> None:
        """
        Mantém a marcação interna que antes aparecia na interface como
        'flags refletido/dobra', mas com comportamento mais consistente.

        Eixo Vertical  -> reflexo esquerda/direita -> marca horizontal.
        Eixo Horizontal -> reflexo cima/baixo       -> marca vertical.
        """
        if eixo == "Vertical":
            novo_valor = not bool(el.get("refletido_horizontal", False))
            el["refletido_horizontal"] = novo_valor
            el["chk_reflete_h"] = novo_valor
        else:
            novo_valor = not bool(el.get("refletido_vertical", False))
            el["refletido_vertical"] = novo_valor
            el["chk_reflete_v"] = novo_valor

        metadados = el.setdefault("metadados", {})
        metadados["marcado_como_espelhado_dobra"] = True
        metadados["marcacao_espelho_dobra"] = eixo.lower()

    def _transladar_elemento(self, el, dx: float, dy: float):
        if self._eh_ponto(el):
            x = float(el[0]) + dx
            y = float(el[1]) + dy
            resto = list(el[2:]) if len(el) > 2 else []
            valores = [x, y, *resto]
            return tuple(valores) if isinstance(el, tuple) else valores

        if isinstance(el, dict):
            saida = deepcopy(el)
            tem_xy = (
                "x" in el
                and "y" in el
                and self._eh_numero(el.get("x"))
                and self._eh_numero(el.get("y"))
            )
            if tem_xy:
                saida["x"] = float(el["x"]) + dx
                saida["y"] = float(el["y"]) + dy

            for chave, valor in el.items():
                if tem_xy and chave in ("x", "y"):
                    continue
                if isinstance(valor, (dict, list, tuple)):
                    saida[chave] = self._transladar_elemento(valor, dx, dy)
            return saida

        if isinstance(el, list):
            return [self._transladar_elemento(item, dx, dy) for item in el]

        if isinstance(el, tuple):
            return tuple(self._transladar_elemento(item, dx, dy) for item in el)

        return deepcopy(el)

    def _interpolar_elemento(self, inicio, fim, t: float):
        if self._eh_ponto(inicio) and self._eh_ponto(fim):
            x = float(inicio[0]) + (float(fim[0]) - float(inicio[0])) * t
            y = float(inicio[1]) + (float(fim[1]) - float(inicio[1])) * t
            resto = list(fim[2:]) if len(fim) > 2 else []
            valores = [x, y, *resto]
            return tuple(valores) if isinstance(fim, tuple) else valores

        if isinstance(inicio, dict) and isinstance(fim, dict):
            saida = deepcopy(fim)
            tem_xy = (
                "x" in inicio
                and "x" in fim
                and "y" in inicio
                and "y" in fim
                and self._eh_numero(inicio["x"])
                and self._eh_numero(fim["x"])
                and self._eh_numero(inicio["y"])
                and self._eh_numero(fim["y"])
            )
            if tem_xy:
                saida["x"] = float(inicio["x"]) + (float(fim["x"]) - float(inicio["x"])) * t
                saida["y"] = float(inicio["y"]) + (float(fim["y"]) - float(inicio["y"])) * t

            for chave, valor_fim in fim.items():
                if tem_xy and chave in ("x", "y"):
                    continue
                if chave in inicio:
                    saida[chave] = self._interpolar_elemento(inicio[chave], valor_fim, t)
            return saida

        if isinstance(inicio, list) and isinstance(fim, list) and len(inicio) == len(fim):
            return [self._interpolar_elemento(a, b, t) for a, b in zip(inicio, fim)]

        if isinstance(inicio, tuple) and isinstance(fim, tuple) and len(inicio) == len(fim):
            return tuple(self._interpolar_elemento(a, b, t) for a, b in zip(inicio, fim))

        return deepcopy(fim)

    # ---------------------------------------------------------------------
    # Pontos e utilidades
    # ---------------------------------------------------------------------
    def _todos_pontos(self, el: dict) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        chaves_lista = (
            "pontos",
            "controle_cantos",
            "controle_auxiliares",
            "marcacoes_no_perimetro",
            "distancias_no_perimetro",
            "marcacoes_perimetro",
            "pontos_margem",
            "margem_pontos",
            "linha_costura",
            "linha_margem",
        )
        for chave in chaves_lista:
            for p in el.get(chave, []) if isinstance(el.get(chave), list) else []:
                if self._eh_ponto(p):
                    pts.append((float(p[0]), float(p[1])))

        chaves_ponto = (
            "fio_origem",
            "fio_fim",
            "p0",
            "p1",
            "p2",
            "inicio",
            "fim",
            "origem",
            "centro",
            "nome_posicao",
            "posicao_nome",
            "texto_posicao",
            "posicao_texto",
            "rotulo_posicao",
            "posicao_rotulo",
        )
        for chave in chaves_ponto:
            if self._eh_ponto(el.get(chave)):
                pts.append((float(el[chave][0]), float(el[chave][1])))
        return pts

    @staticmethod
    def _ease_out_cubic(t: float) -> float:
        t = min(1.0, max(0.0, float(t)))
        return 1.0 - ((1.0 - t) ** 3)

    @staticmethod
    def _eh_numero(valor) -> bool:
        try:
            return isfinite(float(valor))
        except Exception:
            return False

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    @staticmethod
    def _nome_copia(nome: str) -> str:
        nome = nome.strip() or "Molde"
        return nome if nome.lower().endswith("espelhado") else f"{nome} espelhado"

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
