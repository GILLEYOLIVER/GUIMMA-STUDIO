# Arquitetura do Motor Geométrico (Python + C++)

Este documento define a direção arquitetural para transformar as ferramentas em controladoras leves e concentrar cálculos reutilizáveis em um motor geométrico central.

## Objetivo

Separar o sistema em camadas:

- **Python/UI**: ribbon, atalhos, eventos, seleção, histórico, canvas e fluxo das ferramentas.
- **Motor geométrico (alvo C++)**: geometria, interseções, topologia, snapping e edição de nós/segmentos.
- **Bridge**: camada de tradução entre objetos de cena (Qt/Python) e estruturas neutras do motor.

## Modelo de dados alvo

A fonte de verdade deve ser estruturada por entidades com identidade estável:

- **Shape** (`shape_id`)
- **Node** (`node_id`)
- **Segment** (`segment_id`)

O contorno visual no canvas passa a ser derivado dessa estrutura, e não o contrário.

## Módulos recomendados do motor

1. `geometry/basic`: distância, projeção, orientação, bbox, simplificação.
2. `geometry/intersections`: segmento/segmento, curva/segmento, curva/curva, split.
3. `geometry/topology`: grafo, ciclos, faces, fechamento, limpeza.
4. `geometry/curves`: Bézier/spline/arco, amostragem, suavização, offset de curva.
5. `modeling`: operações de molde (fio, piques, nós principais, reconstrução).
6. `snapping`: snap em nó, segmento, interseção, grade e pontos especiais.

## Estado atual no repositório

Foi introduzida uma base de transição totalmente em Python para preparar a ponte com o motor:

- `core/geometry/model.py`: entidades `GeoShape`, `GeoNode`, `GeoSegment` com IDs estáveis.
- `core/geometry/engine.py`: operações geométricas puras e construção de molde.
- `core/geometry_bridge.py`: conversão de elementos de cena para payload neutro.

Também foi adicionado backend nativo **opcional** em C++:

- `core/geometry/native/geometry_native.cpp`: implementação pybind11 para `point_in_polygon` e `internal_angle`.
- `core/geometry/engine.py`: fallback automático (usa C++ quando `geometry_native` estiver compilado/disponível, caso contrário usa Python).
- `core/geometry_cpp/`: módulo pybind11 `guimma_geometry_cpp`, usado para cargas maiores do canvas e das ferramentas.
- `core/geometry_cpp_bridge.py`: ponte tolerante. Cada função tenta chamar o C++ e retorna `None` em caso de indisponibilidade ou falha, deixando a ferramenta voltar para Python.

A ferramenta `Extrair Molde` já passou a consumir a bridge para:

- teste de ponto interno
- construção do molde
- preenchimento de metadados de identidade (`shape_id`, `node_ids`, `segment_ids`)

## Estado atual do motor nativo

O módulo `guimma_geometry_cpp` é carregado automaticamente de uma instalação Python normal ou do build local em `core/geometry_cpp/build`.

Funções nativas em uso:

- `sample_quadratic`, `sample_cubic`, `sample_curve_auto`: amostragem de curvas.
- `polyline_length`, `polygon_area`, `normalize_polyline`: operações básicas de polilinha.
- `point_in_polygon`: teste geométrico.
- `extract_local_enclosing_contour`, `extract_smallest_enclosing_contour`: extração de contorno.
- `seam_offset_closed`: offset fechado de costura total com largura constante.
- motor de snap e indice espacial para reduzir varreduras grandes no canvas.

O build local pode ser atualizado com:

```bash
cmake --build core/geometry_cpp/build
```

As ferramentas não devem importar `guimma_geometry_cpp` diretamente. Use sempre `core.geometry_cpp_bridge`, porque a aplicação precisa continuar funcionando quando o módulo nativo não existir.

## Piques

Piques configurados vivem no molde em `piques_config`; marcações antigas em `marcacoes_no_perimetro` são apenas compatibilidade visual. Novas rotinas devem preferir `piques_config`, com `segmentos`, `ponto`, `ponto_controle`, `sobre_contorno` e metadados de texto quando existirem.

Regras atuais:

- `Inserir Pique` continua sendo a fonte de verdade para cálculo da forma, orientação interna/externa, pontos de controle e integração com graduação.
- `Múltiplos Piques` reutiliza a mesma rotina de inserção, mas trabalha em dois cliques: o primeiro clique inicia no elemento/contorno, o movimento do mouse mostra a divisão uniforme no sentido horário ou anti-horário, e o segundo clique fixa os piques. No modo interno, a linha de divisão usa o imã angular dos ângulos tradicionais quando o snap está ativo.
- `Pique Texto` trabalha como ferramenta de posicionamento: a janela fica aberta, sem botão `Aplicar`, o texto digitado acompanha o cursor e o clique esquerdo grava uma anotação interna no molde. Botão direito finaliza e volta para seleção. Texto interno usa `tipo = "Texto"`, `sobre_contorno = False`, `texto_sem_marca = True` e não desenha X; ele acompanha a visibilidade/graduação quando `aplicar_todos_tamanhos` estiver ativo.
- `Remover Pique` tem remoção individual por clique e remoção por escopo: todos os piques do molde, todos os piques do contorno ou todos os piques internos. A remoção por escopo reaproveita a limpeza individual para remover pontos auxiliares/principais vinculados com segurança.

## Costura

