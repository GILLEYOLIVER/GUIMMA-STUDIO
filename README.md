# GUIMMA STUDIO

GUIMMA STUDIO e uma aplicacao desktop para modelagem de moldes, desenho tecnico, graduacao de tamanhos e organizacao de informacoes de producao.

## Funcionalidades principais

- Desenho no canvas com retas, retangulos, curvas, textos, piques e elementos auxiliares.
- Criacao e extracao de moldes a partir de geometrias desenhadas.
- Graduacao via tabela com abas DX/DY, Distancia/Angulo e Perimetro.
- Grade de tamanhos por molde, com tamanho base, nomes e cores sincronizados entre canvas, tabela e propriedades.
- Visualizacao por tecido: quando "Mostrar cor dos tecidos" esta marcado, o contorno do molde segue a cor configurada para o tecido.
- Controle de linha por cor, estilo e espessura; moldes e elementos derivados devem respeitar a espessura definida.
- Selecao de moldes e tambem de elementos soltos, como linhas, curvas e desenhos livres.
- Snap/ima para aproximacao em pontos e angulos padrao quando a ferramenta ativa suporta esse comportamento.
- Salvamento, abertura, recentes, undo/redo e pontos de restauracao internos.

## Regras atuais de uso

- Campos numericos usam ponto como separador decimal. Exemplos validos: `0.5`, `.5`, `1.25`, `-0.5`.
- Virgula decimal nao deve ser aceita em campos de entrada.
- Ao digitar `.5`, `.1` ou `.9`, o programa interpreta como `0.5`, `0.1` ou `0.9`.
- Moldes novos herdam a grade de tamanhos, nomes e cores dos moldes ja presentes no canvas quando houver uma grade ativa.
- Em portugues, a grade inicial padrao e `P`, `M`, `G`, com `M` como base. Em espanhol, a grade inicial padrao e `S`, `M`, `L`, com `M` como base.
- A tabela de graduacao deve conseguir selecionar e graduar pontos oficiais de qualquer molde, incluindo moldes com curvas e moldes extraidos.
- Elementos livres nao sao pontos oficiais de molde; a graduacao pela tabela atua nos pontos do molde selecionado.

## Documentacao

- Manual do usuario: `docs/MANUAL_DO_PROGRAMA.md`
- Mapa do projeto e ferramentas: `docs/MAPA_PROJETO.md`
- Arquitetura do motor geometrico: `docs/ARQUITETURA_MOTOR_GEOMETRICO.md`

## Validacao local

Com o ambiente Python configurado:

```powershell
python -m py_compile app.py guimma_app.py
python -m pytest tests\test_formatacao.py tests\test_visualizacao_controles.py tests\test_selecionar_tool.py tests\test_tabela_tool.py -q
```
