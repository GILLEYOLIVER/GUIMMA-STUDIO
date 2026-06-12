# Manual do Programa — Ferramentas

Este manual resume **o que cada ferramenta faz** no ribbon atual do GUIMMA STUDIO.

## Como ler este manual

- Ferramentas com módulo em `tools/` estão disponíveis no programa atual.
- Ferramentas citadas como **em desenvolvimento** existem no mapa do ribbon ou na pasta `FERRAMENTAS NAO PRONTAS`, mas ainda não têm implementação final em `tools/`.
- Quando uma ferramenta altera moldes, o comportamento esperado é preservar controles principais, controles auxiliares, fio, piques, nome e metadados sempre que esses dados existirem no molde.

## Atualizações recentes de comportamento

- **Curva**: ao fechar uma figura em modo curva, o fechamento passa a ser suave; o último ponto não deve quebrar a curva formando quina indevida.
- **Extrair Molde**: ao extrair um molde, pontos principais devem representar nós reais, emendas ou encontros de segmentos. Curvas continuam sustentadas por pontos auxiliares, evitando excesso de pontos principais no molde extraído.
- **Graduação via Tabela**: a tabela lê os tamanhos, nomes, cores e tamanho base do molde ativo. Clique normal seleciona apenas um ponto do contorno; `Ctrl + clique` acumula vários pontos para aplicar a mesma graduação. As setas alteram somente o eixo correspondente, preservando a graduação já existente no outro eixo.
- **Remover Graduação**: remove toda a graduação apenas do molde clicado, sem afetar outros moldes.
- **Giro e fio**: duplo clique na borda ou no fio alinha o molde a 0°/90° quando a opção de rotacionar com clique duplo está ativa. A ferramenta Girar permite ângulo livre com ímã leve nos ângulos usuais.
- **Propriedades dos moldes**: a janela abre centralizada e a grade de tamanhos sincroniza imediatamente com as ferramentas que dependem dos tamanhos do molde.
- **Prévia/sombra do molde original**: sombras e prévias devem respeitar os controles atuais do molde e não exibir pontos antigos que já não fazem parte da estrutura oficial.
- **Simplificar Contorno**: remove pontos redundantes da amostragem do contorno, mas mantém controles principais e auxiliares que definem a forma.

## Ferramentas prontas/atualizadas

Estas ferramentas já possuem comportamento implementado e devem ser usadas como referência de operação:

- **Extrair Molde** (`extrair_molde`): identifica contornos fechados, compõe partes quando necessário e cria o molde com pontos principais, pontos auxiliares, fio, nome e numeração. O painel de definição abre junto da caixa de coordenadas no lado direito.
- **Criar Molde** (`criar_molde`): transforma contornos selecionados em molde editável com metadados de modelagem.
- **Curva** (`curva`): desenha curvas por pontos de controle e fecha figuras com continuidade suave no ponto de fechamento.
- **Manipular Pontos** (`manipular_pontos`): move pontos principais e auxiliares do molde, com ajuste fino, caixa de coordenadas, preservação das curvas e cancelamento do arraste com botão direito.
- **Mover Ponto** (`mover_ponto`): variação direta da manipulação para deslocar um ou vários pontos por arraste ou por DX/DY.
- **Inserir Ponto** (`inserir_ponto`): adiciona ponto principal no molde/contorno preservando auxiliares necessários à curva.
- **Excluir Ponto** (`excluir_ponto`): realça os pontos oficiais do molde selecionado, prende o hover no controle mais próximo e exclui pontos principais ou auxiliares mantendo a curva válida.
- **Simplificar Contorno** (`simplificar_contorno`): simplifica contornos selecionados ou clicados, removendo amostras redundantes e preservando controles oficiais.
- **Redefinir Perímetro** (`redefinir_perimetro`): ajusta o perímetro preservando controles e auxiliares do molde.
- **Elemento Paralelo** (`elemento_paralelo`): cria linhas ou contornos paralelos a partir de clique ou seleção.
- **Girar** (`girar`): gira elementos selecionados por ângulo mantendo controles, piques, fio e dados do molde. Na ferramenta de giro, o ângulo é livre e tem apenas um ímã leve nos ângulos mais usados.
- **Espelhar** (`espelhar`): espelha elementos ou moldes preservando controles e metadados.
- **Dobrar** (`dobrar`): dobra moldes como papel por reta, meio ou linha interna, preservando o original.
- **Desdobrar** (`desdobrar`): reabre dobra preservada usando eixo original, linha interna, perímetro ou reta manual.
- **Sentido Fio** (`sentido_fio`): define o fio do molde por dois pontos ou por ângulo.
- **Costura** (`costura`): cria e edita margens/acabamentos de costura no molde.
- **Remover Costura** (`remover_costura`): remove margens de costura aplicadas.
- **Propriedades** (`propriedades`): abre a janela de propriedades do molde para editar nome, fio, numeração, grade e exibição. A janela abre centralizada; alterações na grade de tamanhos, base e cores são propagadas para as ferramentas de graduação.
- **Auto Ajuste** (`ajuste_automatico`): reposiciona automaticamente textos, fio e informações visuais dos moldes.
- **Ponto de Restauração** (`ponto_restauracao`) e **Restaurar** (`restaurar_copia`): salvam e restauram cópias internas de segurança do molde.

