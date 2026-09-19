"""Construcción de una pieza y bucle de error de segundo nivel (F1.11).

Primer nivel (en `structured`): una receta inválida se rechaza por esquema
o por catálogo sin lanzar FreeCAD. Segundo nivel (aquí): una receta VÁLIDA
que FreeCAD rechaza al construir —un taladro que parte la pieza, un sólido
degenerado— devuelve el motivo al Part Designer para que la corrija.
"""

import re
import shutil
import subprocess
from pathlib import Path

from orchestrator.recipes.compose import compose_build_script
from orchestrator.schemas.part_result import BuildOutputError, PartResult
from orchestrator.schemas.recipe import GeneratorCatalog, Recipe

MAX_CONSTRUCCIONES = 3


class ConstruccionFallida(RuntimeError):
    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


def motivo_del_fallo(salida: str) -> str:
    """El motivo que le llega al agente.

    Si el fallo lo detectamos nosotros (F1.7), viene marcado y se extrae
    limpio. Si es un error de FreeCAD que no provocamos, se pasa el final
    del traceback en crudo: peor redactado, pero mejor que nada.
    """
    marcado = re.search(r"INTELLIPRINT_FALLO: (.+)", salida)
    if marcado:
        return marcado.group(1).strip()
    lineas = [linea for linea in salida.strip().splitlines() if linea.strip()]
    return "\n".join(lineas[-6:]) or "build.py terminó sin resultado y sin error"


def build_part(
    receta: Recipe, catalog: GeneratorCatalog, carpeta: Path, freecadcmd: str
) -> PartResult:
    carpeta.mkdir(parents=True, exist_ok=True)
    build = carpeta / "build.py"
    build.write_text(
        compose_build_script(receta, catalog, output_dir=carpeta), encoding="utf-8"
    )
    proceso = subprocess.run(
        [freecadcmd, str(build)], capture_output=True, text=True, timeout=180
    )
    # El intérprete embebido de FreeCAD ignora PYTHONDONTWRITEBYTECODE.
    shutil.rmtree(carpeta / "__pycache__", ignore_errors=True)
    try:
        return PartResult.from_build_output(receta.part, proceso.stdout)
    except BuildOutputError:
        raise ConstruccionFallida(motivo_del_fallo(proceso.stdout + "\n" + proceso.stderr))


def design_and_build(
    agent,
    brief: str,
    catalog: GeneratorCatalog,
    carpeta: Path,
    *,
    freecadcmd: str,
    part: str | None = None,
    max_construcciones: int = MAX_CONSTRUCCIONES,
) -> tuple[Recipe, PartResult]:
    """Diseña y construye, devolviendo al agente el motivo de cada fallo.

    `part` fija el nombre de la pieza: el modelo podría devolver otro en la
    receta, y los artefactos tienen que llamarse como la tarea.
    """
    rechazo: tuple[str, str] | None = None
    motivo = ""
    for _ in range(max_construcciones):
        receta = agent.design(brief, rechazo=rechazo)
        if part is not None:
            receta = receta.model_copy(update={"part": part})
        try:
            return receta, build_part(receta, catalog, Path(carpeta), freecadcmd)
        except ConstruccionFallida as error:
            motivo = error.motivo
            rechazo = (receta.model_dump_json(indent=2), motivo)
    raise ConstruccionFallida(
        f"{max_construcciones} construcciones fallidas. Último motivo: {motivo}"
    )
