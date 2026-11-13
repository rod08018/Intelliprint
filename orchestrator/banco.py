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


class ZonaLibre(_Sonda):
    """La pieza deja libre el sitio de un giro (F9.1 (barrido)): en el
    cilindro de `radio_mm` alrededor del eje que sale de `punto` hacia `eje`
    —la salida del actuador que monta— no hay nada de ella. El soporte del
    pan-tilt 1110-0313 no le dejó sitio a la plataforma, y nadie lo midió
    hasta que las tres piezas estaban dadas por buenas."""
    tipo: Literal["zona_libre"]
    nombre: str
    punto: list[float]
    eje: list[float]
    radio_mm: float


class CaraQueSeOrienta(_Sonda):
    """En una cara plana de la pieza cuya normal es perpendicular a `eje`
    cabe un rectángulo de `cabe_mm` (F9.14 (orienta)): lo que se monte en
    ella cambia
    de orientación cuando la pieza gira alrededor de ese eje. La plataforma
    del pan-tilt 1111-1342 era un disco centrado en el eje de inclinación:
    pasó el banco y una cámara montada en él habría rodado sobre su eje
    óptico en vez de cabecear."""
    tipo: Literal["cara_que_se_orienta"]
    eje: list[float]
    cabe_mm: list[float] = Field(min_length=2, max_length=2)
    tolerancia_grados: float = 20.0


class SeOrienta(BaseModel):
    """Obras: la pieza que gira sobre el eje `eje` (en el mundo, en reposo)
    lleva lo suyo de forma que cambie de orientación al girar. Se mide con
    `CaraQueSeOrienta` sobre esa pieza, con su eje en su propio marco."""
    tipo: Literal["se_orienta"]
    eje: Literal["vertical", "horizontal"]
    cabe_mm: list[float] = Field(min_length=2, max_length=2)
    """Los dos lados de lo que la pieza tiene que llevar: tiene que caber
    ese rectángulo en la cara. El área sola no basta: en una placa de
    32 × 22 (704 mm²) no cabe una cámara de 25 × 24 (600 mm²)."""
    tolerancia_grados: float = 20.0
    porque: str = ""
    giro: Literal["último", "primero"] = "último"
    """Si varias piezas giran sobre un eje así, cuál lleva lo suyo, contando
    de la base a la punta. En el pan-tilt con pinza la cámara va en la
    plataforma, el primer giro horizontal; el último es el dedo."""

    def cotas_de_la_peticion(self) -> list[float]:
        return []   # lo que cabe sale de una hoja de datos, no de la petición


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


class Tornillos(BaseModel):
    """Obras (F9.6 (previsto)): lo comprado está sujeto con los tornillos
    de su ficha, y agarran. `cuantos` se cuenta a mano en el encargo; lo que
    hay se mide en los agujeros de las piezas construidas
    (`tornilleria.tornillos`). El pan-tilt 1111-1342 pasó el banco con un
    servo sin tornillos y el otro con dos agujeros más anchos que ellos."""
    tipo: Literal["tornillos"]
    sujetan: str
    """El id de la ficha de lo que sujetan."""
    metrica: str
    cuantos: int = Field(ge=1)

    def cotas_de_la_peticion(self) -> list[float]:
        return []   # salen de la ficha del componente, no de la petición


class Alcance(BaseModel):
    """Backlogs (F10.1 (serie)): hasta dónde llega la punta, medido del eje
    del hombro —el primer giro que la levanta— y en perpendicular a él, en
    todas las poses del estudio (`estudio.estudiar`). El pan-tilt pasó todo
    lo que se le pedía sin que nadie mirara a dónde llegaba: un brazo de
    20 mm con tres servos habría pasado igual.

    Se medía del eje del primer giro, y el primer brazo (1112-0318) cumplió
    «120 mm» con 233: 120 de brazo y un separador de 105 mm a lo largo del
    eje del hombro. Lo cambió el usuario el 2026-11-12."""
    tipo: Literal["alcance"]
    minimo_mm: float = Field(gt=0)

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.minimo_mm]


class Carga(BaseModel):
    """Backlogs (F10.1 (serie)): cuántos gramos levanta en la punta, en la
    peor pose: lo menor de lo que dejan los actuadores (al 50 % de su par),
    el vuelco si la base no va atornillada, y el material."""
    tipo: Literal["carga"]
    minimo_g: float = Field(gt=0)

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.minimo_g]


class Reduccion(BaseModel):
    """Backlogs (F10.3 (correa)): la relación con la que un motor mueve un
    giro, contada por dientes en lo construido: los de la polea que la pieza
    que gira lleva en su eje entre los de la polea del motor. Y con la
    correa puesta: los dos ejes paralelos y a la distancia de una correa
    cerrada. Sin esto, «con una correa 4:1» pasaba con un motor al lado y
    nada entre los dos."""
    tipo: Literal["reduccion"]
    relacion: float = Field(ge=1)

    def cotas_de_la_peticion(self) -> list[float]:
        return [self.relacion]


class Conserva(BaseModel):
    """Ampliaciones (F9.10 (ampliar)): cuántas de las piezas que el invento
    ya tenía siguen idénticas después de añadirle la función. Se mide en lo
    construido: una pieza cuenta si su STEP es byte a byte el de antes de
    ampliar (`ampliar.HECHAS`). Sin esto, «añádele una pinza» podía rehacer
    el invento entero y pasar igual."""
    tipo: Literal["conserva"]
    minimo: int = Field(ge=1)

    def cotas_de_la_peticion(self) -> list[float]:
        return []   # es una cuenta de piezas, no una cota


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
    # «cualquiera»: la petición dice que gira pero no hacia dónde mira el eje
    # (la polea del 608ZZ, en un soporte que va a un perfil en cualquier postura).
    ejes: list[Literal["vertical", "horizontal", "cualquiera"]]
    # «vuelta entera»: lo que gira en un rodamiento. No es una cota que haya
    # que leer en la petición —«gira» ya la dice—, así que no se exige el 360.
    recorrido_grados: float | Literal["vuelta entera"]

    def grados(self) -> float:
        return 360.0 if self.recorrido_grados == "vuelta entera" else self.recorrido_grados

    def cotas_de_la_peticion(self) -> list[float]:
        return [] if self.recorrido_grados == "vuelta entera" else [self.recorrido_grados]


