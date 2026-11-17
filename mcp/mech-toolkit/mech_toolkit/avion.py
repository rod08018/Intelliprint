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
"""La del perfil de impresora del sistema (AnkerMake M5), en mm. Él imprime
el avión en una Prusa CORE One L+ (2026-11-16), de 300 × 300 × 330: lo que
cabe aquí cabe allí. Cambiar de impresora se hace en su página «Impresora»."""
TRAMO_MAX = 160.0
"""Lo que mide a lo largo de la envergadura un tramo de ala, de pie en la cama.
Con la flecha, la huella de un tramo es su cuerda más lo que avanza el borde
de salida: con 200 mm, el primero medía 296 × 33 y entraba en diagonal con
2,4 mm de sobra (test del 2026-11-16); con 160, con 12."""
CELDA_FUSELAJE = 200.0
CELDA_RAIZ = 230.0
PARED = 1.2
"""La piel del fuselaje, que es de PETG (él, el 2026-11-16: «las alas son de
lw pla el resto de petg»). Era de 2,5 mm y maciza el resto del cuerpo: las
39 piezas sumaban 9,7 litros, unos 6 kg, cuando el dimensionado contaba 0,94
(medido el 2026-11-16)."""
PIEL_ALA = 0.6
"""La piel del ala y los nervios: una pasada de LW-PLA, que es de lo que son
las alas (las raíces, los tramos y los elevones)."""
FUNDA = 1.2
"""La pared que abraza cada larguero de carbono dentro del hueco del ala."""
HUECO_MIN = 3.0
"""Por debajo de este grueso entre caras el ala es maciza: el morro y el
borde de salida. Un hueco que acaba en una cara plana de 3 mm es un puente
de 3 mm, que la impresora hace."""
NERVIO_GRADOS = 50.0
"""Los nervios de un tramo de ala, de la horizontal al imprimirlo de pie: su
cara de abajo queda a 40° de la vertical, que se imprime sin soportes. Un
nervio de costilla, paralelo a la raíz, sería un techo de toda la cuerda."""
CUERDA_ALMA = 0.72
"""El alma de atrás del ala (un tabique de raíz a punta): delante de la
bisagra de los elevones, al 75 %."""
PASO_COSTILLA = 50.0
"""Entre costillas de las raíces, que se imprimen de pie sobre un corte en x:
ahí una costilla (un plano y = cte) es una pared vertical."""
QUILLA_Y = 42.0
"""Las dos quillas bajo la bandeja de la batería, a cada lado de la carga
(80 de ancho): la bandeja apoya en ellas y la carga cuelga entre ellas."""
BANDEJA = 3.0
"""El grueso de la bandeja de la batería."""
TAPA_SERVO = 0.8
SOLAPE_TAPA = 3.0
"""Lo que la tapa de un servo pisa la piel alrededor del hueco."""
MARCO = 3.0
"""El refuerzo del borde de la boca de la panza, por dentro del fuselaje."""
LABIO = 1.2
ALTO_LABIO = 8.0
"""La pestaña de la panza que sube por dentro del marco: ahí van sus M3."""
HOLGURA_PANZA = 0.2
HOLGURA_BISAGRA = 0.5
"""Media ranura a cada lado de la línea de bisagra: 1 mm entre ala y elevón."""
HOLGURA_TUBO = 0.3
"""Lo que se le añade al diámetro de un tubo de carbono para que entre."""
SOLAPE_LARGUEROS = 20.0
"""Los largueros de los dos lados se cruzan en el centro: si acababan los dos
justo en y = 0, cara contra cara, la resta de FreeCAD dejaba el cuerpo central
en tres trozos (prueba a mano del 2026-11-16)."""
TUBO_COMPRADO = 1000.0
"""Lo que mide un tubo de carbono en Amazon (Ø16, Ø10 y Ø6: de 1000 mm), donde
él quiere comprarlo todo (2026-11-16). Cada larguero medía unos 1160 mm: se
corta antes de la punta, y el último tramo del ala va solo pegado."""
MEDIO_LARGO_GONDOLA = 40.0
VARILLA_ELEVON = 2.0
"""La varilla de carbono que une los trozos de un elevón: con Ø3 no le
quedaba pared en la punta, donde el elevón tiene 5 mm de grueso."""
CANAL_CABLES = 6.0
"""El canal de los cables de los servos, de la raíz al servo exterior."""
SALIDA_SERVO = 1.2
"""Cuánto más largo es el hueco del servo por cada mm de hondo, en cada
punta: el ala se imprime de pie y el fondo del hueco sería un techo; así es
una rampa a 50° de la horizontal."""
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


def _hacia_dentro(cara, d, arriba):
    """La cara (u, v), del borde de ataque al de salida, metida `d` (en
    cuerdas) hacia dentro del perfil por su normal. Se quedan solo los puntos
    que siguen avanzando en u: junto al morro la normal mira hacia atrás."""
    salida = []
    for k, (u, v) in enumerate(cara):
        a, b = cara[max(k - 1, 0)], cara[min(k + 1, len(cara) - 1)]
        tu, tv = b[0] - a[0], b[1] - a[1]
        n = math.hypot(tu, tv) or 1.0
        nu, nv = (tv / n, -tu / n) if arriba else (-tv / n, tu / n)
        p = (u + nu * d, v + nv * d)
        if not salida or p[0] > salida[-1][0] + 1e-9:
            salida.append(p)
    return salida


