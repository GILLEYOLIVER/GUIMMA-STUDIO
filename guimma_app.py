from __future__ import annotations

import sys
from typing import Sequence

from PySide6.QtCore import QLibraryInfo, QLocale, QTimer, QTranslator
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QSizePolicy

from config import APP_NOME
from ui.janela_principal import GuimmaStudioMainWindow


class GuimmaStudioApp:
    def __init__(self, argv: Sequence[str] | None = None):
        self._argv = list(argv or sys.argv)
        self.qt_app = QApplication(self._argv)
        self.qt_app.setApplicationName(APP_NOME)
        self._aplicar_traducao_qt_ptbr()
        self._aplicar_tema_claro_global()
        self.janela_principal = GuimmaStudioMainWindow()
        self._corrigir_layout_aba_usuario()
        try:
            self.janela_principal.ribbon.tabbar.currentChanged.connect(self._corrigir_layout_aba_usuario)
        except Exception:
            pass
        QTimer.singleShot(0, self._corrigir_layout_aba_usuario)
        QTimer.singleShot(150, self._corrigir_layout_aba_usuario)
        QTimer.singleShot(350, self._corrigir_layout_aba_usuario)

    def _aplicar_traducao_qt_ptbr(self):
        self._tradutor_qt = QTranslator(self.qt_app)
        caminho_i18n = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        for idioma in ("pt_BR", "pt"):
            if self._tradutor_qt.load(f"qtbase_{idioma}", caminho_i18n):
                self.qt_app.installTranslator(self._tradutor_qt)
                QLocale.setDefault(QLocale(idioma))
                return

    def _aplicar_tema_claro_global(self):
        self.qt_app.setStyle("Fusion")
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor("#efefef"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        pal.setColor(QPalette.Base, QColor("#ffffff"))
        pal.setColor(QPalette.AlternateBase, QColor("#f4f4f4"))
        pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        pal.setColor(QPalette.ToolTipText, QColor("#111111"))
        pal.setColor(QPalette.Text, QColor("#111111"))
        pal.setColor(QPalette.Button, QColor("#f6f6f6"))
        pal.setColor(QPalette.ButtonText, QColor("#111111"))
        pal.setColor(QPalette.BrightText, QColor("#ffffff"))
        pal.setColor(QPalette.Highlight, QColor("#2b7cd3"))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.qt_app.setPalette(pal)

    def _corrigir_layout_aba_usuario(self, *_args):
        """Compacta a aba de usuário e impede corte no canto direito do topo."""
        try:
            from ui import ribbon

            janela = self.janela_principal
            rib = janela.ribbon
            index = rib._tab_index_by_id("usuarios")
            if index is None:
                return

            self._corrigir_faixa_usuarios_topo(janela)

            area_atual = rib.paginas.widget(index)
            pagina_atual = area_atual.widget() if hasattr(area_atual, "widget") else area_atual
            if pagina_atual is None:
                return

            botoes = pagina_atual.findChildren(ribbon.RibbonButton)
            ids: list[str] = []
            for botao in botoes:
                tool_id = str(botao.property("tool_id") or "").strip()
                if tool_id and tool_id not in ids:
                    ids.append(tool_id)
            if not ids:
                return

            assinatura = tuple(ids)
            ja_compacto = getattr(rib, "_usuario_layout_compacto_assinatura", None) == assinatura
            precisa_compactar = len(ids) > 4 and any(not bool(getattr(botao, "compacto", False)) for botao in botoes)

            if precisa_compactar or not ja_compacto:
                tools = [rib._tools[tid] for tid in ids if tid in rib._tools]
                grupos = [("Usuario", tools)] if tools else []
                pagina = ribbon.RibbonPage(grupos, compactar_grupos=True)
                pagina.setMinimumWidth(0)
                pagina.tool_selected.connect(rib._on_tool_selected)
                pagina.adicionar_usuario.connect(rib.adicionar_usuario.emit)
                for grupo in pagina.findChildren(ribbon.RibbonGroup):
                    grupo.estilo_changed.connect(rib.estilo_changed.emit)

                pagina_visivel = rib.paginas.currentIndex()
                antiga = rib.paginas.widget(index)
                rib.paginas.removeWidget(antiga)
                antiga.deleteLater()
                nova_area = rib._criar_viewport_pagina(pagina)
                nova_area.setMinimumWidth(0)
                rib.paginas.insertWidget(index, nova_area)
                rib._usuario_layout_compacto_assinatura = assinatura
                if pagina_visivel == index:
                    rib.paginas.setCurrentIndex(index)
                rib.aplicar_tema(rib._tema_interface)
                area_atual = nova_area

            if hasattr(area_atual, "horizontalScrollBar"):
                area_atual.horizontalScrollBar().setValue(0)
        except Exception:
            return

    def _corrigir_faixa_usuarios_topo(self, janela) -> None:
        """Deixa a linha de ícones encolher e preserva os controles à direita."""
        try:
            linha = getattr(janela, "linha_usuario", None)
            if linha is not None:
                linha.setMinimumWidth(0)
                linha.setMinimumSize(0, 0)
                linha.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                layout_linha = getattr(janela, "layout_linha_usuario", None)
                if layout_linha is not None:
                    layout_linha.setContentsMargins(2, 0, 2, 0)
                    layout_linha.setSpacing(2)

            painel = getattr(janela, "painel_controles_usuario", None)
            if painel is not None:
                painel.setMinimumWidth(300)
                painel.setMaximumWidth(390)
                painel.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

            combo = getattr(janela, "combo_perfil_usuario", None)
            if combo is not None:
                combo.setMinimumWidth(95)
                combo.setMaximumWidth(145)

            ajustes_botoes = (
                ("btn_novo_perfil_usuario", "Novo", 48),
                ("btn_salvar_perfil_usuario", "Salvar", 58),
                ("btn_usuario_add_all", "Adicionar", 76),
                ("btn_usuario_limpar", "Limpar", 58),
            )
            for nome_attr, texto, largura in ajustes_botoes:
                botao = getattr(janela, nome_attr, None)
                if botao is None:
                    continue
                botao.setText(texto)
                botao.setMinimumWidth(largura)
                botao.setMaximumWidth(largura + 16)
                botao.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            faixa = getattr(janela, "faixa_usuarios", None)
            if faixa is not None:
                faixa.setMinimumWidth(0)
                faixa.updateGeometry()
        except Exception:
            return

    def run(self) -> int:
        self.janela_principal.exibir_inicial()
        return self.qt_app.exec()
