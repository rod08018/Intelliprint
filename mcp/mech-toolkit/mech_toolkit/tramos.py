"""Partir una pieza en tramos que caben en la cama: F11.3 (tramos), ADR-022.

Una carcasa de 400 mm no cabe en una cama de 235. Se corta por planos
perpendiculares a un eje, y cada corte lleva su unión a media madera: el
tramo de antes del corte se queda con la parte de dentro de la pared a lo
largo de `lengueta` milímetros (la lengüeta), y el de después con la de
fuera (el labio), con la holgura del perfil entre las dos. Un tornillo que
cruce labio y lengüeta las cierra; lo pone quien diseña, en la pieza entera,
y por eso sus agujeros caen enfrentados.

La pieza entera no cambia: se sigue midiendo y montando como una. Los
tramos son cómo se imprime.

Solo corre dentro de FreeCAD.
"""

import FreeCAD
import Part

from mech_toolkit.componentes import limpia

LABIO_MIN_MM = 0.8
"""Lo más fino que se deja de labio y de lengüeta: dos pasadas de una
boquilla de 0,4. Es un criterio de quien escribió esto, no una medida."""


class TramosError(ValueError):
    """La pieza no se puede partir como se pide. El mensaje vuelve al diseñador."""


EJES = {"x": FreeCAD.Vector(1, 0, 0), "y": FreeCAD.Vector(0, 1, 0),
        "z": FreeCAD.Vector(0, 0, 1)}


def _a_lo_largo(caja, eje: str) -> tuple[float, float]:
    return {"x": (caja.XMin, caja.XMax), "y": (caja.YMin, caja.YMax),
            "z": (caja.ZMin, caja.ZMax)}[eje]


def _rebanada(forma, eje: str, desde: float, hasta: float):
    """Lo que hay de `forma` entre dos planos perpendiculares a `eje`."""
    b = forma.BoundBox
    lo = [b.XMin - 1, b.YMin - 1, b.ZMin - 1]
    hi = [b.XMax + 1, b.YMax + 1, b.ZMax + 1]
    i = "xyz".index(eje)
    lo[i], hi[i] = desde, hasta
    caja = Part.makeBox(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], FreeCAD.Vector(*lo))
    return forma.common(caja)


def _seccion(forma, eje: str, en: float):
    """Las caras del corte de `forma` por el plano `eje = en`."""
    # Una loncha fina y su cara de abajo: `slice` da alambres, y hacer caras
    # con agujeros de alambres sueltos es adivinar cuál va dentro de cuál.
    loncha = _rebanada(forma, eje, en, en + 0.01)
    d = EJES[eje]
    caras = [c for c in loncha.Faces
             if abs(abs(c.normalAt(*c.Surface.parameter(c.CenterOfMass)).dot(d)) - 1) < 1e-6
             and abs(c.CenterOfMass.dot(d) - en) < 1e-4]
    if not caras:
        raise TramosError(f"el corte en {eje} = {en:g} no toca la pieza")
    return caras


