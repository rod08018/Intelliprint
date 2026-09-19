"""Perfil de impresora + material.

`mech-toolkit` es quien posee las holguras (§ 9.2): son un dato de
calibración física, no una decisión de diseño.
"""

from pydantic import BaseModel


class PrinterProfile(BaseModel):
    id: str
    fits: dict[str, float]
    holes: dict[str, float] = {}
    assertion_tol_mm: float = 0.05
    """Cuánto puede desviarse la pieza construida de la cota exigida antes
    de considerarse un fallo. No es la holgura: es la precisión con la que
    el modelo tiene que acertar."""
    calibrated: bool = False

    def fit_mm(self, fit: str) -> float:
        """Holgura en diámetro para un tipo de ajuste."""
        clave = f"{fit}_mm"
        if clave not in self.fits:
            raise KeyError(
                f"el perfil {self.id!r} no define el ajuste {fit!r}. "
                f"Conocidos: {sorted(self.fits)}"
            )
        return self.fits[clave]

    def hole_mm(self, nombre: str) -> float:
        """Diámetro tabulado de un agujero (p. ej. `M3_through`).

        Falla si no está en la tabla en vez de calcularlo: un valor
        calculado a espaldas del perfil sería una cota que nadie ha
        verificado imprimiendo.
        """
        clave = f"{nombre}_mm"
        if clave not in self.holes:
            raise KeyError(
                f"el perfil {self.id!r} no tabula {nombre!r}. "
                f"Añádelo a config/printers/{self.id}.yaml. "
                f"Conocidos: {sorted(self.holes)}"
            )
        return self.holes[clave]
