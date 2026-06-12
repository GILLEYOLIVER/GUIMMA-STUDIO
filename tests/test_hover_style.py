from __future__ import annotations

from ui.hover_style import folha_estilo_hover_global


def test_folha_hover_global_cobre_menus_e_itens_de_lista():
    estilo = folha_estilo_hover_global()

    assert "QMenu::item:selected" in estilo
    assert "QAbstractItemView::item:hover" in estilo
    assert "QTableView::item:hover" in estilo
    assert "QPushButton:hover" in estilo
    assert "QToolButton:hover" in estilo
