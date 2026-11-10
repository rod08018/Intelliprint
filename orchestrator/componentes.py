"""La biblioteca de componentes comprados (F6.11 (biblioteca)).

Un componente es geometría con ficha y fuente, no números sueltos: el
soporte del HC-SR04 (2026-11-05) se diseñó con trece cifras de internet y
ninguna forma, y salió «resuelto» con un sensor que no entraba. La ficha
dice qué es sólido (`cuerpos`), qué hay que dejar libre (`despejar`: cable,
haz de sonido) y dónde se atornilla (`fijacion`).
"""

import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, model_validator

from mech_toolkit.componentes import primitivas as _primitivas

BIBLIOTECA = Path(__file__).resolve().parents[1] / "library" / "components"

Eje = Literal["+x", "-x", "+y", "-y", "+z", "-z"]


class Fuente(BaseModel):
    url: str
    cita: str = Field(min_length=3)


class Cilindro(BaseModel):
    diametro: float = Field(gt=0)
    interior: float | None = Field(default=None, gt=0)
    """Un anillo (un rodamiento): por dentro pasa un eje, y tratarlo como
    macizo haría «chocar» cualquier eje que lo atraviese."""
    alto: float = Field(gt=0)
    eje: Eje

    @model_validator(mode="after")
    def _anillo(self):
        if self.interior is not None and self.interior >= self.diametro:
            raise ValueError("el diámetro interior tiene que ser menor que el exterior")
        return self


class Step(BaseModel):
    """La forma real de una pieza impresa (F7.1 (fichar)): su STEP construido
    y la envolvente en su propio marco, que el orquestador lee sin FreeCAD."""
    ruta: str
    min: list[float]
    max: list[float]


class Cuerpo(BaseModel):
    """Una caja (`caja` = tamaño, `en` = esquina mínima), un cilindro (`en` =
    centro de la base, creciendo en `eje`) o la forma de una pieza impresa
    (`step`, desplazada `en`), en el marco del componente."""
    nombre: str
    caja: list[float] | None = None
    cilindro: Cilindro | None = None
    step: Step | None = None
    en: list[float]
    porque: str = ""
    monta: str = ""
    """En la ficha de una pieza impresa: el id del componente comprado del
    que viene este cuerpo (el SG90 que la pieza lleva montado)."""
    gira_con: str = ""
    """Solo en `despejar`: la cara de una parte que puede girar (un aro del
    rodamiento). La pieza puede tocar las zonas de una sola de esas partes,
    la que va fija; cuál es depende del uso. Proyecto del 608ZZ (2026-11-08):
    el reborde apoyaba en los dos aros."""

    @model_validator(mode="after")
    def _una_forma(self):
        if [self.caja, self.cilindro, self.step].count(None) != 2:
            raise ValueError(f"«{self.nombre}» tiene que ser una caja, un cilindro o un step")
        if self.caja is not None and (len(self.caja) != 3 or min(self.caja) <= 0):
            raise ValueError(f"«{self.nombre}»: una caja son tres medidas positivas")
        if len(self.en) != 3:
            raise ValueError(f"«{self.nombre}»: `en` son tres coordenadas")
        return self


class Agujero(BaseModel):
    nombre: str
    diametro: float = Field(gt=0)
    en: list[float]
    eje: Eje
    # Lo que hace falta para contar y dibujar el tornillo de este agujero
    # (F7.8 (inventario)). Sin `tornillo`, la ficha no dice cuál va, y no se
    # cuenta: la lista del pan-tilt decía «M3, M4» y nada de los del SG90.
    tornillo: str = ""
    """La métrica («M2»)."""
    incluido: bool = False
    """Viene con el componente: se ve en el ensamble, pero no se compra aparte."""
    dentro_mm: float = 0.0
    """Cuánto del tornillo va dentro del componente desde `en`, en la
    dirección de `eje`: el grueso de la oreja de un servo, el fondo de la
    rosca de un motor."""
    tuerca: str = ""
    """Lo que hay que comprar para que el tornillo agarre en el componente:
    la tuerca en T del perfil."""
    a_lo_largo: Eje | None = None
    """El tornillo puede ir en cualquier punto en esa dirección: la ranura
    del perfil, donde la ficha solo marca uno."""


