"""Las formas de un brazo industrial (F12.6 (forma), ADR-023).

El brazo de seis ejes que dibujó el modelo pieza a pieza pasó 16 de 18 en el
banco (corrida 1115-0523) y al usuario le pareció chatarra: «solo pusiste
cilindros conectados con placas». El modelo resuelve cada pieza con lo más
simple que sujeta un motor, y nadie le da la forma del conjunto. Aquí está
esa forma: un tambor en cada articulación y tramos que van de tambor a
tambor. El programa de cada pieza dice sobre qué gira, cuánto mide y qué
motor lleva; lo demás sale de aquí.

Cada pieza está pensada para imprimirse sin soportes, que es donde el modelo
falló una y otra vez:

- una pieza hueca es un vaso: una cara cerrada en la cama y las paredes
  subiendo, abierta por donde entra el motor;
- un agujero redondo tumbado tiene techo: lleva tejado a 45°;
- lo que sale de una pared en el aire lleva una rampa debajo;
- bajo una polea va un cono, no un escalón.

Es una familia, no un diseñador: los giros tumbados van a lo largo de «y»,
los de pie a lo largo de «z», y el brazo se dibuja en reposo hacia arriba.
Otra disposición se dibuja a mano con el resto del kit.
"""

from __future__ import annotations

import math

GRIETA = 2.0
"""Lo que se deja entre dos piezas que giran una junto a la otra."""
PARED = 6.0
"""La pared a la que se atornilla por su cara un motor con reductora."""
PLACA = 7.0
"""La tapa de la base bajo el motor: su eje tiene que asomar para la polea."""
FONDO = 5.0
"""La pared de una cáscara y el fondo donde se atornilla un NEMA 17."""
RADIO_CAMA = 6.0
"""El mayor redondeo que se imprime tocando la cama: lo que pasa de 45° en un
arco de 6 mm vuela menos de los 5 mm que aguanta un alero; con 10, 6,3."""


def _error(texto):
    from mech_toolkit.kit import KitError
    return KitError(texto)


def _salida(kit, padre, eje, que, de):
    """La salida de `padre` a lo largo de `eje` («y» o «z») que es `de` lo
    que esa pieza espera: el aro de un «rodamiento», el eje de un motor con
    «reductora» o el «plato» de una reductora impresa. La pieza de abajo
    trae además el eje de su propio motor, que no es sobre lo que se gira."""
    i = "xyz".index(eje)

    def es(s):
        ficha = kit._fichas.get(s["nombre"].split(":")[0].strip()) or {}
        cuerpos = ficha.get("cuerpos") or []
        if de == "plato":
            return bool((s.get("acople") or {}).get("agujeros"))
        if de == "rodamiento":
            return bool(cuerpos and (cuerpos[0].get("cilindro") or {}).get("interior"))
        return any(c.get("nombre") == "reductora" for c in cuerpos)

    buenas = [s for s in padre.salidas() if abs(abs(s["eje"][i]) - 1) < 1e-6 and es(s)]
    if len(buenas) != 1:
        hay = ", ".join(f"«{s['nombre']}» hacia {tuple(round(c) for c in s['eje'])}"
                        for s in padre.salidas()) or "ninguna"
        raise _error(f"{que} gira sobre el {de} de un eje a lo largo de «{eje}», y la pieza "
                     f"de abajo tiene {len(buenas)} así (tiene: {hay}). Estas formas son "
                     "para un brazo en reposo hacia arriba, con los giros tumbados a lo "
                     "largo de «y»; otra disposición se dibuja con el resto del kit")
    return buenas[0]


def _de(kit, salida) -> dict:
    """La ficha de lo comprado que da esa salida: «nema23-pg47-76: eje»."""
    id_ = salida["nombre"].split(":")[0].strip()
    if id_ not in kit._fichas:
        raise _error(f"no hay ficha de «{id_}», que es de donde sale «{salida['nombre']}»")
    return kit._fichas[id_]


def _cilindro(ficha, nombre) -> tuple[float, float]:
    """(diámetro, alto) del cuerpo `nombre` de una ficha."""
    for c in ficha.get("cuerpos") or []:
        # Una ficha cargada trae las dos claves, «caja» y «cilindro», con
        # None en la que no es: no basta con mirar si la clave está.
        if c.get("nombre") == nombre and c.get("cilindro"):
            return float(c["cilindro"]["diametro"]), float(c["cilindro"]["alto"])
    raise _error(f"la ficha «{ficha['id']}» no tiene un cuerpo cilíndrico «{nombre}»: estas "
                 "formas son para un motor con reductora, un rodamiento o una cicloidal")


