# MCP Suporte ADS

Servidor **Model Context Protocol** (SDK Python oficial, linha 1.x) que expõe chamados de suporte **fictícios** para uma aplicação de IA, via transporte **stdio**.

| Primitiva | Nome | Tipo de acesso |
|-----------|------|----------------|
| Resource | `suporte://politica` | leitura (regras de uso) |
| Tool | `listar_chamados()` | leitura |
| Tool | `consultar_chamado(id: int)` | leitura |
| Tool | `filtrar_chamados(prioridade: "alta" \| "media" \| "baixa")` | leitura |
| Tool | `fechar_chamado(id: int)` | **escrita** (registrada só com `SUPORTE_PERMITIR_ESCRITA=1`) |
| Prompt | `analisar_chamado(id)` | modelo de instrução |

## Estrutura

```
mcp_suporte/
├── servidor.py              # servidor MCP (stdio)
├── cliente.py               # cliente de verificação do protocolo (sem LLM, só leitura)
├── cliente_operacao.py      # cliente que pede confirmação antes de fechar um chamado
├── testes.py                # casos da Etapa 6 executados pelo cliente MCP
├── dados/
│   ├── chamados.json        # dados fictícios usados pelo servidor (único arquivo acessado)
│   └── chamados.inicial.json  # estado inicial, usado para restaurar os dados
├── evidencias/              # saídas geradas (tabela de testes, saída do cliente)
├── logs/auditoria.log       # criado em tempo de execução (uma linha JSON por operação)
├── config_host/             # exemplo de configuração de host MCP
└── requirements-lock.txt
```

## Instalação

Requer Python 3.11 ou superior.

```powershell
# Windows PowerShell
cd mcp_suporte
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
```

```bash
# Linux ou macOS
cd mcp_suporte
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
```

Ambiente usado no desenvolvimento: Python 3.12.10, `mcp` 1.30.0, Windows 10.

## Execução

Todos os comandos com o ambiente virtual ativo, dentro de `mcp_suporte`. Os clientes iniciam o servidor sozinhos, então **não** é preciso rodar `servidor.py` antes. Rodado sozinho, o servidor fica parado esperando mensagens de um cliente no stdin. Isso é normal no stdio.

```powershell
python cliente.py                  # descoberta, resource, prompt e chamadas de leitura
python cliente_operacao.py 101     # mostra o chamado e pede confirmação [s/N] antes de fechar
python testes.py                   # roda todos os casos da Etapa 6 e grava evidencias/resultado_testes.md
```

Para voltar os dados ao estado inicial (os testes fecham o chamado 101):

```powershell
Copy-Item dados\chamados.inicial.json dados\chamados.json      # Windows
cp dados/chamados.inicial.json dados/chamados.json              # Linux/macOS
```

`testes.py` faz essa restauração automaticamente no início.

## Configuração do host de IA

O host precisa de dois caminhos **absolutos**: o Python do `.venv` e o `servidor.py`. O local e o formato do arquivo de configuração dependem do host. Consulte a documentação dele.

**Hosts que usam `mcpServers`** (ex.: Claude Desktop, em `%APPDATA%\Claude\claude_desktop_config.json`). Há um exemplo pronto em `config_host/mcpServers.exemplo.json`:

```json
{
  "mcpServers": {
    "suporte-ads": {
      "command": "C:\\CAMINHO\\mcp_suporte\\.venv\\Scripts\\python.exe",
      "args": ["C:\\CAMINHO\\mcp_suporte\\servidor.py"]
    }
  }
}
```

No Linux/macOS o `command` é `/CAMINHO/mcp_suporte/.venv/bin/python`.

**Claude Code (CLI):**

```powershell
claude mcp add suporte-ads -- "C:\CAMINHO\mcp_suporte\.venv\Scripts\python.exe" "C:\CAMINHO\mcp_suporte\servidor.py"
```

**VS Code** (`.vscode/mcp.json`, usa a chave `servers`):

```json
{
  "servers": {
    "suporte-ads": {
      "type": "stdio",
      "command": "C:\\CAMINHO\\mcp_suporte\\.venv\\Scripts\\python.exe",
      "args": ["C:\\CAMINHO\\mcp_suporte\\servidor.py"]
    }
  }
}
```

### Ferramenta de escrita no host

Com a configuração acima, o host vê **apenas as ferramentas de leitura**: `fechar_chamado` só é registrada quando o processo do servidor recebe `SUPORTE_PERMITIR_ESCRITA=1`, o que o `cliente_operacao.py` faz após a confirmação no terminal. Esta é a configuração recomendada.

Se o professor pedir a escrita no host, adicione `"env": {"SUPORTE_PERMITIR_ESCRITA": "1"}` ao servidor e mantenha a **aprovação manual** da ferramenta. Nunca use "permitir sempre". No Claude Code isso pode ser forçado em `.claude/settings.json`:

```json
{ "permissions": { "ask": ["mcp__suporte-ads__fechar_chamado"] } }
```

## Roteiro de demonstração com IA (Etapa 4)

1. "Consulte o chamado 101 e informe título e prioridade. Use a ferramenta disponível."
2. "Consulte o chamado 999. Caso não exista, informe isso sem criar dados."
3. "Liste os chamados e indique quais possuem prioridade alta."
4. No registro de tool calls do host, capture nome da ferramenta, argumentos, resultado e resposta da IA, e compare com o retorno. Use também `logs/auditoria.log`: cada chamada efetivamente executada aparece lá com timestamp e PID. Uma resposta sem linha correspondente no log **não** veio da ferramenta.

## Segurança e limitações

- O servidor só lê e escreve `dados/chamados.json`, com caminho fixo calculado a partir de `__file__`. Nenhuma ferramenta recebe caminho, comando de shell ou SQL.
- Entradas são validadas em duas camadas. O SDK confere o tipo com `strict=True`, então texto como `"101"` é rejeitado. O próprio servidor confere os valores: ID positivo, prioridade na lista e existência do chamado.
- Auditoria: `logs/auditoria.log` e stderr, uma linha JSON por operação (timestamp, pid, operação, id ou prioridade, resultado), sem credenciais. Erros de **tipo** são barrados pelo SDK antes de a função rodar e por isso não aparecem no log de auditoria.
- `fechar_chamado` é idempotente: em chamado já fechado retorna `alterado: false` e não grava nada.
- **Limitação:** a confirmação é um controle do fluxo do cliente, **não é autenticação no servidor**. Quem iniciar o servidor com `SUPORTE_PERMITIR_ESCRITA=1` consegue fechar chamados sem confirmar. Também não há controle de concorrência entre dois processos servidores gravando ao mesmo tempo.