Asercion = Annotated[Agujeros | Cilindro | Envolvente | SinSoportes | Pendiente | AristasVivas
                     | Resistencia | Ventana | Coaxiales | PasoLibre | ParedMinima | Ranura
                     | Retencion | ComponenteCabe | ComponenteEntra | AccesoTornillo | ZonaLibre
                     | CaraQueSeOrienta | SeOrienta | Tornillos | Componente | Encaje
                     | ConjuntoLibre | Articulaciones | Alcance | Carga | Conserva | Reduccion,
                     Field(discriminator="tipo")]


class Encargo(BaseModel):
    nombre: str
    categoria: Literal["robots", "casa"]
    peticion: str
    oraculo: list[Asercion]
    obra: bool = False
    """Se pide como obra, por partes (F7.5 (obras)), y se juzga pieza a pieza."""
    amplia: str = ""
    """F9.10 (ampliar): el nombre del encargo cuyo invento se amplía. La
    `peticion` es entonces la función que se le añade, y se pide aparte,
    sobre el invento ya diseñado."""
    de_antes: str = ""
    """La petición del encargo que amplía; la pone `cargar_encargos`."""

    @property
    def peticion_entera(self) -> str:
        """Todo lo que la persona pidió: de aquí salen las cotas del oráculo."""
        return f"{self.de_antes.strip()}\n{self.peticion.strip()}".strip()


def cargar_encargos(carpeta: Path) -> list[Encargo]:
    encargos = [Encargo(**yaml.safe_load(p.read_text(encoding="utf-8")))
                for p in sorted(Path(carpeta).glob("*.yaml"))]
    por_nombre = {e.nombre: e for e in encargos}
    for e in encargos:
        if e.amplia:
            base = por_nombre.get(e.amplia)
            if base is None or not (base.obra and e.obra) or base.amplia:
                raise ValueError(f"{e.nombre}: amplía «{e.amplia}», que tiene que ser otro "
                                 "encargo de backlog, y este también")
            e.de_antes = base.peticion
    return encargos


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
    valor: float | None = None
    """La cifra de la sonda, si da una además de su veredicto: a cuánto
    queda un componente de la pieza. Con ella se ve si una pieza que tocaba a
    otra dejó de tocarla (F9.9 (revalidar)); el detalle es para leerlo."""


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
                      "cumple" if r["cumple"] else "no_cumple", detalle=r["detalle"],
                      valor=r.get("valor"))
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

LIMITE_OBRA_S = 4 * LIMITE_S
"""Una obra son varias piezas seguidas, más el desglose y moverla entera:
con la hora de una pieza la mataría la guarda sin haberse colgado nada."""


def _texto(salida) -> str:
    if salida is None:
        return ""
    return salida.decode("utf-8", errors="replace") if isinstance(salida, bytes) else salida


def _correr_ampliacion(encargo: Encargo, carpeta: Path, orden: list[str], freecadcmd: str,
                       env: dict, material: dict | None, laminar, base: Encargo | None,
                       partir_de: Path | None) -> tuple[list[Resultado], str | None]:
    """Un encargo que amplía otro (F9.10 (ampliar)): primero tiene que
    existir el invento, y encima se pide la función con `obra --ampliar`.

    Con `partir_de`, el invento se copia de esa corrida y solo se paga la
    ampliación; la corrida de la que se parte no se toca. Sin él, se pide
    antes el invento entero, aquí mismo."""
    import shutil

    from orchestrator.obra import OBRA
    if base is None:
        raise ValueError(f"{encargo.nombre} amplía «{encargo.amplia}» y no se pasó ese encargo")
    sin = [Resultado(estado="no_cumple", detalle="no hay obra") for _ in encargo.oraculo]
    salidas: list[str] = []

    def pedir(orden_: list[str]) -> bool:
        try:
            proceso = subprocess.run(
                orden_, input="sí\n", capture_output=True, text=True, timeout=LIMITE_OBRA_S,
                env={**env, "INTELLIPRINT_WORKSPACE": str(carpeta)})
        except subprocess.TimeoutExpired as e:
            salidas.append(_texto(e.output) + "\n--- stderr ---\n" + _texto(e.stderr))
            return False
        salidas.append(proceso.stdout + "\n--- stderr ---\n" + proceso.stderr)
        return True

    def cerrar(fallo: str) -> tuple[list[Resultado], str]:
        (carpeta / "salida.txt").write_text("\n".join(salidas), encoding="utf-8")
        return sin, fallo

    if partir_de is not None:
        # Solo por su marca: por el puesto se podría ampliar el invento de
        # otro encargo sin que nada lo dijera.
        marcas = {m.read_text(encoding="utf-8").strip(): m.parent
                  for m in Path(partir_de).glob(f"*/{ENCARGO}")}
        origen = marcas.get(base.nombre)
        if origen is None or next(origen.glob(f"projects/*/{OBRA}"), None) is None:
            return cerrar(f"en {Path(partir_de).name} no está el invento de «{base.nombre}» "
                          "del que partir")
        shutil.copytree(origen / "projects", carpeta / "projects")
    elif not pedir([*orden, base.peticion]):
        return cerrar(f"el invento tardó más de {LIMITE_OBRA_S // 60} minutos")
    plan = next(carpeta.glob(f"projects/*/{OBRA}"), None)
    if plan is None:
        return cerrar(motivo_del_fallo("\n".join(salidas)))
    a_tiempo = pedir([*orden, "--ampliar", "--carpeta", str(plan.parent), encargo.peticion])
    (carpeta / "salida.txt").write_text("\n".join(salidas), encoding="utf-8")
    if not a_tiempo:
        return sin, f"la ampliación tardó más de {LIMITE_OBRA_S // 60} minutos"
    return _juzgar_si_hay_obra(encargo, carpeta, freecadcmd, material, "\n".join(salidas),
                               laminar)


