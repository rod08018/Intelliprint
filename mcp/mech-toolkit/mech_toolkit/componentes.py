"""Un componente comprado, colocado en la pieza (F6.11 (biblioteca)).

La ficha (`library/components/*.yaml`) da la forma del componente en su
propio marco; aquí se coloca en el de la pieza con `en` y cuartos de vuelta
(`giros`), y se construyen sus sólidos para medir si cabe y si entra.

Lo de colocar es Python puro: lo usa el orquestador sin FreeCAD. Lo que
construye sólidos importa FreeCAD dentro de cada función.

Por qué cuartos de vuelta y no cualquier ángulo: con 90° las cajas siguen
alineadas con los ejes y el barrido de entrada se calcula exacto, sin
booleanos encadenados que fallen en silencio (el del SG90, 2026-11-04).
"""

EJES = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0),
        "+z": (0, 0, 1), "-z": (0, 0, -1)}


def _girar(v, eje, grados):
    """Gira el vector `v` un múltiplo de 90° alrededor de x, y o z (regla de
    la mano derecha)."""
    if grados % 90:
        raise ValueError(f"los giros de un componente van de 90 en 90°, no {grados}°")
    x, y, z = v
    for _ in range((int(grados) // 90) % 4):
        if eje == "x":
            y, z = -z, y
        elif eje == "y":
            x, z = z, -x
        elif eje == "z":
            x, y = -y, x
        else:
            raise ValueError(f"eje de giro {eje!r}: es «x», «y» o «z»")
    return [x, y, z]


def colocar(p, en=(0, 0, 0), giros=()):
    """Un punto del marco del componente, en el marco de la pieza."""
    for eje, grados in giros:
        p = _girar(p, eje, grados)
    return [a + b for a, b in zip(p, en)]


def orientar(d, giros=()):
    """Una dirección del marco del componente, en el de la pieza."""
    d = list(EJES[d]) if isinstance(d, str) else list(d)
    for eje, grados in giros:
        d = _girar(d, eje, grados)
    return [round(c) for c in d]


def _ficha(ficha) -> dict:
    return ficha if isinstance(ficha, dict) else ficha.model_dump()


def primitivas(ficha, en=(0, 0, 0), giros=(), de="cuerpos") -> list[dict]:
    """Las cajas y cilindros de la ficha (`cuerpos` o `despejar`), ya
    colocados. Una caja sale como {min, max}; un cilindro como {base, eje,
    diametro, alto}."""
    salida = []
    for c in _ficha(ficha).get(de) or []:
        base = {"nombre": c["nombre"], "porque": c.get("porque") or ""}
        if c.get("caja"):
            x, y, z = c["caja"]
            o = c["en"]
            esquinas = [colocar([o[0] + i * x, o[1] + j * y, o[2] + k * z], en, giros)
                        for i in (0, 1) for j in (0, 1) for k in (0, 1)]
            salida.append({**base, "tipo": "caja",
                           "min": [min(p[n] for p in esquinas) for n in range(3)],
                           "max": [max(p[n] for p in esquinas) for n in range(3)]})
        else:
            cil = c["cilindro"]
            salida.append({**base, "tipo": "cilindro", "base": colocar(c["en"], en, giros),
                           "eje": orientar(cil["eje"], giros),
                           "diametro": float(cil["diametro"]), "alto": float(cil["alto"]),
                           "interior": float(cil["interior"]) if cil.get("interior") else None})
    return salida


# --- con FreeCAD ------------------------------------------------------------------------

def solido(p):
    import FreeCAD
    import Part

    V = FreeCAD.Vector
    if p["tipo"] == "caja":
        a, b = p["min"], p["max"]
        return Part.makeBox(b[0] - a[0], b[1] - a[1], b[2] - a[2], V(*a))
    cilindro = Part.makeCylinder(p["diametro"] / 2, p["alto"], V(*p["base"]), V(*p["eje"]))
    if p.get("interior"):
        # Un poco más largo por los dos lados: un corte a ras deja caras
        # coincidentes, y ese es el booleano que falla en silencio.
        b = [c - e * 0.1 for c, e in zip(p["base"], p["eje"])]
        cilindro = cilindro.cut(Part.makeCylinder(p["interior"] / 2, p["alto"] + 0.2,
                                                  V(*b), V(*p["eje"])))
    return cilindro


def barrido(p, d, largo):
    """El volumen que recorre la primitiva `p` al venir desde `largo` mm en
    la dirección `d` (un eje) hasta su sitio. Exacto para cajas y cilindros
    con los ejes alineados: es su envolvente convexa con la copia desplazada."""
    import FreeCAD
    import Part

    V = FreeCAD.Vector
    if p["tipo"] == "caja":
        a, b = list(p["min"]), list(p["max"])
        for n in range(3):
            if d[n] > 0:
                b[n] += largo
            elif d[n] < 0:
                a[n] -= largo
        return solido({"tipo": "caja", "min": a, "max": b})
    eje = p["eje"]
    paralelo = sum(x * y for x, y in zip(eje, d))
    if paralelo:
        base = p["base"] if paralelo > 0 else [b + c * largo for b, c in zip(p["base"], d)]
        return solido({**p, "base": base, "alto": p["alto"] + largo})
    # Perpendicular: el cilindro, su copia desplazada y la caja que los une.
    # Un anillo que entra de lado barre como si fuera macizo: el eje que lo
    # atraviesa no puede estar ahí mientras entra.
    p = {**p, "interior": None}
    c0 = solido(p)
    c1 = solido({**p, "base": [b + c * largo for b, c in zip(p["base"], d)]})
    tercero = [abs(a) for a in (eje[1] * d[2] - eje[2] * d[1], eje[2] * d[0] - eje[0] * d[2],
                                eje[0] * d[1] - eje[1] * d[0])]
    r = p["diametro"] / 2
    puntos = []
    for t in (0, p["alto"]):
        for s in (0, largo):
            for u in (-r, r):
                puntos.append([p["base"][n] + eje[n] * t + d[n] * s + tercero[n] * u
                               for n in range(3)])
    a = [min(q[n] for q in puntos) for n in range(3)]
    b = [max(q[n] for q in puntos) for n in range(3)]
    return c0.fuse(c1).fuse(Part.makeBox(b[0] - a[0], b[1] - a[1], b[2] - a[2], V(*a)))