def contorno_hueco(perfil, cuerda, piel, desde=0.0, hasta=1.0, puntos=24, punta=0.0):
    """(u, v) del hueco de un perfil de `cuerda` mm con `piel` mm de pared:
    sus dos caras metidas hacia dentro, entre las fracciones de cuerda
    `desde` y `hasta`, y solo donde entre ellas quedan HUECO_MIN mm; cerrado
    por delante y por detrás con un tramo recto (un alma). Con `punta` (mm),
    por los dos lados se cierra en una V que acaba `punta` mm más allá, en
    medio de las dos caras. Siempre con 2·`puntos` puntos, para que la transición
    entre dos secciones los una uno a uno. None si no cabe."""
    arriba, abajo = _caras(_perfil(perfil))
    d = piel / cuerda
    sup, inf = _hacia_dentro(arriba, d, True), _hacia_dentro(abajo, d, False)
    lo = max(desde, sup[0][0], inf[0][0])
    hi = min(hasta, sup[-1][0], inf[-1][0])
    paso = (hi - lo) / 400
    validos = [lo + k * paso for k in range(401)
               if (_en(sup, lo + k * paso) - _en(inf, lo + k * paso)) * cuerda >= HUECO_MIN]
    if len(validos) < 2:
        return None
    # El tramo seguido más largo: delante del alma de atrás no hay huecos sueltos.
    tramos, inicio, antes = [], validos[0], validos[0]
    for u in validos[1:]:
        if u - antes > paso * 1.5:
            tramos.append((inicio, antes))
            inicio = u
        antes = u
    tramos.append((inicio, antes))
    a, b = max(tramos, key=lambda t: t[1] - t[0])
    if (b - a) * cuerda < HUECO_MIN:
        return None
    us = [a + (b - a) * k / (puntos - 1) for k in range(puntos)]
    if punta <= 0:
        return [(u, _en(sup, u)) for u in us] + [(u, _en(inf, u)) for u in reversed(us)]
    # El cuerpo central se imprime de pie sobre un corte en x: el alma de
    # atrás, recta y con la flecha del borde de salida, quedaba a 50° de la
    # vertical y volaba 12,9 mm (cuerpo central 4, 2026-11-16). En V queda a
    # unos 25°. La punta, donde las caras aún no se juntan.
    def en_punta(u_b, u_p):
        """La punta, hacia `u_p`, donde las caras aún no se juntan."""
        while abs(u_p - u_b) > 1e-6 and _en(sup, u_p) - _en(inf, u_p) <= 0.5 / cuerda:
            u_p = u_b + (u_p - u_b) / 2
        return u_p, (_en(sup, u_p) + _en(inf, u_p)) / 2

    # Y por delante igual: el alma de delante, con la flecha del borde de
    # ataque, era un techo apoyando la pieza en su corte de atrás.
    # Donde las caras se juntan antes de `punta` (junto al borde de ataque),
    # la V no cabe hacia fuera y salía casi recta: un alma de 2,2 mm que
    # con la flecha volaba 5,2 mm (cuerpo central 2, 2026-11-16). Entonces
    # la V va hacia dentro: la punta donde estaba el alma y las caras
    # empiezan `punta` mm más allá.
    p = punta / cuerda
    delante, detras = en_punta(a, max(a - p, lo)), en_punta(b, min(b + p, hi))
    if a - delante[0] < 0.9 * p and b - a > 3 * p:
        delante = (a, (_en(sup, a) + _en(inf, a)) / 2)
        a = a + p
    if detras[0] - b < 0.9 * p and b - a > 3 * p:
        detras = (b, (_en(sup, b) + _en(inf, b)) / 2)
        b = b - p
    us = [a + (b - a) * k / (puntos - 1) for k in range(puntos)]
    return ([delante] + [(u, _en(sup, u)) for u in us[1:-1]] + [detras]
            + [(u, _en(inf, u)) for u in reversed(us)])


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


def _elevon_de(d, k):
    """(nombre, tramos) del elevón que lleva el tramo `k`. Desde el 2026-11-16
    hay dos por lado, cada uno con su servo (él: «debe tener alerones,
    implica que debe tener 4 servos»): `elevones` dice qué tramos forman
    cada uno. Sin esa clave, un elevón por tramo, como antes."""
    grupos = d.get("elevones")
    if not grupos:
        return str(k), [k]
    nombres = ["interior", "exterior"] if len(grupos) == 2 else [str(j + 1) for j in range(len(grupos))]
    for nombre, tramos in zip(nombres, grupos):
        if k in tramos:
            return nombre, list(tramos)
    raise _error(f"el tramo {k} lleva elevón y no está en ningún grupo de `elevones` {grupos}")


def _servos(d):
    """Los servos del lado derecho: [{y, elevon, en, caja}] de `dentro`."""
    return [{"y": c["en"][1], "elevon": c["id"].split("-")[2], "en": c["en"], "caja": c["caja"]}
            for c in d.get("dentro", []) if c["id"].startswith("servo-d-")]


def equilibrio(d, sin=()) -> dict:
    """El centro de gravedad (mm) con lo que hay en `dentro`, quitando los ids
    de `sin`, y su margen estático: lo que queda por delante del punto neutro,
    en cuerdas medias. Un ala volante no tiene cola que la corrija: pasado el
    punto neutro (margen negativo) es inestable."""
    quedan = [c for c in d["dentro"] if c["id"] not in sin]
    masa = sum(c["masa_kg"] for c in quedan)
    cg = [sum(c["masa_kg"] * c["en"][k] for c in quedan) / masa for k in range(3)]
    eq = d["equilibrio"]
    return {"masa_kg": masa, "cg": cg,
            "margen": (eq["punto_neutro_x"] - cg[0]) / eq["cuerda_media"]}


