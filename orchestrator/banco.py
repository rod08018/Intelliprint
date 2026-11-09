"""Banco de piezas reales (F6.1 (evaluación)): la medida de «usable».

Cada encargo es una petición como la escribiría una persona, con su
oráculo escrito A MANO desde esa petición: qué agujeros, de qué diámetro y
en qué patrón; qué alojamiento; qué envolvente; si se imprime sin
soportes. El juez mide la pieza construida —su STEP y su laminado—, nunca
la receta: el sargento del 2026-10-27 llevaba el 6.4 en la receta y el
agujero salió de 6.7.

Lo que todavía no se sabe medir (pared mínima, carga, estética) se
declara `pendiente` y cuenta como «sin medir», no como aprobado: así la
nota no sube por medir menos.
"""

import datetime as dt
import itertools
import json
import math
import subprocess
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field

from mech_toolkit.geometry import Cylinder

Estado = Literal["cumple", "no_cumple", "sin_medir"]

POS_TOL_MM = 0.3
"""Cuánto puede desviarse la distancia entre dos centros. Más que la
precisión de una impresora: aquí se juzga si el agujero está EN SU SITIO,
no si está calibrado."""

MISMO_EJE_MM = 0.2


# --- aserciones ---------------------------------------------------------------

class Agujeros(BaseModel):
    """Agujeros pasantes de un diámetro en un patrón. El patrón se da en el
    plano de los agujeros, con cualquier origen: se compara por distancias
    entre centros, que no dependen de dónde ni cómo colocó la pieza el
    modelo."""

    tipo: Literal["agujeros"]
    diametro_mm: float
    patron_mm: list[list[float]]
    tol_mm: float = 0.15

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.diametro_mm] + sorted({abs(c) for p in self.patron_mm for c in p if c})


class Cilindro(BaseModel):
    """Un alojamiento (interior) o un saliente (exterior) con su rango. El
    rango lo fija quien escribe el oráculo desde la cota nominal: un tubo de
    Ø32 no entra en un agujero de Ø32."""

    tipo: Literal["cilindro"]
    interior: bool
    nominal_mm: float
    diametro_min_mm: float
    diametro_max_mm: float

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.nominal_mm]


class Envolvente(BaseModel):
    """Tamaño de la pieza, sin importar cómo esté orientada."""

    tipo: Literal["envolvente"]
    min_mm: list[float] | None = None
    max_mm: list[float] | None = None
    porque: str = ""
    """De dónde sale: suele ser un juicio de ingeniería («el brazo de una
    repisa de 200 tiene que llegar al menos a 150»), no una cota literal."""

    def cotas_de_la_peticion(self) -> list[float]:
        return []


class SinSoportes(BaseModel):
    tipo: Literal["sin_soportes"]

    def cotas_de_la_peticion(self) -> list[float]:
        return []


class _Sonda(BaseModel):
    """Lo que se mide con una sonda de FreeCAD sobre el STEP (F6.12 (techo)).
    Ver `mech_toolkit/sondas.py`."""

    porque: str = ""

    def clave(self) -> str:
        return self.model_dump_json()

    def cotas_de_la_peticion(self) -> list[float]:
        return []


class AristasVivas(_Sonda):
    """«Se ve como un producto»: las aristas exteriores redondeadas o achaflanadas."""
    tipo: Literal["aristas_vivas"]
    max_fraccion: float = 0.1
    angulo_min_grados: float = 60.0


class Resistencia(_Sonda):
    """Aguanta la carga con el factor de seguridad del perfil, calculado en
    la sección REAL de la pieza construida, no en la que dice el concepto."""
    tipo: Literal["resistencia"]
    carga_N: float
    fijacion_diametro_mm: float
    direccion: Literal["entre_agujeros", "perpendicular_al_eje"]
    brazo: Literal["punta", "centro"]
    eje_diametro_mm: float | None = None

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.fijacion_diametro_mm]


class Ventana(_Sonda):
    """Una abertura pasante por la que cabe el cuerpo de un componente."""
    tipo: Literal["ventana"]
    ancho_mm: float
    alto_mm: float

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.ancho_mm, self.alto_mm]


class Coaxiales(_Sonda):
    tipo: Literal["coaxiales"]
    diametros_mm: list[list[float]]
    tol_mm: float = 0.1
    tol_grados: float = 0.5


class PasoLibre(_Sonda):
    tipo: Literal["paso_libre"]
    diametro_mm: float
    eje_de_mm: list[float]


class ParedMinima(_Sonda):
    tipo: Literal["pared_minima"]
    min_mm: float