## Aba Início

### Ações rápidas
- **Desfazer** (`desfazer`): volta a última alteração registrada no histórico.
- **Refazer** (`refazer`): reaplica uma alteração desfeita.
- **Salvar** (`salvar`): salva o projeto atual no arquivo associado.
- **Salvar como** (`salvar_como`): salva o projeto atual em um novo arquivo/caminho.

### Desenho
- **Cor** (`cor`): define cor, estilo e espessura do traço de desenho. Em desenvolvimento como módulo independente.
- **Colar** (`colar`): Cola no desenho o conteúdo copiado.
- **Selecionar** (`selecionar`): Seleciona elementos para editar, mover ou excluir.

### Editar
- **Recortar** (`recortar`): Recorta a seleção atual para reposicionar em seguida.
- **Copiar** (`copiar`): Copia a seleção atual para a área de transferência.
- **Excluir** (`excluir`): Remove os elementos selecionados.

### Selecionar
- **Inverter Selecao** (`inverter_selecao`): Executa a ação específica indicada pelo nome da ferramenta.
- **Selecionar Tudo** (`selecionar_tudo`): Seleciona elementos conforme o critério da ferramenta.
- **Inverter Moldes** (`inverter_moldes`): Executa operação relacionada à criação/seleção/informação de moldes.
- **Selecionar Moldes** (`selecionar_moldes`): Seleciona elementos conforme o critério da ferramenta.

### Restauração
- **Ponto de Restauração** (`ponto_restauracao`): Cria uma cópia interna do molde selecionado para restauração posterior.
- **Restaurar** (`restaurar`): restaura um ponto de restauração salvo. Em desenvolvimento como ferramenta separada.
- **Restaurar Cópia** (`restaurar_copia`): Restaura uma cópia interna salva, substituindo o molde atual ou criando uma cópia restaurada.

### Configuração
- **Cores** (`cores`): abre/aciona ajustes de cores do programa. Em desenvolvimento como módulo independente.
- **Unidade** (`unidade_medidas`): alterna ou configura unidade de medida usada no projeto. Em desenvolvimento como módulo independente.

### Saída
- **Imprimir** (`imprimir`): prepara saída impressa do projeto. Em desenvolvimento.
- **Plotar** (`plotar`): prepara envio para plotter. Em desenvolvimento.

## Aba Construção

