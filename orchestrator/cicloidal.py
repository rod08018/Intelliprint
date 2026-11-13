"""El módulo de la reductora cicloidal para un NEMA 17 (F10.7 (cicloidal)).

Cinco piezas impresas que salen de la relación que se pida, sin que las
dibuje ningún modelo:

- **carcasa**: un vaso que va sobre la cara del motor (o sobre la pared que
  lo sujeta), con los pernos del anillo hechos de una pieza con su pared.
- **excentrica**: va en el eje del motor, con un prisionero; su leva lleva
  el centro del disco dando vueltas.
- **disco**: el de los lóbulos, con el perfil de `mech_toolkit.cicloidal`.
- **salida**: un plato con cuatro pasadores que entran en el disco; gira lo
  que gira el disco, y en su cara de fuera se atornilla lo que se mueve.
- **tapa**: un aro que retiene el plato dentro de la carcasa.

El marco es el del módulo montado: el origen en el centro de la cara de
abajo de la carcasa, y z hacia donde sale el eje del motor.

**Lo que no está comprobado**: nada de esto se ha impreso. Las holguras son
un número (`holgura`), no una medida de la impresora del usuario; plástico
contra plástico, sin rodamientos; y la excéntrica se fía de un prisionero
en un eje de 5 mm. Si gira lo dirá F10.8 (calibrar).
"""

import math

from mech_toolkit import cicloidal as C

from orchestrator.modulos import Modulo

# Todo en milímetros. El círculo de los pernos es lo bastante grande para que
# los cuatro tornillos del motor (a 21,9 mm del eje) queden debajo del disco.
RADIO, RADIO_PERNO = 30.0, 2.5
SUELO, DISCO, PLATO, TAPA = 9.0, 6.0, 4.0, 3.0
JUEGO = 0.5                      # entre el disco y lo que tiene encima y debajo
PARED = 38.0                     # radio de fuera de la carcasa
LEVA = 12.0                      # diámetro de la excéntrica
PASADOR, RADIO_PASADORES = 5.0, 15.0
CUELLO = 26.0                    # radio del cuello del plato, que asoma por la tapa
EJE_DEL_MOTOR, TORNILLOS_DEL_MOTOR = 5.0, 15.5
RADIO_DE_ACOPLE = 20.0           # donde se atornilla lo que se mueve
RELACIONES = (5, 28)
"""Con menos de 5 el disco casi no tiene lóbulos; con más de 28, la
excentricidad por el número de pernos pasa del radio y el perfil se cruza."""
PUNTOS_POR_LOBULO = 32
"""El contorno del disco es un polígono. Con 16 puntos por lóbulo la de 20:1,
construida, atravesaba sus pernos: las cuerdas de los valles se metían en
ellos más de la holgura. Con 32 no; comprobar que un polígono así no se
cruza tarda medio minuto en la de 20:1, una vez por proyecto."""


def excentricidad(pernos: int) -> float:
    """Con 1 mm el disco se socava a partir de 22 pernos: medido con
    `mech_toolkit.cicloidal.holgura_con_los_pernos`, a 26 pernos quedan
    0,04 mm de los 0,15 de holgura, y a 29 se atraviesan. Con 0,7 no."""
    return 1.0 if pernos <= 21 else 0.7
DENSIDAD_APARENTE = 0.6
"""g/cm³ de lo impreso, contando que va con relleno: una estimación para
la masa de la ficha, del lado pesado (el PLA macizo pesa 1,24)."""


def _cuatro(radio: float, desde: float = 45.0) -> list[tuple[float, float]]:
    return [(round(radio * math.cos(math.radians(desde + 90 * k)), 4),
             round(radio * math.sin(math.radians(desde + 90 * k)), 4)) for k in range(4)]


