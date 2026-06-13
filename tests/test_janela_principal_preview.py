from __future__ import annotations

import os
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    GuimmaStudioMainWindow = None
else:
    from PySide6.QtWidgets import QApplication, QFileDialog, QFileSystemModel

    from config import EXTENSAO_PROJETO
    from ui.janela_principal import GuimmaStudioMainWindow


@unittest.skipIf(GuimmaStudioMainWindow is None, "PySide6 nao disponivel neste ambiente")
class JanelaPrincipalPreviewTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_thumbnail_projeto_desenha_fio_e_graduacao(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        molde = {
            "tipo": "polyline",
            "molde": True,
            "cor": "#ff9d00",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
            "fio_origem": [2.0, 2.5],
            "fio_fim": [8.0, 2.5],
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "M", "base": True},
                {"ativo": True, "tamanho": "G", "base": False, "cor": "#f0ff00"},
            ],
            "graduacao_pontos": {
                "0": {"valores": {"G": {"dx": 1.0, "dy": -0.4}}},
                "1": {"valores": {"G": {"dx": 1.0, "dy": -0.4}}},
                "2": {"valores": {"G": {"dx": 1.0, "dy": 0.4}}},
                "3": {"valores": {"G": {"dx": 1.0, "dy": 0.4}}},
            },
        }

        imagem = GuimmaStudioMainWindow._gerar_thumbnail_elementos(janela, [molde], 420, 240)

        self.assertIsNotNone(imagem)
        self.assertFalse(imagem.isNull())
        tem_fio = False
        tem_graduacao = False
        for y in range(imagem.height()):
            for x in range(imagem.width()):
                cor = imagem.pixelColor(x, y)
                if cor.green() > 170 and cor.blue() > 130 and cor.red() < 150:
                    tem_fio = True
                if cor.red() > 190 and cor.green() > 190 and cor.blue() < 130:
                    tem_graduacao = True
            if tem_fio and tem_graduacao:
                break

        self.assertTrue(tem_fio)
        self.assertTrue(tem_graduacao)

    def test_dialogo_projeto_aplica_filtro_gs_no_modelo_de_arquivos(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        filtro = f"Projeto GUIMMA (*{EXTENSAO_PROJETO})"
        with tempfile.TemporaryDirectory() as pasta_tmp:
            pasta = Path(pasta_tmp)
            (pasta / "molde.gs").write_text("", encoding="utf-8")
            (pasta / "audio.mp3").write_text("", encoding="utf-8")

            dialog = QFileDialog(None, "Abrir", str(pasta), filtro)
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setNameFilters([filtro])
            dialog.selectNameFilter(filtro)
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

            GuimmaStudioMainWindow._aplicar_filtro_extensao_dialogo_arquivo(
                janela, dialog, filtro, [EXTENSAO_PROJETO]
            )

            modelos = GuimmaStudioMainWindow._modelos_sistema_arquivos_dialogo(janela, dialog)
            self.assertTrue(modelos)
            for modelo in modelos:
                self.assertIsInstance(modelo, QFileSystemModel)
                self.assertEqual(modelo.nameFilters(), [f"*{EXTENSAO_PROJETO}"])
                self.assertFalse(modelo.nameFilterDisables())


if __name__ == "__main__":
    unittest.main()
