"""Los mandos de los elevones (F13.10 (mandos)).

Al compararlo con el Stallion de Flightory (2026-11-18), el avión no tenía
bisagra, cuerno ni varilla de mando, ni en el diseño ni en la lista de
compras. Y con el corte recto entre ala y elevón (1 mm de ranura), la esquina
de abajo del elevón tocaba el ala a los 10,6° en y = 433, cuando Gazebo los
dejaba ir a ±45°.

Contado a mano: la bisagra va a media altura del perfil, en la línea de
bisagra. Al bajar el elevón θ, su esquina de abajo, a (0,5; −h/2) del eje,
va a x' = 0,5·cos θ − (h/2)·sin θ, y toca la cara del ala (x = −0,5) cuando
0,5·cos θ + 0,5 = (h/2)·sin θ. Con h = 10,91 mm (el MH 60 al 75 % de su
cuerda en y = 433,3), θ = 10,5°.

Con el frente del elevón en V, a β del eje de la bisagra, la esquina no
llega a la cara del ala mientras θ ≤ β (criterio del asistente: ±25° libres,
y β = 30°).
"""

import copy
import json
import math
from pathlib import Path

import pytest

from mech_toolkit import avion

HOY = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))["diseno"]
RECTO = copy.deepcopy(HOY)
RECTO.pop("mandos", None)


def _a_mano(h, g=0.5):
    """El θ de 0,5·cos θ + g = (h/2)·sin θ, por bisección."""
    lo, hi = 0.0, math.pi / 2
    for _ in range(60):
        t = (lo + hi) / 2
        lo, hi = (t, hi) if g * math.cos(t) + g > h / 2 * math.sin(t) else (lo, t)
    return math.degrees((lo + hi) / 2)


def test_la_cuenta_a_mano():
    """θ = 10,5° con h = 10,91: comprobado sustituyendo."""
    t = math.radians(_a_mano(10.91))
    assert 0.5 * math.cos(t) + 0.5 == pytest.approx(10.91 / 2 * math.sin(t), abs=1e-6)
    assert math.degrees(t) == pytest.approx(10.5, abs=0.1)


def test_con_el_corte_recto_el_elevon_toca_el_ala_a_los_10_grados():
    y = 220 + 640 / 3
    assert avion.recorrido_elevon(RECTO, y) == pytest.approx(10.5, abs=0.3)


def test_con_el_corte_en_v_cada_elevon_tiene_25_grados_libres():
    for y0, y1, i in avion._tramos_ala(HOY):
        if avion._con_elevon(HOY, y0, y1, i):
            for y in (y0, (y0 + y1) / 2, y1):
                assert avion.recorrido_elevon(HOY, y) >= 25, y


def test_gazebo_deja_ir_los_elevones_lo_que_dejan_las_piezas():
    """El límite de las articulaciones del simulador sale del recorrido
    medido, no de ±45°."""
    from sim import generar
    r = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))
    libre = min(avion.recorrido_elevon(HOY, y) for y0, y1, i in avion._tramos_ala(HOY)
                if avion._con_elevon(HOY, y0, y1, i) for y in (y0, y1))
    assert generar.limite_elevon(r) == pytest.approx(math.radians(min(libre, 45)), abs=1e-3)


def test_cada_elevon_lleva_sus_bisagras_y_su_cuerno():
    """Tres bisagras de chapa por elevón y un cuerno a la altura de su servo."""
    for nombre, (lado, k) in {"interior": ("d", 2), "exterior": ("d", 3)}.items():
        m = avion.mandos(HOY, k)
        assert len(m["bisagras"]) == 3
        servo = next(s for s in avion._servos(HOY) if s["elevon"] == nombre)
        assert m["cuerno"]["y"] == pytest.approx(servo["y"])
