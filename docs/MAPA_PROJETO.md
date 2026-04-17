# MAPA VISUAL DO PROJETO GUIMMA STUDIO

> Documento de orientação para saber **qual botão chama qual arquivo** e onde fica cada parte do código.

## 1) Fluxo visual principal (botão → código)

```mermaid
flowchart LR
    U[Usuário clica botão] --> JP[ui/janela_principal.py]
    JP --> RIB[ui/ribbon.py]
    RIB --> MAP[ui/tool_pages_map.json]
    MAP --> MOD[importlib.import_module(module)]
    MOD --> TOOL[tools/*.py (classe da ferramenta)]
    TOOL --> CANVAS[canvas/visualizacao.py]
    CANVAS --> SNAP[canvas/snap.py (captura magnética)]
    JP --> FILE[formats/gs_project.py / core/projeto.py]
```

## 2) Botões fixos da interface e destino no código

| Área / Botão | Evento no código | Arquivo principal |
|---|---|---|
| ARQUIVO | `self.botao_arquivo.clicked.connect(self._alternar_backstage)` | `ui/janela_principal.py` |
| Janela do Backstage (altura compacta) | `resizeEvent -> setFixedHeight(min(520, ...))` | `ui/janela_principal.py` |
| Novo | `self.backstage.botoes["Novo"].clicked.connect(self._novo_projeto)` | `ui/janela_principal.py` |
| Abrir | `...connect(self._abrir_projeto)` | `ui/janela_principal.py` |
| Salvar | `...connect(self._salvar_projeto)` | `ui/janela_principal.py` |
| Salvar como | `...connect(self._salvar_projeto_como)` | `ui/janela_principal.py` |
| Janela "Salvar como..." | `SalvarComoDialog` (arquivo + metadados) | `ui/salvar_como_dialog.py` |
| Arquivo recente | `arquivo_recente_clicado -> _abrir_projeto_em_caminho` | `ui/backstage_arquivo.py` + `ui/janela_principal.py` |
| Hover em Arquivos Recentes | `QListWidget::item:hover` (realce + barra lateral) | `ui/backstage_arquivo.py` |
| Botão de fechar aba (✕) | `clicked -> _fechar_aba_documento` | `ui/janela_principal.py` |
| Abas de documentos (alinhadas à esquerda) | `QTabWidget::tab-bar { alignment: left; }` | `ui/janela_principal.py` |
| Barra inferior: Snap (ímã) | `btn_snap.toggled -> _alternar_snap_canvas_atual` | `ui/janela_principal.py` + `canvas/visualizacao.py` + `canvas/snap.py` |
| Barra inferior: Mão | `btn_mao.clicked -> _set_modo_navegacao("mao")` | `ui/janela_principal.py` |
| Barra inferior: Lupa | `btn_lupa.clicked -> _set_modo_navegacao("lupa")` | `ui/janela_principal.py` |
| Barra inferior: Zoom - | `btn_zoom_menos.clicked -> _aplicar_zoom_incremental(1/1.1)` | `ui/janela_principal.py` |
| Barra inferior: Zoom + | `btn_zoom_mais.clicked -> _aplicar_zoom_incremental(1.1)` | `ui/janela_principal.py` |
| Faixa de zoom | `VisualizacaoCanvas.set_zoom(0.025x..99.500x)` + label com 3 casas decimais | `canvas/visualizacao.py` + `ui/janela_principal.py` |
| Topbar/Ribbon (aba ativa com faixa colorida) | `tabbar.currentChanged -> _atualizar_destaque_aba` | `ui/ribbon.py` |

### Observações de comportamento atual do Snap

- O snap calcula candidatos por **nó**, **ponto médio**, **borda** e **centro** em `canvas/snap.py`.
- Em `canvas/visualizacao.py`, o snap é aplicado tanto no desenho (`reta/curva`) quanto no **modo seleção**.
- No clique de seleção (sem arrastar caixa), se existir alvo de snap ativo, a seleção prioriza o `elemento_idx` vindo do snap.
- O marcador de snap mostra o tipo do alvo (ex.: `nó`, `ponto médio`, `borda`, `centro`) ao aproximar o cursor.

