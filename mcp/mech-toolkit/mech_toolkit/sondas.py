"""Sondas: medir en la pieza construida lo que no es un agujero (F6.12 (techo)).

Corren dentro de `freecadcmd` sobre el STEP, y cada una devuelve lo medido
y si cumple. Miden geometría, nunca lo que el diseñador dice de ella: un
concepto que «aguanta 5 kg» no cuenta, la sección real de la pieza sí.

13-15 de las 42 exigencias del banco eran «sin medir» y contaban como no
aprobadas: con 62 % de nota (2026-11-04) el techo era 64 %.
"""

import math

import FreeCAD
import Part

from mech_toolkit.kit import convexa

V = FreeCAD.Vector


def _plano(cara) -> bool:
    return cara.Surface.TypeId == "Part::GeomPlane"


def _normal(cara, punto):
    u, v = cara.Surface.parameter(punto)
    return cara.normalAt(u, v)


def _cilindros_interiores(forma, dmin, dmax):
    """Caras cilíndricas de un agujero o alojamiento con diámetro en [dmin, dmax]."""
    caras = []
    for c in forma.Faces:
        s = c.Surface
        if s.TypeId != "Part::GeomCylinder" or not dmin <= 2 * s.Radius <= dmax:
            continue
        u0, u1, v0, v1 = c.ParameterRange
        p = c.valueAt((u0 + u1) / 2, (v0 + v1) / 2)
        sobre_eje = s.Center + s.Axis * (p - s.Center).dot(s.Axis)
        if c.normalAt((u0 + u1) / 2, (v0 + v1) / 2).dot(p - sobre_eje) < 0:
            caras.append(c)
    return caras


def _centro_de_cara(c):
    """Punto del eje a media altura de la cara cilíndrica."""
    s = c.Surface
    u0, u1, v0, v1 = c.ParameterRange
    p = c.valueAt((u0 + u1) / 2, (v0 + v1) / 2)
    return s.Center + s.Axis * (p - s.Center).dot(s.Axis), V(s.Axis).normalize()


# --- estética medible ---------------------------------------------------------------

def aristas_vivas(forma, max_fraccion=0.1, angulo_min_grados=60.0):
    """Aristas convexas entre dos caras planas que forman un ángulo de al
    menos `angulo_min_grados`: una esquina de 90° sin redondear ni
    achaflanar. Un chaflán de 45° deja dos aristas de 45°, que no cuentan.
    Los bordes de agujero (plano-cilindro) tampoco: no son aristas exteriores."""
    viva = total = 0.0
    for e in forma.Edges:
        caras = forma.ancestorsOfType(e, Part.Face)
        if len(caras) != 2 or not all(_plano(c) for c in caras):
            continue
        p = e.valueAt((e.FirstParameter + e.LastParameter) / 2)
        n1, n2 = (_normal(c, p) for c in caras)
        total += e.Length
        angulo = math.degrees(math.acos(max(-1.0, min(1.0, n1.dot(n2)))))
        if angulo >= angulo_min_grados and convexa(forma, e):
            viva += e.Length
    fraccion = viva / total if total else 0.0
    return {"cumple": fraccion <= max_fraccion,
            "detalle": f"{100 * fraccion:.0f} % de las aristas entre caras planas quedan vivas "
                       f"({viva:.0f} de {total:.0f} mm); se admite hasta "
                       f"{100 * max_fraccion:.0f} %"}


# --- resistencia de la sección real -----------------------------------------------------

