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

A ferramenta `Extrair Molde` já passou a consumir a bridge para:

- teste de ponto interno
- construção do molde
- preenchimento de metadados de identidade (`shape_id`, `node_ids`, `segment_ids`)

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
