from __future__ import annotations

import base64
import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from importlib import import_module
from math import ceil, cos, pi, sin, sqrt
from pathlib import Path
from time import time
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QByteArray, QBuffer, QEvent, QIODevice, QMimeData, QModelIndex, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QDrag, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFileSystemModel,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QListView,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabBar,
    QTabWidget,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
    QSlider,
    QStyledItemDelegate,
)

from canvas.cena import CenaDocumento
from canvas.workspace import AreaDocumentoWidget
from config import EXTENSAO_PROJETO, ICONS_DIR
from core.formatacao import numero_decimal_ponto
from core.line_styles import LINE_STYLES, dash_pattern_for_line, is_geometric_line_style, pen_style_for_line
from core.projeto import Projeto
from formats.gs_project import GSProjectIO
from formats.adsx_io import ADSXIO, ADSXImportError
from formats.adsx_image_trace import vetorizar_preview_adsx
from formats.audaces_xml_import import AudacesXMLImport, xml_doc_para_dict
from formats.audaces_pair_import import AudacesPairImport
from formats.dxf_import import importar_dxf_para_elementos
from ui.backstage_arquivo import BackstageArquivoPanel
from ui.hover_style import folha_estilo_hover_global
from ui.ribbon import RibbonWidget, carregar_icone
from ui.salvar_como_dialog import SalvarComoDialog
from tools.propriedades_tool import ConfigurarCoresTecidosDialog
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from shiboken6 import isValid as _qt_objeto_valido


class _DelegateTraducaoArquivo(QStyledItemDelegate):
    _mapa = {
        "my computer": "Este Computador",
        "desktop": "Área de Trabalho",
        "documents": "Documentos",
        "downloads": "Downloads",
        "network": "Rede",
        "home": "Início",
        "directories": "Diretórios",
        "directory": "Diretório",
        "file folder": "Pasta de arquivos",
        "drive": "Unidade",
        "file": "Arquivo",
    }

    def displayText(self, value, locale):
        txt = str(value or "").strip()
        return self._mapa.get(txt.lower(), txt)


class _BotaoRodapeHover(QPushButton):
    def __init__(self, texto: str, mensagem_hover: str, parent=None):
        super().__init__(texto, parent)
        self._mensagem_hover = mensagem_hover
        self._status_label: QLabel | None = None
        self.setMouseTracking(True)
        self.setToolTip(mensagem_hover)

    def vincular_status(self, lbl_status: QLabel):
        self._status_label = lbl_status

    def enterEvent(self, event):  # noqa: N802
        super().enterEvent(event)
        if self._status_label is not None and self._mensagem_hover:
            self._status_label.setText(self._mensagem_hover)


class _BotaoFerramentaUsuario(QToolButton):
    MIME_TOOL_ID = "application/x-guimma-user-tool-id"

    def __init__(self, tool_id: str, parent=None):
        super().__init__(parent)
        self.tool_id = tool_id
        self._drag_start: QPoint | None = None

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if not (event.buttons() & Qt.LeftButton) or self._drag_start is None:
            super().mouseMoveEvent(event)
            return
        distancia = (event.position().toPoint() - self._drag_start).manhattanLength()
        if distancia < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return
        mime = QMimeData()
        mime.setData(self.MIME_TOOL_ID, self.tool_id.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self._drag_start)
        drag.exec(Qt.MoveAction)


class _LinhaUsuarioDropArea(QWidget):
    def __init__(self, janela: "GuimmaStudioMainWindow"):
        super().__init__()
        self._janela = janela
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(_BotaoFerramentaUsuario.MIME_TOOL_ID):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(_BotaoFerramentaUsuario.MIME_TOOL_ID):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        if not event.mimeData().hasFormat(_BotaoFerramentaUsuario.MIME_TOOL_ID):
            super().dropEvent(event)
            return
        tool_id = bytes(event.mimeData().data(_BotaoFerramentaUsuario.MIME_TOOL_ID)).decode("utf-8")
        self._janela._reordenar_ferramenta_usuario(tool_id, self._indice_drop(event.position().toPoint()))
        event.acceptProposedAction()

    def _indice_drop(self, pos: QPoint) -> int:
        layout = self.layout()
        if layout is None:
            return 0
        indice = 0
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if not isinstance(widget, _BotaoFerramentaUsuario):
                continue
            if pos.x() < widget.geometry().center().x():
                return indice
            indice += 1
        return indice


class GuimmaStudioMainWindow(QMainWindow):
    ARQUIVO_PREFS_APP = Path.home() / ".guimma_studio_prefs.json"
    ARQUIVO_RECUPERACAO = Path.home() / ".guimma_studio_recovery.json"
    MAX_SNAPSHOTS_RECUPERACAO = 5
    INTERVALO_RECUPERACAO_MS = 10_000
    PERFIL_USUARIO_PADRAO = "1"
    TEMA_INTERFACE_PADRAO = "classico_padrao"
    TEMAS_INTERFACE = {
        "classico_padrao": {
            "nome": "Clássico padrão",
            "janela": "#eef2f6",
            "area": "#eceff3",
            "painel": "#ffffff",
            "faixa": "#f4f6f8",
            "texto": "#111111",
            "texto_suave": "#4a5568",
            "borda": "#c8d1da",
            "aba": "#e8edf3",
            "aba_hover": "#dfe8f2",
            "primaria": "#0b7fb8",
            "primaria_escura": "#0a74aa",
            "hover": "#d9edf9",
            "hover_menu": "#e9f3ff",
            "selecionado": "#c5e4f6",
        },
        "azul_neblina": {
            "nome": "Azul neblina",
            "janela": "#edf6fb",
            "area": "#e4f0f8",
            "painel": "#fbfdff",
            "faixa": "#eaf4fb",
            "texto": "#102033",
            "texto_suave": "#476173",
            "borda": "#bfd6e6",
            "aba": "#d9ebf6",
            "aba_hover": "#c8e2f2",
            "primaria": "#2478a7",
            "primaria_escura": "#1b628b",
            "hover": "#d5ecf8",
            "hover_menu": "#dff1fb",
            "selecionado": "#bfe2f5",
        },
        "azul_gelo": {
            "nome": "Azul gelo",
            "janela": "#f3f8fb",
            "area": "#eaf3f8",
            "painel": "#ffffff",
            "faixa": "#eef7fb",
            "texto": "#14212d",
            "texto_suave": "#526b7c",
            "borda": "#cadde8",
            "aba": "#e2f0f7",
            "aba_hover": "#d4eaf5",
            "primaria": "#4a91b8",
            "primaria_escura": "#357699",
            "hover": "#dff0f8",
            "hover_menu": "#e5f4fa",
            "selecionado": "#c9e8f6",
        },
        "verde_menta": {
            "nome": "Verde menta",
            "janela": "#eef8f3",
            "area": "#e4f2eb",
            "painel": "#fbfffd",
            "faixa": "#edf8f2",
            "texto": "#10251d",
            "texto_suave": "#4a6b5e",
            "borda": "#c1dccd",
            "aba": "#dcf0e6",
            "aba_hover": "#cde8dc",
            "primaria": "#2f8f68",
            "primaria_escura": "#247451",
            "hover": "#d6efe3",
            "hover_menu": "#e0f5eb",
            "selecionado": "#bfe7d4",
        },
        "verde_salvia": {
            "nome": "Verde sálvia",
            "janela": "#f1f6f1",
            "area": "#e9f0e8",
            "painel": "#fcfffb",
            "faixa": "#f0f6ef",
            "texto": "#1c281f",
            "texto_suave": "#5e6f60",
            "borda": "#cad9c7",
            "aba": "#e0eadc",
            "aba_hover": "#d2e1ce",
            "primaria": "#5b8f58",
            "primaria_escura": "#477343",
            "hover": "#e0efdc",
            "hover_menu": "#e8f4e5",
            "selecionado": "#cfe7c9",
        },
        "cinza_perola": {
            "nome": "Cinza pérola",
            "janela": "#f1f3f5",
            "area": "#e7ebef",
            "painel": "#ffffff",
            "faixa": "#f6f7f8",
            "texto": "#191f25",
            "texto_suave": "#5d6872",
            "borda": "#cfd6dd",
            "aba": "#e8ecef",
            "aba_hover": "#dde4e9",
            "primaria": "#607d94",
            "primaria_escura": "#4d6679",
            "hover": "#e0e8ee",
            "hover_menu": "#edf2f5",
            "selecionado": "#d2e0e8",
        },
        "lavanda_clara": {
            "nome": "Lavanda clara",
            "janela": "#f5f2fb",
            "area": "#ece7f5",
            "painel": "#fffdff",
            "faixa": "#f5f0fb",
            "texto": "#231b31",
            "texto_suave": "#675a7c",
            "borda": "#d6cbe6",
            "aba": "#eadff6",
            "aba_hover": "#dfd0f0",
            "primaria": "#8065a8",
            "primaria_escura": "#665087",
            "hover": "#e8ddf4",
            "hover_menu": "#f0e8fa",
            "selecionado": "#ddcff1",
        },
        "areia_clara": {
            "nome": "Areia clara",
            "janela": "#f7f4ee",
            "area": "#eee9df",
            "painel": "#fffdf8",
            "faixa": "#f8f4eb",
            "texto": "#2b241b",
            "texto_suave": "#756857",
            "borda": "#ded2bf",
            "aba": "#eee4d4",
            "aba_hover": "#e4d7c4",
            "primaria": "#9a7a4f",
            "primaria_escura": "#7c633f",
            "hover": "#efe4d2",
            "hover_menu": "#f6ead8",
            "selecionado": "#e5d5bd",
        },
    }
    CORES_CANVAS_PADRAO = {
        "desenho": "#ffffff",
        "fundo": "#000000",
        "selecao": "#2da8ff",
        "grade": "#808080",
        "snap_desenho": "#6f6f6f",
        "snap_referencia": "#d71313",
    }
    CORES_TECIDOS_PADRAO = {
        "1": "#ffffff",
        "2": "#00b050",
    }
    CORES_MOLDES_PADRAO = {
        "piques": {"ativo": False, "cor": "#efefef"},
        "piques_internos": {"ativo": False, "cor": "#efefef"},
        "fio": {"ativo": False, "cor": "#efefef"},
        "linhas_auxiliares": {"ativo": False, "cor": "#bfbfbf"},
        "costura": {"ativo": False, "cor": "#efefef"},
        "molde_dobrado": {"ativo": False, "cor": "#efefef"},
        "nome_molde": {"ativo": False, "cor": "#efefef"},
        "descricao": {"ativo": False, "cor": "#efefef"},
        "numeros": {"ativo": False, "cor": "#efefef"},
        "observacoes": {"ativo": False, "cor": "#efefef"},
        "linha_simetria": {"ativo": False, "cor": "#efefef"},
        "margem": {"ativo": False, "cor": "#efefef"},
        "tamanhos_menores": {"ativo": False, "cor": "#efefef"},
        "tamanho_base": {"ativo": False, "cor": "#efefef"},
        "tamanhos_maiores": {"ativo": False, "cor": "#efefef"},
        "ponto_controle": {"ativo": False, "cor": "#efefef", "forma": "Circulo preenchido"},
        "ponto_pique": {"ativo": False, "cor": "#efefef", "forma": "Quadrado preenchido"},
        "ponto_nao_graduado": {"ativo": False, "cor": "#efefef", "forma": "Losango"},
    }
    ESTILO_LINHA_COSTURA_PADRAO = "dash"
    ZOOM_INICIAL_CANVAS = 8.760
    ORIGEM_INICIAL_CANVAS_X = 110.0
    ORIGEM_INICIAL_CANVAS_Y = 0.0
    FERRAMENTAS_USUARIO_PADRAO = [
        "inverter_moldes",
        "espiral_e_curvas",
        "curva",
        "reta",
        "cadastrar_curva",
        "manipular_pontos",
        "inserir_ponto",
        "excluir_ponto",
        "mover_ponto",
        "selecionar_tudo",
        "elemento_paralelo",
        "copiar",
        "colar",
        "desfazer",
        "refazer",
        "ajuste_automatico",
        "excluir",
        "retangulo",
        "cores",
        "cortar",
        "salvar",
        "salvar_como",
        "imprimir",
        "plotar",
        "extrair_molde",
        "criar_molde",
        "dobrar",
        "desdobrar",
        "inserir_pique",
        "remover_costura",
        "ponto_restauracao",
        "restaurar_copia",
        "graduar_curva",
        "agrupar",
        "mover",
        "espelhar",
        "costura",
        "remover_pique",
        "unir",
        "sentido_fio",
        "bainha",
        "relacionamento_piques",
        "pique_texto",
        "autor",
        "conferir",
        "conferir_multiplos",
    ]

    def __init__(self):
        super().__init__()
        self.projeto_atual = Projeto()
        prefs_app = self._carregar_preferencias_app()
        if prefs_app:
            self.projeto_atual.preferencias_usuario.update(prefs_app)
        self.projeto_atual.preferencias_usuario["menu_moldes_visivel"] = False
        self._arquivo_atual: Path | None = None
        self._contador_sem_nome = 0
        # Regra de inicialização: sempre abrir com Selecionar ativo.
        self._ferramenta_ativa_id = "selecionar"
        self.projeto_atual.preferencias_usuario["ferramenta_ativa_id"] = "selecionar"
        self._modo_navegacao = "cursor"
        self._estilo_desenho_atual = {"cor": "#ffffff", "estilo": "solid", "espessura": 1.0, "amplitude": 1.0}
        self._restaurar_estilo_desenho_memorizado()
        self._passo_snap_angular_atual = float(self.projeto_atual.preferencias_usuario.get("passo_snap_angular", 45.0))
        self._unidade_medida = str(self.projeto_atual.preferencias_usuario.get("unidade_medida", "cm"))
        self._passo_unidade_medida = float(self.projeto_atual.preferencias_usuario.get("passo_unidade_medida", 0.5))
        self._unidade_area = str(self.projeto_atual.preferencias_usuario.get("unidade_area", "m"))
        self._precisao_medida = str(self.projeto_atual.preferencias_usuario.get("precisao_medida", "0.01"))
        self._snap_contextual_ativo = bool(self.projeto_atual.preferencias_usuario.get("snap_contextual_ativo", True))
        self._snap_ativo_global = bool(self.projeto_atual.preferencias_usuario.get("snap_ativo", True))
        self._janela_aux_curva: QDialog | None = None
        self._janela_aux_retangulo: QDialog | None = None
        self._janelas_aux_instrucao: dict[str, QDialog] = {}
        self._chk_aux_retangulo_criar_molde: QCheckBox | None = None
        self._retangulo_criar_molde = bool(self.projeto_atual.preferencias_usuario.get("retangulo_criar_molde", True))
        self._cores_canvas_global = self._normalizar_cores_canvas(
            self.projeto_atual.preferencias_usuario.get("cores_canvas_global", {})
        )
        self._cores_moldes_global = self._normalizar_cores_moldes(
            self.projeto_atual.preferencias_usuario.get("cores_moldes_global", {})
        )
        self._estilo_linha_costura_global = str(
            self.projeto_atual.preferencias_usuario.get("estilo_linha_costura_global", self.ESTILO_LINHA_COSTURA_PADRAO)
        )
        self._usar_cores_ferramentas_global = bool(
            self.projeto_atual.preferencias_usuario.get("usar_cores_ferramentas_global", False)
        )
        self._snap_cores_automaticas_global = bool(
            self.projeto_atual.preferencias_usuario.get("snap_cores_automaticas_global", True)
        )
        self._opacidade_imagens_global = max(
            0.0,
            min(float(self.projeto_atual.preferencias_usuario.get("opacidade_imagens_global", 1.0)), 1.0),
        )
        self._mostrar_cor_tecidos_global = bool(self.projeto_atual.preferencias_usuario.get("mostrar_cor_tecidos_global", True))
        self._mostrar_cor_tecidos_menu_global = bool(
            self.projeto_atual.preferencias_usuario.get("mostrar_cor_tecidos_menu_global", False)
        )
        cores_cfg = self.projeto_atual.preferencias_usuario.get("cores_tecidos_global", {})
        self._cores_tecidos_global: dict[str, str] = self._normalizar_cores_tecidos(cores_cfg)
        esquemas = self.projeto_atual.preferencias_usuario.get("esquemas_cores_usuario", {})
        self._esquemas_cores_usuario: dict[str, dict] = dict(esquemas) if isinstance(esquemas, dict) else {}
        self._clipboard_elementos_global: dict | None = None
        self._posicoes_caixas_aux: dict[str, tuple[int, int]] = self._carregar_posicoes_caixas_aux()
        self._painel_coordenadas_pos_global: tuple[int, int] | None = None
        ferramentas_usuario = self.projeto_atual.preferencias_usuario.get(
            "ferramentas_usuario",
            self.FERRAMENTAS_USUARIO_PADRAO,
        )
        self._ferramentas_usuario_ids: list[str] = list(ferramentas_usuario or self.FERRAMENTAS_USUARIO_PADRAO)
        self._garantir_ajuste_automatico_na_barra_usuario()
        self._ultima_aba_nao_usuario = "construcao"
        self._barra_usuarios_posicao = self.projeto_atual.preferencias_usuario.get("barra_usuarios_posicao", "area")
        self._barra_usuarios_modo_lateral = str(
            self.projeto_atual.preferencias_usuario.get("barra_usuarios_modo_lateral", "completa")
        )
        self._barra_usuarios_habilitada = bool(self.projeto_atual.preferencias_usuario.get("barra_usuarios_habilitada", True))
        self._perfis_usuarios: dict[str, list[str]] = {}
        self._perfis_usuarios_cfg: dict[str, dict] = {}
        self._perfil_usuario_atual = self.PERFIL_USUARIO_PADRAO
        self._tema_interface_id = self._normalizar_tema_interface(
            self.projeto_atual.preferencias_usuario.get("tema_interface", self.TEMA_INTERFACE_PADRAO)
        )
        self._acoes_tema_interface: dict[str, list[QAction]] = {}
        self._indice_layout_organizacao_moldes = 0
        self._indice_visualizacao_proximo_molde = -1
        self._pendente_centralizar_indicado = False
        self._inicializar_perfis_usuarios()
        self._opcoes_app = self._carregar_opcoes_app()
        self._timer_salvar_preferencias_app = QTimer(self)
        self._timer_salvar_preferencias_app.setSingleShot(True)
        self._timer_salvar_preferencias_app.timeout.connect(self._salvar_preferencias_app)
        self._timer_salvar_estado = QTimer(self)
        self._timer_salvar_estado.setSingleShot(True)
        self._timer_salvar_estado.timeout.connect(self._salvar_estado_projeto_silenciosamente)
        self._timer_recovery = QTimer(self)
        self._timer_recovery.timeout.connect(self._salvar_snapshot_recuperacao)
        self._aplicar_intervalo_recovery()
        self._assinatura_menu_moldes: tuple | None = None
        self._timer_menu_moldes = QTimer(self)
        self._timer_menu_moldes.setInterval(250)
        self._timer_menu_moldes.timeout.connect(self._sincronizar_menu_moldes_ao_vivo)
        self._menu_backstage_hover_aberto: QMenu | None = None
        self._menu_backstage_hover_origem: str | None = None
        self._menu_backstage_hover_botao: QWidget | None = None
        self._menus_backstage_hover: list[QMenu] = []
        self._ajuste_restauracao_maximizado_pendente = False
        self._timer_fechar_submenu_backstage = QTimer(self)
        self._timer_fechar_submenu_backstage.setSingleShot(True)
        self._timer_fechar_submenu_backstage.timeout.connect(self._fechar_submenu_backstage_se_cursor_fora)
        self._timer_vigiar_submenu_backstage = QTimer(self)
        self._timer_vigiar_submenu_backstage.setInterval(50)  # 50ms para resposta rápida
        self._timer_vigiar_submenu_backstage.timeout.connect(self._processar_hover_backstage_global)
        self.setWindowTitle("GUIMMA STUDIO")
        self._configurar_interface()
        self._aplicar_tema_interface()
        self.ribbon.aplicar_estilo(self._estilo_desenho_atual)
        self._limpar_abas_documentos()
        self._configurar_atalhos()
        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(250, self._oferecer_recuperacao_pos_falha)
        QTimer.singleShot(0, lambda: self._ativar_ferramenta_global("selecionar"))

    def exibir_inicial(self):
        self._aplicar_geometria_normal_padrao()
        self.setWindowState(self.windowState() | Qt.WindowMaximized)
        self.show()
        self._agendar_reencaixe_janela_canvas()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._agendar_reencaixe_janela_canvas()

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() != QEvent.WindowStateChange:
            return
        saiu_do_maximizado = bool(event.oldState() & Qt.WindowMaximized) and not self.isMaximized()
        if saiu_do_maximizado and not self.isMinimized():
            self._ajuste_restauracao_maximizado_pendente = True
            QTimer.singleShot(0, self._aplicar_geometria_restaurada_do_maximizado)

    def _geometria_normal_padrao(self) -> QRect:
        tela = self.screen() or QApplication.primaryScreen()
        area = tela.availableGeometry() if tela is not None else QRect(0, 0, 1388, 893)
        margem = 24
        largura = min(1388, max(900, area.width() - margem))
        altura = min(893, max(620, area.height() - margem))
        x = area.x() + max(0, (area.width() - largura) // 2)
        y = area.y() + max(0, (area.height() - altura) // 2)
        return QRect(x, y, largura, altura)

    def _aplicar_geometria_normal_padrao(self):
        self.setGeometry(self._geometria_normal_padrao())

    def _aplicar_geometria_restaurada_do_maximizado(self):
        if not self._ajuste_restauracao_maximizado_pendente or self.isMaximized() or self.isMinimized():
            return
        self._ajuste_restauracao_maximizado_pendente = False
        self._aplicar_geometria_normal_padrao()
        self._agendar_reencaixe_janela_canvas()

    def _carregar_preferencias_app(self) -> dict:
        try:
            if self.ARQUIVO_PREFS_APP.exists():
                return json.loads(self.ARQUIVO_PREFS_APP.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {}

    def _salvar_preferencias_app(self):
        try:
            self.ARQUIVO_PREFS_APP.write_text(
                json.dumps(self.projeto_atual.preferencias_usuario, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _agendar_salvar_preferencias_app(self, intervalo_ms: int = 350):
        timer = getattr(self, "_timer_salvar_preferencias_app", None)
        if timer is None:
            self._salvar_preferencias_app()
            return
        timer.start(max(0, int(intervalo_ms)))

    def _normalizar_tema_interface(self, tema_id: object) -> str:
        tema = str(tema_id or "").strip()
        return tema if tema in self.TEMAS_INTERFACE else self.TEMA_INTERFACE_PADRAO

    def _tema_interface(self) -> dict[str, str]:
        return self.TEMAS_INTERFACE[self._normalizar_tema_interface(getattr(self, "_tema_interface_id", ""))]

    def _estilo_botao_menu_topo(self) -> str:
        tema = self._tema_interface()
        return (
            f"QToolButton {{ color:{tema['texto']}; font-weight:400; font-size:13px; "
            "padding:0 6px; border:none; background:transparent; }"
            "QToolButton::menu-indicator { subcontrol-origin: padding; subcontrol-position: right center; }"
            f"QToolButton:hover {{ color:{tema['primaria_escura']}; background:{tema['hover']}; }}"
        )

    def _estilo_menu_popup_topo(self) -> str:
        tema = self._tema_interface()
        return folha_estilo_hover_global() + (
            f"QMenu {{ background:{tema['painel']}; color:{tema['texto']}; border:1px solid {tema['borda']}; padding:4px; }}"
            f"QMenu::item {{ color:{tema['texto']}; padding:6px 12px; }}"
            f"QMenu::item:selected {{ background:{tema['hover_menu']}; color:{tema['primaria_escura']}; }}"
            f"QMenu::separator {{ height:1px; background:{tema['borda']}; margin:4px 8px; }}"
        )

    def _estilo_botoes_rodape(self) -> str:
        tema = self._tema_interface()
        return (
            f"QPushButton {{ color:{tema['texto']}; background:transparent; border:none; padding:1px 6px; min-width:22px; }}"
            f"QPushButton:hover {{ background:{tema['hover']}; border:none; }}"
            f"QPushButton:checked {{ background:{tema['selecionado']}; border:none; color:{tema['primaria_escura']}; font-weight:700; }}"
        )

    def _estilo_abas_documentos(self) -> str:
        tema = self._tema_interface()
        return (
            f"QTabWidget::pane {{ border: 1px solid {tema['borda']}; }}"
            "QTabWidget::tab-bar { alignment: left; }"
            f"QTabBar {{ background: {tema['faixa']}; }}"
            f"QTabBar::tab {{ background:{tema['painel']}; color:{tema['texto']}; border:1px solid {tema['borda']}; "
            "padding:0 16px 0 7px; margin-right:1px; min-height:14px; font-size:12px; }"
            f"QTabBar::tab:hover {{ background:{tema['hover']}; }}"
            f"QTabBar::tab:selected {{ background:{tema['painel']}; border-bottom:2px solid {tema['primaria']}; }}"
        )

    def _estilo_botoes_usuario(self) -> str:
        tema = self._tema_interface()
        return (
            f"QPushButton {{ background: transparent; border: 1px solid transparent; color: {tema['texto']}; "
            "font-weight: 400; font-size: 12px; padding: 0 8px; border-radius: 3px; }"
            f"QPushButton:hover {{ background: {tema['hover']}; border-color: {tema['borda']}; color: {tema['primaria_escura']}; }}"
            f"QPushButton:pressed {{ background: {tema['selecionado']}; border-color: {tema['primaria']}; }}"
            f"QPushButton:disabled {{ color: {tema['texto_suave']}; background: transparent; border-color: transparent; }}"
        )

    def _estilo_combo_usuario(self) -> str:
        tema = self._tema_interface()
        return (
            f"QComboBox {{ color:{tema['texto']}; background:{tema['painel']}; border:1px solid {tema['borda']}; "
            "padding: 2px 8px; font-weight: 400; }"
            f"QComboBox:hover {{ border-color:{tema['primaria']}; background:{tema['hover_menu']}; }}"
            f"QComboBox QAbstractItemView {{ color:{tema['texto']}; background:{tema['painel']}; "
            f"selection-background-color:{tema['hover_menu']}; selection-color:{tema['primaria_escura']}; }}"
        )

    def _estilo_botao_linha_usuario(self) -> str:
        tema = self._tema_interface()
        return (
            "QToolButton { border: 1px solid transparent; background: transparent; padding: 0px; margin: 0px; border-radius: 4px; }"
            f"QToolButton:hover {{ border-color: {tema['borda']}; background: {tema['hover']}; }}"
            f"QToolButton:pressed {{ border-color: {tema['primaria']}; background: {tema['selecionado']}; }}"
            f"QToolButton:checked {{ border-color: {tema['primaria']}; background: {tema['selecionado']}; }}"
        )

    def _estilo_barra_lateral_usuario(self) -> str:
        tema = self._tema_interface()
        return (
            f"QFrame#BarraLateralFerramentas {{ background: {tema['faixa']}; border: 1px solid {tema['borda']}; border-radius: 6px; }}"
            f"QLabel#TituloBarraLateralFerramentas {{ color: {tema['primaria_escura']}; font-size: 12px; font-weight: 700; padding: 8px 8px 4px 8px; }}"
            f"QLabel#GrupoBarraLateralFerramentas {{ color: {tema['texto_suave']}; font-size: 10px; font-weight: 700; padding: 8px 8px 2px 8px; }}"
            "QScrollArea { background: transparent; border: none; }"
        )

    def _estilo_botao_barra_lateral_usuario(self) -> str:
        tema = self._tema_interface()
        return (
            f"QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 5px; color: {tema['texto']}; "
            "font-size: 12px; font-weight: 400; padding: 3px 6px; text-align: left; }"
            f"QToolButton:hover {{ background: {tema['hover']}; border: 1px solid {tema['borda']}; color: {tema['primaria_escura']}; }}"
            f"QToolButton:pressed {{ background: {tema['selecionado']}; }}"
            f"QToolButton:checked {{ background: {tema['selecionado']}; border: 1px solid {tema['primaria']}; color: {tema['primaria_escura']}; font-weight: 600; }}"
        )

    def _aplicar_tema_barra_usuario(self):
        if hasattr(self, "faixa_usuarios"):
            tema = self._tema_interface()
            self.faixa_usuarios.setStyleSheet(
                f"QFrame {{ background:{tema['faixa']}; border:1px solid {tema['borda']}; }}"
            )
            for btn in self.faixa_usuarios.findChildren(QPushButton):
                btn.setStyleSheet(self._estilo_botoes_usuario())
            for combo in self.faixa_usuarios.findChildren(QComboBox):
                combo.setStyleSheet(self._estilo_combo_usuario())
            for label in self.faixa_usuarios.findChildren(QLabel):
                label.setStyleSheet(f"color:{tema['texto']}; font-size:12px; font-weight:400;")
            for btn in self.faixa_usuarios.findChildren(_BotaoFerramentaUsuario):
                btn.setStyleSheet(self._estilo_botao_linha_usuario())
        if hasattr(self, "barra_lateral_ferramentas") and self.barra_lateral_ferramentas is not None:
            self.barra_lateral_ferramentas.setStyleSheet(self._estilo_barra_lateral_usuario())
            for btn in self.barra_lateral_ferramentas.findChildren(QToolButton):
                btn.setStyleSheet(self._estilo_botao_barra_lateral_usuario())

    def _aplicar_tema_areas_documento(self):
        if not hasattr(self, "abas_documentos"):
            return
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.aplicar_tema(self._tema_interface())

    def _sincronizar_acoes_tema_interface(self):
        if not hasattr(self, "_acoes_tema_interface"):
            return
        atual = self._normalizar_tema_interface(getattr(self, "_tema_interface_id", ""))
        for tema_id, acoes in self._acoes_tema_interface.items():
            for acao in list(acoes):
                try:
                    acao.blockSignals(True)
                    acao.setChecked(tema_id == atual)
                    acao.blockSignals(False)
                except RuntimeError:
                    continue
                except Exception:
                    continue

    def _criar_submenu_temas_interface(self, parent_menu: QMenu) -> QMenu:
        submenu = parent_menu.addMenu("Tema")
        submenu.setStyleSheet(self._estilo_menu_popup_topo())
        grupo = QActionGroup(self)
        grupo.setExclusive(True)
        self._acoes_tema_interface = {
            tema_id: [acao for acao in acoes if self._qt_widget_vivo(acao)]
            for tema_id, acoes in getattr(self, "_acoes_tema_interface", {}).items()
        }
        for tema_id, cfg in self.TEMAS_INTERFACE.items():
            acao = QAction(str(cfg["nome"]), self)
            acao.setCheckable(True)
            acao.setChecked(tema_id == self._tema_interface_id)
            acao.triggered.connect(
                lambda marcado=False, tid=tema_id: self._definir_tema_interface(tid) if marcado else None
            )
            grupo.addAction(acao)
            submenu.addAction(acao)
            self._acoes_tema_interface.setdefault(tema_id, []).append(acao)
        return submenu

    def _definir_tema_interface(self, tema_id: str, salvar: bool = True):
        tema_id = self._normalizar_tema_interface(tema_id)
        self._tema_interface_id = tema_id
        self.projeto_atual.preferencias_usuario["tema_interface"] = tema_id
        self._aplicar_tema_interface()
        if salvar:
            self._sincronizar_perfil_usuario_atual()
            self.lbl_status.setText(f"Tema aplicado: {self.TEMAS_INTERFACE[tema_id]['nome']}")

    def _aplicar_tema_interface(self):
        if not hasattr(self, "ribbon"):
            return
        tema = self._tema_interface()
        self.setStyleSheet(
            folha_estilo_hover_global()
            +
            f"""
            QMainWindow {{ background: {tema['janela']}; }}
            QWidget {{
                color: {tema['texto']};
            }}
            QLabel, QCheckBox, QRadioButton, QPushButton, QToolButton, QLineEdit, QComboBox, QMenu {{
                color: {tema['texto']};
            }}
            QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
                background: {tema['painel']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
            }}
            QToolTip {{
                background-color: {tema['painel']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
            }}
            QTabBar::tab {{
                background: {tema['aba']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
                font-size: 14px;
                font-weight: 600;
                padding: 6px 20px;
            }}
            QTabBar::tab:selected {{
                background: {tema['painel']};
                color: {tema['primaria_escura']};
                border-bottom: 2px solid {tema['primaria']};
            }}
            QTabBar::tab:hover {{ background: {tema['aba_hover']}; }}
            QTabBar::tab:selected:hover {{
                background: {tema['painel']};
                color: {tema['primaria_escura']};
                border-bottom: 2px solid {tema['primaria']};
            }}
            """
        )
        if hasattr(self, "botao_arquivo"):
            self.botao_arquivo.setStyleSheet(
                f"background:{tema['primaria']};color:white;font-weight:400;border:1px solid {tema['primaria_escura']};"
                "font-size:13px;border-radius:0;padding:0 8px;"
            )
        for btn_name in ("btn_visao", "btn_opcoes", "btn_janelas"):
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.setStyleSheet(self._estilo_botao_menu_topo())
        for menu_name in ("menu_visao", "menu_opcoes", "menu_janelas"):
            menu = getattr(self, menu_name, None)
            if menu is not None:
                menu.setStyleSheet(self._estilo_menu_popup_topo())
        if hasattr(self, "ribbon"):
            self.ribbon.aplicar_tema(tema)
        if hasattr(self, "area_documento_widget"):
            self.area_documento_widget.setStyleSheet(f"background: {tema['area']};")
        self._aplicar_tema_areas_documento()
        self._aplicar_tema_barra_usuario()
        if hasattr(self, "abas_documentos"):
            self.abas_documentos.setStyleSheet(self._estilo_abas_documentos())
        if hasattr(self, "backstage"):
            self.backstage.setStyleSheet(
                f"QFrame#BackstagePanel {{ background: {tema['painel']}; border: 1px solid {tema['borda']}; }}"
                f"QFrame#BackstageLeft {{ background: {tema['faixa']}; border-right: 1px solid {tema['borda']}; }}"
                f"QFrame#BackstageRight {{ background: {tema['painel']}; }}"
                f"QLabel#BackstageTitle {{ color: {tema['primaria_escura']}; font-size: 18px; font-weight: 800; padding: 0 14px 10px 16px; }}"
                f"QLabel#BackstageHeader {{ color: {tema['texto']}; font-size: 19px; font-weight: 700; }}"
                f"QListWidget {{ background: {tema['painel']}; color: {tema['texto']}; border: 1px solid {tema['borda']}; }}"
                f"QListWidget::item:hover {{ background: {tema['hover']}; }}"
            )
            for nome_obj, estilo in {
                "BackstageLeft": f"background: {tema['faixa']}; border-right: 1px solid {tema['borda']};",
                "BackstageRight": f"background: {tema['painel']};",
            }.items():
                widget = self.backstage.findChild(QFrame, nome_obj)
                if widget is not None:
                    widget.setStyleSheet(estilo)
            for nome_obj, estilo in {
                "BackstageTitle": f"color: {tema['primaria_escura']}; font-size: 18px; font-weight: 800; padding: 0 14px 10px 16px;",
                "BackstageHeader": f"font-size: 19px; font-weight: 700; color: {tema['texto']};",
            }.items():
                label = self.backstage.findChild(QLabel, nome_obj)
                if label is not None:
                    label.setStyleSheet(estilo)
            self._aplicar_estilo_hover_backstage_arquivo()
        if hasattr(self, "barra_atalhos_rodape"):
            self.barra_atalhos_rodape.setStyleSheet(
                f"background:{tema['faixa']}; border-top:1px solid {tema['borda']}; border-bottom:1px solid {tema['borda']};"
            )
            for btn in self.barra_atalhos_rodape.findChildren(QPushButton):
                btn.setStyleSheet(self._estilo_botoes_rodape())
        if hasattr(self, "barra_mensagem"):
            self.barra_mensagem.setStyleSheet(
                f"background: {tema['primaria']}; border-top: 1px solid {tema['primaria_escura']}; color: white;"
            )
        if hasattr(self, "lbl_status"):
            self.lbl_status.setStyleSheet("color: white;")
        if hasattr(self, "lbl_escala"):
            self.lbl_escala.setStyleSheet("color: white; font-weight: 600; padding-right: 2px;")
        self._sincronizar_acoes_tema_interface()

    def _cor_hex_valida(self, valor: object, padrao: str) -> str:
        cor = QColor(str(valor or ""))
        return cor.name() if cor.isValid() else QColor(padrao).name()

    def _normalizar_cores_canvas(self, cores: object) -> dict[str, str]:
        base = dict(self.CORES_CANVAS_PADRAO)
        if isinstance(cores, dict):
            for chave in base:
                if chave in cores:
                    base[chave] = self._cor_hex_valida(cores.get(chave), base[chave])
        return base

    def _normalizar_cores_tecidos(self, cores: object) -> dict[str, str]:
        base = dict(self.CORES_TECIDOS_PADRAO)
        if isinstance(cores, dict):
            for chave, valor in cores.items():
                nome = str(chave or "").strip()
                if nome:
                    base[nome] = self._cor_hex_valida(valor, base.get(nome, "#ffffff"))
        return base

    def _normalizar_cores_moldes(self, cores: object) -> dict[str, dict]:
        base = {chave: dict(valor) for chave, valor in self.CORES_MOLDES_PADRAO.items()}
        if isinstance(cores, dict):
            for chave, valor in cores.items():
                if chave not in base or not isinstance(valor, dict):
                    continue
                base[chave]["ativo"] = bool(valor.get("ativo", base[chave]["ativo"]))
                base[chave]["cor"] = self._cor_hex_valida(valor.get("cor"), str(base[chave]["cor"]))
                if "forma" in base[chave]:
                    forma = str(valor.get("forma", base[chave]["forma"]) or base[chave]["forma"])
                    if forma not in {"Circulo preenchido", "Quadrado preenchido", "Losango"}:
                        forma = str(base[chave]["forma"])
                    base[chave]["forma"] = forma
        return base

    def _carregar_opcoes_app(self) -> dict:
        op = self.projeto_atual.preferencias_usuario.get("opcoes_app", {})
        if not isinstance(op, dict):
            op = {}
        return {
            "auto_recuperacao_min": max(1, int(op.get("auto_recuperacao_min", 1))),
            "antialiasing": bool(op.get("antialiasing", True)),
            "validar_ponto_cam": bool(op.get("validar_ponto_cam", True)),
            "texto_tamanho_cm": float(op.get("texto_tamanho_cm", 1.0)),
            "usar_truetype": bool(op.get("usar_truetype", False)),
            "pique_largura_cm": float(op.get("pique_largura_cm", 0.3)),
            "pique_altura_cm": float(op.get("pique_altura_cm", 0.3)),
            "pique_angulo": float(op.get("pique_angulo", 0.0)),
            "mostrar_furador_iso": bool(op.get("mostrar_furador_iso", False)),
            "permitir_graduacao_altura": bool(op.get("permitir_graduacao_altura", False)),
            "usar_ferramentas_moldes": bool(op.get("usar_ferramentas_moldes", True)),
            "rotacionar_duplo_clique": bool(op.get("rotacionar_duplo_clique", True)),
            "exibir_coef_encolhimento": bool(op.get("exibir_coef_encolhimento", True)),
            "exibir_ferramenta_costura": bool(op.get("exibir_ferramenta_costura", False)),
            "permitir_docar_menus_aux": bool(op.get("permitir_docar_menus_aux", False)),
            "barra_tarefas_flutuante": bool(op.get("barra_tarefas_flutuante", False)),
            "tamanho_icone": str(op.get("tamanho_icone", "Grande")),
            "criar_ponto_restauracao_auto": bool(op.get("criar_ponto_restauracao_auto", False)),
            "arquivo_backup": bool(op.get("arquivo_backup", False)),
            "caminho_backup": str(op.get("caminho_backup", "")),
            "config_compartilhadas": str(op.get("config_compartilhadas", "")),
            "compartilhar_tecido": bool(op.get("compartilhar_tecido", False)),
            "compartilhar_regras_graduacao": bool(op.get("compartilhar_regras_graduacao", False)),
            "compartilhar_plotagem": bool(op.get("compartilhar_plotagem", False)),
        }

    def _salvar_opcoes_app(self):
        self.projeto_atual.preferencias_usuario["opcoes_app"] = dict(self._opcoes_app)
        self._salvar_preferencias_app()

    def _aplicar_intervalo_recovery(self):
        self._timer_recovery.start(self.INTERVALO_RECUPERACAO_MS)

    def _capturar_configuracoes_perfil(self) -> dict:
        return {
            "unidade_medida": self._unidade_medida,
            "passo_unidade_medida": self._passo_unidade_medida,
            "unidade_area": self._unidade_area,
            "precisao_medida": self._precisao_medida,
            "barra_usuarios_habilitada": self._barra_usuarios_habilitada,
            "barra_usuarios_posicao": self._barra_usuarios_posicao,
            "barra_usuarios_modo_lateral": self._barra_usuarios_modo_lateral,
            "estilo_desenho": dict(self._estilo_desenho_atual),
            "cores_canvas_global": dict(self._cores_canvas_global),
            "cores_moldes_global": {chave: dict(valor) for chave, valor in self._cores_moldes_global.items()},
            "estilo_linha_costura_global": self._estilo_linha_costura_global,
            "usar_cores_ferramentas_global": bool(self._usar_cores_ferramentas_global),
            "snap_cores_automaticas_global": bool(self._snap_cores_automaticas_global),
            "opacidade_imagens_global": float(self._opacidade_imagens_global),
            "mostrar_cor_tecidos_global": bool(self._mostrar_cor_tecidos_global),
            "mostrar_cor_tecidos_menu_global": bool(self._mostrar_cor_tecidos_menu_global),
            "cores_tecidos_global": dict(self._cores_tecidos_global),
            "esquemas_cores_usuario": {
                str(nome): dict(cfg)
                for nome, cfg in self._esquemas_cores_usuario.items()
                if isinstance(cfg, dict)
            },
            "tema_interface": self._normalizar_tema_interface(self._tema_interface_id),
        }

    def _aplicar_configuracoes_perfil(self, cfg: dict):
        if not isinstance(cfg, dict):
            return
        self._unidade_medida = str(cfg.get("unidade_medida", self._unidade_medida))
        self._passo_unidade_medida = float(cfg.get("passo_unidade_medida", self._passo_unidade_medida))
        self._unidade_area = str(cfg.get("unidade_area", self._unidade_area))
        self._precisao_medida = str(cfg.get("precisao_medida", self._precisao_medida))
        self._barra_usuarios_habilitada = bool(cfg.get("barra_usuarios_habilitada", self._barra_usuarios_habilitada))
        self._barra_usuarios_posicao = str(cfg.get("barra_usuarios_posicao", self._barra_usuarios_posicao))
        self._barra_usuarios_modo_lateral = str(
            cfg.get("barra_usuarios_modo_lateral", self._barra_usuarios_modo_lateral)
        )
        estilo = cfg.get("estilo_desenho")
        if isinstance(estilo, dict):
            self._estilo_desenho_atual.update(estilo)
        self._cores_canvas_global = self._normalizar_cores_canvas(cfg.get("cores_canvas_global", self._cores_canvas_global))
        self._cores_moldes_global = self._normalizar_cores_moldes(cfg.get("cores_moldes_global", self._cores_moldes_global))
        self._estilo_linha_costura_global = str(
            cfg.get("estilo_linha_costura_global", self._estilo_linha_costura_global)
        )
        self._usar_cores_ferramentas_global = bool(
            cfg.get("usar_cores_ferramentas_global", self._usar_cores_ferramentas_global)
        )
        self._snap_cores_automaticas_global = bool(
            cfg.get("snap_cores_automaticas_global", self._snap_cores_automaticas_global)
        )
        self._opacidade_imagens_global = max(
            0.0,
            min(float(cfg.get("opacidade_imagens_global", self._opacidade_imagens_global)), 1.0),
        )
        self._mostrar_cor_tecidos_global = bool(cfg.get("mostrar_cor_tecidos_global", self._mostrar_cor_tecidos_global))
        self._mostrar_cor_tecidos_menu_global = bool(
            cfg.get("mostrar_cor_tecidos_menu_global", self._mostrar_cor_tecidos_menu_global)
        )
        self._cores_tecidos_global = self._normalizar_cores_tecidos(
            cfg.get("cores_tecidos_global", self._cores_tecidos_global)
        )
        esquemas = cfg.get("esquemas_cores_usuario")
        if isinstance(esquemas, dict):
            self._esquemas_cores_usuario = {
                str(nome): dict(valor)
                for nome, valor in esquemas.items()
                if isinstance(valor, dict)
            }
        self._tema_interface_id = self._normalizar_tema_interface(cfg.get("tema_interface", self._tema_interface_id))
        self.projeto_atual.preferencias_usuario["tema_interface"] = self._tema_interface_id
        self._estilo_desenho_atual["cor"] = self._cores_canvas_global["desenho"]
        if hasattr(self, "ribbon"):
            self._aplicar_tema_interface()
            self.ribbon.aplicar_estilo(self._estilo_desenho_atual)
        if hasattr(self, "abas_documentos"):
            self._aplicar_config_visualizacao_nos_canvas()

    def _configurar_interface(self):
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        raiz.addWidget(self._criar_topo())
        raiz.addWidget(self._criar_area_documento(), 1)
        raiz.addWidget(self._criar_barra_inferior())

        self.setStyleSheet(
            """
            QMainWindow { background: #eef2f6; }
            QWidget {
                color: #111111;
            }
            QLabel, QCheckBox, QRadioButton, QPushButton, QToolButton, QLineEdit, QComboBox, QMenu {
                color: #111111;
            }
            QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {
                background: #ffffff;
                color: #111111;
            }
            QToolTip {
                background-color: #f7f7f7;
                color: #111111;
                border: 1px solid #bfc6ce;
            }
            QTabBar::tab {
                background: #f6f7f9;
                color: #101010;
                border: 1px solid #d7dde5;
                font-size: 14px;
                font-weight: 600;
                padding: 6px 20px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0b5f9e;
                border-bottom: 2px solid #0b8dd1;
            }
            QTabBar::tab:hover { background: #ecf4fb; }
            QTabBar::tab:selected:hover {
                background: #ffffff;
                color: #0b5f9e;
                border-bottom: 2px solid #0b8dd1;
            }
            """
        )

    def _criar_topo(self) -> QWidget:
        topo = QWidget()
        layout = QVBoxLayout(topo)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.host_barra_usuario_topo = QWidget()
        self.host_barra_usuario_topo_layout = QVBoxLayout(self.host_barra_usuario_topo)
        self.host_barra_usuario_topo_layout.setContentsMargins(0, 0, 0, 0)
        self.host_barra_usuario_topo_layout.setSpacing(0)
        layout.addWidget(self.host_barra_usuario_topo)

        barra_menu = QWidget()
        sup = QHBoxLayout(barra_menu)
        sup.setContentsMargins(0, 0, 6, 0)
        sup.setSpacing(6)
        barra_menu.setFixedHeight(30)

        self.botao_arquivo = QPushButton("ARQUIVO")
        self.botao_arquivo.setCursor(Qt.PointingHandCursor)
        self.botao_arquivo.setFixedSize(88, 26)
        self.botao_arquivo.clicked.connect(self._alternar_backstage)
        self.botao_arquivo.setStyleSheet(
            "background:#0b7fb8;color:white;font-weight:400;border:1px solid #0b6fa0;"
            "font-size:13px;border-radius:0;padding:0 8px;"
        )
        sup.addWidget(self.botao_arquivo, 0, Qt.AlignLeft)

        self.ribbon = RibbonWidget(include_tabbar=False)
        self.ribbon.tabbar.setExpanding(False)
        self.ribbon.tabbar.setUsesScrollButtons(True)
        self.ribbon.tabbar.setDrawBase(False)
        self.ribbon.tabbar.currentChanged.connect(lambda _: self.backstage.hide())
        self.ribbon.tabbar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ribbon.tabbar.customContextMenuRequested.connect(self._abrir_menu_contexto_aba_ribbon)
        self.ribbon.tab_changed.connect(self._on_tab_ribbon_alterada)
        self.ribbon.adicionar_usuario.connect(self._adicionar_ferramenta_usuario)
        self.ribbon.tool_selected.connect(self._abrir_pagina_ferramenta)
        self.ribbon.estilo_changed.connect(self._atualizar_estilo_desenho)
        self._sincronizar_aba_usuario_ribbon()
        sup.addWidget(self.ribbon.tabbar, 0, Qt.AlignLeft)
        sup.addStretch(1)

        menu_btn_style = self._estilo_botao_menu_topo()
        menu_popup_style = self._estilo_menu_popup_topo()

        self.btn_visao = QToolButton()
        self.btn_visao.setText("VISÃO")
        self.btn_visao.setPopupMode(QToolButton.InstantPopup)
        self.btn_visao.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_visao.setMinimumWidth(86)
        self.btn_visao.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_visao.setStyleSheet(menu_btn_style)
        self.menu_visao = QMenu(self)
        self.menu_visao.setStyleSheet(menu_popup_style)
        self.action_regras = QAction("Réguas", self)
        self.action_regras.setCheckable(True)
        self.action_regras.setChecked(True)
        self.action_regras.toggled.connect(self._alternar_reguas)
        self.menu_visao.addAction(self.action_regras)

        self.action_barra_mensagem = QAction("Barra de mensagem", self)
        self.action_barra_mensagem.setCheckable(True)
        self.action_barra_mensagem.setChecked(True)
        self.action_barra_mensagem.toggled.connect(self._alternar_barra_mensagem)
        self.menu_visao.addAction(self.action_barra_mensagem)

        self.action_menu_moldes = QAction("Menu de moldes", self)
        self.action_menu_moldes.setCheckable(True)
        self.action_menu_moldes.setChecked(bool(self.projeto_atual.preferencias_usuario.get("menu_moldes_visivel", False)))
        self.action_menu_moldes.toggled.connect(self._alternar_menu_moldes)
        self.menu_visao.addAction(self.action_menu_moldes)

        self.action_coordenadas = QAction("Coordenadas", self)
        self.action_coordenadas.setCheckable(True)
        self.action_coordenadas.setChecked(True)
        self.action_coordenadas.toggled.connect(self._alternar_coordenadas_canvas_atual)
        self.menu_visao.addAction(self.action_coordenadas)

        self.action_log = QAction("Mostrar mensagens na área de log", self)
        self.action_log.setCheckable(True)
        self.action_log.setChecked(False)
        self.action_log.toggled.connect(
            lambda ativo: self.lbl_status.setText("Mensagens no log ativas" if ativo else "Mensagens no log ocultas")
        )
        self.menu_visao.addAction(self.action_log)
        self.action_snap_contextual = QAction("Snap contextual (paralelo/perpendicular)", self)
        self.action_snap_contextual.setCheckable(True)
        self.action_snap_contextual.setChecked(True)
        self.action_snap_contextual.toggled.connect(self._alternar_snap_contextual)
        self.menu_visao.addAction(self.action_snap_contextual)
        menu_snap_angular = self.menu_visao.addMenu("Snap angular")
        grupo_passo = QActionGroup(self)
        grupo_passo.setExclusive(True)
        for passo in (30, 45, 60, 90):
            acao = QAction(f"{passo}°", self)
            acao.setCheckable(True)
            acao.setChecked(passo == 45)
            acao.triggered.connect(lambda marcado=False, p=float(passo): self._definir_passo_snap_angular(p) if marcado else None)
            grupo_passo.addAction(acao)
            menu_snap_angular.addAction(acao)
        menu_barra_usuarios = self.menu_visao.addMenu("Barra de usuários")
        self.action_barra_usuarios_habilitada = QAction("Exibir barra de usuários", self)
        self.action_barra_usuarios_habilitada.setCheckable(True)
        self.action_barra_usuarios_habilitada.setChecked(bool(self._barra_usuarios_habilitada))
        self.action_barra_usuarios_habilitada.toggled.connect(self._alternar_barra_usuarios_habilitada)
        menu_barra_usuarios.addAction(self.action_barra_usuarios_habilitada)
        menu_barra_usuarios.addSeparator()
        grupo_posicao_barra = QActionGroup(self)
        grupo_posicao_barra.setExclusive(True)
        self.action_barra_usuarios_topo = QAction("No topo (acima das abas)", self)
        self.action_barra_usuarios_topo.setCheckable(True)
        self.action_barra_usuarios_topo.setChecked(self._barra_usuarios_posicao == "topo")
        self.action_barra_usuarios_topo.triggered.connect(lambda marcado=False: self._definir_posicao_barra_usuarios("topo") if marcado else None)
        grupo_posicao_barra.addAction(self.action_barra_usuarios_topo)
        menu_barra_usuarios.addAction(self.action_barra_usuarios_topo)
        self.action_barra_usuarios_area = QAction("Entre botões e régua", self)
        self.action_barra_usuarios_area.setCheckable(True)
        self.action_barra_usuarios_area.setChecked(self._barra_usuarios_posicao == "area")
        self.action_barra_usuarios_area.triggered.connect(lambda marcado=False: self._definir_posicao_barra_usuarios("area") if marcado else None)
        grupo_posicao_barra.addAction(self.action_barra_usuarios_area)
        menu_barra_usuarios.addAction(self.action_barra_usuarios_area)
        self.action_barra_usuarios_lateral = QAction("Na lateral", self)
        self.action_barra_usuarios_lateral.setCheckable(True)
        self.action_barra_usuarios_lateral.setChecked(self._barra_usuarios_posicao == "lateral")
        self.action_barra_usuarios_lateral.triggered.connect(lambda marcado=False: self._definir_posicao_barra_usuarios("lateral") if marcado else None)
        grupo_posicao_barra.addAction(self.action_barra_usuarios_lateral)
        menu_barra_usuarios.addAction(self.action_barra_usuarios_lateral)
        menu_barra_usuarios.addSeparator()
        menu_estilo_lateral = menu_barra_usuarios.addMenu("Estilo lateral")
        grupo_estilo_lateral = QActionGroup(self)
        grupo_estilo_lateral.setExclusive(True)
        self.action_barra_usuarios_lateral_completa = QAction("Lateral completa (ícone + nome)", self)
        self.action_barra_usuarios_lateral_completa.setCheckable(True)
        self.action_barra_usuarios_lateral_completa.setChecked(self._barra_usuarios_modo_lateral == "completa")
        self.action_barra_usuarios_lateral_completa.triggered.connect(
            lambda marcado=False: self._definir_modo_barra_usuarios_lateral("completa") if marcado else None
        )
        grupo_estilo_lateral.addAction(self.action_barra_usuarios_lateral_completa)
        menu_estilo_lateral.addAction(self.action_barra_usuarios_lateral_completa)
        self.action_barra_usuarios_lateral_icones = QAction("Lateral básica (somente ícones)", self)
        self.action_barra_usuarios_lateral_icones.setCheckable(True)
        self.action_barra_usuarios_lateral_icones.setChecked(self._barra_usuarios_modo_lateral == "icones")
        self.action_barra_usuarios_lateral_icones.triggered.connect(
            lambda marcado=False: self._definir_modo_barra_usuarios_lateral("icones") if marcado else None
        )
        grupo_estilo_lateral.addAction(self.action_barra_usuarios_lateral_icones)
        menu_estilo_lateral.addAction(self.action_barra_usuarios_lateral_icones)
        self.btn_visao.setMenu(self.menu_visao)
        sup.addWidget(self.btn_visao)

        self.btn_opcoes = QToolButton()
        self.btn_opcoes.setText("OPÇÕES")
        self.btn_opcoes.setPopupMode(QToolButton.InstantPopup)
        self.btn_opcoes.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_opcoes.setMinimumWidth(86)
        self.btn_opcoes.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_opcoes.setStyleSheet(menu_btn_style)
        self.menu_opcoes = QMenu(self)
        self.menu_opcoes.setStyleSheet(menu_popup_style)
        self.menu_opcoes.addAction("Preferências", lambda: self.lbl_status.setText("Preferências (em breve)"))
        self._criar_submenu_temas_interface(self.menu_opcoes)
        self.menu_opcoes.addAction("Atalhos", lambda: self.lbl_status.setText("Atalhos (em breve)"))
        self.btn_opcoes.setMenu(self.menu_opcoes)
        sup.addWidget(self.btn_opcoes)

        self.btn_janelas = QToolButton()
        self.btn_janelas.setText("JANELAS")
        self.btn_janelas.setPopupMode(QToolButton.InstantPopup)
        self.btn_janelas.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_janelas.setMinimumWidth(92)
        self.btn_janelas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_janelas.setStyleSheet(menu_btn_style)
        self.menu_janelas = QMenu(self)
        self.menu_janelas.setStyleSheet(menu_popup_style)
        self.menu_janelas.addAction("Organizar janelas", lambda: self.lbl_status.setText("Organização de janelas (em breve)"))
        self.menu_janelas.addAction("Resetar layout", lambda: self.lbl_status.setText("Reset de layout (em breve)"))
        self.btn_janelas.setMenu(self.menu_janelas)
        sup.addWidget(self.btn_janelas)

        for texto, dica in [("?", "Ajuda"), ("i", "Sobre")]:
            ic_btn = QPushButton(texto)
            ic_btn.setFixedSize(18, 18)
            ic_btn.setStyleSheet(
                "QPushButton { border:1px solid #7f858c; border-radius:9px; color:#4f565f; background:#f2f2f2; font-weight:700; }"
                "QPushButton:hover { background:#ffffff; }"
            )
            ic_btn.clicked.connect(lambda _=False, t=dica: self.lbl_status.setText(f"{t} (em breve)"))
            sup.addWidget(ic_btn)
        layout.addWidget(barra_menu)
        self.barra_superior = barra_menu
        layout.addWidget(self.ribbon)

        self.backstage = BackstageArquivoPanel(self)
        self._aplicar_estilo_hover_backstage_arquivo()
        self.backstage.botoes["Novo"].clicked.connect(self._novo_projeto)
        self.backstage.botoes["Abrir"].clicked.connect(self._abrir_projeto)
        self.backstage.botoes["Salvar"].clicked.connect(self._acao_salvar_pelo_backstage)
        self.backstage.botoes["Salvar como"].clicked.connect(self._salvar_projeto_como)
        if "Recuperar perdidos" in self.backstage.botoes:
            self.backstage.botoes["Recuperar perdidos"].clicked.connect(self._abrir_recuperar_perdidos)
        if "Modelo ▸" in self.backstage.botoes:
            self.backstage.botoes["Modelo ▸"].clicked.connect(self._abrir_menu_modelo)
        self.backstage.botoes["Importar ▸"].clicked.connect(self._abrir_menu_importar)
        if "Exportar ▸" in self.backstage.botoes:
            self.backstage.botoes["Exportar ▸"].clicked.connect(self._abrir_menu_exportar)
        self.backstage.botoes["Configurações ▸"].clicked.connect(self._abrir_menu_configuracoes)
        if "Ajuda ▸" in self.backstage.botoes:
            self.backstage.botoes["Ajuda ▸"].clicked.connect(self._abrir_menu_ajuda)
        self.backstage.submenu_hover.connect(self._abrir_submenu_backstage_hover)
        self.backstage.submenu_leave.connect(self._fechar_submenu_backstage_hover)
        self._instalar_hover_backstage_arquivo()
        if "Plotar" in self.backstage.botoes:
            self.backstage.botoes["Plotar"].clicked.connect(self._abrir_dialogo_plotagem)
        if "Imprimir" in self.backstage.botoes:
            self.backstage.botoes["Imprimir"].clicked.connect(self._abrir_dialogo_impressao)
        self.backstage.arquivo_recente_clicado.connect(self._abrir_projeto_em_caminho)

        return topo

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if not hasattr(self, "barra_superior") or not hasattr(self, "ribbon"):
            return
        y = self._topo_backstage()
        altura_disponivel = max(240, self.height() - y - 40)
        self.backstage.setFixedHeight(min(520, altura_disponivel))
        self.backstage.move(0, y)
        area = None
        if hasattr(self, "abas_documentos") and self.abas_documentos.count() > 0:
            area = self._area_documento_atual()
        if isinstance(area, AreaDocumentoWidget):
            area._on_zoom_changed(area.canvas.zoom)
            area.canvas.sincronizar_paineis_auxiliares()

    def _agendar_reencaixe_janela_canvas(self):
        QTimer.singleShot(0, self._reencaixar_janela_canvas)
        QTimer.singleShot(80, self._reencaixar_janela_canvas)
        QTimer.singleShot(250, self._reencaixar_janela_canvas)

    def _reencaixar_janela_canvas(self):
        central = self.centralWidget()
        if central is not None:
            central.updateGeometry()
            layout = central.layout()
            if layout is not None:
                layout.activate()
        area = self._area_documento_atual() if self.abas_documentos.count() > 0 else None
        if isinstance(area, AreaDocumentoWidget):
            self.abas_documentos.setMinimumSize(0, 0)
            area.setMinimumSize(0, 0)
            area.canvas.setMinimumSize(0, 0)
            area.updateGeometry()
            area._on_zoom_changed(area.canvas.zoom)
            area.canvas.sincronizar_paineis_auxiliares()
            area.canvas.update()
        self._atualizar_label_escala()

    def _alternar_backstage(self):
        self.backstage.setVisible(not self.backstage.isVisible())
        if self.backstage.isVisible():
            self.backstage.raise_()
            self._instalar_hover_backstage_arquivo()
            self._timer_vigiar_submenu_backstage.start()
            QTimer.singleShot(0, self._processar_hover_backstage_global)
        else:
            self._fechar_submenu_backstage_hover(forcar=True)
            self._timer_vigiar_submenu_backstage.stop()

    def mousePressEvent(self, event):  # noqa: N802
        super().mousePressEvent(event)
        if self.backstage.isVisible() and event.position().x() > self.backstage.width():
            self._fechar_submenu_backstage_hover(forcar=True)
            self.backstage.hide()
            self._timer_vigiar_submenu_backstage.stop()

    def eventFilter(self, watched, event):  # noqa: N802
        tipo_evento = event.type()

        if (
            tipo_evento == QEvent.MouseButtonPress
            and hasattr(event, "globalPosition")
            and self._alertar_propriedades_aberta_se_clique_fora(event.globalPosition().toPoint())
        ):
            return super().eventFilter(watched, event)

        if (
            self._pendente_centralizar_indicado
            and tipo_evento == QEvent.MouseButtonPress
            and hasattr(watched, "_indices_elementos_em_ponto")
            and hasattr(event, "button")
            and event.button() == Qt.LeftButton
        ):
            pos = watched._ponto_com_snap(event.position())
            indices = watched._indices_elementos_em_ponto(pos)
            if indices:
                self._centralizar_molde_ou_elemento_indicado(idx_indicado=indices[0])
            else:
                self.lbl_status.setText("Nenhum molde/elemento indicado no clique.")
            self._pendente_centralizar_indicado = False
            event.accept()
            return True

        if (
            hasattr(self, "backstage")
            and self.backstage.isVisible()
            and tipo_evento in (QEvent.Enter, QEvent.MouseMove, QEvent.Leave)
        ):
            self._processar_hover_backstage_global()

        if isinstance(watched, QMenu) and getattr(watched, "_menu_hover_backstage", False):
            if tipo_evento in (QEvent.Enter, QEvent.MouseMove):
                self._cancelar_fechamento_submenu_backstage()
            elif tipo_evento == QEvent.Leave:
                self._cancelar_fechamento_submenu_backstage()
            elif tipo_evento in (QEvent.Hide, QEvent.Close):
                self._limpar_menu_backstage_hover_se_necessario(watched)

        if getattr(watched, "_backstage_hover_monitor", False):
            if tipo_evento in (QEvent.Enter, QEvent.MouseMove):
                texto = getattr(watched, "_backstage_item_texto", None)
                if texto and self._item_backstage_tem_submenu(texto):
                    self._abrir_submenu_backstage_hover(texto)
                elif getattr(self, "_menu_backstage_hover_aberto", None) is not None:
                    self._cancelar_fechamento_submenu_backstage()
            elif tipo_evento == QEvent.Leave and getattr(self, "_menu_backstage_hover_aberto", None) is not None:
                self._cancelar_fechamento_submenu_backstage()

        if (
            hasattr(self, "backstage")
            and self.backstage.isVisible()
            and tipo_evento == QEvent.MouseButtonPress
            and hasattr(event, "globalPosition")
        ):
            pos = event.globalPosition().toPoint()
            backstage_topo = self.backstage.mapToGlobal(QPoint(0, 0))
            backstage_rect = self.backstage.rect().translated(backstage_topo)
            botao_topo = self.botao_arquivo.mapToGlobal(QPoint(0, 0))
            botao_rect = self.botao_arquivo.rect().translated(botao_topo)
            if not backstage_rect.contains(pos) and not botao_rect.contains(pos):
                self._fechar_submenu_backstage_hover(forcar=True)
                self.backstage.hide()
        if isinstance(watched, QDialog) and self._eh_caixa_auxiliar_ferramenta(watched) and tipo_evento == QEvent.Move:
            programatica = getattr(watched, "_guimma_ultima_posicao_programatica", None)
            if not isinstance(programatica, QPoint) or watched.pos() != programatica:
                watched._guimma_posicao_movida_usuario = True  # type: ignore[attr-defined]

        if isinstance(watched, QDialog) and tipo_evento in (QEvent.Close, QEvent.Hide):
            self._garantir_selecionar_apos_fechar_janela()
        return super().eventFilter(watched, event)

    def _eh_caixa_auxiliar_ferramenta(self, widget: QDialog) -> bool:
        if widget is getattr(self, "_janela_aux_curva", None):
            return True
        if widget is getattr(self, "_janela_aux_retangulo", None):
            return True
        return widget in getattr(self, "_janelas_aux_instrucao", {}).values()

    def _alertar_propriedades_aberta_se_clique_fora(self, pos_global: QPoint) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        alertou = False
        for widget in app.topLevelWidgets():
            if widget is self or widget.objectName() != "PropriedadesMoldesDialog" or not widget.isVisible():
                continue
            if widget.geometry().contains(pos_global):
                continue
            try:
                if hasattr(widget, "alertar_atencao"):
                    widget.alertar_atencao()
                else:
                    QApplication.beep()
                    QApplication.alert(widget, 0)
                    widget.raise_()
                    widget.activateWindow()
                alertou = True
            except Exception:
                pass
        return alertou

    def _garantir_selecionar_apos_fechar_janela(self):
        def _ativar():
            if getattr(self, "_ferramenta_ativa_id", "selecionar") != "selecionar":
                self._ativar_ferramenta_global("selecionar")
        QTimer.singleShot(0, _ativar)

    def _topo_backstage(self) -> int:
        return self.barra_superior.height()

    def _abrir_menu_contexto_aba_ribbon(self, pos: QPoint):
        indice = self.ribbon.tabbar.tabAt(pos)
        tab_id = self.ribbon.tab_id_at(indice) if indice >= 0 else None
        if not tab_id:
            return
        menu = QMenu(self)
        submenu_usuarios = menu.addMenu("Usuários")
        acao_add_todas = submenu_usuarios.addAction("Adicionar todas as ferramentas para usuário")
        acao = menu.exec(self.ribbon.tabbar.mapToGlobal(pos))
        if acao == acao_add_todas:
            self._adicionar_todas_ferramentas_da_aba_id(tab_id)

    def _log_debug_propriedades(self, mensagem: str):
        if not (
            bool(getattr(self, "_debug_propriedades", False))
            or os.environ.get("GUIMMA_PROPRIEDADES_DEBUG") == "1"
        ):
            return
        try:
            caminho = Path.home() / "guimma_propriedades_debug.log"
            linha = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [janela_principal] {mensagem}"
            print(linha)
            with caminho.open("a", encoding="utf-8") as arq:
                arq.write(linha + "\n")
        except Exception as exc:
            print(f"[janela_principal][log-falhou] {type(exc).__name__}: {exc}")

    def _abrir_propriedades_diretamente(self):
        self._log_debug_propriedades("Atalho/abertura direta de propriedades acionado.")
        try:
            self._abrir_pagina_ferramenta("propriedades")
        except Exception as exc:
            self._log_debug_propriedades(f"Falha na abertura direta de propriedades: {type(exc).__name__}: {exc}")
            raise

    def _abrir_pagina_ferramenta(self, tool_id: str):
        self._log_debug_propriedades(f"_abrir_pagina_ferramenta iniciado com tool_id={tool_id!r}")
        acoes_globais = {
            "imprimir",
            "impressao",
            "print",
            "plotar",
            "plotagem",
            "plot",
            "desfazer",
            "refazer",
            "salvar",
            "salvar_como",
            "cores",
            "unidade_medidas",
        }
        if tool_id in acoes_globais and self._executar_acao_edicao_ribbon(tool_id):
            self._log_debug_propriedades(f"tool_id={tool_id!r} tratado como ação de edição ribbon.")
            return
        tool_def = self.ribbon.tool_def(tool_id)
        self._log_debug_propriedades(f"tool_def encontrado={tool_def is not None}")
        if not tool_def:
            self.lbl_status.setText(f"Ferramenta não encontrada: {tool_id}")
            self._log_debug_propriedades(f"Ferramenta não encontrada para tool_id={tool_id!r}")
            return
        if not self._garantir_canvas_para_ferramenta(tool_id):
            return
        if self._executar_acao_edicao_ribbon(tool_id):
            self._log_debug_propriedades(f"tool_id={tool_id!r} tratado como acao de edicao ribbon.")
            return
        if self._abrir_janela_auxiliar_ferramenta(tool_id, tool_def.title):
            self._log_debug_propriedades(f"tool_id={tool_id!r} abriu janela auxiliar e retornou.")
            return

        area = self._area_documento_atual()
        if area is not None:
            try:
                self._ativar_ferramenta_global(tool_id)
                if tool_id != "selecionar":
                    self.lbl_status.setText(f"{tool_def.title} ativo.")
                return
            except Exception as exc:
                self.lbl_status.setText(f"Falha ao abrir {tool_def.title}: {exc}")
                self._log_debug_propriedades(f"Falha ao ativar {tool_def.title!r}: {type(exc).__name__}: {exc}")
                try:
                    caixa = QMessageBox(self)
                    self._estilizar_message_box(caixa)
                    caixa.setWindowTitle("Erro ao abrir ferramenta")
                    caixa.setIcon(QMessageBox.Critical)
                    caixa.setText(f"{type(exc).__name__}: {exc}")
                    caixa.setStandardButtons(QMessageBox.Ok)
                    self._traduzir_botoes_padrao_message_box(caixa)
                    caixa.exec()
                except Exception as exc2:
                    self._log_debug_propriedades(f"Falha ao mostrar QMessageBox: {type(exc2).__name__}: {exc2}")
                return

        module_name = tool_def.module.replace("/", ".").replace(".py", "")
        self._log_debug_propriedades(
            f"Carregando módulo={module_name!r}, classe={tool_def.class_name!r}, título={tool_def.title!r}"
        )
        try:
            module = import_module(module_name)
            self._log_debug_propriedades(f"Módulo importado com sucesso: {module_name!r}")
            tool_cls = getattr(module, tool_def.class_name)
            self._log_debug_propriedades(f"Classe localizada: {tool_cls}")
            tool = tool_cls()
            self._log_debug_propriedades(f"Instância criada: {tool}")

            area = self._area_documento_atual()
            self._log_debug_propriedades(
                f"Área atual existe={area is not None}; abas={self.abas_documentos.count() if hasattr(self, 'abas_documentos') else '??'}; currentIndex={self.abas_documentos.currentIndex() if hasattr(self, 'abas_documentos') else '??'}"
            )
            canvas = getattr(area, 'canvas', None) if area is not None else None
            self._log_debug_propriedades(f"Canvas atual existe={canvas is not None}")

            abriu = False
            if canvas is not None and hasattr(tool, 'on_activate'):
                self._log_debug_propriedades(f"Chamando on_activate(canvas) para tool_id={tool_id!r}")
                try:
                    resultado = tool.on_activate(canvas)
                    abriu = True
                    self._log_debug_propriedades(f"on_activate executado com sucesso. retorno={resultado!r}")
                except Exception as exc:
                    self._log_debug_propriedades(f"Erro em on_activate: {type(exc).__name__}: {exc}")
                    raise
            else:
                self._log_debug_propriedades(
                    f"on_activate não será usado. canvas_existe={canvas is not None}, tem_on_activate={hasattr(tool, 'on_activate')}"
                )

            self._ativar_ferramenta_global(tool_id)
            self._log_debug_propriedades(f"Ferramenta global ativada: {tool_id!r}")

            if not abriu:
                self._log_debug_propriedades(f"Chamando ativar() para tool_id={tool_id!r}")
                msg = tool.ativar()
                self.lbl_status.setText(msg)
                self._log_debug_propriedades(f"ativar() retornou: {msg!r}")
            else:
                self.lbl_status.setText(f"{tool_def.title} aberta.")
                self._log_debug_propriedades(f"Janela/ferramenta {tool_def.title!r} aberta via on_activate.")
        except Exception as exc:  # pragma: no cover - fallback de carregamento
            self.lbl_status.setText(f"Falha ao abrir {tool_def.title}: {exc}")
            self._log_debug_propriedades(f"Falha ao abrir {tool_def.title!r}: {type(exc).__name__}: {exc}")
            try:
                caixa = QMessageBox(self)
                self._estilizar_message_box(caixa)
                caixa.setWindowTitle("Erro ao abrir ferramenta")
                caixa.setIcon(QMessageBox.Critical)
                caixa.setText(f"{type(exc).__name__}: {exc}")
                caixa.setStandardButtons(QMessageBox.Ok)
                self._traduzir_botoes_padrao_message_box(caixa)
                caixa.exec()
            except Exception as exc2:
                self._log_debug_propriedades(f"Falha ao mostrar QMessageBox: {type(exc2).__name__}: {exc2}")

    def _garantir_canvas_para_ferramenta(self, tool_id: str) -> bool:
        if not hasattr(self, "abas_documentos"):
            return False
        if self._area_documento_atual() is not None:
            return True
        self._adicionar_aba_documento()
        area = self._area_documento_atual()
        if area is None:
            self.lbl_status.setText("Nao foi possivel criar um canvas novo.")
            self._log_debug_propriedades(f"Falha ao criar canvas automatico para tool_id={tool_id!r}.")
            return False
        self.lbl_status.setText("Canvas novo criado.")
        self._log_debug_propriedades(f"Canvas automatico criado para tool_id={tool_id!r}.")
        return True

    def _executar_acao_edicao_ribbon(self, tool_id: str) -> bool:
        if tool_id in {"imprimir", "impressao", "print"}:
            self._abrir_dialogo_impressao()
            return True
        if tool_id in {"plotar", "plotagem", "plot"}:
            self._abrir_dialogo_plotagem()
            return True
        if tool_id == "desfazer":
            self._desfazer_canvas_atual()
            return True
        if tool_id == "refazer":
            self._refazer_canvas_atual()
            return True
        if tool_id == "salvar":
            self._acao_salvar_pelo_backstage()
            return True
        if tool_id == "salvar_como":
            self._salvar_projeto_como()
            return True
        if tool_id == "cores":
            self._abrir_dialogo_cores()
            return True
        if tool_id == "unidade_medidas":
            self._abrir_dialogo_unidade_medida()
            return True

        area = self._area_documento_atual()
        if not area:
            return False
        if tool_id == "copiar":
            self._copiar_canvas_atual()
            self.lbl_status.setText("Copiado")
            return True
        if tool_id == "colar":
            self._colar_canvas_atual()
            self.lbl_status.setText("Colado")
            return True
        acoes_selecao = {
            "selecionar_tudo": (area.canvas.selecionar_tudo, "Selecionado tudo: {total} elemento(s)."),
            "selecionar_moldes": (area.canvas.selecionar_moldes, "Selecionado(s) {total} molde(s)."),
            "inverter_selecao": (area.canvas.inverter_selecao, "Seleção invertida: {total} elemento(s) selecionado(s)."),
            "inverter_moldes": (
                area.canvas.inverter_selecao_moldes,
                "Seleção de moldes invertida: {total} molde(s) selecionado(s).",
            ),
        }
        acao_selecao = acoes_selecao.get(tool_id)
        if acao_selecao:
            func, mensagem = acao_selecao
            func()
            self._ativar_ferramenta_global("selecionar")
            total = len(getattr(area.canvas, "_selecionados", set()) or set())
            self.lbl_status.setText(mensagem.format(total=total))
            return True
        acoes = {
            "recortar": (area.canvas.recortar, "Recortado"),
            "excluir": (area.canvas.apagar_selecionados, "Excluído"),
        }
        acao = acoes.get(tool_id)
        if acao:
            func, mensagem = acao
            func()
            self.lbl_status.setText(mensagem)
            return True
        return False

    def _abrir_janela_auxiliar_ferramenta(self, tool_id: str, titulo: str) -> bool:
        if tool_id == "curva":
            return self._abrir_janela_auxiliar_curva(titulo)
        if tool_id == "retangulo":
            return self._abrir_janela_auxiliar_retangulo(titulo)
        instrucoes = {
            "estender_reta": (
                "Estender reta",
                "1) Clique no endpoint da reta.\n"
                "2) Clique no novo destino para estender.\n"
                "Dica: use Snap ativo para maior precisão.",
            ),
            "estender_ate_elemento": (
                "Estender até elemento",
                "1) Clique no endpoint da reta de origem.\n"
                "2) Clique no elemento alvo.\n"
                "A reta será estendida até a interseção.",
            ),
            "estender_duas_retas": (
                "Estender duas retas",
                "1) Clique na primeira reta.\n"
                "2) Clique na segunda reta.\n"
                "As duas serão estendidas para encontrar a interseção.",
            ),
            "dividir_curva": (
                "Dividir curva",
                "Clique sobre o segmento para inserir um novo ponto de divisão no trecho.",
            ),
        }
        if tool_id not in instrucoes:
            return False
        janela = self._janelas_aux_instrucao.get(tool_id)
        texto_titulo, texto_instrucao = instrucoes[tool_id]
        if janela is None:
            janela = QDialog(self)
            janela.setWindowTitle(f"{titulo} - Auxiliar")
            janela.setModal(False)
            janela.setWindowFlag(Qt.Tool, True)
            janela.setMinimumWidth(380)
            janela.setStyleSheet(
                "QDialog { background:#e6e6e6; border:1px solid #9da3aa; } QLabel { color:#2b2b2b; }"
            )
            layout = QVBoxLayout(janela)
            lbl_titulo = QLabel(f"<b>{texto_titulo}</b>")
            lbl_titulo.setStyleSheet("font-size: 13px;")
            layout.addWidget(lbl_titulo)
            lbl_instrucao = QLabel(texto_instrucao)
            lbl_instrucao.setWordWrap(True)
            lbl_instrucao.setStyleSheet("font-size: 12px; color:#2b2b2b;")
            layout.addWidget(lbl_instrucao)
            janela._lbl_titulo = lbl_titulo  # type: ignore[attr-defined]
            janela._lbl_instrucao = lbl_instrucao  # type: ignore[attr-defined]
            self._janelas_aux_instrucao[tool_id] = janela
        else:
            janela.setWindowTitle(f"{titulo} - Auxiliar")
            if hasattr(janela, "_lbl_titulo"):
                janela._lbl_titulo.setText(f"<b>{texto_titulo}</b>")  # type: ignore[attr-defined]
            if hasattr(janela, "_lbl_instrucao"):
                janela._lbl_instrucao.setText(texto_instrucao)  # type: ignore[attr-defined]

        self._restaurar_posicao_caixa_aux(janela, tool_id)
        janela.show()
        janela.raise_()
        janela.activateWindow()
        self._ativar_ferramenta_global(tool_id)
        self.lbl_status.setText(f"{titulo} ativo.")
        return True

    def _abrir_janela_auxiliar_retangulo(self, titulo: str) -> bool:
        area = self._area_documento_atual()
        if not area:
            return False
        if self._janela_aux_retangulo is None:
            janela = QDialog(self)
            janela.setWindowTitle("Definir retângulos")
            janela.setModal(False)
            if sys.platform == "darwin":
                janela.setWindowFlag(Qt.Tool, False)
                janela.setWindowFlag(Qt.Window, True)
            else:
                janela.setWindowFlag(Qt.Tool, True)
            janela.setMinimumWidth(260)
            janela.setStyleSheet(
                "QDialog { background:#f0f0f0; border:1px solid #bfc7cf; }"
                "QLabel { color:#1f1f1f; }"
                "QCheckBox { color:#1f1f1f; font-size:12px; }"
            )
            layout = QVBoxLayout(janela)
            layout.addWidget(QLabel("<b>Definir retângulos</b>"))
            chk_criar_molde = QCheckBox("Criar molde")
            chk_criar_molde.setTristate(False)
            chk_criar_molde.setEnabled(True)
            chk_criar_molde.setChecked(self._retangulo_criar_molde)
            chk_criar_molde.toggled.connect(self._atualizar_config_retangulo)
            layout.addWidget(chk_criar_molde)
            layout.addWidget(QLabel("Se marcado, o retângulo já vira molde com fio padrão em 0°."), 0)
            self._janela_aux_retangulo = janela
            self._chk_aux_retangulo_criar_molde = chk_criar_molde
        janela = self._janela_aux_retangulo
        if self._chk_aux_retangulo_criar_molde:
            self._chk_aux_retangulo_criar_molde.setChecked(self._retangulo_criar_molde)
        self._restaurar_posicao_caixa_aux(janela, "retangulo")
        janela.show()
        janela.raise_()
        janela.activateWindow()
        self._ativar_ferramenta_global("retangulo")
        modo = "molde (fio 0°)" if self._retangulo_criar_molde else "desenho"
        self.lbl_status.setText(f"{titulo} ativo no modo: {modo}.")
        return True

    def _atualizar_config_retangulo(self, criar_molde: bool):
        self._retangulo_criar_molde = bool(criar_molde)
        self.projeto_atual.preferencias_usuario["retangulo_criar_molde"] = self._retangulo_criar_molde
        self._salvar_preferencias_app()
        area = self._area_documento_atual()
        if area:
            area.canvas.definir_config_retangulo(self._retangulo_criar_molde)

    def _abrir_janela_auxiliar_curva(self, titulo: str) -> bool:
        area = self._area_documento_atual()
        if not area:
            return False

        if self._janela_aux_curva is None:
            janela = QDialog(self)
            janela.setWindowTitle(titulo)
            janela.setModal(False)
            janela.setMinimumWidth(380)
            janela.setWindowFlag(Qt.Tool, True)
            janela.setStyleSheet(
                "QDialog { background:#e6e6e6; border:1px solid #9da3aa; } QLabel { color:#2b2b2b; }"
                "QRadioButton { color:#2b2b2b; padding:2px; }"
            )

            layout = QVBoxLayout(janela)
            layout.addWidget(QLabel("<b>(cm) Curva</b>"))

            rb_np = QRadioButton("NP - Pontos indefinidos")
            rb_suave = QRadioButton("Curva suave")
            rb_3p = QRadioButton("Curva por 3 pontos")
            rb_2p = QRadioButton("Curva por 2 pontos")
            rb_espelhada = QRadioButton("Curvas espelhadas")

            layout.addWidget(rb_np)
            layout.addWidget(rb_suave)
            layout.addWidget(rb_3p)
            layout.addWidget(rb_2p)
            layout.addWidget(rb_espelhada)

            rb_np.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("np") if marcado else None)
            rb_suave.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("suave") if marcado else None)
            rb_3p.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("3p") if marcado else None)
            rb_2p.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("2p") if marcado else None)
            rb_espelhada.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("espelhada") if marcado else None)

            self._rb_curva_np = rb_np
            self._rb_curva_suave = rb_suave
            self._rb_curva_3p = rb_3p
            self._rb_curva_2p = rb_2p
            self._rb_curva_espelhada = rb_espelhada
            self._janela_aux_curva = janela
        else:
            janela = self._janela_aux_curva
            janela.setWindowTitle(titulo)

        if hasattr(self, "_rb_curva_np"):
            self._rb_curva_np.setChecked(True)

        self._restaurar_posicao_caixa_aux(janela, "curva")
        area.canvas.set_modo_curva("np")
        self._ativar_ferramenta_global("curva")
        janela.show()
        janela.raise_()
        janela.activateWindow()
        self.lbl_status.setText(f"{titulo} ativo (pontos indefinidos).")
        return True

    def _definir_modo_curva_area_atual(self, modo: str):
        area = self._area_documento_atual()
        if area:
            area.canvas.set_modo_curva(modo)

        if hasattr(self, "lbl_status") and self.lbl_status is not None:
            if modo == "np":
                self.lbl_status.setText("Curva ativa (pontos indefinidos).")
            elif modo == "suave":
                self.lbl_status.setText("Curva ativa (curva suave).")
            elif modo == "3p":
                self.lbl_status.setText("Curva ativa (3 pontos).")
            else:
                self.lbl_status.setText("Curva ativa (2 pontos).")

    def _restaurar_posicao_caixa_aux(self, janela: QDialog, chave: str):
        area = self._area_documento_atual()
        if not area:
            return
        canvas = area.canvas
        janela.adjustSize()
        gx = canvas.mapToGlobal(canvas.rect().topLeft()).x()
        gy = canvas.mapToGlobal(canvas.rect().topLeft()).y()
        min_x = gx + 8
        min_y = gy + 8
        max_x = gx + max(8, canvas.width() - janela.width() - 8)
        max_y = gy + max(8, canvas.height() - janela.height() - 8)

        pos_padrao = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(janela.width(), janela.height(), abaixo_coordenadas=True)
            pos_padrao = canvas.mapToGlobal(pos_local)
        else:
            x = gx + max(8, canvas.width() - janela.width() - 18)
            y = gy + 16
            pos_padrao = QPoint(max(min_x, min(x, max_x)), max(min_y, min(y, max_y)))

        destino = QPoint(
            max(min_x, min(pos_padrao.x(), max_x)),
            max(min_y, min(pos_padrao.y(), max_y)),
        )
        janela._guimma_ultima_posicao_programatica = QPoint(destino)  # type: ignore[attr-defined]
        janela.move(destino)
        janela._guimma_posicao_inicial_aplicada = True  # type: ignore[attr-defined]
        janela._guimma_posicao_movida_usuario = False  # type: ignore[attr-defined]

    def _memorizar_posicao_caixa_aux(self, janela: QDialog, chave: str):
        self._posicoes_caixas_aux[chave] = (janela.x(), janela.y())
        self.projeto_atual.preferencias_usuario["posicoes_caixas_aux"] = dict(self._posicoes_caixas_aux)
        self._salvar_preferencias_app()

    # ========== FUNÇÕES CORRIGIDAS PARA HOVER DO BACKSTAGE ==========

    def _estilo_botao_backstage_arquivo(self, ativo: bool = False) -> str:
        """Retorna o estilo do botão da coluna ARQUIVO.

        O hover é controlado manualmente para não ficar travado quando um QMenu
        abre por cima da janela e captura os eventos do mouse.
        """
        tema = self._tema_interface()
        fundo = tema["hover"] if ativo else "transparent"
        return f"""
            QPushButton {{
                background: {fundo};
                color: {tema['texto']};
                border: none;
                border-radius: 0px;
                text-align: left;
                padding: 0px 8px 0px 8px;
                font-size: 12px;
                font-weight: 400;
            }}
            QPushButton:pressed {{
                background: {tema['selecionado']};
                color: {tema['texto']};
            }}
            QPushButton:disabled {{
                background: transparent;
                color: {tema['texto_suave']};
            }}
        """

    def _definir_hover_botao_backstage(self, botao: QWidget | None, ativo: bool):
        """Aplica ou remove o destaque visual de um botão do backstage."""
        if not self._qt_widget_vivo(botao):
            return
        try:
            estado_atual = bool(getattr(botao, "_backstage_hover_ativo", False))
            if estado_atual == bool(ativo):
                return
            botao._backstage_hover_ativo = bool(ativo)  # type: ignore[attr-defined]
            botao.setStyleSheet(self._estilo_botao_backstage_arquivo(bool(ativo)))
        except RuntimeError:
            return
        except Exception:
            return

    def _limpar_hover_botoes_backstage(self, manter: QWidget | None = None):
        """Remove hover manual de todos os botões, exceto o informado."""
        if not hasattr(self, "backstage") or self.backstage is None:
            return
        for botao in getattr(self.backstage, "botoes", {}).values():
            if botao is manter:
                self._definir_hover_botao_backstage(botao, True)
            else:
                self._definir_hover_botao_backstage(botao, False)

    def _aplicar_estilo_hover_backstage_arquivo(self):
        """Aplica a cor de hover na coluna ARQUIVO do backstage."""
        if not hasattr(self, "backstage") or self.backstage is None:
            return

        for texto, botao in getattr(self.backstage, "botoes", {}).items():
            try:
                botao.setCursor(Qt.PointingHandCursor)
                botao.setMouseTracking(True)
                botao._backstage_item_texto = texto  # type: ignore[attr-defined]
                botao._backstage_hover_monitor = True  # type: ignore[attr-defined]
                botao._backstage_hover_ativo = False  # type: ignore[attr-defined]
                botao.setStyleSheet(self._estilo_botao_backstage_arquivo(False))
            except RuntimeError:
                continue
            except Exception:
                continue

    def _instalar_hover_backstage_arquivo(self):
        """Configura monitoramento de hover nos botões do backstage."""
        if not hasattr(self, "backstage") or self.backstage is None:
            return
        self.backstage.setMouseTracking(True)
        for texto, botao in getattr(self.backstage, "botoes", {}).items():
            try:
                botao.setMouseTracking(True)
                botao._backstage_item_texto = texto  # type: ignore[attr-defined]
                botao._backstage_hover_monitor = True  # type: ignore[attr-defined]
                try:
                    botao.removeEventFilter(self)
                except Exception:
                    pass
                botao.installEventFilter(self)
            except RuntimeError:
                continue
            except Exception:
                continue

    def _processar_hover_backstage_global(self):
        """Verifica posição do cursor e abre/fecha submenus automaticamente."""
        if not hasattr(self, "backstage") or not self._qt_widget_visivel(self.backstage):
            self._limpar_hover_botoes_backstage()
            return

        self._limpar_referencias_menus_backstage_invalidos()
        cursor_pos = QCursor.pos()
        botao_texto, botao = self._botao_backstage_sob_cursor(cursor_pos)
        menu_atual = getattr(self, "_menu_backstage_hover_aberto", None)
        origem_atual = getattr(self, "_menu_backstage_hover_origem", None)
        botao_atual = getattr(self, "_menu_backstage_hover_botao", None)

        # Se o cursor está em um botão comum, destaque somente ele e feche submenu.
        if botao_texto and botao and not self._item_backstage_tem_submenu(botao_texto):
            self._limpar_hover_botoes_backstage(botao)
            self._cancelar_fechamento_submenu_backstage()
            return

        # Se o cursor está em um botão com submenu, abre imediatamente no hover.
        if botao_texto and botao and self._item_backstage_tem_submenu(botao_texto):
            self._limpar_hover_botoes_backstage(botao)
            if self._qt_widget_visivel(menu_atual) and botao_atual is botao and origem_atual == botao_texto:
                self._cancelar_fechamento_submenu_backstage()
                return
            self._abrir_submenu_backstage_hover(botao_texto, botao)
            return

        # Cursor fora dos botões: se está dentro do menu/corredor, mantém só o botão de origem destacado.
        if (
            self._cursor_sobre_algum_menu_backstage(cursor_pos)
            or self._cursor_sobre_corredor_entre_botao_e_menu(cursor_pos)
            or self._cursor_sobre_corredor_entre_menus_backstage(cursor_pos)
        ):
            self._limpar_hover_botoes_backstage(botao_atual if self._qt_widget_vivo(botao_atual) else None)
            self._cancelar_fechamento_submenu_backstage()
            return

        # Cursor saiu da área útil: remove destaque e fecha.
        self._limpar_hover_botoes_backstage()
        self._cancelar_fechamento_submenu_backstage()

    def _abrir_submenu_backstage_hover(self, item_texto: str, botao: QWidget = None):
        """Abre o submenu referente ao botão (hover)."""
        if not hasattr(self, "backstage") or not self._qt_widget_visivel(self.backstage):
            return

        self._limpar_referencias_menus_backstage_invalidos()
        menu_atual = getattr(self, "_menu_backstage_hover_aberto", None)
        if (
            self._qt_widget_visivel(menu_atual)
            and getattr(self, "_menu_backstage_hover_origem", None) == item_texto
        ):
            self._cancelar_fechamento_submenu_backstage()
            return

        self._fechar_submenu_backstage_hover(forcar=True)

        if botao is None:
            _, botao = self._botao_submenu_backstage_sob_cursor(QCursor.pos())
            if not self._qt_widget_vivo(botao):
                return

        menu = None
        if item_texto == "Modelo ▸":
            menu = self._criar_menu_modelo()
        elif item_texto == "Importar ▸":
            menu = self._criar_menu_importar()
        elif item_texto == "Exportar ▸":
            menu = self._criar_menu_exportar()
        elif item_texto == "Configurações ▸":
            menu = self._criar_menu_configuracoes()
        elif item_texto == "Ajuda ▸":
            menu = self._criar_menu_ajuda()

        if not self._qt_widget_vivo(menu):
            return

        self._preparar_menu_backstage_hover(menu, item_texto)
        self._menu_backstage_hover_aberto = menu
        self._menu_backstage_hover_origem = item_texto
        self._menu_backstage_hover_botao = botao
        self._limpar_hover_botoes_backstage(botao)

        try:
            pos = self._posicao_submenu_backstage(botao)
            menu.popup(pos)
        except RuntimeError:
            self._limpar_referencias_menus_backstage_invalidos()

    def _fechar_submenu_backstage_hover(self, _item_texto: str = None, forcar: bool = False):
        """Fecha o submenu atualmente aberto sem acessar QMenu já destruído."""
        self._cancelar_fechamento_submenu_backstage()
        self._limpar_referencias_menus_backstage_invalidos()

        if not forcar and self._cursor_sobre_area_backstage_ou_menus():
            return

        for menu in list(getattr(self, "_menus_backstage_hover", [])):
            if self._qt_widget_visivel(menu):
                try:
                    menu.close()
                except RuntimeError:
                    pass
                except Exception:
                    pass

        menu = getattr(self, "_menu_backstage_hover_aberto", None)
        if self._qt_widget_visivel(menu):
            try:
                menu.close()
            except RuntimeError:
                pass
            except Exception:
                pass

        self._menu_backstage_hover_aberto = None
        self._menu_backstage_hover_origem = None
        self._menu_backstage_hover_botao = None
        self._menus_backstage_hover = []
        self._limpar_hover_botoes_backstage()

    def _cancelar_fechamento_submenu_backstage(self):
        """Cancela qualquer timer de fechamento pendente."""
        if hasattr(self, "_timer_fechar_submenu_backstage"):
            self._timer_fechar_submenu_backstage.stop()

    def _agendar_fechamento_submenu_backstage(self, atraso_ms: int = 120):
        """Agenda o fechamento do submenu após um pequeno atraso."""
        if hasattr(self, "_timer_fechar_submenu_backstage"):
            self._timer_fechar_submenu_backstage.start(max(1, atraso_ms))

    def _cursor_sobre_widget_global(self, widget: QWidget, pos: QPoint, margem: int = 2) -> bool:
        """Verifica se o cursor global está sobre o widget (com margem)."""
        if not self._qt_widget_visivel(widget):
            return False
        try:
            rect = widget.rect().translated(widget.mapToGlobal(QPoint(0, 0)))
            return rect.adjusted(-margem, -margem, margem, margem).contains(pos)
        except RuntimeError:
            return False
        except Exception:
            return False

    def _cursor_sobre_algum_menu_backstage(self, pos: QPoint) -> bool:
        """Verifica se o cursor está sobre qualquer um dos menus abertos."""
        self._limpar_referencias_menus_backstage_invalidos()
        for menu in list(getattr(self, "_menus_backstage_hover", [])):
            if self._cursor_sobre_widget_global(menu, pos, margem=18):
                return True
        return False

    def _cursor_sobre_corredor_entre_botao_e_menu(self, pos: QPoint) -> bool:
        """Verifica se o cursor está na região entre o botão e o menu aberto."""
        botao = getattr(self, "_menu_backstage_hover_botao", None)
        menu = getattr(self, "_menu_backstage_hover_aberto", None)
        if not self._qt_widget_visivel(botao) or not self._qt_widget_visivel(menu):
            return False
        try:
            rect_botao = botao.rect().translated(botao.mapToGlobal(QPoint(0, 0)))
            rect_menu = menu.rect().translated(menu.mapToGlobal(QPoint(0, 0)))
            left = min(rect_botao.right(), rect_menu.left())
            right = max(rect_botao.right(), rect_menu.left())
            top = min(rect_botao.top(), rect_menu.top())
            bottom = max(rect_botao.bottom(), rect_menu.bottom())
            connector = QRectF(left, top, max(1, right - left), max(1, bottom - top))
            return connector.contains(pos)
        except RuntimeError:
            return False
        except Exception:
            return False

    def _cursor_sobre_corredor_entre_menus_backstage(self, pos: QPoint) -> bool:
        """Mantem menu aberto ao mover do menu principal para um submenu lateral."""
        self._limpar_referencias_menus_backstage_invalidos()
        menus_visiveis: list[QMenu] = []
        for menu in list(getattr(self, "_menus_backstage_hover", [])):
            if self._qt_widget_visivel(menu):
                menus_visiveis.append(menu)
        if len(menus_visiveis) < 2:
            return False
        try:
            retangulos = [menu.rect().translated(menu.mapToGlobal(QPoint(0, 0))) for menu in menus_visiveis]
            for i, a in enumerate(retangulos):
                for b in retangulos[i + 1 :]:
                    if a.intersects(b.adjusted(-10, -10, 10, 10)):
                        continue
                    if a.right() <= b.left():
                        left = a.right()
                        right = b.left()
                    elif b.right() <= a.left():
                        left = b.right()
                        right = a.left()
                    else:
                        left = min(a.left(), b.left())
                        right = max(a.right(), b.right())
                    top = min(a.top(), b.top()) - 36
                    bottom = max(a.bottom(), b.bottom()) + 36
                    corredor = QRectF(left - 16, top, max(32, right - left + 32), max(1, bottom - top))
                    if corredor.contains(pos):
                        return True
        except RuntimeError:
            return False
        except Exception:
            return False
        return False

    def _botao_backstage_sob_cursor(self, pos: QPoint) -> tuple[str | None, QWidget | None]:
        """Retorna qualquer botão do backstage sob o cursor."""
        if not hasattr(self, "backstage") or not self._qt_widget_visivel(self.backstage):
            return None, None
        for texto, botao in getattr(self.backstage, "botoes", {}).items():
            if self._cursor_sobre_widget_global(botao, pos, margem=1):
                return texto, botao
        return None, None

    def _botao_submenu_backstage_sob_cursor(self, pos: QPoint) -> tuple[str | None, QWidget | None]:
        """Retorna o texto e o widget do botão (com submenu) sob o cursor."""
        texto, botao = self._botao_backstage_sob_cursor(pos)
        if texto and self._item_backstage_tem_submenu(texto):
            return texto, botao
        return None, None

    def _item_backstage_tem_submenu(self, texto: str) -> bool:
        """Verifica se o botão do backstage possui um submenu."""
        return texto in {"Modelo ▸", "Importar ▸", "Exportar ▸", "Configurações ▸", "Ajuda ▸"}

    def _mostrar_menu_backstage(self, menu: QMenu, botao: QWidget, origem: str, modo_hover: bool):
        """Exibe o menu (usado tanto para clique quanto hover)."""
        if modo_hover:
            self._abrir_submenu_backstage_hover(origem, botao)
        else:
            self._fechar_submenu_backstage_hover(forcar=True)
            if self._qt_widget_vivo(menu) and self._qt_widget_vivo(botao):
                try:
                    menu.exec(self._posicao_submenu_backstage(botao))
                except RuntimeError:
                    pass

    def _preparar_menu_backstage_hover(self, menu: QMenu, origem: str):
        """Prepara o menu para funcionar com hover (eventos e rastreamento)."""
        if not self._qt_widget_vivo(menu):
            return
        menu._menu_hover_backstage = True  # type: ignore[attr-defined]
        menu._origem_backstage = origem  # type: ignore[attr-defined]
        self._registrar_menus_hover_backstage(menu)
        try:
            menu.aboutToHide.connect(lambda m=menu: self._limpar_menu_backstage_hover_se_necessario(m))
        except RuntimeError:
            pass
        except Exception:
            pass
        try:
            menu.hovered.connect(lambda acao, m=menu: self._ao_hover_acao_menu_backstage(m, acao))
        except RuntimeError:
            pass
        except Exception:
            pass

    def _registrar_menus_hover_backstage(self, menu: QMenu):
        """Registra o menu e seus submenus para monitoramento de hover."""
        if not self._qt_widget_vivo(menu):
            return
        if menu not in self._menus_backstage_hover:
            self._menus_backstage_hover.append(menu)
        try:
            menu.installEventFilter(self)
            menu.setMouseTracking(True)
            for acao in menu.actions():
                sub = acao.menu()
                if sub:
                    sub.setStyleSheet(self._estilo_menu_backstage())
                    sub._menu_hover_backstage = True  # type: ignore[attr-defined]
                    try:
                        sub.aboutToShow.connect(lambda s=sub: self._registrar_menus_hover_backstage(s))
                    except RuntimeError:
                        pass
                    except Exception:
                        pass
                    self._registrar_menus_hover_backstage(sub)
        except RuntimeError:
            self._limpar_referencias_menus_backstage_invalidos()
        except Exception:
            pass

    def _ao_hover_acao_menu_backstage(self, menu: QMenu, acao):
        """Mantem menus de importacao abertos durante a navegacao por submenus."""
        if not self._qt_widget_vivo(menu):
            return
        self._cancelar_fechamento_submenu_backstage()
        try:
            sub = acao.menu() if acao is not None else None
            if sub:
                sub.setStyleSheet(self._estilo_menu_backstage())
                sub._menu_hover_backstage = True  # type: ignore[attr-defined]
                self._registrar_menus_hover_backstage(sub)
        except RuntimeError:
            self._limpar_referencias_menus_backstage_invalidos()
        except Exception:
            pass

    def _limpar_menu_backstage_hover_se_necessario(self, menu: QMenu):
        """Remove referência do menu quando ele for fechado/destruído."""
        if not self._qt_widget_vivo(menu):
            self._limpar_referencias_menus_backstage_invalidos()
            return
        try:
            if menu is getattr(self, "_menu_backstage_hover_aberto", None) and not menu.isVisible():
                self._menu_backstage_hover_aberto = None
                self._menu_backstage_hover_origem = None
                self._menu_backstage_hover_botao = None
                self._menus_backstage_hover = []
                self._limpar_hover_botoes_backstage()
        except RuntimeError:
            self._limpar_referencias_menus_backstage_invalidos()

    def _fechar_submenu_backstage_se_cursor_fora(self):
        """Fechamento agendado, verifica se cursor ainda está fora antes de fechar."""
        if not self._cursor_sobre_area_backstage_ou_menus():
            self._fechar_submenu_backstage_hover(forcar=True)

    def _cursor_sobre_area_backstage_ou_menus(self) -> bool:
        """Verifica se o cursor está sobre backstage, botões ou qualquer menu aberto."""
        pos = QCursor.pos()
        texto, _ = self._botao_backstage_sob_cursor(pos)
        if texto:
            return True
        return (
            self._cursor_sobre_algum_menu_backstage(pos)
            or self._cursor_sobre_corredor_entre_botao_e_menu(pos)
            or self._cursor_sobre_corredor_entre_menus_backstage(pos)
        )

    # ========== FIM DAS CORREÇÕES DE HOVER ==========

    def _abrir_menu_modelo(self, modo_hover: bool = False):
        botao = self.backstage.botoes.get("Modelo ▸")
        if botao is None:
            return
        self._mostrar_menu_backstage(self._criar_menu_modelo(), botao, "Modelo ▸", modo_hover)

    def _criar_menu_modelo(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(self._estilo_menu_backstage())
        menu.addAction("Novo modelo", lambda: self.lbl_status.setText("Novo modelo (em breve)"))
        menu.addAction("Abrir modelo", lambda: self.lbl_status.setText("Abrir modelo (em breve)"))
        menu.addAction("Salvar modelo", lambda: self.lbl_status.setText("Salvar modelo (em breve)"))
        menu.addSeparator()
        menu.addAction("Tabela de medidas", lambda: self.lbl_status.setText("Tabela de medidas (em breve)"))
        menu.addAction("Propriedades do modelo", lambda: self.lbl_status.setText("Propriedades do modelo (em breve)"))
        return menu

    def _abrir_menu_importar(self, modo_hover: bool = False):
        botao = self.backstage.botoes.get("Importar ▸")
        if not botao:
            return
        self._mostrar_menu_backstage(self._criar_menu_importar(), botao, "Importar ▸", modo_hover)

    def _criar_menu_importar(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(self._estilo_menu_backstage())
        menu.addAction("Arquivo DXF", lambda: self._importar_por_tipo("dxf"))
        menu.addAction("Arquivo AAMA/ASTM", lambda: self._importar_por_tipo("aama_astm"))
        menu.addAction("Arquivo de Plotagem", lambda: self._importar_por_tipo("plotagem"))
        menu.addSeparator()
        sub_lectra = menu.addMenu("Lectra")
        sub_lectra.addAction("Arquivo Lectra", lambda: self._importar_por_tipo("aama_astm", origem_inicial="Lectra"))
        menu.addAction("Investronica", lambda: self._importar_por_tipo("aama_astm", origem_inicial="Investronica"))
        menu.addAction("Gerber", lambda: self._importar_por_tipo("aama_astm", origem_inicial="Gerber"))
        menu.addAction("Assyst", lambda: self._importar_por_tipo("aama_astm", origem_inicial="Assyst"))
        menu.addSeparator()
        menu.addAction("Arquivos EMF/XML/ADSX/AMKX", lambda: self._importar_por_tipo("audaces"))
        menu.addAction("Converter manualmente por traçado", self._acao_converter_manual_tracado_adsx)
        sub_adv = menu.addMenu("Arquivos avancados")
        sub_adv.addAction("Arquivos EMF (*.emf)", lambda: self._importar_por_tipo("audaces_emf"))
        sub_adv.addAction("Arquivos XML (*.xml)", lambda: self._importar_por_tipo("audaces_xml"))
        sub_adv.addAction("Arquivos ADSX/AMKX (*.adsx *.amkx)", lambda: self._importar_por_tipo("adsx"))
        sub_adv.addAction("Arquivos EMF + XML", lambda: self._importar_por_tipo("audaces_emf_xml"))
        return menu

    def _abrir_menu_exportar(self, modo_hover: bool = False):
        botao = self.backstage.botoes.get("Exportar ▸")
        if botao is None:
            return
        self._mostrar_menu_backstage(self._criar_menu_exportar(), botao, "Exportar ▸", modo_hover)

    def _criar_menu_exportar(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(self._estilo_menu_backstage())
        menu.addAction("Exportar projeto...", lambda: self.lbl_status.setText("Exportar projeto (em breve)"))
        menu.addAction("Exportar para PDF...", self._abrir_dialogo_impressao)
        menu.addAction("Exportar para plotagem...", self._abrir_dialogo_plotagem)
        menu.addSeparator()
        menu.addAction("DXF/AAMA...", lambda: self.lbl_status.setText("Exportar DXF/AAMA (em breve)"))
        menu.addAction("ASTM...", lambda: self.lbl_status.setText("Exportar ASTM (em breve)"))
        menu.addAction("SVG/Imagem...", lambda: self.lbl_status.setText("Exportar SVG/Imagem (em breve)"))
        return menu

    def _abrir_menu_configuracoes(self, modo_hover: bool = False):
        botao = self.backstage.botoes.get("Configurações ▸")
        if botao is None:
            return
        self._mostrar_menu_backstage(self._criar_menu_configuracoes(), botao, "Configurações ▸", modo_hover)

    def _criar_menu_configuracoes(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(self._estilo_menu_backstage())

        def _add_menu_acao(texto: str, callback, icon_name: str | None = None):
            acao = menu.addAction(texto, callback)
            if icon_name:
                caminho = ICONS_DIR / icon_name
                if caminho.exists():
                    acao.setIcon(carregar_icone(icon_name))
            return acao

        menu.addAction("Opções", self._abrir_dialogo_opcoes)
        menu.addAction("Unidade de medida\tCtrl+U", self._abrir_dialogo_unidade_medida)
        menu.addAction("Mesa digitalizadora", lambda: self.lbl_status.setText("Mesa digitalizadora (em breve)"))
        menu_regras = menu.addMenu("Regras de graduação")
        menu_regras.addAction("Regras de Graduação - Nomes...", lambda: self.lbl_status.setText("Regras de Graduação - Nomes (em breve)"))
        menu_regras.addAction("Regras de Graduação - Valores...", lambda: self.lbl_status.setText("Regras de Graduação - Valores (em breve)"))
        _add_menu_acao("Cores", self._abrir_dialogo_cores, "cores_rapido.svg")
        self._criar_submenu_temas_interface(menu)
        menu.addAction("Grade", lambda: self.lbl_status.setText("Grade (em breve)"))
        menu_snap = menu.addMenu("Snap")
        menu_snap_classico = menu_snap.addMenu("Clássico")
        menu_snap_classico.addAction("Configurações", lambda: self.lbl_status.setText("Snap clássico (em breve)"))
        acao_snap_auto = menu_snap.addAction("Automático")
        acao_snap_auto.setCheckable(True)
        acao_snap_auto.setChecked(True)
        menu_snap.addSeparator()
        menu_snap.addAction("Configurações\tF4", lambda: self.lbl_status.setText("Configurações de snap (em breve)"))
        menu.addAction("Paleta de usuário", lambda: self.lbl_status.setText("Paleta de usuário (em breve)"))
        menu.addAction("Tecidos", lambda: self._ativar_ferramenta_global("tecidos"))
        menu.addAction("Teclas de atalho", lambda: self.lbl_status.setText("Teclas de atalho (em breve)"))
        _add_menu_acao("Impressão...\tCtrl+P", self._abrir_dialogo_impressao, "imprimir_rapido.svg")
        _add_menu_acao("Plotagem...\tCtrl+Shift+P", self._abrir_dialogo_plotagem, "plotar_rapido.svg")
        menu.addAction("Níveis de impressão", self._abrir_dialogo_impressao)
        return menu

    def _abrir_menu_ajuda(self, modo_hover: bool = False):
        botao = self.backstage.botoes.get("Ajuda ▸") or self.backstage.botoes.get("Ajuda")
        if botao is None:
            return
        origem = "Ajuda ▸" if "Ajuda ▸" in self.backstage.botoes else "Ajuda"
        self._mostrar_menu_backstage(self._criar_menu_ajuda(), botao, origem, modo_hover)

    def _criar_menu_ajuda(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(self._estilo_menu_backstage())
        menu.addAction("Ajuda do GUIMMA STUDIO", lambda: self.lbl_status.setText("Ajuda (em breve)"))
        menu.addAction("Tutoriais", lambda: self.lbl_status.setText("Tutoriais (em breve)"))
        menu.addAction("Sobre", lambda: self.lbl_status.setText("Sobre (em breve)"))
        return menu

    def _estilo_menu_backstage(self) -> str:
        tema = self._tema_interface()
        return folha_estilo_hover_global() + (
            f"QMenu {{ background:{tema['painel']}; color:{tema['texto']}; border:1px solid {tema['borda']}; padding:3px; }}"
            f"QMenu::item {{ color:{tema['texto']}; padding:7px 22px 7px 18px; min-width:220px; }}"
            f"QMenu::item:selected {{ background:{tema['hover_menu']}; color:{tema['primaria_escura']}; }}"
            f"QMenu::separator {{ height:1px; background:{tema['borda']}; margin:4px 8px; }}"
            "QMenu::right-arrow { width:10px; height:10px; }"
        )

    def _posicao_submenu_backstage(self, botao: QWidget) -> QPoint:
        return botao.mapToGlobal(QPoint(max(0, botao.width() - 1), 0))



    def _qt_widget_vivo(self, widget) -> bool:
        try:
            return widget is not None and _qt_objeto_valido(widget)
        except Exception:
            return False

    def _qt_widget_visivel(self, widget) -> bool:
        try:
            return self._qt_widget_vivo(widget) and widget.isVisible()
        except RuntimeError:
            return False
        except Exception:
            return False

    def _limpar_referencias_menus_backstage_invalidos(self):
        menus_validos = []
        for menu in list(getattr(self, "_menus_backstage_hover", [])):
            if self._qt_widget_vivo(menu):
                menus_validos.append(menu)
        self._menus_backstage_hover = menus_validos
        atual = getattr(self, "_menu_backstage_hover_aberto", None)
        if atual is not None and not self._qt_widget_vivo(atual):
            self._menu_backstage_hover_aberto = None
            self._menu_backstage_hover_origem = None
            self._menus_backstage_hover = []



    def _abrir_dialogo_opcoes(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Opções")
        dialog.setModal(True)
        dialog.resize(640, 760)
        self._aplicar_estilo_claro_dialogo(dialog)
        lay = QVBoxLayout(dialog)

        topo = QHBoxLayout()
        col_esq = QVBoxLayout()
        col_dir = QVBoxLayout()
        topo.addLayout(col_esq, 1)
        topo.addLayout(col_dir, 1)
        lay.addLayout(topo)

        gb_texto = QGroupBox("Texto")
        g_texto = QGridLayout(gb_texto)
        edt_texto_tam = QLineEdit(str(self._opcoes_app.get("texto_tamanho_cm", 1.0)))
        chk_truetype = QCheckBox("Usar TrueType®")
        chk_truetype.setChecked(self._opcoes_app.get("usar_truetype", False))
        g_texto.addWidget(QLabel("Tamanho da letra (cm)"), 0, 0)
        g_texto.addWidget(edt_texto_tam, 0, 1)
        g_texto.addWidget(chk_truetype, 1, 0, 1, 2)
        col_esq.addWidget(gb_texto)

        gb_salvar = QGroupBox("Salvar")
        g_salvar = QGridLayout(gb_salvar)
        chk_auto = QCheckBox("Auto recuperação (min.)")
        chk_auto.setChecked(True)
        edt_auto = QLineEdit(str(self._opcoes_app.get("auto_recuperacao_min", 1)))
        chk_validar = QCheckBox("Validar se o ponto de cam está definido")
        chk_validar.setChecked(self._opcoes_app.get("validar_ponto_cam", True))
        g_salvar.addWidget(chk_auto, 0, 0)
        g_salvar.addWidget(edt_auto, 0, 1)
        g_salvar.addWidget(chk_validar, 1, 0, 1, 2)
        col_esq.addWidget(gb_salvar)

        gb_prop = QGroupBox("Propriedades dos moldes")
        g_prop = QVBoxLayout(gb_prop)
        chk_grad_alt = QCheckBox("Permitir graduação na altura")
        chk_grad_alt.setChecked(self._opcoes_app.get("permitir_graduacao_altura", False))
        chk_usa_ferr = QCheckBox("Usar ferramentas")
        chk_usa_ferr.setChecked(self._opcoes_app.get("usar_ferramentas_moldes", False))
        chk_rot_duplo = QCheckBox("Rotacionar com clique duplo")
        chk_rot_duplo.setChecked(self._opcoes_app.get("rotacionar_duplo_clique", True))
        chk_coef = QCheckBox("Exibir coeficiente de encolhimento em porcentagem")
        chk_coef.setChecked(self._opcoes_app.get("exibir_coef_encolhimento", True))
        for w in (chk_grad_alt, chk_usa_ferr, chk_rot_duplo, chk_coef):
            g_prop.addWidget(w)
        col_esq.addWidget(gb_prop)

        gb_pique = QGroupBox("Pique")
        g_pique = QGridLayout(gb_pique)
        edt_pique_l = QLineEdit(str(self._opcoes_app.get("pique_largura_cm", 0.3)))
        edt_pique_a = QLineEdit(str(self._opcoes_app.get("pique_altura_cm", 0.3)))
        edt_pique_ang = QLineEdit(str(self._opcoes_app.get("pique_angulo", 0.0)))
        chk_furador_iso = QCheckBox("Mostrar interface furador ISO")
        chk_furador_iso.setChecked(self._opcoes_app.get("mostrar_furador_iso", False))
        g_pique.addWidget(QLabel("Largura (cm)"), 0, 0)
        g_pique.addWidget(edt_pique_l, 0, 1)
        g_pique.addWidget(QLabel("Altura (cm)"), 1, 0)
        g_pique.addWidget(edt_pique_a, 1, 1)
        g_pique.addWidget(QLabel("Ângulo"), 2, 0)
        g_pique.addWidget(edt_pique_ang, 2, 1)
        g_pique.addWidget(chk_furador_iso, 3, 0, 1, 2)
        col_dir.addWidget(gb_pique)

        gb_perf = QGroupBox("Performance")
        g_perf = QVBoxLayout(gb_perf)
        chk_aa = QCheckBox("Usar Antialiasing")
        chk_aa.setChecked(self._opcoes_app.get("antialiasing", True))
        g_perf.addWidget(chk_aa)
        col_dir.addWidget(gb_perf)

        gb_interface = QGroupBox("Interface")
        g_int = QGridLayout(gb_interface)
        chk_costura = QCheckBox("Exibir ferramentas de costura estática")
        chk_costura.setChecked(self._opcoes_app.get("exibir_ferramenta_costura", False))
        chk_dock = QCheckBox("Permitir docar menus auxiliares")
        chk_dock.setChecked(self._opcoes_app.get("permitir_docar_menus_aux", False))
        chk_barra = QCheckBox("Barra de tarefas flutuante")
        chk_barra.setChecked(self._opcoes_app.get("barra_tarefas_flutuante", False))
        cmb_tam_icone = QComboBox()
        cmb_tam_icone.addItems(["Pequeno", "Médio", "Grande"])
        cmb_tam_icone.setCurrentText(self._opcoes_app.get("tamanho_icone", "Grande"))
        g_int.addWidget(chk_costura, 0, 0, 1, 2)
        g_int.addWidget(chk_dock, 1, 0, 1, 2)
        g_int.addWidget(chk_barra, 2, 0, 1, 2)
        g_int.addWidget(QLabel("Tamanho do ícone"), 3, 0)
        g_int.addWidget(cmb_tam_icone, 3, 1)
        col_dir.addWidget(gb_interface)

        gb_rest = QGroupBox("Ponto de restauração")
        g_rest = QVBoxLayout(gb_rest)
        chk_pt_rest = QCheckBox("Criar ponto de restauração ao abrir e salvar arquivo")
        chk_pt_rest.setChecked(self._opcoes_app.get("criar_ponto_restauracao_auto", False))
        g_rest.addWidget(chk_pt_rest)
        lay.addWidget(gb_rest)

        gb_backup = QGroupBox("Configurar arquivo backup")
        g_backup = QGridLayout(gb_backup)
        chk_backup = QCheckBox("Arquivo backup")
        chk_backup.setChecked(self._opcoes_app.get("arquivo_backup", False))
        edt_backup = QLineEdit(self._opcoes_app.get("caminho_backup", ""))
        btn_backup = QPushButton("Alterar")
        def _escolher_backup():
            caminho, _ = QFileDialog.getSaveFileName(
                dialog,
                "Arquivo de backup",
                edt_backup.text().strip() or str(Path.home() / "guimma_backup.bak"),
                "Backup (*.bak);;Todos (*.*)",
                options=QFileDialog.Option.DontUseNativeDialog,
            )
            if caminho:
                edt_backup.setText(caminho)
        btn_backup.clicked.connect(_escolher_backup)
        g_backup.addWidget(chk_backup, 0, 0, 1, 2)
        g_backup.addWidget(edt_backup, 1, 0)
        g_backup.addWidget(btn_backup, 1, 1)
        lay.addWidget(gb_backup)

        gb_comp = QGroupBox("Configurações compartilhadas")
        g_comp = QGridLayout(gb_comp)
        edt_comp = QLineEdit(self._opcoes_app.get("config_compartilhadas", ""))
        btn_add_comp = QPushButton("Adicionar")
        btn_rem_comp = QPushButton("Remover")
        chk_comp_tecido = QCheckBox("Tecido")
        chk_comp_tecido.setChecked(self._opcoes_app.get("compartilhar_tecido", False))
        chk_comp_regra = QCheckBox("Regras de graduação")
        chk_comp_regra.setChecked(self._opcoes_app.get("compartilhar_regras_graduacao", False))
        chk_comp_plot = QCheckBox("Plotagem")
        chk_comp_plot.setChecked(self._opcoes_app.get("compartilhar_plotagem", False))
        g_comp.addWidget(edt_comp, 0, 0, 1, 2)
        g_comp.addWidget(btn_add_comp, 0, 2)
        g_comp.addWidget(chk_comp_tecido, 1, 0)
        g_comp.addWidget(chk_comp_regra, 1, 1)
        g_comp.addWidget(chk_comp_plot, 1, 2)
        g_comp.addWidget(btn_rem_comp, 2, 2)
        lay.addWidget(gb_comp)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(dialog.accept)
        botoes.rejected.connect(dialog.reject)
        lay.addWidget(botoes)

        if dialog.exec() != QDialog.Accepted:
            return
        mins = int(numero_decimal_ponto(edt_auto.text(), 1.0))
        def _float_val(edt: QLineEdit, default: float) -> float:
            return numero_decimal_ponto(edt.text(), default)
        self._opcoes_app["auto_recuperacao_min"] = max(1, mins)
        self._opcoes_app["texto_tamanho_cm"] = _float_val(edt_texto_tam, 1.0)
        self._opcoes_app["usar_truetype"] = chk_truetype.isChecked()
        self._opcoes_app["pique_largura_cm"] = _float_val(edt_pique_l, 0.3)
        self._opcoes_app["pique_altura_cm"] = _float_val(edt_pique_a, 0.3)
        self._opcoes_app["pique_angulo"] = _float_val(edt_pique_ang, 0.0)
        self._opcoes_app["mostrar_furador_iso"] = chk_furador_iso.isChecked()
        self._opcoes_app["antialiasing"] = chk_aa.isChecked()
        self._opcoes_app["validar_ponto_cam"] = chk_validar.isChecked()
        self._opcoes_app["permitir_graduacao_altura"] = chk_grad_alt.isChecked()
        self._opcoes_app["usar_ferramentas_moldes"] = chk_usa_ferr.isChecked()
        self._opcoes_app["rotacionar_duplo_clique"] = chk_rot_duplo.isChecked()
        self._opcoes_app["exibir_coef_encolhimento"] = chk_coef.isChecked()
        self._opcoes_app["exibir_ferramenta_costura"] = chk_costura.isChecked()
        self._opcoes_app["permitir_docar_menus_aux"] = chk_dock.isChecked()
        self._opcoes_app["barra_tarefas_flutuante"] = chk_barra.isChecked()
        self._opcoes_app["tamanho_icone"] = cmb_tam_icone.currentText()
        self._opcoes_app["criar_ponto_restauracao_auto"] = chk_pt_rest.isChecked()
        self._opcoes_app["arquivo_backup"] = chk_backup.isChecked()
        self._opcoes_app["caminho_backup"] = edt_backup.text().strip()
        self._opcoes_app["config_compartilhadas"] = edt_comp.text().strip()
        self._opcoes_app["compartilhar_tecido"] = chk_comp_tecido.isChecked()
        self._opcoes_app["compartilhar_regras_graduacao"] = chk_comp_regra.isChecked()
        self._opcoes_app["compartilhar_plotagem"] = chk_comp_plot.isChecked()
        self._salvar_opcoes_app()
        self._aplicar_intervalo_recovery()
        self.lbl_status.setText("Opções atualizadas.")

    def _abrir_dialogo_cores_legado(self):
        area = self._area_documento_atual()
        if not area:
            return
        canvas = area.canvas
        dialog = QDialog(self)
        dialog.setWindowTitle("Cores")
        dialog.setModal(False)
        dialog.resize(520, 760)
        dialog.setMinimumSize(500, 720)
        self._aplicar_estilo_claro_dialogo(dialog)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        def botao_cor(hex_cor: str):
            btn = QPushButton("")
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(f"background:{hex_cor}; border:1px solid #8a8a8a;")
            return btn

        topo = QHBoxLayout()
        gb_cores = QGroupBox("Cores")
        gb_cores_lay = QGridLayout(gb_cores)
        gb_cores_lay.addWidget(botao_cor("#ea00ff"), 0, 0)
        gb_cores_lay.addWidget(QLabel("Desenho"), 0, 1)
        gb_cores_lay.addWidget(botao_cor("#000000"), 0, 2)
        gb_cores_lay.addWidget(QLabel("Fundo"), 0, 3)
        gb_cores_lay.addWidget(botao_cor("#ff0000"), 1, 0)
        gb_cores_lay.addWidget(QLabel("Seleção"), 1, 1)
        gb_cores_lay.addWidget(botao_cor("#bfbfbf"), 1, 2)
        gb_cores_lay.addWidget(QLabel("Grade"), 1, 3)
        topo.addWidget(gb_cores, 1)

        gb_snap = QGroupBox("Cores do snap")
        gb_snap_lay = QVBoxLayout(gb_snap)
        chk_auto_snap = QCheckBox("Usar cores automáticas")
        chk_auto_snap.setChecked(True)
        gb_snap_lay.addWidget(chk_auto_snap)
        linha_snap_1 = QHBoxLayout()
        linha_snap_1.addWidget(botao_cor("#6f6f6f"))
        linha_snap_1.addWidget(QLabel("Desenho do Snap"))
        linha_snap_1.addStretch(1)
        gb_snap_lay.addLayout(linha_snap_1)
        linha_snap_2 = QHBoxLayout()
        linha_snap_2.addWidget(botao_cor("#d71313"))
        linha_snap_2.addWidget(QLabel("Referência do Snap"))
        linha_snap_2.addStretch(1)
        gb_snap_lay.addLayout(linha_snap_2)
        topo.addWidget(gb_snap, 1)
        layout.addLayout(topo)

        gb_moldes = QGroupBox("Cores dos moldes")
        moldes = QGridLayout(gb_moldes)
        moldes.setHorizontalSpacing(12)
        moldes.setVerticalSpacing(6)
        col_esq = ["Piques", "Piques internos", "Fio", "Linhas auxiliares", "Costura", "Molde dobrado", "Nome molde", "Descrição"]
        col_dir = ["Números", "Observações", "Linha simetria", "Margem", "Tamanhos menores", "Tamanho base", "Tamanho maiores"]
        for i, txt in enumerate(col_esq):
            moldes.addWidget(QCheckBox(""), i, 0)
            moldes.addWidget(botao_cor("#efefef"), i, 1)
            moldes.addWidget(QLabel(txt), i, 2)
        for i, txt in enumerate(col_dir):
            moldes.addWidget(QCheckBox(""), i, 3)
            moldes.addWidget(botao_cor("#efefef"), i, 4)
            moldes.addWidget(QLabel(txt), i, 5)

        base_row = max(len(col_esq), len(col_dir)) + 1
        for idx, texto in enumerate(["Ponto de controle", "Ponto de pique", "Ponto não graduado"]):
            moldes.addWidget(QCheckBox(""), base_row + idx, 0)
            moldes.addWidget(botao_cor("#efefef"), base_row + idx, 1)
            moldes.addWidget(QLabel(texto), base_row + idx, 2)
            cmb = QComboBox()
            cmb.addItems(["Círculo preenchido", "Quadrado preenchido", "Losango"])
            cmb.setCurrentIndex(min(idx, 2))
            moldes.addWidget(cmb, base_row + idx, 3, 1, 3)
        layout.addWidget(gb_moldes)

        chk_conforme = QCheckBox("Mostrar conforme definição das ferramentas")
        chk_conforme.setEnabled(False)
        layout.addWidget(chk_conforme)

        linha_tecidos = QHBoxLayout()
        chk_cor_tecidos = QCheckBox("Mostrar cor dos tecidos")
        chk_cor_tecidos.setChecked(bool(self._mostrar_cor_tecidos_global))
        linha_tecidos.addWidget(chk_cor_tecidos)
        btn_config = QPushButton("Configurar cor dos tecidos")
        linha_tecidos.addWidget(btn_config)
        linha_tecidos.addStretch(1)
        layout.addLayout(linha_tecidos)

        layout.addWidget(QCheckBox("Mostrar cor dos tecidos no menu de moldes"))

        linha_opacidade = QHBoxLayout()
        linha_opacidade.addWidget(QLabel("Opacidade das imagens"))
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(100)
        linha_opacidade.addWidget(slider, 1)
        linha_opacidade.addWidget(QLabel("100 / 100"))
        layout.addLayout(linha_opacidade)

        linha_estilo = QHBoxLayout()
        linha_estilo.addWidget(QLabel("Estilo linha costura"))
        cmb_estilo = QComboBox()
        cmb_estilo.addItems(["- - - - - -", "_______", "· · · · ·"])
        linha_estilo.addWidget(cmb_estilo)
        layout.addLayout(linha_estilo)

        gb_esquema = QGroupBox("Esquema de cores")
        esquema_lay = QHBoxLayout(gb_esquema)
        cmb_esquema = QComboBox()
        esquema_lay.addWidget(cmb_esquema, 1)
        btn_salvar_esquema = QPushButton("Salvar esquema de cores")
        btn_salvar_esquema.setEnabled(False)
        esquema_lay.addWidget(btn_salvar_esquema, 1)
        layout.addWidget(gb_esquema)
        layout.addStretch(1)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        btn_ok = QPushButton("✓ OK")
        btn_cancelar = QPushButton("✕ Cancelar")
        rodape.addWidget(btn_ok)
        rodape.addWidget(btn_cancelar)
        layout.addLayout(rodape)

        def abrir_config():
            tecidos = sorted({
                str(el.get("tecido") or "").strip()
                for el in canvas.cena.elementos
                if el.get("molde") and str(el.get("tecido") or "").strip()
            })
            dialog_tecidos = ConfigurarCoresTecidosDialog(tecidos, dict(self._cores_tecidos_global), dialog)
            if dialog_tecidos.exec() == QDialog.Accepted:
                self.aplicar_config_cores_tecidos_global(mapa_cores=dialog_tecidos.cores_tecidos())

        def aplicar_e_fechar():
            self.aplicar_config_cores_tecidos_global(mostrar=chk_cor_tecidos.isChecked())
            dialog.accept()

        btn_config.clicked.connect(abrir_config)
        btn_ok.clicked.connect(aplicar_e_fechar)
        btn_cancelar.clicked.connect(dialog.reject)
        dialog.exec()

    def _abrir_dialogo_cores(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Cores")
        dialog.resize(780, 860)
        dialog.setMinimumSize(720, 820)
        self._aplicar_estilo_claro_dialogo(dialog)
        raiz = QVBoxLayout(dialog)
        raiz.setContentsMargins(10, 10, 10, 10)
        raiz.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        conteudo = QWidget()
        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        scroll.setWidget(conteudo)
        raiz.addWidget(scroll, 1)

        def atualizar_botao_cor(btn: QPushButton, hex_cor: str):
            cor = self._cor_hex_valida(hex_cor, "#ffffff")
            btn.setProperty("cor", cor)
            btn.setStyleSheet(f"background:{cor}; border:1px solid #8a8a8a; border-radius:2px;")

        def escolher_cor(btn: QPushButton, titulo: str):
            seletor = QColorDialog(QColor(str(btn.property("cor") or "#ffffff")), dialog)
            seletor.setWindowTitle(titulo)
            seletor.setOption(QColorDialog.DontUseNativeDialog, True)
            seletor.setStyleSheet("QColorDialog { background:#f4f4f4; color:#101010; }")
            if seletor.exec() == QDialog.Accepted and seletor.selectedColor().isValid():
                atualizar_botao_cor(btn, seletor.selectedColor().name())

        def botao_cor(hex_cor: str, titulo: str):
            btn = QPushButton("")
            btn.setFixedSize(24, 24)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(titulo)
            atualizar_botao_cor(btn, hex_cor)
            btn.clicked.connect(lambda _=False, b=btn, t=titulo: escolher_cor(b, t))
            return btn

        topo = QHBoxLayout()
        gb_cores = QGroupBox("Cores")
        gb_cores_lay = QGridLayout(gb_cores)
        botoes_canvas: dict[str, QPushButton] = {}
        for chave, titulo, linha, coluna in (
            ("desenho", "Desenho", 0, 0),
            ("fundo", "Fundo", 0, 2),
            ("selecao", "Selecao", 1, 0),
            ("grade", "Grade", 1, 2),
        ):
            botoes_canvas[chave] = botao_cor(self._cores_canvas_global[chave], f"Cor: {titulo}")
            gb_cores_lay.addWidget(botoes_canvas[chave], linha, coluna)
            gb_cores_lay.addWidget(QLabel(titulo), linha, coluna + 1)
        topo.addWidget(gb_cores, 1)

        gb_snap = QGroupBox("Cores do snap")
        gb_snap_lay = QVBoxLayout(gb_snap)
        chk_auto_snap = QCheckBox("Usar cores automaticas")
        chk_auto_snap.setChecked(bool(self._snap_cores_automaticas_global))
        gb_snap_lay.addWidget(chk_auto_snap)
        botoes_canvas["snap_desenho"] = botao_cor(self._cores_canvas_global["snap_desenho"], "Cor: Desenho do Snap")
        botoes_canvas["snap_referencia"] = botao_cor(self._cores_canvas_global["snap_referencia"], "Cor: Referencia do Snap")
        linha_snap_1 = QHBoxLayout()
        linha_snap_1.addWidget(botoes_canvas["snap_desenho"])
        linha_snap_1.addWidget(QLabel("Desenho do Snap"))
        linha_snap_1.addStretch(1)
        gb_snap_lay.addLayout(linha_snap_1)
        linha_snap_2 = QHBoxLayout()
        linha_snap_2.addWidget(botoes_canvas["snap_referencia"])
        linha_snap_2.addWidget(QLabel("Referencia do Snap"))
        linha_snap_2.addStretch(1)
        gb_snap_lay.addLayout(linha_snap_2)
        topo.addWidget(gb_snap, 1)
        layout.addLayout(topo)

        gb_moldes = QGroupBox("Cores dos moldes")
        moldes = QGridLayout(gb_moldes)
        moldes.setHorizontalSpacing(10)
        moldes.setVerticalSpacing(5)
        campos_moldes_esq = [
            ("piques", "Piques"),
            ("piques_internos", "Piques internos"),
            ("fio", "Fio"),
            ("linhas_auxiliares", "Linhas auxiliares"),
            ("costura", "Costura"),
            ("molde_dobrado", "Molde dobrado"),
            ("nome_molde", "Nome molde"),
            ("descricao", "Descricao"),
        ]
        campos_moldes_dir = [
            ("numeros", "Numeros"),
            ("observacoes", "Observacoes"),
            ("linha_simetria", "Linha simetria"),
            ("margem", "Margem"),
            ("tamanhos_menores", "Tamanhos menores"),
            ("tamanho_base", "Tamanho base"),
            ("tamanhos_maiores", "Tamanhos maiores"),
        ]
        widgets_moldes: dict[str, tuple[QCheckBox, QPushButton]] = {}
        combos_pontos: dict[str, QComboBox] = {}

        def adicionar_item_molde(chave: str, texto: str, linha: int, coluna: int):
            cfg = self._cores_moldes_global.get(chave, self.CORES_MOLDES_PADRAO[chave])
            chk = QCheckBox("")
            chk.setChecked(bool(cfg.get("ativo", False)))
            btn = botao_cor(str(cfg.get("cor", "#efefef")), f"Cor: {texto}")
            moldes.addWidget(chk, linha, coluna)
            moldes.addWidget(btn, linha, coluna + 1)
            moldes.addWidget(QLabel(texto), linha, coluna + 2)
            widgets_moldes[chave] = (chk, btn)

        for i, (chave, texto) in enumerate(campos_moldes_esq):
            adicionar_item_molde(chave, texto, i, 0)
        for i, (chave, texto) in enumerate(campos_moldes_dir):
            adicionar_item_molde(chave, texto, i, 3)

        base_row = max(len(campos_moldes_esq), len(campos_moldes_dir))
        separador_pontos = QFrame()
        separador_pontos.setFrameShape(QFrame.HLine)
        separador_pontos.setFrameShadow(QFrame.Sunken)
        moldes.addWidget(separador_pontos, base_row, 0, 1, 6)
        lbl_pontos = QLabel("Pontos")
        lbl_pontos.setStyleSheet("font-weight:600; color:#202020;")
        moldes.addWidget(lbl_pontos, base_row + 1, 0, 1, 6)
        for idx, (chave, texto, padrao) in enumerate((
            ("ponto_controle", "Ponto de controle", "Circulo preenchido"),
            ("ponto_pique", "Ponto de pique", "Quadrado preenchido"),
            ("ponto_nao_graduado", "Ponto nao graduado", "Losango"),
        )):
            linha = base_row + 2 + idx
            adicionar_item_molde(chave, texto, linha, 0)
            cmb = QComboBox()
            cmb.addItems(["Circulo preenchido", "Quadrado preenchido", "Losango"])
            cfg_ponto = self._cores_moldes_global.get(chave, self.CORES_MOLDES_PADRAO[chave])
            cmb.setCurrentText(str(cfg_ponto.get("forma", padrao)))
            combos_pontos[chave] = cmb
            moldes.addWidget(cmb, linha, 3, 1, 3)
        layout.addWidget(gb_moldes)

        chk_conforme = QCheckBox("Mostrar conforme definicao das ferramentas")
        chk_conforme.setChecked(bool(self._usar_cores_ferramentas_global))
        layout.addWidget(chk_conforme)

        cores_tecidos_temp = dict(self._cores_tecidos_global)
        linha_tecidos = QHBoxLayout()
        chk_cor_tecidos = QCheckBox("Mostrar cor dos tecidos")
        chk_cor_tecidos.setChecked(bool(self._mostrar_cor_tecidos_global))
        linha_tecidos.addWidget(chk_cor_tecidos)
        btn_config = QPushButton("Configurar cor dos tecidos")
        linha_tecidos.addWidget(btn_config)
        linha_tecidos.addStretch(1)
        layout.addLayout(linha_tecidos)

        chk_cor_tecidos_menu = QCheckBox("Mostrar cor dos tecidos no menu de moldes")
        chk_cor_tecidos_menu.setChecked(bool(self._mostrar_cor_tecidos_menu_global))
        layout.addWidget(chk_cor_tecidos_menu)

        linha_opacidade = QHBoxLayout()
        linha_opacidade.addWidget(QLabel("Opacidade das imagens"))
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(int(round(float(self._opacidade_imagens_global) * 100.0)))
        linha_opacidade.addWidget(slider, 1)
        lbl_opacidade = QLabel("100 / 100")
        slider.valueChanged.connect(lambda valor: lbl_opacidade.setText(f"{valor} / 100"))
        lbl_opacidade.setText(f"{slider.value()} / 100")
        linha_opacidade.addWidget(lbl_opacidade)
        layout.addLayout(linha_opacidade)

        linha_estilo = QHBoxLayout()
        linha_estilo.addWidget(QLabel("Estilo linha costura"))
        cmb_estilo = QComboBox()
        cmb_estilo.setIconSize(QSize(132, 20))
        cmb_estilo.view().setIconSize(QSize(132, 20))
        for estilo_id, titulo in LINE_STYLES:
            cmb_estilo.addItem(QIcon(self._icone_preview_linha(estilo_id)), titulo, estilo_id)
        cmb_estilo.setCurrentIndex(max(0, cmb_estilo.findData(self._estilo_linha_costura_global)))
        linha_estilo.addWidget(cmb_estilo, 1)
        layout.addLayout(linha_estilo)

        gb_esquema = QGroupBox("Esquema de cores")
        esquema_lay = QHBoxLayout(gb_esquema)
        cmb_esquema = QComboBox()
        esquema_lay.addWidget(cmb_esquema, 1)
        btn_salvar_esquema = QPushButton("Salvar esquema de cores")
        esquema_lay.addWidget(btn_salvar_esquema, 1)
        layout.addWidget(gb_esquema)

        def config_atual() -> dict:
            return {
                "cores_canvas_global": {
                    chave: str(botao.property("cor") or self.CORES_CANVAS_PADRAO[chave])
                    for chave, botao in botoes_canvas.items()
                },
                "cores_moldes_global": {
                    chave: {
                        "ativo": chk.isChecked(),
                        "cor": str(btn.property("cor") or "#efefef"),
                        **({"forma": combos_pontos[chave].currentText()} if chave in combos_pontos else {}),
                    }
                    for chave, (chk, btn) in widgets_moldes.items()
                },
                "estilo_linha_costura_global": str(cmb_estilo.currentData() or self.ESTILO_LINHA_COSTURA_PADRAO),
                "usar_cores_ferramentas_global": chk_conforme.isChecked(),
                "snap_cores_automaticas_global": chk_auto_snap.isChecked(),
                "opacidade_imagens_global": float(slider.value()) / 100.0,
                "mostrar_cor_tecidos_global": chk_cor_tecidos.isChecked(),
                "mostrar_cor_tecidos_menu_global": chk_cor_tecidos_menu.isChecked(),
                "cores_tecidos_global": dict(cores_tecidos_temp),
            }

        def aplicar_config_na_tela(cfg: dict):
            cores_canvas = self._normalizar_cores_canvas(cfg.get("cores_canvas_global", {}))
            for chave, botao in botoes_canvas.items():
                atualizar_botao_cor(botao, cores_canvas.get(chave, self.CORES_CANVAS_PADRAO[chave]))
            cores_moldes = self._normalizar_cores_moldes(cfg.get("cores_moldes_global", {}))
            for chave, (chk, btn) in widgets_moldes.items():
                item = cores_moldes.get(chave, self.CORES_MOLDES_PADRAO[chave])
                chk.setChecked(bool(item.get("ativo", False)))
                atualizar_botao_cor(btn, str(item.get("cor", "#efefef")))
                if chave in combos_pontos:
                    combos_pontos[chave].setCurrentText(str(item.get("forma", self.CORES_MOLDES_PADRAO[chave].get("forma", "Circulo preenchido"))))
            cmb_estilo.setCurrentIndex(max(0, cmb_estilo.findData(str(cfg.get("estilo_linha_costura_global", self.ESTILO_LINHA_COSTURA_PADRAO)))))
            chk_conforme.setChecked(bool(cfg.get("usar_cores_ferramentas_global", False)))
            chk_auto_snap.setChecked(bool(cfg.get("snap_cores_automaticas_global", True)))
            slider.setValue(int(round(float(cfg.get("opacidade_imagens_global", 1.0)) * 100.0)))
            chk_cor_tecidos.setChecked(bool(cfg.get("mostrar_cor_tecidos_global", True)))
            chk_cor_tecidos_menu.setChecked(bool(cfg.get("mostrar_cor_tecidos_menu_global", False)))
            cores_tecidos_temp.clear()
            cores_tecidos_temp.update(self._normalizar_cores_tecidos(cfg.get("cores_tecidos_global", cores_tecidos_temp)))

        def popular_esquemas():
            atual = cmb_esquema.currentText()
            cmb_esquema.blockSignals(True)
            cmb_esquema.clear()
            cmb_esquema.addItem("")
            cmb_esquema.addItem("Padrao GUIMMA")
            for nome in sorted(self._esquemas_cores_usuario):
                cmb_esquema.addItem(nome)
            if atual:
                cmb_esquema.setCurrentText(atual)
            cmb_esquema.blockSignals(False)

        def carregar_esquema(nome: str):
            if not nome:
                return
            if nome == "Padrao GUIMMA":
                aplicar_config_na_tela(
                    {
                        "cores_canvas_global": dict(self.CORES_CANVAS_PADRAO),
                        "cores_moldes_global": {k: dict(v) for k, v in self.CORES_MOLDES_PADRAO.items()},
                        "estilo_linha_costura_global": self.ESTILO_LINHA_COSTURA_PADRAO,
                        "usar_cores_ferramentas_global": False,
                        "snap_cores_automaticas_global": True,
                        "opacidade_imagens_global": 1.0,
                        "mostrar_cor_tecidos_global": True,
                        "mostrar_cor_tecidos_menu_global": False,
                        "cores_tecidos_global": dict(self.CORES_TECIDOS_PADRAO),
                    }
                )
                return
            cfg = self._esquemas_cores_usuario.get(nome)
            if isinstance(cfg, dict):
                aplicar_config_na_tela(cfg)

        def salvar_esquema():
            nome, ok = QInputDialog.getText(dialog, "Salvar esquema de cores", "Nome do esquema:")
            nome = nome.strip()
            if not ok or not nome:
                return
            self._esquemas_cores_usuario[nome] = config_atual()
            self.projeto_atual.preferencias_usuario["esquemas_cores_usuario"] = dict(self._esquemas_cores_usuario)
            self._sincronizar_perfil_usuario_atual()
            self._salvar_preferencias_app()
            popular_esquemas()
            cmb_esquema.setCurrentText(nome)

        def abrir_config():
            area = self._area_documento_atual()
            canvas = area.canvas if area else None
            tecidos = {"1", "2"}
            if canvas is not None:
                tecidos.update(
                    str(el.get("tecido") or "").strip()
                    for el in canvas.cena.elementos
                    if isinstance(el, dict) and el.get("molde") and str(el.get("tecido") or "").strip()
                )
            tecidos.update(cores_tecidos_temp.keys())
            dialog_tecidos = ConfigurarCoresTecidosDialog(sorted(tecidos), dict(cores_tecidos_temp), dialog)
            if dialog_tecidos.exec() == QDialog.Accepted:
                cores_tecidos_temp.clear()
                cores_tecidos_temp.update(self._normalizar_cores_tecidos(dialog_tecidos.cores_tecidos()))

        def aplicar_e_fechar():
            self._aplicar_config_visualizacao_global(config_atual())
            dialog.accept()

        btn_config.clicked.connect(abrir_config)
        btn_salvar_esquema.clicked.connect(salvar_esquema)
        cmb_esquema.currentTextChanged.connect(carregar_esquema)
        popular_esquemas()

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        btn_ok = QPushButton("OK")
        btn_cancelar = QPushButton("Cancelar")
        rodape.addWidget(btn_ok)
        rodape.addWidget(btn_cancelar)
        raiz.addLayout(rodape)

        btn_ok.clicked.connect(aplicar_e_fechar)
        btn_cancelar.clicked.connect(dialog.reject)
        dialog.exec()

    def _aplicar_config_visualizacao_global(self, cfg: dict):
        self._cores_canvas_global = self._normalizar_cores_canvas(cfg.get("cores_canvas_global", {}))
        self._cores_moldes_global = self._normalizar_cores_moldes(cfg.get("cores_moldes_global", {}))
        self._estilo_linha_costura_global = str(
            cfg.get("estilo_linha_costura_global", self.ESTILO_LINHA_COSTURA_PADRAO)
        )
        if self._estilo_linha_costura_global not in {estilo_id for estilo_id, _ in LINE_STYLES}:
            self._estilo_linha_costura_global = self.ESTILO_LINHA_COSTURA_PADRAO
        self._usar_cores_ferramentas_global = bool(cfg.get("usar_cores_ferramentas_global", False))
        self._snap_cores_automaticas_global = bool(cfg.get("snap_cores_automaticas_global", True))
        self._opacidade_imagens_global = max(0.0, min(float(cfg.get("opacidade_imagens_global", 1.0)), 1.0))
        self._mostrar_cor_tecidos_global = bool(cfg.get("mostrar_cor_tecidos_global", True))
        self._mostrar_cor_tecidos_menu_global = bool(cfg.get("mostrar_cor_tecidos_menu_global", False))
        self._cores_tecidos_global = self._normalizar_cores_tecidos(cfg.get("cores_tecidos_global", {}))
        if cfg.get("sincronizar_cor_desenho_ativa", True):
            self._estilo_desenho_atual["cor"] = self._cores_canvas_global["desenho"]
        if hasattr(self, "ribbon"):
            self.ribbon.aplicar_estilo(self._estilo_desenho_atual)

        prefs = self.projeto_atual.preferencias_usuario
        prefs["cores_canvas_global"] = dict(self._cores_canvas_global)
        prefs["cores_moldes_global"] = {chave: dict(valor) for chave, valor in self._cores_moldes_global.items()}
        prefs["estilo_linha_costura_global"] = self._estilo_linha_costura_global
        prefs["usar_cores_ferramentas_global"] = bool(self._usar_cores_ferramentas_global)
        prefs["snap_cores_automaticas_global"] = bool(self._snap_cores_automaticas_global)
        prefs["opacidade_imagens_global"] = float(self._opacidade_imagens_global)
        prefs["mostrar_cor_tecidos_global"] = bool(self._mostrar_cor_tecidos_global)
        prefs["mostrar_cor_tecidos_menu_global"] = bool(self._mostrar_cor_tecidos_menu_global)
        prefs["cores_tecidos_global"] = dict(self._cores_tecidos_global)
        prefs["esquemas_cores_usuario"] = {
            str(nome): dict(valor)
            for nome, valor in self._esquemas_cores_usuario.items()
            if isinstance(valor, dict)
        }
        prefs["estilo_desenho"] = dict(self._estilo_desenho_atual)
        self._aplicar_config_visualizacao_nos_canvas()
        self._sincronizar_perfil_usuario_atual()
        self._salvar_preferencias_app()
        self._atualizar_menu_moldes()
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText("Cores do programa atualizadas.")

    def _icone_preview_linha(self, estilo: str, amplitude: float = 1.0, cor: str = "#111111") -> QPixmap:
        pix = QPixmap(132, 20)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(cor), 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            amp_scale = max(0.2, float(amplitude))
            if is_geometric_line_style(estilo):
                path = QPainterPath()
                path.moveTo(6, 10)
                if estilo.startswith("zigzag"):
                    amp = (2.0 if estilo == "zigzag_soft" else 4.0) * amp_scale
                    passo = 10.0 if estilo == "zigzag_soft" else 12.0
                    x = 6.0
                    sentido = 1.0
                    while x < 126.0:
                        x = min(126.0, x + passo)
                        path.lineTo(x, 10 + (amp * sentido))
                        sentido *= -1.0
                    path.lineTo(126, 10)
                elif estilo.startswith("wave"):
                    amp = (2.0 if estilo == "wave_soft" else 4.0) * amp_scale
                    passo = 12.0 if estilo == "wave_soft" else 14.0
                    for i in range(1, 48):
                        t = i / 47.0
                        x = 6.0 + (120.0 * t)
                        y = 10.0 + (amp * sin((2.0 * pi * (x - 6.0)) / passo))
                        path.lineTo(x, y)
                else:
                    amp = (3.0 if estilo == "half_moon" else 2.6) * amp_scale
                    passo = 16.0 if estilo == "half_moon" else 18.0
                    if estilo == "half_moon":
                        ciclos = max(1, round(120.0 / passo))
                        passo = 120.0 / ciclos
                    x = 6.0
                    while x < 126.0:
                        restante = 126.0 - x
                        if restante < (passo * 0.7):
                            path.lineTo(126.0, 10.0)
                            break
                        fim = min(126.0, x + passo)
                        for i in range(11):
                            t = i / 10.0
                            px = x + ((fim - x) * t)
                            py = 10.0 - (amp * sin(pi * t))
                            path.lineTo(px, py)
                        if estilo != "half_moon":
                            gap = 7.0 if estilo == "dash_half_moon" else 4.0
                            x = fim + gap
                            path.moveTo(min(126.0, x), 10.0)
                        else:
                            x = fim
                painter.drawPath(path)
            else:
                pen.setStyle(pen_style_for_line(estilo))
                padrao = dash_pattern_for_line(estilo)
                if padrao:
                    pen.setDashPattern(padrao)
                painter.setPen(pen)
                painter.drawLine(6, 10, 126, 10)
        finally:
            painter.end()
        return pix

    def _aplicar_config_visualizacao_nos_canvas(self):
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if not isinstance(area, AreaDocumentoWidget):
                continue
            area.canvas.set_config_cores_canvas(self._cores_canvas_global)
            area.canvas.set_config_cores_moldes(
                self._cores_moldes_global,
                self._estilo_linha_costura_global,
                usar_cores_ferramentas=self._usar_cores_ferramentas_global,
            )
            area.canvas.set_snap_cores_automaticas(self._snap_cores_automaticas_global)
            area.canvas.set_opacidade_imagens(self._opacidade_imagens_global)
            area.canvas.set_grid_visivel(bool(getattr(self, "btn_grid", None) and self.btn_grid.isChecked()))
            area.canvas._mostrar_cor_tecidos = bool(self._mostrar_cor_tecidos_global)
            area.canvas._cores_tecidos = dict(self._cores_tecidos_global)
            area.canvas.set_estilo_linha(**self._estilo_desenho_atual)
            area.canvas.update()

    def _aplicar_estilo_claro_dialogo(self, dialog: QDialog):
        tema = self._tema_interface()
        check_icon = (ICONS_DIR / "check_marcado.svg").as_posix()
        dialog.setStyleSheet(
            f"""
            QDialog {{ background: {tema['janela']}; color: {tema['texto']}; }}
            QFileDialog, QMessageBox {{ background: {tema['janela']}; color: {tema['texto']}; }}
            QGroupBox {{
                border: 1px solid {tema['borda']};
                border-radius: 6px;
                margin-top: 18px;
                background: {tema['painel']};
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                top: 1px;
                padding: 0 4px;
                background: {tema['janela']};
                color: {tema['texto']};
            }}
            QLabel, QCheckBox {{ color: {tema['texto']}; }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {tema['borda']};
                background: #ffffff;
            }}
            QCheckBox::indicator:hover {{ border: 1px solid {tema['primaria']}; }}
            QCheckBox::indicator:checked {{
                image: url(__CHECK_ICON__);
                background: #ffffff;
                border: 1px solid {tema['primaria_escura']};
            }}
            QPushButton, QComboBox, QLineEdit, QTextEdit {{
                background: {tema['painel']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
                border-radius: 4px;
                min-height: 24px;
                padding: 3px 7px;
            }}
            QPushButton:hover {{ background: {tema['hover']}; border-color: {tema['primaria']}; }}
            QPushButton:pressed {{ background: {tema['selecionado']}; }}
            QListView, QTreeView, QListWidget {{
                background: {tema['painel']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
                selection-background-color: {tema['selecionado']};
                selection-color: {tema['texto']};
                alternate-background-color: {tema['faixa']};
            }}
            QHeaderView::section {{
                background: {tema['faixa']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
                padding: 4px;
                font-weight: 600;
            }}
            QTableWidget {{
                background: {tema['painel']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
                gridline-color: {tema['borda']};
            }}
            """
            .replace("__CHECK_ICON__", check_icon)
        )

    def _centralizar_dialogo_na_janela(self, dialog: QDialog):
        dialog.adjustSize()
        tela = self.screen() or QApplication.primaryScreen()
        area_disponivel = tela.availableGeometry() if tela is not None else None
        if area_disponivel is not None:
            largura_max = max(320, area_disponivel.width() - 32)
            altura_max = max(240, area_disponivel.height() - 32)
            if dialog.width() > largura_max or dialog.height() > altura_max:
                dialog.resize(min(dialog.width(), largura_max), min(dialog.height(), altura_max))

        geo_dialogo = dialog.frameGeometry()
        if area_disponivel is not None:
            geo_dialogo.moveCenter(area_disponivel.center())
        else:
            geo_dialogo.moveCenter(self.frameGeometry().center())
        if area_disponivel is not None:
            if geo_dialogo.left() < area_disponivel.left():
                geo_dialogo.moveLeft(area_disponivel.left())
            if geo_dialogo.top() < area_disponivel.top():
                geo_dialogo.moveTop(area_disponivel.top())
            if geo_dialogo.right() > area_disponivel.right():
                geo_dialogo.moveRight(area_disponivel.right())
            if geo_dialogo.bottom() > area_disponivel.bottom():
                geo_dialogo.moveBottom(area_disponivel.bottom())
        dialog.move(geo_dialogo.topLeft())

    def _dimensionar_dialogo_para_tela(
        self,
        dialog: QDialog,
        largura_preferida: int,
        altura_preferida: int,
        largura_minima: int,
        altura_minima: int,
    ):
        tela = self.screen() or QApplication.primaryScreen()
        if tela is None:
            dialog.setMinimumSize(largura_minima, altura_minima)
            dialog.resize(largura_preferida, altura_preferida)
            return
        area = tela.availableGeometry()
        largura_max = max(640, area.width() - 80)
        altura_max = max(480, area.height() - 80)
        largura = min(largura_preferida, largura_max)
        altura = min(altura_preferida, altura_max)
        dialog.setMinimumSize(min(largura_minima, largura), min(altura_minima, altura))
        dialog.resize(largura, altura)

    def _centralizar_widget_na_tela(self, widget: QWidget):
        widget.adjustSize()
        tela = None
        try:
            if widget.windowHandle() is not None:
                tela = widget.windowHandle().screen()
        except Exception:
            tela = None
        if tela is None:
            tela = self.screen()
        if tela is None:
            if isinstance(widget, QDialog):
                self._centralizar_dialogo_na_janela(widget)
            return
        geo_tela = tela.availableGeometry()
        geo_widget = widget.frameGeometry()
        geo_widget.moveCenter(geo_tela.center())
        widget.move(geo_widget.topLeft())

    def _forcar_dialogo_arquivo_claro(self, dialog: QFileDialog, *, texto_acao: str | None = None):
        self._aplicar_estilo_claro_dialogo(dialog)
        self._traduzir_rotulos_dialogo_arquivo(dialog, texto_acao=texto_acao)
        self._traduzir_textos_internos_dialogo_arquivo(dialog)
        self._melhorar_coluna_nome_dialogo_arquivo(dialog)

    def _traduzir_rotulos_dialogo_arquivo(self, dialog: QFileDialog, *, texto_acao: str | None = None):
        look_in = "Examinar:" if (texto_acao or "Abrir") == "Abrir" else "Salvar em:"
        dialog.setLabelText(QFileDialog.DialogLabel.LookIn, look_in)
        dialog.setLabelText(QFileDialog.DialogLabel.FileName, "Nome:")
        dialog.setLabelText(QFileDialog.DialogLabel.FileType, "Tipo:")
        dialog.setLabelText(QFileDialog.DialogLabel.Reject, "Cancelar")
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, texto_acao or "Abrir")

    def _melhorar_coluna_nome_dialogo_arquivo(self, dialog: QFileDialog):
        for arvore in dialog.findChildren(QTreeView):
            try:
                arvore.setColumnWidth(0, 420)
                header = arvore.header()
                if header is not None:
                    header.setStretchLastSection(False)
                    header.resizeSection(0, 420)
            except Exception:
                pass

    def _traduzir_textos_internos_dialogo_arquivo(self, dialog: QFileDialog):
        mapa_botoes = {
            "open": "Abrir",
            "&open": "Abrir",
            "choose": "Selecionar",
            "&choose": "Selecionar",
            "cancel": "Cancelar",
            "&cancel": "Cancelar",
        }
        for botao in dialog.findChildren(QPushButton):
            txt = botao.text().strip()
            chave = txt.lower()
            if chave in mapa_botoes:
                botao.setText(mapa_botoes[chave])

        colunas_pt = {
            "name": "Nome",
            "size": "Tamanho",
            "type": "Tipo",
            "date modified": "Data de modificação",
        }
        for arvore in dialog.findChildren(QTreeView):
            modelo = arvore.model()
            if modelo is None:
                continue
            try:
                for col in range(min(8, modelo.columnCount())):
                    atual = str(modelo.headerData(col, Qt.Horizontal) or "").strip()
                    novo = colunas_pt.get(atual.lower())
                    if novo:
                        modelo.setHeaderData(col, Qt.Horizontal, novo)
                self._traduzir_itens_modelo(modelo)
            except Exception:
                pass
        delegate = _DelegateTraducaoArquivo(dialog)
        for view in dialog.findChildren(QAbstractItemView):
            try:
                view.setItemDelegate(delegate)
            except Exception:
                pass

    def _traduzir_itens_modelo(self, modelo):
        mapa = {
            "my computer": "Este Computador",
            "desktop": "Área de Trabalho",
            "documents": "Documentos",
            "downloads": "Downloads",
            "network": "Rede",
            "home": "Início",
            "directories": "Diretórios",
        }

        def _visitar(indice_pai):
            try:
                linhas = modelo.rowCount(indice_pai)
            except Exception:
                return
            for linha in range(linhas):
                idx = modelo.index(linha, 0, indice_pai)
                txt = str(modelo.data(idx) or "").strip()
                traduzido = mapa.get(txt.lower())
                if traduzido:
                    try:
                        modelo.setData(idx, traduzido)
                    except Exception:
                        pass
                _visitar(idx)

        _visitar(QModelIndex())

    def _abrir_dialogo_arquivo_claro(
        self,
        titulo: str,
        filtro: str,
        *,
        modo_salvar: bool = False,
        com_preview_projeto: bool = False,
    ) -> tuple[str, str]:
        filtros = [parte.strip() for parte in str(filtro or "").split(";;") if parte.strip()]
        filtro_eh_projeto = any(f"*{EXTENSAO_PROJETO}" in parte for parte in filtros)
        if filtro_eh_projeto:
            filtros = [f"Projeto GUIMMA (*{EXTENSAO_PROJETO})"]
        filtro_inicial = filtros[0] if filtros else filtro
        dialog = QFileDialog(self, titulo, self._diretorio_arquivo_inicial(), filtro_inicial)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        if filtros:
            dialog.setNameFilters(filtros)
            dialog.selectNameFilter(filtro_inicial)
        if any(f"*{EXTENSAO_PROJETO}" in parte for parte in filtros):
            dialog.setDefaultSuffix(EXTENSAO_PROJETO.lstrip("."))
        self._dimensionar_dialogo_para_tela(dialog, 1320, 820, 900, 620)
        if modo_salvar:
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            dialog.setFileMode(QFileDialog.FileMode.AnyFile)
            self._traduzir_rotulos_dialogo_arquivo(dialog, texto_acao="Salvar")
        else:
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            self._traduzir_rotulos_dialogo_arquivo(dialog, texto_acao="Abrir")
        self._forcar_dialogo_arquivo_claro(dialog, texto_acao="Salvar" if modo_salvar else "Abrir")
        if filtro_eh_projeto:
            self._aplicar_filtro_extensao_dialogo_arquivo(dialog, filtro_inicial, [EXTENSAO_PROJETO])
            QTimer.singleShot(
                0,
                lambda: self._aplicar_filtro_extensao_dialogo_arquivo(
                    dialog, filtro_inicial, [EXTENSAO_PROJETO]
                ),
            )
        if com_preview_projeto and not modo_salvar:
            self._anexar_preview_dialogo_arquivo(dialog)
        self._centralizar_dialogo_na_janela(dialog)
        if dialog.exec() != QDialog.Accepted:
            self._agendar_reencaixe_janela_canvas()
            return "", ""
        arquivos = dialog.selectedFiles()
        caminho = arquivos[0] if arquivos else ""
        if filtro_eh_projeto and caminho and Path(caminho).suffix.lower() != EXTENSAO_PROJETO.lower():
            QMessageBox.warning(
                self,
                "Arquivo incompatível",
                f"Selecione um projeto GUIMMA (*{EXTENSAO_PROJETO}).",
            )
            self._agendar_reencaixe_janela_canvas()
            return "", ""
        if caminho:
            self._memorizar_diretorio_arquivo(Path(caminho))
        self._agendar_reencaixe_janela_canvas()
        return caminho, dialog.selectedNameFilter()

    def _filtros_importacao_moldes(self) -> list[str]:
        return [
            "Arquivos DXF (*.dxf)",
            "Arquivos AMA (*.ama)",
            "Arquivos AAM (*.aam)",
            "Arquivos ASM (*.asm)",
            "Arquivos AST (*.ast)",
            "Todos (*.*)",
        ]

    def _origens_importacao_moldes(self) -> list[str]:
        return [
            "Padrao (ASTM)",
            "Gerber",
            "Investronica",
            "Ioline vs 4.x",
            "Lectra",
            "Pad System",
            "Polytropon",
            "OptiTex",
            "AutoCad",
            "Assyst",
        ]

    def _opcoes_importacao_moldes_padrao(self, origem_inicial: str | None = None) -> dict:
        prefs = self.projeto_atual.preferencias_usuario.get("importacao_moldes", {})
        if not isinstance(prefs, dict):
            prefs = {}
        unidade = str(prefs.get("unidade", "cm")).lower()
        if unidade not in {"mm", "cm", "pol"}:
            unidade = "cm"
        origem = str(prefs.get("origem", "Padrao (ASTM)"))
        if origem_inicial:
            origem = str(origem_inicial)
        if origem not in self._origens_importacao_moldes():
            origem = "Padrao (ASTM)"
        return {
            "unidade": unidade,
            "origem": origem,
            "importar_mesmo_arquivo": bool(prefs.get("importar_mesmo_arquivo", False)),
            "importar_linha_costura": bool(prefs.get("importar_linha_costura", False)),
            "usar_contorno_corte_como_base": bool(prefs.get("usar_contorno_corte_como_base", True)),
        }

    def _abrir_dialogo_importacao_moldes(self, tipo: str, origem_inicial: str | None = None) -> tuple[str, str, dict]:
        filtros = self._filtros_importacao_moldes()
        filtro_inicial = filtros[0]
        titulo = "Importar AAMA-292/1993 | ASTM D6673-01/2001" if tipo == "aama_astm" else "Importar DXF"
        dialog = QFileDialog(self, titulo, self._diretorio_arquivo_inicial(), filtro_inicial)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        dialog.setNameFilters(filtros)
        dialog.selectNameFilter(filtro_inicial)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        self._traduzir_rotulos_dialogo_arquivo(dialog, texto_acao="Abrir")
        self._forcar_dialogo_arquivo_claro(dialog, texto_acao="Abrir")
        self._dimensionar_dialogo_para_tela(dialog, 900, 620, 640, 480)
        controles = self._anexar_opcoes_importacao_moldes(dialog, origem_inicial=origem_inicial)
        self._centralizar_dialogo_na_janela(dialog)
        if dialog.exec() != QDialog.Accepted:
            self._agendar_reencaixe_janela_canvas()
            return "", "", {}
        arquivos = dialog.selectedFiles()
        caminho = arquivos[0] if arquivos else ""
        if caminho:
            self._memorizar_diretorio_arquivo(Path(caminho))
        opcoes = {
            "unidade": "mm" if controles["rb_mm"].isChecked() else ("pol" if controles["rb_pol"].isChecked() else "cm"),
            "origem": controles["cmb_origem"].currentText(),
            "importar_mesmo_arquivo": controles["chk_mesmo"].isChecked(),
            "importar_linha_costura": controles["chk_costura"].isChecked(),
            "usar_contorno_corte_como_base": controles["chk_contorno_base"].isChecked(),
            "tipo_filtro": dialog.selectedNameFilter(),
        }
        self.projeto_atual.preferencias_usuario["importacao_moldes"] = dict(opcoes)
        self._salvar_preferencias_app()
        self._agendar_reencaixe_janela_canvas()
        return caminho, dialog.selectedNameFilter(), opcoes

    def _anexar_opcoes_importacao_moldes(self, dialog: QFileDialog, origem_inicial: str | None = None) -> dict:
        layout = dialog.layout()
        opcoes = self._opcoes_importacao_moldes_padrao(origem_inicial=origem_inicial)
        painel = QFrame(dialog)
        painel.setObjectName("ImportacaoMoldesOptionsPanel")
        painel.setStyleSheet(
            """
            QFrame#ImportacaoMoldesOptionsPanel {
                border-top: 1px solid #b7c4cf;
                background: transparent;
            }
            """
        )
        grid = QGridLayout(painel)
        grid.setContentsMargins(4, 8, 4, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        gb_unidade = QGroupBox("Unidade", painel)
        lay_unidade = QHBoxLayout(gb_unidade)
        rb_mm = QRadioButton("mm", gb_unidade)
        rb_cm = QRadioButton("cm", gb_unidade)
        rb_pol = QRadioButton("pol", gb_unidade)
        for rb in (rb_mm, rb_cm, rb_pol):
            lay_unidade.addWidget(rb)
        lay_unidade.addStretch(1)
        {"mm": rb_mm, "cm": rb_cm, "pol": rb_pol}.get(opcoes["unidade"], rb_cm).setChecked(True)

        gb_origem = QGroupBox("Origem", painel)
        lay_origem = QVBoxLayout(gb_origem)
        cmb_origem = QComboBox(gb_origem)
        cmb_origem.addItems(self._origens_importacao_moldes())
        cmb_origem.setCurrentText(opcoes["origem"])
        lay_origem.addWidget(cmb_origem)
        chk_mesmo = QCheckBox("Importar no mesmo arquivo", gb_origem)
        chk_mesmo.setChecked(bool(opcoes["importar_mesmo_arquivo"]))
        lay_origem.addWidget(chk_mesmo)

        chk_costura = QCheckBox("Importar linha de costura", painel)
        chk_costura.setChecked(bool(opcoes["importar_linha_costura"]))
        chk_contorno_base = QCheckBox("Use contorno de corte como contorno base", painel)
        chk_contorno_base.setChecked(bool(opcoes["usar_contorno_corte_como_base"]))

        grid.addWidget(gb_unidade, 0, 0)
        grid.addWidget(gb_origem, 0, 1, 1, 2)
        grid.addWidget(chk_costura, 1, 0, 1, 3)
        grid.addWidget(chk_contorno_base, 2, 0, 1, 3)
        grid.setColumnStretch(1, 1)

        if isinstance(layout, QGridLayout):
            linha = layout.rowCount()
            layout.addWidget(painel, linha, 0, 1, layout.columnCount())
        elif layout is not None:
            layout.addWidget(painel)

        return {
            "rb_mm": rb_mm,
            "rb_cm": rb_cm,
            "rb_pol": rb_pol,
            "cmb_origem": cmb_origem,
            "chk_mesmo": chk_mesmo,
            "chk_costura": chk_costura,
            "chk_contorno_base": chk_contorno_base,
        }

    def _preparar_elementos_importacao_moldes(self, elementos: list[dict], opcoes: dict) -> list[dict]:
        unidade = str(opcoes.get("unidade", "cm")).lower()
        fator = {"mm": 0.1, "cm": 1.0, "pol": 2.54}.get(unidade, 1.0)
        preparados: list[dict] = []
        for el in elementos:
            if not isinstance(el, dict):
                continue
            novo = deepcopy(el)
            pontos = novo.get("pontos")
            if isinstance(pontos, list) and fator != 1.0:
                novo["pontos"] = [self._escalar_ponto_importado(pt, fator) for pt in pontos]
            novo["unidade_origem"] = unidade
            novo["origem_importacao"] = str(opcoes.get("origem", "Padrao (ASTM)"))
            novo["tipo_filtro_importacao"] = str(opcoes.get("tipo_filtro", ""))
            novo["importar_linha_costura"] = bool(opcoes.get("importar_linha_costura", False))
            novo["usar_contorno_corte_como_base"] = bool(opcoes.get("usar_contorno_corte_como_base", True))
            novo["subtipo_importacao"] = "costura" if novo["importar_linha_costura"] else "contorno_corte"
            preparados.append(novo)
        return preparados

    @staticmethod
    def _escalar_ponto_importado(ponto, fator: float):
        try:
            x, y = ponto
            return (float(x) * fator, float(y) * fator)
        except Exception:
            return ponto

    def _aplicar_filtro_extensao_dialogo_arquivo(
        self,
        dialog: QFileDialog,
        filtro_nome: str,
        extensoes: list[str],
    ):
        padroes: list[str] = []
        for ext in extensoes:
            texto = str(ext or "").strip()
            if not texto:
                continue
            if texto.startswith("*"):
                padrao = texto
            else:
                if not texto.startswith("."):
                    texto = f".{texto}"
                padrao = f"*{texto}"
            if padrao not in padroes:
                padroes.append(padrao)
        if not padroes:
            return

        try:
            dialog.setNameFilters([filtro_nome])
            dialog.selectNameFilter(filtro_nome)
        except Exception:
            pass

        for combo in dialog.findChildren(QComboBox):
            try:
                itens = [combo.itemText(i) for i in range(combo.count())]
            except Exception:
                continue
            if any(padrao in item for padrao in padroes for item in itens):
                combo.setMinimumWidth(max(combo.minimumWidth(), 260))
                try:
                    combo.view().setMinimumWidth(max(combo.view().minimumWidth(), 320))
                except Exception:
                    pass

        for modelo in self._modelos_sistema_arquivos_dialogo(dialog):
            try:
                modelo.setNameFilters(padroes)
                modelo.setNameFilterDisables(False)
            except Exception:
                pass

    def _modelos_sistema_arquivos_dialogo(self, dialog: QFileDialog) -> list[QFileSystemModel]:
        modelos: list[QFileSystemModel] = []

        def _adicionar(modelo):
            sistema = self._modelo_sistema_arquivos(modelo)
            if sistema is not None and not any(sistema is existente for existente in modelos):
                modelos.append(sistema)

        for modelo in dialog.findChildren(QFileSystemModel):
            _adicionar(modelo)
        for view in dialog.findChildren(QAbstractItemView):
            try:
                _adicionar(view.model())
            except Exception:
                pass
        return modelos

    def _modelo_sistema_arquivos(self, modelo) -> QFileSystemModel | None:
        visitados: set[int] = set()
        atual = modelo
        while atual is not None:
            identificador = id(atual)
            if identificador in visitados:
                return None
            visitados.add(identificador)
            if isinstance(atual, QFileSystemModel):
                return atual
            origem = getattr(atual, "sourceModel", None)
            if not callable(origem):
                return None
            try:
                atual = origem()
            except Exception:
                return None

    def _diretorio_arquivo_inicial(self) -> str:
        ultimo = self.projeto_atual.preferencias_usuario.get("ultimo_diretorio_arquivo", "")
        if isinstance(ultimo, str) and ultimo.strip():
            return ultimo
        if self._arquivo_atual is not None:
            return str(self._arquivo_atual.parent)
        return str(Path.home())

    def _memorizar_diretorio_arquivo(self, caminho: Path):
        pasta = caminho if caminho.is_dir() else caminho.parent
        self.projeto_atual.preferencias_usuario["ultimo_diretorio_arquivo"] = str(pasta)
        self._salvar_preferencias_app()

    def _anexar_preview_dialogo_arquivo(self, dialog: QFileDialog):
        layout = dialog.layout()
        if not isinstance(layout, QGridLayout):
            return
        tema = self._tema_interface()
        painel = QFrame(dialog)
        painel.setObjectName("PreviewArquivoPanel")
        painel.setMinimumWidth(430)
        painel.setStyleSheet(
            f"""
            QFrame#PreviewArquivoPanel {{
                background: {tema['painel']};
                border: 1px solid {tema['borda']};
                border-radius: 6px;
            }}
            QLabel#PreviewArquivoTitulo {{
                color: {tema['primaria_escura']};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#PreviewArquivoImagem {{
                background: #050607;
                color: {tema['texto_suave']};
                border: 1px solid {tema['borda']};
                border-radius: 4px;
            }}
            QLabel#PreviewArquivoInfo {{
                color: {tema['texto']};
                background: {tema['faixa']};
                border: 1px solid {tema['borda']};
                border-radius: 4px;
                padding: 7px 9px;
            }}
            """
        )
        box = QVBoxLayout(painel)
        box.setContentsMargins(10, 10, 10, 10)
        box.setSpacing(8)
        lbl_titulo = QLabel("Pré-visualização", painel)
        lbl_titulo.setObjectName("PreviewArquivoTitulo")
        lbl_img = QLabel(f"Selecione um arquivo *{EXTENSAO_PROJETO}", painel)
        lbl_img.setObjectName("PreviewArquivoImagem")
        lbl_img.setAlignment(Qt.AlignCenter)
        lbl_img.setMinimumSize(400, 500)
        lbl_info = QLabel("A prévia mostra contorno, fio e graduação quando existirem.", painel)
        lbl_info.setObjectName("PreviewArquivoInfo")
        lbl_info.setWordWrap(True)
        box.addWidget(lbl_titulo)
        box.addWidget(lbl_img, 1)
        box.addWidget(lbl_info)

        row_count = max(1, layout.rowCount())
        col_count = max(1, layout.columnCount())
        layout.addWidget(painel, 0, col_count, row_count, 1)

        def _atualizar(caminho: str):
            caminho_path = Path(caminho) if caminho else None
            pix = self._carregar_preview_do_projeto(caminho_path) if caminho_path else None
            if pix is None:
                lbl_img.setText("Sem prévia")
                lbl_img.setPixmap(QPixmap())
                lbl_info.setText("Selecione um projeto .gs para ver detalhes do arquivo.")
                return
            lbl_img.setText("")
            lbl_img.setPixmap(pix.scaled(lbl_img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl_info.setText(self._resumo_preview_do_projeto(caminho_path))

        dialog.currentChanged.connect(_atualizar)
        arquivos = dialog.selectedFiles()
        if arquivos:
            _atualizar(arquivos[0])

    def _criptografar_preview(self, dados: bytes) -> bytes:
        chave = b"GUIMMA_PREVIEW_V1"
        return bytes(b ^ chave[i % len(chave)] for i, b in enumerate(dados))

    def _descriptografar_preview(self, dados: bytes) -> bytes:
        return self._criptografar_preview(dados)

    def _carregar_preview_do_projeto(self, caminho: Path) -> QPixmap | None:
        if not caminho.exists() or caminho.suffix.lower() != EXTENSAO_PROJETO.lower():
            return None
        elementos = self._elementos_preview_do_projeto(caminho)
        if elementos:
            imagem = self._gerar_thumbnail_elementos(elementos, largura=960, altura=540)
            if imagem is not None:
                return QPixmap.fromImage(imagem)
        try:
            with ZipFile(caminho, mode="r") as pacote:
                nomes = set(pacote.namelist())
                if "preview/thumbnail.enc" in nomes:
                    bruto = pacote.read("preview/thumbnail.enc")
                    png = self._descriptografar_preview(bruto)
                elif "preview/thumbnail.png" in nomes:
                    png = pacote.read("preview/thumbnail.png")
                elif "thumbnail.png" in nomes:
                    png = pacote.read("thumbnail.png")
                else:
                    return None
        except Exception:
            return None
        img = QImage.fromData(png, "PNG")
        if img.isNull():
            return None
        return QPixmap.fromImage(img)

    def _elementos_preview_do_projeto(self, caminho: Path) -> list[dict]:
        try:
            with ZipFile(caminho, mode="r") as pacote:
                dados = json.loads(pacote.read(GSProjectIO.PROJECT_FILE).decode("utf-8"))
        except Exception:
            return []
        prefs = dados.get("preferencias_usuario", {}) if isinstance(dados, dict) else {}
        docs = prefs.get("documentos_canvas", []) if isinstance(prefs, dict) else []
        if not isinstance(docs, list):
            return []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            elementos = doc.get("elementos", [])
            if isinstance(elementos, list) and elementos:
                return [dict(el) for el in elementos if isinstance(el, dict)]
        return []

    def _resumo_preview_do_projeto(self, caminho: Path | None) -> str:
        if caminho is None:
            return "Selecione um projeto .gs para ver detalhes do arquivo."
        elementos = self._elementos_preview_do_projeto(caminho)
        if not elementos:
            return "Projeto .gs sem elementos de canvas para pré-visualizar."
        moldes = [el for el in elementos if bool(el.get("molde"))]
        graduados = [
            el for el in moldes
            if el.get("graduacao_tamanhos") or el.get("graduacao_tabela") or el.get("graduacao_pontos")
        ]
        com_fio = [
            el for el in moldes
            if el.get("fio_origem") and el.get("fio_fim") and el.get("mostrar_fio", True) is not False
        ]
        linhas = [
            f"{len(moldes)} molde(s)",
            f"{len(elementos)} elemento(s)",
            f"{len(graduados)} com graduação",
            f"{len(com_fio)} com fio",
        ]
        return " • ".join(linhas)


    def _nome_documento_ativo_saida(self) -> str:
        area = self._area_documento_atual()
        if not area:
            return "Sem nome"
        indice = self.abas_documentos.currentIndex()
        nome = self.abas_documentos.tabText(indice) if indice >= 0 else "Sem nome"
        nome = (nome or "Sem nome").strip()
        proibidos = '<>:"/\\|?*'
        for ch in proibidos:
            nome = nome.replace(ch, "_")
        return nome or "Sem nome"

    def _obter_elementos_saida(self, apenas_selecionados: bool = False) -> list[dict]:
        area = self._area_documento_atual()
        if not area:
            return []
        elementos = list(getattr(area.canvas.cena, 'elementos', []) or [])
        if not apenas_selecionados:
            return [dict(el) for el in elementos]
        selecionados = [
            dict(el)
            for el in elementos
            if bool(el.get('selecionado') or el.get('selected') or el.get('is_selected'))
        ]
        return selecionados

    def _polilinhas_elemento_saida(self, el: dict, segmentos_curva: int = 32, segmentos_circulo: int = 48) -> list[list[tuple[float, float]]]:
        tipo = str(el.get('tipo') or '').lower()
        if tipo == 'polyline':
            pontos = [(float(x), float(y)) for x, y in el.get('pontos', []) if isinstance((x, y), tuple)]
            if len(pontos) >= 2:
                return [pontos]
            return []
        if tipo == 'bezier_quadratica':
            p0 = el.get('p0')
            p1 = el.get('p1')
            p2 = el.get('p2')
            if not all(isinstance(p, (tuple, list)) and len(p) == 2 for p in (p0, p1, p2)):
                return []
            x0, y0 = float(p0[0]), float(p0[1])
            x1, y1 = float(p1[0]), float(p1[1])
            x2, y2 = float(p2[0]), float(p2[1])
            pts: list[tuple[float, float]] = []
            for i in range(segmentos_curva + 1):
                t = i / segmentos_curva
                mt = 1.0 - t
                x = (mt * mt * x0) + (2.0 * mt * t * x1) + (t * t * x2)
                y = (mt * mt * y0) + (2.0 * mt * t * y1) + (t * t * y2)
                pts.append((x, y))
            return [pts]
        if tipo in {'circle', 'esfera'}:
            centro = el.get('centro')
            raio = float(el.get('raio', 0.0))
            if not (isinstance(centro, (tuple, list)) and len(centro) == 2 and raio > 0):
                return []
            cx, cy = float(centro[0]), float(centro[1])
            pts = []
            for i in range(segmentos_circulo + 1):
                ang = (2.0 * pi * i) / segmentos_circulo
                pts.append((cx + cos(ang) * raio, cy + sin(ang) * raio))
            return [pts]
        return []

    def _bbox_elementos_saida(self, elementos: list[dict]) -> tuple[float, float, float, float] | None:
        pontos: list[tuple[float, float]] = []
        for el in elementos:
            for linha in self._polilinhas_elemento_saida(el):
                pontos.extend(linha)
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    def _ajustar_retangulo_margens_cm(self, rect: QRectF, margem_esq: float, margem_sup: float, margem_dir: float, margem_inf: float, dpi_x: float, dpi_y: float) -> QRectF:
        px_esq = (margem_esq / 2.54) * dpi_x
        px_dir = (margem_dir / 2.54) * dpi_x
        px_sup = (margem_sup / 2.54) * dpi_y
        px_inf = (margem_inf / 2.54) * dpi_y
        ajustado = QRectF(rect)
        ajustado.adjust(px_esq, px_sup, -px_dir, -px_inf)
        return ajustado

    def _desenhar_elementos_em_painter(self, painter: QPainter, rect: QRectF, elementos: list[dict], config: dict):
        bbox = self._bbox_elementos_saida(elementos)
        if bbox is None:
            return
        min_x, min_y, max_x, max_y = bbox
        largura = max(max_x - min_x, 1.0)
        altura = max(max_y - min_y, 1.0)
        area = QRectF(rect)
        margem_esq = float(config.get('margem_esq', 0.0))
        margem_sup = float(config.get('margem_sup', 0.0))
        margem_dir = float(config.get('margem_dir', 0.0))
        margem_inf = float(config.get('margem_inf', 0.0))
        dpi_x = float(getattr(painter.device(), 'logicalDpiX', lambda: 96)())
        dpi_y = float(getattr(painter.device(), 'logicalDpiY', lambda: 96)())
        area = self._ajustar_retangulo_margens_cm(area, margem_esq, margem_sup, margem_dir, margem_inf, dpi_x, dpi_y)
        if area.width() <= 1 or area.height() <= 1:
            area = QRectF(rect)

        girar_90 = bool(config.get('girar_90', False))
        fator_x = max(0.01, float(config.get('escala_x', 1.0)))
        fator_y = max(0.01, float(config.get('escala_y', 1.0)))
        usar_percent = bool(config.get('usar_percentual', False))
        percentual = max(0.01, float(config.get('percentual', 100.0))) / 100.0
        escala_base = min(area.width() / (altura if girar_90 else largura), area.height() / (largura if girar_90 else altura))
        escala = escala_base * (percentual if usar_percent else 1.0)
        centro_x = (min_x + max_x) / 2.0
        centro_y = (min_y + max_y) / 2.0
        cor_unica = not bool(config.get('em_cores', False))

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(area.center())
        if girar_90:
            painter.rotate(90)
        painter.scale(escala * fator_x, -(escala * fator_y))
        painter.translate(-centro_x, -centro_y)

        for el in elementos:
            cor = '#000000'
            if not cor_unica:
                cor = str(el.get('cor') or el.get('stroke') or el.get('line_color') or '#000000')
            pen = QPen(QColor(cor))
            pen.setWidthF(0.0)
            painter.setPen(pen)
            for linha in self._polilinhas_elemento_saida(el):
                if len(linha) < 2:
                    continue
                path = QPainterPath()
                path.moveTo(linha[0][0], linha[0][1])
                for x, y in linha[1:]:
                    path.lineTo(x, y)
                painter.drawPath(path)
        painter.restore()

        estilo_borda = str(config.get('estilo_borda') or 'nenhum')
        if estilo_borda != 'nenhum':
            painter.save()
            pen = QPen(QColor('#5a5a5a'))
            if estilo_borda == 'tracejada':
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.drawRect(area)
            elif estilo_borda == 'cantos':
                pen.setWidth(1)
                painter.setPen(pen)
                canto = min(area.width(), area.height()) * 0.10
                x1, y1, x2, y2 = area.left(), area.top(), area.right(), area.bottom()
                painter.drawLine(x1, y1, x1 + canto, y1)
                painter.drawLine(x1, y1, x1, y1 + canto)
                painter.drawLine(x2 - canto, y1, x2, y1)
                painter.drawLine(x2, y1, x2, y1 + canto)
                painter.drawLine(x1, y2 - canto, x1, y2)
                painter.drawLine(x1, y2, x1 + canto, y2)
                painter.drawLine(x2 - canto, y2, x2, y2)
                painter.drawLine(x2, y2 - canto, x2, y2)
            painter.restore()

    def _desenhar_documento_impressao(self, printer: QPrinter, config: dict):
        elementos = self._obter_elementos_saida(bool(config.get('apenas_selecionados', False)))
        if not elementos:
            return
        painter = QPainter(printer)
        try:
            rect = QRectF(printer.pageRect(QPrinter.Unit.DevicePixel))
            self._desenhar_elementos_em_painter(painter, rect, elementos, config)
        finally:
            painter.end()

    def _executar_impressao(self, config: dict, visualizar: bool):
        elementos = self._obter_elementos_saida(bool(config.get('apenas_selecionados', False)))
        if not elementos:
            caixa = QMessageBox(self)
            self._estilizar_message_box(caixa)
            caixa.setWindowTitle('Impressão')
            caixa.setIcon(QMessageBox.Information)
            caixa.setText('Não há elementos disponíveis para impressão.')
            caixa.exec()
            return
        printer = QPrinter(QPrinter.HighResolution)
        if visualizar:
            preview = QPrintPreviewDialog(printer, self)
            preview.setWindowTitle('Visualizar impressão')
            preview.paintRequested.connect(lambda pr: self._desenhar_documento_impressao(pr, config))
            preview.exec()
            return
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle('Imprimir')
        if dialog.exec() == QDialog.Accepted:
            self._desenhar_documento_impressao(printer, config)
            self.lbl_status.setText('Impressão enviada.')

    def _abrir_dialogo_impressao(self):
        area = self._area_documento_atual()
        if not area or not getattr(area.canvas.cena, 'elementos', None):
            caixa = QMessageBox(self)
            self._estilizar_message_box(caixa)
            caixa.setWindowTitle('Impressão')
            caixa.setIcon(QMessageBox.Information)
            caixa.setText('Abra um documento com elementos antes de imprimir.')
            caixa.exec()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle('Impressão')
        dialog.setModal(True)
        dialog.resize(420, 560)
        self._aplicar_estilo_claro_dialogo(dialog)
        lay = QVBoxLayout(dialog)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        topo = QHBoxLayout()
        gb_impressao = QGroupBox('Impressão')
        g_imp = QVBoxLayout(gb_impressao)
        rb_tudo = QRadioButton('Tudo')
        rb_tudo.setChecked(True)
        rb_sel = QRadioButton('Selecionados')
        tem_sel = bool(self._obter_elementos_saida(True))
        rb_sel.setEnabled(tem_sel)
        g_imp.addWidget(rb_tudo)
        g_imp.addWidget(rb_sel)
        topo.addWidget(gb_impressao)

        gb_prop = QGroupBox('Proporção')
        g_prop = QVBoxLayout(gb_prop)
        rb_tamanho_folha = QRadioButton('Tamanho da folha')
        rb_tamanho_folha.setChecked(True)
        linha_pct = QHBoxLayout()
        rb_percent = QRadioButton('Porcentagem')
        edt_percent = QDoubleSpinBox()
        edt_percent.setDecimals(2)
        edt_percent.setRange(1.0, 1000.0)
        edt_percent.setValue(100.0)
        edt_percent.setSuffix(' %')
        edt_percent.setEnabled(False)
        rb_percent.toggled.connect(edt_percent.setEnabled)
        linha_pct.addWidget(rb_percent)
        linha_pct.addWidget(edt_percent, 1)
        g_prop.addWidget(rb_tamanho_folha)
        g_prop.addLayout(linha_pct)
        topo.addWidget(gb_prop, 1)
        lay.addLayout(topo)

        gb_fatores = QGroupBox('Fatores de escala')
        g_fat = QGridLayout(gb_fatores)
        edt_x = QDoubleSpinBox()
        edt_x.setDecimals(3)
        edt_x.setRange(0.001, 1000.0)
        edt_x.setValue(1.0)
        edt_y = QDoubleSpinBox()
        edt_y.setDecimals(3)
        edt_y.setRange(0.001, 1000.0)
        edt_y.setValue(1.0)
        chk_cores = QCheckBox('Em cores')
        g_fat.addWidget(QLabel('X'), 0, 0)
        g_fat.addWidget(edt_x, 0, 1)
        g_fat.addWidget(QLabel('Y'), 0, 2)
        g_fat.addWidget(edt_y, 0, 3)
        g_fat.addWidget(chk_cores, 0, 4)
        lay.addWidget(gb_fatores)

        gb_moldes = QGroupBox('Opções dos Moldes')
        g_moldes = QGridLayout(gb_moldes)
        g_moldes.addWidget(QLabel('Selecionar tamanhos'), 0, 0)
        cmb_tamanhos = QComboBox()
        cmb_tamanhos.addItems(['Todos'])
        g_moldes.addWidget(cmb_tamanhos, 0, 1)
        chk_reorg = QCheckBox('Reorganizar moldes')
        g_moldes.addWidget(chk_reorg, 1, 0, 1, 2)
        lay.addWidget(gb_moldes)

        meio = QHBoxLayout()
        gb_margens = QGroupBox('Margens (cm)')
        gb_margens.setMinimumHeight(240)
        g_marg = QGridLayout(gb_margens)
        edt_sup = QDoubleSpinBox()
        edt_sup.setRange(0.0, 99.0)
        edt_sup.setDecimals(2)
        edt_sup.setValue(0.0)
        edt_esq = QDoubleSpinBox()
        edt_esq.setRange(0.0, 99.0)
        edt_esq.setDecimals(2)
        edt_esq.setValue(0.0)
        edt_dir = QDoubleSpinBox()
        edt_dir.setRange(0.0, 99.0)
        edt_dir.setDecimals(2)
        edt_dir.setValue(0.0)
        edt_inf = QDoubleSpinBox()
        edt_inf.setRange(0.0, 99.0)
        edt_inf.setDecimals(2)
        edt_inf.setValue(0.0)
        area_pagina = QFrame()
        area_pagina.setFixedSize(86, 110)
        area_pagina.setStyleSheet('background:#ececec;border:1px solid #cfcfcf;')
        g_marg.addWidget(edt_sup, 0, 1)
        g_marg.addWidget(edt_esq, 1, 0)
        g_marg.addWidget(area_pagina, 1, 1)
        g_marg.addWidget(edt_dir, 1, 2)
        g_marg.addWidget(edt_inf, 2, 1)
        meio.addWidget(gb_margens, 1)

        gb_borda = QGroupBox('Estilo de Borda')
        g_borda = QVBoxLayout(gb_borda)
        rb_sem_borda = QRadioButton('nenhum')
        rb_sem_borda.setChecked(True)
        rb_cantos = QRadioButton('cantos')
        rb_tracejada = QRadioButton('tracejada')
        g_borda.addWidget(rb_sem_borda)
        g_borda.addWidget(rb_cantos)
        g_borda.addWidget(rb_tracejada)
        g_borda.addStretch(1)
        meio.addWidget(gb_borda)
        lay.addLayout(meio)
        lay.addStretch(1)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        btn_imprimir = QPushButton('Imprimir')
        btn_visualizar = QPushButton('Visualizar')
        btn_fechar = QPushButton('Fechar')
        rodape.addWidget(btn_imprimir)
        rodape.addWidget(btn_visualizar)
        rodape.addWidget(btn_fechar)
        lay.addLayout(rodape)

        def _config() -> dict:
            estilo_borda = 'nenhum'
            if rb_cantos.isChecked():
                estilo_borda = 'cantos'
            elif rb_tracejada.isChecked():
                estilo_borda = 'tracejada'
            return {
                'apenas_selecionados': rb_sel.isChecked(),
                'usar_percentual': rb_percent.isChecked(),
                'percentual': float(edt_percent.value()),
                'escala_x': float(edt_x.value()),
                'escala_y': float(edt_y.value()),
                'em_cores': chk_cores.isChecked(),
                'reorganizar': chk_reorg.isChecked(),
                'margem_sup': float(edt_sup.value()),
                'margem_esq': float(edt_esq.value()),
                'margem_dir': float(edt_dir.value()),
                'margem_inf': float(edt_inf.value()),
                'estilo_borda': estilo_borda,
                'girar_90': False,
            }

        btn_visualizar.clicked.connect(lambda: self._executar_impressao(_config(), True))
        btn_imprimir.clicked.connect(lambda: self._executar_impressao(_config(), False))
        btn_fechar.clicked.connect(dialog.reject)
        dialog.exec()

    def _plotagem_cfg(self) -> dict:
        bruto = self.projeto_atual.preferencias_usuario.get("plotagem_cfg", {})
        if not isinstance(bruto, dict):
            bruto = {}
        plotter = bruto.get("plotter_props", {}) if isinstance(bruto.get("plotter_props", {}), dict) else {}
        porta = bruto.get("porta_cfg", {}) if isinstance(bruto.get("porta_cfg", {}), dict) else {}
        return {
            "plotter_props": {
                "largura_papel_cm": float(plotter.get("largura_papel_cm", 185.0)),
                "tamanho_pagina_cm": float(plotter.get("tamanho_pagina_cm", 115.0)),
                "margem_inferior_cm": float(plotter.get("margem_inferior_cm", 0.0)),
                "qualidade": str(plotter.get("qualidade", "Rascunho")),
                "cor": str(plotter.get("cor", "Preto")),
                "resolucao_dmpl": str(plotter.get("resolucao_dmpl", "Padrão")),
                "corte_papel": str(plotter.get("corte_papel", "nao_cortar")),
                "fator_x": float(plotter.get("fator_x", 1.0)),
                "fator_y": float(plotter.get("fator_y", 1.0)),
                "usar_niveis_impressao": bool(plotter.get("usar_niveis_impressao", False)),
                "usar_texto_como_linha": bool(plotter.get("usar_texto_como_linha", False)),
            },
            "porta_cfg": {
                "bits_por_segundo": str(porta.get("bits_por_segundo", "57600")),
                "bits_de_dados": str(porta.get("bits_de_dados", "8")),
                "paridade": str(porta.get("paridade", "Nenhum")),
                "bits_de_parada": str(porta.get("bits_de_parada", "1")),
                "porta_saida": str(porta.get("porta_saida", "COM1")),
            },
        }

    def _salvar_plotagem_cfg(self, cfg: dict):
        self.projeto_atual.preferencias_usuario["plotagem_cfg"] = cfg
        self._salvar_preferencias_app()

    def _abrir_dialogo_propriedades_plotter(self, props_atuais: dict) -> dict | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Propriedades plotter")
        dialog.setModal(True)
        dialog.resize(350, 500)
        self._aplicar_estilo_claro_dialogo(dialog)
        lay = QVBoxLayout(dialog)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Plotter: HPGL/2"))

        gb = QGroupBox("")
        g = QGridLayout(gb)
        edt_largura = QDoubleSpinBox(); edt_largura.setRange(1.0, 9999.0); edt_largura.setDecimals(2); edt_largura.setValue(float(props_atuais.get("largura_papel_cm", 185.0)))
        edt_pagina = QDoubleSpinBox(); edt_pagina.setRange(1.0, 9999.0); edt_pagina.setDecimals(2); edt_pagina.setValue(float(props_atuais.get("tamanho_pagina_cm", 115.0)))
        edt_margem = QDoubleSpinBox(); edt_margem.setRange(0.0, 9999.0); edt_margem.setDecimals(2); edt_margem.setValue(float(props_atuais.get("margem_inferior_cm", 0.0)))
        cmb_qualidade = QComboBox(); cmb_qualidade.addItems(["Rascunho", "Normal", "Alta"]); cmb_qualidade.setCurrentText(str(props_atuais.get("qualidade", "Rascunho")))
        cmb_cor = QComboBox(); cmb_cor.addItems(["Preto", "Colorido"]); cmb_cor.setCurrentText(str(props_atuais.get("cor", "Preto")))
        cmb_res = QComboBox(); cmb_res.addItems(["Padrão", "300", "600"]); cmb_res.setCurrentText(str(props_atuais.get("resolucao_dmpl", "Padrão")))
        g.addWidget(QLabel("Largura do papel (cm)"), 0, 0); g.addWidget(edt_largura, 0, 1)
        g.addWidget(QLabel("Tamanho da página (cm)"), 1, 0); g.addWidget(edt_pagina, 1, 1)
        g.addWidget(QLabel("Margem inferior (cm)"), 2, 0); g.addWidget(edt_margem, 2, 1)
        g.addWidget(QLabel("Qualidade"), 3, 0); g.addWidget(cmb_qualidade, 3, 1)
        g.addWidget(QLabel("Cor"), 4, 0); g.addWidget(cmb_cor, 4, 1)
        g.addWidget(QLabel("Resolução DMPL"), 5, 0); g.addWidget(cmb_res, 5, 1)
        lay.addWidget(gb)

        gb_corte = QGroupBox("Corte do papel")
        corte_lay = QVBoxLayout(gb_corte)
        rb_nao = QRadioButton("Não cortar")
        rb_final = QRadioButton("Cortar no final")
        rb_faixa = QRadioButton("Cortar entre cada faixa")
        corte = str(props_atuais.get("corte_papel", "nao_cortar"))
        rb_nao.setChecked(corte == "nao_cortar")
        rb_final.setChecked(corte == "cortar_final")
        rb_faixa.setChecked(corte == "cortar_faixa")
        for w in (rb_nao, rb_final, rb_faixa):
            corte_lay.addWidget(w)
        lay.addWidget(gb_corte)

        gb_fat = QGroupBox("Fatores de escala")
        fat = QGridLayout(gb_fat)
        edt_fx = QDoubleSpinBox(); edt_fx.setRange(0.01, 1000.0); edt_fx.setDecimals(4); edt_fx.setValue(float(props_atuais.get("fator_x", 1.0)))
        edt_fy = QDoubleSpinBox(); edt_fy.setRange(0.01, 1000.0); edt_fy.setDecimals(4); edt_fy.setValue(float(props_atuais.get("fator_y", 1.0)))
        fat.addWidget(QLabel("X"), 0, 0); fat.addWidget(edt_fx, 0, 1)
        fat.addWidget(QLabel("Y"), 0, 2); fat.addWidget(edt_fy, 0, 3)
        lay.addWidget(gb_fat)

        chk_niveis = QCheckBox("Usar níveis de impressão"); chk_niveis.setChecked(bool(props_atuais.get("usar_niveis_impressao", False)))
        chk_texto = QCheckBox("Utilizar texto como linha"); chk_texto.setChecked(bool(props_atuais.get("usar_texto_como_linha", False)))
        lay.addWidget(chk_niveis)
        lay.addWidget(chk_texto)
        lay.addStretch(1)
        rod = QHBoxLayout(); rod.addStretch(1)
        btn_ok = QPushButton("✓ OK"); btn_cancel = QPushButton("✕ Cancelar")
        rod.addWidget(btn_ok); rod.addWidget(btn_cancel); lay.addLayout(rod)
        btn_ok.clicked.connect(dialog.accept); btn_cancel.clicked.connect(dialog.reject)
        if dialog.exec() != QDialog.Accepted:
            return None
        corte_val = "nao_cortar"
        if rb_final.isChecked():
            corte_val = "cortar_final"
        elif rb_faixa.isChecked():
            corte_val = "cortar_faixa"
        return {
            "largura_papel_cm": float(edt_largura.value()),
            "tamanho_pagina_cm": float(edt_pagina.value()),
            "margem_inferior_cm": float(edt_margem.value()),
            "qualidade": cmb_qualidade.currentText(),
            "cor": cmb_cor.currentText(),
            "resolucao_dmpl": cmb_res.currentText(),
            "corte_papel": corte_val,
            "fator_x": float(edt_fx.value()),
            "fator_y": float(edt_fy.value()),
            "usar_niveis_impressao": chk_niveis.isChecked(),
            "usar_texto_como_linha": chk_texto.isChecked(),
        }

    def _abrir_dialogo_setup_porta(self, porta_atual: dict) -> dict | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Configuração da porta")
        dialog.setModal(True)
        dialog.resize(280, 210)
        self._aplicar_estilo_claro_dialogo(dialog)
        lay = QVBoxLayout(dialog)
        form = QGridLayout()
        cmb_bps = QComboBox(); cmb_bps.addItems(["9600", "19200", "38400", "57600", "115200"]); cmb_bps.setCurrentText(str(porta_atual.get("bits_por_segundo", "57600")))
        cmb_dados = QComboBox(); cmb_dados.addItems(["7", "8"]); cmb_dados.setCurrentText(str(porta_atual.get("bits_de_dados", "8")))
        cmb_paridade = QComboBox(); cmb_paridade.addItems(["Nenhum", "Par", "Ímpar"]); cmb_paridade.setCurrentText(str(porta_atual.get("paridade", "Nenhum")))
        cmb_stop = QComboBox(); cmb_stop.addItems(["1", "2"]); cmb_stop.setCurrentText(str(porta_atual.get("bits_de_parada", "1")))
        form.addWidget(QLabel("Bits por segundo"), 0, 0); form.addWidget(cmb_bps, 0, 1)
        form.addWidget(QLabel("Bits de dados"), 1, 0); form.addWidget(cmb_dados, 1, 1)
        form.addWidget(QLabel("Paridade"), 2, 0); form.addWidget(cmb_paridade, 2, 1)
        form.addWidget(QLabel("Bits de parada"), 3, 0); form.addWidget(cmb_stop, 3, 1)
        lay.addLayout(form)
        lay.addStretch(1)
        rod = QHBoxLayout(); rod.addStretch(1)
        btn_ok = QPushButton("✓ OK"); btn_cancel = QPushButton("✕ Cancelar")
        rod.addWidget(btn_ok); rod.addWidget(btn_cancel); lay.addLayout(rod)
        btn_ok.clicked.connect(dialog.accept); btn_cancel.clicked.connect(dialog.reject)
        if dialog.exec() != QDialog.Accepted:
            return None
        return {
            "bits_por_segundo": cmb_bps.currentText(),
            "bits_de_dados": cmb_dados.currentText(),
            "paridade": cmb_paridade.currentText(),
            "bits_de_parada": cmb_stop.currentText(),
            "porta_saida": str(porta_atual.get("porta_saida", "COM1")),
        }

    def _gerar_hpgl2_do_molde(self, elementos: list[dict], config: dict) -> tuple[str, int, int]:
        polilinhas: list[list[tuple[float, float]]] = []
        for el in elementos:
            polilinhas.extend(self._polilinhas_elemento_saida(el))
        if not polilinhas:
            return "", 0, 0
        pontos = [pt for linha in polilinhas for pt in linha]
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura = max(max_x - min_x, 1.0)
        altura = max(max_y - min_y, 1.0)
        girar_90 = bool(config.get("girar_90", False))
        percentual = max(0.01, float(config.get("percentual", 100.0))) / 100.0
        props = config.get("plotter_props", {}) if isinstance(config.get("plotter_props", {}), dict) else {}
        fator_x = max(0.001, float(props.get("fator_x", 1.0)))
        fator_y = max(0.001, float(props.get("fator_y", 1.0)))
        largura_papel = max(1.0, float(props.get("largura_papel_cm", 185.0)))
        altura_papel = max(1.0, float(props.get("tamanho_pagina_cm", 115.0)))
        margem_inf = max(0.0, float(props.get("margem_inferior_cm", 0.0)))
        margem_u = int(round(margem_inf * 40.0))
        largura_u_disp = max(400, int(round(largura_papel * 20.0)) - 2 * margem_u)
        altura_u_disp = max(400, int(round(altura_papel * 20.0)) - 2 * margem_u)
        largura_base = altura if girar_90 else largura
        altura_base = largura if girar_90 else altura
        escala_fit = min(largura_u_disp / max(largura_base, 1.0), altura_u_disp / max(altura_base, 1.0))
        escala = max(0.1, escala_fit * percentual)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        largura_plot = int(round(largura_base * escala * fator_x))
        altura_plot = int(round(altura_base * escala * fator_y))
        offset_x = margem_u
        offset_y = margem_u

        def _mapear(pt: tuple[float, float]) -> tuple[int, int]:
            x = float(pt[0]) - cx
            y = float(pt[1]) - cy
            if girar_90:
                x, y = -y, x
            hx = int(round(offset_x + (largura_plot / 2.0) + (x * escala * fator_x)))
            hy = int(round(offset_y + (altura_plot / 2.0) + (y * escala * fator_y)))
            return hx, hy

        linhas = []
        for linha in polilinhas:
            if len(linha) < 2:
                continue
            x0, y0 = _mapear(linha[0])
            coords = []
            for pt in linha[1:]:
                x, y = _mapear(pt)
                coords.append(f"{x},{y}")
            linhas.append(f"PU{x0},{y0}PD " + " ".join(coords) + "PU")
        return "".join(linhas), largura_plot + 2 * margem_u, altura_plot + 2 * margem_u

    def _gerar_hpgl2(self, elementos: list[dict], config: dict) -> str:
        corpo, largura_ps, altura_ps = self._gerar_hpgl2_do_molde(elementos, config)
        if not corpo:
            return ''
        props = config.get('plotter_props', {}) if isinstance(config.get('plotter_props', {}), dict) else {}
        qualidade = str(props.get('qualidade', 'Rascunho')).lower()
        ql = '0' if qualidade == 'rascunho' else ('1' if qualidade == 'normal' else '2')
        cabecalho = f"\x1b%-1BBPINPS{int(max(1, largura_ps))},{int(max(1, altura_ps))}SP1QL{ql}"
        return cabecalho + '\r\n' + corpo + 'SP0PG;\r\n'

    def _exportar_plotagem_para_arquivo(self, config: dict):
        elementos = self._obter_elementos_saida(bool(config.get('apenas_selecionados', False)))
        if not elementos:
            caixa = QMessageBox(self)
            self._estilizar_message_box(caixa)
            caixa.setWindowTitle('Plotagem')
            caixa.setIcon(QMessageBox.Information)
            caixa.setText('Não há elementos disponíveis para plotagem.')
            caixa.exec()
            return
        caminho, _ = self._abrir_dialogo_arquivo_claro('HPGL/2', 'Arquivos de plotagem (*.plt);;Todos (*.*)', modo_salvar=True)
        if not caminho:
            return
        destino = Path(caminho)
        if not destino.suffix:
            destino = destino.with_suffix('.plt')
        conteudo = self._gerar_hpgl2(elementos, config)
        if not conteudo.strip():
            caixa = QMessageBox(self)
            self._estilizar_message_box(caixa)
            caixa.setWindowTitle('Plotagem')
            caixa.setIcon(QMessageBox.Warning)
            caixa.setText('Não foi possível gerar o arquivo de plotagem com os elementos atuais.')
            caixa.exec()
            return
        destino.write_text(conteudo, encoding='latin-1', newline='')
        self.lbl_status.setText(f'Arquivo de plotagem salvo em: {destino}')
        caixa = QMessageBox(self)
        self._estilizar_message_box(caixa)
        caixa.setWindowTitle('Plotagem')
        caixa.setIcon(QMessageBox.Information)
        caixa.setText(f'Arquivo HPGL/2 gerado com sucesso.\n\n{destino}')
        caixa.exec()

    def _abrir_dialogo_plotagem(self):
        area = self._area_documento_atual()
        if not area or not getattr(area.canvas.cena, 'elementos', None):
            caixa = QMessageBox(self)
            self._estilizar_message_box(caixa)
            caixa.setWindowTitle('Plotagem')
            caixa.setIcon(QMessageBox.Information)
            caixa.setText('Abra um documento com elementos antes de plotar.')
            caixa.exec()
            return

        cfg_salva = self._plotagem_cfg()
        dialog = QDialog(self)
        dialog.setWindowTitle('Plotagem')
        dialog.setModal(True)
        dialog.resize(640, 440)
        self._aplicar_estilo_claro_dialogo(dialog)
        lay = QHBoxLayout(dialog)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(12)

        col_esq = QVBoxLayout()
        gb_area = QGroupBox('Área de plotagem')
        g_area = QGridLayout(gb_area)
        rb_area_tudo = QRadioButton('Tudo')
        rb_area_tudo.setChecked(True)
        rb_faixas = QRadioButton('Faixas de plotagem')
        edt_faixas = QLineEdit('1-2')
        edt_x_inicial = QDoubleSpinBox()
        edt_x_inicial.setRange(0.0, 99999.0)
        edt_x_inicial.setDecimals(2)
        edt_x_inicial.setValue(0.0)
        g_area.addWidget(rb_area_tudo, 0, 0, 1, 2)
        g_area.addWidget(rb_faixas, 1, 0)
        g_area.addWidget(edt_faixas, 1, 1)
        g_area.addWidget(QLabel('X inicial de plotagem (cm)'), 2, 0)
        g_area.addWidget(edt_x_inicial, 2, 1)
        col_esq.addWidget(gb_area)

        gb_sep = QGroupBox('')
        g_sep = QVBoxLayout(gb_sep)
        chk_tamanhos_sep = QCheckBox('Plotar tamanhos separados')
        cmb_tamanhos = QComboBox()
        cmb_tamanhos.addItems(['Todos'])
        cmb_tamanhos.setEnabled(False)
        chk_tamanhos_sep.toggled.connect(cmb_tamanhos.setEnabled)
        chk_reorg = QCheckBox('Reorganizar moldes')
        g_sep.addWidget(chk_tamanhos_sep)
        g_sep.addWidget(cmb_tamanhos)
        g_sep.addWidget(chk_reorg)
        col_esq.addWidget(gb_sep)

        gb_opts = QGroupBox('Opções de plotagem')
        g_opts = QVBoxLayout(gb_opts)
        chk_para_arquivo = QCheckBox('Plotar para arquivo')
        chk_para_arquivo.setChecked(True)
        chk_girar = QCheckBox('Plotar girando 90°')
        chk_desdobrar = QCheckBox('Desdobrar moldes')
        chk_elem_sel = QCheckBox('Plotar elementos selecionados')
        chk_elem_sel.setEnabled(bool(self._obter_elementos_saida(True)))
        chk_contorno = QCheckBox('Somente contorno de corte')
        chk_gerenciador = QCheckBox('Usar gerenciador de plotagem')
        chk_ferr_hpgl = QCheckBox('Usar ferramentas definidas (HPGL)')
        chk_estilos = QCheckBox('Usar estilos de linha definidos')
        for w in (chk_para_arquivo, chk_girar, chk_desdobrar, chk_elem_sel, chk_contorno, chk_gerenciador, chk_ferr_hpgl, chk_estilos):
            g_opts.addWidget(w)
        col_esq.addWidget(gb_opts, 1)
        lay.addLayout(col_esq, 1)

        col_dir = QVBoxLayout()
        gb_prop = QGroupBox('Proporção')
        g_prop = QHBoxLayout(gb_prop)
        g_prop.addWidget(QLabel('Porcentagem'))
        edt_pct = QDoubleSpinBox()
        edt_pct.setRange(1.0, 1000.0)
        edt_pct.setDecimals(2)
        edt_pct.setValue(100.0)
        edt_pct.setSuffix(' %')
        g_prop.addWidget(edt_pct, 1)
        col_dir.addWidget(gb_prop)

        gb_plotter = QGroupBox('Configurações do plotter')
        g_plotter = QGridLayout(gb_plotter)
        g_plotter.addWidget(QLabel('Plotter'), 0, 0)
        cmb_plotter = QComboBox()
        cmb_plotter.addItems(['HPGL/2'])
        btn_props = QPushButton('Propriedades...')
        g_plotter.addWidget(cmb_plotter, 1, 0)
        g_plotter.addWidget(btn_props, 1, 1)
        g_plotter.addWidget(QLabel('Porta de saída'), 2, 0, 1, 2)
        linha_saida = QHBoxLayout()
        chk_printer = QCheckBox('')
        cmb_printer = QComboBox()
        cmb_printer.addItems(['EPSON7FEDEB (L3150 Series)'])
        cmb_printer.setEnabled(False)
        chk_printer.toggled.connect(cmb_printer.setEnabled)
        linha_saida.addWidget(chk_printer)
        linha_saida.addWidget(cmb_printer, 1)
        g_plotter.addLayout(linha_saida, 3, 0, 1, 2)
        cmb_porta = QComboBox()
        cmb_porta.addItems(['COM1', 'COM2', 'COM3', 'LPT1'])
        btn_setup = QPushButton('Setup...')
        g_plotter.addWidget(cmb_porta, 4, 0)
        g_plotter.addWidget(btn_setup, 4, 1)
        col_dir.addWidget(gb_plotter)

        gb_perf = QGroupBox('Perfis de configuração')
        g_perf = QGridLayout(gb_perf)
        g_perf.addWidget(QLabel('Perfil'), 0, 0)
        cmb_perfil = QComboBox()
        cmb_perfil.addItems([''])
        g_perf.addWidget(cmb_perfil, 0, 1, 1, 2)
        btn_criar = QPushButton('Criar')
        btn_atualizar = QPushButton('Atualizar')
        btn_remover = QPushButton('Remover')
        btn_criar.clicked.connect(lambda: self.lbl_status.setText('Criação de perfil de plotagem em evolução.'))
        btn_atualizar.clicked.connect(lambda: self.lbl_status.setText('Atualização de perfil de plotagem em evolução.'))
        btn_remover.clicked.connect(lambda: self.lbl_status.setText('Remoção de perfil de plotagem em evolução.'))
        g_perf.addWidget(btn_criar, 1, 0)
        g_perf.addWidget(btn_atualizar, 1, 1)
        g_perf.addWidget(btn_remover, 1, 2)
        col_dir.addWidget(gb_perf)
        col_dir.addStretch(1)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        btn_ok = QPushButton('✓ OK')
        btn_cancelar = QPushButton('✕ Cancelar')
        rodape.addWidget(btn_ok)
        rodape.addWidget(btn_cancelar)
        col_dir.addLayout(rodape)
        lay.addLayout(col_dir, 1)

        cfg_edicao = {'plotter_props': dict(cfg_salva['plotter_props']), 'porta_cfg': dict(cfg_salva['porta_cfg'])}
        porta_inicial = str(cfg_edicao['porta_cfg'].get('porta_saida', 'COM1'))
        if porta_inicial in ['COM1', 'COM2', 'COM3', 'LPT1']:
            cmb_porta.setCurrentText(porta_inicial)

        def _abrir_props():
            novo = self._abrir_dialogo_propriedades_plotter(cfg_edicao['plotter_props'])
            if novo is not None:
                cfg_edicao['plotter_props'] = novo
                self.lbl_status.setText('Propriedades do plotter atualizadas.')

        def _abrir_setup():
            novo = self._abrir_dialogo_setup_porta(cfg_edicao['porta_cfg'])
            if novo is not None:
                cfg_edicao['porta_cfg'] = novo
                self.lbl_status.setText('Configuração da porta atualizada.')

        btn_props.clicked.connect(_abrir_props)
        btn_setup.clicked.connect(_abrir_setup)

        def _plotar():
            cfg_edicao['porta_cfg']['porta_saida'] = cmb_porta.currentText()
            self._salvar_plotagem_cfg(cfg_edicao)
            config = {
                'percentual': float(edt_pct.value()),
                'girar_90': chk_girar.isChecked(),
                'desdobrar': chk_desdobrar.isChecked(),
                'apenas_selecionados': chk_elem_sel.isChecked(),
                'somente_contorno': chk_contorno.isChecked(),
                'plotter': cmb_plotter.currentText(),
                'porta_saida': cmb_porta.currentText(),
                'area_modo': 'faixas' if rb_faixas.isChecked() else 'tudo',
                'faixas': edt_faixas.text().strip(),
                'x_inicial': float(edt_x_inicial.value()),
                'plotar_para_arquivo': chk_para_arquivo.isChecked(),
                'plotter_props': dict(cfg_edicao['plotter_props']),
                'porta_cfg': dict(cfg_edicao['porta_cfg']),
            }
            self._exportar_plotagem_para_arquivo(config)
            dialog.accept()

        btn_ok.clicked.connect(_plotar)
        btn_cancelar.clicked.connect(dialog.reject)
        dialog.exec()

    def _importar_por_tipo(self, tipo: str, origem_inicial: str | None = None):
        filtros = {
            "audaces": "Arquivos EMF/XML/ADSX/AMKX (*.emf *.xml *.adsx *.amkx)",
            "adsx": "Arquivos ADSX/AMKX (*.adsx *.amkx)",
            "audaces_emf": "Arquivos EMF (*.emf)",
            "audaces_xml": "Arquivos XML (*.xml)",
            "dxf": "Arquivo DXF (*.dxf)",
            "aama_astm": "Arquivo AAMA/ASTM (*.dxf *.aama *.astm *.rul *.zip)",
            "plotagem": "Arquivo de plotagem (*.plt *.hpgl *.hpgl2 *.hpg *.txt)",
        }
        if tipo == "audaces":
            caminho, _ = self._abrir_dialogo_arquivo_claro("Importar arquivos EMF/XML/ADSX/AMKX", filtros["audaces"])
            if not caminho:
                return
            p = Path(caminho)
            ext = p.suffix.lower()
            if ext in {".adsx", ".amkx"}:
                return self._importar_pacote_audaces(caminho)
            if ext not in {".emf", ".xml"}:
                return
            pasta = p.parent
            emfs = sorted(pasta.glob("*.emf"))
            xmls = sorted(pasta.glob("*.xml"))
            emf_path = str(p) if ext == ".emf" else None
            xml_path = str(p) if ext == ".xml" else None
            stem = p.stem.lower()
            if not emf_path:
                candidatos = [x for x in emfs if stem in x.stem.lower() or x.stem.lower() in stem]
                if len(candidatos) == 1:
                    emf_path = str(candidatos[0])
                elif len(emfs) == 1:
                    emf_path = str(emfs[0])
            if not xml_path:
                candidatos = [x for x in xmls if stem in x.stem.lower() or x.stem.lower() in stem]
                if len(candidatos) == 1:
                    xml_path = str(candidatos[0])
                elif len(xmls) == 1:
                    xml_path = str(xmls[0])
            if not emf_path and xml_path:
                emf_path, _ = self._abrir_dialogo_arquivo_claro("Selecionar arquivo EMF", filtros["audaces_emf"])
            if not xml_path and emf_path:
                xml_path, _ = self._abrir_dialogo_arquivo_claro("Selecionar arquivo XML", filtros["audaces_xml"])
            if emf_path and xml_path:
                self.projeto_atual = AudacesPairImport.importar(emf_path, xml_path, self.projeto_atual)
                info = self.projeto_atual.preferencias_usuario.get("audaces_emf_xml_importacao", {})
                self._arquivo_atual = None
                self._limpar_abas_documentos()
                self._adicionar_aba_documento("EMF + XML", emf_path)
                area = self._area_documento_atual()
                moldes = self.projeto_atual.documentos[0].moldes if self.projeto_atual.documentos else []
                if area and moldes:
                    self._carregar_moldes_reais_no_canvas(area, moldes)
                else:
                    self._aplicar_elementos_importados_canvas(info.get("elementos_canvas", []), "EMF + XML", emf_path)
                self.lbl_status.setText(f"EMF + XML importado com sucesso: {len(moldes)} moldes criados.")
                return
            if emf_path:
                return self._importar_por_tipo("audaces_emf")
            if xml_path:
                return self._importar_por_tipo("audaces_xml")
            return

        if tipo == "audaces_emf_xml":
            emf_path, _ = self._abrir_dialogo_arquivo_claro("Importar EMF + XML (EMF)", filtros["audaces_emf"])
            if not emf_path:
                return
            pergunta = QMessageBox(self)
            self._estilizar_message_box(pergunta)
            pergunta.setWindowTitle("Importacao EMF + XML")
            pergunta.setIcon(QMessageBox.Question)
            pergunta.setText("Deseja selecionar o XML correspondente?")
            pergunta.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            self._traduzir_botoes_padrao_message_box(pergunta)
            resp = pergunta.exec()
            if resp == QMessageBox.Cancel:
                return
            if resp == QMessageBox.Yes:
                xml_path, _ = self._abrir_dialogo_arquivo_claro("Selecionar XML", filtros["audaces_xml"])
                if not xml_path:
                    return
                self.projeto_atual = AudacesPairImport.importar(emf_path, xml_path, self.projeto_atual)
                info = self.projeto_atual.preferencias_usuario.get("audaces_emf_xml_importacao", {})
                self._arquivo_atual = None
                self._limpar_abas_documentos()
                self._adicionar_aba_documento("EMF + XML", emf_path)
                area = self._area_documento_atual()
                moldes_doc = []
                if self.projeto_atual.documentos:
                    moldes_doc = self.projeto_atual.documentos[0].moldes
                print(f"[AUDACES_IMPORT] len(self.projeto_atual.documentos[0].moldes)={len(moldes_doc)}")
                if area and len(moldes_doc) > 0:
                    carregados = self._carregar_moldes_reais_no_canvas(area, moldes_doc)
                    info["canvas_origem"] = "moldes_reais"
                    info["canvas_moldes_renderizados"] = carregados
                    info["canvas_elementos_emf_renderizados"] = 0
                    print("[AUDACES_IMPORT] area.canvas.cena.elementos recebe moldes convertidos de projeto.documentos[0].moldes")
                else:
                    elementos_canvas = info.get("elementos_canvas", [])
                    if area:
                        area.canvas.cena.elementos = [dict(el) for el in elementos_canvas if isinstance(el, dict)]
                        area.canvas.update()
                    info["canvas_origem"] = "elementos_emf_fallback"
                    info["canvas_moldes_renderizados"] = 0
                    info["canvas_elementos_emf_renderizados"] = len(elementos_canvas)
                    print("[AUDACES_IMPORT] area.canvas.cena.elementos recebe preferencias_usuario['audaces_emf_xml_importacao']['elementos_canvas']")
                if area:
                    print(f"[AUDACES_IMPORT] len(area.canvas.cena.elementos)={len(area.canvas.cena.elementos)}")
                print(f"[AUDACES_IMPORT] canvas_origem={info.get('canvas_origem')}")
                print(f"[AUDACES_IMPORT] moldes_carregados_no_canvas={info.get('canvas_moldes_renderizados', 0)}")
                moldes_reais = int(info.get("moldes_reais", 0))
                msg = (
                    f"EMF+XML importado. Vetores: {int(info.get('vetores', 0))}. "
                    f"Contornos fechados: {int(info.get('contornos_fechados', 0))}. "
                    f"Moldes reais: {moldes_reais}. "
                    f"Metadados XML aplicados: {int(info.get('metadados_xml_aplicados', 0))}."
                )
                if moldes_reais == 0:
                    msg += " O EMF foi lido, mas nenhum contorno fechado confiavel foi encontrado. Verifique o relatorio tecnico."
                self.lbl_status.setText(msg)
                caixa = QMessageBox(self)
                self._estilizar_message_box(caixa)
                caixa.setWindowTitle("Importacao EMF + XML")
                caixa.setIcon(QMessageBox.Information)
                caixa.setText(msg)
                caixa.setStandardButtons(QMessageBox.Ok)
                self._traduzir_botoes_padrao_message_box(caixa)
                caixa.exec()
                return
            self.projeto_atual = AudacesPairImport.importar_apenas_emf(emf_path, self.projeto_atual)
            info = self.projeto_atual.preferencias_usuario.get("audaces_emf_importacao", {})
            self._aplicar_elementos_importados_canvas(info.get("elementos_canvas", []), "EMF", emf_path)
            msg = "EMF importado como vetor. Sem XML, os moldes podem ficar sem nomes e propriedades técnicas."
            self.lbl_status.setText(msg)
            return

        opcoes_importacao_moldes: dict = {}
        if tipo in {"dxf", "aama_astm"}:
            caminho, _, opcoes_importacao_moldes = self._abrir_dialogo_importacao_moldes(tipo, origem_inicial=origem_inicial)
        else:
            caminho, _ = self._abrir_dialogo_arquivo_claro(f"Importar {tipo.upper()}", filtros.get(tipo, "Todos (*.*)"))
        if not caminho:
            return

        if tipo == "adsx":
            return self._importar_pacote_audaces(caminho)
            opcoes_adsx = self._dialogo_opcoes_importacao_adsx()
            if opcoes_adsx is None:
                return
            try:
                self.projeto_atual = ADSXIO.importar_para_projeto(caminho, self.projeto_atual)
                self.projeto_atual.preferencias_usuario["adsx_modo_importacao"] = dict(opcoes_adsx)
                self._arquivo_atual = None
                self._atualizar_interface_pos_importacao_adsx(caminho)
            except ADSXImportError as exc:
                caixa = QMessageBox(self)
                self._estilizar_message_box(caixa)
                caixa.setWindowTitle("Importação ADSX")
                caixa.setIcon(QMessageBox.Warning)
                caixa.setText(str(exc))
                caixa.setStandardButtons(QMessageBox.Ok)
                self._traduzir_botoes_padrao_message_box(caixa)
                caixa.exec()
                self.lbl_status.setText(str(exc))
                return
            except Exception as exc:
                import traceback
                traceback.print_exc()
                caixa = QMessageBox(self)
                self._estilizar_message_box(caixa)
                caixa.setWindowTitle("Importação ADSX")
                caixa.setIcon(QMessageBox.Critical)
                caixa.setText(f"Não foi possível importar o arquivo ADSX.\n\n{type(exc).__name__}: {exc}")
                caixa.setStandardButtons(QMessageBox.Ok)
                self._traduzir_botoes_padrao_message_box(caixa)
                caixa.exec()
                self.lbl_status.setText("Falha ao importar ADSX.")
                return
            self._arquivo_atual = None
            self._atualizar_titulo()
            self.backstage.hide()
            self._agendar_salvar_estado_silencioso()
            msg = (
                "ADSX importado como referência visual. "
                "A geometria editável ainda depende de conversor vetorial de EMF + XML."
            )
            self.lbl_status.setText(msg)
            return

        if tipo == "audaces_emf":
            self.projeto_atual = AudacesPairImport.importar_apenas_emf(caminho, self.projeto_atual)
            info = self.projeto_atual.preferencias_usuario.get("audaces_emf_importacao", {})
            self._aplicar_elementos_importados_canvas(info.get("elementos_canvas", []), "EMF", caminho)
            self.lbl_status.setText("EMF importado como vetor. Sem XML, os moldes podem ficar sem nomes e propriedades técnicas.")
            return

        if tipo == "audaces_xml":
            xml_doc = AudacesXMLImport.abrir(caminho)
            self.projeto_atual.preferencias_usuario["audaces_xml_importacao"] = xml_doc_para_dict(xml_doc)
            self.projeto_atual.preferencias_usuario.setdefault("audaces_importados_originais", {})["xml"] = {
                "nome": Path(caminho).name,
                "conteudo_base64": base64.b64encode(Path(caminho).read_bytes()).decode("ascii"),
            }
            linhas = [
                f"Modelo: {xml_doc.nome_modelo}",
                f"Tamanhos do modelo: {len(xml_doc.tamanhos_modelo)}",
                f"Peças no XML: {len(xml_doc.pecas)}",
                "XML carregado como metadado técnico (sem contorno geométrico).",
            ]
            elementos = [{"tipo": "texto", "texto": l, "pos": (6.0, 6.0 + (i * 3.0)), "cor": "#111111", "tamanho": 0.95} for i, l in enumerate(linhas)]
            self._aplicar_elementos_importados_canvas(elementos, "XML", caminho)
            self.lbl_status.setText("XML importado como metadado tecnico. Use EMF + XML para vetor editavel.")
            return

        if tipo in {"dxf", "aama_astm"}:
            elementos = importar_dxf_para_elementos(caminho)
            if not elementos:
                self.lbl_status.setText("Nenhum elemento vetorial encontrado no arquivo.")
                return
            elementos = self._preparar_elementos_importacao_moldes(elementos, opcoes_importacao_moldes)
            nome_doc = "DXF" if tipo == "dxf" else "AAMA/ASTM"
            anexar = bool(opcoes_importacao_moldes.get("importar_mesmo_arquivo", False))
            self._aplicar_elementos_importados_canvas(elementos, nome_doc, caminho, anexar=anexar)
            unidade = str(opcoes_importacao_moldes.get("unidade", "cm"))
            origem = str(opcoes_importacao_moldes.get("origem", "Padrao (ASTM)"))
            modo = "adicionado ao arquivo atual" if anexar else "importado"
            self.lbl_status.setText(f"{nome_doc} {modo}: {len(elementos)} segmentos. Unidade {unidade}, origem {origem}.")
            return

        if tipo == "plotagem":
            elementos = self._importar_hpgl_para_elementos(caminho)
            if not elementos:
                self.lbl_status.setText("Arquivo de plotagem sem vetores reconhecidos.")
                return
            self._aplicar_elementos_importados_canvas(elementos, "Plotagem", caminho)
            self.lbl_status.setText(f"Arquivo de plotagem importado: {len(elementos)} segmentos.")
            return

        imports = self.projeto_atual.preferencias_usuario.setdefault("imports", [])
        imports.append({"tipo": tipo, "caminho": caminho})
        self.backstage.hide()
        self.lbl_status.setText(f"Importação registrada ({tipo}). Suporte completo em evolução.")

    def _importar_pacote_audaces(self, caminho: str):
        opcoes_adsx = self._dialogo_opcoes_importacao_adsx()
        if opcoes_adsx is None:
            return
        tipo_pacote = Path(caminho).suffix.lower().lstrip(".") or "adsx"
        try:
            self.projeto_atual = ADSXIO.importar_para_projeto(caminho, self.projeto_atual)
            self.projeto_atual.preferencias_usuario["adsx_modo_importacao"] = dict(opcoes_adsx)
            self._arquivo_atual = None
            self._atualizar_interface_pos_importacao_adsx(caminho)
        except ADSXImportError as exc:
            caixa = QMessageBox(self)
            self._estilizar_message_box(caixa)
            caixa.setWindowTitle("Importacao ADSX/AMKX")
            caixa.setIcon(QMessageBox.Warning)
            caixa.setText(str(exc))
            caixa.setStandardButtons(QMessageBox.Ok)
            self._traduzir_botoes_padrao_message_box(caixa)
            caixa.exec()
            self.lbl_status.setText(str(exc))
            return
        except Exception as exc:
            import traceback

            traceback.print_exc()
            caixa = QMessageBox(self)
            self._estilizar_message_box(caixa)
            caixa.setWindowTitle("Importacao ADSX/AMKX")
            caixa.setIcon(QMessageBox.Critical)
            caixa.setText(f"Nao foi possivel importar o pacote ADSX/AMKX.\n\n{type(exc).__name__}: {exc}")
            caixa.setStandardButtons(QMessageBox.Ok)
            self._traduzir_botoes_padrao_message_box(caixa)
            caixa.exec()
            self.lbl_status.setText("Falha ao importar pacote ADSX/AMKX.")
            return
        self._arquivo_atual = None
        self._atualizar_titulo()
        self.backstage.hide()
        self._agendar_salvar_estado_silencioso()
        info = self.projeto_atual.preferencias_usuario.get("adsx_importacao", {})
        if bool(info.get("geometria_convertida")):
            self.lbl_status.setText(
                f"{tipo_pacote.upper()} importado como vetor editavel."
            )
        else:
            motivo = str(info.get("motivo_sem_geometria") or "contorno interno ainda nao decodificado")
            self.lbl_status.setText(
                f"{tipo_pacote.upper()} importado apenas como referencia visual. "
                f"Metadados e binario original preservados; sem molde editavel confirmado. {motivo}"
            )

    def _aplicar_elementos_importados_canvas(
        self,
        elementos: list[dict],
        titulo_aba: str,
        caminho_origem: str,
        *,
        anexar: bool = False,
    ):
        if anexar:
            area = self._area_documento_atual()
            if area:
                novos = [dict(el) for el in elementos if isinstance(el, dict)]
                area.canvas.cena.elementos.extend(novos)
                if hasattr(area.canvas, "_registrar_historico"):
                    area.canvas._registrar_historico()
                self._centralizar_canvas_em_elementos(area.canvas, area.canvas.cena.elementos)
                if hasattr(area, "_on_zoom_changed"):
                    area._on_zoom_changed(area.canvas.zoom)
                area.canvas.update()
                self.backstage.hide()
                self._agendar_salvar_estado_silencioso()
                self._agendar_reencaixe_janela_canvas()
                return
        self._arquivo_atual = None
        self._limpar_abas_documentos()
        self._adicionar_aba_documento(titulo_aba, caminho_origem)
        area = self._area_documento_atual()
        if area:
            area.canvas.cena.elementos = [dict(el) for el in elementos if isinstance(el, dict)]
            if hasattr(area.canvas, "_registrar_historico"):
                area.canvas._registrar_historico()
            self._centralizar_canvas_em_elementos(area.canvas, area.canvas.cena.elementos)
            if hasattr(area, "_on_zoom_changed"):
                area._on_zoom_changed(area.canvas.zoom)
            area.canvas.update()
        self._atualizar_titulo()
        self.backstage.hide()
        self._agendar_salvar_estado_silencioso()
        self._agendar_reencaixe_janela_canvas()

    def _carregar_moldes_reais_no_canvas(self, area, moldes):
        if not area:
            return 0
        elementos: list[dict] = []
        for molde in moldes or []:
            for parte in getattr(molde, "partes", []) or []:
                pts = [(float(p.x), float(p.y)) for p in getattr(parte, "pontos", [])]
                if len(pts) < 2:
                    continue
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                base = pts[:-1]
                xs = [x for x, _ in base]
                ys = [y for _, y in base]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                largura = max(xs) - min(xs)
                altura = max(ys) - min(ys)
                margem = largura * 0.20
                y_fio = min(max(ys) - max(0.15, altura * 0.06), cy + max(0.25, altura * 0.08))
                elementos.append({
                    "tipo": "polyline",
                    "pontos": pts,
                    "molde": True,
                    "origem": "molde_real_audaces",
                    "subtipo_audaces": "contorno",
                    "nome_molde": getattr(molde, "nome", "Molde"),
                    "molde_id": getattr(molde, "id", ""),
                    "fio_angulo": 0.0,
                    "fio_origem": (min(xs) + margem, y_fio),
                    "fio_fim": (max(xs) - margem, y_fio),
                    "ponto_texto": (cx, cy),
                    "texto_nome_altura_cm": 3.0,
                    "numero_altura_cm": 0.7,
                    "mostrar_nome": True,
                    "mostrar_fio": True,
                    "mostrar_numeros": True,
                    "cor": "#ff7b00",
                    "bloqueado": False,
                })
        area.canvas.cena.elementos = elementos
        area.canvas.update()
        return len(elementos)

    def _importar_hpgl_para_elementos(self, caminho: str) -> list[dict]:
        try:
            bruto = Path(caminho).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        comandos = [c.strip() for c in bruto.replace("\n", "").split(";") if c.strip()]
        elementos: list[dict] = []
        atual = None
        caneta_baixada = False
        for cmd in comandos:
            op = cmd[:2].upper()
            payload = cmd[2:].strip()
            if op == "PU":
                caneta_baixada = False
                pts = self._hpgl_parse_pontos(payload)
                if pts:
                    atual = pts[-1]
            elif op == "PD":
                pts = self._hpgl_parse_pontos(payload)
                if atual is None and pts:
                    atual = pts.pop(0)
                for pt in pts:
                    if atual is not None:
                        elementos.append({"tipo": "polyline", "pontos": [atual, pt], "cor": "#ff5a00"})
                    atual = pt
                caneta_baixada = True
            elif op == "PA" and caneta_baixada:
                pts = self._hpgl_parse_pontos(payload)
                for pt in pts:
                    if atual is not None:
                        elementos.append({"tipo": "polyline", "pontos": [atual, pt], "cor": "#ff5a00"})
                    atual = pt
        return elementos

    def _hpgl_parse_pontos(self, payload: str) -> list[tuple[float, float]]:
        nums = [n.strip() for n in payload.split(",") if n.strip()]
        if len(nums) < 2:
            return []
        pontos: list[tuple[float, float]] = []
        for i in range(0, len(nums) - 1, 2):
            try:
                x = float(nums[i]) / 40.0
                y = float(nums[i + 1]) / 40.0
            except ValueError:
                continue
            pontos.append((x, y))
        return pontos

    def _dialogo_opcoes_importacao_adsx(self) -> dict | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Modo de importação ADSX")
        layout = QVBoxLayout(dialog)

        chk_preservar = QCheckBox("Preservar arquivo original no .gs")
        chk_preservar.setChecked(True)
        chk_preservar.setEnabled(False)

        chk_preview = QCheckBox("Mostrar preview JPG como referência")
        chk_preview.setChecked(True)

        info = QLabel(
            "A conversão para molde editável ainda não está disponível nesta etapa.\n"
            "O ADSX será preservado dentro do projeto .gs e o preview JPG poderá ser usado apenas como referência visual."
        )
        info.setWordWrap(True)

        dica = QLabel("Para importar moldes editaveis reais, use EMF + XML.")
        dica.setWordWrap(True)
        dica.setStyleSheet("color:#4a5568; font-size:12px;")

        lbl_opacidade = QLabel("Opacidade do preview")
        sld_opacidade = QSlider(Qt.Horizontal)
        sld_opacidade.setRange(10, 100)
        sld_opacidade.setValue(72)
        lbl_pct = QLabel("72%")

        def _sync_opacidade(v: int):
            lbl_pct.setText(f"{int(v)}%")

        def _toggle_opacidade():
            habilitado = chk_preview.isChecked()
            lbl_opacidade.setEnabled(habilitado)
            sld_opacidade.setEnabled(habilitado)
            lbl_pct.setEnabled(habilitado)

        sld_opacidade.valueChanged.connect(_sync_opacidade)
        chk_preview.toggled.connect(_toggle_opacidade)
        _toggle_opacidade()

        op_layout = QHBoxLayout()
        op_layout.addWidget(lbl_opacidade)
        op_layout.addWidget(sld_opacidade, 1)
        op_layout.addWidget(lbl_pct)

        layout.addWidget(chk_preservar)
        layout.addWidget(chk_preview)
        layout.addWidget(info)
        layout.addWidget(dica)
        layout.addLayout(op_layout)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(dialog.accept)
        botoes.rejected.connect(dialog.reject)
        layout.addWidget(botoes)

        if dialog.exec() != QDialog.Accepted:
            return None

        return {
            "preservar_original": True,
            "mostrar_preview_jpg": bool(chk_preview.isChecked()),
            "tentar_vetorizacao_preview": False,
            "importar_geometria_file_ads": False,
            "opacidade_preview": float(sld_opacidade.value() / 100.0),
        }

    def _acao_converter_manual_tracado_adsx(self):
        caixa = QMessageBox(self)
        self._estilizar_message_box(caixa)
        caixa.setWindowTitle("Conversão manual por traçado")
        caixa.setIcon(QMessageBox.Information)
        caixa.setText(
            "Conversão manual por traçado será disponibilizada em uma próxima etapa.\n"
            "Use a camada 'Preview ADSX' como referência visual para redesenho."
        )
        caixa.setStandardButtons(QMessageBox.Ok)
        self._traduzir_botoes_padrao_message_box(caixa)
        caixa.exec()

    def _atualizar_interface_pos_importacao_adsx(self, caminho_adsx: str):
        """
        Atualiza a interface depois da importação ADSX.
        Exibe a geometria real somente quando houver decodificação confiável do file.ads.
        Caso contrário, mostra apenas informações textuais e diagnóstico.
        """
        self._limpar_abas_documentos()
        titulo_pacote = Path(caminho_adsx).suffix.lower().lstrip(".").upper() or "ADSX/AMKX"
        self._adicionar_aba_documento(f"{titulo_pacote} importado", caminho_adsx)

        area = self._area_documento_atual()
        if not area:
            return
        canvas = area.canvas
        info = self.projeto_atual.preferencias_usuario.get("adsx_importacao", {})
        modo_adsx = self.projeto_atual.preferencias_usuario.get("adsx_modo_importacao", {})
        tipo_pacote = str(info.get("tipo_pacote") or self.projeto_atual.audaces_adsx_original.get("tipo_pacote") or "adsx").upper()
        moldes = info.get("moldes", [])
        if not isinstance(moldes, list):
            moldes = []
        elementos_reais = info.get("elementos_canvas", [])
        confianca = str(info.get("geometry_confidence", "none")).lower().strip()
        confiancas_vetoriais = {"high"}
        geometria_convertida = (
            confianca in confiancas_vetoriais
            and bool(info.get("geometria_convertida"))
            and isinstance(elementos_reais, list)
            and bool(elementos_reais)
        )
        diagnostico = info.get("diagnostico_file_ads", {})
        elementos: list[dict] = []
        preview_largura_cena = 0.0
        preview_altura_cena = 0.0
        arquivos_preservados = self.projeto_atual.audaces_adsx_original.get("arquivos_preservados", {})
        preview_nome = ""
        preview_info = {}
        if isinstance(arquivos_preservados, dict):
            for nome, arquivo in arquivos_preservados.items():
                if isinstance(arquivo, dict) and arquivo.get("tipo") in {"preview_image_jpg", "preview_image_png"}:
                    preview_nome = str(nome)
                    preview_info = arquivo
                    break
        preview_b64 = ""
        if isinstance(preview_info, dict):
            preview_b64 = str(preview_info.get("conteudo_base64") or "").strip()
        preview_ok = False
        fallback_vetorizado = False
        if tipo_pacote == "AMKX" and preview_b64:
            escala_x, escala_y = self._escala_preview_amkx_cm_por_px(moldes, preview_b64)
            trace = vetorizar_preview_adsx(preview_b64, escala_x=escala_x, escala_y=escala_y)
            elementos_trace = trace.get("elementos", [])
            if isinstance(elementos_trace, list) and elementos_trace:
                elementos.extend([dict(el) for el in elementos_trace if isinstance(el, dict)])
                geometria_convertida = True
                fallback_vetorizado = True
                diagnostico = {
                    **dict(diagnostico if isinstance(diagnostico, dict) else {}),
                    "motivo": f"AMKX vetorizado a partir do preview: {len(elementos_trace)} contornos editaveis.",
                    "geometry_confidence": "preview_trace",
                    "escala_x_cm_por_px": escala_x,
                    "escala_y_cm_por_px": escala_y,
                }
        elif tipo_pacote == "ADSX" and preview_b64 and bool(modo_adsx.get("vetorizar_preview_adsx", False)):
            escala = self._escala_preview_adsx_cm_por_px(moldes, preview_b64)
            trace = vetorizar_preview_adsx(
                preview_b64,
                escala_x=escala,
                escala_y=escala,
                incluir_linhas_claras=True,
            )
            elementos_trace = trace.get("elementos", [])
            if isinstance(elementos_trace, list) and elementos_trace:
                elementos.extend([dict(el) for el in elementos_trace if isinstance(el, dict)])
                geometria_convertida = True
                fallback_vetorizado = True
                diagnostico = {
                    **dict(diagnostico if isinstance(diagnostico, dict) else {}),
                    "motivo": f"ADSX vetorizado a partir do preview: {len(elementos_trace)} contornos editaveis.",
                    "geometry_confidence": "preview_trace",
                    "escala_cm_por_px": escala,
                }
        mostrar_preview = bool(modo_adsx.get("mostrar_preview_jpg", True)) and not fallback_vetorizado and not geometria_convertida
        if preview_b64 and mostrar_preview:
            pix = QPixmap()
            try:
                pix.loadFromData(base64.b64decode(preview_b64))
            except Exception:
                pix = QPixmap()
            if not pix.isNull():
                if tipo_pacote == "ADSX":
                    escala = self._escala_preview_adsx_cm_por_px(moldes, preview_b64)
                elif tipo_pacote == "AMKX":
                    escala, _escala_y = self._escala_preview_amkx_cm_por_px(moldes, preview_b64)
                else:
                    escala = 1.0
                escala = max(0.01, min(float(escala or 1.0), 20.0))
                preview_largura_cena = float(pix.width()) * float(escala)
                preview_altura_cena = float(pix.height()) * float(escala)
                elementos.append(
                    {
                        "tipo": "imagem",
                        "nome": "Preview ADSX - imagem de referência",
                        "imagem_base64": preview_b64,
                        "pos": (0.0, 0.0),
                        "escala": float(escala),
                        "largura_px": int(pix.width()),
                        "altura_px": int(pix.height()),
                        "opacidade": float(modo_adsx.get("opacidade_preview", 0.72)),
                        "bloqueado": True,
                        "adsx_preview": True,
                    }
                )
                preview_ok = True
                canvas.origem_cena.setX(-(canvas.width() / (2 * max(canvas.zoom, 0.001))))
                canvas.origem_cena.setY(-(canvas.height() / (2 * max(canvas.zoom, 0.001))))
        if geometria_convertida:
            elementos.extend([dict(el) for el in elementos_reais if isinstance(el, dict)])
        else:
            total_moldes = len([m for m in moldes if isinstance(m, dict)])
            motivo = str(diagnostico.get("motivo", "parser file.ads pendente") if isinstance(diagnostico, dict) else "parser file.ads pendente")
            self.lbl_status.setText(
                f"{titulo_pacote} importado: {total_moldes} moldes no XML. "
                f"Preview em escala de referencia; contorno file.ads ainda nao confirmado. {motivo}"
            )
            if not preview_ok:
                elementos.append(
                    {
                        "tipo": "texto",
                        "texto": f"{titulo_pacote} importado. Preview nao encontrado; file.ads preservado para decodificacao.",
                        "pos": (10.0, 10.0),
                        "cor": "#ffffff",
                        "tamanho": 1.0,
                    }
                )

        if hasattr(canvas, "cena") and hasattr(canvas.cena, "elementos"):
            canvas.cena.elementos = []
            canvas.cena.elementos.extend(elementos)

        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        if geometria_convertida and elementos:
            self._centralizar_canvas_em_elementos(canvas, elementos)
        if hasattr(area, "_on_zoom_changed"):
            area._on_zoom_changed(canvas.zoom)
        canvas.update()
        self._agendar_salvar_estado_silencioso()

    def _escala_preview_adsx_cm_por_px(self, moldes: list, preview_b64: str) -> float:
        trace_px = vetorizar_preview_adsx(preview_b64, incluir_linhas_claras=True)
        elementos_px = trace_px.get("elementos", [])
        if not isinstance(elementos_px, list) or not elementos_px:
            return 1.0

        areas_px: list[float] = []
        for el in elementos_px:
            if not isinstance(el, dict):
                continue
            pontos = el.get("pontos", [])
            if not isinstance(pontos, list) or len(pontos) < 2:
                continue
            try:
                xs = [float(x) for x, _ in pontos]
                ys = [float(y) for _, y in pontos]
            except Exception:
                continue
            area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            if area > 0:
                areas_px.append(area)

        areas_cm: list[float] = []
        for molde in moldes:
            if not isinstance(molde, dict):
                continue
            try:
                largura = float(molde.get("largura") or 0.0)
                altura = float(molde.get("altura") or 0.0)
            except (TypeError, ValueError):
                continue
            area = largura * altura
            if area > 0:
                areas_cm.append(area)

        if not areas_px or not areas_cm:
            return 1.0
        areas_px.sort(reverse=True)
        areas_cm.sort(reverse=True)
        razoes: list[float] = []
        for area_cm, area_px in zip(areas_cm[:8], areas_px[:8]):
            if area_px > 0 and area_cm > 0:
                razoes.append((area_cm / area_px) ** 0.5)
        if not razoes:
            return 1.0
        razoes.sort()
        escala = float(razoes[len(razoes) // 2])
        return max(0.05, min(escala, 20.0))

    def _escala_preview_amkx_cm_por_px(self, moldes: list, preview_b64: str) -> tuple[float, float]:
        pix = QPixmap()
        try:
            pix.loadFromData(base64.b64decode(preview_b64))
        except Exception:
            pix = QPixmap()
        largura_px = float(pix.width()) if not pix.isNull() else 0.0
        altura_px = float(pix.height()) if not pix.isNull() else 0.0
        if largura_px <= 0.0 or altura_px <= 0.0:
            return 1.0, 1.0

        marcador = None
        for molde in moldes:
            if not isinstance(molde, dict):
                continue
            meta = molde.get("metadados")
            if isinstance(meta, dict) and meta.get("tipo") == "marker":
                marcador = molde
                break
            if str(molde.get("nome") or "").strip().lower().startswith("encaixe"):
                marcador = molde
                break
        if not isinstance(marcador, dict):
            return 1.0, 1.0

        try:
            largura_cm = float(marcador.get("largura") or 0.0)
            comprimento_cm = float(marcador.get("altura") or 0.0)
        except (TypeError, ValueError):
            return 1.0, 1.0
        if largura_cm <= 0.0 or comprimento_cm <= 0.0:
            return 1.0, 1.0

        escala_x = comprimento_cm / largura_px
        escala_y = largura_cm / altura_px
        if escala_x <= 0.0 or escala_y <= 0.0:
            return 1.0, 1.0
        return escala_x, escala_y

    def _centralizar_canvas_em_elementos(self, canvas, elementos: list[dict], zoom_max: float = 8.0):
        pontos: list[tuple[float, float]] = []
        for el in elementos:
            tipo = el.get("tipo")
            if tipo == "polyline":
                pontos.extend([(float(x), float(y)) for x, y in el.get("pontos", [])])
            elif tipo == "bezier_quadratica":
                for chave in ("p0", "p1", "p2"):
                    if chave in el:
                        x, y = el[chave]
                        pontos.append((float(x), float(y)))
            elif tipo in {"circle", "esfera"}:
                centro = el.get("centro")
                raio = float(el.get("raio", 0.0))
                if isinstance(centro, (tuple, list)) and len(centro) == 2:
                    cx, cy = float(centro[0]), float(centro[1])
                    pontos.extend(
                        [
                            (cx - raio, cy - raio),
                            (cx + raio, cy - raio),
                            (cx - raio, cy + raio),
                            (cx + raio, cy + raio),
                        ]
                    )
        if not pontos:
            return
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura = max(max_x - min_x, 1.0)
        altura = max(max_y - min_y, 1.0)

        area_w = max(canvas.width() - 40, 1)
        area_h = max(canvas.height() - 40, 1)
        novo_zoom = min(area_w / largura, area_h / altura)
        canvas.set_zoom(max(0.05, min(novo_zoom, float(zoom_max))))

        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        canvas.origem_cena.setX(cx - (canvas.width() / (2 * canvas.zoom)))
        canvas.origem_cena.setY(cy - (canvas.height() / (2 * canvas.zoom)))
        canvas.update()

    def _bbox_elemento(self, el: dict) -> tuple[float, float, float, float] | None:
        pontos: list[tuple[float, float]] = []
        tipo = el.get("tipo")
        if tipo == "polyline":
            pontos.extend((float(x), float(y)) for x, y in el.get("pontos", []))
        elif tipo == "bezier_quadratica":
            for chave in ("p0", "p1", "p2"):
                pt = el.get(chave)
                if isinstance(pt, (tuple, list)) and len(pt) == 2:
                    pontos.append((float(pt[0]), float(pt[1])))
        elif tipo in {"circle", "esfera"}:
            centro = el.get("centro")
            raio = float(el.get("raio", 0.0))
            if isinstance(centro, (tuple, list)) and len(centro) == 2:
                cx, cy = float(centro[0]), float(centro[1])
                pontos.extend([(cx - raio, cy - raio), (cx + raio, cy + raio)])
        for chave in (
            "controle_cantos",
            "controle_auxiliares",
            "pontos_controle_principais",
            "pontos_auxiliares",
            "pontos_controle",
            "curva_pontos",
        ):
            arr = el.get(chave)
            if isinstance(arr, list):
                for pt in arr:
                    if isinstance(pt, (tuple, list)) and len(pt) == 2:
                        pontos.append((float(pt[0]), float(pt[1])))
        for chave in ("fio_origem", "fio_fim", "ponto_texto", "seta_origem", "seta_fim"):
            pt = el.get(chave)
            if isinstance(pt, (tuple, list)) and len(pt) == 2:
                pontos.append((float(pt[0]), float(pt[1])))
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    def _transladar_elemento(self, el: dict, dx: float, dy: float):
        tipo = el.get("tipo")
        if tipo == "polyline":
            el["pontos"] = [(float(x) + dx, float(y) + dy) for x, y in el.get("pontos", [])]
        elif tipo == "bezier_quadratica":
            for chave in ("p0", "p1", "p2"):
                pt = el.get(chave)
                if isinstance(pt, (tuple, list)) and len(pt) == 2:
                    el[chave] = (float(pt[0]) + dx, float(pt[1]) + dy)
        elif tipo in {"circle", "esfera"}:
            centro = el.get("centro")
            if isinstance(centro, (tuple, list)) and len(centro) == 2:
                el["centro"] = (float(centro[0]) + dx, float(centro[1]) + dy)

        def _shift_pt(pt):
            if isinstance(pt, (tuple, list)) and len(pt) == 2:
                return (float(pt[0]) + dx, float(pt[1]) + dy)
            return pt

        for chave in (
            "controle_cantos",
            "controle_auxiliares",
            "pontos_controle_principais",
            "pontos_auxiliares",
            "pontos_controle",
            "curva_pontos",
        ):
            arr = el.get(chave)
            if isinstance(arr, list):
                el[chave] = [_shift_pt(p) for p in arr]

        for chave in ("fio_origem", "fio_fim", "ponto_texto", "seta_origem", "seta_fim"):
            if chave in el:
                el[chave] = _shift_pt(el.get(chave))

    def _organizar_moldes_no_canvas_legado(self, canvas, variacao: int | None = None, registrar_historico: bool = True) -> int:
        moldes: list[dict] = []
        for idx, el in enumerate(canvas.cena.elementos):
            if not el.get("molde"):
                continue
            bbox = self._bbox_elemento(el)
            if bbox is None:
                continue
            min_x, min_y, max_x, max_y = bbox
            largura = max(max_x - min_x, 1.0)
            altura = max(max_y - min_y, 1.0)
            moldes.append(
                {
                    "idx": idx,
                    "bbox": bbox,
                    "w": largura,
                    "h": altura,
                    "cx": (min_x + max_x) / 2.0,
                    "cy": (min_y + max_y) / 2.0,
                    "area": largura * altura,
                }
            )
        if not moldes:
            return 0
        moldes.sort(key=lambda info: info["area"], reverse=True)
        n = len(moldes)
        variacao_idx = int(self._indice_layout_organizacao_moldes if variacao is None else variacao) % 3
        media_w = sum(info["w"] for info in moldes) / n
        media_h = sum(info["h"] for info in moldes) / n
        base_gap = max(media_w, media_h) * 0.45 + 8.0
        centros: list[tuple[float, float]] = []
        origem_x, origem_y = 0.0, 0.0

        if variacao_idx == 0:
            colunas = max(1, ceil(sqrt(n)))
            for pos in range(n):
                linha = pos // colunas
                coluna = pos % colunas
                x = origem_x + coluna * (media_w + base_gap)
                y = origem_y + linha * (media_h + base_gap)
                centros.append((x, y))
        elif variacao_idx == 1:
            if n == 1:
                centros = [(origem_x, origem_y)]
            else:
                raio = max(media_w, media_h) * (1.2 + (n / 7.0))
                for pos in range(n):
                    ang = (2.0 * pi * pos / n) - (pi / 2.0)
                    centros.append((origem_x + (raio * cos(ang)), origem_y + (raio * sin(ang))))
        else:
            colunas = 3 if n > 4 else 2
            passo_x = media_w + base_gap
            passo_y = media_h + (base_gap * 0.85)
            for pos in range(n):
                linha = pos // colunas
                coluna = pos % colunas
                deslocamento = passo_x * 0.5 if linha % 2 else 0.0
                x = origem_x + deslocamento + coluna * passo_x
                y = origem_y + linha * passo_y
                centros.append((x, y))

        if centros:
            media_x = sum(x for x, _ in centros) / len(centros)
            media_y = sum(y for _, y in centros) / len(centros)
            centros = [(x - media_x, y - media_y) for x, y in centros]

        movidos: set[int] = set()
        bbox_por_idx: dict[int, tuple[float, float, float, float]] = {}
        for idx, el in enumerate(canvas.cena.elementos):
            if isinstance(el, dict):
                bb = self._bbox_elemento(el)
                if bb is not None:
                    bbox_por_idx[idx] = bb
        for info, (target_x, target_y) in zip(moldes, centros):
            dx = target_x - info["cx"]
            dy = target_y - info["cy"]
            idx_molde = int(info["idx"])
            el_molde = canvas.cena.elementos[idx_molde]
            self._transladar_elemento(el_molde, dx, dy)
            movidos.add(idx_molde)

            chaves_rel = {
                str(el_molde.get("nome_molde") or "").strip(),
                str(el_molde.get("molde_id") or "").strip(),
                str(el_molde.get("id_molde") or "").strip(),
            }
            chaves_rel.discard("")
            if not chaves_rel:
                continue
            for idx, el in enumerate(canvas.cena.elementos):
                if idx in movidos or not isinstance(el, dict):
                    continue
                chaves_el = {
                    str(el.get("nome_molde") or "").strip(),
                    str(el.get("molde_id") or "").strip(),
                    str(el.get("id_molde") or "").strip(),
                }
                chaves_el.discard("")
                if chaves_rel.intersection(chaves_el):
                    self._transladar_elemento(el, dx, dy)
                    movidos.add(idx)

            # Fallback espacial: move elementos auxiliares próximos ao molde
            # (ex.: pontos/controles sem metadado explícito de vínculo).
            min_x, min_y, max_x, max_y = info["bbox"]
            margem_x = max(6.0, (max_x - min_x) * 0.35)
            margem_y = max(6.0, (max_y - min_y) * 0.35)
            area_min_x = min_x - margem_x
            area_min_y = min_y - margem_y
            area_max_x = max_x + margem_x
            area_max_y = max_y + margem_y
            for idx, el in enumerate(canvas.cena.elementos):
                if idx in movidos or not isinstance(el, dict) or el.get("molde"):
                    continue
                bb = bbox_por_idx.get(idx)
                if bb is None:
                    continue
                cx = (bb[0] + bb[2]) / 2.0
                cy = (bb[1] + bb[3]) / 2.0
                if area_min_x <= cx <= area_max_x and area_min_y <= cy <= area_max_y:
                    self._transladar_elemento(el, dx, dy)
                    movidos.add(idx)

            # Fallback determinístico: associa cada elemento remanescente
            # ao molde mais próximo (pelo centro do bbox original).
            for idx, el in enumerate(canvas.cena.elementos):
                if idx in movidos or not isinstance(el, dict) or el.get("molde"):
                    continue
                bb = bbox_por_idx.get(idx)
                if bb is None:
                    continue
                ecx = (bb[0] + bb[2]) / 2.0
                ecy = (bb[1] + bb[3]) / 2.0
                melhor_idx_molde = None
                melhor_d2 = None
                for m in moldes:
                    mcx, mcy = float(m["cx"]), float(m["cy"])
                    d2 = ((ecx - mcx) ** 2) + ((ecy - mcy) ** 2)
                    if melhor_d2 is None or d2 < melhor_d2:
                        melhor_d2 = d2
                        melhor_idx_molde = int(m["idx"])
                if melhor_idx_molde == idx_molde:
                    self._transladar_elemento(el, dx, dy)
                    movidos.add(idx)
        if registrar_historico:
            canvas._registrar_historico()
        canvas.update()
        return n

    def _organizar_moldes_no_canvas(self, canvas, variacao: int | None = None, registrar_historico: bool = True) -> int:
        bbox_por_idx: dict[int, tuple[float, float, float, float]] = {}
        for idx, el in enumerate(canvas.cena.elementos):
            if isinstance(el, dict):
                bb = self._bbox_elemento(el)
                if bb is not None:
                    bbox_por_idx[idx] = bb

        moldes_base: list[dict] = []
        for idx, el in enumerate(canvas.cena.elementos):
            if not isinstance(el, dict) or not el.get("molde") or idx not in bbox_por_idx:
                continue
            chaves = {
                str(el.get("molde_id") or "").strip(),
                str(el.get("id_molde") or "").strip(),
                str(el.get("id") or "").strip(),
            }
            chaves.discard("")
            moldes_base.append({"idx": idx, "bbox": bbox_por_idx[idx], "chaves": chaves, "ordem": len(moldes_base)})
        if not moldes_base:
            return 0

        grupos: list[dict] = []
        dono_por_idx: dict[int, int] = {}
        for grupo_idx, info in enumerate(moldes_base):
            idx_molde = int(info["idx"])
            dono_por_idx[idx_molde] = grupo_idx
            grupos.append({"molde_idx": idx_molde, "indices": {idx_molde}, "bbox_molde": info["bbox"], "ordem": info["ordem"]})

        for idx, el in enumerate(canvas.cena.elementos):
            if idx in dono_por_idx or idx not in bbox_por_idx or not isinstance(el, dict) or el.get("molde"):
                continue
            referencias = {
                str(el.get("costura_de_molde_id") or "").strip(),
                str(el.get("molde_id") or "").strip() if bool(el.get("molde_linha_vinculada")) else "",
                str(el.get("id_molde") or "").strip(),
            }
            referencias.discard("")
            for grupo_idx, info in enumerate(moldes_base):
                if referencias and referencias.intersection(info["chaves"]):
                    grupos[grupo_idx]["indices"].add(idx)
                    dono_por_idx[idx] = grupo_idx
                    break

        for idx, el in enumerate(canvas.cena.elementos):
            if idx in dono_por_idx or idx not in bbox_por_idx or not isinstance(el, dict) or el.get("molde"):
                continue
            bb = bbox_por_idx[idx]
            ecx = (bb[0] + bb[2]) / 2.0
            ecy = (bb[1] + bb[3]) / 2.0
            melhor_idx = None
            melhor_d2 = None
            for grupo_idx, info in enumerate(moldes_base):
                mb = info["bbox"]
                mcx = (mb[0] + mb[2]) / 2.0
                mcy = (mb[1] + mb[3]) / 2.0
                diag = max(sqrt((mb[2] - mb[0]) ** 2 + (mb[3] - mb[1]) ** 2), 1.0)
                d2 = ((ecx - mcx) ** 2) + ((ecy - mcy) ** 2)
                if d2 <= (diag * 2.5) ** 2 and (melhor_d2 is None or d2 < melhor_d2):
                    melhor_d2 = d2
                    melhor_idx = grupo_idx
            if melhor_idx is not None:
                grupos[melhor_idx]["indices"].add(idx)
                dono_por_idx[idx] = melhor_idx

        for grupo in grupos:
            boxes = [bbox_por_idx[idx] for idx in grupo["indices"] if idx in bbox_por_idx]
            min_x = min(bb[0] for bb in boxes)
            min_y = min(bb[1] for bb in boxes)
            max_x = max(bb[2] for bb in boxes)
            max_y = max(bb[3] for bb in boxes)
            grupo["bbox"] = (min_x, min_y, max_x, max_y)
            grupo["w"] = max(max_x - min_x, 1.0)
            grupo["h"] = max(max_y - min_y, 1.0)
            grupo["area"] = grupo["w"] * grupo["h"]

        n = len(grupos)
        variacao_idx = int(self._indice_layout_organizacao_moldes if variacao is None else variacao) % 3
        media_w = sum(float(info["w"]) for info in grupos) / n
        media_h = sum(float(info["h"]) for info in grupos) / n
        gap = max(6.0, min(30.0, max(media_w, media_h) * 0.18))
        if variacao_idx == 0:
            ordenados = sorted(grupos, key=lambda info: (-float(info["h"]), -float(info["area"]), int(info["ordem"])))
        elif variacao_idx == 1:
            ordenados = sorted(grupos, key=lambda info: (int(info["ordem"]) % 2, -float(info["area"])))
        else:
            ordenados = sorted(grupos, key=lambda info: (float(info["w"]), -float(info["h"]), int(info["ordem"])))

        largura_total_original = max(max(float(g["bbox"][2]) for g in grupos) - min(float(g["bbox"][0]) for g in grupos), 1.0)
        largura_alvo = max(sqrt(sum(float(g["area"]) for g in grupos)) * 1.35, media_w)
        largura_alvo = min(max(largura_alvo, media_w), max(largura_total_original * 0.75, media_w))

        posicoes: dict[int, tuple[float, float]] = {}
        x = 0.0
        y = 0.0
        linha_h = 0.0
        for grupo in ordenados:
            w = float(grupo["w"])
            h = float(grupo["h"])
            if x > 0.0 and x + w > largura_alvo:
                x = 0.0
                y += linha_h + gap
                linha_h = 0.0
            desloc = min(gap * 0.8, media_w * 0.18) if variacao_idx == 2 and int(y // max(media_h + gap, 1.0)) % 2 else 0.0
            posicoes[int(grupo["molde_idx"])] = (x + desloc, y)
            x += w + gap
            linha_h = max(linha_h, h)

        layout_boxes = []
        for grupo in grupos:
            tx, ty = posicoes[int(grupo["molde_idx"])]
            layout_boxes.append((tx, ty, tx + float(grupo["w"]), ty + float(grupo["h"])))
        layout_min_x = min(bb[0] for bb in layout_boxes)
        layout_min_y = min(bb[1] for bb in layout_boxes)
        layout_max_x = max(bb[2] for bb in layout_boxes)
        layout_max_y = max(bb[3] for bb in layout_boxes)
        original_min_x = min(float(g["bbox"][0]) for g in grupos)
        original_min_y = min(float(g["bbox"][1]) for g in grupos)
        original_max_x = max(float(g["bbox"][2]) for g in grupos)
        original_max_y = max(float(g["bbox"][3]) for g in grupos)
        offset_x = ((original_min_x + original_max_x) / 2.0) - ((layout_min_x + layout_max_x) / 2.0)
        offset_y = ((original_min_y + original_max_y) / 2.0) - ((layout_min_y + layout_max_y) / 2.0)

        for grupo in grupos:
            target_x, target_y = posicoes[int(grupo["molde_idx"])]
            min_x, min_y, _max_x, _max_y = grupo["bbox"]
            dx = (target_x + offset_x) - float(min_x)
            dy = (target_y + offset_y) - float(min_y)
            for idx in sorted(grupo["indices"]):
                if 0 <= idx < len(canvas.cena.elementos) and isinstance(canvas.cena.elementos[idx], dict):
                    self._transladar_elemento(canvas.cena.elementos[idx], dx, dy)
        if registrar_historico:
            canvas._registrar_historico()
        self._emitir_elementos_canvas_alterados(canvas)
        canvas.update()
        return n

    def _organizar_moldes_canvas_atual(self):
        area = self._area_documento_atual()
        if not area:
            self.lbl_status.setText("Nenhum documento ativo para organizar moldes.")
            return
        layout_aplicado = (self._indice_layout_organizacao_moldes % 3) + 1
        qtd = self._organizar_moldes_no_canvas(area.canvas)
        if not qtd:
            self.lbl_status.setText("Nenhum molde encontrado para organizar.")
            return
        self._indice_layout_organizacao_moldes = (self._indice_layout_organizacao_moldes + 1) % 3
        self._centralizar_canvas_em_elementos(area.canvas, [el for el in area.canvas.cena.elementos if el.get("molde")])
        area._on_zoom_changed(area.canvas.zoom)
        self.lbl_status.setText(f"{qtd} molde(s) reorganizado(s). Layout #{layout_aplicado} pronto.")

    def _indices_moldes_canvas_atual(self) -> list[int]:
        area = self._area_documento_atual()
        if not isinstance(area, AreaDocumentoWidget):
            return []
        moldes = self._moldes_do_canvas_atual() if hasattr(self, "cmb_menu_moldes_ordem") else []
        if moldes:
            return [int(idx) for idx, _molde in moldes]
        return [
            idx
            for idx, el in enumerate(area.canvas.cena.elementos)
            if isinstance(el, dict) and el.get("molde") and bool(el.get("menu_moldes_visivel", True))
        ]

    def _visualizar_proximo_molde(self):
        area = self._area_documento_atual()
        if not isinstance(area, AreaDocumentoWidget):
            self.lbl_status.setText("Nenhum documento ativo para visualizar molde.")
            return
        indices = self._indices_moldes_canvas_atual()
        if not indices:
            self.lbl_status.setText("Nenhum molde encontrado para visualizar.")
            return
        atual = next(iter(getattr(area.canvas, "_selecionados", set()) or []), None)
        if atual in indices:
            pos = (indices.index(int(atual)) + 1) % len(indices)
        else:
            self._indice_visualizacao_proximo_molde = (self._indice_visualizacao_proximo_molde + 1) % len(indices)
            pos = self._indice_visualizacao_proximo_molde
        idx = indices[pos]
        self._indice_visualizacao_proximo_molde = pos
        self._selecionar_molde_menu(idx, centralizar=True)
        nome = str(area.canvas.cena.elementos[idx].get("nome_molde") or f"Molde {idx + 1}").strip()
        self.lbl_status.setText(f"Visualizando molde: {nome}")

    def _elementos_visualizacao_instantanea(self, canvas) -> list[dict]:
        elementos = []
        for el in canvas.cena.elementos:
            if not isinstance(el, dict):
                continue
            item = deepcopy(el)
            cor = item.get("cor")
            if item.get("molde") and bool(getattr(canvas, "_mostrar_cor_tecidos", False)):
                tecido = str(item.get("tecido") or "").strip()
                cor = getattr(canvas, "_cores_tecidos", {}).get(tecido, cor)
            item["_cor_visualizacao_instantanea"] = str(cor or self._cores_canvas_global.get("desenho", "#ffffff"))
            elementos.append(item)
        return elementos

    def _alternar_visualizacao_instantanea(self, ativo: bool):
        area = self._area_documento_atual()
        if not isinstance(area, AreaDocumentoWidget):
            if hasattr(self, "btn_visualizacao_instantanea"):
                self.btn_visualizacao_instantanea.blockSignals(True)
                self.btn_visualizacao_instantanea.setChecked(False)
                self.btn_visualizacao_instantanea.blockSignals(False)
            self.lbl_status.setText("Nenhum documento ativo para visualização instantânea.")
            return
        if ativo:
            elementos = self._elementos_visualizacao_instantanea(area.canvas)
            area.canvas.set_visualizacao_instantanea(elementos)
            self.lbl_status.setText("Visualização instantânea adicionada.")
        else:
            area.canvas.set_visualizacao_instantanea(None)
            self.lbl_status.setText("Visualização instantânea removida.")

    def closeEvent(self, event):  # noqa: N802
        if not self._ha_alteracoes_nao_salvas():
            self._salvar_estado_projeto_silenciosamente()
            self._salvar_preferencias_app()
            self._limpar_arquivo_recuperacao()
            event.accept()
            return
        caixa = QMessageBox(self)
        self._estilizar_message_box(caixa)
        caixa.setWindowTitle("Fechar programa")
        caixa.setIcon(QMessageBox.Question)
        caixa.setText("Existem alterações não salvas. Deseja salvar antes de sair?")
        caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        caixa.setDefaultButton(QMessageBox.Yes)
        self._traduzir_botoes_padrao_message_box(caixa)
        resposta = caixa.exec()
        if resposta == QMessageBox.Cancel:
            event.ignore()
            return
        if resposta == QMessageBox.Yes and not self._salvar_projeto():
            event.ignore()
            return
        self._salvar_preferencias_app()
        self._limpar_arquivo_recuperacao()
        event.accept()

    def _ha_alteracoes_nao_salvas(self) -> bool:
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget) and self._tem_alteracoes_area(area):
                return True
        return False

    def _ha_alteracoes_estado_nao_salvas(self) -> bool:
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget) and self._tem_alteracoes_estado_area(area):
                return True
        return False

    def _novo_projeto(self):
        self._adicionar_aba_documento()
        self.backstage.hide()

    def _salvar_snapshot_recuperacao(self):
        documentos: list[dict] = []
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if not isinstance(area, AreaDocumentoWidget):
                continue
            if not self._tem_alteracoes_area(area) and not self._tem_alteracoes_estado_area(area):
                continue
            payload = self._capturar_estado_documento_canvas(area)
            payload["nome"] = self.abas_documentos.tabText(i) or "(Sem nome)"
            documentos.append(payload)
        if not documentos:
            return
        snapshot = {
            "ts": int(time()),
            "arquivo_atual": str(self._arquivo_atual) if self._arquivo_atual else None,
            "documentos": documentos,
        }
        try:
            snapshots = self._carregar_snapshots_recuperacao()
            snapshots.insert(0, snapshot)
            snapshots = snapshots[: self.MAX_SNAPSHOTS_RECUPERACAO]
            payload = {"versao": 2, "snapshots": snapshots}
            self.ARQUIVO_RECUPERACAO.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _limpar_arquivo_recuperacao(self):
        try:
            if self.ARQUIVO_RECUPERACAO.exists():
                self.ARQUIVO_RECUPERACAO.unlink()
        except Exception:
            pass

    def _oferecer_recuperacao_pos_falha(self):
        snapshots = self._carregar_snapshots_recuperacao()
        if not snapshots:
            return
        caixa = QMessageBox(self)
        self._estilizar_message_box(caixa)
        caixa.setWindowTitle("Atenção")
        caixa.setIcon(QMessageBox.Question)
        caixa.setText("Deseja recuperar arquivo(s) perdido(s)?")
        caixa.setOption(QMessageBox.Option.DontUseNativeDialog, True)
        caixa.addButton("Não", QMessageBox.ButtonRole.ActionRole)
        botao_sim = caixa.addButton("Sim", QMessageBox.ButtonRole.ActionRole)
        QTimer.singleShot(0, lambda: self._centralizar_widget_na_tela(caixa))
        caixa.exec()
        if caixa.clickedButton() is not botao_sim:
            return
        self._restaurar_snapshot_recuperacao(snapshots[0])

    def _carregar_snapshots_recuperacao(self) -> list[dict]:
        if not self.ARQUIVO_RECUPERACAO.exists():
            return []
        try:
            bruto = json.loads(self.ARQUIVO_RECUPERACAO.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(bruto, dict) and isinstance(bruto.get("snapshots"), list):
            candidatos = bruto.get("snapshots", [])
        elif isinstance(bruto, dict) and isinstance(bruto.get("documentos"), list):
            candidatos = [bruto]
        else:
            candidatos = []
        snapshots: list[dict] = []
        for item in candidatos:
            if not isinstance(item, dict):
                continue
            docs = item.get("documentos", [])
            if isinstance(docs, list) and docs:
                snapshots.append(item)
        snapshots.sort(key=lambda item: int(item.get("ts", 0) or 0), reverse=True)
        return snapshots[: self.MAX_SNAPSHOTS_RECUPERACAO]

    def _restaurar_snapshot_recuperacao(self, snapshot: dict) -> bool:
        docs = snapshot.get("documentos", []) if isinstance(snapshot, dict) else []
        if not isinstance(docs, list) or not docs:
            return False
        self._limpar_abas_documentos()
        for doc in docs:
            nome = str(doc.get("nome") or "(Recuperado)")
            self._adicionar_aba_documento(nome=nome)
            area = self._area_documento_atual()
            if not area:
                continue
            area.canvas.cena.elementos = [dict(el) for el in doc.get("elementos", [])]
            self._garantir_coordenadas_abertas(area)
            self._restaurar_viewport_documento_canvas(area, doc)
            self._marcar_area_como_salva(area)
            area.canvas.update()
        self._ativar_ferramenta_global("selecionar")
        self.lbl_status.setText("Recuperação concluída.")
        self._agendar_reencaixe_janela_canvas()

        return True

    def _abrir_recuperar_perdidos(self):
        snapshots = self._carregar_snapshots_recuperacao()
        if not snapshots:
            caixa = QMessageBox(self)
            self._estilizar_message_box(caixa)
            caixa.setWindowTitle("Recuperar perdidos")
            caixa.setIcon(QMessageBox.Information)
            caixa.setText("Nenhum arquivo perdido encontrado.")
            caixa.setStandardButtons(QMessageBox.Ok)
            self._traduzir_botoes_padrao_message_box(caixa)
            QTimer.singleShot(0, lambda: self._centralizar_widget_na_tela(caixa))
            caixa.exec()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Recuperar perdidos")
        dialog.resize(640, 420)
        dialog.setMinimumSize(560, 360)
        self._aplicar_estilo_claro_dialogo(dialog)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)
        titulo = QLabel("Arquivos interrompidos encontrados")
        titulo.setStyleSheet(f"color:{self._tema_interface()['primaria_escura']}; font-size:16px; font-weight:700;")
        subtitulo = QLabel("Escolha uma sessão para recuperar as abas e moldes salvos automaticamente.")
        subtitulo.setWordWrap(True)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        lista = QListWidget()
        lista.setAlternatingRowColors(True)
        lista.setSpacing(3)
        lista.setStyleSheet(lista.styleSheet() + "QListWidget::item { padding: 8px 10px; min-height: 34px; }")
        for idx, snapshot in enumerate(snapshots):
            ts = int(snapshot.get("ts", 0) or 0)
            quando = datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S") if ts else "Data desconhecida"
            docs = snapshot.get("documentos", []) or []
            nomes = ", ".join(str(doc.get("nome") or "(Sem nome)") for doc in docs[:3])
            if len(docs) > 3:
                nomes += f" (+{len(docs) - 3})"
            item = QListWidgetItem(f"{quando}\n{len(docs)} aba(s) - {nomes}")
            item.setData(Qt.UserRole, idx)
            lista.addItem(item)
        lista.setCurrentRow(0)
        layout.addWidget(lista)
        botoes = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        botao_abrir = botoes.button(QDialogButtonBox.Open)
        botao_cancelar = botoes.button(QDialogButtonBox.Cancel)
        if botao_abrir is not None:
            botao_abrir.setText("Recuperar")
        if botao_cancelar is not None:
            botao_cancelar.setText("Cancelar")
        layout.addWidget(botoes)
        botoes.accepted.connect(dialog.accept)
        botoes.rejected.connect(dialog.reject)
        QTimer.singleShot(0, lambda: self._centralizar_dialogo_na_janela(dialog))
        if dialog.exec() != QDialog.Accepted:
            return
        item = lista.currentItem()
        if item is None:
            return
        idx = int(item.data(Qt.UserRole))
        if 0 <= idx < len(snapshots):
            self._restaurar_snapshot_recuperacao(snapshots[idx])
            self.backstage.hide()

    def _abrir_projeto(self):
        self.backstage.hide()
        caminho, _ = self._abrir_dialogo_arquivo_claro(
            "Abrir",
            f"Projeto GUIMMA (*{EXTENSAO_PROJETO})",
            com_preview_projeto=True,
        )
        if caminho:
            self._abrir_projeto_em_caminho(caminho)

    def _abrir_projeto_em_caminho(self, caminho: str):
        caminho_resolvido = str(Path(caminho).resolve())
        self._memorizar_diretorio_arquivo(Path(caminho_resolvido))
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget) and area.property("arquivo_origem") == caminho_resolvido:
                self.abas_documentos.setCurrentIndex(i)
                caixa = QMessageBox(self)
                self._estilizar_message_box(caixa)
                caixa.setWindowTitle("Arquivo já aberto")
                caixa.setIcon(QMessageBox.Information)
                caixa.setText(f"O arquivo já está aberto:\n{Path(caminho).name}")
                caixa.setStandardButtons(QMessageBox.Ok)
                self._traduzir_botoes_padrao_message_box(caixa)
                caixa.exec()
                self.backstage.hide()
                return
        self.projeto_atual = GSProjectIO.abrir(caminho)
        self._restaurar_estilo_desenho_memorizado()
        self._posicoes_caixas_aux = self._carregar_posicoes_caixas_aux()
        self._arquivo_atual = Path(caminho)
        self.backstage.adicionar_recente(caminho)
        self._atualizar_titulo()
        self._adicionar_aba_documento(nome=self._arquivo_atual.stem, caminho_origem=caminho_resolvido)
        area = self._area_documento_atual()
        docs = self.projeto_atual.preferencias_usuario.get("documentos_canvas", [])
        if area and docs:
            doc = docs[0]
            area.canvas.cena.elementos = [dict(el) for el in doc.get("elementos", [])]
            area.canvas.set_painel_auxiliar_posicao(self._painel_coordenadas_pos_global)
            self._garantir_coordenadas_abertas(area)
            qtd_moldes_organizados = self._organizar_moldes_no_canvas(area.canvas, variacao=0, registrar_historico=False)
            area.canvas._registrar_historico()
            if qtd_moldes_organizados:
                QTimer.singleShot(0, lambda a=area: self._centralizar_area_documento(a))
            else:
                QTimer.singleShot(0, lambda a=area: self._aplicar_viewport_inicial(a))
            area.canvas.update()
        if area:
            self._marcar_area_como_salva(area)
        self.backstage.hide()
        self._agendar_reencaixe_janela_canvas()

    def _salvar_projeto(self) -> bool:
        if self._arquivo_atual is None:
            return self._salvar_projeto_como()
        self._renomear_abas_sem_nome(self._arquivo_atual.stem)
        self._sincronizar_documentos_canvas_no_projeto()
        GSProjectIO.salvar(self.projeto_atual, self._arquivo_atual)
        self._salvar_thumbnail_projeto(self._arquivo_atual)
        self.backstage.adicionar_recente(str(self._arquivo_atual))
        self._atualizar_titulo()
        self._marcar_documentos_como_salvos()
        self.backstage.hide()
        return True

    def _acao_salvar_pelo_backstage(self):
        self._salvar_projeto()
        self.backstage.hide()

    def _salvar_projeto_como(self) -> bool:
        pasta_inicial = Path(self._diretorio_arquivo_inicial())
        nome_inicial = self._arquivo_atual.stem if self._arquivo_atual else "novo_projeto"
        dlg = SalvarComoDialog(self, pasta_inicial=pasta_inicial, nome_inicial=nome_inicial)
        QTimer.singleShot(0, lambda: self._centralizar_dialogo_na_janela(dlg))
        if dlg.exec():
            destino = dlg.caminho_destino()
            self._memorizar_diretorio_arquivo(destino)
            self.projeto_atual.preferencias_usuario["salvar_como_meta"] = dlg.metadados()
            self._renomear_abas_sem_nome(destino.stem)
            self._sincronizar_documentos_canvas_no_projeto()
            GSProjectIO.salvar(self.projeto_atual, destino)
            self._salvar_thumbnail_projeto(destino)
            self._arquivo_atual = destino
            self.backstage.adicionar_recente(str(destino))
            self._atualizar_titulo()
            self.backstage.hide()
            self._marcar_documentos_como_salvos()
            return True
        return False

    def _renomear_abas_sem_nome(self, nome_arquivo: str):
        total = self.abas_documentos.count()
        if total <= 0:
            return
        for i in range(total):
            nome_atual = (self.abas_documentos.tabText(i) or "").strip()
            if not nome_atual.startswith("(Sem nome)"):
                continue
            novo_nome = nome_arquivo if total == 1 else f"{nome_arquivo} -{i + 1}"
            self.abas_documentos.setTabText(i, novo_nome)

    @staticmethod
    def _indice_nome_aba_sem_nome(nome: str | None) -> int | None:
        texto = str(nome or "").strip()
        base = "(Sem nome)"
        if texto == base:
            return 1
        if not texto.startswith(base):
            return None
        sufixo = texto[len(base):].strip()
        if sufixo.startswith("-"):
            sufixo = sufixo[1:].strip()
        if not sufixo.isdigit():
            return None
        return max(1, int(sufixo))

    @staticmethod
    def _formatar_nome_aba_sem_nome(indice: int) -> str:
        indice = max(1, int(indice))
        return "(Sem nome)" if indice == 1 else f"(Sem nome)-{indice}"

    def _proximo_nome_aba_sem_nome(self) -> str:
        usados: set[int] = set()
        for i in range(self.abas_documentos.count()):
            indice = self._indice_nome_aba_sem_nome(self.abas_documentos.tabText(i))
            if indice is not None:
                usados.add(indice)
        indice = 1
        while indice in usados:
            indice += 1
        return self._formatar_nome_aba_sem_nome(indice)

    def _renumerar_abas_sem_nome(self) -> None:
        indices_abas = [
            i
            for i in range(self.abas_documentos.count())
            if self._indice_nome_aba_sem_nome(self.abas_documentos.tabText(i)) is not None
        ]
        for ordem, indice_aba in enumerate(indices_abas, start=1):
            self.abas_documentos.setTabText(indice_aba, self._formatar_nome_aba_sem_nome(ordem))

    def _atualizar_titulo(self):
        self.setWindowTitle("GUIMMA STUDIO")

    def _criar_area_documento(self) -> QWidget:
        area = QWidget()
        self.area_documento_widget = area
        area.setStyleSheet(f"background: {self._tema_interface()['area']};")
        area.setMinimumSize(0, 0)

        layout_externo = QHBoxLayout(area)
        layout_externo.setContentsMargins(6, 4, 6, 4)
        layout_externo.setSpacing(6)

        self.barra_lateral_ferramentas = None
        try:
            self.barra_lateral_ferramentas = self._criar_barra_lateral_ferramentas()
            layout_externo.addWidget(self.barra_lateral_ferramentas, 0)
        except Exception as exc:
            print(f"[GUIMMA][barra_lateral] Falha ao criar barra lateral: {type(exc).__name__}: {exc}")

        area_principal = QWidget()
        area_principal.setMinimumSize(0, 0)
        layout = QVBoxLayout(area_principal)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout_externo.addWidget(area_principal, 1)

        self.host_barra_usuario_area = QWidget()
        self.host_barra_usuario_area_layout = QVBoxLayout(self.host_barra_usuario_area)
        self.host_barra_usuario_area_layout.setContentsMargins(0, 0, 0, 0)
        self.host_barra_usuario_area_layout.setSpacing(0)
        layout.addWidget(self.host_barra_usuario_area)
        self._criar_linha_usuarios()
        self.abas_documentos = QTabWidget()
        self.abas_documentos.setMinimumSize(0, 0)
        self.abas_documentos.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.abas_documentos.setTabsClosable(False)
        self.abas_documentos.setMovable(True)
        self.abas_documentos.tabBar().setExpanding(False)
        self.abas_documentos.tabBar().setUsesScrollButtons(True)
        self.abas_documentos.currentChanged.connect(self._on_aba_documento_alterada)
        self.abas_documentos.tabBar().tabMoved.connect(lambda _from, _to: self._reconfigurar_botoes_fechar_abas())
        self.abas_documentos.setStyleSheet(self._estilo_abas_documentos())
        self.painel_menu_moldes = self._criar_painel_menu_moldes()
        self.splitter_documentos = QSplitter(Qt.Horizontal)
        self.splitter_documentos.setChildrenCollapsible(False)
        self.splitter_documentos.setHandleWidth(4)
        self.splitter_documentos.addWidget(self.abas_documentos)
        self.splitter_documentos.addWidget(self.painel_menu_moldes)
        self.splitter_documentos.setStretchFactor(0, 1)
        self.splitter_documentos.setStretchFactor(1, 0)
        self.splitter_documentos.setSizes([1200, 168])
        self.painel_menu_moldes.setVisible(self.action_menu_moldes.isChecked())
        if self.action_menu_moldes.isChecked():
            self._ajustar_splitter_menu_moldes(
                int(self.projeto_atual.preferencias_usuario.get("menu_moldes_largura", 168) or 168)
            )
            self._iniciar_monitor_menu_moldes()
        layout.addWidget(self.splitter_documentos, 1)
        self._reposicionar_barra_usuarios()
        self._atualizar_linha_usuarios()
        self._atualizar_menu_moldes()
        self._on_tab_ribbon_alterada(self.ribbon.current_tab_id() or "inicio")
        self._atualizar_barra_lateral_ferramentas()
        return area

    def _criar_barra_lateral_ferramentas(self) -> QWidget:
        painel = QFrame()
        painel.setObjectName("BarraLateralFerramentas")
        painel.setFixedWidth(154)
        painel.setMinimumHeight(0)
        painel.setStyleSheet(self._estilo_barra_lateral_usuario())

        layout_painel = QVBoxLayout(painel)
        layout_painel.setContentsMargins(0, 0, 0, 0)
        layout_painel.setSpacing(0)

        titulo = QLabel("USUÁRIO")
        titulo.setObjectName("TituloBarraLateralFerramentas")
        self.lbl_titulo_barra_lateral_ferramentas = titulo
        layout_painel.addWidget(titulo, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        conteudo = QWidget()
        self.layout_barra_lateral_ferramentas = QVBoxLayout(conteudo)
        self.layout_barra_lateral_ferramentas.setContentsMargins(6, 0, 6, 8)
        self.layout_barra_lateral_ferramentas.setSpacing(2)
        scroll.setWidget(conteudo)
        layout_painel.addWidget(scroll, 1)

        return painel

    def _criar_botao_barra_lateral_ferramenta(self, tool_id: str, somente_icone: bool = False):
        try:
            tool = self.ribbon.tool_def(tool_id) if hasattr(self, "ribbon") else None
            if not tool:
                return None

            btn = QToolButton()
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly if somente_icone else Qt.ToolButtonTextBesideIcon)
            try:
                icon_name = getattr(tool, "icon", "")
                caminho_icone = ICONS_DIR / icon_name if icon_name else None
                if caminho_icone is not None and caminho_icone.exists():
                    btn.setIcon(carregar_icone(icon_name))
            except Exception:
                pass
            btn.setIconSize(QSize(18, 18))
            btn.setText("" if somente_icone else tool.title)
            btn.setToolTip(tool.title)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("tool_id", tool_id)
            if somente_icone:
                btn.setFixedSize(38, 34)
                btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            else:
                btn.setFixedHeight(31)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(self._estilo_botao_barra_lateral_usuario())
            btn.clicked.connect(lambda _=False, tid=tool_id: self._abrir_pagina_ferramenta(tid))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda _pos, tid=tool_id: self._remover_ferramenta_usuario(tid))
            return btn
        except Exception as exc:
            print(f"[GUIMMA][barra_lateral] Falha ao criar botão {tool_id}: {type(exc).__name__}: {exc}")
            return None

    def _atualizar_barra_lateral_ferramentas(self):
        try:
            if not hasattr(self, "layout_barra_lateral_ferramentas") or not hasattr(self, "barra_lateral_ferramentas"):
                return

            mostrar_lateral = bool(self._barra_usuarios_habilitada) and self._barra_usuarios_posicao == "lateral"
            self.barra_lateral_ferramentas.setVisible(mostrar_lateral)
            if not mostrar_lateral:
                return

            while self.layout_barra_lateral_ferramentas.count():
                item = self.layout_barra_lateral_ferramentas.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

            ativo = getattr(self, "_ferramenta_ativa_id", "selecionar")
            somente_icone = getattr(self, "_barra_usuarios_modo_lateral", "completa") == "icones"
            self.barra_lateral_ferramentas.setFixedWidth(58 if somente_icone else 154)
            if hasattr(self, "lbl_titulo_barra_lateral_ferramentas"):
                self.lbl_titulo_barra_lateral_ferramentas.setText("USUÁRIO")
                self.lbl_titulo_barra_lateral_ferramentas.setAlignment(Qt.AlignCenter if somente_icone else (Qt.AlignLeft | Qt.AlignVCenter))

            if not self._ferramentas_usuario_ids:
                vazio = QLabel("Sem atalhos")
                vazio.setAlignment(Qt.AlignCenter)
                vazio.setToolTip("Sem ferramentas na barra de usuário.")
                vazio.setStyleSheet("color:#64748b; font-size:11px; padding:8px;")
                self.layout_barra_lateral_ferramentas.addWidget(vazio)
                self.layout_barra_lateral_ferramentas.addStretch(1)
                return

            for tool_id in self._ferramentas_usuario_ids:
                botao = self._criar_botao_barra_lateral_ferramenta(tool_id, somente_icone=somente_icone)
                if botao is None:
                    continue
                botao.setChecked(tool_id == ativo)
                if somente_icone:
                    wrap = QWidget()
                    hlay = QHBoxLayout(wrap)
                    hlay.setContentsMargins(0, 0, 0, 0)
                    hlay.addStretch(1)
                    hlay.addWidget(botao)
                    hlay.addStretch(1)
                    self.layout_barra_lateral_ferramentas.addWidget(wrap)
                else:
                    self.layout_barra_lateral_ferramentas.addWidget(botao)

            self.layout_barra_lateral_ferramentas.addStretch(1)
        except Exception as exc:
            print(f"[GUIMMA][barra_lateral] Falha ao atualizar barra lateral: {type(exc).__name__}: {exc}")

    def _criar_painel_menu_moldes(self) -> QWidget:
        painel = QFrame()
        painel.setObjectName("PainelMenuMoldes")
        painel.setMinimumWidth(136)
        painel.setMaximumWidth(220)
        painel.setStyleSheet(
            """
            QFrame#PainelMenuMoldes { background:#f4f4f4; border-left:1px solid #c9cdd2; }
            QLabel { color:#111111; }
            QComboBox { background:#ffffff; color:#111111; border:1px solid #b7b7b7; min-height:20px; }
            QToolButton, QPushButton { background:#ffffff; color:#111111; border:1px solid #c2c7cc; border-radius:2px; }
            QToolButton:hover, QPushButton:hover { background:#e9f3ff; border-color:#7eb0d8; }
            """
        )
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(3)

        titulo = QLabel("Menu de moldes")
        titulo.setStyleSheet("font-size:12px; font-weight:600;")
        lay.addWidget(titulo)

        barra = QHBoxLayout()
        barra.setContentsMargins(0, 0, 0, 0)
        barra.setSpacing(2)
        self.cmb_menu_moldes_ordem = QComboBox()
        self.cmb_menu_moldes_ordem.addItems(["Ordenar por", "Nome", "Tecido", "Prontos primeiro"])
        self.cmb_menu_moldes_ordem.currentTextChanged.connect(lambda _=None: self._atualizar_menu_moldes())
        barra.addWidget(self.cmb_menu_moldes_ordem, 1)
        btn_tamanho = QToolButton()
        btn_tamanho.setText("▦")
        btn_tamanho.setToolTip("Tamanho do painel")
        menu_tam = QMenu(btn_tamanho)
        for texto, largura in (("Painel pequeno", 136), ("Painel médio", 168), ("Painel grande", 220)):
            acao = menu_tam.addAction(texto)
            acao.triggered.connect(lambda _=False, w=largura: self._definir_largura_menu_moldes(w))
        btn_tamanho.setMenu(menu_tam)
        btn_tamanho.setPopupMode(QToolButton.InstantPopup)
        barra.addWidget(btn_tamanho)
        lay.addLayout(barra)

        self.scroll_menu_moldes = QScrollArea()
        self.scroll_menu_moldes.setWidgetResizable(True)
        self.scroll_menu_moldes.setFrameShape(QFrame.NoFrame)
        self.conteudo_menu_moldes = QWidget()
        self.layout_menu_moldes = QVBoxLayout(self.conteudo_menu_moldes)
        self.layout_menu_moldes.setContentsMargins(0, 0, 0, 0)
        self.layout_menu_moldes.setSpacing(3)
        self.scroll_menu_moldes.setWidget(self.conteudo_menu_moldes)
        lay.addWidget(self.scroll_menu_moldes, 1)
        return painel

    def _ajustar_splitter_menu_moldes(self, largura: int):
        if not hasattr(self, "splitter_documentos") or not hasattr(self, "painel_menu_moldes"):
            return
        largura = max(136, min(260, int(largura or 168)))
        tamanhos = self.splitter_documentos.sizes()
        total = sum(tamanhos)
        if total <= 0:
            total = max(self.splitter_documentos.width(), self.width(), largura + 640)
        esquerda = max(320, total - largura)
        self.splitter_documentos.setSizes([esquerda, largura])
        self.painel_menu_moldes.setVisible(True)
        self.painel_menu_moldes.raise_()

    def _definir_largura_menu_moldes(self, largura: int, salvar: bool = True):
        if not hasattr(self, "painel_menu_moldes"):
            return
        largura = max(136, min(260, int(largura or 168)))
        self.painel_menu_moldes.setMinimumWidth(largura)
        self.painel_menu_moldes.setMaximumWidth(largura)
        if self.action_menu_moldes.isChecked():
            self._ajustar_splitter_menu_moldes(largura)
        self.projeto_atual.preferencias_usuario["menu_moldes_largura"] = largura
        if salvar:
            self._salvar_preferencias_app()

    def _alternar_menu_moldes(self, visivel: bool):
        self.projeto_atual.preferencias_usuario["menu_moldes_visivel"] = bool(visivel)
        if hasattr(self, "painel_menu_moldes"):
            self.painel_menu_moldes.setVisible(bool(visivel))
            if visivel:
                largura = int(self.projeto_atual.preferencias_usuario.get("menu_moldes_largura", 168) or 168)
                self._definir_largura_menu_moldes(largura, salvar=False)
                self._ajustar_splitter_menu_moldes(largura)
                self._atualizar_menu_moldes()
                self._iniciar_monitor_menu_moldes()
            else:
                self._parar_monitor_menu_moldes()
        self._salvar_preferencias_app()
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText("Menu de moldes visível" if visivel else "Menu de moldes oculto")

    def _iniciar_monitor_menu_moldes(self):
        if hasattr(self, "_timer_menu_moldes") and not self._timer_menu_moldes.isActive():
            self._timer_menu_moldes.start()

    def _parar_monitor_menu_moldes(self):
        if hasattr(self, "_timer_menu_moldes"):
            self._timer_menu_moldes.stop()
        self._assinatura_menu_moldes = None

    def _assinatura_geometria_molde_menu(self, molde: dict) -> tuple:
        pontos = []
        for pt in molde.get("pontos", []) or []:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    pontos.append((round(float(pt[0]), 3), round(float(pt[1]), 3)))
                except (TypeError, ValueError):
                    continue
        return tuple(pontos)

    def _assinatura_estado_menu_moldes(self) -> tuple:
        if not hasattr(self, "abas_documentos"):
            return ("sem_abas",)
        area = self.abas_documentos.currentWidget()
        if not isinstance(area, AreaDocumentoWidget):
            return ("sem_documento", self.abas_documentos.currentIndex())
        canvas = area.canvas
        selecionados = tuple(sorted(int(i) for i in getattr(canvas, "_selecionados", set()) or []))
        cores_tecidos = tuple(sorted((str(k), str(v)) for k, v in getattr(canvas, "_cores_tecidos", {}).items()))
        ordem = self.cmb_menu_moldes_ordem.currentText() if hasattr(self, "cmb_menu_moldes_ordem") else ""
        moldes = []
        for idx, molde in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if not isinstance(molde, dict) or not molde.get("molde"):
                continue
            moldes.append(
                (
                    idx,
                    str(molde.get("molde_id") or molde.get("id") or ""),
                    str(molde.get("nome_molde") or molde.get("nome") or ""),
                    str(molde.get("tecido") or molde.get("grupo_molde") or ""),
                    str(molde.get("cor") or ""),
                    bool(molde.get("menu_moldes_visivel", True)),
                    bool(molde.get("molde_pronto", True)),
                    self._assinatura_geometria_molde_menu(molde),
                )
            )
        return (
            id(area),
            self.abas_documentos.currentIndex(),
            ordem,
            selecionados,
            bool(getattr(canvas, "_mostrar_cor_tecidos", False)),
            cores_tecidos,
            tuple(moldes),
        )

    def _sincronizar_menu_moldes_ao_vivo(self):
        if not hasattr(self, "action_menu_moldes") or not self.action_menu_moldes.isChecked():
            self._parar_monitor_menu_moldes()
            return
        assinatura = self._assinatura_estado_menu_moldes()
        if assinatura != self._assinatura_menu_moldes:
            self._atualizar_menu_moldes()

    def _limpar_layout_menu_moldes(self):
        if not hasattr(self, "layout_menu_moldes"):
            return
        while self.layout_menu_moldes.count():
            item = self.layout_menu_moldes.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _moldes_do_canvas_atual(self) -> list[tuple[int, dict]]:
        area = self._area_documento_atual()
        if not isinstance(area, AreaDocumentoWidget):
            return []
        itens = [(idx, el) for idx, el in enumerate(area.canvas.cena.elementos) if isinstance(el, dict) and el.get("molde")]
        ordem = self.cmb_menu_moldes_ordem.currentText() if hasattr(self, "cmb_menu_moldes_ordem") else ""
        if ordem == "Nome":
            itens.sort(key=lambda item: str(item[1].get("nome_molde") or "").lower())
        elif ordem == "Tecido":
            itens.sort(key=lambda item: (str(item[1].get("tecido") or ""), str(item[1].get("nome_molde") or "").lower()))
        elif ordem == "Prontos primeiro":
            itens.sort(key=lambda item: (not bool(item[1].get("molde_pronto", True)), str(item[1].get("nome_molde") or "").lower()))
        return itens

    def _atualizar_menu_moldes(self):
        if not hasattr(self, "painel_menu_moldes") or not self.action_menu_moldes.isChecked():
            return
        self._limpar_layout_menu_moldes()
        area = self._area_documento_atual()
        if not isinstance(area, AreaDocumentoWidget):
            self.layout_menu_moldes.addWidget(QLabel("Sem documento ativo."))
            self.layout_menu_moldes.addStretch(1)
            self._assinatura_menu_moldes = self._assinatura_estado_menu_moldes()
            return
        selecionados = set(getattr(area.canvas, "_selecionados", set()) or set())
        moldes = self._moldes_do_canvas_atual()
        if not moldes:
            vazio = QLabel("Sem moldes neste arquivo.")
            vazio.setStyleSheet("font-size:11px; color:#555555; padding:8px;")
            self.layout_menu_moldes.addWidget(vazio)
            self.layout_menu_moldes.addStretch(1)
            self._assinatura_menu_moldes = self._assinatura_estado_menu_moldes()
            return
        for idx, molde in moldes:
            self.layout_menu_moldes.addWidget(self._criar_item_menu_molde(area, idx, molde, idx in selecionados))
        self.layout_menu_moldes.addStretch(1)
        self._assinatura_menu_moldes = self._assinatura_estado_menu_moldes()

    def _criar_item_menu_molde(self, area: AreaDocumentoWidget, idx: int, molde: dict, selecionado: bool) -> QWidget:
        row = QFrame()
        row.setObjectName("ItemMenuMolde")
        row.setProperty("indice_molde", idx)
        row.setCursor(Qt.PointingHandCursor)
        row.setStyleSheet(
            "QFrame#ItemMenuMolde { background:%s; border:1px solid %s; }"
            % ("#cceeff" if selecionado else "#ffffff", "#6eb8d8" if selecionado else "#d3d3d3")
        )
        lay = QVBoxLayout(row)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)

        cab = QHBoxLayout()
        cab.setContentsMargins(0, 0, 0, 0)
        chk = QCheckBox()
        chk.setChecked(bool(molde.get("menu_moldes_visivel", True)))
        chk.setToolTip("Mostrar este molde no canvas")
        chk.toggled.connect(lambda marcado, i=idx: self._definir_visibilidade_molde_menu(i, bool(marcado)))
        cab.addWidget(chk, 0)
        nome = str(molde.get("nome_molde") or f"Molde {idx + 1}").strip()
        lbl = QLabel(nome)
        lbl.setToolTip(nome)
        lbl.setStyleSheet("font-size:11px; font-weight:600; color:#111111;")
        cab.addWidget(lbl, 1)
        lay.addLayout(cab)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setMinimumHeight(76)
        thumb.setPixmap(QPixmap.fromImage(self._gerar_thumbnail_molde_menu(area.canvas, molde, 108, 76)))
        lay.addWidget(thumb)

        if selecionado:
            atalhos = QHBoxLayout()
            atalhos.setContentsMargins(0, 0, 0, 0)
            atalhos.setSpacing(2)
            for texto, dica, acao in (
                ("F", "Centralizar este molde", "foco"),
                ("P", "Propriedades", "propriedades"),
                ("Pt", "Manipular pontos", "manipular_pontos"),
                ("Mv", "Mover", "mover"),
            ):
                btn = QToolButton()
                btn.setText(texto)
                btn.setToolTip(dica)
                btn.setFixedSize(24 if len(texto) == 1 else 28, 20)
                btn.clicked.connect(lambda _=False, i=idx, a=acao: self._atalho_menu_molde(i, a))
                atalhos.addWidget(btn)
            atalhos.addStretch(1)
            lay.addLayout(atalhos)

        def selecionar(_event=None, i=idx):
            self._selecionar_molde_menu(i, centralizar=True)

        row.mousePressEvent = selecionar
        thumb.mousePressEvent = selecionar
        lbl.mousePressEvent = selecionar
        return row

    def _cor_menu_molde(self, canvas, molde: dict) -> QColor:
        tecido = str(molde.get("tecido") or "").strip()
        cor = None
        if tecido and bool(getattr(self, "_mostrar_cor_tecidos_menu_global", False)):
            cor = getattr(canvas, "_cores_tecidos", {}).get(tecido)
        if not cor:
            cor = molde.get("cor") or "#ffea00"
        qcor = QColor(str(cor))
        return qcor if qcor.isValid() else QColor("#ffea00")

    def _gerar_thumbnail_molde_menu(self, canvas, molde: dict, largura: int, altura: int) -> QImage:
        img = QImage(int(largura), int(altura), QImage.Format_ARGB32)
        img.fill(QColor("#f7f7f7"))
        pontos: list[tuple[float, float]] = []
        for pt in molde.get("pontos", []) or []:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    pontos.append((float(pt[0]), float(pt[1])))
                except (TypeError, ValueError):
                    continue
        if len(pontos) < 2:
            return img
        xs = [x for x, _ in pontos]
        ys = [y for _, y in pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        geo_w = max(max_x - min_x, 1.0)
        geo_h = max(max_y - min_y, 1.0)
        margem = 7
        escala = min((largura - margem * 2) / geo_w, (altura - margem * 2) / geo_h)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        path = QPainterPath()
        for i, (x, y) in enumerate(pontos):
            sx = (x - cx) * escala + (largura / 2)
            sy = (y - cy) * escala + (altura / 2)
            if i == 0:
                path.moveTo(sx, sy)
            else:
                path.lineTo(sx, sy)
        if len(pontos) > 2:
            path.closeSubpath()
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        cor = self._cor_menu_molde(canvas, molde)
        painter.setBrush(cor)
        painter.setPen(QPen(cor.darker(125), 1))
        painter.drawPath(path)
        painter.end()
        return img

    def _selecionar_molde_menu(self, idx: int, centralizar: bool = True):
        area = self._area_documento_atual()
        if not isinstance(area, AreaDocumentoWidget) or not (0 <= idx < len(area.canvas.cena.elementos)):
            return
        area.canvas._selecionados = {idx}
        if centralizar:
            self._centralizar_canvas_em_elementos(area.canvas, [area.canvas.cena.elementos[idx]], zoom_max=30.0)
            area._on_zoom_changed(area.canvas.zoom)
        area.canvas.update()
        self._atualizar_menu_moldes()
        self.lbl_status.setText("Clique para visualizar este molde")

    def _definir_visibilidade_molde_menu(self, idx: int, visivel: bool):
        area = self._area_documento_atual()
        if not isinstance(area, AreaDocumentoWidget) or not (0 <= idx < len(area.canvas.cena.elementos)):
            return
        molde = area.canvas.cena.elementos[idx]
        if not isinstance(molde, dict) or not molde.get("molde"):
            return
        molde["menu_moldes_visivel"] = bool(visivel)
        if not visivel:
            molde["molde_pronto"] = False
        else:
            molde["molde_pronto"] = True
        area.canvas._selecionados.discard(idx)
        if hasattr(area.canvas, "_registrar_historico"):
            area.canvas._registrar_historico()
        area.canvas.update()
        self._agendar_salvar_estado_silencioso()
        self._atualizar_menu_moldes()

    def _atalho_menu_molde(self, idx: int, acao: str):
        self._selecionar_molde_menu(idx, centralizar=(acao == "foco"))
        if acao == "propriedades":
            self._abrir_propriedades_diretamente()
        elif acao in {"manipular_pontos", "mover"}:
            self._ativar_ferramenta_global(acao)

    def _criar_linha_usuarios(self):
        if hasattr(self, "faixa_usuarios"):
            return
        faixa = QFrame()
        faixa.setFixedHeight(42)
        tema = self._tema_interface()
        faixa.setStyleSheet(f"QFrame {{ background:{tema['faixa']}; border:1px solid {tema['borda']}; }}")
        lay = QHBoxLayout(faixa)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(6)

        self.btn_usuario_add_all = QPushButton("Adicionar todas da aba")
        self.btn_usuario_add_all.setCursor(Qt.PointingHandCursor)
        self.btn_usuario_add_all.setFixedHeight(26)
        self.btn_usuario_add_all.clicked.connect(self._adicionar_todas_ferramentas_da_aba)
        self.btn_usuario_add_all.setStyleSheet(self._estilo_botoes_usuario())

        self.btn_usuario_limpar = QPushButton("Limpar linha")
        self.btn_usuario_limpar.setCursor(Qt.PointingHandCursor)
        self.btn_usuario_limpar.setFixedHeight(26)
        self.btn_usuario_limpar.clicked.connect(self._limpar_ferramentas_usuario)
        self.btn_usuario_limpar.setStyleSheet(self._estilo_botoes_usuario())

        self.linha_usuario = _LinhaUsuarioDropArea(self)
        self.layout_linha_usuario = QHBoxLayout(self.linha_usuario)
        self.layout_linha_usuario.setContentsMargins(4, 0, 4, 0)
        self.layout_linha_usuario.setSpacing(3)
        lay.addWidget(self.linha_usuario, 1)

        self.painel_controles_usuario = QWidget()
        controles_layout = QHBoxLayout(self.painel_controles_usuario)
        controles_layout.setContentsMargins(0, 0, 0, 0)
        controles_layout.setSpacing(4)

        lbl_usuario = QLabel("Usuário:")
        lbl_usuario.setStyleSheet(f"color:{tema['texto']}; font-size:12px; font-weight:400;")
        controles_layout.addWidget(lbl_usuario, 0)

        self.combo_perfil_usuario = QComboBox()
        self.combo_perfil_usuario.setMinimumWidth(130)
        self.combo_perfil_usuario.setStyleSheet(self._estilo_combo_usuario())
        self.combo_perfil_usuario.currentTextChanged.connect(self._trocar_perfil_usuario)
        controles_layout.addWidget(self.combo_perfil_usuario, 0)

        self.btn_novo_perfil_usuario = QPushButton("Novo")
        self.btn_novo_perfil_usuario.setCursor(Qt.PointingHandCursor)
        self.btn_novo_perfil_usuario.setFixedHeight(26)
        self.btn_novo_perfil_usuario.clicked.connect(self._criar_novo_perfil_usuario)
        self.btn_novo_perfil_usuario.setStyleSheet(self.btn_usuario_add_all.styleSheet())
        controles_layout.addWidget(self.btn_novo_perfil_usuario, 0)

        self.btn_salvar_perfil_usuario = QPushButton("Salvar usuário")
        self.btn_salvar_perfil_usuario.setCursor(Qt.PointingHandCursor)
        self.btn_salvar_perfil_usuario.setFixedHeight(26)
        self.btn_salvar_perfil_usuario.clicked.connect(self._salvar_perfil_usuario_atual)
        self.btn_salvar_perfil_usuario.setStyleSheet(self.btn_usuario_add_all.styleSheet())
        controles_layout.addWidget(self.btn_salvar_perfil_usuario, 0)

        controles_layout.addWidget(self.btn_usuario_add_all, 0)
        controles_layout.addWidget(self.btn_usuario_limpar, 0)
        lay.addWidget(self.painel_controles_usuario, 0)
        self._atualizar_combo_perfis_usuarios()
        self.painel_controles_usuario.setVisible(False)

        self.faixa_usuarios = faixa

    def _on_tab_ribbon_alterada(self, tab_id: str):
        if tab_id != "usuarios":
            self._ultima_aba_nao_usuario = tab_id
        self._atualizar_visibilidade_barra_usuarios(tab_id)
        if hasattr(self, "painel_controles_usuario"):
            self.painel_controles_usuario.setVisible(tab_id == "usuarios")

    def _alternar_barra_usuarios_habilitada(self, habilitada: bool):
        self._barra_usuarios_habilitada = bool(habilitada)
        self.projeto_atual.preferencias_usuario["barra_usuarios_habilitada"] = bool(habilitada)
        self._reposicionar_barra_usuarios()
        self._atualizar_visibilidade_barra_usuarios(self.ribbon.current_tab_id() or "inicio")
        self._sincronizar_menu_barra_usuarios()
        self._salvar_preferencias_app()

    def _definir_posicao_barra_usuarios(self, posicao: str):
        if posicao not in {"topo", "area", "lateral"}:
            return
        self._barra_usuarios_posicao = posicao
        self.projeto_atual.preferencias_usuario["barra_usuarios_posicao"] = posicao
        self._reposicionar_barra_usuarios()
        self._atualizar_visibilidade_barra_usuarios(self.ribbon.current_tab_id() or "inicio")
        self._sincronizar_menu_barra_usuarios()
        self._salvar_preferencias_app()

    def _definir_modo_barra_usuarios_lateral(self, modo: str):
        if modo not in {"completa", "icones"}:
            return
        self._barra_usuarios_modo_lateral = modo
        self.projeto_atual.preferencias_usuario["barra_usuarios_modo_lateral"] = modo
        self._atualizar_barra_lateral_ferramentas()
        self._sincronizar_menu_barra_usuarios()
        self._salvar_preferencias_app()

    def _sincronizar_menu_barra_usuarios(self):
        if hasattr(self, "action_barra_usuarios_habilitada"):
            self.action_barra_usuarios_habilitada.blockSignals(True)
            self.action_barra_usuarios_habilitada.setChecked(bool(self._barra_usuarios_habilitada))
            self.action_barra_usuarios_habilitada.blockSignals(False)
        if hasattr(self, "action_barra_usuarios_topo"):
            self.action_barra_usuarios_topo.setChecked(self._barra_usuarios_posicao == "topo")
        if hasattr(self, "action_barra_usuarios_area"):
            self.action_barra_usuarios_area.setChecked(self._barra_usuarios_posicao == "area")
        if hasattr(self, "action_barra_usuarios_lateral"):
            self.action_barra_usuarios_lateral.setChecked(self._barra_usuarios_posicao == "lateral")
        if hasattr(self, "action_barra_usuarios_lateral_completa"):
            self.action_barra_usuarios_lateral_completa.setChecked(self._barra_usuarios_modo_lateral == "completa")
        if hasattr(self, "action_barra_usuarios_lateral_icones"):
            self.action_barra_usuarios_lateral_icones.setChecked(self._barra_usuarios_modo_lateral == "icones")

    def _reposicionar_barra_usuarios(self):
        if not hasattr(self, "faixa_usuarios"):
            return
        if self.faixa_usuarios.parentWidget() is not None:
            self.faixa_usuarios.setParent(None)
        if not self._barra_usuarios_habilitada:
            self.faixa_usuarios.hide()
        elif self._barra_usuarios_posicao == "topo":
            self.host_barra_usuario_topo_layout.addWidget(self.faixa_usuarios)
            self.faixa_usuarios.show()
        elif self._barra_usuarios_posicao == "area":
            self.host_barra_usuario_area_layout.addWidget(self.faixa_usuarios)
            self.faixa_usuarios.show()
        else:
            self.faixa_usuarios.hide()
        self._atualizar_barra_lateral_ferramentas()

    def _atualizar_visibilidade_barra_usuarios(self, tab_id: str):
        visivel = self._barra_usuarios_habilitada or (tab_id == "usuarios")
        if hasattr(self, "faixa_usuarios"):
            mostrar_faixa = visivel and self._barra_usuarios_posicao in {"topo", "area"}
            self.faixa_usuarios.setVisible(mostrar_faixa)
        if hasattr(self, "barra_lateral_ferramentas") and self.barra_lateral_ferramentas is not None:
            mostrar_lateral = visivel and self._barra_usuarios_posicao == "lateral"
            self.barra_lateral_ferramentas.setVisible(mostrar_lateral)
            if mostrar_lateral:
                self._atualizar_barra_lateral_ferramentas()

    def _lista_usuario_com_ajuste(self, ids: list[str]) -> list[str]:
        saida = list(ids or [])
        if "ajuste_automatico" not in saida:
            try:
                indice_refazer = saida.index("refazer")
                saida.insert(indice_refazer + 1, "ajuste_automatico")
            except ValueError:
                saida.append("ajuste_automatico")
        return saida

    def _garantir_ajuste_automatico_na_barra_usuario(self):
        """Mantém ferramentas fixas na barra de Usuário, mesmo ao limpar/trocar perfil."""
        if not hasattr(self, "_ferramentas_usuario_ids"):
            return
        if "ajuste_automatico" not in self._ferramentas_usuario_ids:
            try:
                indice_refazer = self._ferramentas_usuario_ids.index("refazer")
                self._ferramentas_usuario_ids.insert(indice_refazer + 1, "ajuste_automatico")
            except ValueError:
                self._ferramentas_usuario_ids.append("ajuste_automatico")
        if "ponto_restauracao" not in self._ferramentas_usuario_ids:
            try:
                indice_restaurar = self._ferramentas_usuario_ids.index("restaurar_copia")
                self._ferramentas_usuario_ids.insert(indice_restaurar, "ponto_restauracao")
            except ValueError:
                self._ferramentas_usuario_ids.append("ponto_restauracao")
        if "restaurar_copia" not in self._ferramentas_usuario_ids:
            self._ferramentas_usuario_ids.append("restaurar_copia")

    def _adicionar_ferramenta_usuario(self, tool_id: str):
        if tool_id not in self._ferramentas_usuario_ids:
            self._ferramentas_usuario_ids.append(tool_id)
            self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(self._ferramentas_usuario_ids)
            self._sincronizar_perfil_usuario_atual()
            self._atualizar_linha_usuarios()
        tool = self.ribbon.tool_def(tool_id)
        if tool:
            self.lbl_status.setText(f"{tool.title} adicionada à linha Usuários.")

    def _adicionar_todas_ferramentas_da_aba(self):
        tab_id = self._ultima_aba_nao_usuario or "construcao"
        self._adicionar_todas_ferramentas_da_aba_id(tab_id)

    def _adicionar_todas_ferramentas_da_aba_id(self, tab_id: str):
        adicionadas = 0
        for tool_id in self.ribbon.tool_ids_by_tab(tab_id):
            if tool_id not in self._ferramentas_usuario_ids and self.ribbon.tool_def(tool_id):
                self._ferramentas_usuario_ids.append(tool_id)
                adicionadas += 1
        self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(self._ferramentas_usuario_ids)
        self._sincronizar_perfil_usuario_atual()
        self._atualizar_linha_usuarios()
        self.lbl_status.setText(f"{adicionadas} ferramenta(s) adicionadas da aba '{tab_id}'.")

    def _limpar_ferramentas_usuario(self):
        self._ferramentas_usuario_ids.clear()
        self._garantir_ajuste_automatico_na_barra_usuario()
        self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(self._ferramentas_usuario_ids)
        self._sincronizar_perfil_usuario_atual()
        self._atualizar_linha_usuarios()
        self.lbl_status.setText("Linha Usuários limpa. Auto ajuste permanece fixo.")

    def _remover_ferramenta_usuario(self, tool_id: str):
        if tool_id == "ajuste_automatico":
            self.lbl_status.setText("Auto ajuste é fixo na barra Usuários.")
            return
        if tool_id in self._ferramentas_usuario_ids:
            self._ferramentas_usuario_ids.remove(tool_id)
            self._garantir_ajuste_automatico_na_barra_usuario()
            self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(self._ferramentas_usuario_ids)
            self._sincronizar_perfil_usuario_atual()
            self._atualizar_linha_usuarios()

    def _reordenar_ferramenta_usuario(self, tool_id: str, indice_destino: int):
        if tool_id not in self._ferramentas_usuario_ids:
            return
        indice_origem = self._ferramentas_usuario_ids.index(tool_id)
        indice_destino = max(0, min(int(indice_destino), len(self._ferramentas_usuario_ids)))
        if indice_destino > indice_origem:
            indice_destino -= 1
        if indice_destino == indice_origem:
            return
        self._ferramentas_usuario_ids.pop(indice_origem)
        self._ferramentas_usuario_ids.insert(indice_destino, tool_id)
        self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(self._ferramentas_usuario_ids)
        self._sincronizar_perfil_usuario_atual()
        self._atualizar_linha_usuarios()
        tool = self.ribbon.tool_def(tool_id) if hasattr(self, "ribbon") else None
        nome = tool.title if tool else tool_id
        self.lbl_status.setText(f"{nome} reposicionada na barra Usuários.")

    def _inicializar_perfis_usuarios(self):
        perfis = self.projeto_atual.preferencias_usuario.get("perfis_usuarios")
        if isinstance(perfis, dict) and perfis:
            self._perfis_usuarios = {
                str(nome): self._lista_usuario_com_ajuste(list(ids) if ids else list(self.FERRAMENTAS_USUARIO_PADRAO))
                for nome, ids in perfis.items()
            }
            if "Usuário 1" in self._perfis_usuarios and self.PERFIL_USUARIO_PADRAO not in self._perfis_usuarios:
                self._perfis_usuarios[self.PERFIL_USUARIO_PADRAO] = self._perfis_usuarios.pop("Usuário 1")
            self._perfis_usuarios[self.PERFIL_USUARIO_PADRAO] = self._lista_usuario_com_ajuste(
                list(self.FERRAMENTAS_USUARIO_PADRAO)
            )
        else:
            self._perfis_usuarios = {self.PERFIL_USUARIO_PADRAO: list(self._ferramentas_usuario_ids)}
        perfil_atual = self.projeto_atual.preferencias_usuario.get("perfil_usuario_atual")
        if perfil_atual == "Usuário 1":
            perfil_atual = self.PERFIL_USUARIO_PADRAO
        if isinstance(perfil_atual, str) and perfil_atual in self._perfis_usuarios:
            self._perfil_usuario_atual = perfil_atual
        else:
            self._perfil_usuario_atual = (
                self.PERFIL_USUARIO_PADRAO
                if self.PERFIL_USUARIO_PADRAO in self._perfis_usuarios
                else next(iter(self._perfis_usuarios.keys()))
            )
        self._ferramentas_usuario_ids = self._lista_usuario_com_ajuste(list(
            self._perfis_usuarios.get(self._perfil_usuario_atual, []) or self.FERRAMENTAS_USUARIO_PADRAO
        ))
        cfgs = self.projeto_atual.preferencias_usuario.get("perfis_usuarios_cfg")
        if isinstance(cfgs, dict):
            self._perfis_usuarios_cfg = {str(nome): dict(cfg or {}) for nome, cfg in cfgs.items()}
            if "Usuário 1" in self._perfis_usuarios_cfg and self.PERFIL_USUARIO_PADRAO not in self._perfis_usuarios_cfg:
                self._perfis_usuarios_cfg[self.PERFIL_USUARIO_PADRAO] = self._perfis_usuarios_cfg.pop("Usuário 1")
        else:
            self._perfis_usuarios_cfg = {}
        self._perfis_usuarios_cfg.setdefault(
            self.PERFIL_USUARIO_PADRAO,
            {"tema_interface": self.TEMA_INTERFACE_PADRAO},
        )
        self._aplicar_configuracoes_perfil(self._perfis_usuarios_cfg.get(self._perfil_usuario_atual, {}))

    def _persistir_perfis_usuarios(self):
        self.projeto_atual.preferencias_usuario["perfis_usuarios"] = {
            nome: list(ids) for nome, ids in self._perfis_usuarios.items()
        }
        self._perfis_usuarios_cfg[self._perfil_usuario_atual] = self._capturar_configuracoes_perfil()
        self.projeto_atual.preferencias_usuario["perfis_usuarios_cfg"] = {
            nome: dict(cfg) for nome, cfg in self._perfis_usuarios_cfg.items()
        }
        self.projeto_atual.preferencias_usuario["perfil_usuario_atual"] = self._perfil_usuario_atual
        self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(self._ferramentas_usuario_ids)
        self._salvar_preferencias_app()

    def _sincronizar_perfil_usuario_atual(self):
        self._garantir_ajuste_automatico_na_barra_usuario()
        self._perfis_usuarios[self._perfil_usuario_atual] = list(self._ferramentas_usuario_ids)
        self._persistir_perfis_usuarios()

    def _atualizar_combo_perfis_usuarios(self):
        if not hasattr(self, "combo_perfil_usuario"):
            return
        self.combo_perfil_usuario.blockSignals(True)
        self.combo_perfil_usuario.clear()
        self.combo_perfil_usuario.addItems(self._perfis_usuarios.keys())
        self.combo_perfil_usuario.setCurrentText(self._perfil_usuario_atual)
        self.combo_perfil_usuario.blockSignals(False)

    def _trocar_perfil_usuario(self, nome_perfil: str):
        if not nome_perfil or nome_perfil not in self._perfis_usuarios:
            return
        self._perfil_usuario_atual = nome_perfil
        self._ferramentas_usuario_ids = self._lista_usuario_com_ajuste(list(self._perfis_usuarios.get(nome_perfil, [])))
        self._aplicar_configuracoes_perfil(self._perfis_usuarios_cfg.get(nome_perfil, {}))
        self._persistir_perfis_usuarios()
        self._reposicionar_barra_usuarios()
        self._aplicar_config_unidade_global()
        self._atualizar_estilo_desenho({})
        self.ribbon.aplicar_estilo(self._estilo_desenho_atual)
        if hasattr(self, "action_barra_usuarios_habilitada"):
            self.action_barra_usuarios_habilitada.blockSignals(True)
            self.action_barra_usuarios_habilitada.setChecked(self._barra_usuarios_habilitada)
            self.action_barra_usuarios_habilitada.blockSignals(False)
        self._atualizar_linha_usuarios()
        self._sincronizar_menu_barra_usuarios()
        self.lbl_status.setText(f"Perfil '{nome_perfil}' carregado.")

    def _criar_novo_perfil_usuario(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Novo usuário")
        self._aplicar_estilo_claro_dialogo(dialog)
        lay = QVBoxLayout(dialog)
        lay.addWidget(QLabel("Nome do usuário/perfil:"))
        entrada = QLineEdit()
        lay.addWidget(entrada)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(botoes)
        botoes.accepted.connect(dialog.accept)
        botoes.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.Accepted:
            return
        nome = entrada.text().strip()
        if not nome:
            return
        if nome in self._perfis_usuarios:
            self.lbl_status.setText(f"O perfil '{nome}' já existe.")
            return
        self._perfis_usuarios[nome] = list(self._ferramentas_usuario_ids)
        self._perfis_usuarios_cfg[nome] = dict(self._capturar_configuracoes_perfil())
        self._perfil_usuario_atual = nome
        self._persistir_perfis_usuarios()
        self._atualizar_combo_perfis_usuarios()
        self._atualizar_linha_usuarios()
        self.lbl_status.setText(f"Perfil '{nome}' criado.")

    def _salvar_perfil_usuario_atual(self):
        self._sincronizar_perfil_usuario_atual()
        self.lbl_status.setText(f"Perfil '{self._perfil_usuario_atual}' salvo.")

    def _sincronizar_aba_usuario_ribbon(self):
        if not hasattr(self, "ribbon"):
            return
        self.ribbon.set_user_tools(list(self._ferramentas_usuario_ids), str(self._perfil_usuario_atual))
        self.ribbon.set_active_tool(getattr(self, "_ferramenta_ativa_id", "selecionar"))
        self.ribbon.aplicar_estilo(getattr(self, "_estilo_desenho_atual", {}))

    def _atualizar_linha_usuarios(self):
        self._garantir_ajuste_automatico_na_barra_usuario()
        self._sincronizar_aba_usuario_ribbon()
        if not hasattr(self, "layout_linha_usuario"):
            return
        while self.layout_linha_usuario.count():
            item = self.layout_linha_usuario.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not self._ferramentas_usuario_ids:
            vazio = QLabel("Sem ferramentas ainda. Clique com o botão direito em qualquer ferramenta e selecione 'Adicionar à linha Usuários'.")
            tema = self._tema_interface()
            vazio.setStyleSheet(f"color:{tema['texto_suave']}; font-size:11px; font-weight:400;")
            self.layout_linha_usuario.addWidget(vazio)
            self.layout_linha_usuario.addStretch(1)
            return
        for tool_id in self._ferramentas_usuario_ids:
            tool = self.ribbon.tool_def(tool_id)
            if not tool:
                continue
            btn = _BotaoFerramentaUsuario(tool_id)
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setIcon(carregar_icone(tool.icon))
            btn.setIconSize(QSize(28, 28))
            btn.setFixedSize(30, 30)
            btn.setToolTip(tool.title)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._estilo_botao_linha_usuario())
            btn.clicked.connect(lambda _=False, tid=tool_id: self._abrir_pagina_ferramenta(tid))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, tid=tool_id: self._remover_ferramenta_usuario(tid)
            )
            self.layout_linha_usuario.addWidget(btn)
        self.layout_linha_usuario.addStretch(1)
        self._atualizar_barra_lateral_ferramentas()


    def _conectar_sinal_elementos_canvas(self, canvas) -> None:
        """Conecta o sinal de alteração do canvas sem quebrar se o canvas antigo não tiver esse sinal."""
        sinal = getattr(canvas, "elementos_alterados", None)
        if sinal is None or not hasattr(sinal, "connect"):
            try:
                self._log_debug_propriedades("Canvas sem sinal elementos_alterados; menu de moldes será atualizado manualmente.")
            except Exception:
                pass
            return
        try:
            sinal.connect(self._atualizar_menu_moldes)
        except Exception as exc:
            try:
                self._log_debug_propriedades(f"Falha ao conectar elementos_alterados: {type(exc).__name__}: {exc}")
            except Exception:
                pass

    def _emitir_elementos_canvas_alterados(self, canvas) -> None:
        """Emite a alteração do canvas ou atualiza o menu diretamente como fallback."""
        sinal = getattr(canvas, "elementos_alterados", None)
        if sinal is not None and hasattr(sinal, "emit"):
            try:
                sinal.emit()
                return
            except Exception:
                pass
        try:
            self._atualizar_menu_moldes()
        except Exception:
            pass

    def _adicionar_aba_documento(self, nome: str | None = None, caminho_origem: str | None = None):
        if nome is None:
            nome = self._proximo_nome_aba_sem_nome()
        else:
            nome = str(nome or "").strip()
            if self._indice_nome_aba_sem_nome(nome) is not None:
                nome = self._proximo_nome_aba_sem_nome()
            elif not nome:
                nome = self._proximo_nome_aba_sem_nome()
        area_doc = AreaDocumentoWidget(CenaDocumento())
        area_doc.setMinimumSize(0, 0)
        area_doc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        area_doc.zoom_changed.connect(self._on_zoom_canvas_alterado)
        area_doc.canvas.ferramenta_padrao_solicitada.connect(self._ativar_ferramenta_global)
        area_doc.canvas.snap_changed.connect(self._on_snap_changed)
        self._conectar_sinal_elementos_canvas(area_doc.canvas)
        area_doc.canvas.painel_coordenadas_changed.connect(self._on_painel_coordenadas_changed)
        area_doc.canvas.painel_posicao_changed.connect(self._on_painel_posicao_canvas)
        area_doc.canvas.set_ferramenta_ativa(self._ferramenta_ativa_id)
        area_doc.canvas.set_snap_ativo(self.btn_snap.isChecked())
        area_doc.canvas.set_estilo_linha(**self._estilo_desenho_atual)
        area_doc.canvas.set_config_cores_canvas(self._cores_canvas_global)
        area_doc.canvas.set_config_cores_moldes(
            self._cores_moldes_global,
            self._estilo_linha_costura_global,
            usar_cores_ferramentas=self._usar_cores_ferramentas_global,
        )
        area_doc.canvas.set_snap_cores_automaticas(self._snap_cores_automaticas_global)
        area_doc.canvas.set_opacidade_imagens(self._opacidade_imagens_global)
        area_doc.canvas.set_grid_visivel(bool(getattr(self, "btn_grid", None) and self.btn_grid.isChecked()))
        area_doc.canvas.set_passo_snap_angular(self._passo_snap_angular_atual)
        area_doc.canvas.set_snap_contextual_ativo(self._snap_contextual_ativo)
        area_doc.canvas._cores_tecidos = dict(self._cores_tecidos_global)
        area_doc.canvas._mostrar_cor_tecidos = bool(self._mostrar_cor_tecidos_global)
        area_doc.canvas.set_painel_auxiliar_posicao(self._painel_coordenadas_pos_global)
        area_doc.aplicar_config_unidade(self._unidade_medida, self._passo_unidade_medida)
        area_doc.canvas.set_unidade_quadrado(self._unidade_area, self._fator_unidade_sigla(self._unidade_area))
        area_doc.canvas.set_precisao_medida(self._precisao_medida)
        area_doc.aplicar_tema(self._tema_interface())
        area_doc.canvas.installEventFilter(self)
        area_doc.unidade_menu_solicitado.connect(self._abrir_menu_unidade_medida_em)
        self._garantir_coordenadas_abertas(area_doc)
        self._marcar_area_como_salva(area_doc)
        area_doc.setProperty("arquivo_origem", caminho_origem)
        index = self.abas_documentos.addTab(area_doc, nome)
        self._configurar_botao_fechar_aba(index)
        self.abas_documentos.setCurrentIndex(index)
        QTimer.singleShot(0, lambda a=area_doc: self._aplicar_viewport_inicial(a))
        self._agendar_reencaixe_janela_canvas()
        self._atualizar_menu_moldes()

    def _limpar_abas_documentos(self):
        self._soltar_ferramentas_canvas_para_selecionar()
        while self.abas_documentos.count():
            widget = self.abas_documentos.widget(0)
            self.abas_documentos.removeTab(0)
            if widget:
                widget.deleteLater()
        self._contador_sem_nome = 0

    def _fechar_aba_documento(self, index: int):
        if index < 0 or index >= self.abas_documentos.count():
            return
        nome_aba = self.abas_documentos.tabText(index)
        if not self._confirmar_fechamento_aba(index, nome_aba):
            return
        self._soltar_ferramentas_canvas_para_selecionar()
        widget = self.abas_documentos.widget(index)
        self.abas_documentos.removeTab(index)
        if widget:
            widget.deleteLater()
        self._renumerar_abas_sem_nome()
        self._reconfigurar_botoes_fechar_abas()
        self._on_aba_documento_alterada(self.abas_documentos.currentIndex())

    def _soltar_ferramentas_canvas_para_selecionar(self):
        if getattr(self, "_ferramenta_ativa_id", "selecionar") != "selecionar":
            self._ativar_ferramenta_global("selecionar")
        elif hasattr(self, "_ocultar_janelas_auxiliares"):
            self._ocultar_janelas_auxiliares(exceto="selecionar")
        if not hasattr(self, "abas_documentos"):
            return
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            canvas = getattr(area, "canvas", None)
            if canvas is not None and hasattr(canvas, "set_ferramenta_ativa"):
                canvas.set_ferramenta_ativa("selecionar")

    def _on_zoom_canvas_alterado(self, zoom: float):
        area_atual = self._area_documento_atual()
        if area_atual and self.sender() is area_atual:
            self._atualizar_label_escala(zoom)
            self._agendar_salvar_estado_silencioso()

    def _on_aba_documento_alterada(self, index: int):
        area = self.abas_documentos.widget(index) if index >= 0 else None
        if isinstance(area, AreaDocumentoWidget):
            self._atualizar_label_escala(area.canvas.zoom)
            self.btn_snap.blockSignals(True)
            self.btn_snap.setChecked(area.canvas.snap_ativo())
            self.btn_snap.blockSignals(False)
            self._atualizar_botao_snap_visual(area.canvas.snap_ativo())
            self.action_coordenadas.blockSignals(True)
            self.action_coordenadas.setChecked(area.canvas.painel_coordenadas_visivel())
            self.action_coordenadas.blockSignals(False)
            QTimer.singleShot(0, area.canvas.sincronizar_paineis_auxiliares)
            self._atualizar_menu_moldes()
        else:
            self._atualizar_label_escala(None)
            self._atualizar_menu_moldes()

    def _area_documento_atual(self) -> AreaDocumentoWidget | None:
        area = self.abas_documentos.currentWidget()
        if isinstance(area, AreaDocumentoWidget):
            return area
        try:
            self._log_debug_propriedades(f"_area_documento_atual retornou None. currentWidget={type(area).__name__ if area is not None else None}")
        except Exception:
            pass
        return None

    def _configurar_botao_fechar_aba(self, index: int):
        barra = self.abas_documentos.tabBar()
        botao = QPushButton("×")
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFlat(True)
        botao.setFixedSize(14, 14)
        botao.setToolTip("Fechar aba")
        botao.setStyleSheet(
            "QPushButton { border:none; padding:0; font-size:12px; color:#c62828; font-weight:700; }"
            "QPushButton:hover { background:#ffe9e9; border-radius:7px; color:#9a0000; }"
        )
        botao.clicked.connect(lambda _=False, i=index: self._fechar_aba_documento(i))
        barra.setTabButton(index, QTabBar.RightSide, botao)

    def _reconfigurar_botoes_fechar_abas(self):
        for i in range(self.abas_documentos.count()):
            self._configurar_botao_fechar_aba(i)

    def _configurar_atalhos(self):
        QShortcut(QKeySequence.Undo, self, activated=self._desfazer_canvas_atual)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._refazer_canvas_atual)
        QShortcut(QKeySequence.Copy, self, activated=self._copiar_canvas_atual)
        QShortcut(QKeySequence.Paste, self, activated=self._colar_canvas_atual)
        QShortcut(QKeySequence(Qt.Key_Delete), self, activated=self._apagar_canvas_atual)
        QShortcut(QKeySequence("Ctrl+U"), self, activated=self._abrir_dialogo_unidade_medida)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._abrir_propriedades_diretamente)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._abrir_propriedades_diretamente)
        QShortcut(QKeySequence.Print, self, activated=self._abrir_dialogo_impressao)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, activated=self._abrir_dialogo_plotagem)

    def _desfazer_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
            area.canvas.desfazer_acao()

    def _copiar_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
            area.canvas.copiar()
            if hasattr(area.canvas, "obter_buffer_copia"):
                self._clipboard_elementos_global = area.canvas.obter_buffer_copia()

    def _refazer_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
            area.canvas.refazer_acao()

    def _colar_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
            buffer_canvas = area.canvas.obter_buffer_copia() if hasattr(area.canvas, "obter_buffer_copia") else None
            if buffer_canvas:
                self._clipboard_elementos_global = buffer_canvas
            elif self._clipboard_elementos_global and hasattr(area.canvas, "definir_buffer_copia"):
                area.canvas.definir_buffer_copia(self._clipboard_elementos_global)
            area.canvas.colar()

    def _apagar_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
            area.canvas.apagar_selecionados()

    def _confirmar_fechamento_aba(self, index: int, nome_aba: str) -> bool:
        area = self.abas_documentos.widget(index) if index >= 0 else None
        if isinstance(area, AreaDocumentoWidget) and not self._tem_alteracoes_area(area):
            self._salvar_estado_projeto_silenciosamente()
            return True
        caixa = QMessageBox(self)
        self._estilizar_message_box(caixa)
        caixa.setWindowTitle("Fechando arquivo")
        caixa.setIcon(QMessageBox.Question)
        caixa.setText(f"O arquivo\n{nome_aba}\nfoi alterado. Deseja salvar as alterações?")
        caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        caixa.setDefaultButton(QMessageBox.Yes)
        self._traduzir_botoes_padrao_message_box(caixa)
        resposta = caixa.exec()
        if resposta == QMessageBox.Cancel:
            return False
        if resposta == QMessageBox.Yes:
            return self._salvar_projeto()
        return True

    def _estilizar_message_box(self, caixa: QMessageBox):
        caixa.setStyleSheet(
            """
            QMessageBox {
                background: #f2f5f8;
                color: #1f2d3a;
            }
            QMessageBox QLabel {
                color: #1f2d3a;
                font-size: 12px;
            }
            QMessageBox QPushButton {
                min-width: 84px;
                min-height: 28px;
                background: #ffffff;
                border: 1px solid #bcc9d6;
                border-radius: 6px;
                color: #1f2d3a;
                padding: 3px 10px;
                font-weight: 600;
            }
            QMessageBox QPushButton:hover {
                background: #ebf4fc;
                border-color: #86b3da;
            }
            """
        )

    def _traduzir_botoes_padrao_message_box(self, caixa: QMessageBox):
        mapa = {
            QMessageBox.Yes: "Sim",
            QMessageBox.No: "Não",
            QMessageBox.Cancel: "Cancelar",
            QMessageBox.Ok: "OK",
        }
        for botao_padrao, texto in mapa.items():
            botao = caixa.button(botao_padrao)
            if botao:
                botao.setText(texto)

    def _ordenar_botoes_sim_na_direita(self, caixa: QMessageBox):
        grupo_botoes = caixa.findChild(QDialogButtonBox)
        if grupo_botoes is None:
            return
        grupo_botoes.setLayoutDirection(Qt.RightToLeft)

    def _sincronizar_documentos_canvas_no_projeto(self):
        documentos_canvas: list[dict] = []
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if not isinstance(area, AreaDocumentoWidget):
                continue
            doc_payload = self._capturar_estado_documento_canvas(area)
            doc_payload["nome"] = self.abas_documentos.tabText(i)
            documentos_canvas.append(doc_payload)
        self.projeto_atual.preferencias_usuario["documentos_canvas"] = documentos_canvas

    def _carregar_documentos_canvas(self):
        docs = self.projeto_atual.preferencias_usuario.get("documentos_canvas", [])
        if not docs:
            return

        base_nome_arquivo = self._arquivo_atual.stem if self._arquivo_atual else "(Sem nome)"
        for doc in docs:
            area_doc = AreaDocumentoWidget(CenaDocumento(elementos=doc.get("elementos", [])))
            area_doc.setMinimumSize(0, 0)
            area_doc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            area_doc.zoom_changed.connect(self._on_zoom_canvas_alterado)
            area_doc.canvas.ferramenta_padrao_solicitada.connect(self._ativar_ferramenta_global)
            area_doc.canvas.snap_changed.connect(self._on_snap_changed)
            self._conectar_sinal_elementos_canvas(area_doc.canvas)
            area_doc.canvas.painel_coordenadas_changed.connect(self._on_painel_coordenadas_changed)
            area_doc.canvas.painel_posicao_changed.connect(self._on_painel_posicao_canvas)
            area_doc.canvas.set_ferramenta_ativa(self._ferramenta_ativa_id)
            area_doc.canvas.set_snap_ativo(self.btn_snap.isChecked())
            area_doc.canvas.set_estilo_linha(**self._estilo_desenho_atual)
            area_doc.canvas.set_passo_snap_angular(self._passo_snap_angular_atual)
            area_doc.canvas.set_snap_contextual_ativo(self._snap_contextual_ativo)
            area_doc.canvas._cores_tecidos = dict(self._cores_tecidos_global)
            area_doc.canvas._mostrar_cor_tecidos = bool(self._mostrar_cor_tecidos_global)
            area_doc.canvas.set_config_cores_canvas(self._cores_canvas_global)
            area_doc.canvas.set_config_cores_moldes(
                self._cores_moldes_global,
                self._estilo_linha_costura_global,
                usar_cores_ferramentas=self._usar_cores_ferramentas_global,
            )
            area_doc.canvas.set_snap_cores_automaticas(self._snap_cores_automaticas_global)
            area_doc.canvas.set_opacidade_imagens(self._opacidade_imagens_global)
            area_doc.canvas.set_grid_visivel(bool(getattr(self, "btn_grid", None) and self.btn_grid.isChecked()))
            area_doc.canvas.set_painel_auxiliar_posicao(self._painel_coordenadas_pos_global)
            area_doc.aplicar_config_unidade(self._unidade_medida, self._passo_unidade_medida)
            area_doc.canvas.set_unidade_quadrado(self._unidade_area, self._fator_unidade_sigla(self._unidade_area))
            area_doc.canvas.set_precisao_medida(self._precisao_medida)
            area_doc.aplicar_tema(self._tema_interface())
            area_doc.unidade_menu_solicitado.connect(self._abrir_menu_unidade_medida_em)
            self._garantir_coordenadas_abertas(area_doc)
            self._marcar_area_como_salva(area_doc)
            nome = doc.get("nome") or "(Sem nome)"
            if str(nome).strip().startswith("(Sem nome)"):
                idx_nome = self.abas_documentos.count() + 1
                nome = base_nome_arquivo if idx_nome == 1 else f"{base_nome_arquivo} -{idx_nome}"
            idx = self.abas_documentos.addTab(area_doc, nome)
            self._configurar_botao_fechar_aba(idx)
            if self._restaurar_viewport_documento_canvas(area_doc, doc):
                continue
            if doc.get("elementos"):
                QTimer.singleShot(0, lambda a=area_doc: self._centralizar_area_documento(a))
            else:
                QTimer.singleShot(0, lambda a=area_doc: self._aplicar_viewport_inicial(a))
        self.abas_documentos.setCurrentIndex(self.abas_documentos.count() - 1)
        self._atualizar_menu_moldes()

    def _capturar_estado_documento_canvas(self, area: AreaDocumentoWidget) -> dict:
        return {
            "elementos": area.canvas.elementos_para_salvar(),
            "painel_coordenadas_visivel": area.canvas.painel_coordenadas_visivel(),
            "zoom": float(area.canvas.zoom),
            "origem_cena": {
                "x": float(area.canvas.origem_cena.x()),
                "y": float(area.canvas.origem_cena.y()),
            },
            "snap_ativo": bool(area.canvas._snap_ativo),
        }

    def aplicar_config_cores_tecidos_global(self, mostrar: bool | None = None, mapa_cores: dict[str, str] | None = None):
        if mostrar is not None:
            self._mostrar_cor_tecidos_global = bool(mostrar)
            self.projeto_atual.preferencias_usuario["mostrar_cor_tecidos_global"] = self._mostrar_cor_tecidos_global
        if mapa_cores is not None:
            self._cores_tecidos_global = self._normalizar_cores_tecidos(mapa_cores)
            self.projeto_atual.preferencias_usuario["cores_tecidos_global"] = dict(self._cores_tecidos_global)
        self._aplicar_config_visualizacao_nos_canvas()
        self._sincronizar_perfil_usuario_atual()
        self._salvar_preferencias_app()
        self._atualizar_menu_moldes()

    def _restaurar_viewport_documento_canvas(self, area: AreaDocumentoWidget, doc: dict) -> bool:
        zoom = doc.get("zoom")
        origem = doc.get("origem_cena")
        if not isinstance(zoom, (int, float)) or not isinstance(origem, dict):
            return False
        ox = origem.get("x")
        oy = origem.get("y")
        if not isinstance(ox, (int, float)) or not isinstance(oy, (int, float)):
            return False

        snap_ativo = doc.get("snap_ativo")
        if isinstance(snap_ativo, bool):
            area.canvas.set_snap_ativo(snap_ativo)

        def _aplicar():
            area.canvas.set_zoom(float(zoom))
            area.canvas.origem_cena.setX(float(ox))
            area.canvas.origem_cena.setY(float(oy))
            area._on_zoom_changed(area.canvas.zoom)
            area.canvas.update()

        QTimer.singleShot(0, _aplicar)
        return True

    def _ativar_ferramenta_global(self, tool_id: str):
        preferencia_anterior = self.projeto_atual.preferencias_usuario.get("ferramenta_ativa_id")
        self._ferramenta_ativa_id = tool_id
        if preferencia_anterior != tool_id:
            self.projeto_atual.preferencias_usuario["ferramenta_ativa_id"] = tool_id
            self._agendar_salvar_preferencias_app()
        self.ribbon.set_active_tool(tool_id)
        self._atualizar_barra_lateral_ferramentas()
        self._ocultar_janelas_auxiliares(exceto=tool_id)
        area_atual = self._area_documento_atual()
        if area_atual:
            area_atual.canvas.set_ferramenta_ativa(tool_id)
            area_atual.canvas.definir_config_retangulo(self._retangulo_criar_molde)
        if tool_id == "selecionar":
            self.lbl_status.setText("Selecionar ativada")

    def _ocultar_janelas_auxiliares(self, exceto: str | None = None):
        if exceto != "curva" and self._janela_aux_curva and self._janela_aux_curva.isVisible():
            self._memorizar_posicao_caixa_aux(self._janela_aux_curva, "curva")
            self._janela_aux_curva.hide()
        if exceto != "retangulo" and self._janela_aux_retangulo and self._janela_aux_retangulo.isVisible():
            self._memorizar_posicao_caixa_aux(self._janela_aux_retangulo, "retangulo")
            self._janela_aux_retangulo.hide()
        for chave, janela in self._janelas_aux_instrucao.items():
            if chave == exceto:
                continue
            if janela.isVisible():
                self._memorizar_posicao_caixa_aux(janela, chave)
                janela.hide()

    def _atualizar_estilo_desenho(self, estilo: dict):
        self._estilo_desenho_atual.update(estilo)
        estilo_para_selecionados = {
            chave: self._estilo_desenho_atual[chave]
            for chave in ("cor", "estilo", "espessura", "amplitude")
            if chave in estilo
        }
        self.projeto_atual.preferencias_usuario["estilo_desenho"] = dict(self._estilo_desenho_atual)
        self._sincronizar_perfil_usuario_atual()
        area_atual = self._area_documento_atual()
        if area_atual:
            area_atual.canvas.set_estilo_linha(**self._estilo_desenho_atual)
            if estilo_para_selecionados and hasattr(area_atual.canvas, "aplicar_estilo_linha_selecionados"):
                area_atual.canvas.aplicar_estilo_linha_selecionados(estilo_para_selecionados)
        self.lbl_status.setText(
            f"Cor {self._estilo_desenho_atual['cor']} | Estilo {self._estilo_desenho_atual['estilo']} | "
            f"Espessura {self._estilo_desenho_atual['espessura']:.0f} | Altura {self._estilo_desenho_atual['amplitude']:.1f}"
        )
        self._salvar_preferencias_app()

    def _restaurar_estilo_desenho_memorizado(self):
        estilo_mem = self.projeto_atual.preferencias_usuario.get("estilo_desenho", {})
        if not isinstance(estilo_mem, dict):
            return
        self._estilo_desenho_atual.update(
            {
                "cor": str(estilo_mem.get("cor", self._estilo_desenho_atual["cor"])),
                "estilo": str(estilo_mem.get("estilo", self._estilo_desenho_atual["estilo"])),
                "espessura": float(estilo_mem.get("espessura", self._estilo_desenho_atual["espessura"])),
                "amplitude": float(estilo_mem.get("amplitude", self._estilo_desenho_atual["amplitude"])),
            }
        )

    def _alternar_reguas(self, ativo: bool):
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.set_reguas_visiveis(ativo)
        self.lbl_status.setText("Réguas ativas" if ativo else "Réguas ocultas")

    def _aplicar_config_unidade_global(self):
        self.projeto_atual.preferencias_usuario["unidade_medida"] = self._unidade_medida
        self.projeto_atual.preferencias_usuario["passo_unidade_medida"] = self._passo_unidade_medida
        self.projeto_atual.preferencias_usuario["unidade_area"] = self._unidade_area
        self.projeto_atual.preferencias_usuario["precisao_medida"] = self._precisao_medida
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.aplicar_config_unidade(self._unidade_medida, self._passo_unidade_medida)
                area.canvas.set_unidade_quadrado(self._unidade_area, self._fator_unidade_sigla(self._unidade_area))
                area.canvas.set_precisao_medida(self._precisao_medida)
        self._salvar_preferencias_app()

    def _fator_unidade_sigla(self, sigla: str) -> float:
        mapa_fator = {
            "mm": 0.1,
            "cm": 1.0,
            "m": 100.0,
            "pol": 2.54,
            "ft": 30.48,
            "yd": 91.44,
        }
        return float(mapa_fator.get(str(sigla or "cm"), 1.0))

    def _abrir_menu_unidade_medida_em(self, gx: int, gy: int):
        menu = QMenu(self)
        menu.setStyleSheet(
            folha_estilo_hover_global()
            +
            "QMenu { background:#ffffff; color:#111111; border:1px solid #cfd6de; }"
            "QMenu::item { color:#111111; padding:6px 16px; }"
            "QMenu::item:selected { background:#e9f3ff; color:#0b4f82; }"
        )
        opcoes = [
            ("Milímetros", "mm", 5.0),
            ("Centímetros", "cm", 0.5),
            ("Metros", "m", 0.01),
            ("Polegadas", "pol", 0.25),
            ("Pés", "ft", 0.25),
            ("Jardas", "yd", 0.25),
        ]
        for rotulo, sigla, passo in opcoes:
            acao = menu.addAction(rotulo)
            acao.setCheckable(True)
            acao.setChecked(self._unidade_medida == sigla)
            acao.triggered.connect(lambda _=False, s=sigla, p=passo: self._definir_unidade_medida(s, p))
        menu.addSeparator()
        menu.addAction("Esconder régua", lambda: self.action_regras.setChecked(False))
        menu.exec(QPoint(gx, gy))

    def _definir_unidade_medida(self, sigla: str, passo: float):
        self._unidade_medida = sigla
        self._passo_unidade_medida = float(passo)
        self._aplicar_config_unidade_global()
        self.lbl_status.setText(f"Unidade ativa: {sigla} | passo {passo:g}")

    def _abrir_dialogo_unidade_medida(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Unidades de medida")
        dialog.setModal(True)
        dialog.resize(420, 500)
        self._aplicar_estilo_claro_dialogo(dialog)
        lay = QVBoxLayout(dialog)
        escolhas_linear = [
            ("Milímetros", "mm", 5.0),
            ("Centímetros", "cm", 0.5),
            ("Metros", "m", 0.01),
            ("Polegadas", "pol", 0.25),
            ("Pés", "ft", 0.25),
            ("Jardas", "yd", 0.25),
        ]

        topo = QHBoxLayout()
        grupo_linear = QGroupBox("Linear")
        glay_linear = QVBoxLayout(grupo_linear)
        botoes_linear: list[QRadioButton] = []
        for rotulo, sigla, _passo in escolhas_linear:
            rb = QRadioButton(rotulo)
            rb.setProperty("sigla", sigla)
            rb.setChecked(sigla == self._unidade_medida)
            glay_linear.addWidget(rb)
            botoes_linear.append(rb)
        topo.addWidget(grupo_linear, 1)

        grupo_area = QGroupBox("Quadrado")
        glay_area = QVBoxLayout(grupo_area)
        botoes_area: list[QRadioButton] = []
        for rotulo, sigla, _passo in escolhas_linear:
            rb = QRadioButton(rotulo)
            rb.setProperty("sigla", sigla)
            rb.setChecked(sigla == self._unidade_area)
            glay_area.addWidget(rb)
            botoes_area.append(rb)
        topo.addWidget(grupo_area, 1)
        lay.addLayout(topo)

        grupo_prec = QGroupBox("Precisão")
        grid_prec = QGridLayout(grupo_prec)
        opcoes_prec = [("0.1", "0.1"), ("1/8", "1/8"), ("0.01", "0.01"), ("1/16", "1/16"), ("0.001", "0.001"), ("1/32", "1/32"), ("0.0001", "0.0001"), ("1/64", "1/64")]
        botoes_prec: list[QRadioButton] = []
        for i, (rotulo, valor) in enumerate(opcoes_prec):
            rb = QRadioButton(rotulo)
            rb.setProperty("valor", valor)
            rb.setChecked(valor == self._precisao_medida)
            grid_prec.addWidget(rb, i // 2, i % 2)
            botoes_prec.append(rb)
        lay.addWidget(grupo_prec)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        btn_ok = QPushButton("✓ OK")
        btn_cancelar = QPushButton("✕ Cancelar")
        btn_ok.clicked.connect(dialog.accept)
        btn_cancelar.clicked.connect(dialog.reject)
        rodape.addWidget(btn_ok)
        rodape.addWidget(btn_cancelar)
        lay.addLayout(rodape)

        if dialog.exec() != QDialog.Accepted:
            return
        for rb in botoes_linear:
            if rb.isChecked():
                sigla = str(rb.property("sigla"))
                passo_padrao = next((p for _, s, p in escolhas_linear if s == sigla), 0.5)
                self._definir_unidade_medida(sigla, passo_padrao)
                break
        for rb in botoes_area:
            if rb.isChecked():
                self._unidade_area = str(rb.property("sigla"))
                self.projeto_atual.preferencias_usuario["unidade_area"] = self._unidade_area
                break
        for rb in botoes_prec:
            if rb.isChecked():
                self._precisao_medida = str(rb.property("valor"))
                self.projeto_atual.preferencias_usuario["precisao_medida"] = self._precisao_medida
                break
        self._aplicar_config_unidade_global()
        self._salvar_preferencias_app()

    def _carregar_posicoes_caixas_aux(self) -> dict[str, tuple[int, int]]:
        bruto = self.projeto_atual.preferencias_usuario.get("posicoes_caixas_aux", {})
        if not isinstance(bruto, dict):
            return {}
        resultado: dict[str, tuple[int, int]] = {}
        for chave, valor in bruto.items():
            if isinstance(valor, (list, tuple)) and len(valor) == 2:
                resultado[str(chave)] = (int(valor[0]), int(valor[1]))
        return resultado

    def _definir_passo_snap_angular(self, passo: float):
        self._passo_snap_angular_atual = float(passo)
        self.projeto_atual.preferencias_usuario["passo_snap_angular"] = self._passo_snap_angular_atual
        self._salvar_preferencias_app()
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.canvas.set_passo_snap_angular(self._passo_snap_angular_atual)
        self.lbl_status.setText(f"Snap angular: {self._passo_snap_angular_atual:.0f}° (W = trava principais)")

    def _alternar_snap_contextual(self, ativo: bool):
        self._snap_contextual_ativo = bool(ativo)
        self.projeto_atual.preferencias_usuario["snap_contextual_ativo"] = self._snap_contextual_ativo
        self._salvar_preferencias_app()
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.canvas.set_snap_contextual_ativo(self._snap_contextual_ativo)
        self.lbl_status.setText("Snap contextual ativo" if self._snap_contextual_ativo else "Snap contextual desativado")

    def _alternar_barra_mensagem(self, ativo: bool):
        if hasattr(self, "barra_mensagem"):
            self.barra_mensagem.setVisible(bool(ativo))
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText("Barra de mensagem ativa" if ativo else "Barra de mensagem oculta")

    def _alternar_snap_canvas_atual(self, ativo: bool):
        self._snap_ativo_global = bool(ativo)
        self.projeto_atual.preferencias_usuario["snap_ativo"] = self._snap_ativo_global
        self._salvar_preferencias_app()
        self._atualizar_botao_snap_visual(ativo)
        area = self._area_documento_atual()
        if not area:
            self.lbl_status.setText("Snap ativo" if ativo else "Snap desativado")
            return
        area.canvas.set_snap_ativo(ativo)

    def _alternar_grid_canvas(self, ativo: bool):
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.canvas.set_grid_visivel(bool(ativo))
        self.lbl_status.setText("Grid ativado" if ativo else "Grid desativado")

    def _alternar_graduacao_canvas(self, ativo: bool):
        area = self._area_documento_atual()
        if not isinstance(area, AreaDocumentoWidget):
            self.lbl_status.setText("Graduação visível" if ativo else "Graduação oculta")
            return
        canvas = area.canvas
        elementos = getattr(canvas.cena, "elementos", []) or []
        moldes_selecionados = [
            int(idx)
            for idx in getattr(canvas, "_selecionados", set()) or set()
            if 0 <= int(idx) < len(elementos)
            and isinstance(elementos[int(idx)], dict)
            and elementos[int(idx)].get("molde")
        ]
        apenas_selecionados = bool(moldes_selecionados)
        canvas.set_graduacao_visivel(bool(ativo), apenas_selecionados=apenas_selecionados)
        if apenas_selecionados:
            total = len(moldes_selecionados)
            alvo = "molde selecionado" if total == 1 else f"{total} moldes selecionados"
            estado = "visível" if ativo else "oculta"
            self.lbl_status.setText(f"Graduação {estado} no {alvo}")
        else:
            self.lbl_status.setText("Graduação visível em todos os moldes" if ativo else "Graduação oculta em todos os moldes")

    def _alternar_costura_canvas(self, ativo: bool):
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.canvas.set_costura_visivel(bool(ativo))
        self.lbl_status.setText("Costura visível" if ativo else "Costura oculta")

    def _on_snap_changed(self, ativo: bool):
        self._snap_ativo_global = bool(ativo)
        self.projeto_atual.preferencias_usuario["snap_ativo"] = self._snap_ativo_global
        self._salvar_preferencias_app()
        self._atualizar_botao_snap_visual(ativo)
        self.lbl_status.setText("Snap ativo" if ativo else "Snap desativado")

    def _atualizar_botao_snap_visual(self, ativo: bool) -> None:
        btn = getattr(self, "btn_snap", None)
        if btn is None:
            return
        icone_snap = ICONS_DIR / "snap.svg"
        if icone_snap.exists():
            btn.setIcon(self._icone_snap_estado(bool(ativo)))
            btn.setText("")
        else:
            btn.setText("S" if ativo else "X")
        btn.setToolTip("Snap ativo" if ativo else "Snap desativado")

    def _icone_snap_estado(self, ativo: bool) -> QIcon:
        tamanho = QSize(22, 22)
        icone_snap = ICONS_DIR / "snap.svg"
        if icone_snap.exists():
            pix = carregar_icone("snap.svg").pixmap(tamanho)
        else:
            pix = QPixmap(tamanho)
            pix.fill(Qt.transparent)
        if pix.isNull():
            pix = QPixmap(tamanho)
            pix.fill(Qt.transparent)
        if not icone_snap.exists():
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor("#2f5f7d"), 2.2))
            painter.drawArc(5, 4, 12, 14, 35 * 16, 290 * 16)
            painter.drawLine(5, 11, 5, 16)
            painter.drawLine(17, 11, 17, 16)
            painter.end()
        if not ativo:
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor("#e02020"), 2.8)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(5, 5, 17, 17)
            painter.drawLine(17, 5, 5, 17)
            painter.end()
        return QIcon(pix)

    def _garantir_coordenadas_abertas(self, area: AreaDocumentoWidget | None = None):
        area = area or self._area_documento_atual()
        if not area:
            return
        area.canvas.definir_painel_coordenadas_visivel(True)
        if hasattr(self, "action_coordenadas"):
            self.action_coordenadas.blockSignals(True)
            self.action_coordenadas.setChecked(True)
            self.action_coordenadas.blockSignals(False)

    def _alternar_coordenadas_canvas_atual(self, visivel: bool):
        area = self._area_documento_atual()
        if not area:
            return
        area.canvas.definir_painel_coordenadas_visivel(visivel)
        self.lbl_status.setText("Coordenadas visíveis" if visivel else "Coordenadas ocultas")

    def _on_painel_coordenadas_changed(self, visivel: bool):
        area_atual = self._area_documento_atual()
        if not area_atual or self.sender() is not area_atual.canvas:
            return
        self.action_coordenadas.blockSignals(True)
        self.action_coordenadas.setChecked(visivel)
        self.action_coordenadas.blockSignals(False)

    def _on_painel_posicao_canvas(self, x: int, y: int):
        # Painel de coordenadas fixo no lado direito de cada canvas.
        self._painel_coordenadas_pos_global = None

    def _assinatura_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = {
            "elementos": area.canvas.elementos_para_salvar(),
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = {
            "painel_coordenadas_visivel": area.canvas.painel_coordenadas_visivel(),
            "zoom": float(area.canvas.zoom),
            "origem_cena": {
                "x": float(area.canvas.origem_cena.x()),
                "y": float(area.canvas.origem_cena.y()),
            },
            "snap_ativo": bool(area.canvas._snap_ativo),
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)


    def _tem_alteracoes_area(self, area: AreaDocumentoWidget) -> bool:
        assinatura_salva = area.property("assinatura_salva_conteudo")
        return self._assinatura_canvas(area) != assinatura_salva

    def _tem_alteracoes_estado_area(self, area: AreaDocumentoWidget) -> bool:
        assinatura_estado_salva = area.property("assinatura_salva_estado")
        return self._assinatura_estado_canvas(area) != assinatura_estado_salva

    def _marcar_area_como_salva(self, area: AreaDocumentoWidget):
        area.setProperty("assinatura_salva_conteudo", self._assinatura_canvas(area))
        area.setProperty("assinatura_salva_estado", self._assinatura_estado_canvas(area))

    def _marcar_estado_area_como_salvo(self, area: AreaDocumentoWidget):
        area.setProperty("assinatura_salva_estado", self._assinatura_estado_canvas(area))

    def _marcar_documentos_como_salvos(self):
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                self._marcar_area_como_salva(area)

    def _salvar_estado_projeto_silenciosamente(self):
        if self._arquivo_atual is None:
            return
        if self._ha_alteracoes_nao_salvas():
            return
        if not self._ha_alteracoes_estado_nao_salvas():
            return
        try:
            self._sincronizar_documentos_canvas_no_projeto()
            GSProjectIO.salvar(self.projeto_atual, self._arquivo_atual)
            for i in range(self.abas_documentos.count()):
                area = self.abas_documentos.widget(i)
                if isinstance(area, AreaDocumentoWidget):
                    self._marcar_estado_area_como_salvo(area)
        except Exception:
            pass

    def _agendar_salvar_estado_silencioso(self):
        if hasattr(self, "_timer_salvar_estado"):
            self._timer_salvar_estado.start(450)

    def _criar_barra_inferior(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        atalhos = QFrame()
        self.barra_atalhos_rodape = atalhos
        atalhos.setFixedHeight(24)
        tema = self._tema_interface()
        atalhos.setStyleSheet(
            f"background:{tema['faixa']}; border-top:1px solid {tema['borda']}; border-bottom:1px solid {tema['borda']};"
        )
        row = QHBoxLayout(atalhos)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(4)

        estilo_botao_icone = self._estilo_botoes_rodape()

        self.btn_snap = _BotaoRodapeHover("🧲", "Ativa ou desativa o snap")
        self.btn_snap.setCheckable(True)
        self.btn_snap.setChecked(self._snap_ativo_global)
        self.btn_snap.setCursor(Qt.PointingHandCursor)
        self.btn_snap.setToolTip("Ativar/Desativar snap (ímã)")
        icone_snap = ICONS_DIR / "snap.svg"
        if icone_snap.exists():
            self.btn_snap.setIcon(self._icone_snap_estado(self._snap_ativo_global))
            self.btn_snap.setText("")
        elif not self._snap_ativo_global:
            self.btn_snap.setText("X")
        self.btn_snap.toggled.connect(self._alternar_snap_canvas_atual)
        self.btn_snap.setStyleSheet(estilo_botao_icone)
        row.addWidget(self.btn_snap)

        self.btn_mao = _BotaoRodapeHover("🖐", "Movimenta a posição de visualização")
        self.btn_mao.setCheckable(True)
        self.btn_mao.setFixedHeight(20)
        self.btn_mao.setToolTip("Mão (navegação)")
        self.btn_mao.setStyleSheet(estilo_botao_icone)
        self.btn_mao.clicked.connect(lambda: self._set_modo_navegacao("mao"))
        row.addWidget(self.btn_mao)

        self.btn_lupa = _BotaoRodapeHover("🔍", "Define a visão da área selecionada")
        self.btn_lupa.setCheckable(True)
        self.btn_lupa.setFixedHeight(20)
        self.btn_lupa.setToolTip("Lupa")
        self.btn_lupa.setStyleSheet(estilo_botao_icone)
        self.btn_lupa.clicked.connect(lambda: self._set_modo_navegacao("lupa"))
        row.addWidget(self.btn_lupa)

        self.btn_visualizar_tudo = _BotaoRodapeHover("⤢", "Visualiza toda a área de moldes")
        self.btn_visualizar_tudo.setFixedHeight(20)
        self.btn_visualizar_tudo.setStyleSheet(estilo_botao_icone)
        self.btn_visualizar_tudo.clicked.connect(self._visualizar_todos_os_moldes)
        row.addWidget(self.btn_visualizar_tudo)

        self.btn_zoom_menos = _BotaoRodapeHover("−", "Afasta a visão a cada clique")
        self.btn_zoom_menos.setFixedHeight(20)
        self.btn_zoom_menos.setToolTip("Zoom -")
        self.btn_zoom_menos.setStyleSheet(estilo_botao_icone)
        self.btn_zoom_menos.clicked.connect(lambda: self._aplicar_zoom_incremental(1 / 1.1))
        row.addWidget(self.btn_zoom_menos)

        self.btn_zoom_mais = _BotaoRodapeHover("+", "Aumenta o nível de visualização")
        self.btn_zoom_mais.setFixedHeight(20)
        self.btn_zoom_mais.setToolTip("Zoom +")
        self.btn_zoom_mais.setStyleSheet(estilo_botao_icone)
        self.btn_zoom_mais.clicked.connect(lambda: self._aplicar_zoom_incremental(1.1))
        row.addWidget(self.btn_zoom_mais)

        self.btn_aumenta_indicado = _BotaoRodapeHover("⌕", "Aumenta o nível de visualização de um elemento ou molde indicado")
        self.btn_aumenta_indicado.setFixedHeight(20)
        self.btn_aumenta_indicado.setStyleSheet(estilo_botao_icone)
        self.btn_aumenta_indicado.clicked.connect(self._armar_centralizacao_indicada)
        row.addWidget(self.btn_aumenta_indicado)

        self.btn_desfazer_visao = _BotaoRodapeHover("⟲", "Desfaz o último comando de visualização")
        self.btn_desfazer_visao.setFixedHeight(20)
        self.btn_desfazer_visao.setStyleSheet(estilo_botao_icone)
        self.btn_desfazer_visao.clicked.connect(lambda: self.lbl_status.setText("Desfaz o último comando de visualização"))
        row.addWidget(self.btn_desfazer_visao)

        self.btn_grid = _BotaoRodapeHover("⋮⋮", "Habilita ou desabilita o grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(False)
        self.btn_grid.setFixedHeight(20)
        self.btn_grid.setStyleSheet(estilo_botao_icone)
        icone_grid = ICONS_DIR / "grid.svg"
        if icone_grid.exists():
            self.btn_grid.setIcon(carregar_icone("grid.svg"))
            self.btn_grid.setText("")
        self.btn_grid.toggled.connect(self._alternar_grid_canvas)
        row.addWidget(self.btn_grid)

        self.btn_graduacao = _BotaoRodapeHover("⇅", "Mostra ou esconde graduação")
        self.btn_graduacao.setCheckable(True)
        self.btn_graduacao.setChecked(True)
        self.btn_graduacao.setFixedHeight(20)
        self.btn_graduacao.setStyleSheet(estilo_botao_icone)
        self.btn_graduacao.toggled.connect(self._alternar_graduacao_canvas)
        row.addWidget(self.btn_graduacao)

        self.btn_costura = _BotaoRodapeHover("C", "Mostra ou esconde costura")
        self.btn_costura.setCheckable(True)
        self.btn_costura.setChecked(True)
        self.btn_costura.setFixedHeight(20)
        self.btn_costura.setStyleSheet(estilo_botao_icone)
        icone_costura = ICONS_DIR / "costura.svg"
        if icone_costura.exists():
            self.btn_costura.setIcon(carregar_icone("costura.svg"))
            self.btn_costura.setText("")
        self.btn_costura.toggled.connect(self._alternar_costura_canvas)
        row.addWidget(self.btn_costura)

        self.btn_organizar_moldes = _BotaoRodapeHover("⇵", "Organiza todos os moldes")
        self.btn_organizar_moldes.setFixedHeight(20)
        self.btn_organizar_moldes.setToolTip("Reorganiza todos os moldes com variações de layout")
        self.btn_organizar_moldes.setStyleSheet(estilo_botao_icone)
        self.btn_organizar_moldes.clicked.connect(self._organizar_moldes_canvas_atual)
        row.addWidget(self.btn_organizar_moldes)

        self.btn_proximo_molde = _BotaoRodapeHover("▶", "Visualiza próximo molde")
        self.btn_proximo_molde.setFixedHeight(20)
        self.btn_proximo_molde.setToolTip("Visualiza próximo molde")
        self.btn_proximo_molde.setStyleSheet(estilo_botao_icone)
        self.btn_proximo_molde.clicked.connect(self._visualizar_proximo_molde)
        row.addWidget(self.btn_proximo_molde)

        self.btn_visualizacao_instantanea = _BotaoRodapeHover("◌", "Adicionar visualização instantânea")
        self.btn_visualizacao_instantanea.setCheckable(True)
        self.btn_visualizacao_instantanea.setFixedHeight(20)
        self.btn_visualizacao_instantanea.setToolTip("Adicionar visualização instantânea")
        self.btn_visualizacao_instantanea.setStyleSheet(estilo_botao_icone)
        self.btn_visualizacao_instantanea.toggled.connect(self._alternar_visualizacao_instantanea)
        row.addWidget(self.btn_visualizacao_instantanea)

        row.addStretch(1)
        for btn in atalhos.findChildren(QPushButton):
            if not btn.toolTip():
                dica = btn.statusTip().strip() if btn.statusTip() else ""
                if not dica:
                    dica = btn.text().strip()
                if dica:
                    btn.setToolTip(dica)
        layout.addWidget(atalhos)

        barra = QFrame()
        barra.setFixedHeight(22)
        barra.setStyleSheet(
            f"background: {tema['primaria']}; border-top: 1px solid {tema['primaria_escura']}; color: white;"
        )
        l = QHBoxLayout(barra)
        l.setContentsMargins(10, 0, 10, 0)
        self.lbl_status = QLabel("Pronto")
        self.lbl_status.setMinimumWidth(0)
        self.lbl_status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_status.setStyleSheet("color: white;")
        l.addWidget(self.lbl_status)
        for b in (
            self.btn_snap,
            self.btn_mao,
            self.btn_lupa,
            self.btn_visualizar_tudo,
            self.btn_zoom_menos,
            self.btn_zoom_mais,
            self.btn_aumenta_indicado,
            self.btn_desfazer_visao,
            self.btn_grid,
            self.btn_graduacao,
            self.btn_costura,
            self.btn_organizar_moldes,
            self.btn_proximo_molde,
            self.btn_visualizacao_instantanea,
        ):
            if isinstance(b, _BotaoRodapeHover):
                b.vincular_status(self.lbl_status)
        l.addStretch(1)
        self.lbl_escala = QLabel("Escala 100%")
        self.lbl_escala.setMinimumWidth(150)
        self.lbl_escala.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_escala.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.lbl_escala.setStyleSheet("color: white; font-weight: 600; padding-right: 2px;")
        l.addWidget(self.lbl_escala)
        self.barra_mensagem = barra
        self.barra_mensagem.setVisible(self.action_barra_mensagem.isChecked())
        layout.addWidget(barra)
        return container

    def _set_modo_navegacao(self, modo: str):
        self._modo_navegacao = modo
        self.btn_mao.blockSignals(True)
        self.btn_lupa.blockSignals(True)
        self.btn_mao.setChecked(modo == "mao")
        self.btn_lupa.setChecked(modo == "lupa")
        self.btn_mao.blockSignals(False)
        self.btn_lupa.blockSignals(False)
        self.lbl_status.setText(f"Modo {modo} selecionado")

    def _aplicar_zoom_incremental(self, fator: float):
        area = self._area_documento_atual()
        if not area:
            return
        area.canvas.set_zoom(area.canvas.zoom * fator)

    def _visualizar_todos_os_moldes(self):
        area = self._area_documento_atual()
        if not area:
            return
        canvas = area.canvas
        moldes = [el for el in canvas.cena.elementos if isinstance(el, dict) and el.get("molde")]
        elementos_alvo = moldes if moldes else [el for el in canvas.cena.elementos if isinstance(el, dict)]
        if not elementos_alvo:
            self.lbl_status.setText("Nenhum molde/elemento para visualizar.")
            return
        self._centralizar_canvas_em_elementos(canvas, elementos_alvo)
        self.lbl_status.setText("Visualiza toda a área de moldes.")

    def _armar_centralizacao_indicada(self):
        self._pendente_centralizar_indicado = True
        self.lbl_status.setText("Indique o molde ou elemento.")

    def _centralizar_molde_ou_elemento_indicado(self, idx_indicado: int | None = None):
        area = self._area_documento_atual()
        if not area:
            return
        canvas = area.canvas
        selecionados = sorted(getattr(canvas, "_selecionados", set()))
        alvo = None
        if idx_indicado is not None and 0 <= int(idx_indicado) < len(canvas.cena.elementos):
            alvo = canvas.cena.elementos[int(idx_indicado)]
        elif selecionados:
            idx = selecionados[0]
            if 0 <= idx < len(canvas.cena.elementos):
                alvo = canvas.cena.elementos[idx]
        if alvo is None:
            moldes = [el for el in canvas.cena.elementos if isinstance(el, dict) and el.get("molde")]
            if moldes:
                alvo = moldes[0]
        if alvo is None and canvas.cena.elementos:
            alvo = canvas.cena.elementos[0]
        if alvo is None:
            self.lbl_status.setText("Nenhum molde/elemento para centralizar.")
            return
        bbox = self._bbox_elemento(alvo)
        if bbox is None:
            return
        min_x, min_y, max_x, max_y = bbox
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        canvas.set_zoom(min(20.0, max(0.1, canvas.zoom * 1.35)))
        canvas.origem_cena.setX(cx - (canvas.width() / (2 * canvas.zoom)))
        canvas.origem_cena.setY(cy - (canvas.height() / (2 * canvas.zoom)))
        canvas.update()
        self.lbl_status.setText("Molde/elemento indicado centralizado.")

    def _texto_escala(self, zoom: float) -> str:
        base = max(self.ZOOM_INICIAL_CANVAS, 1e-9)
        percentual = (zoom / base) * 100.0
        return f"Escala {percentual:.3f}%"

    def _atualizar_label_escala(self, zoom: float | None = None):
        if not hasattr(self, "lbl_escala"):
            return
        if zoom is None:
            area = self._area_documento_atual()
            if isinstance(area, AreaDocumentoWidget):
                zoom = area.canvas.zoom
        texto = self._texto_escala(float(zoom)) if isinstance(zoom, (int, float)) else "Escala --"
        self.lbl_escala.setText(texto)
        self.lbl_escala.setVisible(True)
        self.lbl_escala.updateGeometry()
        self.lbl_escala.update()

    def _centralizar_area_documento(self, area: AreaDocumentoWidget):
        elementos = area.canvas.cena.elementos
        if not elementos:
            self._aplicar_viewport_inicial(area)
            return
        self._centralizar_canvas_em_elementos(area.canvas, elementos)
        area._on_zoom_changed(area.canvas.zoom)

    def _aplicar_viewport_inicial(self, area: AreaDocumentoWidget):
        area.canvas.set_zoom(self.ZOOM_INICIAL_CANVAS)
        area.canvas.origem_cena.setX(self.ORIGEM_INICIAL_CANVAS_X)
        area.canvas.origem_cena.setY(self.ORIGEM_INICIAL_CANVAS_Y)
        area._on_zoom_changed(area.canvas.zoom)
        area.canvas.update()

    def _salvar_thumbnail_projeto(self, destino: Path):
        docs = self.projeto_atual.preferencias_usuario.get("documentos_canvas", [])
        if not docs:
            return
        elementos: list[dict] = []
        for doc in docs:
            cand = doc.get("elementos", [])
            if isinstance(cand, list) and cand:
                elementos = cand
                break
        if not elementos:
            return
        imagem = self._gerar_thumbnail_elementos(elementos, largura=960, altura=540)
        if imagem is None:
            return
        arr = QByteArray()
        buffer = QBuffer(arr)
        buffer.open(QIODevice.WriteOnly)
        imagem.save(buffer, "PNG")
        buffer.close()
        png_bytes = bytes(arr)
        with ZipFile(destino, mode="a", compression=ZIP_DEFLATED) as pacote:
            pacote.writestr("preview/thumbnail.png", png_bytes)
            pacote.writestr("preview/thumbnail.enc", self._criptografar_preview(png_bytes))
            pacote.writestr("thumbnail.png", png_bytes)
            pacote.writestr("meta/thumbnail.png", png_bytes)
        self.projeto_atual.preferencias_usuario["thumbnail_internal"] = "preview/thumbnail.png"

    def _gerar_thumbnail_elementos(self, elementos: list[dict], largura: int, altura: int) -> QImage | None:
        def _xy(valor) -> tuple[float, float] | None:
            if isinstance(valor, dict) and "x" in valor and "y" in valor:
                try:
                    return float(valor["x"]), float(valor["y"])
                except Exception:
                    return None
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                try:
                    return float(valor[0]), float(valor[1])
                except Exception:
                    return None
            return None

        def _qpoints(valores) -> list[QPointF]:
            pontos_saida: list[QPointF] = []
            for item in valores or []:
                xy = _xy(item)
                if xy is not None:
                    pontos_saida.append(QPointF(xy[0], xy[1]))
            return pontos_saida

        def _amostrar_bezier(el: dict) -> list[QPointF]:
            p0 = _xy(el.get("p0"))
            p1 = _xy(el.get("p1"))
            p2 = _xy(el.get("p2"))
            if p0 is None or p1 is None or p2 is None:
                return []
            pontos_bezier = []
            for i in range(33):
                t = i / 32.0
                mt = 1.0 - t
                x = (mt * mt * p0[0]) + (2.0 * mt * t * p1[0]) + (t * t * p2[0])
                y = (mt * mt * p0[1]) + (2.0 * mt * t * p1[1]) + (t * t * p2[1])
                pontos_bezier.append(QPointF(x, y))
            return pontos_bezier

        def _pontos_base(el: dict) -> list[QPointF]:
            if el.get("tipo") == "polyline":
                return _qpoints(el.get("pontos", []))
            if el.get("tipo") == "bezier_quadratica":
                return _amostrar_bezier(el)
            return []

        def _graduacao(el: dict, base: list[QPointF]):
            if not el.get("molde") or el.get("mostrar_graduacao", True) is False or len(base) < 2:
                return [], []
            try:
                from canvas.visualizacao import VisualizacaoCanvas

                contornos = VisualizacaoCanvas._contornos_graduacao_tabela(el, base)
                caminhos = VisualizacaoCanvas._caminhos_graduacao_tabela(el, base)
                return contornos, caminhos
            except Exception:
                return [], []

        pontos_bbox: list[QPointF] = []
        elementos_base: list[tuple[dict, list[QPointF], list, list]] = []
        for el in elementos:
            if not isinstance(el, dict):
                continue
            base = _pontos_base(el)
            contornos, caminhos = _graduacao(el, base)
            elementos_base.append((el, base, contornos, caminhos))
            pontos_bbox.extend(base)
            for _nome, _cor, pontos_grad in contornos:
                pontos_bbox.extend(QPointF(pt) for pt in pontos_grad)
            for _nome, _cor, origem, destino in caminhos:
                pontos_bbox.extend([QPointF(origem), QPointF(destino)])
            for chave in ("fio_origem", "fio_fim"):
                xy = _xy(el.get(chave))
                if xy is not None:
                    pontos_bbox.append(QPointF(xy[0], xy[1]))

        if len(pontos_bbox) < 2:
            return None

        xs = [p.x() for p in pontos_bbox]
        ys = [p.y() for p in pontos_bbox]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura_geo = max(max_x - min_x, 1.0)
        altura_geo = max(max_y - min_y, 1.0)

        margem = max(26, int(min(largura, altura) * 0.08))
        escala = min((largura - margem * 2) / largura_geo, (altura - margem * 2) / altura_geo)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0

        def _mapear(ponto: QPointF) -> QPointF:
            return QPointF(
                (ponto.x() - cx) * escala + (largura / 2.0),
                (ponto.y() - cy) * escala + (altura / 2.0),
            )

        def _desenhar_linha(painter: QPainter, pontos_linha: list[QPointF], cor: str, esp: float, estilo=Qt.SolidLine):
            if len(pontos_linha) < 2:
                return
            pen = QPen(QColor(cor), esp, estilo)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for a, b in zip(pontos_linha, pontos_linha[1:]):
                painter.drawLine(_mapear(a), _mapear(b))

        img = QImage(largura, altura, QImage.Format_ARGB32)
        img.fill(QColor("#050607"))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(QRectF(0, 0, largura, altura), QColor("#050607"))

        for el, base, _contornos, _caminhos in elementos_base:
            if el.get("molde"):
                continue
            subtipo = str(el.get("subtipo_audaces") or el.get("metadados", {}).get("subtipo_audaces") or "").lower()
            if subtipo == "costura" or el.get("costura_de_molde_id"):
                _desenhar_linha(painter, base, "#51b8ff", 1.4, Qt.DashLine)
            elif subtipo == "linha_interna" or el.get("molde_linha_vinculada"):
                _desenhar_linha(painter, base, "#aeb7c2", 1.15, Qt.DotLine)
            else:
                _desenhar_linha(painter, base, str(el.get("cor") or "#8be9ff"), 1.2)

        for el, base, contornos, caminhos in elementos_base:
            if not el.get("molde"):
                continue
            for _nome, cor, pontos_grad in contornos:
                cor_grad = str(cor or "#f0ff00")
                if not QColor(cor_grad).isValid():
                    cor_grad = "#f0ff00"
                _desenhar_linha(painter, [QPointF(pt) for pt in pontos_grad], cor_grad, 1.2)
            if el.get("visual_caminho_grade", False):
                for _nome, _cor, origem, destino in caminhos:
                    _desenhar_linha(painter, [QPointF(origem), QPointF(destino)], "#3aa6ff", 1.0, Qt.DotLine)

        for el, base, _contornos, _caminhos in elementos_base:
            if not el.get("molde"):
                continue
            cor_molde = str(el.get("cor") or "#ff9d00")
            if not QColor(cor_molde).isValid() or cor_molde.lower() == "#ffffff":
                cor_molde = "#ff9d00"
            _desenhar_linha(painter, base, cor_molde, 2.4)
            fio_origem = _xy(el.get("fio_origem"))
            fio_fim = _xy(el.get("fio_fim"))
            if fio_origem is not None and fio_fim is not None and el.get("mostrar_fio", True) is not False:
                p1 = QPointF(*fio_origem)
                p2 = QPointF(*fio_fim)
                _desenhar_linha(painter, [p1, p2], "#65e6c3", 1.5)
                centro = _mapear(QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0))
                painter.setPen(QPen(QColor("#65e6c3"), 1.2))
                painter.drawEllipse(centro, 3.5, 3.5)

            controles = _qpoints(el.get("controle_cantos") or el.get("pontos_controle_principais") or [])
            painter.setPen(QPen(QColor("#d8f6ff"), 1.0))
            painter.setBrush(QColor("#050607"))
            for ponto in controles[:8]:
                p = _mapear(ponto)
                painter.drawRect(QRectF(p.x() - 2.5, p.y() - 2.5, 5.0, 5.0))

        painter.end()
        return img
