"""Servidor MCP "Suporte ADS" (transporte stdio).

Capacidades expostas:
  Resource  suporte://politica       regras de uso dos dados
  Tools     listar_chamados          leitura
            consultar_chamado        leitura
            filtrar_chamados         leitura
            fechar_chamado           ESCRITA (so registrada com SUPORTE_PERMITIR_ESCRITA=1)
  Prompt    analisar_chamado

Menor privilegio: o servidor so le e escreve dados/chamados.json, com caminho
fixo calculado a partir de __file__. Nenhuma ferramenta recebe caminho, comando
de shell ou SQL. Por padrao o servidor sobe somente com ferramentas de leitura.

Nunca use print aqui: stdout e o canal do protocolo JSON-RPC. Logs vao para
stderr e para logs/auditoria.log.
"""

import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field
from typing_extensions import TypedDict  # pydantic exige esta versao no Python < 3.12

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_DADOS = BASE_DIR / "dados" / "chamados.json"
ARQUIVO_LOG = BASE_DIR / "logs" / "auditoria.log"

PRIORIDADES = ("alta", "media", "baixa")


# Tipos de retorno: viram o outputSchema de cada ferramenta e o SDK valida o
# structuredContent contra eles antes de responder.
class Chamado(TypedDict):
    id: int
    titulo: str
    prioridade: Literal["alta", "media", "baixa"]
    status: Literal["aberto", "fechado"]


class ListaChamados(TypedDict):
    total: int
    chamados: list[Chamado]


class ResultadoFiltro(TypedDict):
    prioridade: str
    total: int
    chamados: list[Chamado]


class ResultadoFechamento(TypedDict):
    chamado: Chamado
    alterado: bool
    mensagem: str

# A ferramenta de escrita so e registrada quando quem inicia o processo pede
# explicitamente (o cliente de operacao faz isso). O host de IA, configurado
# sem essa variavel, enxerga apenas as ferramentas de leitura.
PERMITIR_ESCRITA = os.environ.get("SUPORTE_PERMITIR_ESCRITA") == "1"


# --------------------------------------------------------------------------
# Auditoria: uma linha JSON por operacao (timestamp, operacao, id, resultado)
# --------------------------------------------------------------------------
ARQUIVO_LOG.parent.mkdir(exist_ok=True)
auditoria = logging.getLogger("suporte.auditoria")
auditoria.setLevel(logging.INFO)
auditoria.propagate = False

_handler_arquivo = logging.FileHandler(ARQUIVO_LOG, encoding="utf-8")
_handler_arquivo.setFormatter(logging.Formatter("%(message)s"))
_handler_stderr = logging.StreamHandler(sys.stderr)
_handler_stderr.setFormatter(logging.Formatter("[auditoria] %(message)s"))
auditoria.addHandler(_handler_arquivo)
auditoria.addHandler(_handler_stderr)


def registrar(operacao: str, resultado: str, **dados: Any) -> None:
    evento = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "operacao": operacao,
        **dados,
        "resultado": resultado,
    }
    auditoria.info(json.dumps(evento, ensure_ascii=False))


# --------------------------------------------------------------------------
# Persistencia restrita a dados/chamados.json
# --------------------------------------------------------------------------
def carregar() -> dict[int, Chamado]:
    """Le o arquivo a cada chamada, para enxergar alteracoes ja persistidas."""
    with ARQUIVO_DADOS.open(encoding="utf-8") as f:
        conteudo = json.load(f)
    return {c["id"]: c for c in conteudo["chamados"]}


