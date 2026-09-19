"""Cinemática biela-manivela-corredera en línea (sin descentrado).

Manivela de radio r gira en el origen; la biela de longitud L une el
muñón de la manivela con la corredera, que desliza sobre el eje X.
Valores esperados calculados a mano: son el oráculo independiente.
"""

import math

import pytest

from sim.linkages import SliderCrank

M = SliderCrank(r=30.0, l=90.0)


def test_punto_muerto_exterior_a_0_grados():
    """Manivela y biela alineadas: la corredera está a r + L."""
    pos = M.at(0)
    assert pos.slider_x == pytest.approx(120.0)
    assert pos.crank_pin == pytest.approx([30.0, 0.0])
    assert pos.rod_angle_deg == pytest.approx(0.0, abs=1e-9)


def test_punto_muerto_interior_a_180_grados():
    assert M.at(180).slider_x == pytest.approx(60.0)


def test_la_carrera_es_dos_veces_el_radio():
    assert M.stroke == pytest.approx(60.0)


def test_a_90_grados_la_biela_esta_mas_inclinada():
    """Muñón en (0, 30); la corredera en x = sqrt(90² - 30²)."""
    pos = M.at(90)
    assert pos.crank_pin == pytest.approx([0.0, 30.0], abs=1e-9)
    assert pos.slider_x == pytest.approx(math.sqrt(90**2 - 30**2))
    assert pos.rod_angle_deg == pytest.approx(-math.degrees(math.asin(30 / 90)))


def test_la_biela_une_muñon_y_corredera_en_todos_los_angulos():
    """Invariante: la distancia muñón-corredera es siempre L."""
    for grados in range(0, 360, 15):
        p = M.at(grados)
        dx, dy = p.slider_x - p.crank_pin[0], 0.0 - p.crank_pin[1]
        assert math.hypot(dx, dy) == pytest.approx(90.0)


def test_una_biela_mas_corta_que_la_manivela_no_es_un_mecanismo():
    """Con L <= r la corredera no llega en toda la vuelta: el mecanismo se
    bloquea. Mejor rechazarlo al diseñar que descubrirlo al montar."""
    with pytest.raises(ValueError, match="bloquea"):
        SliderCrank(r=30.0, l=25.0)