def resistencia(forma, carga_N, fijacion_diametro_mm, direccion, brazo, material,
                eje_diametro_mm=None, secciones=40):
    """Voladizo desde las fijaciones hasta la carga, comprobado en `secciones`
    cortes de la pieza REAL: σ = M·c/I con la inercia de cada corte.

    - Las fijaciones son los agujeros de `fijacion_diametro_mm`; su eje es la
      dirección del brazo, y el lado de la pared, el extremo de la pieza más
      cercano a ellos.
    - La carga va entre los agujeros (`entre_agujeros`, la gravedad en un
      gancho o una escuadra) o perpendicular al eje del alojamiento de
      `eje_diametro_mm` y al brazo (la correa de un motor).
    - Se aplica en la punta, o en el centro de ese alojamiento (`centro`).
    - Si el brazo va en z (vertical al imprimir), la tensión separa capas y
      vale la resistencia entre capas."""
    d = fijacion_diametro_mm
    fijaciones = _cilindros_interiores(forma, d - 0.1, d + 0.1)
    if not fijaciones:
        return {"cumple": False, "detalle": f"no hay agujeros de fijación de Ø{d:g}"}
    # Agujeros del mismo diámetro en dos direcciones (la escuadra de repisa:
    # a la pared y a la repisa). El apoyo es el grupo desde el que la pieza
    # se aleja más a lo largo de su eje: de ahí cuelga el voladizo.
    grupos = []
    for c in fijaciones:
        p, e = _centro_de_cara(c)
        for g_ in grupos:
            if abs(abs(g_[0][1].dot(e)) - 1) < 1e-3:
                g_.append((p, e))
                break
        else:
            grupos.append([(p, e)])

    def extension(grupo):
        eje = grupo[0][1]
        return max(v.Point.dot(eje) for v in forma.Vertexes) - min(
            v.Point.dot(eje) for v in forma.Vertexes)

    centros = max(grupos, key=extension)
    n = centros[0][1]
    alto = [(p - V(0, 0, 0)).dot(n) for p, _ in centros]
    vertices = [v.Point.dot(n) for v in forma.Vertexes]
    lo, hi = min(vertices), max(vertices)
    h = sum(alto) / len(alto)
    pared, sentido = (lo, 1.0) if abs(h - lo) <= abs(h - hi) else (hi, -1.0)
    n_brazo = n * sentido

    if direccion == "entre_agujeros":
        g = None
        for i, (a, _) in enumerate(centros):
            for b, _ in centros[i + 1:]:
                dif = b - a
                dif = dif - n * dif.dot(n)
                if dif.Length > 1.0:
                    g = V(dif).normalize()
                    break
            if g:
                break
        if g is None:
            return {"cumple": False, "detalle": "hace falta más de un agujero de fijación "
                                                 "para saber hacia dónde tira la carga"}
    else:
        ejes = _cilindros_interiores(forma, eje_diametro_mm - 0.2, eje_diametro_mm + 0.6)
        if not ejes:
            return {"cumple": False, "detalle": f"no hay alojamiento de Ø{eje_diametro_mm:g}"}
        g = n.cross(_centro_de_cara(ejes[0])[1])
        if g.Length < 1e-6:
            return {"cumple": False, "detalle": "el eje es paralelo a las fijaciones"}
        g = g.normalize()

    if brazo == "punta":
        largo = (hi - lo)
    else:
        ejes = _cilindros_interiores(forma, eje_diametro_mm - 0.2, eje_diametro_mm + 0.6)
        largo = abs(_centro_de_cara(ejes[0])[0].dot(n) - pared)
    b = n.cross(g).normalize()
    capas = abs(n.z) > 0.7
    resistencia_MPa = material["z_MPa"] if capas else material["xy_MPa"]

    peor = None
    for k in range(1, secciones):
        t = largo * k / secciones
        cables = forma.slice(n, pared + sentido * t)
        if not cables:
            continue
        try:
            cara = Part.makeFace(cables, "Part::FaceMakerBullseye")
        except Exception:
            continue
        # Un corte que pasa por un agujero sale en varias caras (un compuesto):
        # se suman con Steiner respecto al centro de gravedad común.
        trozos = cara.Faces
        area = sum(f.Area for f in trozos)
        if area <= 0:
            continue
        cg = V(0, 0, 0)
        for f in trozos:
            cg = cg + f.CenterOfMass * (f.Area / area)
        bv = [b.x, b.y, b.z]
        inercia = 0.0
        for f in trozos:
            m = f.MatrixOfInertia
            J = [[m.A11, m.A12, m.A13], [m.A21, m.A22, m.A23], [m.A31, m.A32, m.A33]]
            inercia += sum(bv[i] * J[i][j] * bv[j] for i in range(3) for j in range(3))
            inercia += f.Area * ((f.CenterOfMass - cg).dot(g)) ** 2
        c = max(abs((p - cg).dot(g)) for w in cables for p in w.discretize(60))
        if inercia <= 0 or c <= 0:
            continue
        sigma = carga_N * (largo - t) * c / inercia
        if peor is None or sigma > peor[0]:
            peor = (sigma, t)
    if peor is None:
        return {"cumple": False, "detalle": "no se pudo cortar la pieza a lo largo del brazo"}
    sigma, t = peor
    factor = resistencia_MPa / sigma if sigma > 0 else float("inf")
    exigido = material["factor_seguridad"]
    return {"cumple": factor >= exigido,
            "detalle": f"factor {factor:.2f} (se exige {exigido:g}): σ = {sigma:.1f} MPa a "
                       f"{t:.0f} mm de la pared con {carga_N:g} N a {largo:.0f} mm, contra "
                       f"{resistencia_MPa:g} MPa ({'entre capas' if capas else 'en el plano de capa'})"}


# --- ventanas, pasos y ranuras -------------------------------------------------------------

_CRUCE = {"x": ("y", "z"), "y": ("x", "z"), "z": ("x", "y")}


def _rango(bb, eje):
    return getattr(bb, eje.upper() + "Min"), getattr(bb, eje.upper() + "Max")


