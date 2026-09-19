# orchestrator

El orquestador: máquina de estados, agentes y puertos. Ver [SISTEMA_MULTIAGENTE.md](../SISTEMA_MULTIAGENTE.md) § 4.

| Módulo | Responsabilidad |
|---|---|
| `graph.py` | LangGraph: estados, transiciones, gates y reapertura selectiva |
| `agents/` | Un módulo por agente: prompt, esquema de salida y lista blanca de herramientas |
| `schemas/` | Pydantic: `Spec`, `ProductTree`, `Interface`, `Recipe`, `PartTask`, `QaReport` |
| `recipes/` | Compositor `recipe.json` → `build.py` y plantillas de macros |
| `human/` | `HumanPort` y sus adaptadores (§ 8.5) |
| `llm/` | `router.py`: modelo local vs. DeepSeek, perfiles y presupuestos |
| `mcp/` | Clientes MCP (HTTP/SSE) hacia FreeCAD, PrusaSlicer, `mech-toolkit` y `sim` |
| `ui/` | Web de aprobación y seguimiento (adaptador web del `HumanPort`) |

**Regla que atraviesa todo el módulo:** el LLM decide parámetros; el código calcula geometría y emite veredictos. Si escribes una función donde un modelo devuelve un número que luego se usa como cota, revísala.
