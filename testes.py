"""Executa os casos de teste da Etapa 6 pelo cliente MCP e grava a tabela de
evidencias (entrada, esperado, observado) em evidencias/resultado_testes.md.

ATENCAO: antes de comecar, restaura dados/chamados.json a partir de
dados/chamados.inicial.json, porque os testes fecham o chamado 101.

Uso:  python testes.py
"""

import asyncio
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE = Path(__file__).resolve().parent
SERVIDOR = BASE / "servidor.py"
CLIENTE_OPERACAO = BASE / "cliente_operacao.py"
DADOS = BASE / "dados" / "chamados.json"
DADOS_INICIAIS = BASE / "dados" / "chamados.inicial.json"
LOG = BASE / "logs" / "auditoria.log"
SAIDA = BASE / "evidencias" / "resultado_testes.md"

resultados: list[tuple[str, str, str, str, bool]] = []


def registrar(caso: str, entrada: str, esperado: str, observado: str, passou: bool) -> None:
    resultados.append((caso, entrada, esperado, observado, passou))
    print(f"[{'OK' if passou else 'FALHOU'}] {caso}: {observado}")


def hash_dados() -> str:
    return hashlib.sha256(DADOS.read_bytes()).hexdigest()


def chamados_no_json() -> dict[int, dict]:
    conteudo = json.loads(DADOS.read_text(encoding="utf-8"))
    return {c["id"]: c for c in conteudo["chamados"]}


def eventos_log() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(linha) for linha in LOG.read_text(encoding="utf-8").splitlines() if linha]


def texto(result) -> str:
    """Primeira linha da mensagem retornada pela ferramenta."""
    return result.content[0].text.splitlines()[0] if result.content else ""