def _bahias(cara, eje, en):
    """Los huecos de una sección: lo que le falta para llenar su rectángulo
    envolvente. Sirven los cerrados (un agujero) y los abiertos por UN solo
    lado (una ranura en U); uno abierto por dos lados es el rincón de una L y
    no sujeta nada. Fallo real (2026-11-04): la sonda solo miraba agujeros
    cerrados, y la ranura en U del soporte del MG996R, por la que el servo
    entra y atornilla sus orejetas a la placa, contaba como suspenso."""
    bb = cara.BoundBox
    (a, (a0, a1)), (b, (b0, b1)) = ((x, _rango(bb, x)) for x in _CRUCE[eje])

    def punto(va, vb):
        d = {eje: en, a: va, b: vb}
        return V(d["x"], d["y"], d["z"])

    rect = Part.Face(Part.makePolygon([punto(a0, b0), punto(a1, b0), punto(a1, b1),
                                       punto(a0, b1), punto(a0, b0)]))
    for bahia in rect.cut(cara).Faces:
        h = bahia.BoundBox
        lados = sum(abs(v - borde) < 1e-3 for x, bordes in ((a, (a0, a1)), (b, (b0, b1)))
                    for v, borde in zip(_rango(h, x), bordes))
        if lados <= 1:
            yield bahia


def ventana(forma, ancho_mm, alto_mm):
    """Una abertura pasante por la que cabe un rectángulo de ancho × alto
    (el cuerpo de un servo), en la dirección de x, y o z."""
    b = forma.BoundBox
    for eje, n in (("x", V(1, 0, 0)), ("y", V(0, 1, 0)), ("z", V(0, 0, 1))):
        lo, hi = _rango(b, eje)
        # Nueve cortes y no uno: en una escuadra en L el corte por la mitad
        # puede no pasar por la placa que lleva la ventana.
        huecos = []
        for k in range(1, 10):
            en = lo + (hi - lo) * k / 10
            try:
                cara = Part.makeFace(forma.slice(n, en), "Part::FaceMakerBullseye")
                huecos += list(_bahias(cara, eje, en))
            except Exception:
                continue
        for w in huecos:
            c = w.BoundBox.Center
            for a, h in ((ancho_mm, alto_mm), (alto_mm, ancho_mm)):
                largo = hi - lo + 2
                if eje == "z":
                    caja = Part.makeBox(a, h, largo, V(c.x - a / 2, c.y - h / 2, lo - 1))
                elif eje == "y":
                    caja = Part.makeBox(a, largo, h, V(c.x - a / 2, lo - 1, c.z - h / 2))
                else:
                    caja = Part.makeBox(largo, a, h, V(lo - 1, c.y - a / 2, c.z - h / 2))
                # `distToShape` además del booleano: en el soporte del SG90 del
                # banco (2026-11-04) `common` devolvía vacío para una caja que
                # atravesaba la base maciza. Tocar no es pasar: hace falta holgura.
                if forma.common(caja).Volume < 1e-3 and forma.distToShape(caja)[0] > 1e-4:
                    return {"cumple": True,
                            "detalle": f"pasa un {ancho_mm:g} × {alto_mm:g} por la abertura en {eje}"}
    return {"cumple": False,
            "detalle": f"ninguna abertura pasante deja pasar {ancho_mm:g} × {alto_mm:g}"}


def coaxiales(forma, diametros_mm, tol_mm=0.1, tol_grados=0.5):
    """Los alojamientos de los rangos dados comparten eje."""
    ejes = []
    for dmin, dmax in diametros_mm:
        caras = _cilindros_interiores(forma, dmin, dmax)
        if not caras:
            return {"cumple": False, "detalle": f"no hay alojamiento de Ø{dmin:g}–{dmax:g}"}
        ejes.append(_centro_de_cara(caras[0]))
    (p0, e0), peor_d, peor_a = ejes[0], 0.0, 0.0
    for p, e in ejes[1:]:
        angulo = math.degrees(math.acos(min(1.0, abs(e0.dot(e)))))
        dif = p - p0
        distancia = (dif - e0 * dif.dot(e0)).Length
        peor_d, peor_a = max(peor_d, distancia), max(peor_a, angulo)
    return {"cumple": peor_d <= tol_mm and peor_a <= tol_grados,
            "detalle": f"ejes a {peor_d:.2f} mm y {peor_a:.2f}° entre sí "
                       f"(se admite {tol_mm:g} mm y {tol_grados:g}°)"}


def paso_libre(forma, diametro_mm, eje_de_mm):
    """Por el eje del alojamiento `eje_de_mm` pasa un cilindro de
    `diametro_mm` de punta a punta: el paso no se estrecha por debajo."""
    caras = _cilindros_interiores(forma, *eje_de_mm)
    if not caras:
        return {"cumple": False, "detalle": f"no hay alojamiento de Ø{eje_de_mm[0]:g}–{eje_de_mm[1]:g}"}
    centro, eje = _centro_de_cara(caras[0])
    largo = forma.BoundBox.DiagonalLength + 2
    sonda = Part.makeCylinder(diametro_mm / 2, 2 * largo, centro - eje * largo, eje)
    choca = forma.common(sonda).Volume
    return {"cumple": choca < 1e-3,
            "detalle": (f"pasa un Ø{diametro_mm:g} de punta a punta" if choca < 1e-3 else
                        f"un Ø{diametro_mm:g} no pasa: choca con {choca:.1f} mm³ de pieza")}


