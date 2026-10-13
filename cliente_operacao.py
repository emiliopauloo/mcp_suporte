"""Cliente de operacao: fecha um chamado somente apos confirmacao no terminal.

Fluxo:
  1. valida o ID localmente;
  2. inicia o servidor com a escrita habilitada (SUPORTE_PERMITIR_ESCRITA=1);
  3. consulta o chamado (leitura) e mostra o que sera alterado;
  4. pergunta "s/N". Qualquer resposta diferente de s/sim cancela, e
     fechar_chamado NAO e chamado.

Limitacao: a confirmacao e um controle do fluxo deste cliente, nao uma
autenticacao no servidor. Quem iniciar o servidor com a variavel de ambiente
consegue chamar fechar_chamado sem passar por esta pergunta.

Uso:  python cliente_operacao.py 101
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def ler_id(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.exit("Uso: python cliente_operacao.py <id_do_chamado>")
    try:
        id = int(argv[1])
    except ValueError:
        sys.exit(f"ID invalido: {argv[1]!r}. Informe um inteiro positivo.")
    if id <= 0:
        sys.exit(f"ID invalido: {id}. Informe um inteiro positivo.")
    return id


def confirmar(pergunta: str) -> bool:
    try:
        resposta = input(pergunta)
    except EOFError:  # sem terminal/entrada: trata como "nao"
        resposta = ""
    return resposta.strip().lower() in ("s", "sim")


async def main() -> int:
    id = ler_id(sys.argv)
    servidor = Path(__file__).with_name("servidor.py")
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(servidor)],
        env={"SUPORTE_PERMITIR_ESCRITA": "1"},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            consulta = await session.call_tool("consultar_chamado", arguments={"id": id})
            if consulta.isError:
                print("Nao foi possivel consultar:", consulta.content[0].text)
                return 1
            chamado = consulta.structuredContent
            print("Chamado encontrado:", json.dumps(chamado, ensure_ascii=False))

            if not confirmar(f"Confirma o FECHAMENTO do chamado {id} ({chamado['titulo']})? [s/N] "):
                print("Operacao cancelada. Nenhuma chamada de escrita foi feita.")
                return 0

            resultado = await session.call_tool("fechar_chamado", arguments={"id": id})
            if resultado.isError:
                print("Erro ao fechar:", resultado.content[0].text)
                return 1
            print("Resultado:", json.dumps(resultado.structuredContent, ensure_ascii=False))
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
