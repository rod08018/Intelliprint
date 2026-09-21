"""La configuración de Crafty (OpenClaw) generada desde el .env
(F0.2 (docker)).

En el Mac, Crafty se configuró a mano en ~/.openclaw/openclaw.json, con
rutas absolutas, y eso no viaja por git: mudarlo de máquina era rehacerlo
de memoria. Aquí la configuración es una función del entorno, con tests,
y el contenedor la aplica cada vez que arranca.

TELEGRAM_ALLOWED_USERS es la ÚNICA fuente de quién puede escribir
(F5.10 (lista)), para el bot propio y para Crafty. Es opcional: vacía, el
canal está abierto (decisión del usuario, 2026-09-21).

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
    lista = leer_lista_blanca(env.get("TELEGRAM_ALLOWED_USERS"))
    if lista:
        permitidos = sorted(str(i) for i in lista)
        acceso = [
            {"path": "channels.telegram.dmPolicy", "value": "allowlist"},
            {"path": "channels.telegram.allowFrom", "value": permitidos},
            {"path": "commands.ownerAllowFrom", "value": [f"telegram:{i}" for i in permitidos]},
        ]
    else:
        # Canal abierto por decisión del usuario (ADR-012). OpenClaw exige
        # decirlo explícitamente: `open` solo vale con `allowFrom: ["*"]`.
        acceso = [
            {"path": "channels.telegram.dmPolicy", "value": "open"},
            {"path": "channels.telegram.allowFrom", "value": ["*"]},
        ]
    return [
        {"path": "gateway.mode", "value": "local"},
        *acceso,
        # Un bot de un dueño: meterlo en un grupo no debe abrirlo a los
        # demás miembros.
        {"path": "channels.telegram.groupPolicy", "value": "disabled"},
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
