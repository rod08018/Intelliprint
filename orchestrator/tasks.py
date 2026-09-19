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


def spec_to_task(spec: Spec) -> PartTask:
    brief = f"Pieza: `{slug(spec.title)}`.\n\n{spec.description}\n\n"
    if spec.request:
        # La petición literal va entera: el resumen de arriba puede haber
        # perdido cotas, y lo que dijo el usuario manda sobre lo que sepas
        # tú de ese tipo de pieza.
        brief += (
            "Petición literal del usuario. Sus cotas mandan sobre cualquier "
            f"valor que conozcas para este tipo de pieza:\n> {spec.request}\n\n"
        )
    brief += f"Se imprimirá en {spec.material} en una {spec.printer}."
    return PartTask(part=slug(spec.title), brief=brief)
