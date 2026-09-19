"""Articulaciones resueltas por contacto y bloqueos (F3.15 (mecanismos)).

Oráculo independiente: trigonometría a mano. Una barra de ancho 10 que
pivota a 40 mm del centro de un disco de Ø40 se apoya en él cuando su eje
queda a 25 mm del centro, es decir a asin(25/40) = 38.68° de la línea que
une pivote y centro.
"""

import math

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.build import build_part
from orchestrator.mechanisms.contact import SinApoyo, block_problems, solve_contacts
from orchestrator.mechanisms.kinematics import Kinematics
from orchestrator.schemas.mechanism import MechanismSpec
from orchestrator.schemas.recipe import Recipe
from tests.test_generators import _freecadcmd

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")

RECETAS = {
    "disco": Recipe(part="disco", steps=[{"generator": "generate_cylinder", "params": {
        "diameter_mm": 40, "length_mm": 5, "x_mm": 0, "y_mm": 0, "z_mm": 0, "axis": "z"}}]),
    "palanca": Recipe(part="palanca", steps=[{"generator": "generate_link", "params": {
        "center_distance_mm": 30, "width_mm": 10, "thickness_mm": 5, "hole_diameter_mm": 3.35}}]),
}


@pytest.fixture(scope="module")
def piezas(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("apoyo")
    for nombre, receta in RECETAS.items():
        build_part(receta, CATALOGO, carpeta / nombre, _freecadcmd())
    return {n: carpeta / n / f"{n}.step" for n in RECETAS}


def _spec(start="240", limite=60.0, distancia=40.0, dientes=None):
    return MechanismSpec(**{
        "title": "apoyo", "summary": "s",
        "driver": {"start": 0, "end": 90, "step": 45},
        "parts": [
            {"name": "disco", "brief": "b", "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 5],
             "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "t"}},
            {"name": "palanca", "origin": [distancia, 0, 0], "brief": "b",
             "bbox_min": [-5, -5, 0], "bbox_max": [35, 5, 5],
             "joint": {"type": "revolute", "axis": [0, 0, 1],
                       "rest_on": {"target": "disco", "start": start,
                                   "toward": "decrease", "limit": limite}}},
        ],
    })


def test_la_pieza_se_apoya_donde_dice_la_trigonometria(piezas):
    spec = _spec()
    kin = Kinematics(spec)
    resueltos = solve_contacts(spec, kin, piezas, {}, _freecadcmd(), kin.frames())

    esperado = 180 + math.degrees(math.asin(25.02 / 40))
    for t in kin.frames():
        assert resueltos[(t, "palanca")] == pytest.approx(esperado, abs=0.3)
    # Y la pose ya usa el valor resuelto, no la fórmula de partida (los
    # ángulos de Euler salen entre -180 y 180: se compara módulo 360).
    assert kin.poses(0)["palanca"].rotation[2] % 360 == pytest.approx(esperado, abs=0.3)


def test_si_no_llega_a_tocar_lo_dice_con_el_hueco_que_queda(piezas):
    spec = _spec(start="240", limite=5.0)
    kin = Kinematics(spec)
    with pytest.raises(SinApoyo, match="no llega a apoyarse"):
        solve_contacts(spec, kin, piezas, {}, _freecadcmd(), kin.frames())


def test_un_bloqueo_se_comprueba_moviendo_la_pieza_contra_lo_que_la_frena(piezas):
    """Apoyada la palanca en el disco, girarla 5° más la mete en el disco
    (bloqueo real); girarla al otro lado la separa (no hay bloqueo)."""
    spec = _spec()
    kin = Kinematics(spec)
    solve_contacts(spec, kin, piezas, {}, _freecadcmd(), kin.frames())

    bloqueo = {"body": "palanca", "against": "disco", "at": 0, "delta": -5}
    spec_ok = spec.model_copy(update={"blocks": [type(spec).model_fields["blocks"].annotation.__args__[0](**bloqueo)]})
    assert block_problems(spec_ok, kin, piezas, {}, _freecadcmd()) == []

    spec_mal = spec.model_copy(update={"blocks": [type(spec).model_fields["blocks"].annotation.__args__[0](
        **{**bloqueo, "delta": 5})]})
    problemas = block_problems(spec_mal, kin, piezas, {}, _freecadcmd())
    assert len(problemas) == 1 and "NO bloquea" in problemas[0]
