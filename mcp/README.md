# mcp — el paquete `mech-toolkit`

Aquí **no hay servidores MCP**. La carpeta se llama así porque `mech-toolkit` se planeó como un servicio aparte, F2.1 (servicio), y no se hizo: es un paquete de Python que se instala junto al orquestador y se importa. Ver [SISTEMA_MULTIAGENTE.md](../SISTEMA_MULTIAGENTE.md) § 9.2.

Los dos servidores MCP que sí existen están en otro sitio: `orchestrator/mcp_server.py`, que usa Crafty, y `scripts/host_bridge.py`, el puente al PrusaSlicer del PC (§ 9.1).

## `mech-toolkit/mech_toolkit/`

Es donde vive la geometría que el modelo no debe calcular.

| Módulo | Contenido |
|---|---|
| `kit/` | Las operaciones con las que el diseñador escribe `construir(kit)` y la lista blanca que valida su programa (`sandbox.py`) |
| `sondas.py` | Medidas sobre el STEP construido, dentro de FreeCAD: pared mínima, aristas vivas, si un componente cabe y entra, acceso a un tornillo, sitio libre de un giro |
| `componentes.py` | Coloca la forma de una ficha de `library/components/` en la pieza |
| `profile.py` | El perfil de impresora y sus holguras |
| `measure.py`, `geometry.py` | Extraen las caras cilíndricas de una pieza y buscan agujeros y salientes por su posición |
| `generators.py` | El catálogo de generadores de las recetas. Hoy solo construye las piezas de calibración |
| `library_models.py` | Importa los modelos de referencia de `library/models/reference/` |

**Regla:** lo que mide o construye tiene tests antes de que un agente dependa de ello, y el valor esperado sale de un cálculo a mano o de una referencia, no de la salida del propio sistema.
