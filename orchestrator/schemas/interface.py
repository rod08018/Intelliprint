"""Contrato de interfaces entre piezas. Ver SISTEMA_MULTIAGENTE.md § 3."""

from typing import Literal

from pydantic import BaseModel, model_validator

InterfaceType = Literal[
    "bearing_seat",
    "shaft",
    "bolt_pattern",
    "press_fit",
    "slide_fit",
    "snap_fit",
    "cable_pass",
]

Fit = Literal["press", "clearance", "slide"]


class Frame(BaseModel):
    origin: list[float]
    axis: list[float]


class Interface(BaseModel):
    id: str
    state: Literal["symbolic", "resolved"]
    type: InterfaceType
    between: list[str]
    fit: Fit
    hardware_class: str | None = None
    hardware: str | None = None
    nominal_mm: dict[str, float] | None = None
    frame: Frame | None = None

    @model_validator(mode="after")
    def _simbolica_sin_geometria(self) -> "Interface":
        if self.state == "symbolic":
            presentes = [
                campo
                for campo in ("frame", "nominal_mm")
                if getattr(self, campo) is not None
            ]
            if presentes:
                raise ValueError(
                    f"una interfaz simbólica no puede llevar geometría: {presentes}. "
                    "La geometría la resuelve la Fase 2 (ADR-001)."
                )
        else:
            faltantes = [
                campo
                for campo in ("frame", "nominal_mm", "hardware")
                if getattr(self, campo) is None
            ]
            if faltantes:
                raise ValueError(
                    f"una interfaz resuelta exige {faltantes}. "
                    "Sin ellos el Part Designer tendría que inventarlos (ADR-001)."
                )
        return self
