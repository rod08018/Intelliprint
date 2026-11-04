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


class Pendiente(BaseModel):
    """Lo que el banco exige pero aún no sabe medir. Cuenta como sin medir."""

    tipo: Literal["pendiente"]
    que: str
    fase: str

    def cotas_de_la_peticion(self) -> list[float]:
        return []


Asercion = Annotated[Agujeros | Cilindro | Envolvente | SinSoportes | Pendiente,
                     Field(discriminator="tipo")]


class Encargo(BaseModel):
    nombre: str
    categoria: Literal["robots", "casa"]
    peticion: str
    oraculo: list[Asercion]


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


class Resultado(BaseModel):
    estado: Estado
    detalle: str


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
b = forma.BoundBox
print("INTELLIPRINT_BBOX:" + json.dumps([b.XLength, b.YLength, b.ZLength, forma.Volume]))
'''


def extraer_hechos(step: Path, freecadcmd: str, laminado: Path | None) -> Hechos:
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
    return Hechos(cilindros=extract_cylinders(step, freecadcmd), bbox_mm=bbox,
                  volumen_mm3=volumen, soportes=soportes)


def motivo_del_fallo(salida: str) -> str:
    """La línea que dice por qué no salió, no la última del traceback."""
    for linea in reversed(salida.splitlines()):
        if "ConstruccionFallida:" in linea or "Error:" in linea:
            return linea.split(":", 1)[1].strip()[:400]
    lineas = [l for l in salida.splitlines() if l.strip()]
    return (lineas[-1] if lineas else "sin salida")[:400]


def correr(encargo: Encargo, carpeta: Path, orden: list[str], freecadcmd: str,
           env: dict) -> tuple[list[Resultado], str | None]:
    """Pide la pieza como la pediría una persona y la juzga. Devuelve los
    resultados y, si no llegó a construirse, el porqué."""
    carpeta.mkdir(parents=True, exist_ok=True)
    proceso = subprocess.run(
        [*orden, encargo.peticion], input="sí\n", capture_output=True, text=True,
        timeout=1800, env={**env, "INTELLIPRINT_WORKSPACE": str(carpeta)})
    (carpeta / "salida.txt").write_text(proceso.stdout + "\n--- stderr ---\n" + proceso.stderr,
                                        encoding="utf-8")
    step = next(carpeta.glob("projects/*/parts/*/*.step"), None)
    # Que exista el STEP no basta: queda el de un intento fallido. En la
    # primera corrida (2026-11-03) el banco midió los restos de dos piezas
    # que no llegaron a construirse y les dio puntos.
    if proceso.returncode != 0 or step is None:
        sin = [Resultado(estado="no_cumple", detalle="no hay pieza") for _ in encargo.oraculo]
        return sin, motivo_del_fallo(proceso.stdout + "\n" + proceso.stderr)
    laminado = next(carpeta.glob("projects/*/fabrication/slicing_report.json"), None)
    hechos = extraer_hechos(step, freecadcmd, laminado)
    return [juzgar(a, hechos) for a in encargo.oraculo], None