### Retas
- **Reta** (`reta`): Desenha uma reta entre dois pontos.
- **Retângulo** (`retangulo`): Cria retângulos com base em referência no canvas.
- **Por Ângulo** (`por_angulo`): Cria linha/reta com direção angular controlada.
- **Estender reta** (`estender_reta`): Estende uma reta até novo ponto de destino.
- **Estender até elemento** (`estender_ate_elemento`): Estende uma reta até tocar outro elemento.
- **Estender duas retas** (`estender_duas_retas`): Estende duas retas até o ponto de encontro.

### Curvas
- **Curva** (`curva`): Desenha curva por pontos de controle; no fechamento, mantém continuidade suave para evitar quina indevida no último ponto.
- **Dividir Curva** (`dividir_curva`): Divide uma curva em segmentos menores.
- **Espiral e Curvas** (`espiral_e_curvas`): Cria espirais e curvas especiais.
- **Cadastrar curvas** (`cadastrar_curva`): Salva/cadastra um modelo de curva para reuso.
- **Editar Pontos de Curva** (`editar_pontos_de_curva`): Ajusta pontos de controle de curvas existentes.
- **Predefinida** (`predefinida`): Insere curva predefinida.

### Pontos
- **Por Coordenada** (`por_coordenada`): Insere ponto/elemento por coordenadas numéricas.
- **Por Interseção** (`por_intersecao`): Cria ponto na interseção de elementos.
- **No Centro do Arco** (`no_centro_do_arco`): Cria ponto no centro geométrico do arco.
- **No Perímetro** (`no_perimetro`): Cria ponto sobre o perímetro do elemento.
- **Por Distância** (`por_distancia`): Posiciona ponto por distância medida.

### Arcos
- **Por raio** (`por_raio`): Cria arco/circunferência por raio.

### Texto
- **Inserir Texto** (`inserir_texto`): Insere texto técnico no molde.
- **Editar Texto** (`editar_texto`): Edita conteúdo e estilo de textos existentes.

## Aba Produção

### Definir moldes
- **Extrair Molde** (`extrair_molde`): Extrai contornos fechados como moldes, detectando piques, graduações e linhas auxiliares conforme a configuração. Emendas, encontros de segmentos e nós reais viram controles principais; curvas seguem sustentadas por auxiliares.
- **Criar Molde** (`criar_molde`): Converte contornos selecionados em molde com controles, fio, nome e metadados.
- **Digitalizar** (`digitalizar`): Executa a ação específica indicada pelo nome da ferramenta.
- **Sentido Fio** (`sentido_fio`): Define o sentido do fio com dois pontos ou por ângulo.

### Complementar moldes
- **Encolhimento** (`encolhimento`): Executa a ação específica indicada pelo nome da ferramenta.
- **Linha Simetria** (`linha_simetria`): Executa a ação específica indicada pelo nome da ferramenta.
- **Bainha** (`bainha`): Executa a ação específica indicada pelo nome da ferramenta.
- **Dobrar** (`dobrar`): Dobra moldes como papel, preservando o original e gerando linha/eixo de dobra.
- **Desdobrar** (`desdobrar`): Reabre uma dobra preservada usando eixo original, linha interna, perímetro ou reta manual.

### Costura
- **Costura** (`costura`): Define, altera ou remove parâmetros de costura.
- **Remover Costura** (`remover_costura`): Remove margem/acabamento de costura do molde.
- **Trocar Costura** (`trocar_costura`): troca ou redefine o tipo de costura aplicado. Em desenvolvimento.

### Pregas e pences
- **Pregas** (`pregas`): Aplica operações de pences e pregas no molde.
- **Pence Contorno** (`pence_contorno`): Aplica operações de pences e pregas no molde.
- **Pence Interna** (`pence_interna`): Aplica operações de pences e pregas no molde.
- **Fechar Pence** (`fechar_pence`): Aplica operações de pences e pregas no molde.

