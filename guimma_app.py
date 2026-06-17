from __future__ import annotations

import sys
from types import MethodType
from typing import Sequence

from PySide6.QtCore import QEvent, QLibraryInfo, QLocale, QObject, Qt, QTimer, QTranslator
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QMenu, QScrollArea, QSizePolicy, QWidget

from config import APP_NOME
from ui.fonte_padrao import aplicar_fonte_padrao, argv_com_fonte_padrao
from ui.hover_style import aplicar_hover_global, aplicar_hover_menu
from ui.janela_principal import GuimmaStudioMainWindow


def _deslocamento_horizontal_roda(event) -> int:
    pixels = event.pixelDelta()
    if not pixels.isNull():
        if pixels.x():
            return int(pixels.x())
        if pixels.y():
            return int(-pixels.y())
    angulo = event.angleDelta()
    if not angulo.isNull():
        if angulo.x():
            return int(angulo.x() / 2)
        if angulo.y():
            return int(-angulo.y() / 2)
    return 0


class _FiltroScrollHorizontal(QObject):
    """Faz uma QScrollArea horizontal rolar com o mouse sem mostrar barra."""

    def __init__(self, area: QScrollArea):
        super().__init__(area)
        self.area = area

    def instalar(self) -> None:
        objetos = [self.area, self.area.viewport()]
        conteudo = self.area.widget()
        if conteudo is not None:
            objetos.append(conteudo)
            objetos.extend(conteudo.findChildren(QWidget))
        for obj in objetos:
            try:
                obj.installEventFilter(self)
            except Exception:
                pass

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Wheel:
            deslocamento = _deslocamento_horizontal_roda(event)
            if deslocamento:
                barra = self.area.horizontalScrollBar()
                barra.setValue(barra.value() + deslocamento)
                event.accept()
                return True
        return super().eventFilter(obj, event)