def _envolvente(cara, eje: str):
    """El contorno convexo de una cara del corte, como cara."""
    d = EJES[eje]
    u, v = [EJES[e] for e in "xyz" if e != eje]
    en = cara.CenterOfMass.dot(d)
    puntos = sorted({(round(p.dot(u), 4), round(p.dot(v), 4))
                     for p in cara.OuterWire.discretize(Deflection=0.02)})

    def gira(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def media(ps):
        cadena = []
        for p in ps:
            while len(cadena) >= 2 and gira(cadena[-2], cadena[-1], p) <= 0:
                cadena.pop()
            cadena.append(p)
        return cadena[:-1]

    casco = media(puntos) + media(puntos[::-1])
    p3 = [u * a + v * b + d * en for a, b in casco]
    return Part.Face(Part.makePolygon([*p3, p3[0]]))


def _rellena(caras, eje: str):
    """Las caras del corte sin sus huecos: el contorno de fuera, macizo.

    Un anillo (una cáscara cerrada) se rellena por su borde de fuera. Una
    cáscara abierta por un lado se corta en una U, que no tiene «dentro»
    propio: se cierra con su contorno convexo, y así lo de dentro de la U
    queda dentro. Sin esto, a una carcasa abierta por debajo —casi todas—
    la lengüeta le saldría por el medio de la pared, o no le saldría."""
    llenas = []
    for c in caras:
        if len(c.Wires) > 1:
            llenas.append(Part.Face(c.OuterWire))
            continue
        casco = _envolvente(c, eje)
        # Un trozo macizo llena casi todo su contorno; una pared doblada, no.
        llenas.append(c if c.Area > 0.6 * casco.Area else casco)
    todo = llenas[0]
    for c in llenas[1:]:
        todo = todo.fuse(c)
    return limpia(todo) if len(llenas) > 1 else todo


def _encoger(cara, cuanto: float):
    """`cara` con su borde `cuanto` milímetros hacia dentro, o None si no queda nada."""
    try:
        dentro = cara.makeOffset2D(-cuanto)
    except Exception:  # noqa: BLE001 — OCC lanza lo que le parece cuando no queda cara
        return None
    return dentro if dentro.Area > 1e-6 else None


def _pared(caras) -> float:
    """El grueso de la pared en el corte: 2·área / perímetro. En un anillo de
    pared fina es su grueso; en un redondo macizo, su radio."""
    area = sum(c.Area for c in caras)
    borde = sum(w.Length for c in caras for w in c.Wires)
    return 2 * area / borde


def partir(forma, eje: str, cortes, lengueta: float, labio: float | None = None,
           holgura: float = 0.2) -> list:
    """Los tramos de `forma`, de menos a más a lo largo de `eje`, con su
    lengüeta y su labio en cada corte."""
    if eje not in EJES:
        raise TramosError(f"`eje` es «x», «y» o «z», no {eje!r}")
    d = EJES[eje]
    desde, hasta = _a_lo_largo(forma.BoundBox, eje)
    cortes = sorted(float(c) for c in cortes)
    if not cortes:
        raise TramosError("`en` necesita al menos un corte")
    lengueta = float(lengueta)
    for a, b in zip([desde, *cortes], [*cortes, hasta]):
        if b - a < lengueta + 1:
            raise TramosError(
                f"entre {eje} = {a:g} y {eje} = {b:g} hay {b - a:g} mm y la lengüeta mide "
                f"{lengueta:g}: no queda tramo. La pieza va de {desde:g} a {hasta:g}; "
                "separa los cortes o acorta la lengüeta")
    tramos = [_rebanada(forma, eje, a, b) for a, b in zip([desde, *cortes], [*cortes, hasta])]
    for i, c in enumerate(cortes):
        caras = _seccion(forma, eje, c)
        pared = _pared(caras)
        suyo = pared / 2 if labio is None else float(labio)
        if suyo < LABIO_MIN_MM or pared - suyo < LABIO_MIN_MM:
            raise TramosError(
                f"en el corte {eje} = {c:g} la pared mide {pared:.1f} mm: no da para un labio "
                f"y una lengüeta de al menos {LABIO_MIN_MM:g} cada uno. Engrosa la pared "
                f"ahí (hasta {2 * LABIO_MIN_MM + 2 * holgura:.1f} mm o más) o corta por "
                "donde sea más gruesa")
        dentro = _encoger(_rellena(caras, eje), suyo)
        perfil = None
        if dentro is not None:
            trozos = [c_.common(dentro) for c_ in caras]
            trozos = [f for t in trozos for f in t.Faces if f.Area > 1e-6]
            if trozos:
                perfil = Part.makeCompound(trozos)
        if perfil is None:
            raise TramosError(
                f"en el corte {eje} = {c:g} no queda sitio para la lengüeta con un labio de "
                f"{suyo:g} mm. Usa un labio más fino o corta por donde la pieza sea más ancha")
        # La lengüeta sale recta del corte. Si la pieza se estrecha a lo
        # largo de ella, atravesaría el labio del otro tramo.
        tras = _encoger(_rellena(_seccion(forma, eje, c + lengueta - 0.02), eje),
                        LABIO_MIN_MM)
        sobra = perfil.Area if tras is None else sum(
            f.cut(tras.translated(d * -(lengueta - 0.02))).Area for f in perfil.Faces)
        if sobra > 0.5:
            raise TramosError(
                f"junto al corte {eje} = {c:g} la pieza se estrecha: {lengueta:g} mm más "
                f"allá la lengüeta se saldría por la pared ({sobra:.0f} mm² de su sección "
                "quedan fuera). Corta por donde la pieza sea recta a lo largo de la "
                "lengüeta, o acórtala")
        # Solo donde la pieza tenía material: un agujero taladrado a través
        # de la unión tiene que seguir en la lengüeta, que es por donde pasa
        # el tornillo que la cierra. Y si la pieza se ensancha, la lengüeta
        # recta quedaría en el aire, dentro del hueco, sin tocar el labio.
        recta = perfil.extrude(d * lengueta)
        lengua = recta.common(_rebanada(forma, eje, c, c + lengueta))
        if lengua.Volume < 0.8 * recta.Volume:
            raise TramosError(
                f"junto al corte {eje} = {c:g} la pieza no es recta: de la lengüeta de "
                f"{lengueta:g} mm solo el {100 * lengua.Volume / recta.Volume:.0f} % cae en "
                "la pared. Corta por donde la sección no cambie a lo largo de la lengüeta, "
                "o acórtala")
        # El hueco del otro tramo: la lengüeta con la holgura a los lados y al fondo.
        hueco = Part.makeCompound([f.makeOffset2D(holgura) for f in perfil.Faces]).extrude(
            d * (lengueta + holgura))
        antes = limpia(tramos[i].fuse(lengua))
        despues = limpia(tramos[i + 1].cut(hueco))
        for que, t in (("lengüeta", antes), ("labio", despues)):
            if not t.isValid() or len(t.Solids) != 1:
                raise TramosError(
                    f"el corte {eje} = {c:g} deja el tramo del lado de la {que} en "
                    f"{len(t.Solids)} trozos: lo que cruza el corte tiene que ser una sola "
                    "pared cerrada. Corta por otro sitio")
        tramos[i], tramos[i + 1] = antes, despues
    return tramos


def tornillos_del_corte(tramos, i: int, eje: str, corte: float, lengueta: float,
                        agujeros) -> list[str]:
    """Los agujeros de `agujeros` (rasgos del kit) que cierran el corte `i`:
    entran por el labio y siguen por la lengüeta. Se mide en los tramos ya
    partidos: una broca fina por el eje del agujero no toca ninguno de los
    dos, y una gruesa toca los dos."""
    d = EJES[eje]
    valen = []
    for a in agujeros:
        e = FreeCAD.Vector(*a["eje"])
        p = FreeCAD.Vector(*a["entrada"])
        if abs(e.dot(d)) > 0.1 or not corte <= p.dot(d) <= corte + lengueta:
            continue
        r = a["diametro_mm"] / 2
        largo = a.get("profundidad_mm") or 2000.0
        fina = Part.makeCylinder(max(r - 0.2, 0.1), largo, p, e)
        gruesa = Part.makeCylinder(r + 0.6, largo, p, e)
        if all(t.common(fina).Volume < 0.01 and t.common(gruesa).Volume > 0.5
               for t in (tramos[i], tramos[i + 1])):
            valen.append(a["nombre"])
    return valen
