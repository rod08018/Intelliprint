"""Cliente MCP del orquestador (F0.5 (cliente)).

Lo usa para pedirle al host algo que el contenedor no puede hacer solo:
laminar con el PrusaSlicer del escritorio (ver scripts/host_bridge.py).

SÍNCRONO A PROPÓSITO. El orquestador no es una aplicación async: `build.py`
y `slicing.py` lanzan un subproceso y esperan a que termine. Un cliente
async obligaría a teñir de `async` toda la cadena que lo llama, hasta el
CLI, para una llamada que de todas formas bloquea minutos. El async se
queda aquí dentro.
"""

import json

import anyio
from mcp.client import Client


class LlamadaFallida(RuntimeError):
    """La herramienta remota existía y no funcionó, o no existía."""


class PuenteInalcanzable(RuntimeError):
    """No hay nadie escuchando al otro lado."""


# Laminar tarda; el que manda la pieza más grande paga la espera. Cortar a
# los 30 s por defecto convertiría un laminado normal en un fallo de red.
ESPERA_POR_DEFECTO = 900.0


class ClienteMCP:
    """Un MCP al que llamar con una función normal.

    `destino` es la URL del servidor ("http://host.docker.internal:8102/mcp")
    o, en los tests, el propio `MCPServer`: el cliente lo levanta en el
    mismo proceso y se prueba el protocolo de verdad, sin simulacros.
    """

    def __init__(self, destino, timeout: float = ESPERA_POR_DEFECTO):
        self._destino = destino
        self._timeout = timeout

    def _describir(self) -> str:
        return self._destino if isinstance(self._destino, str) else "el servidor en proceso"

    async def _con_sesion(self, trabajo):
        try:
            async with Client(
                self._destino, raise_exceptions=False,
                read_timeout_seconds=self._timeout,
            ) as cliente:
                return await trabajo(cliente)
        except BaseException as e:
            propia = _desenvolver(e)
            if propia is not None:
                raise propia from None
            # Sin la dirección en el mensaje, el fallo más común en marcha
            # —nadie arrancó el puente— se depura a ciegas.
            raise PuenteInalcanzable(
                f"no pude hablar con {self._describir()}: {type(e).__name__}: {e}"
            ) from e

    def herramientas(self) -> list[str]:
        async def trabajo(cliente):
            return [h.name for h in (await cliente.list_tools()).tools]

        return anyio.run(self._con_sesion, trabajo)

    def llamar(self, herramienta: str, **argumentos):
        """El resultado de la herramienta, o `LlamadaFallida` con su motivo."""

        async def trabajo(cliente):
            resultado = await cliente.call_tool(herramienta, argumentos or None)
            if resultado.is_error:
                raise LlamadaFallida(f"{herramienta}: {_texto(resultado)}")
            if resultado.structured_content is not None:
                return resultado.structured_content
            # Una herramienta anotada `-> dict` no declara esquema de salida,
            # así que MCP no rellena structured_content: manda el JSON como
            # texto. Los dos casos son normales y el que llama no tiene por
            # qué distinguirlos.
            texto = _texto(resultado)
            try:
                return json.loads(texto)
            except (ValueError, TypeError):
                return texto

        return anyio.run(self._con_sesion, trabajo)


def _desenvolver(e: BaseException) -> BaseException | None:
    """Nuestra excepción, si está dentro de la que llegó.

    El cliente corre dentro de un grupo de tareas de anyio, y un grupo
    envuelve lo que se lance dentro en un ExceptionGroup. Sin desenvolverlo,
    un `LlamadaFallida` limpio llegaría al orquestador disfrazado de
    "unhandled errors in a TaskGroup", que no dice nada.
    """
    if isinstance(e, (LlamadaFallida, PuenteInalcanzable)):
        return e
    for hijo in getattr(e, "exceptions", ()) or ():
        encontrada = _desenvolver(hijo)
        if encontrada is not None:
            return encontrada
    return None


def _texto(resultado) -> str:
    """Lo que el otro lado dijo, sea un error o una respuesta sin esquema."""
    partes = [
        getattr(c, "text", "") for c in getattr(resultado, "content", []) or []
    ]
    return "\n".join(p for p in partes if p).strip()