def medidas(relacion: int, holgura: float = 0.15) -> dict:
    """Las cotas de las que salen las cinco piezas y la ficha."""
    if int(relacion) != relacion or not RELACIONES[0] <= relacion <= RELACIONES[1]:
        raise ValueError(f"esta cicloidal se hace con una relación entera de {RELACIONES[0]} a "
                         f"{RELACIONES[1]}; no {relacion!r}")
    pernos = int(relacion) + 1
    cavidad = RADIO + RADIO_PERNO / 2
    return {
        "relacion": int(relacion), "pernos": pernos, "holgura": holgura,
        "e": excentricidad(pernos),
        "cavidad": cavidad, "z_disco": SUELO + JUEGO, "z_plato": SUELO + DISCO + 2 * JUEGO,
        "z_borde": SUELO + DISCO + 2 * JUEGO + PLATO + 0.3,
        "alto": SUELO + DISCO + 2 * JUEGO + PLATO + 0.3 + TAPA,
        "z_salida": SUELO + DISCO + 2 * JUEGO + PLATO + 0.3 + TAPA + 1.0,
        "radio_tapa": (cavidad + PARED) / 2,
    }


def _carcasa(m: dict) -> str:
    pernos = [(round(RADIO * math.cos(2 * math.pi * k / m["pernos"]), 4),
               round(RADIO * math.sin(2 * math.pi * k / m["pernos"]), 4))
              for k in range(m["pernos"])]
    return f'''
PERNOS = {pernos!r}
MOTOR = {_cuatro(TORNILLOS_DEL_MOTOR * math.sqrt(2))!r}
TAPA = {_cuatro(m["radio_tapa"])!r}

def construir(kit):
    pieza = kit.cilindro({2 * PARED}, {m["z_borde"]})
    pieza = pieza - kit.cilindro({2 * m["cavidad"]}, {m["z_borde"]}, en=(0, 0, {SUELO}))
    for x, y in PERNOS:
        # Hasta justo debajo del plato de salida, que gira encima de ellos:
        # hasta el borde lo atravesaban (lo vio el test con las piezas hechas).
        pieza = pieza + kit.cilindro({2 * RADIO_PERNO}, {m["z_plato"] - 0.2 - SUELO + 0.5},
                                     en=(x, y, {SUELO - 0.5}))
    pieza = pieza.taladrar("paso del eje", 22.6, en=(0, 0, {SUELO}))
    for n, (x, y) in enumerate(MOTOR):
        pieza = pieza.taladrar("cabeza %d" % n, 6.5, en=(x, y, {SUELO}), profundidad=5.5)
        pieza = pieza.tornillo("motor %d" % n, "M3", en=(x, y, {SUELO - 5.5}))
    for n, (x, y) in enumerate(TAPA):
        pieza = pieza.tornillo("tapa %d" % n, "M3", en=(x, y, {m["z_borde"]}), tipo="rosca",
                               profundidad=9)
    return pieza
'''


def _excentrica(m: dict) -> str:
    return f'''
def construir(kit):
    cubo = kit.cilindro({LEVA}, {SUELO + 0.3 - 2.5}, en=(0, 0, 2.5))
    leva = kit.cilindro({LEVA}, {DISCO + 2 * JUEGO - 0.6}, en=({m["e"]}, 0, {SUELO + 0.3 - 0.5}))
    pieza = (cubo + leva).taladrar("eje del motor", {EJE_DEL_MOTOR} + kit.holgura("slide"),
                                   en=(0, 0, {SUELO + DISCO + 2 * JUEGO}))
    return pieza.tornillo("prisionero", "M3", en=({-LEVA / 2}, 0, 5.5), eje="+x", tipo="rosca",
                          profundidad={LEVA / 2 - 1})
'''


