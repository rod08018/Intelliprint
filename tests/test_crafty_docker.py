"""Crafty en Docker: OpenClaw en su contenedor, Intelliprint en el suyo
(F0.2 (docker)).

En el Mac, Crafty lanzaba `intelliprint-mcp` como subproceso por stdio.
En contenedores eso no puede ser: el binario, FreeCAD y el modelo viven en
la imagen del orquestador, no en la de OpenClaw. Así que el MCP de
Intelliprint se sirve por HTTP dentro de la red del compose y Crafty lo
llama por URL.

Y la configuración de Crafty deja de hacerse a mano: sale del .env, con
TELEGRAM_ALLOWED_USERS como ÚNICA fuente de quién puede escribir
(F5.10 (lista)).
"""

import pytest

from orchestrator.crafty import lote_de_configuracion
from orchestrator.mcp_server import opciones_de_arranque

ENV = {"TELEGRAM_ALLOWED_USERS": "111,222"}


def _valor(lote, ruta):
    return next(c["value"] for c in lote if c["path"] == ruta)


# --- El MCP de Intelliprint por HTTP -----------------------------------------


def test_por_defecto_el_mcp_sigue_siendo_stdio():
    """Uso nativo: OpenClaw lo lanza como subproceso, como en el Mac."""
    assert opciones_de_arranque({})[0] == "stdio"


def test_en_el_compose_se_sirve_por_http_a_la_red_interna():
    transporte, opciones = opciones_de_arranque(
        {"INTELLIPRINT_MCP_TRANSPORT": "streamable-http", "INTELLIPRINT_MCP_PORT": "8200"})
    assert transporte == "streamable-http"
    assert opciones["host"] == "0.0.0.0" and opciones["port"] == 8200


def test_el_nombre_del_servicio_es_un_host_legitimo():
    """El servidor MCP rechaza cabeceras Host que no conoce (defensa contra
    rebinding de DNS). Crafty llega como `intelliprint-mcp:8200`: si ese
    nombre no está en la lista, todas las llamadas dan 421."""
    _, opciones = opciones_de_arranque(
        {"INTELLIPRINT_MCP_TRANSPORT": "streamable-http", "INTELLIPRINT_MCP_PORT": "8200"})
    assert "intelliprint-mcp:8200" in opciones["transport_security"].allowed_hosts


# --- El buzón compartido ------------------------------------------------------


def test_el_buzon_se_puede_mover_con_una_variable(tmp_path, monkeypatch):
    """El MCP devuelve RUTAS y Crafty las abre en su contenedor. Montando el
    mismo volumen en la misma ruta a los dos lados, la ruta vale en ambos."""
    from orchestrator.jobs import entregar

    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    (proyecto / "request.md").write_text("x", encoding="utf-8")
    buzon = tmp_path / "buzon"
    monkeypatch.setenv("INTELLIPRINT_BUZON", str(buzon))

    entregados = entregar(proyecto)
    assert entregados["peticion"] == str(buzon / "proyecto" / "request.md")


# --- La configuración de Crafty -----------------------------------------------


def test_solo_los_de_la_lista_pueden_escribir_a_crafty():
    lote = lote_de_configuracion(ENV)
    assert _valor(lote, "channels.telegram.dmPolicy") == "allowlist"
    assert sorted(_valor(lote, "channels.telegram.allowFrom")) == ["111", "222"]


def test_los_grupos_estan_cerrados():
    """Crafty es un bot de un dueño. Meterlo en un grupo no debe abrirlo a
    los demás miembros."""
    assert _valor(lote_de_configuracion(ENV), "channels.telegram.groupPolicy") == "disabled"


def test_los_de_la_lista_son_los_duenos_de_los_comandos():
    assert sorted(_valor(lote_de_configuracion(ENV), "commands.ownerAllowFrom")) == [
        "telegram:111", "telegram:222"]


def test_sin_lista_crafty_atiende_a_cualquiera():
    """Decisión del usuario: canal abierto. En OpenClaw, «open» exige
    `allowFrom: ["*"]` de forma explícita."""
    lote = lote_de_configuracion({})
    assert _valor(lote, "channels.telegram.dmPolicy") == "open"
    assert _valor(lote, "channels.telegram.allowFrom") == ["*"]
    assert not [c for c in lote if c["path"] == "commands.ownerAllowFrom"]


def test_crafty_llama_a_intelliprint_por_la_red_del_compose():
    servidor = _valor(lote_de_configuracion(ENV), "mcp.servers.intelliprint")
    assert servidor["url"] == "http://intelliprint-mcp:8200/mcp"
    # Sin esto OpenClaw usa SSE, que no es lo que sirve MCPServer.
    assert servidor["transport"] == "streamable-http"


def test_la_espera_cubre_el_arranque_de_freecad_y_el_razonador():
    """Lo decía config/openclaw/README.md: el primer modelo que responde es
    el razonador, que piensa minutos antes de hablar."""
    servidor = _valor(lote_de_configuracion(ENV), "mcp.servers.intelliprint")
    assert servidor["requestTimeoutMs"] >= 120_000


def test_ningun_secreto_acaba_en_la_configuracion():
    """El token y la clave se quedan en el entorno; openclaw.json vive en un
    volumen y se copia, se inspecciona y se sube a donde no debe."""
    env = {**ENV, "TELEGRAM_BOT_TOKEN": "123:SECRETO", "DEEPSEEK_API_KEY": "sk-SECRETO"}
    assert "SECRETO" not in repr(lote_de_configuracion(env))


def test_crafty_conversa_con_flash_por_defecto():
    """OpenClaw pone deepseek-v4-pro con pensamiento alto: no ve imágenes
    (comprobado: a una imagen roja contestó «Desconocido») y cuesta ~3.3
    veces más en salida, solo para conversar. Decisión del usuario: Flash."""
    lote = lote_de_configuracion(ENV)
    assert _valor(lote, "agents.defaults.model.primary") == "deepseek/deepseek-flash"


def test_el_modelo_de_crafty_se_cambia_desde_el_entorno():
    lote = lote_de_configuracion({**ENV, "CRAFTY_MODEL": "deepseek/deepseek-v4-pro"})
    assert _valor(lote, "agents.defaults.model.primary") == "deepseek/deepseek-v4-pro"