def _capsula(kit, x1, r1, x2, r2, z0, alto):
    """Dos tambores de eje vertical unidos por sus tangentes: la planta de la
    base, o un tramo tumbado."""
    s = (r1 - r2) / (x2 - x1)
    c = math.sqrt(1 - s * s)
    entre = [(x1 + r1 * s, r1 * c), (x2 + r2 * s, r2 * c),
             (x2 + r2 * s, -r2 * c), (x1 + r1 * s, -r1 * c)]
    return (kit.cilindro(2 * r1, alto, en=(x1, 0, z0), eje="z")
            + kit.cilindro(2 * r2, alto, en=(x2, 0, z0), eje="z")
            + kit.extruir(entre, alto, plano="xy", desde=z0))


def base(kit, distancia, rodamiento, motor, alto, tablero):
    """Un pedestal hueco con el motor bajo su joroba. Se imprime boca abajo:
    la tapa en la cama y las paredes subiendo. Los tornillos del tablero
    bajan por cuatro columnas huecas, como en una bancada de fundición: una
    oreja por fuera sería, boca abajo, un alero en el aire."""
    C, HB = float(distancia), float(alto)
    D, w = _cilindro(kit._fichas.get(rodamiento) or {"id": rodamiento}, "rodamiento")
    cajas = [c["caja"] for c in (kit._fichas.get(motor) or {}).get("cuerpos") or []
             if c.get("caja")]
    if not cajas:
        raise _error(f"«{motor}» no tiene cuerpo de caja en su ficha: no sé cuánto ocupa")
    RB = D / 2 + 49.5
    RM = max(math.hypot(c[0], c[1]) for c in cajas) / 2 + 10.1
    pilares = [(0.634 * RB, 0.829 * RB), (0.634 * RB, -0.829 * RB),
               (-C - 12, RM + 5), (-C - 12, -RM - 5)]
    cuerpo = _capsula(kit, 0, RB, -C, RM, 0, HB).redondear(RADIO_CAMA, "arriba")
    for x, y in pilares:
        cuerpo = cuerpo + kit.cilindro(18, HB, en=(x, y, 0), eje="z")
    pieza = cuerpo.quitar("interior", _capsula(kit, 0, RB - 5, -C, RM - 5, -1, HB - 9))
    # El rodamiento va hundido lo que mide de ancho: encima de él cabe el
    # cono que sube del eje a la polea, que si no dejaba un techo plano.
    pieza = pieza + kit.cilindro(D + 17, 2 * w + 3, en=(0, 0, HB - 3 * w - 5), eje="z")
    rod = kit.componente(rodamiento, en=(0, 0, HB - 2 * w), entra_por="+z")
    pieza = pieza.quitar("asiento del rodamiento", rod.hueco("press"))
    pieza = pieza.quitar("paso del eje", kit.cilindro(D - 7, 2 * w + 15,
                                                      en=(0, 0, HB - 3 * w - 6), eje="z"))
    m = kit.componente(motor, en=(-C, 0, HB - PLACA), entra_por="-z")
    pieza = pieza.quitar("paso del motor", m.hueco())
    for n, a in enumerate(m.agujeros()):
        x, y, _ = a["en"]
        pieza = pieza.tornillo(f"motor {n}", a["tornillo"] or "M4", en=(x, y, HB), eje="-z")
    for n, (x, y) in enumerate(pilares):
        pieza = pieza.taladrar(f"acceso {n}", 10, en=(x, y, HB), eje="-z", profundidad=HB - 8)
        pieza = pieza.tornillo(f"tablero {n}", tablero, en=(x, y, 8), eje="-z")
    return pieza.acabar()