## 3) Mapa detalhado do Ribbon (todas as ferramentas)

| Aba | Grupo | Tool ID | Texto do botão | Módulo Python | Classe | Ícone |
|---|---|---|---|---|---|---|
| Início | Desenho | `cor` | Cor | `tools/cor_tool.py` | `Ferramenta` | `cor.svg` |
| Início | Desenho | `selecionar` | Selecionar | `tools/selecionar_tool.py` | `Ferramenta` | `selecionar.svg` |
| Início | Editar | `colar` | Colar | `tools/colar_tool.py` | `Ferramenta` | `colar.svg` |
| Início | Editar | `recortar` | Recortar | `tools/recortar_tool.py` | `Ferramenta` | `recortar.svg` |
| Início | Editar | `excluir` | Excluir | `tools/excluir_tool.py` | `Ferramenta` | `excluir.svg` |
| Início | Selecionar | `inverter_selecao` | Inverter Selecao | `tools/inverter_selecao_tool.py` | `Ferramenta` | `inverter_selecao.svg` |
| Início | Selecionar | `selecionar_tudo` | Selecionar Tudo | `tools/selecionar_tudo_tool.py` | `Ferramenta` | `selecionar_tudo.svg` |
| Início | Selecionar | `selecionar_moldes` | Selecionar Moldes | `tools/selecionar_moldes_tool.py` | `Ferramenta` | `selecionar_moldes.svg` |
| Construção | Retas | `reta` | Reta | `tools/construcao.py` | `FerramentaReta` | `reta.svg` |
| Construção | Retas | `retangulo` | Retangulo | `tools/construcao.py` | `FerramentaRetangulo` | `retangulo.svg` |
| Construção | Retas | `por_angulo` | Por Angulo | `tools/construcao.py` | `FerramentaPorAngulo` | `por_angulo.svg` |
| Construção | Retas | `estender_reta` | Estender reta | `tools/construcao.py` | `FerramentaEstenderReta` | `reta.svg` |
| Construção | Retas | `estender_ate_elemento` | Estender até elemento | `tools/construcao.py` | `FerramentaEstenderAteElemento` | `reta.svg` |
| Construção | Retas | `estender_duas_retas` | Estender duas retas | `tools/construcao.py` | `FerramentaEstenderDuasRetas` | `reta.svg` |
| Construção | Curvas | `curva` | Curva | `tools/construcao.py` | `FerramentaCurva` | `curva.svg` |
| Construção | Curvas | `dividir_curva` | Dividir Curva | `tools/dividir_curva_tool.py` | `Ferramenta` | `dividir_curva.svg` |
| Construção | Curvas | `predefinida` | Predefinida | `tools/predefinida_tool.py` | `Ferramenta` | `predefinida.svg` |
| Construção | Pontos | `por_coordenada` | Por Coordenada | `tools/por_coordenada_tool.py` | `Ferramenta` | `por_coordenada.svg` |
| Construção | Pontos | `por_intersecao` | Por Intersecao | `tools/por_intersecao_tool.py` | `Ferramenta` | `por_intersecao.svg` |
| Construção | Pontos | `por_distancia` | Por Distancia | `tools/por_distancia_tool.py` | `Ferramenta` | `por_distancia.svg` |
| Construção | Arcos | `por_raio` | Por Raio | `tools/por_raio_tool.py` | `Ferramenta` | `por_raio.svg` |
| Construção | Texto | `inserir_texto` | Inserir Texto | `tools/inserir_texto_tool.py` | `Ferramenta` | `inserir_texto.svg` |
| Construção | Texto | `editar_texto` | Editar Texto | `tools/editar_texto_tool.py` | `Ferramenta` | `editar_texto.svg` |
| Produção | Definir moldes | `extrair_molde` | Extrair Molde | `tools/extrair_molde_tool.py` | `Ferramenta` | `extrair_molde.svg` |
| Produção | Definir moldes | `criar_molde` | Criar Molde | `tools/criar_molde_tool.py` | `Ferramenta` | `criar_molde.svg` |
| Produção | Definir moldes | `digitalizar` | Digitalizar | `tools/digitalizar_tool.py` | `Ferramenta` | `digitalizar.svg` |
| Produção | Definir moldes | `sentido_fio` | Sentido Fio | `tools/sentido_fio_tool.py` | `Ferramenta` | `sentido_fio.svg` |
| Produção | Complementar moldes | `encolhimento` | Encolhimento | `tools/encolhimento_tool.py` | `Ferramenta` | `encolhimento.svg` |
| Produção | Complementar moldes | `linha_simetria` | Linha Simetria | `tools/linha_simetria_tool.py` | `Ferramenta` | `linha_simetria.svg` |
| Produção | Complementar moldes | `bainha` | Bainha | `tools/bainha_tool.py` | `Ferramenta` | `bainha.svg` |
| Produção | Complementar moldes | `dobrar` | Dobrar | `tools/dobrar_tool.py` | `Ferramenta` | `dobrar.svg` |
| Produção | Costura | `costura` | Costura | `tools/costura_tool.py` | `Ferramenta` | `costura.svg` |
| Produção | Costura | `remover_costura` | Remover Costura | `tools/remover_costura_tool.py` | `Ferramenta` | `remover_costura.svg` |
| Produção | Costura | `trocar_costura` | Trocar Costura | `tools/trocar_costura_tool.py` | `Ferramenta` | `trocar_costura.svg` |
| Produção | Pregas e pences | `pregas` | Pregas | `tools/pregas_tool.py` | `Ferramenta` | `pregas.svg` |
| Produção | Pregas e pences | `pence_contorno` | Pence Contorno | `tools/pence_contorno_tool.py` | `Ferramenta` | `pence_contorno.svg` |
| Produção | Pregas e pences | `pence_interna` | Pence Interna | `tools/pence_interna_tool.py` | `Ferramenta` | `pence_interna.svg` |
| Produção | Pregas e pences | `fechar_pence` | Fechar Pence | `tools/fechar_pence_tool.py` | `Ferramenta` | `fechar_pence.svg` |
| Produção | Cortar e unir | `multiplas_pences` | Multiplas Pences | `tools/multiplas_pences_tool.py` | `Ferramenta` | `multiplas_pences.svg` |
| Produção | Cortar e unir | `cortar` | Cortar | `tools/cortar_tool.py` | `Ferramenta` | `cortar.svg` |
| Produção | Cortar e unir | `unir` | Unir | `tools/unir_tool.py` | `Ferramenta` | `unir.svg` |
| Marcações | Piques | `inserir_pique` | Inserir Pique | `tools/inserir_pique_tool.py` | `Ferramenta` | `inserir_pique.svg` |
| Marcações | Piques | `remover_pique` | Remover Pique | `tools/remover_pique_tool.py` | `Ferramenta` | `remover_pique.svg` |
| Marcações | Piques | `pique_texto` | Pique Texto | `tools/pique_texto_tool.py` | `Ferramenta` | `pique_texto.svg` |
| Marcações | Piques | `multiplos` | Multiplos | `tools/multiplos_tool.py` | `Ferramenta` | `multiplos.svg` |
| Marcações | Editar piques | `alinhar` | Alinhar | `tools/alinhar_tool.py` | `Ferramenta` | `alinhar.svg` |
| Marcações | Editar piques | `substituir` | Substituir | `tools/substituir_tool.py` | `Ferramenta` | `substituir.svg` |
| Marcações | Editar piques | `alterar` | Alterar | `tools/alterar_tool.py` | `Ferramenta` | `alterar.svg` |
| Graduação | Graduar | `tabela` | Tabela | `tools/tabela_tool.py` | `Ferramenta` | `tabela.svg` |
| Graduação | Graduar | `mouse` | Mouse | `tools/mouse_tool.py` | `Ferramenta` | `mouse.svg` |
| Graduação | Graduar | `regras` | Regras | `tools/regras_tool.py` | `Ferramenta` | `regras.svg` |
| Graduação | Graduar | `criar_regra` | Criar Regra | `tools/criar_regra_tool.py` | `Ferramenta` | `criar_regra.svg` |
| Graduação | Manipular graduação | `remover_graduacao` | Remover Graduacao | `tools/remover_graduacao_tool.py` | `Ferramenta` | `remover_graduacao.svg` |
| Graduação | Manipular graduação | `separar` | Separar | `tools/separar_tool.py` | `Ferramenta` | `separar.svg` |
| Graduação | Manipular graduação | `agrupar` | Agrupar | `tools/agrupar_tool.py` | `Ferramenta` | `agrupar.svg` |
| Graduação | Manipular graduação | `graduar_curva` | Graduar Curva | `tools/graduar_curva_tool.py` | `Ferramenta` | `graduar_curva.svg` |
| Manipulação | Redefinir | `modificar` | Modificar | `tools/modificar_tool.py` | `Ferramenta` | `modificar.svg` |
| Manipulação | Redefinir | `editar` | Editar | `tools/editar_tool.py` | `Ferramenta` | `editar.svg` |
| Manipulação | Redefinir | `manipular_pontos` | Manipular Pontos | `tools/manipular_pontos_tool.py` | `Ferramenta` | `manipular_pontos.svg` |
| Manipulação | Redefinir | `mover` | Mover | `tools/mover_tool.py` | `Ferramenta` | `mover.svg` |
| Manipulação | Indicar | `elemento_paralelo` | Elemento Paralelo | `tools/elemento_paralelo_tool.py` | `Ferramenta` | `elemento_paralelo.svg` |
| Manipulação | Indicar | `girar` | Girar | `tools/girar_tool.py` | `Ferramenta` | `girar.svg` |
| Manipulação | Indicar | `espelhar` | Espelhar | `tools/espelhar_tool.py` | `Ferramenta` | `espelhar.svg` |
| Manipulação | Manipular molde | `inserir_ponto` | Inserir Ponto | `tools/inserir_ponto_tool.py` | `Ferramenta` | `inserir_ponto.svg` |
| Manipulação | Manipular molde | `excluir_ponto` | Excluir Ponto | `tools/excluir_ponto_tool.py` | `Ferramenta` | `excluir_ponto.svg` |
| Manipulação | Manipular molde | `arredondar_ou_chanfrar` | Arredondar Ou Chanfrar | `tools/arredondar_ou_chanfrar_tool.py` | `Ferramenta` | `arredondar_ou_chanfrar.svg` |
| Conferência | Perímetro | `conferir` | Conferir | `tools/conferir_tool.py` | `Ferramenta` | `conferir.svg` |
| Conferência | Perímetro | `conferir_multiplos` | Conferir Multiplos | `tools/conferir_multiplos_tool.py` | `Ferramenta` | `conferir_multiplos.svg` |
| Conferência | Perímetro | `controle_curvas` | Controle Curvas | `tools/controle_curvas_tool.py` | `Ferramenta` | `controle_curvas.svg` |
| Conferência | Perímetro | `cota_perimetro` | Cota Perimetro | `tools/cota_perimetro_tool.py` | `Ferramenta` | `cota_perimetro.svg` |
| Conferência | Distância | `cota_distancia` | Cota Distancia | `tools/cota_distancia_tool.py` | `Ferramenta` | `cota_distancia.svg` |
| Conferência | Distância | `distancia` | Distancia | `tools/distancia_tool.py` | `Ferramenta` | `distancia.svg` |
| Conferência | Distância | `comparar_distancia` | Comparar Distancia | `tools/comparar_distancia_tool.py` | `Ferramenta` | `comparar_distancia.svg` |
| Conferência | Distância | `raio` | Raio | `tools/raio_tool.py` | `Ferramenta` | `raio.svg` |
| Modelo | Informações | `propriedades` | Propriedades | `tools/propriedades_tool.py` | `Ferramenta` | `propriedades.svg` |
| Modelo | Informações | `tecidos` | Tecidos | `tools/tecidos_tool.py` | `Ferramenta` | `tecidos.svg` |
| Modelo | Informações | `autor` | Autor | `tools/autor_tool.py` | `Ferramenta` | `autor.svg` |
| Modelo | Informações | `informacoes_moldes` | Informacoes Moldes | `tools/informacoes_moldes_tool.py` | `Ferramenta` | `informacoes_moldes.svg` |
| Modelo | Operações | `variantes` | Variantes | `tools/variantes_tool.py` | `Ferramenta` | `variantes.svg` |
| Modelo | Operações | `relacionamento_piques` | Relacionamento Piques | `tools/relacionamento_piques_tool.py` | `Ferramenta` | `relacionamento_piques.svg` |
| Modelo | Operações | `imagens` | Imagens | `tools/imagens_tool.py` | `Ferramenta` | `imagens.svg` |
| Modelo | Operações | `substituir` | Substituir | `tools/substituir_tool.py` | `Ferramenta` | `substituir.svg` |

