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
cuerda y Ø6 al 60 %), como en los aviones de LW-PLA de Flightory. Las celdas
del cuerpo central, que los largueros no cruzan todas, llevan guías: trozos
de varilla de Ø2 en tacos pegados por dentro a la pared (`guias`).
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
2,4 mm de sobra (test del 2026-11-16); con 160, con 12.

Esta y las dos de abajo son las de la cama del sistema (235 × 235 × 250).
Un diseño dice las suyas con `tramo_max`, `celda_fuselaje` y `celda_raiz`:
él imprime en una CORE One L+ de 300 × 300 × 330, y con estas salían 44
piezas («porque estamos sacando muchisimas piezas», 2026-11-18)."""
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
TACO_GUIA = 8.0
"""Los tacos de las guías del cuerpo central: con la varilla de Ø2 en un
agujero de 2,3, les quedan 2,85 mm de pared."""
MEDIO_TACO = 10.0
"""Lo que mide un taco a cada lado del corte, sin la punta."""
MEDIA_GUIA = 9.0
"""Lo que entra cada guía en cada celda: un trozo de 18 mm de varilla."""
PUNTA_TACO = 6.0
"""El cono con el que acaba un taco: con la cara plana, la celda impresa de
pie sobre el otro corte la tendría de techo, 8 mm en el aire."""
SOLAPE_TACO = 0.8
"""Lo que el taco se mete en la pared del fuselaje para quedar pegado a ella."""
SALIDA_SERVO = 1.2
"""Cuánto más largo es el hueco del servo por cada mm de hondo, en cada
punta: el ala se imprime de pie y el fondo del hueco sería un techo; así es
una rampa a 50° de la horizontal."""
LARGO_PIE = 150.0
"""El de la deriva y el de la pata, a lo largo de la viga."""
PATA_CUERDA = (100.0, 70.0)
"""La cuerda de la pata, en su raíz y en su pie: más corta que la de la deriva."""

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
        n = max(1, math.ceil((y1 - y0) / d.get("tramo_max", TRAMO_MAX) - 1e-9))
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

    celda = d.get("celda_fuselaje", CELDA_FUSELAJE)
    if d.get("cortes_fuselaje"):
        # Dados por el diseño: el borde de ataque del centro del avión del
        # 2026-11-18 va a 41°, y en la celda que lo lleva de pie sobre su
        # corte de delante su morro volaba 24,4 mm fuera del fuselaje (cuerpo
        # central 2). Se corta detrás de él y esa celda se imprime sobre su
        # cara de atrás. Quien los da responde de que cada celda se imprima.
        cortes = [float(c) for c in d["cortes_fuselaje"]]
        if cortes[0] != x0 or cortes[-1] != x1:
            raise _error(f"los cortes del cuerpo central van del morro (x = {x0:g}) a la "
                         f"cola (x = {x1:g}), no de {cortes[0]:g} a {cortes[-1]:g}")
        if any(b <= a for a, b in zip(cortes, cortes[1:])):
            raise _error(f"los cortes del cuerpo central no van en orden: {cortes}")
        n = len(cortes) - 1
    else:
        n = math.ceil((x1 - x0) / celda - 1e-9)
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
        cortes = [a if a < c < b and not d.get("cortes_fuselaje") else c for c in cortes]
    for c0, c1 in zip(cortes, cortes[1:]):
        if c1 - c0 > celda * 1.15 and not d.get("cortes_fuselaje"):
            raise _error(f"la celda del cuerpo central de x = {c0:g} a {c1:g} no cabe: "
                         "los bordes del ala no dejan cortar en otro sitio")
    celdas = {f"centro-{k + 1}": (cortes[k], cortes[k + 1], -y_medio, y_medio) for k in range(n)}
    y_raiz = est[d["raiz"]][0]
    if y_raiz <= y_medio:
        return celdas

    ys = [y_medio + (y_raiz - y_medio) * k / 8 for k in range(9)]
    lo = min(borde(y)[0] for y in ys) - 15
    hi = max(borde(y)[1] for y in ys) + 15
    m = math.ceil((hi - lo) / d.get("celda_raiz", CELDA_RAIZ) - 1e-9)
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
                          "fuselaje y centro del ala: la batería, la carga y la electrónica; "
                          "se pega a la de al lado con guías de varilla de Ø2"))
    if any(c["id"] == "bateria" for c in d.get("dentro", [])):
        lista.append(("panza", "Panza", "la tapa de abajo del fuselaje, con cuatro M3: lleva la "
                      "bandeja de la batería y, colgada debajo entre dos quillas, la carga, que "
                      "mira por sus ventanas; por su boca entra también la electrónica"))
    for lado, ala, el in (("d", "derecha", "derecho"), ("i", "izquierda", "izquierdo")):
        for id_ in _celdas(d):
            if id_.startswith("raiz"):
                k = id_.split("-")[2]
                lista.append((f"raiz-{lado}-{k}", f"Raíz del ala {ala} {k}",
                              "donde el ala se funde con el fuselaje"
                              + ("; por ella cruzan los manguitos donde se enchufan las alas"
                                 if _desmontable(d) else "")))
        for k, (y0, y1, i) in enumerate(_tramos_ala(d), 1):
            if _levantado(d, i):
                if not d.get("punta_unida"):
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
                             if servo else "")
                          + ("; con la punta levantada, de la misma pieza"
                             if _con_punta(d, k) else "")
                          + ("; se enchufa al cuerpo por el larguero de Ø10 y un pasador, "
                             "y la sujeta un M3" if k == 1 and _desmontable(d) else "")))
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
                if _mandos(d):
                    que += "; va con tres bisagras de papel y su cuerno por abajo"
                lista.append((f"elevon-{lado}-{k}", f"Elevón {el} {nombre}"
                              + (f" {trozos.index(k) + 1}" if len(trozos) > 1 else ""), que))
        pilon = ("une la viga al ala con dos M3 que llegan a la funda del larguero"
                 if d.get("pilon_atornillado") else "une la viga al ala")
        if d["rotores"].get("aletas"):
            lista += [(f"gondola-{lado}-delante", f"Góndola delantera {ala}",
                       "un motor de sustentación sobre la viga y, debajo, la pata delantera: "
                       "para posarse"),
                      (f"gondola-{lado}-detras", f"Góndola trasera {ala}",
                       "un motor de sustentación sobre la viga y, debajo, la deriva: "
                       "estabilidad de guiñada y pata trasera"),
                      (f"pilon-{lado}", f"Pilón {el}", pilon)]
            continue
        lista += [(f"gondola-{lado}-delante", f"Góndola delantera {ala}",
                   "un motor de sustentación sobre la viga"),
                  (f"gondola-{lado}-detras", f"Góndola trasera {ala}",
                   "un motor de sustentación sobre la viga"),
                  (f"pilon-{lado}", f"Pilón {el}", pilon),
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


DESMONTABLE = {"enchufe": 5.0, "manguito": [12.0, 10.0], "pasa": 60.0, "tijera": [10.0, 3.0],
               "pasador": [6.0, 0.75, 20.0], "tornillo": 25.0}
"""Las alas desmontables (F13.7 (desmontable)), decididas por él el 2026-11-18
al compararlo con el Stallion de Flightory. Con la flecha, los largueros de
las dos alas forman una V, y el de cada lado pasaba 20 mm al otro
(`SOLAPE_LARGUEROS`): los dos se cortaban en el centro y el avión no se podía
montar (medido a mano ese día). Ahora:

- `enchufe`: el Ø10 de cada ala sale de su raíz 5 Ø (criterio del asistente)
  y entra en un `manguito` de carbono de 12 × 10 pegado al cuerpo central;
- `pasa`: cada manguito cruza el fuselaje hasta 60 mm al otro lado del centro,
  y los dos se cruzan en tijera: en el centro, el de la derecha sube
  `tijera[0]` mm y el de la izquierda baja `tijera[1]`, girando cada uno
  sobre la punta de su larguero; entre los dos tubos de Ø12 queda 1 mm. No
  a partes iguales: bajando 6,5 el de la izquierda, la electrónica (techo en
  −15,5) no pasaba bajo él al empujarla hacia el morro. Subiendo 10 el de la
  derecha, en su raíz (30,5 mm de grueso) le quedan 0,9 mm de sobra con su
  funda (cuentas del 2026-11-19);