def _por_dentro(forma, tramo):
    """El punto medio del tramo está dentro del sólido, no en su piel."""
    medio = tramo.valueAt((tramo.FirstParameter + tramo.LastParameter) / 2)
    return forma.isInside(medio, 1e-4, False)


def pared_minima(forma, min_mm, por_cara=5, area_min_mm2=4.0):
    """El espesor más fino, con rayos hacia dentro desde puntos de cada cara
    plana: la primera porción de material que atraviesa el rayo es la pared."""
    fino = None
    for cara in forma.Faces:
        if not _plano(cara) or cara.Area < area_min_mm2:
            continue
        u0, u1, v0, v1 = cara.ParameterRange
        for i in range(por_cara):
            for j in range(por_cara):
                u = u0 + (u1 - u0) * (i + 0.5) / por_cara
                v = v0 + (v1 - v0) * (j + 0.5) / por_cara
                if not cara.isPartOfDomain(u, v):
                    continue
                p = cara.valueAt(u, v)
                n = cara.normalAt(u, v)
                rayo = Part.LineSegment(p + n * 0.01, p - n * 500).toShape()
                tramos = forma.common(rayo).Edges
                # Solo cuenta un tramo que va POR DENTRO del material. Los
                # puntos salen de la caja UV de la cara, y en una cara que
                # no es un rectángulo (el fondo hexagonal de una tuerca) caen
                # sobre su borde: ahí el rayo empieza rozando la pared
                # lateral del hueco y `common` devuelve ese roce de 0.01 mm.
                # La base del pan-tilt (2026-11-09) salió «con fallos» por
                # esa pared inexistente, y cinco intentos la persiguieron.
                cerca = [e for e in tramos
                         if min((x.Point - p).Length for x in e.Vertexes) < 0.05
                         and _por_dentro(forma, e)]
                if not cerca:
                    continue
                grosor = min(e.Length for e in cerca)
                if fino is None or grosor < fino[0]:
                    fino = (grosor, p)
    if fino is None:
        # «Sin medir», no «no cumple»: el adaptador de tubo del banco
        # `1106-1630`, todo de revolución, salió «no resuelto» por esto.
        return {"cumple": None, "detalle": "no se pudo medir ninguna pared"}
    g, p = fino
    return {"cumple": g >= min_mm - 1e-3,
            "detalle": f"la pared más fina mide {g:.2f} mm (en {p.x:.1f}, {p.y:.1f}, {p.z:.1f}); "
                       f"se exige {min_mm:g}"}


def ranura(forma, min_mm, max_mm, area_min_mm2=50.0):
    """Dos caras planas enfrentadas, con el hueco entre ellas vacío, separadas
    entre `min_mm` y `max_mm`: la boca de un clip que abraza un canto."""
    planas = [c for c in forma.Faces if _plano(c) and c.Area >= area_min_mm2]
    mejor = None
    for i, a in enumerate(planas):
        na = _normal(a, a.CenterOfMass)
        for b in planas[i + 1:]:
            nb = _normal(b, b.CenterOfMass)
            if na.dot(nb) > -0.999:
                continue
            dif = b.CenterOfMass - a.CenterOfMass
            d = dif.dot(na)
            if d <= 0 or nb.dot(a.CenterOfMass - b.CenterOfMass) <= 0:
                continue
            prisma = a.extrude(na * d)
            solape = prisma.common(b.extrude(nb * d)).Volume / d if d else 0
            if solape < area_min_mm2 or forma.common(prisma).Volume > 0.01 * prisma.Volume:
                continue
            if min_mm <= d < max_mm:
                return {"cumple": True, "detalle": f"boca de {d:.2f} mm entre caras enfrentadas"}
            mejor = d if mejor is None or abs(d - min_mm) < abs(mejor - min_mm) else mejor
    return {"cumple": False,
            "detalle": (f"la boca más parecida mide {mejor:.2f} mm; se pide de {min_mm:g} a "
                        f"{max_mm:g}" if mejor is not None else "no hay ninguna boca entre caras planas")}


def retencion(forma, diametro_min_mm, diametro_max_mm, vuelta_min_grados=200.0):
    """Un alojamiento que abraza más de media vuelta: lo que entra a presión
    por una abertura más estrecha que él y queda retenido."""
    caras = _cilindros_interiores(forma, diametro_min_mm, diametro_max_mm)
    if not caras:
        return {"cumple": False,
                "detalle": f"no hay alojamiento de Ø{diametro_min_mm:g}–{diametro_max_mm:g}"}
    # Las caras del mismo cilindro (mismo eje y radio) suman su vuelta.
    grupos = {}
    for c in caras:
        p, e = _centro_de_cara(c)
        clave = (round(c.Surface.Radius, 2), round(p.x, 1), round(p.y, 1), round(p.z, 1))
        u0, u1, _, _ = c.ParameterRange
        grupos[clave] = grupos.get(clave, 0.0) + math.degrees(u1 - u0)
    vuelta = max(grupos.values())
    return {"cumple": vuelta >= vuelta_min_grados,
            "detalle": f"el alojamiento abraza {min(vuelta, 360):.1f}°; hace falta "
                       f"{vuelta_min_grados:g}° para que retenga"}


