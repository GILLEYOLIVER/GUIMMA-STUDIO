from __future__ import annotations

from pathlib import Path

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
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class SalvarComoDialog(QDialog):
    def __init__(self, parent=None, pasta_inicial: Path | None = None, nome_inicial: str = "novo_projeto"):
        super().__init__(parent)
        self.setWindowTitle("Salvar como...")
        self.setMinimumSize(760, 520)
        self._pasta = Path(pasta_inicial or Path.home())

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

        self.edt_nome = QLineEdit(nome_inicial)
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItem("Projeto GUIMMA (*.gstudio)")
        g.addWidget(self.edt_nome, 1, 0, 1, 2)
        g.addWidget(self.cmb_tipo, 2, 0, 1, 2)
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
        btn_cancelar.clicked.connect(self.reject)
        btn_salvar.clicked.connect(self.accept)
        botoes.addWidget(btn_cancelar)
        botoes.addWidget(btn_salvar)
        raiz.addLayout(botoes)

    def _selecionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta", str(self._pasta))
        if pasta:
            self._pasta = Path(pasta)
            self.edt_pasta.setText(str(self._pasta))

    def caminho_destino(self) -> Path:
        nome = self.edt_nome.text().strip() or "novo_projeto"
        destino = self._pasta / nome
        if destino.suffix.lower() != ".gstudio":
            destino = destino.with_suffix(".gstudio")
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