class Salida(BaseModel):
    """Lo que el componente mueve (el eje de un servo), para verificar un
    conjunto moviéndolo (F7.4 (conjunto)): la pieza que lo toca gira
    alrededor de la recta que pasa por `en` en la dirección `eje`."""
    nombre: str
    en: list[float]
    eje: Eje
    recorrido: tuple[float, float]
    """En grados, desde el centro del recorrido. De la hoja de datos."""
    largo: float = 0.0
    """Cuánto ocupa lo que se mueve a lo largo del eje, desde `en`: el ancho
    del aro de un rodamiento. Con solo el punto, la polea del banco apoyada
    en la cara de ARRIBA del 608ZZ quedaba a 7.35 mm de su cara de abajo y
    no giraba con él (1110-0313)."""
    porque: str = ""


class Ficha(BaseModel):
    id: str
    nombre: str
    alias: list[str] = []
    """Cómo lo llama la gente en una petición («HC-SR04», «NEMA 17»): así se
    sabe que la petición nombra un componente que ya tiene ficha."""
    accesorios: list[str] = []
    """Lo que va EN el componente y no en la pieza: la tuerca en T del perfil
    2020. No se busca ni se convierte en requisitos: en el proyecto del 608ZZ
    (2026-11-06) sus 9.5, 4.5 y 6 mm de una tienda acabaron de requisitos."""
    verificado: bool = False
    """Solo si alguien lo midió con calibre: una hoja de datos puede no
    coincidir con la unidad que tiene la persona."""
    origen: Literal["comprado", "impreso"] = "comprado"
    """«impreso»: una pieza que diseñó este sistema y se congeló para diseñar
    las siguientes contra ella (F7.1 (fichar))."""
    proyecto: str = ""
    """De qué proyecto sale una pieza impresa."""
    fuentes: list[Fuente] = Field(min_length=1)
    marco: str
    mira: Eje
    cuerpos: list[Cuerpo] = Field(min_length=1)
    despejar: list[Cuerpo] = []
    fijacion: list[Agujero] = []
    salidas: list[Salida] = []
    notas: str = ""


def bibliotecas() -> list[Path]:
    """La biblioteca de lo comprado y, con `INTELLIPRINT_FICHAS` (carpetas
    separadas por `os.pathsep`), las fichas de piezas impresas de una obra
    (F7.1 (fichar)): son de ese proyecto, no de `library/`."""
    extra = [Path(p) for p in os.environ.get("INTELLIPRINT_FICHAS", "").split(os.pathsep) if p]
    return [BIBLIOTECA, *extra]


def _ruta(id_: str, extra=()) -> Path | None:
    for carpeta in [*bibliotecas(), *map(Path, extra)]:
        if (carpeta / f"{id_}.yaml").is_file():
            return carpeta / f"{id_}.yaml"
    return None


def ids() -> list[str]:
    return sorted({p.stem for c in bibliotecas() for p in c.glob("*.yaml")})


def cargar(id_: str, extra=()) -> Ficha:
    """`extra`: más carpetas de fichas, para quien no corre dentro de la obra
    (la web, que no tiene `INTELLIPRINT_FICHAS`)."""
    ruta = _ruta(id_, extra)
    if ruta is None:
        raise KeyError(f"no hay ficha de «{id_}»; hay: {', '.join(ids()) or 'ninguna'}")
    ficha = Ficha(**yaml.safe_load(ruta.read_text(encoding="utf-8")))
    # La ruta del STEP va relativa a la ficha: la obra se puede mover o
    # montar en otra carpeta (el contenedor) y la ficha sigue valiendo.
    for c in ficha.cuerpos:
        if c.step and not Path(c.step.ruta).is_absolute():
            c.step.ruta = str((ruta.parent / c.step.ruta).resolve())
    return ficha


def primitivas(ficha: Ficha, en=(0, 0, 0), giros=(), de="cuerpos") -> list[dict]:
    return _primitivas(ficha, en, giros, de)


def _plano(texto: str) -> str:
    return re.sub(r"[\s\-_]+", "", texto.casefold())


def mencionados(texto: str) -> list[str]:
    """Los componentes de la biblioteca que nombra `texto`. Lo decide el
    código, no el modelo: si el HC-SR04 tiene ficha, nadie lo busca en una
    tienda (de ahí salieron el PCB de 43 y el Ø8, 2026-11-05)."""
    plano = _plano(texto)
    return [i for i in ids()
            if any(_plano(a) in plano for a in [i, *cargar(i).alias] if _plano(a))]


def de_la_ficha(texto: str) -> list[str]:
    """Los componentes de los que habla `texto`, por su nombre o por un
    accesorio suyo («tuerca en T de 2020» → perfil-2020). Lo que sale aquí
    tiene sus medidas en la ficha: no se busca ni da requisitos sueltos."""
    plano = _plano(texto)
    return [i for i in ids()
            if any(_plano(a) in plano
                   for a in [i, *cargar(i).alias, *cargar(i).accesorios] if _plano(a))]


