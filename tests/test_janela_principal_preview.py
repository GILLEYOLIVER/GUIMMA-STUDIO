from __future__ import annotations

import os
import re
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    GuimmaStudioMainWindow = None
else:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPageSize, QPainter
    from PySide6.QtPrintSupport import QPrinter
    from PySide6.QtWidgets import QApplication, QFileDialog, QFileSystemModel, QTreeView

    from config import EXTENSAO_PROJETO
    from ui.janela_principal import GuimmaStudioMainWindow


@unittest.skipIf(GuimmaStudioMainWindow is None, "PySide6 nao disponivel neste ambiente")
class JanelaPrincipalPreviewTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    @staticmethod
    def _pixels_nao_brancos(imagem: QImage) -> tuple[list[int], list[int]]:
        xs: list[int] = []
        ys: list[int] = []
        for y in range(imagem.height()):
            for x in range(imagem.width()):
                cor = imagem.pixelColor(x, y)
                if cor.red() < 245 or cor.green() < 245 or cor.blue() < 245:
                    xs.append(x)
                    ys.append(y)
        return xs, ys

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

    def test_dialogo_arquivo_mantem_coluna_nome_larga(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        filtro = "Arquivos DXF (*.dxf)"
        with tempfile.TemporaryDirectory() as pasta_tmp:
            pasta = Path(pasta_tmp)
            (pasta / "arquivo_com_nome_grande_para_importacao.dxf").write_text("", encoding="utf-8")

            dialog = QFileDialog(None, "Importar DXF", str(pasta), filtro)
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setViewMode(QFileDialog.ViewMode.Detail)
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            dialog.show()
            QApplication.processEvents()

            GuimmaStudioMainWindow._melhorar_coluna_nome_dialogo_arquivo(janela, dialog)
            QApplication.processEvents()

            arvores = dialog.findChildren(QTreeView)
            self.assertTrue(arvores)
            self.assertGreaterEqual(dialog.minimumWidth(), 760)
            self.assertTrue(any(arvore.columnWidth(0) >= 500 for arvore in arvores))
            dialog.close()

    def test_abas_sem_nome_sao_renumeradas_quando_sobra_uma(self):
        class _AbasFake:
            def __init__(self, nomes):
                self.nomes = list(nomes)

            def count(self):
                return len(self.nomes)

            def tabText(self, indice):
                return self.nomes[indice]

            def setTabText(self, indice, nome):
                self.nomes[indice] = nome

        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        janela.abas_documentos = _AbasFake(["(Sem nome)-2"])

        GuimmaStudioMainWindow._renumerar_abas_sem_nome(janela)

        self.assertEqual(janela.abas_documentos.nomes, ["(Sem nome)"])

    def test_hpgl_plotagem_percentual_100_mantem_escala_real(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        retangulo = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 20.0), (0.0, 20.0), (0.0, 0.0)],
        }

        corpo, _largura, _altura = GuimmaStudioMainWindow._gerar_hpgl2_do_molde(
            janela,
            [retangulo],
            {
                "percentual": 100.0,
                "plotter_props": {
                    "largura_papel_cm": 185.0,
                    "tamanho_pagina_cm": 115.0,
                    "fator_x": 1.0,
                    "fator_y": 1.0,
                },
            },
        )

        coords = [(int(x), int(y)) for x, y in re.findall(r"(-?\d+),(-?\d+)", corpo)]
        xs = [x for x, _y in coords]
        ys = [y for _x, y in coords]
        self.assertEqual(max(xs) - min(xs), 4000)
        self.assertEqual(max(ys) - min(ys), 8000)

    def test_elementos_saida_usa_indices_selecionados_do_canvas(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        molde_pequeno = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 20.0), (0.0, 20.0), (0.0, 0.0)],
        }
        molde_grande = {
            "tipo": "polyline",
            "pontos": [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0), (100.0, 100.0)],
        }
        canvas = SimpleNamespace(cena=SimpleNamespace(elementos=[molde_pequeno, molde_grande]), _selecionados={0})
        janela._area_documento_atual = lambda: SimpleNamespace(canvas=canvas)

        selecionados = GuimmaStudioMainWindow._obter_elementos_saida(janela, True)
        bbox = GuimmaStudioMainWindow._bbox_elementos_saida(janela, selecionados)

        self.assertEqual(selecionados, [molde_pequeno])
        self.assertEqual(bbox, (0.0, 0.0, 10.0, 20.0))

    def test_printer_impressao_abre_com_a4_por_padrao(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)

        printer = GuimmaStudioMainWindow._criar_printer_impressao(janela)

        self.assertEqual(printer.pageLayout().pageSize().id(), QPageSize.PageSizeId.A4)

    def test_pixels_por_cm_impressao_usa_tamanho_fisico_da_pagina(self):
        class _DispositivoImpressora:
            def pageRect(self, unidade):
                if unidade == QPrinter.Unit.DevicePixel:
                    return QRectF(0, 0, 2480, 3508)
                if unidade == QPrinter.Unit.Millimeter:
                    return QRectF(0, 0, 210, 297)
                return QRectF()

            def logicalDpiX(self):
                return 96

            def logicalDpiY(self):
                return 96

        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)

        px_cm_x, px_cm_y = GuimmaStudioMainWindow._pixels_por_cm_dispositivo(
            janela,
            _DispositivoImpressora(),
            QRectF(0, 0, 2480, 3508),
        )

        self.assertAlmostEqual(px_cm_x, 2480 / 21.0, places=3)
        self.assertAlmostEqual(px_cm_y, 3508 / 29.7, places=3)

    def test_impressao_percentual_100_mantem_escala_real(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        retangulo = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (10.0, 0.0), (10.0, 20.0), (0.0, 20.0), (0.0, 0.0)],
        }
        imagem = QImage(1200, 1200, QImage.Format_ARGB32)
        imagem.setDotsPerMeterX(round(100 / 0.0254))
        imagem.setDotsPerMeterY(round(100 / 0.0254))
        imagem.fill(QColor("#ffffff"))
        painter = QPainter(imagem)
        try:
            GuimmaStudioMainWindow._desenhar_elementos_em_painter(
                janela,
                painter,
                QRectF(0, 0, imagem.width(), imagem.height()),
                [retangulo],
                {
                    "usar_percentual": True,
                    "percentual": 100.0,
                    "escala_x": 1.0,
                    "escala_y": 1.0,
                    "em_cores": False,
                    "estilo_borda": "nenhum",
                },
            )
        finally:
            painter.end()

        xs: list[int] = []
        ys: list[int] = []
        for y in range(imagem.height()):
            for x in range(imagem.width()):
                cor = imagem.pixelColor(x, y)
                if cor.red() < 245 or cor.green() < 245 or cor.blue() < 245:
                    xs.append(x)
                    ys.append(y)

        self.assertTrue(xs)
        largura_px = max(xs) - min(xs)
        altura_px = max(ys) - min(ys)
        esperado_largura = (10.0 / 2.54) * imagem.logicalDpiX()
        esperado_altura = (20.0 / 2.54) * imagem.logicalDpiY()
        self.assertAlmostEqual(largura_px, esperado_largura, delta=5)
        self.assertAlmostEqual(altura_px, esperado_altura, delta=5)

    def test_impressao_percentual_100_preserva_posicao_vertical_do_canvas(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        molde_superior = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)],
        }
        molde_inferior = {
            "tipo": "polyline",
            "pontos": [(12.0, 16.0), (14.0, 16.0), (14.0, 18.0), (12.0, 18.0), (12.0, 16.0)],
        }
        imagem = QImage(1200, 1200, QImage.Format_ARGB32)
        imagem.setDotsPerMeterX(round(100 / 0.0254))
        imagem.setDotsPerMeterY(round(100 / 0.0254))
        imagem.fill(QColor("#ffffff"))
        painter = QPainter(imagem)
        try:
            GuimmaStudioMainWindow._desenhar_elementos_em_painter(
                janela,
                painter,
                QRectF(0, 0, imagem.width(), imagem.height()),
                [molde_superior, molde_inferior],
                {
                    "usar_percentual": True,
                    "percentual": 100.0,
                    "escala_x": 1.0,
                    "escala_y": 1.0,
                    "em_cores": False,
                    "estilo_borda": "nenhum",
                    "margem_sup": 0.0,
                    "margem_esq": 0.0,
                    "margem_dir": 0.0,
                    "margem_inf": 0.0,
                },
            )
        finally:
            painter.end()

        superiores: list[int] = []
        inferiores: list[int] = []
        for y in range(imagem.height()):
            for x in range(imagem.width()):
                cor = imagem.pixelColor(x, y)
                if cor.red() < 245 or cor.green() < 245 or cor.blue() < 245:
                    if x < 250:
                        superiores.append(y)
                    elif x > 350:
                        inferiores.append(y)

        self.assertTrue(superiores)
        self.assertTrue(inferiores)
        self.assertLess(sum(superiores) / len(superiores), sum(inferiores) / len(inferiores))

    def test_impressao_tamanho_folha_usa_margem_segura_a4(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        retangulo = {
            "tipo": "polyline",
            "pontos": [(0.0, 0.0), (50.0, 0.0), (50.0, 80.0), (0.0, 80.0), (0.0, 0.0)],
        }
        imagem = QImage(2100, 2970, QImage.Format_ARGB32)
        imagem.setDotsPerMeterX(10000)
        imagem.setDotsPerMeterY(10000)
        imagem.fill(QColor("#ffffff"))
        painter = QPainter(imagem)
        try:
            GuimmaStudioMainWindow._desenhar_elementos_em_painter(
                janela,
                painter,
                QRectF(0, 0, imagem.width(), imagem.height()),
                [retangulo],
                {
                    "usar_percentual": False,
                    "percentual": 100.0,
                    "escala_x": 1.0,
                    "escala_y": 1.0,
                    "em_cores": False,
                    "estilo_borda": "nenhum",
                    "margem_sup": 0.0,
                    "margem_esq": 0.0,
                    "margem_dir": 0.0,
                    "margem_inf": 0.0,
                    "margem_segura_a4": True,
                },
            )
        finally:
            painter.end()

        xs, ys = self._pixels_nao_brancos(imagem)
        self.assertTrue(xs)
        self.assertGreaterEqual(min(xs), 95)
        self.assertGreaterEqual(min(ys), 95)
        self.assertLessEqual(max(xs), imagem.width() - 95)
        self.assertLessEqual(max(ys), imagem.height() - 95)

    def test_proximo_nome_sem_nome_reusa_primeiro_indice_livre(self):
        class _AbasFake:
            def __init__(self, nomes):
                self.nomes = list(nomes)

            def count(self):
                return len(self.nomes)

            def tabText(self, indice):
                return self.nomes[indice]

        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        janela.abas_documentos = _AbasFake(["Modelo", "(Sem nome)-2"])

        nome = GuimmaStudioMainWindow._proximo_nome_aba_sem_nome(janela)

        self.assertEqual(nome, "(Sem nome)")

    def test_memoria_dialogos_arquivo_guarda_pastas_por_fluxo(self):
        janela = GuimmaStudioMainWindow.__new__(GuimmaStudioMainWindow)
        janela.projeto_atual = SimpleNamespace(preferencias_usuario={})
        janela._arquivo_atual = None
        salvamentos = []
        janela._timer_salvar_preferencias_app = None
        janela._salvar_preferencias_app = lambda: salvamentos.append(True)

        with tempfile.TemporaryDirectory() as pasta_abrir, tempfile.TemporaryDirectory() as pasta_salvar:
            arquivo_abertura = Path(pasta_abrir) / f"modelo{EXTENSAO_PROJETO}"
            destino_salvar = Path(pasta_salvar) / f"saida{EXTENSAO_PROJETO}"

            GuimmaStudioMainWindow._memorizar_local_dialogo(janela, "abertura", arquivo_abertura)
            GuimmaStudioMainWindow._memorizar_local_dialogo(
                janela,
                "salvamento",
                destino_salvar,
                modo_salvar=True,
            )

            pasta_abertura = GuimmaStudioMainWindow._diretorio_memorizado_dialogo(janela, "abertura")
            pasta_salvamento = GuimmaStudioMainWindow._diretorio_memorizado_dialogo(
                janela,
                "salvamento",
                modo_salvar=True,
            )

        locais = janela.projeto_atual.preferencias_usuario["locais_dialogos_arquivo"]
        self.assertEqual(pasta_abertura, pasta_abrir)
        self.assertEqual(pasta_salvamento, pasta_salvar)
        self.assertEqual(locais["abertura"], pasta_abrir)
        self.assertEqual(locais["salvamento"], pasta_salvar)
        self.assertEqual(locais["geral"], pasta_salvar)
        self.assertTrue(salvamentos)

    def test_alertas_salvamento_detectam_nome_repetido_e_tamanho_diferente(self):
        grade_exg = [
            {"tamanho": "PP"},
            {"tamanho": "P", "base": True},
            {"tamanho": "M"},
            {"tamanho": "G"},
            {"tamanho": "GG"},
            {"tamanho": "EXG"},
            {"tamanho": "G2"},
        ]
        grade_g1 = [
            {"tamanho": "PP"},
            {"tamanho": "P", "base": True},
            {"tamanho": "M"},
            {"tamanho": "G"},
            {"tamanho": "GG"},
            {"tamanho": "G1"},
            {"tamanho": "G2"},
        ]
        elementos = [
            {
                "tipo": "polyline",
                "molde": True,
                "nome_molde": "K3",
                "graduacao_grade_nome": "PP-G2(P)",
                "graduacao_tamanhos": grade_exg,
                "graduacao_pontos": {"0": {"valores": {"EXG": {"dx": 1.0, "dy": 0.0}}}},
            },
            {
                "tipo": "polyline",
                "molde": True,
                "nome_molde": "K3",
                "graduacao_grade_nome": "PP-G2(P)",
                "graduacao_tamanhos": grade_g1,
                "graduacao_pontos": {"0": {"valores": {"G1": {"dx": 1.0, "dy": 0.0}}}},
            },
        ]

        alertas = GuimmaStudioMainWindow._coletar_alertas_moldes_elementos(
            elementos,
            validar_ponto_cam=False,
        )

        self.assertEqual(len(alertas), 2)
        problemas = "\n".join("\n".join(alerta["problemas"]) for alerta in alertas)
        self.assertIn("Nome do molde repetido", problemas)
        self.assertIn("Nome do tamanho diferente", problemas)
        self.assertIn("EXG", problemas)
        self.assertIn("G1", problemas)


if __name__ == "__main__":
    unittest.main()