def _celdas(d):
    """{id: (x0, x1, y0, y1)} de las celdas del cuerpo central (lado derecho y
    centro; las de la izquierda son su reflejo)."""
    fus = d["fuselaje"]
    est = _estaciones(d)
    y_medio = max(f[1] for f in fus) / 2 + 20
    x0, x1 = fus[0][0], fus[-1][0]

    def borde(y):
        j = max(k for k in range(d["raiz"]) if est[k][0] <= y)
        a, b = est[j], est[j + 1]
        t = (y - a[0]) / (b[0] - a[0])
        le = a[1] + (b[1] - a[1]) * t
        return le, le + a[3] + (b[3] - a[3]) * t

    n = math.ceil((x1 - x0) / CELDA_FUSELAJE - 1e-9)
    cortes = [x0 + (x1 - x0) * k / n for k in range(n + 1)]
    # Un corte no cae en los bordes de ataque y de salida del centro del ala:
    # con la flecha, cada uno queda a 50° de la vertical en una celda que se
    # imprime de pie, y solo vale si su celda se apoya del lado bueno. Un
    # corte en medio del borde de salida dejaba un trozo en cada celda y la
    # de delante no tenía postura (cuerpo central 4, 2026-11-16). Con margen:
    # la transición del centro no es lineal entre estaciones.
    ys = [y_medio * k / 8 for k in range(9)]
    les, tes = [borde(y)[0] for y in ys], [borde(y)[1] for y in ys]
    for a, b in ((min(les) - 5, max(les) + 30), (min(tes) - 25, max(tes) + 5)):
        cortes = [a if a < c < b else c for c in cortes]
    for c0, c1 in zip(cortes, cortes[1:]):
        if c1 - c0 > CELDA_FUSELAJE * 1.15:
            raise _error(f"la celda del cuerpo central de x = {c0:g} a {c1:g} no cabe: "
                         "los bordes del ala no dejan cortar en otro sitio")
    celdas = {f"centro-{k + 1}": (cortes[k], cortes[k + 1], -y_medio, y_medio) for k in range(n)}
    y_raiz = est[d["raiz"]][0]
    if y_raiz <= y_medio:
        return celdas

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
    if any(c["id"] == "bateria" for c in d.get("dentro", [])):
        lista.append(("panza", "Panza", "la tapa de abajo del fuselaje, con cuatro M3: lleva la "
                      "bandeja de la batería y, colgada debajo entre dos quillas, la carga, que "
                      "mira por sus ventanas; por su boca entra también la electrónica"))
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
            servo = [s for s in _servos(d) if y0 < s["y"] < y1]
            # Los largueros se cortan al metro del tubo comprado: el último
            # tramo puede no llevar ninguno.
            llegan = sum(extremos_larguero(d, f, di)[1][2] > y0 for f, di in d["largueros"])
            con = {2: "con los dos largueros", 1: "con un larguero",
                   0: "sin larguero: va solo pegado"}[llegan]
            lista.append((f"ala-{lado}-{k}", f"Ala {ala}, tramo {k}",
                          f"de {y0:g} a {y1:g} mm del centro, {con}"
                          + (f"; lleva el servo del elevón {servo[0]['elevon']}, por abajo"
                             if servo else "")))
            for s in servo:
                lista.append((f"tapa-servo-{lado}-{s['elevon']}",
                              f"Tapa del servo {s['elevon']} {el}",
                              "tapa el hueco del servo bajo el ala, con ranura para el brazo"))
            if _con_elevon(d, y0, y1, i):
                nombre, trozos = _elevon_de(d, k)
                que = "alerón y timón de profundidad a la vez; lo mueve su servo"
                if len(trozos) > 1:
                    que += (f"; trozo {trozos.index(k) + 1} de {len(trozos)}, unidos con "
                            f"una varilla de carbono de Ø{VARILLA_ELEVON:g}")
                lista.append((f"elevon-{lado}-{k}", f"Elevón {el} {nombre}"
                              + (f" {trozos.index(k) + 1}" if len(trozos) > 1 else ""), que))
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


def extremos_larguero(d, f, diametro):
    """((x, z, y) de un extremo, del otro) de un larguero: recto, del centro
    (un poco más allá) a donde el perfil todavía le deja 1,2 mm de pared por
    cada lado, dentro del primer panel del ala exterior, y sin pasar de
    TUBO_COMPRADO de largo."""
    est = _estaciones(d)
    i = d["raiz"]
    perfil = est[i][5]
    de = _punto_larguero(d, -SOLAPE_LARGUEROS, f)

    def largo(y):
        return math.dist(de, _punto_larguero(d, y, f))

    y_fin = est[i + 1][0]
    for k in range(101):
        y = est[i][0] + (est[i + 1][0] - est[i][0]) * k / 100
        if _grueso(perfil, f) * _estacion(d, y)[2] < diametro + 2.4:
            y_fin = y
            break
    if largo(y_fin) > TUBO_COMPRADO:
        lo, hi = est[i][0], y_fin
        for _ in range(50):
            y = (lo + hi) / 2
            lo, hi = (y, hi) if largo(y) <= TUBO_COMPRADO else (lo, y)
        y_fin = lo
    return de, _punto_larguero(d, y_fin, f)


def _larguero(kit, d, f, diametro, puntas=False, pared=0.0):
    """El agujero de un larguero (`extremos_larguero`). Con `puntas`, en gota
    hacia +x y hacia -x: lo que se imprime de pie sobre un corte en x no deja
    techo en el agujero. Con `pared`, la funda que lo abraza dentro del hueco
    del ala: `pared` mm más gruesa."""
    de, a_ = extremos_larguero(d, f, diametro)
    return _tubo(kit, de, a_, diametro + 2 * pared, puntas)


def _tubo(kit, de, a_, diametro, puntas=False, holgura=HOLGURA_TUBO):
    """Un agujero recto de `de` a `a_`, cada uno (x, z, y). Con `puntas`, en
    gota (ver `_larguero`). Con `holgura=0` y sin puntas, lo que va dentro."""
    import FreeCAD
    import Part
    from mech_toolkit.kit import Cuerpo

    (xa, za, ya), (xb, zb, yb) = de, a_
    a, b = FreeCAD.Vector(xa, ya, za), FreeCAD.Vector(xb, yb, zb)
    eje = b - a
    largo = eje.Length
    eje.normalize()
    r = (diametro + holgura) / 2
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


def _largueros(kit, d, puntas=False, pared=0.0):
    hueco = None
    for f, diametro in d["largueros"]:
        t = _larguero(kit, d, f, diametro, puntas, pared)
        hueco = t if hueco is None else hueco + t
    return hueco


def _caras_en(d, y):
    """(arriba, abajo): los puntos (x, z) de cada cara del ala en `y`, del
    borde de ataque al de salida."""
    x, z, c, t, p = _estacion(d, y)
    arriba, abajo = _caras(_perfil(p))
    return ([_girado(u, v, x, z, c, t) for u, v in arriba],
            [_girado(u, v, x, z, c, t) for u, v in abajo])


def _z_cara(cara, x):
    for (x0, z0), (x1, z1) in zip(cara, cara[1:]):
        if x0 <= x <= x1 and x1 > x0:
            return z0 + (z1 - z0) * (x - x0) / (x1 - x0)
    raise _error(f"x = {x:g} cae fuera del perfil")