class Ranura(_Sonda):
    tipo: Literal["ranura"]
    min_mm: float
    max_mm: float
    area_min_mm2: float = 50.0

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.max_mm]


class Retencion(_Sonda):
    tipo: Literal["retencion"]
    diametro_min_mm: float
    diametro_max_mm: float
    vuelta_min_grados: float = 200.0


class ComponenteCabe(_Sonda):
    """El componente de la ficha, en su sitio, no choca con la pieza, deja
    libres sus zonas (cable, haz) y se apoya en ella (F6.11 (biblioteca))."""
    tipo: Literal["componente_cabe"]
    ficha: dict
    en: list[float]
    giros: list[list] = []


class ComponenteEntra(_Sonda):
    """El componente se puede llevar a su sitio viniendo desde `entra_por`."""
    tipo: Literal["componente_entra"]
    ficha: dict
    en: list[float]
    giros: list[list] = []
    entra_por: Literal["+x", "-x", "+y", "-y", "+z", "-z"]


class AccesoTornillo(_Sonda):
    """La cabeza del tornillo «nombre» llega a su sitio desde fuera: un
    cilindro de `diametro_mm` desde la entrada del agujero, hacia atrás por
    su eje, no toca la pieza. Proyecto del 608ZZ (2026-11-09): el tornillo de
    abajo quedó a 1 mm detrás del alojamiento y no había cómo apretarlo."""
    tipo: Literal["acceso_tornillo"]
    nombre: str
    entrada: list[float]
    eje: list[float]
    diametro_mm: float


class Componente(BaseModel):
    """El componente de la biblioteca cabe en la pieza y se puede meter
    (F6.11 (biblioteca)). La forma sale de la ficha; dónde va y por dónde
    entra, de lo que el programa declaró con `kit.componente`. Si no lo
    declaró, no hay cómo comprobarlo, y no se aprueba."""
    tipo: Literal["componente"]
    ficha: str
    cuantos: int = 1
    """En una obra, cuántos hay entre todas sus piezas (el pan-tilt, dos SG90)."""

    def clave(self) -> str:
        return self.model_dump_json()

    def cotas_de_la_peticion(self) -> list[float]:
        return []


class Pendiente(BaseModel):
    """Lo que el banco exige pero aún no sabe medir. Cuenta como sin medir."""

    tipo: Literal["pendiente"]
    que: str
    fase: str

    def cotas_de_la_peticion(self) -> list[float]:
        return []


class Encaje(BaseModel):
    """Obras (F7.5 (obras)): cada pieza cabe y entra en la que se diseñó
    contra ella. Se sondea su forma construida (la ficha que dejó «está bien,
    la siguiente»), donde la colocó la otra, no lo que su programa dijo."""

    tipo: Literal["encaje"]

    def cotas_de_la_peticion(self) -> list[float]:
        return []


class ConjuntoLibre(BaseModel):
    """Obras: el conjunto se mueve por todo su recorrido sin que nada choque
    (F7.4 (conjunto)), con las piezas construidas y lo comprado que montan."""

    tipo: Literal["conjunto_libre"]

    def cotas_de_la_peticion(self) -> list[float]:
        return []


class Articulaciones(BaseModel):
    """Obras: los giros que pide la petición, por su eje en el mundo (en
    reposo) y su recorrido. La cinemática sale de la geometría, no la dice un
    modelo: si el soporte no queda en el eje del servo, aquí no aparece."""

    tipo: Literal["articulaciones"]
    ejes: list[Literal["vertical", "horizontal"]]
    recorrido_grados: float

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.recorrido_grados]


Asercion = Annotated[Agujeros | Cilindro | Envolvente | SinSoportes | Pendiente | AristasVivas
                     | Resistencia | Ventana | Coaxiales | PasoLibre | ParedMinima | Ranura
                     | Retencion | ComponenteCabe | ComponenteEntra | AccesoTornillo
                     | Componente | Encaje | ConjuntoLibre | Articulaciones,
                     Field(discriminator="tipo")]


class Encargo(BaseModel):
    nombre: str
    categoria: Literal["robots", "casa"]
    peticion: str
    oraculo: list[Asercion]
    obra: bool = False
    """Se pide como obra, por partes (F7.5 (obras)), y se juzga pieza a pieza."""


def cargar_encargos(carpeta: Path) -> list[Encargo]:
    return [Encargo(**yaml.safe_load(p.read_text(encoding="utf-8")))
            for p in sorted(Path(carpeta).glob("*.yaml"))]


# --- hechos y juicio ----------------------------------------------------------