# --- el componente cabe y entra (F6.11 (biblioteca)) -------------------------------------
#
# El soporte del HC-SR04 (2026-11-05) salió «resuelto» y el sensor no entraba:
# nada de lo que se medía era el sensor. Aquí se mete el componente de la
# ficha en la pieza. El programa solo dice DÓNDE va y POR DÓNDE entra; la
# forma sale de la ficha, así que no es preguntarle a la pieza qué cree ser.

TOL_CHOQUE_MM3 = 0.05
"""Apoyarse es tocar sin volumen común; algo más es meterse en la pieza."""
TOQUE_MAX_MM = 1.0
"""Un componente a más de esto de la pieza no está sujeto: está flotando."""


def _choca(forma, s) -> float:
    """El volumen común, sin fiarse de un booleano vacío: con el SG90
    (2026-11-04) `common` devolvió nada para una caja que atravesaba la base
    maciza. Si un punto de dentro del sólido cae dentro de la pieza, choca."""
    v = forma.common(s).Volume
    if v <= TOL_CHOQUE_MM3 and forma.isInside(_punto_dentro(s), 1e-6, False):
        return s.Volume
    return v


def _punto_dentro(s):
    """Un punto que es del sólido. El centro de masas no vale para un anillo
    (el 608): cae en el agujero, justo donde va el eje, y el eje «chocaba»."""
    s = s.Solids[0] if s.ShapeType == "Compound" and len(s.Solids) == 1 else s
    c = s.CenterOfMass
    if s.isInside(c, 1e-6, False):
        return c
    import FreeCAD
    b = s.BoundBox
    for i in range(1, 10):
        for j in range(1, 10):
            for k in range(1, 10):
                p = FreeCAD.Vector(b.XMin + b.XLength * i / 10, b.YMin + b.YLength * j / 10,
                                   b.ZMin + b.ZLength * k / 10)
                if s.isInside(p, 1e-6, False):
                    return p
    return c


def componente_cabe(forma, ficha, en, giros=()):
    """En su sitio, ningún cuerpo del componente se mete en la pieza, las
    zonas a despejar (cable, haz) quedan libres y el componente se apoya en
    la pieza."""
    from mech_toolkit.componentes import primitivas, solido

    fallos = []
    cuerpos = primitivas(ficha, en, giros, "cuerpos")
    tocadas = {}
    for de, que in (("cuerpos", "choca"), ("despejar", "tapa")):
        for p in primitivas(ficha, en, giros, de):
            v = _choca(forma, solido(p))
            if p.get("gira_con"):
                # Una cara de algo que puede girar: tocarla es apoyarse en
                # esa parte, y vale si es la única que se toca.
                if v > TOL_CHOQUE_MM3:
                    tocadas.setdefault(p["gira_con"], []).append(f"«{p['nombre']}» {v:.1f} mm³")
                continue
            if v > TOL_CHOQUE_MM3:
                porque = f" ({p['porque']})" if de == "despejar" and p["porque"] else ""
                fallos.append(f"«{p['nombre']}» {que} {v:.1f} mm³{porque}")
    if len(tocadas) > 1:
        fallos.append(
            f"la pieza apoya a la vez en {' y en '.join(sorted(tocadas))} "
            f"({'; '.join(t for v in tocadas.values() for t in v)}), y uno de los dos gira: "
            "roza. Apoya solo en el que va fijo y aparta la pieza de las caras del otro")
    if fallos:
        return {"cumple": False, "detalle": f"{ficha.get('nombre', ficha['id'])} no cabe: "
                                            + "; ".join(fallos)}
    cerca = min(forma.distToShape(solido(p))[0] for p in cuerpos)
    # Una pieza de la obra (F7.1 (fichar)) es un vecino: puede ir al lado sin
    # tocar, como la base bajo el soporte de giro del pan-tilt (2026-11-09),
    # que gira libre por encima. Atornillarse a ella se comprueba con sus
    # agujeros con nombre, no aquí.
    if cerca > TOQUE_MAX_MM and ficha.get("origen") != "impreso":
        return {"cumple": False,
                "detalle": f"{ficha.get('nombre', ficha['id'])} no toca la pieza: queda a "
                           f"{cerca:.1f} mm; donde está colocado no lo sujeta nada"}
    return {"cumple": True, "detalle": f"cabe, y se apoya a {cerca:.2f} mm de la pieza"}


PASO_ENTRA_MM = 0.5