def _servo_en(d, s):
    """(x, y, z) del centro de un servo: apoyado en la cara de abajo del ala
    por su punto más alto, para que no asome, y con 1 mm de piel encima."""
    x, y = s["en"][0], s["en"][1]
    lx, _, lz = s["caja"]
    arriba, abajo = _caras_en(d, y)
    xs = [x - lx / 2 + lx * k / 12 for k in range(13)]
    suelo = max(_z_cara(abajo, q) for q in xs)
    techo = min(_z_cara(arriba, q) for q in xs)
    if techo - 1 < suelo + lz:
        raise _error(f"el servo de {lz:g} mm de grueso no cabe en y = {y:g}: el ala tiene ahí "
                     f"{techo - suelo:.1f} mm entre caras y hace falta 1 mm de piel encima")
    return x, y, suelo + lz / 2


def _hueco_servo(kit, d, s):
    """El hueco de un servo, abierto por abajo para meterlo (se tapa con una
    tapa). En sus puntas a lo largo de y se abre en rampa (SALIDA_SERVO): el
    ala se imprime de pie y el fondo del hueco sería un techo."""
    x, y, z = _servo_en(d, s)
    lx, ly, lz = s["caja"]
    arriba = z + lz / 2 + 0.5
    abajo = z - lz / 2 - 15
    m = ly / 2 + 0.5
    ancho = m + SALIDA_SERVO * (arriba - abajo)
    return kit.extruir([(y - m, arriba), (y - ancho, abajo), (y + ancho, abajo), (y + m, arriba)],
                       lx + 1, plano="yz", desde=x - lx / 2 - 0.5)


def _canal(kit, d, cables=None):
    """El canal de los cables de los servos de un lado: recto, a la altura de
    la línea media del perfil y a la cuerda de los servos, del centro del
    fuselaje al servo más de fuera. Pasa por el hueco del de dentro. Con
    `cables`, el mazo de cables de ese diámetro que va dentro."""
    servos = _servos(d)
    if not servos:
        return None
    y_fin = max(s["y"] for s in servos)
    x, _, c, _, _ = _estacion(d, servos[0]["y"], d["raiz"])
    f = (servos[0]["en"][0] - x) / c
    de, a_ = _punto_larguero(d, -10, f), _punto_larguero(d, y_fin, f)
    if cables:
        return _tubo(kit, de, a_, cables, holgura=0)
    return _tubo(kit, de, a_, CANAL_CABLES, puntas=True)


def _varilla(kit, d, tramos, hueco=True):
    """La varilla de carbono que une los trozos de un elevón: a 4 mm detrás
    de la bisagra, de 5 mm dentro del primero a 5 mm antes del final del
    último. Los agujeros son ciegos: la varilla queda dentro."""
    ts = _tramos_ala(d)
    y0, y1 = ts[tramos[0] - 1][0] + 5, ts[tramos[-1] - 1][1] - 5
    f = d["elevon"][1]

    def punto(y):
        x, z, c, t, p = _estacion(d, y)
        g = f + (HOLGURA_BISAGRA + 3.5) / c
        if _grueso(p, g) * c < VARILLA_ELEVON + HOLGURA_TUBO + 1.6:
            raise _error(f"la varilla de Ø{VARILLA_ELEVON:g} del elevón no cabe en y = {y:g}: "
                         f"el elevón tiene ahí {_grueso(p, g) * c:.1f} mm de grueso")
        return (*_girado(g, _comba(p, g), x, z, c, t), y)
    return _tubo(kit, punto(y0), punto(y1), VARILLA_ELEVON,
                 holgura=HOLGURA_TUBO if hueco else 0)


def dentro(kit, d, que):
    """El cuerpo de `que`: una de las cosas de `dentro` con caja (la batería,
    la carga, la electrónica, un servo), `canal-d`/`canal-i` o
    `varilla-d`/`varilla-i`. Para verlas en su sitio y comprobar que caben."""
    lado = que.split("-")[-1] if que.split("-")[-1] in ("d", "i") else None
    if que.startswith("canal-") and lado:
        canal = _canal(kit, d, cables=CANAL_CABLES - 2)
        if canal is None:
            raise _error("el avión no tiene servos colocados en `dentro`: no hay canal")
        return _lado(canal, lado)
    if que.startswith("varilla-") and lado:
        largos = [g for g in d.get("elevones", []) if len(g) > 1]
        if not largos:
            raise _error("ningún elevón tiene más de un trozo: no hay varilla")
        return _lado(_varilla(kit, d, largos[0], hueco=False), lado)
    cosas = {c["id"]: c for c in d.get("dentro", []) if c.get("caja")}
    if que not in cosas:
        raise _error(f"dentro del avión no hay {que!r}: hay {', '.join(cosas)}, "
                     "canal-d, canal-i, varilla-d y varilla-i")
    c = cosas[que]
    lx, ly, lz = c["caja"]
    if que.startswith("servo-"):
        s = {"en": [c["en"][0], abs(c["en"][1]), c["en"][2]], "caja": c["caja"]}
        x, y, z = _servo_en(d, s)
        caja = kit.caja(lx, ly, lz, en=(x - lx / 2, y - ly / 2, z - lz / 2))
        return caja if c["en"][1] > 0 else caja.espejo("xz", conservar=False)
    x, y, z = c["en"]
    return kit.caja(lx, ly, lz, en=(x - lx / 2, y - ly / 2, z - lz / 2))


def _fus(d):
    """[(x, ancho, alto, z del centro)] del fuselaje. La z de cada sección es
    opcional (sin ella, `z_fuselaje`): desde el 2026-11-16 el fuselaje se
    ahonda en el centro de gravedad para llevar la batería y, debajo, la
    carga."""
    return [(f[0], f[1], f[2], f[3] if len(f) > 3 else d["z_fuselaje"]) for f in d["fuselaje"]]


def _elipse_en(kit, ancho, alto, dz):
    """Una elipse cuyo centro sube `dz` sobre el eje de la transición (en una
    transición a lo largo de x, v es z)."""
    from mech_toolkit.kit import Seccion
    base = kit.elipse(ancho, alto)
    return Seccion(lambda centro, u, v: base._alambre(centro + v * dz, u, v))


def _seccion_fus(d, x):
    """(ancho, alto, z) del fuselaje en `x`, lineal entre secciones."""
    fus = _fus(d)
    for a, b in zip(fus, fus[1:]):
        if a[0] <= x <= b[0]:
            t = (x - a[0]) / (b[0] - a[0])
            return tuple(a[k] + (b[k] - a[k]) * t for k in (1, 2, 3))
    raise _error(f"x = {x:g} cae fuera del fuselaje")