### Cortar e unir
- **Multiplas Pences** (`multiplas_pences`): Aplica operações de pences e pregas no molde.
- **Cortar** (`cortar`): Executa a ação específica indicada pelo nome da ferramenta.
- **Unir** (`unir`): Executa a ação específica indicada pelo nome da ferramenta.

## Aba Marcações

### Piques
- **Inserir Pique** (`inserir_pique`): Insere, remove ou ajusta piques de marcação.
- **Remover Pique** (`remover_pique`): Insere, remove ou ajusta piques de marcação.
- **Pique Texto** (`pique_texto`): Insere, remove ou ajusta piques de marcação.
- **Multiplos** (`multiplos`): Executa a ação específica indicada pelo nome da ferramenta.

### Editar piques
- **Alinhar** (`alinhar`): Transforma a geometria para reposicionamento e ajuste.
- **Substituir** (`substituir`): Executa a ação específica indicada pelo nome da ferramenta.
- **Alterar** (`alterar`): Executa a ação específica indicada pelo nome da ferramenta.

## Aba Graduação

### Graduar
- **Tabela** (`tabela`): gradua pontos do contorno via tabela `DX/DY`.
  - A janela sempre usa os tamanhos, nomes, cores e tamanho base gravados no molde atual.
  - Clique normal em um ponto do contorno seleciona somente aquele ponto para graduação.
  - `Ctrl + clique` acumula ou remove pontos da seleção, permitindo graduar vários pontos juntos sem fechar a janela.
  - Os valores aplicados pela tabela afetam apenas os pontos selecionados.
  - As setas horizontais alteram `DX`; as setas verticais alteram `DY`. Usar uma seta de um eixo não apaga os valores já definidos no outro eixo.
  - O campo incremental aceita medidas limpas, como `1 cm`, `1.1 cm`, `1.78 cm` ou `2 cm`, sem zeros desnecessários.
  - A linha do tamanho base preserva a cor do tamanho; o destaque azul aparece apenas nas células numéricas `DX/DY` da base.
  - Se o molde for fechado/removido do canvas, a janela da Tabela fecha automaticamente.
- **Mouse** (`mouse`): Executa a ação específica indicada pelo nome da ferramenta.
- **Regras** (`regras`): Gerencia regras e tabelas de graduação.
- **Criar Regra** (`criar_regra`): Gerencia regras e tabelas de graduação.

### Manipular graduação
- **Remover Graduacao** (`remover_graduacao`): clique em um molde para remover toda a graduação daquele molde, incluindo tabela, pontos graduados e grade de tamanhos. Não altera outros moldes.
- **Separar Tamanhos** (`separar`): Executa a ação específica indicada pelo nome da ferramenta.
- **Agrupar** (`agrupar`): Executa a ação específica indicada pelo nome da ferramenta.
- **Graduar Curva** (`graduar_curva`): Executa operação de criação, ajuste ou conferência de curvas.

## Aba Manipulação

### Redefinir
- **Modificar** (`modificar`): Edita parâmetros/elementos já existentes no desenho.
- **Editar** (`editar`): Edita parâmetros/elementos já existentes no desenho.
- **Manipular Pontos** (`manipular_pontos`): Manipula pontos principais e auxiliares do molde, com caixa de coordenadas, ajuste fino e cancelamento por botão direito durante o arraste.
- **Mover** (`mover`): Transforma a geometria para reposicionamento e ajuste.
- **Mover Ponto** (`mover_ponto`): Move um ou vários pontos por arraste ou por deslocamento DX/DY.
- **Manipulação rápida** (`manipulacao_rapida`): reúne ações rápidas de manipulação geométrica. Em desenvolvimento.
- **Redefinir Perímetro** (`redefinir_perimetro`): Ajusta o perímetro preservando controles oficiais do molde.
- **Dividir elementos** (`dividir_elementos`): divide elementos selecionados em partes independentes. Em desenvolvimento.

