# El canal humano: Crafty sobre OpenClaw

Crafty es el agente de OpenClaw que habla por Telegram: **él conversa, entiende
el encargo y lanza el trabajo**; Intelliprint diseña. Los dos se comunican por
un servidor MCP, no por línea de órdenes.

Aquí viven las instrucciones de Crafty **versionadas**, porque OpenClaw las lee
desde su propia carpeta (`~/.openclaw/workspace/`), fuera del repositorio: si
esa máquina se pierde o se cambia de ordenador, se pierden con ella.

| Archivo | Qué es | Dónde lo lee OpenClaw |
|---|---|---|
| `INTELLIPRINT.md` | Cómo atiende Crafty: cuándo preguntar, cuándo lanzar, qué mandar, qué hacer si un proyecto se bloquea | `~/.openclaw/workspace/INTELLIPRINT.md` |
| `IDENTITY.md` | Quién es Crafty y en qué tono habla | `~/.openclaw/workspace/IDENTITY.md` |

En Docker se copian solos en cada arranque del contenedor: se editan **aquí**,
que es donde los versiona git, y el cambio llega con `docker compose restart
crafty`. Copiarlos a mano solo hace falta en una instalación nativa:

```bash
cp config/openclaw/*.md ~/.openclaw/workspace/
```

## Levantarlo: `docker compose up -d crafty`

Crafty corre en su propio contenedor, con la imagen oficial de OpenClaw fijada a
una versión. **Ya no hay nada que configurar a mano**: su configuración sale del
`.env` (`orchestrator/crafty.py`, con tests) y se aplica en cada arranque.

```bash
docker compose up -d crafty
```

Lo que hace falta en `.env`:

| Variable | Para qué |
|---|---|
| `DEEPSEEK_API_KEY` | El modelo con el que **conversa** Crafty (Intelliprint usa el suyo) |
| `TELEGRAM_BOT_TOKEN` | El bot de @BotFather |
| `TELEGRAM_ALLOWED_USERS` | Opcional. Vacía: canal **abierto**, atiende a cualquiera (decisión del usuario). Con ids, solo a ellos (F5.10 (lista)) |
| `OPENCLAW_GATEWAY_TOKEN` | Protege el gateway de OpenClaw; cualquier cadena larga y aleatoria |

Ningún secreto se guarda en `openclaw.json`: la clave y los tokens quedan como
**referencias** a variables de entorno. Ese archivo vive en un volumen, y un
volumen se copia, se inspecciona y acaba subido a donde no debe.

### Las tres piezas

```
  crafty-config   genera la configuración desde el .env  (un solo paso, y termina)
        │
  crafty          OpenClaw + Telegram  ──MCP por HTTP──►  intelliprint-mcp
                                                          (FreeCAD, los agentes)
```

En el Mac, Crafty lanzaba `intelliprint-mcp` como subproceso por stdio. En
contenedores no puede: el binario, FreeCAD y el modelo viven en **otra imagen**.
Así que Intelliprint sirve su MCP por HTTP en la red interna del compose y Crafty
lo llama por URL. No se publica ningún puerto al host: ese servidor lanza
proyectos que gastan dinero.

Los archivos que Crafty te manda (el GIF, el ensamble) pasan por un **buzón**: un
volumen montado en los dos contenedores **en la misma ruta**, así que las rutas
que devuelve el MCP valen tal cual al otro lado.

Los dos `.md` de esta carpeta se copian al workspace de Crafty en **cada
arranque**: se editan aquí, que es donde los versiona git, y un cambio llega con
reiniciar el contenedor.

### Quién puede hablarle

El canal va **abierto** por decisión del usuario: sin lista, `dmPolicy: open`
con `allowFrom: ["*"]`. Si se ponen ids en `TELEGRAM_ALLOWED_USERS`, esa misma
lista cierra el bot propio y a Crafty: sale `dmPolicy: allowlist` con los ids,
`groupPolicy: disabled` —meterlo en un grupo no lo abre a los demás miembros— y
`commands.ownerAllowFrom`. Tu id numérico te lo dice @userinfobot.

### Un bot, un ordenador

Telegram entrega cada mensaje **una sola vez**. Dos OpenClaw con el mismo token
se pelean por los mensajes y el canal se vuelve errático: unos llegan a uno y
otros al otro.

Antes de levantarlo aquí, **para el de la máquina vieja**. En macOS era un
LaunchAgent (`ai.openclaw.gateway`):

```bash
launchctl bootout gui/$(id -u)/ai.openclaw.gateway
```

Y el de aquí se para con `docker compose stop crafty`.

Si se quiere tener las dos máquinas a la vez, hace falta **un bot distinto** en
cada una (otro token de @BotFather).

### Los proyectos no se mudan

`workspace/` no está versionado (§ `.gitignore`): los diseños hechos —sus GIF,
sus ensambles y sus costes— se quedan en el ordenador donde se hicieron. Si hay
alguno que interese conservar, hay que copiarlo a mano. Un trabajo en marcha
tampoco se traslada: muere con esa máquina y hay que relanzarlo.
