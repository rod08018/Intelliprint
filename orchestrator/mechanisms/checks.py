"""Comprobaciones de coherencia entre la cinemática y las piezas dibujadas.

Fallo real que motivó este módulo (reto de la bisagra): el enunciado decía
a la vez "placa centrada en el origen" y "origen en el centro del nudillo".
El Part Designer siguió la primera frase; la pieza giraba alrededor de un
punto sin agujero y el pasador atravesaba la placa. El barrido lo ve como
un solape, pero no dice POR QUÉ. Esto sí.
"""

from pathlib import Path

from mech_toolkit.geometry import Frame, _distancia_a_recta, _paralelo
from mech_toolkit.measure import extract_cylinders
from orchestrator.assembly import pair_gaps
from orchestrator.schemas.mechanism import MechanismSpec

POS_TOL_MM = 0.2


def joint_axis_problems(spec: MechanismSpec, steps: dict[str, Path], freecadcmd: str) -> list[str]:
    """Toda pieza con articulación de giro tiene que tener, en su eje de giro
    (que pasa por su origen local), un agujero o un saliente cilíndrico."""
    problemas = []
    for p in spec.parts:
        if p.joint is None or p.joint.type != "revolute" or p.name not in steps:
            continue
        eje = Frame(origin=[0.0, 0.0, 0.0], axis=p.joint.axis)
        caras = extract_cylinders(steps[p.name], freecadcmd)
        coaxiales = [c for c in caras if _paralelo(c.axis, eje.axis)
                     and _distancia_a_recta(eje.origin, c.point, c.axis) <= POS_TOL_MM]
        if coaxiales:
            continue
        agujeros = sorted({
            (round(c.point[0], 2), round(c.point[1], 2), round(c.point[2], 2), round(2 * c.radius, 2))
            for c in caras if c.internal and _paralelo(c.axis, eje.axis)
        })
        donde = "; ".join(f"Ø{d:g} con el eje por ({x:g}, {y:g}, {z:g})" for x, y, z, d in agujeros[:6])
        problemas.append(
            f"«{p.name}» gira alrededor del eje {p.joint.axis} que pasa por su ORIGEN LOCAL, "
            f"pero la pieza dibujada no tiene ningún agujero ni saliente en ese eje. "
            f"Sus agujeros paralelos a ese eje están en: {donde or 'ninguno'}. "
            "El enunciado tiene que poner el agujero del pasador (o el eje) exactamente en el "
            "origen de la pieza y no contradecirse sobre dónde está el origen."
        )
    return problemas


def stop_problems(spec: MechanismSpec, layout, steps: dict[str, Path], freecadcmd: str,
                  max_gap_mm: float = 0.05) -> list[str]:
    """Cada tope declarado tiene que tocar en `at` y bloquear más allá."""
    problemas = []
    paso = spec.driver.step
    for tope in spec.stops:
        mas_alla = tope.at + (paso if tope.beyond == "above" else -paso)
        frames = {tope.at: layout.poses(tope.at), mas_alla: layout.poses(mas_alla)}
        huecos = {g["angle"]: g["gap_mm"] for g in pair_gaps(
            steps, layout.pins(), frames, [(tope.a, tope.b)], freecadcmd)}
        en, despues = huecos[tope.at], huecos[mas_alla]
        nombre = f"el tope entre «{tope.a}» y «{tope.b}» en t = {tope.at:g}"
        if en > max_gap_mm:
            problemas.append(f"{nombre} no llega a tocar: quedan {en:.2f} mm de hueco")
        elif en < 0:
            problemas.append(f"{nombre} ya se atraviesa ({-en:.1f} mm³ en común); "
                             "tienen que tocarse justo en ese valor, sin solaparse")
        if despues >= 0:
            problemas.append(
                f"{nombre} no bloquea: con t = {mas_alla:g} siguen sin tocarse "
                f"({despues:.2f} mm), así que el movimiento podría seguir")
    return problemas
