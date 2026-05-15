from __future__ import annotations

from copy import deepcopy
from math import isfinite
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from tools.tool_base import FerramentaBase

try:
    from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao
except Exception:  # pragma: no cover - mantém a ferramenta funcionando em teste isolado
    instalar_memoria_posicao = None
    restaurar_posicao = None


class InverterMoldesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:inverter_moldes"
        self.setWindowTitle("Inverter Moldes")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(318)
        self.setStyleSheet(
            """
            QDialog { background:#f2f2f2; color:#111111; }
            QLabel, QCheckBox { color:#111111; font-size:11px; }
            QComboBox {
                background:#ffffff; color:#111111;
                border:1px solid #aeb4ba; min-height:22px;
                padding-left:4px;
            }
            QPushButton {
                background:#ffffff; color:#111111;
                border:1px solid #aeb4ba;
                min-height:24px;
                padding:3px 10px;
            }
            QPushButton:hover { background:#e9f3ff; border-color:#4aa3df; }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(7)

        form = QFormLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems([
            "Horizontal",
            "Vertical",
            "Horizontal e vertical",
        ])

        self.cmb_referencia = QComboBox()
        self.cmb_referencia.addItems([
            "Centro de cada molde",
            "Centro da seleção",
            "Último clique",
            "Origem 0,0",
        ])

        form.addRow("Inverter", self.cmb_tipo)
        form.addRow("Referência", self.cmb_referencia)
        raiz.addLayout(form)

        self.chk_criar_copia = QCheckBox("Criar cópia invertida")
        self.chk_criar_copia.setChecked(False)
        self.chk_incluir_vinculos = QCheckBox("Incluir costuras e linhas do molde")
        self.chk_incluir_vinculos.setChecked(True)
        self.chk_atualizar_flags = QCheckBox("Atualizar marcações de espelhamento")
        self.chk_atualizar_flags.setChecked(True)
        self.chk_preservar_selecao = QCheckBox("Manter resultado selecionado")
        self.chk_preservar_selecao.setChecked(True)

        raiz.addWidget(self.chk_criar_copia)
        raiz.addWidget(self.chk_incluir_vinculos)
        raiz.addWidget(self.chk_atualizar_flags)
        raiz.addWidget(self.chk_preservar_selecao)

        self.lbl_status = QLabel("Selecione um ou mais moldes.")
        self.lbl_status.setWordWrap(True)
        raiz.addWidget(self.lbl_status)

        self.btn_aplicar = QPushButton("Aplicar")
        raiz.addWidget(self.btn_aplicar)

    def atualizar_status(self, texto: str) -> None:
        self.lbl_status.setText(texto)


class Ferramenta(FerramentaBase):
    id_ferramenta = "inverter_moldes"
    nome = "Inverter Moldes"
    usa_painel_auxiliar = False
    descricao_painel = (
        "Inverte moldes selecionados. Clique em um molde para selecionar; "
        "clique novamente, Enter ou Aplicar executa. Botão direito fecha."
    )

    _dialog_por_canvas: dict[int, InverterMoldesDialog] = {}

    def __init__(self):
        super().__init__()
        self._ultimo_clique: QPointF | None = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._ultimo_clique = None
        self._operacao_finalizada = False
        self._direito_confirma_fechamento = False

        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._status(canvas, "Inverter Moldes: selecione um molde ou pressione Enter para inverter a seleção.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._operacao_finalizada and not self._direito_confirma_fechamento:
                self._direito_confirma_fechamento = True
                self._status(canvas, "Operação finalizada. Clique direito novamente fecha a ferramenta.")
            else:
                self._fechar(canvas)
            event.accept()
            return True

        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        self._ultimo_clique = QPointF(pos)

        candidatos = canvas._indices_elementos_em_ponto(pos) if hasattr(canvas, "_indices_elementos_em_ponto") else []
        selecionados = set(getattr(canvas, "_selecionados", set()) or set())

        if candidatos and (not selecionados or int(candidatos[0]) not in selecionados):
            canvas._selecionados = {int(candidatos[0])}
            canvas.update()
            self._operacao_finalizada = False
            self._direito_confirma_fechamento = False
            self._status(canvas, "Molde selecionado. Clique esquerdo novamente, Enter ou Aplicar para inverter.")
            event.accept()
            return True

        self._aplicar(canvas)
        event.accept()
        return True

    def on_key_press(self, canvas, event) -> bool:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._aplicar(canvas)
            event.accept()
            return True
        if event.key() == Qt.Key_Escape:
            self._fechar(canvas)
            event.accept()
            return True
        return False

    def _obter_dialog(self, canvas) -> InverterMoldesDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = InverterMoldesDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            if instalar_memoria_posicao is not None:
                instalar_memoria_posicao(dialog, dialog._chave_posicao)
        if not hasattr(dialog, "_hooked"):
            dialog._hooked = True  # type: ignore[attr-defined]
            dialog.btn_aplicar.clicked.connect(lambda: self._aplicar(canvas))
            dialog.cmb_tipo.currentTextChanged.connect(lambda _txt: self._preview_status(canvas))
            dialog.cmb_referencia.currentTextChanged.connect(lambda _txt: self._preview_status(canvas))
            dialog.chk_criar_copia.toggled.connect(lambda _ativo: self._preview_status(canvas))
        return dialog

    def _restaurar_dialog(self, canvas, dialog: InverterMoldesDialog) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            try:
                fallback = canvas.mapToGlobal(
                    canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
                )
            except Exception:
                fallback = None
        if fallback is None and hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 92))
        if restaurar_posicao is not None:
            restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)
        elif fallback is not None:
            dialog.move(fallback)

    def _preview_status(self, canvas) -> None:
        dialog = self._obter_dialog(canvas)
        acao = "criar cópia invertida" if dialog.chk_criar_copia.isChecked() else "inverter no próprio molde"
        self._status(canvas, f"Inverter Moldes: {dialog.cmb_tipo.currentText()} — {acao}.")

    def _aplicar(self, canvas) -> None:
        dialog = self._obter_dialog(canvas)
        indices_base = self._indices_validos(canvas)
        if not indices_base:
            self._status(canvas, "Inverter Moldes: selecione ao menos um molde ou elemento.")
            return

        incluir_vinculos = dialog.chk_incluir_vinculos.isChecked()
        indices = self._indices_com_vinculos(canvas, indices_base) if incluir_vinculos else list(indices_base)
        if not indices:
            self._status(canvas, "Inverter Moldes: nada válido para inverter.")
            return

        tipo = dialog.cmb_tipo.currentText()
        criar_copia = dialog.chk_criar_copia.isChecked()
        atualizar_flags = dialog.chk_atualizar_flags.isChecked()
        referencia_modo = dialog.cmb_referencia.currentText()

        if criar_copia:
            novos = [deepcopy(canvas.cena.elementos[i]) for i in indices]
            self._renovar_ids_e_vinculos(novos)
            self._inverter_conjunto(novos, tipo, referencia_modo, atualizar_flags)
            inicio = len(canvas.cena.elementos)
            canvas.cena.elementos.extend(novos)
            resultado = list(range(inicio, inicio + len(novos)))
        else:
            elementos = [canvas.cena.elementos[i] for i in indices]
            self._inverter_conjunto(elementos, tipo, referencia_modo, atualizar_flags)
            resultado = indices

        if dialog.chk_preservar_selecao.isChecked():
            # Mantém selecionados apenas moldes principais quando possível.
            principais = [i for i in resultado if 0 <= i < len(canvas.cena.elementos) and canvas.cena.elementos[i].get("molde")]
            canvas._selecionados = set(principais or resultado)
        else:
            canvas._selecionados = set()

        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        if hasattr(canvas, "elementos_alterados"):
            try:
                canvas.elementos_alterados.emit()
            except Exception:
                pass
        canvas.update()

        self._operacao_finalizada = True
        self._direito_confirma_fechamento = False
        acao = "cópia invertida criada" if criar_copia else "inversão aplicada"
        self._status(canvas, f"Inverter Moldes: {acao} em {len(indices_base)} item(ns). Clique esquerdo continua; direito fecha.")

    def _inverter_conjunto(
        self,
        elementos: list[dict],
        tipo: str,
        referencia_modo: str,
        atualizar_flags: bool,
    ) -> None:
        if referencia_modo == "Centro de cada molde":
            for el in elementos:
                ref = self._centro_elemento(el)
                if ref is not None:
                    self._inverter_elemento(el, tipo, ref, atualizar_flags)
            return

        ref = self._referencia_conjunto(elementos, referencia_modo)
        if ref is None:
            return
        for el in elementos:
            self._inverter_elemento(el, tipo, ref, atualizar_flags)

    def _referencia_conjunto(self, elementos: list[dict], modo: str) -> QPointF | None:
        if modo == "Último clique" and self._ultimo_clique is not None:
            return QPointF(self._ultimo_clique)
        if modo == "Origem 0,0":
            return QPointF(0.0, 0.0)
        bbox = self._bbox_elementos(elementos)
        if bbox is None:
            return None
        min_x, min_y, max_x, max_y = bbox
        return QPointF((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    def _centro_elemento(self, el: dict) -> QPointF | None:
        pontos = self._todos_pontos(el)
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    def _bbox_elementos(self, elementos: list[dict]) -> tuple[float, float, float, float] | None:
        pontos: list[tuple[float, float]] = []
        for el in elementos:
            pontos.extend(self._todos_pontos(el))
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    def _inverter_elemento(self, el: dict, tipo: str, ref: QPointF, atualizar_flags: bool) -> None:
        inverter_x = tipo in {"Horizontal", "Horizontal e vertical"}
        inverter_y = tipo in {"Vertical", "Horizontal e vertical"}

        def conv_ponto(p):
            x = float(p[0])
            y = float(p[1])
            if inverter_x:
                x = (2.0 * ref.x()) - x
            if inverter_y:
                y = (2.0 * ref.y()) - y
            if isinstance(p, list):
                return [x, y, *p[2:]]
            return (x, y, *p[2:])

        for chave in (
            "pontos",
            "controle_cantos",
            "controle_auxiliares",
            "marcacoes_no_perimetro",
            "distancias_no_perimetro",
            "marcacoes_perimetro",
        ):
            if isinstance(el.get(chave), list):
                el[chave] = [conv_ponto(p) if self._eh_ponto(p) else p for p in el.get(chave, [])]

        for chave in (
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
        ):
            if self._eh_ponto(el.get(chave)):
                el[chave] = conv_ponto(el.get(chave))

        for chave in ("pontos_controle_principais", "pontos_auxiliares"):
            if isinstance(el.get(chave), list):
                for item in el[chave]:
                    if isinstance(item, dict) and self._numero(item.get("x")) and self._numero(item.get("y")):
                        x, y = conv_ponto((item["x"], item["y"]))[:2]
                        item["x"] = x
                        item["y"] = y

        for chave in (
            "estado_dobra",
            "contornos_dobra_original",
            "dobra_eixo",
            "ponto_restauracao",
            "pontos_restauracao",
            "restauracao",
        ):
            if chave in el:
                el[chave] = self._transformar_valor_recursivo(el.get(chave), conv_ponto)

        if atualizar_flags:
            if inverter_x:
                el["refletido_horizontal"] = not bool(el.get("refletido_horizontal", False))
                if "chk_reflete_h" in el:
                    el["chk_reflete_h"] = not bool(el.get("chk_reflete_h", False))
            if inverter_y:
                el["refletido_vertical"] = not bool(el.get("refletido_vertical", False))
                if "chk_reflete_v" in el:
                    el["chk_reflete_v"] = not bool(el.get("chk_reflete_v", False))

        meta = el.setdefault("metadados", {})
        if isinstance(meta, dict):
            meta["ultima_transformacao"] = f"inverter_moldes:{tipo}"

    def _transformar_valor_recursivo(self, valor, conv_ponto):
        if isinstance(valor, dict):
            novo = dict(valor)
            if self._numero(novo.get("x")) and self._numero(novo.get("y")):
                x, y = conv_ponto((novo["x"], novo["y"]))[:2]
                novo["x"] = x
                novo["y"] = y
                return novo
            for chave, item in list(novo.items()):
                if self._chave_com_pontos(chave):
                    novo[chave] = self._transformar_valor_recursivo(item, conv_ponto)
            return novo

        if isinstance(valor, list):
            if self._eh_ponto(valor):
                return conv_ponto(valor)
            return [self._transformar_valor_recursivo(item, conv_ponto) for item in valor]

        if isinstance(valor, tuple):
            if self._eh_ponto(valor):
                return conv_ponto(valor)
            return tuple(self._transformar_valor_recursivo(item, conv_ponto) for item in valor)

        return valor

    @staticmethod
    def _chave_com_pontos(chave: object) -> bool:
        txt = str(chave or "").lower()
        return any(
            termo in txt
            for termo in (
                "ponto",
                "pontos",
                "contorno",
                "controle",
                "marcacao",
                "marcação",
                "dobra",
                "eixo",
                "origem",
                "fim",
                "posicao",
                "posição",
                "seta",
                "fio",
            )
        )

    def _indices_validos(self, canvas) -> list[int]:
        indices = []
        for i in sorted(getattr(canvas, "_selecionados", set()) or []):
            try:
                idx = int(i)
            except Exception:
                continue
            if 0 <= idx < len(canvas.cena.elementos):
                indices.append(idx)
        return indices

    def _indices_com_vinculos(self, canvas, selecionados: list[int]) -> list[int]:
        indices = set(selecionados)

        for idx in list(selecionados):
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("molde") and hasattr(canvas, "_indices_costuras_vinculadas"):
                try:
                    indices.update(int(i) for i in canvas._indices_costuras_vinculadas(idx))
                except Exception:
                    pass

            molde_id = self._molde_id(el)
            if molde_id and el.get("molde"):
                for j, outro in enumerate(canvas.cena.elementos):
                    if j in indices:
                        continue
                    if self._linha_vinculada_ao_molde(outro, molde_id):
                        indices.add(j)

        return sorted(i for i in indices if 0 <= i < len(canvas.cena.elementos))

    def _renovar_ids_e_vinculos(self, elementos: list[dict]) -> None:
        mapa_molde: dict[str, str] = {}

        for el in elementos:
            mid = self._molde_id(el)
            if mid and (el.get("molde") or el.get("costura_de_molde_id") or el.get("molde_linha_vinculada")):
                mapa_molde.setdefault(mid, str(uuid4()))
            costura_mid = str(el.get("costura_de_molde_id") or "").strip()
            if costura_mid:
                mapa_molde.setdefault(costura_mid, str(uuid4()))

        for el in elementos:
            if str(el.get("id") or "").strip():
                el["id"] = str(uuid4())

            mid_antigo = self._molde_id(el)
            if mid_antigo:
                el["molde_id"] = mapa_molde.get(mid_antigo, str(uuid4()) if el.get("molde") else mid_antigo)

            costura_mid = str(el.get("costura_de_molde_id") or "").strip()
            if costura_mid:
                novo_mid = mapa_molde.get(costura_mid, costura_mid)
                el["costura_de_molde_id"] = novo_mid
                el["molde_id"] = novo_mid
                el["molde_linha_vinculada"] = True
                el["parte_do_molde"] = True

            if bool(el.get("molde_linha_vinculada")):
                mid = str(el.get("molde_id") or "").strip()
                if mid in mapa_molde:
                    el["molde_id"] = mapa_molde[mid]
                el["parte_do_molde"] = True

            meta = el.get("metadados")
            if isinstance(meta, dict):
                if "id" in meta:
                    meta["id"] = str(uuid4())
                for chave in ("molde_id", "costura_de_molde_id"):
                    valor = str(meta.get(chave) or "").strip()
                    if valor in mapa_molde:
                        meta[chave] = mapa_molde[valor]

    def _todos_pontos(self, el: dict) -> list[tuple[float, float]]:
        pontos: list[tuple[float, float]] = []
        for chave in (
            "pontos",
            "controle_cantos",
            "controle_auxiliares",
            "marcacoes_no_perimetro",
            "distancias_no_perimetro",
            "marcacoes_perimetro",
        ):
            if isinstance(el.get(chave), list):
                for p in el.get(chave, []):
                    if self._eh_ponto(p):
                        pontos.append((float(p[0]), float(p[1])))

        for chave in (
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
        ):
            if self._eh_ponto(el.get(chave)):
                p = el[chave]
                pontos.append((float(p[0]), float(p[1])))

        for chave in (
            "estado_dobra",
            "contornos_dobra_original",
            "dobra_eixo",
            "ponto_restauracao",
            "pontos_restauracao",
            "restauracao",
        ):
            pontos.extend(self._coletar_pontos_recursivo(el.get(chave)))

        return pontos

    def _coletar_pontos_recursivo(self, valor) -> list[tuple[float, float]]:
        pontos: list[tuple[float, float]] = []
        if isinstance(valor, dict):
            if self._numero(valor.get("x")) and self._numero(valor.get("y")):
                pontos.append((float(valor["x"]), float(valor["y"])))
            for chave, item in valor.items():
                if self._chave_com_pontos(chave):
                    pontos.extend(self._coletar_pontos_recursivo(item))
        elif isinstance(valor, (list, tuple)):
            if self._eh_ponto(valor):
                pontos.append((float(valor[0]), float(valor[1])))
            else:
                for item in valor:
                    pontos.extend(self._coletar_pontos_recursivo(item))
        return pontos

    @staticmethod
    def _linha_vinculada_ao_molde(elemento: dict, molde_id: str) -> bool:
        if not molde_id:
            return False
        if str(elemento.get("costura_de_molde_id") or "").strip() == molde_id:
            return True
        if bool(elemento.get("molde_linha_vinculada")) and str(elemento.get("molde_id") or "").strip() == molde_id:
            return True
        return False

    @staticmethod
    def _molde_id(elemento: dict) -> str:
        return str(elemento.get("molde_id") or elemento.get("id") or "").strip()

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False

    @staticmethod
    def _numero(valor) -> bool:
        try:
            return isfinite(float(valor))
        except Exception:
            return False

    def _fechar(self, canvas) -> None:
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        self._status(canvas, "Ferramenta Inverter Moldes finalizada. Voltando para Selecionar.")

    def _status(self, canvas, texto: str) -> None:
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.atualizar_status(texto)
        try:
            if getattr(canvas, "lbl_status", None) is not None:
                canvas.lbl_status.setText(texto)
        except Exception:
            pass
        try:
            self.set_status(texto)
        except Exception:
            pass