def correr(encargo: Encargo, carpeta: Path, orden: list[str], freecadcmd: str,
           env: dict, material: dict | None = None,
           laminar=None, base: Encargo | None = None,
           partir_de: Path | None = None) -> tuple[list[Resultado], str | None]:
    """Pide la pieza como la pediría una persona y la juzga. Devuelve los
    resultados y, si no llegó a construirse, el porqué. `base` y
    `partir_de`, solo para un encargo que amplía otro."""
    marcar_carpeta(carpeta, encargo.nombre)
    if encargo.amplia:
        return _correr_ampliacion(encargo, carpeta, orden, freecadcmd, env, material, laminar,
                                  base, partir_de)
    limite = LIMITE_OBRA_S if encargo.obra else LIMITE_S
    try:
        proceso = subprocess.run(
            [*orden, encargo.peticion], input="sí\n", capture_output=True, text=True,
            timeout=limite, env={**env, "INTELLIPRINT_WORKSPACE": str(carpeta)})
    except subprocess.TimeoutExpired as e:
        # Banco `1106-1554` (2026-11-06): esto salía de aquí y la corrida
        # entera murió en el primer encargo. Se pierde el encargo, no el banco.
        texto = _texto(e.output) + "\n--- stderr ---\n" + _texto(e.stderr)
        (carpeta / "salida.txt").write_text(texto, encoding="utf-8")
        sin = [Resultado(estado="no_cumple", detalle="no hay pieza") for _ in encargo.oraculo]
        return sin, f"tardó más de {limite // 60} minutos"
    (carpeta / "salida.txt").write_text(proceso.stdout + "\n--- stderr ---\n" + proceso.stderr,
                                        encoding="utf-8")
    if encargo.obra:
        return _juzgar_si_hay_obra(encargo, carpeta, freecadcmd, material,
                                   proceso.stdout + "\n" + proceso.stderr, laminar)
    step = next(carpeta.glob("projects/*/parts/*/*.step"), None)
    # Que exista el STEP no basta: queda el de un intento fallido. En la
    # primera corrida (2026-11-03) el banco midió los restos de dos piezas
    # que no llegaron a construirse y les dio puntos.
    if not construida(carpeta, proceso.returncode, proceso.stdout) or step is None:
        sin = [Resultado(estado="no_cumple", detalle="no hay pieza") for _ in encargo.oraculo]
        return sin, motivo_del_fallo(proceso.stdout + "\n" + proceso.stderr)
    return juzgar_pieza(encargo, carpeta, freecadcmd, material, laminar), None


def _juzgar_si_hay_obra(encargo: Encargo, carpeta: Path, freecadcmd: str,
                        material: dict | None, salida: str,
                        laminar=None) -> tuple[list[Resultado], str | None]:
    """Una obra se juzga con lo que tenga construido: las piezas que falten
    no cumplen, con su nombre. Sin desglose no hay nada que juzgar."""
    from orchestrator.obra import OBRA
    if next(Path(carpeta).glob(f"projects/*/{OBRA}"), None) is None:
        sin = [Resultado(estado="no_cumple", detalle="no hay obra") for _ in encargo.oraculo]
        return sin, motivo_del_fallo(salida)
    return juzgar_obra(encargo, carpeta, freecadcmd, material, laminar=laminar), None


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


def laminado_del_juez(encargo: Encargo, step: Path, del_diseno: Path, carpeta: Path,
                      laminar) -> Path | None:
    """El laminado con el que se juzga «sin soportes». El diseño ya no lamina
    (2026-11-09: no se sabe en qué impresora se imprimirá), así que lo hace
    el juez, y solo si se pide «sin soportes»: lo sigue diciendo PrusaSlicer,
    no el propio sistema. Las corridas viejas traen el del diseño: se usa."""
    from orchestrator.slicing import LaminadoFallido

    if del_diseno.is_file():
        return del_diseno
    if laminar is None or not any(isinstance(a, SinSoportes) for a in encargo.oraculo):
        return None
    destino = Path(carpeta) / "juez"
    destino.mkdir(parents=True, exist_ok=True)
    try:
        informe = laminar(step.with_suffix(".stl"), destino / f"{step.stem}.gcode")
    except LaminadoFallido:
        return None
    salida = destino / f"{step.stem}.json"
    salida.write_text(json.dumps(informe.model_dump()), encoding="utf-8")
    return salida


def juzgar_pieza(encargo: Encargo, carpeta: Path, freecadcmd: str,
                 material: dict | None = None, laminar=None) -> list[Resultado]:
    step = next(carpeta.glob("projects/*/parts/*/*.step"))
    laminado = laminado_del_juez(encargo, step, step.parent.parent.parent / "fabrication"
                                 / "slicing_report.json", carpeta, laminar)
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
        if r < a.grados() - 1e-6:
            continue
        if c in faltan:
            faltan.remove(c)
        elif "cualquiera" in faltan:
            faltan.remove("cualquiera")
    if faltan:
        return Resultado(estado="no_cumple", detalle=(
            f"falta un giro {' y uno '.join(faltan)} de {a.grados():g}°; hay: {texto}"))
    return Resultado(estado="cumple", detalle=f"articulaciones: {texto}")


def _sondeado(h: Hechos, sondas: list) -> Resultado:
    return _junta([(s.tipo, h.sondas.get(s.clave())
                    or Resultado(estado="sin_medir", detalle="sin medir")) for s in sondas],
                  "cabe y entra")


