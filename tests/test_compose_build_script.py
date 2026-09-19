"""Composición de build.py a partir de una receta.

El LLM produce la receta; este código produce el Python. Ver DECISIONES.md
ADR-002 y SISTEMA_MULTIAGENTE.md § 5.2.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.recipes.compose import RESULT_PREFIX, compose_build_script
from orchestrator.schemas.recipe import (
    GeneratorCatalog,
    GeneratorSpec,
    Recipe,
    RecipeStep,
)


def _catalogo_con_caja() -> GeneratorCatalog:
    return GeneratorCatalog(
        [
            GeneratorSpec(
                name="generate_box",
                required_params={"length", "width", "height"},
                # Texto solo como opción cerrada; compose le pone las comillas.
                choice_params={"name": {"B"}},
                template=(
                    'obj = doc.addObject("Part::Box", $name)\n'
                    "obj.Length = $length\n"
                    "obj.Width = $width\n"
                    "obj.Height = $height"
                ),
            )
        ]
    )


def _receta_cubo_20mm() -> Recipe:
    return Recipe(
        part="cubo",
        steps=[
            RecipeStep(
                generator="generate_box",
                params={"name": "B", "length": 20, "width": 20, "height": 20},
            )
        ],
    )


def test_compone_el_script_renderizando_la_plantilla_del_generador():
    """Los parámetros de la receta acaban en el código, sustituidos."""
    script = compose_build_script(_receta_cubo_20mm(), _catalogo_con_caja())

    assert """doc.addObject("Part::Box", 'B')""" in script
    assert "obj.Length = 20" in script


def test_una_plantilla_con_codigo_python_real_no_se_rompe():
    """Los generadores de verdad llevan listas, dicts y bucles.

    Cualquier `{` literal en el código reventaría una sustitución basada
    en str.format, y eso deja fuera a casi todo generador no trivial: un
    patrón de tornillos necesita una lista de coordenadas.
    """
    catalogo = GeneratorCatalog(
        [
            GeneratorSpec(
                name="generate_holes",
                required_params={"pitch"},
                template=(
                    "_p = $pitch\n"
                    "for _x, _y in [(_p, _p), (-_p, _p)]:\n"
                    '    _cfg = {"x": _x, "y": _y}\n'
                    "    doc.addObject('Part::Cylinder', 'h')\n"
                ),
            )
        ]
    )
    receta = Recipe(
        part="placa",
        steps=[RecipeStep(generator="generate_holes", params={"pitch": 15.5})],
    )

    script = compose_build_script(receta, catalogo)

    assert "_p = 15.5" in script
    assert '_cfg = {"x": _x, "y": _y}' in script  # el dict sobrevive intacto


def _freecadcmd() -> str | None:
    """freecadcmd del entorno, o el del bundle de macOS."""
    return (
        os.environ.get("FREECADCMD")
        or shutil.which("freecadcmd")
        or next(
            (
                ruta
                for ruta in ["/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"]
                if Path(ruta).exists()
            ),
            None,
        )
    )


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_script_compuesto_construye_geometria_correcta_en_freecad(tmp_path):
    """La prueba de fondo de ADR-002: la receta produce la pieza esperada.

    No basta con que el script tenga buena pinta. Se ejecuta en un proceso
    `freecadcmd` real (§ 9.3) y se comprueba el volumen del sólido: un cubo
    de 20 mm son 8000 mm³ exactos.
    """
    script = compose_build_script(
        _receta_cubo_20mm(), _catalogo_con_caja(), output_dir=tmp_path
    )
    build_py = tmp_path / "build.py"
    build_py.write_text(script, encoding="utf-8")

    proceso = subprocess.run(
        [_freecadcmd(), str(build_py)],
        capture_output=True,
        text=True,
        timeout=180,
    )

    linea = next(
        (l for l in proceso.stdout.splitlines() if l.startswith(RESULT_PREFIX)), None
    )
    assert linea is not None, f"sin línea de resultado.\n{proceso.stdout}\n{proceso.stderr}"

    resultado = json.loads(linea[len(RESULT_PREFIX) :])
    assert resultado["volume_mm3"] == pytest.approx(8000.0, rel=1e-6)
    assert (tmp_path / "cubo.stl").exists()
