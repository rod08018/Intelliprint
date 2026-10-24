"""Para qué es una pieza, y con eso cómo se lamina (F3.16 (usos)).

Aparte para que el esquema del mecanismo y el laminado compartan la misma
lista sin importarse el uno al otro."""

from typing import Literal, get_args

Uso = Literal["general", "estructural", "estetica", "prototipo"]
"""El diseñador elige uno; los números de cada uno están en
config/slicing/usos.yaml."""

USOS: tuple[str, ...] = get_args(Uso)
