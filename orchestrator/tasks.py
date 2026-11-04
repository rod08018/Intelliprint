"""Spec → PartTask (F1.9 (PartTask)).

Versión mínima para la Fase 1, con una sola pieza. Cuando haya varias,
`Decomposition` (F3.2 (decomposition)) produce un árbol de tareas y esto desaparece.
"""

import re
import unicodedata

from orchestrator.schemas.part_task import PartTask
from orchestrator.schemas.spec import Spec


def slug(texto: str) -> str:
    """Nombre usable como carpeta y como nombre de archivo."""
    sin_tildes = (
        unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes.lower()).strip("_")


NOMBRE_DE_PIEZA_MAX = 32
"""El nombre de la pieza sale tres veces en su ruta (carpeta del proyecto,
parts/<pieza>/, <pieza>.FCStd), y FreeCAD en Windows no pasa de 260
caracteres: «placa_40x40x5_con_taladro_central_de_25_mm» construía a 204 y
fallaba a 262 (2026-10-27)."""


def nombre_corto(texto: str, maximo: int = NOMBRE_DE_PIEZA_MAX) -> str:
    """El slug de `texto` en `maximo` caracteres, cortado entre palabras."""
    nombre = slug(texto)
    if len(nombre) <= maximo:
        return nombre
    corte = nombre[:maximo + 1].rfind("_")
    return (nombre[:corte] if corte > 0 else nombre[:maximo]).strip("_")


def spec_to_task(spec: Spec, concepto=None) -> PartTask:
    """`concepto`: el `ConceptoComprobado` que aprobó la persona (F3.18 (ingeniero))."""
    brief = f"Pieza: `{nombre_corto(spec.title)}`.\n\n{spec.description}\n\n"
    if spec.request:
        # La petición literal va entera: el resumen de arriba puede haber
        # perdido cotas, y lo que dijo el usuario manda sobre lo que sepas
        # tú de ese tipo de pieza.
        brief += (
            "Petición literal del usuario. Sus cotas mandan sobre cualquier "
            f"valor que conozcas para este tipo de pieza:\n> {spec.request}\n\n"
        )
    if spec.requisitos:
        # Con su id: así la medida (F6) y el revisor pueden decir «R3 no se
        # cumple», y una modificación reemplaza R3 en vez de añadir prosa.
        brief += "Requisitos (cada uno con su id):\n" + "".join(
            f"- **{r.id}** ({r.tipo}, {r.origen}): {r.texto}"
            + (f" → {r.valor:g} {r.unidad}" if r.valor is not None else "")
            + (f", {r.cantidad} de ellos" if r.cantidad else "")
            + (f", a {', '.join(f'{s:g}' for s in r.separaciones_mm)} mm entre centros"
               if r.separaciones_mm else "")
            + (f"; tiene que pasar entero por una abertura de la pieza: "
               f"{' × '.join(f'{s:g}' for s in r.seccion_mm)} mm"
               if len(r.seccion_mm) == 2 else "") + "\n"
            for r in spec.requisitos) + "\n"
    if concepto is not None:
        brief += concepto.para_el_disenador() + "\n\n"
    brief += f"Se imprimirá en {spec.material} en una {spec.printer}."
    return PartTask(part=nombre_corto(spec.title), brief=brief)
