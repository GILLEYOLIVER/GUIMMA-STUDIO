from __future__ import annotations

import base64
import json
import sys
from datetime import datetime
from importlib import import_module
from math import ceil, cos, pi, sin, sqrt
from pathlib import Path
from time import time
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QByteArray, QBuffer, QEvent, QIODevice, QModelIndex, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QListView,
    QPushButton,
    QRadioButton,
    QSizePolicy,
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
from core.projeto import Projeto
from formats.gs_project import GSProjectIO
from formats.adsx_io import ADSXIO, ADSXImportError
from formats.audaces_xml_import import AudacesXMLImport, xml_doc_para_dict
from formats.audaces_pair_import import AudacesPairImport
from formats.dxf_import import importar_dxf_para_elementos
from ui.backstage_arquivo import BackstageArquivoPanel
from ui.ribbon import RibbonWidget
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

    def vincular_status(self, lbl_status: QLabel):
        self._status_label = lbl_status

    def enterEvent(self, event):  # noqa: N802
        super().enterEvent(event)
        if self._status_label is not None and self._mensagem_hover:
            self._status_label.setText(self._mensagem_hover)


class GuimmaStudioMainWindow(QMainWindow):
    ARQUIVO_PREFS_APP = Path.home() / ".guimma_studio_prefs.json"
    ARQUIVO_RECUPERACAO = Path.home() / ".guimma_studio_recovery.json"
    ZOOM_INICIAL_CANVAS = 8.760
    ORIGEM_INICIAL_CANVAS_X = 110.0
    ORIGEM_INICIAL_CANVAS_Y = 0.0

    def __init__(self):
        super().__init__()
        self.projeto_atual = Projeto()
        prefs_app = self._carregar_preferencias_app()
        if prefs_app:
            self.projeto_atual.preferencias_usuario.update(prefs_app)
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
        self._mostrar_cor_tecidos_global = bool(self.projeto_atual.preferencias_usuario.get("mostrar_cor_tecidos_global", False))
        cores_cfg = self.projeto_atual.preferencias_usuario.get("cores_tecidos_global", {})
        self._cores_tecidos_global: dict[str, str] = dict(cores_cfg) if isinstance(cores_cfg, dict) else {}
        self._clipboard_elementos_global: dict | None = None
        self._posicoes_caixas_aux: dict[str, tuple[int, int]] = self._carregar_posicoes_caixas_aux()
        self._painel_coordenadas_pos_global: tuple[int, int] | None = None
        self._ferramentas_usuario_ids: list[str] = list(self.projeto_atual.preferencias_usuario.get("ferramentas_usuario", []))
        self._ultima_aba_nao_usuario = "construcao"
        self._barra_usuarios_posicao = self.projeto_atual.preferencias_usuario.get("barra_usuarios_posicao", "area")
        self._barra_usuarios_habilitada = True
        self._perfis_usuarios: dict[str, list[str]] = {}
        self._perfis_usuarios_cfg: dict[str, dict] = {}
        self._perfil_usuario_atual = "Usuário 1"
        self._indice_layout_organizacao_moldes = 0
        self._inicializar_perfis_usuarios()
        self._opcoes_app = self._carregar_opcoes_app()
        self._timer_salvar_estado = QTimer(self)
        self._timer_salvar_estado.setSingleShot(True)
        self._timer_salvar_estado.timeout.connect(self._salvar_estado_projeto_silenciosamente)
        self._timer_recovery = QTimer(self)
        self._timer_recovery.timeout.connect(self._salvar_snapshot_recuperacao)
        self._aplicar_intervalo_recovery()
        self._menu_backstage_hover_aberto: QMenu | None = None
        self._menu_backstage_hover_origem: str | None = None
        self._menu_backstage_hover_botao: QWidget | None = None
        self._menus_backstage_hover: list[QMenu] = []
        self._timer_fechar_submenu_backstage = QTimer(self)
        self._timer_fechar_submenu_backstage.setSingleShot(True)
        self._timer_fechar_submenu_backstage.timeout.connect(self._fechar_submenu_backstage_se_cursor_fora)
        self._timer_vigiar_submenu_backstage = QTimer(self)
        self._timer_vigiar_submenu_backstage.setInterval(50)  # 50ms para resposta rápida
        self._timer_vigiar_submenu_backstage.timeout.connect(self._processar_hover_backstage_global)
        self.setWindowTitle("GUIMMA STUDIO")
        self._configurar_interface()
        self.ribbon.aplicar_estilo(self._estilo_desenho_atual)
        self._limpar_abas_documentos()
        self._configurar_atalhos()
        QApplication.instance().installEventFilter(self)
        self._oferecer_recuperacao_pos_falha()
        QTimer.singleShot(0, lambda: self._ativar_ferramenta_global("selecionar"))
        self.showMaximized()

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
        minutos = max(1, int(self._opcoes_app.get("auto_recuperacao_min", 1)))
        self._timer_recovery.start(minutos * 60 * 1000)

    def _capturar_configuracoes_perfil(self) -> dict:
        return {
            "unidade_medida": self._unidade_medida,
            "passo_unidade_medida": self._passo_unidade_medida,
            "unidade_area": self._unidade_area,
            "precisao_medida": self._precisao_medida,
            "barra_usuarios_habilitada": self._barra_usuarios_habilitada,
            "barra_usuarios_posicao": self._barra_usuarios_posicao,
            "estilo_desenho": dict(self._estilo_desenho_atual),
        }

    def _aplicar_configuracoes_perfil(self, cfg: dict):
        if not isinstance(cfg, dict):
            return
        self._unidade_medida = str(cfg.get("unidade_medida", self._unidade_medida))
        self._passo_unidade_medida = float(cfg.get("passo_unidade_medida", self._passo_unidade_medida))
        self._unidade_area = str(cfg.get("unidade_area", self._unidade_area))
        self._precisao_medida = str(cfg.get("precisao_medida", self._precisao_medida))
        self._barra_usuarios_habilitada = True
        self._barra_usuarios_posicao = str(cfg.get("barra_usuarios_posicao", self._barra_usuarios_posicao))
        estilo = cfg.get("estilo_desenho")
        if isinstance(estilo, dict):
            self._estilo_desenho_atual.update(estilo)

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
        sup.addWidget(self.ribbon.tabbar, 0, Qt.AlignLeft)
        sup.addStretch(1)

        menu_btn_style = (
            "QToolButton { color:#1b1b1b; font-weight:400; font-size:13px; padding:0 6px; border:none; background:transparent; }"
            "QToolButton::menu-indicator { subcontrol-origin: padding; subcontrol-position: right center; }"
            "QToolButton:hover { color:#0b5f9e; }"
        )
        menu_popup_style = (
            "QMenu { background:#ffffff; color:#111111; border:1px solid #cfd6de; padding:4px; }"
            "QMenu::item { color:#111111; padding:6px 12px; }"
            "QMenu::item:selected { background:#e9f3ff; color:#0b4f82; }"
        )

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
        self.action_menu_moldes.triggered.connect(lambda: self.lbl_status.setText("Menu de moldes (em breve)"))
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
        self.action_barra_usuarios_habilitada.setChecked(True)
        self.action_barra_usuarios_habilitada.setEnabled(False)
        self.action_barra_usuarios_habilitada.toggled.connect(self._alternar_barra_usuarios_habilitada)
        menu_barra_usuarios.addAction(self.action_barra_usuarios_habilitada)
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
        self.action_barra_usuarios_area.setChecked(self._barra_usuarios_posicao != "topo")
        self.action_barra_usuarios_area.triggered.connect(lambda marcado=False: self._definir_posicao_barra_usuarios("area") if marcado else None)
        grupo_posicao_barra.addAction(self.action_barra_usuarios_area)
        menu_barra_usuarios.addAction(self.action_barra_usuarios_area)
        self.btn_visao.setMenu(self.menu_visao)
        sup.addWidget(self.btn_visao)

        self.btn_opcoes = QToolButton()
        self.btn_opcoes.setText("OPÇÕES")
        self.btn_opcoes.setPopupMode(QToolButton.InstantPopup)
        self.btn_opcoes.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_opcoes.setMinimumWidth(86)
        self.btn_opcoes.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_opcoes.setStyleSheet(menu_btn_style)
        menu_opcoes = QMenu(self)
        menu_opcoes.setStyleSheet(menu_popup_style)
        menu_opcoes.addAction("Preferências", lambda: self.lbl_status.setText("Preferências (em breve)"))
        menu_opcoes.addAction("Atalhos", lambda: self.lbl_status.setText("Atalhos (em breve)"))
        self.btn_opcoes.setMenu(menu_opcoes)
        sup.addWidget(self.btn_opcoes)

        self.btn_janelas = QToolButton()
        self.btn_janelas.setText("JANELAS")
        self.btn_janelas.setPopupMode(QToolButton.InstantPopup)
        self.btn_janelas.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_janelas.setMinimumWidth(92)
        self.btn_janelas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_janelas.setStyleSheet(menu_btn_style)
        menu_janelas = QMenu(self)
        menu_janelas.setStyleSheet(menu_popup_style)
        menu_janelas.addAction("Organizar janelas", lambda: self.lbl_status.setText("Organização de janelas (em breve)"))
        menu_janelas.addAction("Resetar layout", lambda: self.lbl_status.setText("Reset de layout (em breve)"))
        self.btn_janelas.setMenu(menu_janelas)
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
            hasattr(self, "backstage")
            and self.backstage.isVisible()
            and tipo_evento in (QEvent.Enter, QEvent.MouseMove, QEvent.Leave)
        ):
            self._processar_hover_backstage_global()

        if isinstance(watched, QMenu) and getattr(watched, "_menu_hover_backstage", False):
            if tipo_evento in (QEvent.Enter, QEvent.MouseMove):
                self._cancelar_fechamento_submenu_backstage()
            elif tipo_evento == QEvent.Leave:
                self._agendar_fechamento_submenu_backstage(70)
            elif tipo_evento in (QEvent.Hide, QEvent.Close):
                self._limpar_menu_backstage_hover_se_necessario(watched)

        if getattr(watched, "_backstage_hover_monitor", False):
            if tipo_evento in (QEvent.Enter, QEvent.MouseMove):
                texto = getattr(watched, "_backstage_item_texto", None)
                if texto and self._item_backstage_tem_submenu(texto):
                    self._abrir_submenu_backstage_hover(texto)
                elif getattr(self, "_menu_backstage_hover_aberto", None) is not None:
                    self._agendar_fechamento_submenu_backstage(70)
            elif tipo_evento == QEvent.Leave and getattr(self, "_menu_backstage_hover_aberto", None) is not None:
                self._agendar_fechamento_submenu_backstage(70)

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
        if isinstance(watched, QDialog) and tipo_evento in (QEvent.Close, QEvent.Hide):
            self._garantir_selecionar_apos_fechar_janela()
        return super().eventFilter(watched, event)

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
        if self._executar_acao_edicao_ribbon(tool_id):
            self._log_debug_propriedades(f"tool_id={tool_id!r} tratado como ação de edição ribbon.")
            return
        tool_def = self.ribbon.tool_def(tool_id)
        self._log_debug_propriedades(f"tool_def encontrado={tool_def is not None}")
        if not tool_def:
            self.lbl_status.setText(f"Ferramenta não encontrada: {tool_id}")
            self._log_debug_propriedades(f"Ferramenta não encontrada para tool_id={tool_id!r}")
            return
        if self._abrir_janela_auxiliar_ferramenta(tool_id, tool_def.title):
            self._log_debug_propriedades(f"tool_id={tool_id!r} abriu janela auxiliar e retornou.")
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
        acoes = {
            "copiar": (area.canvas.copiar, "Copiado"),
            "colar": (area.canvas.colar, "Colado"),
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

            layout.addWidget(rb_np)
            layout.addWidget(rb_suave)
            layout.addWidget(rb_3p)
            layout.addWidget(rb_2p)

            rb_np.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("np") if marcado else None)
            rb_suave.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("suave") if marcado else None)
            rb_3p.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("3p") if marcado else None)
            rb_2p.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("2p") if marcado else None)

            self._rb_curva_np = rb_np
            self._rb_curva_suave = rb_suave
            self._rb_curva_3p = rb_3p
            self._rb_curva_2p = rb_2p
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
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(janela.width(), janela.height(), abaixo_coordenadas=True)
            pos_global = canvas.mapToGlobal(pos_local)
            janela.move(pos_global)
            return
        gx = canvas.mapToGlobal(canvas.rect().topLeft()).x()
        gy = canvas.mapToGlobal(canvas.rect().topLeft()).y()
        min_x = gx + 8
        min_y = gy + 8
        max_x = gx + max(8, canvas.width() - janela.width() - 8)
        max_y = gy + max(8, canvas.height() - janela.height() - 8)

        pos = self._posicoes_caixas_aux.get(chave)
        if pos:
            x = max(min_x, min(pos[0], max_x))
            y = max(min_y, min(pos[1], max_y))
            janela.move(x, y)
            return

        x = gx + max(8, canvas.width() - janela.width() - 18)
        y = gy + 16
        janela.move(max(min_x, min(x, max_x)), max(min_y, min(y, max_y)))

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
        fundo = "#d9edf9" if ativo else "transparent"
        return f"""
            QPushButton {{
                background: {fundo};
                color: #111111;
                border: none;
                border-radius: 0px;
                text-align: left;
                padding: 0px 8px 0px 8px;
                font-size: 12px;
                font-weight: 400;
            }}
            QPushButton:pressed {{
                background: #c6e2f4;
                color: #000000;
            }}
            QPushButton:disabled {{
                background: transparent;
                color: #777777;
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
            if self._qt_widget_visivel(menu_atual):
                self._fechar_submenu_backstage_hover(forcar=True)
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
        if self._cursor_sobre_algum_menu_backstage(cursor_pos) or self._cursor_sobre_corredor_entre_botao_e_menu(cursor_pos):
            self._limpar_hover_botoes_backstage(botao_atual if self._qt_widget_vivo(botao_atual) else None)
            self._cancelar_fechamento_submenu_backstage()
            return

        # Cursor saiu da área útil: remove destaque e fecha.
        self._limpar_hover_botoes_backstage()
        if self._qt_widget_visivel(menu_atual):
            self._agendar_fechamento_submenu_backstage(40)
        else:
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
            if self._cursor_sobre_widget_global(menu, pos, margem=1):
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
        return self._cursor_sobre_algum_menu_backstage(pos) or self._cursor_sobre_corredor_entre_botao_e_menu(pos)

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
        menu.addAction("Audaces (*.emf *.xml *.adsx)", lambda: self._importar_por_tipo("audaces"))
        sub_adv = menu.addMenu("Audaces Avançado")
        sub_adv.addAction("EMF (*.emf)", lambda: self._importar_por_tipo("audaces_emf"))
        sub_adv.addAction("XML (*.xml)", lambda: self._importar_por_tipo("audaces_xml"))
        sub_adv.addAction("ADSX (*.adsx)", lambda: self._importar_por_tipo("adsx"))
        sub_adv.addAction("EMF + XML", lambda: self._importar_por_tipo("audaces_emf_xml"))
        menu.addSeparator()
        menu.addAction("Converter manualmente por traçado", self._acao_converter_manual_tracado_adsx)
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
                    acao.setIcon(QIcon(str(caminho)))
            return acao

        menu.addAction("Opções", self._abrir_dialogo_opcoes)
        menu.addAction("Unidade de medida\tCtrl+U", self._abrir_dialogo_unidade_medida)
        menu.addAction("Mesa digitalizadora", lambda: self.lbl_status.setText("Mesa digitalizadora (em breve)"))
        menu_regras = menu.addMenu("Regras de graduação")
        menu_regras.addAction("Regras de Graduação - Nomes...", lambda: self.lbl_status.setText("Regras de Graduação - Nomes (em breve)"))
        menu_regras.addAction("Regras de Graduação - Valores...", lambda: self.lbl_status.setText("Regras de Graduação - Valores (em breve)"))
        _add_menu_acao("Cores", self._abrir_dialogo_cores, "cores_rapido.svg")
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
        return (
            "QMenu { background:#ffffff; color:#111111; border:1px solid #c8d0d8; padding:3px; }"
            "QMenu::item { color:#111111; padding:7px 22px 7px 18px; min-width:220px; }"
            "QMenu::item:selected { background:#e6f2ff; color:#0b4f82; }"
            "QMenu::separator { height:1px; background:#d8dee6; margin:4px 8px; }"
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
        try:
            mins = int(float(edt_auto.text().strip().replace(",", ".")))
        except Exception:
            mins = 1
        def _float_val(edt: QLineEdit, default: float) -> float:
            try:
                return float(edt.text().strip().replace(",", "."))
            except Exception:
                return default
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

    def _abrir_dialogo_cores(self):
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

    def _aplicar_estilo_claro_dialogo(self, dialog: QDialog):
        dialog.setStyleSheet(
            """
            QDialog { background: #efefef; color: #111111; }
            QGroupBox { border: 1px solid #c8c8c8; margin-top: 10px; background: #f5f5f5; }
            QGroupBox::title { left: 6px; padding: 0 2px; }
            QLabel, QCheckBox { color: #111111; }
            QPushButton, QComboBox, QLineEdit {
                background: #ffffff;
                color: #111111;
                border: 1px solid #b5bcc3;
                border-radius: 3px;
                min-height: 22px;
                padding: 2px 6px;
            }
            QTableWidget {
                background: #ffffff;
                color: #111111;
                border: 1px solid #b5bcc3;
                gridline-color: #d6dbe0;
            }
            QHeaderView::section {
                background: #f1f1f1;
                color: #111111;
                border: 1px solid #c2c8cf;
                padding: 3px;
            }
            """
        )

    def _centralizar_dialogo_na_janela(self, dialog: QDialog):
        dialog.adjustSize()
        geo_janela = self.frameGeometry()
        centro_janela = geo_janela.center()
        geo_dialogo = dialog.frameGeometry()
        geo_dialogo.moveCenter(centro_janela)
        dialog.move(geo_dialogo.topLeft())

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

    def _forcar_dialogo_arquivo_claro(self, dialog: QFileDialog):
        self._traduzir_rotulos_dialogo_arquivo(dialog)
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
        dialog = QFileDialog(self, titulo, self._diretorio_arquivo_inicial(), filtro)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        dialog.resize(1320, 820)
        dialog.setMinimumSize(1180, 740)
        if modo_salvar:
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            dialog.setFileMode(QFileDialog.FileMode.AnyFile)
            self._traduzir_rotulos_dialogo_arquivo(dialog, texto_acao="Salvar")
        else:
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            self._traduzir_rotulos_dialogo_arquivo(dialog, texto_acao="Abrir")
        self._forcar_dialogo_arquivo_claro(dialog)
        if com_preview_projeto and not modo_salvar:
            self._anexar_preview_dialogo_arquivo(dialog)
        self._centralizar_dialogo_na_janela(dialog)
        if dialog.exec() != QDialog.Accepted:
            return "", ""
        arquivos = dialog.selectedFiles()
        caminho = arquivos[0] if arquivos else ""
        if caminho:
            self._memorizar_diretorio_arquivo(Path(caminho))
        return caminho, dialog.selectedNameFilter()

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
        painel = QFrame(dialog)
        painel.setFrameShape(QFrame.StyledPanel)
        painel.setMinimumWidth(390)
        box = QVBoxLayout(painel)
        box.setContentsMargins(8, 8, 8, 8)
        box.setSpacing(6)
        lbl_titulo = QLabel("Pré-visualização", painel)
        lbl_titulo.setStyleSheet("font-weight:600;")
        lbl_img = QLabel(f"Selecione um arquivo *{EXTENSAO_PROJETO}", painel)
        lbl_img.setAlignment(Qt.AlignCenter)
        lbl_img.setMinimumSize(360, 520)
        lbl_img.setStyleSheet("background:#101010;color:#d8d8d8;border:1px solid #3a3a3a;")
        box.addWidget(lbl_titulo)
        box.addWidget(lbl_img, 1)

        row_count = max(1, layout.rowCount())
        col_count = max(1, layout.columnCount())
        layout.addWidget(painel, 0, col_count, row_count, 1)

        def _atualizar(caminho: str):
            pix = self._carregar_preview_do_projeto(Path(caminho)) if caminho else None
            if pix is None:
                lbl_img.setText("Sem prévia")
                lbl_img.setPixmap(QPixmap())
                return
            lbl_img.setText("")
            lbl_img.setPixmap(pix.scaled(lbl_img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

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

    def _importar_por_tipo(self, tipo: str):
        filtros = {
            "audaces": "Audaces (*.emf *.xml *.adsx)",
            "adsx": "Audaces ADSX (*.adsx)",
            "audaces_emf": "Metafile EMF (*.emf)",
            "audaces_xml": "Arquivo de dados XML (*.xml)",
            "dxf": "Arquivo DXF (*.dxf)",
            "aama_astm": "Arquivo AAMA/ASTM (*.dxf *.aama *.astm *.rul *.zip)",
            "plotagem": "Arquivo de plotagem (*.plt *.hpgl *.hpgl2 *.hpg *.txt)",
        }
        if tipo == "audaces":
            caminho, _ = self._abrir_dialogo_arquivo_claro("Importar Audaces", filtros["audaces"])
            if not caminho:
                return
            p = Path(caminho)
            ext = p.suffix.lower()
            if ext == ".adsx":
                return self._importar_por_tipo("adsx")
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
                emf_path, _ = self._abrir_dialogo_arquivo_claro("Deseja selecionar o arquivo EMF do Audaces?", filtros["audaces_emf"])
            if not xml_path and emf_path:
                xml_path, _ = self._abrir_dialogo_arquivo_claro("Deseja selecionar o arquivo XML de dados do Audaces?", filtros["audaces_xml"])
            if emf_path and xml_path:
                self.projeto_atual = AudacesPairImport.importar(emf_path, xml_path, self.projeto_atual)
                info = self.projeto_atual.preferencias_usuario.get("audaces_emf_xml_importacao", {})
                self._arquivo_atual = None
                self._limpar_abas_documentos()
                self._adicionar_aba_documento("Audaces", emf_path)
                area = self._area_documento_atual()
                moldes = self.projeto_atual.documentos[0].moldes if self.projeto_atual.documentos else []
                if area and moldes:
                    self._carregar_moldes_reais_no_canvas(area, moldes)
                else:
                    self._aplicar_elementos_importados_canvas(info.get("elementos_canvas", []), "Audaces", emf_path)
                self.lbl_status.setText(f"Audaces importado com sucesso: {len(moldes)} moldes criados.")
                return
            if emf_path:
                return self._importar_por_tipo("audaces_emf")
            if xml_path:
                return self._importar_por_tipo("audaces_xml")
            return

        if tipo == "audaces_emf_xml":
            emf_path, _ = self._abrir_dialogo_arquivo_claro("Importar Audaces EMF + XML (EMF)", filtros["audaces_emf"])
            if not emf_path:
                return
            pergunta = QMessageBox(self)
            self._estilizar_message_box(pergunta)
            pergunta.setWindowTitle("Importação Audaces EMF + XML")
            pergunta.setIcon(QMessageBox.Question)
            pergunta.setText("Deseja selecionar o XML correspondente do Audaces?")
            pergunta.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            self._traduzir_botoes_padrao_message_box(pergunta)
            resp = pergunta.exec()
            if resp == QMessageBox.Cancel:
                return
            if resp == QMessageBox.Yes:
                xml_path, _ = self._abrir_dialogo_arquivo_claro("Selecionar XML Audaces", filtros["audaces_xml"])
                if not xml_path:
                    return
                self.projeto_atual = AudacesPairImport.importar(emf_path, xml_path, self.projeto_atual)
                info = self.projeto_atual.preferencias_usuario.get("audaces_emf_xml_importacao", {})
                self._arquivo_atual = None
                self._limpar_abas_documentos()
                self._adicionar_aba_documento("Audaces EMF + XML", emf_path)
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
                    msg += " O EMF foi lido, mas nenhum contorno fechado confiável foi encontrado. Verifique o relatório técnico."
                self.lbl_status.setText(msg)
                caixa = QMessageBox(self)
                self._estilizar_message_box(caixa)
                caixa.setWindowTitle("Importação Audaces")
                caixa.setIcon(QMessageBox.Information)
                caixa.setText(msg)
                caixa.setStandardButtons(QMessageBox.Ok)
                self._traduzir_botoes_padrao_message_box(caixa)
                caixa.exec()
                return
            self.projeto_atual = AudacesPairImport.importar_apenas_emf(emf_path, self.projeto_atual)
            info = self.projeto_atual.preferencias_usuario.get("audaces_emf_importacao", {})
            self._aplicar_elementos_importados_canvas(info.get("elementos_canvas", []), "Audaces EMF", emf_path)
            msg = "EMF importado como vetor. Sem XML, os moldes podem ficar sem nomes e propriedades técnicas."
            self.lbl_status.setText(msg)
            return

        caminho, _ = self._abrir_dialogo_arquivo_claro(f"Importar {tipo.upper()}", filtros.get(tipo, "Todos (*.*)"))
        if not caminho:
            return

        if tipo == "adsx":
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
            self._aplicar_elementos_importados_canvas(info.get("elementos_canvas", []), "Audaces EMF", caminho)
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
            self._aplicar_elementos_importados_canvas(elementos, "Audaces XML", caminho)
            self.lbl_status.setText("XML Audaces importado como metadado técnico. Use EMF + XML para vetor editável.")
            return

        if tipo in {"dxf", "aama_astm"}:
            elementos = importar_dxf_para_elementos(caminho)
            if not elementos:
                self.lbl_status.setText("Nenhum elemento vetorial encontrado no arquivo.")
                return
            nome_doc = "DXF" if tipo == "dxf" else "AAMA/ASTM"
            self._aplicar_elementos_importados_canvas(elementos, nome_doc, caminho)
            self.lbl_status.setText(f"{nome_doc} importado com sucesso: {len(elementos)} segmentos.")
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

    def _aplicar_elementos_importados_canvas(self, elementos: list[dict], titulo_aba: str, caminho_origem: str):
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
                elementos.append({
                    "tipo": "polyline",
                    "pontos": pts,
                    "molde": True,
                    "origem": "molde_real_audaces",
                    "subtipo_audaces": "contorno",
                    "nome_molde": getattr(molde, "nome", "Molde"),
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

        dica = QLabel("Para importar moldes editáveis reais, use Audaces EMF + XML.")
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
        self._adicionar_aba_documento("ADSX importado", caminho_adsx)

        area = self._area_documento_atual()
        if not area:
            return
        canvas = area.canvas
        info = self.projeto_atual.preferencias_usuario.get("adsx_importacao", {})
        modo_adsx = self.projeto_atual.preferencias_usuario.get("adsx_modo_importacao", {})
        moldes = info.get("moldes", [])
        if not isinstance(moldes, list):
            moldes = []
        elementos_reais = info.get("elementos_canvas", [])
        confianca = str(info.get("geometry_confidence", "none")).lower().strip()
        geometria_convertida = (
            confianca == "high" and bool(info.get("geometria_convertida")) and isinstance(elementos_reais, list) and bool(elementos_reais)
        )
        diagnostico = info.get("diagnostico_file_ads", {})
        elementos: list[dict] = []
        preview_info = self.projeto_atual.audaces_adsx_original.get("arquivos_preservados", {}).get("file.jpg", {})
        preview_b64 = ""
        if isinstance(preview_info, dict):
            preview_b64 = str(preview_info.get("conteudo_base64") or "").strip()
        preview_ok = False
        mostrar_preview = bool(modo_adsx.get("mostrar_preview_jpg", True))
        if preview_b64 and mostrar_preview:
            pix = QPixmap()
            try:
                pix.loadFromData(base64.b64decode(preview_b64))
            except Exception:
                pix = QPixmap()
            if not pix.isNull():
                largura_visivel = max(canvas.width() / max(canvas.zoom, 0.001), 1.0)
                altura_visivel = max(canvas.height() / max(canvas.zoom, 0.001), 1.0)
                escala = min((largura_visivel * 0.82) / max(float(pix.width()), 1.0), (altura_visivel * 0.82) / max(float(pix.height()), 1.0))
                escala = max(0.01, min(escala, 8.0))
                elementos.append(
                    {
                        "tipo": "imagem",
                        "nome": "Preview ADSX - imagem de referência",
                        "imagem_base64": preview_b64,
                        "pos": (0.0, 0.0),
                        "escala": float(escala),
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
            trace_msg = None
            total_moldes = len([m for m in moldes if isinstance(m, dict)])
            elementos.append(
                {
                    "tipo": "texto",
                    "texto": (
                        "Arquivo ADSX reconhecido.\n"
                        f"Moldes detectados no XML: {total_moldes}.\n"
                        f"Preview visual: {'disponível' if preview_ok else 'não encontrado'}.\n"
                        "Binário file.ads preservado.\n"
                        "Conversão geométrica ainda pendente."
                    ),
                    "pos": (10.0, -18.0 if preview_ok else 10.0),
                    "cor": "#111111",
                    "tamanho": 1.0,
                }
            )
            elementos.append(
                {
                    "tipo": "texto",
                    "texto": f"Diagnóstico file.ads: {diagnostico.get('motivo', 'sem detalhes')} (confiança: {confianca})",
                    "pos": (10.0, -8.0 if preview_ok else 20.0),
                    "cor": "#444444",
                    "tamanho": 0.9,
                }
            )
            for i, molde in enumerate(moldes, start=1):
                if not isinstance(molde, dict):
                    continue
                nome = str(molde.get("nome") or f"Molde {i}")
                tamanho = str(molde.get("tamanho") or "")
                quantidade = molde.get("quantidade")
                linha = f"- {nome}"
                if tamanho:
                    linha += f" — tamanho {tamanho}"
                if quantidade is not None:
                    linha += f" — quantidade {quantidade}"
                elementos.append(
                    {
                        "tipo": "texto",
                        "texto": linha,
                        "pos": (10.0, (i * 3.0) + (4.0 if preview_ok else 24.0)),
                        "cor": "#333333",
                        "tamanho": 0.85,
                    }
                )
            if preview_ok:
                elementos.append(
                    {
                        "tipo": "texto",
                        "texto": "Pré-visualização ADSX. Não é molde editável.",
                        "pos": (10.0, -28.0),
                        "cor": "#ffb703",
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

    def _centralizar_canvas_em_elementos(self, canvas, elementos: list[dict]):
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
        canvas.set_zoom(max(0.05, min(novo_zoom, 8.0)))

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
        if not pontos:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    def _transladar_elemento(self, el: dict, dx: float, dy: float):
        tipo = el.get("tipo")
        if tipo == "polyline":
            el["pontos"] = [(float(x) + dx, float(y) + dy) for x, y in el.get("pontos", [])]
            return
        if tipo == "bezier_quadratica":
            for chave in ("p0", "p1", "p2"):
                pt = el.get(chave)
                if isinstance(pt, (tuple, list)) and len(pt) == 2:
                    el[chave] = (float(pt[0]) + dx, float(pt[1]) + dy)
            return
        if tipo in {"circle", "esfera"}:
            centro = el.get("centro")
            if isinstance(centro, (tuple, list)) and len(centro) == 2:
                el["centro"] = (float(centro[0]) + dx, float(centro[1]) + dy)

    def _organizar_moldes_no_canvas(self, canvas, variacao: int | None = None, registrar_historico: bool = True) -> int:
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

        for info, (target_x, target_y) in zip(moldes, centros):
            dx = target_x - info["cx"]
            dy = target_y - info["cy"]
            self._transladar_elemento(canvas.cena.elementos[info["idx"]], dx, dy)
        if registrar_historico:
            canvas._registrar_historico()
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
            self.ARQUIVO_RECUPERACAO.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _limpar_arquivo_recuperacao(self):
        try:
            if self.ARQUIVO_RECUPERACAO.exists():
                self.ARQUIVO_RECUPERACAO.unlink()
        except Exception:
            pass

    def _oferecer_recuperacao_pos_falha(self):
        if not self.ARQUIVO_RECUPERACAO.exists():
            return
        try:
            bruto = json.loads(self.ARQUIVO_RECUPERACAO.read_text(encoding="utf-8"))
        except Exception:
            return
        docs = bruto.get("documentos", [])
        if not isinstance(docs, list) or not docs:
            return
        caixa = QMessageBox(self)
        self._estilizar_message_box(caixa)
        caixa.setWindowTitle("Atenção")
        caixa.setIcon(QMessageBox.Question)
        caixa.setText("Deseja recuperar arquivo(s) perdido(s)?")
        caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        self._traduzir_botoes_padrao_message_box(caixa)
        QTimer.singleShot(0, lambda: self._centralizar_widget_na_tela(caixa))
        if caixa.exec() != QMessageBox.Yes:
            self._limpar_arquivo_recuperacao()
            return
        self._limpar_abas_documentos()
        for doc in docs:
            nome = str(doc.get("nome") or "(Recuperado)")
            self._adicionar_aba_documento(nome=nome)
            area = self._area_documento_atual()
            if not area:
                continue
            area.canvas.cena.elementos = [dict(el) for el in doc.get("elementos", [])]
            if "painel_coordenadas_visivel" in doc:
                area.canvas.definir_painel_coordenadas_visivel(bool(doc.get("painel_coordenadas_visivel")))
            self._restaurar_viewport_documento_canvas(area, doc)
            self._marcar_area_como_salva(area)
            area.canvas.update()
        self._ativar_ferramenta_global("selecionar")
        self.lbl_status.setText("Recuperação concluída.")

    def _abrir_projeto(self):
        self.backstage.hide()
        caminho, _ = self._abrir_dialogo_arquivo_claro(
            "Abrir",
            f"Projeto GUIMMA (*{EXTENSAO_PROJETO});;Todos (*.*)",
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
            if "painel_coordenadas_visivel" in doc:
                area.canvas.definir_painel_coordenadas_visivel(bool(doc.get("painel_coordenadas_visivel")))
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

    def _atualizar_titulo(self):
        self.setWindowTitle("GUIMMA STUDIO")

    def _criar_area_documento(self) -> QWidget:
        area = QWidget()
        area.setStyleSheet("background: #eceff3;")
        layout = QVBoxLayout(area)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        self.host_barra_usuario_area = QWidget()
        self.host_barra_usuario_area_layout = QVBoxLayout(self.host_barra_usuario_area)
        self.host_barra_usuario_area_layout.setContentsMargins(0, 0, 0, 0)
        self.host_barra_usuario_area_layout.setSpacing(0)
        layout.addWidget(self.host_barra_usuario_area)
        self._criar_linha_usuarios()
        self.abas_documentos = QTabWidget()
        self.abas_documentos.setTabsClosable(False)
        self.abas_documentos.setMovable(True)
        self.abas_documentos.tabBar().setExpanding(False)
        self.abas_documentos.tabBar().setUsesScrollButtons(True)
        self.abas_documentos.currentChanged.connect(self._on_aba_documento_alterada)
        self.abas_documentos.tabBar().tabMoved.connect(lambda _from, _to: self._reconfigurar_botoes_fechar_abas())
        self.abas_documentos.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #d7dbe1; }"
            "QTabWidget::tab-bar { alignment: left; }"
            "QTabBar { background: #f9f9f9; }"
            "QTabBar::tab { background:#ffffff; border:1px solid #d7dbe1; padding:2px 20px 2px 9px; margin-right:1px; min-height:18px; }"
            "QTabBar::tab:selected { background:#ffffff; border-bottom:2px solid #0b8dd1; }"
        )
        layout.addWidget(self.abas_documentos, 1)
        self._reposicionar_barra_usuarios()
        self._atualizar_linha_usuarios()
        self._on_tab_ribbon_alterada(self.ribbon.current_tab_id() or "inicio")
        return area

    def _criar_linha_usuarios(self):
        if hasattr(self, "faixa_usuarios"):
            return
        faixa = QFrame()
        faixa.setFixedHeight(42)
        faixa.setStyleSheet("QFrame { background:#f5f9fe; border:1px solid #c9dbef; }")
        lay = QHBoxLayout(faixa)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(6)

        self.btn_usuario_add_all = QPushButton("Adicionar todas da aba")
        self.btn_usuario_add_all.setCursor(Qt.PointingHandCursor)
        self.btn_usuario_add_all.setFixedHeight(26)
        self.btn_usuario_add_all.clicked.connect(self._adicionar_todas_ferramentas_da_aba)
        self.btn_usuario_add_all.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                color: #111111;
                font-weight: 400;
                font-size: 12px;
                padding: 0 8px;
            }
            QPushButton:hover { background: rgba(20, 120, 200, 0.10); }
            QPushButton:pressed { background: rgba(20, 120, 200, 0.16); }
            QPushButton:disabled { color: #555555; background: transparent; }
            """
        )

        self.btn_usuario_limpar = QPushButton("Limpar linha")
        self.btn_usuario_limpar.setCursor(Qt.PointingHandCursor)
        self.btn_usuario_limpar.setFixedHeight(26)
        self.btn_usuario_limpar.clicked.connect(self._limpar_ferramentas_usuario)
        self.btn_usuario_limpar.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                color: #111111;
                font-weight: 400;
                font-size: 12px;
                padding: 0 8px;
            }
            QPushButton:hover { background: rgba(20, 120, 200, 0.10); }
            QPushButton:pressed { background: rgba(20, 120, 200, 0.16); }
            QPushButton:disabled { color: #555555; background: transparent; }
            """
        )

        self.linha_usuario = QWidget()
        self.layout_linha_usuario = QHBoxLayout(self.linha_usuario)
        self.layout_linha_usuario.setContentsMargins(4, 0, 4, 0)
        self.layout_linha_usuario.setSpacing(3)
        lay.addWidget(self.linha_usuario, 1)

        self.painel_controles_usuario = QWidget()
        controles_layout = QHBoxLayout(self.painel_controles_usuario)
        controles_layout.setContentsMargins(0, 0, 0, 0)
        controles_layout.setSpacing(4)

        lbl_usuario = QLabel("Usuário:")
        lbl_usuario.setStyleSheet("color:#111111; font-size:12px; font-weight:400;")
        controles_layout.addWidget(lbl_usuario, 0)

        self.combo_perfil_usuario = QComboBox()
        self.combo_perfil_usuario.setMinimumWidth(130)
        self.combo_perfil_usuario.setStyleSheet(
            """
            QComboBox {
                color:#111111;
                background:#ffffff;
                border:1px solid #b7b7b7;
                padding: 2px 8px;
                font-weight: 400;
            }
            QComboBox QAbstractItemView {
                color:#111111;
                background:#ffffff;
                selection-background-color:#e9f3ff;
                selection-color:#111111;
            }
            """
        )
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
        self._barra_usuarios_habilitada = True
        self.projeto_atual.preferencias_usuario["barra_usuarios_habilitada"] = True
        self._atualizar_visibilidade_barra_usuarios(self.ribbon.current_tab_id() or "inicio")
        self._salvar_preferencias_app()

    def _definir_posicao_barra_usuarios(self, posicao: str):
        if posicao not in {"topo", "area"}:
            return
        self._barra_usuarios_posicao = posicao
        self.projeto_atual.preferencias_usuario["barra_usuarios_posicao"] = posicao
        self._reposicionar_barra_usuarios()
        self._atualizar_visibilidade_barra_usuarios(self.ribbon.current_tab_id() or "inicio")
        self._salvar_preferencias_app()

    def _reposicionar_barra_usuarios(self):
        if not hasattr(self, "faixa_usuarios"):
            return
        if self.faixa_usuarios.parentWidget() is not None:
            self.faixa_usuarios.setParent(None)
        if self._barra_usuarios_posicao == "topo":
            self.host_barra_usuario_topo_layout.addWidget(self.faixa_usuarios)
        else:
            self.host_barra_usuario_area_layout.addWidget(self.faixa_usuarios)

    def _atualizar_visibilidade_barra_usuarios(self, tab_id: str):
        if hasattr(self, "faixa_usuarios"):
            visivel = self._barra_usuarios_habilitada or (tab_id == "usuarios")
            self.faixa_usuarios.setVisible(visivel)

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
        self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = []
        self._sincronizar_perfil_usuario_atual()
        self._atualizar_linha_usuarios()
        self.lbl_status.setText("Linha Usuários limpa.")

    def _remover_ferramenta_usuario(self, tool_id: str):
        if tool_id in self._ferramentas_usuario_ids:
            self._ferramentas_usuario_ids.remove(tool_id)
            self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(self._ferramentas_usuario_ids)
            self._sincronizar_perfil_usuario_atual()
            self._atualizar_linha_usuarios()

    def _inicializar_perfis_usuarios(self):
        perfis = self.projeto_atual.preferencias_usuario.get("perfis_usuarios")
        if isinstance(perfis, dict) and perfis:
            self._perfis_usuarios = {str(nome): list(ids) for nome, ids in perfis.items()}
        else:
            self._perfis_usuarios = {"Usuário 1": list(self._ferramentas_usuario_ids)}
        perfil_atual = self.projeto_atual.preferencias_usuario.get("perfil_usuario_atual")
        if isinstance(perfil_atual, str) and perfil_atual in self._perfis_usuarios:
            self._perfil_usuario_atual = perfil_atual
        else:
            self._perfil_usuario_atual = next(iter(self._perfis_usuarios.keys()))
        self._ferramentas_usuario_ids = list(self._perfis_usuarios.get(self._perfil_usuario_atual, []))
        cfgs = self.projeto_atual.preferencias_usuario.get("perfis_usuarios_cfg")
        if isinstance(cfgs, dict):
            self._perfis_usuarios_cfg = {str(nome): dict(cfg or {}) for nome, cfg in cfgs.items()}
        else:
            self._perfis_usuarios_cfg = {}
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
        self._ferramentas_usuario_ids = list(self._perfis_usuarios.get(nome_perfil, []))
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
        self.lbl_status.setText(f"Perfil '{nome}' criado.")

    def _salvar_perfil_usuario_atual(self):
        self._sincronizar_perfil_usuario_atual()
        self.lbl_status.setText(f"Perfil '{self._perfil_usuario_atual}' salvo.")

    def _atualizar_linha_usuarios(self):
        if not hasattr(self, "layout_linha_usuario"):
            return
        while self.layout_linha_usuario.count():
            item = self.layout_linha_usuario.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not self._ferramentas_usuario_ids:
            vazio = QLabel("Sem ferramentas ainda. Clique com o botão direito em qualquer ferramenta e selecione 'Adicionar à linha Usuários'.")
            vazio.setStyleSheet("color:#111111; font-size:11px; font-weight:400;")
            self.layout_linha_usuario.addWidget(vazio)
            self.layout_linha_usuario.addStretch(1)
            return
        for tool_id in self._ferramentas_usuario_ids:
            tool = self.ribbon.tool_def(tool_id)
            if not tool:
                continue
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setIcon(QIcon(str(ICONS_DIR / tool.icon)))
            btn.setIconSize(QSize(28, 28))
            btn.setFixedSize(30, 30)
            btn.setToolTip(tool.title)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                """
                QToolButton {
                    border: none;
                    background: transparent;
                    padding: 0px;
                    margin: 0px;
                }
                QToolButton:hover {
                    border: none;
                    background: rgba(20, 120, 200, 0.10);
                }
                QToolButton:pressed {
                    border: none;
                    background: rgba(20, 120, 200, 0.16);
                }
                """
            )
            btn.clicked.connect(lambda _=False, tid=tool_id: self._abrir_pagina_ferramenta(tid))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, tid=tool_id: self._remover_ferramenta_usuario(tid)
            )
            self.layout_linha_usuario.addWidget(btn)
        self.layout_linha_usuario.addStretch(1)

    def _adicionar_aba_documento(self, nome: str | None = None, caminho_origem: str | None = None):
        if nome is None:
            self._contador_sem_nome += 1
            nome = "(Sem nome)" if self._contador_sem_nome == 1 else f"(Sem nome) -{self._contador_sem_nome}"
        area_doc = AreaDocumentoWidget(CenaDocumento())
        area_doc.zoom_changed.connect(self._on_zoom_canvas_alterado)
        area_doc.canvas.ferramenta_padrao_solicitada.connect(self._ativar_ferramenta_global)
        area_doc.canvas.snap_changed.connect(self._on_snap_changed)
        area_doc.canvas.painel_coordenadas_changed.connect(self._on_painel_coordenadas_changed)
        area_doc.canvas.painel_posicao_changed.connect(self._on_painel_posicao_canvas)
        area_doc.canvas.set_ferramenta_ativa(self._ferramenta_ativa_id)
        area_doc.canvas.set_snap_ativo(self.btn_snap.isChecked())
        area_doc.canvas.set_estilo_linha(**self._estilo_desenho_atual)
        area_doc.canvas.set_passo_snap_angular(self._passo_snap_angular_atual)
        area_doc.canvas.set_snap_contextual_ativo(self._snap_contextual_ativo)
        area_doc.canvas._cores_tecidos = dict(self._cores_tecidos_global)
        area_doc.canvas._mostrar_cor_tecidos = bool(self._mostrar_cor_tecidos_global)
        area_doc.canvas.set_painel_auxiliar_posicao(self._painel_coordenadas_pos_global)
        area_doc.aplicar_config_unidade(self._unidade_medida, self._passo_unidade_medida)
        area_doc.canvas.set_unidade_quadrado(self._unidade_area, self._fator_unidade_sigla(self._unidade_area))
        area_doc.canvas.set_precisao_medida(self._precisao_medida)
        area_doc.unidade_menu_solicitado.connect(self._abrir_menu_unidade_medida_em)
        self._marcar_area_como_salva(area_doc)
        area_doc.setProperty("arquivo_origem", caminho_origem)
        index = self.abas_documentos.addTab(area_doc, nome)
        self._configurar_botao_fechar_aba(index)
        self.abas_documentos.setCurrentIndex(index)
        QTimer.singleShot(0, lambda a=area_doc: self._aplicar_viewport_inicial(a))

    def _limpar_abas_documentos(self):
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
        widget = self.abas_documentos.widget(index)
        self.abas_documentos.removeTab(index)
        if widget:
            widget.deleteLater()
        self._reconfigurar_botoes_fechar_abas()
        self._on_aba_documento_alterada(self.abas_documentos.currentIndex())

    def _on_zoom_canvas_alterado(self, zoom: float):
        area_atual = self._area_documento_atual()
        if area_atual and self.sender() is area_atual:
            self.lbl_escala.setText(self._texto_escala(zoom))
            self._agendar_salvar_estado_silencioso()

    def _on_aba_documento_alterada(self, index: int):
        area = self.abas_documentos.widget(index) if index >= 0 else None
        if isinstance(area, AreaDocumentoWidget):
            self.lbl_escala.setText(self._texto_escala(area.canvas.zoom))
            self.btn_snap.blockSignals(True)
            self.btn_snap.setChecked(area.canvas.snap_ativo())
            self.btn_snap.blockSignals(False)
            self.action_coordenadas.blockSignals(True)
            self.action_coordenadas.setChecked(area.canvas.painel_coordenadas_visivel())
            self.action_coordenadas.blockSignals(False)
            QTimer.singleShot(0, area.canvas.sincronizar_paineis_auxiliares)
        else:
            self.lbl_escala.setText("Escala --")

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
        botao.setFixedSize(18, 18)
        botao.setToolTip("Fechar aba")
        botao.setStyleSheet(
            "QPushButton { border:none; padding:0; font-size:14px; color:#c62828; font-weight:700; }"
            "QPushButton:hover { background:#ffe9e9; border-radius:9px; color:#9a0000; }"
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
            if self._clipboard_elementos_global and hasattr(area.canvas, "definir_buffer_copia"):
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
            area_doc.zoom_changed.connect(self._on_zoom_canvas_alterado)
            area_doc.canvas.ferramenta_padrao_solicitada.connect(self._ativar_ferramenta_global)
            area_doc.canvas.snap_changed.connect(self._on_snap_changed)
            area_doc.canvas.painel_coordenadas_changed.connect(self._on_painel_coordenadas_changed)
            area_doc.canvas.painel_posicao_changed.connect(self._on_painel_posicao_canvas)
            area_doc.canvas.set_ferramenta_ativa(self._ferramenta_ativa_id)
            area_doc.canvas.set_snap_ativo(self.btn_snap.isChecked())
            area_doc.canvas.set_estilo_linha(**self._estilo_desenho_atual)
            area_doc.canvas.set_passo_snap_angular(self._passo_snap_angular_atual)
            area_doc.canvas.set_snap_contextual_ativo(self._snap_contextual_ativo)
            area_doc.canvas._cores_tecidos = dict(self._cores_tecidos_global)
            area_doc.canvas._mostrar_cor_tecidos = bool(self._mostrar_cor_tecidos_global)
            area_doc.canvas.set_painel_auxiliar_posicao(self._painel_coordenadas_pos_global)
            area_doc.aplicar_config_unidade(self._unidade_medida, self._passo_unidade_medida)
            area_doc.canvas.set_unidade_quadrado(self._unidade_area, self._fator_unidade_sigla(self._unidade_area))
            area_doc.canvas.set_precisao_medida(self._precisao_medida)
            area_doc.unidade_menu_solicitado.connect(self._abrir_menu_unidade_medida_em)
            if "painel_coordenadas_visivel" in doc:
                area_doc.canvas.definir_painel_coordenadas_visivel(bool(doc.get("painel_coordenadas_visivel")))
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
            self._cores_tecidos_global = dict(mapa_cores)
            self.projeto_atual.preferencias_usuario["cores_tecidos_global"] = dict(self._cores_tecidos_global)
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if not isinstance(area, AreaDocumentoWidget):
                continue
            area.canvas._mostrar_cor_tecidos = bool(self._mostrar_cor_tecidos_global)
            area.canvas._cores_tecidos = dict(self._cores_tecidos_global)
            area.canvas.update()
        self._salvar_preferencias_app()

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
        self._ferramenta_ativa_id = tool_id
        self.projeto_atual.preferencias_usuario["ferramenta_ativa_id"] = tool_id
        self._salvar_preferencias_app()
        self.ribbon.set_active_tool(tool_id)
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
        self.projeto_atual.preferencias_usuario["estilo_desenho"] = dict(self._estilo_desenho_atual)
        self._sincronizar_perfil_usuario_atual()
        area_atual = self._area_documento_atual()
        if area_atual:
            area_atual.canvas.set_estilo_linha(**self._estilo_desenho_atual)
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
        area = self._area_documento_atual()
        if not area:
            self.lbl_status.setText("Snap ativo" if ativo else "Snap desativado")
            return
        area.canvas.set_snap_ativo(ativo)

    def _on_snap_changed(self, ativo: bool):
        self._snap_ativo_global = bool(ativo)
        self.projeto_atual.preferencias_usuario["snap_ativo"] = self._snap_ativo_global
        self._salvar_preferencias_app()
        self.lbl_status.setText("Snap ativo" if ativo else "Snap desativado")

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
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
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

    def _marcar_documentos_como_salvos(self):
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                self._marcar_area_como_salva(area)

    def _salvar_estado_projeto_silenciosamente(self):
        if self._arquivo_atual is None:
            return
        if not self._ha_alteracoes_estado_nao_salvas():
            return
        try:
            self._sincronizar_documentos_canvas_no_projeto()
            GSProjectIO.salvar(self.projeto_atual, self._arquivo_atual)
            self._marcar_documentos_como_salvos()
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
        atalhos.setFixedHeight(24)
        atalhos.setStyleSheet("background:#f4f6f8; border-top:1px solid #c8d1da; border-bottom:1px solid #dce2e8;")
        row = QHBoxLayout(atalhos)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(4)

        estilo_botao_icone = (
            "QPushButton { color:#1f1f1f; background:transparent; border:none; padding:1px 6px; min-width:22px; }"
            "QPushButton:hover { background:#d9edf9; border:none; }"
            "QPushButton:checked { background:#c5e4f6; border:none; color:#0a4f82; font-weight:700; }"
        )

        self.btn_snap = _BotaoRodapeHover("🧲", "Ativa ou desativa o snap")
        self.btn_snap.setCheckable(True)
        self.btn_snap.setChecked(self._snap_ativo_global)
        self.btn_snap.setCursor(Qt.PointingHandCursor)
        self.btn_snap.setToolTip("Ativar/Desativar snap (ímã)")
        icone_snap = ICONS_DIR / "snap.svg"
        if icone_snap.exists():
            self.btn_snap.setIcon(QIcon(str(icone_snap)))
            self.btn_snap.setText("")
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
        self.btn_aumenta_indicado.clicked.connect(self._centralizar_molde_ou_elemento_indicado)
        row.addWidget(self.btn_aumenta_indicado)

        self.btn_desfazer_visao = _BotaoRodapeHover("⟲", "Desfaz o último comando de visualização")
        self.btn_desfazer_visao.setFixedHeight(20)
        self.btn_desfazer_visao.setStyleSheet(estilo_botao_icone)
        self.btn_desfazer_visao.clicked.connect(lambda: self.lbl_status.setText("Desfaz o último comando de visualização"))
        row.addWidget(self.btn_desfazer_visao)

        self.btn_grid = _BotaoRodapeHover("⋮⋮", "Habilita ou desabilita o grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.setFixedHeight(20)
        self.btn_grid.setStyleSheet(estilo_botao_icone)
        self.btn_grid.clicked.connect(lambda: self.lbl_status.setText("Habilita ou desabilita o grid"))
        row.addWidget(self.btn_grid)

        self.btn_graduacao = _BotaoRodapeHover("⇅", "Mostra ou esconde graduação")
        self.btn_graduacao.setCheckable(True)
        self.btn_graduacao.setChecked(True)
        self.btn_graduacao.setFixedHeight(20)
        self.btn_graduacao.setStyleSheet(estilo_botao_icone)
        self.btn_graduacao.clicked.connect(lambda: self.lbl_status.setText("Mostra ou esconde graduação"))
        row.addWidget(self.btn_graduacao)

        self.btn_organizar_moldes = _BotaoRodapeHover("⇵", "Organiza todos os moldes")
        self.btn_organizar_moldes.setFixedHeight(20)
        self.btn_organizar_moldes.setToolTip("Reorganiza todos os moldes com variações de layout")
        self.btn_organizar_moldes.setStyleSheet(estilo_botao_icone)
        self.btn_organizar_moldes.clicked.connect(self._organizar_moldes_canvas_atual)
        row.addWidget(self.btn_organizar_moldes)

        row.addStretch(1)
        layout.addWidget(atalhos)

        barra = QFrame()
        barra.setFixedHeight(22)
        barra.setStyleSheet("background: #0b88b6; border-top: 1px solid #0a7aa2; color: white;")
        l = QHBoxLayout(barra)
        l.setContentsMargins(10, 0, 10, 0)
        self.lbl_status = QLabel("Pronto")
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
            self.btn_organizar_moldes,
        ):
            if isinstance(b, _BotaoRodapeHover):
                b.vincular_status(self.lbl_status)
        l.addStretch(1)
        self.lbl_escala = QLabel("Escala 100%")
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

    def _centralizar_molde_ou_elemento_indicado(self):
        area = self._area_documento_atual()
        if not area:
            return
        canvas = area.canvas
        selecionados = sorted(getattr(canvas, "_selecionados", set()))
        alvo = None
        if selecionados:
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
        imagem = self._gerar_thumbnail_elementos(elementos, largura=320, altura=180)
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
        pontos: list[tuple[float, float]] = []
        for el in elementos:
            if el.get("tipo") == "polyline":
                pontos.extend([(float(x), float(y)) for x, y in el.get("pontos", [])])
        if len(pontos) < 2:
            return None
        xs = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura_geo = max(max_x - min_x, 1.0)
        altura_geo = max(max_y - min_y, 1.0)

        margem = 12
        escala = min((largura - margem * 2) / largura_geo, (altura - margem * 2) / altura_geo)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0

        img = QImage(largura, altura, QImage.Format_ARGB32)
        img.fill(QColor("#000000"))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#ff5a00"), 2))
        for el in elementos:
            if el.get("tipo") != "polyline":
                continue
            pts = el.get("pontos", [])
            if len(pts) < 2:
                continue
            pontos_norm = [(float(x), float(y)) for x, y in pts]
            for (x1, y1), (x2, y2) in zip(pontos_norm, pontos_norm[1:]):
                sx1 = (x1 - cx) * escala + (largura / 2)
                sy1 = (y1 - cy) * escala + (altura / 2)
                sx2 = (x2 - cx) * escala + (largura / 2)
                sy2 = (y2 - cy) * escala + (altura / 2)
                painter.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))
        painter.end()
        return img
