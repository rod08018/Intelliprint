"""Grafo del proyecto (F1.14) con versionado git por etapa (F1.15).

Fase 1: un camino lineal admisión → diseño → laminado para una pieza. En
la Fase 3 se sustituye por el recorrido completo de la máquina de estados
(descomposición, interfaces, gate 1, ensamble); un `static_part` seguirá
saltándose la ingeniería de sistema (ADR-010).

La persistencia la da el checkpointer de SQLite de LangGraph: se guarda
el estado tras cada nodo, así que si el proceso muere a mitad, invocar de
nuevo con el mismo `thread_id` continúa desde el nodo que falló sin
repetir lo anterior. Es la base de que un proyecto pueda esperar días
(regla 7 de § 4).
"""

import datetime as dt
import json
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypedDict

import yaml
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.human.port import HumanPort
from orchestrator.schemas.spec import Spec
from orchestrator.state_machine import AprobacionRequerida, advance
from orchestrator.tasks import slug, spec_to_task


class Estado(TypedDict, total=False):
    peticion: str
    estado: str
    spec: dict
    proyecto: str
    part: str
    recipe: dict
    result: dict
    slicing: dict


@dataclass
class Dependencias:
    """Todo lo que el grafo usa se inyecta: así se prueba sin LLM ni FreeCAD."""

    requirements: Any  # .draft(peticion) -> Spec
    disenar: Callable  # (spec, carpeta, part) -> (Recipe, PartResult)
    laminar: Callable  # (stl, salida) -> SlicingReport
    port: HumanPort
    workspace: Path


def versionar(proyecto: Path, mensaje: str) -> None:
    """Un commit por etapa en el repo git del propio proyecto (F1.15).

    Firmado como Crafty y no con la identidad del usuario: son cambios
    que hizo el sistema, y así se distinguen de los que haga él a mano.
    """
    if not (proyecto / ".git").exists():
        subprocess.run(["git", "init", "-q", str(proyecto)], check=True)
    subprocess.run(["git", "-C", str(proyecto), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(proyecto),
         "-c", "user.name=Crafty", "-c", "user.email=crafty@intelliprint.local",
         "commit", "-q", "--allow-empty", "-m", mensaje],
        check=True,
    )


def _resumen(spec: Spec) -> str:
    lineas = [
        f"  título:      {spec.title}",
        f"  clase:       {spec.product_class}",
        f"  material:    {spec.material} en {spec.printer}",
        f"  descripción: {spec.description}",
    ]
    if spec.payload_g is not None:
        lineas.append(f"  carga:       {spec.payload_g:g} g")
    if spec.reach_mm is not None:
        lineas.append(f"  alcance:     {spec.reach_mm:g} mm")
    if spec.estimated_critical:
        lineas.append(
            f"  ⚠️ supuse estos datos y el diseño depende de ellos: "
            f"{', '.join(spec.estimated_critical)}"
        )
    return "\n" + "\n".join(lineas)


def crear_grafo(deps: Dependencias, db_path: Path):
    def admision(s: Estado) -> Estado:
        spec = deps.requirements.draft(s["peticion"])
        try:
            estado = advance("INTAKE", "SPEC_READY", port=deps.port, resumen=_resumen(spec))
        except AprobacionRequerida:
            # Sin confirmación no hay proyecto: nada en disco (ADR-008).
            return {"spec": spec.model_dump(), "estado": "INTAKE"}

        proyecto = deps.workspace / f"{dt.date.today().isoformat()}-{slug(spec.title)}"
        proyecto.mkdir(parents=True, exist_ok=True)
        (proyecto / "spec.yaml").write_text(
            yaml.safe_dump(spec.model_dump(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        versionar(proyecto, "admisión: SPEC_READY")
        return {"spec": spec.model_dump(), "estado": estado, "proyecto": str(proyecto)}

    def diseno(s: Estado) -> Estado:
        spec = Spec(**s["spec"])
        tarea = spec_to_task(spec)
        proyecto = Path(s["proyecto"])
        carpeta = proyecto / "parts" / tarea.part
        carpeta.mkdir(parents=True, exist_ok=True)

        receta, resultado = deps.disenar(spec, carpeta, tarea.part)
        (carpeta / "recipe.json").write_text(receta.model_dump_json(indent=2), encoding="utf-8")
        versionar(proyecto, "diseño: PARTS_BUILT")
        return {
            "part": tarea.part,
            "recipe": receta.model_dump(),
            "result": resultado.model_dump(),
            "estado": "PARTS_BUILT",
        }

    def laminado(s: Estado) -> Estado:
        proyecto = Path(s["proyecto"])
        part = s["part"]
        fabricacion = proyecto / "fabrication"
        fabricacion.mkdir(exist_ok=True)

        informe = deps.laminar(
            proyecto / "parts" / part / f"{part}.stl", fabricacion / f"{part}.gcode"
        )
        (fabricacion / "slicing_report.json").write_text(
            json.dumps(informe.model_dump(), indent=2), encoding="utf-8"
        )
        versionar(proyecto, "laminado: SLICED")
        return {"slicing": informe.model_dump(), "estado": "SLICED"}

    def tras_admision(s: Estado) -> str:
        return "diseno" if s["estado"] == "SPEC_READY" else END

    grafo = StateGraph(Estado)
    grafo.add_node("admision", admision)
    grafo.add_node("diseno", diseno)
    grafo.add_node("laminado", laminado)
    grafo.add_edge(START, "admision")
    grafo.add_conditional_edges("admision", tras_admision, ["diseno", END])
    grafo.add_edge("diseno", "laminado")
    grafo.add_edge("laminado", END)

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(str(db_path), check_same_thread=False)
    return grafo.compile(checkpointer=SqliteSaver(conexion))
