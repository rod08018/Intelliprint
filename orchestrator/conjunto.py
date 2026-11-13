"""Un conjunto de la obra se verifica moviéndolo (F7.4 (conjunto)).

Hasta el 2026-11-09 el nodo «conjunto» del pan-tilt decía «su verificación
aún no existe»: cada pieza se medía sola y nadie movía el giro y la
inclinación juntos para ver si algo chocaba.

La cinemática no se le pide a un modelo, sale de la geometría construida:

- **Sobre qué va cada pieza.** Cada una colocó con `kit.componente` la pieza
  de la obra sobre la que se diseñó; sus rasgos guardan dónde.
- **Alrededor de qué gira.** Lo comprado que monta la pieza de abajo tiene
  sus `salidas` en la ficha (el eje del SG90). La pieza que llega a ese eje
  gira con él; la que no, va fija.
- **Cuánto.** El recorrido de la ficha, sacado de su hoja de datos.

Luego se barre todo el recorrido en FreeCAD con las piezas construidas y los
cuerpos de lo comprado, y cada choque dice en qué ángulos pasa.
"""

import itertools
import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from mech_toolkit.componentes import colocar, orientar, primitivas
from mech_toolkit.geometry import Placement

VERIFICACION = "verificacion.json"
ALCANCE_MM = 5.0
"""Hasta dónde se considera que una pieza toca un eje: el cuerno del SG90
sobresale 3.6 de la carcasa (TA0233), y lo que se acopla a él está ahí."""
PASO = 10.0
IGNORAR = (-1e9, None)
SE_TOCAN = (0.0, None)
"""Entre dos piezas sin ningún giro por medio —atornilladas una a otra—:
tocarse sí, atravesarse no. La holgura del perfil es para lo que se mueve.
La pinza del banco 1112-1359 «chocaba en reposo» con la plataforma a la que
va atornillada, por quedar a 0.00 mm de ella."""


# --- giros, sin numpy ------------------------------------------------------------------------