### Indicar
- **Elemento Paralelo** (`elemento_paralelo`): Cria linha ou contorno paralelo por clique ou por seleção.
- **Girar** (`girar`): Gira elementos selecionados por ângulo, preservando controles, piques e fio.
- **Copiar** (`copiar`): copia elementos selecionados para o buffer interno.
- **Dimensionar** (`dimensionar`): escala ou redimensiona elementos/molde selecionado. Em desenvolvimento.
- **Espelhar** (`espelhar`): Espelha elementos ou moldes preservando controles e metadados.

### Cerca
- **Definir cerca** (`definir_cerca`): define uma área/cerca de seleção ou manipulação. Em desenvolvimento.
- **Mover cerca** (`mover_cerca`): desloca a cerca definida e seus elementos relacionados. Em desenvolvimento.

### Manipular molde
- **Definir curva** (`definir_curva`): converte ou ajusta trecho de molde para comportamento de curva. Em desenvolvimento.
- **Inserir Ponto** (`inserir_ponto`): adiciona ponto principal no contorno do molde, atualizando controles e preservando auxiliares de curva.
- **Excluir Ponto** (`excluir_ponto`): Exclui pontos principais ou auxiliares, realça os controles do molde selecionado e prende o hover no ponto mais próximo.
- **Transformar em elementos** (`transformar_em_elementos`): transforma molde/estrutura em elementos editáveis independentes. Em desenvolvimento.
- **Alinhar** (`alinhar`): alinha ou distribui elementos selecionados.
- **Copiar ou trocar elemento** (`copiar_ou_trocar_elemento`): copia ou substitui elemento do molde. Em desenvolvimento.
- **Arredondar Ou Chanfrar** (`arredondar_ou_chanfrar`): Executa a ação específica indicada pelo nome da ferramenta.
- **Simplificar contorno** (`simplificar_contorno`): remove pontos redundantes da linha do contorno sem apagar controles principais/auxiliares oficiais.

## Aba Conferência

### Perímetro
- **Conferir** (`conferir`): Confere medidas e consistência do molde.
- **Conferir Multiplos** (`conferir_multiplos`): Confere medidas e consistência do molde.
- **Controle Curvas** (`controle_curvas`): Executa operação de criação, ajuste ou conferência de curvas.
- **Cota Perimetro** (`cota_perimetro`): Mede ou compara distâncias no desenho.
- **Perimetro** (`perimetro`): consulta ou calcula perímetro do elemento/molde. Em desenvolvimento.

### Distância
- **Cota Distancia** (`cota_distancia`): Mede ou compara distâncias no desenho.
- **Distancia** (`distancia`): Mede ou compara distâncias no desenho.
- **Comparar Distancia** (`comparar_distancia`): Mede ou compara distâncias no desenho.
- **Raio** (`raio`): Executa a ação específica indicada pelo nome da ferramenta.

## Aba Modelo

### Informações
- **Propriedades** (`propriedades`): Abre a janela de propriedades dos moldes selecionados.
- **Tecidos** (`tecidos`): Executa a ação específica indicada pelo nome da ferramenta.
- **Autor** (`autor`): Executa a ação específica indicada pelo nome da ferramenta.
- **Informacoes Moldes** (`informacoes_moldes`): Executa operação relacionada à criação/seleção/informação de moldes.

### Operações
- **Variantes** (`variantes`): Executa a ação específica indicada pelo nome da ferramenta.
- **Relacionamento Piques** (`relacionamento_piques`): Insere, remove ou ajusta piques de marcação.
- **Imagens** (`imagens`): Executa a ação específica indicada pelo nome da ferramenta.
- **Substituir** (`substituir`): Executa a ação específica indicada pelo nome da ferramenta.

## Aba Usuários

- Esta aba é usada para organizar a linha de usuário (atalhos personalizados).
- **Auto Ajuste** (`ajuste_automatico`): Ferramenta fixa da barra de usuário para reorganizar automaticamente nome, fio e textos dos moldes.
