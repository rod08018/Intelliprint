"""Las cuentas de una reductora cicloidal (F10.7 (cicloidal), ADR-021).

Sin FreeCAD: el perfil del disco, la relación y la comprobación de que el
disco no atraviesa los pernos al dar la vuelta la excéntrica.

Cómo funciona: en el eje del motor va una excéntrica, que lleva el centro
del disco dando vueltas a `excentricidad` del eje. El disco tiene lóbulos y
rueda por dentro de un anillo de pernos fijos; como tiene un lóbulo menos
que pernos hay, por cada vuelta de la excéntrica el disco gira un lóbulo
hacia atrás. Ese giro lento es la salida.

De dónde sale: «What is Cycloidal Drive? Designing, 3D Printing and
Testing» (howtomechatronics.com). Las ecuaciones del perfil, sus cuatro
parámetros —«N: Number of rollers», «Rr: Radius of the roller», «R: Radius
of the rollers PCD», «E: Eccentricity»—, que el disco tiene «one less
cycloidal lobe» que pernos el anillo, y que «the eccentricity value should
be smaller than half of the roller diameter».
"""

import math


def relacion(pernos: int) -> int:
    """Vueltas de la excéntrica por cada vuelta del disco: sus lóbulos."""
    return pernos - 1


def _comprobar(pernos: int, radio: float, radio_perno: float, excentricidad: float) -> None:
    if int(pernos) != pernos or pernos < 4:
        raise ValueError(f"una cicloidal tiene al menos 4 pernos, y enteros; no {pernos!r}")
    if not 0 < excentricidad < radio_perno:
        raise ValueError(
            f"la excentricidad ({excentricidad:g} mm) tiene que ser menor que el radio de un "
            f"perno ({radio_perno:g} mm)")
    if excentricidad * pernos >= radio:
        raise ValueError(
            f"con {pernos} pernos en un círculo de radio {radio:g} mm y {excentricidad:g} mm de "
            f"excentricidad el perfil del disco se cruza consigo mismo: la excentricidad por "
            f"el número de pernos ({excentricidad * pernos:g}) tiene que ser menor que el radio")


def perfil(pernos: int, radio: float, radio_perno: float, excentricidad: float,
           holgura: float = 0.0, puntos: int = 720) -> list[tuple[float, float]]:
    """El contorno del disco, `puntos` puntos (x, y) en su propio marco, con
    su centro en el origen. `radio` es el del círculo en el que van los
    centros de los pernos. Con `holgura`, el disco se encoge eso por todo
    su contorno: es lo mismo que dibujarlo para unos pernos más gruesos."""
    _comprobar(pernos, radio, radio_perno, excentricidad)
    n, r, rr, e = pernos, radio, radio_perno + holgura, excentricidad
    salida = []
    for k in range(puntos):
        t = 2 * math.pi * k / puntos
        psi = math.atan2(math.sin((1 - n) * t), (r / (e * n)) - math.cos((1 - n) * t))
        salida.append((r * math.cos(t) - rr * math.cos(t + psi) - e * math.cos(n * t),
                       -r * math.sin(t) + rr * math.sin(t + psi) + e * math.sin(n * t)))
    return salida


def centro_del_disco(excentricidad: float, giro_excentrica: float) -> tuple[float, float]:
    """Dónde está el centro del disco con la excéntrica girada ese ángulo.
    Con ella a 0, el perfil de `perfil` encaja en los pernos con su centro
    a `excentricidad` hacia +x."""
    return (excentricidad * math.cos(giro_excentrica), excentricidad * math.sin(giro_excentrica))


def giro_del_disco(pernos: int, giro_excentrica: float) -> float:
    """Lo que ha girado el disco: al revés que la excéntrica, y un lóbulo
    por vuelta."""
    return -giro_excentrica / relacion(pernos)


def _a_un_segmento(p, a, b) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    largo2 = dx * dx + dy * dy
    t = 0.0 if largo2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / largo2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def holgura_con_los_pernos(pernos: int, radio: float, radio_perno: float, excentricidad: float,
                           giro_excentrica: float, holgura: float = 0.0,
                           giro_del_disco: float | None = None, puntos: int = 1440) -> float:
    """Lo que queda entre el disco y el perno que tiene más cerca, con la
    excéntrica en ese ángulo: 0 si lo roza, negativo si lo atraviesa. Es
    geometría, no la fórmula del perfil vuelta del revés: el contorno se
    coloca donde lo deja la excéntrica y se mide a cada perno. Los pernos
    van en los ángulos 2πk/N. `giro_del_disco`, para probar otra relación."""
    contorno = perfil(pernos, radio, radio_perno, excentricidad, holgura, puntos)
    giro = (globals()["giro_del_disco"](pernos, giro_excentrica)
            if giro_del_disco is None else giro_del_disco)
    cx, cy = centro_del_disco(excentricidad, giro_excentrica)
    c, s = math.cos(giro), math.sin(giro)
    puesto = [(cx + c * x - s * y, cy + s * x + c * y) for x, y in contorno]
    menor = math.inf
    for k in range(pernos):
        a = 2 * math.pi * k / pernos
        centro = (radio * math.cos(a), radio * math.sin(a))
        cerca = min(_a_un_segmento(centro, puesto[i - 1], puesto[i]) for i in range(len(puesto)))
        # Si el centro del perno ha quedado dentro del disco, lo atraviesa de lleno.
        dentro = math.hypot(centro[0] - cx, centro[1] - cy) < min(
            math.hypot(x - cx, y - cy) for x, y in puesto)
        menor = min(menor, (-cerca if dentro else cerca) - radio_perno)
    return menor
