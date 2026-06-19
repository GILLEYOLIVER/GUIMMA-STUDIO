from __future__ import annotations

import os
import unittest
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    _bbox_visual_molde = None
    _converter_ponto_visual_entre_moldes = None
    FLAGS_VISUALIZACAO_MOLDE = ()
    MoldeRef = None
    NumeroLimpoDoubleSpinBox = None
    PreviewMoldeWidget = None
    PropriedadesMoldesDialog = None
    FerramentaPropriedades = None
    QApplication = None
    QComboBox = None
    QGroupBox = None
    QIcon = None
    QLabel = None
    QLineEdit = None
    QPointF = None
    QTableWidget = None
    QTreeWidget = None
    QTreeWidgetItem = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QIcon, QPainterPath
    from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox, QLabel, QLineEdit, QTableWidget, QTreeWidget, QTreeWidgetItem

    from tools.propriedades_tool import (
        CHAVE_VISUALIZACAO_CUSTOMIZADA,
        FLAGS_VISUALIZACAO_MOLDE,
        Ferramenta as FerramentaPropriedades,
        MoldeRef,
        NumeroLimpoDoubleSpinBox,
        PreviewMoldeWidget,
        PropriedadesMoldesDialog,
        _bbox_visual_molde,
        _converter_ponto_visual_entre_moldes,
    )


