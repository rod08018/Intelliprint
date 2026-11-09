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

from orchestrator.build import ConstruccionFallida, guardar_diseno
from orchestrator.registry import latir
from orchestrator.schemas.concepto import ConceptoComprobado
from orchestrator.schemas.spec import Spec
from orchestrator.slicing import LaminadoFallido
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
    avisos: list[str] = []
    """Lo que el kit no pudo hacer sin romper la pieza (aristas que quedaron vivas)."""


CONCEPTO = "concepto.json"
INVESTIGACION = "investigacion.json"
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


def _redactar(peticion: str, carpeta: Path, requisitos, log, externos: str = "") -> Spec:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "request.md").write_text(peticion.strip() + "\n", encoding="utf-8")
    log("  admisión: el Requirements Agent redacta la especificación…")
    spec: Spec = (requisitos.draft(peticion, externos=externos) if externos
                  else requisitos.draft(peticion))
    (carpeta / "spec.yaml").write_text(
        yaml.safe_dump(spec.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    # Sin categoría a propósito: pedírsela al Requirements Agent cambió cómo
    # describe la pieza. El soporte NEMA17 de la e2e pasó a «Soporte estático
    # … con placa de montaje» y el ingeniero le añadió un pie en L, dos veces
    # de dos (2026-11-08). La categoría de una pieza la pone la persona.
    (carpeta / "pieza.json").write_text(
        json.dumps({"title": spec.title}, ensure_ascii=False), encoding="utf-8")
    return spec


def _titulo(carpeta: Path) -> str:
    try:
        return json.loads((carpeta / "pieza.json").read_text(encoding="utf-8"))["title"]
    except (OSError, ValueError, KeyError):
        return carpeta.name


def concebir_pieza(peticion: str, carpeta: Path, **kw) -> ConceptoComprobado | None:
    """Ver `_concebir`. Con latido: Crafty lanza la pieza en el contenedor
    del MCP y la web la mira desde el suyo, donde el pid de job.json no
    existe. Sin él, el soporte del 608ZZ en marcha se veía terminado
    (2026-11-08)."""
    with latir(carpeta):
        return _concebir(peticion, Path(carpeta), **kw)


def disenar_pieza(peticion: str, carpeta: Path, **kw) -> "InformePieza":
    """Ver `_disenar`. Con latido, por lo mismo que `concebir_pieza`."""
    with latir(carpeta):
        return _disenar(peticion, Path(carpeta), **kw)


ANTERIOR = "concepto_anterior.json"
CAMBIOS = "cambios.md"


def _de_la_vuelta_anterior(carpeta: Path) -> dict:
    """El último concepto que vio la persona y los cambios que pidió sobre
    él. Los cambios van al ingeniero y NO a la petición: el agente de
    requisitos leyó «un bloque macizo de unos 8 mm» —el defecto que había
    que quitar— como una cota de 8 mm que cumplir (pan-tilt, 2026-11-09)."""
    kw = {}
    if (carpeta / ANTERIOR).is_file():
        kw["anterior"] = ConceptoComprobado.model_validate_json(
            (carpeta / ANTERIOR).read_text(encoding="utf-8"))
    if (carpeta / CAMBIOS).is_file():
        kw["cambios"] = (carpeta / CAMBIOS).read_text(encoding="utf-8")
    return kw


def _concebir(peticion: str, carpeta: Path, *, requisitos, ingeniero,
              investigador=None, log=print) -> ConceptoComprobado | None:
    """Redacta la especificación y el concepto, y PARA a esperar el visto
    bueno. Devuelve None si el concepto no sale (queda `blocked.md`).

    `investigador` (F3.21 (investigar)): antes de redactar, busca en internet
    las medidas de lo que la petición nombra sin medir. Lo encontrado entra
    en los requisitos como `catalogo` y sale en el concepto con su fuente."""
    carpeta = Path(carpeta)
    # Un concepto nuevo (p. ej. tras contestar a sus preguntas) necesita un
    # visto bueno nuevo: el anterior era de otra cosa.
    (carpeta / APROBADO).unlink(missing_ok=True)
    (carpeta / CONCEPTO).unlink(missing_ok=True)
    # Lo de una ronda anterior ya no describe este proyecto: con rounds.json
    # o blocked.md viejos, el registro lo daría por fallido o aprobado.
    for viejo in ("rounds.json", "blocked.md", "pieza_report.json"):
        (carpeta / viejo).unlink(missing_ok=True)
    investigacion = None
    if investigador is not None:
        try:
            investigacion = investigador.investigar(peticion)
        except ValueError as e:   # el modelo no dio datos citables: se sigue sin ellos
            log(f"  investigación: no salió ({e})")
        if investigacion is not None:
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / INVESTIGACION).write_text(investigacion.model_dump_json(indent=2),
                                                 encoding="utf-8")
    try:
        spec = _redactar(peticion, carpeta, requisitos, log,
                         investigacion.texto_para_peticion() if investigacion else "")
        log(f"  «{spec.title}»: el ingeniero piensa cómo resolverlo…")
        concepto = ingeniero.concebir(spec, **_de_la_vuelta_anterior(carpeta))
    except ValueError as e:   # SalidaInvalida: el modelo no dio un concepto que se sostenga
        titulo = _titulo(carpeta)
        _cerrar(carpeta, titulo, InformePieza(titulo=titulo, resuelto=False,
                                              motivo=f"el concepto no salió: {e}"), peticion)
        return None
    (carpeta / CONCEPTO).write_text(concepto.model_dump_json(indent=2), encoding="utf-8")
    buscado = investigacion.texto_para_concepto() if investigacion else ""
    (carpeta / "concepto.md").write_text(
        f"# {spec.title}: el concepto\n\n{concepto.texto()}\n"
        + (f"\n{buscado}\n" if buscado else ""), encoding="utf-8")
    log(concepto.texto())
    return concepto


def _disenar(peticion: str, carpeta: Path, *, requisitos,
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
    guardar_diseno(carpeta / "parts" / tarea.part, receta)
    informe.volumen_mm3, informe.bbox_mm = resultado.volume_mm3, list(resultado.bbox_mm)
    informe.avisos = list(resultado.avisos)

    # Lo que la trazabilidad no encontró es un defecto, no una nota al pie:
    # la pieza no lleva una cota que pediste.
    if resultado.untraced_mm:
        cotas = ", ".join(f"{c:g} mm" for c in resultado.untraced_mm)
        informe.motivo = f"cotas de tu petición que NO aparecen en la pieza: {cotas}"
    if resultado.defectos:
        # F6.8 (mejor): la pieza sale, pero no como la pediste, y se dice qué falta.
        informe.motivo = "\n".join(filter(None, [
            informe.motivo, "la pieza entregada no cumple:", *resultado.defectos]))

    if laminar is not None:
        log("  laminado…")
        fabricacion = carpeta / "fabrication"
        fabricacion.mkdir(exist_ok=True)
        stl = carpeta / "parts" / tarea.part / f"{tarea.part}.stl"
        # Un laminado que falla no borra la pieza: el 2026-11-05 la excepción
        # tumbó el proceso y nueve piezas construidas quedaron sin informe.
        try:
            lamina = laminar(stl, fabricacion / f"{tarea.part}.gcode")
        except LaminadoFallido as e:
            informe.motivo = "\n".join(filter(None, [
                informe.motivo, f"no se pudo laminar: {e}"]))
        else:
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
