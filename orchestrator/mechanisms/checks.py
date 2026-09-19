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