def columna(kit, abajo, hombro, altura, dientes):
    """El eje y la polea abajo, un cono que se abre y una columna que sube
    hasta el tambor del hombro, con la reductora dentro. Se imprime de pie."""
    aro = _salida(kit, abajo, "z", "la columna", "rodamiento")
    X, Y, zr = aro["punto"]
    if abs(X) > 1e-6 or abs(Y) > 1e-6:
        raise _error("la columna gira sobre el eje z del dibujo: coloca la base con su "
                     "rodamiento en x = 0, y = 0")
    try:
        d = float(_de(kit, aro)["cuerpos"][0]["cilindro"]["interior"])
    except (KeyError, IndexError, TypeError):
        raise _error(f"«{aro['nombre']}» no es el aro de un rodamiento: la columna entra "
                     "en el agujero de uno") from None
    w = aro["largo"]
    HB, HS = zr + 2 * w, float(altura)
    Dg, Lg = _cilindro(kit._fichas.get(hombro) or {"id": hombro}, "reductora")
    largo = Lg + 2 + PARED
    y0, y1 = -largo / 2, largo / 2
    DT, RT, ZT = Dg + 44, largo / 2, HB + 20
    if HS - DT / 2 - 5 <= ZT + 10:
        raise _error(f"el hombro a {HS:g} mm queda bajo: con esta base y esta reductora "
                     f"tiene que ir a {ZT + DT / 2 + 16:.0f} mm o más")
    eje = kit.cilindro(d - kit.holgura("slide"), w + 1, en=(0, 0, zr - 1), eje="z")
    sube = kit.cono(d - kit.holgura("slide"), 66, w + 1.5, en=(0, 0, zr + w), eje="z")
    cono = kit.cono(66, 2 * RT, ZT - (HB + 11), en=(0, 0, HB + 11), eje="z")
    # La columna no pasa de la cara del hombro (rozaría el tramo que cuelga
    # de él) y se abre pronto hasta lo que mide el tambor: abriéndose
    # despacio, las esquinas de abajo del tambor salían de ella en el aire.
    cuerpo = kit.transicion([(kit.elipse(2 * RT, 2 * RT), 0),
                             (kit.rectangulo(DT, largo, radio=8), HS - DT / 2 - 5 - ZT),
                             (kit.rectangulo(DT, largo, radio=8), HS - ZT)],
                            eje="z", en=(0, 0, ZT), recta=True)
    pieza = eje + sube + cono + cuerpo + kit.cilindro(DT, largo, en=(0, y0, HS), eje="y")
    m = kit.componente(hombro, en=(0, y1 - PARED, HS), girar=[("x", -90)], entra_por="-y")
    pieza = pieza.quitar("paso del hombro", m.hueco())
    a = (Dg / 2 + 1) / math.sqrt(2)
    tejado = kit.extruir([(-a, HS + a - 1), (a, HS + a - 1), (0, HS + 2 * a - 0.5)], Lg + 3,
                         plano="xz", desde=y0 - 1)
    pieza = pieza.quitar("tejado del hombro", tejado)
    for n, ag in enumerate(m.agujeros()):
        x, _, z = ag["en"]
        pieza = pieza.tornillo(f"hombro {n}", ag["tornillo"] or "M5", en=(x, y1, z), eje="-y",
                               avellanado=10.5)
    pieza = pieza.acabar()
    return pieza + kit.polea_gt2("polea", dientes, en=(0, 0, HB + 1.5), eje="+z")


def tramo(kit, abajo, largo, codo, grosor):
    """Dos tambores unidos por sus tangentes, con un rebaje en la cara de
    fuera. Se dibuja tumbado, que es como se imprime (la cara de dentro en
    la cama), y se pone de pie antes de taladrarlo."""
    s = _salida(kit, abajo, "y", "el tramo", "reductora")
    X, YF, HS = s["punto"]
    if s["eje"][1] < 0:
        raise _error("el tramo cuelga del lado +y de la columna: el eje del hombro tiene "
                     "que salir hacia +y")
    de, _ = _cilindro(_de(kit, s), "eje")
    Dh, _ = _cilindro(_de(kit, s), "reductora")
    Dg, _ = _cilindro(kit._fichas.get(codo) or {"id": codo}, "reductora")
    YA, GA, L = YF + PARED + GRIETA, float(grosor), float(largo)
    R1, R2 = Dh / 2 + 22, Dg / 2 + 16

    def de_pie(c):
        return c.girar(-90, eje="y").girar(-90, eje="z").mover(X, YA, HS)

    losa = _capsula(kit, 0, R1, L, R2, 0, GA).redondear(RADIO_CAMA, "arriba")
    pieza = de_pie(losa).quitar("rebaje", de_pie(_capsula(kit, 0, R1 - 12, L, R2 - 12,
                                                          GA - 2.5, 5)))
    pieza = pieza.taladrar("eje del hombro", de + kit.holgura("slide"), en=(X, YA + GA, HS),
                           eje="-y")
    m = kit.componente(codo, en=(X, YA + PARED, HS + L), girar=[("x", 90)], entra_por="+y")
    pieza = pieza.quitar("paso del codo", m.hueco())
    for n, ag in enumerate(m.agujeros()):
        x, _, z = ag["en"]
        pieza = pieza.tornillo(f"codo {n}", ag["tornillo"] or "M5", en=(x, YA, z), eje="+y",
                               avellanado=10.5)
    return pieza.acabar()


