"""Construye un mecanismo completo: piezas, barrido de choques, ensamble y
animación. El ensamble se guarda SIEMPRE, también si hay choques: es
justamente cuando más falta hace abrirlo y ver dónde está el problema.

Las piezas las diseña el Part Designer con `llm_designer`, a partir de
los enunciados de la disposición (F3.14 (mecanismo)). Sin diseñador se
usan las recetas de referencia de la disposición.
"""

from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from mech_toolkit.generators import CATALOGO
from orchestrator.assembly import Collision, build_assembly, sweep_collisions
from orchestrator.build import build_part, design_and_build
from orchestrator.schemas.part_result import PartResult

Disenar = Callable[[str, Path], None]
"""(pieza, carpeta) → construye la pieza en `carpeta/<pieza>.step`."""

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

    def collision_summary(self) -> list[str]:
        """Un renglón por par de piezas: en qué ángulos y el peor caso."""
        pares: dict[tuple[str, str], list[Collision]] = {}
        for c in self.collisions:
            pares.setdefault((c.a, c.b), []).append(c)
        return [
            f"{a} / {b}: a {', '.join(f'{c.angle:g}°' for c in cs[:6])}"
            f"{'…' if len(cs) > 6 else ''} ({len(cs)} posiciones). Peor: "
            + min(cs, key=lambda c: c.gap_mm).motivo
            for (a, b), cs in pares.items()
        ]


def llm_designer(
    agent,
    briefs: dict[str, str],
    freecadcmd: str,
    check: Callable[[str, PartResult], str | None] | None = None,
) -> Disenar:
    """El Part Designer diseña cada pieza desde su enunciado. El enunciado
    hace también de petición para la trazabilidad (F1.16 (trazabilidad)):
    una cota que el modelo pierda vuelve a él con el valor exacto.

    `check(pieza, resultado)` comprueba la pieza construida (p. ej. que esté
    donde la espera el ensamble); su motivo también vuelve al modelo."""

    def disenar(nombre: str, carpeta: Path) -> None:
        receta, _ = design_and_build(
            agent, briefs[nombre], CATALOGO, carpeta,
            freecadcmd=freecadcmd, part=nombre, request=briefs[nombre],
            check=(lambda r: check(nombre, r)) if check else None,
        )
        # Qué diseñó el modelo y a partir de qué, junto a la pieza.
        (carpeta / "recipe.json").write_text(receta.model_dump_json(indent=2), encoding="utf-8")
        (carpeta / "brief.md").write_text(briefs[nombre] + "\n", encoding="utf-8")

    return disenar


def build_mechanism(
    layout,
    carpeta: Path,
    freecadcmd: str,
    *,
    min_gap_mm: float,
    angulos: list[float] | None = None,
    animar: bool = True,
    disenar: Disenar | None = None,
) -> MechanismReport:
    carpeta = Path(carpeta)
    angulos = list(angulos if angulos is not None else range(0, 360, 10))

    recetas = layout.recipes()
    if disenar is None:
        disenar = lambda n, c: build_part(recetas[n], CATALOGO, c, freecadcmd)  # noqa: E731

    steps = {}
    for nombre in recetas:
        disenar(nombre, carpeta / "parts" / nombre)
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
