from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from core.projeto import Projeto
from formats.audaces_emf_import import AudacesEMFImport
from formats.audaces_pair_import import AudacesPairImport
from formats.audaces_xml_import import AudacesXMLImport


def _emr(record_type: int, payload: bytes) -> bytes:
    return struct.pack('<II', record_type, len(payload) + 8) + payload


def _sample_emf_bytes() -> bytes:
    # HEADER bounds 0,0,100,60
    header_payload = struct.pack('<4i', 0, 0, 100, 60)
    # POLYGON com 4 pontos fechados
    poly_payload = struct.pack('<4iI', 0, 0, 100, 60, 4) + struct.pack('<8i', 0, 0, 100, 0, 100, 60, 0, 0)
    eof_payload = b''
    return b''.join([
        _emr(1, header_payload),
        _emr(3, poly_payload),
        _emr(14, eof_payload),
    ])


def _sample_xml_text() -> str:
    return '''<?xml version="1.0" encoding="ISO-8859-1"?>
<DATA_FILE_AUDACES>
  <INFO FILE="modelo.adsx" />
  <MODEL NAME_M="Camisa Base" />
  <SIZES_M>
    <SIZE_M NAME_SM="  G2" PERIMETER_SM="123,4" AREA_SM="456,7" />
  </SIZES_M>
  <PATTERNS>
    <PATTERN NAME_P="Frente" DESCRIPTION_P="Frente camisa" FABRIC_P="ALGODAO" QUANTITY_P="1" NOTCHS_P="3">
      <SIZES_P>
        <SIZE_P NAME_SP="G2" PERIMETER_SP="120,0" AREA_SP="450,0" WIDTH_SP="50" HEIGHT_SP="60" />
      </SIZES_P>
    </PATTERN>
  </PATTERNS>
</DATA_FILE_AUDACES>
'''


class TestAudacesEMFXMLImport(unittest.TestCase):
    def test_xml_import(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / '02.xml'
            p.write_text(_sample_xml_text(), encoding='iso-8859-1')
            doc = AudacesXMLImport.abrir(p)
            self.assertEqual(doc.nome_modelo, 'Camisa Base')
            self.assertEqual(doc.tamanhos_modelo[0].nome, 'G2')
            self.assertEqual(len(doc.pecas), 1)

    def test_emf_import(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / '01.emf'
            p.write_bytes(_sample_emf_bytes())
            doc = AudacesEMFImport.abrir(p)
            self.assertGreaterEqual(len(doc.elementos), 1)
            self.assertGreaterEqual(doc.relatorio.get('contornos_fechados', 0), 1)

    def test_pair_import(self):
        with tempfile.TemporaryDirectory() as td:
            emf = Path(td) / '01.emf'
            xml = Path(td) / '02.xml'
            emf.write_bytes(_sample_emf_bytes())
            xml.write_text(_sample_xml_text(), encoding='iso-8859-1')
            projeto = Projeto()
            projeto = AudacesPairImport.importar(emf, xml, projeto)
            info = projeto.preferencias_usuario.get('audaces_emf_xml_importacao', {})
            self.assertEqual(projeto.nome, 'Camisa Base')
            self.assertGreaterEqual(info.get('vetores', 0), 1)
            self.assertIn('audaces_importados_originais', projeto.preferencias_usuario)
            self.assertTrue(Path(info.get('debug_report_path', '')).exists())


if __name__ == '__main__':
    unittest.main()