@asynccontextmanager
async def sessao(escrita: bool = False):
    """Cada sessao inicia um processo servidor novo (como o host faria)."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVIDOR)],
        env={"SUPORTE_PERMITIR_ESCRITA": "1"} if escrita else None,
    )
    # A auditoria do servidor tambem vai para logs/auditoria.log; aqui o
    # stderr e descartado so para manter a saida dos testes legivel.
    with open(os.devnull, "w") as descarte:
        async with stdio_client(params, errlog=descarte) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def operar(id: str, resposta: str) -> subprocess.CompletedProcess:
    """Executa o cliente de operacao simulando a resposta digitada no terminal."""
    return subprocess.run(
        [sys.executable, str(CLIENTE_OPERACAO), id],
        input=resposta + "\n", capture_output=True, text=True, timeout=60,
    )


async def testes_de_leitura() -> None:
    async with sessao() as s:
        r = await s.call_tool("consultar_chamado", {"id": 101})
        c = r.structuredContent or {}
        registrar(
            "Consulta valida", "consultar_chamado id=101", "Titulo e prioridade corretos",
            f"isError={r.isError}; titulo={c.get('titulo')!r}, prioridade={c.get('prioridade')!r}",
            not r.isError and c.get("titulo") == "Falha no login" and c.get("prioridade") == "alta",
        )

        antes = hash_dados()
        r = await s.call_tool("consultar_chamado", {"id": 999})
        inalterado = hash_dados() == antes and 999 not in chamados_no_json()
        registrar(
            "Registro ausente", "consultar_chamado id=999", "Erro sem criar registro",
            f"isError={r.isError}; '{texto(r)}'; JSON inalterado={inalterado}",
            r.isError and inalterado,
        )

        for rotulo, valor in (("negativo", -5), ("zero", 0), ("texto", "abc"), ("texto numerico", "101")):
            antes = hash_dados()
            r = await s.call_tool("consultar_chamado", {"id": valor})
            inalterado = hash_dados() == antes
            registrar(
                f"Entrada invalida ({rotulo})", f"consultar_chamado id={valor!r}", "Rejeicao sem alteracao",
                f"isError={r.isError}; '{texto(r)}'; JSON inalterado={inalterado}",
                r.isError and inalterado,
            )

        r = await s.call_tool("filtrar_chamados", {"prioridade": "alta"})
        c = r.structuredContent or {}
        lista = c.get("chamados", [])
        registrar(
            "Filtro valido", "filtrar_chamados prioridade='alta'", "Apenas chamados de prioridade alta",
            f"isError={r.isError}; ids={[x['id'] for x in lista]}; prioridades={sorted({x['prioridade'] for x in lista})}",
            not r.isError and len(lista) > 0 and all(x["prioridade"] == "alta" for x in lista),
        )

        r = await s.call_tool("filtrar_chamados", {"prioridade": "media"})
        c = r.structuredContent or {}
        registrar(
            "Filtro valido sem resultado", "filtrar_chamados prioridade='media'", "Lista vazia, sem erro",
            f"isError={r.isError}; total={c.get('total')}; chamados={c.get('chamados')}",
            not r.isError and c.get("chamados") == [],
        )

        r = await s.call_tool("filtrar_chamados", {"prioridade": "urgente"})
        registrar(
            "Filtro invalido", "filtrar_chamados prioridade='urgente'", "Erro de validacao",
            f"isError={r.isError}; '{texto(r)}'", r.isError,
        )

        nomes = [t.name for t in (await s.list_tools()).tools]
        antes = hash_dados()
        r = await s.call_tool("fechar_chamado", {"id": 101})
        registrar(
            "Menor privilegio (host)", "sessao sem SUPORTE_PERMITIR_ESCRITA; fechar_chamado id=101",
            "Ferramenta de escrita nao exposta",
            f"tools={nomes}; isError={r.isError}; '{texto(r)}'",
            "fechar_chamado" not in nomes and r.isError and hash_dados() == antes,
        )

        try:
            await s.read_resource("file:///C:/Windows/win.ini")
            registrar("Arquivo arbitrario", "resources/read file:///C:/Windows/win.ini",
                      "Recurso inexistente (erro)", "conteudo retornado", False)
        except Exception as e:
            registrar("Arquivo arbitrario", "resources/read file:///C:/Windows/win.ini",
                      "Recurso inexistente (erro)", f"erro: {e}", True)


async def testes_de_escrita() -> None:
    antes, log_antes = hash_dados(), len(eventos_log())
    p = operar("101", "n")
    escritas = [e for e in eventos_log()[log_antes:] if e["operacao"] == "fechar_chamado"]
    status = chamados_no_json()[101]["status"]
    registrar(
        "Confirmacao negada", "cliente_operacao.py 101, resposta 'n'", "Nenhuma chamada de escrita",
        f"saida='{p.stdout.strip().splitlines()[-1]}'; eventos fechar_chamado no log={len(escritas)}; status={status}",
        p.returncode == 0 and not escritas and hash_dados() == antes and status == "aberto",
    )

    log_antes = len(eventos_log())
    p = operar("101", "s")
    escritas = [e for e in eventos_log()[log_antes:] if e["operacao"] == "fechar_chamado"]
    status = chamados_no_json()[101]["status"]
    registrar(
        "Confirmacao aceita", "cliente_operacao.py 101, resposta 's'", "Status fechado no JSON",
        f"status no JSON={status}; log='{escritas[-1]['resultado'] if escritas else '-'}'",
        p.returncode == 0 and status == "fechado" and len(escritas) == 1,
    )

    # Nova sessao = novo processo servidor, sem nada em memoria da sessao anterior.
    async with sessao() as s:
        r = await s.call_tool("consultar_chamado", {"id": 101})
        c = r.structuredContent or {}
    registrar(
        "Persistencia", "nova sessao (servidor reiniciado); consultar_chamado id=101",
        "Status permanece fechado", f"isError={r.isError}; status={c.get('status')!r}",
        not r.isError and c.get("status") == "fechado",
    )

    antes = hash_dados()
    p = operar("101", "s")
    linha = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    registrar(
        "Repeticao", "cliente_operacao.py 101 novamente, resposta 's'",
        "Comportamento definido: idempotente, sem nova escrita",
        f"{linha}; JSON inalterado={hash_dados() == antes}",
        p.returncode == 0 and '"alterado": false' in linha and hash_dados() == antes,
    )

    log_antes = len(eventos_log())
    p = operar("abc", "s")
    registrar(
        "ID invalido no cliente de operacao", "cliente_operacao.py abc", "Rejeitado antes de iniciar o servidor",
        f"exit={p.returncode}; '{p.stderr.strip()}'; eventos no log={len(eventos_log()) - log_antes}",
        p.returncode != 0 and len(eventos_log()) == log_antes,
    )


def gravar_evidencias() -> None:
    def celula(valor: str) -> str:
        return str(valor).replace("|", "\\|").replace("\n", " ")

    linhas = [
        "# Resultado dos testes (Etapa 6)",
        "",
        f"- Executado em: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Python {platform.python_version()} | mcp {version('mcp')} | {platform.system()} {platform.release()}",
        "- Todas as operacoes foram feitas pelo protocolo MCP (stdio); dados restaurados de chamados.inicial.json no inicio.",
        "",
        "| # | Caso | Entrada ou acao | Resultado esperado | Resultado observado | Status |",
        "|---|------|-----------------|--------------------|---------------------|--------|",
    ]
    for i, (caso, entrada, esperado, observado, passou) in enumerate(resultados, 1):
        linhas.append(
            f"| {i} | {celula(caso)} | `{celula(entrada)}` | {celula(esperado)} | "
            f"{celula(observado)} | {'OK' if passou else 'FALHOU'} |"
        )
    aprovados = sum(r[4] for r in resultados)
    linhas += ["", f"**{aprovados}/{len(resultados)} casos aprovados.**", ""]
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text("\n".join(linhas), encoding="utf-8")


async def main() -> int:
    shutil.copyfile(DADOS_INICIAIS, DADOS)
    await testes_de_leitura()
    await testes_de_escrita()
    gravar_evidencias()
    aprovados = sum(r[4] for r in resultados)
    print(f"\n{aprovados}/{len(resultados)} casos aprovados. Evidencias em {SAIDA.relative_to(BASE)}")
    return 0 if aprovados == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
