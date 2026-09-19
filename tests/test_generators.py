"""Generadores de mech-toolkit, probados construyendo geometría real.

Una plantilla que "parece bien" no vale: se ejecuta en `freecadcmd` y se
comprueba el volumen del sólido resultante. Ver PLAN_PROYECTO.md § 6:
las herramientas deterministas tienen tests antes de que un agente las use.
"""

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.recipes.compose import RESULT_PREFIX, compose_build_script
from orchestrator.schemas.recipe import Recipe, RecipeStep


def _freecadcmd() -> str | None:
    return (
        os.environ.get("FREECADCMD")
        or shutil.which("freecadcmd")
        or next(
            (
                r
                for r in ["/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"]
                if Path(r).exists()
            ),
            None,
        )
    )


def _construir(receta: Recipe, tmp_path: Path) -> dict:
    script = compose_build_script(receta, CATALOGO, output_dir=tmp_path)
    build = tmp_path / "build.py"
    build.write_text(script, encoding="utf-8")

    proceso = subprocess.run(
        [_freecadcmd(), str(build)], capture_output=True, text=True, timeout=180
    )
    linea = next(
        (l for l in proceso.stdout.splitlines() if l.startswith(RESULT_PREFIX)), None
    )
    assert linea is not None, (
        f"build.py no terminó.\n--- script ---\n{script}\n"
        f"--- stdout ---\n{proceso.stdout[-2000:]}\n--- stderr ---\n{proceso.stderr[-2000:]}"
    )
    return json.loads(linea[len(RESULT_PREFIX) :])


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_soporte_nema17_sale_con_las_dimensiones_exactas(tmp_path):
    """Placa 60x60x6 con taladro central Ø22 y 4 agujeros M3 en cuadro de 31.

    Es el entregable de la Fase 1. El volumen se calcula a mano, así que
    un generador que se equivoque de radio o no perfore no puede pasar.
    """
    receta = Recipe(
        part="soporte_nema17",
        steps=[
            RecipeStep(
                generator="generate_plate",
                params={"length_mm": 60, "width_mm": 60, "thickness_mm": 6},
            ),
            RecipeStep(
                generator="generate_center_bore",
                params={"diameter_mm": 22},
            ),
            RecipeStep(
                generator="generate_square_bolt_pattern",
                params={"hole_diameter_mm": 3.3, "pitch_mm": 31},
            ),
        ],
    )

    resultado = _construir(receta, tmp_path)

    esperado = (
        60 * 60 * 6
        - math.pi * 11**2 * 6
        - 4 * math.pi * 1.65**2 * 6
    )
    assert resultado["volume_mm3"] == pytest.approx(esperado, rel=1e-4)
    assert resultado["bbox_mm"] == pytest.approx([60, 60, 6])
    assert (tmp_path / "soporte_nema17.stl").exists()
