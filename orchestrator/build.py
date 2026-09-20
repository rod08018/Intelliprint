"""Construcción de una pieza y bucle de error de segundo nivel (F1.11 (bucle)).

Primer nivel (en `structured`): una receta inválida se rechaza por esquema
o por catálogo sin lanzar FreeCAD. Segundo nivel (aquí): una receta VÁLIDA
que FreeCAD rechaza al construir —un taladro que parte la pieza, un sólido
degenerado— devuelve el motivo al Part Designer para que la corrija.
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from orchestrator.fcstd import mostrar_solo
from orchestrator.recipes.compose import compose_build_script
from orchestrator.schemas.part_result import BuildOutputError, PartResult
from orchestrator.schemas.recipe import GeneratorCatalog, Recipe
from orchestrator.traceability import untraced

MAX_CONSTRUCCIONES = 3


class ConstruccionFallida(RuntimeError):
    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class CajaNoCuadra(ConstruccionFallida):
    """La pieza está bien dibujada pero no ocupa la caja declarada. Eso suele
    ser de quien la declaró, no de quien la dibujó: sube sin gastar el resto
    de intentos del Part Designer."""


def motivo_del_fallo(salida: str) -> str:
    """El motivo que le llega al agente.

    Si el fallo lo detectamos nosotros (F1.7 (validez)), viene marcado y se extrae
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
        resultado = PartResult.from_build_output(receta.part, proceso.stdout)
    except BuildOutputError:
        raise ConstruccionFallida(motivo_del_fallo(proceso.stdout + "\n" + proceso.stderr))
    # Sin esto FreeCAD abre el .FCStd con todo oculto (ver orchestrator/fcstd.py).
    mostrar_solo(carpeta / f"{receta.part}.FCStd", resultado.fcstd_object)
    return resultado


def design_and_build(
    agent,
    brief: str,
    catalog: GeneratorCatalog,
    carpeta: Path,
    *,
    freecadcmd: str,
    part: str | None = None,
    request: str | None = None,
    check: Callable[[PartResult], str | None] | None = None,
    check_es_de_la_caja: bool = False,
    max_construcciones: int = MAX_CONSTRUCCIONES,
) -> tuple[Recipe, PartResult]:
    """Diseña y construye, devolviendo al agente el motivo de cada fallo.

    `part` fija el nombre de la pieza: el modelo podría devolver otro en la
    receta, y los artefactos tienen que llamarse como la tarea.

    `check` mira la pieza YA construida y devuelve el motivo si no vale
    (p. ej. que está mal colocada para el ensamble). Ese motivo vuelve al
    agente por el mismo camino que un fallo de FreeCAD.
    """
    rechazo: tuple[str, str] | None = None
    motivo = ""
    for intento in range(max_construcciones):
        receta = agent.design(brief, rechazo=rechazo)
        if part is not None:
            receta = receta.model_copy(update={"part": part})

        # F1.16 (trazabilidad): las cotas de la petición literal tienen que estar en la
        # receta. Si faltan, vuelve al agente con el valor exacto; en el
        # último intento se construye igualmente y queda anotado.
        perdidas = untraced(request, receta) if request else []
        if perdidas and intento < max_construcciones - 1:
            cotas = ", ".join(f"{c:g} mm" for c in perdidas)
            rechazo = (
                receta.model_dump_json(indent=2),
                f"estas cotas de la petición del usuario no aparecen en tu receta: "
                f"{cotas}. Úsalas tal cual; mandan sobre lo que sepas de este tipo de pieza.",
            )
            continue

        try:
            resultado = build_part(receta, catalog, Path(carpeta), freecadcmd)
            defecto = check(resultado) if check is not None else None
            if defecto:
                # Un desacuerdo de CAJA suele ser de quien la declaró, no de
                # quien dibujó: se le da una corrección al Part Designer y, si
                # sigue, se sube el problema en vez de gastar los tres intentos.
                if check_es_de_la_caja and intento >= 1:
                    raise CajaNoCuadra(f"la caja declarada no cuadra: {defecto}")
                raise ConstruccionFallida(defecto)
            return receta, resultado.model_copy(update={"untraced_mm": perdidas})
        except CajaNoCuadra:
            raise
        except ConstruccionFallida as error:
            motivo = error.motivo
            rechazo = (receta.model_dump_json(indent=2), motivo)
    raise ConstruccionFallida(
        f"{max_construcciones} construcciones fallidas. Último motivo: {motivo}"
    )