def juzgar_obra(encargo: Encargo, carpeta: Path, freecadcmd: str,
                material: dict | None = None, hechos_de=None,
                laminar=None) -> list[Resultado]:
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
                if not isinstance(a, (Componente, Encaje, ConjuntoLibre, Articulaciones,
                                      SeOrienta, Tornillos, Alcance, Carga, Conserva,
                                      Reduccion))]
    # Solo se sondea lo que el oráculo pregunta: cada sonda es FreeCAD.
    pedidos = {a.ficha for a in encargo.oraculo if isinstance(a, Componente)}
    encaje = any(isinstance(a, Encaje) for a in encargo.oraculo)
    medidas: dict[str, tuple] = {}
    for p in piezas.values():
        rasgos = json.loads((p.step.parent / "rasgos.json").read_text(encoding="utf-8"))
        propias = [(r, sondas_del_rasgo(r)) for r in p.propios if r["ficha"] in pedidos]
        encajes = [(r, sondas_del_rasgo(r, [fichas])) for r in rasgos if encaje
                   and r.get("tipo") == "componente" and str(r.get("ficha")).startswith("obra-")]
        laminado = laminado_del_juez(encargo, p.step, p.step.parent.parent.parent
                                     / "fabrication" / "slicing_report.json", carpeta, laminar)
        medir = [*de_pieza, *(s for _, ss in propias + encajes for s in ss)]
        medidas[p.id] = (hechos_de(p.step, freecadcmd, laminado, medir, material),
                         propias, encajes)

    conjuntos = [n for n in ob.nodos if n.tipo == "conjunto"]
    verificaciones = [json.loads(f.read_text(encoding="utf-8")) for n in conjuntos
                      if (f := proyecto / O.NODOS / n.id / VERIFICACION).is_file()]
    estudios: dict[str, dict] = {}   # cada conjunto se estudia una vez
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
        elif isinstance(a, Tornillos):
            salida.append(_tornillos(a, proyecto, piezas))
        elif isinstance(a, Conserva):
            salida.append(_conserva(a, proyecto, piezas))
        elif isinstance(a, Reduccion):
            salida.append(_reduccion(a, proyecto, piezas))
        elif isinstance(a, (Alcance, Carga)):
            salida.append(_del_estudio(a, proyecto, [n.id for n in conjuntos], freecadcmd,
                                       estudios))
        elif isinstance(a, SeOrienta):
            pieza, r = _mide_si_orienta(a, proyecto, freecadcmd, material)
            salida.append(r if pieza is None else Resultado(
                estado=r.estado, detalle=f"«{piezas[pieza].nombre}»: {r.detalle}"))
        else:
            salida.append(_junta([(piezas[i].nombre, juzgar(a, h))
                                  for i, (h, _, _) in medidas.items()],
                                 f"en las {len(medidas)} piezas"))
    return salida


def _del_estudio(a: "Alcance | Carga", proyecto: Path, conjuntos: list[str],
                 freecadcmd: str, estudios: dict[str, dict]) -> Resultado:
    """Lo que el estudio de movimientos (F7.10 (estudio)) dice del alcance o
    de la carga. Se estudia aquí, con las piezas construidas, y no se lee el
    `estudio.json` de la corrida: así rejuzgar mide con el código de hoy."""
    from orchestrator import estudio

    if not conjuntos:
        return Resultado(estado="no_cumple", detalle="el backlog no tiene conjunto")
    for c in conjuntos:
        if c not in estudios:
            try:
                estudios[c] = estudio.estudio_entero(proyecto, c, freecadcmd)
            except (OSError, StopIteration, ValueError, KeyError) as error:
                return Resultado(estado="sin_medir",
                                 detalle=f"no se pudo estudiar el conjunto: {error!r}")
    hechos = [estudios[c] for c in conjuntos]
    if not any(e["servos"] for e in hechos):
        return Resultado(estado="no_cumple", detalle="ninguna pieza gira: no hay brazo que medir")
    if isinstance(a, Alcance):
        mejor = max(hechos, key=lambda e: e["alcance"]["del_hombro_mm"])["alcance"]
        llega, h = mejor["del_hombro_mm"], mejor["hombro"]
        desde = (f"del eje de «{h['nombre']}», "
                 + ("el primer giro que la levanta" if h["levanta"]
                    else "el primer giro: ninguno la levanta")) if h else "sin giros hasta la punta"
        if llega >= a.minimo_mm:
            return Resultado(estado="cumple", valor=llega, detalle=(
                f"la punta llega a {llega:.1f} mm {desde}"))
        return Resultado(estado="no_cumple", valor=llega, detalle=(
            f"la punta llega a {llega:.1f} mm y se piden {a.minimo_mm:g}, medido {desde}"))
    # Lo que no se pudo medir no se da por bueno: ni un giro que carga peso
    # sin que se sepa el par de lo que lo mueve, ni el material sin FreeCAD.
    for e in hechos:
        sin_par = [s["nombre"] for s in e["servos"]
                   if "par_bloqueo_Nm" not in s and s["par_max_Nm"] > 1e-9]
        if sin_par:
            return Resultado(estado="sin_medir", detalle=(
                "no se sabe el par de lo que mueve «" + "», «".join(sin_par) + "»"))
        sin_material = [f"«{m['nombre']}»: {m['detalle']}" for m in e.get("material", [])
                        if str(m["detalle"]).startswith("no corrió")]
        if sin_material or "material" not in e:
            return Resultado(estado="sin_medir", detalle=(
                "no se midió lo que aguanta el material: "
                + ("; ".join(sin_material) or "sin FreeCAD")))
    peor = min(hechos, key=lambda e: math.inf if e["carga_max"]["g"] is None
               else e["carga_max"]["g"])
    g, limita, donde = peor["carga_max"]["g"], peor["carga_max"]["limita"], peor["carga"]["donde"]
    if g is None:
        return Resultado(estado="cumple", detalle=f"nada limita la carga {donde}")
    levanta = f"{round(g, 1):g} g"
    if g >= a.minimo_g:
        return Resultado(estado="cumple", valor=g,
                         detalle=f"levanta {levanta} {donde}; lo limita el {limita}")
    return Resultado(estado="no_cumple", valor=g, detalle=(
        f"levanta {levanta} y se piden {a.minimo_g:g}, {donde}; lo limita el {limita}"))


