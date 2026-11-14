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
    bbox_min: list[float] | None = None
    bbox_max: list[float] | None = None
    """Dónde queda la pieza en su propio marco. El tamaño no basta para
    ensamblar: una placa centrada en el origen y otra que empieza en él
    miden lo mismo."""
    solids: int
    fcstd_object: str | None = None
    """Nombre interno de la pieza final dentro del .FCStd."""
    rasgos: list[dict] = []
    """Los agujeros, tuercas, colisas y huecos con nombre que registró el kit
    (F5.18 (kit)): lo que la medida compara con los requisitos."""
    avisos: list[str] = []
    """Lo que el kit no pudo hacer sin romper la pieza, p. ej. aristas que
    no admitían el redondeo y quedaron vivas."""
    tramos: list[dict] = []
    """Si la pieza se partió para que quepa en la cama (F11.3 (tramos)): de
    cada tramo, su número, su STL (en `tramos/`), su volumen y su caja."""
    cortes: list[dict] = []
    """Los cortes de una pieza partida: eje, dónde, cuánto mide la lengüeta y
    qué tornillos cruzan labio y lengüeta, medido en los tramos."""
    defectos: list[str] = []
    """Requisitos que la pieza entregada NO cumple, medidos al construir
    (F6.7 (lazo)): se entrega la mejor que salió, no una que cumple."""
    untraced_mm: list[float] = []
    """Cotas de la petición literal que no aparecen en la receta tras los
    reintentos (F1.16 (trazabilidad)). Se muestran en el informe; no rompen la pieza."""

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
