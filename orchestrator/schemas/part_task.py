"""Tarea de diseño de una pieza. Ver SISTEMA_MULTIAGENTE.md § 4."""

from typing import Literal

from pydantic import BaseModel

PartState = Literal[
    "TODO",
    "DESIGNING",
    "DFM",
    "QA",
    "PASS",
    "FAIL",
    "BLOCKED_ON_HUMAN",
]
"""`BLOCKED_ON_HUMAN` es transversal: el planificador salta la pieza y
sigue con las demás (regla 7)."""

MAX_ITERATIONS = 3
"""Regla 2. Al agotarse, la regla 5 dice qué sigue: escalar y luego preguntar."""


class PartTask(BaseModel):
    part: str
    state: PartState = "TODO"
    iterations: int = 0
    depends_on: list[str] = []
    interfaces: list[str] = []

    @property
    def can_retry(self) -> bool:
        return self.iterations < MAX_ITERATIONS
