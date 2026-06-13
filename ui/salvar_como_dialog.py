from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QStyledItemDelegate,
    QStyle,
)
from config import EXTENSAO_PROJETO


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


class SalvarComoDialog(QDialog):
    def __init__(self, parent=None, pasta_inicial: Path | None = None, nome_inicial: str = "novo_projeto"):
        super().__init__(parent)
        self._tema = self._tema_do_parent(parent)
        self.setWindowTitle("Salvar como...")
        self.setMinimumSize(860, 600)
        self.resize(940, 650)
        self._pasta = Path(pasta_inicial or Path.home())
        self._atalhos_pastas = self._criar_atalhos_pastas()
        self.setObjectName("SalvarComoDialog")
        self.setStyleSheet(self._stylesheet())

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(10)

        topo = QGroupBox("Arquivo")
        g = QGridLayout(topo)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(8)

        self.edt_pasta = QLineEdit(str(self._pasta))
        self.edt_pasta.setReadOnly(True)
        btn_escolher_pasta = QPushButton("Selecionar pasta...")
        btn_escolher_pasta.clicked.connect(self._selecionar_pasta)
        g.addWidget(self.edt_pasta, 0, 0)
        g.addWidget(btn_escolher_pasta, 0, 1)

        self.lst_arquivos_existentes = QListWidget()
        self.lst_arquivos_existentes.setMinimumHeight(160)
        self.lst_arquivos_existentes.setAlternatingRowColors(True)
        self.lst_arquivos_existentes.itemClicked.connect(self._usar_nome_arquivo_existente)
        self.lst_locais = QListWidget()
        self.lst_locais.setFixedWidth(170)
        self.lst_locais.setSpacing(4)
        self.lst_locais.itemClicked.connect(self._selecionar_local_rapido)
        self._popular_locais_rapidos()
        area_arquivos = QHBoxLayout()
        area_arquivos.setSpacing(8)
        area_arquivos.addWidget(self.lst_locais)
        area_arquivos.addWidget(self.lst_arquivos_existentes, 1)
        g.addLayout(area_arquivos, 1, 0, 1, 2)

        self.edt_nome = QLineEdit(nome_inicial)
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItem(f"Projeto GUIMMA (*{EXTENSAO_PROJETO})")
        g.addWidget(self.edt_nome, 2, 0, 1, 2)
        g.addWidget(self.cmb_tipo, 3, 0, 1, 2)
        raiz.addWidget(topo)

        meta = QGroupBox("Informações do modelo")
        form = QFormLayout(meta)
        self.chk_associar = QCheckBox("Associar modelo ao nome do arquivo")
        self.edt_modelo = QLineEdit(nome_inicial)
        self.edt_colecao = QLineEdit()
        self.edt_cliente = QLineEdit()
        self.edt_descricao = QTextEdit()
        self.edt_descricao.setFixedHeight(90)
        self.edt_palavra = QLineEdit()
        self.chk_backup = QCheckBox("Arquivo backup")
        form.addRow(self.chk_associar)
        form.addRow("Modelo:", self.edt_modelo)
        form.addRow("Coleção:", self.edt_colecao)
        form.addRow("Cliente:", self.edt_cliente)
        form.addRow("Descrição:", self.edt_descricao)
        form.addRow("Palavra chave:", self.edt_palavra)
        form.addRow(self.chk_backup)
        raiz.addWidget(meta, 1)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        btn_cancelar = QPushButton("Cancelar")
        btn_salvar = QPushButton("Salvar")
        btn_salvar.setObjectName("PrimaryButton")
        btn_cancelar.clicked.connect(self.reject)
        btn_salvar.clicked.connect(self.accept)
        botoes.addWidget(btn_cancelar)
        botoes.addWidget(btn_salvar)
        raiz.addLayout(botoes)
        self._atualizar_lista_arquivos_existentes()

    @staticmethod
    def _tema_do_parent(parent) -> dict[str, str]:
        if parent is not None and hasattr(parent, "_tema_interface"):
            try:
                tema = parent._tema_interface()
                if isinstance(tema, dict):
                    return dict(tema)
            except Exception:
                pass
        return {
            "janela": "#eef2f6",
            "painel": "#ffffff",
            "faixa": "#f4f6f8",
            "texto": "#111111",
            "texto_suave": "#4a5568",
            "borda": "#c8d1da",
            "primaria": "#0b7fb8",
            "primaria_escura": "#0a74aa",
            "hover": "#d9edf9",
            "hover_menu": "#e9f3ff",
            "selecionado": "#c5e4f6",
        }

    def _stylesheet(self) -> str:
        tema = self._tema
        return f"""
            QDialog#SalvarComoDialog {{
                background: {tema['janela']};
                color: {tema['texto']};
            }}
            QGroupBox {{
                background: {tema['painel']};
                border: 1px solid {tema['borda']};
                border-radius: 6px;
                margin-top: 14px;
                font-size: 13px;
                font-weight: 700;
                color: {tema['texto']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background: {tema['janela']};
                color: {tema['primaria_escura']};
            }}
            QLineEdit, QTextEdit, QComboBox {{
                background: {tema['painel']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
                border-radius: 4px;
                padding: 5px 7px;
                selection-background-color: {tema['selecionado']};
                selection-color: {tema['texto']};
            }}
            QLineEdit:read-only {{
                background: {tema['faixa']};
                color: {tema['texto_suave']};
            }}
            QListWidget {{
                background: {tema['painel']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
                border-radius: 4px;
                outline: none;
                alternate-background-color: {tema['faixa']};
            }}
            QListWidget::item {{
                min-height: 34px;
                padding: 5px 9px;
            }}
            QListWidget::item:selected {{
                background: {tema['selecionado']};
                color: {tema['texto']};
            }}
            QListWidget::item:disabled {{
                color: {tema['texto_suave']};
            }}
            QPushButton {{
                background: {tema['painel']};
                color: {tema['texto']};
                border: 1px solid {tema['borda']};
                border-radius: 4px;
                padding: 6px 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {tema['hover']}; border-color: {tema['primaria']}; }}
            QPushButton:pressed {{ background: {tema['selecionado']}; }}
            QPushButton#PrimaryButton {{
                background: {tema['primaria']};
                color: #ffffff;
                border-color: {tema['primaria_escura']};
            }}
            QPushButton#PrimaryButton:hover {{
                background: {tema['primaria_escura']};
            }}
            QCheckBox, QLabel {{
                color: {tema['texto']};
            }}
        """

    def _selecionar_pasta(self):
        dialog = QFileDialog(self, "Selecionar pasta", str(self._pasta))
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        dialog.resize(1180, 760)
        dialog.setMinimumSize(1040, 680)
        dialog.setStyleSheet(self._stylesheet())
        dialog.setLabelText(QFileDialog.DialogLabel.LookIn, "Examinar:")
        dialog.setLabelText(QFileDialog.DialogLabel.FileName, "Diretório:")
        dialog.setLabelText(QFileDialog.DialogLabel.FileType, "Tipo:")
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Selecionar")
        dialog.setLabelText(QFileDialog.DialogLabel.Reject, "Cancelar")
        try:
            dialog.setSidebarUrls(self._urls_laterais_dialogo())
        except Exception:
            pass
        self._traduzir_textos_internos_dialogo_arquivo(dialog)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_centralizar_dialogo_na_janela"):
            QTimer.singleShot(0, lambda: parent._centralizar_dialogo_na_janela(dialog))
        for arvore in dialog.findChildren(QTreeView):
            try:
                arvore.setColumnWidth(0, 420)
                header = arvore.header()
                if header is not None:
                    header.setStretchLastSection(False)
                    header.resizeSection(0, 420)
            except Exception:
                pass
        if dialog.exec() != QDialog.Accepted:
            return
        arquivos = dialog.selectedFiles()
        pasta = arquivos[0] if arquivos else ""
        if pasta:
            self._pasta = Path(pasta)
            self.edt_pasta.setText(str(self._pasta))
            self._marcar_local_rapido_atual()
            self._atualizar_lista_arquivos_existentes()

    def _criar_atalhos_pastas(self) -> list[tuple[str, Path | None, QStyle.StandardPixmap]]:
        home = Path.home()

        def _standard_path(tipo: QStandardPaths.StandardLocation, fallback: Path) -> Path:
            caminho = QStandardPaths.writableLocation(tipo)
            return Path(caminho) if caminho else fallback

        desktop = _standard_path(QStandardPaths.StandardLocation.DesktopLocation, home / "Desktop")
        documentos = _standard_path(QStandardPaths.StandardLocation.DocumentsLocation, home / "Documents")
        downloads = _standard_path(QStandardPaths.StandardLocation.DownloadLocation, home / "Downloads")
        unidade = Path(home.anchor) if home.anchor else home
        return [
            ("Início", home, QStyle.StandardPixmap.SP_DirHomeIcon),
            ("Área de Trabalho", desktop, QStyle.StandardPixmap.SP_DesktopIcon),
            ("Documentos", documentos, QStyle.StandardPixmap.SP_DirIcon),
            ("Downloads", downloads, QStyle.StandardPixmap.SP_DirIcon),
            ("Bibliotecas", home, QStyle.StandardPixmap.SP_DirIcon),
            ("Este Computador", unidade, QStyle.StandardPixmap.SP_ComputerIcon),
            ("Rede", None, QStyle.StandardPixmap.SP_DriveNetIcon),
        ]

    def _popular_locais_rapidos(self):
        self.lst_locais.clear()
        for nome, pasta, icone_padrao in self._atalhos_pastas:
            item = QListWidgetItem(self.style().standardIcon(icone_padrao), nome)
            item.setData(Qt.UserRole, str(pasta) if pasta else "")
            if pasta is None or not pasta.exists():
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.lst_locais.addItem(item)
        self._marcar_local_rapido_atual()

    def _marcar_local_rapido_atual(self):
        atual = str(self._pasta.resolve()).lower() if self._pasta.exists() else str(self._pasta).lower()
        for i in range(self.lst_locais.count()):
            item = self.lst_locais.item(i)
            pasta = str(item.data(Qt.UserRole) or "")
            if pasta and pasta.lower() == atual:
                self.lst_locais.setCurrentItem(item)
                return
        self.lst_locais.setCurrentRow(-1)

    def _selecionar_local_rapido(self, item: QListWidgetItem):
        pasta = str(item.data(Qt.UserRole) or "").strip()
        if not pasta:
            return
        caminho = Path(pasta)
        if not caminho.exists():
            return
        self._pasta = caminho
        self.edt_pasta.setText(str(self._pasta))
        self._atualizar_lista_arquivos_existentes()
        self._marcar_local_rapido_atual()

    def _urls_laterais_dialogo(self) -> list[QUrl]:
        urls: list[QUrl] = []
        vistos: set[str] = set()
        for _, pasta, _ in self._atalhos_pastas:
            if pasta is None or not pasta.exists():
                continue
            chave = str(pasta.resolve()).lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            urls.append(QUrl.fromLocalFile(str(pasta)))
        return urls

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
        for view in dialog.findChildren(QTreeView):
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

    def _atualizar_lista_arquivos_existentes(self):
        self.lst_arquivos_existentes.clear()
        if not self._pasta.exists():
            return
        self._marcar_local_rapido_atual()
        arquivos = sorted(self._pasta.glob(f"*{EXTENSAO_PROJETO}"), key=lambda p: p.name.lower())
        for caminho in arquivos:
            item = QListWidgetItem(caminho.name)
            item.setData(Qt.UserRole, caminho.stem)
            self.lst_arquivos_existentes.addItem(item)

    def _usar_nome_arquivo_existente(self, item: QListWidgetItem):
        nome = str(item.data(Qt.UserRole) or "").strip()
        if nome:
            self.edt_nome.setText(nome)

    def caminho_destino(self) -> Path:
        nome = self.edt_nome.text().strip() or "novo_projeto"
        destino = self._pasta / nome
        if destino.suffix.lower() != EXTENSAO_PROJETO:
            destino = destino.with_suffix(EXTENSAO_PROJETO)
        return destino

    def metadados(self) -> dict:
        return {
            "associar_modelo": self.chk_associar.isChecked(),
            "modelo": self.edt_modelo.text().strip(),
            "colecao": self.edt_colecao.text().strip(),
            "cliente": self.edt_cliente.text().strip(),
            "descricao": self.edt_descricao.toPlainText().strip(),
            "palavra_chave": self.edt_palavra.text().strip(),
            "arquivo_backup": self.chk_backup.isChecked(),
        }
