# scripts

Lo que se ejecuta en el **host**, fuera de Docker.

| Script | Para qué |
|---|---|
| `start-host-mcps.ps1` | Arranca el puente del host |
| `host_bridge.py` | El puente: un servidor MCP con el que el contenedor usa el PrusaSlicer del PC (puerto 8102) |
| `eval_requirements.py` | Mide la extracción de requisitos con llamadas reales al modelo. Se ejecuta a mano; no es parte de la suite |
| `eval_structured_output.py` | Mide cuántas veces el modelo devuelve un esquema válido a la primera. También a mano |

## El puente del host

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-host-mcps.ps1
```

**Por qué PrusaSlicer está fuera y FreeCAD dentro** (ADR-014): FreeCAD es una
herramienta interna —construye y calla—, así que va en la imagen y el
orquestador lo lanza como subproceso. PrusaSlicer es donde la persona mira
**qué va a imprimir** antes de mandarlo a la máquina, y tiene que ser el suyo,
con su versión y sus ajustes.

El puente ofrece `laminar` (sin ventana, devuelve gramos y horas) y
`abrir_en_prusaslicer` (abre el programa con las piezas y el perfil cargados —es
lo que hace el botón de la interfaz web).

Comprueba lo que entra **aunque el orquestador ya lo haya comprobado**: el que
ejecuta no delega eso en el que pide. Las rutas tienen que estar dentro de
`workspace/`, y el perfil se pide por NOMBRE y se resuelve en `config/slicing/`;
si se pudiera mandar la ruta, el contenedor estaría eligiendo qué archivo del PC
se lee.

Sin el puente arrancado, el contenedor no puede laminar ni abrir PrusaSlicer.

El otro servidor MCP, el del sentido contrario, es `intelliprint-mcp`
(`orchestrator/mcp_server.py`): con él Intelliprint **ofrece** sus herramientas a
Crafty. Por stdio en uso nativo, y por HTTP dentro del compose, donde Crafty vive
en otra imagen y no puede lanzarlo como subproceso.
