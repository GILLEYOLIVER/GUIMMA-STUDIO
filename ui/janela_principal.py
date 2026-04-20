from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
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
    QHBoxLayout,
    QInputDialog,
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


class GuimmaStudioMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.projeto_atual = Projeto()
        self._arquivo_atual: Path | None = None
        self._contador_sem_nome = 0
        self._ferramenta_ativa_id = "selecionar"
        self._modo_navegacao = "cursor"
        self._estilo_desenho_atual = {"cor": "#ffffff", "estilo": "solid", "espessura": 1.0, "amplitude": 1.0}
        self._restaurar_estilo_desenho_memorizado()
        self._passo_snap_angular_atual = 45.0
        self._snap_contextual_ativo = True
        self._janela_aux_curva: QDialog | None = None
        self._janela_aux_retangulo: QDialog | None = None
        self._chk_aux_retangulo_criar_molde: QCheckBox | None = None
        self._retangulo_criar_molde = True
        self._posicoes_caixas_aux: dict[str, tuple[int, int]] = self._carregar_posicoes_caixas_aux()
        self._painel_coordenadas_pos_global: tuple[int, int] | None = None
        self._ferramentas_usuario_ids: list[str] = list(self.projeto_atual.preferencias_usuario.get("ferramentas_usuario", []))
        self._ultima_aba_nao_usuario = "construcao"
        self._barra_usuarios_posicao = self.projeto_atual.preferencias_usuario.get("barra_usuarios_posicao", "area")
        self._barra_usuarios_habilitada = bool(self.projeto_atual.preferencias_usuario.get("barra_usuarios_habilitada", True))
        self._perfis_usuarios: dict[str, list[str]] = {}
        self._perfil_usuario_atual = "Usuário 1"
        self._inicializar_perfis_usuarios()
        self.setWindowTitle("GUIMMA STUDIO")
        self._configurar_interface()
        self._carregar_documentos_canvas()
        self._configurar_atalhos()
        QApplication.instance().installEventFilter(self)
        self.showMaximized()

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

        self.btn_visao = QToolButton()
        self.btn_visao.setText("VISÃO")
        self.btn_visao.setPopupMode(QToolButton.InstantPopup)
        self.btn_visao.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_visao.setMinimumWidth(86)
        self.btn_visao.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_visao.setStyleSheet(menu_btn_style)
        self.menu_visao = QMenu(self)
        self.menu_visao.setStyleSheet(
            "QMenu { background:#ffffff; color:#111111; border:1px solid #cfd6de; }"
            "QMenu::item:selected { background:#e9f3ff; color:#0b4f82; }"
        )
        self.action_regras = QAction("Réguas", self)
        self.action_regras.setCheckable(True)
        self.action_regras.setChecked(True)
        self.action_regras.toggled.connect(lambda ativo: self.lbl_status.setText("Réguas ativas" if ativo else "Réguas ocultas"))
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
        self.backstage.botoes["Salvar"].clicked.connect(self._salvar_projeto)
        self.backstage.botoes["Salvar como"].clicked.connect(self._salvar_projeto_como)
        self.backstage.botoes["Importar ▸"].clicked.connect(self._abrir_menu_importar)
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

    def _abrir_pagina_ferramenta(self, tool_id: str):
        if self._executar_acao_edicao_ribbon(tool_id):
            return
        tool_def = self.ribbon.tool_def(tool_id)
        if not tool_def:
            self.lbl_status.setText(f"Ferramenta não encontrada: {tool_id}")
            return
        if self._abrir_janela_auxiliar_ferramenta(tool_id, tool_def.title):
            return

        module_name = tool_def.module.replace("/", ".").replace(".py", "")
        try:
            module = import_module(module_name)
            tool_cls = getattr(module, tool_def.class_name)
            tool = tool_cls()
            msg = tool.ativar()
            self._ativar_ferramenta_global(tool_id)
            self.lbl_status.setText(msg)
        except Exception as exc:  # pragma: no cover - fallback de carregamento
            self.lbl_status.setText(f"Falha ao abrir {tool_def.title}: {exc}")

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
            rb_2p.setChecked(True)
            layout.addWidget(rb_2p)
            layout.addWidget(rb_3p)
            rb_2p.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("2p") if marcado else None)
            rb_3p.toggled.connect(lambda marcado: self._definir_modo_curva_area_atual("3p") if marcado else None)
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

    def _restaurar_posicao_caixa_aux(self, janela: QDialog, chave: str):
        pos = self._posicoes_caixas_aux.get(chave)
        if pos:
            janela.move(*pos)

    def _memorizar_posicao_caixa_aux(self, janela: QDialog, chave: str):
        self._posicoes_caixas_aux[chave] = (janela.x(), janela.y())
        self.projeto_atual.preferencias_usuario["posicoes_caixas_aux"] = dict(self._posicoes_caixas_aux)

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
        caminho, _ = QFileDialog.getOpenFileName(self, f"Importar {tipo.upper()}", "", filtros.get(tipo, "Todos (*.*)"))
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
            if el.get("tipo") != "polyline":
                continue
            pontos.extend([(float(x), float(y)) for x, y in el.get("pontos", [])])
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

    def closeEvent(self, event):  # noqa: N802
        if not self._ha_alteracoes_nao_salvas():
            event.accept()
            return
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Fechar programa")
        caixa.setIcon(QMessageBox.Question)
        caixa.setText("Existem alterações não salvas. Deseja salvar antes de sair?")
        caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        caixa.setDefaultButton(QMessageBox.Yes)
        resposta = caixa.exec()
        if resposta == QMessageBox.Cancel:
            event.ignore()
            return
        if resposta == QMessageBox.Yes and not self._salvar_projeto():
            event.ignore()
            return
        event.accept()

    def _ha_alteracoes_nao_salvas(self) -> bool:
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget) and self._tem_alteracoes_area(area):
                return True
        return False

    def _novo_projeto(self):
        self._adicionar_aba_documento()
        self.backstage.hide()

    def _abrir_projeto(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir projeto",
            "",
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
                QMessageBox.information(self, "Arquivo já aberto", f"O arquivo já está aberto:\n{Path(caminho).name}")
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
            area.canvas._registrar_historico()
            QTimer.singleShot(0, lambda a=area: self._centralizar_area_documento(a))
            area.canvas.update()
        if area:
            area.setProperty("assinatura_salva", self._assinatura_canvas(area))
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
        return True

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
            "QTabBar::tab { background:#ffffff; border:1px solid #d7dbe1; padding:3px 22px 3px 10px; margin-right:1px; }"
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
        faixa.setFixedHeight(52)
        faixa.setStyleSheet("QFrame { background:#f5f9fe; border:1px solid #c9dbef; }")
        lay = QHBoxLayout(faixa)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)

        self.btn_usuario_add_all = QPushButton("Adicionar todas da aba")
        self.btn_usuario_add_all.setCursor(Qt.PointingHandCursor)
        self.btn_usuario_add_all.setFixedHeight(34)
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
        self.btn_usuario_limpar.setFixedHeight(34)
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
        self.btn_novo_perfil_usuario.setFixedHeight(34)
        self.btn_novo_perfil_usuario.clicked.connect(self._criar_novo_perfil_usuario)
        self.btn_novo_perfil_usuario.setStyleSheet(self.btn_usuario_add_all.styleSheet())
        controles_layout.addWidget(self.btn_novo_perfil_usuario, 0)

        self.btn_salvar_perfil_usuario = QPushButton("Salvar usuário")
        self.btn_salvar_perfil_usuario.setCursor(Qt.PointingHandCursor)
        self.btn_salvar_perfil_usuario.setFixedHeight(34)
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

    def _definir_posicao_barra_usuarios(self, posicao: str):
        if posicao not in {"topo", "area"}:
            return
        self._barra_usuarios_posicao = posicao
        self.projeto_atual.preferencias_usuario["barra_usuarios_posicao"] = posicao
        self._reposicionar_barra_usuarios()
        self._atualizar_visibilidade_barra_usuarios(self.ribbon.current_tab_id() or "inicio")

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
            self.faixa_usuarios.setVisible(self._barra_usuarios_habilitada)

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

    def _persistir_perfis_usuarios(self):
        self.projeto_atual.preferencias_usuario["perfis_usuarios"] = {
            nome: list(ids) for nome, ids in self._perfis_usuarios.items()
        }
        self.projeto_atual.preferencias_usuario["perfil_usuario_atual"] = self._perfil_usuario_atual
        self.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(self._ferramentas_usuario_ids)

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
        self._persistir_perfis_usuarios()
        self._atualizar_linha_usuarios()
        self.lbl_status.setText(f"Perfil '{nome_perfil}' carregado.")

    def _criar_novo_perfil_usuario(self):
        nome, ok = QInputDialog.getText(self, "Novo usuário", "Nome do usuário/perfil:")
        nome = (nome or "").strip()
        if not ok or not nome:
            return
        if nome in self._perfis_usuarios:
            self.lbl_status.setText(f"O perfil '{nome}' já existe.")
            return
        self._perfis_usuarios[nome] = list(self._ferramentas_usuario_ids)
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
        area_doc.setProperty("assinatura_salva", self._assinatura_canvas(area_doc))
        area_doc.setProperty("arquivo_origem", caminho_origem)
        index = self.abas_documentos.addTab(area_doc, nome)
        self._configurar_botao_fechar_aba(index)
        self.abas_documentos.setCurrentIndex(index)

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
        else:
            self.lbl_escala.setText("Escala --")

    def _area_documento_atual(self) -> AreaDocumentoWidget | None:
        area = self.abas_documentos.currentWidget()
        if isinstance(area, AreaDocumentoWidget):
            return area
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
            return True
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Fechando arquivo")
        caixa.setIcon(QMessageBox.Question)
        caixa.setText(f"O arquivo\n{nome_aba}\nfoi alterado. Deseja salvar as alterações?")
        caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        caixa.setDefaultButton(QMessageBox.Yes)
        resposta = caixa.exec()
        if resposta == QMessageBox.Cancel:
            return False
        if resposta == QMessageBox.Yes:
            return self._salvar_projeto()
        return True

    def _sincronizar_documentos_canvas_no_projeto(self):
        documentos_canvas: list[dict] = []
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if not isinstance(area, AreaDocumentoWidget):
                continue
            documentos_canvas.append(
                {
                    "nome": self.abas_documentos.tabText(i),
                    "elementos": area.canvas.elementos_para_salvar(),
                    "painel_coordenadas_visivel": area.canvas.painel_coordenadas_visivel(),
                }
            )
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
            if "painel_coordenadas_visivel" in doc:
                area_doc.canvas.definir_painel_coordenadas_visivel(bool(doc.get("painel_coordenadas_visivel")))
            area_doc.setProperty("assinatura_salva", self._assinatura_canvas(area_doc))
            nome = doc.get("nome") or "(Sem nome)"
            if str(nome).strip().startswith("(Sem nome)"):
                idx_nome = self.abas_documentos.count() + 1
                nome = base_nome_arquivo if idx_nome == 1 else f"{base_nome_arquivo} -{idx_nome}"
            idx = self.abas_documentos.addTab(area_doc, nome)
            self._configurar_botao_fechar_aba(idx)
            QTimer.singleShot(0, lambda a=area_doc: self._centralizar_area_documento(a))
        self.abas_documentos.setCurrentIndex(self.abas_documentos.count() - 1)

    def _ativar_ferramenta_global(self, tool_id: str):
        self._ferramenta_ativa_id = tool_id
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
        area_atual = self._area_documento_atual()
        if area_atual:
            area_atual.canvas.set_estilo_linha(**self._estilo_desenho_atual)
        self.lbl_status.setText(
            f"Cor {self._estilo_desenho_atual['cor']} | Estilo {self._estilo_desenho_atual['estilo']} | "
            f"Espessura {self._estilo_desenho_atual['espessura']:.0f} | Altura {self._estilo_desenho_atual['amplitude']:.1f}"
        )

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
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.canvas.set_passo_snap_angular(self._passo_snap_angular_atual)
        self.lbl_status.setText(f"Snap angular: {self._passo_snap_angular_atual:.0f}° (W = trava principais)")

    def _alternar_snap_contextual(self, ativo: bool):
        self._snap_contextual_ativo = bool(ativo)
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
        area = self._area_documento_atual()
        if not area:
            self.lbl_status.setText("Snap ativo" if ativo else "Snap desativado")
            return
        area.canvas.set_snap_ativo(ativo)

    def _on_snap_changed(self, ativo: bool):
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
        self._painel_coordenadas_pos_global = (x, y)
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.canvas.set_painel_auxiliar_posicao(self._painel_coordenadas_pos_global)

    def _assinatura_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = {
            "elementos": area.canvas.elementos_para_salvar(),
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _tem_alteracoes_area(self, area: AreaDocumentoWidget) -> bool:
        assinatura_salva = area.property("assinatura_salva")
        return self._assinatura_canvas(area) != assinatura_salva

    def _marcar_documentos_como_salvos(self):
        for i in range(self.abas_documentos.count()):
            area = self.abas_documentos.widget(i)
            if isinstance(area, AreaDocumentoWidget):
                area.setProperty("assinatura_salva", self._assinatura_canvas(area))

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
        self.btn_snap.setChecked(True)
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
        return f"Escala {zoom * 100:.3f}%"

    def _centralizar_area_documento(self, area: AreaDocumentoWidget):
        elementos = area.canvas.cena.elementos
        if not elementos:
            return
        self._centralizar_canvas_em_elementos(area.canvas, elementos)
        area._on_zoom_changed(area.canvas.zoom)

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
