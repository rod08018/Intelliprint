# scripts

Utilidades del **host**, fuera de Docker.

| Script | Para qué |
|---|---|
| `demo.py` | Recorrido de extremo a extremo para ver el sistema funcionando. **Usa DeepSeek**: el Requirements Agent y el Part Designer son agentes de verdad, así que necesita `DEEPSEEK_API_KEY` |
| `eval_part_designer.py` | Mide al Part Designer contra peticiones de referencia |
| `eval_requirements.py` | Mide la extracción de requisitos |
| `eval_structured_output.py` | Mide cuántas veces el modelo devuelve un esquema válido a la primera |

## El puente del host

`start-host-mcps.ps1` levanta los MCP que tienen que correr **en el PC**, fuera
del contenedor. Hoy hay uno: el de PrusaSlicer (`host_bridge.py`, puerto 8102).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-host-mcps.ps1
```

**Por qué PrusaSlicer está fuera y FreeCAD dentro** (ADR-014): FreeCAD es una
herramienta interna —construye y calla—, así que va en la imagen. PrusaSlicer es
donde la persona mira **qué va a imprimir** antes de mandarlo a la máquina, y
tiene que ser el suyo, con su versión y sus ajustes.

El puente ofrece `laminar` (sin ventana, devuelve gramos y horas),
`abrir_en_prusaslicer` (abre el programa con las piezas y el perfil cargados —es
lo que hace el botón de la interfaz web) y `perfiles`.

Comprueba lo que entra **aunque el orquestador ya lo haya comprobado**: el que
ejecuta no delega eso en el que pide. Las rutas tienen que estar dentro de
`workspace/`, y el perfil se pide por NOMBRE y se resuelve en `config/slicing/`;
si se pudiera mandar la ruta, el contenedor estaría eligiendo qué archivo del PC
se lee.

> Este script **no existió durante meses**, aunque este README lo daba por hecho
> junto a un puente `mcp-proxy` y un cliente MCP en el orquestador. Lo que sí es
> cierto desde el principio, y sigue siéndolo, es que **el orquestador lanza
> `freecadcmd` como subproceso**: un MCP de FreeCAD levantado en el host no lo
> usa nadie. Lo que necesita es el binario accesible y `FREECADCMD` apuntándolo
> —y dentro del contenedor ya lo está.

El otro MCP, el del sentido contrario, es `intelliprint-mcp`
(`orchestrator/mcp_server.py`): con él Intelliprint **ofrece** sus herramientas a
Crafty. Por stdio en uso nativo, y por HTTP dentro del compose, donde Crafty vive
en otra imagen y no puede lanzarlo como subproceso.