def antebrazo(kit, abajo, largo, motor, reductora):
    """Una cáscara que se afina hasta el aro del giro, con el motor dentro y
    la cola abierta por donde entra. Se imprime boca abajo, con la tapa en
    la cama. El cubo del codo lleva una rampa encima: sin ella, boca abajo,
    sería un tambor que sale de la pared en el aire."""
    s = _salida(kit, abajo, "y", "el antebrazo", "reductora")
    X, yc, ZE = s["punto"]
    if s["eje"][1] > 0:
        raise _error("el antebrazo vuelve hacia el centro: el eje del codo tiene que salir "
                     "hacia -y")
    de, _ = _cilindro(_de(kit, s), "eje")
    ficha = kit._fichas.get(reductora) or {}
    try:
        sale = float(ficha["salidas"][0]["en"][2])
        Dr, _ = _cilindro(ficha, "carcasa")
    except (KeyError, IndexError):
        raise _error(f"«{reductora}» no es una reductora con plato de salida") from None
    cara = yc - PARED - GRIETA          # la cara del cubo que mira al tramo
    YJ = cara - 52                      # el motor pasa al lado del eje del codo, no por él
    ZW = ZE + float(largo) - sale
    z0, A = ZE - 70, Dr + 4
    cuerpo = kit.transicion([(kit.rectangulo(76, 56, radio=24), 0),
                             (kit.rectangulo(100, 56, radio=26), 40),
                             (kit.rectangulo(100, 56, radio=26), ZW - 40 - z0),
                             (kit.elipse(A, A), ZW - z0)],
                            eje="z", en=(X, YJ, z0), recta=True).vaciar(FONDO, abierta="-z")
    cubo = kit.cilindro(70, cara - YJ - 23, en=(X, YJ + 23, ZE), eje="y")
    rampa = kit.extruir([(YJ + 23, ZE), (cara, ZE), (cara, ZE + 35), (YJ + 28, ZE + 62),
                         (YJ + 23, ZE + 62)], 70, plano="yz", desde=X - 35)
    pieza = cuerpo + cubo + rampa
    pieza = pieza.taladrar("eje del codo", de + kit.holgura("slide"), en=(X, cara, ZE),
                           eje="-y", profundidad=26)
    m = kit.componente(motor, en=(X, YJ, ZW - FONDO), girar=[("z", 90)], entra_por="-z")
    pieza = pieza.quitar("paso del motor", m.hueco())
    kit.componente(reductora, en=(X, YJ, ZW), entra_por="+z")
    for n, ag in enumerate(m.agujeros()):
        x, y, _ = ag["en"]
        pieza = pieza.tornillo(f"motor {n}", ag["tornillo"] or "M3", en=(x, y, ZW), eje="-z")
    return pieza.acabar()


def _plato(salida, que):
    acople = salida.get("acople") or {}
    try:
        return float(acople["agujeros"][0]["radio"]), acople.get("tornillo") or "M3"
    except (KeyError, IndexError):
        raise _error(f"{que} se atornilla al plato de una reductora, y «{salida['nombre']}» "
                     "no tiene plato con agujeros") from None


def _reductora(kit, id_):
    ficha = kit._fichas.get(id_) or {}
    try:
        return float(ficha["salidas"][0]["en"][2]), _cilindro(ficha, "carcasa")[0]
    except (KeyError, IndexError):
        raise _error(f"«{id_}» no es una reductora con plato de salida") from None


