"""La biblioteca de componentes comprados (F6.11 (biblioteca)).

Un componente es geometría con ficha y fuente, no números sueltos: el
soporte del HC-SR04 (2026-11-05) se diseñó con trece cifras de internet y
ninguna forma, y salió «resuelto» con un sensor que no entraba. La ficha
dice qué es sólido (`cuerpos`), qué hay que dejar libre (`despejar`: cable,
haz de sonido) y dónde se atornilla (`fijacion`).
"""

from pathlib import Path
from typing import Literal

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
