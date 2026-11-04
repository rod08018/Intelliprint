"""Una pieza suelta, sin pasar por el flujo de mecanismos (F5.17 (pieza)).

Hasta ahora la web, Crafty y el bot solo sabían pedir mecanismos, y un
mecanismo exige dos piezas como mínimo: un soporte o un gancho había que
disfrazarlo de mecanismo. Esto es el camino de `intelliprint new` sin la
confirmación por consola —quien pide desde la web o Telegram ya confirmó
al pedir— y en la carpeta que le dan, para que el registro, la web y el
canal lo vean como a cualquier otro proyecto.

Deja en la carpeta lo mismo que espera el registro: `request.md`,
`rounds.json` (una ronda; su `feedback` es lo que falla) y, si no sale,
`blocked.md` con el porqué.
"""

import json
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel

from orchestrator.build import ConstruccionFallida
from orchestrator.schemas.spec import Spec
from orchestrator.tasks import spec_to_task


class InformePieza(BaseModel):
    titulo: str
    pieza: str = ""
    resuelto: bool
    motivo: str = ""
    volumen_mm3: float | None = None
    bbox_mm: list[float] = []
    gramos: float | None = None
    soportes: bool | None = None


def disenar_pieza(peticion: str, carpeta: Path, *, requisitos,
                  disenar: Callable, laminar: Callable | None, log=print) -> InformePieza:
    """`requisitos`: el Requirements Agent. `disenar(spec, carpeta, parte)`
    devuelve (receta, resultado) o lanza `ConstruccionFallida`.
    `laminar(stl, gcode)` devuelve el `SlicingReport`; None si no hay
    laminador (la pieza sale igual, sin gramos)."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "request.md").write_text(peticion.strip() + "\n", encoding="utf-8")

    log("  admisión: el Requirements Agent redacta la especificación…")
    spec: Spec = requisitos.draft(peticion)
    (carpeta / "spec.yaml").write_text(
        yaml.safe_dump(spec.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    (carpeta / "pieza.json").write_text(
        json.dumps({"title": spec.title}, ensure_ascii=False), encoding="utf-8")
    tarea = spec_to_task(spec)
    log(f"  «{spec.title}»: el Part Designer dibuja «{tarea.part}»…")

    informe = InformePieza(titulo=spec.title, pieza=tarea.part, resuelto=False)
    try:
        receta, resultado = disenar(spec, carpeta / "parts" / tarea.part, tarea.part)
    except ConstruccionFallida as e:
        informe.motivo = e.motivo
        _cerrar(carpeta, spec.title, informe, peticion)
        return informe
    (carpeta / "parts" / tarea.part / "recipe.json").write_text(
        receta.model_dump_json(indent=2), encoding="utf-8")
    informe.volumen_mm3, informe.bbox_mm = resultado.volume_mm3, list(resultado.bbox_mm)

    # Lo que la trazabilidad no encontró es un defecto, no una nota al pie:
    # la pieza no lleva una cota que pediste.
    if resultado.untraced_mm:
        cotas = ", ".join(f"{c:g} mm" for c in resultado.untraced_mm)
        informe.motivo = f"cotas de tu petición que NO aparecen en la pieza: {cotas}"

    if laminar is not None:
        log("  laminado…")
        fabricacion = carpeta / "fabrication"
        fabricacion.mkdir(exist_ok=True)
        stl = carpeta / "parts" / tarea.part / f"{tarea.part}.stl"
        lamina = laminar(stl, fabricacion / f"{tarea.part}.gcode")
        (fabricacion / "slicing_report.json").write_text(
            json.dumps(lamina.model_dump(), indent=2), encoding="utf-8")
        informe.gramos, informe.soportes = lamina.grams, lamina.needs_supports

    informe.resuelto = not informe.motivo
    _cerrar(carpeta, spec.title, informe, peticion)
    return informe


def _cerrar(carpeta: Path, titulo: str, informe: InformePieza, peticion: str) -> None:
    (carpeta / "rounds.json").write_text(json.dumps(
        [{"number": 1, "title": titulo, "feedback": informe.motivo, "plan": None}],
        indent=2, ensure_ascii=False), encoding="utf-8")
    (carpeta / "pieza_report.json").write_text(informe.model_dump_json(indent=2),
                                                encoding="utf-8")
    if not informe.resuelto:
        (carpeta / "blocked.md").write_text("\n".join([
            f"# {titulo}: hace falta que decidas", "",
            "## Lo que pediste", "", f"> {peticion.strip().splitlines()[0][:300]}", "",
            "## Qué falla", "", "```", informe.motivo.strip()[:1200], "```", ""]),
            encoding="utf-8")
