"""Construye un mecanismo completo: piezas, barrido de choques, ensamble y
animación. El ensamble se guarda SIEMPRE, también si hay choques: es
justamente cuando más falta hace abrirlo y ver dónde está el problema.

Hoy las piezas salen de las recetas de referencia de la disposición; el
Part Designer entrará por `disenar` (F3.14 (mecanismo)).
"""

from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from mech_toolkit.generators import CATALOGO
from orchestrator.assembly import Collision, build_assembly, sweep_collisions
from orchestrator.build import build_part
from orchestrator.schemas.recipe import Recipe

POSE_GUARDADA = 30.0
"""Ángulo del ensamble guardado. No 0°: con la manivela alineada con la
biela la foto no deja ver que son dos piezas."""


class MechanismReport(BaseModel):
    parts: dict[str, str]
    assembly: str
    animation: str | None
    angles: list[float]
    min_gap_mm: float
    collisions: list[Collision]

    @property
    def ok(self) -> bool:
        return not self.collisions


def build_mechanism(
    layout,
    carpeta: Path,
    freecadcmd: str,
    *,
    min_gap_mm: float,
    angulos: list[float] | None = None,
    animar: bool = True,
    disenar: Callable[[str, Recipe], Recipe] | None = None,
) -> MechanismReport:
    carpeta = Path(carpeta)
    angulos = list(angulos if angulos is not None else range(0, 360, 10))

    steps = {}
    for nombre, receta in layout.recipes().items():
        if disenar is not None:
            receta = disenar(nombre, receta)
        build_part(receta, CATALOGO, carpeta / "parts" / nombre, freecadcmd)
        steps[nombre] = carpeta / "parts" / nombre / f"{nombre}.step"

    poses = {a: layout.poses(a) for a in angulos}
    choques = sweep_collisions(steps, layout.pins(), poses, min_gap_mm, freecadcmd)

    ensamble = carpeta / "assembly.FCStd"
    build_assembly(steps, layout.pins(), layout.poses(POSE_GUARDADA), ensamble, freecadcmd)

    gif = None
    if animar:
        from orchestrator.animation import render_gif, tessellate

        gif = render_gif(
            tessellate(steps, layout.pins(), freecadcmd), poses,
            carpeta / "animation.gif", title=carpeta.name,
        )

    return MechanismReport(
        parts={n: str(p) for n, p in steps.items()},
        assembly=str(ensamble),
        animation=str(gif) if gif else None,
        angles=angulos,
        min_gap_mm=min_gap_mm,
        collisions=choques,
    )
