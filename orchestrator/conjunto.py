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


@dataclass
class Articulacion:
    pieza: str
    padre: str
    de: str
    punto: list
    eje: list
    recorrido: tuple


def leer_piezas(carpeta: Path, conjunto: str) -> dict[str, Pieza]:
    """Las piezas del conjunto, en el orden de la obra (lo de abajo antes)."""
    from orchestrator import obra as O
    from orchestrator.componentes import cargar

    carpeta = Path(carpeta)
    ob = O.cargar_obra(carpeta)
    ids = [i for i in ob.orden()
           if i in ob.nodo(conjunto).depende_de and ob.nodo(i).tipo == "pieza"]
    fichas = O.carpeta_de_fichas(carpeta)
    piezas: dict[str, Pieza] = {}
    en_el_mundo: dict[str, tuple] = {}
    vistos: list[tuple] = []
    for i in ids:
        parte = O._pieza_construida(carpeta / O.NODOS / i)
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
                comprados.append((r["nombre"], ficha, list(r["en"]), giros))
        en_el_mundo[i] = (_componer(en_el_mundo[p.padre], p.al_padre) if p.padre
                          else (I3, [0.0, 0.0, 0.0]))
        for de, ficha, en, giros in comprados:
            # La plataforma del pan-tilt coloca también el SG90 del soporte, en
            # su mismo sitio, para dejarle hueco: es del soporte, no suyo. Si
            # fuera suyo giraría con ella y «chocaría» con su alojamiento.
            r, t = _componer(en_el_mundo[i], (_giros(giros), en))
            clave = (ficha.id, tuple(round(x, 1) for x in t),
                     tuple(round(x) for fila in r for x in fila))
            if clave in vistos:
                continue
            vistos.append(clave)
            p.montados += [{**x, "de": de} for x in primitivas(ficha, en, giros, "cuerpos")]
            p.salidas += [{"de": de, "nombre": s.nombre, "punto": colocar(s.en, en, giros),
                           "eje": orientar(s.eje, giros), "recorrido": tuple(s.recorrido)}
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


def articulaciones(piezas: dict[str, Pieza]) -> list[Articulacion]:
    """La pieza que llega a una salida de lo que monta la de abajo gira con
    ella; si hay varias, con la más cercana. La que no llega va fija."""
    salida = []
    for p in piezas.values():
        if p.padre is None or not piezas[p.padre].salidas:
            continue
        caja = _caja_en(p.envolvente, p.al_padre)
        d, s = min(((_a_la_caja(s["punto"], caja), s) for s in piezas[p.padre].salidas),
                   key=lambda x: x[0])
        if d <= ALCANCE_MM:
            salida.append(Articulacion(p.id, p.padre, s["de"], s["punto"], s["eje"],
                                       s["recorrido"]))
    return salida


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


def _recorrido(a: Articulacion, paso: float) -> list[float]:
    lo, hi = a.recorrido
    n = max(1, round((hi - lo) / paso))
    return [round(lo + (hi - lo) * k / n, 6) for k in range(n + 1)]


def verificar_conjunto(carpeta: Path, conjunto: str, freecadcmd: str, min_gap_mm: float,
                       paso: float = PASO) -> dict:
    """Mueve el conjunto por todo el recorrido de sus articulaciones y deja
    lo que pasa en `nodos/<conjunto>/verificacion.json`, más el ensamble en
    reposo (`assembly.FCStd`) para abrirlo en FreeCAD."""
    from orchestrator import obra as O
    from orchestrator.assembly import build_assembly, sweep_collisions

    carpeta = Path(carpeta)
    piezas = leer_piezas(carpeta, conjunto)
    arts = {a.pieza: a for a in articulaciones(piezas)}
    # Cada sólido es de una pieza: la construida, y lo comprado que monta.
    duenos = {i: i for i in piezas}
    solidos = {}
    for p in piezas.values():
        if p.montados:
            solidos[f"{p.id}: montado"] = [{k: v for k, v in m.items() if k != "de"}
                                           for m in p.montados]
            duenos[f"{p.id}: montado"] = p.id
    steps = {p.id: p.step for p in piezas.values()}

    # Cada par se barre solo por las articulaciones que hay entre sus dos
    # piezas: el giro del soporte no cambia nada entre el soporte y la
    # plataforma, y barrerlo con ella multiplicaría las poses por 19.
    grupos: dict[tuple, list] = {}
    for x, y in itertools.combinations(sorted(duenos), 2):
        if duenos[x] == duenos[y]:
            continue
        entre = set(_hasta_la_raiz(piezas, duenos[x])) ^ set(_hasta_la_raiz(piezas, duenos[y]))
        grupos.setdefault(tuple(sorted(j for j in entre if j in arts)), []).append((x, y))

    choques = []
    for juntas, pares in grupos.items():
        usados = sorted({s for par in pares for s in par})
        rejilla = [dict(zip(juntas, valores)) for valores in
                   itertools.product(*[_recorrido(arts[j], paso) for j in juntas])]
        cuadros = {}
        for k, angulos in enumerate(rejilla):
            mundo = poses(piezas, arts, angulos)
            cuadros[float(k)] = {s: _placement(mundo[duenos[s]]) for s in usados}
        reglas = {(x, y): IGNORAR for x, y in itertools.combinations(usados, 2)
                  if (x, y) not in pares and (y, x) not in pares}
        for c in sweep_collisions({s: steps[s] for s in usados if s in steps}, {}, cuadros,
                                  min_gap_mm, freecadcmd, reglas,
                                  {s: solidos[s] for s in usados if s in solidos}):
            choques.append({"a": duenos[c.a], "b": duenos[c.b], "solido_a": c.a,
                            "solido_b": c.b, "angulos": rejilla[int(c.angle)],
                            "hueco_mm": round(c.gap_mm, 3)})

    v = {"ok": not choques, "paso": paso, "min_gap_mm": min_gap_mm,
         "articulaciones": [{"pieza": a.pieza, "padre": a.padre, "de": a.de,
                             "punto": a.punto, "eje": a.eje, "recorrido": list(a.recorrido)}
                            for a in arts.values()],
         "choques": choques, "resumen": _resumen(piezas, choques, paso)}
    dir_nodo = carpeta / O.NODOS / conjunto
    dir_nodo.mkdir(parents=True, exist_ok=True)
    reposo = poses(piezas, arts, {})
    build_assembly(steps, {}, {s: _placement(reposo[duenos[s]]) for s in duenos},
                   dir_nodo / "assembly.FCStd", freecadcmd, solidos)
    (dir_nodo / VERIFICACION).write_text(json.dumps(v, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    return v


def _que(piezas, solido: str) -> str:
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
        tramos = []
        for j in cs[0]["angulos"]:
            tramos.append(f"«{piezas[j].nombre}» girada "
                          f"{_tramos([c['angulos'][j] for c in cs], paso)}")
        peor = min(c["hueco_mm"] for c in cs)
        como = (f"se meten {-peor:.1f} mm³ una en otra" if peor < 0
                else f"quedan a {peor:.2f} mm")
        cuando = ", ".join(tramos) if tramos else "en reposo"
        lineas.append(f"{_que(piezas, x)} y {_que(piezas, y)} chocan con {cuando} ({como})")
    return lineas
