"""El VTOL de la Fase 13, dibujado A MANO por el asistente con el kit (2026-11-16).

Él lo pidió así: «tú diseña y usa lo que habías dicho; quiero que se haga
rápido». Las medidas salen de `scripts/avion_vtol_dimensionar.py` (AeroSandbox)
y de su JSON, `scripts/avion_vtol.json`. **No es nota del sistema**: los
programas de las piezas los escribió el asistente; el kit los construye.

Cada pieza se dibuja donde va montada (x hacia atrás, y hacia la derecha, z
arriba, en mm) y cabe en una cama de 235 × 235 × 250. Lo comprado (vigas y
largueros de carbono, motores, hélices, batería) no se imprime.

Uso, desde el repo:
    MSYS_NO_PATHCONV=1 docker compose run --rm -T --entrypoint python3 suite - \\
        /workspace/projects/<carpeta> < scripts/avion_vtol_a_mano.py
Con un segundo argumento (un id de pieza), construye solo esa, en /tmp.
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

from orchestrator import cli
from orchestrator import obra as O
from orchestrator.schemas.obra import Obra
from tests.test_revalidar import _lista

raiz = cli._raiz()
os.chdir(raiz)
P = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/avion")
SOLO = sys.argv[2] if len(sys.argv) > 2 else None
if P.exists() and not str(P).startswith("/tmp/"):
    raise SystemExit(f"{P} ya existe y no es temporal: no se toca")
shutil.rmtree(P, ignore_errors=True)
P.mkdir(parents=True)
os.environ["INTELLIPRINT_WORKSPACE"] = str(P.parent.parent)
D = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))

# --- La geometría (mm) ---------------------------------------------------------
# Estaciones del ala: (y, x del borde de ataque, z del borde de ataque, cuerda,
# alabeo en grados). Las mismas que dimensionó AeroSandbox.
EST = [(0, 0, 0, 500, 2), (170, 120, 0, 300, 2), (250, 160, 5, 230, 1.5),
       (1300, 240, 55, 150, -1)]
CORTES_ALA = [250, 460, 670, 880, 1090, 1300]
ALERON_DESDE = 880          # los dos tramos de la punta llevan alerón
BISAGRA_ALA = 0.75          # fracción de cuerda
Y_VIGA, Z_VIGA = 380, -25   # vigas de carbono de Ø20
MOTORES_X = (-76, 760)      # equidistantes del centro de gravedad (x = 342)
X_COLA, Z_COLA, C_COLA = 1030, 200, 130
COLA_HASTA, TIMON_HASTA = 400, 365
CORTES_COLA = [0, 200, 400]

COMUN = f'''
ALA = {[tuple(p) for p in D["perfiles"]["ala"]["puntos"]]!r}
COLA = {[tuple(p) for p in D["perfiles"]["cola"]["puntos"]]!r}
COMBA = {D["perfiles"]["ala"]["comba"]["0.27"]!r}
COMBA_T = {D["perfiles"]["ala"]["comba"]["0.62"]!r}
EST = {EST!r}
Y_VIGA = {Y_VIGA}
Z_VIGA = {Z_VIGA}
X_COLA = {X_COLA}
Z_COLA = {Z_COLA}
C_COLA = {C_COLA}
COLA_HASTA = {COLA_HASTA}
TIMON_HASTA = {TIMON_HASTA}
BISAGRA_ALA = {BISAGRA_ALA}
HOLGURA = 0.5     # media ranura de cada lado de una bisagra: 1 mm entre las dos
LARGO = 4000


def fuera(y):
    """(x, z, cuerda, alabeo) del ala exterior, de los 250 a los 1300 mm: lineal,
    así el 27 % de la cuerda es una recta y el larguero, un tubo recto."""
    a, b = EST[2], EST[3]
    t = (y - a[0]) / (b[0] - a[0])
    return [a[i] + (b[i] - a[i]) * t for i in range(1, 5)]


def perfil(kit, x, z, c, alabeo, puntos=ALA, comba=COMBA):
    """La sección del ala en su sitio, girada `alabeo` sobre el 27 % de su
    cuerda, que es donde va el larguero: así el giro no lo saca del perfil."""
    px, pz = x + 0.27 * c, z + comba * c
    s, k = sin(radians(alabeo)), cos(radians(alabeo))
    res = []
    for u, v in puntos:
        dx, dz = x + u * c - px, z + v * c - pz
        res.append((px + dx * k + dz * s, pz - dx * s + dz * k))
    return kit.seccion(res)


def ala_entre(kit, y0, y1):
    return kit.transicion([(perfil(kit, *fuera(y0)), y0), (perfil(kit, *fuera(y1)), y1)],
                          eje="y")


def punto_larguero(y, f, comba):
    x, z, c, alabeo = fuera(y)
    return (x + f * c, y, z + comba * c - (f - 0.27) * c * sin(radians(alabeo)))


def largueros(kit, hasta_principal=1090):
    """Los dos tubos de carbono, con la holgura de deslizar: Ø12 al 27 % de la
    cuerda hasta los 1090 mm (más allá el perfil mide menos de 15) y Ø6 al 62 %
    hasta la punta. Cruzan el cuerpo central."""
    # Empiezan 20 mm más allá del centro: los de los dos lados se solapan. Si
    # acababan los dos justo en y = 0, cara contra cara, la resta de FreeCAD
    # dejaba el cuerpo central en tres trozos (prueba del 2026-11-16).
    p = kit.barrer(kit.elipse(12.3, 12.3), [punto_larguero(-20, 0.27, COMBA),
                                            punto_larguero(hasta_principal, 0.27, COMBA)])
    t = kit.barrer(kit.elipse(6.3, 6.3), [punto_larguero(-20, 0.62, COMBA_T),
                                          punto_larguero(1310, 0.62, COMBA_T)])
    return p + t


def tras_bisagra(kit, y0, y1, f, margen):
    """El prisma que queda detrás de la línea de bisagra (al `f` de la cuerda),
    entre y0 e y1: lo que se mueve del alerón."""
    a, b = fuera(y0), fuera(y1)
    xa, xb = a[0] + f * a[2] + margen, b[0] + f * b[2] + margen
    return kit.extruir([(xa, y0), (xa + 400, y0), (xb + 400, y1), (xb, y1)], 400,
                       plano="xy", desde=-150)


def lado(cuerpo, s):
    return cuerpo if s > 0 else cuerpo.espejo("xz", conservar=False)


def rombo(kit, x, largo, ancho):
    """Ventana en la panza, centrada en x: un rombo de `largo` en x y `ancho`
    en y. Con el largo mayor que el ancho sus lados pasan de 45°."""
    return kit.extruir([(x - largo / 2, 0), (x, ancho / 2), (x + largo / 2, 0), (x, -ancho / 2)],
                       60, plano="xy", desde=-130)


def cuerpo_central(kit):
    """El fuselaje y el centro del ala en una pieza lisa: el ala integrada. El
    fuselaje lleva dentro la batería (6S10P de 21700, 210 × 126 × 70), la carga y
    la electrónica; abajo, dos ventanas de cámara y la del lidar."""
    # El morro es largo y el hueco acaba en punta por los dos lados: impreso de
    # pie, un hueco que acaba en una cara plana es un techo, y el morro romo de
    # la primera prueba pedía soportes (2026-11-16).
    secciones = [(-260, 20, 18), (-200, 70, 60), (-130, 140, 115), (-60, 170, 140),
                 (300, 170, 140), (560, 110, 90), (720, 50, 50)]
    fus = kit.transicion([(kit.elipse(w, h), x) for x, w, h in secciones], eje="x",
                         en=(0, 0, -20))
    centro = kit.transicion([(perfil(kit, e[1], e[2], e[3], e[4]), e[0]) for e in EST[:3]],
                            eje="y")
    cuerpo = fus + centro.espejo("xz")
    hueco = [(-230, 30, 26), (-200, 62, 52), (-130, 132, 107), (-60, 163, 133), (300, 163, 133),
             (560, 103, 83), (650, 62, 58), (690, 20, 20)]
    cuerpo = cuerpo - kit.transicion([(kit.elipse(w, h), x) for x, w, h in hueco], eje="x",
                                     en=(0, 0, -20))
    cuerpo = cuerpo - largueros(kit) - largueros(kit).espejo("xz", conservar=False)
    # Donde el larguero principal sale del hueco del fuselaje, el techo de su
    # agujero se queda sin apoyo al imprimir de pie (8,5 mm en el aire, prueba
    # del 2026-11-16): ahí el agujero lleva puntas a 45° delante y detrás.
    r = 6.15 * 1.4142
    for s in (1, -1):
        q = punto_larguero(77.5, 0.27, COMBA)
        cx, cz = q[0], q[2]
        cuerpo = cuerpo - kit.extruir([(cx - r, cz), (cx, cz + 6.15), (cx + r, cz), (cx, cz - 6.15)],
                                      40, plano="xz", desde=57.5 if s > 0 else -97.5)
    # Las ventanas son rombos, no círculos: la pieza se imprime de pie (x
    # arriba) y el techo de una ventana redonda vuela (prueba del 2026-11-16).
    cuerpo = cuerpo - rombo(kit, -80, 40, 36)                          # cámara abajo
    cuerpo = cuerpo - kit.barrer(kit.elipse(32, 32), [(-170, 0, -40), (-250, 0, -120)])
    cuerpo = cuerpo - rombo(kit, 60, 84, 72)                          # lidar
    # El motor de empuje en la cola: cuatro M3 en un círculo de 25 y el paso
    # del eje.
    # El paso del eje acaba en cono: con fondo plano era un techo al imprimir.
    cuerpo = cuerpo - kit.cono(12, 0, 7, en=(721, 0, -20), eje="-x")
    for k in range(4):
        a = radians(45 + 90 * k)
        cuerpo = cuerpo - kit.cilindro(2.8, 12, en=(709, 12.5 * cos(a), -20 + 12.5 * sin(a)),
                                       eje="x")
    return cuerpo


def tramo_ala(kit, y0, y1, s):
    cuerpo = ala_entre(kit, y0, y1) - largueros(kit)
    if y0 >= {ALERON_DESDE}:
        cuerpo = cuerpo - tras_bisagra(kit, y0 - 1, y1 + 1, BISAGRA_ALA, -HOLGURA)
    return lado(cuerpo, s)


def aleron(kit, y0, y1, s):
    cuerpo = ala_entre(kit, y0, y1) & tras_bisagra(kit, y0 - 1, y1 + 1, BISAGRA_ALA, HOLGURA)
    return lado(cuerpo, s)


def estabilizador(kit, y0, y1):
    sec = [(X_COLA + u * C_COLA, Z_COLA + v * C_COLA) for u, v in COLA]
    return kit.transicion([(kit.seccion(sec), y0), (kit.seccion(sec), y1)], eje="y")


def tras_bisagra_cola(kit, y0, y1, margen):
    x = X_COLA + 0.7 * C_COLA + margen
    return kit.caja(300, y1 - y0, 60, en=(x, y0, Z_COLA - 30))


def tramo_cola(kit, y0, y1, s):
    cuerpo = estabilizador(kit, y0, y1)
    cuerpo = cuerpo - kit.cilindro(6.3, 900, en=(X_COLA + 0.27 * C_COLA, -450, Z_COLA), eje="y")
    cuerpo = cuerpo - tras_bisagra_cola(kit, y0 - 1, min(y1, TIMON_HASTA) + HOLGURA, -HOLGURA)
    return lado(cuerpo, s)


def timon_profundidad(kit, y0, y1, s):
    cuerpo = estabilizador(kit, y0, min(y1, TIMON_HASTA)) & tras_bisagra_cola(
        kit, y0 - 1, min(y1, TIMON_HASTA) + 1, HOLGURA)
    return lado(cuerpo, s)


def deriva_entera(kit):
    """La deriva sobre el final de la viga: de 190 de cuerda abajo a 130 arriba,
    y un carenado de Ø28 que abraza la viga 160 mm."""
    def sec(x, c):
        return kit.seccion([(x + u * c, Y_VIGA + v * c) for u, v in COLA])
    # Un pie de caras rectas abraza la viga y deja abajo una cara plana para
    # imprimirla de pie: el carenado redondo de la primera prueba colgaba en el
    # aire. El agujero de la viga va en lágrima, con la punta hacia arriba.
    d = kit.transicion([(sec(990, 190), -10), (sec(X_COLA, C_COLA), Z_COLA)], eje="z")
    d = d + kit.transicion([(kit.rectangulo(190, 30, 12), -45), (kit.rectangulo(190, 30, 12), -5)],
                           eje="z", en=(1085, Y_VIGA, 0))
    r = 10.15
    d = d - kit.cilindro(2 * r, 161, en=(989, Y_VIGA, Z_VIGA), eje="x")
    d = d - kit.extruir([(Y_VIGA - r * 0.7071, Z_VIGA + r * 0.7071),
                         (Y_VIGA + r * 0.7071, Z_VIGA + r * 0.7071),
                         (Y_VIGA, Z_VIGA + r * 1.4142)], 161, plano="yz", desde=989)
    return d - estabilizador(kit, 200, COLA_HASTA).mover(dz=-0.01)


def tras_bisagra_deriva(kit, margen):
    x = 1122 + margen
    return kit.extruir([(x, -4), (x + 300, -4), (x + 300, Z_COLA + 40), (x, Z_COLA + 40)], 80,
                       plano="xz", desde=Y_VIGA - 40)


def deriva(kit, s):
    return lado(deriva_entera(kit) - tras_bisagra_deriva(kit, -HOLGURA), s)


def timon(kit, s):
    t = deriva_entera(kit) & tras_bisagra_deriva(kit, HOLGURA)
    return lado(t - estabilizador(kit, 200, COLA_HASTA).mover(dz=-1), s)


def gondola(kit, x, s):
    """El soporte de un motor de sustentación: abraza la viga y deja arriba,
    a z = -3, una cara plana de 42 × 40 con cuatro M3 en un círculo de 25
    (el de un motor de la clase 4014; compruébalo con el que compres)."""
    g = kit.transicion([(kit.rectangulo(30, 30, 13), x - 45), (kit.rectangulo(42, 46, 6), x - 20),
                        (kit.rectangulo(42, 46, 6), x + 20), (kit.rectangulo(30, 30, 13), x + 45)],
                       eje="x", en=(0, 0, 0), recta=True)
    g = g.mover(dy=Y_VIGA, dz=-26) & kit.caja(200, 100, 100, en=(x - 100, Y_VIGA - 50, -100 - 3))
    g = g - kit.cilindro(20.3, 120, en=(x - 60, Y_VIGA, Z_VIGA), eje="x")
    g = g - kit.cilindro(10, 4, en=(x, Y_VIGA, -6))
    for k in range(4):
        a = radians(45 + 90 * k)
        g = g - kit.cilindro(2.8, 9, en=(x + 12.5 * cos(a), Y_VIGA + 12.5 * sin(a), -11))
    g = g - kit.cilindro(3.3, 60, en=(x + 30, Y_VIGA - 30, Z_VIGA), eje="y")   # pasador M3
    return lado(g, s)


def cara_de_abajo(x, z, c, alabeo):
    """Los puntos de la cara de abajo del perfil en su sitio, del borde de
    ataque al de salida."""
    px, pz = x + 0.27 * c, z + COMBA * c
    s, k = sin(radians(alabeo)), cos(radians(alabeo))
    i0 = 0
    for i in range(len(ALA)):
        if ALA[i][0] < ALA[i0][0]:
            i0 = i
    res = []
    for u, v in ALA[i0:]:
        dx, dz = x + u * c - px, z + v * c - pz
        res.append((px + dx * k + dz * s, pz - dx * s + dz * k))
    return res


def pilon(kit, s):
    """Une la viga al ala: una placa de 24 de grueso que por arriba copia la
    cara de abajo del ala y por abajo abraza la viga. Restarle el ala a un
    bloque dejaba trozos sueltos (prueba del 2026-11-16): aquí el borde de
    arriba se dibuja con los puntos del perfil."""
    abajo = [p for p in cara_de_abajo(*fuera(Y_VIGA)) if 200 <= p[0] <= 360]
    contorno = [(abajo[0][0], -27), (abajo[-1][0], -27)] + list(reversed(abajo))
    p = kit.extruir(contorno, 24, plano="xz", desde=Y_VIGA - 12)
    p = p - kit.cilindro(20.3, 300, en=(130, Y_VIGA, Z_VIGA), eje="x")
    return lado(p, s)
'''

# --- Las piezas ---------------------------------------------------------------
PIEZAS = []   # (id, nombre, qué hace, expresión)
CELDAS_X = [-260, -60, 140, 340, 540, 725]
for i, (x0, x1) in enumerate(zip(CELDAS_X, CELDAS_X[1:]), 1):
    PIEZAS.append((f"centro-{i}", f"Cuerpo central {i}",
                   "fuselaje y centro del ala, con la batería y la carga dentro",
                   f"cuerpo_central(kit) & kit.caja({x1 - x0}, 190, 300, en=({x0}, -95, -150))"))
for s, nombre, el in ((1, "derecha", "derecho"), (-1, "izquierda", "izquierdo")):
    for i, (x0, x1) in enumerate(((-10, 230), (230, 475)), 1):
        y0 = 95 if s > 0 else -250
        PIEZAS.append((f"raiz-{nombre[0]}-{i}", f"Raíz del ala {nombre} {i}",
                       "donde el ala se funde con el fuselaje",
                       f"cuerpo_central(kit) & kit.caja({x1 - x0}, 155, 300, en=({x0}, {y0}, -150))"))
    for i, (y0, y1) in enumerate(zip(CORTES_ALA, CORTES_ALA[1:]), 1):
        PIEZAS.append((f"ala-{nombre[0]}-{i}", f"Ala {nombre}, tramo {i}",
                       f"de {y0} a {y1} mm del centro, con los dos largueros",
                       f"tramo_ala(kit, {y0}, {y1}, {s})"))
        if y0 >= ALERON_DESDE:
            PIEZAS.append((f"aleron-{nombre[0]}-{i}", f"Alerón {el} {i}",
                           "se mueve con un servo de 9 g", f"aleron(kit, {y0}, {y1}, {s})"))
    for i, (y0, y1) in enumerate(zip(CORTES_COLA, CORTES_COLA[1:]), 1):
        PIEZAS.append((f"cola-{nombre[0]}-{i}", f"Estabilizador {el} {i}",
                       "la cola en H, sobre las derivas", f"tramo_cola(kit, {y0}, {y1}, {s})"))
        PIEZAS.append((f"profundidad-{nombre[0]}-{i}", f"Timón de profundidad {el} {i}",
                       "se mueve con un servo de 9 g", f"timon_profundidad(kit, {y0}, {y1}, {s})"))
    PIEZAS.append((f"deriva-{nombre[0]}", f"Deriva {nombre}", "al final de la viga",
                   f"deriva(kit, {s})"))
    PIEZAS.append((f"timon-{nombre[0]}", f"Timón de dirección {el}",
                   "se mueve con un servo de 9 g", f"timon(kit, {s})"))
    for x, donde in zip(MOTORES_X, ("delantera", "trasera")):
        PIEZAS.append((f"motor-{nombre[0]}-{donde[0]}", f"Góndola {donde} {nombre}",
                       "un motor de sustentación sobre la viga", f"gondola(kit, {x}, {s})"))
    PIEZAS.append((f"pilon-{nombre[0]}", f"Pilón {el}", "une la viga al ala",
                   f"pilon(kit, {s})"))

if SOLO:
    PIEZAS = [p for p in PIEZAS if p[0] == SOLO]

obra = Obra(titulo="VTOL de 2,6 m, a mano y sin modelo",
            nodos=[{"id": i, "nombre": n, "que_hace": q} for i, n, q, _ in PIEZAS])
O.guardar(P, obra, por="mano")
if len(PIEZAS) > 1:
    O.aprobar(P, por="mano")
m, c = D["masa_kg"], D["crucero"]
(P / "request.md").write_text(
    "VTOL de ala integrada, «como el TerraHawk pero mejorado». **Diseñado a mano por el "
    "asistente el 2026-11-16, no por el modelo**: las cuentas con AeroSandbox "
    "(`scripts/avion_vtol_dimensionar.py`) y las piezas con el kit "
    "(`scripts/avion_vtol_a_mano.py`).\n\n"
    f"- Envergadura {D['envergadura_m']} m, ala de {D['area_alar_m2']} m², alargamiento "
    f"{D['alargamiento']}; perfil SD7037 en el ala y NACA 0009 en la cola.\n"
    f"- Peso al despegar {m['total']} kg, con {m['carga útil']} kg de carga (dos cámaras y un "
    f"lidar) y una batería 6S{D['bateria']['paralelo']}P de 21700 ({D['bateria']['Wh']} Wh, "
    f"{[v for k, v in m.items() if k.startswith('batería')][0]} kg).\n"
    f"- Crucero a {c['velocidad_m_s'] * 3.6:.0f} km/h: L/D {c['L_D']}, {c['potencia_W']} W. "
    f"Autonomía {D['autonomia_h']} h y {D['alcance_km']:.0f} km, con 15 % de reserva y "
    f"{D['vtol']['minutos']:.0f} min de vuelo vertical ({D['vtol']['potencia_W']:.0f} W).\n"
    f"- Pérdida a {D['perdida_m_s']} m/s; centro de gravedad a {D['estabilidad']['cg_x_m'] * 1000:.0f} "
    "mm del borde de ataque del centro (margen estático del 10 %).\n\n"
    "**Se compra:** dos vigas de carbono de Ø20 × 1,3 m; largueros de carbono de Ø12 (2 × 1,1 m) "
    "y de Ø6 (2 × 1,3 m) y una varilla de Ø6 × 0,8 m para la cola; cuatro motores de "
    "sustentación de la clase 4014 con hélices de 15\" y sus variadores; un motor de empuje "
    "de la clase 3515 con hélice de 13\"; 60 celdas 21700 de 4,5 Ah; controladora, GPS, "
    "telemetría y seis servos de 9 g. Los motores y las celdas son una propuesta del "
    "asistente, sin comprobar contra su tienda.\n\n"
    "**Lo que no está medido:** que vuele. Las masas de lo impreso y de lo comprado y los "
    "rendimientos son estimaciones del asistente; la aerodinámica es la de AeroSandbox, no "
    "un túnel. El Cuerpo central 3 pide soporte en dos puntos de 38 mm², donde el larguero "
    "cruza la pared del fuselaje.\n", encoding="utf-8")

hechas, fallos = [], []
for id_, nombre, _, expr in PIEZAS:
    t = time.time()
    codigo = COMUN + f"\n\ndef construir(kit):\n    return {expr}\n"
    try:
        _lista(P, id_, codigo)
    except Exception as e:  # noqa: BLE001
        fallos.append(id_)
        print(f"{id_}: NO SE CONSTRUYÓ: {type(e).__name__}: {str(e)[-800:]}", flush=True)
        continue
    parte = O._pieza_construida(P / O.NODOS / id_)
    env = json.loads((parte / "envolvente.json").read_text(encoding="utf-8"))
    mide = sorted(round(b - a, 1) for a, b in zip(env["min"], env["max"]))
    cabe = mide[0] <= 235 and mide[1] <= 235 and mide[2] <= 250
    from orchestrator.voladizos import como_imprimir
    [stl] = list(parte.glob("*.stl"))
    postura, zonas = como_imprimir(stl, 45, 10)
    hechas.append(id_)
    print(f"{id_}: {time.time() - t:.0f} s, mide {mide}{'' if cabe else ' NO CABE'}; "
          f"{'sin soportes' if postura else 'PIDE SOPORTES'}", flush=True)
    if not postura:
        from orchestrator.voladizos import zona_en_palabras
        mejor = min(zonas, key=lambda q: sum(z.area_mm2 for z in zonas[q]))
        for z in zonas[mejor][:4]:
            print(f"    {mejor}: {zona_en_palabras(z)}", flush=True)

print(f"HECHAS {len(hechas)} de {len(PIEZAS)}; fallan: {fallos}", flush=True)
if not SOLO and hechas:
    from orchestrator.vista import dibujar_piezas
    stls = sorted(P.glob("nodos/*/parts/*/*.stl"))
    print("VISTA:", dibujar_piezas(stls, P / "vista.png", "VTOL de 2,6 m, a mano"))