def salvar(chamados: dict[int, Chamado]) -> None:
    """Grava em arquivo temporario e troca de uma vez (os.replace), para que
    uma falha no meio da escrita nao deixe o JSON corrompido."""
    conteudo = {"chamados": [chamados[i] for i in sorted(chamados)]}
    fd, temporario = tempfile.mkstemp(dir=ARQUIVO_DADOS.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(conteudo, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temporario, ARQUIVO_DADOS)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------
# Validacao de entrada
# --------------------------------------------------------------------------
# strict=True: o SDK rejeita texto ("101", "abc"), float e bool antes de a
# funcao rodar. Os limites de valor sao conferidos abaixo, no proprio servidor.
IdChamado = Annotated[
    int,
    Field(strict=True, description="Identificador do chamado (inteiro positivo), ex.: 101"),
]


def validar_id(operacao: str, id: int) -> None:
    if id <= 0:
        registrar(operacao, "rejeitado: id nao positivo", id=id)
        raise ValueError("O identificador deve ser um inteiro positivo")


def buscar(operacao: str, id: int) -> tuple[dict[int, Chamado], Chamado]:
    validar_id(operacao, id)
    chamados = carregar()
    if id not in chamados:
        registrar(operacao, "erro: chamado nao encontrado", id=id)
        raise ValueError(f"Chamado {id} nao encontrado")
    return chamados, chamados[id]


# --------------------------------------------------------------------------
# Servidor e primitivas MCP
# --------------------------------------------------------------------------
mcp = FastMCP(
    "Suporte ADS",
    instructions=(
        "Servidor de chamados ficticios. Responda sobre chamados somente com "
        "base no retorno das ferramentas e nunca invente IDs ou prioridades."
    ),
    log_level="WARNING",
)

LEITURA = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


@mcp.resource(
    "suporte://politica",
    name="politica",
    description="Regras de uso dos dados de suporte que a IA deve seguir.",
    mime_type="text/plain",
)
def politica() -> str:
    return (
        "Politica do assistente de suporte (dados ficticios):\n"
        "1. Responda sobre chamados somente com base no retorno das ferramentas.\n"
        "2. Nao invente chamados, IDs, titulos, prioridades ou status.\n"
        "3. Se a ferramenta retornar erro, informe o erro; nao crie dados.\n"
        "4. fechar_chamado altera dados e exige confirmacao humana antes da chamada.\n"
        "5. Prioridades validas: alta, media, baixa. Status validos: aberto, fechado."
    )


@mcp.tool(title="Listar chamados", annotations=LEITURA)
def listar_chamados() -> ListaChamados:
    """Lista todos os chamados ficticios com id, titulo, prioridade e status."""
    chamados = list(carregar().values())
    registrar("listar_chamados", "ok", total=len(chamados))
    return {"total": len(chamados), "chamados": chamados}


@mcp.tool(title="Consultar chamado", annotations=LEITURA)
def consultar_chamado(id: IdChamado) -> Chamado:
    """Consulta um chamado pelo identificador inteiro positivo.
    Retorna erro se o chamado nao existir; nunca cria registros."""
    _, chamado = buscar("consultar_chamado", id)
    registrar("consultar_chamado", "ok", id=id)
    return chamado


@mcp.tool(title="Filtrar chamados por prioridade", annotations=LEITURA)
def filtrar_chamados(
    prioridade: Annotated[
        str,
        # O enum no schema orienta o host/LLM; a validacao real e feita abaixo,
        # porque o schema anunciado nao garante o que o cliente vai enviar.
        Field(description="alta, media ou baixa", json_schema_extra={"enum": list(PRIORIDADES)}),
    ],
) -> ResultadoFiltro:
    """Lista os chamados de uma prioridade (alta, media ou baixa).
    Prioridade valida sem chamados retorna lista vazia; qualquer outro valor e rejeitado."""
    if prioridade not in PRIORIDADES:
        registrar("filtrar_chamados", "rejeitado: prioridade invalida", prioridade=prioridade)
        raise ValueError(f"Prioridade invalida: {prioridade!r}. Use alta, media ou baixa.")
    encontrados = [c for c in carregar().values() if c["prioridade"] == prioridade]
    registrar("filtrar_chamados", "ok", prioridade=prioridade, total=len(encontrados))
    return {"prioridade": prioridade, "total": len(encontrados), "chamados": encontrados}


def fechar_chamado(id: IdChamado) -> ResultadoFechamento:
    """ESCRITA: altera o status do chamado para fechado e grava em disco.
    So chame apos confirmacao explicita do usuario. Chamado ja fechado nao e
    alterado (operacao idempotente: retorna alterado=false)."""
    chamados, chamado = buscar("fechar_chamado", id)
    if chamado["status"] == "fechado":
        registrar("fechar_chamado", "sem alteracao: ja estava fechado", id=id)
        return {"chamado": chamado, "alterado": False,
                "mensagem": "Chamado ja estava fechado; nada foi alterado."}
    chamado["status"] = "fechado"
    salvar(chamados)
    registrar("fechar_chamado", "ok: status alterado para fechado", id=id)
    return {"chamado": chamado, "alterado": True, "mensagem": "Chamado fechado."}


if PERMITIR_ESCRITA:
    mcp.add_tool(
        fechar_chamado,
        title="Fechar chamado",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
        ),
    )


@mcp.prompt(description="Pede a IA que consulte o chamado pela ferramenta e explique a prioridade.")
def analisar_chamado(id: str) -> str:
    return (
        f"Consulte o chamado {id} usando a ferramenta consultar_chamado e explique "
        "a prioridade com base apenas no retorno da ferramenta. Se a ferramenta "
        "retornar erro ou o chamado nao existir, informe a ausencia sem criar dados."
    )


if __name__ == "__main__":
    if not ARQUIVO_DADOS.exists():
        sys.exit(f"Arquivo de dados ausente: {ARQUIVO_DADOS}")
    registrar("inicializacao", "ok", escrita_habilitada=PERMITIR_ESCRITA)
    mcp.run(transport="stdio")
