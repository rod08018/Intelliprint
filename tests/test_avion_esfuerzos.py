"""Los esfuerzos de los tubos de carbono (F13.11 (esfuerzos)).

Al compararlo con el Stallion de Flightory (2026-11-18), nadie medía si los
largueros aguantan: contado a mano, el Ø10 trabajaba a unos 125 MPa a 1 g y
a unos 500 a 4 g, y el anuncio no da la resistencia del tubo.

La sustentación a lo largo del ala se reparte por el método de Schrenk (la
media de la forma en planta y una elipse), que se puede comprobar a mano. Lo
aceptado es criterio del asistente: 4 g con la masa del avión, 600 MPa el
carbono y 100 GPa su módulo (el anuncio no da ninguno de los dos).
"""

import copy
import json
import math
from pathlib import Path

import pytest

from mech_toolkit import avion

HOY = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))["diseno"]


def test_un_tubo_de_10_por_8():
    """I = π(D⁴ − d⁴)/64 y W = I/(D/2), a mano: 289,8 mm⁴ y 57,96 mm³."""
    i, w = avion.seccion_tubo(10, 8)
    assert i == pytest.approx(289.8, abs=0.1)
    assert w == pytest.approx(57.96, abs=0.01)


def test_la_viga_con_un_motor_a_fondo_en_voladizo():
    """Ø16 × 12 con 3 kg a 430 mm del apoyo: 3·9,81·430 / (π(16⁴ − 12⁴)/64/8)
    = 46,0 MPa."""
    i, w = avion.seccion_tubo(16, 12)
    assert 3 * 9.81 * 430 / w == pytest.approx(46.0, abs=0.1)


def test_schrenk_en_un_ala_rectangular():
    """En un ala rectangular de semienvergadura s, la forma en planta reparte
    L/s por unidad de largo y la elipse 4L/(π s)·√(1 − (y/s)²). El momento en
    la raíz de la recta es L·s/2, y el de la elipse, 4L·s/(3π): Schrenk da la
    media, L·s·(1/4 + 2/(3π))."""
    d = {"estaciones": [[0, 0, 0, 200, 0, "mh60"], [1000, 0, 0, 200, 0, "mh60"]]}
    m = avion.momento_flector(d, 100.0, 0.0)
    assert m == pytest.approx(100 * 1000 * (0.25 + 2 / (3 * math.pi)) / 1000, rel=0.01)


def test_a_4_g_ningun_tubo_pasa_de_600_mpa():
    e = avion.esfuerzos(HOY)
    assert e["n"] == 4.0
    altos = {k: round(v["mpa"]) for k, v in e["tubos"].items() if v["mpa"] > 600}
    assert altos == {}, e["tubos"]


def test_los_esfuerzos_dicen_que_tubos_miden():
    """Los largueros en la raíz del ala, el manguito en el centro y las vigas
    con los motores a fondo."""
    e = avion.esfuerzos(HOY)
    assert {"larguero-10", "larguero-6", "manguito", "viga"} <= set(e["tubos"])
    assert e["flecha_punta_mm_1g"] > 0
