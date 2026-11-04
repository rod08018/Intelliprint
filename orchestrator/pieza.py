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

Antes de modelar, el ingeniero propone un concepto y la persona lo aprueba
(F3.20 (concepto)): `concebir_pieza` lo deja en `concepto.md` y para;
`aprobar_concepto` deja la marca, y `disenar_pieza` modela ESE concepto con
la especificación que se aprobó, sin redactarla otra vez.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel

from orchestrator.build import ConstruccionFallida
from orchestrator.schemas.concepto import ConceptoComprobado
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


CONCEPTO = "concepto.json"
APROBADO = "concepto_aprobado"


def concepto_pendiente(carpeta: Path) -> bool:
    """Hay un concepto y nadie le ha dado el visto bueno."""
    return (Path(carpeta) / CONCEPTO).exists() and not (Path(carpeta) / APROBADO).exists()


def aprobar_concepto(carpeta: Path, por: str) -> None:
    """La marca del visto bueno, con quién y cuándo: es la barrera humana
    del concepto, y queda en el proyecto como cualquier otra evidencia."""
    carpeta = Path(carpeta)
    if not (carpeta / CONCEPTO).exists():
        raise ValueError(f"{carpeta.name} no tiene ningún concepto que aprobar")
    (carpeta / APROBADO).write_text(json.dumps(
        {"por": por, "cuando": dt.datetime.now().isoformat(timespec="seconds")}),
        encoding="utf-8")


def _redactar(peticion: str, carpeta: Path, requisitos, log) -> Spec:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "request.md").write_text(peticion.strip() + "\n", encoding="utf-8")
    log("  admisión: el Requirements Agent redacta la especificación…")
    spec: Spec = requisitos.draft(peticion)
    (carpeta / "spec.yaml").write_text(
        yaml.safe_dump(spec.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    (carpeta / "pieza.json").write_text(
        json.dumps({"title": spec.title}, ensure_ascii=False), encoding="utf-8")
    return spec


def _titulo(carpeta: Path) -> str:
    try:
        return json.loads((carpeta / "pieza.json").read_text(encoding="utf-8"))["title"]
    except (OSError, ValueError, KeyError):
        return carpeta.name


def concebir_pieza(peticion: str, carpeta: Path, *, requisitos, ingeniero,
                   log=print) -> ConceptoComprobado | None:
    """Redacta la especificación y el concepto, y PARA a esperar el visto
    bueno. Devuelve None si el concepto no sale (queda `blocked.md`)."""
    carpeta = Path(carpeta)
    # Un concepto nuevo (p. ej. tras contestar a sus preguntas) necesita un
    # visto bueno nuevo: el anterior era de otra cosa.
    (carpeta / APROBADO).unlink(missing_ok=True)
    (carpeta / CONCEPTO).unlink(missing_ok=True)
    # Lo de una ronda anterior ya no describe este proyecto: con rounds.json
    # o blocked.md viejos, el registro lo daría por fallido o aprobado.
    for viejo in ("rounds.json", "blocked.md", "pieza_report.json"):
        (carpeta / viejo).unlink(missing_ok=True)
    try:
        spec = _redactar(peticion, carpeta, requisitos, log)
        log(f"  «{spec.title}»: el ingeniero piensa cómo resolverlo…")
        concepto = ingeniero.concebir(spec)
    except ValueError as e:   # SalidaInvalida: el modelo no dio un concepto que se sostenga
        titulo = _titulo(carpeta)
        _cerrar(carpeta, titulo, InformePieza(titulo=titulo, resuelto=False,
                                              motivo=f"el concepto no salió: {e}"), peticion)
        return None
    (carpeta / CONCEPTO).write_text(concepto.model_dump_json(indent=2), encoding="utf-8")
    (carpeta / "concepto.md").write_text(
        f"# {spec.title}: el concepto\n\n{concepto.texto()}\n", encoding="utf-8")
    log(concepto.texto())
    return concepto


def disenar_pieza(peticion: str, carpeta: Path, *, requisitos,
                  disenar: Callable, laminar: Callable | None, log=print) -> InformePieza:
    """`requisitos`: el Requirements Agent. `disenar(spec, carpeta, parte,
    concepto)` devuelve (receta, resultado) o lanza `ConstruccionFallida`.
    `laminar(stl, gcode)` devuelve el `SlicingReport`; None si no hay
    laminador (la pieza sale igual, sin gramos).

    Con un concepto aprobado en la carpeta, se modela ESE concepto con la
    especificación que se aprobó: redactarla otra vez podría dar otra."""
    carpeta = Path(carpeta)
    concepto = None
    if (carpeta / APROBADO).exists() and (carpeta / CONCEPTO).exists():
        spec = Spec(**yaml.safe_load((carpeta / "spec.yaml").read_text(encoding="utf-8")))
        concepto = ConceptoComprobado.model_validate_json(
            (carpeta / CONCEPTO).read_text(encoding="utf-8"))
    else:
        spec = _redactar(peticion, carpeta, requisitos, log)
    tarea = spec_to_task(spec, concepto)
    log(f"  «{spec.title}»: el Part Designer dibuja «{tarea.part}»…")

    informe = InformePieza(titulo=spec.title, pieza=tarea.part, resuelto=False)
    try:
        receta, resultado = disenar(spec, carpeta / "parts" / tarea.part, tarea.part, concepto)
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
