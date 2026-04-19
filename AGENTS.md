# AGENTS.md

## Objetivo
Este repositório deve priorizar trabalho em Pull Requests (PRs) antes de novas implementações avulsas.

## Ordem de prioridade
1. Verificar se existe PR aberto relacionado à tarefa atual.
2. Se houver PR aberto, trabalhar nele primeiro.
3. Somente iniciar nova branch ou nova implementação se não existir PR aberto aplicável.

## Regra de atuação em PRs
- Sempre considerar o PR aberto como prioridade máxima.
- Antes de qualquer alteração, atualizar a branch local com a base mais recente.
- Sempre buscar reduzir divergências com a branch principal antes de editar arquivos.
- Sempre que possível, reaproveitar o trabalho já existente no PR em vez de recriar a solução.

## Atualização de branch
Antes de começar qualquer edição:
- buscar atualizações remotas
- atualizar a branch base
- rebasear ou sincronizar a branch de trabalho com a base mais recente
- somente depois iniciar alterações

## Conflitos
Quando houver conflito:
- tentar resolver automaticamente primeiro, com segurança
- preservar a intenção funcional das duas mudanças
- evitar apagar código útil apenas para eliminar o conflito
- após resolver, validar se o sistema continua consistente

Se o conflito não puder ser resolvido com segurança:
- parar
- explicar objetivamente quais arquivos entraram em conflito
- explicar qual foi a divergência encontrada
- sugerir a menor intervenção manual possível

## Aprovação e autonomia
Preferir um fluxo com mínima interrupção:
- ler arquivos relevantes sem pedir confirmação
- editar arquivos necessários diretamente
- executar comandos locais necessários para análise, validação e correção
- evitar pedir aprovação para ações rotineiras dentro do diretório do projeto

Nunca:
- executar ações destrutivas sem necessidade real
- apagar grandes blocos de código sem confirmar consistência
- forçar soluções que escondam conflitos reais

## Estratégia de merge
Objetivo:
- aceitar o máximo possível das mudanças existentes
- incorporar novas alterações sem perder comportamento já aprovado
- minimizar retrabalho
- evitar conflitos recorrentes

Ao integrar mudanças:
- preservar APIs já usadas no projeto
- manter nomes de arquivos e estrutura existente, salvo necessidade real
- preferir ajustes pequenos e compatíveis ao invés de refatorações amplas durante resolução de PR

## Validação obrigatória
Depois de editar ou resolver conflito:
- rodar validações compatíveis com o projeto
- verificar erros de sintaxe
- verificar imports
- verificar se a funcionalidade principal afetada continua operando
- registrar claramente o que foi alterado

## Estilo de resposta
Ao final do trabalho, informar de forma objetiva:
- o que foi alterado
- em quais arquivos
- se houve conflito
- se o conflito foi resolvido automaticamente
- se ainda existe algum ponto que exige revisão humana

## Regras de segurança
Nunca mascarar problema para “forçar” merge limpo.
Nunca inventar sucesso de validação.
Nunca afirmar que não há conflito sem verificar.
Sempre preferir transparência e consistência do repositório.

## Preferências deste repositório
- Priorizar PRs abertos sempre
- Tentar resolver conflitos automaticamente sempre que for seguro
- Fazer o máximo possível sem interromper o fluxo
- Manter compatibilidade com a base existente
- Evitar mudanças desnecessárias fora do escopo da tarefa