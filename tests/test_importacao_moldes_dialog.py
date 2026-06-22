from __future__ import annotations

import os
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    GuimmaStudioMainWindow = None
else:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QMenu

    import ui.janela_principal as janela_principal_module
    from ui.janela_principal import GuimmaStudioMainWindow


@unittest.skipIf(GuimmaStudioMainWindow is None, "PySide6 nao disponivel neste ambiente")
class ImportacaoMoldesDialogTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is not None:
            cls._app = QApplication.instance() or QApplication([])

    def tearDown(self):
        app = QApplication.instance() if QApplication is not None else None
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            if isinstance(widget, QMenu):
                try:
                    widget.close()
                except RuntimeError:
                    pass
        app.processEvents()

    def test_preparar_elementos_aplica_unidade_e_metadados(self):
        elementos = [{"tipo": "polyline", "pontos": [(10.0, 20.0), (30.0, 40.0)], "cor": "#ff5a00"}]
        opcoes = {
            "unidade": "mm",
            "origem": "Gerber",
            "tipo_filtro": "Arquivos DXF (*.dxf)",
            "importar_linha_costura": True,
            "usar_contorno_corte_como_base": False,
        }

        preparados = GuimmaStudioMainWindow._preparar_elementos_importacao_moldes(
            GuimmaStudioMainWindow,
            elementos,
            opcoes,
        )

        self.assertEqual(preparados[0]["pontos"], [(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(preparados[0]["unidade_origem"], "mm")
        self.assertEqual(preparados[0]["origem_importacao"], "Gerber")
        self.assertEqual(preparados[0]["subtipo_importacao"], "costura")
        self.assertTrue(preparados[0]["importar_linha_costura"])
        self.assertFalse(preparados[0]["usar_contorno_corte_como_base"])
        self.assertEqual(elementos[0]["pontos"], [(10.0, 20.0), (30.0, 40.0)])

    def test_preparar_elementos_converte_polegada_para_centimetro(self):
        elementos = [{"tipo": "polyline", "pontos": [(1, 2)]}]
        opcoes = {"unidade": "pol", "origem": "AutoCad"}

        preparados = GuimmaStudioMainWindow._preparar_elementos_importacao_moldes(
            GuimmaStudioMainWindow,
            elementos,
            opcoes,
        )

        self.assertEqual(preparados[0]["pontos"], [(2.54, 5.08)])
        self.assertEqual(preparados[0]["subtipo_importacao"], "contorno_corte")

    def test_origem_inicial_do_menu_sobrescreve_preferencia_salva(self):
        fake = SimpleNamespace(
            projeto_atual=SimpleNamespace(
                preferencias_usuario={
                    "importacao_moldes": {
                        "unidade": "cm",
                        "origem": "Gerber",
                    }
                }
            )
        )
        fake._origens_importacao_moldes = lambda: GuimmaStudioMainWindow._origens_importacao_moldes(fake)

        opcoes = GuimmaStudioMainWindow._opcoes_importacao_moldes_padrao(fake, origem_inicial="Lectra")

        self.assertEqual(opcoes["origem"], "Lectra")

    def test_menu_importacao_agenda_acao_apos_fechar_backstage(self):
        janela = GuimmaStudioMainWindow()
        self.addCleanup(janela.close)
        chamadas = []
        janela._importar_por_tipo = lambda tipo, origem_inicial=None: chamadas.append((tipo, origem_inicial))
        janela.backstage.show()

        menu = janela._criar_menu_importar()
        acao_dxf = next(acao for acao in menu.actions() if acao.text() == "Arquivo DXF")
        with patch.object(janela_principal_module.sys, "platform", "linux"):
            acao_dxf.trigger()

        self.assertEqual(chamadas, [])
        QApplication.processEvents()
        self.assertEqual(chamadas, [("dxf", None)])
        self.assertFalse(janela.backstage.isVisible())

    def test_botao_importacao_continua_como_submenu_do_backstage(self):
        janela = GuimmaStudioMainWindow()
        self.addCleanup(janela.close)

        botao = janela.backstage.botoes["Importar ▸"]

        self.assertIsNone(botao.menu())
        self.assertTrue(janela._item_backstage_tem_submenu("Importar ▸"))
        menu = janela._criar_menu_importar()
        self.assertIn("Arquivos EMF/XML/ADSX/AMKX", [acao.text() for acao in menu.actions()])

    def test_hover_nao_duplica_menu_durante_clique_importar(self):
        janela = GuimmaStudioMainWindow()
        self.addCleanup(janela.close)
        chamadas = []
        botao = janela.backstage.botoes["Importar ▸"]
        janela.backstage.show()
        janela._menu_backstage_exec_aberto = True
        janela._botao_backstage_sob_cursor = lambda _pos: ("Importar ▸", botao)
        janela._abrir_submenu_backstage_hover = lambda texto, botao_arg=None: chamadas.append((texto, botao_arg))

        janela._processar_hover_backstage_global()

        self.assertEqual(chamadas, [])

    def test_submenu_arquivos_avancados_e_preparado_para_clique(self):
        janela = GuimmaStudioMainWindow()
        self.addCleanup(janela.close)

        menu = janela._criar_menu_importar()
        janela._preparar_submenus_backstage_exec(menu, "Importar ▸")
        acao_adv = next(acao for acao in menu.actions() if acao.text() == "Arquivos avancados")
        submenu = acao_adv.menu()
        popup_chamado = []
        submenu.popup = lambda pos: popup_chamado.append(pos)
        submenu.raise_ = lambda: None

        janela._mostrar_submenu_backstage_exec(menu, acao_adv)

        self.assertIs(janela._menu_backstage_exec_submenu_atual, submenu)
        self.assertTrue(getattr(submenu, "_menu_backstage", False))
        self.assertEqual(len(popup_chamado), 1)

    def test_subitem_arquivos_avancados_agenda_importacao(self):
        janela = GuimmaStudioMainWindow()
        self.addCleanup(janela.close)
        chamadas = []
        janela._importar_por_tipo = lambda tipo, origem_inicial=None: chamadas.append((tipo, origem_inicial))
        janela.backstage.show()

        menu = janela._criar_menu_importar()
        acao_adv = next(acao for acao in menu.actions() if acao.text() == "Arquivos avancados")
        submenu = acao_adv.menu()
        acao_emf = next(acao for acao in submenu.actions() if acao.text() == "Arquivos EMF (*.emf)")
        with patch.object(janela_principal_module.sys, "platform", "linux"):
            janela._executar_acao_importacao_avancada(acao_emf)

        self.assertEqual(chamadas, [])
        QApplication.processEvents()
        self.assertEqual(chamadas, [("audaces_emf", None)])

    def test_submenu_arquivos_avancados_mapeia_xml_para_importacao(self):
        janela = GuimmaStudioMainWindow()
        self.addCleanup(janela.close)
        chamadas = []
        janela._importar_por_tipo = lambda tipo, origem_inicial=None: chamadas.append((tipo, origem_inicial))
        janela.backstage.show()

        menu = janela._criar_menu_importar()
        acao_adv = next(acao for acao in menu.actions() if acao.text() == "Arquivos avancados")
        submenu = acao_adv.menu()
        acao_xml = next(acao for acao in submenu.actions() if acao.text() == "Arquivos XML (*.xml)")
        with patch.object(janela_principal_module.sys, "platform", "linux"):
            janela._executar_acao_importacao_avancada(acao_xml)

        self.assertEqual(chamadas, [])
        QApplication.processEvents()
        self.assertEqual(chamadas, [("audaces_xml", None)])

    def test_emf_e_xml_audaces_resolvem_o_mesmo_par_automaticamente(self):
        janela = GuimmaStudioMainWindow()
        self.addCleanup(janela.close)
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td)
            emf = pasta / "modelo 6414.emf"
            xml = pasta / "modelo 6414.xml"
            emf.write_bytes(b"emf")
            xml.write_text("<xml />", encoding="utf-8")

            self.assertEqual(janela._resolver_par_audaces_emf_xml(emf), (str(emf), str(xml)))
            self.assertEqual(janela._resolver_par_audaces_emf_xml(xml), (str(emf), str(xml)))

    def test_moldes_reais_importados_sao_centralizados_no_canvas(self):
        class CanvasFake:
            def __init__(self):
                self.cena = SimpleNamespace(elementos=[])
                self.zoom = 1.0
                self.origem_cena = QPointF(0.0, 0.0)
                self.atualizacoes = 0

            def width(self):
                return 1000

            def height(self):
                return 500

            def set_zoom(self, zoom):
                self.zoom = float(zoom)

            def update(self):
                self.atualizacoes += 1

        janela = GuimmaStudioMainWindow()
        self.addCleanup(janela.close)
        canvas = CanvasFake()
        zooms_informados = []
        area = SimpleNamespace(
            canvas=canvas,
            _on_zoom_changed=lambda zoom: zooms_informados.append(float(zoom)),
        )
        molde = SimpleNamespace(
            nome="Molde central",
            id="M1",
            partes=[
                SimpleNamespace(
                    pontos=[
                        SimpleNamespace(x=100.0, y=20.0),
                        SimpleNamespace(x=110.0, y=20.0),
                        SimpleNamespace(x=110.0, y=70.0),
                        SimpleNamespace(x=100.0, y=70.0),
                    ]
                )
            ],
        )

        carregados = janela._carregar_moldes_reais_no_canvas(area, [molde])

        centro_view_x = canvas.origem_cena.x() + (canvas.width() / (2 * canvas.zoom))
        centro_view_y = canvas.origem_cena.y() + (canvas.height() / (2 * canvas.zoom))
        self.assertEqual(carregados, 1)
        self.assertEqual(len(canvas.cena.elementos), 1)
        self.assertAlmostEqual(centro_view_x, 105.0)
        self.assertAlmostEqual(centro_view_y, 45.0)
        self.assertTrue(zooms_informados)
        self.assertGreater(canvas.atualizacoes, 0)


if __name__ == "__main__":
    unittest.main()