def _mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mv(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


def _tr(a):
    return [list(c) for c in zip(*a)]


I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _componer(a, b):
    """(R, t) de b seguido de a: p -> Ra·(Rb·p + tb) + ta."""
    (ra, ta), (rb, tb) = a, b
    return _mm(ra, rb), [x + y for x, y in zip(_mv(ra, tb), ta)]


def _inversa(t):
    r, d = t
    rt = _tr(r)
    return rt, [-x for x in _mv(rt, d)]


def _giros(giros) -> list:
    """La matriz de los cuartos de vuelta de un componente, como los aplica
    `mech_toolkit.componentes.colocar`."""
    columnas = [colocar(e, (0, 0, 0), giros) for e in ([1, 0, 0], [0, 1, 0], [0, 0, 1])]
    return _tr(columnas)


def _rodrigues(eje, grados) -> list:
    """Girar `grados` alrededor de `eje` (mano derecha)."""
    n = math.sqrt(sum(c * c for c in eje))
    x, y, z = (c / n for c in eje)
    c, s = math.cos(math.radians(grados)), math.sin(math.radians(grados))
    k = 1 - c
    return [[c + x * x * k, x * y * k - z * s, x * z * k + y * s],
            [y * x * k + z * s, c + y * y * k, y * z * k - x * s],
            [z * x * k - y * s, z * y * k + x * s, c + z * z * k]]


def _angulos_freecad(r) -> list[float]:
    """(rx, ry, rz) en grados con R = Rz·Ry·Rx, como coloca el ensamble. Con
    la inclinación a ±90° hay bloqueo de cardán: rz va a 0 y rx lo da todo."""
    s = max(-1.0, min(1.0, -r[2][0]))
    if abs(s) < 1 - 1e-9:
        ry = math.asin(s)
        rx = math.atan2(r[2][1], r[2][2])
        rz = math.atan2(r[1][0], r[0][0])
    else:
        ry = math.copysign(math.pi / 2, s)
        rx = math.atan2(math.copysign(1, s) * r[0][1], r[1][1])
        rz = 0.0
    return [math.degrees(rx), math.degrees(ry), math.degrees(rz)]


def _placement(t) -> Placement:
    r, d = t
    return Placement(origin=[float(x) for x in d], rotation=_angulos_freecad(r))


# --- las piezas y sus articulaciones ---------------------------------------------------------

@dataclass
class Pieza:
    id: str
    nombre: str
    step: Path
    envolvente: tuple[list, list]
    padre: str | None = None
    al_padre: tuple | None = None
    """(R, t): de su marco al de la pieza sobre la que va."""
    montados: list[dict] = field(default_factory=list)
    """Cajas y cilindros de lo comprado que monta, en su marco, con «de»."""
    salidas: list[dict] = field(default_factory=list)
    propios: list[dict] = field(default_factory=list)
    """Los rasgos de lo comprado que aloja ella, sin lo que coloca solo para
    dejar hueco a lo de otra: el banco cuenta los SG90 de la obra con esto."""


@dataclass
class Articulacion:
    pieza: str
    padre: str
    de: str
    punto: list
    eje: list
    recorrido: tuple


def leer_piezas(carpeta: Path, conjunto: str | None = None,
                solo_construidas: bool = False) -> dict[str, Pieza]:
    """Las piezas del conjunto (sin conjunto, todas las de la obra), en el
    orden de la obra: lo de abajo antes. `solo_construidas` salta las que no
    llegaron a construirse, para que el banco juzgue lo que haya."""
    from orchestrator import obra as O
    from orchestrator.componentes import cargar

    carpeta = Path(carpeta)
    ob = O.cargar_obra(carpeta)
    ids = [i for i in ob.orden() if ob.nodo(i).tipo == "pieza"
           and (conjunto is None or i in ob.nodo(conjunto).depende_de)]
    fichas = O.carpeta_de_fichas(carpeta)
    piezas: dict[str, Pieza] = {}
    en_el_mundo: dict[str, tuple] = {}
    vistos: list[tuple] = []
    for i in ids:
        try:
            parte = O._pieza_construida(carpeta / O.NODOS / i)
        except ValueError:
            if solo_construidas:
                continue
            raise
        env = json.loads((parte / "envolvente.json").read_text(encoding="utf-8"))
        rasgos = (json.loads((parte / "rasgos.json").read_text(encoding="utf-8"))
                  if (parte / "rasgos.json").is_file() else [])
        p = Pieza(i, ob.nodo(i).nombre, O._step_de(parte), (env["min"], env["max"]))
        comprados = []
        for r in rasgos:
            if r.get("tipo") != "componente" or not r.get("ficha"):
                continue
            giros = [tuple(g) for g in r.get("giros") or []]
            otra = r["ficha"].removeprefix("obra-")
            if r["ficha"].startswith("obra-") and otra in piezas:
                if p.padre is None:   # la primera que colocó: sobre la que va
                    p.padre = otra
                    p.al_padre = _inversa((_giros(giros), list(r["en"])))
                continue
            ficha = cargar(r["ficha"], [fichas])
            if ficha.origen != "impreso":
                comprados.append((r["nombre"], ficha, list(r["en"]), giros, r))
        en_el_mundo[i] = (_componer(en_el_mundo[p.padre], p.al_padre) if p.padre
                          else (I3, [0.0, 0.0, 0.0]))
        for de, ficha, en, giros, rasgo in comprados:
            # La plataforma del pan-tilt coloca también el SG90 del soporte, en
            # su mismo sitio, para dejarle hueco: es del soporte, no suyo. Si
            # fuera suyo giraría con ella y «chocaría» con su alojamiento.
            r, t = _componer(en_el_mundo[i], (_giros(giros), en))
            clave = (ficha.id, tuple(round(x, 1) for x in t),
                     tuple(round(x) for fila in r for x in fila))
            if clave in vistos:
                continue
            vistos.append(clave)
            p.propios.append(rasgo)
            p.montados += [{**x, "de": de} for x in primitivas(ficha, en, giros, "cuerpos")]
            p.salidas += [{"de": de, "ficha": ficha.id, "nombre": s.nombre,
                           "punto": colocar(s.en, en, giros),
                           "eje": orientar(s.eje, giros), "recorrido": tuple(s.recorrido),
                           "largo": s.largo}
                          for s in ficha.salidas]
        piezas[i] = p
    return piezas


def _caja_en(envolvente, t):
    a, b = envolvente
    esquinas = [_componer(t, (I3, [x, y, z]))[1]
                for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]
    return ([min(p[n] for p in esquinas) for n in range(3)],
            [max(p[n] for p in esquinas) for n in range(3)])


def _a_la_caja(punto, caja) -> float:
    a, b = caja
    return math.sqrt(sum(max(lo - x, 0, x - hi) ** 2 for x, lo, hi in zip(punto, a, b)))


def _salida_a_la_caja(s: dict, caja) -> float:
    """Del tramo que ocupa la salida (de `punto` a `largo` por su eje) a la
    caja: una polea puede apoyar en cualquiera de las dos caras del aro."""
    largo = s.get("largo", 0.0)
    n = max(1, math.ceil(largo / 0.5))
    return min(_a_la_caja([p + e * largo * k / n for p, e in zip(s["punto"], s["eje"])], caja)
               for k in range(n + 1))


def giros_del_plan(obra) -> dict[str, tuple[str, str]] | None:
    """{pieza que gira: (ficha del componente, salida)} según las uniones del
    plan (F9.2 (uniones)), o None si el backlog es de antes de tenerlas:
    entonces se sigue adivinando por cercanía, como siempre."""
    from orchestrator.componentes import cargar
    from orchestrator.plan import salida_de
    from orchestrator.schemas.obra import Gira
    if not obra.uniones:
        return None
    return {u.gira: (u.componente, salida_de(u, cargar(u.componente)).nombre)
            for u in obra.uniones if isinstance(u, Gira)}


def recorridos_del_plan(obra) -> dict[str, float] | None:
    """{pieza que gira: los grados que el plan le pide}, o None si el
    backlog es de antes de tener uniones."""
    from orchestrator.schemas.obra import Gira
    if not obra.uniones:
        return None
    return {u.gira: u.recorrido_grados for u in obra.uniones if isinstance(u, Gira)}


def _lo_pedido(de_la_ficha: tuple, grados: float | None) -> tuple:
    """El recorrido que se barre: lo que pide el plan, la mitad a cada lado
    de como se dibujó la pieza, sin salirse de lo que da la ficha.

    El dedo de la pinza del banco 1112-1359 tenía que cerrar 60° y se barrió
    los 180° del SG90: «chocaba» en ángulos a los que nunca va a ir, y una
    pinza no puede dar media vuelta junto a su dedo fijo."""
    lo, hi = de_la_ficha
    if not grados or grados >= hi - lo - 1e-6:
        return tuple(de_la_ficha)
    if hi - lo >= 360 - 1e-6:
        # Lo que da la vuelta entera (un rodamiento, de 0° a 360° en su
        # ficha) no tiene un lado al que no llegue. Corrido a «de 0° a 180°»,
        # un brazo dibujado estirado nunca bajaba, y a quien lo dibuja se le
        # dice «90° a cada lado» (F10.2 (transmisión)).
        return (-grados / 2, grados / 2)
    # Centrado en el reposo; si la ficha no llega por un lado, se corre.
    a = min(max(-grados / 2, lo), hi - grados)
    return (a, a + grados)


def articulaciones(piezas: dict[str, Pieza],
                   giros: dict[str, tuple[str, str]] | None = None,
                   recorridos: dict[str, float] | None = None) -> list[Articulacion]:
    """La pieza que llega a una salida de lo que monta la de abajo gira con
    ella; si hay varias, con la más cercana. La que no llega va fija.

    Con `giros` (`giros_del_plan`) solo gira lo que el plan dice, y sobre la
    salida que dice (F9.5 (parcial)). Por cercanía, una tapa atornillada a
    menos de 5 mm de un eje habría girado con él. Con `recorridos`
    (`recorridos_del_plan`), cada una gira lo que el plan le pide."""
    salida = []
    for p in piezas.values():
        if p.padre is None or not piezas[p.padre].salidas:
            continue
        candidatas = piezas[p.padre].salidas
        if giros is not None:
            if p.id not in giros:
                continue
            ficha, nombre = giros[p.id]
            # Las fichas de antes no guardaban de qué componente era la salida.
            candidatas = [s for s in candidatas
                          if s.get("ficha", ficha) == ficha and s["nombre"] == nombre]
            if not candidatas:
                continue
        caja = _caja_en(p.envolvente, p.al_padre)
        d, s = min(((_salida_a_la_caja(s, caja), s) for s in candidatas),
                   key=lambda x: x[0])
        if d <= ALCANCE_MM:
            salida.append(Articulacion(p.id, p.padre, s["de"], s["punto"], s["eje"],
                                       _lo_pedido(s["recorrido"], (recorridos or {}).get(p.id))))
    return salida


def articulaciones_de(carpeta: Path, piezas: dict[str, Pieza]) -> list[Articulacion]:
    """Las del backlog de `carpeta`, con su plan si lo tiene. Todo el que
    mueve un conjunto pasa por aquí: el barrido, el visor y el estudio tienen
    que girar las mismas piezas."""
    from orchestrator import obra as O
    obra = O.cargar_obra(Path(carpeta))
    return articulaciones(piezas, giros_del_plan(obra), recorridos_del_plan(obra))


def poses(piezas: dict[str, Pieza], arts: dict[str, Articulacion],
          angulos: dict[str, float]) -> dict[str, tuple]:
    """(R, t) de cada pieza en el marco de la primera, con cada articulación
    girada lo que diga `angulos` (0 si no lo dice)."""
    mundo: dict[str, tuple] = {}
    for p in piezas.values():
        if p.padre is None:
            mundo[p.id] = (I3, [0.0, 0.0, 0.0])
            continue
        t = p.al_padre
        a = arts.get(p.id)
        if a is not None and angulos.get(p.id):
            r = _rodrigues(a.eje, angulos[p.id])
            giro = (r, [x - y for x, y in zip(a.punto, _mv(r, a.punto))])
            t = _componer(giro, t)
        mundo[p.id] = _componer(mundo[p.padre], t)
    return mundo


# --- el barrido ------------------------------------------------------------------------------

def _hasta_la_raiz(piezas, i) -> list[str]:
    camino = []
    while piezas[i].padre is not None:
        camino.append(i)
        i = piezas[i].padre
    return camino


def _puntos(recorrido, tramos: int) -> list[float]:
    lo, hi = recorrido
    return [round(lo + (hi - lo) * k / tramos, 6) for k in range(tramos + 1)]


def _recorrido(a: Articulacion, paso: float) -> list[float]:
    lo, hi = a.recorrido
    return _puntos(a.recorrido, max(1, round((hi - lo) / paso)))


MAX_POSES = 8000
"""Hasta cuántas combinaciones de giros se prueban de una vez. Caben tres
giros de 180° con la rejilla de 10° (19³ = 6 859); con cuatro ya no."""


def rejilla_de_poses(recorridos: dict[str, tuple], paso: float,
                     limite: int = MAX_POSES) -> tuple[list[dict], dict | None]:
    """Las poses en las que se prueban a la vez los giros de `recorridos`
    ({giro: (de, a)}), y lo que se dejó sin probar (None si nada).

    Si todas las combinaciones de la rejilla de `paso` caben en `limite`,
    son esas. Si no (F10.5 (muestreo)), una rejilla más gruesa: el mismo
    número impar de puntos en cada giro, el mayor que quepa, para que lleve
    siempre los dos extremos y el centro, que es el reposo. Un brazo de
    cinco ejes pedía 2 476 099 poses entre su primera pieza y la última, y
    no se podía ni empezar a mover; se barre cada 45° (3 125) y se dice. Lo
    que cae entre dos puntos de la rejilla no se ha mirado."""
    finas = {j: _puntos(r, max(1, round((r[1] - r[0]) / paso))) for j, r in recorridos.items()}
    total = math.prod(len(f) for f in finas.values())
    if total <= limite:
        return [dict(zip(finas, v)) for v in itertools.product(*finas.values())], None

    def caben(n):
        return math.prod(min(n, len(f)) for f in finas.values())

    n = 3
    while n + 2 <= max(len(f) for f in finas.values()) and caben(n + 2) <= limite:
        n += 2
    # A un giro corto, que ya iba con menos puntos, no se le inventan más.
    gruesas = {j: f if len(f) <= n else _puntos(recorridos[j], n - 1) for j, f in finas.items()}
    poses_ = [dict(zip(gruesas, v)) for v in itertools.product(*gruesas.values())]
    return poses_, {
        "juntas": list(recorridos), "probadas": len(poses_), "de": total,
        "cada_grados": {j: round((recorridos[j][1] - recorridos[j][0]) / max(len(g) - 1, 1), 3)
                        for j, g in gruesas.items()}}


def muestreo_en_palabras(muestreos: list[dict]) -> str:
    """Lo que no se probó, para quien lee el resultado."""
    partes = []
    for m in muestreos:
        cada = sorted({g for g in m["cada_grados"].values()}, reverse=True)
        partes.append(f"con {len(m['juntas'])} giros a la vez se probaron {m['probadas']} poses "
                      f"de {m['de']} (cada {cada[0]:g}°)")
    return "no se probaron todas las poses: " + "; ".join(dict.fromkeys(partes))


def _ida_y_vuelta(a: Articulacion, paso: float) -> list[float]:
    """De reposo a un extremo, al otro y de vuelta a reposo; una vuelta
    entera si el recorrido lo es (un rodamiento). Siempre en la rejilla del
    barrido: así cada cuadro se busca exacto en los choques."""
    rejilla = _recorrido(a, paso)
    if a.recorrido[1] - a.recorrido[0] >= 360:
        return rejilla
    reposo = min(range(len(rejilla)), key=lambda k: abs(rejilla[k]))
    return (rejilla[reposo::-1] + rejilla[1:] + rejilla[-2:reposo - 1 if reposo else None:-1])


def fotogramas(arts: dict[str, Articulacion], paso: float = PASO) -> list[dict[str, float]]:
    """Los ángulos de cada cuadro de la animación: cada articulación por
    turno con las demás quietas, y al final todas a la vez. La plataforma del
    pan-tilt chocaba con la base solo al girar e inclinar juntas (2026-11-09):
    por turnos no se habría visto."""
    cuadros = [{**{j: 0.0 for j in arts}, i: v}
               for i, a in arts.items() for v in _ida_y_vuelta(a, paso)]
    if len(arts) > 1:
        idas = {i: _ida_y_vuelta(a, paso) for i, a in arts.items()}
        n = max(len(v) for v in idas.values())
        # Todas a la vez: cada una avanza su ida y vuelta al mismo ritmo,
        # tomando el cuadro de la rejilla más cercano.
        cuadros += [{i: v[round(k * (len(v) - 1) / (n - 1))] for i, v in idas.items()}
                    for k in range(n)]
    return cuadros


def chocan_en(angulos: dict[str, float], choques: list[dict]) -> set[str]:
    """Los sólidos que chocan con la pieza en `angulos`. Cada choque guarda
    solo las articulaciones que hay entre sus dos piezas; las demás no
    cambian nada entre ellas."""
    return {s for c in choques
            if all(abs(angulos.get(j, 0.0) - v) < 1e-6 for j, v in c["angulos"].items())
            for s in (c["solido_a"], c["solido_b"])}


ROJO = "#e02424"
COLOR_COMPRADO = "#5d6d7e"
COLORES_PIEZAS = ("#9aa5b1", "#3bb273", "#3a7be8", "#9b59b6", "#f1c40f", "#1abc9c")
"""Sin naranjas ni rosas: el rojo es solo para lo que choca."""


ANCHO_ROTULO = 80
"""Caracteres por línea del rótulo de un cuadro: con más se sale del dibujo."""


def rotulo(piezas: dict[str, Pieza], juntas: list[str], angulos: dict[str, float],
           rojos: set[str]) -> str:
    """El ángulo de cada articulación y, si algo choca, qué: una línea por
    cosa y partida al ancho del dibujo. Con los nombres enteros en una sola
    línea, el del pan-tilt del banco se salía por los dos lados (2026-11-10)."""
    import textwrap
    partes = [f"{piezas[j].nombre} {angulos[j]:g}°" for j in juntas]
    if rojos:
        partes.append("choca: " + " ↔ ".join(piezas[r].nombre for r in piezas if r in rojos))
    return "\n".join(textwrap.fill(p, ANCHO_ROTULO) for p in partes)


ENSAMBLE = "ensamble.json"


def guardar_ensamble(mallas: dict, piezas: dict[str, Pieza], arts: dict[str, Articulacion],
                     duenos: dict[str, str], paso: float, destino: Path) -> Path:
    """Lo que necesita el visor 3D de la web (F7.9 (visor)): cada malla en el
    marco de su sólido, de qué pieza es y qué articulaciones se mueven. Las
    poses no van aquí: las da `pose_para_el_visor`, con la misma cinemática
    que barrió los choques."""
    colores = {s: COLORES_PIEZAS[k % len(COLORES_PIEZAS)] for k, s in enumerate(piezas)}
    datos = {
        "solidos": {s: {"pieza": duenos[s], "color": colores.get(s, COLOR_COMPRADO),
                        # Al centésimo de milímetro: el JSON del pan-tilt baja a la mitad.
                        "v": [round(c, 2) for p in v for c in p], "t": [i for tri in t for i in tri]}
                    for s, (v, t) in mallas.items() if s in duenos},
        "piezas": {i: {"nombre": p.nombre} for i, p in piezas.items()},
        "articulaciones": [{"pieza": a.pieza, "nombre": piezas[a.pieza].nombre,
                            "recorrido": list(a.recorrido), "paso": paso} for a in arts.values()],
    }
    destino = Path(destino)
    destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
    return destino


def pose_para_el_visor(carpeta: Path, conjunto: str, angulos: dict[str, float]) -> dict:
    """{"poses": {pieza: 4x4 por filas}, "rojos": [sólidos]}: el conjunto con
    cada articulación a su ángulo, y lo que la verificación vio chocar ahí.
    Los ángulos van a la rejilla del barrido: entre dos puntos de la rejilla
    no se comprobó nada, y no se puede decir que no choque."""
    from orchestrator import obra as O
    piezas = leer_piezas(carpeta, conjunto, solo_construidas=True)
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    v = json.loads((Path(carpeta) / O.NODOS / conjunto / VERIFICACION).read_text(encoding="utf-8"))
    paso = v.get("paso") or PASO
    rejilla = {}
    for j, a in arts.items():
        if j in angulos:
            lo, hi = a.recorrido
            rejilla[j] = min(max(round(angulos[j] / paso) * paso, lo), hi)
    mundo = poses(piezas, arts, rejilla)
    return {"poses": {i: [*r[0], t[0], *r[1], t[1], *r[2], t[2], 0, 0, 0, 1]
                      for i, (r, t) in mundo.items()},
            "angulos": rejilla,
            "rojos": sorted(chocan_en(rejilla, v.get("choques") or []))}


def animar_conjunto(piezas: dict[str, Pieza], arts: dict[str, Articulacion],
                    steps: dict[str, Path], solidos: dict[str, list], duenos: dict[str, str],
                    choques: list[dict], gif: Path, freecadcmd: str, titulo: str,
                    paso: float = PASO) -> Path:
    """El GIF del conjunto moviéndose por lo mismo que se barrió, con lo que
    choca en rojo en los cuadros en que choca. Hasta el 2026-11-10 la obra
    solo dejaba el ensamble en reposo: el pan-tilt «se movía entero sin
    chocar» y nadie lo había visto moverse."""
    from orchestrator.animation import render_gif, tessellate

    mallas = tessellate(steps, {}, freecadcmd, solidos=solidos)
    # Las mismas mallas, para el visor de la web: teselar cuesta un FreeCAD.
    guardar_ensamble(mallas, piezas, arts, duenos, paso, Path(gif).parent / ENSAMBLE)
    cuadros = fotogramas(arts, paso) or [{}]
    colores = {s: COLORES_PIEZAS[k % len(COLORES_PIEZAS)] for k, s in enumerate(piezas)}
    colores.update({s: COLOR_COMPRADO for s in duenos if s not in piezas})

    def rotular(k):
        return rotulo(piezas, list(arts), cuadros[k],
                      {duenos[s] for s in chocan_en(cuadros[k], choques)})

    marcos = []
    for k, a in enumerate(cuadros):
        mundo = poses(piezas, arts, a)
        marcos.append((k, {s: _placement(mundo[duenos[s]]) for s in duenos}))
    return render_gif(mallas, marcos, gif, title=titulo, colors=colores, label=rotular,
                      resaltar=lambda k: chocan_en(cuadros[k], choques), color_resaltado=ROJO)


def _abrazados(piezas: dict[str, Pieza], arts: dict[str, Articulacion]) -> set[tuple]:
    """{(pieza, componente)}: lo comprado en lo que otra pieza gira
    abrazándolo —un rodamiento, cuya salida ocupa un tramo (`largo`)—.

    La pieza que gira en un rodamiento va encajada en su aro: tocarlo es lo
    que tiene que hacer. En la articulación del banco 1113-0216 el eje del
    brazo «chocaba» con el 608ZZ, a 0,00 mm. Un servo no entra aquí: lo que
    gira con él va en su cuerno, por delante de la carcasa."""
    return {(a.padre, a.de) for a in arts.values()
            if any(s["de"] == a.de and s.get("largo") and s["punto"] == a.punto
                   for s in piezas[a.padre].salidas)}


def _solidos(piezas: dict[str, Pieza],
             arts: dict[str, Articulacion] | None = None) -> tuple[dict, dict, dict]:
    """(dueños, sólidos, steps). Cada sólido es de una pieza: la construida,
    y lo comprado que monta. Con `arts`, sin los rodamientos en los que gira
    otra pieza (`_abrazados`): no se barren contra nada."""
    duenos = {i: i for i in piezas}
    solidos = {}
    fuera = _abrazados(piezas, arts) if arts else set()
    for p in piezas.values():
        suyos = [m for m in p.montados if (p.id, m["de"]) not in fuera]
        if suyos:
            solidos[f"{p.id}: montado"] = [{k: v for k, v in m.items() if k != "de"}
                                           for m in suyos]
            duenos[f"{p.id}: montado"] = p.id
    return duenos, solidos, {p.id: p.step for p in piezas.values()}


def _barrer(piezas: dict[str, Pieza], arts: dict[str, Articulacion], duenos: dict,
            solidos: dict, steps: dict, freecadcmd: str, min_gap_mm: float,
            paso: float = PASO, solo: str | None = None,
            muestreo: list | None = None) -> list[dict]:
    """Los choques al mover las piezas por todo el recorrido de sus
    articulaciones. Con `solo`, nada más los pares en los que entra esa
    pieza (o lo que monta): lo que ya había se barrió cuando se construyó.
    En `muestreo` se apunta lo que no se probó entero (`rejilla_de_poses`)."""
    from orchestrator.assembly import sweep_collisions

    # Cada par se barre solo por las articulaciones que hay entre sus dos
    # piezas: el giro del soporte no cambia nada entre el soporte y la
    # plataforma, y barrerlo con ella multiplicaría las poses por 19.
    grupos: dict[tuple, list] = {}
    for x, y in itertools.combinations(sorted(duenos), 2):
        if duenos[x] == duenos[y] or (solo is not None and solo not in (duenos[x], duenos[y])):
            continue
        entre = set(_hasta_la_raiz(piezas, duenos[x])) ^ set(_hasta_la_raiz(piezas, duenos[y]))
        grupos.setdefault(tuple(sorted(j for j in entre if j in arts)), []).append((x, y))

    choques = []
    for juntas, pares in grupos.items():
        usados = sorted({s for par in pares for s in par})
        rejilla, sin_probar = rejilla_de_poses({j: arts[j].recorrido for j in juntas}, paso)
        if sin_probar and muestreo is not None:
            muestreo.append(sin_probar)
        cuadros = {}
        for k, angulos in enumerate(rejilla):
            mundo = poses(piezas, arts, angulos)
            cuadros[float(k)] = {s: _placement(mundo[duenos[s]]) for s in usados}
        reglas = {(x, y): IGNORAR for x, y in itertools.combinations(usados, 2)
                  if (x, y) not in pares and (y, x) not in pares}
        if not juntas:
            reglas.update({par: SE_TOCAN for par in pares})
        for c in sweep_collisions({s: steps[s] for s in usados if s in steps}, {}, cuadros,
                                  min_gap_mm, freecadcmd, reglas,
                                  {s: solidos[s] for s in usados if s in solidos}):
            choques.append({"a": duenos[c.a], "b": duenos[c.b], "solido_a": c.a,
                            "solido_b": c.b, "angulos": rejilla[int(c.angle)],
                            "hueco_mm": round(c.gap_mm, 3)})
    return choques


def mover_lo_construido(carpeta: Path, nodo: str, freecadcmd: str, min_gap_mm: float,
                        paso: float = PASO) -> dict:
    """Mueve la pieza recién construida de `nodo` contra las que ya hay,
    sin esperar al nodo conjunto (F9.5 (parcial)): {"choques", "correccion"}.

    El pan-tilt del banco 1110-0313 se movió entero por primera vez con sus
    tres piezas dadas por buenas, y el choque ya no tenía arreglo barato.
    Aquí el choque vuelve al bucle de la pieza que se está diseñando, como
    cualquier otra medida. No escribe nada ni anima: la verificación del
    conjunto sigue siendo la del todo."""
    from orchestrator import obra as O

    carpeta = Path(carpeta)
    piezas = leer_piezas(carpeta, solo_construidas=True)
    if nodo not in piezas:
        return {"choques": [], "correccion": ""}
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    duenos, solidos, steps = _solidos(piezas, arts)
    choques = _barrer(piezas, arts, duenos, solidos, steps, freecadcmd, min_gap_mm, paso,
                      solo=nodo)
    textos = correcciones(piezas, arts, choques, paso,
                          presupuestos_del_plan(O.cargar_obra(carpeta)))
    # Lo que no es de esta pieza (falta sitio en la que monta el actuador)
    # se le dice igual: es lo que hay, y lo ve quien revise el proyecto.
    return {"choques": choques,
            "correccion": "\n".join(([textos[nodo]] if nodo in textos else [])
                                    + [f"(De «{piezas[i].nombre}») {t}"
                                       for i, t in textos.items() if i != nodo])}


def presupuestos_del_plan(obra) -> dict[str, float] | None:
    """{pieza que gira: radio libre que el plan le reserva}, o None."""
    from orchestrator.schemas.obra import Gira
    if not obra.uniones:
        return None
    return {u.gira: u.radio_libre_mm for u in obra.uniones
            if isinstance(u, Gira) and u.radio_libre_mm}


def verificar_conjunto(carpeta: Path, conjunto: str, freecadcmd: str, min_gap_mm: float,
                       paso: float = PASO, animar: bool = True) -> dict:
    """Mueve el conjunto por todo el recorrido de sus articulaciones y deja
    lo que pasa en `nodos/<conjunto>/verificacion.json`, más el ensamble en
    reposo (`assembly.FCStd`) para abrirlo en FreeCAD."""
    from orchestrator import obra as O
    from orchestrator.assembly import build_assembly

    carpeta = Path(carpeta)
    piezas = leer_piezas(carpeta, conjunto)
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    duenos, solidos, steps = _solidos(piezas, arts)
    muestreo: list[dict] = []
    choques = _barrer(piezas, arts, duenos, solidos, steps, freecadcmd, min_gap_mm, paso,
                      muestreo=muestreo)

    reposo = poses(piezas, arts, {})
    # «eje» va en el marco de la pieza de abajo; el banco pregunta si el giro
    # es vertical u horizontal en el mundo, y eso solo lo dice el reposo.
    v = {"ok": not choques, "paso": paso, "min_gap_mm": min_gap_mm,
         "articulaciones": [{"pieza": a.pieza, "padre": a.padre, "de": a.de,
                             "punto": a.punto, "eje": a.eje,
                             "eje_mundo": _mv(reposo[a.padre][0], a.eje),
                             "recorrido": list(a.recorrido)}
                            for a in arts.values()],
         "choques": choques, "resumen": _resumen(piezas, choques, paso),
         "muestreo": muestreo,
         "correcciones": correcciones(piezas, arts, choques, paso,
                                      presupuestos_del_plan(O.cargar_obra(carpeta)))}
    dir_nodo = carpeta / O.NODOS / conjunto
    dir_nodo.mkdir(parents=True, exist_ok=True)
    build_assembly(steps, {}, {s: _placement(reposo[duenos[s]]) for s in duenos},
                   dir_nodo / "assembly.FCStd", freecadcmd, solidos)
    (dir_nodo / VERIFICACION).write_text(json.dumps(v, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    if animar:
        ob = O.cargar_obra(carpeta)
        gif = animar_conjunto(piezas, arts, steps, solidos, duenos, choques,
                              dir_nodo / "animation.gif", freecadcmd, ob.nodo(conjunto).nombre,
                              paso)
        # El conjunto de toda la obra es la animación del proyecto: la web,
        # Crafty y Telegram la buscan en la raíz, como la de un mecanismo.
        ultimo = [i for i in ob.orden() if ob.nodo(i).tipo == "conjunto"][-1]
        if conjunto == ultimo:
            shutil.copyfile(gif, carpeta / "animation.gif")
    return v


# --- quién corrige un choque (F7.7 (culpable)) -----------------------------------------------

def culpable(piezas: dict[str, Pieza], a: str, b: str) -> str:
    """De dos piezas que chocan, la que se diseñó contra la otra: la que va
    después en la obra. Es la que puede cambiar sin deshacer la otra."""
    orden = list(piezas)
    return a if orden.index(a) > orden.index(b) else b


def _a_la_recta(p, punto, eje) -> float:
    d = [x - y for x, y in zip(p, punto)]
    n = math.sqrt(sum(c * c for c in eje))
    e = [c / n for c in eje]
    a = sum(x * y for x, y in zip(d, e))
    return math.sqrt(max(sum(x * x for x in d) - a * a, 0.0))


def _caja_de(piezas: dict[str, Pieza], solido: str):
    """La caja de un sólido en el marco de su pieza: la envolvente si es la
    pieza; si es lo comprado que monta, la de sus cajas y cilindros."""
    if solido in piezas:
        return piezas[solido].envolvente
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for m in piezas[solido.removesuffix(": montado")].montados:
        if m.get("tipo") == "caja":
            puntos = [m["min"], m["max"]]
        else:
            r = m["diametro"] / 2
            fin = [b + e * m["alto"] for b, e in zip(m["base"], m["eje"])]
            puntos = [[c + s * r for c in q] for q in (m["base"], fin) for s in (-1, 1)]
        for q in puntos:
            lo = [min(x, y) for x, y in zip(lo, q)]
            hi = [max(x, y) for x, y in zip(hi, q)]
    return lo, hi


def _cerca_de_la_recta(caja, punto, eje) -> float:
    """La distancia de la recta a la caja (en el marco de la caja): la
    distancia a una recta es convexa, así que bajar coordenada a coordenada
    recortando a la caja llega al mínimo."""
    lo, hi = caja
    p = [(a + b) / 2 for a, b in zip(lo, hi)]
    n = math.sqrt(sum(c * c for c in eje))
    e = [c / n for c in eje]
    for _ in range(200):
        for k in range(3):
            # d(p) = (p-c) - ((p-c)·e) e; a lo largo de x_k es una parábola
            # con mínimo donde su derivada se anula.
            resto = [x - y for x, y in zip(p, punto)]
            a = sum(x * y for x, y in zip(resto, e))
            g = resto[k] - a * e[k]
            curva = 1 - e[k] * e[k]
            if curva > 1e-12:
                p[k] = min(max(p[k] - g / curva, lo[k]), hi[k])
    return _a_la_recta(p, punto, eje)


def _sin_sitio(piezas, arts, j: str, radio: float, paso: float) -> tuple[str, str] | None:
    """Si la pieza que monta el actuador de `j` no le dejó el radio que el
    plan le reserva: (esa pieza, qué decirle). None si lo dejó."""
    a = arts[j]
    salida = next((s for s in piezas[a.padre].salidas
                   if s["punto"] == a.punto and s["eje"] == a.eje), None)
    if salida is None:
        return None
    libre, que = radio_libre(piezas, arts, a.padre, salida, paso)
    if libre >= radio - 0.05:
        return None
    return a.padre, (
        f"No deja sitio para que gire «{piezas[j].nombre}»: el plan reserva {radio:g} mm "
        f"alrededor del eje del {a.de} que monta esta pieza y solo hay {libre:.1f} mm, porque "
        f"{_que(piezas, que)} queda a {libre:.1f} mm de ese eje. Sube o aleja el {a.de} al "
        f"menos {radio - libre:.1f} mm más, sin cambiar cómo se une esta pieza a lo que tiene "
        "debajo. Lo demás se queda como está.")


def correcciones(piezas: dict[str, Pieza], arts: dict[str, Articulacion],
                 choques: list[dict], paso: float = PASO,
                 presupuestos: dict[str, float] | None = None) -> dict[str, str]:
    """Qué decirle a cada pieza que choca, con cifras con las que se puede
    actuar: contra qué choca y en qué ángulos, hasta dónde llega girando
    alrededor de su eje y dónde empieza lo que choca. Así era la corrección
    que escribió la persona el 9 de noviembre, la que arregló el pan-tilt.

    Con `presupuestos` (`presupuestos_del_plan`), el culpable es quien
    incumple el suyo (ADR-020). «La que va después» mandó corregir la
    plataforma del pan-tilt 1110-0313, que bajó de 68.4 a 37.7 mm y no podía
    bajar más: el soporte le había dejado 12.7."""
    reposo = poses(piezas, arts, {})
    por_pieza: dict[str, list[str]] = {}
    pares: dict[tuple, list] = {}
    for c in choques:
        pares.setdefault((c["solido_a"], c["solido_b"]), []).append(c)
    for (x, y), cs in pares.items():
        dx, dy = (s.removesuffix(": montado") for s in (x, y))
        quien = culpable(piezas, dx, dy)
        otro = y if quien == dx else x
        frase = (f"Choca al moverse (verificado en FreeCAD moviendo el conjunto entero): "
                 f"{_resumen(piezas, cs, paso)[0]}.")
        # Su articulación, o la de la pieza que la lleva.
        j = quien
        while j is not None and j not in arts:
            j = piezas[j].padre
        if j is not None and (presupuestos or {}).get(j):
            falta = _sin_sitio(piezas, arts, j, presupuestos[j], paso)
            if falta is not None:
                if falta[1] not in por_pieza.setdefault(falta[0], []):
                    por_pieza[falta[0]].append(falta[1])
                continue
        if j is not None:
            a = arts[j]
            r_p, t_p = reposo[a.padre]
            punto = [x + y for x, y in zip(_mv(r_p, a.punto), t_p)]
            eje = _mv(r_p, a.eje)
            radio = max(_a_la_recta(q, punto, eje) for q in _esquinas(piezas[quien].envolvente,
                                                                          reposo[quien]))
            r_o, t_o = _inversa(reposo[otro.removesuffix(": montado")])
            hasta = _cerca_de_la_recta(_caja_de(piezas, otro),
                                       [x + y for x, y in zip(_mv(r_o, punto), t_o)],
                                       _mv(r_o, eje))
            en_su_marco = _componer(_inversa(reposo[quien]), (I3, punto))[1]
            frase += (f" Gira alrededor del {a.de} de «{piezas[a.padre].nombre}», que en tu "
                      f"marco pasa por ({', '.join(f'{v:.1f}' for v in en_su_marco)}); "
                      f"tu caja llega a {radio:.1f} mm de ese eje, y {_que(piezas, otro)} "
                      f"empieza a {hasta:.1f} mm de él.")
        frase += (" Cámbiala para que no choque en ningún ángulo —menos radio de giro, o más "
                  "lejos de lo que choca— sin mover dónde se acopla al eje. Lo demás se queda "
                  "como está.")
        por_pieza.setdefault(quien, []).append(frase)
    return {i: "\n".join(por_pieza[i]) for i in piezas if i in por_pieza}


def _esquinas(envolvente, t) -> list:
    a, b = envolvente
    return [_componer(t, (I3, [x, y, z]))[1]
            for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]


SUELO, LEJISIMOS = "suelo", 1e5


def _que(piezas, solido: str) -> str:
    if solido == SUELO:
        return "aquello en lo que se apoya el invento"
    if solido in piezas:
        return f"«{piezas[solido].nombre}»"
    dueno = solido.removesuffix(": montado")
    return f"lo comprado que monta «{piezas[dueno].nombre}»"


def _tramos(valores, paso) -> str:
    """{-50, -40, 40, 50} con paso 10 -> «de -50° a -40° y de 40° a 50°». De
    punta a punta («de -50° a 50°») parecía que el pan-tilt chocaba también
    en reposo (2026-11-09)."""
    vals = sorted(set(valores))
    tramos, inicio = [], vals[0]
    for a, b in zip(vals, vals[1:] + [None]):
        if b is None or b - a > paso + 1e-6:
            tramos.append(f"{inicio:g}°" if inicio == a else f"de {inicio:g}° a {a:g}°")
            inicio = b
    return " y ".join(tramos)


def _resumen(piezas, choques, paso: float = PASO) -> list[str]:
    """Una línea por par que choca, con los tramos de cada articulación en que
    pasa: es lo que la persona lee en la tarjeta del conjunto."""
    por_par: dict[tuple, list] = {}
    for c in choques:
        por_par.setdefault((c["solido_a"], c["solido_b"]), []).append(c)
    lineas = []
    for (x, y), cs in por_par.items():
        # «X y Y chocan con Y girada…» se leía como si Y chocara consigo
        # misma (pan-tilt, 2026-11-09): los ángulos van tras un «si».
        tramos = []
        for j in cs[0]["angulos"]:
            angulos = _tramos([c["angulos"][j] for c in cs], paso)
            tramos.append(f"«{piezas[j].nombre}» "
                          + (f"está girada {angulos}" if not tramos else angulos))
        peor = min(c["hueco_mm"] for c in cs)
        como = (f"se meten {-peor:.1f} mm³ una en otra" if peor < 0
                else f"quedan a {peor:.2f} mm")
        cuando = "si " + "; y ".join(tramos) if tramos else "en reposo"
        lineas.append(f"{_que(piezas, x)} y {_que(piezas, y)} chocan {cuando} ({como})")
    return lineas


# --- el sitio libre de un giro (F9.1 (barrido)) ----------------------------------------------

def _caja_del_montado(m: dict):
    """La caja de UNA primitiva de lo comprado, en el marco de la pieza que
    lo monta. De una en una y no todas juntas como `_caja_de`: con dos
    componentes en una pieza, su caja común taparía el sitio que hay entre
    los dos."""
    if m.get("tipo") == "caja":
        return m["min"], m["max"]
    r = m["diametro"] / 2
    fin = [b + e * m["alto"] for b, e in zip(m["base"], m["eje"])]
    puntos = [[c + s * r for c in q] for q in (m["base"], fin) for s in (-1, 1)]
    return ([min(p[k] for p in puntos) for k in range(3)],
            [max(p[k] for p in puntos) for k in range(3)])


def _semirrecta_a_la_caja(caja, punto, eje, largo: float | None = None) -> float:
    """De la semirrecta que sale de `punto` hacia `eje` a la caja, en el
    marco de la caja. La distancia a un convexo es convexa a lo largo de la
    semirrecta, así que se busca el mínimo partiendo el tramo en tercios;
    más allá de la esquina que más lejos se proyecta solo puede crecer.

    Con `largo`, solo el tramo que mide eso desde `punto`."""
    lo, hi = caja
    n = math.sqrt(sum(c * c for c in eje))
    e = [c / n for c in eje]
    esquinas = [[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    a, b = 0.0, max(0.0, max(sum((q - p) * d for q, p, d in zip(c, punto, e)) for c in esquinas))
    if largo is not None:
        b = min(b, largo)

    def lejos(s):
        return _a_la_caja([p + d * s for p, d in zip(punto, e)], caja)

    for _ in range(100):
        m1, m2 = a + (b - a) / 3, b - (b - a) / 3
        if lejos(m1) <= lejos(m2):
            b = m2
        else:
            a = m1
    return lejos((a + b) / 2)


def radio_libre(piezas: dict[str, Pieza], arts: dict[str, Articulacion], pieza: str,
                salida: dict, paso: float = PASO,
                largo: float | None = None, suelo: bool = False) -> tuple[float, str | None]:
    """Cuánto sitio tiene lo que gire alrededor de `salida`, una salida de lo
    que monta `pieza`: la distancia del eje a lo más cercano de lo que hay
    DEBAJO —las piezas sobre las que va y lo comprado que montan—, y qué es.

    El pan-tilt del banco 1110-0313 falló por esto y nadie lo había medido:
    su soporte dejaba 12.7 mm entre el eje de inclinación y el SG90 de la
    base, la plataforma medía 37.7, y la corrección se le pidió a la
    plataforma, que no podía encoger tanto. El sitio lo decide la pieza que
    monta el actuador, y se puede medir en cuanto esa pieza está construida,
    sin esperar a la que gira.

    Se mide en todos los ángulos de los giros de debajo: el eje de
    inclinación barre la base entera cuando el soporte gira. Y desde la cara
    de la salida hacia fuera (semirrecta, no recta): lo que gira va por
    delante del actuador, y lo que este tiene detrás no le estorba.

    Con cajas, así que es prudente de más: la medida exacta sigue siendo el
    barrido. Lo de la propia `pieza` no entra —el actuador está dentro de su
    caja y daría siempre 0—: eso lo mide la sonda con su forma real.

    Con `largo`, el sitio alrededor de un tramo y no de la semirrecta
    entera: lo que se atornilla después ocupa un fondo, no llega al infinito
    (`medida.sin_sitio_para_lo_nuevo`).

    Con `suelo`, cuenta también lo que hay bajo la pieza de abajo del todo:
    se apoya en algo (es lo que supone el estudio al mirar si vuelca), y
    quien busca dónde cabe un eje no puede encontrarlo bajo la mesa. Sin
    él, 80 mm por debajo de una plataforma «había» 46 mm libres."""
    debajo, j = [], piezas[pieza].padre
    while j is not None:
        debajo.append(j)
        j = piezas[j].padre
    mejor: tuple[float, str | None] = (math.inf, None)
    juntas = [j for j in _hasta_la_raiz(piezas, pieza) if j in arts]
    for valores in itertools.product(*[_recorrido(arts[j], paso) for j in juntas]):
        mundo = poses(piezas, arts, dict(zip(juntas, valores)))
        for a in debajo:
            r, t = _componer(_inversa(mundo[a]), mundo[pieza])
            punto = [x + y for x, y in zip(_mv(r, salida["punto"]), t)]
            eje = _mv(r, salida["eje"])
            cajas = [(a, piezas[a].envolvente)]
            cajas += [(f"{a}: montado", _caja_del_montado(m)) for m in piezas[a].montados]
            if suelo and piezas[a].padre is None:
                cajas.append((SUELO, ([-LEJISIMOS] * 3,
                                      [LEJISIMOS, LEJISIMOS, piezas[a].envolvente[0][2]])))
            for solido, caja in cajas:
                d = _semirrecta_a_la_caja(caja, punto, eje, largo)
                if d < mejor[0] - 1e-9:
                    mejor = (d, solido)
    return mejor
