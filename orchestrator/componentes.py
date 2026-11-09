"""La biblioteca de componentes comprados (F6.11 (biblioteca)).

Un componente es geometría con ficha y fuente, no números sueltos: el
soporte del HC-SR04 (2026-11-05) se diseñó con trece cifras de internet y
ninguna forma, y salió «resuelto» con un sensor que no entraba. La ficha
dice qué es sólido (`cuerpos`), qué hay que dejar libre (`despejar`: cable,
haz de sonido) y dónde se atornilla (`fijacion`).
"""

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


class Cuerpo(BaseModel):
    """Una caja (`caja` = tamaño, `en` = esquina mínima) o un cilindro (`en` =
    centro de la base, creciendo en `eje`), en el marco del componente."""
    nombre: str
    caja: list[float] | None = None
    cilindro: Cilindro | None = None
    en: list[float]
    porque: str = ""
    gira_con: str = ""
    """Solo en `despejar`: la cara de una parte que puede girar (un aro del
    rodamiento). La pieza puede tocar las zonas de una sola de esas partes,
    la que va fija; cuál es depende del uso. Proyecto del 608ZZ (2026-11-08):
    el reborde apoyaba en los dos aros."""

    @model_validator(mode="after")
    def _una_forma(self):
        if (self.caja is None) == (self.cilindro is None):
            raise ValueError(f"«{self.nombre}» tiene que ser una caja o un cilindro")
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
    fuentes: list[Fuente] = Field(min_length=1)
    marco: str
    mira: Eje
    cuerpos: list[Cuerpo] = Field(min_length=1)
    despejar: list[Cuerpo] = []
    fijacion: list[Agujero] = []
    notas: str = ""


def ids() -> list[str]:
    return sorted(p.stem for p in BIBLIOTECA.glob("*.yaml"))


def cargar(id_: str) -> Ficha:
    ruta = BIBLIOTECA / f"{id_}.yaml"
    if not ruta.is_file():
        raise KeyError(f"no hay ficha de «{id_}»; hay: {', '.join(ids()) or 'ninguna'}")
    return Ficha(**yaml.safe_load(ruta.read_text(encoding="utf-8")))


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
        if p["tipo"] == "caja":
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
    if c.caja:
        return f"caja {' × '.join(_g(v) for v in c.caja)} desde ({', '.join(_g(v) for v in c.en)})"
    k = c.cilindro
    anillo = f" con agujero de Ø{_g(k.interior)}" if k.interior else ""
    return (f"cilindro Ø{_g(k.diametro)}{anillo} × {_g(k.alto)} hacia {k.eje} desde "
            f"({', '.join(_g(v) for v in c.en)})")


def resumen(ficha: Ficha) -> str:
    """Lo que el ingeniero y el diseñador leen de un componente: su tamaño,
    qué choca, qué hay que dejar libre y por qué, dónde se atornilla, y que
    nadie lo ha medido con calibre."""
    a, b = envolvente(ficha)
    fuentes = sorted({urlparse(f.url).hostname.removeprefix("www.") for f in ficha.fuentes})
    medido = "medido con calibre" if ficha.verificado else "sin verificar con calibre"
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
