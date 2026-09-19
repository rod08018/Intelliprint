"""Resultado de construir una pieza en `freecadcmd`. Ver § 9.3."""

import json

from pydantic import BaseModel

from orchestrator.recipes.compose import RESULT_PREFIX


class BuildOutputError(ValueError):
    """`build.py` no dejó un resultado legible en stdout."""


class PartResult(BaseModel):
    part: str
    volume_mm3: float
    bbox_mm: list[float]
    solids: int
    fcstd_object: str | None = None
    """Nombre interno de la pieza final dentro del .FCStd."""
    untraced_mm: list[float] = []
    """Cotas de la petición literal que no aparecen en la receta tras los
    reintentos (F1.16). Se muestran en el informe; no rompen la pieza."""

    @classmethod
    def from_build_output(cls, part: str, stdout: str) -> "PartResult":
        for linea in stdout.splitlines():
            if linea.startswith(RESULT_PREFIX):
                datos = json.loads(linea[len(RESULT_PREFIX) :])
                return cls(**{**datos, "part": part})
        raise BuildOutputError(
            f"{part}: build.py no emitió línea de resultado. "
            "O falló antes de terminar, o no se compuso con compose_build_script."
        )