def _disco(m: dict) -> str:
    contorno = [(round(x + m["e"], 4), round(y, 4))
                for x, y in C.perfil(m["pernos"], RADIO, RADIO_PERNO, m["e"],
                                     m["holgura"], puntos=PUNTOS_POR_LOBULO * m["pernos"])]
    agujeros = [(round(x + m["e"], 4), y) for x, y in _cuatro(RADIO_PASADORES)]
    return f'''
CONTORNO = {contorno!r}
PASADORES = {agujeros!r}

def construir(kit):
    pieza = kit.extruir(CONTORNO, {DISCO}, desde={m["z_disco"]})
    pieza = pieza.taladrar("leva", {LEVA + 2 * m["holgura"]}, en=({m["e"]}, 0, {m["z_disco"] + DISCO}))
    for n, (x, y) in enumerate(PASADORES):
        pieza = pieza.taladrar("pasador %d" % n, {PASADOR + 2 * m["e"] + 2 * m["holgura"]},
                               en=(x, y, {m["z_disco"] + DISCO}))
    return pieza
'''


def _salida(m: dict) -> str:
    """Se dibuja como se imprime, con el cuello abajo y los pasadores hacia
    arriba, para que no pida soportes; montada va al revés (`MONTAJE`)."""
    cuello = m["z_salida"] - (m["z_plato"] + PLATO)
    return f'''
PASADORES = {_cuatro(RADIO_PASADORES)!r}
ACOPLE = {_cuatro(RADIO_DE_ACOPLE, 0.0)!r}

def construir(kit):
    pieza = kit.cilindro({2 * CUELLO}, {cuello + 0.5}) + kit.cilindro(
        {2 * (m["cavidad"] - 0.3)}, {PLATO}, en=(0, 0, {cuello}))
    for x, y in PASADORES:
        pieza = pieza + kit.cilindro({PASADOR}, {DISCO + JUEGO + 0.3}, en=(x, y, {cuello + PLATO - 0.5}))
    pieza = pieza.taladrar("paso del eje", 6.5, en=(0, 0, {cuello + PLATO}))
    for n, (x, y) in enumerate(ACOPLE):
        pieza = pieza.tornillo("acople %d" % n, "M3", en=(x, y, 0), eje="+z", tipo="rosca",
                               profundidad=7)
    return pieza
'''


def _tapa(m: dict) -> str:
    return f'''
TORNILLOS = {_cuatro(m["radio_tapa"])!r}

def construir(kit):
    pieza = kit.tubo({2 * PARED}, {2 * (CUELLO + 0.3)}, {TAPA}, en=(0, 0, {m["z_borde"]}))
    for n, (x, y) in enumerate(TORNILLOS):
        pieza = pieza.tornillo("tapa %d" % n, "M3", en=(x, y, {m["alto"]}))
    return pieza
'''


def montaje(relacion: int, giro_excentrica: float = 0.0) -> dict[str, tuple]:
    """Dónde va cada pieza construida, con la excéntrica girada ese ángulo
    (en grados): {pieza: (origen, (rx, ry, rz))}, en el marco del módulo. La
    excéntrica gira con el motor; el disco, con su centro en la leva, y al
    revés; el plato, lo que el disco."""
    m = medidas(relacion)
    a = math.radians(giro_excentrica)
    lento = math.degrees(C.giro_del_disco(m["pernos"], a))
    cx, cy = C.centro_del_disco(m["e"], a)
    c, s = math.cos(math.radians(lento)), math.sin(math.radians(lento))
    # El disco se dibujó con su centro en (E, 0): gira sobre él y va a (cx, cy).
    return {
        "carcasa": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        "tapa": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        "excentrica": ((0.0, 0.0, 0.0), (0.0, 0.0, giro_excentrica)),
        "disco": ((cx - c * m["e"], cy - s * m["e"], 0.0), (0.0, 0.0, lento)),
        "salida": ((0.0, 0.0, m["z_salida"]), (180.0, 0.0, lento)),
    }


