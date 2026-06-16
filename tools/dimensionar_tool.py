from __future__ import annotations

from copy import deepcopy
from math import isclose

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from tools.tool_base import FerramentaBase
from tools.dialog_lifetime import limpar_global_ao_destruir, qobject_valido
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class DimensionarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DimensionarDialog")
        self.setWindowTitle("Dimensionar")
        self.setWindowFlags(Qt.Tool)
        self.setFixedWidth(270)
        self._sincronizando = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(10, 10, 10, 10)
        raiz.setSpacing(8)

        titulo = QLabel("Escala da selecao")
        titulo.setObjectName("titulo")
        raiz.addWidget(titulo)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        self.spn_x = self._spin_percentual()
        self.spn_y = self._spin_percentual()
        self.chk_proporcional = QCheckBox("Manter proporcao")
        self.chk_proporcional.setChecked(True)
        self.cmb_pivo = QComboBox()
        self.cmb_pivo.addItems(["Centro da selecao", "Origem do desenho"])

        form.addRow("Largura", self.spn_x)
        form.addRow("Altura", self.spn_y)
        form.addRow("", self.chk_proporcional)
        form.addRow("Pivo", self.cmb_pivo)
        raiz.addLayout(form)

        botoes = QHBoxLayout()
        botoes.setContentsMargins(0, 0, 0, 0)
        botoes.setSpacing(6)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_aplicar = QPushButton("Aplicar")
        self.btn_aplicar.setDefault(True)
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_aplicar.clicked.connect(self.accept)
        botoes.addStretch(1)
        botoes.addWidget(self.btn_cancelar)
        botoes.addWidget(self.btn_aplicar)
        raiz.addLayout(botoes)

        self.spn_x.valueChanged.connect(self._x_alterado)
        self.spn_y.valueChanged.connect(self._y_alterado)

        self.setStyleSheet(
            """
            QDialog#DimensionarDialog { background:#eef7f9; }
            QLabel { color:#16202a; font-size:11px; }
            QLabel#titulo { font-weight:600; font-size:12px; }
            QDoubleSpinBox, QComboBox {
                background:#ffffff;
                border:1px solid #aeb8c2;
                border-radius:3px;
                min-height:22px;
                padding:2px 4px;
                font-size:11px;
            }
            QCheckBox { color:#16202a; font-size:11px; }
            QPushButton {
                background:#f8fbfd;
                border:1px solid #aeb8c2;
                border-radius:4px;
                min-height:23px;
                padding:2px 10px;
                font-size:11px;
            }
            QPushButton:hover { background:#d9efff; border-color:#77a8cc; }
            QPushButton:pressed { background:#bfe3ff; }
            """
        )

    def valores(self) -> tuple[float, float, str]:
        return float(self.spn_x.value()), float(self.spn_y.value()), self.cmb_pivo.currentText()

    def resetar_escala(self) -> None:
        self._sincronizando = True
        try:
            self.spn_x.setValue(100.0)
            self.spn_y.setValue(100.0)
        finally:
            self._sincronizando = False

    def _x_alterado(self, valor: float) -> None:
        if self._sincronizando or not self.chk_proporcional.isChecked():
            return
        self._sincronizando = True
        self.spn_y.setValue(float(valor))
        self._sincronizando = False

    def _y_alterado(self, valor: float) -> None:
        if self._sincronizando or not self.chk_proporcional.isChecked():
            return
        self._sincronizando = True
        self.spn_x.setValue(float(valor))
        self._sincronizando = False

    @staticmethod
    def _spin_percentual() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(1.0, 10000.0)
        spin.setDecimals(2)
        spin.setSingleStep(5.0)
        spin.setSuffix(" %")
        spin.setValue(100.0)
        return spin