def envolvente(ficha: Ficha, de="cuerpos") -> tuple[list[float], list[float]]:
    minimos, maximos = [], []
    for p in primitivas(ficha, de=de):
        if p["tipo"] in ("caja", "step"):
            minimos.append(p["min"])
            maximos.append(p["max"])
            continue
        r = p["diametro"] / 2
        fin = [b + e * p["alto"] for b, e in zip(p["base"], p["eje"])]
        minimos.append([min(b, f) - (0 if e else r) for b, f, e in zip(p["base"], fin, p["eje"])])
        maximos.append([max(b, f) + (0 if e else r) for b, f, e in zip(p["base"], fin, p["eje"])])
    return ([min(m[n] for m in minimos) for n in range(3)],
            [max(m[n] for m in maximos) for n in range(3)])


def _g(v) -> str:
    return f"{round(v, 3):g}"


def _forma(c: Cuerpo) -> str:
    if c.step:
        a, b = c.step.min, c.step.max
        return (f"la forma real de la pieza (STEP), envolvente "
                f"{' × '.join(_g(y - x) for x, y in zip(a, b))} de "
                f"({', '.join(_g(v + o) for v, o in zip(a, c.en))}) a "
                f"({', '.join(_g(v + o) for v, o in zip(b, c.en))})")
    if c.caja:
        return f"caja {' × '.join(_g(v) for v in c.caja)} desde ({', '.join(_g(v) for v in c.en)})"
    k = c.cilindro
    anillo = f" con agujero de Ø{_g(k.interior)}" if k.interior else ""
    return (f"cilindro Ø{_g(k.diametro)}{anillo} × {_g(k.alto)} hacia {k.eje} desde "
            f"({', '.join(_g(v) for v in c.en)})")


def fuente(url: str) -> str:
    """El sitio de una fuente, o la fuente tal cual si no es una URL (una
    pieza impresa cita su proyecto)."""
    return (urlparse(url).hostname or url).removeprefix("www.")


def resumen(ficha: Ficha) -> str:
    """Lo que el ingeniero y el diseñador leen de un componente: su tamaño,
    qué choca, qué hay que dejar libre y por qué, dónde se atornilla, y que
    nadie lo ha medido con calibre."""
    a, b = envolvente(ficha)
    fuentes = sorted({fuente(f.url) for f in ficha.fuentes})
    medido = "medido con calibre" if ficha.verificado else "sin verificar con calibre"
    if ficha.origen == "impreso":
        medido = f"pieza impresa en este proyecto, {medido}"
    lineas = [
        f"### `{ficha.id}`: {ficha.nombre} ({medido}; fuentes: {', '.join(fuentes)})",
        f"Marco de la ficha: {ficha.marco.strip()}",
        f"Mira hacia {ficha.mira}. Envolvente: "
        f"{' × '.join(_g(y - x) for x, y in zip(a, b))} mm (x de {_g(a[0])} a {_g(b[0])}, "
        f"y de {_g(a[1])} a {_g(b[1])}, z de {_g(a[2])} a {_g(b[2])}).",
        "Lo que choca:",
        *(f"- {c.nombre}: {_forma(c)}" + (f" ({c.porque})" if c.porque else "")
          for c in ficha.cuerpos)]
    libres = [c for c in ficha.despejar if not c.gira_con]
    if libres:
        lineas += ["Lo que hay que dejar libre:",
                   *(f"- {c.nombre}: {_forma(c)}" + (f" ({c.porque})" if c.porque else "")
                     for c in libres)]
    giran = [c for c in ficha.despejar if c.gira_con]
    if giran:
        partes = sorted({c.gira_con for c in giran})
        lineas += [f"Uno de estos gira: {', '.join(partes)}. La pieza apoya en uno solo, "
                   "el que va fijo, y deja libres las caras del otro:",
                   *(f"- {c.nombre}: {_forma(c)}" for c in giran)]
    if ficha.fijacion:
        lineas += ["Agujeros de fijación:",
                   *(f"- {h.nombre}: Ø{_g(h.diametro)} en ({', '.join(_g(v) for v in h.en)}), "
                     f"hacia {h.eje}" for h in ficha.fijacion)]
    if ficha.notas:
        lineas.append(f"Notas: {ficha.notas.strip()}")
    return "\n".join(lineas)