def _fuselaje(kit, d):
    return kit.transicion([(_elipse_en(kit, w, h, z), x) for x, w, h, z in _fus(d)], eje="x")


_PIEL_MEDIDA: dict = {}


def _piel_fuselaje(kit, d):
    """[(x, ancho, alto, z del centro)] de la piel del fuselaje tal como sale,
    cortada cada 20 mm (cada 10 junto a las puntas). La transición suave pasa
    por las secciones del diseño pero entre ellas se sale: en x = 300 la
    panza bajaba 17 mm más que las dos secciones que la rodean, y un hueco
    hecho con esas secciones dejaba la panza casi maciza (543 cm³, 2026-11-16).
    Sus secciones son elipses (de elipses con los mismos pesos), así que su
    caja las da enteras."""
    import FreeCAD
    clave = json.dumps([d["fuselaje"], d.get("z_fuselaje")])
    if clave not in _PIEL_MEDIDA:
        fus = _fus(d)
        a, b = fus[0][0], fus[-1][0]
        xs = sorted({round(x, 3) for x in
                     [a + 10 * k for k in range(1, 7)] + [b - 10 * k for k in range(1, 7)]
                     + [x for x in range(int(a) + 80, int(b) - 60, 20)]
                     + [f[0] for f in fus[1:-1]]})
        forma = _fuselaje(kit, d)._forma
        medida = []
        for x in xs:
            cortes = forma.slice(FreeCAD.Vector(1, 0, 0), x)
            caja = cortes[0].BoundBox
            for c in cortes[1:]:
                caja.add(c.BoundBox)
            medida.append((x, caja.YLength, caja.ZLength, (caja.ZMin + caja.ZMax) / 2))
        _PIEL_MEDIDA[clave] = medida
    return _PIEL_MEDIDA[clave]


def _hueco_fuselaje(kit, d, pared=PARED):
    """Por dentro, a `pared` de la piel medida (y 0,1 mm más: entre corte y
    corte el hueco va en recta), y acabado en punta a 45° por los dos lados:
    el morro romo de la primera prueba dejaba un techo."""
    fus = _fus(d)
    dentro = [(x, w - 2 * pared - 0.2, h - 2 * pared - 0.2, z)
              for x, w, h, z in _piel_fuselaje(kit, d)]
    # Las puntas, un 25 % más largas que a 45° justos: en el límite, la de la
    # cola daba voladizo (cuerpo central 5, 2026-11-16). El hueco empieza en
    # el primer corte desde el que la punta cabe, y acaba en el último: en la
    # cola quedan 25 mm macizos para el motor de empuje.
    x_ini, x_fin = fus[0][0] + PARED + 5, fus[-1][0] - PARED - 25

    # Con el lado largo de la elipse: con el corto, por el ancho la punta se
    # pasaba de 45° en cuanto el morro salía más ancho que alto (cuerpo
    # central 1, al ahondar el vientre bajo la carga, 2026-11-16).
    def largo(s):
        return 1.25 * (max(s[1], s[2]) / 2 - 3)

    dentro = [s for s in dentro if min(s[1], s[2]) > 8]
    i = next(k for k, s in enumerate(dentro) if s[0] - largo(s) >= x_ini)
    j = max(k for k, s in enumerate(dentro) if s[0] + largo(s) <= x_fin)
    dentro = dentro[i:j + 1]
    # Acaban en una elipse de 6: con 16, el final era un techo plano de 16 mm
    # (cuerpo central 5).
    x1, w1, h1, z1 = dentro[0]
    xf = x1 - largo(dentro[0])
    xn, wn, hn, zn = dentro[-1]
    xb = xn + largo(dentro[-1])
    # Con la forma de la sección de al lado, en pequeño: de un círculo a una
    # elipse la transición se retorcía y dejaba en el morro una cara de 1 mm²
    # que empezaba en el aire (cuerpo central 1, 2026-11-16).
    secs = ([(xf, 6 * w1 / min(w1, h1), 6 * h1 / min(w1, h1), z1)] + dentro
            + [(xb, 6 * wn / min(wn, hn), 6 * hn / min(wn, hn), zn)])
    # En tramos rectos: suave, la transición se pasaba de la piel junto a la
    # cola y dejaba dos astillas sueltas (el cuerpo central 5 salía en tres
    # sólidos, 2026-11-16). Recta, además, la punta tiene la pendiente que se
    # le calcula.
    return kit.transicion([(_elipse_en(kit, w, h, z), x) for x, w, h, z in secs], eje="x",
                          recta=True)


def _rombo(kit, d, x, largo, ancho):
    _, h, z = _seccion_fus(d, x)
    abajo = z - h / 2
    return kit.extruir([(x - largo / 2, 0), (x, ancho / 2), (x + largo / 2, 0), (x, -ancho / 2)],
                       PARED + 30, plano="xy", desde=abajo - 15)


def _estacion_centro(d, y):
    """(x, z, cuerda, torsión, perfil) del centro del ala (de y = 0 a la raíz
    del ala exterior), lineal entre estaciones; el perfil, el de la de dentro."""
    est = _estaciones(d)
    for a, b in zip(est[:d["raiz"]], est[1:d["raiz"] + 1]):
        if a[0] - 1e-6 <= y <= b[0] + 1e-6:
            t = (y - a[0]) / (b[0] - a[0])
            return [a[k] + (b[k] - a[k]) * t for k in range(1, 5)] + [a[5] if t < 1 - 1e-6
                                                                      else b[5]]
    raise _error(f"y = {y:g} cae fuera del centro del ala")


def _seccion_hueca(kit, x, z, c, t, p, desde=0.0, hasta=1.0, punta=0.0, piel=PIEL_ALA):
    cont = contorno_hueco(p, c, piel, desde, hasta, punta=punta)
    return None if cont is None else kit.seccion([_girado(u, v, x, z, c, t) for u, v in cont])


def _hueco_centro(kit, d):
    """El hueco del centro del ala, de lado a lado, con la piel del ala, y
    cerrado en la raíz del ala exterior por una costilla: ahí se pega el
    primer tramo, que va abierto."""
    est = _estaciones(d)
    ys = [e[0] for e in est[:d["raiz"] + 1]]
    ys[-1] -= PIEL_ALA
    secs = [(_seccion_hueca(kit, *_estacion_centro(d, y), punta=3.0), y) for y in ys]
    return kit.transicion(secs, eje="y").espejo("xz")


