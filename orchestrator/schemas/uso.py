"""Para qué es una pieza, y con eso cómo se lamina (F3.16 (usos)).

Lo declaraba el diseñador de mecanismos para cada pieza. Ese flujo se quitó
(F9.13 (limpieza)), pero los mecanismos que ya hay lo llevan en su
`mechanism.json` y la web los abre en PrusaSlicer con los ajustes de cada
uso. Una pieza o un backlog no lo declaran: van como «general»."""

from typing import Literal, get_args

Uso = Literal["general", "estructural", "estetica", "prototipo"]
"""Los números de cada uno están en config/slicing/usos.yaml."""

USOS: tuple[str, ...] = get_args(Uso)