def generar(relacion: int, holgura: float = 0.15) -> Modulo:
    m = medidas(relacion, holgura)
    id_ = f"cicloidal-nema17-{m['relacion']}"
    volumen = (math.pi * PARED ** 2 * SUELO + math.pi * (PARED ** 2 - m["cavidad"] ** 2)
               * (m["z_borde"] - SUELO) + math.pi * (RADIO - RADIO_PERNO) ** 2 * DISCO
               + math.pi * m["cavidad"] ** 2 * PLATO + math.pi * CUELLO ** 2 * (TAPA + 1.3)
               + math.pi * (PARED ** 2 - CUELLO ** 2) * TAPA)
    ficha = {
        "id": id_,
        "nombre": f"Reductora cicloidal {m['relacion']}:1 para NEMA 17",
        "alias": [f"cicloidal {m['relacion']}:1"],
        "origen": "modulo", "verificado": False, "reduccion": m["relacion"],
        "fuentes": [{
            "url": "https://howtomechatronics.com/how-it-works/"
                   "what-is-cycloidal-driver-designing-3d-printing-and-testing/",
            "cita": "x = (R*cos(t))-(Rr*cos(t+arctan(sin((1-N)*t)/((R/(E*N))-cos((1-N)*t)))))"
                    "-(E*cos(N*t)); the disk has one less cycloidal lobe"}],
        "marco": ("Origen en el centro de la cara de abajo de la carcasa, la que va contra la "
                  "cara del motor o contra la pared que lo sujeta. El eje del motor entra por "
                  "abajo y la salida gira arriba, hacia +z."),
        "mira": "+z",
        # Solo lo que no gira. El plato de salida asoma 1 mm por encima de la
        # tapa y es a lo que se atornilla lo que se mueve: va como `acople` de
        # la salida, igual que el cuerno de un servo, y no como un cuerpo
        # contra el que chocar.
        "cuerpos": [
            {"nombre": "carcasa", "cilindro": {"diametro": 2 * PARED, "alto": m["alto"],
                                               "eje": "+z"}, "en": [0, 0, 0]}],
        # Los cuatro tornillos del motor atraviesan el suelo de la carcasa: sus
        # cabezas quedan dentro. No llevan `tornillo`: los cuenta el motor.
        "fijacion": [{"nombre": f"motor {n + 1}", "diametro": 3.3, "en": [x, y, 0], "eje": "-z"}
                     for n, (x, y) in enumerate(_cuatro(TORNILLOS_DEL_MOTOR * math.sqrt(2)))],
        "salidas": [{
            "nombre": "salida", "en": [0, 0, m["z_salida"]], "eje": "+z", "recorrido": [0, 360],
            "porque": "el plato gira sin tope, una vuelta por cada "
                      f"{m['relacion']} del motor, y al revés que él",
            "acople": {"nombre": "plato de salida", "cubo_diametro": 6.5, "cubo_alto": 0.1,
                       "grosor": 1.0, "brazos": 4, "de_punta_a_punta": 2 * CUELLO,
                       "agujeros": [{"radio": RADIO_DE_ACOPLE, "diametro": 3.0}],
                       "tornillo": "M3", "fondo_mm": 7.0,
                       "porque": "cuatro agujeros para rosca de M3, de 7 mm de fondo"}}],
        "notas": ("Va sobre un NEMA 17 con los cuatro tornillos del motor, que atraviesan su "
                  "suelo (3,5 mm) y lo que haya entre los dos: la pared de la pieza que los "
                  "sujeta lleva los cuatro pasantes de M3 y un paso de Ø23 para el eje. Se "
                  "monta en este orden: la excéntrica en el eje, la carcasa, el disco, el "
                  "plato y la tapa."),
        "masa_g": round(volumen / 1000 * DENSIDAD_APARENTE),
    }
    return Modulo(
        id=id_, ficha=ficha,
        piezas={"carcasa": _carcasa(m), "excentrica": _excentrica(m), "disco": _disco(m),
                "salida": _salida(m), "tapa": _tapa(m)},
        otros={"Tornillo M3 × 12 (tapa de la reductora)": 4,
               "Prisionero M3 × 5 (excéntrica)": 1})
