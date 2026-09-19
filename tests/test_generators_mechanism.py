"""Generadores para mecanismos: barra con dos agujeros, cajas y agujeros
colocados. Probados construyendo geometría real; volúmenes a mano."""

import math

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.build import build_part
from orchestrator.schemas.recipe import Recipe, RecipeStep
from tests.test_generators import _freecadcmd


def _construir(tmp_path, pasos):
    receta = Recipe(part="p", steps=[RecipeStep(generator=g, params=p) for g, p in pasos])
    return build_part(receta, CATALOGO, tmp_path, _freecadcmd())


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_barra_con_dos_agujeros_para_manivela_o_biela(tmp_path):
    """Forma de estadio: rectángulo d x w con semicírculos de radio w/2 en
    los extremos, y un agujero en cada centro. Origen en el primer agujero,
    que es el pivote: así la pieza gira alrededor de su propio origen."""
    r = _construir(tmp_path, [("generate_link", {
        "center_distance_mm": 30, "width_mm": 10, "thickness_mm": 5, "hole_diameter_mm": 3.4})])

    estadio = (30 * 10 + math.pi * 5**2) * 5
    agujeros = 2 * math.pi * 1.7**2 * 5
    assert r.volume_mm3 == pytest.approx(estadio - agujeros, rel=1e-4)
    assert r.bbox_mm == pytest.approx([40, 10, 5])


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_cajas_colocadas_se_suman_en_una_sola_pieza(tmp_path):
    """Una bancada: placa y un raíl encima. Dos cajas que se tocan forman
    un único sólido."""
    r = _construir(tmp_path, [
        ("generate_box", {"length_mm": 100, "width_mm": 40, "height_mm": 4,
                          "x_mm": 0, "y_mm": 0, "z_mm": -4}),
        ("generate_box", {"length_mm": 80, "width_mm": 5, "height_mm": 6,
                          "x_mm": 10, "y_mm": 12, "z_mm": 0}),
    ])

    assert r.volume_mm3 == pytest.approx(100 * 40 * 4 + 80 * 5 * 6, rel=1e-6)
    assert r.solids == 1


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_agujero_colocado_donde_se_pide(tmp_path):
    """El pivote de la manivela no tiene por qué estar en el centro de la
    bancada."""
    r = _construir(tmp_path, [
        ("generate_box", {"length_mm": 100, "width_mm": 40, "height_mm": 4,
                          "x_mm": 30, "y_mm": 0, "z_mm": 0}),
        ("generate_hole", {"diameter_mm": 3.4, "x_mm": 0, "y_mm": 0}),
    ])

    assert r.volume_mm3 == pytest.approx(100 * 40 * 4 - math.pi * 1.7**2 * 4, rel=1e-5)