A costura é tratada como extensão do molde, não como molde independente. Ela guarda vínculo com o molde por metadados como `costura_de_molde_id`, `molde_id`, `costura_segmentos`, `costura_parcial`, `costura_largura_inicio`, `costura_largura_fim` e `costura_graduacao`.

Regras atuais:

- Costura total com largura constante usa `seam_offset_closed_cpp` em `tools/costura_tool.py`.
- Se o C++ não estiver disponível, `_gerar_costura` usa o algoritmo Python equivalente.
- Costura parcial, costura com largura final diferente e acabamentos especiais continuam em Python por enquanto, porque dependem das escolhas da janela da ferramenta.
- Ao mover, girar, alterar perímetro, excluir ponto ou modificar o molde, `sincronizar_costuras_vinculadas` recalcula a costura a partir do perímetro atual.
- A costura aplicada no tamanho base é refletida nos tamanhos graduados. A seleção de remover/adicionar trabalha na base e depois replica o resultado.
- A visibilidade da costura graduada respeita a visibilidade das graduações; se as graduações estão escondidas, suas costuras também ficam escondidas.
- O botão de rodapé de costura controla mostrar/esconder as costuras sem remover os dados do molde.
- Piques não dividem nem removem costura. Inserções de pique usam o fluxo de edição do ponto sem alterar a definição dos trechos costurados.

O contrato visual é: o usuário vê a costura como uma linha pontilhada ao redor da borda, mas o dado persistido continua derivado do molde. Não crie um segundo molde para representar costura.

## Caches e invalidação

O canvas mantém caches de runtime para melhorar desempenho, especialmente em desenhos grandes:

- cache de pontos renderizados e curvas suavizadas;
- cache de caminhos Qt (`QPainterPath`) por assinatura geométrica;
- índice espacial leve para hit-test e busca de elementos;
- cache de contornos e caminhos graduados;
- assinaturas de costura vinculada para evitar recálculo quando o molde não mudou.

Esses dados são temporários. Campos internos com prefixo `_runtime_` não devem ser salvos no arquivo `.gs` como fonte de verdade. Quando um elemento muda, o fluxo correto é atualizar a estrutura do elemento, invalidar/emitir alteração pelo canvas e deixar os caches serem reconstruídos.

A janela de propriedades também trabalha com cópias limpas para edição. Ao abrir, aplicar ou restaurar propriedades, objetos Qt de runtime como `QPainterPath`, `QPixmap`, `QImage` e caches `_runtime_*` são descartados da cópia, porque eles pertencem somente ao desenho em memória e não ao molde.

Para medir gargalos locais, rode a aplicação ou os testes com:

```bash
GUIMMA_PERF=1 .venv/bin/python main.py
```

Os logs de desempenho ajudam a decidir o próximo candidato a migração para C++ sem alterar o modo de operação das ferramentas.

## Janelas e fluxo de UI

Janelas de ferramenta devem abrir inicialmente à direita, abaixo da janela de coordenadas, quando houver espaço. A posição é calculada pelo suporte comum de UI, preservando a liberdade do usuário mover a janela depois.

Exceção atual: `Propriedades dos moldes` abre centralizada sobre a janela principal. Essa janela é grande, de edição geral, e não deve usar o encaixe lateral das caixas pequenas de ferramenta.

Na aba `Visualização` de Propriedades, o bloco de checkboxes usa três colunas fixas e altura mínima. Não volte a distribuir essas opções em uma grade estreita de muitas colunas, porque o Qt comprime os rótulos e corta indicadores quando a prévia do molde ocupa o restante da janela.

A prévia de Propriedades deve desenhar piques configurados pelos segmentos reais de `piques_config`, acompanhando a aparência do canvas. O X é apenas fallback para marcações antigas sem segmentos, não o desenho padrão do pique.

As janelas de abrir/salvar/recuperar usam filtros restritos para projeto GUIMMA (`*.gs`) quando esse tipo está selecionado. A prévia deve mostrar o molde com mais nitidez e metadados úteis, sem misturar arquivos de outros tipos no filtro ativo.

## Regras transversais que o motor deve preservar

- Campos numericos de UI usam ponto decimal; `.5` deve ser tratado como `0.5` e virgula decimal deve ser rejeitada.
- Moldes precisam manter pontos oficiais separados de amostras visuais de curvas. A graduacao por tabela atua nos pontos oficiais.
- Moldes com curvas e moldes extraidos devem continuar graduaveis por ponto, usando referencias estaveis no contorno.
- Elementos soltos podem ser selecionados e manipulados, mas nao devem ser confundidos com pontos oficiais de graduacao.
- Cores de tecido e espessura de linha sao propriedades visuais que devem acompanhar moldes criados, extraidos e graduados.

## Estratégia de migração incremental

1. **Padronizar payload** das ferramentas no bridge.
2. **Mover regras geométricas** de cada ferramenta para `core/geometry/engine.py`.
3. **Trocar engine Python por binding C++** mantendo a mesma API no bridge.
4. **Converter histórico** para comandos semânticos com IDs estáveis.
5. **Generalizar edição no canvas** via nós/segmentos compartilhados.

## Contrato de integração (proposto)

- Entrada no motor: shapes + contexto da operação (clique, parâmetros, tolerâncias).
- Saída do motor: alterações estruturadas por IDs (`create/update/delete` de shape/node/segment).
- UI: aplica diffs, atualiza seleção/overlay e registra comando no histórico.

Com esse contrato, cada ferramenta deixa de “fazer a matemática” e passa a orquestrar operações de alto nível.
