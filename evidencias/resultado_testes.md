# Resultado dos testes (Etapa 6)

- Executado em: 2026-10-13T16:57:07-03:00
- Python 3.12.10 | mcp 1.30.0 | Windows 10
- Todas as operacoes foram feitas pelo protocolo MCP (stdio); dados restaurados de chamados.inicial.json no inicio.

| # | Caso | Entrada ou acao | Resultado esperado | Resultado observado | Status |
|---|------|-----------------|--------------------|---------------------|--------|
| 1 | Consulta valida | `consultar_chamado id=101` | Titulo e prioridade corretos | isError=False; titulo='Falha no login', prioridade='alta' | OK |
| 2 | Registro ausente | `consultar_chamado id=999` | Erro sem criar registro | isError=True; 'Error executing tool consultar_chamado: Chamado 999 nao encontrado'; JSON inalterado=True | OK |
| 3 | Entrada invalida (negativo) | `consultar_chamado id=-5` | Rejeicao sem alteracao | isError=True; 'Error executing tool consultar_chamado: O identificador deve ser um inteiro positivo'; JSON inalterado=True | OK |
| 4 | Entrada invalida (zero) | `consultar_chamado id=0` | Rejeicao sem alteracao | isError=True; 'Error executing tool consultar_chamado: O identificador deve ser um inteiro positivo'; JSON inalterado=True | OK |
| 5 | Entrada invalida (texto) | `consultar_chamado id='abc'` | Rejeicao sem alteracao | isError=True; 'Error executing tool consultar_chamado: 1 validation error for consultar_chamadoArguments'; JSON inalterado=True | OK |
| 6 | Entrada invalida (texto numerico) | `consultar_chamado id='101'` | Rejeicao sem alteracao | isError=True; 'Error executing tool consultar_chamado: 1 validation error for consultar_chamadoArguments'; JSON inalterado=True | OK |
| 7 | Filtro valido | `filtrar_chamados prioridade='alta'` | Apenas chamados de prioridade alta | isError=False; ids=[101, 103]; prioridades=['alta'] | OK |
| 8 | Filtro valido sem resultado | `filtrar_chamados prioridade='media'` | Lista vazia, sem erro | isError=False; total=0; chamados=[] | OK |
| 9 | Filtro invalido | `filtrar_chamados prioridade='urgente'` | Erro de validacao | isError=True; 'Error executing tool filtrar_chamados: Prioridade invalida: 'urgente'. Use alta, media ou baixa.' | OK |
| 10 | Menor privilegio (host) | `sessao sem SUPORTE_PERMITIR_ESCRITA; fechar_chamado id=101` | Ferramenta de escrita nao exposta | tools=['listar_chamados', 'consultar_chamado', 'filtrar_chamados']; isError=True; 'Unknown tool: fechar_chamado' | OK |
| 11 | Arquivo arbitrario | `resources/read file:///C:/Windows/win.ini` | Recurso inexistente (erro) | erro: Unknown resource: file:///C:/Windows/win.ini | OK |
| 12 | Confirmacao negada | `cliente_operacao.py 101, resposta 'n'` | Nenhuma chamada de escrita | saida='Confirma o FECHAMENTO do chamado 101 (Falha no login)? [s/N] Operacao cancelada. Nenhuma chamada de escrita foi feita.'; eventos fechar_chamado no log=0; status=aberto | OK |
| 13 | Confirmacao aceita | `cliente_operacao.py 101, resposta 's'` | Status fechado no JSON | status no JSON=fechado; log='ok: status alterado para fechado' | OK |
| 14 | Persistencia | `nova sessao (servidor reiniciado); consultar_chamado id=101` | Status permanece fechado | isError=False; status='fechado' | OK |
| 15 | Repeticao | `cliente_operacao.py 101 novamente, resposta 's'` | Comportamento definido: idempotente, sem nova escrita | Confirma o FECHAMENTO do chamado 101 (Falha no login)? [s/N] Resultado: {"chamado": {"id": 101, "titulo": "Falha no login", "prioridade": "alta", "status": "fechado"}, "alterado": false, "mensagem": "Chamado ja estava fechado; nada foi alterado."}; JSON inalterado=True | OK |
| 16 | ID invalido no cliente de operacao | `cliente_operacao.py abc` | Rejeitado antes de iniciar o servidor | exit=1; 'ID invalido: 'abc'. Informe um inteiro positivo.'; eventos no log=0 | OK |

**16/16 casos aprovados.**
