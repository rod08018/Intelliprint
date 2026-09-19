"""Reporte de laminado de una placa."""

from pydantic import BaseModel, model_validator


class SlicingReport(BaseModel):
    plate: int
    filament_mm: float
    grams: float
    time_s: int
    needs_supports: bool
    parts: list[str] = []

    @model_validator(mode="after")
    def _gramos_coherentes_con_filamento(self) -> "SlicingReport":
        if self.filament_mm > 0 and self.grams == 0:
            raise ValueError(
                "se gastó filamento pero el peso es 0 g: el perfil de "
                "PrusaSlicer no tiene densidad de material configurada. "
                "Aceptarlo dejaría a cero el coste y el resumen del Gate #2."
            )
        return self