- el Ø6 acaba a ras de la raíz: no va paralelo al Ø10 (4,4° de diferencia) y
  el ala no podría deslizar sobre los dos. En su lugar, un `pasador` de Ø6 ×
  2·20 al 75 % de la cuerda, paralelo al Ø10, que impide que el ala gire;
- un M3 a lo largo de x, `tornillo` mm dentro de la raíz, cruza manguito y
  larguero por su eje neutro, por un tetón que sirve de guía para taladrarlos
  juntos (las plantillas de taladrar del Stallion)."""


def _desmontable(d):
    m = d.get("desmontable")
    if not m:
        return None
    return {**DESMONTABLE, **(m if isinstance(m, dict) else {})}


def _principal(d, f):
    """Si el larguero al `f` de la cuerda es el de delante: el que lleva manguito."""
    return f == d["largueros"][0][0]


def _fin_larguero(d, f, diametro, y_ini):
    """La y donde acaba un larguero que empieza en `y_ini`: donde el perfil
    todavía le deja 1,2 mm de pared por cada lado, dentro del primer panel del
    ala exterior, y sin pasar de TUBO_COMPRADO de largo."""
    est = _estaciones(d)
    i = d["raiz"]
    perfil = est[i][5]
    de = _punto_larguero(d, y_ini, f)

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
    return y_fin


def _punto_eje(d, y, f, lado, y_fin):
    """(x, z, y) del eje de un larguero en `y`, en las coordenadas del lado
    derecho (el izquierdo es su reflejo). El de delante de un ala desmontable
    sube (derecha) o baja (izquierda) en tijera, girando sobre su punta."""
    x, z, yy = _punto_larguero(d, y, f)
    m = _desmontable(d)
    if m and _principal(d, f):
        sube = m["tijera"][0] if lado == "d" else -m["tijera"][1]
        z += sube * (y_fin - y) / y_fin
    return x, z, yy


def extremos_larguero(d, f, diametro, lado="d"):
    """((x, z, y) de un extremo, del otro) de un larguero, en las coordenadas
    del lado derecho: recto, del centro (un poco más allá) a `_fin_larguero`.
    En un ala desmontable, el de delante sale de la raíz lo que entra en su
    manguito y los demás acaban en ella."""
    m = _desmontable(d)
    y_raiz = _estaciones(d)[d["raiz"]][0]
    if m is None:
        y_ini = -SOLAPE_LARGUEROS
    elif _principal(d, f):
        y_ini = y_raiz - m["enchufe"] * diametro
    else:
        y_ini = y_raiz
    y_fin = _fin_larguero(d, f, diametro, y_ini)
    return _punto_eje(d, y_ini, f, lado, y_fin), _punto_eje(d, y_fin, f, lado, y_fin)


def extremos_manguito(d, lado="d"):
    """((x, z, y), (x, z, y)) del manguito de un ala desmontable, en las
    coordenadas del lado derecho: de la raíz (medio mm dentro) a `pasa` mm al
    otro lado del centro, sobre el eje del larguero de delante."""
    m = _desmontable(d)
    f, di = d["largueros"][0]
    y_fin = extremos_larguero(d, f, di, lado)[1][2]
    y_raiz = _estaciones(d)[d["raiz"]][0]
    return (_punto_eje(d, y_raiz - 0.5, f, lado, y_fin),
            _punto_eje(d, -m["pasa"], f, lado, y_fin))


def _deslizar(d, lado="d"):
    """El vector unitario (x, z, y) por el que el ala entra en su manguito."""
    f, di = d["largueros"][0]
    a, b = extremos_larguero(d, f, di, lado)
    v = [b[k] - a[k] for k in range(3)]
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v]


def extremos_pasador(d, lado="d"):
    """((x, z, y), (x, z, y)) del pasador de detrás, paralelo al larguero de
    delante y con la mitad a cada lado de la raíz."""
    m = _desmontable(d)
    diametro, f, medio = m["pasador"]
    y_raiz = _estaciones(d)[d["raiz"]][0]
    x, z, c, t, p = _estacion(d, y_raiz)
    cx, cz = _girado(f, _comba(p, f), x, z, c, t)
    u = _deslizar(d, lado)
    k = medio / u[2]
    return ((cx - u[0] * k, cz - u[1] * k, y_raiz - medio),
            (cx + u[0] * k, cz + u[1] * k, y_raiz + medio))


def tornillo_raiz(d, lado="d"):
    """((x, z, y) de la cabeza, del final) del M3 que sujeta un ala desmontable:
    a lo largo de x, desde el borde de ataque de la raíz, cruzando el manguito
    por su eje neutro (a la altura de su eje). 12 mm más allá del manguito."""
    m = _desmontable(d)
    f, di = d["largueros"][0]
    y_fin = extremos_larguero(d, f, di, lado)[1][2]
    y = _estaciones(d)[d["raiz"]][0] - m["tornillo"]
    x, z, _ = _punto_eje(d, y, f, lado, y_fin)
    x_le = _estacion_centro(d, y)[0]
    return (x_le - 1, z, y), (x + m["manguito"][0] / 2 + 12, z, y)


def tubos(d) -> list[dict]:
    """Los tubos comprados, en su sitio y en (x, y, z): los largueros, los
    manguitos y pasadores de un ala desmontable y las vigas de los rotores.
    Cada uno {id, de, a, diametro}; el larguero que entra en su manguito lo
    dice en `dentro_de`."""
    m = _desmontable(d)
    out = []
    for lado, s in (("d", 1), ("i", -1)):
        def real(p, s=s):
            return (p[0], s * p[2], p[1])
        for f, di in d["largueros"]:
            de, a_ = extremos_larguero(d, f, di, lado)
            t = {"id": f"larguero-{di:g}-{lado}", "de": real(de), "a": real(a_), "diametro": di}
            if m and _principal(d, f):
                t["dentro_de"] = f"manguito-{lado}"
            out.append(t)
        if m:
            de, a_ = extremos_manguito(d, lado)
            out.append({"id": f"manguito-{lado}", "de": real(de), "a": real(a_),
                        "diametro": m["manguito"][0], "diametro_interior": m["manguito"][1]})
            de, a_ = extremos_pasador(d, lado)
            out.append({"id": f"pasador-{lado}", "de": real(de), "a": real(a_),
                        "diametro": m["pasador"][0]})
        x0, x1 = extremos_viga(d)
        y, zv = s * d["rotores"]["y"], _z_viga(d)
        out.append({"id": f"viga-{lado}", "de": (x0, y, zv), "a": (x1, y, zv),
                    "diametro": d["rotores"]["viga"]})
    return out


def _larguero(kit, d, f, diametro, puntas=False, pared=0.0, lado="d"):
    """El agujero de un larguero (`extremos_larguero`). Con `puntas`, en gota
    hacia +x y hacia -x: lo que se imprime de pie sobre un corte en x no deja
    techo en el agujero. Con `pared`, la funda que lo abraza dentro del hueco
    del ala: `pared` mm más gruesa."""
    de, a_ = extremos_larguero(d, f, diametro, lado)
    return _tubo(kit, de, a_, diametro + 2 * pared, puntas)


def _tubos_centro(kit, d, lado="d", puntas=False, pared=0.0):
    """Los agujeros (o con `pared`, las fundas) de lo que cruza el cuerpo
    central, de los dos lados y ya en su sitio, para la pieza de `lado`
    dibujada en las coordenadas de la derecha. Sin alas desmontables, los
    largueros; con ellas, los manguitos y la mitad de cada pasador. Los dos
    manguitos no son reflejo uno del otro (van en tijera): en una pieza de la
    izquierda, que se dibuja a la derecha y se refleja, se cambian de sitio."""
    m = _desmontable(d)
    if m is None:
        t = _largueros(kit, d, puntas, pared)
        return t + t.espejo("xz", conservar=False)
    otro = "i" if lado == "d" else "d"

    def de_un_lado(ll):
        t = _tubo(kit, *extremos_manguito(d, ll), m["manguito"][0] + 2 * pared, puntas)
        (xa, za, ya), (xb, zb, yb) = extremos_pasador(d, ll)
        # El agujero pasa un diámetro de la raíz, donde ya no hay cuerpo: el
        # pasador va inclinado con la flecha, y su mitad cortada en recto en
        # la raíz dejaba sin taladrar una cuña de 6 mm³ (2026-11-19). La
        # funda no, que se metería en el ala.
        k = 0.5 if pared else 0.5 + m["pasador"][0] / math.dist((xa, za, ya), (xb, zb, yb))
        fin = (xa + k * (xb - xa), za + k * (zb - za), ya + k * (yb - ya))
        return t + _tubo(kit, (xa, za, ya), fin, m["pasador"][0] + 2 * pared, puntas)
    return de_un_lado(lado) + de_un_lado(otro).espejo("xz", conservar=False)


def _tornillo_centro(kit, d, lado="d"):
    """(tetones, agujeros) del M3 que sujeta cada ala desmontable, de los dos
    lados y ya en su sitio (ver `_tubos_centro`). El tetón va de pie al
    imprimir la raíz, que se apoya en un corte en x, y acaba en cono por los
    dos lados: no sabe sobre cuál se imprime. La cabeza entra por un
    avellanado desde el borde de ataque hasta 8 mm del manguito; la rosca la
    hace el tornillo en el PETG, en un agujero de Ø2,5 al otro lado."""
    m = _desmontable(d)
    otro = "i" if lado == "d" else "d"
    r = (m["manguito"][0] + HOLGURA_TUBO) / 2

    def de_un_lado(ll):
        (xa, z, y), (xb, _, _) = tornillo_raiz(d, ll)
        xm = xb - m["manguito"][0] / 2 - 12
        teton = kit.cilindro(10, xb - xa, en=(xa, y, z), eje="x") + kit.cono(
            10, 0, 5, en=(xb, y, z), eje="x")
        xc = xm - r - 8
        hueco = (kit.cilindro(6.5, xc - xa + 1, en=(xa - 1, y, z), eje="x")
                 + kit.cono(6.5, 0, 3.25, en=(xc, y, z), eje="x")
                 + kit.cilindro(3.3, xm + r + 1 - xc, en=(xc, y, z), eje="x")
                 + kit.cilindro(2.5, xb - 1 - (xm + r), en=(xm + r, y, z), eje="x"))
        return teton, hueco
    t1, h1 = de_un_lado(lado)
    t2, h2 = de_un_lado(otro)
    return (t1 + t2.espejo("xz", conservar=False), h1 + h2.espejo("xz", conservar=False))


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


def _largueros(kit, d, puntas=False, pared=0.0, desde=None, lado="d"):
    """Los de `_larguero`, todos; con `desde`, solo los que pasan de esa y
    (en el lado derecho)."""
    hueco = None
    for f, diametro in d["largueros"]:
        if desde is not None and extremos_larguero(d, f, diametro)[1][2] <= desde:
            continue
        t = _larguero(kit, d, f, diametro, puntas, pared, lado)
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


def largo_varilla(d) -> float:
    """Los mm de varilla de Ø2 que pide el avión: la de cada elevón de varios
    trozos, de los dos lados, y 2·MEDIA_GUIA por guía del cuerpo central."""
    largo = 2 * MEDIA_GUIA * len(guias(d))
    for g in d.get("elevones", []):
        if len(g) > 1:
            largo += 2 * math.dist(*_extremos_varilla(d, g))
    return largo


def _extremos_varilla(d, tramos):
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
    return punto(y0), punto(y1)


def _varilla(kit, d, tramos, hueco=True):
    """La varilla de carbono que une los trozos de un elevón: a 4 mm detrás
    de la bisagra, de 5 mm dentro del primero a 5 mm antes del final del
    último. Los agujeros son ciegos: la varilla queda dentro."""
    return _tubo(kit, *_extremos_varilla(d, tramos), VARILLA_ELEVON,
                 holgura=HOLGURA_TUBO if hueco else 0)


def guias(d) -> list[tuple[int, str]]:
    """[(k, lado)] de las guías del cuerpo central: en el corte entre la celda
    k y la k + 1, una varilla de Ø2 por lado (izquierda, derecha, arriba y
    abajo). Él, el 2026-11-16, a si se añadían guías entre las celdas, que se
    pegaban a tope: «Sí, añádelas». Abajo no donde el corte cae junto a la
    boca de la panza: allí no hay pared, y el taco se quedaba en el aire."""
    cortes = [c for i, c in sorted(_celdas(d).items(), key=lambda t: t[1][0])
              if i.startswith("centro")]
    x0, x1, _ = panza(d)
    lista = []
    for k, c in enumerate(cortes[:-1], 1):
        xc = c[1]
        lados = ["izquierda", "derecha", "arriba"]
        if not x0 - 30 < xc < x1 + 30:
            lados.append("abajo")
        lista += [(k, lado) for lado in lados]
    return lista


def _guias_en(kit, d, k=None) -> list[tuple[float, float, float, str]]:
    """[(x, y, z, lado)] del eje de cada guía (de la del corte k, si se dice),
    a TACO_GUIA/2 − SOLAPE_TACO por dentro de la piel tal como sale en el
    corte: la transición del fuselaje se sale de las secciones del diseño, y
    un taco puesto con ellas quedaba suelto en el hueco."""
    import FreeCAD
    # Lo medido se guarda, como la piel: cada celda lo pedía cortando el
    # fuselaje entero una vez por guía.
    clave = json.dumps([d["fuselaje"], d.get("z_fuselaje"), guias(d), _celdas(d)], default=str)
    if clave not in _GUIAS_MEDIDAS:
        forma = _fuselaje(kit, d)._forma
        celdas = _celdas(d)
        dentro_ = PARED + TACO_GUIA / 2 - SOLAPE_TACO
        cajas, lista = {}, []
        for kk, lado in guias(d):
            xc = celdas[f"centro-{kk}"][1]
            if xc not in cajas:
                cortes = forma.slice(FreeCAD.Vector(1, 0, 0), xc)
                cajas[xc] = cortes[0].BoundBox
                for c in cortes[1:]:
                    cajas[xc].add(c.BoundBox)
            caja = cajas[xc]
            zm = (caja.ZMin + caja.ZMax) / 2
            y, z = {"izquierda": (caja.YMin + dentro_, zm), "derecha": (caja.YMax - dentro_, zm),
                    "arriba": (0.0, caja.ZMax - dentro_),
                    "abajo": (0.0, caja.ZMin + dentro_)}[lado]
            lista.append((kk, (xc, y, z, lado)))
        _GUIAS_MEDIDAS[clave] = lista
    return [g for kk, g in _GUIAS_MEDIDAS[clave] if k is None or kk == k]


_GUIAS_MEDIDAS: dict = {}


def _tacos(kit, d, x0, x1):
    """Los tacos de las guías que caen en la celda de x0 a x1 (cada uno, la
    mitad que le toca), y los agujeros de sus varillas."""
    tacos = agujeros = None
    for xc, y, z, _ in _guias_en(kit, d):
        if abs(xc - x0) < 1e-6:
            t = kit.cilindro(TACO_GUIA, MEDIO_TACO, en=(xc, y, z), eje="x") + kit.cono(
                TACO_GUIA, 0, PUNTA_TACO, en=(xc + MEDIO_TACO, y, z), eje="x")
        elif abs(xc - x1) < 1e-6:
            t = kit.cilindro(TACO_GUIA, MEDIO_TACO, en=(xc - MEDIO_TACO, y, z), eje="x") + kit.cono(
                TACO_GUIA, 0, PUNTA_TACO, en=(xc - MEDIO_TACO, y, z), eje="-x")
        else:
            continue
        a = kit.cilindro(VARILLA_ELEVON + HOLGURA_TUBO, 2 * MEDIA_GUIA,
                         en=(xc - MEDIA_GUIA, y, z), eje="x")
        tacos = t if tacos is None else tacos + t
        agujeros = a if agujeros is None else agujeros + a
    return tacos, agujeros


def dentro(kit, d, que):
    """El cuerpo de `que`: una de las cosas de `dentro` con caja (la batería,
    la carga, la electrónica, un servo), `canal-d`/`canal-i`,
    `varilla-d`/`varilla-i` o `guia-k-lado` (la varilla de ese lado en el
    corte k del cuerpo central). Para verlas en su sitio y comprobar que
    caben."""
    if que.startswith("guia-"):
        # Una varilla cada vez: las de un corte juntas son varios sólidos, y
        # el sistema no construye una pieza que no sea uno (2026-11-17).
        _, k, lado = que.split("-", 2)
        lados = [ll for kk, ll in guias(d) if kk == int(k)]
        if lado not in lados:
            raise _error(f"el corte {k} no lleva guía {lado!r}: lleva "
                         + (", ".join(lados[:-1]) + " y " + lados[-1] if lados else "ninguna"))
        xc, y, z, _ = next(g for g in _guias_en(kit, d, int(k)) if g[3] == lado)
        return kit.cilindro(VARILLA_ELEVON, 2 * MEDIA_GUIA, en=(xc - MEDIA_GUIA, y, z), eje="x")
    if que.startswith("tubo-"):
        # Un tubo comprado (`tubos`), sólido y a su medida: para medir que no
        # atraviesa ninguna pieza (F13.8 (choques)).
        t = {t["id"]: t for t in tubos(d)}.get(que[5:])
        if t is None:
            raise _error(f"el avión no tiene el tubo {que[5:]!r}: tiene "
                         + ", ".join(x["id"] for x in tubos(d)))
        (xa, ya, za), (xb, yb, zb) = t["de"], t["a"]
        lleno = _tubo(kit, (xa, za, ya), (xb, zb, yb), t["diametro"], holgura=0)
        if t.get("diametro_interior"):
            lleno = lleno - _tubo(kit, (xa, za, ya), (xb, zb, yb), t["diametro_interior"],
                                  holgura=0)
        return lleno
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


def _cuerpo_central(kit, d, celda=None, lado="d"):
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
    hueco_ala = hueco_ala - _tubos_centro(kit, d, lado, puntas=True, pared=FUNDA)
    tornillos = _tornillo_centro(kit, d, lado) if _desmontable(d) else None
    if tornillos is not None:
        hueco_ala = hueco_ala - tornillos[0]
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
    agujeros = None
    if celda is not None:
        tacos, agujeros = _tacos(kit, d, celda[0], celda[1])
        if tacos is not None:
            cuerpo = cuerpo + tacos
    cuerpo = cuerpo - _tubos_centro(kit, d, lado, puntas=True)
    if tornillos is not None:
        cuerpo = cuerpo - tornillos[1]
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
    if agujeros is not None:
        cuerpo = cuerpo - agujeros
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
                     en=(x0, s * d.get("quilla_y", QUILLA_Y) - PIEL_ALA, zc - 300)) & hueco
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


def _seccion_aplastada(kit, x, z, c, t, p, desde, hasta, piel):
    """La sección hueca con su alto llevado casi a cero hacia la línea media
    del perfil: el final de un hueco en tejado."""
    cont = contorno_hueco(p, c, piel, desde, hasta)
    if cont is None:
        return None
    return kit.seccion([_girado(u, _comba(p, u) + (v - _comba(p, u)) * 0.03, x, z, c, t)
                        for u, v in cont])


def _hueco_tramo(kit, d, y0, y1, i, elevon, punta, piel=PIEL_ALA, raiz_cerrada=False,
                 fuera_cerrada=False):
    """El hueco de un tramo del ala exterior: abierto por sus dos caras salvo
    en la punta, que acaba cerrada. Dos celdas, delante y detrás del alma; la
    de detrás no la llevan los tramos con elevón, que ahí tienen la bisagra.

    Con las juntas cerradas (F13.9 (juntas)), al compararlo con el Stallion de
    Flightory (2026-11-18): abiertas, dos tramos se pegaban solo por el canto
    de su piel de 0,6 mm (de 326 a 570 mm², medido ese día; las del Stallion,
    de 1 394 a 3 534). Con `raiz_cerrada`, una costilla en la raíz, que de pie
    es lo primero que se imprime; con `fuera_cerrada`, el hueco acaba en
    tejado hacia la línea media del perfil, a 40° de la vertical al imprimirlo
    de pie (una costilla arriba sería un techo de toda la cuerda)."""
    ya = y0 + piel if raiz_cerrada else y0 - 1
    yb = y1 - PIEL_ALA if punta or fuera_cerrada else y1 + 1
    m = _mandos(d)
    celdas = [(0.0, CUERDA_ALMA)] + ([] if elevon else [(CUERDA_ALMA, 1.0)])
    hueco = None
    for desde, hasta in celdas:
        def limites(y, c, desde=desde, hasta=hasta):
            e = piel / 2 / c
            h = hasta
            if elevon and m and hasta < 1:
                # Delante de la bisagra, BANDA_BISAGRA maciza para las bisagras de chapa.
                h = min(hasta, d["elevon"][1] - (BANDA_BISAGRA + HOLGURA_BISAGRA) / c)
            return desde + (e if desde else 0), h - (e if h < 1 else 0)

        def seccion(y, aplastada=False):
            x, z, c, t, p = _estacion(d, y, i)
            a, b = limites(y, c)
            if aplastada:
                return _seccion_aplastada(kit, x, z, c, t, p, a, b, piel)
            return _seccion_hueca(kit, x, z, c, t, p, a, b, piel=piel)
        if fuera_cerrada and not punta:
            x, z, c, t, p = _estacion(d, yb, i)
            alto = max((_grueso(p, u / 40) * c for u in range(41)), default=0) / 2
            y_tejado = yb - 1.2 * alto
            tramos = [(seccion(ya), ya), (seccion(y_tejado), y_tejado),
                      (seccion(yb, aplastada=True), yb)]
        else:
            tramos = [(seccion(ya), ya), (seccion(yb), yb)]
        if any(s is None for s, _ in tramos):
            continue
        celda = kit.transicion(tramos, eje="y", recta=fuera_cerrada and not punta)
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


MANDOS = {"bisel": 30.0}
"""Los mandos de los elevones (F13.10 (mandos)), al compararlo con el Stallion
de Flightory (2026-11-18). Con el corte recto, la esquina de abajo del elevón
tocaba el ala a los 10,6° (contado a mano en y = 433); con el frente del
elevón en V a `bisel` grados del eje de la bisagra, no toca mientras baje o
suba menos que eso. Se piden ±25° libres (criterio del asistente)."""
BANDA_BISAGRA = 8.0
"""Lo macizo del ala delante de la bisagra, donde entran las bisagras de chapa:
con el alma al 72 % quedaban de 4,8 a 7,6 mm."""
BISAGRA_CHAPA = (26.0, 0.8, 7.5, 10.0)
"""La ranura de una bisagra de chapa de 25 × 20 (las del Stallion): largo a lo
largo de la bisagra, grueso, y lo que entra en el ala y en el elevón."""
CUERNO = (9.0, 19.0, 1.6)
"""Los dos agujeros del cuerno del elevón, por debajo y a la altura de su
servo: a 9 y 19 mm detrás de la bisagra, de Ø1,6 para tornillos de M2."""


def _mandos(d):
    m = d.get("mandos")
    if not m:
        return None
    return {**MANDOS, **(m if isinstance(m, dict) else {})}


def recorrido_elevon(d, y) -> float:
    """Los grados que el elevón puede bajar o subir en `y` antes de que su
    frente toque la cara de atrás del ala (el menor de los dos). La bisagra
    va a media altura del perfil, en la línea de bisagra; el ala acaba en
    una cara plana HOLGURA_BISAGRA por delante, y el elevón empieza otro tanto
    por detrás, recto o en V (`mandos`)."""
    x, z, c, t, p = _estacion(d, y)
    f = d["elevon"][1]
    arriba, abajo = _caras(_perfil(p))
    vc = _comba(p, f)
    h_arriba, h_abajo = (_en(arriba, f) - vc) * c, (vc - _en(abajo, f)) * c
    g = HOLGURA_BISAGRA
    m = _mandos(d)
    tb = math.tan(math.radians(m["bisel"])) if m else 0.0
    frente = [(g + abs(dz) * tb, dz) for dz in
              [-h_abajo + (h_arriba + h_abajo) * k / 40 for k in range(41)]]
    libre = []
    for signo in (1, -1):
        theta = 0.0
        while theta < 90:
            a = math.radians(signo * (theta + 0.05))
            toca = False
            for dx, dz in frente:
                xr = dx * math.cos(a) + dz * math.sin(a)
                zr = -dx * math.sin(a) + dz * math.cos(a)
                if xr < -g and -h_abajo <= zr <= h_arriba:
                    toca = True
                    break
            if toca:
                break
            theta += 0.05
        libre.append(theta)
    return min(libre)


def _servo_de_tramo(d, k):
    y0, y1, _ = _tramos_ala(d)[k - 1]
    return next((s for s in _servos(d) if y0 < s["y"] < y1), None)


def mandos(d, k) -> dict:
    """Dónde van las bisagras de chapa (y) y el cuerno del elevón del tramo `k`."""
    y0, y1, _ = _tramos_ala(d)[k - 1]
    s = _servo_de_tramo(d, k)
    return {"bisagras": [y0 + (y1 - y0) * q for q in (0.2, 0.5, 0.8)],
            "cuerno": {"y": s["y"] if s else (y0 + y1) / 2}}


def _ejes_bisagra(d, y, i):
    """(punto de la bisagra (x, y, z), a lo largo de ella, hacia atrás por la
    cuerda, hacia arriba): unitarios y a derechas."""
    f = d["elevon"][1]

    def punto(yy):
        x, z, c, t, p = _estacion(d, yy, i)
        px, pz = _girado(f, _comba(p, f), x, z, c, t)
        return (px, yy, pz), (x, z, c, t, p)
    h, (x, z, c, t, p) = punto(y)
    h1, _ = punto(y + 1)
    e = [h1[k] - h[k] for k in range(3)]
    ne = math.sqrt(sum(v * v for v in e))
    e = [v / ne for v in e]
    qx, qz = _girado(f + 0.1, _comba(p, f), x, z, c, t)
    cu = [qx - h[0], 0.0, qz - h[2]]
    n = [e[1] * cu[2] - e[2] * cu[1], e[2] * cu[0] - e[0] * cu[2], e[0] * cu[1] - e[1] * cu[0]]
    nn = math.sqrt(sum(v * v for v in n))
    n = [v / nn for v in n]
    if n[2] < 0:
        n = [-v for v in n]
    cu = [n[1] * e[2] - n[2] * e[1], n[2] * e[0] - n[0] * e[2], n[0] * e[1] - n[1] * e[0]]
    return h, e, cu, n


def _caja_local(kit, o, ex, ey, ez, lx, ly, lz):
    """Una caja de lx × ly × lz con su esquina en `o` y sus lados por los ejes
    unitarios ex, ey, ez (a derechas)."""
    import FreeCAD
    import Part
    from mech_toolkit.kit import Cuerpo
    m = FreeCAD.Matrix(ex[0], ey[0], ez[0], o[0], ex[1], ey[1], ez[1], o[1],
                       ex[2], ey[2], ez[2], o[2], 0, 0, 0, 1)
    caja = Part.makeBox(lx, ly, lz)
    caja.transformShape(m)
    return Cuerpo(caja, kit)


def _ranuras_bisagra(kit, d, k):
    """Las ranuras de las tres bisagras de chapa del elevón del tramo `k`: a
    media altura, la mitad de cada una en el ala y la otra en el elevón."""
    _, _, i = _tramos_ala(d)[k - 1]
    largo, grueso, en_ala, en_elevon = BISAGRA_CHAPA
    g = HOLGURA_BISAGRA
    todas = None
    for y in mandos(d, k)["bisagras"]:
        h, e, cu, n = _ejes_bisagra(d, y, i)
        o = [h[j] - e[j] * largo / 2 - cu[j] * (g + en_ala) - n[j] * grueso / 2 for j in range(3)]
        r = _caja_local(kit, o, e, cu, n, largo, 2 * g + en_ala + en_elevon, grueso)
        todas = r if todas is None else todas + r
    return todas


def _cuerno(kit, d, k):
    """Los dos agujeros del cuerno, por debajo del elevón del tramo `k`."""
    _, _, i = _tramos_ala(d)[k - 1]
    y = mandos(d, k)["cuerno"]["y"]
    h, e, cu, n = _ejes_bisagra(d, y, i)
    x, z, c, t, p = _estacion(d, y, i)
    f = d["elevon"][1]
    a, b, diametro = CUERNO
    todos = None
    for s in (a, b):
        hl = _grueso(p, f + s / c) * c
        # Ciego: entra desde abajo hasta 1,2 mm de la cara de arriba.
        top = [h[j] + cu[j] * s + n[j] * (hl / 2 - 1.2) for j in range(3)]
        hueco = _cilindro_hacia(kit, diametro, hl + 5, top, [-v for v in n])
        todos = hueco if todos is None else todos + hueco
    return todos


def _cilindro_hacia(kit, diametro, largo, base, eje):
    """Un cilindro desde `base` (x, y, z) a lo largo del vector unitario `eje`."""
    import FreeCAD
    import Part
    from mech_toolkit.kit import Cuerpo
    return Cuerpo(Part.makeCylinder(diametro / 2, largo, FreeCAD.Vector(*base),
                                    FreeCAD.Vector(*eje)), kit)


def _elevon_v(kit, d, y0, y1, i):
    """Todo lo que queda detrás del frente en V del elevón, de `y0` a `y1`."""
    tb = math.tan(math.radians(_mandos(d)["bisel"]))
    f = d["elevon"][1]
    secs = []
    for y in (y0 - 1, y1 + 1):
        x, z, c, t, p = _estacion(d, y, i)
        g, vc, alto = HOLGURA_BISAGRA / c, _comba(p, f), 0.3
        puntos = [(f + g, vc), (f + g + alto * tb, vc + alto), (2.0, vc + alto),
                  (2.0, vc - alto), (f + g + alto * tb, vc - alto)]
        secs.append((kit.seccion([_girado(u, v, x, z, c, t) for u, v in puntos]), y))
    return kit.transicion(secs, eje="y", recta=True)


TUBO_INTERIOR = {16.0: 12.0, 12.0: 10.0, 10.0: 8.0, 6.0: 4.0}
"""El diámetro de dentro de los tubos de la lista de compras (de 1 mm de pared)."""
E_CARBONO = 100000.0
"""N/mm²: el módulo de un tubo de carbono pultruido, supuesto del asistente
(el anuncio no lo da)."""


def seccion_tubo(diametro, interior) -> tuple[float, float]:
    """(I en mm⁴, W en mm³) de un tubo."""
    i = math.pi * (diametro ** 4 - interior ** 4) / 64
    return i, i / (diametro / 2)


def _cuerda_planta(d, y):
    est = d["estaciones"]
    for a, b in zip(est, est[1:]):
        if a[0] <= y <= b[0]:
            return a[3] + (b[3] - a[3]) * (y - a[0]) / (b[0] - a[0])
    return est[-1][3]


def momento_flector(d, sustentacion, y0, pasos=2000) -> float:
    """N·m en `y0` (mm) de media ala que sustenta `sustentacion` N, repartida
    por el método de Schrenk: la media de la forma en planta (las cuerdas de
    `estaciones`) y de una elipse."""
    est = d["estaciones"]
    s = est[-1][0]
    dy = s / pasos
    ys = [(k + 0.5) * dy for k in range(pasos)]
    area = sum(_cuerda_planta(d, y) for y in ys) * dy
    m = 0.0
    for y in ys:
        if y <= y0:
            continue
        carga = sustentacion / 2 * (_cuerda_planta(d, y) / area
                                    + 4 / (math.pi * s) * math.sqrt(max(0.0, 1 - (y / s) ** 2)))
        m += carga * (y - y0) * dy
    return m / 1000


def esfuerzos(d, n=4.0) -> dict:
    """Lo que trabajan los tubos de carbono a `n` g con la masa de `dentro`
    (criterio del asistente: 4 g). Los largueros en la raíz del ala exterior,
    repartiendo el momento por su rigidez; el manguito de un ala desmontable
    con todo el momento del centro; cada viga en voladizo desde su pilón con
    un motor a fondo (`rotores.empuje_kg`). Y la flecha de la punta a 1 g."""
    masa = equilibrio(d)["masa_kg"]
    media = n * masa * 9.81 / 2
    y_raiz = _estaciones(d)[d["raiz"]][0]
    tubos = {}
    secciones = {di: seccion_tubo(di, TUBO_INTERIOR[float(di)]) for _, di in d["largueros"]}
    rigidez = sum(i for i, _ in secciones.values())
    m_raiz = momento_flector(d, media, y_raiz)
    for _, di in d["largueros"]:
        i, w = secciones[di]
        tubos[f"larguero-{di:g}"] = {"mpa": m_raiz * 1000 * i / rigidez / w, "n_m": m_raiz,
                                     "donde": f"y = {y_raiz:g}"}
    m = _desmontable(d)
    if m:
        _, w = seccion_tubo(*m["manguito"])
        m0 = momento_flector(d, media, 0.0)
        tubos["manguito"] = {"mpa": m0 * 1000 / w, "n_m": m0, "donde": "y = 0"}
    ro = d["rotores"]
    if ro.get("empuje_kg"):
        x, z, c, t, p = _estacion(d, ro["y"])
        _, w = seccion_tubo(ro["viga"], TUBO_INTERIOR[float(ro["viga"])])
        x0, x1 = x + 0.12 * c, x + 0.88 * c
        brazo = max(x0 - ro["x"][0], ro["x"][1] - x1)
        tubos["viga"] = {"mpa": ro["empuje_kg"] * 9.81 * brazo / w,
                         "n_m": ro["empuje_kg"] * 9.81 * brazo / 1000,
                         "donde": f"a {brazo:.0f} mm del pilón"}
    # La flecha a 1 g: el ala exterior en voladizo desde su raíz.
    s = d["estaciones"][-1][0]
    pasos = 200
    dy = (s - y_raiz) / pasos
    giro = flecha = 0.0
    for k in range(pasos):
        y = y_raiz + (k + 0.5) * dy
        curva = momento_flector(d, masa * 9.81 / 2, y, pasos=400) * 1000 / (E_CARBONO * rigidez)
        giro += curva * dy
        flecha += giro * dy
    return {"n": n, "masa_kg": masa, "tubos": tubos, "flecha_punta_mm_1g": flecha}


def _tramo(kit, d, k):
    y0, y1, i = _tramos_ala(d)[k - 1]
    return y0, y1, i, _ala_entre(kit, d, y0, y1, i)


def _con_punta(d, k):
    """Si el tramo `k` lleva pegada la punta levantada (`punta_unida`): él, el
    2026-11-18, «Sí, bájalas», con una cama de 300 × 300 × 330. El último tramo
    del avión de ese día (de 646,7 a 860) y su punta (de 860 a 945) miden
    juntos 298,3 de alto de pie sobre la raíz, y de huella unos 270 × 110:
    caben, y son dos piezas menos."""
    tramos = _tramos_ala(d)
    return (bool(d.get("punta_unida")) and k < len(tramos)
            and _levantado(d, tramos[k][2]) and not _levantado(d, tramos[k - 1][2]))


def _z_viga(d):
    """El centro de la viga: bajo la cara de abajo del ala donde pasa la viga,
    con sitio para el pilón."""
    y = d["rotores"]["y"]
    x, z, c, t, p = _estacion(d, y)
    _, abajo = _caras(_perfil(p))
    bajo = min(_girado(u, v, x, z, c, t)[1] for u, v in abajo if 0.1 <= u <= 0.9)
    return bajo - d["rotores"]["viga"] / 2 - 10


MOTOR_SUBIR = (50.0, 30.0)
"""Ø y alto del motor 4312 de sustentación; MOTOR_EMPUJE, los del 3510. Son
supuestos del asistente para verlo montado: los anuncios no dan el plano."""
MOTOR_EMPUJE = (42.0, 25.0)
SOBRE_EL_MOTOR = 5.0
"""Del motor a la pala: el buje de la hélice."""


def _cilindro_tris(p0, eje, largo, radio, n=24):
    """Un cilindro cerrado en triángulos, de `p0` a lo largo de `eje` (unitario)."""
    a = (1.0, 0.0, 0.0) if abs(eje[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (eje[1] * a[2] - eje[2] * a[1], eje[2] * a[0] - eje[0] * a[2], eje[0] * a[1] - eje[1] * a[0])
    nu = math.sqrt(sum(c * c for c in u))
    u = tuple(c / nu for c in u)
    v = (eje[1] * u[2] - eje[2] * u[1], eje[2] * u[0] - eje[0] * u[2], eje[0] * u[1] - eje[1] * u[0])

    def punto(k, h):
        t = 2 * math.pi * k / n
        return tuple(p0[i] + eje[i] * h + radio * (math.cos(t) * u[i] + math.sin(t) * v[i])
                     for i in range(3))
    abajo, arriba = p0, tuple(p0[i] + eje[i] * largo for i in range(3))
    tris = []
    for k in range(n):
        a0, a1, b0, b1 = punto(k, 0), punto(k + 1, 0), punto(k, largo), punto(k + 1, largo)
        tris += [(a0, a1, b1), (a0, b1, b0), (abajo, a1, a0), (arriba, b0, b1)]
    return tris


def _pala_tris(centro, largo_dir, normal, diametro, grueso=3.0, n=16):
    """Una hélice de dos palas, plana: un huso de `diametro` de punta a punta
    a lo largo de `largo_dir`, y de grueso `grueso` según `normal`."""
    ancho = (normal[1] * largo_dir[2] - normal[2] * largo_dir[1],
             normal[2] * largo_dir[0] - normal[0] * largo_dir[2],
             normal[0] * largo_dir[1] - normal[1] * largo_dir[0])
    r, w = diametro / 2, 0.06 * diametro
    contorno = []
    for k in range(2 * n):
        t = 2 * math.pi * k / (2 * n)
        s, q = r * math.cos(t), w * math.sin(t) * (0.35 + 0.65 * abs(math.cos(t)))
        contorno.append(tuple(centro[i] + s * largo_dir[i] + q * ancho[i] for i in range(3)))

    def subir(p, h):
        return tuple(p[i] + h * normal[i] for i in range(3))
    tris = []
    for k in range(len(contorno)):
        a, b = contorno[k], contorno[(k + 1) % len(contorno)]
        tris += [(centro, a, b), (subir(centro, grueso), subir(b, grueso), subir(a, grueso)),
                 (a, subir(b, grueso), b), (a, subir(a, grueso), subir(b, grueso))]
    return tris


def extremos_viga(d) -> tuple[float, float]:
    """(x de delante, x de atrás) de cada viga de carbono. Con `aletas`, de la
    punta de la pata a la de la deriva, que van en las góndolas; si no, de
    punta a punta de las góndolas (y la deriva, detrás, se quedaba sin viga
    en 120 mm: visto el 2026-11-17)."""
    ro = d["rotores"]
    if ro.get("aletas"):
        pata = d.get("pata", {}).get("cuerda", PATA_CUERDA)
        return ro["x"][0] - pata[0] / 2, ro["x"][1] + d["deriva"]["cuerda"][0] / 2
    return ro["x"][0] - MEDIO_LARGO_GONDOLA, ro["x"][1] + MEDIO_LARGO_GONDOLA


def comprado_a_la_vista(d) -> dict[str, list]:
    """Lo comprado que se ve por fuera, en triángulos y en su sitio: las dos
    vigas de carbono, los cinco motores y sus hélices. Solo para enseñarlo
    montado: sin ellos, la vista del avión dejaba las góndolas y las derivas
    sueltas junto al ala (él, 2026-11-17: «no se entiende qué son»)."""
    ro = d["rotores"]
    zv, dv = _z_viga(d), ro["viga"]
    arriba = zv + dv / 2 + 12          # la cara de arriba de la góndola (`_gondola`)
    motor = ro.get("motor", MOTOR_SUBIR)
    out = {}
    for lado, s in (("d", 1), ("i", -1)):
        y = s * ro["y"]
        x0, x1 = extremos_viga(d)
        out[f"viga-{lado}"] = _cilindro_tris((x0, y, zv), (1, 0, 0), x1 - x0, dv / 2)
        for donde, x in (("delante", ro["x"][0]), ("detras", ro["x"][1])):
            out[f"motor-{lado}-{donde}"] = _cilindro_tris((x, y, arriba), (0, 0, 1),
                                                          motor[1], motor[0] / 2)
            g = 1 / math.sqrt(2)
            out[f"helice-{lado}-{donde}"] = _pala_tris(
                (x, y, arriba + motor[1] + SOBRE_EL_MOTOR), (g, s * g, 0), (0, 0, 1),
                ro["helice"])
    # Los largueros, manguitos y pasadores van dentro del ala y no salen en la
    # foto, pero en FreeCAD, escondida el ala, se ve cómo se enchufa
    # (F13.14 (ensamble)).
    for t in tubos(d):
        if t["id"].startswith("viga"):
            continue
        largo = math.dist(t["de"], t["a"])
        eje = tuple((b - a) / largo for a, b in zip(t["de"], t["a"]))
        out[t["id"]] = _cilindro_tris(t["de"], eje, largo, t["diametro"] / 2)
    xe, zf = d["empuje"]["x"], d["z_fuselaje"]
    out["motor-empuje"] = _cilindro_tris((xe, 0, zf), (1, 0, 0), MOTOR_EMPUJE[1],
                                         MOTOR_EMPUJE[0] / 2)
    out["helice-empuje"] = _pala_tris((xe + MOTOR_EMPUJE[1] + SOBRE_EL_MOTOR, 0, zf), (0, 0, 1),
                                      (1, 0, 0), d["empuje"]["helice"])
    return out


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


HOLGURA_PILON = 0.4
PILON_TORNILLOS = (14.0, 9.0)
"""Los dos M3 del pilón atornillado (F13.12 (pilón)): a 14 mm a cada lado del
eje de la viga, para no tocarla (radio 8,15) ni dejar sin pared la tuerca, y
9 mm delante y detrás del eje del larguero de Ø10, pegados a su funda."""


def _tornillos_pilon_en(d):
    """[(x, y)] de los dos M3 del pilón atornillado."""
    ro = d["rotores"]
    f, di = d["largueros"][0]
    dy, dx = PILON_TORNILLOS
    out = []
    for s in (-1, 1):
        y = ro["y"] + s * dy
        x = _punto_larguero(d, y, f)[0] + s * dx
        out.append((x, y))
    return out


def _ancho_pilon(d):
    dv = d["rotores"]["viga"]
    return 2 * (PILON_TORNILLOS[0] + 6) if d.get("pilon_atornillado") else dv + 8


def _tetones_pilon(kit, d):
    """Dentro del ala, un tetón en rombo por cada M3 del pilón, de la piel de
    abajo a la de arriba y pegado a la funda del larguero: así el empuje de
    los rotores pasa al larguero y no cuelga de 0,6 mm de piel (en el
    Stallion, el larguero pasa por el brazo del motor). Sus caras van a 40°
    de la vertical al imprimir el tramo de pie."""
    todos = None
    for x, y in _tornillos_pilon_en(d):
        arriba, abajo = _caras_en(d, y)
        zs, zi = _z_cara(arriba, x), _z_cara(abajo, x)
        r = (zs - zi) / 2 + 1
        h = r / math.tan(math.radians(40))
        zm = (zs + zi) / 2
        t = kit.extruir([(y - h, zm), (y, zm - r), (y + h, zm), (y, zm + r)], 8, plano="yz",
                        desde=x - 4)
        todos = t if todos is None else todos + t
    return todos


def _tornillos_pilon(kit, d):
    """Los agujeros de los M3 del pilón: verticales, de arriba del ala al fondo
    del pilón (la cabeza arriba, sobre el tetón)."""
    todos = None
    for x, y in _tornillos_pilon_en(d):
        t = kit.cilindro(3.3, 300, en=(x, y, -150))
        todos = t if todos is None else todos + t
    return todos


def _pilon(kit, d):
    """Une la viga al ala: una placa que por arriba copia la cara de abajo del
    ala. Restarle el ala a un bloque dejaba trozos sueltos (2026-11-16). Copia
    la de los dos lados de la placa: con el diedro, la cara del ala baja
    0,06 mm por mm hacia dentro. Atornillado (F13.12 (pilón)), es más ancho y
    lleva la tuerca de cada M3 en un hueco por debajo."""
    ro = d["rotores"]
    y, zv, dv = ro["y"], _z_viga(d), ro["viga"]
    if not d.get("pilon_atornillado"):
        # Pegado, la extrusión de una sección, como antes: la transición de
        # abajo, con el diedro, le dejaba al derecho un borde en el aire
        # (pedía soportes en `test_avion_formas`, 2026-11-19).
        x, z, c, t, p = _estacion(d, y)
        _, abajo = _caras(_perfil(p))
        cara = [_girado(u, v, x, z, c, t) for u, v in abajo if 0.12 <= u <= 0.88]
        contorno = [(cara[0][0], zv - 2), (cara[-1][0], zv - 2)] + list(reversed(cara))
        placa = kit.extruir(contorno, dv + 8, plano="xz", desde=y - (dv + 8) / 2)
        return placa - kit.cilindro(dv + HOLGURA_TUBO, 2 * c, en=(x - c / 2, y, zv), eje="x")
    ancho = _ancho_pilon(d)
    # Atornillado, 0,4 mm por debajo del ala: la placa reglada entre sus dos
    # bordes y el ala, transición de secciones con torsión, no coinciden, y
    # con 40 mm de ancho se cruzaban 627 mm³ (2026-11-19); con 0,2 aún
    # quedaban 2,4, donde la cara curva junto al borde de ataque se copia con
    # tramos rectos. Pegado copiaba la cara; atornillado, el tornillo cierra
    # esa holgura.
    baja = HOLGURA_PILON if d.get("pilon_atornillado") else 0.0
    secs = []
    for yy in (y - ancho / 2, y + ancho / 2):
        x, z, c, t, p = _estacion(d, yy)
        _, abajo = _caras(_perfil(p))
        cara = [(px, pz - baja) for px, pz in
                (_girado(u, v, x, z, c, t) for u, v in abajo if 0.12 <= u <= 0.88)]
        contorno = [(cara[0][0], zv - 2), (cara[-1][0], zv - 2)] + list(reversed(cara))
        secs.append((kit.seccion(contorno), yy))
    placa = kit.transicion(secs, eje="y", recta=True)
    x, z, c, t, p = _estacion(d, y)
    placa = placa - kit.cilindro(dv + HOLGURA_TUBO, 2 * c, en=(x - c / 2, y, zv), eje="x")
    if d.get("pilon_atornillado"):
        # Atornillado se imprime como se dibuja, sobre su cara de abajo: el
        # arco de la viga, de Ø16, quedaba en el aire (726 mm², 2026-11-19).
        # Tejado hacia arriba.
        r = (dv + HOLGURA_TUBO) / 2
        k = r / math.sqrt(2)
        placa = placa - kit.extruir([(y - k, zv + k), (y + k, zv + k), (y, zv + r * math.sqrt(2))],
                                    2 * c, plano="yz", desde=x - c / 2)
        placa = placa - _tornillos_pilon(kit, d)
        for xt, yt in _tornillos_pilon_en(d):
            placa = placa - kit.hexagono(5.8, 2.6, en=(xt, yt, zv - 2.01))
    return placa


def _sin_viga(kit, d, p, x0, x1):
    """`p` con el agujero de la viga de `x0` a `x1`. Lleva tejado hacia abajo,
    que al imprimir la pieza boca abajo es arriba."""
    ro = d["rotores"]
    y, zv, dv = ro["y"], _z_viga(d), ro["viga"]
    r = (dv + HOLGURA_TUBO) / 2
    p = p - kit.cilindro(2 * r, x1 - x0 + 2, en=(x0 - 1, y, zv), eje="x")
    k = r / math.sqrt(2)
    return p - kit.extruir([(y - k, zv - k), (y + k, zv - k), (y, zv - r * math.sqrt(2))],
                           x1 - x0 + 2, plano="yz", desde=x0 - 1)


def _gondola_con_aleta(kit, d, x, cuerda, alto):
    """La góndola de un motor con la pata o la deriva debajo, centrada en él:
    una pieza. Separadas, la deriva se montaba 30 mm sobre la góndola de atrás
    (11 383 mm³ comunes, medido el 2026-11-17). El pie de la aleta sube hasta
    la cara del motor, para que toda la pieza apoye en ella boca abajo."""
    zv, dv = _z_viga(d), d["rotores"]["viga"]
    x0 = x - cuerda[0] / 2
    p = _gondola(kit, d, x) + _pie(kit, d, x0, cuerda, alto, techo=zv + dv / 2 + 12,
                                   viga=False)
    return _sin_viga(kit, d, p, x0, x0 + cuerda[0])


def _pie(kit, d, x0, cuerda, alto, techo=None, viga=True):
    """Una aleta bajo la viga (la deriva o la pata) con su pie: el pie abraza la
    viga y tiene arriba una cara plana, sobre la que se imprime boca abajo
    (en `techo`; si no, 4 mm sobre la viga). El agujero de la viga lleva
    tejado hacia abajo, que al imprimir es arriba."""
    ro = d["rotores"]
    y, zv, dv = ro["y"], _z_viga(d), ro["viga"]
    c0, c1 = cuerda
    techo = zv + dv / 2 + 4 if techo is None else techo

    def sec(x, c):
        return kit.seccion([(x + u * c, y + v * c) for u, v in _perfil("naca0008")])
    aleta = kit.transicion([(sec(x0, c0), -(zv - dv / 2)), (sec(x0 + (c0 - c1), c1),
                                                            -(zv - alto))], eje="-z")
    pie = kit.transicion([(kit.rectangulo(c0, dv + 8, 4), zv - dv / 2 - 4),
                          (kit.rectangulo(c0, dv + 8, 4), techo)],
                         eje="z", en=(x0 + c0 / 2, y, 0))
    p = aleta + pie
    return _sin_viga(kit, d, p, x0, x0 + c0) if viga else p


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
        trozo = _cuerpo_central(kit, d, (x0, x1, y0, y1),
                                "d" if partes[0] == "centro" else lado)
        return trozo if partes[0] == "centro" else _lado(trozo, lado)
    if partes[0] == "ala":
        k = int(partes[2])
        ala = _ala(kit, d, k, lado)
        if _con_punta(d, k):
            # Las dos se cortan en el mismo plano con la misma sección: el
            # hueco del tramo, abierto por su cara de fuera, sigue en el de la
            # punta, y la unión es una sola pieza.
            # Detrás de la bisagra, debajo de la punta va el hueco del elevón:
            # de pie sobre la raíz, la punta empezaba ahí en el aire, un techo
            # de 40 mm (2026-11-18). Se le quita una rampa que sube a 40° de la
            # vertical, que además deja holgura al final del elevón.
            _, y1, i = _tramos_ala(d)[k - 1]
            x, _, c, _, _ = _estacion(d, y1, i)
            xh = x + d["elevon"][1] * c - HOLGURA_BISAGRA
            rampa = kit.extruir([(xh, y1 - 1), (xh + 400, y1 - 1), (xh + 400, y1 - 1 + 1.2 * 400)],
                                600, plano="xy", desde=-300)
            ala = ala + (_ala(kit, d, k + 1, lado) - rampa)
        return _lado(ala, lado)
    if partes[0] == "elevon":
        k = int(partes[2])
        y0, y1, i, ala = _tramo(kit, d, k)
        if _mandos(d):
            elevon = ala & _elevon_v(kit, d, y0, y1, i)
            elevon = elevon - _ranuras_bisagra(kit, d, k) - _cuerno(kit, d, k)
        else:
            elevon = ala & _bisagra(kit, d, y0, y1, HOLGURA_BISAGRA)
        _, trozos = _elevon_de(d, k)
        if len(trozos) > 1:
            elevon = elevon - _varilla(kit, d, trozos)
        return _lado(elevon, lado)
    return _pieza_rotores(kit, d, partes, lado)


def _ala(kit, d, k, lado="d"):
    """El tramo `k` del ala de `lado`, dibujado a la derecha, vaciado, con sus
    agujeros y su bisagra."""
    y0, y1, i, ala = _tramo(kit, d, k)
    con_elevon = _con_elevon(d, y0, y1, i)
    tramos = _tramos_ala(d)
    # Las juntas (F13.9 (juntas)): cerradas por las dos caras donde se pega
    # un tramo con otro; abiertas donde la punta va pegada en la misma pieza.
    juntas = bool(d.get("juntas"))
    raiz_cerrada = juntas and not (k > 1 and _con_punta(d, k - 1))
    fuera_cerrada = juntas and not _con_punta(d, k) and k < len(tramos)
    hueco = _hueco_tramo(kit, d, y0, y1, i, con_elevon, _levantado(d, i),
                         raiz_cerrada=raiz_cerrada, fuera_cerrada=fuera_cerrada)
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
        # Solo las fundas de los largueros que entran en el tramo más
        # que el radio de la funda. Los del avión del 2026-11-18 acaban
        # en el corte de la punta (y = 860), y por el diedro su disco
        # final asomaba 2,4 mm en ella: dos rodajas sueltas dentro del
        # hueco, y la pieza salía en tres sólidos.
        dentro = _largueros(kit, d, pared=FUNDA,
                            desde=y0 + max(di for _, di in d["largueros"]) / 2 + FUNDA,
                            lado=lado)
        if not _levantado(d, i):
            nervios = _nervios(kit, d, y0, y1, i)
            dentro = nervios if dentro is None else dentro + nervios
        for s in _servos(d):
            if y0 < s["y"] < y1:
                cajon = _cajon_servo(kit, d, s)
                dentro = cajon if dentro is None else dentro + cajon
        if k == 1 and _desmontable(d):
            dentro = dentro + _tubo(kit, *extremos_pasador(d, lado),
                                    _desmontable(d)["pasador"][0] + 2 * FUNDA)
            # Lo mismo que el agujero del Ø6 (abajo): su funda empezaba en la
            # raíz con la tapa inclinada 18°, un techo en el aire dentro del
            # hueco (10 mm², 2026-11-19). Empieza un diámetro antes, dentro
            # de la costilla.
            for f, di in d["largueros"][1:]:
                de, a_ = extremos_larguero(d, f, di, lado)
                u = [(q - p_) / math.dist(de, a_) for p_, q in zip(de, a_)]
                dentro = dentro + _tubo(kit, tuple(p_ - di * w for p_, w in zip(de, u)),
                                        tuple(p_ + 2 * di * w for p_, w in zip(de, u)),
                                        di + 2 * FUNDA)
        if d.get("pilon_atornillado") and y0 < d["rotores"]["y"] < y1:
            dentro = dentro + _tetones_pilon(kit, d)
        if dentro is None:
            ala = ala - hueco
        else:
            bb = hueco._forma.BoundBox
            dentro = dentro & kit.caja(bb.XLength + 2, bb.YLength + 2, bb.ZLength + 2,
                                       en=(bb.XMin - 1, bb.YMin - 1, bb.ZMin - 1))
            ala = (ala - hueco) + (dentro & ala)
    ala = ala - _largueros(kit, d, lado=lado)
    if k == 1 and _desmontable(d):
        ala = ala - _tubo(kit, *extremos_pasador(d, lado), _desmontable(d)["pasador"][0])
        # El Ø6 acaba a ras de la raíz, y su agujero, cortado en recto al
        # tubo, quedaba con la flecha 18° inclinado respecto a la costilla:
        # solo la cruzaba a medias, y la cuña que dejaba empezaba en el aire
        # impresa de pie (10 mm², 2026-11-19). Se alarga un diámetro hacia
        # fuera, donde no hay ala.
        for f, di in d["largueros"][1:]:
            de, a_ = extremos_larguero(d, f, di, lado)
            u = [(q - p_) / math.dist(de, a_) for p_, q in zip(de, a_)]
            ala = ala - _tubo(kit, tuple(p_ - di * w for p_, w in zip(de, u)),
                              tuple(p_ + di * w for p_, w in zip(de, u)), di)
    if d.get("pilon_atornillado") and y0 < d["rotores"]["y"] < y1:
        ala = ala - _tornillos_pilon(kit, d)
    canal = _canal(kit, d)
    if canal is not None and y0 < max(s["y"] for s in _servos(d)):
        ala = ala - canal
    for s in _servos(d):
        if y0 < s["y"] < y1:
            ala = ala - _hueco_servo(kit, d, s)
    if _con_elevon(d, y0, y1, i):
        ala = ala - _bisagra(kit, d, y0, y1, -HOLGURA_BISAGRA)
        if _mandos(d):
            ala = ala - _ranuras_bisagra(kit, d, k)
    return ala


def _pieza_rotores(kit, d, partes, lado):
    """Las góndolas, los pilones y, en los aviones sin `aletas`, la pata y la deriva."""
    ro = d["rotores"]
    if partes[0] == "gondola":
        delante = partes[2] == "delante"
        x = ro["x"][0 if delante else 1]
        if ro.get("aletas"):
            cuerda = (d.get("pata", {}).get("cuerda", PATA_CUERDA) if delante
                      else d["deriva"]["cuerda"])
            return _lado(_gondola_con_aleta(kit, d, x, cuerda, d["deriva"]["alto"]), lado)
        return _lado(_gondola(kit, d, x), lado)
    if partes[0] == "pilon":
        return _lado(_pilon(kit, d), lado)
    de = d["deriva"]
    if partes[0] == "deriva":
        return _lado(_pie(kit, d, de["x"], de["cuerda"], de["alto"]), lado)
    # La pata va justo detrás de la góndola delantera, con la cuerda de la
    # deriva más corta: la hélice va arriba y la pata abajo.
    return _lado(_pie(kit, d, ro["x"][0] + MEDIO_LARGO_GONDOLA + 3, PATA_CUERDA, de["alto"]), lado)
