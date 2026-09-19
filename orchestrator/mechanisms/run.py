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
    notes: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.collisions

    def collision_summary(self) -> list[str]:
        """Un renglón por par de piezas: en qué ángulos y el peor caso."""
        pares: dict[tuple[str, str], list[Collision]] = {}
        for c in self.collisions:
            pares.setdefault((c.a, c.b), []).append(c)
        return [
            f"{a} / {b}: con t = {', '.join(f'{c.angle:g}' for c in cs[:6])}"
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


def reference_bounds(layout, carpeta: Path, freecadcmd: str):
    """Construye las piezas de referencia de la disposición y devuelve una
    comprobación `check(pieza, resultado)` contra su caja envolvente.

    Lo que se compara es DÓNDE está la pieza, no cómo está hecha: el modelo
    puede usar otros generadores, pero la pieza tiene que ocupar el sitio
    que las poses le asignan."""
    cajas = {}
    for nombre, receta in layout.recipes().items():
        r = build_part(receta, CATALOGO, Path(carpeta) / nombre, freecadcmd)
        cajas[nombre] = (r.bbox_min, r.bbox_max)

    def check(nombre: str, resultado: PartResult, tol: float = 0.1) -> str | None:
        lo, hi = cajas[nombre]
        fuera = [i for i in range(3)
                 if abs(resultado.bbox_min[i] - lo[i]) > tol or abs(resultado.bbox_max[i] - hi[i]) > tol]
        if not fuera:
            return None
        rango = lambda a, b, i: f"{'xyz'[i]} de {a[i]:.4g} a {b[i]:.4g} mm"  # noqa: E731
        return (
            f"la pieza ocupa {', '.join(rango(resultado.bbox_min, resultado.bbox_max, i) for i in fuera)}; "
            f"el ensamble la necesita en {', '.join(rango(lo, hi, i) for i in fuera)}. "
            "Revisa el origen, la posición y las medidas de cada cuerpo según el enunciado."
        )

    return check


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
    """`layout` es la disposición de un mecanismo. Obligatorio: `recipes()`,
    `briefs()`, `pins()` y `poses(t)`. Opcional: `frames()` (valores de t de
    una vuelta o ciclo), `pair_rules()`, `colors`, `label(t)`, `view`,
    `saved_frame` y `notes()` (líneas para el informe)."""
    carpeta = Path(carpeta)
    if angulos is None:
        angulos = layout.frames() if hasattr(layout, "frames") else range(0, 360, 10)
    angulos = list(angulos)
    reglas = layout.pair_rules() if hasattr(layout, "pair_rules") else {}

    if disenar is None:
        recetas = layout.recipes()
        disenar = lambda n, c: build_part(recetas[n], CATALOGO, c, freecadcmd)  # noqa: E731

    steps = {}
    for nombre in layout.briefs():
        disenar(nombre, carpeta / "parts" / nombre)
        steps[nombre] = carpeta / "parts" / nombre / f"{nombre}.step"

    poses = {a: layout.poses(a) for a in angulos}
    choques = sweep_collisions(steps, layout.pins(), poses, min_gap_mm, freecadcmd, reglas)

    ensamble = carpeta / "assembly.FCStd"
    guardada = getattr(layout, "saved_frame", POSE_GUARDADA)
    build_assembly(steps, layout.pins(), layout.poses(guardada), ensamble, freecadcmd)

    gif = None
    if animar:
        from orchestrator.animation import render_gif, tessellate

        animacion = (
            [(t, layout.poses(t)) for t in layout.animation_frames()]
            if hasattr(layout, "animation_frames") else poses
        )
        gif = render_gif(
            tessellate(steps, layout.pins(), freecadcmd), animacion,
            carpeta / "animation.gif", title=getattr(layout, "title", carpeta.name),
            colors=getattr(layout, "colors", None), label=getattr(layout, "label", None),
            view=getattr(layout, "view", (40, -65)),
        )

    return MechanismReport(
        parts={n: str(p) for n, p in steps.items()},
        assembly=str(ensamble),
        animation=str(gif) if gif else None,
        angles=angulos,
        min_gap_mm=min_gap_mm,
        collisions=choques,
        notes=layout.notes() if hasattr(layout, "notes") else [],
    )
