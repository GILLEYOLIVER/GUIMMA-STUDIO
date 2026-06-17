from __future__ import annotations

import os
import unittest
from importlib.util import find_spec

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    RibbonWidget = None
else:
    from PySide6.QtWidgets import QApplication, QScrollArea

    from ui.ribbon import RibbonWidget


@unittest.skipIf(QApplication is None, "PySide6 nao disponivel neste ambiente")
class RibbonPerformanceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication(["guimma-test"])

    def test_set_user_tools_reaproveita_pagina_quando_assinatura_nao_muda(self):
        ribbon = RibbonWidget(include_tabbar=False)
        index = ribbon._tab_index_by_id("usuarios")
        self.assertIsNotNone(index)

        ribbon.set_user_tools(["selecionar", "reta"], "Usuario")
        pagina_original = ribbon.paginas.widget(index)

        ribbon.set_user_tools(["selecionar", "reta"], "Usuario")

        self.assertIs(ribbon.paginas.widget(index), pagina_original)

    def test_set_user_tools_reconstroi_pagina_quando_ferramentas_mudam(self):
        ribbon = RibbonWidget(include_tabbar=False)
        index = ribbon._tab_index_by_id("usuarios")
        self.assertIsNotNone(index)

        ribbon.set_user_tools(["selecionar"], "Usuario")
        pagina_original = ribbon.paginas.widget(index)

        ribbon.set_user_tools(["selecionar", "reta"], "Usuario")

        self.assertIsNot(ribbon.paginas.widget(index), pagina_original)

    def test_ribbon_constroi_abas_sob_demanda(self):
        ribbon = RibbonWidget(include_tabbar=False)
        self.assertIn(0, ribbon._paginas_construidas)
        self.assertNotIn(1, ribbon._paginas_construidas)
        self.assertIsInstance(ribbon.paginas.widget(0), QScrollArea)

        ribbon.tabbar.setCurrentIndex(1)

        self.assertIn(1, ribbon._paginas_construidas)
        self.assertIsInstance(ribbon.paginas.widget(1), QScrollArea)

    def test_todas_as_abas_podem_ser_construidas_sob_demanda(self):
        ribbon = RibbonWidget(include_tabbar=False)

        for index in range(ribbon.tabbar.count()):
            ribbon.tabbar.setCurrentIndex(index)

        self.assertEqual(ribbon._paginas_construidas, set(range(ribbon.tabbar.count())))
        for index in range(ribbon.tabbar.count()):
            self.assertIsInstance(ribbon.paginas.widget(index), QScrollArea)


if __name__ == "__main__":
    unittest.main()