## 4) Estrutura do projeto (onde fica cada coisa)

```text
GUIMMA-STUDIO/
├── main.py                      # entrada da aplicação
├── guimma_app.py                # inicialização do app Qt
├── config.py                    # caminhos globais, ícones, extensão de arquivo
├── ui/
│   ├── janela_principal.py      # janela principal, backstage, abas, status, barra inferior
│   ├── ribbon.py                # ribbon, grupos e botões de ferramenta
│   ├── backstage_arquivo.py     # painel Arquivo (Novo/Abrir/Salvar/Recentes)
│   └── tool_pages_map.json      # mapa botão->módulo->classe->ícone por aba/grupo
├── canvas/
│   ├── workspace.py             # área com régua horizontal/vertical + canvas
│   ├── visualizacao.py          # desenho, seleção, mover, copiar/colar, undo/redo
│   ├── snap.py                  # lógica de captura magnética (snap)
│   └── cena.py                  # modelo de elementos desenhados
├── tools/
│   ├── tool_base.py             # base/padrão de ferramentas
│   ├── construcao.py            # ferramentas de construção consolidadas
│   └── *_tool.py                # módulos de ferramentas individuais
├── core/
│   └── projeto.py               # modelo principal de projeto
├── formats/
│   └── gs_project.py            # abrir/salvar formato .gs_project
└── assets/icons/*.svg           # ícones dos botões e ferramentas
```

