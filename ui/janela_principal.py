from __future__ import annotations

import json
from datetime import datetime
from importlib import import_module
from math import ceil, cos, pi, sin, sqrt
from pathlib import Path
from time import time
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QByteArray, QBuffer, QEvent, QIODevice, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSlider,
)

from canvas.cena import CenaDocumento
from canvas.workspace import AreaDocumentoWidget
from config import EXTENSAO_PROJETO, ICONS_DIR
from core.projeto import Projeto
from formats.gs_project import GSProjectIO
from formats.dxf_import import importar_dxf_para_elementos
from ui.backstage_arquivo import BackstageArquivoPanel
from ui.ribbon import RibbonWidget
from ui.salvar_como_dialog import SalvarComoDialog
from tools.propriedades_tool import ConfigurarCoresTecidosDialog


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
        self._ferramenta_ativa_id = str(self.projeto_atual.preferencias_usuario.get("ferramenta_ativa_id", "selecionar"))
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
        self._chk_aux_retangulo_criar_molde: QCheckBox | None = None
        self._retangulo_criar_molde = bool(self.projeto_atual.preferencias_usuario.get("retangulo_criar_molde", True))
        self._posicoes_caixas_aux: dict[str, tuple[int, int]] = self._carregar_posicoes_caixas_aux()
        self._painel_coordenadas_pos_global: tuple[int, int] | None = None
        self._ferramentas_usuario_ids: list[str] = list(self.projeto_atual.preferencias_usuario.get("ferramentas_usuario", []))
        self._ultima_aba_nao_usuario = "construcao"
        self._barra_usuarios_posicao = self.projeto_atual.preferencias_usuario.get("barra_usuarios_posicao", "area")
        self._barra_usuarios_habilitada = bool(self.projeto_atual.preferencias_usuario.get("barra_usuarios_habilitada", False))
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
        self.setWindowTitle("GUIMMA STUDIO")
        self._configurar_interface()
        self.ribbon.aplicar_estilo(self._estilo_desenho_atual)
        self._limpar_abas_documentos()
        self._configurar_atalhos()
        QApplication.instance().installEventFilter(self)
        self._oferecer_recuperacao_pos_falha()
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
        self._barra_usuarios_habilitada = bool(cfg.get("barra_usuarios_habilitada", self._barra_usuarios_habilitada))
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
        self.action_barra_usuarios_habilitada.setChecked(self._barra_usuarios_habilitada)
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
        self.backstage.botoes["Novo"].clicked.connect(self._novo_projeto)
        self.backstage.botoes["Abrir"].clicked.connect(self._abrir_projeto)
        self.backstage.botoes["Salvar"].clicked.connect(self._acao_salvar_pelo_backstage)
        self.backstage.botoes["Salvar como"].clicked.connect(self._salvar_projeto_como)
        self.backstage.botoes["Importar ▸"].clicked.connect(self._abrir_menu_importar)
        self.backstage.botoes["Configurações ▸"].clicked.connect(self._abrir_menu_configuracoes)
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

    def mousePressEvent(self, event):  # noqa: N802
        super().mousePressEvent(event)
        if self.backstage.isVisible() and event.position().x() > self.backstage.width():
            self.backstage.hide()

    def eventFilter(self, watched, event):  # noqa: N802
        if (
            hasattr(self, "backstage")
            and self.backstage.isVisible()
            and event.type() == QEvent.MouseButtonPress
            and hasattr(event, "globalPosition")
        ):
            pos = event.globalPosition().toPoint()
            backstage_topo = self.backstage.mapToGlobal(QPoint(0, 0))
            backstage_rect = self.backstage.rect().translated(backstage_topo)
            botao_topo = self.botao_arquivo.mapToGlobal(QPoint(0, 0))
            botao_rect = self.botao_arquivo.rect().translated(botao_topo)
            if not backstage_rect.contains(pos) and not botao_rect.contains(pos):
                self.backstage.hide()
        return super().eventFilter(watched, event)

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
                QMessageBox.critical(self, "Erro ao abrir ferramenta", f"{type(exc).__name__}: {exc}")
            except Exception as exc2:
                self._log_debug_propriedades(f"Falha ao mostrar QMessageBox: {type(exc2).__name__}: {exc2}")

    def _executar_acao_edicao_ribbon(self, tool_id: str) -> bool:
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
        if not acao:
            return False
        func, mensagem = acao
        func()
        self.lbl_status.setText(mensagem)
        return True

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
        janela = QDialog(self)
        janela.setWindowTitle(f"{titulo} - Auxiliar")
        janela.setModal(True)
        janela.setMinimumWidth(380)
        janela.setStyleSheet(
            "QDialog { background:#e6e6e6; border:1px solid #9da3aa; } QLabel { color:#2b2b2b; }"
            "QPushButton { background:#d7d7d7; border:1px solid #9da3aa; padding:4px 10px; color:#1f1f1f; }"
            "QPushButton:disabled { color:#5f5f5f; background:#d8d8d8; border:1px solid #b3b3b3; }"
        )
        layout = QVBoxLayout(janela)
        texto_titulo, texto_instrucao = instrucoes[tool_id]
        lbl_titulo = QLabel(f"<b>{texto_titulo}</b>")
        lbl_titulo.setStyleSheet("font-size: 13px;")
        layout.addWidget(lbl_titulo)
        lbl_instrucao = QLabel(texto_instrucao)
        lbl_instrucao.setWordWrap(True)
        lbl_instrucao.setStyleSheet("font-size: 12px; color:#2b2b2b;")
        layout.addWidget(lbl_instrucao)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText("Ativar ferramenta")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        layout.addWidget(botoes)
        botoes.accepted.connect(janela.accept)
        botoes.rejected.connect(janela.reject)
        self._restaurar_posicao_caixa_aux(janela, tool_id)
        if janela.exec() != QDialog.Accepted:
            self._memorizar_posicao_caixa_aux(janela, tool_id)
            self.lbl_status.setText(f"{titulo} cancelado.")
            return True
        self._memorizar_posicao_caixa_aux(janela, tool_id)
        self._ativar_ferramenta_global(tool_id)
        self.lbl_status.setText(f"{titulo} ativo. Siga os passos da janela auxiliar.")
        return True

    def _abrir_janela_auxiliar_retangulo(self, titulo: str) -> bool:
        area = self._area_documento_atual()
        if not area:
            return False
        if self._janela_aux_retangulo is None:
            janela = QDialog(self)
            janela.setWindowTitle("Definir retângulos")
            janela.setModal(False)
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
            rb_2p = QRadioButton("Curva por 2 pontos")
            rb_3p = QRadioButton("Curva por 3 pontos")
            rb_np = QRadioButton("Pontos indefinidos")
            rb_2p.setChecked(True)
            layout.addWidget(rb_2p)
            layout.addWidget(rb_3p)
            layout.addWidget(rb_np)
            rb_2p.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("2p") if marcado else None)
            rb_3p.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("3p") if marcado else None)
            rb_np.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("np") if marcado else None)
            self._janela_aux_curva = janela
        else:
            janela = self._janela_aux_curva
            janela.setWindowTitle(titulo)
        self._restaurar_posicao_caixa_aux(janela, "curva")
        area.canvas.set_modo_curva("2p")
        self._ativar_ferramenta_global("curva")
        janela.show()
        janela.raise_()
        janela.activateWindow()
        self.lbl_status.setText(f"{titulo} ativo (2 pontos).")
        return True

    def _definir_modo_curva_area_atual(self, modo: str):
        area = self._area_documento_atual()
        if area:
            area.canvas.set_modo_curva(modo)
        if hasattr(self, "lbl_status") and self.lbl_status is not None:
            if modo == "np":
                self.lbl_status.setText("Curva ativa (pontos indefinidos).")
            elif modo == "3p":
                self.lbl_status.setText("Curva ativa (3 pontos).")
            else:
                self.lbl_status.setText("Curva ativa (2 pontos).")

    def _restaurar_posicao_caixa_aux(self, janela: QDialog, chave: str):
        area = self._area_documento_atual()
        if not area:
            return
        canvas = area.canvas
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

    def _abrir_menu_importar(self):
        botao = self.backstage.botoes.get("Importar ▸")
        if not botao:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#ffffff; color:#111111; border:1px solid #cfd6de; }"
            "QMenu::item:selected { background:#e9f3ff; color:#0b4f82; }"
        )
        menu.addAction("Arquivo DXF", lambda: self._importar_por_tipo("dxf"))
        menu.addAction("Arquivo AAMA/ASTM", lambda: self._importar_por_tipo("aama"))
        menu.addAction("Arquivo de Plotagem", lambda: self._importar_por_tipo("plot"))
        menu.addAction("Lectra", lambda: self._importar_por_tipo("lectra"))
        menu.addAction("Investronica", lambda: self._importar_por_tipo("investronica"))
        menu.addAction("Gerber", lambda: self._importar_por_tipo("gerber"))
        menu.addAction("Assyst", lambda: self._importar_por_tipo("assyst"))
        pos = botao.mapToGlobal(botao.rect().bottomRight())
        menu.exec(pos)

    def _abrir_menu_configuracoes(self):
        botao = self.backstage.botoes.get("Configurações ▸")
        if botao is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #ffffff; border: 1px solid #c8d0d8; }"
            "QMenu::item { padding: 6px 18px; }"
            "QMenu::item:selected { background: #e6f2ff; }"
        )
        menu.addAction("Opções", self._abrir_dialogo_opcoes)
        menu.addAction("Unidade de medida\tCtrl+U", self._abrir_dialogo_unidade_medida)
        menu.addAction("Mesa digitalizadora", lambda: self.lbl_status.setText("Mesa digitalizadora (em breve)"))
        menu_regras = menu.addMenu("Regras de graduação")
        menu_regras.addAction("Regras de Graduação - Nomes...", lambda: self.lbl_status.setText("Regras de Graduação - Nomes (em breve)"))
        menu_regras.addAction("Regras de Graduação - Valores...", lambda: self.lbl_status.setText("Regras de Graduação - Valores (em breve)"))
        menu.addAction("Cores", self._abrir_dialogo_cores)
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
        menu.addAction("Níveis de impressão", lambda: self.lbl_status.setText("Níveis de impressão (em breve)"))
        pos = botao.mapToGlobal(botao.rect().bottomRight())
        menu.exec(pos)

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
        chk_cor_tecidos.setChecked(bool(getattr(canvas, "_mostrar_cor_tecidos", False)))
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
            dialog_tecidos = ConfigurarCoresTecidosDialog(tecidos, dict(getattr(canvas, "_cores_tecidos", {})), dialog)
            if dialog_tecidos.exec() == QDialog.Accepted:
                canvas._cores_tecidos = dialog_tecidos.cores_tecidos()
                canvas.update()

        def aplicar_e_fechar():
            canvas._mostrar_cor_tecidos = chk_cor_tecidos.isChecked()
            canvas.update()
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

    def _abrir_dialogo_arquivo_claro(
        self,
        titulo: str,
        filtro: str,
        *,
        modo_salvar: bool = False,
    ) -> tuple[str, str]:
        dialog = QFileDialog(self, titulo, "", filtro)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        if modo_salvar:
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        else:
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        self._aplicar_estilo_claro_dialogo(dialog)
        self._centralizar_dialogo_na_janela(dialog)
        if dialog.exec() != QDialog.Accepted:
            return "", ""
        arquivos = dialog.selectedFiles()
        caminho = arquivos[0] if arquivos else ""
        return caminho, dialog.selectedNameFilter()

    def _importar_por_tipo(self, tipo: str):
        filtros = {
            "dxf": "DXF (*.dxf)",
            "aama": "AAMA/ASTM (*.aama *.astm *.zip)",
            "plot": "Plotagem (*.plt *.hpgl *.txt)",
            "lectra": "Lectra (*.mdl *.iba *.zip)",
            "investronica": "Investronica (*.vec *.pat *.zip)",
            "gerber": "Gerber (*.ger *.gbr *.zip)",
            "assyst": "Assyst (*.assyst *.ast *.zip)",
        }
        caminho, _ = self._abrir_dialogo_arquivo_claro(f"Importar {tipo.upper()}", filtros.get(tipo, "Todos (*.*)"))
        if not caminho:
            return
        area = self._area_documento_atual()
        if tipo == "dxf" and area:
            elementos = importar_dxf_para_elementos(caminho)
            if not elementos:
                self.lbl_status.setText("DXF sem entidades LINE/LWPOLYLINE suportadas.")
                return
            area.canvas.cena.elementos.extend(elementos)
            area.canvas._registrar_historico()
            self._centralizar_canvas_em_elementos(area.canvas, elementos)
            area._on_zoom_changed(area.canvas.zoom)
            area.canvas.update()
            self.backstage.hide()
            self.lbl_status.setText(f"Importado DXF: {len(elementos)} segmentos")
            return

        imports = self.projeto_atual.preferencias_usuario.setdefault("imports", [])
        imports.append({"tipo": tipo, "caminho": caminho})
        self.backstage.hide()
        self.lbl_status.setText(f"Importação registrada ({tipo}). Suporte completo em evolução.")

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
        self.lbl_status.setText("Recuperação concluída.")

    def _abrir_projeto(self):
        caminho, _ = self._abrir_dialogo_arquivo_claro(
            "Abrir projeto",
            f"Projeto GUIMMA (*{EXTENSAO_PROJETO} *.gstudio);;Todos (*.*)",
        )
        if caminho:
            self._abrir_projeto_em_caminho(caminho)

    def _abrir_projeto_em_caminho(self, caminho: str):
        caminho_resolvido = str(Path(caminho).resolve())
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
        pasta_inicial = self._arquivo_atual.parent if self._arquivo_atual else Path.home()
        nome_inicial = self._arquivo_atual.stem if self._arquivo_atual else "novo_projeto"
        dlg = SalvarComoDialog(self, pasta_inicial=pasta_inicial, nome_inicial=nome_inicial)
        if dlg.exec():
            destino = dlg.caminho_destino()
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
        self._barra_usuarios_habilitada = habilitada
        self.projeto_atual.preferencias_usuario["barra_usuarios_habilitada"] = habilitada
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

    def _desfazer_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
            area.canvas.desfazer_acao()

    def _copiar_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
            area.canvas.copiar()

    def _refazer_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
            area.canvas.refazer_acao()

    def _colar_canvas_atual(self):
        area = self._area_documento_atual()
        if area:
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
        if tool_id != "curva" and self._janela_aux_curva and self._janela_aux_curva.isVisible():
            self._memorizar_posicao_caixa_aux(self._janela_aux_curva, "curva")
            self._janela_aux_curva.hide()
        if tool_id != "retangulo" and self._janela_aux_retangulo and self._janela_aux_retangulo.isVisible():
            self._memorizar_posicao_caixa_aux(self._janela_aux_retangulo, "retangulo")
            self._janela_aux_retangulo.hide()
        area_atual = self._area_documento_atual()
        if area_atual:
            area_atual.canvas.set_ferramenta_ativa(tool_id)
            area_atual.canvas.definir_config_retangulo(self._retangulo_criar_molde)
        if tool_id == "selecionar":
            self.lbl_status.setText("Selecionar ativada")

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

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = self._capturar_estado_documento_canvas(area)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _assinatura_estado_canvas(self, area: AreaDocumentoWidget) -> str:
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
        atalhos.setFixedHeight(30)
        atalhos.setStyleSheet("background:#f1f3f5; border-top:1px solid #c8d1da; border-bottom:1px solid #dce2e8;")
        row = QHBoxLayout(atalhos)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(4)

        self.btn_snap = QPushButton("Snap")
        self.btn_snap.setCheckable(True)
        self.btn_snap.setChecked(self._snap_ativo_global)
        self.btn_snap.setCursor(Qt.PointingHandCursor)
        self.btn_snap.setToolTip("Ativar/Desativar snap (ímã)")
        icone_snap = ICONS_DIR / "snap.svg"
        if icone_snap.exists():
            self.btn_snap.setIcon(QIcon(str(icone_snap)))
        self.btn_snap.toggled.connect(self._alternar_snap_canvas_atual)
        self.btn_snap.setStyleSheet(
            "QPushButton { color:#1f1f1f; background:#ffffff; border:1px solid #b6c0cb; padding:3px 10px; }"
            "QPushButton:checked { background:#d2ebff; border-color:#4396d6; color:#0a4f82; font-weight:700; }"
        )
        row.addWidget(self.btn_snap)

        self.btn_mao = QPushButton("🖐")
        self.btn_mao.setCheckable(True)
        self.btn_mao.setFixedHeight(24)
        self.btn_mao.setToolTip("Mão (navegação)")
        self.btn_mao.clicked.connect(lambda: self._set_modo_navegacao("mao"))
        row.addWidget(self.btn_mao)

        self.btn_lupa = QPushButton("🔍")
        self.btn_lupa.setCheckable(True)
        self.btn_lupa.setFixedHeight(24)
        self.btn_lupa.setToolTip("Lupa")
        self.btn_lupa.clicked.connect(lambda: self._set_modo_navegacao("lupa"))
        row.addWidget(self.btn_lupa)

        self.btn_zoom_menos = QPushButton("−")
        self.btn_zoom_menos.setFixedHeight(24)
        self.btn_zoom_menos.setToolTip("Zoom -")
        self.btn_zoom_menos.clicked.connect(lambda: self._aplicar_zoom_incremental(1 / 1.1))
        row.addWidget(self.btn_zoom_menos)

        self.btn_zoom_mais = QPushButton("+")
        self.btn_zoom_mais.setFixedHeight(24)
        self.btn_zoom_mais.setToolTip("Zoom +")
        self.btn_zoom_mais.clicked.connect(lambda: self._aplicar_zoom_incremental(1.1))
        row.addWidget(self.btn_zoom_mais)

        self.btn_organizar_moldes = QPushButton("Organizar moldes")
        self.btn_organizar_moldes.setFixedHeight(24)
        self.btn_organizar_moldes.setToolTip("Reorganiza todos os moldes com variações de layout")
        self.btn_organizar_moldes.clicked.connect(self._organizar_moldes_canvas_atual)
        row.addWidget(self.btn_organizar_moldes)

        row.addStretch(1)
        layout.addWidget(atalhos)

        barra = QFrame()
        barra.setFixedHeight(28)
        barra.setStyleSheet("background: #0b88b6; border-top: 1px solid #0a7aa2; color: white;")
        l = QHBoxLayout(barra)
        l.setContentsMargins(10, 0, 10, 0)
        self.lbl_status = QLabel("Pronto")
        l.addWidget(self.lbl_status)
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
            (x1, y1), (x2, y2) = pts[0], pts[1]
            sx1 = (x1 - cx) * escala + (largura / 2)
            sy1 = (y1 - cy) * escala + (altura / 2)
            sx2 = (x2 - cx) * escala + (largura / 2)
            sy2 = (y2 - cy) * escala + (altura / 2)
            painter.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))
        painter.end()
        return img