def _costillas(kit, d):
    """Las costillas de las raíces (planos y = cte, cada PASO_COSTILLA), que
    al imprimirlas de pie sobre un corte en x son paredes."""
    est = _estaciones(d)
    y_medio = max(f[1] for f in d["fuselaje"]) / 2 + 20
    y_raiz = est[d["raiz"]][0]
    n = max(0, math.floor((y_raiz - y_medio) / PASO_COSTILLA))
    # Y una en la junta del cuerpo central con las raíces, de dos pieles: el
    # corte la parte y a cada lado le queda la suya. Sin ella, la punta
    # delantera del hueco, que va en flecha, quedaba abierta en el corte y
    # volaba 5,2 mm (cuerpo central 2, 2026-11-16); y las dos piezas se
    # pegaban solo por el canto de una piel de 0,6 mm.
    todas = kit.caja(2000, 2 * PIEL_ALA, 600, en=(-1000, y_medio - PIEL_ALA, -300))
    for k in range(n):
        y = y_medio + (y_raiz - y_medio) * (k + 0.5) / n
        c = kit.caja(2000, PIEL_ALA, 600, en=(-1000, y - PIEL_ALA / 2, -300))
        todas = c if todas is None else todas + c
    return None if todas is None else todas.espejo("xz")


def panza(d) -> tuple[float, float, float]:
    """(x0, x1, z del corte) de la panza: la tapa de abajo del fuselaje por
    la que entran la batería, la carga y la electrónica. Por arriba no se
    puede: el larguero de atrás cruza el fuselaje sobre la batería. El corte
    va a la altura más baja en la que la boca, por dentro del marco y la
    pestaña, deja pasar la batería con 1 mm por cada lado."""
    bat = next(c for c in d["dentro"] if c["id"] == "bateria")
    (x, _, _), (lx, ly, _) = bat["en"], bat["caja"]
    x0, x1 = x - lx / 2 - 2, x + lx / 2 + 2
    falta = ly / 2 + 1 + PARED + MARCO + HOLGURA_PANZA + LABIO
    z_corte = -math.inf
    for xq in [x0, x1] + [f[0] for f in d["fuselaje"] if x0 < f[0] < x1]:
        w, h, zc = _seccion_fus(d, xq)
        if w / 2 <= falta:
            raise _error(f"la batería de {ly:g} de ancho no pasa por la panza en x = {xq:g}: "
                         f"el fuselaje mide ahí {w:g}")
        z_corte = max(z_corte, zc - h / 2 * math.sqrt(1 - (falta / (w / 2)) ** 2))
    return x0, x1, z_corte


def _abajo_de(d, que):
    c = next(c for c in d["dentro"] if c["id"] == que)
    return c["en"][2] - c["caja"][2] / 2


def _tornillos_panza(kit, d):
    """Cuatro M3 de lado a lado por el marco y la pestaña de la panza."""
    x0, x1, zc = panza(d)
    todos = None
    for x in (x0 + 20, x1 - 20):
        t = kit.cilindro(3.3, 400, en=(x, -200, zc + ALTO_LABIO / 2), eje="y")
        todos = t if todos is None else todos + t
    return todos


def _repisa(kit, d):
    """La repisa de la electrónica, en el morro: se mete por la panza y se
    empuja hacia delante, bajo los largueros. Un plano z = cte, que de pie
    sobre un corte en x es una pared."""
    c = next(c for c in d["dentro"] if c["id"] == "electronica")
    x0 = c["en"][0] - c["caja"][0] / 2 - 10
    x1 = panza(d)[0]
    z = _abajo_de(d, "electronica") - 0.5
    return kit.caja(x1 - x0, 200, BANDEJA, en=(x0, -100, z - BANDEJA))


def _cuerpo_central(kit, d, celda=None):
    """El fuselaje con el centro del ala, hueco. Con `celda` ((x0, x1, y0,
    y1)), solo lo que cae dentro: el cuerpo y sus huecos se recortan antes de
    unirlos y restarlos, que da el mismo sólido y FreeCAD lo hace en menos
    tiempo. Entero, el cuerpo central 1 tardaba 253 s con el vientre ahondado
    bajo la carga, y el tope es 180; 58 s eran unir los dos huecos enteros y
    42 restarlos (2026-11-16). Los huecos, con 5 mm de margen: cortados justo
    en la celda, sus caras coincidirían con las del cuerpo."""
    if celda is not None:
        x0, x1, y0, y1 = celda
        caja = kit.caja(x1 - x0, y1 - y0, 600, en=(x0, y0, -300))
        holgada = kit.caja(x1 - x0 + 10, y1 - y0 + 10, 600, en=(x0 - 5, y0 - 5, -300))

        def recorta(c):
            r = c._forma.common(holgada._forma)
            return (c & holgada) if r.Volume > 1 else None
    else:
        def recorta(c):
            return c
    est = _estaciones(d)
    centro = kit.transicion([(_seccion(kit, e[1], e[2], e[3], e[4], e[5]), e[0])
                             for e in est[:d["raiz"] + 1]], eje="y")
    # Hueco por dentro: el fuselaje a PARED de la piel y el centro del ala a
    # PIEL_ALA, con lo que lleva dentro hecho de material: las costillas de
    # las raíces, las fundas de los largueros, la repisa de la electrónica y
    # el marco de la boca de la panza. El hueco del ala no pasa por la pared
    # del fuselaje: se la comía donde se cruzan, y cada celda salía en dos
    # mitades sueltas, la de arriba y la de abajo, con las fundas de los
    # largueros flotando entre ellas (cuerpo central 3, 2026-11-16).
    # Las fundas, solo en el hueco del ala, de la pared del fuselaje a las
    # costillas: dentro del fuselaje el tubo cruza libre de pared a pared.
    # Con funda, el corte entre dos celdas la dejaba suelta en el aire,
    # porque el larguero va en flecha (cuerpo central 2).
    fuselaje = _fuselaje(kit, d)
    hueco_fus = _hueco_fuselaje(kit, d)
    hueco_ala = _hueco_centro(kit, d) - (fuselaje - hueco_fus)
    costillas = _costillas(kit, d)
    if costillas is not None:
        hueco_ala = hueco_ala - costillas
    fundas = _largueros(kit, d, puntas=True, pared=FUNDA)
    hueco_ala = hueco_ala - fundas - fundas.espejo("xz", conservar=False)
    trozos = [h for h in (recorta(hueco_fus), recorta(hueco_ala)) if h is not None]
    hueco = trozos[0] if len(trozos) == 1 else trozos[0] + trozos[1]
    hueco = hueco - _repisa(kit, d)
    cuerpo = fuselaje + centro.espejo("xz")
    if celda is not None:
        cuerpo = cuerpo & caja
    x0, x1, zc = panza(d)
    marco = (_hueco_fuselaje(kit, d) - _hueco_fuselaje(kit, d, PARED + MARCO)) & kit.caja(
        x1 - x0 + 2 * MARCO, 400, ALTO_LABIO + 4, en=(x0 - MARCO, -200, zc))
    cuerpo = cuerpo - (hueco - marco)
    largueros = _largueros(kit, d, puntas=True)
    cuerpo = cuerpo - largueros - largueros.espejo("xz", conservar=False)
    canal = _canal(kit, d)
    if canal is not None:
        cuerpo = cuerpo - canal - canal.espejo("xz", conservar=False)
    # La boca de la panza, y sus tornillos.
    cuerpo = cuerpo - kit.caja(x1 - x0, 400, 300, en=(x0, -200, zc - 300))
    cuerpo = cuerpo - _tornillos_panza(kit, d)
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