## 5) Atalhos de teclado atuais

| Atalho | Ação | Onde está ligado |
|---|---|---|
| Ctrl+Z | Desfazer | `ui/janela_principal.py` -> `canvas/visualizacao.py` |
| Ctrl+Shift+Z | Refazer | `ui/janela_principal.py` -> `canvas/visualizacao.py` |
| Ctrl+C | Copiar seleção | `ui/janela_principal.py` -> `canvas/visualizacao.py` |
| Ctrl+V | Colar | `ui/janela_principal.py` -> `canvas/visualizacao.py` |
| Delete | Apagar selecionados | `ui/janela_principal.py` -> `canvas/visualizacao.py` |

## 6) Regra prática para localizar código rápido

1. **Se é botão do topo/ribbon**: começar em `ui/ribbon.py` e `ui/tool_pages_map.json`.
2. **Se é botão de arquivo/salvamento**: começar em `ui/janela_principal.py` e `ui/backstage_arquivo.py`.
3. **Se desenha no canvas**: ir para `canvas/visualizacao.py`.
4. **Se é captura magnética (imã/snap)**: ir para `canvas/snap.py`.
5. **Se é lógica específica da ferramenta**: abrir módulo em `tools/*.py` indicado no mapa do ribbon.

---
Atualize este mapa sempre que criar novo botão, nova aba do ribbon ou novo módulo em `tools/`.
