# Implementação de MCP em um assistente de suporte

**Atividade prática avaliativa — Análise e Desenvolvimento de Sistemas, 6º semestre**

Integrantes: [NOME 1] · [NOME 2] · [NOME 3]
Data: 13/10/2026
Ambiente: Python 3.12.10 · SDK `mcp` 1.30.0 (linha 1.x) · Windows 10 · protocolo 2025-11-25

---

## 1. Objetivo

Construir um servidor Model Context Protocol (MCP) que dê a uma aplicação de IA acesso **padronizado e controlado** a chamados de suporte fictícios. Sem isso, o modelo não conhece os registros atuais e pode inventar prioridades e status. O servidor expõe uma Resource, quatro Tools (três de leitura e uma de escrita) e um Prompt. Os dados ficam persistidos em JSON e todas as operações são registradas em log de auditoria.

## 2. Arquitetura e responsabilidades

```
┌──────────────────────── HOST (aplicação de IA) ────────────────────────┐
│                                                                        │
│   LLM ── escolhe ferramenta e argumentos ──►  CLIENTE MCP              │
│    ▲      (a partir de nome, descrição           (ClientSession)       │
│    │       e inputSchema)                            │                 │
│    └──────── resultado da ferramenta ◄───────────────┤                 │
└──────────────────────────────────────────────────────┼─────────────────┘
                              JSON-RPC 2.0 sobre stdio │ (stdin / stdout)
                                                       ▼
            ┌────────── SERVIDOR MCP  servidor.py (processo filho) ──────────┐
            │ Resource  suporte://politica       Prompt  analisar_chamado     │
            │ Tools     listar_chamados · consultar_chamado · filtrar_chamados│
            │           fechar_chamado*  (*só com SUPORTE_PERMITIR_ESCRITA=1) │
            │ validação de entrada ──► auditoria (stderr + logs/auditoria.log)│
            └──────────────────────────────┬──────────────────────────────────┘
                                           ▼  único arquivo acessado
                                   dados/chamados.json

  Fluxo de escrita:  usuário no terminal ─► cliente_operacao.py (pergunta s/N)
                     ─► inicia servidor com escrita habilitada ─► fechar_chamado
```

| Componente | Responsabilidade |
|------------|------------------|
| **Host** | Aplicação que o usuário usa (chat com IA). Contém o LLM, gerencia o cliente MCP, apresenta as ferramentas ao modelo e pode pedir aprovação humana antes de uma chamada. |
| **LLM** | Interpreta o pedido, **decide** se chama uma ferramenta e com quais argumentos, e redige a resposta final a partir do retorno. Não acessa os dados diretamente. |
| **Cliente MCP** | Mantém a sessão 1:1 com um servidor: `initialize`, descoberta (`tools/list`, `resources/list`, `prompts/list`) e chamadas (`tools/call`, `resources/read`, `prompts/get`). |
| **Servidor MCP** | Declara as capacidades, valida entradas, executa a operação e devolve o resultado ou um erro (`isError: true`). É o único que toca nos dados. |
| **Transporte stdio** | O cliente inicia o servidor como **processo filho** e troca mensagens JSON-RPC pelo stdin/stdout dele. Por isso o servidor nunca usa `print`: qualquer texto no stdout corromperia o protocolo. Logs vão para stderr. |

O SDK (`FastMCP`) cuida da serialização JSON-RPC, do ciclo de vida da sessão e da geração dos schemas a partir das anotações de tipo do Python.

## 3. Implementação

| Primitiva | Assinatura | Comportamento |
|-----------|------------|---------------|
| Resource | `suporte://politica` (text/plain) | Regras que a IA deve seguir: não inventar dados, relatar erros, exigir confirmação para escrita. |
| Tool (leitura) | `listar_chamados() -> ListaChamados` | Todos os chamados com id, título, prioridade e status. |
| Tool (leitura) | `consultar_chamado(id: int) -> Chamado` | Erro se `id ≤ 0` ou inexistente; nunca cria registro. |
| Tool (leitura) | `filtrar_chamados(prioridade) -> ResultadoFiltro` | Aceita só `alta`, `media`, `baixa`. Filtro válido sem resultados retorna lista vazia; outro valor retorna erro. |
| Tool (escrita) | `fechar_chamado(id: int) -> ResultadoFechamento` | Muda o status para `fechado` e grava. Idempotente: em chamado já fechado retorna `alterado: false` sem gravar. |
| Prompt | `analisar_chamado(id: str)` | Instrui a IA a consultar pela ferramenta e explicar a prioridade só com base no retorno. |

