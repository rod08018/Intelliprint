# mcp — servidores propios

Servidores MCP que corren en Docker. Ver [SISTEMA_MULTIAGENTE.md](../SISTEMA_MULTIAGENTE.md) § 9.2.

Los de FreeCAD y PrusaSlicer **no** están aquí: viven en el host y se exponen por HTTP (§ 8.2).

## `mech-toolkit`

Herramientas deterministas. Es donde vive la geometría que el LLM no debe calcular.

| Subcarpeta | Contenido |
|---|---|
| `generators/` | Un módulo por generador (`generate_bearing_housing`, `generate_bolt_pattern`, `generate_servo_mount`…). Es el catálogo con el que se componen las recetas (hoy, las piezas de calibración) |

**Regla de la sección 6 del plan:** las herramientas deterministas deben tener tests **antes** de que un agente las use.

Añadir un generador aquí es la respuesta correcta cuando la métrica de escotilla sube (§ 6.3): cada pieza atípica nombra el generador que falta.