def _panza_pieza(kit, d):
    """La panza: el fondo del fuselaje bajo el corte, con sus ventanas, las
    dos quillas, la bandeja de la batería encima de ellas y la pestaña que
    sube por dentro del marco. La carga va colgada bajo la bandeja, entre las
    quillas; la batería, encima, sujeta con dos cintas por sus ranuras. Todo
    son planos que contienen x: de pie sobre un corte en x, paredes."""
    x0, x1, zc = panza(d)
    largo = x1 - x0
    hueco = _hueco_fuselaje(kit, d)
    piel = (_fuselaje(kit, d) - hueco) & kit.caja(largo, 400, 300, en=(x0, -200, zc - 300))
    bat = next(c for c in d["dentro"] if c["id"] == "bateria")
    ly = bat["caja"][1]
    z_bandeja = _abajo_de(d, "bateria") - 0.5
    bandeja = kit.caja(largo, ly + 1, BANDEJA, en=(x0, -(ly + 1) / 2, z_bandeja - BANDEJA))
    # Dos cintas de velcro de 20 mm rodean la batería; cada una pasa por dos
    # ranuras de 20 × 4, a los lados. Con una ranura de lado a lado (4 × 110)
    # la panza, de pie, tenía un techo de 110 mm (2026-11-16).
    for x in (x0 + largo * 0.3, x0 + largo * 0.7):
        for s in (1, -1):
            bandeja = bandeja - kit.caja(20, 4, 20, en=(x - 10, s * (ly / 2 - 6) - 2,
                                                        z_bandeja - 10))
    quillas = None
    for s in (1, -1):
        q = kit.caja(largo, PIEL_ALA * 2, z_bandeja - BANDEJA - (zc - 300),
                     en=(x0, s * QUILLA_Y - PIEL_ALA, zc - 300)) & hueco
        quillas = q if quillas is None else quillas + q
    fuera = PARED + MARCO + HOLGURA_PANZA
    pestana = (_hueco_fuselaje(kit, d, fuera) - _hueco_fuselaje(kit, d, fuera + LABIO)) & kit.caja(
        largo, 400, ALTO_LABIO, en=(x0, -200, zc))
    # El reborde del corte, de la piel a la pestaña: sin él la pestaña, que
    # sube por dentro del marco, no tocaba la piel y salía suelta (2026-11-16).
    # Es donde apoya el marco del cuerpo.
    reborde = (_fuselaje(kit, d) - _hueco_fuselaje(kit, d, fuera + LABIO)) & kit.caja(
        largo, 400, LABIO, en=(x0, -200, zc - LABIO))
    # Los tornillos solo cruzan la pestaña: se taladran en ella antes de
    # unirla. Taladrados en la panza entera, OCC daba a veces un sólido no
    # válido (2 de cada 12 construcciones iguales, y otra vez en los tests,
    # 2026-11-16): sus booleanas en paralelo no dan siempre lo mismo.
    pestana = pestana - _tornillos_panza(kit, d)
    p = piel + reborde + quillas + bandeja + pestana
    for x, l, a in d.get("ventanas", []):
        p = p - _rombo(kit, d, x, l, a)
    return p


def _tapa_servo(kit, d, s):
    """La tapa del hueco de un servo, por fuera de la cara de abajo del ala:
    pisa SOLAPE_TAPA la piel alrededor del hueco y deja una ranura para el eje
    y el brazo. Plana, se imprime tumbada; se sujeta con cinta o dos tornillos."""
    x, y, z = _servo_en(d, s)
    lx, ly, lz = s["caja"]
    arriba = z + lz / 2 + 0.5
    _, abajo = _caras_en(d, y)
    xs = [x - lx / 2 - 0.5 + (lx + 1) * k / 8 for k in range(9)]
    piel = min(_z_cara(abajo, q) for q in xs)
    ancho = ly / 2 + 0.5 + SALIDA_SERVO * (arriba - piel)
    tapa = kit.caja(lx + 1 + 2 * SOLAPE_TAPA, 2 * (ancho + SOLAPE_TAPA), TAPA_SERVO,
                    en=(x - lx / 2 - 0.5 - SOLAPE_TAPA, y - ancho - SOLAPE_TAPA, piel - TAPA_SERVO))
    return tapa - kit.caja(8, ly - 8, 10, en=(x - 4, y - (ly - 8) / 2, piel - 5))


def _cajon_servo(kit, d, s):
    """Las paredes que rodean el hueco de un servo dentro del hueco del ala:
    el hueco crecido FUNDA por todos lados, con sus rampas a 50°."""
    x, y, z = _servo_en(d, s)
    lx, ly, lz = s["caja"]
    arriba = z + lz / 2 + 0.5 + FUNDA
    abajo = z - lz / 2 - 15
    m = ly / 2 + 0.5 + FUNDA
    ancho = m + SALIDA_SERVO * (arriba - abajo)
    return kit.extruir([(y - m, arriba), (y - ancho, abajo), (y + ancho, abajo), (y + m, arriba)],
                       lx + 1 + 2 * FUNDA, plano="yz", desde=x - lx / 2 - 0.5 - FUNDA)


