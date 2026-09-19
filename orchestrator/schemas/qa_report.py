"""Informe de QA. Ver SISTEMA_MULTIAGENTE.md § 7.1."""

from typing import Literal

from pydantic import BaseModel


class Assertion(BaseModel):
    """Capa 1: derivada de una interfaz resuelta (§ 3.3), no de un LLM."""

    name: str
    interface: str
    expected: float
    tol: float
    measured: float | None
    """None = se buscó donde el contrato dice y NO había nada. Es FAIL,
    nunca "sin comprobar": eso sería aprobar por omisión (ADR-011)."""
    unit: Literal["mm", "count"] = "mm"
    """Mismos nombres que `AssertionSpec` de mech-toolkit a propósito: es
    ese objeto con la medición ya puesta, y viaja entre servicios como
    JSON. Dos vocabularios para lo mismo acabarían en un mapeo con bugs."""

    @property
    def ok(self) -> bool:
        if self.measured is None:
            return False
        return abs(self.measured - self.expected) <= self.tol


class DfmCheck(BaseModel):
    """Capa 2: chequeo determinista sobre el STL."""

    name: str
    passed: bool
    detail: str = ""


class Defect(BaseModel):
    """Capa 3: lo único que el LLM puede escribir."""

    description: str
    source: Literal["vision", "text", "human"] = "vision"


class QaReport(BaseModel):
    part: str
    assertions: list[Assertion] = []
    dfm_checks: list[DfmCheck] = []
    llm_defects: list[Defect] = []

    @property
    def verdict(self) -> Literal["PASS", "FAIL"]:
        # PASS ⟺ capa1 ∧ capa2 ∧ capa3.defectos == []
        #
        # El LLM solo escribe en `llm_defects`. No hay ninguna ruta por la
        # que pueda convertir un FAIL determinista en PASS: su peor
        # comportamiento posible es ser inútil, no ser permisivo (ADR-003).
        if (
            all(a.ok for a in self.assertions)
            and all(c.passed for c in self.dfm_checks)
            and not self.llm_defects
        ):
            return "PASS"
        return "FAIL"
