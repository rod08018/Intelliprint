# orchestrator

El orquestador: los flujos de pieza y de backlog, sus agentes y la web. Ver [SISTEMA_MULTIAGENTE.md](../SISTEMA_MULTIAGENTE.md) § 4.

| Módulo | Responsabilidad |
|---|---|
| `agents/` | Un módulo por agente: prompt, esquema de salida y lista blanca de herramientas |
| `schemas/` | Pydantic: `Spec`, `ProductTree`, `Recipe`, `PartTask` |
| `recipes/` | Compositor `recipe.json` → `build.py` y plantillas de macros |
| `llm/` | `router.py`: modelo local vs. DeepSeek, perfiles y presupuestos |
| `mcp/` | Clientes MCP (HTTP/SSE) hacia FreeCAD, PrusaSlicer y `mech-toolkit` |
| `web/` | Web de aprobación y seguimiento |

**Regla que atraviesa todo el módulo:** el LLM decide parámetros; el código calcula geometría y emite veredictos. Si escribes una función donde un modelo devuelve un número que luego se usa como cota, revísala.
