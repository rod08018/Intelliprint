"""Extracción de caras cilíndricas del STEP con FreeCAD (F2.13).

Se usa el STEP y no el .FCStd: el STEP contiene SOLO la pieza final con
sus cilindros exactos; el .FCStd arrastra brocas, cortes intermedios, etc.
"""

import math

import pytest

from mech_toolkit.generators import CATALOGO
from mech_toolkit.geometry import Frame, find_bore, find_holes_on_circle
from mech_toolkit.measure import extract_cylinders
from orchestrator.build import build_part
from orchestrator.schemas.recipe import Recipe, RecipeStep
from tests.test_generators import _freecadcmd


def _nema17(tmp_path, taladro=22.0, agujero=3.3, paso=31.0, espesor=6.0):
    receta = Recipe(
        part="pieza",
        steps=[
            RecipeStep(generator="generate_plate",
                       params={"length_mm": 60, "width_mm": 60, "thickness_mm": espesor}),
            RecipeStep(generator="generate_center_bore", params={"diameter_mm": taladro}),
            RecipeStep(generator="generate_square_bolt_pattern",
                       params={"hole_diameter_mm": agujero, "pitch_mm": paso}),
        ],
    )
    build_part(receta, CATALOGO, tmp_path, _freecadcmd())
    return tmp_path / "pieza.step"


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_extrae_los_cilindros_reales_del_soporte(tmp_path):
    caras = extract_cylinders(_nema17(tmp_path), _freecadcmd())
    eje_z = Frame(origin=[0, 0, 0], axis=[0, 0, 1])

    taladro = find_bore(caras, eje_z)
    assert taladro.radius == pytest.approx(11.0)
    assert taladro.length == pytest.approx(6.0)

    agujeros = find_holes_on_circle(caras, eje_z, pcd_mm=31 * math.sqrt(2))
    assert len(agujeros) == 4
    assert all(a.radius == pytest.approx(1.65) for a in agujeros)