def _conserva(a: Conserva, proyecto: Path, piezas: dict) -> Resultado:
    """Cuántas piezas de antes de ampliar siguen byte a byte como estaban."""
    from orchestrator import ampliar
    from orchestrator import obra as O

    hechas = ampliar.hechas(proyecto)
    if not hechas:
        return Resultado(estado="no_cumple", detalle=(
            "el invento no se amplió: no hay piezas de antes que conservar"))
    # La primera: lo que había antes de añadirle nada.
    antes = hechas[0]["antes"]
    iguales = [i for i, h in antes.items()
               if i in piezas and ampliar.huella(piezas[i].step) == h]
    # Por el nombre del plan: una pieza que se está corrigiendo no está
    # construida y no sale en `piezas`.
    nombres = {n.id: n.nombre for n in O.cargar_obra(proyecto).nodos}
    rehechas = [nombres.get(i, i) for i in antes if i not in iguales]
    detalle = f"{len(iguales)} de {len(antes)} piezas que ya había siguen idénticas"
    if rehechas:
        detalle += "; cambiaron «" + "», «".join(rehechas) + "»"
    if len(iguales) >= a.minimo:
        return Resultado(estado="cumple", valor=len(iguales), detalle=detalle)
    return Resultado(estado="no_cumple", valor=len(iguales),
                     detalle=f"{detalle}, y se piden {a.minimo}")


def _reduccion(a: Reduccion, proyecto: Path, piezas: dict) -> Resultado:
    """La relación de cada correa del plan, contada en las piezas."""
    from orchestrator import transmision

    try:
        medidas = transmision.medidas(proyecto)
    except (OSError, ValueError, KeyError) as error:
        return Resultado(estado="sin_medir", detalle=f"no se pudo medir la correa: {error!r}")
    if not medidas:
        return Resultado(estado="no_cumple",
                         detalle="el plan no mueve ningún giro por una correa")
    peor = None
    for u, m in medidas:
        gira = piezas[u.gira].nombre if u.gira in piezas else u.gira
        defectos = m["sobre"] + m["gira"]
        if m["hechos"] is None:
            r = Resultado(estado="no_cumple", detalle=(
                f"«{gira}»: " + (defectos[0] if defectos else "no lleva una polea en su eje")))
        elif abs(m["hechos"] / m["z1"] - a.relacion) > 1e-6:
            r = Resultado(estado="no_cumple", valor=m["hechos"] / m["z1"], detalle=(
                f"«{gira}» lleva una polea de {m['hechos']} dientes y la del motor tiene "
                f"{m['z1']}: {m['hechos'] / m['z1']:g}:1, y se pide {a.relacion:g}:1"))
        elif defectos or m["correa"] is None:
            r = Resultado(estado="no_cumple", valor=a.relacion, detalle=(
                f"«{gira}»: " + (defectos[0] if defectos else
                                 "no se pudo medir la distancia entre los dos ejes")))
        else:
            r = Resultado(estado="cumple", valor=a.relacion, detalle=(
                f"«{gira}» lleva una polea de {m['hechos']} dientes y la del motor tiene "
                f"{m['z1']}: {a.relacion:g}:1, con los ejes a {m['entre_ejes_mm']:.1f} mm, que "
                f"es una correa de {m['correa']['dientes']} dientes"))
            return r
        peor = peor or r
    return peor


def _tornillos(a: Tornillos, proyecto: Path, piezas: dict) -> Resultado:
    """Cuántos de los tornillos que sujetan `a.sujetan` hay y agarran."""
    from orchestrator.tornilleria import tornillos

    suyos = [t for t in tornillos(proyecto)
             if t.componente == a.sujetan and t.metrica == a.metrica]
    flojos = [t for t in suyos if t.no_rosca()]
    agarran = len(suyos) - len(flojos)
    que = f"tornillos {a.metrica} que sujetan los {a.sujetan}"
    if agarran == a.cuantos:
        return Resultado(estado="cumple", detalle=f"los {a.cuantos} {que} están y agarran")
    detalle = f"de los {a.cuantos} {que} agarran {agarran} de {a.cuantos}"
    if flojos:
        donde = sorted({piezas[t.lo_monta].nombre for t in flojos})
        detalle += (f"; {len(flojos)} de «{'», «'.join(donde)}» "
                    f"{'va' if len(flojos) == 1 else 'van'} en un agujero de "
                    f"Ø{max(t.agarra_mm for t in flojos):g}, más ancho que el tornillo")
    if len(suyos) < a.cuantos:
        detalle += f"; {a.cuantos - len(suyos)} no {'tiene' if a.cuantos - len(suyos) == 1 else 'tienen'} agujero"
    return Resultado(estado="no_cumple", detalle=detalle)


def la_que_gira(proyecto: Path, cual: str,
                primera: bool = False) -> tuple[str, list[float]] | None:
    """(pieza, eje en su marco) de la pieza del backlog que gira sobre un
    eje «vertical» u «horizontal» en el mundo, en reposo; la última si hay
    varias, que es la que lleva la carga. None si ninguna.

    `primera`: la primera, de la base a la punta. Con una pinza encima
    (F9.10 (ampliar)) la última es el dedo, y la cámara va en la plataforma."""
    from orchestrator.conjunto import _mv, _tr, articulaciones_de, leer_piezas, poses

    piezas = leer_piezas(Path(proyecto), solo_construidas=True)
    arts = {a.pieza: a for a in articulaciones_de(Path(proyecto), piezas)}
    reposo = poses(piezas, arts, {})
    hallada = None
    for a in arts.values():
        eje = _mv(reposo[a.padre][0], a.eje)
        z = abs(eje[2]) / math.sqrt(sum(x * x for x in eje))
        if ("vertical" if z > 0.99 else "horizontal" if z < 0.01 else "") == cual:
            hallada = (a.pieza, [float(x) for x in _mv(_tr(reposo[a.pieza][0]), eje)])
            if primera:
                break
    return hallada