def _entra_paso_a_paso(forma, p, d, largo):
    """La forma real de una pieza impresa, en posiciones cada
    `PASO_ENTRA_MM` desde su sitio hacia fuera por `d`, hasta que su caja ya
    no toca la de la pieza. Su barrido exacto no sale barato (ver `barrido`)."""
    from mech_toolkit.componentes import solido

    s = solido(p)
    caja = forma.BoundBox
    t = PASO_ENTRA_MM   # en t=0 está en su sitio: eso lo mide `componente_cabe`
    while t <= largo:
        movida = s.translated(FreeCAD.Vector(*d) * t)
        if not movida.BoundBox.intersect(caja):
            return None
        v = forma.common(movida).Volume
        if v > TOL_CHOQUE_MM3:
            return (f"«{p['nombre']}» choca con {v:.0f} mm³ de pieza cuando le faltan "
                    f"{t:.1f} mm para llegar a su sitio")
        t += PASO_ENTRA_MM
    return None


def componente_entra(forma, ficha, en, giros=(), entra_por="+z"):
    """El componente se puede llevar hasta su sitio viniendo desde
    `entra_por` («+z»: desde arriba, bajando), sin atravesar la pieza."""
    from mech_toolkit.componentes import EJES, barrido, primitivas

    d = EJES[entra_por]
    largo = forma.BoundBox.DiagonalLength + 2
    fallos = []
    for p in primitivas(ficha, en, giros, "cuerpos"):
        if p["tipo"] == "step":
            choque = _entra_paso_a_paso(forma, p, d, largo)
            if choque:
                fallos.append(choque)
            continue
        comun = forma.common(barrido(p, d, largo))
        if comun.Volume > TOL_CHOQUE_MM3:
            b = comun.BoundBox
            n = [abs(c) for c in d].index(1)
            eje = "xyz"[n]
            desde, hasta = ((b.XMin, b.XMax), (b.YMin, b.YMax), (b.ZMin, b.ZMax))[n]
            fallos.append(f"«{p['nombre']}» atraviesa {comun.Volume:.0f} mm³ de pieza "
                          f"(entre {eje}={desde:.1f} y {eje}={hasta:.1f})")
    if fallos:
        return {"cumple": False,
                "detalle": f"no se puede meter viniendo desde {entra_por}: " + "; ".join(fallos)}
    return {"cumple": True, "detalle": f"entra viniendo desde {entra_por} sin tocar nada"}


def acceso_tornillo(forma, nombre, entrada, eje, diametro_mm):
    """La cabeza del tornillo `nombre` (Ø`diametro_mm`) llega a la entrada
    del agujero viniendo de fuera por su eje: por ahí entra el tornillo y por
    ahí llega la llave."""
    e = FreeCAD.Vector(*eje)
    e.normalize()
    fuera = e * -1
    largo = forma.BoundBox.DiagonalLength + 2
    camino = Part.makeCylinder(diametro_mm / 2, largo, FreeCAD.Vector(*entrada), fuera)
    comun = forma.common(camino)
    if comun.Volume <= TOL_CHOQUE_MM3:
        return {"cumple": True, "detalle": f"la cabeza de «{nombre}» llega desde fuera"}
    cerca = comun.distToShape(Part.Vertex(FreeCAD.Vector(*entrada)))[0]
    return {"cumple": False,
            "detalle": f"la cabeza del tornillo «{nombre}» (Ø{diametro_mm:g}) no llega a su "
                       f"sitio: el camino desde fuera, por el eje del agujero, choca con "
                       f"{comun.Volume:.0f} mm³ de pieza a {cerca:.1f} mm de la entrada; ni el "
                       "tornillo entra ni la llave lo aprieta"}


def zona_libre(forma, nombre, punto, eje, radio_mm):
    """En el cilindro de `radio_mm` alrededor del eje que sale de `punto`
    hacia `eje` no hay nada de la pieza: es el sitio de lo que gira sobre la
    salida `nombre` del actuador que la pieza monta (F9.1 (barrido))."""
    e = FreeCAD.Vector(*eje)
    e.normalize()
    largo = forma.BoundBox.DiagonalLength + 2 * radio_mm + 2
    zona = Part.makeCylinder(radio_mm, largo, FreeCAD.Vector(*punto), e)
    comun = forma.common(zona)
    if comun.Volume <= TOL_CHOQUE_MM3:
        return {"cumple": True,
                "detalle": f"deja libres los {radio_mm:g} mm alrededor de «{nombre}»"}
    # Hasta dónde llega lo que estorba, medido desde el eje: con eso se sabe
    # cuánto hay que apartarlo.
    recta = Part.makeLine(FreeCAD.Vector(*punto), FreeCAD.Vector(*punto) + e * largo)
    cerca = comun.distToShape(recta)[0]
    return {"cumple": False,
            "detalle": f"la pieza mete {comun.Volume:.0f} mm³ en el sitio de lo que gira sobre "
                       f"«{nombre}»: en un cilindro de radio {radio_mm:g} mm alrededor de ese "
                       "eje, desde la cara por donde sale hacia fuera, no puede haber nada, y "
                       f"lo que estorba llega a {cerca:.1f} mm del eje"}


