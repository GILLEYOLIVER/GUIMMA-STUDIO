from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QTabBar, QTabWidget, QVBoxLayout, QWidget

from canvas.cena import CenaDocumento
from canvas.workspace import AreaDocumentoWidget
from config import EXTENSAO_PROJETO, ICONS_DIR
from core.projeto import Projeto
from formats.gs_project import GSProjectIO
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
        self.setWindowTitle("GUIMMA STUDIO")
        self._configurar_interface()
        self._configurar_atalhos()
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
                padding: 6px 18px;
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

        barra_menu = QWidget()
        sup = QHBoxLayout(barra_menu)
        sup.setContentsMargins(0, 0, 4, 0)
        sup.setSpacing(0)
        barra_menu.setFixedHeight(30)

        self.botao_arquivo = QPushButton("ARQUIVO")
        self.botao_arquivo.setCursor(Qt.PointingHandCursor)
        self.botao_arquivo.setFixedSize(88, 26)
        self.botao_arquivo.clicked.connect(self._alternar_backstage)
        self.botao_arquivo.setStyleSheet(
            "background:#0b7fb8;color:white;font-weight:700;border:1px solid #0b6fa0;"
            "border-radius:0;padding:0 8px;"
        )
        sup.addWidget(self.botao_arquivo, 0, Qt.AlignLeft)

        self.ribbon = RibbonWidget(include_tabbar=False)
        self.ribbon.tabbar.setExpanding(True)
        self.ribbon.tabbar.setDrawBase(False)
        self.ribbon.tabbar.currentChanged.connect(lambda _: self.backstage.hide())
        self.ribbon.tool_selected.connect(self._abrir_pagina_ferramenta)
        sup.addWidget(self.ribbon.tabbar, 1)

        sup.addWidget(QLabel("VISÃO • OPÇÕES • JANELAS"))
        layout.addWidget(barra_menu)
        self.barra_superior = barra_menu
        layout.addWidget(self.ribbon)

        self.backstage = BackstageArquivoPanel(self)
        self.backstage.botoes["Novo"].clicked.connect(self._novo_projeto)
        self.backstage.botoes["Abrir"].clicked.connect(self._abrir_projeto)
        self.backstage.botoes["Salvar"].clicked.connect(self._salvar_projeto)
        self.backstage.botoes["Salvar como"].clicked.connect(self._salvar_projeto_como)
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

    def _topo_backstage(self) -> int:
        return self.barra_superior.height()

    def _abrir_pagina_ferramenta(self, tool_id: str):
        tool_def = self.ribbon.tool_def(tool_id)
        if not tool_def:
            self.lbl_status.setText(f"Ferramenta não encontrada: {tool_id}")
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

    def _novo_projeto(self):
        self._adicionar_aba_documento()
        self.backstage.hide()

    def _abrir_projeto(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Abrir projeto", "", f"Projeto GUIMMA (*{EXTENSAO_PROJETO});;Todos (*.*)")
        if caminho:
            self._abrir_projeto_em_caminho(caminho)

    def _abrir_projeto_em_caminho(self, caminho: str):
        self.projeto_atual = GSProjectIO.abrir(caminho)
        self._arquivo_atual = Path(caminho)
        self.backstage.adicionar_recente(caminho)
        self._atualizar_titulo()
        self._carregar_documentos_canvas()
        self.backstage.hide()

    def _salvar_projeto(self) -> bool:
        if self._arquivo_atual is None:
            return self._salvar_projeto_como()
        self._sincronizar_documentos_canvas_no_projeto()
        GSProjectIO.salvar(self.projeto_atual, self._arquivo_atual)
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
            self._sincronizar_documentos_canvas_no_projeto()
            GSProjectIO.salvar(self.projeto_atual, destino)
            self._arquivo_atual = destino
            self.backstage.adicionar_recente(str(destino))
            self._atualizar_titulo()
            self.backstage.hide()
            self._marcar_documentos_como_salvos()
            return True
        return False

    def _atualizar_titulo(self):
        sufixo = self._arquivo_atual.name if self._arquivo_atual else "sem arquivo"
        self.setWindowTitle(f"GUIMMA STUDIO — {self.projeto_atual.nome} ({sufixo})")

    def _criar_area_documento(self) -> QWidget:
        area = QWidget()
        area.setStyleSheet("background: #eceff3;")
        layout = QVBoxLayout(area)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
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
            "QTabBar::tab { background:#ffffff; border:1px solid #d7dbe1; padding:3px 10px; margin-right:1px; }"
            "QTabBar::tab:selected { background:#ffffff; border-bottom:2px solid #0b8dd1; }"
        )
        layout.addWidget(self.abas_documentos, 1)
        return area

    def _adicionar_aba_documento(self, nome: str | None = None):
        if nome is None:
            self._contador_sem_nome += 1
            nome = "(Sem nome)" if self._contador_sem_nome == 1 else f"(Sem nome) -{self._contador_sem_nome}"
        area_doc = AreaDocumentoWidget(CenaDocumento())
        area_doc.zoom_changed.connect(self._on_zoom_canvas_alterado)
        area_doc.canvas.ferramenta_padrao_solicitada.connect(self._ativar_ferramenta_global)
        area_doc.canvas.snap_changed.connect(self._on_snap_changed)
        area_doc.canvas.set_ferramenta_ativa(self._ferramenta_ativa_id)
        area_doc.canvas.set_snap_ativo(self.btn_snap.isChecked())
        area_doc.setProperty("assinatura_salva", self._assinatura_canvas(area_doc))
        index = self.abas_documentos.addTab(area_doc, nome)
        self._configurar_botao_fechar_aba(index)
        self.abas_documentos.setCurrentIndex(index)

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
        else:
            self.lbl_escala.setText("Escala --")

    def _area_documento_atual(self) -> AreaDocumentoWidget | None:
        area = self.abas_documentos.currentWidget()
        if isinstance(area, AreaDocumentoWidget):
            return area
        return None

    def _configurar_botao_fechar_aba(self, index: int):
        barra = self.abas_documentos.tabBar()
        botao = QPushButton("✕")
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFlat(True)
        botao.setFixedSize(16, 16)
        botao.setStyleSheet("QPushButton { color:#c62828; border:none; font-weight:700; } QPushButton:hover { color:#ff5252; }")
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
                    "painel_retas_pos": area.canvas.painel_auxiliar_posicao(),
                }
            )
        self.projeto_atual.preferencias_usuario["documentos_canvas"] = documentos_canvas

    def _carregar_documentos_canvas(self):
        while self.abas_documentos.count():
            widget = self.abas_documentos.widget(0)
            self.abas_documentos.removeTab(0)
            if widget:
                widget.deleteLater()

        docs = self.projeto_atual.preferencias_usuario.get("documentos_canvas", [])
        if not docs:
            self._adicionar_aba_documento(self._arquivo_atual.stem if self._arquivo_atual else None)
            return

        for doc in docs:
            area_doc = AreaDocumentoWidget(CenaDocumento(elementos=doc.get("elementos", [])))
            area_doc.zoom_changed.connect(self._on_zoom_canvas_alterado)
            area_doc.canvas.ferramenta_padrao_solicitada.connect(self._ativar_ferramenta_global)
            area_doc.canvas.snap_changed.connect(self._on_snap_changed)
            area_doc.canvas.set_ferramenta_ativa(self._ferramenta_ativa_id)
            area_doc.canvas.set_snap_ativo(self.btn_snap.isChecked())
            painel_pos = doc.get("painel_retas_pos")
            if isinstance(painel_pos, (list, tuple)) and len(painel_pos) == 2:
                area_doc.canvas.set_painel_auxiliar_posicao((int(painel_pos[0]), int(painel_pos[1])))
            area_doc.setProperty("assinatura_salva", self._assinatura_canvas(area_doc))
            nome = doc.get("nome") or "(Sem nome)"
            idx = self.abas_documentos.addTab(area_doc, nome)
            self._configurar_botao_fechar_aba(idx)
        self.abas_documentos.setCurrentIndex(0)

    def _ativar_ferramenta_global(self, tool_id: str):
        self._ferramenta_ativa_id = tool_id
        area_atual = self._area_documento_atual()
        if area_atual:
            area_atual.canvas.set_ferramenta_ativa(tool_id)
        if tool_id == "selecionar":
            self.lbl_status.setText("Selecionar ativada")

    def _alternar_snap_canvas_atual(self, ativo: bool):
        area = self._area_documento_atual()
        if not area:
            self.lbl_status.setText("Snap ativo" if ativo else "Snap desativado")
            return
        area.canvas.set_snap_ativo(ativo)

    def _on_snap_changed(self, ativo: bool):
        self.lbl_status.setText("Snap ativo" if ativo else "Snap desativado")

    def _assinatura_canvas(self, area: AreaDocumentoWidget) -> str:
        payload = {
            "elementos": area.canvas.elementos_para_salvar(),
            "painel": area.canvas.painel_auxiliar_posicao(),
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