def _mide_si_orienta(a: "SeOrienta", proyecto: Path, freecadcmd: str,
                     material: dict | None) -> tuple[str | None, "Resultado"]:
    """(pieza que gira sobre el eje que pide `a`, lo que mide en ella)."""
    from orchestrator.conjunto import leer_piezas
    cual = la_que_gira(proyecto, a.eje, primera=a.giro == "primero")
    if cual is None:
        return None, Resultado(estado="no_cumple", detalle=(
            f"ninguna pieza gira sobre un eje {a.eje}: no hay qué orientar"))
    pieza, eje = cual
    step = leer_piezas(Path(proyecto), solo_construidas=True)[pieza].step
    [r] = medir_sondas(step, [CaraQueSeOrienta(
        tipo="cara_que_se_orienta", eje=eje, cabe_mm=a.cabe_mm,
        tolerancia_grados=a.tolerancia_grados)], freecadcmd, material or {})
    return pieza, r


def la_que_no_orienta(encargo: Encargo, proyecto: Path, freecadcmd: str,
                      material: dict | None = None) -> tuple[str | None, str]:
    """(pieza, qué decirle a su ingeniero) si el encargo pide que algo se
    oriente y la pieza construida no lo hace; (None, "") si no hay nada que
    decir. Es lo que le diría la persona al verla: no inclina nada."""
    for a in encargo.oraculo:
        if not isinstance(a, SeOrienta):
            continue
        pieza, r = _mide_si_orienta(a, proyecto, freecadcmd, material)
        if pieza is not None and r.estado == "no_cumple":
            return pieza, (
                f"{NO_ORIENTA}, y como está no lo orienta: "
                f"{r.detalle}. Lo que lleva mide {a.cabe_mm[0]:g} × {a.cabe_mm[1]:g} mm y "
                "tiene que caber entero en una cara plana que mire de lado respecto al eje "
                "sobre el que gira (su normal, perpendicular al eje): una repisa o una "
                "escuadra que sale del acople, no un disco centrado en el eje. Cuenta la "
                "parte plana de la cara, sin los redondeos del borde: hazla 1 mm más grande "
                "de cada lado. Los taladros de dentro no quitan sitio; una ceja o un escalón "
                "sí, porque parten la cara.")
    return None, ""


def las_que_no_sujetan(encargo: Encargo, proyecto: Path) -> dict[str, str]:
    """{pieza: lo que le falta} de las piezas del backlog que no llevan los
    tornillos que prevé su plan, en orden; vacío si a ninguna le falta nada o
    el encargo no lo pide (F9.6 (previsto)).

    Todas, no solo la primera. Hasta F9.9 (revalidar) bastaba la primera:
    corregirla rehacía de cero las que iban encima, que contaban sus
    tornillos al dibujarse. Ahora las de encima se quedan si siguen valiendo,
    y cada una tiene que corregir lo suyo."""
    if not any(isinstance(a, Tornillos) for a in encargo.oraculo):
        return {}
    from orchestrator import obra
    from orchestrator.medida import uniones_sin_hacer
    arbol = obra.cargar_obra(Path(proyecto))
    salida = {}
    for i in arbol.orden():
        faltan = uniones_sin_hacer(proyecto, i) if arbol.nodo(i).tipo == "pieza" else []
        if faltan:
            salida[i] = "\n".join(faltan)
    return salida


NO_ORIENTA = "Esta pieza gira para orientar lo que lleva"
"""Cómo empieza la corrección de `la_que_no_orienta`: con ella se sabe, en
`cambios.md`, que la pieza ya se rehízo una vez por esto."""


def rejuzgar(encargos: list[Encargo], corrida: Path, freecadcmd: str,
             material: dict | None = None, laminar=None) -> tuple[dict, dict]:
    """Vuelve a juzgar las piezas de una corrida ya hecha, sin pedirlas otra
    vez: cambiar el juez no debería costar 46 minutos de modelo. Una pieza
    cuenta como construida si `intelliprint new` dijo «Listo»; que exista el
    STEP no basta (puede ser el de un intento fallido)."""
    resultados, fallos = {}, {}
    for i, e in enumerate(encargos, 1):
        carpeta = carpeta_del_encargo(Path(corrida), i, e.nombre)
        salida = carpeta / "salida.txt"
        texto = salida.read_text(encoding="utf-8", errors="ignore") if salida.exists() else ""
        if e.obra:
            resultados[e.nombre], fallo = _juzgar_si_hay_obra(e, carpeta, freecadcmd, material,
                                                              texto, laminar)
            if fallo:
                fallos[e.nombre] = fallo
            continue
        if (not texto or not construida(carpeta, None, texto)
                or next(carpeta.glob("projects/*/parts/*/*.step"), None) is None):
            resultados[e.nombre] = [Resultado(estado="no_cumple", detalle="no hay pieza")
                                    for _ in e.oraculo]
            fallos[e.nombre] = "no se construyó en esa corrida"
            continue
        resultados[e.nombre] = juzgar_pieza(e, carpeta, freecadcmd, material, laminar)
    return resultados, fallos


ENCARGO = "encargo.txt"


def marcar_carpeta(carpeta: Path, nombre: str) -> None:
    """Deja escrito de qué encargo es la carpeta de una corrida."""
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    (Path(carpeta) / ENCARGO).write_text(nombre, encoding="utf-8")


