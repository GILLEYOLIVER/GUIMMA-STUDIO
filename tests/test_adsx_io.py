from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from core.projeto import Projeto
from formats.adsx_io import ADSXIO, ADSXImportError
from formats.gs_project import GSProjectIO


class ADSXIOTestCase(unittest.TestCase):
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
                pacote.writestr("file.jpg", b"\xff\xd8\xff\xe0fakejpg")
            if incluir_ids:
                pacote.writestr("print/IDS.json", json.dumps({"ids": [1, 2]}))
        return caminho

    def test_abrir_adsx_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = self._criar_adsx(Path(tmp))
            doc = ADSXIO.abrir(caminho)
            self.assertEqual(doc.nome_arquivo, "modelo.adsx")
            self.assertIn("file.ads", doc.arquivos_preservados)
            self.assertEqual(doc.data_xml_normalizado.get("ads_signature"), "CADZ")
            self.assertGreaterEqual(len(doc.moldes), 2)

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
            self.assertIn(adsx_info.get("geometry_confidence"), {"none", "low", "medium", "high"})
            self.assertTrue(adsx_info.get("preview_disponivel"))
            self.assertFalse(adsx_info.get("geometria_convertida", True))
            self.assertFalse(adsx_info.get("elementos_canvas", []))
            self.assertFalse(projeto.documentos[0].moldes)

            caminho_gs = pasta / "teste.gs"
            GSProjectIO.salvar(projeto, caminho_gs)
            reaberto = GSProjectIO.abrir(caminho_gs)
            self.assertIn("audaces_adsx_original", reaberto.para_dict())
            ads_preservado = reaberto.audaces_adsx_original["arquivos_preservados"]["file.ads"]["conteudo_base64"]
            self.assertTrue(base64.b64decode(ads_preservado).startswith(b"CADZ"))

    def test_adsx_invalido(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "invalido.adsx"
            caminho.write_text("nao zip", encoding="utf-8")
            with self.assertRaises(ADSXImportError):
                ADSXIO.abrir(caminho)


if __name__ == "__main__":
    unittest.main()