PASO_REJILLA_MM = 0.5
"""Cada cuánto se mira si un punto de la cara es de la pieza, al buscar
dónde cabe un rectángulo."""


def _cabe_en(caras, origen, u, v, lados) -> bool:
    """Si en la región que forman `caras` (del mismo plano, con sus agujeros
    tapados) cabe un rectángulo de `lados`, alineado con `u` y `v`."""
    rellenas = [Part.Face(c.OuterWire) for c in caras]
    puntos = [p.Point - origen for c in caras for p in c.OuterWire.Vertexes]
    us, vs = [q.dot(u) for q in puntos], [q.dot(v) for q in puntos]
    nu = int((max(us) - min(us)) / PASO_REJILLA_MM + 1e-6) + 1
    nv = int((max(vs) - min(vs)) / PASO_REJILLA_MM + 1e-6) + 1
    a, b = (int(round(x / PASO_REJILLA_MM)) for x in lados)
    if a >= nu or b >= nv:
        return False

    def dentro(i, j):
        punto = origen + u * (min(us) + i * PASO_REJILLA_MM) + v * (min(vs) + j * PASO_REJILLA_MM)
        return any(f.isInside(punto, 1e-3, True) for f in rellenas)

    # Suma acumulada: cuántos puntos de la rejilla son de la pieza en cada
    # esquina, para saber de una resta si una ventana entera lo es.
    suma = [[0] * (nv + 1) for _ in range(nu + 1)]
    for i in range(nu):
        for j in range(nv):
            suma[i + 1][j + 1] = suma[i][j + 1] + suma[i + 1][j] - suma[i][j] + dentro(i, j)
    todos = (a + 1) * (b + 1)
    return any(suma[i + a + 1][j + b + 1] - suma[i][j + b + 1] - suma[i + a + 1][j]
               + suma[i][j] == todos
               for i in range(nu - a) for j in range(nv - b))


def cara_que_se_orienta(forma, eje, cabe_mm, tolerancia_grados=20.0):
    """En una cara plana cuya normal es perpendicular a `eje` cabe un
    rectángulo de `cabe_mm`: lo que se monte ahí cambia de orientación
    cuando la pieza gira sobre ese eje (F9.14 (orienta)).

    - Las caras del mismo plano cuentan juntas: una unión de dos cuerpos
      deja la cara partida, y es la misma superficie.
    - Los agujeros de dentro no quitan sitio: lo montado los tapa. Lo que
      manda es el contorno.
    - El rectángulo se prueba alineado con el eje, de las dos maneras.

    Primero se midió el área, y no era lo que había que medir: la placa de
    32 × 22 de la corrida 1111-1342 tiene 704 mm², más que los 600 de una
    cámara de 25 × 24, y la cámara no cabe en el lado de 22."""
    import math

    e = FreeCAD.Vector(*eje)
    e.normalize()
    limite = math.sin(math.radians(tolerancia_grados))
    planos: dict[tuple, list] = {}
    for cara in forma.Faces:
        if cara.Surface.__class__.__name__ != "Plane":
            continue
        u0, u1, v0, v1 = cara.ParameterRange
        n = cara.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        d = n.dot(cara.CenterOfMass)
        clave = (round(n.x, 3), round(n.y, 3), round(n.z, 3), round(d, 2))
        planos.setdefault(clave, []).append(cara)
    pide = f"{cabe_mm[0]:g} × {cabe_mm[1]:g}"
    orientados = []   # (área, lados de su envolvente en el plano, caras, u, v)
    for (x, y, z, _), caras in planos.items():
        n = FreeCAD.Vector(x, y, z)
        if abs(n.dot(e)) > limite:
            continue
        u = e - n * e.dot(n)
        u.normalize()
        v = n.cross(u)
        puntos = [p.Point for c in caras for p in c.OuterWire.Vertexes]
        us, vs = [q.dot(u) for q in puntos], [q.dot(v) for q in puntos]
        orientados.append((sum(c.Area for c in caras), (max(us) - min(us), max(vs) - min(vs)),
                           caras, u, v))
    if not orientados:
        mayor = max((sum(c.Area for c in caras) for caras in planos.values()), default=0.0)
        return {"cumple": False,
                "detalle": f"ninguna cara plana cambia de orientación al girar: la mayor "
                           f"({mayor:.0f} mm²) mira a lo largo del eje y gira sobre sí misma. "
                           f"Hace falta una cara plana donde quepan {pide} mm, con la normal "
                           "perpendicular al eje"}
    orientados.sort(key=lambda o: -o[0])
    for _, (lu, lv), caras, u, v in orientados:
        origen = FreeCAD.Vector(0, 0, 0) + caras[0].CenterOfMass - u * caras[0].CenterOfMass.dot(u) \
            - v * caras[0].CenterOfMass.dot(v)
        if any(_cabe_en(caras, origen, u, v, lados)
               for lados in (cabe_mm, cabe_mm[::-1])):
            return {"cumple": True,
                    "detalle": f"en una cara plana de {lu:.0f} × {lv:.0f} mm que cambia de "
                               f"orientación al girar caben {pide} mm"}
    _, (lu, lv), _, _, _ = orientados[0]
    return {"cumple": False,
            "detalle": f"en la mayor cara plana que cambia de orientación al girar "
                       f"({lu:.0f} × {lv:.0f} mm) no cabe un rectángulo de {pide}"}