class _ScrollLinhaUsuario(QScrollArea):
    """Área horizontal da barra Usuários: rola com mouse/trackpad sem mostrar barra."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ScrollLinhaUsuario")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(34)
        self.setMouseTracking(True)
        self.setStyleSheet(
            "QScrollArea#ScrollLinhaUsuario { background: transparent; border: none; }"
            "QScrollArea#ScrollLinhaUsuario > QWidget > QWidget { background: transparent; }"
        )

    def reinstalar_filtros(self) -> None:
        objetos = [self, self.viewport()]
        conteudo = self.widget()
        if conteudo is not None:
            objetos.append(conteudo)
            objetos.extend(conteudo.findChildren(QWidget))
        for obj in objetos:
            try:
                obj.installEventFilter(self)
            except Exception:
                pass

    def _rolar_evento(self, event) -> bool:
        deslocamento = _deslocamento_horizontal_roda(event)
        if not deslocamento:
            return False
        barra = self.horizontalScrollBar()
        barra.setValue(barra.value() + deslocamento)
        event.accept()
        return True

    def wheelEvent(self, event):  # noqa: N802
        if self._rolar_evento(event):
            return
        super().wheelEvent(event)

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Wheel:
            if self._rolar_evento(event):
                return True
        return super().eventFilter(obj, event)


class GuimmaStudioApp:
    def __init__(self, argv: Sequence[str] | None = None):
        self._argv = argv_com_fonte_padrao(list(argv or sys.argv))
        self.qt_app = QApplication(self._argv)
        self.qt_app.setApplicationName(APP_NOME)
        aplicar_fonte_padrao(self.qt_app)
        self._aplicar_traducao_qt_ptbr()
        self._aplicar_tema_claro_global()
        aplicar_hover_global(self.qt_app)
        self.janela_principal = GuimmaStudioMainWindow()
        self._instalar_nome_fixo_aba_usuario()
        self._instalar_menu_contexto_usuario()
        self._corrigir_layout_aba_usuario()
        try:
            self.janela_principal.ribbon.tabbar.currentChanged.connect(self._on_ribbon_tab_changed)
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
                QLocale.setDefault(QLocale.c())
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

    def _on_ribbon_tab_changed(self, *_args):
        try:
            self._fixar_nome_aba_usuario(self.janela_principal)
            self._corrigir_scroll_ribbon_principal(self.janela_principal)
        except Exception:
            pass

    def _instalar_nome_fixo_aba_usuario(self):
        janela = self.janela_principal
        try:
            rib = janela.ribbon
            if getattr(rib, "_guimma_nome_usuario_fixo", False):
                self._fixar_nome_aba_usuario(janela)
                return
            set_user_tools_original = rib.set_user_tools

            def set_user_tools_fixado(tool_ids: list[str], titulo: str):
                set_user_tools_original(tool_ids, "Usuário")
                self._fixar_nome_aba_usuario(janela)

            rib.set_user_tools = set_user_tools_fixado
            rib._guimma_nome_usuario_fixo = True
            self._fixar_nome_aba_usuario(janela)
        except Exception:
            pass

    def _fixar_nome_aba_usuario(self, janela=None) -> None:
        try:
            janela = janela or self.janela_principal
            rib = janela.ribbon
            index = rib._tab_index_by_id("usuarios")
            if index is None:
                return
            rib._tabs[index].title = "Usuário"
            rib.tabbar.setTabText(index, "Usuário")
        except Exception:
            pass

    def _instalar_menu_contexto_usuario(self):
        janela = self.janela_principal

        def abrir_menu_contexto_aba_ribbon(janela_ref, pos):
            try:
                indice = janela_ref.ribbon.tabbar.tabAt(pos)
                tab_id = janela_ref.ribbon.tab_id_at(indice) if indice >= 0 else None
                if not tab_id:
                    return

                menu = QMenu(janela_ref)
                aplicar_hover_menu(menu)
                submenu_usuarios = menu.addMenu("Usuários")
                acao_add_aba = submenu_usuarios.addAction("Adicionar ferramentas desta aba")
                acao_add_todas = submenu_usuarios.addAction("Adicionar todas as ferramentas para usuário")
                submenu_usuarios.addSeparator()
                acao_resetar = submenu_usuarios.addAction("Resetar barra de usuário padrão")

                acao = menu.exec(janela_ref.ribbon.tabbar.mapToGlobal(pos))
                if acao == acao_add_aba:
                    origem = tab_id
                    if origem == "usuarios":
                        origem = getattr(janela_ref, "_ultima_aba_nao_usuario", "construcao") or "construcao"
                    janela_ref._adicionar_todas_ferramentas_da_aba_id(origem)
                    self._corrigir_layout_aba_usuario()
                elif acao == acao_add_todas:
                    self._adicionar_todas_ferramentas_para_usuario(janela_ref)
                elif acao == acao_resetar:
                    self._resetar_barra_usuario_padrao(janela_ref)
            except Exception as exc:
                try:
                    janela_ref.lbl_status.setText(f"Falha no menu Usuários: {type(exc).__name__}: {exc}")
                except Exception:
                    pass

        janela._abrir_menu_contexto_aba_ribbon = MethodType(abrir_menu_contexto_aba_ribbon, janela)

    def _ids_todas_ferramentas_disponiveis(self, janela) -> list[str]:
        ids: list[str] = []
        rib = janela.ribbon
        for tab in getattr(rib, "_tabs", []) or []:
            if getattr(tab, "tab_id", "") == "usuarios":
                continue
            for grupo in getattr(tab, "groups", []) or []:
                for tool_id in getattr(grupo, "tools", []) or []:
                    if tool_id in getattr(rib, "_tools", {}) and tool_id not in ids:
                        ids.append(tool_id)
        for tool_id in getattr(rib, "_tools", {}).keys():
            if tool_id not in ids:
                ids.append(tool_id)
        return ids

    def _adicionar_todas_ferramentas_para_usuario(self, janela) -> None:
        ids_atuais = list(getattr(janela, "_ferramentas_usuario_ids", []) or [])
        adicionadas = 0
        for tool_id in self._ids_todas_ferramentas_disponiveis(janela):
            if tool_id not in ids_atuais:
                ids_atuais.append(tool_id)
                adicionadas += 1
        janela._ferramentas_usuario_ids = janela._lista_usuario_com_ajuste(ids_atuais)
        janela.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(janela._ferramentas_usuario_ids)
        janela._sincronizar_perfil_usuario_atual()
        janela._atualizar_linha_usuarios()
        janela._sincronizar_menu_barra_usuarios()
        self._corrigir_layout_aba_usuario()
        janela.lbl_status.setText(f"{adicionadas} ferramenta(s) adicionada(s) ao usuário atual.")

    def _resetar_barra_usuario_padrao(self, janela) -> None:
        janela._ferramentas_usuario_ids = janela._lista_usuario_com_ajuste(list(janela.FERRAMENTAS_USUARIO_PADRAO))
        janela._garantir_ajuste_automatico_na_barra_usuario()
        janela.projeto_atual.preferencias_usuario["ferramentas_usuario"] = list(janela._ferramentas_usuario_ids)
        janela._sincronizar_perfil_usuario_atual()
        janela._atualizar_linha_usuarios()
        janela._sincronizar_menu_barra_usuarios()
        self._corrigir_layout_aba_usuario()
        janela.lbl_status.setText("Barra de usuário restaurada para o padrão.")

    def _corrigir_layout_aba_usuario(self, *_args):
        """Compacta abas e impede barras de rolagem visíveis no topo."""
        try:
            from ui import ribbon

            janela = self.janela_principal
            rib = janela.ribbon
            self._fixar_nome_aba_usuario(janela)
            assinatura_scroll = rib.paginas.count()
            if getattr(rib, "_scroll_ribbon_corrigido_assinatura", None) != assinatura_scroll:
                self._corrigir_scroll_ribbon_principal(janela)
                rib._scroll_ribbon_corrigido_assinatura = assinatura_scroll
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
                self._fixar_nome_aba_usuario(janela)
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
                rib._cache_botoes_ribbon_valido = False
                rib._usuario_layout_compacto_assinatura = assinatura
                rib._tema_aplicado_signature = None
                if pagina_visivel == index:
                    rib.paginas.setCurrentIndex(index)
                rib.aplicar_tema(rib._tema_interface)
                area_atual = nova_area
                self._corrigir_scroll_ribbon_principal(janela)
                rib._scroll_ribbon_corrigido_assinatura = rib.paginas.count()

            if hasattr(area_atual, "horizontalScrollBar"):
                area_atual.horizontalScrollBar().setValue(0)
            self._fixar_nome_aba_usuario(janela)
        except Exception:
            return

    def _corrigir_scroll_ribbon_principal(self, janela) -> None:
        """Remove a barra visível do ribbon e faz a faixa rolar com a roda do mouse."""
        try:
            rib = janela.ribbon
            filtros = getattr(janela, "_filtros_scroll_ribbon_principal", [])
            instalados = {id(getattr(filtro, "area", None)) for filtro in filtros}
            for i in range(rib.paginas.count()):
                area = rib.paginas.widget(i)
                if not isinstance(area, QScrollArea):
                    continue
                if getattr(area, "objectName", lambda: "")() == "ScrollLinhaUsuario":
                    continue
                area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                area.horizontalScrollBar().setFixedHeight(0)
                area.setFrameShape(QFrame.NoFrame)
                widget = area.widget()
                if widget is not None:
                    widget.resize(widget.sizeHint())
                    altura = max(1, int(widget.sizeHint().height() + 1))
                    area.setMinimumHeight(altura)
                    area.setMaximumHeight(max(area.maximumHeight(), altura))
                if id(area) not in instalados:
                    filtro = _FiltroScrollHorizontal(area)
                    filtro.instalar()
                    filtros.append(filtro)
                    instalados.add(id(area))
                else:
                    for filtro in filtros:
                        if getattr(filtro, "area", None) is area:
                            filtro.instalar()
                            break
            janela._filtros_scroll_ribbon_principal = filtros
        except Exception:
            return

    def _corrigir_faixa_usuarios_topo(self, janela) -> None:
        """Deixa a linha de ícones rolar horizontalmente sem encavalar."""
        try:
            linha = getattr(janela, "linha_usuario", None)
            if linha is not None:
                self._instalar_scroll_linha_usuario(janela, linha)
                linha.setMinimumSize(0, 0)
                linha.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                layout_linha = getattr(janela, "layout_linha_usuario", None)
                largura_conteudo = self._largura_conteudo_linha_usuario(linha, layout_linha)
                scroll = getattr(janela, "scroll_linha_usuario", None)
                largura_visivel = scroll.viewport().width() if scroll is not None else linha.width()
                linha.setFixedWidth(max(largura_conteudo, largura_visivel, 1))
                linha.setFixedHeight(32)
                if layout_linha is not None:
                    layout_linha.setContentsMargins(2, 0, 2, 0)
                    layout_linha.setSpacing(2)
                    layout_linha.setSizeConstraint(layout_linha.SizeConstraint.SetMinimumSize)
                if scroll is not None:
                    scroll.setFixedHeight(34)
                    scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    scroll.reinstalar_filtros()
                    scroll.widget().updateGeometry()

            painel = getattr(janela, "painel_controles_usuario", None)
            if painel is not None:
                painel.setMinimumWidth(360)
                painel.setMaximumWidth(470)
                painel.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                painel_layout = painel.layout()
                if painel_layout is not None:
                    painel_layout.setContentsMargins(0, 0, 0, 0)
                    painel_layout.setSpacing(8)

            combo = getattr(janela, "combo_perfil_usuario", None)
            if combo is not None:
                combo.setMinimumWidth(105)
                combo.setMaximumWidth(130)
                combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            ajustes_botoes = (
                ("btn_novo_perfil_usuario", "Novo", 62),
                ("btn_salvar_perfil_usuario", "Salvar", 62),
                ("btn_usuario_add_all", "Adicionar", 82),
                ("btn_usuario_limpar", "Limpar", 64),
            )
            for nome_attr, texto, largura in ajustes_botoes:
                botao = getattr(janela, nome_attr, None)
                if botao is None:
                    continue
                botao.setText(texto)
                botao.setMinimumWidth(largura)
                botao.setMaximumWidth(largura)
                botao.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            faixa = getattr(janela, "faixa_usuarios", None)
            if faixa is not None:
                faixa.setMinimumWidth(0)
                faixa.updateGeometry()
        except Exception:
            return

    def _largura_conteudo_linha_usuario(self, linha, layout_linha) -> int:
        if layout_linha is None:
            return max(1, linha.sizeHint().width() + 8)
        margens = layout_linha.contentsMargins()
        espacamento = max(0, int(layout_linha.spacing()))
        widgets = []
        for i in range(layout_linha.count()):
            item = layout_linha.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            widgets.append(widget)
            widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        largura = margens.left() + margens.right() + 8
        for widget in widgets:
            largura += max(widget.minimumWidth(), widget.sizeHint().width(), 30)
        if len(widgets) > 1:
            largura += espacamento * (len(widgets) - 1)
        return max(largura, 1)

    def _instalar_scroll_linha_usuario(self, janela, linha) -> None:
        scroll_existente = getattr(janela, "scroll_linha_usuario", None)
        if scroll_existente is not None:
            try:
                scroll_existente.reinstalar_filtros()
            except Exception:
                pass
            return
        parent = linha.parentWidget()
        layout_parent = parent.layout() if parent is not None else None
        if layout_parent is None:
            return
        indice = -1
        stretch = 1
        for i in range(layout_parent.count()):
            item = layout_parent.itemAt(i)
            if item is not None and item.widget() is linha:
                indice = i
                try:
                    stretch = max(1, layout_parent.stretch(i))
                except Exception:
                    stretch = 1
                break
        if indice < 0:
            return
        layout_parent.removeWidget(linha)
        scroll = _ScrollLinhaUsuario(parent)
        scroll.setWidget(linha)
        janela.scroll_linha_usuario = scroll
        layout_parent.insertWidget(indice, scroll, stretch)
        scroll.horizontalScrollBar().setValue(0)
        scroll.reinstalar_filtros()

    def run(self) -> int:
        self.janela_principal.exibir_inicial()
        return self.qt_app.exec()