**Implementação autoral (Etapa 5):**

- **Persistência.** Os registros saíram da memória para `dados/chamados.json`. O caminho é calculado a partir de `__file__`, nunca vem do cliente. O arquivo é relido a cada chamada, então alterações persistidas são vistas por qualquer sessão. A gravação usa arquivo temporário + `os.replace`, de modo que uma falha no meio não deixa JSON corrompido. Foi adicionado o campo `status` (`aberto`/`fechado`).
- **Tipos de retorno.** São declarados com `TypedDict`. O SDK gera um `outputSchema` e valida o `structuredContent` antes de responder, então um registro com prioridade ou status fora do domínio vira erro, não dado inválido.
- **Anotações.** As ferramentas de leitura levam `readOnlyHint=true`. `fechar_chamado` leva `destructiveHint=true` e `idempotentHint=true`, para que o host saiba que deve pedir aprovação.
- **Cliente de operação.** `cliente_operacao.py` valida o ID localmente, consulta e mostra o chamado, e pergunta `[s/N]`. Qualquer resposta diferente de `s`/`sim`, ou entrada vazia, cancela **sem chamar** `fechar_chamado`.
- **Auditoria.** Cada operação gera uma linha JSON em `logs/auditoria.log` e em stderr: `timestamp`, `pid`, `operacao`, `id` ou `prioridade`, `resultado`. Exemplo real:
  `{"timestamp": "2026-10-13T16:57:04-03:00", "pid": 29328, "operacao": "fechar_chamado", "id": 101, "resultado": "ok: status alterado para fechado"}`

## 4. Decisões de segurança

1. **Menor privilégio por padrão.** Sem a variável `SUPORTE_PERMITIR_ESCRITA=1`, o servidor nem registra `fechar_chamado`. O host de IA, configurado sem ela, só enxerga ferramentas de leitura (teste 10: `Unknown tool: fechar_chamado`). A escrita fica restrita ao cliente com confirmação.
2. **Nenhuma superfície arbitrária.** Não há ferramenta que receba caminho, comando de shell ou SQL. A única Resource tem URI fixa. Pedir `file:///C:/Windows/win.ini` retorna `Unknown resource` (teste 11).
3. **Validação em camadas.** (a) O schema anuncia tipos e o `enum` de prioridades para orientar o modelo, mas o schema **não garante** o que chega. (b) O SDK valida o tipo com `strict=True`, então `"abc"` e até `"101"` (texto) são rejeitados. (c) O próprio servidor valida os valores: ID positivo, prioridade na lista, chamado existente.
4. **Erros como resultado de ferramenta.** Erros voltam como `isError: true` com mensagem clara. O modelo recebe "Chamado 999 nao encontrado" em vez de silêncio, que poderia levá-lo a inventar.
5. **Rastreabilidade.** O log de auditoria permite verificar se uma resposta da IA corresponde a uma execução real: mesma operação, mesmo ID, mesmo horário e PID do processo servidor. Nenhuma credencial é registrada.
6. **Escrita idempotente e atômica.** Repetir o fechamento não gera nova escrita (teste 15), e a troca de arquivo é atômica.

## 5. Testes (executados pelo cliente MCP, `python testes.py`)

