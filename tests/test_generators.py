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


# --- Cuerpos colocados donde se pide --------------------------------------------
#
# Con estos generadores se componen las piezas de calibración
# (`orchestrator/calibracion.py`): cajas, cilindros y agujeros en un sitio
# dado. Volúmenes a mano.

needs_freecad = pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")


def _construir_pasos(tmp_path, pasos):
    from orchestrator.build import build_part

    receta = Recipe(part="p", steps=[RecipeStep(generator=g, params=p) for g, p in pasos])
    return build_part(receta, CATALOGO, tmp_path, _freecadcmd())


@needs_freecad
def test_cajas_colocadas_se_suman_en_una_sola_pieza(tmp_path):
    """Una bancada: placa y un raíl encima. Dos cajas que se tocan forman
    un único sólido."""
    r = _construir_pasos(tmp_path, [
        ("generate_box", {"length_mm": 100, "width_mm": 40, "height_mm": 4,
                          "x_mm": 0, "y_mm": 0, "z_mm": -4}),
        ("generate_box", {"length_mm": 80, "width_mm": 5, "height_mm": 6,
                          "x_mm": 10, "y_mm": 12, "z_mm": 0}),
    ])

    assert r.volume_mm3 == pytest.approx(100 * 40 * 4 + 80 * 5 * 6, rel=1e-6)
    assert r.solids == 1


@needs_freecad
def test_un_agujero_colocado_donde_se_pide(tmp_path):
    """El agujero no tiene por qué estar en el centro de la placa."""
    r = _construir_pasos(tmp_path, [
        ("generate_box", {"length_mm": 100, "width_mm": 40, "height_mm": 4,
                          "x_mm": 30, "y_mm": 0, "z_mm": 0}),
        ("generate_hole", {"diameter_mm": 3.4, "x_mm": 0, "y_mm": 0}),
    ])

    assert r.volume_mm3 == pytest.approx(100 * 40 * 4 - math.pi * 1.7**2 * 4, rel=1e-5)


@needs_freecad
def test_cilindro_horizontal_con_agujero_a_lo_largo_de_su_eje(tmp_path):
    """Un nudillo de bisagra: cilindro a lo largo de X con agujero pasante."""
    r = _construir_pasos(tmp_path, [
        ("generate_cylinder", {"diameter_mm": 10, "length_mm": 20, "x_mm": 5,
                               "y_mm": 0, "z_mm": 0, "axis": "x"}),
        ("generate_hole_axis", {"diameter_mm": 4, "x_mm": 0, "y_mm": 0, "z_mm": 0, "axis": "x"}),
    ])
    assert r.volume_mm3 == pytest.approx(math.pi * (25 - 4) * 20, rel=1e-5)
    assert r.bbox_min == pytest.approx([5, -5, -5], abs=1e-6)
    assert r.bbox_max == pytest.approx([25, 5, 5], abs=1e-6)


@needs_freecad
def test_vaciado_con_caja(tmp_path):
    r = _construir_pasos(tmp_path, [
        ("generate_box", {"length_mm": 40, "width_mm": 20, "height_mm": 10,
                          "x_mm": 0, "y_mm": 0, "z_mm": 0}),
        ("generate_cut_box", {"length_mm": 10, "width_mm": 30, "height_mm": 4,
                              "x_mm": 0, "y_mm": 0, "z_mm": 6}),
    ])
    assert r.volume_mm3 == pytest.approx(40 * 20 * 10 - 10 * 20 * 4, rel=1e-6)
