from __future__ import annotations

import base64
from copy import deepcopy
from importlib import import_module
from math import atan2, cos, degrees, log10, radians, sin, sqrt
from time import monotonic
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFontMetrics, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, \
    QPolygon, QWheelEvent
from PySide6.QtWidgets import QMenu, QWidget

from canvas.cena import CenaDocumento
from canvas.painel_coordenadas import PainelCoordenadas
from canvas.snap import SnapManager, SnapResult
from core.line_styles import dash_pattern_for_line, is_geometric_line_style, pen_style_for_line


class VisualizacaoCanvas(QWidget):
    zoom_changed = Signal(float)
    ferramenta_padrao_solicitada = Signal(str)
    snap_changed = Signal(bool)
    painel_coordenadas_changed = Signal(bool)
    painel_posicao_changed = Signal(int, int)

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.cena = cena
        self.zoom = 1.0
        self.origem_cena = QPointF(0.0, 0.0)
        self.ferramenta_ativa: str | None = None
        self._pontos_reta: list[QPointF] = []
        self._preview_reta: QPointF | None = None
        self._marcacoes_temporarias: list[QPointF] = []
        self._ponto_coordenada_aplicada: QPointF | None = None
        self._cursor_tela = QPointF(0.0, 0.0)
        self._historico_elementos: list[list[dict]] = [[]]
        self._indice_historico = 0
        self._buffer_copia: dict | None = None
        self._offset_colagem = 0
        self._selecionados: set[int] = set()
        self._inicio_selecao: QPointF | None = None
        self._fim_selecao: QPointF | None = None
        self._arrastando_selecao = False
        self._ultimo_ponto_arrasto: QPointF | None = None
        self._moveu_selecao = False
        self._painel_coordenadas_posicao: tuple[int, int] | None = None
        self._painel_coordenadas_visivel = True
        self._aguardando_retorno_selecao = False
        self._cliques_direito_reta = 0
        self._snap_manager = SnapManager()
        self._snap_ativo = True
        self._snap_resultado: SnapResult | None = None
        self._snap_candidatos: list[SnapResult] = []
        self._snap_indice = 0
        self._guia_fechamento: tuple[QPointF, QPointF] | None = None
        self._guias_alinhamento: list[tuple[QPointF, QPointF]] = []
        self._linha_cor = "#ffffff"
        self._cores_tecidos: dict[str, str] = {}
        self._mostrar_cor_tecidos = False
        self._linha_estilo = "solid"
        self._linha_espessura = 1.0
        self._linha_amplitude = 1.0
        self._unidade_sigla = "cm"
        self._unidade_fator = 1.0  # 1 unidade de cena = 1 cm
        self._unidade_quadrado_sigla = "m"
        self._unidade_quadrado_fator = 100.0  # 1 m = 100 cm de cena
        self._precisao_medida = "0.01"
        self._casas_precisao = 2
        self._snap_angular_passo = 45.0
        self._snap_contextual_ativo = True
        self._tecla_w_trava_principal = False
        self._extensao_origem: tuple[int, bool] | None = None
        self._segmento_primeira_reta: tuple[int, int] | None = None
        self._curva_estado = "parada"
        self._curva_p0: QPointF | None = None
        self._curva_p2: QPointF | None = None
        self._curva_p1: QPointF | None = None
        self._curva_preview_fim: QPointF | None = None
        self._curva_pmedio: QPointF | None = None
        self._modo_curva = "np"
        self._cliques_direito_curva = 0
        self._arrastando_alca_curva: tuple[int, str] | None = None
        self._ciclo_selecao_indices: list[int] = []
        self._ciclo_selecao_cursor: QPointF | None = None
        self._retangulo_inicio: QPointF | None = None
        self._retangulo_preview: QPointF | None = None
        self._retangulo_criar_molde = True
        self._arrastando_ponto_poly: tuple[int, int] | None = None
        self._hover_ponto_poly: tuple[int, int] | None = None
        self._guia_ponto_poly: tuple[QPointF, QPointF | None, QPointF | None] | None = None
        self._runtime_tool = None
        self._destacar_reta_temporaria: tuple[QPointF, QPointF] | None = None  # Para ferramenta reta
        self._ultimo_clique_direito_ts = 0.0
        self._sequencia_clique_direito = 0
        self.lbl_status = None  # Será definido pela janela principal
        self._imagem_cache: dict[str, QPixmap] = {}

        self.setMinimumSize(100, 100)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.painel_coordenadas = PainelCoordenadas(self)
        self.painel_coordenadas.desfazer_ponto.connect(self._desfazer_ponto)
        self.painel_coordenadas.aplicar.connect(self._aplicar_coordenadas)
        self.painel_coordenadas.alternado.connect(self._set_painel_coordenadas_visivel)
        self.painel_coordenadas.posicao_alterada.connect(self._registrar_posicao_painel)
        self.painel_coordenadas.set_unidade_medida(self._unidade_sigla, self._unidade_fator)
        self.painel_coordenadas.show()

    def set_zoom(self, zoom: float):
        self.zoom = max(0.025, min(zoom, 10000.0))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def set_ferramenta_ativa(self, tool_id: str):
        if self._runtime_tool and hasattr(self._runtime_tool, "on_deactivate"):
            self._runtime_tool.on_deactivate(self)
        self.ferramenta_ativa = tool_id
        self._runtime_tool = self._carregar_runtime_ferramenta(tool_id)
        if self._runtime_tool and hasattr(self._runtime_tool, "on_activate"):
            self._runtime_tool.on_activate(self)
        self._aguardando_retorno_selecao = False
        self._cliques_direito_reta = 0
        self._sequencia_clique_direito = 0
        self._snap_resultado = None
        self._snap_candidatos = []
        self._snap_indice = 0
        if tool_id in {"reta", "curva"}:
            if self._painel_coordenadas_visivel:
                self.painel_coordenadas.show()
            self._reposicionar_painel_coordenadas()
            if tool_id == "curva":
                self._pontos_reta.clear()
                self._preview_reta = None
                self._guia_fechamento = None
                self._guias_alinhamento = []
                self._cliques_direito_curva = 0
        else:
            self._pontos_reta.clear()
            self._preview_reta = None
            self._guia_fechamento = None
            self._guias_alinhamento = []
        if tool_id != "curva":
            self._resetar_estado_curva()
        if tool_id not in {"estender_reta", "estender_ate_elemento"}:
            self._extensao_origem = None
        if tool_id != "estender_duas_retas":
            self._segmento_primeira_reta = None
        if tool_id != "retangulo":
            self._retangulo_inicio = None
            self._retangulo_preview = None
        if tool_id != "manipular_pontos":
            self._arrastando_ponto_poly = None
            self._hover_ponto_poly = None
            self._guia_ponto_poly = None
        self.update()

    def _carregar_runtime_ferramenta(self, tool_id: str):
        try:
            module = import_module(f"tools.{tool_id}_tool")
            tool_cls = getattr(module, "Ferramenta")
            return tool_cls()
        except Exception:
            return None

    # ========== Métodos públicos ==========

    def snap_ativo(self) -> bool:
        return self._snap_ativo

    def set_snap_ativo(self, ativo: bool):
        self._snap_ativo = ativo
        if not ativo:
            self._snap_resultado = None
            self._snap_candidatos = []
            self._snap_indice = 0
        self.snap_changed.emit(ativo)
        self.update()

    def painel_coordenadas_visivel(self) -> bool:
        return self._painel_coordenadas_visivel

    def definir_painel_coordenadas_visivel(self, visivel: bool):
        self._painel_coordenadas_visivel = visivel
        if visivel:
            self.painel_coordenadas.show()
            self._reposicionar_painel_coordenadas()
        else:
            self.painel_coordenadas.hide()
        self.painel_coordenadas_changed.emit(visivel)

    def set_painel_auxiliar_posicao(self, pos: tuple[int, int] | None):
        self._painel_coordenadas_posicao = None
        self._reposicionar_painel_coordenadas()

    def sincronizar_paineis_auxiliares(self):
        """Recalcula posições dos painéis flutuantes com o tamanho atual do canvas."""
        self._reposicionar_painel_coordenadas()
        if self._runtime_tool and hasattr(self._runtime_tool, "on_canvas_resize"):
            self._runtime_tool.on_canvas_resize(self)

    def painel_auxiliar_posicao(self) -> tuple[int, int] | None:
        if self.painel_coordenadas.isVisible():
            return self.painel_coordenadas.x(), self.painel_coordenadas.y()
        return None

    def set_estilo_linha(self, cor: str | None = None, estilo: str | None = None,
                         espessura: float | None = None, amplitude: float | None = None):
        if cor:
            self._linha_cor = cor
        if estilo:
            self._linha_estilo = estilo
        if espessura is not None:
            self._linha_espessura = max(1.0, float(espessura))
        if amplitude is not None:
            self._linha_amplitude = max(0.2, float(amplitude))
        self.update()

    def set_modo_curva(self, modo: str):
        modo_txt = str(modo).lower().strip()

        if modo_txt in {"np", "n", "indefinido", "indefinidos"}:
            self._modo_curva = "np"
        elif modo_txt in {"suave", "spline", "livre"}:
            self._modo_curva = "suave"
        elif modo_txt.startswith("3"):
            self._modo_curva = "3p"
        else:
            self._modo_curva = "2p"

        self._resetar_estado_curva()

    def set_unidade_medida(self, unidade_sigla: str, fator_unidade: float):
        self._unidade_sigla = str(unidade_sigla or "cm")
        self._unidade_fator = max(1e-9, float(fator_unidade))
        if hasattr(self, "painel_coordenadas"):
            self.painel_coordenadas.set_unidade_medida(self._unidade_sigla, self._unidade_fator)

    def set_unidade_quadrado(self, unidade_sigla: str, fator_unidade: float):
        self._unidade_quadrado_sigla = str(unidade_sigla or "m")
        self._unidade_quadrado_fator = max(1e-9, float(fator_unidade))

    def set_precisao_medida(self, precisao: str):
        txt = str(precisao or "0.01").strip()
        self._precisao_medida = txt
        if "/" in txt:
            try:
                num_txt, den_txt = txt.split("/", 1)
                num = abs(float(num_txt))
                den = abs(float(den_txt))
                valor = num / max(den, 1e-9)
                self._casas_precisao = max(0, min(6, int(round(-log10(valor))) + 1))
            except Exception:
                self._casas_precisao = 2
        else:
            if "." in txt:
                self._casas_precisao = max(0, min(6, len(txt.split(".", 1)[1])))
            else:
                self._casas_precisao = 0
        if hasattr(self, "painel_coordenadas") and hasattr(self.painel_coordenadas, "set_precisao_medida"):
            self.painel_coordenadas.set_precisao_medida(self._casas_precisao)

    def converter_de_cena(self, valor: float) -> float:
        return float(valor) / self._unidade_fator

    def converter_para_cena(self, valor: float) -> float:
        return float(valor) * self._unidade_fator

    def formatar_valor_unidade(self, valor_cena: float, casas: int | None = None) -> str:
        casas_final = self._casas_precisao if casas is None else max(0, int(casas))
        valor_unidade = self.converter_de_cena(valor_cena)
        return f"{valor_unidade:.{casas_final}f}"

    def formatar_distancia(self, valor_cena: float, casas: int | None = None) -> str:
        txt = self.formatar_valor_unidade(valor_cena, casas=casas)
        return f"{txt} {self._unidade_sigla}"

    def formatar_distancia_quadrado(self, valor_cena: float, casas: int | None = None) -> str:
        casas_final = self._casas_precisao if casas is None else max(0, int(casas))
        valor_unidade = float(valor_cena) / max(self._unidade_quadrado_fator, 1e-9)
        txt = f"{valor_unidade:.{casas_final}f}"
        return f"{txt} {self._unidade_quadrado_sigla}"

    def set_passo_snap_angular(self, passo: float):
        self._snap_angular_passo = max(1.0, float(passo))

    def set_snap_contextual_ativo(self, ativo: bool):
        self._snap_contextual_ativo = bool(ativo)

    def definir_config_retangulo(self, criar_molde: bool):
        self._retangulo_criar_molde = bool(criar_molde)
        if self._runtime_tool and hasattr(self._runtime_tool, "set_criar_molde"):
            self._runtime_tool.set_criar_molde(criar_molde)

    def _elemento_serializavel(self, elemento: dict) -> dict:
        """Retorna uma cópia limpa do elemento, sem objetos Qt/runtime.

        Nunca salve QPixmap, QImage, QWidget ou caches dentro de
        self.cena.elementos. Esses objetos existem só em tempo de execução e
        quebram deepcopy/json/.gs.
        """
        if not isinstance(elemento, dict):
            return {}
        limpo = {}
        for chave, valor in elemento.items():
            nome_chave = str(chave)
            if nome_chave.startswith("_"):
                continue
            if nome_chave in {"pixmap", "qimage", "qpixmap", "imagem_qt", "_pixmap_cache"}:
                continue
            if isinstance(valor, (QPixmap, QImage)):
                continue
            try:
                limpo[chave] = deepcopy(valor)
            except Exception:
                continue
        return limpo

    def _elementos_serializaveis(self, elementos: list[dict] | None = None) -> list[dict]:
        origem = self.cena.elementos if elementos is None else elementos
        return [self._elemento_serializavel(el) for el in origem if isinstance(el, dict)]

    def _limpar_cache_runtime_elementos(self):
        """Remove caches Qt gravados acidentalmente na cena."""
        for elemento in self.cena.elementos:
            if isinstance(elemento, dict):
                for chave in list(elemento.keys()):
                    if str(chave).startswith("_") or isinstance(elemento.get(chave), (QPixmap, QImage)):
                        elemento.pop(chave, None)

    def elementos_para_salvar(self) -> list[dict]:
        self._limpar_cache_runtime_elementos()
        elementos = self._elementos_serializaveis()
        if len(self._pontos_reta) >= 2:
            fase = 0.0
            for inicio, fim in zip(self._pontos_reta, self._pontos_reta[1:]):
                comprimento = sqrt((fim.x() - inicio.x()) ** 2 + (fim.y() - inicio.y()) ** 2)
                elementos.append({
                    "tipo": "polyline",
                    "pontos": [(inicio.x(), inicio.y()), (fim.x(), fim.y())],
                    "cor": self._linha_cor,
                    "espessura": self._linha_espessura,
                    "estilo": self._linha_estilo,
                    "amplitude": self._linha_amplitude,
                    "fase_inicio": fase,
                })
                fase += comprimento
        return elementos

    def desfazer_acao(self):
        if self._pontos_reta:
            self._desfazer_ponto()
            return
        if self._indice_historico == 0:
            return
        self._indice_historico -= 1
        self.cena.elementos = self._elementos_serializaveis(self._historico_elementos[self._indice_historico])
        self.update()

    def refazer_acao(self):
        if self._indice_historico >= len(self._historico_elementos) - 1:
            return
        self._indice_historico += 1
        self.cena.elementos = self._elementos_serializaveis(self._historico_elementos[self._indice_historico])
        self.update()

    def copiar(self):
        if self._selecionados:
            self._buffer_copia = {
                "tipo": "multiplos",
                "elementos": [self._elemento_serializavel(self.cena.elementos[idx]) for idx in
                              sorted(self._selecionados)],
            }
            return
        if self._pontos_reta and len(self._pontos_reta) >= 2:
            self._buffer_copia = {
                "tipo": "polyline",
                "pontos": [(p.x(), p.y()) for p in self._pontos_reta],
                "cor": self._linha_cor,
                "espessura": self._linha_espessura,
                "estilo": self._linha_estilo,
                "amplitude": self._linha_amplitude,
                "fase_inicio": 0.0,
            }
            return
        if self.cena.elementos:
            self._buffer_copia = self._elemento_serializavel(self.cena.elementos[-1])

    def obter_buffer_copia(self) -> dict | None:
        if not self._buffer_copia:
            return None
        return self._elemento_serializavel(self._buffer_copia)

    def definir_buffer_copia(self, buffer_copia: dict | None):
        self._buffer_copia = self._elemento_serializavel(buffer_copia) if isinstance(buffer_copia, dict) else None

    def colar(self):
        if not self._buffer_copia:
            return
        self._selecionados.clear()
        itens = self._buffer_copia.get("elementos", []) if self._buffer_copia.get("tipo") == "multiplos" else [
            self._buffer_copia]
        dx, dy = self._delta_colagem_para_centro(itens)
        if self._buffer_copia.get("tipo") == "multiplos":
            for item in self._buffer_copia.get("elementos", []):
                novo = self._elemento_serializavel(item)
                self._transladar_elemento(novo, dx, dy)
                self.cena.elementos.append(novo)
                self._selecionados.add(len(self.cena.elementos) - 1)
        else:
            novo = self._elemento_serializavel(self._buffer_copia)
            self._transladar_elemento(novo, dx, dy)
            self.cena.elementos.append(novo)
            self._selecionados.add(len(self.cena.elementos) - 1)
        self._registrar_historico()
        self.update()

    def _delta_colagem_para_centro(self, elementos: list[dict]) -> tuple[float, float]:
        pontos: list[tuple[float, float]] = []
        for el in elementos:
            if el.get("tipo") == "polyline":
                pontos.extend([(float(x), float(y)) for x, y in el.get("pontos", [])])
            elif el.get("tipo") == "bezier_quadratica":
                for chave in ("p0", "p1", "p2"):
                    if chave in el:
                        x, y = el[chave]
                        pontos.append((float(x), float(y)))
        if not pontos:
            return 0.0, 0.0
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        cx = (min(xs) + max(xs)) / 2.0
        cy = (min(ys) + max(ys)) / 2.0
        centro_tela = QPointF(float(self.width()) * 0.5, float(self.height()) * 0.5)
        centro_cena = self._tela_para_cena(centro_tela)
        return centro_cena.x() - cx, centro_cena.y() - cy

    def _transladar_elemento(self, elemento: dict, dx: float, dy: float):
        if elemento.get("tipo") == "polyline":
            elemento["pontos"] = [(float(x) + dx, float(y) + dy) for x, y in elemento.get("pontos", [])]
        elif elemento.get("tipo") == "bezier_quadratica":
            for chave in ("p0", "p1", "p2"):
                if chave in elemento:
                    x, y = elemento[chave]
                    elemento[chave] = (float(x) + dx, float(y) + dy)

        for chave in ("controle_cantos", "controle_auxiliares", "fio_origem", "fio_fim"):
            valor = elemento.get(chave)
            if isinstance(valor, list):
                elemento[chave] = [(float(x) + dx, float(y) + dy) for x, y in valor]
            elif isinstance(valor, (tuple, list)) and len(valor) == 2:
                elemento[chave] = (float(valor[0]) + dx, float(valor[1]) + dy)

        for chave in ("pontos_controle_principais", "pontos_auxiliares"):
            valor = elemento.get(chave)
            if isinstance(valor, list):
                for item in valor:
                    if isinstance(item, dict):
                        item["x"] = float(item.get("x", 0.0)) + dx
                        item["y"] = float(item.get("y", 0.0)) + dy

    def recortar(self):
        self.copiar()
        self.apagar_selecionados()

    def apagar_selecionados(self):
        if not self._selecionados:
            return
        self.cena.elementos = [el for idx, el in enumerate(self.cena.elementos) if idx not in self._selecionados]
        self._selecionados.clear()
        self._registrar_historico()
        self.update()

    def selecionar_tudo(self):
        self._selecionados = set(range(len(self.cena.elementos)))
        self.update()

    def selecionar_moldes(self):
        self._selecionados = {idx for idx, el in enumerate(self.cena.elementos) if el.get("molde")}
        self.update()

    def inverter_selecao(self):
        total = set(range(len(self.cena.elementos)))
        self._selecionados = total - set(self._selecionados)
        self.update()

    def inverter_selecao_moldes(self):
        moldes = {idx for idx, el in enumerate(self.cena.elementos) if el.get("molde")}
        self._selecionados = moldes - (set(self._selecionados) & moldes)
        self.update()

    def _ativar_ferramenta_janela_principal(self, tool_id: str):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_ativar_ferramenta_global"):
                parent._ativar_ferramenta_global(tool_id)
                return
            parent = parent.parentWidget()

    def _abrir_menu_contexto_canvas(self, pos_global: QPoint):
        pos_local = self.mapFromGlobal(pos_global)
        pos_cena = self._ponto_com_snap(QPointF(float(pos_local.x()), float(pos_local.y())))
        molde_no_cursor = self._indice_molde_em_ponto(pos_cena)
        menu = QMenu(self)
        a_props = menu.addAction("Propriedades\tCtrl+Enter")
        a_vars = menu.addAction("Variantes")
        a_infos = menu.addAction("Informações modelo\tCtrl+M")
        menu.addSeparator()
        a_excluir = menu.addAction("Excluir\tDel")
        a_recortar = menu.addAction("Recortar\tCtrl+X")
        a_copiar = menu.addAction("Copiar\tCtrl+C")
        a_colar = menu.addAction("Colar\tCtrl+V")
        menu.addSeparator()
        a_sel_tudo = menu.addAction("Selecionar tudo\tCtrl+T")
        a_sel_moldes = menu.addAction("Selecionar moldes")
        a_inv_sel = menu.addAction("Inverter seleção")
        a_inv_sel_moldes = menu.addAction("Inverter seleção moldes")
        menu.addSeparator()
        a_criar_restore = menu.addAction("Cria ponto de restauração")
        a_restaurar = menu.addAction("Restaurar")
        a_restaurar_copia = menu.addAction("Restaura ponto de restauração com cópia")

        tem_sel = bool(self._selecionados)
        a_excluir.setEnabled(tem_sel)
        a_recortar.setEnabled(tem_sel)
        a_copiar.setEnabled(tem_sel)
        a_criar_restore.setEnabled(False)
        a_restaurar.setEnabled(False)
        a_restaurar_copia.setEnabled(False)

        escolhido: QAction | None = menu.exec(pos_global)
        if escolhido is None:
            return
        if escolhido is a_props:
            if molde_no_cursor is not None:
                self._selecionados = {molde_no_cursor}
                self.update()
            self._ativar_ferramenta_janela_principal("propriedades")
        elif escolhido is a_vars:
            self._ativar_ferramenta_janela_principal("variantes")
        elif escolhido is a_infos:
            self._ativar_ferramenta_janela_principal("informacoes_moldes")
        elif escolhido is a_excluir:
            self.apagar_selecionados()
        elif escolhido is a_recortar:
            self.copiar()
            self.apagar_selecionados()
        elif escolhido is a_copiar:
            self.copiar()
        elif escolhido is a_colar:
            self.colar()
        elif escolhido is a_sel_tudo:
            self.selecionar_tudo()
        elif escolhido is a_sel_moldes:
            self.selecionar_moldes()
        elif escolhido is a_inv_sel:
            self.inverter_selecao()
        elif escolhido is a_inv_sel_moldes:
            self.inverter_selecao_moldes()

    # ========== Métodos internos ==========

    def _registrar_historico(self):
        self._aplicar_padrao_grade_primeiro_molde()
        self._limpar_cache_runtime_elementos()
        snapshot = self._elementos_serializaveis()
        if self._indice_historico < len(self._historico_elementos) - 1:
            self._historico_elementos = self._historico_elementos[:self._indice_historico + 1]
        self._historico_elementos.append(snapshot)
        if len(self._historico_elementos) > 200:
            self._historico_elementos.pop(0)
        self._indice_historico = len(self._historico_elementos) - 1

    def _aplicar_padrao_grade_primeiro_molde(self):
        moldes = [el for el in self.cena.elementos if isinstance(el, dict) and el.get("molde")]
        if len(moldes) < 2:
            return
        molde_base = moldes[0]
        linhas_base = molde_base.get("graduacao_tamanhos")
        if not isinstance(linhas_base, list) or not linhas_base:
            return
        linhas_normalizadas = [dict(l) for l in linhas_base if isinstance(l, dict)]
        if not linhas_normalizadas:
            return
        grade_base = str(molde_base.get("graduacao_grade_nome") or "").strip()
        for molde in moldes[1:]:
            linhas = molde.get("graduacao_tamanhos")
            if not isinstance(linhas, list) or not linhas:
                molde["graduacao_tamanhos"] = deepcopy(linhas_normalizadas)
                if grade_base:
                    molde["graduacao_grade_nome"] = grade_base

    def _resetar_estado_curva(self):
        self._curva_estado = "parada"
        self._curva_p0 = None
        self._curva_p2 = None
        self._curva_p1 = None
        self._curva_preview_fim = None
        self._curva_pmedio = None
        self._arrastando_alca_curva = None

    def _controle_para_tres_pontos(self, p0: QPointF, pmedio: QPointF, p2: QPointF) -> QPointF:
        # B(0.5) = 0.25*p0 + 0.5*p1 + 0.25*p2  =>  p1 = 2*pmedio - 0.5*(p0+p2)
        return QPointF(
            (2.0 * pmedio.x()) - (0.5 * (p0.x() + p2.x())),
            (2.0 * pmedio.y()) - (0.5 * (p0.y() + p2.y())),
        )

    def _curva_pronta_para_finalizar(self) -> bool:
        if self._modo_curva == "3p":
            return all(p is not None for p in (self._curva_p0, self._curva_pmedio, self._curva_p2))
        return all(p is not None for p in (self._curva_p0, self._curva_p1, self._curva_p2))

    def _finalizar_curva(self):
        if not self._curva_pronta_para_finalizar():
            return
        if self._modo_curva == "3p" and self._curva_p1 is None and self._curva_p0 and self._curva_pmedio and self._curva_p2:
            self._curva_p1 = self._controle_para_tres_pontos(self._curva_p0, self._curva_pmedio, self._curva_p2)
        if self._curva_p0 is None or self._curva_p1 is None or self._curva_p2 is None:
            return
        self.cena.elementos.append(
            {
                "tipo": "bezier_quadratica",
                "p0": (self._curva_p0.x(), self._curva_p0.y()),
                "p1": (self._curva_p1.x(), self._curva_p1.y()),
                "p2": (self._curva_p2.x(), self._curva_p2.y()),
                "cor": self._linha_cor,
                "espessura": self._linha_espessura,
                "estilo": self._linha_estilo,
                "amplitude": self._linha_amplitude,
                "fase_inicio": 0.0,
            }
        )
        self._registrar_historico()
        self._resetar_estado_curva()
        self.update()

    def _alca_curva_em_ponto(self, pos: QPointF) -> tuple[int, str] | None:
        tolerancia = 10.0 / max(self.zoom, 0.001)
        candidatos = sorted(self._selecionados) if self._selecionados else range(len(self.cena.elementos))
        for idx in candidatos:
            if idx < 0 or idx >= len(self.cena.elementos):
                continue
            el = self.cena.elementos[idx]
            if el.get("tipo") != "bezier_quadratica":
                continue
            for chave in ("p0", "p1", "p2"):
                px, py = el.get(chave, (None, None))
                if px is None or py is None:
                    continue
                if self._dist(QPointF(float(px), float(py)), pos) <= tolerancia:
                    return idx, chave
        return None

    def _reposicionar_painel_coordenadas(self):
        if not self.painel_coordenadas.isVisible():
            return
        x = max(8, self.width() - self.painel_coordenadas.width() - 12)
        y = 16
        self.painel_coordenadas.move(x, y)

    def calcular_posicao_painel_auxiliar(self, largura: int, altura: int, abaixo_coordenadas: bool = True) -> QPoint:
        margem_direita = 12
        margem_topo = 16
        x = max(8, self.width() - int(largura) - margem_direita)
        y = margem_topo
        if abaixo_coordenadas and self.painel_coordenadas.isVisible():
            y = self.painel_coordenadas.y() + self.painel_coordenadas.height() + 8
        max_y = max(margem_topo, self.height() - int(altura) - 8)
        y = max(margem_topo, min(y, max_y))
        return QPoint(int(x), int(y))

    def _tela_para_cena(self, ponto: QPointF) -> QPointF:
        return QPointF((ponto.x() / self.zoom) + self.origem_cena.x(),
                       (ponto.y() / self.zoom) + self.origem_cena.y())

    def _cena_para_tela(self, ponto: QPointF) -> QPointF:
        return QPointF((ponto.x() - self.origem_cena.x()) * self.zoom,
                       (ponto.y() - self.origem_cena.y()) * self.zoom)

    def _adicionar_candidato_snap(
            self,
            candidatos: list[SnapResult],
            pos_cena: QPointF,
            ponto: QPointF | None,
            tipo: str,
            elemento_idx: int | None = None,
            tol_cena: float | None = None,
    ):
        if ponto is None:
            return
        dist = self._dist(pos_cena, ponto)
        if tol_cena is not None and dist > tol_cena:
            return
        candidatos.append(SnapResult(ponto=QPointF(ponto), tipo=tipo, distancia=dist, elemento_idx=elemento_idx))

    def _prioridade_tipo_snap(self, tipo: str) -> int:
        ordem = {
            "nó": 0,
            "interseção": 1,
            "centro": 2,
            "ponto médio": 3,
            "borda": 4,
            "controle": 5,
            "coord": 6,
            "fio": 7,
            "nome": 8,
            "grade": 9,
        }
        return ordem.get(tipo, 99)

    def _segmentos_snap_de_pontos(self, pontos: list[QPointF]) -> list[tuple[QPointF, QPointF]]:
        if len(pontos) < 2:
            return []
        return [(QPointF(a), QPointF(b)) for a, b in zip(pontos, pontos[1:])]

    def _candidatos_snap_temporarios(self, pos_cena: QPointF, tol_cena: float) -> list[SnapResult]:
        candidatos: list[SnapResult] = []

        # Segmentos/nós temporários da reta em construção.
        if self._pontos_reta:
            pontos_reta = [QPointF(p) for p in self._pontos_reta]
            for ponto in pontos_reta:
                self._adicionar_candidato_snap(candidatos, pos_cena, ponto, "nó", None, tol_cena)
            for inicio, fim in self._segmentos_snap_de_pontos(pontos_reta):
                meio = QPointF((inicio.x() + fim.x()) / 2.0, (inicio.y() + fim.y()) / 2.0)
                proj = self._snap_manager._projetar_em_segmento(pos_cena, inicio, fim)
                self._adicionar_candidato_snap(candidatos, pos_cena, meio, "ponto médio", None, tol_cena)
                self._adicionar_candidato_snap(candidatos, pos_cena, proj, "borda", None, tol_cena)
            if self._preview_reta is not None:
                inicio = QPointF(pontos_reta[-1])
                fim = QPointF(self._preview_reta)
                proj = self._snap_manager._projetar_em_segmento(pos_cena, inicio, fim)
                self._adicionar_candidato_snap(candidatos, pos_cena, fim, "nó", None, tol_cena)
                self._adicionar_candidato_snap(candidatos, pos_cena, proj, "borda", None, tol_cena)

        # Permite que a ferramenta ativa ofereça os snaps temporários dela.
        if self._runtime_tool and hasattr(self._runtime_tool, "obter_candidatos_snap"):
            try:
                extras = self._runtime_tool.obter_candidatos_snap(self, QPointF(pos_cena))
                for item in extras or []:
                    if isinstance(item, SnapResult):
                        if item.distancia <= tol_cena:
                            candidatos.append(item)
            except Exception:
                pass

        return candidatos

    def _ponto_com_snap(self, pos_tela: QPointF) -> QPointF:
        pos_cena = self._tela_para_cena(pos_tela)
        if not self._snap_ativo:
            self._snap_resultado = None
            self._snap_candidatos = []
            self._snap_indice = 0
            return pos_cena

        tol_px = self._tolerancia_snap_px()
        tol_cena = tol_px / max(self.zoom, 0.001)
        candidatos = self._snap_manager.calcular_candidatos(
            self.cena, pos_cena, self.zoom, tolerancia_px=tol_px
        )

        for idx, el in enumerate(self.cena.elementos):
            if el.get("tipo") == "bezier_quadratica":
                p0 = QPointF(*el["p0"])
                p1 = QPointF(*el["p1"])
                p2 = QPointF(*el["p2"])
                candidatos_bezier = [
                    ("nó", p0),
                    ("controle", p1),
                    ("nó", p2),
                    ("ponto médio", QPointF((p0.x() + p2.x()) / 2.0, (p0.y() + p2.y()) / 2.0)),
                ]
                for tipo, ponto in candidatos_bezier:
                    self._adicionar_candidato_snap(candidatos, pos_cena, ponto, tipo, idx, tol_cena)
            for chave in ("controle_cantos", "controle_auxiliares"):
                for p in el.get(chave, []) or []:
                    if not isinstance(p, (list, tuple)) or len(p) != 2:
                        continue
                    ponto = QPointF(float(p[0]), float(p[1]))
                    self._adicionar_candidato_snap(candidatos, pos_cena, ponto, "controle", idx, tol_cena)
            if el.get("molde"):
                fio_origem = el.get("fio_origem")
                fio_fim = el.get("fio_fim")
                if isinstance(fio_origem, (list, tuple)) and len(fio_origem) == 2 and isinstance(fio_fim,
                                                                                                 (list, tuple)) and len(
                        fio_fim) == 2:
                    p1 = QPointF(float(fio_origem[0]), float(fio_origem[1]))
                    p2 = QPointF(float(fio_fim[0]), float(fio_fim[1]))
                    pm = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
                    for tipo, ponto in (("fio", p1), ("fio", p2), ("fio", pm)):
                        self._adicionar_candidato_snap(candidatos, pos_cena, ponto, tipo, idx, tol_cena)
                    proj_fio = self._projecao_no_segmento(pos_cena, p1, p2)
                    if self._dist(proj_fio, pos_cena) <= (tol_cena * 1.4):
                        self._adicionar_candidato_snap(candidatos, pos_cena, proj_fio, "fio", idx, tol_cena * 1.5)
                if el.get("mostrar_nome", True) and str(el.get("nome_molde") or "").strip():
                    pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                    base = pts[:-1] if len(pts) >= 2 and pts[0] == pts[-1] else pts
                    if base:
                        cx = sum(p.x() for p in base) / len(base)
                        cy = sum(p.y() for p in base) / len(base)
                        p_nome = QPointF(cx, cy)
                        self._adicionar_candidato_snap(candidatos, pos_cena, p_nome, "nome", idx, tol_cena * 1.5)

        candidatos.extend(self._candidatos_snap_temporarios(pos_cena, tol_cena))

        if self._ponto_coordenada_aplicada is not None:
            dist = self._dist(pos_cena, self._ponto_coordenada_aplicada)
            if dist <= tol_cena:
                candidatos.insert(0, SnapResult(
                    ponto=QPointF(self._ponto_coordenada_aplicada),
                    tipo="coord",
                    distancia=dist,
                    elemento_idx=None,
                ))

        if candidatos:
            candidatos_sem_grade = [c for c in candidatos if c.tipo != "grade"]
            if candidatos_sem_grade:
                candidatos = candidatos_sem_grade

        candidatos.sort(key=lambda c: (self._prioridade_tipo_snap(c.tipo), c.distancia))
        self._snap_candidatos = candidatos

        if self._snap_candidatos:
            self._snap_indice = min(self._snap_indice, len(self._snap_candidatos) - 1)
            self._snap_resultado = self._snap_candidatos[self._snap_indice]
        else:
            self._snap_resultado = None
            self._snap_indice = 0
        if self._snap_resultado:
            return self._snap_resultado.ponto
        return pos_cena

    def _tolerancia_snap_px(self) -> float:
        dpi = float(self.logicalDpiX()) if self.logicalDpiX() > 0 else 96.0
        return (dpi / 2.54) * 0.5

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

    def _snap_angular(self, origem: QPointF, destino: QPointF,
                      travar_snap_exato: bool = False, travar_principais: bool = False,
                      liberar_angular: bool | None = None) -> QPointF:
        if liberar_angular is not None:
            travar_principais = not bool(liberar_angular)
        if not self._snap_ativo:
            return destino
        if liberar_angular:
            return destino
        if travar_snap_exato and self._snap_resultado and self._snap_resultado.tipo in {"nó", "ponto médio", "centro",
                                                                                        "borda", "coord", "interseção"}:
            return destino
        dx = destino.x() - origem.x()
        dy = destino.y() - origem.y()
        dist = sqrt(dx * dx + dy * dy)
        if dist <= 0.0001:
            return destino
        ang = degrees(atan2(-dy, dx))
        ang_principal = round(ang / 45.0) * 45.0
        if travar_principais:
            return QPointF(origem.x() + dist * cos(radians(ang_principal)),
                           origem.y() - dist * sin(radians(ang_principal)))
        if self._snap_contextual_ativo and len(self._pontos_reta) >= 2:
            ang_contextual = self._snap_angular_contextual(origem, ang)
            if ang_contextual is not None:
                return QPointF(origem.x() + dist * cos(radians(ang_contextual)),
                               origem.y() - dist * sin(radians(ang_contextual)))
        angulo_dist = self._dist_angular(ang, ang_principal)
        tolerancia_principal = max(1.8, min(5.0, self._snap_angular_passo * 0.12))
        if angulo_dist <= tolerancia_principal:
            return QPointF(origem.x() + dist * cos(radians(ang_principal)),
                           origem.y() - dist * sin(radians(ang_principal)))
        return destino

    def _snap_angular_contextual(self, origem: QPointF, ang_atual: float) -> float | None:
        ponto_anterior = self._pontos_reta[-2]
        vx = origem.x() - ponto_anterior.x()
        vy = origem.y() - ponto_anterior.y()
        dist_ref = sqrt(vx * vx + vy * vy)
        if dist_ref <= 0.0001:
            return None
        ang_ref = degrees(atan2(-vy, vx))
        candidatos = [ang_ref, ang_ref + 180.0, ang_ref + 90.0, ang_ref - 90.0]
        melhor = min(candidatos, key=lambda ang: self._dist_angular(ang_atual, ang))
        if self._dist_angular(ang_atual, melhor) <= 5.0:
            return melhor
        return None

    def _dist_angular(self, a: float, b: float) -> float:
        diff = abs((a - b) % 360.0)
        return min(diff, 360.0 - diff)

    def _aplicar_guia_fechamento(self, origem: QPointF, destino: QPointF) -> QPointF:
        self._guia_fechamento = None
        if len(self._pontos_reta) < 2 or not self._snap_resultado:
            return destino
        if self._snap_resultado.tipo not in {"nó", "ponto médio", "centro", "borda", "coord", "interseção"}:
            return destino
        ponto_final = self._snap_resultado.ponto
        ponto_anterior = self._pontos_reta[-2]
        vec_ref = QPointF(origem.x() - ponto_anterior.x(), origem.y() - ponto_anterior.y())
        vec_cursor = QPointF(destino.x() - origem.x(), destino.y() - origem.y())
        mod_ref = sqrt(vec_ref.x() * vec_ref.x() + vec_ref.y() * vec_ref.y())
        mod_cursor = sqrt(vec_cursor.x() * vec_cursor.x() + vec_cursor.y() * vec_cursor.y())
        if mod_ref <= 0.0001 or mod_cursor <= 0.0001:
            return destino
        det = (vec_ref.x() * vec_cursor.y()) - (vec_ref.y() * vec_cursor.x())
        if abs(det) <= 0.0001:
            return destino
        delta = QPointF(origem.x() - ponto_final.x(), origem.y() - ponto_final.y())
        t = ((delta.x() * vec_cursor.y()) - (delta.y() * vec_cursor.x())) / det
        u = ((delta.x() * vec_ref.y()) - (delta.y() * vec_ref.x())) / det
        if u < 0:
            return destino
        intersecao = QPointF(ponto_final.x() + t * vec_ref.x(), ponto_final.y() + t * vec_ref.y())
        tolerancia_cena = self._tolerancia_snap_px() / max(self.zoom, 0.001)
        dist_intersecao = sqrt((intersecao.x() - destino.x()) ** 2 + (intersecao.y() - destino.y()) ** 2)
        if dist_intersecao > tolerancia_cena * 4:
            return destino
        self._guia_fechamento = (ponto_final, intersecao)
        if dist_intersecao <= tolerancia_cena:
            return intersecao
        return destino

    def _aplicar_guias_alinhamento(self, origem: QPointF, destino: QPointF) -> QPointF:
        self._guias_alinhamento = []
        if not self._snap_ativo:
            return destino
        if self._snap_resultado and self._snap_resultado.tipo in {"nó", "ponto médio", "centro", "borda", "coord",
                                                                  "interseção"}:
            return destino
        candidatos: list[QPointF] = []
        candidatos.extend(self._pontos_reta[:-1])
        for el in self.cena.elementos:
            if el.get("tipo") == "polyline":
                candidatos.extend(QPointF(float(x), float(y)) for x, y in el.get("pontos", []))
        if not candidatos:
            return destino
        tol = self._tolerancia_snap_px() / max(self.zoom, 0.001)
        melhor_x: QPointF | None = None
        melhor_y: QPointF | None = None
        dist_x = float("inf")
        dist_y = float("inf")
        for pt in candidatos:
            dx = abs(destino.x() - pt.x())
            dy = abs(destino.y() - pt.y())
            if dx <= tol and dx < dist_x:
                melhor_x = pt
                dist_x = dx
            if dy <= tol and dy < dist_y:
                melhor_y = pt
                dist_y = dy
        ajustado = QPointF(destino)
        if melhor_x:
            ajustado.setX(melhor_x.x())
            self._guias_alinhamento.append((QPointF(melhor_x.x(), melhor_x.y()), QPointF(melhor_x.x(), ajustado.y())))
        if melhor_y:
            ajustado.setY(melhor_y.y())
            self._guias_alinhamento.append((QPointF(melhor_y.x(), melhor_y.y()), QPointF(ajustado.x(), melhor_y.y())))
        return ajustado

    def _aplicar_coordenadas(self, payload: dict):
        origem = self._pontos_reta[-1] if self._pontos_reta else QPointF(0.0, 0.0)
        dx_u = payload.get("dx")
        dy_u = payload.get("dy")
        ang = payload.get("a")
        dist_u = payload.get("d")
        dx = self.converter_para_cena(dx_u) if dx_u is not None else None
        dy = self.converter_para_cena(dy_u) if dy_u is not None else None
        dist = self.converter_para_cena(dist_u) if dist_u is not None else None
        destino: QPointF | None = None
        if ang is not None and dist is not None:
            rad = radians(ang)
            destino = QPointF(origem.x() + (dist * cos(rad)), origem.y() - (dist * sin(rad)))
        elif dx is not None or dy is not None:
            destino = QPointF(origem.x() + float(dx or 0.0), origem.y() + float(dy or 0.0))
        if destino is None:
            return
        destino = self._snap_angular(origem, destino)
        self._ponto_coordenada_aplicada = destino
        self._marcacoes_temporarias.append(destino)
        self.painel_coordenadas.atualizar_preview(origem, destino)
        self.update()

    def _desfazer_ponto(self):
        if not self._pontos_reta:
            return
        self._pontos_reta.pop()
        if self._pontos_reta:
            self._preview_reta = self._pontos_reta[-1]
        else:
            self._preview_reta = None
            self._guia_fechamento = None
        self.update()

    def _finalizar_reta_atual(self):
        if len(self._pontos_reta) == 1:
            self._pontos_reta.clear()
            self._preview_reta = None
            self._guia_fechamento = None
            self._guias_alinhamento = []
            self._aguardando_retorno_selecao = False
            return
        if len(self._pontos_reta) >= 2:
            fase = 0.0
            for inicio, fim in zip(self._pontos_reta, self._pontos_reta[1:]):
                comprimento = sqrt((fim.x() - inicio.x()) ** 2 + (fim.y() - inicio.y()) ** 2)
                self.cena.elementos.append({
                    "tipo": "polyline",
                    "pontos": [(inicio.x(), inicio.y()), (fim.x(), fim.y())],
                    "cor": self._linha_cor,
                    "espessura": self._linha_espessura,
                    "estilo": self._linha_estilo,
                    "amplitude": self._linha_amplitude,
                    "fase_inicio": fase,
                })
                fase += comprimento
            self._registrar_historico()
            ultimo_ponto = self._pontos_reta[-1]
            self._pontos_reta = [ultimo_ponto]
            self._preview_reta = ultimo_ponto
            self._guia_fechamento = None
            self._guias_alinhamento = []
            self._aguardando_retorno_selecao = True

    def _set_painel_coordenadas_visivel(self, visivel: bool):
        self._painel_coordenadas_visivel = visivel
        self.painel_coordenadas_changed.emit(visivel)

    def _registrar_posicao_painel(self, x: int, y: int):
        self._painel_coordenadas_posicao = None
        self.painel_posicao_changed.emit(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposicionar_painel_coordenadas()
        if self._runtime_tool and hasattr(self._runtime_tool, "on_canvas_resize"):
            self._runtime_tool.on_canvas_resize(self)

    def wheelEvent(self, event: QWheelEvent):
        cursor_tela = event.position()
        cursor_cena_antes = self._tela_para_cena(cursor_tela)
        delta = event.angleDelta().y()
        fator = 1.1 if delta > 0 else 0.9
        self.set_zoom(self.zoom * fator)
        self.origem_cena = QPointF(
            cursor_cena_antes.x() - (cursor_tela.x() / self.zoom),
            cursor_cena_antes.y() - (cursor_tela.y() / self.zoom),
        )
        event.accept()

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._ativar_ferramenta_janela_principal("propriedades")
                event.accept()
                return
            if event.key() == Qt.Key_M:
                self._ativar_ferramenta_janela_principal("informacoes_moldes")
                event.accept()
                return
        if self._runtime_tool and hasattr(self._runtime_tool, "on_key_press"):
            if self._runtime_tool.on_key_press(self, event):
                return
        if event.key() == Qt.Key_W and not event.isAutoRepeat():
            self._tecla_w_trava_principal = True
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self._runtime_tool and hasattr(self._runtime_tool, "on_key_release"):
            if self._runtime_tool.on_key_release(self, event):
                return
        if event.key() == Qt.Key_W and not event.isAutoRepeat():
            self._tecla_w_trava_principal = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._tecla_w_trava_principal = False
        super().focusOutEvent(event)

    def leaveEvent(self, event):
        self._snap_resultado = None
        self._snap_candidatos = []
        self._snap_indice = 0
        self._tecla_w_trava_principal = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.RightButton:
            agora = monotonic()
            if (agora - self._ultimo_clique_direito_ts) <= 0.45:
                self._sequencia_clique_direito += 1
            else:
                self._sequencia_clique_direito = 1
            self._ultimo_clique_direito_ts = agora
            if self.ferramenta_ativa != "selecionar" and self._sequencia_clique_direito >= 2:
                self._sequencia_clique_direito = 0
                self.ferramenta_padrao_solicitada.emit("selecionar")
                event.accept()
                return
            if not (event.modifiers() & Qt.ControlModifier):
                pos_cena_bruta = self._tela_para_cena(event.position())
                molde_alvo = self._indice_molde_em_ponto(pos_cena_bruta)
                if molde_alvo is None and self._snap_resultado is not None and self._snap_resultado.elemento_idx is not None:
                    idx_snap = int(self._snap_resultado.elemento_idx)
                    if 0 <= idx_snap < len(self.cena.elementos) and self.cena.elementos[idx_snap].get("molde"):
                        molde_alvo = idx_snap
                if molde_alvo is not None:
                    self._selecionados = {molde_alvo}
                    self.update()
                    self._ativar_ferramenta_janela_principal("propriedades")
                    event.accept()
                    return
        elif event.button() == Qt.LeftButton:
            self._sequencia_clique_direito = 0
        if self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_press"):
            if self._runtime_tool.on_mouse_press(self, event):
                return
        if self.ferramenta_ativa == "selecionar" and event.button() == Qt.RightButton:
            pos = self._ponto_com_snap(event.position())
            molde_alvo = self._indice_molde_em_ponto(pos)
            if molde_alvo is not None:
                self._selecionados = {molde_alvo}
                self.update()
            if event.modifiers() & Qt.ControlModifier:
                if self._selecionar_proximo_em_ponto(pos):
                    event.accept()
                    return
            self._abrir_menu_contexto_canvas(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self._ponto_com_snap(event.position())
        if self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_move"):
            if self._runtime_tool.on_mouse_move(self, event):
                self.update()
                return
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_release"):
            if self._runtime_tool.on_mouse_release(self, event):
                return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.ferramenta_ativa != "selecionar" and event.button() in (Qt.LeftButton, Qt.RightButton):
            self.ferramenta_padrao_solicitada.emit("selecionar")
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        painter.setRenderHint(QPainter.Antialiasing)

        # Desenha destaque de reta temporária (para modo paralela/perpendicular)
        if self._destacar_reta_temporaria:
            pen = QPen(QColor("#ffaa00"), 3, Qt.DashDotLine)
            painter.setPen(pen)
            p1_tela = self._cena_para_tela(self._destacar_reta_temporaria[0])
            p2_tela = self._cena_para_tela(self._destacar_reta_temporaria[1])
            painter.drawLine(p1_tela, p2_tela)

        for idx, elemento in enumerate(self.cena.elementos):
            if elemento.get("tipo") == "imagem":
                self._desenhar_imagem_referencia(painter, elemento)
                continue
            cor_base = elemento.get("cor", "#d0d0d0")
            if elemento.get("molde") and self._mostrar_cor_tecidos:
                tecido = str(elemento.get("tecido") or "").strip()
                if tecido and tecido in self._cores_tecidos:
                    cor_base = self._cores_tecidos[tecido]
            selecionado = idx in self._selecionados
            is_molde = bool(elemento.get("molde"))
            cor = cor_base
            esp = float(elemento.get("espessura", 1.0))
            if elemento.get("tipo") == "polyline":
                pontos = [QPointF(x, y) for x, y in elemento.get("pontos", [])]
                if len(pontos) < 2:
                    continue
                self._desenhar_polilinha(painter, pontos, cor=cor, espessura=esp,
                                         estilo=str(elemento.get("estilo", "solid")),
                                         amplitude=float(elemento.get("amplitude", 1.0)),
                                         fase_inicial=float(elemento.get("fase_inicio", 0.0)))
            elif elemento.get("tipo") == "bezier_quadratica":
                self._desenhar_bezier_quadratica(painter, QPointF(*elemento["p0"]), QPointF(*elemento["p1"]),
                                                 QPointF(*elemento["p2"]),
                                                 cor=cor, espessura=esp, estilo=str(elemento.get("estilo", "solid")),
                                                 amplitude=float(elemento.get("amplitude", 1.0)),
                                                 destacar_controles=(idx in self._selecionados))
            if selecionado and not is_molde:
                self._desenhar_bbox_selecao_elemento(painter, elemento)

        self._desenhar_overlays_moldes(painter)

        if self._runtime_tool and hasattr(self._runtime_tool, "on_paint_overlay"):
            self._runtime_tool.on_paint_overlay(self, painter)
        self._desenhar_overlay_snap_ativo(painter)

    def _desenhar_imagem_referencia(self, painter: QPainter, elemento: dict):
        imagem_b64 = str(elemento.get("imagem_base64") or "").strip()
        if not imagem_b64:
            return
        cache_key = str(elemento.get("cache_id") or elemento.get("nome") or "imagem") + ":" + str(hash(imagem_b64))
        pixmap = self._imagem_cache.get(cache_key)
        if not isinstance(pixmap, QPixmap) or pixmap.isNull():
            try:
                bruto = base64.b64decode(imagem_b64)
                img = QImage.fromData(bruto)
                if img.isNull():
                    return
                pixmap = QPixmap.fromImage(img)
                self._imagem_cache[cache_key] = pixmap
            except Exception:
                return
        if pixmap.isNull():
            return
        pos = elemento.get("pos") or (0.0, 0.0)
        if not (isinstance(pos, (tuple, list)) and len(pos) == 2):
            pos = (0.0, 0.0)
        escala = max(0.01, float(elemento.get("escala", 1.0)))
        centro_tela = self._cena_para_tela(QPointF(float(pos[0]), float(pos[1])))
        largura_tela = max(1.0, pixmap.width() * escala * self.zoom)
        altura_tela = max(1.0, pixmap.height() * escala * self.zoom)
        x = centro_tela.x() - (largura_tela / 2.0)
        y = centro_tela.y() - (altura_tela / 2.0)
        painter.save()
        painter.setOpacity(max(0.05, min(float(elemento.get("opacidade", 0.72)), 1.0)))
        painter.drawPixmap(int(x), int(y), int(largura_tela), int(altura_tela), pixmap)
        painter.restore()

    def _desenhar_overlay_snap_ativo(self, painter: QPainter):
        if not self._snap_ativo or not self._snap_resultado:
            return
        snap_tela = self._cena_para_tela(self._snap_resultado.ponto)
        cor = QColor("#ffd400")
        if self._snap_resultado.tipo == "controle":
            cor = QColor("#2da8ff")
        elif self._snap_resultado.tipo in {"borda", "ponto médio"}:
            cor = QColor("#7df9ff")
        elif self._snap_resultado.tipo == "interseção":
            cor = QColor("#ff62b0")
        pen = QPen(cor, 1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(snap_tela, 6, 6)
        painter.drawLine(QPointF(snap_tela.x() - 8, snap_tela.y()), QPointF(snap_tela.x() + 8, snap_tela.y()))
        painter.drawLine(QPointF(snap_tela.x(), snap_tela.y() - 8), QPointF(snap_tela.x(), snap_tela.y() + 8))

    def _desenhar_overlays_moldes(self, painter: QPainter):
        for idx, el in enumerate(self.cena.elementos):
            if not el.get("molde"):
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 3:
                continue
            base = pontos[:-1] if pontos and pontos[0] == pontos[-1] else pontos
            if not base:
                continue
            if idx in self._selecionados:
                self._desenhar_selecao_molde(painter, base, el)

            if el.get("mostrar_nome", True):
                nome = str(el.get("nome_molde") or "")
                if nome:
                    cx = sum(p.x() for p in base) / len(base)
                    cy = sum(p.y() for p in base) / len(base)
                    tela = self._cena_para_tela(QPointF(cx, cy))
                    fonte_nome = painter.font()
                    fonte_nome.setPointSizeF(
                        self._tamanho_visual_molde(el, ("tam_nome", "tamanho_nome", "fonte_nome"), 10.0))
                    painter.setFont(fonte_nome)
                    painter.setPen(QPen(QColor("#ffffff"), 1.0))
                    painter.drawText(int(tela.x() - 20), int(tela.y()), nome)

            if el.get("mostrar_fio", True):
                fio_origem = el.get("fio_origem")
                fio_fim = el.get("fio_fim")
                if fio_origem and fio_fim:
                    p1 = QPointF(float(fio_origem[0]), float(fio_origem[1]))
                    p2 = QPointF(float(fio_fim[0]), float(fio_fim[1]))
                else:
                    xs = [p.x() for p in base]
                    ys = [p.y() for p in base]
                    largura = max(xs) - min(xs)
                    margem = largura * 0.12
                    y_fio = min(ys) + ((max(ys) - min(ys)) * 0.24)
                    p1 = QPointF(min(xs) + margem, y_fio)
                    p2 = QPointF(max(xs) - margem, y_fio)
                self._desenhar_seta_fio(painter, p1, p2)

                rotulo_fio = (
                        el.get("fio_rotulo")
                        or el.get("fio_texto")
                        or el.get("titulo_fio")
                        or el.get("nome_fio")
                        or ""
                )
                if rotulo_fio:
                    self._desenhar_rotulo_fio(
                        painter,
                        p1,
                        p2,
                        str(rotulo_fio),
                        tamanho=self._tamanho_visual_molde(el, ("tam_fio", "tamanho_fio", "fonte_fio"), 9.0),
                    )
                else:
                    fim_tela = self._cena_para_tela(p2)
                    ang = float(el.get("fio_angulo", 90.0))
                    fonte_fio = painter.font()
                    fonte_fio.setPointSizeF(
                        self._tamanho_visual_molde(el, ("tam_fio", "tamanho_fio", "fonte_fio"), 9.0))
                    painter.setFont(fonte_fio)
                    painter.setPen(QPen(QColor("#ffffff"), 1.0))
                    painter.drawText(int(fim_tela.x() + 6), int(fim_tela.y() + 4), f"{int(round(ang))}°")

            if el.get("mostrar_controles", True) and idx not in self._selecionados:
                cantos = [QPointF(float(x), float(y)) for x, y in el.get("controle_cantos", [])]
                if cantos:
                    cx = sum(p.x() for p in cantos) / len(cantos)
                    cy = sum(p.y() for p in cantos) / len(cantos)
                else:
                    cx, cy = 0.0, 0.0
                painter.setPen(QPen(QColor("#ffffff"), 1.0))
                fonte_num = painter.font()
                fonte_num.setPointSizeF(
                    self._tamanho_visual_molde(el, ("tam_numero", "tamanho_numero", "fonte_numeracao"), 9.0))
                painter.setFont(fonte_num)
                for i, pt in enumerate(cantos, start=1):
                    pt_tela = self._cena_para_tela(pt)
                    painter.drawRect(int(pt_tela.x() - 3), int(pt_tela.y() - 3), 6, 6)
                    dx = pt.x() - cx
                    dy = pt.y() - cy
                    mod = max(1e-6, sqrt((dx * dx) + (dy * dy)))
                    off_x = (dx / mod) * 11.0
                    off_y = (dy / mod) * 11.0
                    painter.drawText(int(pt_tela.x() + off_x), int(pt_tela.y() + off_y), str(i))
                if self._ferramenta_manipulacao_ativa():
                    aux = [QPointF(float(x), float(y)) for x, y in el.get("controle_auxiliares", [])]
                    painter.setPen(QPen(QColor("#ff3b30"), 1.0))
                    painter.setBrush(QColor("#ff3b30"))
                    for pt in aux:
                        pt_tela = self._cena_para_tela(pt)
                        painter.drawRect(int(pt_tela.x() - 2), int(pt_tela.y() - 2), 4, 4)

    def _desenhar_selecao_molde(self, painter: QPainter, base: list[QPointF], el: dict):
        if not base:
            return
        margem_cm = 0.5
        min_x = min(pt.x() for pt in base) - margem_cm
        max_x = max(pt.x() for pt in base) + margem_cm
        min_y = min(pt.y() for pt in base) - margem_cm
        max_y = max(pt.y() for pt in base) + margem_cm
        canto_sup_esq = self._cena_para_tela(QPointF(min_x, min_y))
        canto_inf_dir = self._cena_para_tela(QPointF(max_x, max_y))
        x_ini = min(canto_sup_esq.x(), canto_inf_dir.x())
        y_ini = min(canto_sup_esq.y(), canto_inf_dir.y())
        largura = abs(canto_inf_dir.x() - canto_sup_esq.x())
        altura = abs(canto_inf_dir.y() - canto_sup_esq.y())

        ret_pen = QPen(QColor("#2da8ff"), 1.0, Qt.DashLine)
        ret_pen.setDashPattern([3.5, 2.5])
        painter.setPen(ret_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(x_ini), int(y_ini), int(largura), int(altura))

        cantos = [QPointF(float(x), float(y)) for x, y in el.get("controle_cantos", [])]
        if len(cantos) >= 4:
            pontos_controle = [self._cena_para_tela(pt) for pt in cantos[:4]]
        else:
            pontos_controle = [self._cena_para_tela(pt) for pt in base[:4]]

        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.setBrush(QColor("#000000"))
        for pt in pontos_controle:
            d = 4
            diamond = QPolygon([
                QPoint(int(pt.x()), int(pt.y() - d)),
                QPoint(int(pt.x() + d), int(pt.y())),
                QPoint(int(pt.x()), int(pt.y() + d)),
                QPoint(int(pt.x() - d), int(pt.y())),
            ])
            painter.drawPolygon(diamond)

    def _desenhar_bbox_selecao_elemento(self, painter: QPainter, elemento: dict):
        pontos: list[QPointF] = []
        if elemento.get("tipo") == "polyline":
            pontos = [QPointF(float(x), float(y)) for x, y in elemento.get("pontos", [])]
        elif elemento.get("tipo") == "bezier_quadratica":
            pontos = [QPointF(*elemento["p0"]), QPointF(*elemento["p1"]), QPointF(*elemento["p2"])]
        if not pontos:
            return
        margem_cm = 0.5
        min_x = min(p.x() for p in pontos) - margem_cm
        max_x = max(p.x() for p in pontos) + margem_cm
        min_y = min(p.y() for p in pontos) - margem_cm
        max_y = max(p.y() for p in pontos) + margem_cm
        canto_sup_esq = self._cena_para_tela(QPointF(min_x, min_y))
        canto_inf_dir = self._cena_para_tela(QPointF(max_x, max_y))
        x_ini = min(canto_sup_esq.x(), canto_inf_dir.x())
        y_ini = min(canto_sup_esq.y(), canto_inf_dir.y())
        largura = abs(canto_inf_dir.x() - canto_sup_esq.x())
        altura = abs(canto_inf_dir.y() - canto_sup_esq.y())
        pen = QPen(QColor("#2da8ff"), 1.0, Qt.DashLine)
        pen.setDashPattern([3.5, 2.5])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(x_ini), int(y_ini), int(largura), int(altura))

    def _desenhar_seta_fio(self, painter: QPainter, inicio: QPointF, fim: QPointF):
        p1_tela = self._cena_para_tela(inicio)
        p2_tela = self._cena_para_tela(fim)
        dx = p2_tela.x() - p1_tela.x()
        dy = p2_tela.y() - p1_tela.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-6:
            return

        ux = dx / comp
        uy = dy / comp
        nx = -uy
        ny = ux

        margem_px = min(18.0, max(8.0, comp * 0.02))
        base_inicio = QPointF(p1_tela.x() + (ux * margem_px), p1_tela.y() + (uy * margem_px))
        base_fim = QPointF(p2_tela.x() - (ux * margem_px), p2_tela.y() - (uy * margem_px))

        pen = QPen(QColor("#ffffff"), 1.15)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        painter.drawLine(base_inicio, base_fim)

        tamanho_seta = min(14.0, max(7.5, comp * 0.028))
        meia_largura = tamanho_seta * 0.32

        self._desenhar_ponta_seta_fechada(
            painter,
            ponta=p2_tela,
            direcao=QPointF(ux, uy),
            normal=QPointF(nx, ny),
            comprimento=tamanho_seta,
            meia_largura=meia_largura,
        )
        self._desenhar_ponta_seta_fechada(
            painter,
            ponta=p1_tela,
            direcao=QPointF(-ux, -uy),
            normal=QPointF(nx, ny),
            comprimento=tamanho_seta,
            meia_largura=meia_largura,
        )

    def _desenhar_ponta_seta_fechada(
            self,
            painter: QPainter,
            ponta: QPointF,
            direcao: QPointF,
            normal: QPointF,
            comprimento: float,
            meia_largura: float,
    ):
        base = QPointF(
            ponta.x() - (direcao.x() * comprimento),
            ponta.y() - (direcao.y() * comprimento),
        )
        esquerdo = QPointF(
            base.x() + (normal.x() * meia_largura),
            base.y() + (normal.y() * meia_largura),
        )
        direito = QPointF(
            base.x() - (normal.x() * meia_largura),
            base.y() - (normal.y() * meia_largura),
        )
        path = QPainterPath()
        path.moveTo(ponta)
        path.lineTo(esquerdo)
        path.lineTo(direito)
        path.closeSubpath()
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawPath(path)
        painter.restore()

    def _desenhar_rotulo_fio(self, painter: QPainter, inicio: QPointF, fim: QPointF, texto: str,
                             tamanho: float | None = None):
        meio = QPointF((inicio.x() + fim.x()) / 2.0, (inicio.y() + fim.y()) / 2.0)
        meio_tela = self._cena_para_tela(meio)
        dx = fim.x() - inicio.x()
        dy = fim.y() - inicio.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-6:
            return

        nx = -dy / comp
        ny = dx / comp
        offset_px = 12.0
        ancora = QPointF(
            meio_tela.x() + (nx * offset_px),
            meio_tela.y() + (ny * offset_px),
        )

        painter.save()
        fonte = painter.font()
        fonte.setBold(False)
        if tamanho is not None:
            fonte.setPointSizeF(float(max(6.0, tamanho)))
        painter.setFont(fonte)
        metrics = QFontMetrics(painter.font())
        largura = metrics.horizontalAdvance(texto)
        altura = metrics.height()
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.drawText(
            int(round(ancora.x() - (largura / 2))),
            int(round(ancora.y() - 4)),
            int(round(largura)),
            int(round(altura)),
            Qt.AlignCenter,
            texto,
        )
        painter.restore()

    def _ferramenta_manipulacao_ativa(self) -> bool:
        return str(self.ferramenta_ativa or "") in {
            "manipular_pontos",
            "mover",
            "mover_pontos",
            "editar_pontos_de_curva",
            "no_perimetro",
        }

    def _tamanho_visual_molde(self, el: dict, chaves: tuple[str, ...], padrao: float) -> float:
        for chave in chaves:
            valor = el.get(chave)
            if valor is None:
                continue
            try:
                return float(max(6.0, float(valor)))
            except Exception:
                continue
        return float(padrao)

    def _cor_realce(self, cor_hex: str) -> str:
        cor = QColor(cor_hex)
        if not cor.isValid():
            cor = QColor("#d0d0d0")
        return cor.lighter(135).name()

    def _desenhar_polilinha(self, painter: QPainter, pontos: list[QPointF], cor: str = "#ff5a00",
                            espessura: float = 1.0, estilo: str = "solid", amplitude: float = 1.0,
                            fase_inicial: float = 0.0):
        fase = fase_inicial
        for inicio, fim in zip(pontos, pontos[1:]):
            fase = self._desenhar_segmento(painter, inicio, fim, cor=cor, espessura=espessura,
                                           estilo=estilo, amplitude=amplitude, fase=fase)

    def _desenhar_bezier_quadratica(self, painter: QPainter, p0: QPointF, p1: QPointF, p2: QPointF,
                                    cor: str, espessura: float, estilo: str, amplitude: float,
                                    destacar_controles: bool = False):
        pontos = self._amostrar_bezier_quadratica(p0, p1, p2, segmentos=42)
        self._desenhar_polilinha(painter, pontos, cor=cor, espessura=espessura, estilo=estilo, amplitude=amplitude)
        if not destacar_controles:
            return
        self._desenhar_segmento(painter, p0, p1, tracejado=True, cor="#6fa8ff")
        self._desenhar_segmento(painter, p1, p2, tracejado=True, cor="#6fa8ff")
        self._desenhar_marca_x(painter, p0, cor="#7dffb3")
        self._desenhar_marca_x(painter, p1, cor="#ff7dd1")
        self._desenhar_marca_x(painter, p2, cor="#7dffb3")

    def _amostrar_bezier_quadratica(self, p0: QPointF, p1: QPointF, p2: QPointF, segmentos: int = 36) -> list[QPointF]:
        pontos: list[QPointF] = []
        n = max(8, int(segmentos))
        for i in range(n + 1):
            t = i / n
            u = 1.0 - t
            x = (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x())
            y = (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y())
            pontos.append(QPointF(x, y))
        return pontos

    def _desenhar_segmento(self, painter: QPainter, inicio: QPointF, fim: QPointF, tracejado: bool = False,
                           cor: str = "#ff5a00", espessura: float = 1.0, estilo: str = "solid",
                           amplitude: float = 1.0, fase: float = 0.0) -> float:
        comprimento = sqrt((fim.x() - inicio.x()) ** 2 + (fim.y() - inicio.y()) ** 2)
        if not tracejado and is_geometric_line_style(estilo):
            self._desenhar_segmento_geometrico(painter, inicio, fim, cor=cor, espessura=espessura,
                                               estilo=estilo, amplitude=max(0.2, float(amplitude)), fase=fase)
            return fase + comprimento
        pen = QPen(QColor(cor), espessura)
        if tracejado:
            pen.setStyle(Qt.DotLine)
        else:
            self._aplicar_estilo_caneta(pen, estilo)
        painter.setPen(pen)
        painter.drawLine(self._cena_para_tela(inicio), self._cena_para_tela(fim))
        return fase + comprimento

    def _desenhar_segmento_geometrico(self, painter: QPainter, inicio: QPointF, fim: QPointF,
                                      cor: str, espessura: float, estilo: str, amplitude: float, fase: float):
        p1 = QPointF(inicio)
        p2 = QPointF(fim)
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        comprimento = sqrt(dx * dx + dy * dy)
        if comprimento <= 0.001:
            return
        ux = dx / comprimento
        uy = dy / comprimento
        nx = -uy
        ny = ux
        amp = max(0.2, comprimento * 0.02) * amplitude
        passo = max(0.8, comprimento * 0.08)
        modo = "zigzag"
        if estilo == "zigzag_strong":
            amp, passo, modo = max(0.3, comprimento * 0.03) * amplitude, max(1.0, comprimento * 0.10), "zigzag"
        elif estilo == "wave_soft":
            amp, passo, modo = max(0.18, comprimento * 0.018) * amplitude, max(0.9, comprimento * 0.09), "wave"
        elif estilo == "wave_strong":
            amp, passo, modo = max(0.3, comprimento * 0.03) * amplitude, max(1.1, comprimento * 0.11), "wave"
        elif estilo == "half_moon":
            amp = max(0.25, comprimento * 0.02) * amplitude
            passo = max(1.1, comprimento * 0.12)
            ciclos = max(1, round(comprimento / passo))
            passo = comprimento / ciclos
            modo = "half_moon_full"
        elif estilo in {"dash_half_moon", "dash_half_moon_alt"}:
            amp = max(0.25, comprimento * 0.02) * amplitude
            passo = max(1.1, comprimento * 0.12)
            modo = "half_moon_dash"
        path = QPainterPath(self._cena_para_tela(p1))
        if modo == "zigzag":
            t = 0.0
            while t < comprimento:
                sentido = 1.0 if int((fase + t) / max(passo, 0.0001)) % 2 == 0 else -1.0
                px = p1.x() + (ux * t) + (nx * amp * sentido)
                py = p1.y() + (uy * t) + (ny * amp * sentido)
                path.lineTo(self._cena_para_tela(QPointF(px, py)))
                t += passo
            path.lineTo(self._cena_para_tela(p2))
        elif modo == "wave":
            periodos = max(1, int(comprimento / max(passo, 0.0001)))
            amostras = min(480, max(48, periodos * 24))
            for i in range(1, amostras + 1):
                t = (comprimento * i) / amostras
                seno = sin((2.0 * 3.14159265359 * (fase + t)) / passo)
                px = p1.x() + (ux * t) + (nx * amp * seno)
                py = p1.y() + (uy * t) + (ny * amp * seno)
                path.lineTo(self._cena_para_tela(QPointF(px, py)))
        elif modo == "half_moon_full":
            ciclos = max(1, round(comprimento / max(passo, 0.0001)))
            for ciclo in range(ciclos):
                base_inicio = passo * ciclo
                amostras_arco = min(120, max(14, int(passo * 8)))
                for i in range(1, amostras_arco + 1):
                    frac = i / amostras_arco
                    base_t = base_inicio + (passo * frac)
                    theta = (3.14159265359 * (fase + base_t)) / passo
                    altura = amp * abs(sin(theta))
                    px = p1.x() + (ux * base_t) + (nx * altura)
                    py = p1.y() + (uy * base_t) + (ny * altura)
                    path.lineTo(self._cena_para_tela(QPointF(px, py)))
        else:
            t = 0.0
            while t < comprimento:
                restante = comprimento - t
                if restante < (passo * 0.7):
                    fim_resto = QPointF(p1.x() + (ux * comprimento), p1.y() + (uy * comprimento))
                    path.lineTo(self._cena_para_tela(fim_resto))
                    break
                arco = min(passo, restante)
                amostras_arco = min(96, max(12, int(arco * 7)))
                for i in range(1, amostras_arco + 1):
                    frac = i / amostras_arco
                    base_t = t + (arco * frac)
                    theta = (3.14159265359 * (fase + base_t)) / passo
                    altura = amp * abs(sin(theta))
                    px = p1.x() + (ux * base_t) + (nx * altura)
                    py = p1.y() + (uy * base_t) + (ny * altura)
                    path.lineTo(self._cena_para_tela(QPointF(px, py)))
                if estilo != "half_moon":
                    gap = passo * (0.45 if estilo == "dash_half_moon" else 0.25)
                    t += arco + gap
                    if t < comprimento:
                        path.moveTo(self._cena_para_tela(QPointF(p1.x() + (ux * t), p1.y() + (uy * t))))
                else:
                    t += arco
        pen = QPen(QColor(cor), max(1.0, float(espessura)))
        pen.setStyle(Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(pen)
        painter.drawPath(path)

    def _aplicar_estilo_caneta(self, pen: QPen, estilo: str):
        pen.setStyle(pen_style_for_line(estilo))
        padrao = dash_pattern_for_line(estilo)
        if padrao:
            pen.setDashPattern(padrao)

    def _desenhar_marca_x(self, painter: QPainter, ponto: QPointF, cor: str = "#ff5a00"):
        pt = self._cena_para_tela(ponto)
        pen = QPen(QColor(cor), 1)
        painter.setPen(pen)
        painter.drawLine(int(pt.x() - 5), int(pt.y() - 5), int(pt.x() + 5), int(pt.y() + 5))
        painter.drawLine(int(pt.x() - 5), int(pt.y() + 5), int(pt.x() + 5), int(pt.y() - 5))

    def _distancia_ponto_segmento(self, a: QPointF, b: QPointF, p: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-9:
            return sqrt((p.x() - a.x()) ** 2 + (p.y() - a.y()) ** 2)
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return sqrt((p.x() - proj.x()) ** 2 + (p.y() - proj.y()) ** 2)

    def _projecao_no_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> QPointF:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-9:
            return QPointF(a)
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
        return QPointF(a.x() + (abx * t), a.y() + (aby * t))

    def _indices_elementos_em_ponto(self, pos: QPointF) -> list[int]:
        tolerancia = 8.0 / max(self.zoom, 0.001)
        candidatos: list[int] = []
        for idx in range(len(self.cena.elementos) - 1, -1, -1):
            el = self.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                if any(self._distancia_ponto_segmento(a, b, pos) <= tolerancia for a, b in zip(pontos, pontos[1:])):
                    candidatos.append(idx)
            elif el.get("tipo") == "bezier_quadratica":
                p0 = QPointF(*el["p0"])
                p1 = QPointF(*el["p1"])
                p2 = QPointF(*el["p2"])
                amostra = self._amostrar_bezier_quadratica(p0, p1, p2, segmentos=40)
                if any(self._distancia_ponto_segmento(a, b, pos) <= tolerancia for a, b in zip(amostra, amostra[1:])):
                    candidatos.append(idx)
            if el.get("molde"):
                fio_origem = el.get("fio_origem")
                fio_fim = el.get("fio_fim")
                if isinstance(fio_origem, (list, tuple)) and isinstance(fio_fim, (list, tuple)) and len(
                        fio_origem) == 2 and len(fio_fim) == 2:
                    p1 = QPointF(float(fio_origem[0]), float(fio_origem[1]))
                    p2 = QPointF(float(fio_fim[0]), float(fio_fim[1]))
                    if self._distancia_ponto_segmento(p1, p2, pos) <= tolerancia:
                        candidatos.append(idx)
                if el.get("mostrar_nome", True) and str(el.get("nome_molde") or "").strip():
                    pontos_nome = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                    base_nome = pontos_nome[:-1] if len(pontos_nome) >= 3 and pontos_nome[0] == pontos_nome[
                        -1] else pontos_nome
                    if base_nome:
                        cx = sum(p.x() for p in base_nome) / len(base_nome)
                        cy = sum(p.y() for p in base_nome) / len(base_nome)
                        if self._dist(QPointF(cx, cy), pos) <= (tolerancia * 2.0):
                            candidatos.append(idx)
        return candidatos

    def _indice_molde_em_ponto(self, pos: QPointF) -> int | None:
        for idx in self._indices_elementos_em_ponto(pos):
            if 0 <= idx < len(self.cena.elementos) and self.cena.elementos[idx].get("molde"):
                return idx
        return None

    def _clique_em_molde_selecionado(self, pos: QPointF) -> bool:
        if not self._selecionados:
            return False
        candidatos = set(self._indices_elementos_em_ponto(pos))
        for idx in self._selecionados:
            if idx in candidatos and 0 <= idx < len(self.cena.elementos):
                if self.cena.elementos[idx].get("molde"):
                    return True
        return False

    def _selecionar_proximo_em_ponto(self, pos: QPointF) -> bool:
        candidatos = self._indices_elementos_em_ponto(pos)
        if not candidatos:
            return False
        mesmo_cursor = (
                self._ciclo_selecao_cursor is not None
                and sqrt(
            (self._ciclo_selecao_cursor.x() - pos.x()) ** 2 + (self._ciclo_selecao_cursor.y() - pos.y()) ** 2)
                <= (8.0 / max(self.zoom, 0.001))
        )
        if not mesmo_cursor or candidatos != self._ciclo_selecao_indices:
            self._ciclo_selecao_indices = candidatos
            self._ciclo_selecao_cursor = QPointF(pos)
            proximo = candidatos[0]
        else:
            atual = next(iter(self._selecionados), None)
            if atual in candidatos:
                idx_atual = candidatos.index(atual)
                proximo = candidatos[(idx_atual + 1) % len(candidatos)]
            else:
                proximo = candidatos[0]
        self._selecionados = {proximo}
        self.update()
        return True
