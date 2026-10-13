"""Cliente de verificacao do protocolo (Etapa 3).

NAO contem LLM: cada chamada abaixo foi decidida pelo programador. Serve para
provar inicializacao, descoberta de capacidades, leitura e chamadas via stdio.
Usa somente ferramentas de leitura; a escrita fica no cliente_operacao.py.

Uso:  python cliente.py
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def titulo(texto: str) -> None:
    print(f"\n=== {texto} ===")


def mostrar(result) -> None:
    print("isError:", result.isError)
    for item in result.content:
        print(getattr(item, "text", item))


async def main():
    servidor = Path(__file__).with_name("servidor.py")
    params = StdioServerParameters(command=sys.executable, args=[str(servidor)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            titulo("initialize")
            print("Servidor:", init.serverInfo.name, init.serverInfo.version)
            print("Protocolo:", init.protocolVersion)

            titulo("tools/list")
            tools = await session.list_tools()
            print("Ferramentas:", [t.name for t in tools.tools])
            for t in tools.tools:
                somente_leitura = t.annotations.readOnlyHint if t.annotations else None
                print(f"- {t.name} (readOnly={somente_leitura}): {t.description.splitlines()[0]}")
                print(f"  inputSchema: {t.inputSchema}")

            titulo("resources/list")
            for r in (await session.list_resources()).resources:
                print(f"- {r.uri} ({r.mimeType}): {r.description}")

            titulo("prompts/list")
            for p in (await session.list_prompts()).prompts:
                print(f"- {p.name} args={[a.name for a in p.arguments or []]}: {p.description}")

            titulo("resources/read suporte://politica")
            leitura = await session.read_resource("suporte://politica")
            print(leitura.contents[0].text)

            titulo("prompts/get analisar_chamado id=101")
            prompt = await session.get_prompt("analisar_chamado", arguments={"id": "101"})
            print(prompt.messages[0].content.text)

            titulo("tools/call consultar_chamado id=101")
            result = await session.call_tool("consultar_chamado", arguments={"id": 101})
            print(result.model_dump_json(indent=2))

            titulo("tools/call consultar_chamado id=999 (erro esperado)")
            erro = await session.call_tool("consultar_chamado", arguments={"id": 999})
            mostrar(erro)

            titulo("tools/call filtrar_chamados prioridade=alta")
            filtro = await session.call_tool("filtrar_chamados", arguments={"prioridade": "alta"})
            mostrar(filtro)

            titulo("tools/call filtrar_chamados prioridade=urgente (erro esperado)")
            filtro_invalido = await session.call_tool("filtrar_chamados", arguments={"prioridade": "urgente"})
            mostrar(filtro_invalido)

            assert not result.isError
            assert result.structuredContent["titulo"] == "Falha no login"
            assert result.structuredContent["prioridade"] == "alta"
            assert erro.isError
            assert not filtro.isError
            assert filtro_invalido.isError
            print("\nVerificacao concluida: todas as assercoes passaram.")


if __name__ == "__main__":
    asyncio.run(main())
