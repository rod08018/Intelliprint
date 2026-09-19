"""Validez del sólido al construir (F1.7).

Experimento previo en FreeCAD 1.1.3:
- Taladro Ø70 en placa de 60: 4 sólidos, isValid()=True, volumen plausible.
  Solo lo detecta contar los sólidos.
- Cáscara abierta: isValid()=False, volumen plausible (800 en vez de 1000).
  Solo lo detecta isValid().
Hacen falta las dos comprobaciones.
"""

import subprocess
from pathlib import Path

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.recipes.compose import RESULT_PREFIX, compose_build_script
from orchestrator.schemas.part_result import PartResult
from orchestrator.schemas.recipe import GeneratorCatalog, GeneratorSpec, Recipe, RecipeStep
from tests.test_generators import _freecadcmd


def _ejecutar(receta: Recipe, catalogo, tmp_path: Path) -> subprocess.CompletedProcess:
    build = tmp_path / "build.py"
    build.write_text(compose_build_script(receta, catalogo, output_dir=tmp_path))
    return subprocess.run(
        [_freecadcmd(), str(build)], capture_output=True, text=True, timeout=180
    )


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_pieza_partida_en_trozos_falla_al_construir(tmp_path):
    """Error realista de un modelo: equivocarse de radio y partir la pieza."""
    receta = Recipe(
        part="placa_rota",
        steps=[
            RecipeStep(
                generator="generate_plate",
                params={"length_mm": 60, "width_mm": 60, "thickness_mm": 6},
            ),
            RecipeStep(generator="generate_center_bore", params={"diameter_mm": 70}),
        ],
    )

    proceso = _ejecutar(receta, CATALOGO, tmp_path)
    salida = proceso.stdout + proceso.stderr

    assert RESULT_PREFIX not in proceso.stdout
    assert "4 sólidos" in salida  # el motivo tiene que llegar al agente (F1.11)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_solido_invalido_falla_al_construir(tmp_path):
    catalogo = GeneratorCatalog(
        [
            GeneratorSpec(
                name="generate_broken",
                required_params=set(),
                template=(
                    "_caja = Part.makeBox(10, 10, 10)\n"
                    "_roto = Part.Solid(Part.Shell(_caja.Faces[:-1]))\n"
                    "_f = doc.addObject('Part::Feature', 'roto')\n"
                    "_f.Shape = _roto\n"
                ),
            )
        ]
    )
    receta = Recipe(part="rota", steps=[RecipeStep(generator="generate_broken")])

    proceso = _ejecutar(receta, catalogo, tmp_path)

    assert RESULT_PREFIX not in proceso.stdout
    assert "no es válido" in proceso.stdout + proceso.stderr


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_resultado_cuenta_solidos_reales_no_objetos_del_documento(tmp_path):
    """El soporte NEMA17 tiene 9 objetos en el documento (placa, brocas,
    cortes...) pero es UN sólido. Contar objetos era un error."""
    receta = Recipe(
        part="nema",
        steps=[
            RecipeStep(
                generator="generate_plate",
                params={"length_mm": 60, "width_mm": 60, "thickness_mm": 6},
            ),
            RecipeStep(generator="generate_center_bore", params={"diameter_mm": 22}),
            RecipeStep(
                generator="generate_square_bolt_pattern",
                params={"hole_diameter_mm": 3.3, "pitch_mm": 31},
            ),
        ],
    )

    proceso = _ejecutar(receta, CATALOGO, tmp_path)

    assert PartResult.from_build_output("nema", proceso.stdout).solids == 1