| # | Caso | Entrada ou ação | Esperado | Observado | Status |
|---|------|-----------------|----------|-----------|--------|
| 1 | Consulta válida | `consultar_chamado(101)` | Título e prioridade corretos | "Falha no login", alta | OK |
| 2 | Registro ausente | `consultar_chamado(999)` | Erro sem criar registro | `isError=true` "Chamado 999 nao encontrado"; JSON inalterado | OK |
| 3–4 | Entrada inválida | `id=-5`, `id=0` | Rejeição sem alteração | `isError=true` "O identificador deve ser um inteiro positivo"; JSON inalterado | OK |
| 5–6 | Entrada inválida | `id="abc"`, `id="101"` | Rejeição sem alteração | `isError=true` validação de tipo do SDK; JSON inalterado | OK |
| 7 | Filtro válido | `filtrar_chamados("alta")` | Só prioridade alta | ids [101, 103], todos "alta" | OK |
| 8 | Filtro válido vazio | `filtrar_chamados("media")` | Lista vazia | `total=0, chamados=[]` | OK |
| 9 | Filtro inválido | `filtrar_chamados("urgente")` | Erro de validação | `isError=true` "Prioridade invalida" | OK |
| 10 | Menor privilégio | sessão do host chama `fechar_chamado` | Escrita não exposta | `Unknown tool: fechar_chamado` | OK |
| 11 | Arquivo arbitrário | `resources/read file:///C:/Windows/win.ini` | Erro | `Unknown resource` | OK |
| 12 | Confirmação negada | fechar 101, responde `n` | Nenhuma chamada de escrita | "Operacao cancelada"; 0 eventos `fechar_chamado` no log; status aberto | OK |
| 13 | Confirmação aceita | fechar 101, responde `s` | Status fechado no JSON | JSON: `fechado`; log: "ok: status alterado para fechado" | OK |
| 14 | Persistência | nova sessão (novo processo), consultar 101 | Continua fechado | `status=fechado` | OK |
| 15 | Repetição | fechar 101 de novo, `s` | Comportamento definido | `alterado=false`, "ja estava fechado"; JSON inalterado | OK |
| 16 | ID inválido no cliente | `cliente_operacao.py abc` | Rejeitar antes do servidor | exit 1; nenhum evento no log | OK |

Resultado: **16/16 aprovados**. A tabela completa gerada automaticamente está em `evidencias/resultado_testes.md` e a saída do cliente de verificação em `evidencias/saida_cliente.txt`.

**Repetição (caso 15):** optamos por idempotência. Fechar um chamado já fechado não é erro: o objetivo do usuário (chamado fechado) já está atendido. O servidor informa `alterado: false`, não grava e registra "sem alteracao" no log. Assim uma nova tentativa após falha de rede é segura.

## 6. Resposta do modelo × operação executada

O `cliente.py` e o `testes.py` **não contêm LLM**: cada chamada foi escrita pelo programador, o que prova o protocolo, mas não é um agente de IA. Na integração com o host (Etapa 4), quem escolhe a ferramenta e os argumentos é o modelo. Uma resposta só está **sustentada** quando existe a tool call correspondente e o texto bate com o retorno dela. A conferência é feita em duas fontes independentes: o registro de tool calls do host e a linha correspondente em `logs/auditoria.log`.

| Pedido | Ferramenta / argumentos | Resultado da ferramenta | Resposta da IA | Sustentada? |
|--------|-------------------------|-------------------------|----------------|-------------|
| "Consulte o chamado 101 e informe título e prioridade. Use a ferramenta disponível." | [preencher] | [preencher] | [preencher] | [sim/não] |
| "Consulte o chamado 999. Caso não exista, informe isso sem criar dados." | [preencher] | [preencher] | [preencher] | [sim/não] |
| "Liste os chamados e indique quais possuem prioridade alta." | [preencher] | [preencher] | [preencher] | [sim/não] |

[Inserir capturas de tela do host mostrando as tool calls e as linhas do `auditoria.log` com o mesmo horário.]

## 7. Limitações

