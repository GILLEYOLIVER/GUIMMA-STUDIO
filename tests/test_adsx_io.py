from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage

from core.projeto import Projeto
from formats.adsx_io import ADSXIO, ADSXImportError
from formats.gs_project import GSProjectIO


class ADSXIOTestCase(unittest.TestCase):
    def _preview_jpg_bytes(self) -> bytes:
        img = QImage(120, 80, QImage.Format_RGB32)
        img.fill(QColor("#000000"))
        for y in range(15, 62):
            for x in range(18, 88):
                if x in {18, 19, 86, 87} or y in {15, 16, 60, 61}:
                    img.setPixelColor(x, y, QColor("#00d084"))
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        img.save(buffer, "JPG")
        return bytes(buffer.data())

    def _criar_adsx(self, pasta: Path, nome: str = "modelo.adsx", incluir_jpg: bool = True, incluir_ids: bool = True) -> Path:
        caminho = pasta / nome
        data_xml = (
            "<Projeto nome='Modelo Camisa'><Moldes>"
            "<Molde nome='Frente' tamanho='M' quantidade='1' area='123.45' perimetro='56.7' largura='30' altura='45' />"
            "<Molde nome='Costas' tamanho='G' quantidade='2' area='130.55' perimetro='58.1' largura='31' altura='46' />"
            "</Moldes></Projeto>"
        )
        with ZipFile(caminho, "w", compression=ZIP_DEFLATED) as pacote:
            pacote.writestr("index.json", json.dumps({"versao": 1}, ensure_ascii=False))
            pacote.writestr("data.xml", data_xml.encode("utf-8"))
            pacote.writestr("file.ads", b"CADZ vs9.1\x00\x01\x02")
            if incluir_jpg:
                pacote.writestr("file.jpg", self._preview_jpg_bytes())
            if incluir_ids:
                pacote.writestr("print/IDS.json", json.dumps({"ids": [1, 2]}))
        return caminho

    def _criar_amkx(self, pasta: Path, nome: str = "encaixe.amkx") -> Path:
        caminho = pasta / nome
        file_info = {
            "name": "encaixe.amkx",
            "models": {
                "Modelo Teste": {
                    "file": "modelo.adsx",
                    "patterns": "3",
                    "sizes": ["P", "M", "G"],
                    "quantity": {"1": {"P": "1", "M": "1", "G": "1"}},
                }
            },
            "markers": {
                "1": {
                    "placed": "3",
                    "length": "120.5",
                    "width": "80",
                    "area": "900",
                    "cutPerimeter": "250.75",
                }
            },
        }
        with ZipFile(caminho, "w", compression=ZIP_DEFLATED) as pacote:
            pacote.writestr("index.json", json.dumps({"files": {"file": "file.amk", "info": "fileInformation.json"}}, ensure_ascii=False))
            pacote.writestr("fileInformation.json", json.dumps(file_info, ensure_ascii=False))
            pacote.writestr("file.amk", b"AMK fake binary")
            pacote.writestr("1.png", b"\x89PNG\r\n\x1a\nfakepng")
            pacote.writestr("print/IDS.json", json.dumps({"ids": []}))
        return caminho

    def test_abrir_adsx_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = self._criar_adsx(Path(tmp))
            doc = ADSXIO.abrir(caminho)
            self.assertEqual(doc.nome_arquivo, "modelo.adsx")
            self.assertEqual(doc.tipo_pacote, "adsx")
            self.assertIn("file.ads", doc.arquivos_preservados)
            self.assertEqual(doc.data_xml_normalizado.get("ads_signature"), "CADZ")
            self.assertGreaterEqual(len(doc.moldes), 2)

    def test_abrir_amkx_preserva_binario_preview_e_metadados(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = self._criar_amkx(Path(tmp))
            doc = ADSXIO.abrir(caminho)
            self.assertEqual(doc.tipo_pacote, "amkx")
            self.assertIn("file.amk", doc.arquivos_preservados)
            self.assertIn("1.png", doc.arquivos_preservados)
            self.assertEqual(doc.arquivos_preservados["file.amk"].tipo, "audaces_binary_amk")
            self.assertEqual(doc.arquivos_preservados["1.png"].tipo, "preview_image_png")
            self.assertGreaterEqual(len(doc.moldes), 2)

            projeto = ADSXIO.importar_para_projeto(caminho, Projeto())
            info = projeto.preferencias_usuario.get("adsx_importacao", {})
            self.assertEqual(info.get("tipo_pacote"), "amkx")
            self.assertEqual(info.get("binario_audaces"), "file.amk")
            self.assertEqual(info.get("previews"), ["1.png"])

    def test_importar_e_persistir_em_gs(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            adsx = self._criar_adsx(pasta, incluir_jpg=True, incluir_ids=False)
            projeto = Projeto()
            ADSXIO.importar_para_projeto(adsx, projeto)

            self.assertIn("audaces_adsx_original", projeto.para_dict())
            self.assertTrue(projeto.audaces_adsx_original.get("arquivos_preservados", {}).get("file.ads"))
            self.assertTrue(projeto.audaces_adsx_original.get("arquivos_preservados", {}).get("file.jpg"))
            adsx_info = projeto.preferencias_usuario.get("adsx_importacao", {})
            self.assertIn("diagnostico_file_ads", adsx_info)
            self.assertIn(adsx_info.get("geometry_confidence"), {"none", "low", "medium", "high", "preview_trace"})
            self.assertTrue(adsx_info.get("preview_disponivel"))
            self.assertFalse(adsx_info.get("geometria_convertida"))
            self.assertFalse(adsx_info.get("geometria_aproximada"))
            self.assertTrue(adsx_info.get("preview_apenas_referencia"))
            self.assertIn("motivo_sem_geometria", adsx_info)
            elementos = adsx_info.get("elementos_canvas", [])
            self.assertEqual(elementos, [])
            self.assertFalse(projeto.documentos[0].moldes)

            caminho_gs = pasta / "teste.gs"
            GSProjectIO.salvar(projeto, caminho_gs)
            reaberto = GSProjectIO.abrir(caminho_gs)
            self.assertIn("audaces_adsx_original", reaberto.para_dict())
            ads_preservado = reaberto.audaces_adsx_original["arquivos_preservados"]["file.ads"]["conteudo_base64"]
            self.assertTrue(base64.b64decode(ads_preservado).startswith(b"CADZ"))

    def test_salvar_gs_anexa_arquivos_importados(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            conteudo = b"DXF fake"
            projeto = Projeto()
            projeto.preferencias_usuario["arquivos_importados_anexos"] = [
                {
                    "id": "abc123",
                    "nome": "molde.dxf",
                    "anexo_zip": "attachments/imports/abc123_molde.dxf",
                    "conteudo_base64": base64.b64encode(conteudo).decode("ascii"),
                }
            ]

            caminho_gs = pasta / "teste.gs"
            GSProjectIO.salvar(projeto, caminho_gs)

            with ZipFile(caminho_gs, "r") as pacote:
                self.assertEqual(pacote.read("attachments/imports/abc123_molde.dxf"), conteudo)
            reaberto = GSProjectIO.abrir(caminho_gs)
            anexo = reaberto.preferencias_usuario["arquivos_importados_anexos"][0]
            self.assertEqual(base64.b64decode(anexo["conteudo_base64"]), conteudo)

    def test_adsx_invalido(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "invalido.adsx"
            caminho.write_text("nao zip", encoding="utf-8")
            with self.assertRaises(ADSXImportError):
                ADSXIO.abrir(caminho)


if __name__ == "__main__":
    unittest.main()