def carga_en_camino(forma, desde, hasta, gravedad, material, secciones=30):
    """La fuerza que aguanta una pieza que cuelga de `desde` (el eje de su
    servo) con la carga en `hasta` (donde se monta lo de fuera), hacia
    `gravedad` (F7.10 (estudio)). Como `resistencia`, σ = M·c/I en cortes
    de la pieza REAL, pero sin pedir agujeros de fijación: una pieza de un
    robot no se atornilla a una pared, la sostiene el cuerno del servo.

    Devuelve `N_max`, la fuerza en `hasta` con la que el corte peor llega a
    la resistencia entre el factor de seguridad."""
    a, b = V(*desde), V(*hasta)
    largo = (b - a).Length
    if largo < 1.0:
        return {"cumple": True, "N_max": None, "detalle": "la carga cae sobre el eje: no flexa"}
    n = (b - a).normalize()
    g = V(*gravedad)
    g = g - n * g.dot(n)                       # lo que flexa: la gravedad de través
    if g.Length < 1e-6:
        return {"cumple": True, "N_max": None, "detalle": "la carga tira a lo largo: no flexa"}
    g = g.normalize()
    b_eje = n.cross(g).normalize()
    capas = abs(n.z) > 0.7
    resistencia_MPa = material["z_MPa"] if capas else material["xy_MPa"]
    peor = None
    for k in range(1, secciones):
        t = largo * k / secciones
        cables = forma.slice(n, a.dot(n) + t)
        if not cables:
            continue
        try:
            cara = Part.makeFace(cables, "Part::FaceMakerBullseye")
        except Exception:
            continue
        trozos = cara.Faces
        area = sum(f.Area for f in trozos)
        if area <= 0:
            continue
        cg = V(0, 0, 0)
        for f in trozos:
            cg = cg + f.CenterOfMass * (f.Area / area)
        bv = [b_eje.x, b_eje.y, b_eje.z]
        inercia = 0.0
        for f in trozos:
            m = f.MatrixOfInertia
            J = [[m.A11, m.A12, m.A13], [m.A21, m.A22, m.A23], [m.A31, m.A32, m.A33]]
            inercia += sum(bv[i] * J[i][j] * bv[j] for i in range(3) for j in range(3))
            inercia += f.Area * ((f.CenterOfMass - cg).dot(g)) ** 2
        c = max(abs((p - cg).dot(g)) for w in cables for p in w.discretize(60))
        if inercia <= 0 or c <= 0:
            continue
        sigma_por_N = (largo - t) * c / inercia
        if peor is None or sigma_por_N > peor[0]:
            peor = (sigma_por_N, t)
    if peor is None:
        return {"cumple": None, "N_max": None, "detalle": "no se pudo cortar la pieza en ese tramo"}
    sigma_por_N, t = peor
    n_max = resistencia_MPa / material["factor_seguridad"] / sigma_por_N
    return {"cumple": True, "N_max": n_max, "t_mm": t,
            "detalle": f"{n_max:.1f} N en la punta: el corte peor, a {t:.0f} mm del eje, "
                       f"{'entre capas' if capas else 'en el plano de capa'} "
                       f"({resistencia_MPa:g} MPa, factor {material['factor_seguridad']:g})"}


SONDAS = {"aristas_vivas": aristas_vivas, "resistencia": resistencia, "ventana": ventana,
          "coaxiales": coaxiales, "paso_libre": paso_libre, "pared_minima": pared_minima,
          "ranura": ranura, "retencion": retencion, "componente_cabe": componente_cabe,
          "componente_entra": componente_entra, "acceso_tornillo": acceso_tornillo,
          "zona_libre": zona_libre, "cara_que_se_orienta": cara_que_se_orienta}


def medir(forma, especificaciones: list[dict], material: dict) -> list[dict]:
    resultados = []
    for spec in especificaciones:
        parametros = {k: v for k, v in spec.items() if k not in ("tipo", "porque")}
        if spec["tipo"] == "resistencia":
            parametros["material"] = material
        try:
            resultados.append(SONDAS[spec["tipo"]](forma, **parametros))
        except Exception as e:
            # Una sonda rota no tumba las demás, y no es un fallo de la pieza:
            # `cumple: None` sale como «sin medir», no como «no cumple».
            resultados.append({"cumple": None,
                               "detalle": f"la sonda falló: {type(e).__name__}: {e}"})
    return resultados
