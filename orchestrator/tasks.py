"""Spec → PartTask (F1.9).

Versión mínima para la Fase 1, con una sola pieza. Cuando haya varias,
`Decomposition` (F3.2) produce un árbol de tareas y esto desaparece.
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
    brief = (
        f"Pieza: `{slug(spec.title)}`.\n\n"
        f"{spec.description}\n\n"
        f"Se imprimirá en {spec.material} en una {spec.printer}."
    )
    return PartTask(part=slug(spec.title), brief=brief)
