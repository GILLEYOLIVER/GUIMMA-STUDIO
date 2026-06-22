from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.projeto import Projeto
from formats.audaces_emf_import import AudacesEMFImport, EMFVectorElement
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

    def test_resolver_tamanho_base_prefere_base_explicita_a_menor_tamanho(self):
        labels = ['PP', 'P', 'M', 'G', 'GG', 'G1', 'G2']
        self.assertEqual(AudacesPairImport._resolver_tamanho_base(labels, ['"P"']), 'P')

    def test_resolver_tamanho_base_usa_nome_grade_parenteses(self):
        labels = ['PP', 'P', 'M', 'G', 'GG', 'G1', 'G2']
        self.assertEqual(
            AudacesPairImport._resolver_tamanho_base(labels, [], nome_grade='PP-G2(P)'),
            'P',
        )

    def test_resolver_tamanho_base_fallback_por_padrao_de_grade(self):
        self.assertEqual(AudacesPairImport._resolver_tamanho_base(['P', 'M', 'G'], []), 'M')
        self.assertEqual(AudacesPairImport._resolver_tamanho_base(['PP', 'P', 'M', 'G'], []), 'P')
        self.assertEqual(AudacesPairImport._resolver_tamanho_base(['36', '38', '40', '42', '44'], []), '40')

    def test_grade_xml_doc_consolida_base_mesmo_com_primeira_peca_sem_base(self):
        xml_doc = SimpleNamespace(
            pecas=[
                SimpleNamespace(
                    tamanho_base=None,
                    tamanhos=[
                        SimpleNamespace(tamanho='PP'),
                        SimpleNamespace(tamanho='P'),
                    ],
                ),
                SimpleNamespace(
                    tamanho_base='"P"',
                    tamanhos=[
                        SimpleNamespace(tamanho='M'),
                        SimpleNamespace(tamanho='G'),
                    ],
                ),
            ],
            tamanhos_modelo=[],
            bruto_normalizado={
                'tag': 'DATA_FILE_AUDACES',
                'atributos': {},
                'filhos': [{'tag': 'GRADE', 'atributos': {'NAME_GRAD': 'PP-G(P)'}, 'filhos': []}],
            },
        )

        labels, base = AudacesPairImport._grade_xml_doc(xml_doc)

        self.assertEqual(labels, ['PP', 'P', 'M', 'G'])
        self.assertEqual(base, 'P')

    def test_grade_por_cores_com_xml_garante_base_unica(self):
        elementos = [
            SimpleNamespace(cor='#00d000', metadados={'subtipo_audaces': 'contorno'}),
            SimpleNamespace(cor='#0080ff', metadados={'subtipo_audaces': 'contorno'}),
            SimpleNamespace(cor='#ffffff', metadados={'subtipo_audaces': 'contorno'}),
        ]

        grade = AudacesPairImport._grade_detectada_por_cores(
            elementos,
            grade_labels=['PP', 'P', 'M', 'G'],
            tamanho_base='"P"',
        )

        self.assertIsNotNone(grade)
        _nome, linhas, base = grade
        self.assertEqual(base, 'P')
        self.assertEqual([linha['tamanho'] for linha in linhas if linha.get('base')], ['P'])
        self.assertEqual([linha['tamanho'] for linha in linhas if linha.get('visivel_emf')], ['P', 'M', 'G'])
        self.assertFalse(next(linha for linha in linhas if linha['tamanho'] == 'PP')['visivel_emf'])

    def test_regularizar_graduacao_importada_gera_pp_e_tamanhos_faltantes(self):
        elemento = {
            'tipo': 'polyline',
            'molde': True,
            'pontos': [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            'graduacao_tamanhos': [
                {'tamanho': 'PP', 'base': False, 'cor': '#6a6a6a'},
                {'tamanho': 'P', 'base': True, 'cor': '#00d000'},
                {'tamanho': 'M', 'base': False, 'cor': '#0080ff'},
                {'tamanho': 'G', 'base': False, 'cor': '#ffffff'},
                {'tamanho': 'GG', 'base': False, 'cor': '#ff00ff'},
                {'tamanho': 'G1', 'base': False, 'cor': '#ff8000'},
                {'tamanho': 'G2', 'base': False, 'cor': '#aa00ff'},
            ],
            'graduacao_contornos_importados': [
                {
                    'tamanho': 'P',
                    'base': True,
                    'cor': '#00d000',
                    'pontos': [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
                },
                {
                    'tamanho': 'G2',
                    'base': False,
                    'cor': '#aa00ff',
                    'pontos': [(-5.0, -5.0), (15.0, -5.0), (15.0, 15.0), (-5.0, 15.0), (-5.0, -5.0)],
                },
            ],
        }

        rel = AudacesPairImport._regularizar_graduacao_importada(elemento)

        self.assertTrue(rel.get('aplicado'))
        self.assertEqual([item['tamanho'] for item in elemento['graduacao_contornos_importados']], ['P', 'G2'])
        contornos = elemento['graduacao_contornos_regularizados_preview']
        self.assertEqual([item['tamanho'] for item in contornos], ['PP', 'M', 'G', 'GG', 'G1'])
        self.assertEqual([item['tamanho'] for item in contornos if item.get('base')], [])
        pp = next(item for item in contornos if item['tamanho'] == 'PP')
        self.assertTrue(pp['sintetico'])
        xs_pp = [x for x, _y in pp['pontos']]
        ys_pp = [y for _x, y in pp['pontos']]
        self.assertGreater(min(xs_pp), 0.0)
        self.assertGreater(min(ys_pp), 0.0)
        self.assertLess(max(xs_pp), 10.0)
        self.assertLess(max(ys_pp), 10.0)
        tabela = elemento.get('graduacao_tabela_derivada')
        self.assertEqual(tabela.get('modo'), 'dx_dy')
        self.assertEqual(tabela.get('base'), 'P')
        self.assertFalse(tabela.get('regras_exatas'))
        self.assertFalse(elemento.get('graduacao_preferir_tabela_dxdy'))
        self.assertFalse(elemento.get('graduacao_regras_exatas'))
        self.assertFalse(elemento.get('graduacao_renderizar_regularizada'))
        self.assertFalse(elemento.get('graduacao_renderizar_por_tabela_derivada'))
        self.assertNotIn('graduacao_tabela', elemento)
        self.assertIn('PP', tabela['pontos']['0']['valores'])
        self.assertIn('G2', tabela['pontos']['0']['valores'])
        dx_pp = tabela['pontos']['0']['valores']['PP']['dx']
        dy_pp = tabela['pontos']['0']['valores']['PP']['dy']
        self.assertGreater(abs(dx_pp) + abs(dy_pp), 0.0)

    def test_regularizar_pp_usa_dimensoes_xml_quando_nao_ha_contorno_menor_real(self):
        elemento = {
            'tipo': 'polyline',
            'molde': True,
            'pontos': [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            'graduacao_dimensoes_xml': {
                'PP': {'largura': 9.0, 'altura': 9.0},
                'P': {'largura': 10.0, 'altura': 10.0},
                'M': {'largura': 12.0, 'altura': 12.0},
            },
            'graduacao_tamanhos': [
                {'tamanho': 'PP', 'base': False, 'cor': '#bdbdbd'},
                {'tamanho': 'P', 'base': True, 'cor': '#00d000'},
                {'tamanho': 'M', 'base': False, 'cor': '#0080ff'},
            ],
            'graduacao_contornos_importados': [
                {
                    'tamanho': 'P',
                    'base': True,
                    'cor': '#00d000',
                    'pontos': [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
                },
                {
                    'tamanho': 'M',
                    'base': False,
                    'cor': '#0080ff',
                    'pontos': [(-1.0, -1.0), (11.0, -1.0), (11.0, 11.0), (-1.0, 11.0), (-1.0, -1.0)],
                },
            ],
        }

        AudacesPairImport._regularizar_graduacao_importada(elemento)

        pp = next(item for item in elemento['graduacao_contornos_regularizados_preview'] if item['tamanho'] == 'PP')
        xs = [x for x, _y in pp['pontos']]
        ys = [y for _x, y in pp['pontos']]
        self.assertAlmostEqual(min(xs), 0.5)
        self.assertAlmostEqual(max(xs), 9.5)
        self.assertAlmostEqual(min(ys), 0.5)
        self.assertAlmostEqual(max(ys), 9.5)
        self.assertEqual(pp['metodo_regularizacao'], 'dimensoes_xml_base')

    def test_regularizar_com_dimensoes_xml_preserva_contorno_real_para_render(self):
        elemento = {
            'tipo': 'polyline',
            'molde': True,
            'pontos': [(0.0, 0.0), (4.0, 0.0), (5.0, 2.0), (6.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
            'graduacao_dimensoes_xml': {
                'P': {'largura': 10.0, 'altura': 8.0},
                'M': {'largura': 12.0, 'altura': 10.0},
            },
            'graduacao_tamanhos': [
                {'tamanho': 'P', 'base': True, 'cor': '#00d000'},
                {'tamanho': 'M', 'base': False, 'cor': '#0080ff'},
            ],
            'graduacao_contornos_importados': [
                {
                    'tamanho': 'P',
                    'base': True,
                    'cor': '#00d000',
                    'pontos': [(0.0, 0.0), (4.0, 0.0), (5.0, 2.0), (6.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)],
                },
                {
                    'tamanho': 'M',
                    'base': False,
                    'cor': '#0080ff',
                    'pontos': [(-1.0, -1.0), (11.0, -1.0), (11.0, 9.0), (-1.0, 9.0), (-1.0, -1.0)],
                },
            ],
        }

        rel = AudacesPairImport._regularizar_graduacao_importada(elemento)

        self.assertEqual(rel.get('metodo'), 'contornos_reais_emf_com_complementos_por_campo_dxdy')
        self.assertFalse(elemento.get('graduacao_renderizar_regularizada'))
        self.assertFalse(elemento.get('graduacao_renderizar_por_tabela_derivada'))
        self.assertEqual(elemento['graduacao_contornos_regularizados_preview'], [])
        contorno_m = next(item for item in elemento['graduacao_contornos_importados'] if item['tamanho'] == 'M')
        self.assertEqual(contorno_m['pontos'][0], (-1.0, -1.0))

    def test_agrupar_graduacao_aceita_contorno_quase_fechado_do_emf(self):
        base = EMFVectorElement(
            tipo='polyline',
            pontos=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            fechado=True,
            cor='#00d000',
            espessura=1.0,
            bbox=(0.0, 0.0, 10.0, 10.0),
            raw_record_type=87,
            metadados={'subtipo_audaces': 'contorno'},
        )
        tamanho_m = EMFVectorElement(
            tipo='polyline',
            pontos=[
                (-1.0, -1.0),
                (5.0, -1.0),
                (11.0, -1.0),
                (11.0, 5.0),
                (11.0, 11.0),
                (5.0, 11.0),
                (-1.0, 11.0),
                (-1.0, 5.0),
                (-1.0, -0.25),
            ],
            fechado=False,
            cor='#0080ff',
            espessura=1.0,
            bbox=(-1.0, -1.0, 11.0, 11.0),
            raw_record_type=87,
            metadados={'subtipo_audaces': 'linha_interna'},
        )
        grade = (
            'P-M(P)',
            [
                {'ativo': True, 'tamanho': 'P', 'cor': '#00d000', 'base': True},
                {'ativo': True, 'tamanho': 'M', 'cor': '#0080ff', 'base': False},
            ],
            'P',
        )

        grupos = AudacesPairImport._agrupar_contornos_graduados_emf([base, tamanho_m], grade)

        self.assertEqual(len(grupos), 1)
        self.assertEqual([item['tamanho'] for item in grupos[0]['contornos']], ['P', 'M'])
        self.assertTrue(next(item for item in grupos[0]['contornos'] if item['tamanho'] == 'M')['fechado_forcado'])
        self.assertEqual(tamanho_m.metadados.get('subtipo_audaces'), 'graduacao_importada')

    def test_controles_importados_incluem_principais_e_auxiliares(self):
        elemento = {
            'tipo': 'polyline',
            'molde': True,
            'pontos': [
                (0.0, 0.0),
                (2.0, 0.0),
                (5.0, 0.0),
                (8.0, 0.0),
                (10.0, 0.0),
                (10.0, 2.0),
                (10.0, 5.0),
                (10.0, 8.0),
                (10.0, 10.0),
                (8.0, 10.0),
                (5.0, 10.0),
                (2.0, 10.0),
                (0.0, 10.0),
                (0.0, 8.0),
                (0.0, 5.0),
                (0.0, 2.0),
                (0.0, 0.0),
            ],
        }

        AudacesPairImport._aplicar_controles_cantos_canvas(elemento)

        self.assertEqual(
            elemento.get('controle_cantos'),
            [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        )
        self.assertIn((5.0, 0.0), elemento.get('controle_auxiliares'))
        self.assertIn((10.0, 5.0), elemento.get('controle_auxiliares'))
        self.assertEqual(len(elemento.get('pontos_auxiliares')), len(elemento.get('controle_auxiliares')))
        self.assertEqual(elemento.get('pontos_auxiliares')[0].get('origem'), 'audaces_emf_auxiliar')

    def test_controles_importados_mantem_curva_suave_como_auxiliar(self):
        elemento = {
            'tipo': 'polyline',
            'molde': True,
            'pontos': [
                (10.0, 0.0),
                (7.07, 7.07),
                (0.0, 10.0),
                (-7.07, 7.07),
                (-10.0, 0.0),
                (-7.07, -7.07),
                (0.0, -10.0),
                (7.07, -7.07),
                (10.0, 0.0),
            ],
        }

        AudacesPairImport._aplicar_controles_cantos_canvas(elemento)

        self.assertEqual(elemento.get('controle_cantos'), [])
        self.assertEqual(len(elemento.get('controle_auxiliares')), 8)
        self.assertEqual(len(elemento.get('pontos_auxiliares')), 8)

    def test_controles_importados_promovem_quina_media_local(self):
        cantos = AudacesPairImport._controle_cantos_por_quinas([
            (-1.0, 0.0),
            (0.0, 0.0),
            (1.0, 0.0),
            (2.0, 1.0),
            (3.0, 2.0),
            (4.0, 3.0),
        ])

        self.assertIn((1.0, 0.0), cantos)

    def test_regularizar_graduacao_importada_preserva_tamanho_existente_real(self):
        elemento = {
            'tipo': 'polyline',
            'molde': True,
            'pontos': [
                (0.0, 0.0),
                (8.0, 0.0),
                (10.0, 4.0),
                (8.0, 8.0),
                (0.0, 8.0),
                (-2.0, 4.0),
                (0.0, 0.0),
            ],
            'graduacao_tamanhos': [
                {'tamanho': 'P', 'base': True, 'cor': '#00d000'},
                {'tamanho': 'M', 'base': False, 'cor': '#0080ff'},
            ],
            'graduacao_contornos_importados': [
                {
                    'tamanho': 'P',
                    'base': True,
                    'cor': '#00d000',
                    'pontos': [
                        (0.0, 0.0),
                        (8.0, 0.0),
                        (10.0, 4.0),
                        (8.0, 8.0),
                        (0.0, 8.0),
                        (-2.0, 4.0),
                        (0.0, 0.0),
                    ],
                },
                {
                    'tamanho': 'M',
                    'base': False,
                    'cor': '#0080ff',
                    'pontos': [
                        (-1.0, -1.0),
                        (9.0, -1.0),
                        (16.0, 5.0),
                        (13.0, 8.5),
                        (9.0, 9.0),
                        (-1.0, 9.0),
                        (-3.0, 5.0),
                        (-1.0, -1.0),
                    ],
                },
            ],
        }

        AudacesPairImport._regularizar_graduacao_importada(elemento)

        self.assertEqual(elemento['graduacao_contornos_regularizados_preview'], [])
        self.assertFalse(elemento.get('graduacao_renderizar_regularizada'))
        self.assertEqual(
            len(elemento['graduacao_contornos_importados'][1]['pontos']),
            8,
        )
        self.assertEqual(
            elemento['graduacao_regularizada_por_base']['metodo'],
            'contornos_reais_emf_com_complementos_por_campo_dxdy',
        )
        self.assertEqual(elemento['graduacao_dxdy_resumo']['base'], 'P')
        self.assertEqual(elemento['graduacao_dxdy_resumo']['tamanhos'], ['M'])
        self.assertFalse(elemento.get('graduacao_preferir_tabela_dxdy'))
        self.assertFalse(elemento.get('graduacao_regras_exatas'))
        self.assertNotIn('graduacao_tabela', elemento)
        self.assertIn('graduacao_tabela_derivada', elemento)
        self.assertFalse(elemento.get('graduacao_renderizar_por_tabela_derivada'))

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

    def test_direct_emf_6414_usa_adsx_adjacente_para_escala_e_grade_base(self):
        raiz = Path(__file__).resolve().parents[1]
        emf = raiz / '6414 BLUSA GOLA PADRE E ROLITE MANGA DE PREGAS.emf'
        adsx = emf.with_suffix('.adsx')
        self.assertTrue(emf.exists())
        self.assertTrue(adsx.exists())

        projeto = AudacesPairImport.importar_apenas_emf(emf, Projeto())
        info = projeto.preferencias_usuario.get('audaces_emf_importacao', {})
        grade = info.get('grade_detectada') or {}
        moldes = [
            el
            for el in info.get('elementos_canvas', [])
            if isinstance(el, dict) and el.get('molde')
        ]

        self.assertTrue(info.get('xml_adjacente_usado'))
        self.assertEqual(info.get('xml_adjacente_tipo'), 'adsx_data_xml')
        self.assertEqual(info.get('unidade_resultado'), 'cm_calibrado_por_xml_adjacente')
        self.assertGreater(float(info.get('escala_y_aplicada', 0.0)), float(info.get('escala_x_aplicada', 0.0)))
        self.assertEqual(info.get('diagnostico_file_ads', {}).get('assinatura'), 'CADZ')
        self.assertFalse(info.get('diagnostico_file_ads', {}).get('regras_graduacao_decodificadas'))
        self.assertFalse(info.get('graduacao_regras_exatas'))
        self.assertEqual(grade.get('nome'), 'PP-G2(P)')
        self.assertEqual(grade.get('tamanho_base'), 'P')
        self.assertEqual(grade.get('quantidade_tamanhos'), 7)
        self.assertGreaterEqual(len(moldes), 5)
        calibracao = info.get('calibracao_dimensoes_xml') or {}
        self.assertTrue(calibracao.get('aplicado'))
        self.assertGreaterEqual(calibracao.get('moldes_calibrados', 0), 5)

        def _bbox_dimensoes(pontos):
            pontos_validos = [(float(x), float(y)) for x, y in pontos]
            if len(pontos_validos) >= 2 and pontos_validos[0] == pontos_validos[-1]:
                pontos_validos = pontos_validos[:-1]
            xs = [x for x, _y in pontos_validos]
            ys = [y for _x, y in pontos_validos]
            return max(xs) - min(xs), max(ys) - min(ys)

        for molde in moldes:
            dimensoes_xml = molde.get('graduacao_dimensoes_xml') or {}
            base_nome = str(molde.get('tamanho_base_detectado') or '').strip()
            if not dimensoes_xml or not base_nome:
                continue
            dimensoes_base = dimensoes_xml.get(base_nome) or dimensoes_xml.get(base_nome.upper())
            if not dimensoes_base:
                continue
            largura, altura = _bbox_dimensoes(molde.get('pontos') or [])
            self.assertAlmostEqual(largura, float(dimensoes_base.get('largura')), places=6)
            self.assertAlmostEqual(altura, float(dimensoes_base.get('altura')), places=6)

        primeiro_com_grade = next(el for el in moldes if el.get('graduacao_tamanhos'))
        self.assertEqual(
            [linha.get('tamanho') for linha in primeiro_com_grade.get('graduacao_tamanhos')],
            ['PP', 'P', 'M', 'G', 'GG', 'G1', 'G2'],
        )
        self.assertEqual(
            [linha.get('tamanho') for linha in primeiro_com_grade.get('graduacao_tamanhos') if linha.get('base')],
            ['P'],
        )
        self.assertEqual(primeiro_com_grade.get('tamanho_base'), 'P')
        self.assertEqual(primeiro_com_grade.get('tamanho_base_detectado'), 'P')
        self.assertFalse(primeiro_com_grade.get('graduacao_regras_exatas'))
        self.assertEqual(
            [item.get('tamanho') for item in primeiro_com_grade.get('graduacao_contornos_regularizados_preview')],
            ['PP'],
        )
        self.assertTrue(
            next(item for item in primeiro_com_grade.get('graduacao_contornos_regularizados_preview') if item.get('tamanho') == 'PP').get('sintetico')
        )
        self.assertFalse(primeiro_com_grade.get('graduacao_renderizar_regularizada'))
        self.assertFalse(primeiro_com_grade.get('graduacao_suavizar_topologia_base'))
        self.assertIn('M', [item.get('tamanho') for item in primeiro_com_grade.get('graduacao_contornos_importados', [])])
        self.assertEqual(primeiro_com_grade.get('graduacao_tabela_derivada', {}).get('modo'), 'dx_dy')
        self.assertEqual(primeiro_com_grade.get('graduacao_tabela_derivada', {}).get('base'), 'P')
        self.assertNotIn('graduacao_tabela', primeiro_com_grade)
        self.assertFalse(primeiro_com_grade.get('graduacao_preferir_tabela_dxdy'))
        self.assertIn(
            'PP',
            primeiro_com_grade.get('graduacao_tabela_derivada', {}).get('pontos', {}).get('0', {}).get('valores', {}),
        )
        self.assertTrue(primeiro_com_grade.get('render_smooth'))
        self.assertTrue(any(el.get('controle_cantos') for el in moldes))
        self.assertTrue(any(el.get('pontos_controle_principais') for el in moldes))
        self.assertTrue(any(int(el.get('cantos_preservados_importacao') or 0) >= 2 for el in moldes))

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
        if info.get('xml_adjacente_usado'):
            self.assertTrue(info.get('calibracao_dimensoes_xml', {}).get('aplicado'))
        if info.get('xml_adjacente_usado'):
            self.assertEqual(info.get('nomes_moldes_origem'), 'xml_adjacente')
        else:
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
            pontos.extend(el.get('controle_cantos', []) or [])
            pontos.extend(el.get('controle_auxiliares', []) or [])
            pontos.extend(el.get('pontos_controle_principais', []) or [])
            pontos.extend(el.get('pontos_auxiliares', []) or [])
            for item in el.get('graduacao_contornos_importados', []) or []:
                if isinstance(item, dict):
                    pontos.extend(item.get('pontos', []) or [])
            for item in el.get('graduacao_contornos_regularizados_preview', []) or []:
                if isinstance(item, dict):
                    pontos.extend(item.get('pontos', []) or [])
        def _xy(pt):
            if isinstance(pt, dict):
                return float(pt['x']), float(pt['y'])
            return float(pt[0]), float(pt[1])
        xy = [_xy(pt) for pt in pontos]
        xs = [x for x, _ in xy]
        ys = [y for _, y in xy]
        self.assertAlmostEqual((min(xs) + max(xs)) / 2.0, 0.0, places=6)
        self.assertAlmostEqual((min(ys) + max(ys)) / 2.0, 0.0, places=6)


if __name__ == '__main__':
    unittest.main()