def carpeta_del_encargo(corrida: Path, puesto: int, nombre: str) -> Path:
    """La carpeta del encargo `nombre` en una corrida. Van numeradas por el
    puesto en la lista con la que se lanzó: la 1110-0313 se lanzó solo con
    los dos backlogs y su `01` es el pan-tilt, el encargo 11. Rejuzgarla o
    reanudarla con otra lista leía la carpeta de otro encargo. Con la marca
    se busca por nombre; las corridas de antes no la tienen y se siguen
    leyendo por el puesto."""
    corrida = Path(corrida)
    marcas = {m.read_text(encoding="utf-8").strip(): m.parent for m in corrida.glob(f"*/{ENCARGO}")}
    if nombre in marcas:
        return marcas[nombre]
    por_puesto = corrida / f"{puesto:02d}"
    if por_puesto in marcas.values():
        return corrida / f"sin-{nombre}"   # esa carpeta es de otro encargo
    return por_puesto


def _lo_medido(proyecto: Path, nodo: str) -> str:
    """Lo que no cumple la pieza construida de `nodo`, como quedó en su informe."""
    from orchestrator import obra
    informe = Path(proyecto) / obra.NODOS / nodo / "pieza_report.json"
    if not informe.is_file():
        return ""
    return (json.loads(informe.read_text(encoding="utf-8")).get("motivo") or "").strip()


def correcciones_del_conjunto(proyecto: Path) -> dict[str, str]:
    """Lo que la verificación del primer conjunto que choca le pide a cada
    pieza que lo causa (F7.7 (culpable)), en el orden de la obra."""
    from orchestrator import obra
    from orchestrator.conjunto import VERIFICACION
    proyecto = Path(proyecto)
    for i, estado in obra.estados(proyecto).items():
        if estado == "con choques":
            v = json.loads((proyecto / obra.NODOS / i / VERIFICACION).read_text(encoding="utf-8"))
            return v.get("correcciones") or {}
    return {}


def la_que_no_deja_sitio(proyecto: Path, nodo: str) -> tuple[str, str] | None:
    """Si `nodo`, que no salió bien, va atornillado a una pieza hecha que no
    le dejó sitio: (esa pieza, lo que se le midió). None si no.

    El soporte de la pinza del banco 1112-1359 salió encima del servo de
    inclinación porque ahí daban los agujeros de la plataforma. Corregirlo a
    él no lo saca de ahí."""
    from orchestrator import obra
    from orchestrator.medida import sin_sitio_para_lo_nuevo
    from orchestrator.schemas.obra import Fija
    proyecto = Path(proyecto)
    arbol = obra.cargar_obra(proyecto)
    orden = arbol.orden()
    fuera = {nodo, *arbol.dependientes(nodo)}
    for u in arbol.uniones_de(nodo):
        if not isinstance(u, Fija):
            continue
        abajo = u.agarra if u.cabeza == nodo else u.cabeza
        if abajo not in orden or orden.index(abajo) > orden.index(nodo):
            continue   # el exterior, o una que se diseña después
        falta = sin_sitio_para_lo_nuevo(proyecto, abajo, como_si_faltara=fuera)
        if falta:
            return abajo, "\n".join(falta)
    return None


def _corregir_la_que_no_deja_sitio(proyecto: Path, nodo: str, abajo: str, falta: str) -> None:
    """Corrige `abajo` con lo medido y manda hacer de nuevo `nodo` y lo que
    lleva encima que tampoco salió: se diseñaron contra unos agujeros que
    van a cambiar de cara, y retocarlos sería partir de una pieza que no
    puede valer. Lo que sí salió bien se queda, por revalidar."""
    from orchestrator import obra
    arbol = obra.cargar_obra(proyecto)
    estados = obra.estados(proyecto)

    def salio_bien(i):
        informe = Path(proyecto) / obra.NODOS / i / "pieza_report.json"
        return estados[i] == "lista" and informe.is_file() and bool(
            json.loads(informe.read_text(encoding="utf-8")).get("resuelto"))

    a_rehacer = [i for i in (nodo, *arbol.dependientes(nodo))
                 if arbol.nodo(i).tipo == "pieza" and not salio_bien(i)]
    obra.corregir(proyecto, abajo, falta)
    motivo = (f"«{arbol.nodo(abajo).nombre}», a la que se atornilla esta pieza, se ha "
              "corregido: sus agujeros para esta daban a un sitio ocupado y ahora están en "
              "otra cara. Esta pieza se hace de nuevo contra ella, donde ahora hay sitio.")
    # De arriba abajo: rehacer una deja por revalidar lo construido encima,
    # y eso de encima es justo lo que también se rehace.
    for i in reversed(a_rehacer):
        obra.rehacer(proyecto, i, motivo if i == nodo else "")


def nodo_a_rehacer(proyecto: Path) -> str | None:
    """La primera pieza, en orden, que no salió bien: sin construir, o dada
    por lista por el banco con defectos. Si todas salieron y el conjunto
    choca, la primera que lo causa: hasta el 2026-11-10 el banco se paraba
    ahí porque «un choque no dice qué pieza lo causa», y el pan-tilt 1110-0313
    se quedó con sus tres piezas bien y sin moverse entero."""
    from orchestrator import obra
    proyecto = Path(proyecto)
    arbol = obra.cargar_obra(proyecto)
    for i, estado in obra.estados(proyecto).items():
        if estado in ("verificado", "bloqueado"):
            continue
        if arbol.nodo(i).tipo == "conjunto":
            return next(iter(correcciones_del_conjunto(proyecto)), None)
        informe = proyecto / obra.NODOS / i / "pieza_report.json"
        if estado == "lista" and informe.is_file() and json.loads(
                informe.read_text(encoding="utf-8")).get("resuelto"):
            continue
        return i
    return None


