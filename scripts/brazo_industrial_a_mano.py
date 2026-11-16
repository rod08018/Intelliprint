"""El brazo de seis ejes con forma de brazo industrial, A MANO y sin modelo.

Las siete piezas del encargo 18 (600 mm, 2 kg) escritas por el asistente con el
kit: un tambor en cada articulación y tramos que van de tambor a tambor, con
el hueco de cada motor, el rodamiento, la polea y sus tornillos. Es la forma
que el usuario aprobó en un boceto el 2026-11-15 (ADR-023), puesta a prueba
con piezas de verdad antes de dársela al sistema. **No es el sistema ni es
nota suya**: dice que estas formas se construyen, se imprimen sin soportes y
pasan el banco; no que el modelo sepa dibujarlas.

Construye las piezas una a una, las mide como en su bucle, monta el conjunto y
lo juzga con el encargo del banco, todo en una carpeta temporal:

    docker compose run --rm -T -e SOPORTES=1 --entrypoint python3 suite - /tmp/brazo [hasta_qué_pieza] < scripts/brazo_industrial_a_mano.py

(por la entrada, para que `orchestrator` y `tests` se importen desde /app).

Con una carpeta montada en /salida deja ahí el STEP y el STL de cada pieza.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

from mech_toolkit import transmisiones as T
from orchestrator import banco, cli, modulos
from orchestrator import obra as O
from orchestrator.plan import validar_plan
from orchestrator.schemas.obra import Obra
from tests.test_brazo_grande import PLAN
from tests.test_revalidar import _lista

raiz = cli._raiz()
os.chdir(raiz)
CORRIDA = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/brazo")
HASTA = sys.argv[2] if len(sys.argv) > 2 else "brida"
if CORRIDA.exists() and not str(CORRIDA).startswith("/tmp/"):
    raise SystemExit(f"{CORRIDA} ya existe y no es temporal: no se toca")
shutil.rmtree(CORRIDA, ignore_errors=True)
PROYECTO = HASTA == "proyecto"
HASTA = "brida" if PROYECTO else HASTA
P = CORRIDA if PROYECTO else CORRIDA / "01" / "projects" / "a"
P.mkdir(parents=True)
os.environ["INTELLIPRINT_WORKSPACE"] = str(P.parent.parent)
env = dict(os.environ)
freecad = cli._freecadcmd(env)
perfil = cli._perfil(raiz, env)

# La correa de la base: la más corta que deja el motor a más de 78 mm del eje.
correa, C = next((n, c) for n in range(60, 400, 5)
                 if (c := T.distancia_entre_ejes(20, 100, n)) and c >= 78)
print(f"correa de {correa} dientes: ejes a {C:.2f} mm", flush=True)


# Las piezas del brazo industrial, escritas a mano por el asistente con el kit:
# para probar las formas (un tambor por articulación, tramos de tambor a
# tambor) con sus motores, rodamientos y tornillos de verdad, sin modelo.
# Se pega entre brazo_industrial_cabeza.py y brazo_industrial_cola.py.

COMUN = f'''
C = {C!r}            # del eje de la base al del motor que la mueve
HB = 78.0            # el alto de la base: su cara de arriba
RB = 82.0            # el radio de la base alrededor de su eje
RM = 50.0            # el de la joroba que tapa el motor
RT = 40.0            # el radio de la columna giratoria donde acaba su cono: no más que la cara del hombro, o roza el brazo
ZT = HB + 20.0       # y la altura a la que acaba
HS = 185.0           # la altura del hombro
DT = 100.0           # el diámetro del tambor del hombro
YF = 34.0            # la cara por donde sale el eje del hombro, hacia +y
YA = YF + 8.0        # la cara de dentro del brazo superior
GA = 50.0            # su grosor
ZE = HS + 190.0      # el codo
RE = 44.0            # el radio del brazo superior en el codo
YJ = -12.0           # el eje del antebrazo: su motor pasa al lado del eje del codo
Z4 = ZE + 145.0      # la cara del plato del giro del antebrazo
ZW = Z4 - 24.3       # la tapa del antebrazo, donde se apoya la reductora
Z5 = Z4 + 140.0      # el eje del cabeceo
YP = YJ + 40 + 24.3  # la cara del plato del cabeceo, hacia +y
ZP = Z5 + 87.2       # la tapa de la mano
Z6 = ZP + 24.3       # la cara del plato del último giro
ACOPLE = [(20, 0), (0, 20), (-20, 0), (0, -20)]


def capsula(kit, x1, r1, x2, r2, z0, alto):
    """Dos tambores de eje vertical unidos por sus tangentes."""
    s = (r1 - r2) / (x2 - x1)
    c = sqrt(1 - s * s)
    entre = [(x1 + r1 * s, r1 * c), (x2 + r2 * s, r2 * c),
             (x2 + r2 * s, -r2 * c), (x1 + r1 * s, -r1 * c)]
    return (kit.cilindro(2 * r1, alto, en=(x1, 0, z0), eje="z")
            + kit.cilindro(2 * r2, alto, en=(x2, 0, z0), eje="z")
            + kit.extruir(entre, alto, plano="xy", desde=z0))
'''

# Un pedestal hueco, con el motor de la base bajo su joroba. Se imprime boca
# abajo: la tapa en la cama y las paredes subiendo. Los tornillos del tablero
# bajan por cuatro columnas huecas, como los de una bancada de fundición.
BASE = COMUN + '''
PILARES = [(52, 68), (52, -68), (-C - 12, 55), (-C - 12, -55)]


def construir(kit):
    cuerpo = capsula(kit, 0, RB, -C, RM, 0, HB).redondear(6, "arriba")
    for x, y in PILARES:
        cuerpo = cuerpo + kit.cilindro(18, HB, en=(x, y, 0), eje="z")
    pieza = cuerpo.quitar("interior", capsula(kit, 0, RB - 5, -C, RM - 5, -1, HB - 9))
    # El rodamiento va hundido 7 mm: encima de él cabe el cono que sube del
    # eje a la polea, que si no dejaba un techo plano bajo ella.
    pieza = pieza + kit.cilindro(82, 17, en=(0, 0, HB - 26), eje="z")
    rod = kit.componente("6810-2rs", en=(0, 0, HB - 14), entra_por="+z")
    pieza = pieza.quitar("asiento del rodamiento", rod.hueco("press"))
    pieza = pieza.quitar("paso del eje", kit.cilindro(58, 29, en=(0, 0, HB - 27), eje="z"))
    motor = kit.componente("nema23", en=(-C, 0, HB - 7), entra_por="-z")
    pieza = pieza.quitar("paso del motor", motor.hueco())
    for n, a in enumerate(motor.agujeros()):
        x, y, z = a["en"]
        pieza = pieza.tornillo("motor %d" % n, "M4", en=(x, y, HB), eje="-z")
    for n, (x, y) in enumerate(PILARES):
        pieza = pieza.taladrar("acceso %d" % n, 10, en=(x, y, HB), eje="-z", profundidad=HB - 8)
        pieza = pieza.tornillo("tablero %d" % n, "M4", en=(x, y, 8), eje="-z")
    return pieza.acabar()
'''

# La columna giratoria: el eje y la polea abajo, un cono que se abre, y una
# columna que sube hasta el tambor del hombro, que lleva dentro la reductora.
# Se imprime de pie: todo lo de fuera sube derecho o se cierra hacia dentro.
TORRETA = COMUN + '''
def construir(kit):
    kit.componente("obra-base", en=(0, 0, 0), entra_por="-z")
    y0, y1 = YF - 74, YF + 6
    eje = kit.cilindro(50 - kit.holgura("slide"), 8, en=(0, 0, HB - 15), eje="z")
    sube = kit.cono(50 - kit.holgura("slide"), 66, 8.5, en=(0, 0, HB - 7), eje="z")
    cono = kit.cono(66, 2 * RT, ZT - (HB + 11), en=(0, 0, HB + 11), eje="z")
    # La columna se abre pronto hasta lo que mide el tambor: si se abría
    # despacio, las esquinas de abajo del tambor salían de ella en el aire.
    columna = kit.transicion([(kit.elipse(2 * RT, 2 * RT), 0),
                              (kit.rectangulo(DT, y1 - y0, radio=8), HS - DT / 2 - 5 - ZT),
                              (kit.rectangulo(DT, y1 - y0, radio=8), HS - ZT)],
                             eje="z", en=(0, (y0 + y1) / 2, ZT), recta=True)
    tambor = kit.cilindro(DT, y1 - y0, en=(0, y0, HS), eje="y")
    pieza = eje + sube + cono + columna + tambor
    hombro = kit.componente("nema23-pg47-76", en=(0, YF, HS), girar=[("x", -90)],
                            entra_por="-y")
    pieza = pieza.quitar("paso del hombro", hombro.hueco())
    # Un agujero redondo tumbado tiene techo: se le pone tejado a 45°.
    tejado = kit.extruir([(-20.5, HS + 19.5), (20.5, HS + 19.5), (0, HS + 40.5)], 75,
                         plano="xz", desde=y0 - 1)
    pieza = pieza.quitar("tejado del hombro", tejado)
    for n, a in enumerate(hombro.agujeros()):
        x, y, z = a["en"]
        pieza = pieza.tornillo("hombro %d" % n, "M5", en=(x, y1, z), eje="-y", avellanado=10.5)
    pieza = pieza.acabar()
    return pieza + kit.polea_gt2("polea", 100, en=(0, 0, HB + 1.5), eje="+z")
'''

# El brazo superior: dos tambores unidos por sus tangentes, con un rebaje en
# la cara de fuera. Se dibuja tumbado, que es como se imprime (la cara de
# dentro en la cama), y se pone de pie antes de taladrarlo.
BRAZO = COMUN + '''
def de_pie(cuerpo):
    return cuerpo.girar(-90, eje="y").girar(-90, eje="z").mover(0, YA, HS)


def construir(kit):
    kit.componente("obra-torreta", en=(0, 0, 0), entra_por="-y")
    losa = capsula(kit, 0, DT / 2, ZE - HS, RE, 0, GA).redondear(6, "arriba")
    rebaje = capsula(kit, 0, DT / 2 - 12, ZE - HS, RE - 12, GA - 2.5, 5)
    pieza = de_pie(losa).quitar("rebaje", de_pie(rebaje))
    pieza = pieza.taladrar("eje del hombro", 12 + kit.holgura("slide"), en=(0, YA + GA, HS),
                           eje="-y")
    codo = kit.componente("nema23-pg47-56", en=(0, YA + 6, ZE), girar=[("x", 90)],
                          entra_por="+y")
    pieza = pieza.quitar("paso del codo", codo.hueco())
    for n, a in enumerate(codo.agujeros()):
        x, y, z = a["en"]
        pieza = pieza.tornillo("codo %d" % n, "M5", en=(x, YA, z), eje="+y", avellanado=10.5)
    return pieza.acabar()
'''

# El antebrazo: una cáscara que se afina hasta el aro del giro, con el motor
# dentro y la cola abierta por donde entra. Se imprime boca abajo, con la tapa
# en la cama. El cubo del codo lleva una rampa encima: sin ella, boca abajo,
# sería un tambor que sale de la pared en el aire.
ANTEBRAZO = COMUN + '''
def construir(kit):
    kit.componente("obra-brazo", en=(0, 0, 0), entra_por="+y")
    z0 = ZE - 70
    cuerpo = kit.transicion([(kit.rectangulo(76, 56, radio=24), 0),
                             (kit.rectangulo(100, 56, radio=26), 40),
                             (kit.rectangulo(100, 56, radio=26), ZW - 40 - z0),
                             (kit.elipse(80, 80), ZW - z0)],
                            eje="z", en=(0, YJ, z0), recta=True)
    cuerpo = cuerpo.vaciar(5, abierta="-z")
    cubo = kit.cilindro(70, 29, en=(0, 11, ZE), eje="y")
    rampa = kit.extruir([(11, ZE), (40, ZE), (40, ZE + 35), (16, ZE + 62), (11, ZE + 62)], 70,
                        plano="yz", desde=-35)
    pieza = cuerpo + cubo + rampa
    pieza = pieza.taladrar("eje del codo", 12 + kit.holgura("slide"), en=(0, 40, ZE), eje="-y",
                           profundidad=26)
    motor = kit.componente("nema17", en=(0, YJ, ZW - 5), girar=[("z", 90)], entra_por="-z")
    pieza = pieza.quitar("paso del motor", motor.hueco())
    kit.componente("cicloidal-nema17-28", en=(0, YJ, ZW), entra_por="+z")
    for n, a in enumerate(motor.agujeros()):
        x, y, z = a["en"]
        pieza = pieza.tornillo("motor %d" % n, "M3", en=(x, y, ZW), eje="-z")
    return pieza.acabar()
'''

# La muñeca: una bandeja con la forma del tambor del cabeceo arriba. El suelo
# de la bandeja es la pared donde se atornillan el motor (dentro) y la
# reductora (fuera); se imprime con ese suelo en la cama y queda abierta por
# el otro lado, que es por donde entra el motor.
GIRO = COMUN + '''
def construir(kit):
    kit.componente("obra-antebrazo", en=(0, 0, 0), entra_por="-z")
    y0, y1 = YJ - 40, YJ + 40
    fuera = (kit.caja(80, 80, Z5 - Z4, en=(-40, y0, Z4))
             + kit.cilindro(80, 80, en=(0, y0, Z5), eje="y"))
    dentro = (kit.caja(70, 75, Z5 - Z4 - 6, en=(-35, y0 - 1, Z4 + 6))
              + kit.cilindro(70, 75, en=(0, y0 - 1, Z5), eje="y"))
    pieza = fuera.quitar("interior", dentro)
    motor = kit.componente("nema17", en=(0, y1 - 6, Z5), girar=[("z", 180), ("x", -90)],
                           entra_por="-y")
    pieza = pieza.quitar("paso del motor", motor.hueco())
    kit.componente("cicloidal-nema17-28", en=(0, y1, Z5), girar=[("x", -90)], entra_por="+y")
    for n, a in enumerate(motor.agujeros()):
        x, y, z = a["en"]
        pieza = pieza.tornillo("motor %d" % n, "M3", en=(x, y1, z), eje="-y")
    for n, (dx, dy) in enumerate(ACOPLE):
        # La llave baja derecha hasta cada tornillo del plato por un agujero del techo.
        pieza = pieza.taladrar("acceso %d" % n, 6.5, en=(dx, YJ + dy, Z5 + 41), eje="-z",
                               profundidad=12)
        pieza = pieza.tornillo("acople %d" % n, "M3", en=(dx, YJ + dy, Z4 + 6), eje="-z")
    return pieza.acabar()
'''

# La mano: otra bandeja, con el tambor abajo (gira en el cabeceo) y la tapa
# arriba, donde van el motor y la reductora del último giro.
MANO = COMUN + '''
def construir(kit):
    kit.componente("obra-giro", en=(0, 0, 0), entra_por="-y")
    fuera = (kit.caja(80, 80, ZP - Z5, en=(-40, YP, Z5))
             + kit.cilindro(80, 80, en=(0, YP, Z5), eje="y"))
    dentro = (kit.caja(70, 75, ZP - 6 - Z5, en=(-35, YP + 6, Z5))
              + kit.cilindro(70, 75, en=(0, YP + 6, Z5), eje="y"))
    pieza = fuera.quitar("interior", dentro)
    motor = kit.componente("nema17", en=(0, YP + 40, ZP - 6), girar=[("z", 180)],
                           entra_por="+y")
    pieza = pieza.quitar("paso del motor", motor.hueco())
    kit.componente("cicloidal-nema17-10", en=(0, YP + 40, ZP), entra_por="+z")
    for n, (dx, dz) in enumerate(ACOPLE):
        pieza = pieza.tornillo("acople %d" % n, "M3", en=(dx, YP + 6, Z5 + dz), eje="-y")
    for n, a in enumerate(motor.agujeros()):
        x, y, z = a["en"]
        pieza = pieza.tornillo("motor %d" % n, "M3", en=(x, y, ZP), eje="-z")
    return pieza.acabar()
'''

# La brida: donde se atornilla la herramienta, y hasta donde se mide el alcance.
BRIDA = COMUN + '''
def construir(kit):
    kit.componente("obra-mano", en=(0, 0, 0), entra_por="-z")
    yb = YP + 40
    pieza = kit.cilindro(63, 14, en=(0, yb, Z6), eje="z")
    for n, (dx, dy) in enumerate(ACOPLE):
        pieza = pieza.tornillo("acople %d" % n, "M3", en=(dx, yb + dy, Z6 + 14), eje="-z")
    for n, (dx, dy) in enumerate([(9, 9), (-9, 9), (-9, -9), (9, -9)]):
        pieza = pieza.tornillo("herramienta %d" % n, "M3", en=(dx, yb + dy, Z6 + 14), eje="-z")
    return pieza.acabar()
'''


(P / "request.md").write_text(
    "Brazo de seis ejes, 600 mm y 2 kg, con forma de brazo industrial, escrito a mano por el asistente y sin "
    "modelo (2026-11-15): para probar las formas antes de dárselas al sistema.\n",
    encoding="utf-8")
obra = Obra(**{**PLAN, "titulo": "Brazo industrial de seis ejes, a mano y sin modelo"})
print("PLAN:", validar_plan(obra, perfil.datos["holes"]), flush=True)
from orchestrator import dimensionar  # noqa: E402
print("dimensionado:", [(p["union"], round(p["pide_Nm"], 3), round(p["da_Nm"], 3))
                        for p in dimensionar.pares(obra)], flush=True)
O.guardar(P, obra, por="mano")
O.aprobar(P, por="mano")
os.environ["INTELLIPRINT_FICHAS"] = str(O.carpeta_de_fichas(P))
os.environ.pop("INTELLIPRINT_AJENOS", None)
os.environ.pop("INTELLIPRINT_UNIONES", None)


def medir(nodo):
    from orchestrator.medida import (componentes_sin_colocar, defectos_de_alcance,
                                     defectos_de_giro, defectos_de_orientacion,
                                     no_cabe_en_la_impresora, sin_sitio_para_lo_nuevo,
                                     uniones_sin_hacer)
    from orchestrator.transmision import defectos_de_transmision
    parte = O._pieza_construida(P / O.NODOS / nodo)
    rasgos = json.loads((parte / "rasgos.json").read_text(encoding="utf-8"))
    e = json.loads((parte / "envolvente.json").read_text(encoding="utf-8"))
    mide = [round(b - a, 1) for a, b in zip(e["min"], e["max"])]
    print("  mide", mide, flush=True)
    medidas = {"sin colocar": lambda: componentes_sin_colocar(obra.nodo(nodo).compra, rasgos),
               "giro": lambda: defectos_de_giro(P, nodo),
               "eje": lambda: defectos_de_orientacion(P, nodo),
               "alcance": lambda: defectos_de_alcance(P, nodo),
               "tornillos": lambda: uniones_sin_hacer(P, nodo),
               "sitio": lambda: sin_sitio_para_lo_nuevo(P, nodo),
               "correa": lambda: defectos_de_transmision(P, nodo),
               "cama": lambda: no_cabe_en_la_impresora(mide, perfil.cama_mm)}
    for que, f in medidas.items():
        try:
            print(f"  {que}: {f() or 'bien'}", flush=True)
        except Exception as fallo:  # noqa: BLE001
            print(f"  {que}: SE ROMPIÓ: {type(fallo).__name__}: {fallo}", flush=True)


PIEZAS = (("base", BASE), ("torreta", TORRETA), ("brazo", BRAZO), ("antebrazo", ANTEBRAZO),
          ("giro", GIRO), ("mano", MANO), ("brida", BRIDA))
for nodo, codigo in PIEZAS:
    t = time.time()
    os.environ["INTELLIPRINT_UNIONES"] = str(O.escribir_uniones(P, nodo))
    try:
        _lista(P, nodo, codigo)
    except Exception as fallo:  # noqa: BLE001
        print(f"{nodo}: NO SE CONSTRUYÓ: {type(fallo).__name__}: {str(fallo)[-1500:]}", flush=True)
        raise SystemExit(1)
    print(f"{nodo}: construida en {time.time() - t:.0f} s", flush=True)
    if Path("/salida").is_dir():
        parte = O._pieza_construida(P / O.NODOS / nodo)
        for f in list(parte.glob("*.step")) + list(parte.glob("*.stl")):
            shutil.copy(f, Path("/salida") / f"{nodo}{f.suffix}")
    if os.environ.get("SOPORTES"):
        from orchestrator.voladizos import defecto_de_soportes
        parte = O._pieza_construida(P / O.NODOS / nodo)
        [stl] = list(parte.glob("*.stl"))
        print("  soportes:", defecto_de_soportes(stl, perfil.datos.get("impresion") or perfil.datos) or "bien", flush=True)
    if PROYECTO:
        continue      # para verlo en la web no hace falta medir cada pieza, que tarda
    medir(nodo)
    if nodo == HASTA:
        break
os.environ.pop("INTELLIPRINT_UNIONES", None)
if HASTA != "brida":
    raise SystemExit(0)

t = time.time()
print("módulos:", len(modulos.construir(P, freecad, perfil.datos)), f"piezas en {time.time() - t:.0f} s",
      flush=True)
from orchestrator.conjunto import VERIFICACION, verificar_conjunto  # noqa: E402
t = time.time()
v = verificar_conjunto(P, "todo", freecad, min_gap_mm=perfil.impresora.fit_mm("slide") / 2,
                       animar=False)
print(f"conjunto: movido en {time.time() - t:.0f} s; ok: {v['ok']}", flush=True)
for a in v["articulaciones"]:
    print(f"  «{a['pieza']}» sobre «{a['padre']}» ({a['de']}), de {a['recorrido'][0]:g}° a "
          f"{a['recorrido'][1]:g}°; eje {[round(x, 2) for x in a['eje_mundo']]}")
print("\n".join(f"  - {x}" for x in v["resumen"]), flush=True)
if not (P / O.NODOS / "todo" / VERIFICACION).is_file():
    (P / O.NODOS / "todo").mkdir(parents=True, exist_ok=True)
    (P / O.NODOS / "todo" / VERIFICACION).write_text(json.dumps(v), encoding="utf-8")

if PROYECTO:
    from orchestrator.vista import dibujar_piezas
    stls = sorted(P.glob("nodos/*/parts/*/*.stl"))
    print("VISTA:", dibujar_piezas(stls, P / "vista.png", "Brazo de seis ejes, a mano"))
    raise SystemExit(0)
[e] = [e for e in banco.cargar_encargos(Path("tests/banco/encargos"))
       if e.nombre == "brazo_seis_ejes_2kg"]
resultados = banco.juzgar_obra(e, CORRIDA / "01", freecad, perfil.datos["resistencia"])
for a, r in zip(e.oraculo, resultados):
    print(f"JUEZ {a.tipo}: {r.estado} — {r.detalle}", flush=True)
print("NOTA:", sum(r.estado == "cumple" for r in resultados), "de", len(resultados))
from orchestrator.estudio import estudio_entero  # noqa: E402
try:
    est = estudio_entero(P, "todo", freecad, raiz)
    for m in est.get("material", []):
        print("MATERIAL:", m["nombre"], m["carga_max_g"], "|", m["detalle"])
    for s in est["servos"]:
        print("MOTOR:", {k: s.get(k) for k in ("nombre", "par_max_Nm", "par_disponible_Nm",
                                               "aguanta", "carga_max_g")})
except Exception as fallo:  # noqa: BLE001
    print("ESTUDIO: SE ROMPIÓ:", type(fallo).__name__, fallo)
from orchestrator.materiales import materiales  # noqa: E402
print("SE COMPRA:", [(c["nombre"], c["cuantos"]) for c in materiales(P)["comprado"]])

