"""Si una pieza se imprime sin soportes, medido en su forma y sin slicer.

Decidido por el usuario el 2026-11-13: «el slicer no tiene nada que ver con
el diseño; quiero tener el diseño bien antes de andar tocando PrusaSlicer».
El diseño no lamina desde el 2026-11-09, así que una pieza no sabía que pedía
soportes hasta que juzgaba el banco: la carcasa del encargo 16 (banco
1114-0023) gastó quince intentos sin que nadie se lo dijera.

Lo que una impresora no hace en el aire está en su perfil: voladizos de más
de `overhang_max_deg` desde la vertical y puentes de más de `bridge_max_mm`.
Aquí se mira la malla de la pieza apoyada en cada una de sus seis caras:

- **vuela** un triángulo que mira hacia abajo más de lo que deja el ángulo y
  no está sobre la cama;
- los que se tocan forman una **zona**, y lo que cuenta de ella es a cuánto
  queda su punto más alejado de donde la **sostiene** material que viene de
  abajo: una pared, un pilar, la cama o la propia curva que se cierra;
- vale si no pasa de medio puente: un puente de 10 mm apoyado en sus dos
  lados, un alero de 5.

No sabe de refrigeración ni de materiales, no mira si la pieza se despega de
la cama y solo prueba las seis posturas derechas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

POSTURAS: dict[str, tuple[float, float, float]] = {
    "-z": (0, 0, -1), "+z": (0, 0, 1), "-x": (-1, 0, 0), "+x": (1, 0, 0),
    "-y": (0, -1, 0), "+y": (0, 1, 0),
}
"""La cara de la pieza que va a la cama, y hacia dónde cae entonces lo que no
se sostiene. «-z» es como se dibuja. Los nombres, los de `slicing.POSTURAS`."""

EN_LA_CAMA_MM = 0.05
AREA_MIN_MM2 = 1.0
"""Una zona más pequeña es el canto de un redondeo o ruido de la malla."""
MAX_PUNTOS = 6000
"""De una zona se miran como mucho estos puntos, repartidos: para saber a
cuánto queda el más alejado sobra, y una carcasa curva tiene cientos de miles."""
PASO_MM = 1.0
"""Cada cuánto se mira dentro de un triángulo grande: una cara plana son dos
triángulos, y sus esquinas pueden estar todas apoyadas con el centro al aire."""


@dataclass(frozen=True)
class Zona:
    area_mm2: float
    vuela_mm: float
    """A cuánto queda su punto más alejado de donde se sostiene; infinito si
    no la sostiene nada: empieza en el aire."""
    plana: bool
    """Un techo: mira recto hacia abajo. Si no, una cara inclinada."""
    caja: tuple[list[float], list[float]]
    """Dónde está, en el marco de la pieza tal como se dibuja."""


def _malla(stl: Path):
    """(vértices únicos, índices de cada triángulo), sin los degenerados."""
    import numpy as np

    from orchestrator.tornilleria import _triangulos
    stl = Path(stl)
    t = _triangulos(str(stl), stl.stat().st_mtime)
    v, idx = np.unique(np.round(t.reshape(-1, 3), 4), axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)
    distintos = (idx[:, 0] != idx[:, 1]) & (idx[:, 1] != idx[:, 2]) & (idx[:, 0] != idx[:, 2])
    return v, idx[distintos]


def _a_segmentos(p, a, b):
    """Distancia de cada punto de `p` (m, 3) al más cercano de los segmentos
    `a`–`b` (s, 3)."""
    import numpy as np
    ab = b - a
    largo2 = np.maximum((ab * ab).sum(1), 1e-12)
    salida = np.empty(len(p))
    # Por tandas: una carcasa curva tiene miles de puntos y miles de aristas
    # en el borde, y todos contra todos no cabe en memoria.
    tanda = max(1, 2_000_000 // max(1, len(a)))
    for i in range(0, len(p), tanda):
        q = p[i:i + tanda]
        t = np.clip(((q[:, None, :] - a[None]) * ab[None]).sum(2) / largo2[None], 0, 1)
        cerca = a[None] + t[..., None] * ab[None]
        salida[i:i + tanda] = np.sqrt(((q[:, None, :] - cerca) ** 2).sum(2)).min(1)
    return salida


def _puntos(tri, paso):
    """Puntos repartidos por un triángulo (3, 3), como mucho cada `paso`."""
    import numpy as np
    lado = max(np.linalg.norm(tri[i] - tri[(i + 1) % 3]) for i in range(3))
    k = int(min(60, max(1, math.ceil(lado / paso))))
    ij = [(i, j) for i in range(k + 1) for j in range(k + 1 - i)]
    w = np.array([(i / k, j / k, 1 - (i + j) / k) for i, j in ij])
    return w @ tri


def voladizos(stl: Path, postura: str, angulo_max_deg: float, puente_max_mm: float) -> list[Zona]:
    """Las zonas de la pieza que, apoyada en `postura`, no se pueden imprimir
    sin soportes; vacío si se puede."""
    import numpy as np

    g = np.array(POSTURAS[postura], dtype=float)
    v, idx = _malla(stl)
    p = v[idx]                                            # (n, 3, 3)
    normal = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    doble = np.linalg.norm(normal, axis=1)
    area = doble / 2
    normal = normal / np.maximum(doble, 1e-12)[:, None]
    baja = v @ g                                          # cuanto mayor, más abajo
    cama = baja.max()
    mira = normal @ g
    en_cama = (baja[idx] >= cama - EN_LA_CAMA_MM).all(1) & (mira > 0.99)
    vuela = (mira > math.cos(math.radians(angulo_max_deg)) + 1e-3) & ~en_cama & (area > 1e-9)
    if not vuela.any():
        return []

    # Quién comparte cada arista con quién.
    n = len(idx)
    aristas = np.sort(np.stack([idx[:, [0, 1]], idx[:, [1, 2]], idx[:, [2, 0]]], 1), 2)
    aristas = aristas.reshape(-1, 2)
    de = np.repeat(np.arange(n), 3)
    orden = np.lexsort((aristas[:, 1], aristas[:, 0]))
    aristas, de = aristas[orden], de[orden]
    igual = (aristas[1:] == aristas[:-1]).all(1)
    pares = np.stack([de[:-1][igual], de[1:][igual]], 1)   # triángulos vecinos
    comun = aristas[:-1][igual]

    # Las zonas: lo que vuela y se toca.
    padre = np.arange(n)

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for a, b in pares[vuela[pares[:, 0]] & vuela[pares[:, 1]]]:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[ra] = rb
    grupo = np.full(n, -1)
    for i in np.flatnonzero(vuela):
        grupo[i] = raiz(i)

    # El borde de cada zona, y si ahí la sostiene algo que viene de abajo.
    centro = p.mean(1)
    zonas = []
    borde = vuela[pares[:, 0]] != vuela[pares[:, 1]]
    dentro = np.where(vuela[pares[:, 0]], pares[:, 0], pares[:, 1])
    fuera = np.where(vuela[pares[:, 0]], pares[:, 1], pares[:, 0])
    for z in np.unique(grupo[grupo >= 0]):
        suyos = np.where(grupo == z)[0]
        total = float(area[suyos].sum())
        if total < AREA_MIN_MM2:
            continue
        m = borde & (grupo[dentro] == z)
        e0, e1 = v[comun[m, 0]], v[comun[m, 1]]
        t_in, t_out = dentro[m], fuera[m]
        bajo_arista = np.maximum(baja[comun[m, 0]], baja[comun[m, 1]])
        sobre_cama = np.minimum(baja[comun[m, 0]], baja[comun[m, 1]]) >= cama - EN_LA_CAMA_MM
        baja_mas = baja[idx[t_out]].max(1) > bajo_arista + 1e-3
        # Una esquina viva (convexa) no sostiene: es el final de lo que
        # vuela. Sí un rincón, o la misma superficie que sigue bajando.
        hacia = centro[t_in] - (e0 + e1) / 2
        hacia = hacia / np.maximum(np.linalg.norm(hacia, axis=1), 1e-12)[:, None]
        no_convexa = (normal[t_out] * hacia).sum(1) > -0.2
        sostiene = sobre_cama | (baja_mas & no_convexa)
        # En una malla fina cada triángulo ya es pequeño: bastan sus
        # esquinas. Solo los grandes (una cara plana) se miran por dentro.
        grandes = suyos[area[suyos] > PASO_MM ** 2]
        puntos = np.concatenate([p[suyos].reshape(-1, 3),
                                 *(_puntos(p[i], PASO_MM) for i in grandes[:2000])])
        if len(puntos) > MAX_PUNTOS:
            puntos = puntos[::len(puntos) // MAX_PUNTOS + 1]
        if sostiene.any():
            lejos = float(_a_segmentos(puntos, e0[sostiene], e1[sostiene]).max())
        else:
            lejos = math.inf
        if lejos <= puente_max_mm / 2 + 0.05:
            continue
        esquinas = p[suyos].reshape(-1, 3)
        zonas.append(Zona(
            area_mm2=round(total, 1), vuela_mm=round(lejos, 1) if lejos != math.inf else lejos,
            plana=bool((mira[suyos] * area[suyos]).sum() / total > 0.99),
            caja=([round(float(x), 2) for x in esquinas.min(0)],
                  [round(float(x), 2) for x in esquinas.max(0)])))
    return sorted(zonas, key=lambda z: -z.area_mm2)


def como_imprimir(stl: Path, angulo_max_deg: float,
                  puente_max_mm: float) -> tuple[str | None, dict[str, list[Zona]]]:
    """(la primera postura en la que nada vuela, o None; las zonas de cada
    postura). Como se dibuja va primero."""
    zonas = {q: voladizos(stl, q, angulo_max_deg, puente_max_mm) for q in POSTURAS}
    return next((q for q in POSTURAS if not zonas[q]), None), zonas


def zona_en_palabras(z: Zona) -> str:
    que = "un techo plano" if z.plana else "una cara inclinada"
    lo, hi = z.caja
    donde = (f"x de {lo[0]:g} a {hi[0]:g}, y de {lo[1]:g} a {hi[1]:g}, "
             f"z de {lo[2]:g} a {hi[2]:g}")
    vuelo = ("no la sostiene nada: empieza en el aire" if z.vuela_mm == math.inf
             else f"vuela {z.vuela_mm:g} mm desde donde se apoya")
    return f"{que} de {z.area_mm2:.0f} mm² ({donde}) que {vuelo}"


def defecto_de_soportes(stl: Path, perfil: dict) -> list[str]:
    """Qué decirle a la pieza si no hay postura en la que se imprima sin
    soportes: sobre qué cara le falta menos y qué zonas vuelan ahí."""
    angulo, puente = perfil.get("overhang_max_deg"), perfil.get("bridge_max_mm")
    if not angulo or not puente:
        return []
    postura, zonas = como_imprimir(stl, angulo, puente)
    if postura is not None:
        return []
    mejor = min(zonas, key=lambda q: sum(z.area_mm2 for z in zonas[q]))
    lista = "; ".join(zona_en_palabras(z) for z in zonas[mejor][:4])
    mas = f"; y {len(zonas[mejor]) - 4} más" if len(zonas[mejor]) > 4 else ""
    return [
        f"sin soportes: no hay cara sobre la que esta pieza se imprima sin soportes (la "
        f"impresora hace voladizos de hasta {angulo:g}° desde la vertical y puentes de hasta "
        f"{puente:g} mm). Apoyada en su cara {mejor}, que es como menos le falta, queda en el "
        f"aire: {lista}{mas}. Las coordenadas son las de tu programa. Para quitar una zona: "
        f"ciérrala con un chaflán o un arco de {angulo:g}°, haz que nazca desde la cama en esa "
        f"postura, acórtala a menos de {puente / 2:g} mm de vuelo, o ábrela del todo. Y piensa "
        "primero qué cara va a la cama"]
