# orchestrator

Los flujos de pieza y de backlog, sus agentes, lo que mide el código y las dos puertas por las que se usa: la web y el servidor MCP para Crafty. Ver [SISTEMA_MULTIAGENTE.md](../SISTEMA_MULTIAGENTE.md) § 4.

| Módulo | Responsabilidad |
|---|---|
| `cli.py` | Las órdenes de `intelliprint`: `pieza`, `obra`, `banco`, `calibrar`, `animar`, `estudio`, `proyectos`, `perfil` |
| `pieza.py`, `obra.py` | Los dos flujos. Cada llamada da un paso y para donde hace falta la persona; el estado son los archivos de la carpeta del proyecto |
| `agents/`, `investigar.py`, `juez.py` | Los cinco agentes (requisitos, investigador, ingeniero, diseñador con el kit y desglosador) y el aviso opcional de JEV. Las instrucciones están en `config/agents/` |
| `llm/`, `schemas/` | Rol → modelo según el perfil, salida validada con reintento, gasto y tope; y los esquemas Pydantic (`Spec`, `Concepto`, `Programa`, `Obra`…) |
| `plan.py`, `medida.py`, `ingenieria.py`, `traceability.py` | Lo que comprueba el código: el plan mecánico, la resistencia del concepto y las medidas de la pieza construida |
| `build.py`, `recipes/`, `fcstd.py` | Componen el `build.py` de una pieza, lo ejecutan en `freecadcmd` y devuelven cada fallo al diseñador |
| `conjunto.py`, `assembly.py`, `animation.py`, `vista.py`, `estudio.py` | Mueven un conjunto y buscan choques, guardan el ensamble, dibujan la animación y hacen el estudio de movimientos |
| `componentes.py`, `tornilleria.py`, `materiales.py` | Las fichas de `library/components/`, y la tornillería y la lista de materiales contadas en lo construido |
| `banco.py` | El banco de pruebas que da la nota |
| `impresion.py`, `calibracion.py`, `medidas_impresora.py` | El perfil activo, las piezas de calibración y lo que el usuario midió en su impresora |
| `slicing.py`, `perfiles_laminado.py`, `proyecto_3mf.py`, `hostpaths.py`, `mcp/` | Laminado, por el puente del host (`mcp/client.py`) o con el binario local |
| `jobs.py`, `registry.py` | Trabajos en segundo plano, uno a la vez, y clasificación de los proyectos por lo que hay en su carpeta |
| `mcp_server.py`, `crafty.py` | El servidor MCP que usa Crafty, y su configuración generada desde el `.env` |
| `web/` | La interfaz web (FastAPI; el HTML se genera en Python) |

**Regla que atraviesa todo el módulo:** el modelo decide; el código calcula, mide y da los veredictos. Si escribes una función donde un modelo devuelve un número que luego se usa como cota sin que nada lo compruebe, revísala.
