"""Disposición de una biela-manivela-corredera: piezas, medidas y posición
de cada una en cada ángulo. La decide el código a partir de la carrera y
de las holguras del perfil; el modelo diseñará cada pieza después."""

import pytest

from mech_toolkit.profile import PrinterProfile
from orchestrator.mechanisms.slider_crank import SliderCrankLayout

PERFIL = PrinterProfile(
    id="ankermake_m5_petg",
    fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35},
)


def _layout(carrera=60.0):
    return SliderCrankLayout(stroke_mm=carrera, profile=PERFIL)


def test_la_carrera_pedida_fija_el_radio_de_la_manivela():
    lay = _layout(60)
    assert lay.r == pytest.approx(30.0)
    assert lay.kinematics.stroke == pytest.approx(60.0)


def test_los_agujeros_de_las_articulaciones_llevan_la_holgura_del_perfil():
    """Un eje M3 de Ø3.0 tiene que girar: agujero = 3.0 + holgura."""
    assert _layout().hole_d == pytest.approx(3.35)


def test_la_corredera_tiene_juego_en_la_guia():
    """Holgura de deslizamiento del perfil (0.20 en diámetro, 0.10 por lado)."""
    lay = _layout()
    hueco = lay.rail_inner_y - lay.slider_w / 2
    assert hueco == pytest.approx(0.10)


def test_las_piezas_del_mecanismo():
    assert set(_layout().recipes()) == {"bancada", "manivela", "biela", "corredera"}


def test_la_biela_une_el_muñon_con_la_corredera_en_cada_angulo():
    """La biela se coloca con origen en el muñón y girada su ángulo: su
    otro agujero tiene que caer justo en el pasador de la corredera."""
    import math
    lay = _layout()
    for grados in (0, 45, 90, 200, 310):
        pos = lay.poses(grados)
        biela = pos["biela"]
        extremo_x = biela.origin[0] + lay.l * math.cos(math.radians(biela.rotation[2]))
        extremo_y = biela.origin[1] + lay.l * math.sin(math.radians(biela.rotation[2]))
        assert extremo_x == pytest.approx(pos["corredera"].origin[0])
        assert extremo_y == pytest.approx(0.0, abs=1e-9)


def test_las_capas_no_se_tocan_en_altura():
    """Manivela y corredera por encima de la bancada, biela por encima de
    ambas, con un hueco axial entre capas: si se tocaran, rozarían."""
    lay = _layout()
    pos = lay.poses(0)
    assert pos["manivela"].origin[2] > 0
    assert pos["biela"].origin[2] > pos["manivela"].origin[2] + lay.thickness
