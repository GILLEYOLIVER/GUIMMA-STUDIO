from __future__ import annotations


COR_HOVER = "#d9edf9"
COR_HOVER_MENU = "#cfe8ff"
COR_HOVER_BORDA = "#6aa7d8"
COR_HOVER_TEXTO = "#073b63"
COR_SELECAO = "#2b7cd3"


def folha_estilo_hover_global() -> str:
    return f"""
    QMenu {{
        background: #eef5ef;
        color: #111111;
        border: 1px solid #9aa8b3;
        padding: 3px;
    }}
    QMenu::item {{
        min-height: 20px;
        padding: 4px 28px 4px 16px;
        background: transparent;
    }}
    QMenu::item:selected {{
        background: {COR_HOVER_MENU};
        color: {COR_HOVER_TEXTO};
    }}
    QMenu::item:disabled {{
        color: #8a8f94;
    }}
    QMenu::separator {{
        height: 1px;
        background: #aab4bd;
        margin: 5px 4px;
    }}
    QMenu::right-arrow {{
        width: 9px;
        height: 9px;
    }}

    QPushButton:hover,
    QToolButton:hover,
    QComboBox:hover,
    QSpinBox:hover,
    QDoubleSpinBox:hover,
    QLineEdit:hover,
    QTextEdit:hover,
    QPlainTextEdit:hover {{
        background: {COR_HOVER};
        border-color: {COR_HOVER_BORDA};
        color: {COR_HOVER_TEXTO};
    }}
    QPushButton:pressed,
    QToolButton:pressed {{
        background: #c7e4f7;
        border-color: #438dc5;
    }}
    QPushButton:checked,
    QToolButton:checked {{
        background: #c5e4f6;
        color: {COR_HOVER_TEXTO};
    }}

    QComboBox::drop-down:hover {{
        background: #cfe8ff;
        border-left-color: {COR_HOVER_BORDA};
    }}
    QAbstractItemView::item:hover,
    QListWidget::item:hover,
    QTreeWidget::item:hover,
    QTreeView::item:hover,
    QTableWidget::item:hover,
    QTableView::item:hover {{
        background: {COR_HOVER_MENU};
        color: {COR_HOVER_TEXTO};
    }}
    QAbstractItemView::item:selected,
    QListWidget::item:selected,
    QTreeWidget::item:selected,
    QTreeView::item:selected,
    QTableWidget::item:selected,
    QTableView::item:selected {{
        background: {COR_SELECAO};
        color: #ffffff;
    }}

    QTabBar::tab:hover {{
        background: {COR_HOVER};
        color: {COR_HOVER_TEXTO};
    }}
    QHeaderView::section:hover {{
        background: #e5f3fc;
        color: {COR_HOVER_TEXTO};
    }}
    QScrollBar::handle:hover {{
        background: #6aa7d8;
    }}
    """


def aplicar_hover_global(app) -> None:
    atual = str(app.styleSheet() or "")
    marcador = "QMenu::item:selected"
    if marcador in atual and "QAbstractItemView::item:hover" in atual:
        return
    app.setStyleSheet((atual + "\n" + folha_estilo_hover_global()).strip())


def aplicar_hover_menu(menu) -> None:
    menu.setStyleSheet(folha_estilo_hover_global())
