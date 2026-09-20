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

Al cambiarlos aquí hay que copiarlos allí (y al revés, si se editan en caliente):

```bash
cp config/openclaw/*.md ~/.openclaw/workspace/
```

## Levantarlo en otro ordenador

**Nada de esto viaja por git.** Ni los secretos, ni `~/.openclaw/`, ni
`workspace/` (proyectos generados), ni el entorno de Python. Lo que sigue es lo
mínimo para que el canal vuelva a funcionar.

1. **Intelliprint**: clonar el repositorio, crear el entorno e instalarlo, y
   tener FreeCAD con `freecadcmd` en el PATH.
2. **Secretos**: copiar `.env.example` a `.env` y pegar a mano la clave de
   DeepSeek. Se llevan **por un canal seguro, nunca por el repositorio**: están
   en `.gitignore` por eso mismo.
3. **OpenClaw**: instalarlo, dar de alta al agente Crafty y copiarle los dos
   `.md` de esta carpeta a su workspace.
4. **Registrar el MCP** en `~/.openclaw/openclaw.json`. Las rutas son absolutas,
   así que hay que **adaptarlas** al sitio donde quedó el repositorio:

```json
{
  "mcp": {
    "servers": {
      "intelliprint": {
        "command": "<repo>/.venv/bin/intelliprint-mcp",
        "cwd": "<repo>",
        "connectionTimeoutMs": 120000,
        "requestTimeoutMs": 120000
      }
    }
  }
}
```

Los dos minutos de espera no sobran: el servidor arranca FreeCAD y el primer
modelo que responde es el razonador, que piensa varios minutos antes de hablar.

5. **Telegram**: el token del bot va en `channels.telegram.botToken`, y el dueño
   del canal en `commands.ownerAllowFrom`.

### Un bot, un ordenador

Telegram entrega cada mensaje **una sola vez**. Dos OpenClaw con el mismo token
se pelean por los mensajes y el canal se vuelve errático: unos llegan a uno y
otros al otro.

Antes de levantarlo en la máquina nueva, **para el de la vieja**. En macOS es un
LaunchAgent (`ai.openclaw.gateway`):

```bash
launchctl bootout gui/$(id -u)/ai.openclaw.gateway
```

Si se quiere tener las dos máquinas a la vez, hace falta **un bot distinto** en
cada una (otro token de @BotFather).

### Los proyectos no se mudan

`workspace/` no está versionado (§ `.gitignore`): los diseños hechos —sus GIF,
sus ensambles y sus costes— se quedan en el ordenador donde se hicieron. Si hay
alguno que interese conservar, hay que copiarlo a mano. Un trabajo en marcha
tampoco se traslada: muere con esa máquina y hay que relanzarlo.
