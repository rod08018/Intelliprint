"""Comprobaciones de coherencia entre la cinemática y las piezas dibujadas.

Fallo real que motivó este módulo (reto de la bisagra): el enunciado decía
a la vez "placa centrada en el origen" y "origen en el centro del nudillo".
El Part Designer siguió la primera frase; la pieza giraba alrededor de un
punto sin agujero y el pasador atravesaba la placa. El barrido lo ve como
un solape, pero no dice POR QUÉ. Esto sí.
"""

from pathlib import Path

from mech_toolkit.geometry import Frame, _distancia_a_recta, _paralelo
from orchestrator.mechanisms.expr import _nombres, _parse
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


def _apoyadas_a_cero(spec: MechanismSpec, min_gap_mm: float) -> list[str]:
    """Piezas colocadas JUSTO sobre la cara de otra: el barrido lo devuelve
    como «quedan a 0.00 mm», un renglón por par, y el agente acaba
    reescribiendo el mecanismo entero en vez de subirlas una décima."""
    if min_gap_mm <= 0:
        return []
    cajas = {p.name: (p.bbox_min, p.bbox_max) for p in spec.parts}
    pegadas = []
    for p in spec.parts:
        if p.name not in cajas or p.joint is None and p.parent is None:
            continue
        base_z = p.origin[2] + cajas[p.name][0][2]
        for otra in spec.parts:
            if otra is p or otra.parent is not None:
                continue
            techo = otra.origin[2] + cajas[otra.name][1][2]
            if 0 <= base_z - techo < min_gap_mm:
                pegadas.append((p.name, otra.name, techo + min_gap_mm - base_z))
                break
    if not pegadas:
        return []
    nombres = ", ".join(f"«{a}» sobre «{b}»" for a, b, _ in pegadas)
    subir = max(d for _, _, d in pegadas)
    return [
        f"estas piezas se apoyan sin holgura: {nombres}. Entre dos piezas que no se "
        f"tocan hacen falta {min_gap_mm:g} mm: súbelas {subir:.2f} mm, o decláralas en "
        "contacto si de verdad tienen que tocarse."
    ]


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


def mechanism_problems(spec: MechanismSpec, min_gap_mm: float = 0.0) -> list[str]:
    """Lo que el agente no puede dejar sin verificar, mirando su propia
    declaración. Sale de un fallo real: un trinquete aprobado que no
    trinqueteaba, porque nada obligaba a declarar contactos ni bloqueos.

    Dos reglas, las dos deterministas:

    1. Una articulación cuyo valor no depende del ciclo no es una
       articulación: es una pieza colocada y quieta.
    2. Una pieza que ni se mueve ni toca a ninguna otra no pinta nada: o es
       decoración, o le falta declarar su contacto.
    """
    problemas = []
    ciclo = {spec.driver.name}
    emparejadas = {n for r in spec.rules for n in (r.a, r.b)}
    emparejadas |= {n for t in spec.stops for n in (t.a, t.b)}
    emparejadas |= {n for b in spec.blocks for n in (b.body, b.against)}
    emparejadas |= {b.joint.rest_on.target for b in spec.bodies
                    if b.joint and b.joint.rest_on}

    # La bancada está quieta por definición: es el suelo del mecanismo. Se
    # exime la primera pieza fija declarada, que es como la escriben siempre.
    suelo = next((b.name for b in spec.parts if b.joint is None and b.parent is None), None)

    for b in spec.bodies:
        if b.name == suelo:
            continue
        movil = False
        if b.joint is not None and b.joint.rest_on is not None:
            movil = True
        elif b.joint is not None:
            usa_ciclo = bool(_nombres(_parse(b.joint.value), b.joint.value) & ciclo)
            if not usa_ciclo:
                problemas.append(
                    f"«{b.name}» declara una articulación {b.joint.type} con valor constante "
                    f"({b.joint.value}): así nunca se mueve. Si de verdad se mueve, su valor "
                    f"tiene que depender de {spec.driver.name}; si se mueve porque otra pieza "
                    "la empuja, usa `rest_on`; y si está quieta, quítale la articulación y "
                    "declara cómo se sujeta."
                )
            movil = usa_ciclo
        if b.stretch is not None:
            usados = _nombres(_parse(b.stretch), b.stretch)
            if usados:
                movil = True
            else:
                problemas.append(
                    f"«{b.name}» declara un estiramiento constante ({b.stretch}): una pieza "
                    "elástica que no se deforma no devuelve nada. Hazlo depender del ciclo "
                    f"o de lo que se mueve la pieza que la comprime (`q_<pieza>`)."
                )
        padre_movil = b.parent is not None
        if not movil and not padre_movil and b.name not in emparejadas:
            problemas.append(
                f"«{b.name}» no se mueve en todo el ciclo y no toca a ninguna otra pieza: "
                "no hay nada que verificar sobre ella. Declara con qué va unida o en "
                "contacto (`rules`), o qué la mueve."
            )
    # Un bloqueo sobre una pieza que se mueve por fórmula no demuestra nada:
    # la fórmula la mueve igual, la bloqueen o no. (El trinquete "resuelto"
    # declaraba las dos cosas a la vez.)
    for bl in spec.blocks:
        cuerpo = next((b for b in spec.bodies if b.name == bl.body), None)
        if cuerpo is not None and cuerpo.joint is not None and cuerpo.joint.value is not None:
            problemas.append(
                f"declaras que «{bl.against}» impide moverse a «{bl.body}», pero el "
                f"movimiento de «{bl.body}» lo impones tú con la fórmula "
                f"{cuerpo.joint.value!r}: esa fórmula la mueve igual, la bloqueen o no. "
                "Si esa pieza se mueve porque otra la empuja, usa `rest_on` con "
                "`carry: true` y deja que la geometría decida cuánto avanza."
            )
    problemas += _apoyadas_a_cero(spec, min_gap_mm)
    return problemas
