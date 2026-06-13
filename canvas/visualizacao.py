from __future__ import annotations

import base64
from copy import deepcopy
from importlib import import_module
from math import acos, atan2, cos, degrees, hypot, log10, radians, sin, sqrt
from time import monotonic
from types import SimpleNamespace
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, \
    QPolygon, QWheelEvent
from PySide6.QtWidgets import QMenu, QWidget

from canvas.cena import CenaDocumento
from canvas.painel_coordenadas import PainelCoordenadas
from canvas.snap import SnapManager, SnapResult, chave_tipo_snap, rotulo_tipo_snap, tipo_snap_movimento_fluido
from core.formatacao import formatar_numero, numero_decimal_ponto
from core.geometry.engine import quadratic_bezier_control_for_point
from core.line_styles import dash_pattern_for_line, is_geometric_line_style, pen_style_for_line
from ui.hover_style import aplicar_hover_menu
from ui.posicao_janelas import salvar_posicao


class VisualizacaoCanvas(QWidget):
    LIMITE_DESFAZER = 250
    TAMANHO_NOME_PADRAO_CM = 3.0
    TAMANHO_NUMERO_PADRAO_CM = 0.7
    DISTANCIA_NUMERO_PADRAO_CM = 0.4

    zoom_changed = Signal(float)
    ferramenta_padrao_solicitada = Signal(str)
    snap_changed = Signal(bool)
    painel_coordenadas_changed = Signal(bool)
    painel_posicao_changed = Signal(int, int)
    elementos_alterados = Signal()

    def __init__(self, cena: CenaDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.cena = cena
        self.zoom = 1.0
        self.origem_cena = QPointF(0.0, 0.0)
        self.ferramenta_ativa: str | None = None
        self._pontos_reta: list[QPointF] = []
        self._pontos_reta_finalizados = False
        self._preview_reta: QPointF | None = None
        self._marcacoes_temporarias: list[QPointF] = []
        self._ponto_coordenada_aplicada: QPointF | None = None
        self._origem_preview_coordenadas: QPointF | None = None
        self._operacao_coordenadas_ativa = False
        self._operacao_coordenadas_origem: QPointF | None = None
        self._cursor_tela = QPointF(0.0, 0.0)
        self._historico_elementos: list[list[dict]] = [self._elementos_serializaveis()]
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
        self._ultimo_status_snap: str | None = None
        self._guia_fechamento: tuple[QPointF, QPointF] | None = None
        self._guias_alinhamento: list[tuple[QPointF, QPointF]] = []
        self._linha_cor = "#ffffff"
        self._cores_tecidos: dict[str, str] = {}
        self._mostrar_cor_tecidos = False
        self._cores_canvas: dict[str, str] = {
            "desenho": "#ffffff",
            "fundo": "#000000",
            "selecao": "#2da8ff",
            "grade": "#808080",
            "snap_desenho": "#6f6f6f",
            "snap_referencia": "#d71313",
        }
        self._cores_moldes: dict[str, dict] = {}
        self._estilo_linha_costura = "dash"
        self._usar_cores_ferramentas = False
        self._snap_cores_automaticas = True
        self._opacidade_imagens = 1.0
        self._grid_visivel = True
        self._visualizacao_instantanea_elementos: list[dict] = []
        self._linha_estilo = "solid"
        self._linha_espessura = 1.0
        self._linha_amplitude = 1.0
        self._unidade_sigla = "cm"
        self._unidade_fator = 1.0
        self._unidade_quadrado_sigla = "m"
        self._unidade_quadrado_fator = 100.0
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
        self._runtime_tool_cache: dict[str, object] = {}
        self._destacar_reta_temporaria: tuple[QPointF, QPointF] | None = None
        self._ultimo_clique_direito_ts = 0.0
        self._sequencia_clique_direito = 0
        self.lbl_status = None
        self._imagem_cache: dict[str, QPixmap] = {}
        self._mostrar_curva_original_emf = False
        self._piscando_ponto_restauracao_indices: set[int] = set()
        self._piscando_ponto_restauracao_visivel = False
        self._piscando_ponto_restauracao_geracao = 0
        self._zoom_interativo = False
        self._timer_fim_zoom = QTimer(self)
        self._timer_fim_zoom.setSingleShot(True)
        self._timer_fim_zoom.timeout.connect(self._finalizar_zoom_interativo)

        self.setMinimumSize(100, 100)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        # Política de foco padrão: pode receber foco por clique
        self.setFocusPolicy(Qt.ClickFocus)

        self.painel_coordenadas = PainelCoordenadas(self)
        self.painel_coordenadas.desfazer_ponto.connect(self._desfazer_ponto)
        self.painel_coordenadas.aplicar.connect(self._aplicar_coordenadas)
        self.painel_coordenadas.limpar.connect(self._limpar_marcacoes_coordenadas)
        self.painel_coordenadas.alternado.connect(self._set_painel_coordenadas_visivel)
        self.painel_coordenadas.posicao_alterada.connect(self._registrar_posicao_painel)
        self.painel_coordenadas.set_unidade_medida(self._unidade_sigla, self._unidade_fator)
        self.painel_coordenadas.show()

    # ========== MODIFICAÇÃO PRINCIPAL ==========
    def mousePressEvent(self, event: QMouseEvent):
        # Se a ferramenta ativa for "inserir_texto", não rouba o foco
        if self.ferramenta_ativa == "inserir_texto":
            event.accept()
            if self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_press"):
                self._runtime_tool.on_mouse_press(self, event)
            return
        super().mousePressEvent(event)
    # ========== FIM DA MODIFICAÇÃO ==========

    def set_zoom(self, zoom: float):
        self.zoom = max(0.025, min(zoom, 10000.0))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def set_ferramenta_ativa(self, tool_id: str):
        """Ativa a ferramenta e ajusta a política de foco do canvas."""
        mesma_ferramenta = tool_id == self.ferramenta_ativa and self._runtime_tool is not None
        if not mesma_ferramenta and self._runtime_tool and hasattr(self._runtime_tool, "on_deactivate"):
            self._runtime_tool.on_deactivate(self)
        if not mesma_ferramenta:
            self.cancelar_operacao_coordenadas(limpar_preview=True)
        self.ferramenta_ativa = tool_id
        self._runtime_tool = self._carregar_runtime_ferramenta(tool_id)
        if self._runtime_tool and hasattr(self._runtime_tool, "on_activate"):
            self._runtime_tool.on_activate(self)

        # ========== MODIFICAÇÃO PARA INSERIR TEXTO ==========
        if tool_id == "inserir_texto":
            self.setFocusPolicy(Qt.NoFocus)  # Canvas não ganha foco por clique
        else:
            self.setFocusPolicy(Qt.ClickFocus)  # Comportamento normal
        # ===================================================

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
        if tool_id in self._runtime_tool_cache:
            return self._runtime_tool_cache[tool_id]
        try:
            module = import_module(f"tools.{tool_id}_tool")
            tool_cls = getattr(module, "Ferramenta")
            tool = tool_cls()
            self._runtime_tool_cache[tool_id] = tool
            return tool
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
            self._ultimo_status_snap = None
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
        self._painel_coordenadas_posicao = pos
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

    def set_graduacao_visivel(self, visivel: bool) -> bool:
        alterou = False
        for elemento in self.cena.elementos:
            if not isinstance(elemento, dict) or not elemento.get("molde"):
                continue
            novo = bool(visivel)
            if bool(elemento.get("mostrar_graduacao", True)) != novo:
                elemento["mostrar_graduacao"] = novo
                alterou = True
        if alterou:
            self._emitir_elementos_alterados()
        self.update()
        return alterou

    def aplicar_estilo_linha_selecionados(self, estilo: dict | None) -> bool:
        if not self._selecionados or not isinstance(estilo, dict):
            return False
        alterou = False
        for idx in sorted(self._selecionados):
            if not (0 <= int(idx) < len(self.cena.elementos)):
                continue
            elemento = self.cena.elementos[int(idx)]
            if not isinstance(elemento, dict):
                continue
            is_molde = bool(elemento.get("molde"))
            if "espessura" in estilo:
                try:
                    espessura = max(1.0, float(estilo.get("espessura")))
                except (TypeError, ValueError):
                    espessura = 1.0
                if float(elemento.get("espessura", 1.0) or 1.0) != espessura:
                    elemento["espessura"] = espessura
                    alterou = True
                if is_molde and float(elemento.get("espessura_graduacao", 1.0) or 1.0) != espessura:
                    elemento["espessura_graduacao"] = espessura
                    alterou = True
            if "estilo" in estilo:
                novo_estilo = str(estilo.get("estilo") or "solid")
                if str(elemento.get("estilo", "solid")) != novo_estilo:
                    elemento["estilo"] = novo_estilo
                    alterou = True
            if "amplitude" in estilo:
                try:
                    amplitude = max(0.2, float(estilo.get("amplitude")))
                except (TypeError, ValueError):
                    amplitude = 1.0
                if float(elemento.get("amplitude", 1.0) or 1.0) != amplitude:
                    elemento["amplitude"] = amplitude
                    alterou = True
            if "cor" in estilo and not is_molde:
                cor = str(estilo.get("cor") or "").strip()
                if cor and str(elemento.get("cor", "")) != cor:
                    elemento["cor"] = cor
                    alterou = True
        if alterou:
            self._registrar_historico()
            self._emitir_elementos_alterados()
            self.update()
        return alterou

    def _cor_hex_segura(self, valor: object, padrao: str) -> str:
        """Normaliza uma cor recebida da janela principal sem quebrar o canvas."""
        try:
            cor = QColor(str(valor or ""))
            if cor.isValid():
                return cor.name()
        except Exception:
            pass
        return str(padrao)

    def set_config_cores_canvas(self, cores: dict | None):
        """Recebe as cores globais do canvas vindas da janela principal.

        A janela principal chama este método ao criar/abrir documentos. Ele
        precisa existir mesmo quando a configuração vier incompleta, para evitar
        falha de abertura do projeto.
        """
        base = {
            "desenho": "#ffffff",
            "fundo": "#000000",
            "selecao": "#2da8ff",
            "grade": "#808080",
            "snap_desenho": "#6f6f6f",
            "snap_referencia": "#d71313",
        }
        atual = dict(getattr(self, "_cores_canvas", base) or base)
        atual.update({k: atual.get(k, v) for k, v in base.items()})
        if isinstance(cores, dict):
            for chave, padrao in base.items():
                if chave in cores:
                    atual[chave] = self._cor_hex_segura(cores.get(chave), padrao)
        self._cores_canvas = atual
        self.update()

    def set_config_cores_moldes(
            self,
            cores: dict | None,
            estilo_linha_costura: str | None = None,
            usar_cores_ferramentas: bool | None = None,
    ):
        """Recebe as cores de moldes/itens técnicos vindas da janela principal."""
        normalizadas: dict[str, dict] = {}
        if isinstance(cores, dict):
            for chave, valor in cores.items():
                if isinstance(valor, dict):
                    item = {
                        "ativo": bool(valor.get("ativo", False)),
                        "cor": self._cor_hex_segura(valor.get("cor"), "#efefef"),
                    }
                    if "forma" in valor:
                        forma = str(valor.get("forma") or "").strip()
                        if forma in {"Circulo preenchido", "Quadrado preenchido", "Losango"}:
                            item["forma"] = forma
                    normalizadas[str(chave)] = item
        self._cores_moldes = normalizadas
        if estilo_linha_costura is not None:
            self._estilo_linha_costura = str(estilo_linha_costura or "dash")
        if usar_cores_ferramentas is not None:
            self._usar_cores_ferramentas = bool(usar_cores_ferramentas)
        self.update()

    def set_snap_cores_automaticas(self, ativo: bool):
        self._snap_cores_automaticas = bool(ativo)
        self.update()

    def set_opacidade_imagens(self, valor: float):
        try:
            self._opacidade_imagens = max(0.0, min(float(valor), 1.0))
        except (TypeError, ValueError):
            self._opacidade_imagens = 1.0
        self.update()

    def set_grid_visivel(self, visivel: bool):
        """Liga/desliga a grade sem depender de implementação externa."""
        self._grid_visivel = bool(visivel)
        self.update()

    def set_visualizacao_instantanea(self, elementos: list[dict] | None):
        """Mostra uma cópia visual temporária dos elementos atuais.

        Usado pelo botão de visualização instantânea da barra inferior. Não
        entra no histórico nem no arquivo salvo.
        """
        if not elementos:
            self._visualizacao_instantanea_elementos = []
        else:
            try:
                self._visualizacao_instantanea_elementos = [deepcopy(e) for e in elementos if isinstance(e, dict)]
            except Exception:
                self._visualizacao_instantanea_elementos = []
        self.update()

    def _config_cor_molde(self, chave: str, padrao: str) -> str:
        if bool(getattr(self, "_usar_cores_ferramentas", False)):
            return str(padrao)
        cfg = getattr(self, "_cores_moldes", {}).get(chave, {})
        if isinstance(cfg, dict) and bool(cfg.get("ativo", False)):
            return self._cor_hex_segura(cfg.get("cor"), padrao)
        return str(padrao)

    def _config_forma_molde(self, chave: str, padrao: str) -> str:
        cfg = getattr(self, "_cores_moldes", {}).get(chave, {})
        if isinstance(cfg, dict):
            forma = str(cfg.get("forma") or "").strip()
            if forma in {"Circulo preenchido", "Quadrado preenchido", "Losango"}:
                return forma
        return str(padrao)

    def _config_ponto_molde(self, chave: str, cor_padrao: str, forma_padrao: str) -> tuple[str, str]:
        return self._config_cor_molde(chave, cor_padrao), self._config_forma_molde(chave, forma_padrao)

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
        return formatar_numero(valor_unidade, casas_final)

    def formatar_distancia(self, valor_cena: float, casas: int | None = None) -> str:
        txt = self.formatar_valor_unidade(valor_cena, casas=casas)
        return f"{txt} {self._unidade_sigla}"

    def formatar_distancia_quadrado(self, valor_cena: float, casas: int | None = None) -> str:
        casas_final = self._casas_precisao if casas is None else max(0, int(casas))
        valor_unidade = float(valor_cena) / max(self._unidade_quadrado_fator, 1e-9)
        txt = formatar_numero(valor_unidade, casas_final)
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


    def _emitir_elementos_alterados(self) -> None:
        """Avisa a janela principal que a lista/estado dos moldes mudou."""
        try:
            self.elementos_alterados.emit()
        except Exception:
            pass

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
        if self._runtime_tool and hasattr(self._runtime_tool, "desfazer_etapa"):
            try:
                if self._runtime_tool.desfazer_etapa(self):
                    return
            except Exception:
                pass
        if self._remover_ultima_marcacao_coordenadas():
            return
        if self._pontos_reta and not (self._pontos_reta_finalizados and len(self._pontos_reta) == 1):
            self._desfazer_ponto()
            return
        self._garantir_estado_atual_no_historico()
        if self._indice_historico == 0:
            return
        self._indice_historico -= 1
        self.cena.elementos = self._elementos_serializaveis(self._historico_elementos[self._indice_historico])
        self._emitir_elementos_alterados()
        self.update()

    def refazer_acao(self):
        self._garantir_estado_atual_no_historico()
        if self._indice_historico >= len(self._historico_elementos) - 1:
            return
        self._indice_historico += 1
        self.cena.elementos = self._elementos_serializaveis(self._historico_elementos[self._indice_historico])
        self._emitir_elementos_alterados()
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
        if isinstance(self._buffer_copia.get("elementos"), list):
            itens = self._buffer_copia.get("elementos", [])
        elif self._buffer_copia.get("tipo") == "multiplos":
            itens = self._buffer_copia.get("elementos", [])
        else:
            itens = [self._buffer_copia]
        dx, dy = self._delta_colagem_para_centro(itens)
        if isinstance(self._buffer_copia.get("elementos"), list) or self._buffer_copia.get("tipo") == "multiplos":
            for item in itens:
                if not isinstance(item, dict):
                    continue
                novo = self._elemento_serializavel(item)
                self._transladar_elemento(novo, dx, dy)
                self.cena.elementos.append(novo)
                self._selecionados.add(len(self.cena.elementos) - 1)
        elif isinstance(self._buffer_copia, dict):
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

        # A dobra faz parte do molde: se o molde dobrado for movido,
        # a sombra/pontilhado, eixo salvo e dados de restauração precisam
        # acompanhar o mesmo deslocamento. Sem isso, a linha pontilhada fica
        # parada no canvas como se fosse um objeto solto.
        self._transladar_dados_dobra_elemento(elemento, dx, dy)

    def _transladar_ponto_serializado(self, valor, dx: float, dy: float):
        if isinstance(valor, (tuple, list)) and len(valor) >= 2:
            try:
                novo = [float(valor[0]) + dx, float(valor[1]) + dy]
                if len(valor) > 2:
                    novo.extend(valor[2:])
                return tuple(novo) if isinstance(valor, tuple) else novo
            except Exception:
                return valor
        return valor

    def _transladar_lista_pontos_serializada(self, valor, dx: float, dy: float):
        if not isinstance(valor, list):
            return valor
        saida = []
        for item in valor:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                saida.append(self._transladar_ponto_serializado(item, dx, dy))
            else:
                saida.append(item)
        return saida

    def _transladar_eixo_serializado(self, eixo, dx: float, dy: float):
        if not isinstance(eixo, dict):
            return eixo
        novo = dict(eixo)
        tipo = str(novo.get("tipo") or "").lower()
        try:
            if tipo == "h" and "valor" in novo:
                novo["valor"] = float(novo.get("valor", 0.0)) + dy
            elif tipo == "v" and "valor" in novo:
                novo["valor"] = float(novo.get("valor", 0.0)) + dx
            elif tipo == "line":
                if "p1" in novo:
                    novo["p1"] = self._transladar_ponto_serializado(novo.get("p1"), dx, dy)
                if "p2" in novo:
                    novo["p2"] = self._transladar_ponto_serializado(novo.get("p2"), dx, dy)
        except Exception:
            return eixo
        return novo

    def _transladar_dados_dobra_elemento(self, elemento: dict, dx: float, dy: float) -> None:
        if not isinstance(elemento, dict):
            return

        for chave_eixo in ("dobra_eixo",):
            if isinstance(elemento.get(chave_eixo), dict):
                elemento[chave_eixo] = self._transladar_eixo_serializado(elemento[chave_eixo], dx, dy)

        estado = elemento.get("estado_dobra")
        if isinstance(estado, dict):
            for chave in (
                "contorno_original",
                "contorno_dobrado",
                "contorno_aberto",
                "contorno_lado_original",
                "contorno_lado_dobrado",
                "contorno_lado_oculto",
                "contorno_pontilhado",
                "metade_movida",
                "pontos",
            ):
                if isinstance(estado.get(chave), list):
                    estado[chave] = self._transladar_lista_pontos_serializada(estado[chave], dx, dy)
            if isinstance(estado.get("eixo"), dict):
                estado["eixo"] = self._transladar_eixo_serializado(estado["eixo"], dx, dy)

        registros = elemento.get("contornos_dobra_original")
        if isinstance(registros, list):
            for registro in registros:
                if not isinstance(registro, dict):
                    continue
                for chave in (
                    "pontos",
                    "metade_movida",
                    "contorno_lado_original",
                    "contorno_lado_dobrado",
                    "contorno_lado_oculto",
                    "contorno_pontilhado",
                    "contorno_dobrado",
                    "contorno_aberto",
                ):
                    if isinstance(registro.get(chave), list):
                        registro[chave] = self._transladar_lista_pontos_serializada(registro[chave], dx, dy)
                if isinstance(registro.get("eixo"), dict):
                    registro["eixo"] = self._transladar_eixo_serializado(registro["eixo"], dx, dy)

    def recortar(self):
        self.copiar()
        self.apagar_selecionados()

    def apagar_selecionados(self):
        if not self._selecionados:
            return
        apagar = set(self._selecionados)
        for idx in list(self._selecionados):
            if 0 <= idx < len(self.cena.elementos) and self.cena.elementos[idx].get("molde"):
                apagar.update(self._indices_costuras_vinculadas(idx))
        self.cena.elementos = [el for idx, el in enumerate(self.cena.elementos) if idx not in apagar]
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

    def _executar_ferramenta_canvas_direta(self, tool_id: str):
        """Executa uma ferramenta simples diretamente no canvas.

        Usado pelo menu de contexto para ações que não precisam abrir página do
        ribbon. Assim o ponto de restauração funciona mesmo quando o botão ainda
        não estiver exposto na barra.
        """
        try:
            module = import_module(f"tools.{tool_id}_tool")
            tool_cls = getattr(module, "Ferramenta")
            tool = tool_cls()
            if hasattr(tool, "on_activate"):
                tool.on_activate(self)
                return
            if hasattr(tool, "ativar"):
                mensagem = tool.ativar()
                if getattr(self, "lbl_status", None) is not None:
                    self.lbl_status.setText(str(mensagem or ""))
        except Exception as exc:
            try:
                if getattr(self, "lbl_status", None) is not None:
                    self.lbl_status.setText(f"Falha ao executar {tool_id}: {exc}")
            except Exception:
                pass

    def _tem_ponto_restauracao_disponivel(self) -> bool:
        store = getattr(self, "_guimma_pontos_restauracao_moldes", None)
        return isinstance(store, dict) and bool(store)

    def _abrir_menu_contexto_canvas(self, pos_global: QPoint):
        pos_local = self.mapFromGlobal(pos_global)
        pos_cena = self._ponto_com_snap(QPointF(float(pos_local.x()), float(pos_local.y())))
        molde_no_cursor = self._indice_molde_em_ponto(pos_cena)
        menu = QMenu(self)
        aplicar_hover_menu(menu)
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
        tem_molde_alvo = bool(
            molde_no_cursor is not None
            or any(
                0 <= int(idx) < len(self.cena.elementos)
                and isinstance(self.cena.elementos[int(idx)], dict)
                and self.cena.elementos[int(idx)].get("molde")
                for idx in self._selecionados
            )
        )
        tem_ponto_restauracao = self._tem_ponto_restauracao_disponivel()
        a_excluir.setEnabled(tem_sel)
        a_recortar.setEnabled(tem_sel)
        a_copiar.setEnabled(tem_sel)
        a_criar_restore.setEnabled(tem_molde_alvo)
        a_restaurar.setEnabled(tem_ponto_restauracao)
        a_restaurar_copia.setEnabled(tem_ponto_restauracao)

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
        elif escolhido is a_criar_restore:
            if molde_no_cursor is not None and molde_no_cursor not in self._selecionados:
                self._selecionados = {molde_no_cursor}
                self.update()
            self._executar_ferramenta_canvas_direta("ponto_restauracao")
        elif escolhido is a_restaurar or escolhido is a_restaurar_copia:
            if molde_no_cursor is not None and molde_no_cursor not in self._selecionados:
                self._selecionados = {molde_no_cursor}
                self.update()
            self._executar_ferramenta_canvas_direta("restaurar_copia")

    def piscar_ponto_restauracao(self, indices, vezes: int = 4, intervalo_ms: int = 140):
        """Pisca em azul os moldes que acabaram de receber ponto de restauração."""
        elementos = list(getattr(self.cena, "elementos", []) or [])
        alvos: set[int] = set()
        try:
            iter_indices = list(indices or [])
        except TypeError:
            iter_indices = [indices]
        for idx in iter_indices:
            try:
                idx_int = int(idx)
            except Exception:
                continue
            if 0 <= idx_int < len(elementos):
                elemento = elementos[idx_int]
                if isinstance(elemento, dict) and elemento.get("molde"):
                    alvos.add(idx_int)
        if not alvos:
            return

        self._piscando_ponto_restauracao_geracao += 1
        geracao = self._piscando_ponto_restauracao_geracao
        self._piscando_ponto_restauracao_indices = set(alvos)
        self._piscando_ponto_restauracao_visivel = True
        self.update()

        total_passos = max(1, int(vezes)) * 2
        intervalo = max(60, int(intervalo_ms))

        def alternar(passos_restantes: int):
            if geracao != getattr(self, "_piscando_ponto_restauracao_geracao", None):
                return
            if passos_restantes <= 0:
                self._piscando_ponto_restauracao_indices.clear()
                self._piscando_ponto_restauracao_visivel = False
                self.update()
                return
            self._piscando_ponto_restauracao_visivel = not self._piscando_ponto_restauracao_visivel
            self.update()
            QTimer.singleShot(intervalo, lambda: alternar(passos_restantes - 1))

        QTimer.singleShot(intervalo, lambda: alternar(total_passos - 1))

    # ========== Métodos internos ==========

    def _registrar_historico(self):
        self._aplicar_padrao_grade_primeiro_molde()
        self._limpar_cache_runtime_elementos()
        snapshot = self._elementos_serializaveis()
        if self._indice_historico < len(self._historico_elementos) - 1:
            self._historico_elementos = self._historico_elementos[:self._indice_historico + 1]
        if self._historico_elementos and self._historico_elementos[-1] == snapshot:
            self._indice_historico = len(self._historico_elementos) - 1
            self._emitir_elementos_alterados()
            return
        self._historico_elementos.append(snapshot)
        if len(self._historico_elementos) > self.LIMITE_DESFAZER + 1:
            self._historico_elementos.pop(0)
        self._indice_historico = len(self._historico_elementos) - 1
        self._emitir_elementos_alterados()

    def _garantir_estado_atual_no_historico(self) -> None:
        snapshot = self._elementos_serializaveis()
        if not self._historico_elementos:
            self._historico_elementos = [snapshot]
            self._indice_historico = 0
            return
        if not (0 <= self._indice_historico < len(self._historico_elementos)):
            self._indice_historico = max(0, min(self._indice_historico, len(self._historico_elementos) - 1))
        if self._historico_elementos[self._indice_historico] == snapshot:
            return
        if self._indice_historico < len(self._historico_elementos) - 1:
            self._historico_elementos = self._historico_elementos[:self._indice_historico + 1]
        self._historico_elementos.append(snapshot)
        if len(self._historico_elementos) > self.LIMITE_DESFAZER + 1:
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
        if self._painel_coordenadas_posicao is not None:
            x, y = self._painel_coordenadas_posicao
            self.painel_coordenadas.move(QPoint(int(x), int(y)))
            salvar_posicao(self.painel_coordenadas, "painel:coordenadas")
            return
        x = max(8, self.width() - self.painel_coordenadas.width() - 12)
        y = 16
        self.painel_coordenadas.move(
            self._limitar_posicao_painel_auxiliar(QPoint(x, y), self.painel_coordenadas.width(), self.painel_coordenadas.height())
        )
        salvar_posicao(self.painel_coordenadas, "painel:coordenadas")

    def calcular_posicao_painel_auxiliar(self, largura: int, altura: int, abaixo_coordenadas: bool = True) -> QPoint:
        margem_direita = 12
        margem_topo = 16
        x = max(8, self.width() - int(largura) - margem_direita)
        y = margem_topo
        if abaixo_coordenadas and self.painel_coordenadas.isVisible():
            x = self.painel_coordenadas.x() + self.painel_coordenadas.width() - int(largura)
            y = self.painel_coordenadas.y() + self.painel_coordenadas.height() + 8
        max_x = max(8, self.width() - int(largura) - 8)
        max_y = max(margem_topo, self.height() - int(altura) - 8)
        x = max(8, min(x, max_x))
        y = max(margem_topo, min(y, max_y))
        return QPoint(int(x), int(y))

    def _limitar_posicao_painel_auxiliar(self, pos: QPoint, largura: int, altura: int) -> QPoint:
        max_x = max(8, self.width() - int(largura) - 8)
        max_y = max(16, self.height() - int(altura) - 8)
        return QPoint(max(8, min(int(pos.x()), max_x)), max(16, min(int(pos.y()), max_y)))

    def _tela_para_cena(self, ponto: QPointF) -> QPointF:
        return QPointF((ponto.x() / self.zoom) + self.origem_cena.x(),
                       (ponto.y() / self.zoom) + self.origem_cena.y())

    def _cena_para_tela(self, ponto: QPointF) -> QPointF:
        return QPointF((ponto.x() - self.origem_cena.x()) * self.zoom,
                       (ponto.y() - self.origem_cena.y()) * self.zoom)

    @staticmethod
    def _coordenadas_bbox_elemento(elemento: dict):
        if not isinstance(elemento, dict):
            return

        def adicionar(item):
            try:
                if isinstance(item, dict):
                    yield float(item["x"]), float(item["y"])
                elif isinstance(item, (tuple, list)) and len(item) >= 2:
                    yield float(item[0]), float(item[1])
            except Exception:
                return

        for chave in (
            "pontos",
            "controle_cantos",
            "pontos_controle_principais",
            "controle_auxiliares",
            "pontos_auxiliares",
            "pontos_principais",
            "pontos_controle_curva",
            "pontos_controle",
            "controle_pontos",
            "marcacoes_no_perimetro",
        ):
            for item in elemento.get(chave, []) or []:
                yield from adicionar(item)
        for chave in ("p0", "p1", "p2", "centro", "fio_origem", "fio_fim", "pos"):
            item = elemento.get(chave)
            if item is not None:
                yield from adicionar(item)

    @staticmethod
    def _assinatura_bbox_elemento(elemento: dict) -> tuple:
        assinatura = []
        for chave in (
            "pontos",
            "controle_cantos",
            "pontos_controle_principais",
            "controle_auxiliares",
            "pontos_auxiliares",
            "pontos_principais",
            "pontos_controle_curva",
            "pontos_controle",
            "controle_pontos",
            "marcacoes_no_perimetro",
        ):
            valor = elemento.get(chave)
            if isinstance(valor, (list, tuple)):
                primeiro = repr(valor[0]) if valor else ""
                ultimo = repr(valor[-1]) if valor else ""
                assinatura.append((chave, id(valor), len(valor), primeiro, ultimo))
        for chave in ("p0", "p1", "p2", "centro", "fio_origem", "fio_fim", "pos"):
            valor = elemento.get(chave)
            if valor is not None:
                assinatura.append((chave, repr(valor)))
        return tuple(assinatura)

    def _bbox_cena_elemento(self, elemento: dict) -> tuple[float, float, float, float] | None:
        assinatura = self._assinatura_bbox_elemento(elemento)
        if elemento.get("_runtime_bbox_assinatura") == assinatura:
            return elemento.get("_runtime_bbox_cena")
        pontos = list(self._coordenadas_bbox_elemento(elemento))
        if not pontos:
            elemento["_runtime_bbox_assinatura"] = assinatura
            elemento["_runtime_bbox_cena"] = None
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        elemento["_runtime_bbox_assinatura"] = assinatura
        elemento["_runtime_bbox_cena"] = bbox
        return bbox

    def _elemento_proximo_ponto_cena(self, elemento: dict, ponto: QPointF, margem_cena: float) -> bool:
        bbox = self._bbox_cena_elemento(elemento)
        if bbox is None:
            return True
        min_x, min_y, max_x, max_y = bbox
        return (
            min_x - margem_cena <= ponto.x() <= max_x + margem_cena
            and min_y - margem_cena <= ponto.y() <= max_y + margem_cena
        )

    def _elemento_visivel_no_viewport(self, elemento: dict, margem_px: float = 32.0) -> bool:
        if elemento.get("tipo") == "imagem":
            return True
        bbox = self._bbox_cena_elemento(elemento)
        if bbox is None:
            return True
        margem_cena = float(margem_px) / max(float(self.zoom), 0.001)
        viewport_min_x = self.origem_cena.x() - margem_cena
        viewport_min_y = self.origem_cena.y() - margem_cena
        viewport_max_x = self.origem_cena.x() + (self.width() / max(float(self.zoom), 0.001)) + margem_cena
        viewport_max_y = self.origem_cena.y() + (self.height() / max(float(self.zoom), 0.001)) + margem_cena
        min_x, min_y, max_x, max_y = bbox
        return not (
            max_x < viewport_min_x
            or min_x > viewport_max_x
            or max_y < viewport_min_y
            or min_y > viewport_max_y
        )

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

    def _rotulo_snap_resultado(self, resultado: SnapResult | None = None) -> str:
        resultado = self._snap_resultado if resultado is None else resultado
        return rotulo_tipo_snap(getattr(resultado, "tipo", None))

    def descricao_snap_atual(self) -> str:
        if not self._snap_resultado:
            return ""
        return f"Snap: {self._rotulo_snap_resultado(self._snap_resultado)}"

    def _atualizar_status_snap(self) -> None:
        if not self._snap_resultado:
            self._ultimo_status_snap = None
            return
        texto = self.descricao_snap_atual()
        if not texto or texto == self._ultimo_status_snap:
            return
        self._ultimo_status_snap = texto
        if getattr(self, "lbl_status", None) is not None:
            self.lbl_status.setText(texto)

    def _prioridade_tipo_snap(self, tipo: str) -> int:
        ordem = {
            "nó": 0,
            "controle principal": 0,
            "controle auxiliar": 1,
            "controle": 1,
            "interseção": 2,
            "centro": 3,
            "borda": 4,
            "ponto médio": 5,
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
            self._ultimo_status_snap = None
            return pos_cena

        tol_px = self._tolerancia_snap_px()
        tol_cena = tol_px / max(self.zoom, 0.001)
        candidatos = self._snap_manager.calcular_candidatos(
            self.cena, pos_cena, self.zoom, tolerancia_px=tol_px
        )

        for idx, el in enumerate(self.cena.elementos):
            if not self._elemento_proximo_ponto_cena(el, pos_cena, tol_cena * 2.5):
                continue
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
            for chave, tipo_controle in (
                ("controle_cantos", "controle principal"),
                ("pontos_controle_principais", "controle principal"),
                ("controle_auxiliares", "controle auxiliar"),
                ("pontos_auxiliares", "controle auxiliar"),
            ):
                for p in el.get(chave, []) or []:
                    try:
                        if isinstance(p, dict):
                            ponto = QPointF(float(p["x"]), float(p["y"]))
                        elif isinstance(p, (list, tuple)) and len(p) >= 2:
                            ponto = QPointF(float(p[0]), float(p[1]))
                        else:
                            continue
                    except Exception:
                        continue
                    self._adicionar_candidato_snap(candidatos, pos_cena, ponto, tipo_controle, idx, tol_cena)
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
                    pos_nome = el.get("ponto_texto_nome") or el.get("ponto_texto") or el.get("nome_posicao") or el.get("nome_centro")
                    if isinstance(pos_nome, (list, tuple)) and len(pos_nome) == 2:
                        p_nome = QPointF(float(pos_nome[0]), float(pos_nome[1]))
                        self._adicionar_candidato_snap(candidatos, pos_cena, p_nome, "nome", idx, tol_cena * 1.5)
                    else:
                        pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                        base = pts[:-1] if len(pts) >= 2 and pts[0] == pts[-1] else pts
                        if base:
                            cx = sum(p.x() for p in base) / len(base)
                            cy = sum(p.y() for p in base) / len(base)
                            p_nome = QPointF(cx, cy)
                            self._adicionar_candidato_snap(candidatos, pos_cena, p_nome, "nome", idx, tol_cena * 1.5)

        candidatos.extend(self._candidatos_snap_temporarios(pos_cena, tol_cena))

        pontos_coord = list(getattr(self, "_marcacoes_temporarias", []) or [])
        if self._ponto_coordenada_aplicada is not None and not pontos_coord:
            pontos_coord.append(self._ponto_coordenada_aplicada)
        for ponto_coord in pontos_coord:
            dist = self._dist(pos_cena, ponto_coord)
            if dist <= tol_cena:
                candidatos.append(SnapResult(
                    ponto=QPointF(ponto_coord),
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
        self._atualizar_status_snap()
        if self._snap_resultado:
            return self._snap_resultado.ponto
        return pos_cena

    def _ponto_com_snap_movimento(self, pos_tela: QPointF, ignorar_elementos=None, elementos_sombra=None) -> QPointF:
        pos_cena = self._tela_para_cena(pos_tela)
        if not self._snap_ativo:
            self._snap_resultado = None
            self._snap_candidatos = []
            self._snap_indice = 0
            self._ultimo_status_snap = None
            return pos_cena

        tol_px = self._tolerancia_snap_px()
        self._ponto_com_snap(pos_tela)
        ignorados: set[int] = set()
        for idx in ignorar_elementos or []:
            try:
                ignorados.add(int(idx))
            except Exception:
                continue

        candidatos = [
            c for c in self._snap_candidatos
            if tipo_snap_movimento_fluido(c.tipo)
            and (c.elemento_idx is None or int(c.elemento_idx) not in ignorados)
        ]
        candidatos.extend(self._candidatos_snap_sombra(elementos_sombra, pos_cena, tol_px))
        candidatos.sort(key=lambda c: (self._prioridade_tipo_snap(c.tipo), c.distancia))
        self._snap_candidatos = candidatos
        if candidatos:
            self._snap_indice = min(self._snap_indice, len(candidatos) - 1)
            self._snap_resultado = candidatos[self._snap_indice]
            self._atualizar_status_snap()
            return self._snap_resultado.ponto

        self._snap_resultado = None
        self._snap_indice = 0
        self._ultimo_status_snap = None
        return pos_cena

    def _candidatos_snap_sombra(self, elementos_sombra, pos_cena: QPointF, tol_px: float) -> list[SnapResult]:
        elementos = self._normalizar_elementos_sombra(elementos_sombra)
        if not elementos:
            return []
        try:
            candidatos = self._snap_manager.calcular_candidatos(
                SimpleNamespace(elementos=elementos),
                pos_cena,
                self.zoom,
                tolerancia_px=tol_px,
            )
        except Exception:
            return []
        return [
            SnapResult(ponto=QPointF(c.ponto), tipo=c.tipo, distancia=c.distancia, elemento_idx=None)
            for c in candidatos
            if tipo_snap_movimento_fluido(c.tipo)
        ]

    @staticmethod
    def _normalizar_elementos_sombra(elementos_sombra) -> list[dict]:
        if not elementos_sombra:
            return []
        fonte = elementos_sombra.values() if isinstance(elementos_sombra, dict) else elementos_sombra
        saida: list[dict] = []
        for item in fonte:
            el = item
            if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], dict):
                el = item[1]
            if isinstance(el, dict):
                saida.append(el)
        return saida

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
        origem = self._origem_coordenadas_atual()
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

    def _origem_coordenadas_atual(self) -> QPointF:
        if isinstance(self._operacao_coordenadas_origem, QPointF):
            return QPointF(self._operacao_coordenadas_origem)
        origem = None
        if self._runtime_tool and hasattr(self._runtime_tool, "origem_coordenadas"):
            try:
                origem = self._runtime_tool.origem_coordenadas(self)
            except Exception:
                origem = None
        if isinstance(origem, QPointF):
            return QPointF(origem)
        if self._pontos_reta:
            return QPointF(self._pontos_reta[-1])
        if isinstance(self._origem_preview_coordenadas, QPointF):
            return QPointF(self._origem_preview_coordenadas)
        return QPointF(0.0, 0.0)

    def definir_origem_preview_coordenadas(self, origem: QPointF | None) -> None:
        self._origem_preview_coordenadas = QPointF(origem) if isinstance(origem, QPointF) else None

    def iniciar_operacao_coordenadas(self, origem: QPointF) -> None:
        self._operacao_coordenadas_origem = QPointF(origem)
        self._operacao_coordenadas_ativa = True
        self.painel_coordenadas.atualizar_preview(origem, origem)

    def atualizar_operacao_coordenadas(self, destino: QPointF) -> None:
        if not self._operacao_coordenadas_ativa:
            return
        self.painel_coordenadas.atualizar_preview(self._origem_coordenadas_atual(), QPointF(destino))

    def finalizar_operacao_coordenadas(self, destino: QPointF | None = None) -> None:
        if not self._operacao_coordenadas_ativa:
            return
        origem = self._origem_coordenadas_atual()
        destino_final = QPointF(destino) if isinstance(destino, QPointF) else origem
        self.painel_coordenadas.atualizar_preview(origem, destino_final)
        self._operacao_coordenadas_ativa = False
        self._operacao_coordenadas_origem = None
        self._origem_preview_coordenadas = QPointF(destino_final)

    def cancelar_operacao_coordenadas(self, limpar_preview: bool = False) -> None:
        self._operacao_coordenadas_ativa = False
        self._operacao_coordenadas_origem = None
        if limpar_preview and hasattr(self, "painel_coordenadas"):
            self._origem_preview_coordenadas = None
            self.painel_coordenadas.atualizar_preview(None, None)

    def _atualizar_preview_coordenadas_mouse(self, destino: QPointF) -> None:
        if not hasattr(self, "painel_coordenadas") or not self.painel_coordenadas.isVisible():
            return
        if not self._operacao_coordenadas_ativa:
            return
        self.painel_coordenadas.atualizar_preview(self._origem_coordenadas_atual(), QPointF(destino))

    def _ferramenta_gerencia_coordenadas(self) -> bool:
        return bool(getattr(self._runtime_tool, "gerencia_coordenadas_operacao", False))

    def _coordenadas_auto_apos_press(self, event: QMouseEvent, aceito: bool, ativa_antes: bool) -> None:
        if not aceito or self._ferramenta_gerencia_coordenadas() or event.button() != Qt.LeftButton:
            return
        pos = self._ponto_com_snap(event.position())
        if ativa_antes and self._operacao_coordenadas_ativa:
            self.finalizar_operacao_coordenadas(pos)
        elif not self._operacao_coordenadas_ativa:
            self.iniciar_operacao_coordenadas(pos)

    def _coordenadas_auto_apos_release(self, event: QMouseEvent, aceito: bool) -> None:
        if not aceito or self._ferramenta_gerencia_coordenadas() or event.button() != Qt.LeftButton:
            return
        if self._operacao_coordenadas_ativa:
            self.finalizar_operacao_coordenadas(self._ponto_com_snap(event.position()))

    def _desfazer_ponto(self):
        if self._remover_ultima_marcacao_coordenadas():
            return
        if not self._pontos_reta:
            return
        self._pontos_reta_finalizados = False
        self._pontos_reta.pop()
        if self._pontos_reta:
            self._preview_reta = self._pontos_reta[-1]
        else:
            self._preview_reta = None
            self._guia_fechamento = None
        self.update()

    def _remover_ultima_marcacao_coordenadas(self) -> bool:
        if self._marcacoes_temporarias:
            self._marcacoes_temporarias.pop()
            self._ponto_coordenada_aplicada = (
                QPointF(self._marcacoes_temporarias[-1]) if self._marcacoes_temporarias else None
            )
            if self._ponto_coordenada_aplicada is None:
                self._snap_resultado = None
                self._snap_candidatos = []
                self._snap_indice = 0
            self.update()
            return True
        if self._ponto_coordenada_aplicada is not None:
            self._ponto_coordenada_aplicada = None
            self._snap_resultado = None
            self._snap_candidatos = []
            self._snap_indice = 0
            self.update()
            return True
        return False

    def _limpar_marcacoes_coordenadas(self) -> None:
        self._marcacoes_temporarias.clear()
        self._ponto_coordenada_aplicada = None
        self._snap_resultado = None
        self._snap_candidatos = []
        self._snap_indice = 0
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
            self._pontos_reta_finalizados = True
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
        self._zoom_interativo = True
        self._timer_fim_zoom.start(140)
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

    def _finalizar_zoom_interativo(self):
        if not self._zoom_interativo:
            return
        self._zoom_interativo = False
        self.update()

    def keyPressEvent(self, event):
        if (
            self.ferramenta_ativa == "extrair_molde"
            and self._runtime_tool
            and hasattr(self._runtime_tool, "on_key_press")
        ):
            if self._runtime_tool.on_key_press(self, event):
                return
        if event.modifiers() & Qt.ControlModifier:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._ativar_ferramenta_janela_principal("propriedades")
                event.accept()
                return
            if event.key() == Qt.Key_M:
                self._ativar_ferramenta_janela_principal("informacoes_moldes")
                event.accept()
                return
        if self.ferramenta_ativa != "extrair_molde" and self._runtime_tool and hasattr(self._runtime_tool, "on_key_press"):
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
        ferramenta = str(self.ferramenta_ativa or "")
        ferramentas_com_clique_proprio = {
            "extrair_molde",
            "costura",
            "alinhar",
            "girar",
            "espelhar",
            "elemento_paralelo",
            "recortar",
            "cortar",
            "sentido_fio",
            "dobrar",
            "desdobrar",
        }
        runtime_ja_processado = False
        # Ferramentas ativas precisam receber o botão direito antes do canvas abrir
        # menu/propriedades. Isso permite cancelar/confirmar fluxos como papel real.
        runtime_tem_prioridade = (
            ferramenta in ferramentas_com_clique_proprio
            or (event.button() == Qt.RightButton and ferramenta and ferramenta != "selecionar")
        )
        if (
            runtime_tem_prioridade
            and self._runtime_tool
            and hasattr(self._runtime_tool, "on_mouse_press")
        ):
            runtime_ja_processado = True
            ativa_antes = self._operacao_coordenadas_ativa
            aceito = self._runtime_tool.on_mouse_press(self, event)
            self._coordenadas_auto_apos_press(event, aceito, ativa_antes)
            if aceito:
                return
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
        elif event.button() == Qt.LeftButton:
            self._sequencia_clique_direito = 0
        if not runtime_ja_processado and self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_press"):
            ativa_antes = self._operacao_coordenadas_ativa
            aceito = self._runtime_tool.on_mouse_press(self, event)
            self._coordenadas_auto_apos_press(event, aceito, ativa_antes)
            if aceito:
                return
        if self.ferramenta_ativa == "selecionar" and event.button() == Qt.RightButton:
            pos = self._ponto_com_snap(event.position())
            elementos_alvo = self._indices_elementos_em_ponto(pos)
            elemento_alvo = elementos_alvo[0] if elementos_alvo else None
            if elemento_alvo is not None:
                self._selecionados = {elemento_alvo}
                self.update()
                if not (event.modifiers() & Qt.ControlModifier):
                    event.accept()
                    return
            if event.modifiers() & Qt.ControlModifier:
                if self._selecionar_proximo_em_ponto(pos):
                    event.accept()
                    return
            self._abrir_menu_contexto_canvas(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = self._ponto_com_snap(event.position())
        if not self._ferramenta_gerencia_coordenadas():
            self._atualizar_preview_coordenadas_mouse(pos)
        if self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_move"):
            if self._runtime_tool.on_mouse_move(self, event):
                self.update()
                return
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_release"):
            aceito = self._runtime_tool.on_mouse_release(self, event)
            self._coordenadas_auto_apos_release(event, aceito)
            if aceito:
                return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.ferramenta_ativa == "extrair_molde":
            if self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_double_click"):
                self._runtime_tool.on_mouse_double_click(self, event)
            event.accept()
            return
        if event.button() == Qt.RightButton and not (event.modifiers() & Qt.ControlModifier):
            pos_cena_bruta = self._tela_para_cena(event.position())
            molde_alvo = self._indice_molde_em_ponto(pos_cena_bruta)
            if molde_alvo is None and self._snap_resultado is not None and self._snap_resultado.elemento_idx is not None:
                idx_snap = int(self._snap_resultado.elemento_idx)
                if 0 <= idx_snap < len(self.cena.elementos) and self.cena.elementos[idx_snap].get("molde"):
                    molde_alvo = idx_snap
            if molde_alvo is not None:
                self._sequencia_clique_direito = 0
                self._selecionados = {molde_alvo}
                self.update()
                self._ativar_ferramenta_janela_principal("propriedades")
                event.accept()
                return
        if self._runtime_tool and hasattr(self._runtime_tool, "on_mouse_double_click"):
            if self._runtime_tool.on_mouse_double_click(self, event):
                return
        if self.ferramenta_ativa != "selecionar" and event.button() in (Qt.LeftButton, Qt.RightButton):
            self.ferramenta_padrao_solicitada.emit("selecionar")
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        fundo = getattr(self, "_cores_canvas", {}).get("fundo", "#000000")
        painter.fillRect(self.rect(), QColor(fundo))
        painter.setRenderHint(QPainter.Antialiasing, True)

        if bool(getattr(self, "_grid_visivel", True)):
            self._desenhar_grade_canvas(painter)

        self._desenhar_visualizacao_instantanea(painter)

        # Desenha destaque de reta temporária (para modo paralela/perpendicular)
        if self._destacar_reta_temporaria:
            pen = QPen(QColor("#ffaa00"), 3, Qt.DashDotLine)
            painter.setPen(pen)
            p1_tela = self._cena_para_tela(self._destacar_reta_temporaria[0])
            p2_tela = self._cena_para_tela(self._destacar_reta_temporaria[1])
            painter.drawLine(p1_tela, p2_tela)

        elementos_visiveis: set[int] = set()
        for idx, elemento in enumerate(self.cena.elementos):
            if not self._elemento_visivel_no_viewport(elemento):
                continue
            if self._elemento_oculto_por_visualizacao_molde(elemento):
                continue
            elementos_visiveis.add(idx)
            if elemento.get("tipo") == "imagem":
                self._desenhar_imagem_referencia(painter, elemento)
                continue
            cor_base = self._cor_linha_elemento(elemento)
            selecionado = idx in self._selecionados
            is_molde = bool(elemento.get("molde"))
            cor = cor_base
            esp = float(elemento.get("espessura", 1.0))
            if elemento.get("tipo") == "polyline":
                cor, esp, estilo = self._estilo_por_subtipo_audaces(elemento, cor, esp, str(elemento.get("estilo", "solid")))
                pontos = self._pontos_render_elemento(elemento)
                if len(pontos) < 2:
                    continue
                if is_molde:
                    self._desenhar_preenchimento_molde(painter, elemento, pontos)
                if elemento.get("pontos_tracado_real"):
                    self._desenhar_polilinha(painter, pontos, cor=cor, espessura=esp,
                                             estilo=estilo,
                                             amplitude=float(elemento.get("amplitude", 1.0)),
                                             fase_inicial=float(elemento.get("fase_inicio", 0.0)))
                    self._desenhar_marcacoes_piques_elemento(painter, elemento, cor)
                    continue
                if self._desenhar_parabola_3p_elemento(
                    painter,
                    elemento,
                    cor=cor,
                    espessura=esp,
                    estilo=estilo,
                    amplitude=float(elemento.get("amplitude", 1.0)),
                ):
                    self._desenhar_marcacoes_piques_elemento(painter, elemento, cor)
                    continue
                if self._elemento_curva_suave(elemento) and not elemento.get("pontos_tracado_real"):
                    self._desenhar_curva_suave_elemento(painter, elemento, cor=cor, espessura=esp, estilo=estilo)
                    self._desenhar_marcacoes_piques_elemento(painter, elemento, cor)
                    continue
                self._desenhar_polilinha(painter, pontos, cor=cor, espessura=esp,
                                         estilo=estilo,
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

            self._desenhar_marcacoes_piques_elemento(painter, elemento, cor)

        for marca in getattr(self, "_marcacoes_temporarias", []) or []:
            self._desenhar_marca_x(painter, QPointF(marca), cor="#ff40ff", tamanho_px=6)

        self._desenhar_overlays_moldes(painter, elementos_visiveis)

        if self._runtime_tool and hasattr(self._runtime_tool, "on_paint_overlay"):
            self._runtime_tool.on_paint_overlay(self, painter)
        self._desenhar_overlay_snap_ativo(painter)

    def _desenhar_grade_canvas(self, painter: QPainter):
        """Desenha uma grade leve no canvas, respeitando zoom/origem."""
        try:
            passo_cena = 10.0
            if self.zoom >= 12.0:
                passo_cena = 1.0
            elif self.zoom >= 4.0:
                passo_cena = 5.0
            elif self.zoom < 0.35:
                passo_cena = 50.0
            cor_grade = QColor(getattr(self, "_cores_canvas", {}).get("grade", "#808080"))
            cor_grade.setAlpha(45)
            painter.save()
            painter.setPen(QPen(cor_grade, 1.0))
            canto1 = self._tela_para_cena(QPointF(0.0, 0.0))
            canto2 = self._tela_para_cena(QPointF(float(self.width()), float(self.height())))
            min_x, max_x = sorted((canto1.x(), canto2.x()))
            min_y, max_y = sorted((canto1.y(), canto2.y()))
            inicio_x = int(min_x // passo_cena) * passo_cena
            inicio_y = int(min_y // passo_cena) * passo_cena
            x = inicio_x
            limite = 0
            while x <= max_x and limite < 4000:
                a = self._cena_para_tela(QPointF(x, min_y))
                b = self._cena_para_tela(QPointF(x, max_y))
                painter.drawLine(QPointF(a.x(), 0.0), QPointF(b.x(), float(self.height())))
                x += passo_cena
                limite += 1
            y = inicio_y
            limite = 0
            while y <= max_y and limite < 4000:
                a = self._cena_para_tela(QPointF(min_x, y))
                b = self._cena_para_tela(QPointF(max_x, y))
                painter.drawLine(QPointF(0.0, a.y()), QPointF(float(self.width()), b.y()))
                y += passo_cena
                limite += 1
            painter.restore()
        except Exception:
            return

    def _desenhar_preenchimento_molde(self, painter: QPainter, elemento: dict, pontos: list[QPointF]):
        if not bool(elemento.get("visual_preencher", False)):
            return
        if len(pontos) < 3:
            return
        base = pontos[:-1] if pontos[0] == pontos[-1] else pontos
        if len(base) < 3:
            return
        cor = self._cor_preenchimento_molde(elemento)
        path = QPainterPath(self._cena_para_tela(base[0]))
        for pt in base[1:]:
            path.lineTo(self._cena_para_tela(pt))
        path.closeSubpath()
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(cor)
        painter.drawPath(path)
        painter.restore()

    @staticmethod
    def _cor_preenchimento_molde(elemento: dict) -> QColor:
        cor = QColor(str(elemento.get("cor") or "#ffffff"))
        if not cor.isValid():
            cor = QColor("#ffffff")
        return cor

    def _cor_linha_elemento(self, elemento: dict, padrao: str = "#d0d0d0") -> str:
        cor_base = str(elemento.get("cor") or padrao)
        if elemento.get("molde") and bool(getattr(self, "_mostrar_cor_tecidos", False)):
            tecido = str(elemento.get("tecido") or "").strip()
            cor_tecido = getattr(self, "_cores_tecidos", {}).get(tecido)
            cor = QColor(str(cor_tecido or ""))
            if cor.isValid():
                return cor.name()
        cor = QColor(cor_base)
        return cor.name() if cor.isValid() else QColor(padrao).name()

    def _molde_por_id_visualizacao(self, molde_id: str) -> dict | None:
        alvo = str(molde_id or "").strip()
        if not alvo:
            return None
        for el in getattr(self.cena, "elementos", []) or []:
            if isinstance(el, dict) and el.get("molde") and self._molde_id_elemento(el) == alvo:
                return el
        return None

    def _elemento_oculto_por_visualizacao_molde(self, elemento: dict) -> bool:
        if not isinstance(elemento, dict) or elemento.get("molde"):
            return False
        metadados = elemento.get("metadados") if isinstance(elemento.get("metadados"), dict) else {}
        subtipo = str(elemento.get("subtipo_audaces") or metadados.get("subtipo_audaces") or "").strip()
        costura_id = str(elemento.get("costura_de_molde_id") or metadados.get("costura_de_molde_id") or "").strip()
        linha_id = str(elemento.get("molde_id") or metadados.get("molde_id") or "").strip()
        if subtipo == "costura" or costura_id:
            molde = self._molde_por_id_visualizacao(costura_id or linha_id)
            return bool(isinstance(molde, dict) and molde.get("mostrar_costura", True) is False)
        if subtipo == "linha_interna" or bool(elemento.get("molde_linha_vinculada")):
            molde = self._molde_por_id_visualizacao(linha_id)
            return bool(isinstance(molde, dict) and molde.get("mostrar_linhas_auxiliares", True) is False)
        return False

    def _desenhar_visualizacao_instantanea(self, painter: QPainter):
        elementos = getattr(self, "_visualizacao_instantanea_elementos", []) or []
        if not elementos:
            return
        painter.save()
        painter.setOpacity(0.34)
        for elemento in elementos:
            if not isinstance(elemento, dict):
                continue
            if not self._elemento_visivel_no_viewport(elemento):
                continue
            cor = str(elemento.get("_cor_visualizacao_instantanea") or elemento.get("cor") or "#ffffff")
            esp = max(1.0, float(elemento.get("espessura", 1.0) or 1.0))
            try:
                if elemento.get("tipo") == "polyline":
                    pontos = [QPointF(float(x), float(y)) for x, y in elemento.get("pontos", [])]
                    if elemento.get("pontos_tracado_real") and len(pontos) >= 2:
                        self._desenhar_polilinha(
                            painter,
                            pontos,
                            cor=cor,
                            espessura=esp,
                            estilo=str(elemento.get("estilo", "solid")),
                            amplitude=float(elemento.get("amplitude", 1.0) or 1.0),
                            fase_inicial=float(elemento.get("fase_inicio", 0.0) or 0.0),
                        )
                        continue
                    if self._desenhar_parabola_3p_elemento(
                        painter,
                        elemento,
                        cor=cor,
                        espessura=esp,
                        estilo=str(elemento.get("estilo", "solid")),
                        amplitude=float(elemento.get("amplitude", 1.0) or 1.0),
                    ):
                        continue
                    if len(pontos) >= 2:
                        self._desenhar_polilinha(
                            painter,
                            pontos,
                            cor=cor,
                            espessura=esp,
                            estilo=str(elemento.get("estilo", "solid")),
                            amplitude=float(elemento.get("amplitude", 1.0) or 1.0),
                            fase_inicial=float(elemento.get("fase_inicio", 0.0) or 0.0),
                        )
                elif elemento.get("tipo") == "bezier_quadratica":
                    self._desenhar_bezier_quadratica(
                        painter,
                        QPointF(*elemento["p0"]),
                        QPointF(*elemento["p1"]),
                        QPointF(*elemento["p2"]),
                        cor=cor,
                        espessura=esp,
                        estilo=str(elemento.get("estilo", "solid")),
                        amplitude=float(elemento.get("amplitude", 1.0) or 1.0),
                        destacar_controles=False,
                    )
            except Exception:
                continue
        painter.restore()

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
        opacidade_elemento = max(0.05, min(float(elemento.get("opacidade", 0.72)), 1.0))
        opacidade_global = max(0.0, min(float(getattr(self, "_opacidade_imagens", 1.0)), 1.0))
        painter.setOpacity(max(0.0, min(opacidade_elemento * opacidade_global, 1.0)))
        painter.drawPixmap(int(x), int(y), int(largura_tela), int(altura_tela), pixmap)
        painter.restore()

    def _desenhar_overlay_snap_ativo(self, painter: QPainter):
        if not self._snap_ativo or not self._snap_resultado:
            return
        if self._snap_sobre_graduacao_visivel(self._snap_resultado):
            return
        snap_tela = self._cena_para_tela(self._snap_resultado.ponto)
        cor = QColor("#ffd400")
        if self._snap_resultado.tipo in {"controle", "controle principal", "controle auxiliar"}:
            cor = QColor(getattr(self, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        elif self._snap_resultado.tipo in {"borda", "ponto médio"}:
            cor = QColor("#7df9ff")
        elif self._snap_resultado.tipo == "interseção":
            cor = QColor("#ff62b0")
        if not bool(getattr(self, "_snap_cores_automaticas", True)):
            tipo_snap = chave_tipo_snap(getattr(self._snap_resultado, "tipo", ""))
            chave = (
                "snap_referencia"
                if tipo_snap in {"controle", "controle principal", "controle auxiliar", "intersecao"}
                else "snap_desenho"
            )
            cor = QColor(getattr(self, "_cores_canvas", {}).get(chave, "#6f6f6f"))
        pen = QPen(cor, 1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(snap_tela, 6, 6)
        painter.drawLine(QPointF(snap_tela.x() - 8, snap_tela.y()), QPointF(snap_tela.x() + 8, snap_tela.y()))
        painter.drawLine(QPointF(snap_tela.x(), snap_tela.y() - 8), QPointF(snap_tela.x(), snap_tela.y() + 8))
        rotulo = self._rotulo_snap_resultado(self._snap_resultado)
        if rotulo:
            fonte = painter.font()
            fonte.setPointSize(max(8, fonte.pointSize()))
            fonte.setBold(True)
            painter.setFont(fonte)
            metrics = QFontMetrics(fonte)
            largura = metrics.horizontalAdvance(rotulo) + 12
            altura = metrics.height() + 6
            x = snap_tela.x() + 10
            y = snap_tela.y() - altura - 10
            if x + largura > self.width() - 4:
                x = snap_tela.x() - largura - 10
            if y < 4:
                y = snap_tela.y() + 12
            caixa = QRectF(float(x), float(y), float(largura), float(altura))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 185))
            painter.drawRoundedRect(caixa, 4, 4)
            painter.setPen(QPen(cor, 1.0))
            painter.drawText(caixa.adjusted(6, 2, -6, -2), Qt.AlignCenter, rotulo)

    def _snap_sobre_graduacao_visivel(self, resultado: SnapResult | None) -> bool:
        if resultado is None:
            return False
        tipo = str(getattr(resultado, "tipo", "") or "").strip().lower()
        if tipo not in {"borda", "nó", "no", "controle", "controle principal", "controle auxiliar", "ponto médio"}:
            return False
        ponto = getattr(resultado, "ponto", None)
        if not isinstance(ponto, QPointF):
            return False
        tolerancia = max(0.04, 8.0 / max(float(getattr(self, "zoom", 1.0)), 0.001))
        for elemento in getattr(self.cena, "elementos", []) or []:
            if not isinstance(elemento, dict) or not elemento.get("molde"):
                continue
            if elemento.get("mostrar_graduacao", True) is False:
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in elemento.get("pontos", []) or []]
            if len(pontos) < 3:
                continue
            base = pontos[:-1] if pontos and pontos[0] == pontos[-1] else pontos
            for _nome, _cor, contorno in self._contornos_graduacao_tabela(elemento, base):
                if any(
                    self._distancia_ponto_segmento(a, b, ponto) <= tolerancia
                    for a, b in zip(contorno, contorno[1:])
                ):
                    return True
        return False

    def _ferramenta_dobra_ativa(self) -> bool:
        ferramenta = str(getattr(self, "ferramenta_ativa", "") or "").strip().lower()
        return ferramenta in {"dobrar", "desdobrar"}

    def _molde_tem_referencia_dobra_original(self, el: dict) -> bool:
        if not isinstance(el, dict):
            return False
        if isinstance(el.get("contornos_dobra_original"), list) and bool(el.get("contornos_dobra_original")):
            return True
        estado = el.get("estado_dobra") if isinstance(el.get("estado_dobra"), dict) else None
        if estado and estado.get("contorno_lado_oculto"):
            return True
        return False

    def _deve_desenhar_contorno_dobra_original(self, el: dict) -> bool:
        """Mostra o pontilhado enquanto o molde permanecer dobrado.

        Esse pontilhado representa onde o lado do papel ficou depois da dobra.
        Por isso ele deve continuar visível mesmo após sair da ferramenta
        Dobrar/Desdobrar. Ele só desaparece quando o molde é desdobrado.
        """
        if not isinstance(el, dict):
            return False
        if not self._molde_tem_referencia_dobra_original(el):
            return False
        # Se o usuário desligou explicitamente a visualização, respeita.
        if el.get("mostrar_contorno_dobra_original") is False:
            return False
        estado = el.get("estado_dobra") if isinstance(el.get("estado_dobra"), dict) else None
        dobrado = bool(el.get("molde_dobrado")) or bool(estado and estado.get("ativo"))
        # Durante a ferramenta ativa também permite visualizar a referência
        # de uma dobra selecionada. Fora dela, só mostra se o molde está dobrado.
        return bool(dobrado or self._ferramenta_dobra_ativa())

    def _deve_desenhar_eixo_dobra_salvo(self) -> bool:
        """Não desenha eixo salvo da dobra como overlay permanente.

        A linha/eixo azul é apenas uma guia temporária da operação atual,
        desenhada pela própria ferramenta Dobrar/Desdobrar enquanto o usuário
        está escolhendo a dobra. Se o eixo salvo do molde for redesenhado aqui,
        ele pode aparecer no local antigo quando o molde já foi movido e, ao
        abrir a ferramenta novamente, dá a impressão de que a linha ficou presa
        no canvas.

        O eixo continua salvo nos dados do molde para restaurar/desdobrar, mas
        não deve ser exibido por este overlay global.
        """
        return False

    def _desenhar_overlays_moldes(self, painter: QPainter, elementos_visiveis: set[int] | None = None):
        for idx, el in enumerate(self.cena.elementos):
            if not el.get("molde"):
                continue
            if elementos_visiveis is not None and idx not in elementos_visiveis:
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 3:
                continue
            base = pontos[:-1] if pontos and pontos[0] == pontos[-1] else pontos
            if not base:
                continue
            # A referência pontilhada acompanha o lado dobrado do papel.
            # Ela NÃO representa mais o molde aberto antigo; representa onde o lado ficou após dobrar.
            # O eixo azul continua sendo apenas guia operacional de Dobrar/Desdobrar.
            if self._deve_desenhar_contorno_dobra_original(el):
                self._desenhar_contorno_dobra_original(painter, el)
            if self._deve_desenhar_eixo_dobra_salvo():
                self._desenhar_eixo_dobra_salvo(painter, el)

            self._desenhar_graduacao_tabela_molde(painter, el, base)

            if idx in getattr(self, "_piscando_ponto_restauracao_indices", set()) and getattr(self, "_piscando_ponto_restauracao_visivel", False):
                self._desenhar_piscar_ponto_restauracao(painter, base)

            if idx in self._selecionados and self.ferramenta_ativa != "manipular_pontos":
                self._desenhar_selecao_molde(painter, base, el)

            self._desenhar_margens_molde_canvas(painter, el, base)

            self._desenhar_texto_config_molde_canvas(
                painter,
                el,
                base,
                chave="nome",
                texto=str(el.get("nome_molde") or ""),
                visivel=bool(el.get("mostrar_nome", True)),
                padrao_ref="Centro centro",
            )

            self._desenhar_texto_config_molde_canvas(
                painter,
                el,
                base,
                chave="descricao",
                texto=str(el.get("descricao") or ""),
                visivel=bool(el.get("visual_descricao", el.get("mostrar_descricao", False))),
                padrao_ref="Centro abaixo",
            )
            self._desenhar_texto_config_molde_canvas(
                painter,
                el,
                base,
                chave="observacoes",
                texto=str(el.get("observacoes") or el.get("observacao") or ""),
                visivel=bool(el.get("visual_observacoes", el.get("mostrar_observacoes", False))),
                padrao_ref="Centro topo",
            )
            self._desenhar_metadados_molde_canvas(painter, el, base)

            if el.get("mostrar_fio", True):
                cor_fio = self._config_cor_molde("fio", "#ffffff")
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
                bbox_tela = self._bbox_tela_pontos(base)
                fio_visual_px = self._valor_float_molde(el, ("fio_tamanho_px", "tam_fio_px", "tamanho_fio_px"), None)
                if fio_visual_px is not None:
                    p1_tela, p2_tela = self._calcular_fio_tela_fixo(p1, p2, bbox_tela, float(fio_visual_px))
                    self._desenhar_seta_fio_tela(painter, p1_tela, p2_tela, cor=cor_fio)
                else:
                    p1_tela = self._cena_para_tela(p1)
                    p2_tela = self._cena_para_tela(p2)
                    self._desenhar_seta_fio(painter, p1, p2, cor=cor_fio)

                rotulo_fio = (
                        el.get("fio_rotulo")
                        or el.get("fio_texto")
                        or el.get("titulo_fio")
                        or el.get("nome_fio")
                        or ""
                )
                if rotulo_fio:
                    if fio_visual_px is not None:
                        self._desenhar_rotulo_fio_tela(
                            painter,
                            p1_tela,
                            p2_tela,
                            str(rotulo_fio),
                            tamanho=self._tamanho_pixel_molde(el, ("tam_fio_px", "tamanho_fio_px"), 10.0),
                            cor=cor_fio,
                        )
                    else:
                        self._desenhar_rotulo_fio(
                            painter,
                            p1,
                            p2,
                            str(rotulo_fio),
                            tamanho=self._tamanho_visual_molde(el, ("tam_fio", "tamanho_fio", "fonte_fio"), 9.0),
                            cor=cor_fio,
                        )
                else:
                    ang = float(el.get("fio_angulo", 90.0))
                    fonte_fio = painter.font()
                    tamanho_fio_px = self._tamanho_pixel_molde(el, ("tam_fio_px", "tamanho_fio_px"), 10.0)
                    fonte_fio.setPixelSize(int(max(6, round(tamanho_fio_px))))
                    painter.setFont(fonte_fio)
                    cor_fio = self._config_cor_molde("fio", "#ffffff")
                    painter.setPen(QPen(QColor(cor_fio), 1.0))
                    texto_ang = f"{int(round(ang))}°"
                    metrics_fio = QFontMetrics(painter.font())
                    largura_ang = metrics_fio.horizontalAdvance(texto_ang)
                    altura_ang = metrics_fio.height()
                    x_ang = p2_tela.x() + 6.0
                    y_ang = p2_tela.y() + 4.0
                    x_ang = max(bbox_tela[0] + 2.0, min(x_ang, bbox_tela[2] - largura_ang - 2.0))
                    y_ang = max(bbox_tela[1] + altura_ang, min(y_ang, bbox_tela[3] - 2.0))
                    painter.drawText(int(x_ang), int(y_ang), texto_ang)

            mostrar_numeros = bool(el.get("mostrar_numeros", el.get("mostrar_controles", True)))
            if mostrar_numeros:
                cantos = [QPointF(float(x), float(y)) for x, y in el.get("controle_cantos", [])]
                if cantos:
                    cx = sum(p.x() for p in cantos) / len(cantos)
                    cy = sum(p.y() for p in cantos) / len(cantos)
                else:
                    cx, cy = 0.0, 0.0
                painter.setPen(QPen(QColor(self._config_cor_molde("numeros", "#ffffff")), 1.0))
                fonte_num = painter.font()
                tamanho_num_px = self._tamanho_texto_cm_para_px(
                    self._altura_texto_config_cm(el, "numero", self.TAMANHO_NUMERO_PADRAO_CM),
                    minimo_px=7.0,
                    maximo_px=220.0,
                )
                fonte_num.setPixelSize(int(round(tamanho_num_px)))
                fonte_num.setBold(False)
                painter.setFont(fonte_num)
                metrics_num = QFontMetrics(painter.font())
                distancia_num_cm = self._valor_float_molde_decimal(
                    el,
                    ("numero_distancia_cm", "distancia_numero_cm", "afastamento_numero_cm"),
                    self.DISTANCIA_NUMERO_PADRAO_CM,
                )
                afastamento = max(2.0, float(distancia_num_cm) * max(float(getattr(self, "zoom", 1.0)), 0.01))
                cantos_numeracao = self._cantos_para_numeracao_horaria_tela(cantos)
                centro_numeros = QPointF(cx, cy)
                itens_numeracao = []
                for i, pt in enumerate(cantos_numeracao, start=1):
                    itens_numeracao.append((pt, str(i), True))
                for i, pt in enumerate(self._pontos_piques_para_numeracao(el, cantos), start=1):
                    itens_numeracao.append((pt, str(i), False))
                self._desenhar_numeros_molde_canvas(painter, metrics_num, itens_numeracao, centro_numeros, afastamento)
                if el.get("mostrar_controles", True) and self._ferramenta_manipulacao_ativa():
                    aux = [QPointF(float(x), float(y)) for x, y in el.get("controle_auxiliares", [])]
                    cor_aux = QColor(self._config_cor_molde("ponto_nao_graduado", "#ff3b30"))
                    painter.setPen(QPen(cor_aux, 1.0))
                    painter.setBrush(cor_aux)
                    for pt in aux:
                        pt_tela = self._cena_para_tela(pt)
                        painter.drawRect(int(pt_tela.x() - 2), int(pt_tela.y() - 2), 4, 4)

    def _desenhar_graduacao_moldes_visiveis(self, painter: QPainter, elementos_visiveis: set[int] | None = None):
        for idx, el in enumerate(self.cena.elementos):
            if not isinstance(el, dict) or not el.get("molde"):
                continue
            if elementos_visiveis is not None and idx not in elementos_visiveis:
                continue
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
            if len(pontos) < 3:
                continue
            base = pontos[:-1] if pontos and pontos[0] == pontos[-1] else pontos
            if base:
                self._desenhar_graduacao_tabela_molde(painter, el, base)

    def _desenhar_graduacao_tabela_molde(self, painter: QPainter, el: dict, base: list[QPointF]) -> None:
        if el.get("mostrar_graduacao", True) is False:
            return
        contornos = self._contornos_graduacao_tabela(el, base)
        if not contornos:
            return
        painter.save()
        try:
            if el.get("visual_caminho_grade", False):
                self._desenhar_caminhos_graduacao_molde(painter, el, base)
            for _nome, cor, pontos in contornos:
                self._desenhar_polilinha(
                    painter,
                    pontos,
                    cor=self._cor_tamanho_graduacao(el, _nome, cor),
                    espessura=self._espessura_graduacao_molde(el),
                    estilo="solid",
                )
            cor_base = self._cor_tamanho_base_graduacao(el)
            if cor_base:
                pontos_base = [QPointF(pt) for pt in base]
                if len(pontos_base) >= 2:
                    pontos_base.append(QPointF(pontos_base[0]))
                    self._desenhar_polilinha(
                        painter,
                        pontos_base,
                        cor=cor_base,
                        espessura=self._espessura_graduacao_molde(el),
                        estilo="solid",
                    )
        finally:
            painter.restore()

    def _desenhar_caminhos_graduacao_molde(self, painter: QPainter, el: dict, base: list[QPointF]) -> None:
        caminhos = self._caminhos_graduacao_tabela(el, base)
        if not caminhos:
            return
        for nome, cor, origem, destino in caminhos:
            self._desenhar_polilinha(
                painter,
                [origem, destino],
                cor=self._cor_tamanho_graduacao(el, nome, cor),
                espessura=max(1.0, self._espessura_graduacao_molde(el) * 0.75),
                estilo="dash",
            )

    def _cor_tamanho_base_graduacao(self, el: dict) -> str | None:
        tamanhos = el.get("graduacao_tamanhos") if isinstance(el, dict) else None
        if not isinstance(tamanhos, list) or not tamanhos:
            return None
        linhas = [linha for linha in tamanhos if isinstance(linha, dict) and linha.get("ativo", True)]
        if not linhas:
            return None
        base_idx = next((idx for idx, linha in enumerate(linhas) if linha.get("base")), len(linhas) // 2)
        cor = QColor(str(linhas[base_idx].get("cor") or ""))
        if not cor.isValid():
            return None
        return self._config_cor_molde("tamanho_base", cor.name())

    def _cor_tamanho_graduacao(self, el: dict, nome: str, cor_padrao: str) -> str:
        chave = self._chave_cor_tamanho_graduacao(el, nome)
        return self._config_cor_molde(chave, cor_padrao) if chave else str(cor_padrao)

    @staticmethod
    def _chave_cor_tamanho_graduacao(el: dict, nome: str) -> str | None:
        tamanhos = el.get("graduacao_tamanhos") if isinstance(el, dict) else None
        if not isinstance(tamanhos, list) or not tamanhos:
            return None
        linhas = [linha for linha in tamanhos if isinstance(linha, dict) and linha.get("ativo", True)]
        if not linhas:
            return None
        base_idx = next((idx for idx, linha in enumerate(linhas) if linha.get("base")), len(linhas) // 2)
        nome_txt = str(nome or "").strip()
        for idx, linha in enumerate(linhas):
            atual = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if atual != nome_txt:
                continue
            if idx < base_idx:
                return "tamanhos_menores"
            if idx > base_idx:
                return "tamanhos_maiores"
            return "tamanho_base"
        return None

    @staticmethod
    def _espessura_graduacao_molde(el: dict) -> float:
        valor = el.get("espessura_graduacao") if "espessura_graduacao" in el else el.get("espessura", 1.0)
        try:
            return max(1.0, float(valor or 1.0))
        except (TypeError, ValueError):
            return 1.0

    @staticmethod
    def _contornos_graduacao_tabela(el: dict, base: list[QPointF]) -> list[tuple[str, str, list[QPointF]]]:
        if not isinstance(el, dict) or not isinstance(base, list) or len(base) < 2:
            return []
        tabela = el.get("graduacao_tabela") if isinstance(el.get("graduacao_tabela"), dict) else {}
        pontos_cfg = tabela.get("pontos") if isinstance(tabela, dict) else None
        if not isinstance(pontos_cfg, dict):
            pontos_cfg = el.get("graduacao_pontos")
        if not isinstance(pontos_cfg, dict) or not pontos_cfg:
            return []

        tamanhos = el.get("graduacao_tamanhos")
        if not isinstance(tamanhos, list) or not tamanhos:
            return []
        linhas = [dict(linha) for linha in tamanhos if isinstance(linha, dict) and linha.get("ativo", True)]
        if not linhas:
            return []
        base_idx = next((idx for idx, linha in enumerate(linhas) if linha.get("base")), len(linhas) // 2)
        base_nome = str(linhas[base_idx].get("tamanho") or linhas[base_idx].get("nome") or "").strip()

        contorno = [QPointF(pt) for pt in base]
        if len(contorno) > 1 and contorno[0] == contorno[-1]:
            contorno = contorno[:-1]
        if len(contorno) < 2:
            return []

        saida: list[tuple[str, str, list[QPointF]]] = []
        for linha in linhas:
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if not nome or nome == base_nome:
                continue
            cor = str(linha.get("cor") or "#ffcc00")
            if not QColor(cor).isValid():
                cor = "#ffcc00"
            deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
                pontos_cfg,
                nome,
                len(contorno),
                contorno=contorno,
                referencias=VisualizacaoCanvas._pontos_referencia_graduacao(el),
            )
            if not deslocamentos:
                continue
            pontos_tamanho = [
                QPointF(pt.x() + dx, pt.y() + dy)
                for pt, (dx, dy) in zip(contorno, deslocamentos)
            ]
            if len(pontos_tamanho) >= 2:
                pontos_tamanho.append(QPointF(pontos_tamanho[0]))
                saida.append((nome, cor, pontos_tamanho))
        return saida

    @staticmethod
    def _caminhos_graduacao_tabela(el: dict, base: list[QPointF]) -> list[tuple[str, str, QPointF, QPointF]]:
        if not isinstance(base, list) or len(base) < 2:
            return []
        contorno = [QPointF(pt) for pt in base]
        if len(contorno) > 1 and contorno[0] == contorno[-1]:
            contorno = contorno[:-1]
        if len(contorno) < 2:
            return []
        caminhos: list[tuple[str, str, QPointF, QPointF]] = []
        for nome, cor, pontos_tamanho in VisualizacaoCanvas._contornos_graduacao_tabela(el, contorno):
            pontos = [QPointF(pt) for pt in pontos_tamanho]
            if len(pontos) > 1 and pontos[0] == pontos[-1]:
                pontos = pontos[:-1]
            for origem, destino in zip(contorno, pontos):
                if VisualizacaoCanvas._dist_qpoints(origem, destino) > 1e-7:
                    caminhos.append((nome, cor, QPointF(origem), QPointF(destino)))
        return caminhos

    @staticmethod
    def _deslocamentos_graduacao_tamanho(
        pontos_cfg: dict,
        tamanho: str,
        quantidade: int,
        *,
        contorno: list[QPointF] | None = None,
        referencias: list[QPointF] | None = None,
    ) -> list[tuple[float, float]]:
        if quantidade <= 0:
            return []
        ancoras: dict[int, tuple[float, float]] = {}
        contorno_valido = contorno if isinstance(contorno, list) and len(contorno) == quantidade else None
        referencias_validas = [ponto for ponto in referencias or [] if isinstance(ponto, QPointF)]
        if contorno_valido:
            for ponto in referencias_validas:
                idx_ref = VisualizacaoCanvas._indice_mais_proximo_no_contorno(contorno_valido, ponto)
                if idx_ref is not None:
                    ancoras.setdefault(idx_ref, (0.0, 0.0))
        for chave, cfg in VisualizacaoCanvas._iter_pontos_graduacao_cfg(pontos_cfg):
            valores = cfg.get("valores") if isinstance(cfg, dict) else None
            valor_tamanho = valores.get(tamanho) if isinstance(valores, dict) else None
            if not isinstance(valor_tamanho, dict):
                continue
            dx = VisualizacaoCanvas._float_graduacao(valor_tamanho.get("dx"))
            dy = VisualizacaoCanvas._float_graduacao(valor_tamanho.get("dy"))
            idx = None
            if contorno_valido:
                ponto_cfg = VisualizacaoCanvas._qpoint_graduacao_cfg(cfg.get("ponto"))
                if ponto_cfg is not None:
                    idx = VisualizacaoCanvas._indice_mais_proximo_no_contorno(contorno_valido, ponto_cfg)
            try:
                idx_cfg = int(cfg.get("indice", chave))
            except Exception:
                idx_cfg = None
            if (
                idx is None
                and contorno_valido
                and idx_cfg is not None
                and 0 <= idx_cfg < len(referencias_validas)
            ):
                idx = VisualizacaoCanvas._indice_mais_proximo_no_contorno(contorno_valido, referencias_validas[idx_cfg])
            if idx is None:
                idx = idx_cfg
            if idx is not None and 0 <= int(idx) < quantidade:
                ancoras[int(idx)] = (dx, dy)
        if not ancoras or not any(abs(dx) > 1e-9 or abs(dy) > 1e-9 for dx, dy in ancoras.values()):
            return []
        if contorno_valido:
            return VisualizacaoCanvas._interpolar_deslocamentos_ancorados(quantidade, ancoras)
        saida = [(0.0, 0.0) for _ in range(quantidade)]
        for idx, deslocamento in ancoras.items():
            if 0 <= idx < quantidade:
                saida[idx] = deslocamento
        return saida

    @staticmethod
    def _iter_pontos_graduacao_cfg(pontos_cfg: dict):
        if not isinstance(pontos_cfg, dict):
            return
        for chave, cfg in pontos_cfg.items():
            if isinstance(cfg, dict):
                yield chave, cfg

    @staticmethod
    def _pontos_referencia_graduacao(el: dict) -> list[QPointF]:
        if not isinstance(el, dict):
            return []
        for chave in ("pontos_controle_principais", "controle_cantos", "pontos_graduacao"):
            origem = el.get(chave)
            if not isinstance(origem, list) or not origem:
                continue
            pontos = []
            for item in origem:
                ponto = VisualizacaoCanvas._qpoint_graduacao_cfg(item)
                if ponto is not None:
                    pontos.append(ponto)
            if len(pontos) > 1 and VisualizacaoCanvas._dist_qpoints(pontos[0], pontos[-1]) <= 1e-7:
                pontos.pop()
            if pontos:
                return pontos
        return []

    @staticmethod
    def _qpoint_graduacao_cfg(valor) -> QPointF | None:
        try:
            if isinstance(valor, QPointF):
                return QPointF(valor)
            if isinstance(valor, dict):
                return QPointF(float(valor["x"]), float(valor["y"]))
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return QPointF(float(valor[0]), float(valor[1]))
        except Exception:
            return None
        return None

    @staticmethod
    def _indice_mais_proximo_no_contorno(contorno: list[QPointF], ponto: QPointF) -> int | None:
        if not contorno:
            return None
        distancias = [
            (VisualizacaoCanvas._dist_qpoints(atual, ponto), idx)
            for idx, atual in enumerate(contorno)
        ]
        return min(distancias, key=lambda item: item[0])[1]

    @staticmethod
    def _interpolar_deslocamentos_ancorados(quantidade: int, ancoras: dict[int, tuple[float, float]]) -> list[tuple[float, float]]:
        saida = [(0.0, 0.0) for _ in range(quantidade)]
        indices = sorted({idx for idx in ancoras if 0 <= int(idx) < quantidade})
        if not indices:
            return saida
        if len(indices) == 1:
            saida[indices[0]] = ancoras[indices[0]]
            return saida
        for pos, inicio in enumerate(indices):
            fim = indices[(pos + 1) % len(indices)]
            dx0, dy0 = ancoras[inicio]
            dx1, dy1 = ancoras[fim]
            passo_total = (fim - inicio) % quantidade
            if passo_total <= 0:
                passo_total = quantidade
            for passo in range(passo_total + 1):
                idx = (inicio + passo) % quantidade
                t = passo / passo_total if passo_total else 0.0
                saida[idx] = (dx0 + ((dx1 - dx0) * t), dy0 + ((dy1 - dy0) * t))
        return saida

    @staticmethod
    def _dist_qpoints(a: QPointF, b: QPointF) -> float:
        return hypot(float(a.x()) - float(b.x()), float(a.y()) - float(b.y()))

    @staticmethod
    def _float_graduacao(valor) -> float:
        return numero_decimal_ponto(valor, 0.0)

    def _desenhar_numeros_molde_canvas(
        self,
        painter: QPainter,
        metrics: QFontMetrics,
        itens: list[tuple[QPointF, str, bool]],
        centro: QPointF,
        afastamento: float,
    ) -> None:
        layouts = self._layout_numeros_molde_canvas(metrics, itens, centro, afastamento)
        cor_ponto, forma_ponto = self._config_ponto_molde("ponto_controle", "#000000", "Quadrado preenchido")
        for item in layouts:
            if item["marcador"]:
                pt_tela = self._cena_para_tela(item["ponto"])
                self._desenhar_marcador_ponto_tela(painter, pt_tela, cor_ponto, forma_ponto, 3)
        for item in layouts:
            largura = float(item["largura"])
            altura = float(item["altura"])
            rect = QRectF(
                float(item["x"]) - (largura / 2.0),
                float(item["y"]) - (altura / 2.0),
                largura,
                altura,
            )
            painter.drawText(rect, Qt.AlignCenter, str(item["texto"]))

    def _layout_numeros_molde_canvas(
        self,
        metrics: QFontMetrics,
        itens: list[tuple[QPointF, str, bool]],
        centro: QPointF,
        afastamento: float,
    ) -> list[dict]:
        layouts: list[dict] = []
        for pt, texto, desenhar_marcador in itens:
            texto = str(texto)
            ancora, eixo = self._ancora_numero_molde(pt, centro, afastamento)
            layouts.append(
                {
                    "ponto": QPointF(pt),
                    "texto": texto,
                    "marcador": bool(desenhar_marcador),
                    "x": float(ancora.x()),
                    "y": float(ancora.y()),
                    "largura": float(max(1, metrics.horizontalAdvance(texto)) + 2),
                    "altura": float(max(1, metrics.height())),
                    "eixo": eixo,
                }
            )
        self._distribuir_numeros_proximos(layouts)
        return layouts

    def _ancora_numero_molde(self, pt: QPointF, centro: QPointF, afastamento: float) -> tuple[QPointF, str]:
        pt_tela = self._cena_para_tela(pt)
        dx = pt.x() - centro.x()
        dy = pt.y() - centro.y()
        mod = max(1e-6, sqrt((dx * dx) + (dy * dy)))
        ux = dx / mod
        uy = dy / mod
        eixo_distribuicao = "x" if abs(uy) >= abs(ux) else "y"
        return QPointF(pt_tela.x() + (ux * afastamento), pt_tela.y() + (uy * afastamento)), eixo_distribuicao

    def _distribuir_numeros_proximos(self, layouts: list[dict]) -> None:
        for eixo in ("x", "y"):
            candidatos = [item for item in layouts if item.get("eixo") == eixo]
            if len(candidatos) < 2:
                continue
            transversal = "y" if eixo == "x" else "x"
            tamanho_transversal = "altura" if eixo == "x" else "largura"
            faixa = max(18.0, max(float(item[tamanho_transversal]) for item in candidatos) * 1.6)
            grupos: list[list[dict]] = []
            centros_grupo: list[float] = []
            for item in sorted(candidatos, key=lambda atual: (float(atual[transversal]), float(atual[eixo]))):
                valor = float(item[transversal])
                if not grupos or abs(valor - centros_grupo[-1]) > faixa:
                    grupos.append([item])
                    centros_grupo.append(valor)
                    continue
                grupos[-1].append(item)
                centros_grupo[-1] = sum(float(atual[transversal]) for atual in grupos[-1]) / len(grupos[-1])

            for grupo in grupos:
                ordenados = sorted(grupo, key=lambda atual: float(atual[eixo]))
                cluster: list[dict] = []
                for item in ordenados:
                    if not cluster:
                        cluster = [item]
                        continue
                    anterior = cluster[-1]
                    tamanho_anterior = float(anterior["largura" if eixo == "x" else "altura"])
                    tamanho_atual = float(item["largura" if eixo == "x" else "altura"])
                    distancia_minima = (tamanho_anterior / 2.0) + (tamanho_atual / 2.0) + 6.0
                    if float(item[eixo]) - float(anterior[eixo]) <= distancia_minima:
                        cluster.append(item)
                    else:
                        self._centralizar_cluster_numeros(cluster, eixo)
                        cluster = [item]
                self._centralizar_cluster_numeros(cluster, eixo)

    @staticmethod
    def _centralizar_cluster_numeros(cluster: list[dict], eixo: str) -> None:
        if len(cluster) < 2:
            return
        tamanho_chave = "largura" if eixo == "x" else "altura"
        gap = 6.0
        tamanhos = [float(item[tamanho_chave]) for item in cluster]
        total = sum(tamanhos) + (gap * (len(cluster) - 1))
        naturais = [float(item[eixo]) for item in cluster]
        meio = (min(naturais) + max(naturais)) / 2.0
        cursor = meio - (total / 2.0)
        for item, tamanho in zip(cluster, tamanhos):
            item[eixo] = cursor + (tamanho / 2.0)
            cursor += tamanho + gap

    def _pontos_piques_para_numeracao(self, el: dict, pontos_existentes: list[QPointF] | None = None) -> list[QPointF]:
        pontos: list[QPointF] = []
        existentes = [QPointF(pt) for pt in (pontos_existentes or [])]
        for cfg in el.get("piques_config", []) or []:
            if not isinstance(cfg, dict):
                continue
            ponto = self._ponto_cfg_pique(cfg)
            if ponto is not None and not self._ponto_ja_listado(existentes, ponto) and not self._ponto_ja_listado(pontos, ponto):
                pontos.append(QPointF(ponto))
        for item in el.get("marcacoes_no_perimetro", []) or []:
            ponto = self._qpoint_serializado(item)
            if ponto is not None and not self._ponto_ja_listado(existentes, ponto) and not self._ponto_ja_listado(pontos, ponto):
                pontos.append(QPointF(ponto))
        return pontos

    @staticmethod
    def _ponto_ja_listado(pontos: list[QPointF], ponto: QPointF, tolerancia: float = 1e-6) -> bool:
        return any(sqrt((pt.x() - ponto.x()) ** 2 + (pt.y() - ponto.y()) ** 2) <= tolerancia for pt in pontos)

    @staticmethod
    def _cantos_para_numeracao_horaria_tela(cantos: list[QPointF]) -> list[QPointF]:
        if len(cantos) <= 1:
            return list(cantos)
        if len(cantos) == 2:
            primeiro, segundo = cantos
            dx = abs(primeiro.x() - segundo.x())
            dy = abs(primeiro.y() - segundo.y())
            if dx >= dy:
                ordenados = sorted(cantos, key=lambda p: (p.x(), p.y()))
            else:
                ordenados = sorted(cantos, key=lambda p: (p.y(), p.x()))
            return [QPointF(p) for p in ordenados]
        area = 0.0
        total = len(cantos)
        for i, atual in enumerate(cantos):
            proximo = cantos[(i + 1) % total]
            area += (atual.x() * proximo.y()) - (proximo.x() * atual.y())
        if area < 0.0:
            return [QPointF(cantos[0]), *[QPointF(p) for p in reversed(cantos[1:])]]
        return [QPointF(p) for p in cantos]

    def _pontos_serializados_para_qpoint(self, origem) -> list[QPointF]:
        pontos: list[QPointF] = []
        if not isinstance(origem, list):
            return pontos
        for item in origem:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                try:
                    pontos.append(QPointF(float(item[0]), float(item[1])))
                except Exception:
                    pass
        return pontos

    def _centro_bbox_pontos(self, pontos: list[QPointF]) -> QPointF | None:
        if not pontos:
            return None
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    def _offset_dobra_salva_para_molde_atual(self, el: dict) -> QPointF:
        """Retorna quanto os dados salvos da dobra precisam acompanhar o molde.

        Alguns fluxos antigos de movimentação deslocavam apenas os pontos do
        molde e deixavam o contorno pontilhado salvo na posição antiga. Como a
        sombra pontilhada faz parte do molde dobrado, ela é desenhada com esse
        deslocamento compensado.
        """
        if not isinstance(el, dict):
            return QPointF(0.0, 0.0)
        atuais = self._pontos_serializados_para_qpoint(el.get("pontos") or [])
        if len(atuais) >= 2 and abs(atuais[0].x() - atuais[-1].x()) <= 1e-7 and abs(atuais[0].y() - atuais[-1].y()) <= 1e-7:
            atuais = atuais[:-1]
        estado = el.get("estado_dobra") if isinstance(el.get("estado_dobra"), dict) else None
        referencia = None
        if estado:
            referencia = estado.get("contorno_dobrado") or estado.get("pontos_dobrados")
        if not referencia:
            registros = el.get("contornos_dobra_original")
            if isinstance(registros, list) and registros:
                ultimo = registros[-1]
                if isinstance(ultimo, dict):
                    referencia = ultimo.get("contorno_dobrado")
        ref_pts = self._pontos_serializados_para_qpoint(referencia or [])
        if len(ref_pts) >= 2 and abs(ref_pts[0].x() - ref_pts[-1].x()) <= 1e-7 and abs(ref_pts[0].y() - ref_pts[-1].y()) <= 1e-7:
            ref_pts = ref_pts[:-1]
        c_atual = self._centro_bbox_pontos(atuais)
        c_ref = self._centro_bbox_pontos(ref_pts)
        if c_atual is None or c_ref is None:
            return QPointF(0.0, 0.0)
        return QPointF(c_atual.x() - c_ref.x(), c_atual.y() - c_ref.y())

    def _aplicar_offset_pontos(self, pontos: list[QPointF], offset: QPointF) -> list[QPointF]:
        if abs(offset.x()) <= 1e-9 and abs(offset.y()) <= 1e-9:
            return pontos
        return [QPointF(p.x() + offset.x(), p.y() + offset.y()) for p in pontos]

    def _registro_dobra_visual_atual(self, el: dict):
        """Retorna somente a referência visual da dobra atual.

        Versões anteriores desenhavam os dois últimos registros de
        contornos_dobra_original. Isso deixava pontilhados antigos presos no
        canvas quando o molde era movido ou dobrado novamente. O pontilhado é a
        sombra do lado dobrado atual, portanto só uma referência deve ser
        desenhada: primeiro o estado_dobra ativo, depois o último registro.
        """
        if not isinstance(el, dict):
            return None
        estado = el.get("estado_dobra") if isinstance(el.get("estado_dobra"), dict) else None
        if estado and (estado.get("contorno_lado_dobrado") or estado.get("contorno_lado_oculto") or estado.get("contorno_pontilhado")):
            return estado
        registros = el.get("contornos_dobra_original")
        if isinstance(registros, list):
            for registro in reversed(registros):
                if isinstance(registro, dict) and (registro.get("contorno_lado_dobrado") or registro.get("contorno_pontilhado") or registro.get("contorno_lado_oculto")):
                    return registro
        return None

    def _desenhar_contorno_dobra_original(self, painter: QPainter, el: dict):
        """Desenha apenas a sombra pontilhada da dobra atual."""
        if not bool(el.get("mostrar_contorno_dobra_original", True)):
            return
        registro = self._registro_dobra_visual_atual(el)
        if not isinstance(registro, dict):
            return
        origem = (
            registro.get("contorno_lado_dobrado")
            or registro.get("contorno_pontilhado")
            or registro.get("contorno_lado_oculto")
        )
        if not isinstance(origem, list):
            return
        pontos = self._pontos_serializados_para_qpoint(origem)
        if len(pontos) < 2:
            return
        pontos = self._aplicar_offset_pontos(pontos, self._offset_dobra_salva_para_molde_atual(el))
        if abs(pontos[0].x() - pontos[-1].x()) > 1e-7 or abs(pontos[0].y() - pontos[-1].y()) > 1e-7:
            pontos.append(QPointF(pontos[0]))
        cor_ref = str(el.get("cor") or "#8e949b")
        if not QColor(cor_ref).isValid():
            cor_ref = "#8e949b"
        cor_ref = self._config_cor_molde("molde_dobrado", cor_ref)
        painter.save()
        pen = QPen(QColor(cor_ref), 1.0, Qt.DashLine)
        pen.setDashPattern([4.0, 3.0])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        self._desenhar_polilinha(painter, pontos, cor=cor_ref, espessura=1.0, estilo="dash")
        painter.restore()

    def _desenhar_eixo_dobra_salvo(self, painter: QPainter, el: dict):
        """Mostra o eixo salvo da última dobra, mesmo depois de aplicada."""
        eixo_info = el.get("dobra_eixo")
        if not isinstance(eixo_info, dict):
            estado = el.get("estado_dobra") if isinstance(el.get("estado_dobra"), dict) else None
            eixo_info = estado.get("eixo") if estado else None
        if not isinstance(eixo_info, dict):
            return
        try:
            tipo = str(eixo_info.get("tipo") or "").lower()
            offset = self._offset_dobra_salva_para_molde_atual(el)
            base = []
            for item in el.get("pontos", []) or []:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    base.append(QPointF(float(item[0]), float(item[1])))
            if not base:
                return
            min_x = min(p.x() for p in base)
            max_x = max(p.x() for p in base)
            min_y = min(p.y() for p in base)
            max_y = max(p.y() for p in base)
            margem = max(max_x - min_x, max_y - min_y, 1.0) * 0.04
            if tipo == "h":
                y = float(eixo_info.get("valor")) + offset.y()
                p1 = QPointF(min_x - margem, y)
                p2 = QPointF(max_x + margem, y)
            elif tipo == "v":
                x = float(eixo_info.get("valor")) + offset.x()
                p1 = QPointF(x, min_y - margem)
                p2 = QPointF(x, max_y + margem)
            elif tipo == "line":
                raw1 = eixo_info.get("p1")
                raw2 = eixo_info.get("p2")
                if not (isinstance(raw1, (tuple, list)) and isinstance(raw2, (tuple, list)) and len(raw1) >= 2 and len(raw2) >= 2):
                    return
                p1 = QPointF(float(raw1[0]) + offset.x(), float(raw1[1]) + offset.y())
                p2 = QPointF(float(raw2[0]) + offset.x(), float(raw2[1]) + offset.y())
            else:
                return
        except Exception:
            return
        painter.save()
        pen = QPen(QColor(getattr(self, "_cores_canvas", {}).get("selecao", "#2da8ff")), 1.0, Qt.DashLine)
        pen.setDashPattern([6.0, 4.0])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(self._cena_para_tela(p1), self._cena_para_tela(p2))
        painter.restore()

    def _desenhar_piscar_ponto_restauracao(self, painter: QPainter, base: list[QPointF]):
        if len(base) < 3:
            return
        cor = QColor(getattr(self, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        if not cor.isValid():
            cor = QColor("#2da8ff")
        painter.save()
        path = QPainterPath(self._cena_para_tela(base[0]))
        for pt in base[1:]:
            path.lineTo(self._cena_para_tela(pt))
        path.closeSubpath()
        preenchimento = QColor(cor)
        preenchimento.setAlpha(70)
        contorno = QColor(cor)
        contorno.setAlpha(235)
        pen = QPen(contorno, 3.0)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(preenchimento)
        painter.drawPath(path)
        painter.restore()

    def _desenhar_selecao_molde(self, painter: QPainter, base: list[QPointF], el: dict):
        if not base:
            return
        pontos_bbox = list(base)
        pontos_bbox.extend(self._pontos_costuras_vinculadas(el))
        margem_cm = 1.5
        min_x = min(pt.x() for pt in pontos_bbox) - margem_cm
        max_x = max(pt.x() for pt in pontos_bbox) + margem_cm
        min_y = min(pt.y() for pt in pontos_bbox) - margem_cm
        max_y = max(pt.y() for pt in pontos_bbox) + margem_cm
        canto_sup_esq = self._cena_para_tela(QPointF(min_x, min_y))
        canto_inf_dir = self._cena_para_tela(QPointF(max_x, max_y))
        x_ini = min(canto_sup_esq.x(), canto_inf_dir.x())
        y_ini = min(canto_sup_esq.y(), canto_inf_dir.y())
        largura = abs(canto_inf_dir.x() - canto_sup_esq.x())
        altura = abs(canto_inf_dir.y() - canto_sup_esq.y())

        ret_pen = QPen(QColor(getattr(self, "_cores_canvas", {}).get("selecao", "#2da8ff")), 1.0, Qt.DashLine)
        ret_pen.setDashPattern([3.5, 2.5])
        painter.setPen(ret_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(x_ini), int(y_ini), int(largura), int(altura))

        pontos_controle = [self._cena_para_tela(pt) for pt in self._pontos_controle_selecao_molde(base, el)]

        cor_ponto, forma_ponto = self._config_ponto_molde("ponto_controle", "#000000", "Losango")
        for pt in pontos_controle:
            self._desenhar_marcador_ponto_tela(painter, pt, cor_ponto, forma_ponto, 4)

    def _desenhar_marcador_ponto_tela(
            self,
            painter: QPainter,
            pt: QPointF,
            cor: str,
            forma: str,
            raio: int = 4,
    ):
        cor_qt = QColor(str(cor or "#000000"))
        if not cor_qt.isValid():
            cor_qt = QColor("#000000")
        painter.setPen(QPen(QColor("#ffffff"), 1.0))
        painter.setBrush(cor_qt)
        d = max(2, int(raio))
        forma_txt = str(forma or "").strip().lower()
        if "quadrado" in forma_txt:
            painter.drawRect(int(pt.x() - d), int(pt.y() - d), d * 2, d * 2)
        elif "circulo" in forma_txt or "círculo" in forma_txt:
            painter.drawEllipse(pt, d, d)
        else:
            diamond = QPolygon([
                QPoint(int(pt.x()), int(pt.y() - d)),
                QPoint(int(pt.x() + d), int(pt.y())),
                QPoint(int(pt.x()), int(pt.y() + d)),
                QPoint(int(pt.x() - d), int(pt.y())),
            ])
            painter.drawPolygon(diamond)

    def _pontos_controle_selecao_molde(self, base: list[QPointF], el: dict) -> list[QPointF]:
        if "controle_cantos" in el:
            cantos: list[QPointF] = []
            valores = el.get("controle_cantos")
            if isinstance(valores, list):
                for item in valores:
                    pt = self._qpoint_serializado(item)
                    if pt is not None:
                        cantos.append(QPointF(pt))
            return cantos[:4]
        return [QPointF(pt) for pt in base[:4]]

    def _desenhar_bbox_selecao_elemento(self, painter: QPainter, elemento: dict):
        pontos: list[QPointF] = []
        if elemento.get("tipo") == "polyline":
            pontos = [QPointF(float(x), float(y)) for x, y in elemento.get("pontos", [])]
            pontos.extend(self._pontos_costuras_vinculadas(elemento))
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
        pen = QPen(QColor(getattr(self, "_cores_canvas", {}).get("selecao", "#2da8ff")), 1.0, Qt.DashLine)
        pen.setDashPattern([3.5, 2.5])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(x_ini), int(y_ini), int(largura), int(altura))

    def _ponto_referencia_molde_canvas(self, base: list[QPointF], referencia: str) -> QPointF:
        xs = [p.x() for p in base]
        ys = [p.y() for p in base]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        ref = str(referencia or "Centro centro").strip().lower()
        if "esquerda" in ref:
            x = min_x
        elif "direita" in ref:
            x = max_x
        else:
            x = (min_x + max_x) / 2.0
        if "topo" in ref:
            y = min_y
        elif "abaixo" in ref or "baixo" in ref:
            y = max_y
        else:
            y = (min_y + max_y) / 2.0
        return QPointF(x, y)

    def _valor_float_molde_decimal(self, el: dict, chaves: tuple[str, ...], padrao=None):
        """Lê número salvo no molde usando ponto decimal como padrão.

        O programa deve trabalhar com ponto decimal: 0.5 = meio centímetro,
        0.4 = quatro milímetros, 1.2 = doze milímetros. A vírgula é aceita
        apenas para não quebrar arquivos antigos, mas os valores novos devem
        ser gravados e exibidos com ponto.
        """
        for chave in chaves:
            valor = el.get(chave)
            if valor is None:
                continue
            try:
                return float(str(valor).replace(",", ".").replace("cm", "").strip())
            except Exception:
                continue
        return padrao

    def _tamanho_texto_cm_para_px(self, altura_cm: float, minimo_px: float = 6.0, maximo_px: float = 260.0) -> float:
        # 1 unidade da cena = 1 cm. Assim, 5.0 cm no campo de propriedades
        # vira 5 cm reais no canvas, multiplicado pelo zoom atual.
        try:
            valor = float(altura_cm)
        except Exception:
            valor = 0.0
        return max(minimo_px, min(maximo_px, valor * max(float(getattr(self, "zoom", 1.0)), 0.01)))

    def _altura_texto_config_cm(self, el: dict, chave: str, padrao_cm: float) -> float:
        valor = self._valor_float_molde_decimal(
            el,
            (
                f"texto_{chave}_altura_cm",
                f"altura_texto_{chave}_cm",
                f"altura_{chave}_cm",
                f"tam_{chave}_cm",
                f"tamanho_{chave}_cm",
            ),
            None,
        )
        if valor is None and chave == "nome":
            valor = self._valor_float_molde_decimal(el, ("tam_nome", "tamanho_nome", "fonte_nome"), None)
        if valor is None and chave in {"numero", "numeros", "números"}:
            valor = self._valor_float_molde_decimal(el, ("numero_altura_cm", "altura_numero_cm", "tam_numero", "tamanho_numero"), None)
        if valor is None:
            valor = padrao_cm
        return max(0.05, float(valor))

    def _tamanho_texto_config_canvas(self, el: dict, chave: str, padrao_px: float = 10.0) -> float:
        padrao_cm = self.TAMANHO_NOME_PADRAO_CM if chave == "nome" else 0.7
        valor_cm = self._valor_float_molde_decimal(
            el,
            (f"texto_{chave}_altura_cm", f"altura_texto_{chave}_cm", f"altura_{chave}_cm"),
            None,
        )
        if valor_cm is not None:
            return self._tamanho_texto_cm_para_px(valor_cm)
        valor_px = self._valor_float_molde_decimal(
            el,
            (f"texto_{chave}_tamanho_px", f"texto_{chave}_altura_px", f"tam_{chave}_px"),
            None,
        )
        if valor_px is not None:
            return max(7.0, min(180.0, float(valor_px)))
        return self._tamanho_texto_cm_para_px(padrao_cm) if padrao_px == 10.0 else float(padrao_px)

    def _desenhar_texto_config_molde_canvas(
            self,
            painter: QPainter,
            el: dict,
            base: list[QPointF],
            chave: str,
            texto: str,
            visivel: bool,
            padrao_ref: str = "Centro centro",
    ):
        texto = str(texto or "").strip()
        if not visivel or not texto or not base:
            return
        referencia = str(el.get(f"referencia_texto_{chave}") or padrao_ref).strip()
        ponto_raw = el.get(f"ponto_texto_{chave}")
        if chave == "nome" and ponto_raw is None:
            ponto_raw = el.get("ponto_texto")
        if referencia.lower() == "livre" and isinstance(ponto_raw, (list, tuple)) and len(ponto_raw) == 2:
            ponto = QPointF(float(ponto_raw[0]), float(ponto_raw[1]))
        else:
            ponto = self._ponto_referencia_molde_canvas(base, referencia)
        tela = self._cena_para_tela(ponto)
        bbox_tela = self._bbox_tela_pontos(base)
        margem_px = 6.0
        limite_largura = max(12.0, bbox_tela[2] - bbox_tela[0] - (margem_px * 2.0))
        limite_altura = max(10.0, bbox_tela[3] - bbox_tela[1] - (margem_px * 2.0))
        fonte = painter.font()
        fonte.setBold(False)
        fonte.setPixelSize(int(round(self._tamanho_texto_config_canvas(el, chave, 10.0))))
        painter.setFont(fonte)
        metrics = QFontMetrics(painter.font())
        linhas = texto.splitlines() or [texto]
        largura = min(max(metrics.horizontalAdvance(l) for l in linhas), int(limite_largura))
        altura = min(metrics.height() * max(1, len(linhas)), int(limite_altura))
        tela = self._ponto_tela_dentro_bbox(tela, bbox_tela, largura, altura, margem_px)
        alinhamento_txt = str(el.get(f"alinhamento_texto_{chave}") or "Centro").lower()
        alinhamento = Qt.AlignVCenter
        if "esquerda" in alinhamento_txt:
            alinhamento |= Qt.AlignLeft
        elif "direita" in alinhamento_txt:
            alinhamento |= Qt.AlignRight
        else:
            alinhamento |= Qt.AlignCenter
        angulo = float(el.get(f"texto_{chave}_angulo", 0.0) or 0.0)
        rect = QRectF(-largura / 2.0, -altura / 2.0, largura, altura)
        painter.save()
        painter.translate(tela)
        if abs(angulo) > 1e-6:
            painter.rotate(-angulo)
        chave_cor = "nome_molde" if chave == "nome" else chave
        painter.setPen(QPen(QColor(self._config_cor_molde(chave_cor, "#ffffff")), 1.0))
        painter.drawText(rect, alinhamento, texto)
        painter.restore()

    def _linhas_metadados_molde_canvas(self, el: dict, base: list[QPointF]) -> list[str]:
        linhas: list[str] = []
        modelo = str(el.get("modelo") or el.get("nome_modelo") or el.get("modelo_nome") or "").strip()
        if el.get("visual_modelo", False) and modelo:
            linhas.append(f"Modelo {modelo}")
        grade = str(el.get("graduacao_grade_nome") or "").strip()
        if el.get("visual_grade_tamanhos", False) and grade:
            linhas.append(f"Grade {grade}")
        tecido = str(el.get("tecido") or "").strip()
        if el.get("visual_tecido", False) and tecido:
            linhas.append(f"Tecido {tecido}")
        if el.get("visual_quantidade", False):
            qtd = str(el.get("qtd_modelo", 1) or 1).strip()
            sufixo = " (Par)" if el.get("par", False) else ""
            linhas.append(f"Quantidade {qtd}{sufixo}")
        giro = str(el.get("giro") or "").strip()
        if el.get("visual_giro", False) and giro:
            linhas.append(f"Giro {giro}")
        if el.get("visual_perimetro_molde", False) and len(base) >= 2:
            perimetro = 0.0
            for a, b in zip(base, base[1:] + [base[0]]):
                perimetro += sqrt((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2)
            linhas.append(f"Perímetro {formatar_numero(perimetro)} {self._unidade_sigla}")
        return linhas

    def _desenhar_metadados_molde_canvas(self, painter: QPainter, el: dict, base: list[QPointF]) -> None:
        linhas = self._linhas_metadados_molde_canvas(el, base)
        if not linhas or not base:
            return
        cx = sum(p.x() for p in base) / len(base)
        cy = sum(p.y() for p in base) / len(base)
        pos = self._cena_para_tela(QPointF(cx, cy))
        bbox_tela = self._bbox_tela_pontos(base)
        painter.save()
        fonte = painter.font()
        fonte.setBold(False)
        fonte.setPixelSize(int(round(self._tamanho_texto_cm_para_px(0.45, minimo_px=7.0, maximo_px=42.0))))
        painter.setFont(fonte)
        metrics = QFontMetrics(painter.font())
        altura = max(10, metrics.height() + 2)
        y = min(bbox_tela[3] - (altura * len(linhas)), pos.y() + 18.0)
        y = max(bbox_tela[1] + 2.0, y)
        painter.setPen(QPen(QColor(self._config_cor_molde("nome_molde", "#ffffff")), 1.0))
        for linha in linhas:
            largura = min(max(70, metrics.horizontalAdvance(linha) + 10), max(80, bbox_tela[2] - bbox_tela[0] - 8))
            x = max(bbox_tela[0] + 4.0, min(pos.x() - largura / 2.0, bbox_tela[2] - largura - 4.0))
            painter.drawText(QRectF(x, y, largura, altura), Qt.AlignCenter, linha)
            y += altura
        painter.restore()

    def _area_assinada_pontos_canvas(self, pontos: list[QPointF]) -> float:
        area = 0.0
        total = len(pontos)
        for i, p1 in enumerate(pontos):
            p2 = pontos[(i + 1) % total]
            area += (p1.x() * p2.y()) - (p2.x() * p1.y())
        return area / 2.0

    def _margens_por_segmento_canvas(self, molde: dict, total_segmentos: int) -> dict[int, float]:
        margens: dict[int, float] = {}
        for dados in (molde.get("margens_molde"), molde.get("margens"), molde.get("margem_cm_por_elemento")):
            if isinstance(dados, list):
                for item in dados:
                    if not isinstance(item, dict):
                        continue
                    idx = item.get("indice", item.get("segmento", item.get("elemento")))
                    valor = item.get("margem", item.get("valor", item.get("cm")))
                    try:
                        if isinstance(idx, str) and idx.lower().startswith("elemento"):
                            idx = idx.split()[-1]
                        idx_int = int(idx) - 1 if int(idx) >= 1 else int(idx)
                        if 0 <= idx_int < total_segmentos:
                            margens[idx_int] = max(0.0, float(str(valor).replace(",", ".")))
                    except Exception:
                        continue
            elif isinstance(dados, dict):
                for idx, valor in dados.items():
                    try:
                        idx_txt = str(idx).strip()
                        if idx_txt.lower().startswith("elemento"):
                            idx_txt = idx_txt.split()[-1]
                        idx_int = int(idx_txt) - 1 if int(idx_txt) >= 1 else int(idx_txt)
                        if 0 <= idx_int < total_segmentos:
                            margens[idx_int] = max(0.0, float(str(valor).replace(",", ".")))
                    except Exception:
                        continue
        return margens

    def _pontos_offset_segmento_canvas(self, base: list[QPointF], seg_idx: int, margem: float, sentido: float):
        total = len(base)
        if total < 2:
            return None
        a = base[seg_idx % total]
        b = base[(seg_idx + 1) % total]
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-9:
            return None
        nx = (-dy / comp) * sentido
        ny = (dx / comp) * sentido
        off_a = QPointF(a.x() + nx * margem, a.y() + ny * margem)
        off_b = QPointF(b.x() + nx * margem, b.y() + ny * margem)
        return a, b, off_a, off_b

    def _intersecao_linhas_canvas(self, a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF) -> QPointF | None:
        x1, y1, x2, y2 = a1.x(), a1.y(), a2.x(), a2.y()
        x3, y3, x4, y4 = b1.x(), b1.y(), b2.x(), b2.y()
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) <= 1e-9:
            return None
        px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
        py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
        return QPointF(px, py)

    def _desenhar_margens_molde_canvas(self, painter: QPainter, molde: dict, base: list[QPointF]):
        if not molde.get("mostrar_margem", False) or len(base) < 3:
            return
        margens = self._margens_por_segmento_canvas(molde, len(base))
        if not margens:
            return
        sentido = 1.0 if self._area_assinada_pontos_canvas(base) < 0.0 else -1.0
        cor = QColor(self._config_cor_molde("margem", self._cor_linha_elemento(molde, "#ffffff")))
        painter.save()
        pen = QPen(cor, max(1.0, float(molde.get("espessura", 1.0))))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        total = len(base)
        for seg_idx, margem in margens.items():
            if margem <= 0:
                continue
            pontos_offset = self._pontos_offset_segmento_canvas(base, seg_idx, margem, sentido)
            if pontos_offset is None:
                continue
            a, b, off_a, off_b = pontos_offset
            painter.drawLine(self._cena_para_tela(off_a), self._cena_para_tela(off_b))
            margem_anterior = float(margens.get((seg_idx - 1) % total, 0.0) or 0.0)
            if margem_anterior > 0:
                anterior = self._pontos_offset_segmento_canvas(base, (seg_idx - 1) % total, margem_anterior, sentido)
                if anterior is not None:
                    canto = QPainterPath(self._cena_para_tela(anterior[3]))
                    controle = self._intersecao_linhas_canvas(anterior[2], anterior[3], off_a, off_b)
                    if controle is None:
                        controle = QPointF(anterior[3].x() + off_a.x() - a.x(), anterior[3].y() + off_a.y() - a.y())
                    canto.quadTo(self._cena_para_tela(controle), self._cena_para_tela(off_a))
                    painter.drawPath(canto)
            else:
                painter.drawLine(self._cena_para_tela(a), self._cena_para_tela(off_a))
            margem_proxima = float(margens.get((seg_idx + 1) % total, 0.0) or 0.0)
            if margem_proxima <= 0:
                painter.drawLine(self._cena_para_tela(off_b), self._cena_para_tela(b))
        painter.restore()

    def _bbox_tela_pontos(self, pontos: list[QPointF]) -> tuple[float, float, float, float]:
        pts = [self._cena_para_tela(p) for p in pontos]
        if not pts:
            return (0.0, 0.0, float(self.width()), float(self.height()))
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def _valor_float_molde(self, el: dict, chaves: tuple[str, ...], padrao):
        return self._valor_float_molde_decimal(el, chaves, padrao)

    def _tamanho_pixel_molde(self, el: dict, chaves: tuple[str, ...], padrao: float) -> float:
        valor = self._valor_float_molde(el, chaves, None)
        if valor is None:
            valor = padrao
        try:
            return float(max(4.0, min(96.0, float(valor))))
        except Exception:
            return float(max(4.0, min(96.0, padrao)))

    def _fonte_ajustada_px(self, painter: QPainter, texto: str, tamanho_px: float, limite_largura: float, limite_altura: float):
        fonte = painter.font()
        tamanho = int(max(4, min(96, round(float(tamanho_px)))))
        while tamanho >= 4:
            fonte.setPixelSize(tamanho)
            metrics = QFontMetrics(fonte)
            if metrics.horizontalAdvance(texto) <= limite_largura and metrics.height() <= limite_altura:
                return fonte
            tamanho -= 1
        fonte.setPixelSize(4)
        return fonte

    def _ponto_tela_dentro_bbox(
            self,
            ponto: QPointF,
            bbox: tuple[float, float, float, float],
            largura: float,
            altura: float,
            margem: float = 4.0,
    ) -> QPointF:
        min_x, min_y, max_x, max_y = bbox
        metade = largura / 2.0
        x = max(min_x + margem + metade, min(ponto.x(), max_x - margem - metade))
        y = max(min_y + margem + (altura / 2.0), min(ponto.y(), max_y - margem - (altura / 2.0)))
        return QPointF(x, y)

    def _calcular_fio_tela_fixo(
            self,
            inicio: QPointF,
            fim: QPointF,
            bbox_tela: tuple[float, float, float, float],
            tamanho_px: float,
    ) -> tuple[QPointF, QPointF]:
        p1 = self._cena_para_tela(inicio)
        p2 = self._cena_para_tela(fim)
        centro = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-6:
            dx, dy, comp = 1.0, 0.0, 1.0
        ux = dx / comp
        uy = dy / comp
        min_x, min_y, max_x, max_y = bbox_tela
        folga = 8.0
        alcance = max(8.0, self._alcance_bbox_por_direcao(centro, QPointF(ux, uy), bbox_tela) * 2.0 - folga)
        tamanho = max(8.0, min(float(tamanho_px), alcance))
        metade = tamanho / 2.0
        return (
            QPointF(centro.x() - ux * metade, centro.y() - uy * metade),
            QPointF(centro.x() + ux * metade, centro.y() + uy * metade),
        )

    def _alcance_bbox_por_direcao(self, centro: QPointF, direcao: QPointF, bbox: tuple[float, float, float, float]) -> float:
        min_x, min_y, max_x, max_y = bbox
        candidatos: list[float] = []
        if abs(direcao.x()) > 1e-9:
            candidatos.append((max_x - centro.x()) / direcao.x())
            candidatos.append((min_x - centro.x()) / direcao.x())
        if abs(direcao.y()) > 1e-9:
            candidatos.append((max_y - centro.y()) / direcao.y())
            candidatos.append((min_y - centro.y()) / direcao.y())
        positivos = [abs(t) for t in candidatos if t > 0]
        return min(positivos) if positivos else 8.0

    def _desenhar_seta_fio_tela(self, painter: QPainter, p1_tela: QPointF, p2_tela: QPointF, cor: str = "#ffffff"):
        dx = p2_tela.x() - p1_tela.x()
        dy = p2_tela.y() - p1_tela.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-6:
            return
        ux = dx / comp
        uy = dy / comp
        nx = -uy
        ny = ux
        margem_px = min(12.0, max(5.0, comp * 0.06))
        base_inicio = QPointF(p1_tela.x() + (ux * margem_px), p1_tela.y() + (uy * margem_px))
        base_fim = QPointF(p2_tela.x() - (ux * margem_px), p2_tela.y() - (uy * margem_px))
        pen = QPen(QColor(cor), 1.15)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        painter.drawLine(base_inicio, base_fim)
        tamanho_seta = min(12.0, max(6.0, comp * 0.16))
        meia_largura = tamanho_seta * 0.32
        self._desenhar_ponta_seta_fechada(painter, p2_tela, QPointF(ux, uy), QPointF(nx, ny), tamanho_seta, meia_largura, cor=cor)
        self._desenhar_ponta_seta_fechada(painter, p1_tela, QPointF(-ux, -uy), QPointF(nx, ny), tamanho_seta, meia_largura, cor=cor)

    def _desenhar_rotulo_fio_tela(self, painter: QPainter, p1_tela: QPointF, p2_tela: QPointF, texto: str, tamanho: float | None = None, cor: str = "#ffffff"):
        dx = p2_tela.x() - p1_tela.x()
        dy = p2_tela.y() - p1_tela.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-6:
            return
        nx = -dy / comp
        ny = dx / comp
        meio = QPointF((p1_tela.x() + p2_tela.x()) / 2.0, (p1_tela.y() + p2_tela.y()) / 2.0)
        ancora = QPointF(meio.x() + (nx * 12.0), meio.y() + (ny * 12.0))
        painter.save()
        fonte = painter.font()
        fonte.setBold(False)
        fonte.setPixelSize(int(max(6, round(float(tamanho or 10.0)))))
        painter.setFont(fonte)
        metrics = QFontMetrics(painter.font())
        largura = metrics.horizontalAdvance(texto)
        altura = metrics.height()
        painter.setPen(QPen(QColor(cor), 1.0))
        painter.drawText(int(round(ancora.x() - largura / 2.0)), int(round(ancora.y() - 4.0)), int(round(largura)), int(round(altura)), Qt.AlignCenter, texto)
        painter.restore()

    def _desenhar_seta_fio(self, painter: QPainter, inicio: QPointF, fim: QPointF, cor: str = "#ffffff"):
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

        pen = QPen(QColor(cor), 1.15)
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
            cor=cor,
        )
        self._desenhar_ponta_seta_fechada(
            painter,
            ponta=p1_tela,
            direcao=QPointF(-ux, -uy),
            normal=QPointF(nx, ny),
            comprimento=tamanho_seta,
            meia_largura=meia_largura,
            cor=cor,
        )

    def _desenhar_ponta_seta_fechada(
            self,
            painter: QPainter,
            ponta: QPointF,
            direcao: QPointF,
            normal: QPointF,
            comprimento: float,
            meia_largura: float,
            cor: str = "#ffffff",
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
        painter.setBrush(QColor(cor))
        painter.drawPath(path)
        painter.restore()

    def _desenhar_rotulo_fio(self, painter: QPainter, inicio: QPointF, fim: QPointF, texto: str,
                             tamanho: float | None = None, cor: str = "#ffffff"):
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
        painter.setPen(QPen(QColor(cor), 1.0))
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
            "mover_ponto",
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

    def _elemento_curva_suave(self, elemento: dict) -> bool:
        if not isinstance(elemento, dict):
            return False
        return bool(
            elemento.get("curva_suave")
            or elemento.get("suavizar")
            or str(elemento.get("tipo_curva") or "").lower() == "parabola_3p"
            or str(elemento.get("tipo_curva") or "").lower().startswith("spline")
            or str(elemento.get("renderizacao") or "").lower() == "curva_suave"
        )

    def _qpoint_serializado(self, item) -> QPointF | None:
        try:
            if isinstance(item, dict):
                return QPointF(float(item.get("x", 0.0)), float(item.get("y", 0.0)))
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                return QPointF(float(item[0]), float(item[1]))
        except Exception:
            return None
        return None

    def _controles_parabola_3p_elemento(self, elemento: dict) -> list[QPointF]:
        if str(elemento.get("tipo_curva") or "").strip().lower() != "parabola_3p":
            return []
        for chave in ("pontos_principais", "pontos_controle_curva", "pontos_controle_principais", "pontos_controle"):
            origem = elemento.get(chave)
            if not isinstance(origem, list):
                continue
            pontos = [pt for item in origem if (pt := self._qpoint_serializado(item)) is not None]
            if len(pontos) == 3:
                return [QPointF(p) for p in pontos]
        origem = elemento.get("pontos")
        if isinstance(origem, list) and len(origem) == 3:
            pontos = [pt for item in origem if (pt := self._qpoint_serializado(item)) is not None]
            if len(pontos) == 3:
                return [QPointF(p) for p in pontos]
        return []

    def _desenhar_parabola_3p_elemento(
            self,
            painter: QPainter,
            elemento: dict,
            cor: str,
            espessura: float,
            estilo: str = "solid",
            amplitude: float = 1.0,
    ) -> bool:
        controles = self._controles_parabola_3p_elemento(elemento)
        if len(controles) != 3:
            return False
        p0, pmedio, p2 = controles
        cx, cy = quadratic_bezier_control_for_point(
            (float(p0.x()), float(p0.y())),
            (float(pmedio.x()), float(pmedio.y())),
            (float(p2.x()), float(p2.y())),
        )
        self._desenhar_bezier_quadratica(
            painter,
            p0,
            QPointF(cx, cy),
            p2,
            cor=cor,
            espessura=espessura,
            estilo=estilo,
            amplitude=amplitude,
            destacar_controles=False,
        )
        return True

    def _pontos_curva_suave_elemento(self, elemento: dict) -> list[QPointF]:
        # Para ferramenta Curva, os pontos salvos são os pontos principais.
        # Priorizar "pontos" evita usar campos antigos defasados e mantém o
        # desenho exatamente onde a manipulação deixou.
        origem = elemento.get("pontos") or elemento.get("pontos_controle_curva") or elemento.get("pontos_principais") or []
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

    def _desenhar_curva_suave_por_pontos(
            self,
            painter: QPainter,
            pontos: list[QPointF],
            cor: str = "#ffffff",
            espessura: float = 1.0,
            estilo: str = "solid",
    ):
        if len(pontos) < 2:
            return
        if len(pontos) == 2:
            self._desenhar_polilinha(painter, pontos, cor=cor, espessura=espessura, estilo=estilo)
            return

        fechado = len(pontos) > 3 and self._dist_qpoint(pontos[0], pontos[-1]) <= 1e-6
        pts = [QPointF(p) for p in (pontos[:-1] if fechado else pontos)]
        if len(pts) < 3:
            self._desenhar_polilinha(painter, pontos, cor=cor, espessura=espessura, estilo=estilo)
            return

        path = QPainterPath(self._cena_para_tela(pts[0]))
        total = len(pts)
        limite = total if fechado else total - 1
        tensao = 1.0
        for i in range(limite):
            p0 = pts[(i - 1) % total] if fechado or i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[(i + 1) % total]
            p3 = pts[(i + 2) % total] if fechado or i + 2 < total else p2

            c1 = QPointF(
                p1.x() + (p2.x() - p0.x()) * tensao / 6.0,
                p1.y() + (p2.y() - p0.y()) * tensao / 6.0,
            )
            c2 = QPointF(
                p2.x() - (p3.x() - p1.x()) * tensao / 6.0,
                p2.y() - (p3.y() - p1.y()) * tensao / 6.0,
            )
            path.cubicTo(self._cena_para_tela(c1), self._cena_para_tela(c2), self._cena_para_tela(p2))
        if fechado:
            path.closeSubpath()

        painter.save()
        pen = QPen(QColor(cor), espessura)
        self._aplicar_estilo_caneta(pen, estilo)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.restore()

    def _desenhar_curva_suave_elemento(
            self,
            painter: QPainter,
            elemento: dict,
            cor: str,
            espessura: float,
            estilo: str = "solid",
    ):
        pontos = self._pontos_curva_suave_elemento(elemento)
        self._desenhar_curva_suave_por_pontos(painter, pontos, cor=cor, espessura=espessura, estilo=estilo)

    def _desenhar_polilinha_suavizada(self, painter: QPainter, pontos: list[QPointF], cor: str = "#ff5a00",
                                      espessura: float = 1.0, estilo: str = "solid"):
        """Desenha contornos importados do Audaces com curva visual suave.

        A geometria original continua salva como pontos do molde. Este método melhora
        apenas a renderização do contorno/costura no canvas, evitando a aparência
        facetada das polylines vindas do EMF. Cantos fortes continuam retos.
        """
        if len(pontos) < 3:
            self._desenhar_polilinha(painter, pontos, cor=cor, espessura=espessura, estilo=estilo)
            return

        pts = list(pontos)
        fechado = len(pts) > 3 and self._dist_qpoint(pts[0], pts[-1]) <= 1e-6
        if fechado:
            pts = pts[:-1]
        if len(pts) < 3:
            self._desenhar_polilinha(painter, pontos, cor=cor, espessura=espessura, estilo=estilo)
            return

        path = QPainterPath(self._cena_para_tela(pts[0]))
        total = len(pts)
        for i in range(total if fechado else total - 1):
            p0 = pts[(i - 1) % total] if fechado or i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[(i + 1) % total]
            p3 = pts[(i + 2) % total] if fechado or i + 2 < total else p2

            # Preserva quinas/cantos. Em linhas quase retas ou curvas suaves, usa cubicTo.
            ang1 = self._angulo_suavizacao(p0, p1, p2)
            ang2 = self._angulo_suavizacao(p1, p2, p3)
            if ang1 < 132.0 or ang2 < 132.0:
                path.lineTo(self._cena_para_tela(p2))
                continue

            tensao = 0.55
            c1 = QPointF(p1.x() + ((p2.x() - p0.x()) * tensao / 6.0), p1.y() + ((p2.y() - p0.y()) * tensao / 6.0))
            c2 = QPointF(p2.x() - ((p3.x() - p1.x()) * tensao / 6.0), p2.y() - ((p3.y() - p1.y()) * tensao / 6.0))
            path.cubicTo(self._cena_para_tela(c1), self._cena_para_tela(c2), self._cena_para_tela(p2))
        if fechado:
            path.closeSubpath()

        pen = QPen(QColor(cor), espessura)
        self._aplicar_estilo_caneta(pen, estilo)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

    @staticmethod
    def _dist_qpoint(a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return sqrt((dx * dx) + (dy * dy))

    @staticmethod
    def _angulo_suavizacao(a: QPointF, b: QPointF, c: QPointF) -> float:
        v1x = a.x() - b.x()
        v1y = a.y() - b.y()
        v2x = c.x() - b.x()
        v2y = c.y() - b.y()
        n1 = sqrt((v1x * v1x) + (v1y * v1y))
        n2 = sqrt((v2x * v2x) + (v2y * v2y))
        if n1 <= 1e-9 or n2 <= 1e-9:
            return 180.0
        cosv = max(-1.0, min(1.0, ((v1x * v2x) + (v1y * v2y)) / (n1 * n2)))
        return degrees(acos(cosv))

    def _desenhar_polilinha(self, painter: QPainter, pontos: list[QPointF], cor: str = "#ff5a00",
                            espessura: float = 1.0, estilo: str = "solid", amplitude: float = 1.0,
                            fase_inicial: float = 0.0):
        if len(pontos) >= 2 and not is_geometric_line_style(estilo):
            painter.save()
            try:
                path = QPainterPath(self._cena_para_tela(pontos[0]))
                for p in pontos[1:]:
                    path.lineTo(self._cena_para_tela(p))
                pen = QPen(QColor(cor), espessura)
                self._aplicar_estilo_caneta(pen, estilo)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
            finally:
                painter.restore()
            return
        fase = fase_inicial
        for inicio, fim in zip(pontos, pontos[1:]):
            fase = self._desenhar_segmento(painter, inicio, fim, cor=cor, espessura=espessura,
                                           estilo=estilo, amplitude=amplitude, fase=fase)

    def _desenhar_bezier_quadratica(self, painter: QPainter, p0: QPointF, p1: QPointF, p2: QPointF,
                                    cor: str, espessura: float, estilo: str, amplitude: float,
                                    destacar_controles: bool = False):
        if is_geometric_line_style(estilo):
            pontos = self._amostrar_bezier_quadratica(p0, p1, p2, segmentos=96)
            self._desenhar_polilinha(painter, pontos, cor=cor, espessura=espessura, estilo=estilo, amplitude=amplitude)
        else:
            path = QPainterPath(self._cena_para_tela(p0))
            path.quadTo(self._cena_para_tela(p1), self._cena_para_tela(p2))
            pen = QPen(QColor(cor), espessura)
            self._aplicar_estilo_caneta(pen, estilo)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
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

    def _desenhar_marca_x(self, painter: QPainter, ponto: QPointF, cor: str = "#ff5a00", tamanho_px: int = 5):
        pt = self._cena_para_tela(ponto)
        tamanho = max(1, int(tamanho_px))
        pen = QPen(QColor(cor), 1)
        painter.setPen(pen)
        painter.drawLine(int(pt.x() - tamanho), int(pt.y() - tamanho), int(pt.x() + tamanho), int(pt.y() + tamanho))
        painter.drawLine(int(pt.x() - tamanho), int(pt.y() + tamanho), int(pt.x() + tamanho), int(pt.y() - tamanho))

    def _desenhar_marcacoes_piques_elemento(self, painter: QPainter, elemento: dict, cor_molde: str) -> None:
        if elemento.get("mostrar_piques", True) is False:
            return
        pontos_piques_detalhados = self._desenhar_piques_configurados(painter, elemento, cor_molde)
        for mx, my in elemento.get("marcacoes_no_perimetro", []) or []:
            ponto_marcacao = QPointF(float(mx), float(my))
            if any(self._dist(ponto_marcacao, ponto_cfg) <= 1e-6 for ponto_cfg in pontos_piques_detalhados):
                continue
            self._desenhar_marca_x(painter, ponto_marcacao, cor=self._cor_piques_elemento(elemento, cor_molde), tamanho_px=7)

    def _desenhar_piques_configurados(self, painter: QPainter, elemento: dict, cor_molde: str) -> list[QPointF]:
        pontos_desenhados: list[QPointF] = []
        configs = [cfg for cfg in elemento.get("piques_config", []) or [] if isinstance(cfg, dict)]
        for cfg in configs:
            if not isinstance(cfg, dict):
                continue
            cor = self._cor_piques_elemento(elemento, cor_molde, interno=not bool(cfg.get("sobre_contorno", True)))
            ponto = self._ponto_cfg_pique(cfg)
            if ponto is not None:
                pontos_desenhados.append(ponto)
            segmentos = cfg.get("segmentos") or []
            desenhou = False
            for segmento in segmentos:
                pts = self._segmento_cfg_pique(segmento)
                if pts is None:
                    continue
                a, b = pts
                self._desenhar_segmento(painter, a, b, cor=cor, espessura=2.0)
                desenhou = True
            if not desenhou and ponto is not None:
                self._desenhar_marca_x(painter, ponto, cor=cor, tamanho_px=7)
        self._desenhar_piques_graduados_configurados(painter, elemento, cor_molde, configs)
        return pontos_desenhados

    def _desenhar_piques_graduados_configurados(self, painter: QPainter, elemento: dict, cor_molde: str, configs: list[dict]) -> None:
        if elemento.get("mostrar_graduacao", True) is False:
            return
        linhas = self._linhas_graduacao_nao_base(elemento)
        if not linhas:
            return
        base = self._base_contorno_graduacao(elemento)
        if len(base) < 2:
            return
        pontos_cfg = self._pontos_cfg_graduacao_elemento(elemento)
        if not pontos_cfg:
            return
        referencias = self._pontos_referencia_graduacao(elemento)
        deslocamentos_por_tamanho: dict[str, list[tuple[float, float]]] = {}
        for linha in linhas:
            nome = str(linha.get("tamanho") or linha.get("nome") or "").strip()
            if not nome:
                continue
            deslocamentos = self._deslocamentos_graduacao_tamanho(
                pontos_cfg,
                nome,
                len(base),
                contorno=base,
                referencias=referencias,
            )
            if deslocamentos:
                deslocamentos_por_tamanho[nome] = deslocamentos
        if not deslocamentos_por_tamanho:
            return
        for cfg in configs:
            if not bool(cfg.get("sobre_contorno", True)):
                continue
            ponto = self._ponto_cfg_pique(cfg)
            if ponto is None:
                continue
            segmentos = [self._segmento_cfg_pique(segmento) for segmento in (cfg.get("segmentos") or [])]
            segmentos = [segmento for segmento in segmentos if segmento is not None]
            cor = self._cor_piques_elemento(elemento, cor_molde, interno=False)
            for _nome, deslocamentos in deslocamentos_por_tamanho.items():
                deslocamento = self._deslocamento_graduacao_no_ponto(base, deslocamentos, ponto)
                if deslocamento is None:
                    continue
                if segmentos:
                    for a, b in segmentos:
                        self._desenhar_segmento(
                            painter,
                            QPointF(a.x() + deslocamento.x(), a.y() + deslocamento.y()),
                            QPointF(b.x() + deslocamento.x(), b.y() + deslocamento.y()),
                            cor=cor,
                            espessura=2.0,
                        )
                else:
                    self._desenhar_marca_x(
                        painter,
                        QPointF(ponto.x() + deslocamento.x(), ponto.y() + deslocamento.y()),
                        cor=cor,
                        tamanho_px=7,
                    )

    @staticmethod
    def _pontos_cfg_graduacao_elemento(elemento: dict) -> dict:
        tabela = elemento.get("graduacao_tabela") if isinstance(elemento.get("graduacao_tabela"), dict) else {}
        pontos_cfg = tabela.get("pontos") if isinstance(tabela, dict) else None
        if isinstance(pontos_cfg, dict):
            return pontos_cfg
        legado = elemento.get("graduacao_pontos")
        return legado if isinstance(legado, dict) else {}

    @staticmethod
    def _linhas_graduacao_nao_base(elemento: dict) -> list[dict]:
        tamanhos = elemento.get("graduacao_tamanhos") if isinstance(elemento, dict) else None
        if not isinstance(tamanhos, list) or not tamanhos:
            return []
        linhas = [linha for linha in tamanhos if isinstance(linha, dict) and linha.get("ativo", True)]
        if not linhas:
            return []
        base_idx = next((idx for idx, linha in enumerate(linhas) if linha.get("base")), len(linhas) // 2)
        return [linha for idx, linha in enumerate(linhas) if idx != base_idx]

    @staticmethod
    def _base_contorno_graduacao(elemento: dict) -> list[QPointF]:
        pontos: list[QPointF] = []
        for item in elemento.get("pontos", []) or []:
            ponto = VisualizacaoCanvas._qpoint_graduacao_cfg(item)
            if ponto is not None:
                pontos.append(ponto)
        if len(pontos) > 1 and VisualizacaoCanvas._dist_qpoints(pontos[0], pontos[-1]) <= 1e-7:
            pontos.pop()
        return pontos

    @staticmethod
    def _deslocamento_graduacao_no_ponto(
        base: list[QPointF],
        deslocamentos: list[tuple[float, float]],
        ponto: QPointF,
    ) -> QPointF | None:
        if len(base) < 2 or len(deslocamentos) != len(base):
            return None
        melhor: tuple[float, int, float] | None = None
        pares = list(zip(base, base[1:] + [base[0]]))
        for idx, (a, b) in enumerate(pares):
            vx = b.x() - a.x()
            vy = b.y() - a.y()
            denom = (vx * vx) + (vy * vy)
            if denom <= 1e-12:
                t = 0.0
                proj = QPointF(a)
            else:
                t = max(0.0, min(1.0, (((ponto.x() - a.x()) * vx) + ((ponto.y() - a.y()) * vy)) / denom))
                proj = QPointF(a.x() + (vx * t), a.y() + (vy * t))
            dist = VisualizacaoCanvas._dist_qpoints(proj, ponto)
            if melhor is None or dist < melhor[0]:
                melhor = (dist, idx, t)
        if melhor is None:
            return None
        _dist, idx, t = melhor
        prox_idx = (idx + 1) % len(base)
        dx_a, dy_a = deslocamentos[idx]
        dx_b, dy_b = deslocamentos[prox_idx]
        return QPointF(dx_a + ((dx_b - dx_a) * t), dy_a + ((dy_b - dy_a) * t))

    def _cor_piques_elemento(self, elemento: dict, cor_molde: str, interno: bool = False) -> str:
        cor_base = self._cor_linha_elemento(elemento, str(cor_molde or "#ffffff"))
        return self._config_cor_molde("piques_internos" if interno else "piques", cor_base)

    @staticmethod
    def _ponto_cfg_pique(cfg: dict) -> QPointF | None:
        try:
            ponto = cfg.get("ponto")
            if isinstance(ponto, dict):
                return QPointF(float(ponto["x"]), float(ponto["y"]))
            if isinstance(ponto, (list, tuple)) and len(ponto) >= 2:
                return QPointF(float(ponto[0]), float(ponto[1]))
        except Exception:
            return None
        return None

    @staticmethod
    def _segmento_cfg_pique(segmento) -> tuple[QPointF, QPointF] | None:
        try:
            if isinstance(segmento, dict):
                a = segmento.get("a") or segmento.get("inicio")
                b = segmento.get("b") or segmento.get("fim")
            elif isinstance(segmento, (list, tuple)) and len(segmento) >= 2:
                a, b = segmento[0], segmento[1]
            else:
                return None
            if isinstance(a, dict):
                pa = QPointF(float(a["x"]), float(a["y"]))
            else:
                pa = QPointF(float(a[0]), float(a[1]))
            if isinstance(b, dict):
                pb = QPointF(float(b["x"]), float(b["y"]))
            else:
                pb = QPointF(float(b[0]), float(b[1]))
            return pa, pb
        except Exception:
            return None

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
        candidatos: dict[int, float] = {}

        def adicionar_candidato(idx: int, distancia: float) -> None:
            atual = candidatos.get(idx)
            if atual is None or distancia < atual:
                candidatos[idx] = distancia

        for idx in range(len(self.cena.elementos) - 1, -1, -1):
            el = self.cena.elementos[idx]
            if el.get("tipo") == "polyline":
                pontos = self._pontos_hit_teste_elemento(el)
                distancias = [self._distancia_ponto_segmento(a, b, pos) for a, b in zip(pontos, pontos[1:])]
                if distancias and min(distancias) <= tolerancia:
                    adicionar_candidato(idx, min(distancias))
            elif el.get("tipo") == "bezier_quadratica":
                p0 = QPointF(*el["p0"])
                p1 = QPointF(*el["p1"])
                p2 = QPointF(*el["p2"])
                amostra = self._amostrar_bezier_quadratica(p0, p1, p2, segmentos=40)
                distancias = [self._distancia_ponto_segmento(a, b, pos) for a, b in zip(amostra, amostra[1:])]
                if distancias and min(distancias) <= tolerancia:
                    adicionar_candidato(idx, min(distancias))
            else:
                pontos = self._pontos_hit_teste_elemento(el)
                distancias = [self._distancia_ponto_segmento(a, b, pos) for a, b in zip(pontos, pontos[1:])]
                if distancias and min(distancias) <= tolerancia:
                    adicionar_candidato(idx, min(distancias))
            if el.get("molde"):
                fio_origem = el.get("fio_origem")
                fio_fim = el.get("fio_fim")
                if isinstance(fio_origem, (list, tuple)) and isinstance(fio_fim, (list, tuple)) and len(
                        fio_origem) == 2 and len(fio_fim) == 2:
                    p1 = QPointF(float(fio_origem[0]), float(fio_origem[1]))
                    p2 = QPointF(float(fio_fim[0]), float(fio_fim[1]))
                    distancia = self._distancia_ponto_segmento(p1, p2, pos)
                    if distancia <= tolerancia:
                        adicionar_candidato(idx, distancia)
                if el.get("mostrar_nome", True) and str(el.get("nome_molde") or "").strip():
                    pos_nome = el.get("ponto_texto_nome") or el.get("ponto_texto") or el.get("nome_posicao") or el.get("nome_centro")
                    if isinstance(pos_nome, (list, tuple)) and len(pos_nome) == 2:
                        p_nome = QPointF(float(pos_nome[0]), float(pos_nome[1]))
                        distancia = self._dist(p_nome, pos)
                        if distancia <= (tolerancia * 2.0):
                            adicionar_candidato(idx, distancia)
                    else:
                        pontos_nome = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
                        base_nome = pontos_nome[:-1] if len(pontos_nome) >= 3 and pontos_nome[0] == pontos_nome[
                            -1] else pontos_nome
                        if base_nome:
                            cx = sum(p.x() for p in base_nome) / len(base_nome)
                            cy = sum(p.y() for p in base_nome) / len(base_nome)
                            distancia = self._dist(QPointF(cx, cy), pos)
                            if distancia <= (tolerancia * 2.0):
                                adicionar_candidato(idx, distancia)
        return [
            idx
            for idx, _distancia in sorted(
                candidatos.items(),
                key=lambda item: (
                    round(float(item[1]), 6),
                    -int(item[0]),
                    self._prioridade_selecao_elemento(item[0])[0],
                ),
            )
        ]

    def _pontos_hit_teste_elemento(self, elemento: dict) -> list[QPointF]:
        if not isinstance(elemento, dict):
            return []
        if elemento.get("tipo") == "bezier_quadratica":
            try:
                return self._amostrar_bezier_quadratica(
                    QPointF(*elemento["p0"]),
                    QPointF(*elemento["p1"]),
                    QPointF(*elemento["p2"]),
                    segmentos=40,
                )
            except Exception:
                return []
        if self._elemento_curva_suave(elemento):
            pontos_curva = self._pontos_curva_suave_elemento(elemento)
            if len(pontos_curva) >= 2:
                return pontos_curva
        for chave in (
            "pontos",
            "pontos_tracado_real",
            "pontos_principais",
            "pontos_controle_curva",
            "pontos_controle_principais",
            "pontos_controle",
            "controle_cantos",
            "controle_pontos",
        ):
            origem = elemento.get(chave)
            if not isinstance(origem, list) or len(origem) < 2:
                continue
            pontos = [pt for item in origem if (pt := self._qpoint_serializado(item)) is not None]
            if len(pontos) >= 2:
                return pontos
        return []

    def _prioridade_selecao_elemento(self, idx: int) -> tuple[int, int]:
        el = self.cena.elementos[idx] if 0 <= idx < len(self.cena.elementos) else {}
        subtipo = str(el.get("subtipo_audaces") or el.get("metadados", {}).get("subtipo_audaces") or "").strip()
        if el.get("molde") or subtipo == "contorno":
            return (0, -idx)
        if subtipo == "linha_interna":
            return (1, -idx)
        if subtipo == "costura":
            return (2, -idx)
        return (3, -idx)

    def _estilo_por_subtipo_audaces(self, elemento: dict, cor: str, esp: float, estilo: str) -> tuple[str, float, str]:
        subtipo = str(elemento.get("subtipo_audaces") or elemento.get("metadados", {}).get("subtipo_audaces") or "").strip()
        if subtipo == "contorno":
            return cor, max(1.35, esp), "solid"
        if subtipo == "costura":
            return self._config_cor_molde("costura", cor), max(0.85, esp * 0.82), str(getattr(self, "_estilo_linha_costura", "dash") or "dash")
        if subtipo == "linha_interna":
            return self._config_cor_molde("linhas_auxiliares", "#bfbfbf"), max(0.75, esp * 0.8), "solid"
        if subtipo in {"fio", "pique"}:
            chave = "fio" if subtipo == "fio" else "piques"
            return self._config_cor_molde(chave, "#83ffb6"), max(0.8, esp * 0.8), "dot"
        if subtipo in {"texto", "anotacao"}:
            return "#9a9a9a", max(0.7, esp * 0.7), "dot"
        return cor, esp, estilo

    def _molde_id_elemento(self, elemento: dict) -> str:
        return str(elemento.get("molde_id") or elemento.get("id") or "").strip()

    def _indices_costuras_vinculadas(self, elemento_ou_idx) -> list[int]:
        if isinstance(elemento_ou_idx, int):
            if not (0 <= elemento_ou_idx < len(self.cena.elementos)):
                return []
            elemento = self.cena.elementos[elemento_ou_idx]
        else:
            elemento = elemento_ou_idx
        molde_id = self._molde_id_elemento(elemento)
        if not molde_id:
            return []
        indices: list[int] = []
        for idx, el in enumerate(self.cena.elementos):
            costura_vinculada = str(el.get("costura_de_molde_id") or "") == molde_id
            linha_vinculada = bool(el.get("molde_linha_vinculada")) and str(el.get("molde_id") or "") == molde_id
            if costura_vinculada or linha_vinculada:
                indices.append(idx)
        return indices

    def _pontos_costuras_vinculadas(self, elemento: dict) -> list[QPointF]:
        pontos: list[QPointF] = []
        for idx in self._indices_costuras_vinculadas(elemento):
            if 0 <= idx < len(self.cena.elementos):
                el = self.cena.elementos[idx]
                if el.get("tipo") == "polyline":
                    pontos.extend(QPointF(float(x), float(y)) for x, y in el.get("pontos", []))
        return pontos

    def set_mostrar_curva_original_emf(self, ativo: bool):
        self._mostrar_curva_original_emf = bool(ativo)
        self.update()

    def _pontos_render_elemento(self, elemento: dict) -> list[QPointF]:
        if self._mostrar_curva_original_emf:
            meta = elemento.get("metadados", {})
            orig = meta.get("pontos_originais_emf")
            if isinstance(orig, list) and len(orig) >= 2:
                return [QPointF(float(x), float(y)) for x, y in orig]
        return [QPointF(x, y) for x, y in elemento.get("pontos", [])]

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
