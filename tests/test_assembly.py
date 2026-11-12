"""Ensamble en FreeCAD y barrido de choques (`orchestrator/assembly.py`).

El ensamble es lo que el usuario abre para ver el conjunto; el barrido es
lo que comprueba que se mueve en TODO el recorrido, no solo en la pose que
se guarda. El criterio es físico (F2.20 (encaje)): entre dos piezas que no
se tocan tiene que quedar al menos la mitad de la holgura deslizante del
perfil, no basta con que no se intersequen.

Las piezas son de aquí y están hechas a mano: una base con un agujero para
un tope, y un brazo que gira 6 mm por encima de ella. Con el tope corto el
brazo le pasa a 1 mm; con el tope alto, lo atraviesa cuando apunta hacia
él (a 180°) y solo entonces. Hasta F9.13 (limpieza) hacía de muestra la
biela-manivela del flujo de mecanismos.
"""

import zipfile

import pytest

from mech_toolkit.generators import CATALOGO
from mech_toolkit.geometry import Placement
from mech_toolkit.profile import PrinterProfile
from orchestrator.assembly import build_assembly, sweep_collisions
from orchestrator.build import build_part
from orchestrator.schemas.recipe import Recipe
from tests.test_generators import _freecadcmd

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")

PERFIL = PrinterProfile(
    id="ankermake_m5_petg",
    fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35},
)
HUECO_MIN = PERFIL.fit_mm("slide") / 2

TOPE_X = -30.0
ALTO_DEL_BRAZO = 6.0
"""El brazo va de z = 6 a z = 11."""

RECETAS = {
    # Placa de 80 x 80 x 4 con la cara de arriba en z = 0, y un agujero de
    # Ø4.4 por el que pasa el tope (Ø4) con 0.2 de holgura radial.
    "base": [
        {"generator": "generate_box", "params": {
            "length_mm": 80, "width_mm": 80, "height_mm": 4, "x_mm": 0, "y_mm": 0, "z_mm": -4}},
        {"generator": "generate_hole", "params": {"diameter_mm": 4.4, "x_mm": TOPE_X, "y_mm": 0}},
    ],
    # De x = -4 a x = 36 en su marco: girado 180° llega a x = -36, por
    # encima del tope.
    "brazo": [
        {"generator": "generate_box", "params": {
            "length_mm": 40, "width_mm": 8, "height_mm": 5, "x_mm": 16, "y_mm": 0, "z_mm": 0}},
    ],
}

TOPE_CORTO = {"tope": (4.0, 9.0)}
"""De z = -4 a z = 5: el brazo le pasa a 1 mm por encima."""
TOPE_ALTO = {"tope": (4.0, 24.0)}
"""De z = -4 a z = 20: el brazo lo atraviesa cuando apunta hacia él."""


def poses(grados: float) -> dict[str, Placement]:
    return {
        "base": Placement(),
        "brazo": Placement(origin=[0, 0, ALTO_DEL_BRAZO], rotation=[0, 0, grados]),
        "tope": Placement(origin=[TOPE_X, 0, -4]),
    }


def construir_piezas(carpeta) -> dict:
    """Las piezas de muestra construidas de verdad: nombre -> su STEP."""
    steps = {}
    for nombre, pasos in RECETAS.items():
        build_part(Recipe(part=nombre, steps=pasos), CATALOGO, carpeta / nombre, _freecadcmd())
        steps[nombre] = carpeta / nombre / f"{nombre}.step"
    return steps


@pytest.fixture(scope="module")
def piezas(tmp_path_factory):
    return construir_piezas(tmp_path_factory.mktemp("brazo"))


def _poses(angulos):
    return {a: poses(a) for a in angulos}


