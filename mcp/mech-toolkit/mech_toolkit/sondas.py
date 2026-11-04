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
        fuera = n1 + n2
        if fuera.Length < 1e-9:
            continue
        convexa = not forma.isInside(p + fuera.normalize() * 0.05, 1e-6, True)
        if convexa and angulo >= angulo_min_grados:
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

def ventana(forma, ancho_mm, alto_mm):
    """Una abertura pasante por la que cabe un rectángulo de ancho × alto
    (el cuerpo de un servo), en la dirección de x, y o z."""
    b = forma.BoundBox
    for eje, n in (("x", V(1, 0, 0)), ("y", V(0, 1, 0)), ("z", V(0, 0, 1))):
        lo, hi = {"x": (b.XMin, b.XMax), "y": (b.YMin, b.YMax), "z": (b.ZMin, b.ZMax)}[eje]
        # Nueve cortes y no uno: en una escuadra en L el corte por la mitad
        # puede no pasar por la placa que lleva la ventana.
        huecos = []
        for k in range(1, 10):
            try:
                cara = Part.makeFace(forma.slice(n, lo + (hi - lo) * k / 10),
                                     "Part::FaceMakerBullseye")
            except Exception:
                continue
            huecos += [w for f in cara.Faces for w in f.Wires[1:]]
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
                if forma.common(caja).Volume < 1e-3:
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
                cerca = [e for e in tramos if min((x.Point - p).Length for x in e.Vertexes) < 0.05]
                if not cerca:
                    continue
                grosor = min(e.Length for e in cerca)
                if fino is None or grosor < fino[0]:
                    fino = (grosor, p)
    if fino is None:
        return {"cumple": False, "detalle": "no se pudo medir ninguna pared"}
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


SONDAS = {"aristas_vivas": aristas_vivas, "resistencia": resistencia, "ventana": ventana,
          "coaxiales": coaxiales, "paso_libre": paso_libre, "pared_minima": pared_minima,
          "ranura": ranura, "retencion": retencion}


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
