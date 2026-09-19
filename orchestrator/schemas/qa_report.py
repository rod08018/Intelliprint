"""Informe de QA. Ver SISTEMA_MULTIAGENTE.md § 7.1."""

from typing import Literal

from pydantic import BaseModel


class Assertion(BaseModel):
    """Capa 1: derivada de una interfaz resuelta (§ 3.3), no de un LLM."""

    name: str
    interface: str
    expected_mm: float
    tol_mm: float
    measured_mm: float

    @property
    def ok(self) -> bool:
        return abs(self.measured_mm - self.expected_mm) <= self.tol_mm


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