def muneca(kit, abajo, largo, motor, reductora):
    """Una bandeja con la forma del tambor del cabeceo arriba. Su suelo es
    la pared donde se atornillan el motor (dentro) y la reductora (fuera):
    se imprime con ese suelo en la cama y queda abierta por el otro lado,
    que es por donde entra el motor."""
    s = _salida(kit, abajo, "z", "la muñeca", "plato")
    X, YJ, Z4 = s["punto"]
    r, metrica = _plato(s, "la muñeca")
    _, Dr = _reductora(kit, reductora)
    A = Dr + 4
    Z5, y0, y1 = Z4 + float(largo), YJ - A / 2, YJ + A / 2
    fuera = (kit.caja(A, A, Z5 - Z4, en=(X - A / 2, y0, Z4))
             + kit.cilindro(A, A, en=(X, y0, Z5), eje="y"))
    dentro = (kit.caja(A - 10, A - 5, Z5 - Z4 - PARED, en=(X - A / 2 + 5, y0 - 1, Z4 + PARED))
              + kit.cilindro(A - 10, A - 5, en=(X, y0 - 1, Z5), eje="y"))
    pieza = fuera.quitar("interior", dentro)
    m = kit.componente(motor, en=(X, y1 - PARED, Z5), girar=[("z", 180), ("x", -90)],
                       entra_por="-y")
    pieza = pieza.quitar("paso del motor", m.hueco())
    kit.componente(reductora, en=(X, y1, Z5), girar=[("x", -90)], entra_por="+y")
    for n, ag in enumerate(m.agujeros()):
        x, _, z = ag["en"]
        pieza = pieza.tornillo(f"motor {n}", ag["tornillo"] or "M3", en=(x, y1, z), eje="-y")
    for n, (dx, dy) in enumerate([(r, 0), (0, r), (-r, 0), (0, -r)]):
        # La llave baja derecha hasta cada tornillo del plato por un agujero del techo.
        pieza = pieza.taladrar(f"acceso {n}", 6.5, en=(X + dx, YJ + dy, Z5 + A / 2 + 1),
                               eje="-z", profundidad=12)
        pieza = pieza.tornillo(f"acople {n}", metrica, en=(X + dx, YJ + dy, Z4 + PARED),
                               eje="-z")
    return pieza.acabar()


def mano(kit, abajo, largo, motor, reductora, brida):
    """Otra bandeja, con el tambor abajo (gira en el cabeceo) y la tapa
    arriba, donde van el motor y la reductora del último giro."""
    s = _salida(kit, abajo, "y", "la mano", "plato")
    X, YP, Z5 = s["punto"]
    if s["eje"][1] < 0:
        raise _error("la mano va del lado +y de la muñeca: el plato del cabeceo tiene que "
                     "mirar hacia +y")
    r, metrica = _plato(s, "la mano")
    sale, Dr = _reductora(kit, reductora)
    A = Dr + 4
    ZP = Z5 + float(largo) - sale - float(brida)
    if ZP - PARED - Z5 < 45:
        raise _error(f"la mano de {largo:g} mm no deja sitio al motor: con esta reductora y "
                     f"una brida de {brida:g} tiene que medir {45 + PARED + sale + brida:.0f} "
                     "o más")
    fuera = (kit.caja(A, A, ZP - Z5, en=(X - A / 2, YP, Z5))
             + kit.cilindro(A, A, en=(X, YP, Z5), eje="y"))
    dentro = (kit.caja(A - 10, A - 5, ZP - PARED - Z5, en=(X - A / 2 + 5, YP + PARED, Z5))
              + kit.cilindro(A - 10, A - 5, en=(X, YP + PARED, Z5), eje="y"))
    pieza = fuera.quitar("interior", dentro)
    m = kit.componente(motor, en=(X, YP + A / 2, ZP - PARED), girar=[("z", 180)],
                       entra_por="+y")
    pieza = pieza.quitar("paso del motor", m.hueco())
    kit.componente(reductora, en=(X, YP + A / 2, ZP), entra_por="+z")
    for n, (dx, dz) in enumerate([(r, 0), (0, r), (-r, 0), (0, -r)]):
        pieza = pieza.tornillo(f"acople {n}", metrica, en=(X + dx, YP + PARED, Z5 + dz),
                               eje="-y")
    for n, ag in enumerate(m.agujeros()):
        x, y, _ = ag["en"]
        pieza = pieza.tornillo(f"motor {n}", ag["tornillo"] or "M3", en=(x, y, ZP), eje="-z")
    return pieza.acabar()


def brida(kit, abajo, grosor, diametro, herramienta):
    """Donde se atornilla la herramienta, y hasta donde se mide el alcance."""
    s = _salida(kit, abajo, "z", "la brida", "plato")
    X, Y, Z6 = s["punto"]
    r, metrica = _plato(s, "la brida")
    G = float(grosor)
    pieza = kit.cilindro(diametro, G, en=(X, Y, Z6), eje="z")
    for n, (dx, dy) in enumerate([(r, 0), (0, r), (-r, 0), (0, -r)]):
        pieza = pieza.tornillo(f"acople {n}", metrica, en=(X + dx, Y + dy, Z6 + G), eje="-z")
    for n, (dx, dy) in enumerate([(9, 9), (-9, 9), (-9, -9), (9, -9)]):
        pieza = pieza.tornillo(f"herramienta {n}", herramienta, en=(X + dx, Y + dy, Z6 + G),
                               eje="-z")
    return pieza.acabar()
