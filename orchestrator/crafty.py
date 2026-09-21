"""La configuración de Crafty (OpenClaw) generada desde el .env
(F0.2 (docker)).

En el Mac, Crafty se configuró a mano en ~/.openclaw/openclaw.json, con
rutas absolutas, y eso no viaja por git: mudarlo de máquina era rehacerlo
de memoria. Aquí la configuración es una función del entorno, con tests,
y el contenedor la aplica cada vez que arranca.

TELEGRAM_ALLOWED_USERS es la ÚNICA fuente de quién puede escribir
(F5.10 (lista)): la misma lista cierra el bot propio de Intelliprint y a
Crafty. Dos listas acabarían diciendo cosas distintas.

    python -m orchestrator.crafty > lote.json
    openclaw config set --batch-json "$(cat lote.json)"
"""

import json
import os
import sys

from orchestrator.human.adapters.telegram import leer_lista_blanca

URL_INTELLIPRINT = "http://intelliprint-mcp:8200/mcp"
"""El servicio del compose. Dentro de la red de Docker se llama por su
nombre; no se publica al host."""

ESPERA_MS = 180_000
"""Lo que puede tardar una llamada. config/openclaw/README.md ya pedía dos
minutos: el servidor arranca FreeCAD y el primer modelo que contesta es el
razonador, que piensa varios minutos antes de hablar."""


def lote_de_configuracion(env) -> list[dict]:
    """Los cambios para `openclaw config set --batch-json`.

    Sin secretos: el token del bot y la clave de DeepSeek se quedan en el
    entorno. openclaw.json vive en un volumen, y un volumen se copia, se
    inspecciona y acaba subido a donde no debe.
    """
    permitidos = sorted(str(i) for i in leer_lista_blanca(env.get("TELEGRAM_ALLOWED_USERS")))
    return [
        {"path": "gateway.mode", "value": "local"},
        # Solo la lista, y por id numérico (los @alias se cambian y se
        # heredan). `pairing` —el valor por defecto— deja que cualquiera
        # pida acceso; aquí no se pide, se tiene o no.
        {"path": "channels.telegram.dmPolicy", "value": "allowlist"},
        {"path": "channels.telegram.allowFrom", "value": permitidos},
        # Un bot de un dueño: meterlo en un grupo no debe abrirlo a los
        # demás miembros.
        {"path": "channels.telegram.groupPolicy", "value": "disabled"},
        {"path": "commands.ownerAllowFrom", "value": [f"telegram:{i}" for i in permitidos]},
        {"path": "mcp.servers.intelliprint", "value": {
            "url": URL_INTELLIPRINT,
            # Sin esto OpenClaw habla SSE, y MCPServer sirve streamable-http.
            "transport": "streamable-http",
            "connectionTimeoutMs": ESPERA_MS,
            "requestTimeoutMs": ESPERA_MS,
        }},
    ]


def main() -> None:
    try:
        lote = lote_de_configuracion(os.environ)
    except ValueError as e:
        sys.exit(f"Crafty no se configura: {e}")
    print(json.dumps(lote, ensure_ascii=False))


if __name__ == "__main__":
    main()
