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


def spec_to_task(spec: Spec) -> PartTask:
    brief = f"Pieza: `{nombre_corto(spec.title)}`.\n\n{spec.description}\n\n"
    if spec.request:
        # La petición literal va entera: el resumen de arriba puede haber
        # perdido cotas, y lo que dijo el usuario manda sobre lo que sepas
        # tú de ese tipo de pieza.
        brief += (
            "Petición literal del usuario. Sus cotas mandan sobre cualquier "
            f"valor que conozcas para este tipo de pieza:\n> {spec.request}\n\n"
        )
    brief += f"Se imprimirá en {spec.material} en una {spec.printer}."
    return PartTask(part=nombre_corto(spec.title), brief=brief)