class Ferramenta(FerramentaBase):
    id_ferramenta = "dimensionar"
    nome = "Dimensionar"
    usa_painel_auxiliar = False
    descricao_painel = "Escala a selecao preservando os dados existentes do molde."
    _dialog_global: DimensionarDialog | None = None

    def on_activate(self, canvas) -> None:
        super().on_activate(canvas)
        if self._indices_selecionados(canvas):
            self._abrir_dialogo(canvas)
            return
        self._status(canvas, "Dimensionar: selecione um molde/elemento ou clique em um para dimensionar.")

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._finalizar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = self._posicao_cena(canvas, event)
        idx = self._indice_elemento_em_ponto(canvas, pos)
        if idx is None:
            self._status(canvas, "Nenhum elemento encontrado no clique.")
            event.accept()
            return True
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {idx}
        if hasattr(canvas, "update"):
            canvas.update()
        self._abrir_dialogo(canvas, pos)
        event.accept()
        return True

    def _abrir_dialogo(self, canvas, pos_cena: QPointF | None = None) -> None:
        dialog = self._dialogo(canvas)
        dialog.resetar_escala()
        self._reposicionar_dialogo(canvas, dialog, pos_cena)
        if dialog.exec() != QDialog.Accepted:
            self._status(canvas, "Dimensionar cancelado.")
            return
        escala_x_pct, escala_y_pct, pivo_modo = dialog.valores()
        if self._dimensionar_selecao(canvas, escala_x_pct, escala_y_pct, pivo_modo=pivo_modo):
            self._status(canvas, f"Dimensionado: largura {escala_x_pct:g}% | altura {escala_y_pct:g}%.")
        else:
            self._status(canvas, "Dimensionar: nada foi alterado.")

    def _dimensionar_selecao(
        self,
        canvas,
        escala_x_pct: float,
        escala_y_pct: float,
        *,
        pivo_modo: str = "Centro da selecao",
    ) -> bool:
        if canvas is None or not hasattr(canvas, "cena"):
            return False
        sx = float(escala_x_pct) / 100.0
        sy = float(escala_y_pct) / 100.0
        if sx <= 0.0 or sy <= 0.0:
            return False
        if isclose(sx, 1.0, abs_tol=1e-12) and isclose(sy, 1.0, abs_tol=1e-12):
            return False
        indices = self._indices_para_dimensionar(canvas)
        if not indices:
            return False
        elementos = [canvas.cena.elementos[idx] for idx in indices if 0 <= idx < len(canvas.cena.elementos)]
        pivo = self._pivo_elementos(elementos, pivo_modo)
        antes = deepcopy(elementos)
        for el in elementos:
            self._dimensionar_elemento(el, sx, sy, pivo)
        if antes == elementos:
            return False
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        if hasattr(canvas, "elementos_alterados"):
            try:
                canvas.elementos_alterados.emit()
            except Exception:
                pass
        if hasattr(canvas, "update"):
            canvas.update()
        return True

    def _indices_para_dimensionar(self, canvas) -> list[int]:
        indices = set(self._indices_selecionados(canvas))
        if hasattr(canvas, "_indices_transformacao_com_vinculados"):
            return list(canvas._indices_transformacao_com_vinculados(indices))
        elementos = list(getattr(canvas.cena, "elementos", []) or [])
        for idx in list(indices):
            if not (0 <= idx < len(elementos)):
                continue
            el = elementos[idx]
            if isinstance(el, dict) and el.get("molde"):
                if hasattr(canvas, "_indices_costuras_vinculadas"):
                    try:
                        indices.update(int(i) for i in canvas._indices_costuras_vinculadas(idx))
                    except Exception:
                        pass
                molde_id = self._molde_id(el)
                if molde_id:
                    for outro_idx, outro in enumerate(elementos):
                        if outro_idx in indices or not isinstance(outro, dict):
                            continue
                        if self._linha_vinculada_ao_molde(outro, molde_id):
                            indices.add(outro_idx)
        return sorted(i for i in indices if 0 <= i < len(elementos))

    def _pivo_elementos(self, elementos: list[dict], pivo_modo: str) -> QPointF:
        if str(pivo_modo or "").lower().startswith("origem"):
            return QPointF(0.0, 0.0)
        pontos: list[tuple[float, float]] = []
        for el in elementos:
            pontos.extend(self._coletar_pontos(el))
        if not pontos:
            return QPointF(0.0, 0.0)
        min_x = min(x for x, _y in pontos)
        max_x = max(x for x, _y in pontos)
        min_y = min(y for _x, y in pontos)
        max_y = max(y for _x, y in pontos)
        return QPointF((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    def _dimensionar_elemento(self, el: dict, sx: float, sy: float, pivo: QPointF) -> None:
        if not isinstance(el, dict):
            return
        for chave in self._CHAVES_LISTAS_PONTOS:
            if chave in el:
                el[chave] = self._dimensionar_lista_ou_mapa_pontos(el.get(chave), sx, sy, pivo)
        for chave in self._CHAVES_PONTOS_SOLTOS:
            if chave in el:
                el[chave] = self._dimensionar_ponto(el.get(chave), sx, sy, pivo)
        if isinstance(el.get("piques_config"), list):
            el["piques_config"] = self._dimensionar_piques(el.get("piques_config"), sx, sy, pivo)
        self._dimensionar_graduacao(el, sx, sy, pivo)
        for chave in (
            "estado_dobra",
            "contornos_dobra_original",
            "dobra_eixo",
            "ponto_restauracao",
            "pontos_restauracao",
            "restauracao",
        ):
            if chave in el:
                el[chave] = self._dimensionar_estrutura_pontos(el.get(chave), sx, sy, pivo)

    def _dimensionar_piques(self, piques, sx: float, sy: float, pivo: QPointF):
        escala_media = (abs(float(sx)) + abs(float(sy))) / 2.0
        saida = []
        for cfg in piques or []:
            if not isinstance(cfg, dict):
                saida.append(cfg)
                continue
            novo = self._dimensionar_estrutura_pontos(cfg, sx, sy, pivo)
            if isinstance(novo, dict):
                self._multiplicar_numero(novo, "largura_cm", escala_media)
                self._multiplicar_numero(novo, "altura_cm", escala_media)
                self._multiplicar_numero(novo, "texto_altura_cm", escala_media)
                self._multiplicar_numero(novo, "dx_cm", sx)
                self._multiplicar_numero(novo, "dy_cm", sy)
                self._multiplicar_numero(novo, "texto_dx_cm", sx)
                self._multiplicar_numero(novo, "texto_dy_cm", sy)
            saida.append(novo)
        return saida

    def _dimensionar_graduacao(self, el: dict, sx: float, sy: float, pivo: QPointF) -> None:
        vistos: set[int] = set()

        def dimensionar_pontos_cfg(pontos_cfg):
            if not isinstance(pontos_cfg, dict):
                return
            for cfg in pontos_cfg.values():
                if not isinstance(cfg, dict) or id(cfg) in vistos:
                    continue
                vistos.add(id(cfg))
                if "ponto" in cfg:
                    cfg["ponto"] = self._dimensionar_ponto(cfg.get("ponto"), sx, sy, pivo)
                valores = cfg.get("valores")
                if isinstance(valores, dict):
                    for dados_tamanho in valores.values():
                        if not isinstance(dados_tamanho, dict):
                            continue
                        self._multiplicar_numero(dados_tamanho, "dx", sx)
                        self._multiplicar_numero(dados_tamanho, "dy", sy)

        tabela = el.get("graduacao_tabela")
        if isinstance(tabela, dict):
            dimensionar_pontos_cfg(tabela.get("pontos"))
        dimensionar_pontos_cfg(el.get("graduacao_pontos"))

    def _dimensionar_lista_ou_mapa_pontos(self, valor, sx: float, sy: float, pivo: QPointF):
        if isinstance(valor, dict):
            return {chave: self._dimensionar_ponto(ponto, sx, sy, pivo) for chave, ponto in valor.items()}
        if isinstance(valor, list):
            return [self._dimensionar_ponto(ponto, sx, sy, pivo) for ponto in valor]
        if isinstance(valor, tuple):
            return tuple(self._dimensionar_ponto(ponto, sx, sy, pivo) for ponto in valor)
        return valor

    def _dimensionar_estrutura_pontos(self, valor, sx: float, sy: float, pivo: QPointF):
        if self._eh_ponto_serializado(valor):
            return self._dimensionar_ponto(valor, sx, sy, pivo)
        if isinstance(valor, dict):
            novo = dict(valor)
            for chave, item in list(novo.items()):
                chave_txt = str(chave or "").lower()
                if chave_txt in self._CHAVES_NUMERICAS_SEM_COORDENADA:
                    continue
                if self._chave_com_pontos(chave_txt) or isinstance(item, (dict, list, tuple)):
                    novo[chave] = self._dimensionar_estrutura_pontos(item, sx, sy, pivo)
            return novo
        if isinstance(valor, list):
            return [self._dimensionar_estrutura_pontos(item, sx, sy, pivo) for item in valor]
        if isinstance(valor, tuple):
            return tuple(self._dimensionar_estrutura_pontos(item, sx, sy, pivo) for item in valor)
        return valor

    def _dimensionar_ponto(self, valor, sx: float, sy: float, pivo: QPointF):
        try:
            if isinstance(valor, QPointF):
                return QPointF(pivo.x() + ((valor.x() - pivo.x()) * sx), pivo.y() + ((valor.y() - pivo.y()) * sy))
            if isinstance(valor, dict) and "x" in valor and "y" in valor:
                novo = dict(valor)
                novo["x"] = pivo.x() + ((float(valor["x"]) - pivo.x()) * sx)
                novo["y"] = pivo.y() + ((float(valor["y"]) - pivo.y()) * sy)
                return novo
            if isinstance(valor, list) and len(valor) >= 2:
                return [
                    pivo.x() + ((float(valor[0]) - pivo.x()) * sx),
                    pivo.y() + ((float(valor[1]) - pivo.y()) * sy),
                    *valor[2:],
                ]
            if isinstance(valor, tuple) and len(valor) >= 2:
                return (
                    pivo.x() + ((float(valor[0]) - pivo.x()) * sx),
                    pivo.y() + ((float(valor[1]) - pivo.y()) * sy),
                    *valor[2:],
                )
        except Exception:
            return valor
        return valor

    def _coletar_pontos(self, valor) -> list[tuple[float, float]]:
        pontos: list[tuple[float, float]] = []
        if self._eh_ponto_serializado(valor):
            ponto = self._tupla_ponto(valor)
            if ponto is not None:
                pontos.append(ponto)
            return pontos
        if isinstance(valor, dict):
            for chave, item in valor.items():
                chave_txt = str(chave or "").lower()
                if chave_txt in self._CHAVES_NUMERICAS_SEM_COORDENADA:
                    continue
                if self._chave_com_pontos(chave_txt) or isinstance(item, (dict, list, tuple)):
                    pontos.extend(self._coletar_pontos(item))
        elif isinstance(valor, (list, tuple)):
            for item in valor:
                pontos.extend(self._coletar_pontos(item))
        return pontos

    def _indice_elemento_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indices_elementos_em_ponto"):
            try:
                indices = list(canvas._indices_elementos_em_ponto(pos) or [])
                if indices:
                    return int(indices[0])
            except Exception:
                pass
        if hasattr(canvas, "_indice_molde_em_ponto"):
            try:
                idx = canvas._indice_molde_em_ponto(pos)
                if idx is not None:
                    return int(idx)
            except Exception:
                pass
        return None

    def _dialogo(self, canvas) -> DimensionarDialog:
        cls = type(self)
        if not qobject_valido(cls._dialog_global):
            cls._dialog_global = DimensionarDialog(canvas)
            instalar_memoria_posicao(cls._dialog_global, "dialog:dimensionar")
            limpar_global_ao_destruir(cls._dialog_global, cls, "_dialog_global")
        dialog = cls._dialog_global
        if not qobject_valido(dialog):
            dialog = DimensionarDialog(canvas)
            cls._dialog_global = dialog
            instalar_memoria_posicao(dialog, "dialog:dimensionar")
            limpar_global_ao_destruir(dialog, cls, "_dialog_global")
        if dialog.parentWidget() is not canvas:
            dialog.setParent(canvas)
        return dialog

    def _reposicionar_dialogo(self, canvas, dialog: DimensionarDialog, pos_cena: QPointF | None = None) -> None:
        fallback = None
        if pos_cena is not None and hasattr(canvas, "_cena_para_tela") and hasattr(canvas, "mapToGlobal"):
            tela = canvas._cena_para_tela(pos_cena)
            fallback = canvas.mapToGlobal(QPoint(int(tela.x()) + 14, int(tela.y()) + 14))
        elif hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos)
        restaurar_posicao(dialog, "dialog:dimensionar", fallback=fallback)

    def _posicao_cena(self, canvas, event) -> QPointF:
        try:
            return QPointF(canvas._ponto_com_snap(event.position()))
        except Exception:
            if hasattr(canvas, "_tela_para_cena"):
                return QPointF(canvas._tela_para_cena(event.position()))
            return QPointF(event.position())

    def _indices_selecionados(self, canvas) -> list[int]:
        if canvas is None or not hasattr(canvas, "cena"):
            return []
        elementos = list(getattr(canvas.cena, "elementos", []) or [])
        indices = sorted(int(i) for i in (getattr(canvas, "_selecionados", set()) or set()))
        return [idx for idx in indices if 0 <= idx < len(elementos)]

    def _finalizar(self, canvas) -> None:
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        elif hasattr(canvas, "ferramenta_padrao_solicitada"):
            try:
                canvas.ferramenta_padrao_solicitada.emit("selecionar")
            except Exception:
                pass
        if hasattr(canvas, "update"):
            canvas.update()
        self._status(canvas, "Ferramenta Dimensionar finalizada.")

    def _status(self, canvas, texto: str) -> None:
        try:
            if getattr(canvas, "lbl_status", None) is not None:
                canvas.lbl_status.setText(texto)
                return
        except Exception:
            pass
        try:
            self.set_status(texto)
        except Exception:
            pass

    @staticmethod
    def _molde_id(elemento: dict) -> str:
        return str(elemento.get("molde_id") or elemento.get("id") or "").strip()

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
    def _multiplicar_numero(dados: dict, chave: str, fator: float) -> None:
        try:
            if chave in dados:
                dados[chave] = float(dados[chave]) * float(fator)
        except Exception:
            pass

    @staticmethod
    def _tupla_ponto(valor) -> tuple[float, float] | None:
        try:
            if isinstance(valor, QPointF):
                return float(valor.x()), float(valor.y())
            if isinstance(valor, dict) and "x" in valor and "y" in valor:
                return float(valor["x"]), float(valor["y"])
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return float(valor[0]), float(valor[1])
        except Exception:
            return None
        return None

    @classmethod
    def _eh_ponto_serializado(cls, valor) -> bool:
        return cls._tupla_ponto(valor) is not None

    @staticmethod
    def _chave_com_pontos(chave: str) -> bool:
        return any(
            termo in chave
            for termo in (
                "ponto",
                "pontos",
                "contorno",
                "controle",
                "marcacao",
                "marcação",
                "segmento",
                "segmentos",
                "pique",
                "piques",
                "origem",
                "fim",
                "posicao",
                "posição",
                "seta",
                "fio",
                "eixo",
            )
        )

    _CHAVES_LISTAS_PONTOS = (
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
    _CHAVES_PONTOS_SOLTOS = (
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
    _CHAVES_NUMERICAS_SEM_COORDENADA = {
        "valores",
        "valor",
        "dx",
        "dy",
        "largura",
        "altura",
        "largura_cm",
        "altura_cm",
        "texto_dx_cm",
        "texto_dy_cm",
        "texto_altura_cm",
        "angulo",
    }