def _nervios(kit, d, y0, y1, i):
    """Los nervios de un tramo de ala: tabiques en zigzag (celosía) que van
    de la cara de abajo a la de arriba subiendo NERVIO_GRADOS sobre la
    horizontal al imprimir el tramo de pie. Cada uno es un plano que contiene
    x: va de borde a borde, y el hueco lo recorta."""
    a = math.radians(NERVIO_GRADOS)
    ym = (y0 + y1) / 2
    x, z, c, t, p = _estacion(d, ym, i)
    alto = _grueso(p, 0.3) * c
    paso = alto * math.tan(a)
    n = max(1, math.floor((y1 - y0) / paso))
    largo = 4 * alto
    todos = None
    for k in range(n):
        yk = y0 + (y1 - y0) * (k + 0.5) / n
        xk, zk, ck, tk, pk = _estacion(d, yk, i)
        zc = _girado(0.3, _comba(pk, 0.3), xk, zk, ck, tk)[1]
        s = 1 if k % 2 == 0 else -1
        dy, dz = math.sin(a), s * math.cos(a)        # a lo largo del nervio
        ny, nz = -dz, dy                              # su normal
        e = PIEL_ALA / 2
        esquinas = [(yk + dy * largo / 2 + ny * e, zc + dz * largo / 2 + nz * e),
                    (yk + dy * largo / 2 - ny * e, zc + dz * largo / 2 - nz * e),
                    (yk - dy * largo / 2 - ny * e, zc - dz * largo / 2 - nz * e),
                    (yk - dy * largo / 2 + ny * e, zc - dz * largo / 2 + nz * e)]
        nervio = kit.extruir(esquinas, 2 * c + 400, plano="yz", desde=x - c - 200)
        todos = nervio if todos is None else todos + nervio
    return todos


def _hueco_tramo(kit, d, y0, y1, i, elevon, punta, piel=PIEL_ALA):
    """El hueco de un tramo del ala exterior: abierto por sus dos caras (se
    pegan tramo con tramo sobre la costilla de la raíz) salvo en la punta,
    que acaba cerrada. Dos celdas, delante y detrás del alma; la de detrás no
    la llevan los tramos con elevón, que ahí tienen la bisagra."""
    ya, yb = y0 - 1, (y1 - PIEL_ALA if punta else y1 + 1)
    celdas = [(0.0, CUERDA_ALMA)] + ([] if elevon else [(CUERDA_ALMA, 1.0)])
    hueco = None
    for desde, hasta in celdas:
        secs = []
        for y in (ya, yb):
            x, z, c, t, p = _estacion(d, y, i)
            e = piel / 2 / c
            secs.append(_seccion_hueca(kit, x, z, c, t, p, desde + (e if desde else 0),
                                       hasta - (e if hasta < 1 else 0), piel=piel))
        if None in secs:
            continue
        celda = kit.transicion([(secs[0], ya), (secs[1], yb)], eje="y")
        hueco = celda if hueco is None else hueco + celda
    return hueco


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
    if partes[0] == "panza":
        return _panza_pieza(kit, d)
    if partes[0] == "tapa":
        s = next(s for s in _servos(d) if s["elevon"] == partes[3])
        return _lado(_tapa_servo(kit, d, s), partes[2])
    if partes[0] in ("centro", "raiz"):
        celdas = _celdas(d)
        x0, x1, y0, y1 = celdas[id_ if partes[0] == "centro" else f"raiz-d-{partes[2]}"]
        trozo = _cuerpo_central(kit, d, (x0, x1, y0, y1))
        return trozo if partes[0] == "centro" else _lado(trozo, lado)
    if partes[0] in ("ala", "elevon"):
        k = int(partes[2])
        y0, y1, i, ala = _tramo(kit, d, k)
        if partes[0] == "ala":
            con_elevon = _con_elevon(d, y0, y1, i)
            hueco = _hueco_tramo(kit, d, y0, y1, i, con_elevon, _levantado(d, i))
            if hueco is not None:
                # Lo de dentro (nervios, fundas de los largueros y cajones de
                # los servos) se suma después de vaciar, recortado a la forma
                # del tramo: es el mismo sólido (ala − (hueco − dentro) =
                # (ala − hueco) + (ala & dentro)), pero restar un hueco que los
                # nervios parten en 14 trozos le costaba a OCC 158 s en el
                # primer tramo, y la pieza entera pasaba del tope de 180
                # (2026-11-16). Antes de recortarlo a la forma, a la caja del
                # hueco: cada nervio sale 200 mm por delante y por detrás del
                # ala, y cruzar eso con la piel curva costaba el triple.
                dentro = _largueros(kit, d, pared=FUNDA)
                if not _levantado(d, i):
                    dentro = dentro + _nervios(kit, d, y0, y1, i)
                for s in _servos(d):
                    if y0 < s["y"] < y1:
                        dentro = dentro + _cajon_servo(kit, d, s)
                bb = hueco._forma.BoundBox
                dentro = dentro & kit.caja(bb.XLength + 2, bb.YLength + 2, bb.ZLength + 2,
                                           en=(bb.XMin - 1, bb.YMin - 1, bb.ZMin - 1))
                ala = (ala - hueco) + (dentro & ala)
            ala = ala - _largueros(kit, d)
            canal = _canal(kit, d)
            if canal is not None and y0 < max(s["y"] for s in _servos(d)):
                ala = ala - canal
            for s in _servos(d):
                if y0 < s["y"] < y1:
                    ala = ala - _hueco_servo(kit, d, s)
            if _con_elevon(d, y0, y1, i):
                ala = ala - _bisagra(kit, d, y0, y1, -HOLGURA_BISAGRA)
            return _lado(ala, lado)
        elevon = ala & _bisagra(kit, d, y0, y1, HOLGURA_BISAGRA)
        _, trozos = _elevon_de(d, k)
        if len(trozos) > 1:
            elevon = elevon - _varilla(kit, d, trozos)
        return _lado(elevon, lado)
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