@unittest.skipIf(_bbox_visual_molde is None, "PySide6 não disponível neste ambiente")
class PropriedadesVisualizacaoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    class _CheckFake:
        def __init__(self, marcado: bool = False):
            self._marcado = bool(marcado)

        def isChecked(self) -> bool:
            return self._marcado

        def setChecked(self, marcado: bool):
            self._marcado = bool(marcado)

    def test_converte_posicao_visual_proporcionalmente_entre_moldes(self):
        origem = {
            "pontos": [(100.0, 200.0), (300.0, 200.0), (300.0, 300.0), (100.0, 300.0)],
        }
        destino = {
            "pontos": [(10.0, 20.0), (30.0, 20.0), (30.0, 60.0), (10.0, 60.0)],
        }

        convertido = _converter_ponto_visual_entre_moldes(
            [150.0, 225.0],
            _bbox_visual_molde(origem),
            _bbox_visual_molde(destino),
        )

        self.assertEqual(convertido, [15.0, 30.0])

    def test_mantem_deslocamento_externo_do_texto_ao_aplicar_todos(self):
        origem = {
            "pontos": [(100.0, 200.0), (300.0, 200.0), (300.0, 300.0), (100.0, 300.0)],
        }
        destino = {
            "pontos": [(10.0, 20.0), (30.0, 20.0), (30.0, 60.0), (10.0, 60.0)],
        }

        convertido = _converter_ponto_visual_entre_moldes(
            [50.0, 350.0],
            _bbox_visual_molde(origem),
            _bbox_visual_molde(destino),
        )

        self.assertEqual(convertido, [5.0, 80.0])

    def test_config_visual_numeros_nao_forca_exibicao(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.cmb_elementos_molde = SimpleNamespace(currentText=lambda: "Números")
        dialog.ed_altura_texto = SimpleNamespace(value=lambda: 0.42)
        molde = {"mostrar_numeros": False}

        PropriedadesMoldesDialog._salvar_config_visual_molde(dialog, molde)

        self.assertFalse(molde["mostrar_numeros"])
        self.assertEqual(molde["numero_altura_cm"], 0.42)

    def test_config_visual_numeros_aceita_rotulo_sem_acento(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.cmb_elementos_molde = SimpleNamespace(currentText=lambda: "Numeros")
        dialog.ed_altura_texto = SimpleNamespace(value=lambda: 1.35)
        molde = {"mostrar_numeros": True}

        PropriedadesMoldesDialog._salvar_config_visual_molde(dialog, molde)

        self.assertEqual(molde["numero_altura_cm"], 1.35)

    def test_config_visual_texto_e_fio_nao_forcam_checkbox_ligada(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.ed_altura_texto = SimpleNamespace(value=lambda: 2.4)
        dialog.ed_angulo_texto = SimpleNamespace(value=lambda: 15.0)
        dialog.ed_espaco_linhas = SimpleNamespace(value=lambda: 0.5)
        dialog.ed_referencia = SimpleNamespace(currentText=lambda: "Livre")
        dialog.ed_alinhamento = SimpleNamespace(currentText=lambda: "Direita")
        dialog.cmb_elementos_molde = SimpleNamespace(currentText=lambda: "Nome")
        molde = {"mostrar_nome": False}

        PropriedadesMoldesDialog._salvar_config_visual_molde(dialog, molde)

        self.assertFalse(molde["mostrar_nome"])
        self.assertEqual(molde["texto_nome_altura_cm"], 2.4)
        self.assertEqual(molde["texto_nome_angulo"], 15.0)
        self.assertEqual(molde["alinhamento_texto_nome"], "Direita")

        dialog.cmb_elementos_molde = SimpleNamespace(currentText=lambda: "Fio")
        molde_fio = {"mostrar_fio": False}

        PropriedadesMoldesDialog._salvar_config_visual_molde(dialog, molde_fio)

        self.assertFalse(molde_fio["mostrar_fio"])

    def test_aplicar_visualizacao_em_lote_nao_forca_texto_ou_fio_visivel(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog._salvar_margens_no_molde = lambda *args, **kwargs: None
        molde = {"mostrar_nome": False, "mostrar_fio": False}
        dados = {
            "bbox_origem": None,
            "cor": "#ffffff",
            "margens": {},
            "textos": {},
            "fio": {},
            "numeros": {},
            "visual_observacoes": False,
            "mostrar_nome": False,
            "mostrar_fio": False,
            "chave_visual": "nome",
            "texto_altura_cm": 3.2,
            "texto_angulo": 5.0,
            "espaco_linhas": 0.33,
            "referencia_texto": "Livre",
            "alinhamento_texto": "Centro",
        }

        PropriedadesMoldesDialog._aplicar_visualizacao_em_molde(dialog, molde, dados)

        self.assertFalse(molde["mostrar_nome"])
        self.assertFalse(molde["mostrar_fio"])
        self.assertEqual(molde["texto_nome_altura_cm"], 3.2)

    def test_carregar_elemento_visual_preenche_campos_do_elemento_correto(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.cmb_elementos_molde = QComboBox()
        dialog.cmb_elementos_molde.addItems(["Nenhum", "Nome", "Descrição", "Observações", "Fio", "Números"])
        dialog.ed_referencia = QComboBox()
        dialog.ed_referencia.addItems(["Livre", "Centro centro", "Abaixo direita"])
        dialog.ed_alinhamento = QComboBox()
        dialog.ed_alinhamento.addItems(["Esquerda", "Centro", "Direita"])
        dialog.ed_angulo_texto = NumeroLimpoDoubleSpinBox()
        dialog.ed_altura_texto = NumeroLimpoDoubleSpinBox()
        dialog.ed_espaco_linhas = NumeroLimpoDoubleSpinBox()
        dialog.ed_nome_visualizacao = QLineEdit()
        dialog.lbl_nome_visualizacao = QLabel()
        molde = {
            "nome_molde": "K2",
            "descricao": "DESC",
            "texto_nome_altura_cm": 9.0,
            "texto_descricao_altura_cm": 1.25,
            "texto_descricao_angulo": 12.0,
            "espaco_linhas_texto_descricao": 0.75,
            "referencia_texto_descricao": "Abaixo direita",
            "alinhamento_texto_descricao": "Direita",
        }

        PropriedadesMoldesDialog._carregar_controles_visual_elemento(dialog, molde, "Descrição")

        self.assertEqual(dialog.ed_nome_visualizacao.text(), "DESC")
        self.assertEqual(dialog.ed_referencia.currentText(), "Abaixo direita")
        self.assertEqual(dialog.ed_alinhamento.currentText(), "Direita")
        self.assertEqual(dialog.ed_altura_texto.value(), 1.25)
        self.assertEqual(dialog.ed_angulo_texto.value(), 12.0)
        self.assertEqual(dialog.ed_espaco_linhas.value(), 0.75)

    def test_sincronizar_graduacao_propriedades_fica_no_rascunho(self):
        class _SignalFake:
            def __init__(self):
                self.emissoes = 0

            def emit(self):
                self.emissoes += 1

        class _CanvasFake:
            def __init__(self):
                self.elementos_alterados = _SignalFake()
                self.updates = 0
                self.rascunho_visualizacao = None

            def update(self):
                self.updates += 1

            def set_visualizacao_rascunho(self, elementos):
                self.rascunho_visualizacao = elementos

        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog._suspender_auto_aplicar = False
        dialog.canvas = _CanvasFake()
        dialog.cmb_grade_tamanhos = QComboBox()
        dialog.cmb_grade_tamanhos.addItem("P-G(M)")
        dialog._graduacao_linhas = [
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
        ]
        rascunho = {}
        real = {}
        dialog._moldes_alvo_graduacao = lambda: [rascunho]
        dialog._moldes_reais_alvo_graduacao = lambda: [real]
        dialog._sincronizar_valores_graduacao_tamanhos = lambda *args, **kwargs: None
        dialog._elementos_edicao = lambda: [rascunho]

        PropriedadesMoldesDialog._sincronizar_gradacao_no_molde(dialog)

        self.assertEqual(rascunho["graduacao_grade_nome"], "P-G(M)")
        self.assertIn("graduacao_tamanhos", rascunho)
        self.assertNotIn("graduacao_grade_nome", real)
        self.assertEqual(dialog.canvas.elementos_alterados.emissoes, 0)
        self.assertEqual(dialog.canvas.rascunho_visualizacao[0]["graduacao_grade_nome"], "P-G(M)")
        self.assertEqual(dialog.canvas.rascunho_visualizacao[0]["_indice_visualizacao_rascunho"], 0)

    def test_flags_visualizacao_sao_lidos_e_aplicados_no_molde(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        for attr, _chave, padrao in FLAGS_VISUALIZACAO_MOLDE:
            setattr(dialog, attr, self._CheckFake(not padrao))

        flags = PropriedadesMoldesDialog._ler_flags_visualizacao_formulario(dialog)
        molde = {}
        PropriedadesMoldesDialog._aplicar_flags_visualizacao_molde(molde, flags)

        for _attr, chave, padrao in FLAGS_VISUALIZACAO_MOLDE:
            self.assertEqual(flags[chave], not padrao)
            self.assertEqual(molde[chave], not padrao)
        self.assertTrue(molde[CHAVE_VISUALIZACAO_CUSTOMIZADA])

    def test_preencher_flags_visualizacao_normaliza_molde_legado_para_novo_padrao(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        checks = {}
        for attr, _chave, _padrao in FLAGS_VISUALIZACAO_MOLDE:
            checks[attr] = self._CheckFake(False)
            setattr(dialog, attr, checks[attr])

        molde = {"mostrar_graduacao": False, "visual_tecido": True}
        PropriedadesMoldesDialog._preencher_flags_visualizacao(dialog, molde)

        self.assertTrue(checks["chk_graduacao"].isChecked())
        self.assertFalse(checks["chk_tecido_visual"].isChecked())
        self.assertTrue(checks["chk_mostrar_nome"].isChecked())
        self.assertTrue(checks["chk_visual_descricao"].isChecked())
        self.assertTrue(checks["chk_mostrar_fio"].isChecked())
        self.assertTrue(checks["chk_costura"].isChecked())
        self.assertTrue(checks["chk_mostrar_numeros"].isChecked())
        self.assertFalse(checks["chk_caminho_grade"].isChecked())
        self.assertTrue(checks["chk_quantidade_visual"].isChecked())
        self.assertTrue(checks["chk_pique"].isChecked())
        self.assertFalse(checks["chk_modelo"].isChecked())
        self.assertFalse(checks["chk_preencher"].isChecked())
        self.assertFalse(checks["chk_linhas_aux"].isChecked())
        self.assertFalse(checks["chk_grade_tam"].isChecked())
        self.assertFalse(checks["chk_perimetro_molde"].isChecked())
        self.assertFalse(checks["chk_margem_visual"].isChecked())
        self.assertFalse(checks["chk_giro_visual"].isChecked())
        self.assertTrue(molde["mostrar_graduacao"])
        self.assertFalse(molde["visual_tecido"])
        self.assertNotIn(CHAVE_VISUALIZACAO_CUSTOMIZADA, molde)

    def test_preencher_flags_visualizacao_preserva_molde_customizado(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        checks = {}
        for attr, _chave, _padrao in FLAGS_VISUALIZACAO_MOLDE:
            checks[attr] = self._CheckFake(False)
            setattr(dialog, attr, checks[attr])

        PropriedadesMoldesDialog._preencher_flags_visualizacao(
            dialog,
            {
                CHAVE_VISUALIZACAO_CUSTOMIZADA: True,
                "mostrar_graduacao": False,
                "visual_tecido": True,
            },
        )

        self.assertFalse(checks["chk_graduacao"].isChecked())
        self.assertTrue(checks["chk_tecido_visual"].isChecked())

    def test_indice_molde_preferencial_usa_indice_forcado_do_duplo_clique(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        elementos = [
            {"molde": True, "nome_molde": "K1"},
            {"molde": True, "nome_molde": "K2"},
            {"molde": True, "nome_molde": "K3"},
        ]
        dialog.canvas = SimpleNamespace(_selecionados={0}, _indice_propriedades_preferido=2)
        dialog._elementos_edicao = lambda: elementos

        self.assertEqual(PropriedadesMoldesDialog._indice_molde_preferencial(dialog), 2)

    def test_indice_molde_preferencial_usa_identidade_forcada_antes_da_selecao(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        elementos = [
            {"molde": True, "nome_molde": "K1", "molde_id": "mae"},
            {"molde": True, "nome_molde": "K1 - M", "molde_id": "sep-m"},
            {
                "molde": True,
                "nome_molde": "K1 - G",
                "molde_id": "sep-g",
                "origem_extracao": "separar_tamanho",
                "tamanho_extraido": "G",
            },
        ]
        dialog.canvas = SimpleNamespace(
            _selecionados={0},
            _indice_propriedades_preferido=0,
            _propriedades_molde_identidade_preferida={
                "molde_id": "sep-g",
                "nome_molde": "K1 - G",
                "origem_extracao": "separar_tamanho",
                "tamanho_extraido": "G",
            },
        )
        dialog._elementos_edicao = lambda: elementos

        self.assertEqual(PropriedadesMoldesDialog._indice_molde_preferencial(dialog), 2)

    def test_indice_molde_preferencial_nao_usa_base_quando_separado_herda_molde_id(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        elementos = [
            {"molde": True, "nome_molde": "K1", "molde_id": "k1"},
            {
                "molde": True,
                "nome_molde": "K1 - G",
                "molde_id": "k1",
                "origem_extracao": "separar_tamanho",
                "tamanho_extraido": "G",
            },
            {
                "molde": True,
                "nome_molde": "K1 - P",
                "molde_id": "k1",
                "origem_extracao": "separar_tamanho",
                "tamanho_extraido": "P",
            },
        ]
        dialog.canvas = SimpleNamespace(
            _selecionados={0},
            _indice_propriedades_preferido=1,
            _propriedades_molde_identidade_preferida={
                "molde_id": "k1",
                "nome_molde": "K1 - G",
                "origem_extracao": "separar_tamanho",
                "tamanho_extraido": "G",
            },
        )
        dialog._elementos_edicao = lambda: elementos

        self.assertEqual(PropriedadesMoldesDialog._indice_molde_preferencial(dialog), 1)

    def test_indice_molde_preferencial_usa_objeto_real_do_molde_separado(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        base = {"molde": True, "nome_molde": "1", "molde_id": "k1"}
        separado = {
            "molde": True,
            "nome_molde": "K1 - G",
            "molde_id": "k1",
            "origem_extracao": "separar_tamanho",
            "tamanho_extraido": "G",
        }
        elementos_reais = [base, separado]
        elementos_rascunho = [dict(base), dict(separado)]
        dialog.canvas = SimpleNamespace(
            _selecionados={0},
            _indice_propriedades_preferido=0,
            _propriedades_molde_objeto_preferido=separado,
            _propriedades_molde_identidade_preferida={"molde_id": "k1"},
        )
        dialog._elementos_canvas_reais = lambda: elementos_reais
        dialog._elementos_edicao = lambda: elementos_rascunho

        self.assertEqual(PropriedadesMoldesDialog._indice_molde_preferencial(dialog), 1)

    def test_recarregar_lista_marca_molde_redirecionado_por_identidade(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        elementos = [
            {"molde": True, "nome_molde": "K1", "tecido": "1", "molde_id": "mae"},
            {"molde": True, "nome_molde": "K1 - M", "tecido": "1", "molde_id": "sep-m"},
            {
                "molde": True,
                "nome_molde": "K1 - G",
                "tecido": "1",
                "molde_id": "sep-g",
                "origem_extracao": "separar_tamanho",
                "tamanho_extraido": "G",
            },
        ]
        preenchidos = []
        dialog.canvas = SimpleNamespace(
            _selecionados={0},
            _indice_propriedades_preferido=0,
            _propriedades_molde_identidade_preferida={"molde_id": "sep-g"},
        )
        dialog.arvore = QTreeWidget()
        dialog._indice_atual = 0
        dialog._refs = []
        dialog._itens_molde_por_indice = {}
        dialog._combos_tecido_por_item = {}
        dialog._suspender_item_changed = False
        dialog._suspender_combo_tecido_arvore = False
        dialog._elementos_edicao = lambda: elementos
        dialog._atualizar_conflitos_grade_modelo = lambda: None
        dialog._tecidos_disponiveis = lambda: []
        dialog._assinatura_grade_referencia_global = lambda: None
        dialog._icone_status_molde = lambda *_args, **_kwargs: QIcon()
        dialog._instalar_combo_tecido_item = lambda *_args, **_kwargs: None
        dialog._atualizar_combo_moldes = lambda: None
        dialog._preencher_campos = lambda molde: preenchidos.append(
            molde.get("nome_molde") if isinstance(molde, dict) else None
        )

        PropriedadesMoldesDialog.recarregar_lista(dialog)

        selecionados = [
            idx
            for idx, item in dialog._itens_molde_por_indice.items()
            if item.isSelected()
        ]
        self.assertEqual(dialog._indice_atual, 2)
        self.assertEqual(selecionados, [2])
        self.assertEqual(preenchidos[-1], "K1 - G")

    def test_recarregar_lista_prioriza_molde_selecionado_no_canvas(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        elementos = [
            {"molde": True, "nome_molde": "K1", "tecido": "1"},
            {"molde": True, "nome_molde": "K2", "tecido": "1"},
            {"molde": True, "nome_molde": "K3", "tecido": "1"},
        ]
        preenchidos = []
        dialog.canvas = SimpleNamespace(_selecionados={2})
        dialog.arvore = QTreeWidget()
        dialog._indice_atual = 0
        dialog._refs = []
        dialog._itens_molde_por_indice = {}
        dialog._combos_tecido_por_item = {}
        dialog._suspender_item_changed = False
        dialog._suspender_combo_tecido_arvore = False
        dialog._elementos_edicao = lambda: elementos
        dialog._atualizar_conflitos_grade_modelo = lambda: None
        dialog._tecidos_disponiveis = lambda: []
        dialog._assinatura_grade_referencia_global = lambda: None
        dialog._icone_status_molde = lambda *_args, **_kwargs: QIcon()
        dialog._instalar_combo_tecido_item = lambda *_args, **_kwargs: None
        dialog._atualizar_combo_moldes = lambda: None
        dialog._preencher_campos = lambda molde: preenchidos.append(
            molde.get("nome_molde") if isinstance(molde, dict) else None
        )

        PropriedadesMoldesDialog.recarregar_lista(dialog)

        self.assertEqual(dialog._indice_atual, 2)
        self.assertEqual(preenchidos[-1], "K3")

    def test_rascunho_propriedades_ignora_cache_runtime_qpainterpath(self):
        path = QPainterPath(QPointF(0.0, 0.0))
        path.lineTo(QPointF(10.0, 0.0))
        elemento = {
            "molde": True,
            "nome_molde": "K1",
            "pontos": [(0.0, 0.0), (10.0, 0.0)],
            "_runtime_path_polilinha_tela_cache": {"path": path},
        }
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.canvas = SimpleNamespace(cena=SimpleNamespace(elementos=[elemento]))

        rascunho = PropriedadesMoldesDialog._criar_rascunho_elementos(dialog)
        snapshot = PropriedadesMoldesDialog._criar_snapshot_moldes(dialog)

        self.assertEqual(rascunho[0]["nome_molde"], "K1")
        self.assertEqual(snapshot[0]["nome_molde"], "K1")
        self.assertNotIn("_runtime_path_polilinha_tela_cache", rascunho[0])
        self.assertNotIn("_runtime_path_polilinha_tela_cache", snapshot[0])

    def test_abrir_propriedades_centraliza_depois_de_mostrar(self):
        eventos = []

        class _DialogFake:
            _indice_atual = 0

            def isVisible(self):
                return False

            def _iniciar_sessao_edicao(self):
                eventos.append("sessao")

            def _indice_molde_preferencial(self):
                return 0

            def recarregar_lista(self):
                eventos.append("lista")

            def centralizar_na_tela(self):
                eventos.append("centralizar")

            def show(self):
                eventos.append("show")

            def raise_(self):
                eventos.append("raise")

            def activateWindow(self):
                eventos.append("activate")

            def geometry(self):
                return SimpleNamespace(getRect=lambda: (0, 0, 100, 100))

        class _CanvasFake:
            def window(self):
                return None

            def findChildren(self, *_args, **_kwargs):
                return []

        ferramenta = FerramentaPropriedades()
        ferramenta._obter_dialog = lambda _canvas: _DialogFake()

        ferramenta.on_activate(_CanvasFake())

        self.assertLess(eventos.index("show"), eventos.index("centralizar"))

    def test_abrir_propriedades_respeita_aba_graduacao_preferida(self):
        indices_tabs = []

        class _DialogFake:
            _indice_atual = 0
            tabs = SimpleNamespace(setCurrentIndex=lambda idx: indices_tabs.append(idx))

            def isVisible(self):
                return False

            def _iniciar_sessao_edicao(self):
                pass

            def _indice_molde_preferencial(self):
                return 0

            def recarregar_lista(self):
                pass

            def centralizar_na_tela(self):
                pass

            def show(self):
                pass

            def raise_(self):
                pass

            def activateWindow(self):
                pass

            def geometry(self):
                return SimpleNamespace(getRect=lambda: (0, 0, 100, 100))

        class _CanvasFake:
            _propriedades_tab_preferida = "graduacao"

            def window(self):
                return None

            def findChildren(self, *_args, **_kwargs):
                return []

        canvas = _CanvasFake()
        ferramenta = FerramentaPropriedades()
        ferramenta._obter_dialog = lambda _canvas: _DialogFake()

        ferramenta.on_activate(canvas)

        self.assertEqual(indices_tabs, [1])
        self.assertIsNone(canvas._propriedades_tab_preferida)

    def test_layout_visualizacao_tem_altura_para_nao_cortar_checkboxes(self):
        canvas = SimpleNamespace(
            cena=SimpleNamespace(elementos=[]),
            _selecionados=set(),
            _mostrar_cor_tecidos=False,
            _cores_tecidos={},
        )
        dialog = PropriedadesMoldesDialog(canvas)
        self.addCleanup(dialog.close)

        grupo_visualizacao = dialog.findChild(QGroupBox, "VisualizacaoOptionsGroup")

        self.assertIsNotNone(grupo_visualizacao)
        self.assertGreaterEqual(dialog.height(), 830)
        self.assertGreaterEqual(dialog.minimumHeight(), 790)
        self.assertGreaterEqual(dialog.tabs.minimumHeight(), 470)
        self.assertGreaterEqual(grupo_visualizacao.minimumHeight(), 205)
        self.assertGreaterEqual(dialog.chk_caminho_grade.minimumHeight(), 24)
        self.assertGreaterEqual(dialog.chk_grade_tam.minimumHeight(), 24)
        self.assertEqual(dialog.tbl_graduacao.height(), 286)

    def test_preview_piques_usa_segmentos_configurados_em_vez_de_x(self):
        class _PainterFake:
            def __init__(self):
                self.linhas = []

            def save(self):
                pass

            def restore(self):
                pass

            def setPen(self, _pen):
                pass

            def drawLine(self, *args):
                self.linhas.append(args)

        preview = PreviewMoldeWidget.__new__(PreviewMoldeWidget)
        preview._molde = {
            "mostrar_piques": True,
            "piques_config": [
                {
                    "ponto": (5.0, 0.0),
                    "segmentos": [((5.0, 0.0), (5.0, 1.0)), ((4.7, 1.0), (5.3, 1.0))],
                }
            ],
            "marcacoes_no_perimetro": [(5.0, 0.0)],
        }
        painter = _PainterFake()

        PreviewMoldeWidget._desenhar_piques(preview, painter, lambda ponto: QPointF(ponto), "#ffffff")

        self.assertEqual(len(painter.linhas), 2)
        self.assertTrue(all(len(args) == 2 for args in painter.linhas))
        self.assertEqual((painter.linhas[0][0].x(), painter.linhas[0][0].y()), (5.0, 0.0))
        self.assertEqual((painter.linhas[0][1].x(), painter.linhas[0][1].y()), (5.0, 1.0))

    def test_preview_graduacao_respeita_checkbox_visualizacao(self):
        from canvas.visualizacao import VisualizacaoCanvas

        class _PainterFake:
            def __init__(self):
                self.paths = 0

            def save(self):
                pass

            def restore(self):
                pass

            def setPen(self, _pen):
                pass

            def drawPath(self, _path):
                self.paths += 1

        original = VisualizacaoCanvas._contornos_graduacao_tabela
        VisualizacaoCanvas._contornos_graduacao_tabela = staticmethod(
            lambda _molde, _base: [("G", "#ffcc00", [QPointF(0.0, 0.0), QPointF(10.0, 0.0)])]
        )
        try:
            preview = PreviewMoldeWidget.__new__(PreviewMoldeWidget)
            base = [QPointF(0.0, 0.0), QPointF(10.0, 0.0)]
            mapear = lambda ponto: QPointF(ponto)

            preview._molde = {"mostrar_graduacao": False}
            painter = _PainterFake()
            PreviewMoldeWidget._desenhar_graduacao(preview, painter, base, mapear)
            self.assertEqual(painter.paths, 0)

            preview._molde = {"mostrar_graduacao": True}
            painter = _PainterFake()
            PreviewMoldeWidget._desenhar_graduacao(preview, painter, base, mapear)
            self.assertEqual(painter.paths, 1)
        finally:
            VisualizacaoCanvas._contornos_graduacao_tabela = staticmethod(original)

    def test_novo_tamanho_usa_proporcao_da_graduacao_existente(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        molde = {
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "valores": {
                            "P": {"dx": -1.0, "dy": 1.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 1.0, "dy": -1.0},
                        }
                    }
                }
            },
            "graduacao_pontos": {
                "0": {
                    "valores": {
                        "P": {"dx": -1.0, "dy": 1.0},
                        "M": {"dx": 0.0, "dy": 0.0},
                        "G": {"dx": 1.0, "dy": -1.0},
                    }
                }
            },
        }
        novas_linhas = [
            {"ativo": True, "tamanho": "PP", "base": False},
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
            {"ativo": True, "tamanho": "GG", "base": False},
        ]

        PropriedadesMoldesDialog._sincronizar_valores_graduacao_tamanhos(dialog, molde, novas_linhas)

        valores = molde["graduacao_tabela"]["pontos"]["0"]["valores"]
        self.assertEqual(valores["PP"], {"dx": -2.0, "dy": 2.0})
        self.assertEqual(valores["GG"], {"dx": 2.0, "dy": -2.0})
        self.assertEqual(molde["graduacao_pontos"]["0"]["valores"]["PP"], {"dx": -2.0, "dy": 2.0})

    def test_tamanho_adicionado_continua_distancia_da_regra_existente(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        linhas_antigas = [
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
        ]
        molde = {
            "graduacao_tamanhos": linhas_antigas,
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "valores": {
                            "P": {"dx": -1.0, "dy": -1.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 1.0, "dy": 1.0},
                        }
                    }
                }
            },
        }
        novas_linhas = [
            {"ativo": True, "tamanho": "NOVO_SUP_1", "base": False},
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
            {"ativo": True, "tamanho": "NOVO_INF_1", "base": False},
        ]

        PropriedadesMoldesDialog._sincronizar_valores_graduacao_tamanhos(
            dialog,
            molde,
            novas_linhas,
            linhas_antigas=linhas_antigas,
        )

        valores = molde["graduacao_tabela"]["pontos"]["0"]["valores"]
        self.assertEqual(valores["NOVO_SUP_1"], {"dx": -2.0, "dy": -2.0})
        self.assertEqual(valores["NOVO_INF_1"], {"dx": 2.0, "dy": 2.0})

    def test_trocar_grade_mantem_graduacao_por_posicao(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        linhas_antigas = [
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
        ]
        molde = {
            "graduacao_tamanhos": linhas_antigas,
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "valores": {
                            "P": {"dx": -1.0, "dy": 1.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 1.0, "dy": -1.0},
                        }
                    }
                }
            },
        }
        novas_linhas = [
            {"ativo": True, "tamanho": "S", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "L", "base": False},
        ]

        PropriedadesMoldesDialog._sincronizar_valores_graduacao_tamanhos(
            dialog,
            molde,
            novas_linhas,
            linhas_antigas=linhas_antigas,
        )

        valores = molde["graduacao_tabela"]["pontos"]["0"]["valores"]
        self.assertEqual(valores["S"], {"dx": -1.0, "dy": 1.0})
        self.assertEqual(valores["L"], {"dx": 1.0, "dy": -1.0})

    def test_trocar_para_grade_maior_mantem_distancia_da_regra_existente(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        linhas_antigas = [
            {"ativo": True, "tamanho": "PP", "base": False},
            {"ativo": True, "tamanho": "P", "base": False},
            {"ativo": True, "tamanho": "M", "base": True},
            {"ativo": True, "tamanho": "G", "base": False},
            {"ativo": True, "tamanho": "GG", "base": False},
        ]
        molde = {
            "graduacao_tamanhos": linhas_antigas,
            "graduacao_tabela": {
                "pontos": {
                    "0": {
                        "valores": {
                            "PP": {"dx": -4.0, "dy": 0.0},
                            "P": {"dx": -2.0, "dy": 0.0},
                            "M": {"dx": 0.0, "dy": 0.0},
                            "G": {"dx": 2.0, "dy": 0.0},
                            "GG": {"dx": 4.0, "dy": 0.0},
                        }
                    }
                }
            },
        }
        novas_linhas = [
            {"ativo": True, "tamanho": "36", "base": False},
            {"ativo": True, "tamanho": "38", "base": False},
            {"ativo": True, "tamanho": "40", "base": True},
            {"ativo": True, "tamanho": "42", "base": False},
            {"ativo": True, "tamanho": "44", "base": False},
            {"ativo": True, "tamanho": "46", "base": False},
            {"ativo": True, "tamanho": "48", "base": False},
            {"ativo": True, "tamanho": "50", "base": False},
        ]

        PropriedadesMoldesDialog._sincronizar_valores_graduacao_tamanhos(
            dialog,
            molde,
            novas_linhas,
            linhas_antigas=linhas_antigas,
        )

        valores = molde["graduacao_tabela"]["pontos"]["0"]["valores"]
        self.assertEqual(valores["36"], {"dx": -4.0, "dy": 0.0})
        self.assertEqual(valores["38"], {"dx": -2.0, "dy": 0.0})
        self.assertEqual(valores["42"], {"dx": 2.0, "dy": 0.0})
        self.assertEqual(valores["44"], {"dx": 4.0, "dy": 0.0})
        self.assertEqual(valores["46"], {"dx": 6.0, "dy": 0.0})
        self.assertEqual(valores["50"], {"dx": 10.0, "dy": 0.0})

    def test_aplicar_grade_preserva_cores_dos_tamanhos_existentes(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog._graduacao_linhas = [
            {"ativo": True, "tamanho": "P", "cor": "#c87575", "base": False},
            {"ativo": True, "tamanho": "M", "cor": "#d60b0b", "base": True},
            {"ativo": True, "tamanho": "G", "cor": "#5d95b7", "base": False},
        ]
        dialog._renderizar_tabela_graduacao = lambda: None
        dialog._sincronizar_gradacao_no_molde = lambda: None
        dialog._gerar_cor_aleatoria = lambda: "#123456"

        PropriedadesMoldesDialog._aplicar_grade_tamanhos(dialog, "P-G(M)")

        cores = {linha["tamanho"]: linha["cor"] for linha in dialog._graduacao_linhas}
        self.assertEqual(cores, {"P": "#c87575", "M": "#d60b0b", "G": "#5d95b7"})

    def test_grade_numerica_curta_inclui_tamanho_base(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)

        tamanhos, base = PropriedadesMoldesDialog._extrair_tamanhos_grade(dialog, "1-3(2)")

        self.assertEqual(tamanhos, ["1", "2", "3"])
        self.assertEqual(base, "2")

    def test_grade_numerica_adulta_mantem_passo_dois(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)

        tamanhos, base = PropriedadesMoldesDialog._extrair_tamanhos_grade(dialog, "36-50(40)")

        self.assertEqual(tamanhos, ["36", "38", "40", "42", "44", "46", "48", "50"])
        self.assertEqual(base, "40")

    def test_grade_pp_g2_com_base_p_extrai_tamanhos_padrao(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)

        tamanhos, base = PropriedadesMoldesDialog._extrair_tamanhos_grade(dialog, "PP-G2(P)")

        self.assertEqual(tamanhos, ["PP", "P", "M", "G", "GG", "G1", "G2"])
        self.assertEqual(base, "P")

    def test_grade_pp_xg_nao_recebe_tamanhos_g1_g2(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)

        tamanhos, base = PropriedadesMoldesDialog._extrair_tamanhos_grade(dialog, "PP-XG(M)")

        self.assertEqual(tamanhos, ["PP", "P", "M", "G", "GG", "XG"])
        self.assertEqual(base, "M")

    def test_aplicar_grade_pp_g2_usa_cores_padrao_do_preset(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog._graduacao_linhas = [
            {"ativo": True, "tamanho": "P", "cor": "#111111", "base": False},
            {"ativo": True, "tamanho": "M", "cor": "#222222", "base": True},
            {"ativo": True, "tamanho": "G", "cor": "#333333", "base": False},
        ]
        dialog._renderizar_tabela_graduacao = lambda: None
        dialog._sincronizar_gradacao_no_molde = lambda: None
        dialog._gerar_cor_aleatoria = lambda: "#123456"

        PropriedadesMoldesDialog._aplicar_grade_tamanhos(dialog, "PP-G2(P)")

        self.assertEqual(
            [linha["tamanho"] for linha in dialog._graduacao_linhas],
            ["PP", "P", "M", "G", "GG", "G1", "G2"],
        )
        self.assertEqual(
            {linha["tamanho"]: linha["cor"] for linha in dialog._graduacao_linhas},
            {
                "PP": "#00ff00",
                "P": "#ffff00",
                "M": "#2b7cd3",
                "G": "#ffffff",
                "GG": "#ff00ff",
                "G1": "#ff8c00",
                "G2": "#7b1fff",
            },
        )
        self.assertEqual(
            [linha["tamanho"] for linha in dialog._graduacao_linhas if linha.get("base")],
            ["P"],
        )

    def test_carregar_graduacao_do_molde_respeita_linhas_reais_sem_impor_pmg(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        dialog.cmb_grade_tamanhos = QComboBox()
        dialog.cmb_grade_tamanhos.addItems(["P-G(M)", "PP-GG(M)"])
        dialog._renderizar_tabela_graduacao = lambda: None

        molde = {
            "graduacao_grade_nome": "P-G(M)",
            "graduacao_tamanhos": [
                {"ativo": True, "tamanho": "PP", "cor": "#ef4fa0", "base": False},
                {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
                {"ativo": True, "tamanho": "M", "cor": "#2b7cd3", "base": True},
                {"ativo": True, "tamanho": "G", "cor": "#ff8c00", "base": False},
                {"ativo": True, "tamanho": "GG", "cor": "#6694e8", "base": False},
                {"ativo": True, "tamanho": "NOVO_INF_1", "cor": "#92d4a3", "base": False},
            ],
        }

        PropriedadesMoldesDialog._carregar_graduacao_do_molde(dialog, molde)

        self.assertEqual(
            [linha["tamanho"] for linha in dialog._graduacao_linhas],
            ["PP", "P", "M", "G", "GG", "NOVO_INF_1"],
        )
        self.assertEqual(dialog.cmb_grade_tamanhos.currentText(), "PP/P/M/G/GG/NOVO_INF_1(M)")
        self.assertNotEqual(dialog.cmb_grade_tamanhos.currentText(), "P-G(M)")

    def test_propriedades_define_conflito_quando_grade_difere_do_modelo(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        base = {
            "graduacao_grade_nome": "P-G(M)",
            "graduacao_tamanhos": [
                {"tamanho": "P"},
                {"tamanho": "M"},
                {"tamanho": "G"},
            ],
        }
        diferente = {
            "graduacao_grade_nome": "36-44(40)",
            "graduacao_tamanhos": [
                {"tamanho": "36"},
                {"tamanho": "40"},
                {"tamanho": "44"},
            ],
        }
        igual = {
            "graduacao_grade_nome": "P-G(M)",
            "graduacao_tamanhos": [
                {"tamanho": "P"},
                {"tamanho": "M"},
                {"tamanho": "G"},
            ],
        }
        dialog._refs = [
            MoldeRef(indice=0, nome="K1", dados=base),
            MoldeRef(indice=1, nome="K2", dados=diferente),
            MoldeRef(indice=2, nome="K3", dados=igual),
        ]
        dialog.lbl_alerta_grade = QLabel()

        PropriedadesMoldesDialog._atualizar_conflitos_grade_modelo(dialog)

        self.assertFalse(base["conflito_grade_modelo"])
        self.assertTrue(diferente["conflito_grade_modelo"])
        self.assertEqual(diferente["grade_modelo_referencia"], "P-G(M)|P/M/G")
        self.assertFalse(igual["conflito_grade_modelo"])
        self.assertEqual(diferente["graduacao_grade_nome"], "36-44(40)")
        self.assertFalse(dialog.lbl_alerta_grade.isHidden())
        self.assertIn("Erro de grade", dialog.lbl_alerta_grade.text())
        self.assertIn("P-G(M)", dialog.lbl_alerta_grade.text())
        self.assertIn("36-44(40)", dialog.lbl_alerta_grade.text())

        tooltip = PropriedadesMoldesDialog._tooltip_grade_molde(
            dialog,
            dialog._refs[1],
            "P-G(M)|P/M/G",
        )
        self.assertIn("Grade diferente", tooltip)
        self.assertIn("Referência: P-G(M)", tooltip)


    def test_propriedades_alerta_quando_nome_do_tamanho_difere(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        com_exg = {
            "molde_pronto": True,
            "graduacao_grade_nome": "PP-G2(P)",
            "graduacao_tamanhos": [
                {"tamanho": "PP"},
                {"tamanho": "P"},
                {"tamanho": "M"},
                {"tamanho": "G"},
                {"tamanho": "GG"},
                {"tamanho": "EXG"},
                {"tamanho": "G2"},
            ],
        }
        com_g1 = {
            "molde_pronto": True,
            "graduacao_grade_nome": "PP-G2(P)",
            "graduacao_tamanhos": [
                {"tamanho": "PP"},
                {"tamanho": "P"},
                {"tamanho": "M"},
                {"tamanho": "G"},
                {"tamanho": "GG"},
                {"tamanho": "G1"},
                {"tamanho": "G2"},
            ],
        }
        dialog._refs = [
            MoldeRef(indice=0, nome="FRENTE 2X", dados=com_exg),
            MoldeRef(indice=1, nome="FORRO FRENTE 1X", dados=com_g1),
        ]
        dialog.lbl_alerta_grade = QLabel()

        PropriedadesMoldesDialog._atualizar_conflitos_grade_modelo(dialog)

        self.assertTrue(com_exg["conflito_nome_tamanho_modelo"])
        self.assertTrue(com_g1["conflito_nome_tamanho_modelo"])
        self.assertFalse(dialog.lbl_alerta_grade.isHidden())
        self.assertIn("Erro de nome de tamanho", dialog.lbl_alerta_grade.text())
        self.assertIn("EXG", dialog.lbl_alerta_grade.text())
        self.assertIn("G1", dialog.lbl_alerta_grade.text())

        tooltip = PropriedadesMoldesDialog._tooltip_grade_molde(
            dialog,
            dialog._refs[1],
            "PP-G2(P)|PP/P/M/G/GG/EXG/G2",
        )
        self.assertIn("Nome de tamanho diferente", tooltip)
        self.assertIn("EXG", tooltip)
        self.assertIn("G1", tooltip)

    def test_propriedades_alerta_quando_nome_do_molde_repete(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        grade = [
            {"tamanho": "P"},
            {"tamanho": "M", "base": True},
            {"tamanho": "G"},
        ]
        primeiro = {"molde_pronto": True, "nome_molde": "K3", "graduacao_grade_nome": "P-G(M)", "graduacao_tamanhos": grade}
        segundo = {"molde_pronto": True, "nome_molde": "K3", "graduacao_grade_nome": "P-G(M)", "graduacao_tamanhos": grade}
        terceiro = {"molde_pronto": True, "nome_molde": "K4", "graduacao_grade_nome": "P-G(M)", "graduacao_tamanhos": grade}
        dialog._refs = [
            MoldeRef(indice=0, nome="K3", dados=primeiro),
            MoldeRef(indice=1, nome="K3", dados=segundo),
            MoldeRef(indice=2, nome="K4", dados=terceiro),
        ]
        dialog.lbl_alerta_grade = QLabel()

        PropriedadesMoldesDialog._atualizar_conflitos_grade_modelo(dialog)

        self.assertTrue(primeiro["conflito_nome_molde_modelo"])
        self.assertTrue(segundo["conflito_nome_molde_modelo"])
        self.assertFalse(terceiro["conflito_nome_molde_modelo"])
        self.assertIn("Erro de nome de molde", dialog.lbl_alerta_grade.text())
        tooltip = PropriedadesMoldesDialog._tooltip_grade_molde(dialog, dialog._refs[0], "P-G(M)|P/M/G")
        self.assertIn("Nome de molde repetido", tooltip)
        self.assertIn("K3", tooltip)

    def test_alerta_nome_repetido_some_imediatamente_ao_renomear_molde(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        primeiro = {"molde": True, "molde_pronto": True, "nome_molde": "K3", "conflito_nome_molde_modelo": True}
        segundo = {"molde": True, "molde_pronto": True, "nome_molde": "K3", "conflito_nome_molde_modelo": True}
        elementos = [primeiro, segundo]
        item_primeiro = QTreeWidgetItem(["K3"])
        item_primeiro.setData(0, Qt.UserRole, 0)
        item_segundo = QTreeWidgetItem(["K3"])
        item_segundo.setData(0, Qt.UserRole, 1)
        dialog._indice_atual = None
        dialog._suspender_item_changed = False
        dialog._refs = [
            MoldeRef(indice=0, nome="K3", dados=primeiro),
            MoldeRef(indice=1, nome="K3", dados=segundo),
        ]
        dialog._itens_molde_por_indice = {0: item_primeiro, 1: item_segundo}
        dialog.lbl_alerta_grade = QLabel("Erro de nome de molde")
        dialog.lbl_alerta_grade.setHidden(False)
        dialog.preview = SimpleNamespace(set_molde=lambda _molde: None)
        dialog._elementos_edicao = lambda: elementos
        dialog._atualizar_combo_moldes = lambda: None

        item_segundo.setText(0, "K4")
        PropriedadesMoldesDialog._quando_item_editado(dialog, item_segundo, 0)

        self.assertEqual(segundo["nome_molde"], "K4")
        self.assertFalse(primeiro["conflito_nome_molde_modelo"])
        self.assertFalse(segundo["conflito_nome_molde_modelo"])
        self.assertTrue(dialog.lbl_alerta_grade.isHidden())
        self.assertEqual(item_primeiro.toolTip(0), "")
        self.assertEqual(item_segundo.toolTip(0), "")

    def test_alerta_nome_repetido_atualiza_instantaneo_pelo_campo_molde(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        primeiro = {"molde": True, "molde_pronto": True, "nome_molde": "K2"}
        segundo = {"molde": True, "molde_pronto": True, "nome_molde": "K3"}
        elementos = [primeiro, segundo]
        item_primeiro = QTreeWidgetItem(["K2"])
        item_primeiro.setData(0, Qt.UserRole, 0)
        item_segundo = QTreeWidgetItem(["K3"])
        item_segundo.setData(0, Qt.UserRole, 1)
        dialog._indice_atual = 1
        dialog._suspender_auto_aplicar = False
        dialog._suspender_item_changed = False
        dialog._refs = [
            MoldeRef(indice=0, nome="K2", dados=primeiro),
            MoldeRef(indice=1, nome="K3", dados=segundo),
        ]
        dialog._itens_molde_por_indice = {0: item_primeiro, 1: item_segundo}
        dialog.lbl_alerta_grade = QLabel()
        dialog.preview = SimpleNamespace(set_molde=lambda _molde: None)
        dialog._elementos_edicao = lambda: elementos

        PropriedadesMoldesDialog._renomear_molde_atual_instantaneo(dialog, "K2")

        self.assertTrue(primeiro["conflito_nome_molde_modelo"])
        self.assertTrue(segundo["conflito_nome_molde_modelo"])
        self.assertFalse(dialog.lbl_alerta_grade.isHidden())
        self.assertIn("Erro de nome de molde", dialog.lbl_alerta_grade.text())
        self.assertIn("Nome de molde repetido", item_segundo.toolTip(0))

        PropriedadesMoldesDialog._renomear_molde_atual_instantaneo(dialog, "K4")

        self.assertEqual(segundo["nome_molde"], "K4")
        self.assertFalse(primeiro["conflito_nome_molde_modelo"])
        self.assertFalse(segundo["conflito_nome_molde_modelo"])
        self.assertTrue(dialog.lbl_alerta_grade.isHidden())
        self.assertEqual(item_primeiro.toolTip(0), "")
        self.assertEqual(item_segundo.toolTip(0), "")

    def test_editar_nome_tamanho_na_tabela_atualiza_grade_do_molde(self):
        dialog = PropriedadesMoldesDialog.__new__(PropriedadesMoldesDialog)
        molde = {}
        publicados = []
        dialog._graduacao_linhas = [
            {"ativo": True, "tamanho": "P", "cor": "#ffff00", "base": False},
            {"ativo": True, "tamanho": "M", "cor": "#2d80d7", "base": True},
            {"ativo": True, "tamanho": "G", "cor": "#ff8800", "base": False},
        ]
        dialog._linha_gradacao_atual = 1
        dialog._suspender_auto_aplicar = False
        dialog.tbl_graduacao = QTableWidget(0, 3)
        dialog.cmb_grade_tamanhos = QComboBox()
        dialog.cmb_grade_tamanhos.addItem("P-G(M)")
        dialog._moldes_alvo_graduacao = lambda: [molde]
        dialog._sincronizar_valores_graduacao_tamanhos = lambda *_args, **_kwargs: None
        dialog._publicar_rascunho_visualizacao = lambda: publicados.append(True)

        PropriedadesMoldesDialog._renderizar_tabela_graduacao(dialog)
        item = dialog.tbl_graduacao.item(1, 1)
        item.setText("EXG")
        PropriedadesMoldesDialog._quando_tamanho_graduacao_editado(dialog, item)

        self.assertEqual(dialog._graduacao_linhas[1]["tamanho"], "EXG")
        self.assertEqual(molde["graduacao_tamanhos"][1]["tamanho"], "EXG")
        self.assertEqual(molde["graduacao_tamanhos_ativos"], ["P", "EXG", "G"])
        self.assertIn("EXG", dialog.cmb_grade_tamanhos.currentText())
        self.assertTrue(publicados)


if __name__ == "__main__":
    unittest.main()
