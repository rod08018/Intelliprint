# scripts

Utilidades del **host**, fuera de Docker.

| Script | Para qué |
|---|---|
| `start-host-mcps.ps1` | Lanza `mcp-proxy` para los MCP de FreeCAD (:8101) y PrusaSlicer (:8102) |

Los MCP de FreeCAD y PrusaSlicer hablan por **stdio** y no se pueden invocar desde un contenedor, así que se exponen por HTTP con un puente en el host (§ 8.2). El orquestador solo ve URLs.

Recuerda que FreeCAD se usa de dos formas (§ 9.3): la instancia **GUI** con el addon RPC para inspección y ensamble, y procesos **`freecadcmd`** efímeros para construir piezas en paralelo. El script solo necesita ocuparse de la primera.