- **A confirmação não é autenticação.** É controle de fluxo do cliente. Quem iniciar o servidor com `SUPORTE_PERMITIR_ESCRITA=1` fecha chamados sem confirmar, e o servidor não sabe *quem* é o usuário.
- **Concorrência.** Sem controle entre processos: dois servidores (ex.: host e cliente de operação) fazendo leitura-modificação-escrita ao mesmo tempo podem perder uma atualização. O `os.replace` evita arquivo corrompido, mas não esse caso.
- **Log.** É local, sem rotação, sem proteção contra adulteração e sem identificação de usuário. Entradas barradas pela validação de tipo do SDK não chegam à função e por isso não aparecem no log de auditoria.
- **Anotações e Resource são orientações.** `readOnlyHint`, `destructiveHint` e a política em `suporte://politica` dependem do host e do modelo respeitarem. O controle efetivo está no servidor (validação e ferramenta de escrita não registrada).
- **Escopo.** Dados fictícios em JSON, sem paginação e com transporte só local (stdio).

## 8. Questões para reflexão

**1. Por que MCP não substitui o LLM nem uma base RAG?**
MCP é um **protocolo de integração**: padroniza como um host descobre e chama capacidades externas. Ele não interpreta linguagem natural, não raciocina e não redige respostas; isso é papel do LLM. RAG é uma técnica de **recuperação de conhecimento**: indexar documentos (normalmente com embeddings) e injetar trechos relevantes no contexto. MCP pode transportar uma ferramenta de busca RAG, mas não faz indexação nem busca semântica. Os três se complementam. Neste projeto, a ferramenta dá o dado exato e atual do chamado 101, algo que uma busca aproximada em documentos não garante.

**2. Qual parte do projeto decide chamar uma ferramenta?**
Com IA, quem **decide** é o LLM dentro do host, a partir do nome, descrição e schema anunciados no `tools/list`. O host/cliente **executa** a decisão e pode exigir aprovação humana. O servidor **não decide** nada: valida e executa o que recebe. No `cliente.py` e no `testes.py`, a decisão é do código, ou seja, do programador.

**3. O que a ferramenta retorna quando o modelo inventa um ID?**
Um resultado de erro (`isError: true`) com a mensagem "Chamado 999 nao encontrado", sem criar nem alterar registros (testes 2–6). IDs não positivos ou em texto também são rejeitados. A operação fica no log. Se a IA ainda assim afirmar título ou prioridade, a resposta não está sustentada por nenhum retorno de ferramenta.

**4. Qual risco permanece com confirmação apenas no cliente?**
O servidor confia em quem o iniciou. Outro cliente, um script ou um host configurado com escrita e aprovação automática ("permitir sempre") pode chamar `fechar_chamado` sem confirmação. Um texto malicioso dentro dos dados (*prompt injection*) também pode induzir o modelo a pedir a escrita. Além disso, não há identificação do usuário no log, e quem tem acesso ao arquivo pode editá-lo diretamente.

**5. Como migrar para múltiplos usuários com autenticação e controle de concorrência?**
- Trocar stdio por **Streamable HTTP** com HTTPS e a **autorização OAuth 2.1** prevista na especificação MCP. O servidor valida o token a cada requisição e conhece o usuário.
- Aplicar **RBAC** no servidor: perfil "leitor" só lista e consulta; perfil "atendente" pode fechar.
- Mover os dados para um **SGBD** (ex.: PostgreSQL) com transações. Usar **controle otimista** com coluna `versao` (`UPDATE ... WHERE id = ? AND versao = ?`) ou bloqueio de linha (`SELECT ... FOR UPDATE`).
- Levar a **confirmação para o servidor**: fluxo em duas etapas com token de confirmação, ou *elicitation* do MCP quando o host suportar.
- Registrar **auditoria com o ID do usuário** em tabela só de inserção, com limites de taxa por usuário.

## Referências

- MODEL CONTEXT PROTOCOL. *Specification*. Disponível em: https://modelcontextprotocol.io/specification. Acesso em: 13 out. 2026.
- MODEL CONTEXT PROTOCOL. *Python SDK — documentação v1.x*. Disponível em: https://py.sdk.modelcontextprotocol.io/v1/. Acesso em: 13 out. 2026.
- MODEL CONTEXT PROTOCOL. *python-sdk* (repositório). Disponível em: https://github.com/modelcontextprotocol/python-sdk. Acesso em: 13 out. 2026.
- Material base da disciplina: *Model Context Protocol (MCP)*, PDF fornecido pelo professor.
