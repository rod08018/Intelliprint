"""Articulaciones resueltas por contacto y bloqueos (F3.15 (mecanismos)).

Oráculo independiente: trigonometría a mano. Una barra de ancho 10 que
pivota a 40 mm del centro de un disco de Ø40 se apoya en él cuando su eje
queda a 25 mm del centro, es decir a asin(25/40) = 38.68° de la línea que
une pivote y centro.
"""

import math
import re

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


def _hueco(piezas, kin, valor, t=0, a="palanca", b="disco"):
    from orchestrator.assembly import pair_gaps
    return pair_gaps(piezas, {}, {t: kin.poses(t, {a: valor})}, [(a, b)], _freecadcmd())[0]["gap_mm"]


def test_el_apoyo_resuelto_deja_el_hueco_dentro_de_la_banda_del_contacto(piezas):
    """Fallo real (11 de 19 rondas del trinquete): el solucionador aceptaba la
    PRIMERA muestra con hueco ≤ 0.02, y eso incluye un solape de 14 mm³. El
    barrido juzgaba después el mismo par con otro criterio y lo rechazaba."""
    spec = _spec()
    kin = Kinematics(spec)
    resueltos = solve_contacts(spec, kin, piezas, {}, _freecadcmd(), kin.frames())

    for t in kin.frames():
        hueco = _hueco(piezas, kin, resueltos[(t, "palanca")], t)
        assert 0 <= hueco <= 0.05, f"con t={t} el apoyo quedó en {hueco}"


def test_si_el_punto_de_partida_ya_penetra_se_dice_eso_y_no_otra_cosa(piezas):
    """Con `start` dentro del objetivo el solucionador devolvía ese mismo
    valor, con todo su solape, y sin avisar."""
    spec = _spec(start="180")          # apuntando al disco: la barra lo atraviesa
    with pytest.raises(SinApoyo, match="punto de partida"):
        solve_contacts(spec, Kinematics(spec), piezas, {}, _freecadcmd(), [0])


def test_cuando_no_toca_se_informa_el_hueco_MINIMO_y_donde(piezas):
    """Informaba el hueco del ÚLTIMO punto del barrido, no el más cercano:
    al agente se le daba un número que no era su mejor aproximación."""
    spec = _spec(start="240", limite=8.0)
    with pytest.raises(SinApoyo) as e:
        solve_contacts(spec, Kinematics(spec), piezas, {}, _freecadcmd(), [0])

    assert "más cerca" in str(e.value)
    numeros = [float(x) for x in re.findall(r"\d+\.\d+", str(e.value))]
    minimo = min(_hueco(piezas, Kinematics(spec), v) for v in (240, 236, 232))
    assert any(abs(n - minimo) < 0.5 for n in numeros), str(e.value)


def test_la_regla_de_contacto_del_apoyo_se_deriva_sola(piezas):
    """Un `rest_on` sin regla de contacto explícita era un fallo garantizado:
    el barrido exigía 0.1 mm donde el solucionador dejaba 0.02."""
    from orchestrator.mechanisms.spec_layout import SpecLayout

    reglas = SpecLayout(_spec()).pair_rules()

    assert reglas[("palanca", "disco")][0] == 0.0
    assert reglas[("palanca", "disco")][1] is not None


@pytest.fixture(scope="module")
def bloques(tmp_path_factory):
    """Dos cajas: un empujador que va y vuelve, y un carro que solo se mueve
    cuando lo empujan. Es el caso más limpio para probar la memoria."""
    carpeta = tmp_path_factory.mktemp("memoria")
    caja = lambda n: Recipe(part=n, steps=[{"generator": "generate_box", "params": {
        "length_mm": 10, "width_mm": 10, "height_mm": 5, "x_mm": 5, "y_mm": 0, "z_mm": 0}}])
    for nombre in ("carro", "empujador"):
        build_part(caja(nombre), CATALOGO, carpeta / nombre, _freecadcmd())
    return {n: carpeta / n / f"{n}.step" for n in ("carro", "empujador")}


def _carro_empujado(carry=True):
    """El empujador avanza y vuelve; el carro empieza delante de él."""
    return MechanismSpec(**{
        "title": "memoria", "summary": "s",
        "driver": {"start": 0, "end": 180, "step": 45},
        "parts": [
            {"name": "carro", "brief": "b", "bbox_min": [0, -5, 0], "bbox_max": [10, 5, 5],
             "joint": {"type": "prismatic", "axis": [1, 0, 0],
                       "rest_on": {"target": "empujador", "start": "20", "toward": "increase",
                                   "limit": 40, "carry": carry}}},
            {"name": "empujador", "brief": "b", "bbox_min": [0, -5, 0], "bbox_max": [10, 5, 5],
             "joint": {"type": "prismatic", "axis": [1, 0, 0], "value": "30*sin(t)"}},
        ],
    })


def test_la_pieza_con_memoria_solo_avanza_cuando_la_empujan(bloques):
    """El empujador entra (t: 0→90) y empuja el carro; al salir (90→180) el
    carro NO retrocede: se queda donde llegó."""
    spec = _carro_empujado()
    kin = Kinematics(spec)
    resueltos = solve_contacts(spec, kin, bloques, {}, _freecadcmd(), kin.frames())

    valores = [resueltos[(t, "carro")] for t in kin.frames()]
    assert valores == sorted(valores), f"el carro retrocedió: {valores}"
    assert valores[0] == pytest.approx(20, abs=0.5)      # nadie lo ha tocado aún
    assert valores[2] == pytest.approx(40, abs=0.6)      # empujado: 30 del empujador + su largo
    assert valores[-1] == pytest.approx(valores[2], abs=0.5)   # y ahí se queda


def test_sin_memoria_la_misma_pieza_ni_siquiera_se_puede_resolver(bloques):
    """El contraste: sin `carry`, cada fotograma parte del mismo sitio fijo,
    así que en cuanto el empujador llega lo atraviesa y no hay solución. Con
    memoria, el carro va delante de él. Por eso hace falta la memoria."""
    spec = _carro_empujado(carry=False)

    with pytest.raises(SinApoyo, match="punto de partida"):
        solve_contacts(spec, Kinematics(spec), bloques, {}, _freecadcmd(), [45])