def test_el_ensamble_lleva_todas_las_piezas_y_ejes_visibles(piezas, tmp_path):
    fcstd = tmp_path / "assembly.FCStd"
    build_assembly(piezas, TOPE_CORTO, poses(30), fcstd, _freecadcmd())

    with zipfile.ZipFile(fcstd) as z:
        documento = z.read("Document.xml").decode()
        gui = z.read("GuiDocument.xml").decode()
    esperados = set(piezas) | set(TOPE_CORTO)
    for nombre in esperados:
        assert f'name="{nombre}"' in documento
    # Todas visibles: un ensamble con piezas ocultas es el bug del .FCStd vacío.
    assert gui.count('<Bool value="true"/>') == len(esperados)
    assert '<Bool value="false"/>' not in gui


def test_lo_que_se_mueve_libre_no_choca_en_toda_la_vuelta(piezas):
    choques = sweep_collisions(
        piezas, TOPE_CORTO, _poses(range(0, 360, 15)), HUECO_MIN, _freecadcmd()
    )
    assert choques == []


def test_el_barrido_encuentra_un_choque_que_solo_ocurre_en_algunos_angulos(piezas):
    """El tope alto choca con el brazo solo cuando este pasa por encima de
    él (a 180°). Una sola pose guardada a 0° no lo vería nunca."""
    choques = sweep_collisions(
        piezas, TOPE_ALTO, _poses([0, 180]), HUECO_MIN, _freecadcmd()
    )
    pares = {(c.angle, frozenset((c.a, c.b))) for c in choques}
    assert (180, frozenset(("brazo", "tope"))) in pares
    assert not any(c.angle == 0 and {c.a, c.b} == {"brazo", "tope"} for c in choques)
    choque = next(c for c in choques if c.angle == 180 and "tope" in (c.a, c.b))
    assert choque.gap_mm < HUECO_MIN
    assert "180" in choque.motivo and "tope" in choque.motivo


def test_la_animacion_da_una_vuelta_con_el_brazo_en_movimiento(piezas, tmp_path):
    pytest.importorskip("matplotlib")
    from PIL import Image, ImageChops

    from orchestrator.animation import render_gif, tessellate

    angulos = [0, 90, 180, 270]
    gif = render_gif(
        tessellate(piezas, TOPE_CORTO, _freecadcmd()), _poses(angulos),
        tmp_path / "brazo.gif",
    )
    with Image.open(gif) as img:
        assert img.n_frames == len(angulos)
        img.seek(0)
        primero = img.convert("RGB")
        img.seek(2)
        mitad = img.convert("RGB")
    # A 0° y a 180° el brazo apunta a lados opuestos.
    assert ImageChops.difference(primero, mitad).getbbox() is not None


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_barrido_no_mide_los_pares_que_no_pueden_tocarse():
    """Banco 1112-0318: el primer brazo de tres ejes salió con sus cuatro
    piezas y no llegó a moverse entero. Tres giros son 19³ = 6 859 poses, y
    en cada una se medía la distancia exacta entre cada par de sólidos, que
    con piezas de verdad cuesta décimas de segundo: FreeCAD pasó de los 600 s.
    Casi todas esas poses tienen las piezas lejos una de otra: si sus cajas
    están separadas más que la holgura, no pueden rozarse y no hay que medir.

    Dos cubos de 10 mm, uno quieto y el otro con su esquina en x = 100, 50,
    10.05 y 5. A mano, los huecos son 90, 40 y 0.05 mm, y en el último se
    meten 5 × 10 × 10 = 500 mm³. Con 0.2 mm de holgura chocan los dos
    últimos, y solo esos dos hay que medirlos."""
    from orchestrator.assembly import _datos, _run
    cubo = [{"tipo": "caja", "min": [0, 0, 0], "max": [10, 10, 10]}]
    cuadros = {float(k): {"a": Placement(), "b": Placement(origin=(x, 0, 0))}
               for k, x in enumerate((100, 50, 10.05, 5))}
    datos = _datos({}, {}, cuadros, {"a": cubo, "b": cubo})
    datos["min_gap"], datos["rules"] = 0.2, {}
    r = _run(datos, _freecadcmd())
    assert [(c["angle"], round(c["gap_mm"], 2)) for c in r["collisions"]] == [(2.0, 0.05),
                                                                             (3.0, -500.0)]
    assert (r["medidos"], r["descartados"]) == (2, 2)
