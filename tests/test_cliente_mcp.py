"""El cliente con el que el orquestador llama a un MCP (F0.5 (cliente)).

El orquestador es código síncrono: `build.py` y `slicing.py` lanzan
subprocesos y esperan. El cliente tiene que caber en eso, así que expone
una llamada normal y se ocupa él del async por dentro.

Se prueba contra un servidor DE VERDAD, montado en el propio proceso: no
hay simulacro que pueda mentir sobre el protocolo.
"""

import pytest
from mcp.server import MCPServer

from orchestrator.mcp.client import ClienteMCP, LlamadaFallida, PuenteInalcanzable


@pytest.fixture
def servidor():
    mcp = MCPServer("de-prueba")

    @mcp.tool()
    def sumar(a: int, b: int) -> dict:
        return {"total": a + b}

    @mcp.tool()
    def romperse() -> dict:
        raise RuntimeError("se rompió por dentro")

    @mcp.tool()
    def fallar_bien() -> dict:
        return {"ok": False, "error": "no encuentro el STL"}

    return mcp


def test_una_llamada_devuelve_lo_que_dijo_la_herramienta(servidor):
    assert ClienteMCP(servidor).llamar("sumar", a=2, b=3) == {"total": 5}


def test_se_pueden_listar_las_herramientas(servidor):
    assert set(ClienteMCP(servidor).herramientas()) == {"sumar", "romperse", "fallar_bien"}


def test_una_excepcion_remota_llega_SIN_su_motivo(servidor):
    """Esto no es un capricho del cliente: MCP NO manda el texto de una
    excepción del servidor. Dice "Error executing tool romperse" y se
    guarda el porqué.

    Queda escrito como test porque determina cómo hay que escribir una
    herramienta: si quiere que el otro lado sepa qué pasó, tiene que
    DEVOLVER el motivo, no lanzarlo. Es lo que hace `laminar` del puente,
    con su `{"ok": False, "error": ...}`."""
    with pytest.raises(LlamadaFallida) as fallo:
        ClienteMCP(servidor).llamar("romperse")
    assert "romperse" in str(fallo.value)
    assert "se rompió por dentro" not in str(fallo.value)


def test_una_herramienta_que_devuelve_el_motivo_si_lo_transmite(servidor):
    """La forma correcta de fallar en una herramienta MCP."""
    assert ClienteMCP(servidor).llamar("fallar_bien") == {
        "ok": False, "error": "no encuentro el STL"
    }


def test_una_herramienta_que_no_existe_se_distingue_de_una_que_falla(servidor):
    with pytest.raises(LlamadaFallida, match="no_existe"):
        ClienteMCP(servidor).llamar("no_existe")


def test_si_no_hay_nadie_al_otro_lado_el_error_dice_a_donde_iba():
    """El fallo más probable en marcha es que nadie arrancó el puente. El
    error tiene que decir la dirección, o se depura a ciegas."""
    cliente = ClienteMCP("http://127.0.0.1:9/mcp", timeout=5)
    with pytest.raises(PuenteInalcanzable, match="127.0.0.1:9"):
        cliente.llamar("sumar", a=1, b=1)
