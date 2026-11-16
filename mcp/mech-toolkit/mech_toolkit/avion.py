"""Las formas de un VTOL de ala volante (F13.3 (costillas), ADR-023).

El usuario pidió un VTOL «como el TerraHawk pero mejorado» y, al ver la
primera versión (2026-11-16: cola en H sobre vigas largas, 8,7 kg), «quiero
que lo nuestro sea ligero» y «más parecido a un avión moderno eficiente».
Como con el brazo (ADR-023), la forma la pone el código y el diseño son
números: dónde están las secciones del ala, el fuselaje, los largueros, las
vigas de los rotores. De aquí sale cada pieza imprimible.

La familia: un ala volante con flecha (perfil autoestable), un fuselaje
fundido con el centro del ala, las puntas levantadas, dos vigas de carbono
bajo el ala con un rotor de sustentación delante y otro detrás, la hélice de
empuje en la cola del fuselaje, y bajo cada viga una deriva atrás y una pata
delante (son el tren de aterrizaje).

Cada pieza cabe en la cama y está pensada para imprimirse sin soportes:

- el ala se imprime de pie sobre la cara de su raíz: la flecha y la punta
  levantada no pasan de 45°;
- el cuerpo central se corta en celdas que se imprimen de pie sobre un corte;
  su hueco acaba en punta por los dos lados (un hueco que acaba en una cara
  plana es un techo);
- las ventanas de la panza son rombos, y el agujero de cada larguero lleva puntas
  a 45° donde cruza el hueco del fuselaje;
- las derivas y las patas se imprimen boca abajo, sobre la cara plana del pie
  que abraza la viga, y su agujero lleva tejado.

Las piezas se pegan: los largueros de carbono las alinean (Ø10 al 25 % de la
cuerda y Ø6 al 60 %), como en los aviones de LW-PLA de Flightory.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

CAMA = (235.0, 235.0, 250.0)
"""La de la impresora del usuario (AnkerMake M5), en mm."""
TRAMO_MAX = 160.0
"""Lo que mide a lo largo de la envergadura un tramo de ala, de pie en la cama.
Con la flecha, la huella de un tramo es su cuerda más lo que avanza el borde
de salida: con 200 mm, el primero medía 296 × 33 y entraba en diagonal con
2,4 mm de sobra (test del 2026-11-16); con 160, con 12."""
CELDA_FUSELAJE = 200.0
CELDA_RAIZ = 230.0
PARED = 2.5
"""La del fuselaje, que lleva dentro la batería y la carga."""
HOLGURA_BISAGRA = 0.5
"""Media ranura a cada lado de la línea de bisagra: 1 mm entre ala y elevón."""
HOLGURA_TUBO = 0.3
"""Lo que se le añade al diámetro de un tubo de carbono para que entre."""
SOLAPE_LARGUEROS = 20.0
"""Los largueros de los dos lados se cruzan en el centro: si acababan los dos
justo en y = 0, cara contra cara, la resta de FreeCAD dejaba el cuerpo central
en tres trozos (prueba a mano del 2026-11-16)."""
MEDIO_LARGO_GONDOLA = 40.0
LARGO_PIE = 150.0
"""El de la deriva y el de la pata, a lo largo de la viga."""

_PERFILES: dict | None = None


def _error(texto):
    from mech_toolkit.kit import KitError
    return KitError(texto)


def _perfil(nombre):
    global _PERFILES
    if _PERFILES is None:
        _PERFILES = json.loads((Path(__file__).parent / "perfiles_alares.json").read_text(
            encoding="utf-8"))
    if nombre not in _PERFILES or nombre.startswith("_"):
        raise _error(f"perfil {nombre!r} desconocido: hay "
                     f"{', '.join(k for k in _PERFILES if not k.startswith('_'))}")
    return _PERFILES[nombre]


def _caras(puntos):
    """(cara de arriba, cara de abajo), cada una del borde de ataque al de
    salida. Los puntos van del borde de salida por arriba al de ataque y
    vuelven por abajo."""
    i = min(range(len(puntos)), key=lambda k: puntos[k][0])
    return list(reversed(puntos[:i + 1])), puntos[i:]


def _en(cara, f):
    for (u0, v0), (u1, v1) in zip(cara, cara[1:]):
        if u0 <= f <= u1 and u1 > u0:
            return v0 + (v1 - v0) * (f - u0) / (u1 - u0)
    return cara[-1][1]


def _comba(nombre, f):
    arriba, abajo = _caras(_perfil(nombre))
    return (_en(arriba, f) + _en(abajo, f)) / 2


def _grueso(nombre, f):
    arriba, abajo = _caras(_perfil(nombre))
    return _en(arriba, f) - _en(abajo, f)


def _girado(u, v, x, z, c, torsion):
    """El punto (u, v) del perfil, en fracciones de cuerda, puesto en su sitio:
    girado `torsion` grados (positivo, morro arriba) sobre el 25 % de la cuerda."""
    s, k = math.sin(math.radians(torsion)), math.cos(math.radians(torsion))
    dx, dz = (u - 0.25) * c, v * c
    return (x + 0.25 * c + dx * k + dz * s, z - dx * s + dz * k)


# --- el diseño ---------------------------------------------------------------

def _estaciones(d):
    est = d["estaciones"]
    if len(est) < d["raiz"] + 2:
        raise _error("`estaciones` necesita el centro, la raíz del ala exterior y la punta")
    return est


def _panel_de(d, y):
    est = _estaciones(d)
    for i in range(d["raiz"], len(est) - 1):
        if est[i][0] - 1e-6 <= y <= est[i + 1][0] + 1e-6:
            return i
    raise _error(f"y = {y:g} cae fuera del ala exterior")


def _estacion(d, y, i=None):
    """(x, z, cuerda, torsión, perfil) del ala exterior en `y`, lineal dentro de
    su panel; con `i`, del panel `i` aunque `y` caiga fuera (para alargar)."""
    est = _estaciones(d)
    i = _panel_de(d, y) if i is None else i
    a, b = est[i], est[i + 1]
    t = (y - a[0]) / (b[0] - a[0])
    return [a[k] + (b[k] - a[k]) * t for k in range(1, 5)] + [a[5]]


def _levantado(d, i):
    a, b = _estaciones(d)[i], _estaciones(d)[i + 1]
    return (b[2] - a[2]) / (b[0] - a[0]) > math.tan(math.radians(20))


def _tramos_ala(d):
    """[(y0, y1, panel)] del ala exterior, cada uno de TRAMO_MAX como mucho."""
    est = _estaciones(d)
    tramos = []
    for i in range(d["raiz"], len(est) - 1):
        y0, y1 = est[i][0], est[i + 1][0]
        n = max(1, math.ceil((y1 - y0) / TRAMO_MAX - 1e-9))
        tramos += [(y0 + (y1 - y0) * k / n, y0 + (y1 - y0) * (k + 1) / n, i) for k in range(n)]
    return tramos


def _con_elevon(d, y0, y1, i):
    """Los tramos no se cortan donde empieza el elevón: lo lleva el tramo
    cuyo centro queda detrás de ese inicio."""
    return not _levantado(d, i) and (y0 + y1) / 2 >= d["elevon"][0]


def _celdas(d):
    """{id: (x0, x1, y0, y1)} de las celdas del cuerpo central (lado derecho y
    centro; las de la izquierda son su reflejo)."""
    fus = d["fuselaje"]
    est = _estaciones(d)
    y_medio = max(w for _, w, _ in fus) / 2 + 20
    x0, x1 = fus[0][0], fus[-1][0]
    n = math.ceil((x1 - x0) / CELDA_FUSELAJE - 1e-9)
    celdas = {f"centro-{k + 1}": (x0 + (x1 - x0) * k / n, x0 + (x1 - x0) * (k + 1) / n,
                                   -y_medio, y_medio) for k in range(n)}
    y_raiz = est[d["raiz"]][0]
    if y_raiz <= y_medio:
        return celdas

    def borde(y):
        j = max(k for k in range(d["raiz"]) if est[k][0] <= y)
        a, b = est[j], est[j + 1]
        t = (y - a[0]) / (b[0] - a[0])
        le = a[1] + (b[1] - a[1]) * t
        return le, le + a[3] + (b[3] - a[3]) * t

    ys = [y_medio + (y_raiz - y_medio) * k / 8 for k in range(9)]
    lo = min(borde(y)[0] for y in ys) - 15
    hi = max(borde(y)[1] for y in ys) + 15
    m = math.ceil((hi - lo) / CELDA_RAIZ - 1e-9)
    for k in range(m):
        celdas[f"raiz-d-{k + 1}"] = (lo + (hi - lo) * k / m, lo + (hi - lo) * (k + 1) / m,
                                     y_medio, y_raiz)
    return celdas


def piezas(d) -> list[tuple[str, str, str]]:
    """[(id, nombre, qué hace)] de todas las piezas impresas del avión."""
    lista = []
    for id_ in _celdas(d):
        if id_.startswith("centro"):
            lista.append((id_, f"Cuerpo central {id_.split('-')[1]}",
                          "fuselaje y centro del ala: la batería, la carga y la electrónica"))
    for lado, ala, el in (("d", "derecha", "derecho"), ("i", "izquierda", "izquierdo")):
        for id_ in _celdas(d):
            if id_.startswith("raiz"):
                k = id_.split("-")[2]
                lista.append((f"raiz-{lado}-{k}", f"Raíz del ala {ala} {k}",
                              "donde el ala se funde con el fuselaje"))
        for k, (y0, y1, i) in enumerate(_tramos_ala(d), 1):
            if _levantado(d, i):
                lista.append((f"ala-{lado}-{k}", f"Punta {el}", "la punta levantada del ala"))
                continue
            lista.append((f"ala-{lado}-{k}", f"Ala {ala}, tramo {k}",
                          f"de {y0:g} a {y1:g} mm del centro, con los dos largueros"))
            if _con_elevon(d, y0, y1, i):
                lista.append((f"elevon-{lado}-{k}", f"Elevón {el} {k}",
                              "alerón y timón de profundidad a la vez; lo mueve un servo"))
        lista += [(f"gondola-{lado}-delante", f"Góndola delantera {ala}",
                   "un motor de sustentación sobre la viga"),
                  (f"gondola-{lado}-detras", f"Góndola trasera {ala}",
                   "un motor de sustentación sobre la viga"),
                  (f"pilon-{lado}", f"Pilón {el}", "une la viga al ala"),
                  (f"pata-{lado}", f"Pata delantera {ala}", "bajo la viga: para posarse"),
                  (f"deriva-{lado}", f"Deriva {ala}",
                   "bajo la cola de la viga: estabilidad de guiñada y pata trasera")]
    return lista


# --- la geometría ---------------------------------------------------------------

def _seccion(kit, x, z, c, torsion, perfil):
    return kit.seccion([_girado(u, v, x, z, c, torsion) for u, v in _perfil(perfil)])


def _ala_entre(kit, d, y0, y1, i=None):
    a, b = _estacion(d, y0, i), _estacion(d, y1, i)
    return kit.transicion([(_seccion(kit, *a), y0), (_seccion(kit, *b), y1)], eje="y")


def _punto_larguero(d, y, f):
    i = d["raiz"]
    x, z, c, t, p = _estacion(d, y, i)
    return (*_girado(f, _comba(p, f), x, z, c, t), y)


def _larguero(kit, d, f, diametro, puntas=False):
    """El agujero de un larguero: recto, del centro (un poco más allá) a donde
    el perfil todavía le deja 1,2 mm de pared por cada lado, dentro del primer
    panel del ala exterior. Con `puntas`, en gota hacia +x y hacia -x: lo que se imprime
    de pie sobre un corte en x no deja techo en el agujero."""
    import FreeCAD
    import Part
    from mech_toolkit.kit import Cuerpo

    est = _estaciones(d)
    i = d["raiz"]
    perfil = est[i][5]
    y_fin = est[i + 1][0]
    for k in range(101):
        y = est[i][0] + (est[i + 1][0] - est[i][0]) * k / 100
        if _grueso(perfil, f) * _estacion(d, y)[2] < diametro + 2.4:
            y_fin = y
            break
    (xa, za, ya), (xb, zb, yb) = _punto_larguero(d, -SOLAPE_LARGUEROS, f), _punto_larguero(d, y_fin, f)
    a, b = FreeCAD.Vector(xa, ya, za), FreeCAD.Vector(xb, yb, zb)
    eje = b - a
    largo = eje.Length
    eje.normalize()
    r = (diametro + HOLGURA_TUBO) / 2
    forma = Part.makeCylinder(r, largo, a, eje)
    if puntas:
        # Una gota por cada lado: la punta a r·√2 y los lados tangentes al
        # círculo a 45°. Un rombo hasta (0, r) se queda dentro del círculo y
        # el techo seguía siendo cilindro a 19° de la horizontal: el cuerpo
        # central 3 pedía soportes (2026-11-16), como en el primer VTOL, cuyo
        # agujero no tenía punta. Hacia los lados no se ensancha: el tubo
        # sigue sujeto.
        u = FreeCAD.Vector(1, 0, 0) - eje * eje.x
        u.normalize()
        v = eje.cross(u)
        k, t = r * math.sqrt(2), r / math.sqrt(2)
        gota = [a + u * k, a + (u + v) * t, a + (v - u) * t, a - u * k, a - (u + v) * t,
                a + (u - v) * t]
        forma = forma.fuse(Part.Face(Part.makePolygon(gota + gota[:1])).extrude(eje * largo))
    return Cuerpo(forma, kit)


def _largueros(kit, d, puntas=False):
    hueco = None
    for f, diametro in d["largueros"]:
        t = _larguero(kit, d, f, diametro, puntas)
        hueco = t if hueco is None else hueco + t
    return hueco


def _fuselaje(kit, d):
    zf = d["z_fuselaje"]
    return kit.transicion([(kit.elipse(w, h), x) for x, w, h in d["fuselaje"]], eje="x",
                          en=(0, 0, zf))


def _hueco_fuselaje(kit, d):
    """Por dentro, a PARED de la piel, y acabado en punta a 45° por los dos
    lados: el morro romo de la primera prueba dejaba un techo."""
    fus = d["fuselaje"]
    dentro = [(x, w - 2 * PARED, h - 2 * PARED) for x, w, h in fus[1:-1]]
    # Las puntas, un 25 % más largas que a 45° justos: en el límite, la de la
    # cola daba voladizo (cuerpo central 5, 2026-11-16).
    # Acaban en una elipse de 6: con 16, el final era un techo plano de 16 mm
    # (cuerpo central 5).
    x1, w1, h1 = dentro[0]
    xf = max(x1 - 1.25 * (min(w1, h1) / 2 - 3), fus[0][0] + PARED + 5)
    xn, wn, hn = dentro[-1]
    xb = min(xn + 1.25 * (min(wn, hn) / 2 - 3), fus[-1][0] - PARED - 25)
    secs = [(xf, 6, 6)] + dentro + [(xb, 6, 6)]
    # En tramos rectos: suave, la transición se pasaba de la piel junto a la
    # cola y dejaba dos astillas sueltas (el cuerpo central 5 salía en tres
    # sólidos, 2026-11-16). Recta, además, la punta tiene la pendiente que se
    # le calcula.
    return kit.transicion([(kit.elipse(w, h), x) for x, w, h in secs], eje="x",
                          en=(0, 0, d["z_fuselaje"]), recta=True)


def _rombo(kit, d, x, largo, ancho):
    fus = d["fuselaje"]
    abajo = d["z_fuselaje"] - max(h for _, _, h in fus) / 2
    return kit.extruir([(x - largo / 2, 0), (x, ancho / 2), (x + largo / 2, 0), (x, -ancho / 2)],
                       PARED + 30, plano="xy", desde=abajo - 15)


def _cuerpo_central(kit, d):
    est = _estaciones(d)
    centro = kit.transicion([(_seccion(kit, e[1], e[2], e[3], e[4], e[5]), e[0])
                             for e in est[:d["raiz"] + 1]], eje="y")
    cuerpo = _fuselaje(kit, d) + centro.espejo("xz")
    cuerpo = cuerpo - _hueco_fuselaje(kit, d)
    largueros = _largueros(kit, d, puntas=True)
    cuerpo = cuerpo - largueros - largueros.espejo("xz", conservar=False)
    for x, largo, ancho in d.get("ventanas", []):
        cuerpo = cuerpo - _rombo(kit, d, x, largo, ancho)
    # El motor de empuje en la cola: cuatro M3 en un círculo de 19 (motores de
    # la clase 28xx) y el paso del eje, que acaba en cono: con fondo plano era
    # un techo al imprimir de pie (prueba del 2026-11-16).
    xe, zf = d["empuje"]["x"], d["z_fuselaje"]
    cuerpo = cuerpo - kit.cono(10, 0, 6, en=(xe + 0.5, 0, zf), eje="-x")
    for k in range(4):
        a = math.radians(45 + 90 * k)
        cuerpo = cuerpo - kit.cilindro(2.8, 10, en=(xe - 9.5, 9.5 * math.cos(a),
                                                    zf + 9.5 * math.sin(a)), eje="x")
    return cuerpo


def _lado(cuerpo, lado):
    return cuerpo if lado == "d" else cuerpo.espejo("xz", conservar=False)


def _bisagra(kit, d, y0, y1, margen):
    f = d["elevon"][1]
    a, b = _estacion(d, y0), _estacion(d, y1)
    xa, xb = a[0] + f * a[2] + margen, b[0] + f * b[2] + margen
    # Se alarga 1 mm por cada lado para cortar de lado a lado, siguiendo la
    # pendiente: alargada en recta, la bisagra quedaba 0,36 mm atrás en la
    # raíz del elevón (test del 2026-11-16).
    pendiente = (xb - xa) / (y1 - y0)
    xa, xb, y0, y1 = xa - pendiente, xb + pendiente, y0 - 1, y1 + 1
    return kit.extruir([(xa, y0), (xa + 400, y0), (xb + 400, y1), (xb, y1)], 600,
                       plano="xy", desde=-300)


def _tramo(kit, d, k):
    y0, y1, i = _tramos_ala(d)[k - 1]
    return y0, y1, i, _ala_entre(kit, d, y0, y1, i)


def _z_viga(d):
    """El centro de la viga: bajo la cara de abajo del ala donde pasa la viga,
    con sitio para el pilón."""
    y = d["rotores"]["y"]
    x, z, c, t, p = _estacion(d, y)
    _, abajo = _caras(_perfil(p))
    bajo = min(_girado(u, v, x, z, c, t)[1] for u, v in abajo if 0.1 <= u <= 0.9)
    return bajo - d["rotores"]["viga"] / 2 - 10


def _gondola(kit, d, x):
    """El soporte de un motor de sustentación: abraza la viga y deja arriba una
    cara plana con cuatro M3 en un círculo de 25 (compruébalo con el motor que
    compres) y el paso del eje."""
    ro = d["rotores"]
    y, zv, dv = ro["y"], _z_viga(d), ro["viga"]
    arriba = zv + dv / 2 + 12
    abajo = zv - dv / 2 - 5
    medio = kit.rectangulo(34, arriba - abajo + 8, 5)
    punta = kit.rectangulo(dv + 8, dv + 8, (dv + 8) / 2 - 2)
    L = MEDIO_LARGO_GONDOLA
    g = kit.transicion([(punta, x - L), (medio, x - L / 2), (medio, x + L / 2), (punta, x + L)],
                       eje="x", recta=True)
    g = g.mover(dy=y, dz=(arriba + abajo) / 2 - 4) & kit.caja(2 * L + 10, 80, 120,
                                                              en=(x - L - 5, y - 40, arriba - 120))
    g = g - kit.cilindro(dv + HOLGURA_TUBO, 2 * L + 20, en=(x - L - 10, y, zv), eje="x")
    g = g - kit.cono(10, 0, 5, en=(x, y, arriba + 0.5), eje="-z")
    for k in range(4):
        a = math.radians(45 + 90 * k)
        g = g - kit.cilindro(2.8, 9, en=(x + 12.5 * math.cos(a), y + 12.5 * math.sin(a),
                                          arriba - 8.5))
    return g - kit.cilindro(3.3, 60, en=(x + L / 2 + 6, y - 30, zv), eje="y")   # pasador M3


def _pilon(kit, d):
    """Une la viga al ala: una placa que por arriba copia la cara de abajo del
    ala. Restarle el ala a un bloque dejaba trozos sueltos (2026-11-16)."""
    ro = d["rotores"]
    y, zv, dv = ro["y"], _z_viga(d), ro["viga"]
    x, z, c, t, p = _estacion(d, y)
    _, abajo = _caras(_perfil(p))
    cara = [_girado(u, v, x, z, c, t) for u, v in abajo if 0.12 <= u <= 0.88]
    contorno = [(cara[0][0], zv - 2), (cara[-1][0], zv - 2)] + list(reversed(cara))
    placa = kit.extruir(contorno, dv + 8, plano="xz", desde=y - (dv + 8) / 2)
    return placa - kit.cilindro(dv + HOLGURA_TUBO, 2 * c, en=(x - c / 2, y, zv), eje="x")


def _pie(kit, d, x0, cuerda, alto):
    """Una aleta bajo la viga (la deriva o la pata) con su pie: el pie abraza la
    viga y tiene arriba una cara plana, sobre la que se imprime boca abajo. El
    agujero de la viga lleva tejado hacia abajo, que al imprimir es arriba."""
    ro = d["rotores"]
    y, zv, dv = ro["y"], _z_viga(d), ro["viga"]
    c0, c1 = cuerda

    def sec(x, c):
        return kit.seccion([(x + u * c, y + v * c) for u, v in _perfil("naca0008")])
    aleta = kit.transicion([(sec(x0, c0), -(zv - dv / 2)), (sec(x0 + (c0 - c1), c1),
                                                            -(zv - alto))], eje="-z")
    pie = kit.transicion([(kit.rectangulo(c0, dv + 8, 4), zv - dv / 2 - 4),
                          (kit.rectangulo(c0, dv + 8, 4), zv + dv / 2 + 4)],
                         eje="z", en=(x0 + c0 / 2, y, 0))
    p = aleta + pie
    r = (dv + HOLGURA_TUBO) / 2
    p = p - kit.cilindro(2 * r, c0 + 2, en=(x0 - 1, y, zv), eje="x")
    k = r / math.sqrt(2)
    return p - kit.extruir([(y - k, zv - k), (y + k, zv - k), (y, zv - r * math.sqrt(2))],
                           c0 + 2, plano="yz", desde=x0 - 1)


def pieza(kit, d, id_):
    """La pieza `id_` de `piezas(d)`, en su sitio."""
    ids = [p[0] for p in piezas(d)]
    if id_ not in ids:
        raise _error(f"el avión no tiene la pieza {id_!r}: tiene {', '.join(ids)}")
    partes = id_.split("-")
    lado = partes[1] if len(partes) > 1 and partes[1] in ("d", "i") else "d"
    if partes[0] in ("centro", "raiz"):
        celdas = _celdas(d)
        x0, x1, y0, y1 = celdas[id_ if partes[0] == "centro" else f"raiz-d-{partes[2]}"]
        trozo = _cuerpo_central(kit, d) & kit.caja(x1 - x0, y1 - y0, 600, en=(x0, y0, -300))
        return trozo if partes[0] == "centro" else _lado(trozo, lado)
    if partes[0] in ("ala", "elevon"):
        y0, y1, i, ala = _tramo(kit, d, int(partes[2]))
        if partes[0] == "ala":
            ala = ala - _largueros(kit, d)
            if _con_elevon(d, y0, y1, i):
                ala = ala - _bisagra(kit, d, y0, y1, -HOLGURA_BISAGRA)
            return _lado(ala, lado)
        return _lado(ala & _bisagra(kit, d, y0, y1, HOLGURA_BISAGRA), lado)
    ro = d["rotores"]
    if partes[0] == "gondola":
        return _lado(_gondola(kit, d, ro["x"][0 if partes[2] == "delante" else 1]), lado)
    if partes[0] == "pilon":
        return _lado(_pilon(kit, d), lado)
    de = d["deriva"]
    if partes[0] == "deriva":
        return _lado(_pie(kit, d, de["x"], de["cuerda"], de["alto"]), lado)
    # La pata va justo detrás de la góndola delantera, con la cuerda de la
    # deriva más corta: la hélice va arriba y la pata abajo.
    return _lado(_pie(kit, d, ro["x"][0] + MEDIO_LARGO_GONDOLA + 3, [100, 70], de["alto"]), lado)