def reanudar(encargos: list[Encargo], corrida: Path, orden: list[str], freecadcmd: str,
             env: dict, material: dict | None = None, laminar=None) -> tuple[dict, dict]:
    """Sigue los backlogs de una corrida desde la pieza que falló, y juzga
    otra vez. Relanzar el backlog entero tras cada arreglo (2026-11-09/10)
    costaba hora y media por vuelta para volver a la misma pieza, y cada
    vuelta solo enseñaba un fallo. Lo hecho se queda; la pieza que falló se
    archiva (no se borra) y lo construido contra ella se revalida cuando la
    nueva está lista (F9.9 (revalidar)), en la misma orden."""
    from orchestrator import obra
    from orchestrator.build import carpeta_libre
    from orchestrator.pieza import CAMBIOS
    for i, e in enumerate(encargos, 1):
        carpeta = carpeta_del_encargo(Path(corrida), i, e.nombre)
        hecho = next(carpeta.glob(f"projects/*/{obra.OBRA}"), None) if e.obra else None
        nodo = nodo_a_rehacer(hecho.parent) if hecho is not None else None
        # F9.9 (revalidar): si la orden se cortó con una pieza por revalidar
        # no hay nada que corregir ni que archivar; basta con seguirla.
        estados = obra.estados(hecho.parent).values() if hecho is not None else ()
        solo_seguir = "por revalidar" in estados
        if solo_seguir:
            nodo = None
        # Lo mismo si las piezas salieron todas y la orden se cortó moviendo
        # el conjunto (el primer brazo, banco 1112-0318: FreeCAD pasó de los
        # 600 s): no hay pieza que rehacer ni choque que corregir, y reanudar
        # se lo saltaba. Moverlo no gasta modelo.
        elif nodo is None and "por verificar" in estados:
            solo_seguir = True
        de_concepto = ""
        if nodo is None and hecho is not None and not solo_seguir:
            # Todo construido y sin chocar, y aun así la pieza no sirve para
            # lo que se pidió (F9.14 (orienta)).
            nodo, de_concepto = la_que_no_orienta(e, hecho.parent, freecadcmd, material)
        sin_tornillos: dict[str, str] = {}
        if nodo is None and hecho is not None and not solo_seguir:
            sin_tornillos = las_que_no_sujetan(e, hecho.parent)
            nodo = next(iter(sin_tornillos), None)
        if nodo is None and not solo_seguir:
            continue
        proyecto = hecho.parent
        correcciones = correcciones_del_conjunto(proyecto)
        sin_sitio = None if solo_seguir else la_que_no_deja_sitio(proyecto, nodo)
        if solo_seguir:
            pass
        elif sin_sitio:
            _corregir_la_que_no_deja_sitio(proyecto, nodo, *sin_sitio)
        elif de_concepto:
            apuntado = proyecto / obra.NODOS / nodo / CAMBIOS
            ya_rehecha = apuntado.is_file() and NO_ORIENTA in apuntado.read_text(encoding="utf-8")
            if ya_rehecha and obra.programa_construido(proyecto, nodo):
                # El concepto ya se rehízo por esto y lo que falla es el
                # dibujo: en la 1111-1342 el ingeniero pidió una placa de
                # 32 × 22 y el diseñador le talló una ceja que la dejó en
                # 28 × 18. Rehacerla otra vez tiraría un concepto bueno.
                obra.corregir(proyecto, nodo, de_concepto)
            else:
                # No se retoca la que hay: un disco en el eje no se arregla
                # moviendo una cota. Se rehace desde su concepto, con lo
                # medido apuntado para el ingeniero.
                obra.rehacer(proyecto, nodo, de_concepto)
        elif sin_tornillos:
            # Les faltan agujeros: se corrige la que hay, que por lo demás
            # está bien (pasó todo lo otro), con lo que falta en cifras. En
            # orden, de abajo arriba: corregir una marca por revalidar las
            # de encima, y corregir después una de esas le quita la marca.
            for otro, falta in sin_tornillos.items():
                if obra.programa_construido(proyecto, otro):
                    obra.corregir(proyecto, otro, falta)
                else:
                    obra.rehacer(proyecto, otro, falta)
        elif nodo in correcciones and obra.programa_construido(proyecto, nodo):
            # Se corrige la pieza que hay, como la corrigió la persona en la
            # web el 9 de noviembre. Las que se diseñaron contra ella y
            # también chocan llevan su propia corrección: ya no se archivan
            # solo por ir encima (F9.9 (revalidar)), así que hay que
            # pedírsela, o seguirían chocando igual.
            obra.corregir(proyecto, nodo, correcciones[nodo])
            for otro in obra.cargar_obra(proyecto).dependientes(nodo):
                if otro not in correcciones:
                    continue
                if obra.programa_construido(proyecto, otro):
                    obra.corregir(proyecto, otro, correcciones[otro])
                else:
                    obra.rehacer(proyecto, otro, correcciones[otro])
        elif obra.programa_construido(proyecto, nodo) and _lo_medido(proyecto, nodo):
            # F9.5 (parcial): la pieza se construyó y no cumple. Se corrige la
            # que hay con lo que se le midió, que trae las cifras: rehacerla
            # pedía otro concepto y salía otra pieza, sin saber por qué falló.
            obra.corregir(proyecto, nodo, _lo_medido(proyecto, nodo))
        else:
            obra.rehacer(proyecto, nodo)
        salida = carpeta / "salida.txt"
        if salida.exists():
            salida.rename(carpeta_libre(carpeta / "salida-anterior.txt"))
        try:
            proceso = subprocess.run(
                [*orden, "--carpeta", str(proyecto), e.peticion], input="sí\n",
                capture_output=True, text=True, timeout=LIMITE_OBRA_S,
                env={**env, "INTELLIPRINT_WORKSPACE": str(carpeta)})
            texto = proceso.stdout + "\n--- stderr ---\n" + proceso.stderr
        except subprocess.TimeoutExpired as error:
            texto = (_texto(error.output) + "\n--- stderr ---\n" + _texto(error.stderr)
                     + f"\n(tardó más de {LIMITE_OBRA_S // 60} minutos)")
        salida.write_text(texto, encoding="utf-8")
    return rejuzgar(encargos, corrida, freecadcmd, material, laminar)
