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


def _sample_segmented_open_emf_bytes() -> bytes:
    # HEADER bounds 0,0,100,60 and rclFrame 10 cm x 6 cm.
    header_payload = struct.pack('<8i', 0, 0, 100, 60, 0, 0, 10000, 6000)

    def line(x1: int, y1: int, x2: int, y2: int) -> bytes:
        bounds = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        payload = struct.pack('<4iI', *bounds, 2) + struct.pack('<4i', x1, y1, x2, y2)
        return _emr(4, payload)

    eof_payload = b''
    return b''.join([
        _emr(1, header_payload),
        line(0, 0, 100, 0),
        line(100, 0, 100, 60),
        line(100, 60, 0, 60),
        line(0, 60, 0, 0),
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

    def test_direct_emf_import_unites_open_segments_as_mold(self):
        with tempfile.TemporaryDirectory() as td:
            emf = Path(td) / 'segmentado.emf'
            emf.write_bytes(_sample_segmented_open_emf_bytes())
            projeto = AudacesPairImport.importar_apenas_emf(emf, Projeto())
            info = projeto.preferencias_usuario.get('audaces_emf_importacao', {})
            self.assertGreaterEqual(info.get('segmentos_unidos', 0), 3)
            self.assertEqual(info.get('moldes_reais'), 1)
            self.assertEqual(projeto.nome, 'segmentado')
            self.assertEqual(projeto.documentos[0].nome, 'segmentado')
            self.assertEqual(len(projeto.documentos[0].moldes), 1)
            moldes = [el for el in info.get('elementos_canvas', []) if el.get('molde')]
            self.assertTrue(moldes)
            self.assertEqual(str(moldes[0].get('nome_molde', '')), 'K1')
            self.assertFalse(moldes[0].get('mostrar_nome', True))
            self.assertEqual(projeto.documentos[0].moldes[0].nome, 'K1')
            pontos = [pt for el in info.get('elementos_canvas', []) for pt in el.get('pontos', [])]
            xs = [float(x) for x, _ in pontos]
            ys = [float(y) for _, y in pontos]
            self.assertAlmostEqual((min(xs) + max(xs)) / 2.0, 0.0, places=6)
            self.assertAlmostEqual((min(ys) + max(ys)) / 2.0, 0.0, places=6)
            self.assertEqual(info.get('fator_escala_final'), AudacesPairImport.ESCALA_CALIBRACAO_EMF_DIRETO)
            self.assertEqual(info.get('curvas_reconstruidas'), 0)

    @unittest.skipUnless(
        (Path.home() / 'Desktop' / '6414 BLUSA GOLA PADRE E ROLITE MANGA DE PREGAS.emf').exists(),
        'arquivo EMF real do usuario nao esta disponivel',
    )
    def test_direct_emf_real_6414_is_processed_as_molds(self):
        emf = Path.home() / 'Desktop' / '6414 BLUSA GOLA PADRE E ROLITE MANGA DE PREGAS.emf'
        projeto = AudacesPairImport.importar_apenas_emf(emf, Projeto())
        info = projeto.preferencias_usuario.get('audaces_emf_importacao', {})
        self.assertEqual(projeto.nome, emf.stem)
        self.assertEqual(projeto.documentos[0].nome, emf.stem)
        self.assertGreaterEqual(info.get('moldes_reais', 0), 5)
        depois = info.get('diagnostico_depois', {})
        self.assertLess(depois.get('elementos_canvas_final', 10**9), info.get('elementos_canvas_antes_uniao', 0))
        self.assertGreater(info.get('segmentos_unidos', 0), 500)
        self.assertGreater(info.get('curvas_reconstruidas', 0), 0)
        self.assertEqual(info.get('canvas_origem'), 'moldes_reais_processados')
        self.assertTrue(info.get('centralizacao_importacao', {}).get('aplicado'))
        self.assertGreaterEqual(info.get('fios_detectados', 0), 2)
        self.assertIsNotNone(info.get('grade_detectada'))
        self.assertEqual(info.get('nomes_moldes_origem'), 'indice_temporario_sem_strings_texto_no_emf')
        self.assertGreaterEqual(depois.get('grupos_graduados_detectados', 0), 1)
        self.assertGreaterEqual(depois.get('contornos_graduacao_ocultos', 0), 1)
        moldes_canvas = [
            el
            for el in info.get('elementos_canvas', [])
            if isinstance(el, dict) and el.get('molde')
        ]
        self.assertNotIn(emf.stem, {str(el.get('nome_molde') or '') for el in moldes_canvas})
        self.assertTrue(any(el.get('graduacao_contornos_importados') for el in moldes_canvas))
        cores = {el.get('cor') for el in info.get('elementos_canvas', []) if isinstance(el, dict)}
        self.assertGreaterEqual(len(cores), 4)
        pontos = []
        for el in info.get('elementos_canvas', []):
            if not isinstance(el, dict):
                continue
            pontos.extend(el.get('pontos', []) or [])
            for item in el.get('graduacao_contornos_importados', []) or []:
                if isinstance(item, dict):
                    pontos.extend(item.get('pontos', []) or [])
        xs = [float(x) for x, _ in pontos]
        ys = [float(y) for _, y in pontos]
        self.assertAlmostEqual((min(xs) + max(xs)) / 2.0, 0.0, places=6)
        self.assertAlmostEqual((min(ys) + max(ys)) / 2.0, 0.0, places=6)


if __name__ == '__main__':
    unittest.main()
