# scripts

Utilidades del **host**, fuera de Docker.

| Script | Para qué |
|---|---|
| `demo.py` | Recorrido de extremo a extremo sin modelo, para ver el sistema funcionando |
| `eval_part_designer.py` | Mide al Part Designer contra peticiones de referencia |
| `eval_requirements.py` | Mide la extracción de requisitos |
| `eval_structured_output.py` | Mide cuántas veces el modelo devuelve un esquema válido a la primera |

## Lo que este README prometía y NO existe

Decía que aquí vivía `start-host-mcps.ps1`, un puente `mcp-proxy` para exponer por HTTP los MCP de FreeCAD (:8101) y PrusaSlicer (:8102) al contenedor (§ 8.2, F0.4), y que «el orquestador solo ve URLs».

**Nada de eso se construyó.** No hay script, no hay puente y no hay cliente MCP en el orquestador (F0.5, `orchestrator/mcp/client.py`). El orquestador **lanza `freecadcmd` como subproceso** y le pasa rutas del sistema de archivos: ver `_freecadcmd()` en `orchestrator/cli.py`.

Esto importa al montar el sistema en otra máquina: **un MCP de FreeCAD ya levantado en el host no lo usa nadie.** Lo que Intelliprint necesita es el binario `freecadcmd` accesible, y `FREECADCMD` apuntándolo si no está en el PATH. Queda anotado como deuda en el plan.

El único MCP que sí existe es el del sentido contrario: `intelliprint-mcp` (`orchestrator/mcp_server.py`), con el que Intelliprint **ofrece** sus herramientas a OpenClaw por stdio.