class Hechos(BaseModel):
    """Lo medido en la pieza construida."""

    cilindros: list[Cylinder]
    bbox_mm: list[float]
    volumen_mm3: float
    soportes: bool | None = None
    """Lo que dijo PrusaSlicer; None si no se laminó."""
    sondas: dict[str, "Resultado"] = {}
    """Lo que midió cada sonda (F6.12 (techo)), por la clave de su aserción."""


class Resultado(BaseModel):
    estado: Estado
    detalle: str


Hechos.model_rebuild()   # `sondas` usa Resultado, que va después


def _unitario(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _base_del_plano(eje):
    """Dos vectores perpendiculares al eje: el plano donde están los centros."""
    e = _unitario(eje)
    otro = [1, 0, 0] if abs(e[0]) < 0.9 else [0, 1, 0]
    u = _unitario([e[1] * otro[2] - e[2] * otro[1], e[2] * otro[0] - e[0] * otro[2],
                   e[0] * otro[1] - e[1] * otro[0]])
    v = [e[1] * u[2] - e[2] * u[1], e[2] * u[0] - e[0] * u[2], e[0] * u[1] - e[1] * u[0]]
    return u, v


def _agujeros_distintos(caras: list[Cylinder]) -> list[Cylinder]:
    """Un agujero partido por una cara, o con avellanado, son varias caras
    sobre el mismo eje: cuentan como uno."""
    unicos: list[Cylinder] = []
    for c in caras:
        e = _unitario(c.axis)
        repetido = False
        for u in unicos:
            if abs(sum(a * b for a, b in zip(e, _unitario(u.axis)))) < 0.999:
                continue
            d = [a - b for a, b in zip(c.point, u.point)]
            along = sum(a * b for a, b in zip(d, e))
            perp = math.sqrt(max(0.0, sum(x * x for x in d) - along * along))
            if perp < MISMO_EJE_MM:
                repetido = True
                break
        if not repetido:
            unicos.append(c)
    return unicos


def _distancias(puntos):
    return sorted(math.dist(a, b) for a, b in itertools.combinations(puntos, 2))


def _juzgar_agujeros(a: Agujeros, h: Hechos) -> Resultado:
    n = len(a.patron_mm)
    interiores = [c for c in h.cilindros if c.internal]
    del_diametro = _agujeros_distintos(
        [c for c in interiores if abs(2 * c.radius - a.diametro_mm) <= a.tol_mm])
    pedido = f"{n} agujeros de Ø{a.diametro_mm:g} en su patrón"
    if len(del_diametro) < n:
        otros = sorted({round(2 * c.radius, 2) for c in interiores})
        return Resultado(estado="no_cumple", detalle=(
            f"pide {pedido}; hay {len(del_diametro)} de ese diámetro. "
            f"Diámetros de agujero en la pieza: {', '.join(f'Ø{d:g}' for d in otros) or 'ninguno'}"))
    objetivo = _distancias(a.patron_mm)
    mejor = math.inf
    # Agrupar por dirección del eje: un patrón es de agujeros paralelos.
    for eje in {tuple(round(x, 3) for x in _unitario(c.axis)) for c in del_diametro}:
        paralelos = [c for c in del_diametro
                     if abs(sum(x * y for x, y in zip(eje, _unitario(c.axis)))) > 0.999]
        if len(paralelos) < n:
            continue
        u, v = _base_del_plano(eje)
        planos = [(sum(p * q for p, q in zip(c.point, u)), sum(p * q for p, q in zip(c.point, v)))
                  for c in paralelos]
        for combo in itertools.combinations(planos[:14], n):
            desvio = max(abs(x - y) for x, y in zip(_distancias(combo), objetivo)) if n > 1 else 0
            mejor = min(mejor, desvio)
    if mejor <= POS_TOL_MM:
        return Resultado(estado="cumple", detalle=f"{pedido}: desvío máximo {mejor:.2f} mm")
    detalle = f"pide {pedido}; los de ese diámetro no forman el patrón"
    if mejor < math.inf:
        detalle += f" (lo más cercano se desvía {mejor:.2f} mm entre centros)"
    return Resultado(estado="no_cumple", detalle=detalle)


def _juzgar_cilindro(a: Cilindro, h: Hechos) -> Resultado:
    tipo = "alojamiento" if a.interior else "saliente"
    candidatos = [2 * c.radius for c in h.cilindros if c.internal == a.interior]
    dentro = [d for d in candidatos if a.diametro_min_mm <= d <= a.diametro_max_mm]
    rango = f"Ø{a.diametro_min_mm:g}–{a.diametro_max_mm:g} para Ø{a.nominal_mm:g}"
    if dentro:
        return Resultado(estado="cumple", detalle=f"{tipo} Ø{dentro[0]:.2f} ({rango})")
    cerca = min(candidatos, key=lambda d: abs(d - a.nominal_mm), default=None)
    return Resultado(estado="no_cumple", detalle=(
        f"pide un {tipo} {rango}; "
        + (f"el más parecido es Ø{cerca:.2f}" if cerca is not None else f"no hay ningún {tipo}")))


def _juzgar_envolvente(a: Envolvente, h: Hechos) -> Resultado:
    medida = sorted(h.bbox_mm, reverse=True)
    texto = " x ".join(f"{x:g}" for x in medida)
    if a.min_mm and any(m < x - 0.05 for m, x in zip(medida, sorted(a.min_mm, reverse=True))):
        return Resultado(estado="no_cumple", detalle=(
            f"mide {texto}; tiene que llegar al menos a "
            f"{' x '.join(f'{x:g}' for x in sorted(a.min_mm, reverse=True))}. {a.porque}".strip()))
    if a.max_mm and any(m > x + 0.05 for m, x in zip(medida, sorted(a.max_mm, reverse=True))):
        return Resultado(estado="no_cumple", detalle=(
            f"mide {texto}; no puede pasar de "
            f"{' x '.join(f'{x:g}' for x in sorted(a.max_mm, reverse=True))}. {a.porque}".strip()))
    return Resultado(estado="cumple", detalle=f"mide {texto}")


def juzgar(a, h: Hechos) -> Resultado:
    if isinstance(a, _Sonda):
        return h.sondas.get(a.clave()) or Resultado(estado="sin_medir",
                                                     detalle="la sonda no llegó a medir")
    if isinstance(a, Agujeros):
        return _juzgar_agujeros(a, h)
    if isinstance(a, Cilindro):
        return _juzgar_cilindro(a, h)
    if isinstance(a, Envolvente):
        return _juzgar_envolvente(a, h)
    if isinstance(a, SinSoportes):
        if h.soportes is None:
            return Resultado(estado="sin_medir", detalle="no se laminó")
        return (Resultado(estado="no_cumple", detalle="PrusaSlicer pide soportes")
                if h.soportes else Resultado(estado="cumple", detalle="se lamina sin soportes"))
    return Resultado(estado="sin_medir", detalle=f"{a.que} — se medirá con {a.fase}")


def sondas_de_componente(a: Componente, rasgos: list[dict]) -> list[_Sonda]:
    """Las dos sondas de un componente, con la ficha de la biblioteca y la
    colocación que declaró el programa. Vacío si no lo colocó."""
    from orchestrator.componentes import cargar

    colocado = next((r for r in rasgos if r.get("tipo") == "componente"
                     and r.get("ficha") == a.ficha), None)
    return [] if colocado is None else sondas_del_rasgo(colocado)


def sondas_del_rasgo(colocado: dict, extra=()) -> list[_Sonda]:
    """Cabe y entra, para un componente que el programa colocó con
    `kit.componente`: lo usan el banco y el bucle de diseño (F6.7 (lazo)).
    `extra`: más carpetas de fichas (las de una obra)."""
    from orchestrator.componentes import cargar

    ficha = cargar(colocado["ficha"], extra).model_dump()
    donde = {"ficha": ficha, "en": colocado["en"], "giros": colocado.get("giros") or []}
    return [ComponenteCabe(tipo="componente_cabe", **donde),
            ComponenteEntra(tipo="componente_entra", entra_por=colocado["entra_por"], **donde)]


def juzgar_componente(a: Componente, sondas: list[_Sonda], h: Hechos) -> Resultado:
    if not sondas:
        return Resultado(estado="no_cumple", detalle=(
            f"la pieza no dice dónde va el {a.ficha} (no usa `kit.componente`): no se "
            "puede comprobar que quepa ni que entre"))
    medidas = [h.sondas.get(s.clave()) or Resultado(estado="sin_medir", detalle="sin medir")
               for s in sondas]
    for estado in ("no_cumple", "sin_medir"):
        malas = [m.detalle for m in medidas if m.estado == estado]
        if malas:
            return Resultado(estado=estado, detalle="; ".join(malas))
    return Resultado(estado="cumple", detalle="; ".join(m.detalle for m in medidas))


def nota(resultados: list[Resultado]) -> float:
    """Lo que cumple entre TODO lo exigido: lo no medido cuenta en el
    denominador, o una pieza de la que no se mide nada sacaría un 100 %."""
    return sum(r.estado == "cumple" for r in resultados) / len(resultados) if resultados else 0.0


def informe(por_encargo: dict[str, list[Resultado]], *, modelo: str = "",
            coste_usd: float | None = None, fallos: dict[str, str] | None = None) -> str:
    fallos = fallos or {}
    todos = [r for rs in por_encargo.values() for r in rs]
    lineas = [f"# Banco de piezas — {dt.date.today().isoformat()}", ""]
    if modelo:
        lineas.append(f"**Modelo:** {modelo}  ")
    if coste_usd is not None:
        lineas.append(f"**Coste:** {coste_usd:.2f} USD  ")
    lineas += [f"**Nota global:** {100 * nota(todos):.0f} % "
               f"({sum(r.estado == 'cumple' for r in todos)} de {len(todos)} exigencias)", "",
               "| Encargo | Nota | Cumple | No cumple | Sin medir |", "|---|---|---|---|---|"]
    for nombre, rs in por_encargo.items():
        cuenta = {e: sum(r.estado == e for r in rs) for e in ("cumple", "no_cumple", "sin_medir")}
        lineas.append(f"| {nombre} | {100 * nota(rs):.0f} % | {cuenta['cumple']} | "
                      f"{cuenta['no_cumple']} | {cuenta['sin_medir']} |")
    for nombre, rs in por_encargo.items():
        lineas += ["", f"## {nombre}", ""]
        if nombre in fallos:
            lineas += [f"**No se construyó:** {fallos[nombre]}", ""]
        lineas += [f"- **{r.estado}** — {r.detalle}" for r in rs]
    return "\n".join(lineas) + "\n"


# --- ejecución ---------------------------------------------------------------

_ENVOLVENTE = '''\
import json
import Part
forma = Part.read({step!r})
# optimalBoundingBox: con redondeos tóricos BoundBox sale holgada; la placa
# de 80 × 50 del e2e medía 80.82 × 50.82 para el juez (2026-11-04).
b = forma.optimalBoundingBox()
print("INTELLIPRINT_BBOX:" + json.dumps([b.XLength, b.YLength, b.ZLength, forma.Volume]))
'''


_SONDAS = '''\
import json
import sys
sys.path.insert(0, {toolkit!r})
import Part
from mech_toolkit.sondas import medir
forma = Part.read({step!r})
if len(forma.Solids) == 1:
    forma = forma.Solids[0]
print("INTELLIPRINT_SONDAS:" + json.dumps(medir(forma, json.loads({specs!r}),
                                                json.loads({material!r}))))
'''


def medir_sondas(step: Path, aserciones: list, freecadcmd: str,
                 material: dict) -> list[Resultado]:
    """Corre las sondas de `aserciones` sobre el STEP, en un solo freecadcmd."""
    import tempfile

    import mech_toolkit

    if not aserciones:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "sondas.py"
        script.write_text(_SONDAS.format(
            toolkit=str(Path(mech_toolkit.__file__).resolve().parent.parent), step=str(step),
            specs=json.dumps([a.model_dump() for a in aserciones]),
            material=json.dumps(material)), encoding="utf-8")
        proceso = subprocess.run([freecadcmd, str(script)], capture_output=True, text=True,
                                 timeout=900)
    linea = next((l for l in proceso.stdout.splitlines() if l.startswith("INTELLIPRINT_SONDAS:")),
                 None)
    if linea is None:
        motivo = (proceso.stdout + proceso.stderr).strip().splitlines()[-1:] or ["sin salida"]
        return [Resultado(estado="sin_medir", detalle=f"las sondas no corrieron: {motivo[0]}")
                for _ in aserciones]
    return [Resultado(estado="sin_medir" if r["cumple"] is None else
                      "cumple" if r["cumple"] else "no_cumple", detalle=r["detalle"])
            for r in json.loads(linea.split(":", 1)[1])]


def extraer_hechos(step: Path, freecadcmd: str, laminado: Path | None,
                   aserciones: list | None = None, material: dict | None = None) -> Hechos:
    import tempfile

    from mech_toolkit.measure import extract_cylinders

    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "envolvente.py"
        script.write_text(_ENVOLVENTE.format(step=str(step)), encoding="utf-8")
        salida = subprocess.run([freecadcmd, str(script)], capture_output=True,
                                text=True, timeout=180).stdout
    linea = next(l for l in salida.splitlines() if l.startswith("INTELLIPRINT_BBOX:"))
    *bbox, volumen = json.loads(linea.split(":", 1)[1])
    soportes = None
    if laminado is not None and laminado.exists():
        soportes = json.loads(laminado.read_text(encoding="utf-8"))["needs_supports"]
    sondas = [a for a in aserciones or [] if isinstance(a, _Sonda)]
    medidas = medir_sondas(step, sondas, freecadcmd, material or {}) if sondas else []
    return Hechos(cilindros=extract_cylinders(step, freecadcmd), bbox_mm=bbox,
                  volumen_mm3=volumen, soportes=soportes,
                  sondas={a.clave(): r for a, r in zip(sondas, medidas)})


def motivo_del_fallo(salida: str) -> str:
    """La línea que dice por qué no salió, no la última del traceback."""
    for linea in reversed(salida.splitlines()):
        if "ConstruccionFallida:" in linea or "Error:" in linea:
            return linea.split(":", 1)[1].strip()[:400]
    lineas = [l for l in salida.splitlines() if l.strip()]
    return (lineas[-1] if lineas else "sin salida")[:400]


LIMITE_S = 3600
"""Lo más que espera el banco a un encargo. Es una guarda contra cuelgues,
no una exigencia: la web no tiene límite. Con 30 minutos, el MG996R del
banco `1106-1554` no llegó: concepto y cinco vueltas del razonador, a unos
cinco minutos cada una."""


def _texto(salida) -> str:
    if salida is None:
        return ""
    return salida.decode("utf-8", errors="replace") if isinstance(salida, bytes) else salida


def correr(encargo: Encargo, carpeta: Path, orden: list[str], freecadcmd: str,
           env: dict, material: dict | None = None) -> tuple[list[Resultado], str | None]:
    """Pide la pieza como la pediría una persona y la juzga. Devuelve los
    resultados y, si no llegó a construirse, el porqué."""
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        proceso = subprocess.run(
            [*orden, encargo.peticion], input="sí\n", capture_output=True, text=True,
            timeout=LIMITE_S, env={**env, "INTELLIPRINT_WORKSPACE": str(carpeta)})
    except subprocess.TimeoutExpired as e:
        # Banco `1106-1554` (2026-11-06): esto salía de aquí y la corrida
        # entera murió en el primer encargo. Se pierde el encargo, no el banco.
        texto = _texto(e.output) + "\n--- stderr ---\n" + _texto(e.stderr)
        (carpeta / "salida.txt").write_text(texto, encoding="utf-8")
        sin = [Resultado(estado="no_cumple", detalle="no hay pieza") for _ in encargo.oraculo]
        return sin, f"tardó más de {LIMITE_S // 60} minutos"
    (carpeta / "salida.txt").write_text(proceso.stdout + "\n--- stderr ---\n" + proceso.stderr,
                                        encoding="utf-8")
    if encargo.obra:
        return _juzgar_si_hay_obra(encargo, carpeta, freecadcmd, material,
                                   proceso.stdout + "\n" + proceso.stderr)
    step = next(carpeta.glob("projects/*/parts/*/*.step"), None)
    # Que exista el STEP no basta: queda el de un intento fallido. En la
    # primera corrida (2026-11-03) el banco midió los restos de dos piezas
    # que no llegaron a construirse y les dio puntos.
    if not construida(carpeta, proceso.returncode, proceso.stdout) or step is None:
        sin = [Resultado(estado="no_cumple", detalle="no hay pieza") for _ in encargo.oraculo]
        return sin, motivo_del_fallo(proceso.stdout + "\n" + proceso.stderr)
    return juzgar_pieza(encargo, carpeta, freecadcmd, material), None


def _juzgar_si_hay_obra(encargo: Encargo, carpeta: Path, freecadcmd: str,
                        material: dict | None, salida: str) -> tuple[list[Resultado], str | None]:
    """Una obra se juzga con lo que tenga construido: las piezas que falten
    no cumplen, con su nombre. Sin desglose no hay nada que juzgar."""
    from orchestrator.obra import OBRA
    if next(Path(carpeta).glob(f"projects/*/{OBRA}"), None) is None:
        sin = [Resultado(estado="no_cumple", detalle="no hay obra") for _ in encargo.oraculo]
        return sin, motivo_del_fallo(salida)
    return juzgar_obra(encargo, carpeta, freecadcmd, material), None


def construida(carpeta: Path, codigo: int | None, salida: str) -> bool:
    """`intelliprint pieza` sale con 1 cuando la pieza no cumple, pero la
    entrega igual (F6.8 (mejor)) y deja su informe con el volumen: esa pieza
    se juzga. Una que no se construyó deja informe sin volumen. `new` (las
    corridas viejas) decía «Listo»."""
    informe = next(Path(carpeta).glob("projects/*/pieza_report.json"), None)
    if informe is not None:
        try:
            return json.loads(informe.read_text(encoding="utf-8")).get("volumen_mm3") is not None
        except ValueError:
            return False
    # `recipe.json` se guarda solo cuando la construcción salió (un intento
    # fallido no lo deja). Sin él, la línea base del 2026-11-05 dio 0 %: el
    # laminado reventó después de construir y el informe no se escribió.
    if next(Path(carpeta).glob("projects/*/parts/*/recipe.json"), None) is not None:
        return True
    return codigo == 0 or "] Listo:" in salida


def juzgar_pieza(encargo: Encargo, carpeta: Path, freecadcmd: str,
                 material: dict | None = None) -> list[Resultado]:
    step = next(carpeta.glob("projects/*/parts/*/*.step"))
    laminado = next(carpeta.glob("projects/*/fabrication/slicing_report.json"), None)
    rasgos_json = step.parent / "rasgos.json"
    rasgos = json.loads(rasgos_json.read_text(encoding="utf-8")) if rasgos_json.exists() else []
    de_componente = {a.clave(): sondas_de_componente(a, rasgos)
                     for a in encargo.oraculo if isinstance(a, Componente)}
    medir = [*encargo.oraculo, *(s for ss in de_componente.values() for s in ss)]
    hechos = extraer_hechos(step, freecadcmd, laminado, medir, material)
    return [juzgar_componente(a, de_componente[a.clave()], hechos) if isinstance(a, Componente)
            else juzgar(a, hechos) for a in encargo.oraculo]


def _junta(resultados: list[tuple[str, Resultado]], todas: str) -> Resultado:
    """Un resultado de varios, cada uno de una pieza: cumple si cumplen todos;
    si no, dice en cuáles falla."""
    for estado in ("no_cumple", "sin_medir"):
        malos = [f"«{n}»: {r.detalle}" for n, r in resultados if r.estado == estado]
        if malos:
            return Resultado(estado=estado, detalle="; ".join(malos))
    return Resultado(estado="cumple", detalle=todas)


def _articulaciones(a: Articulaciones, v: list[dict]) -> Resultado:
    def cual(eje):
        z = abs(eje[2]) / math.sqrt(sum(x * x for x in eje))
        return "vertical" if z > 0.99 else "horizontal" if z < 0.01 else "inclinado"

    hay = [(cual(j.get("eje_mundo") or j["eje"]), j["recorrido"][1] - j["recorrido"][0])
           for j in v]
    texto = ", ".join(f"{c} de {r:g}°" for c, r in hay) or "ninguna"
    faltan = list(a.ejes)
    for c, r in hay:
        if c in faltan and r >= a.recorrido_grados - 1e-6:
            faltan.remove(c)
    if faltan:
        return Resultado(estado="no_cumple", detalle=(
            f"falta un giro {' y uno '.join(faltan)} de {a.recorrido_grados:g}°; hay: {texto}"))
    return Resultado(estado="cumple", detalle=f"articulaciones: {texto}")


def _sondeado(h: Hechos, sondas: list) -> Resultado:
    return _junta([(s.tipo, h.sondas.get(s.clave())
                    or Resultado(estado="sin_medir", detalle="sin medir")) for s in sondas],
                  "cabe y entra")


def juzgar_obra(encargo: Encargo, carpeta: Path, freecadcmd: str,
                material: dict | None = None, hechos_de=None) -> list[Resultado]:
    """F7.5 (obras). Lo que se pide a una pieza se mide en CADA pieza de la
    obra; los componentes, en la que los aloja; y además el encaje entre
    piezas, el conjunto moviéndose y sus articulaciones. Antes el banco medía
    el primer STEP que encontraba: en una obra habría juzgado solo la base."""
    from orchestrator import obra as O
    from orchestrator.conjunto import VERIFICACION, leer_piezas

    hechos_de = hechos_de or extraer_hechos
    proyecto = next(Path(carpeta).glob(f"projects/*/{O.OBRA}")).parent
    ob = O.cargar_obra(proyecto)
    fichas = O.carpeta_de_fichas(proyecto)
    piezas = leer_piezas(proyecto, solo_construidas=True)
    sin_construir = [n.nombre for n in ob.nodos if n.tipo == "pieza" and n.id not in piezas]

    de_pieza = [a for a in encargo.oraculo
                if not isinstance(a, (Componente, Encaje, ConjuntoLibre, Articulaciones))]
    # Solo se sondea lo que el oráculo pregunta: cada sonda es FreeCAD.
    pedidos = {a.ficha for a in encargo.oraculo if isinstance(a, Componente)}
    encaje = any(isinstance(a, Encaje) for a in encargo.oraculo)
    medidas: dict[str, tuple] = {}
    for p in piezas.values():
        rasgos = json.loads((p.step.parent / "rasgos.json").read_text(encoding="utf-8"))
        propias = [(r, sondas_del_rasgo(r)) for r in p.propios if r["ficha"] in pedidos]
        encajes = [(r, sondas_del_rasgo(r, [fichas])) for r in rasgos if encaje
                   and r.get("tipo") == "componente" and str(r.get("ficha")).startswith("obra-")]
        laminado = p.step.parent.parent.parent / "fabrication" / "slicing_report.json"
        medir = [*de_pieza, *(s for _, ss in propias + encajes for s in ss)]
        medidas[p.id] = (hechos_de(p.step, freecadcmd, laminado, medir, material),
                         propias, encajes)

    conjuntos = [n for n in ob.nodos if n.tipo == "conjunto"]
    verificaciones = [json.loads(f.read_text(encoding="utf-8")) for n in conjuntos
                      if (f := proyecto / O.NODOS / n.id / VERIFICACION).is_file()]
    salida = []
    for a in encargo.oraculo:
        if sin_construir and not isinstance(a, (ConjuntoLibre, Articulaciones)):
            salida.append(Resultado(estado="no_cumple", detalle=(
                "no se construyó: " + ", ".join(f"«{n}»" for n in sin_construir))))
        elif isinstance(a, Componente):
            hay = [(piezas[i].nombre, juzgar_componente(a, ss, h))
                   for i, (h, propias, _) in medidas.items()
                   for r, ss in propias if r["ficha"] == a.ficha]
            if len(hay) != a.cuantos:
                salida.append(Resultado(estado="no_cumple", detalle=(
                    f"hay {len(hay)} {a.ficha} en las piezas y se piden {a.cuantos}")))
            else:
                salida.append(_junta(hay, f"los {a.cuantos} {a.ficha} caben y entran"))
        elif isinstance(a, Encaje):
            hay = [(f"{piezas[i].nombre}» con «{r['ficha']}", _sondeado(h, ss))
                   for i, (h, _, encajes) in medidas.items() for r, ss in encajes]
            if not hay:
                salida.append(Resultado(estado="no_cumple", detalle=(
                    "ninguna pieza se colocó contra otra con `kit.componente`")))
            else:
                salida.append(_junta(hay, f"{len(hay)} uniones entre piezas caben y entran"))
        elif isinstance(a, ConjuntoLibre):
            if not conjuntos:
                salida.append(Resultado(estado="no_cumple", detalle="la obra no tiene conjunto"))
            elif len(verificaciones) < len(conjuntos):
                salida.append(Resultado(estado="no_cumple",
                                        detalle="el conjunto no se movió (no hay verificación)"))
            elif all(v["ok"] for v in verificaciones):
                salida.append(Resultado(estado="cumple",
                                        detalle="se mueve por todo su recorrido sin chocar"))
            else:
                salida.append(Resultado(estado="no_cumple", detalle="; ".join(
                    r for v in verificaciones for r in v.get("resumen", []))))
        elif isinstance(a, Articulaciones):
            salida.append(_articulaciones(a, [j for v in verificaciones
                                              for j in v.get("articulaciones", [])]))
        else:
            salida.append(_junta([(piezas[i].nombre, juzgar(a, h))
                                  for i, (h, _, _) in medidas.items()],
                                 f"en las {len(medidas)} piezas"))
    return salida


def rejuzgar(encargos: list[Encargo], corrida: Path, freecadcmd: str,
             material: dict | None = None) -> tuple[dict, dict]:
    """Vuelve a juzgar las piezas de una corrida ya hecha, sin pedirlas otra
    vez: cambiar el juez no debería costar 46 minutos de modelo. Una pieza
    cuenta como construida si `intelliprint new` dijo «Listo»; que exista el
    STEP no basta (puede ser el de un intento fallido)."""
    resultados, fallos = {}, {}
    for i, e in enumerate(encargos, 1):
        carpeta = Path(corrida) / f"{i:02d}"
        salida = carpeta / "salida.txt"
        texto = salida.read_text(encoding="utf-8", errors="ignore") if salida.exists() else ""
        if e.obra:
            resultados[e.nombre], fallo = _juzgar_si_hay_obra(e, carpeta, freecadcmd, material,
                                                              texto)
            if fallo:
                fallos[e.nombre] = fallo
            continue
        if (not texto or not construida(carpeta, None, texto)
                or next(carpeta.glob("projects/*/parts/*/*.step"), None) is None):
            resultados[e.nombre] = [Resultado(estado="no_cumple", detalle="no hay pieza")
                                    for _ in e.oraculo]
            fallos[e.nombre] = "no se construyó en esa corrida"
            continue
        resultados[e.nombre] = juzgar_pieza(e, carpeta, freecadcmd, material)
    return resultados, fallos
