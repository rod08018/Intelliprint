"""Servidor MCP de Intelliprint (F5.6 (telegram)).

Es la puerta por la que Crafty —el agente de OpenClaw que habla contigo en
Telegram— usa el sistema. OpenClaw pone la conversación; Intelliprint pone
el diseño. Esa separación es la de § 8.5: el canal es transporte, no un
agente del grafo.

Cada herramienta devuelve datos, nunca instrucciones. Lo que llegue por el
canal es una petición de diseño y nada más: aquí no hay ninguna forma de
ejecutar código arbitrario.

Se arranca solo (lo lanza OpenClaw por stdio):
    intelliprint-mcp
"""

import os
import sys
from pathlib import Path

from mcp.server import MCPServer

from orchestrator.jobs import JobStore

mcp = MCPServer(
    "intelliprint",
    instructions=(
        "Diseño de mecanismos imprimibles en 3D. `disenar_mecanismo` tarda "
        "minutos y trabaja en segundo plano: no esperes, pregunta el estado."
    ),
)


def _raiz() -> Path:
    for carpeta in [Path.cwd(), *Path.cwd().parents]:
        if (carpeta / "config" / "models.yaml").exists():
            return carpeta
    sys.exit("ejecuta intelliprint-mcp dentro del repo de Intelliprint")


def _store() -> JobStore:
    raiz = _raiz()
    workspace = Path(os.environ.get("INTELLIPRINT_WORKSPACE") or raiz / "workspace")
    ejecutable = raiz / ".venv" / "bin" / "intelliprint"
    comando = [str(ejecutable) if ejecutable.exists() else "intelliprint", "mecanismo"]
    return JobStore(workspace / "projects", comando)


@mcp.tool()
def disenar_mecanismo(peticion: str) -> dict:
    """Diseña un mecanismo a partir de una petición en texto y lo verifica.

    Tarda varios minutos: devuelve al momento el identificador del proyecto
    y sigue trabajando por su cuenta. Consulta `estado_proyecto` para saber
    cómo va y `archivos_proyecto` cuando termine.

    La petición debe describir el mecanismo con todo lo que el usuario haya
    dicho: qué tiene que hacer, medidas, límites de movimiento y qué piezas
    exige. Cuanto más completa, menos rondas de corrección.
    """
    store = _store()
    try:
        job = store.start(peticion)
    except RuntimeError as e:
        return {"error": str(e), "en_marcha": store.current()}
    return {
        "proyecto": job,
        "aviso": "Diseñando. Cada ronda tarda unos 4 minutos y hay hasta 5 rondas. "
                 "Pregunta el estado de vez en cuando; no te quedes esperando.",
    }


@mcp.tool()
def estado_proyecto(proyecto: str = "") -> dict:
    """Cómo va un proyecto: si sigue trabajando, en qué ronda y lo último
    que hizo. Sin argumento, el más reciente."""
    store = _store()
    if not proyecto:
        proyectos = store.list(1)
        if not proyectos:
            return {"estado": "no hay proyectos todavía"}
        proyecto = proyectos[0]["id"]
    try:
        return store.status(proyecto)
    except KeyError as e:
        return {"error": str(e)}


@mcp.tool()
def archivos_proyecto(proyecto: str = "") -> dict:
    """Rutas de los archivos de un proyecto: la animación del movimiento
    (GIF), el ensamble para FreeCAD, la revisión frente a la petición y el
    diseño del mecanismo. Manda al usuario el GIF y el ensamble."""
    store = _store()
    if not proyecto:
        proyectos = store.list(1)
        if not proyectos:
            return {"error": "no hay proyectos todavía"}
        proyecto = proyectos[0]["id"]
    archivos = store.artifacts(proyecto)
    return archivos or {"error": f"{proyecto} todavía no tiene archivos"}


@mcp.tool()
def listar_proyectos(limite: int = 10) -> list[dict]:
    """Los proyectos más recientes con su estado."""
    return _store().list(limite)


@mcp.tool()
def cancelar_proyecto(proyecto: str) -> dict:
    """Detiene un proyecto en marcha."""
    store = _store()
    store.cancel(proyecto)
    return store.status(proyecto)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
