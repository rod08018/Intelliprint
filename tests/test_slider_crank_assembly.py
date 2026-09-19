"""Ensamble de la biela-manivela-corredera en FreeCAD y barrido de choques.

El ensamble es lo que el usuario abre para verificar el mecanismo; el
barrido es lo que comprueba que funciona en TODA la vuelta, no solo en la
pose que se guarda. El criterio es físico (F2.20 (encaje)): entre dos
piezas que no se tocan tiene que quedar al menos la mitad de la holgura
deslizante del perfil, no basta con que no se intersequen.
"""

import zipfile

import pytest

from mech_toolkit.generators import CATALOGO
from mech_toolkit.profile import PrinterProfile
from orchestrator.assembly import build_assembly, sweep_collisions
from orchestrator.build import build_part
from orchestrator.mechanisms.slider_crank import SliderCrankLayout
from tests.test_generators import _freecadcmd

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")

PERFIL = PrinterProfile(
    id="ankermake_m5_petg",
    fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35},
)
HUECO_MIN = PERFIL.fit_mm("slide") / 2


@pytest.fixture(scope="module")
def piezas(tmp_path_factory):
    lay = SliderCrankLayout(stroke_mm=60, profile=PERFIL)
    carpeta = tmp_path_factory.mktemp("biela")
    steps = {}
    for nombre, receta in lay.recipes().items():
        build_part(receta, CATALOGO, carpeta / nombre, _freecadcmd())
        steps[nombre] = carpeta / nombre / f"{nombre}.step"
    return lay, steps


def _poses(lay, angulos):
    return {a: lay.poses(a) for a in angulos}


def test_el_ensamble_lleva_todas_las_piezas_y_ejes_visibles(piezas, tmp_path):
    lay, steps = piezas
    fcstd = tmp_path / "assembly.FCStd"
    build_assembly(steps, lay.pins(), lay.poses(30), fcstd, _freecadcmd())

    with zipfile.ZipFile(fcstd) as z:
        documento = z.read("Document.xml").decode()
        gui = z.read("GuiDocument.xml").decode()
    esperados = set(steps) | set(lay.pins())
    for nombre in esperados:
        assert f'name="{nombre}"' in documento
    # Todas visibles: un ensamble con piezas ocultas es el bug del .FCStd vacío.
    assert gui.count('<Bool value="true"/>') == len(esperados)
    assert '<Bool value="false"/>' not in gui


def test_el_mecanismo_no_choca_en_toda_la_vuelta(piezas):
    lay, steps = piezas
    choques = sweep_collisions(
        steps, lay.pins(), _poses(lay, range(0, 360, 15)), HUECO_MIN, _freecadcmd()
    )
    assert choques == []


def test_el_barrido_encuentra_un_choque_que_solo_ocurre_en_algunos_angulos(piezas):
    """Un eje de pivote demasiado alto choca con la biela solo cuando esta
    pasa por encima del pivote (manivela hacia atrás, ~180°). Una sola pose
    guardada a 0° no lo vería nunca."""
    lay, steps = piezas
    ejes = dict(lay.pins())
    d, _ = ejes["eje_pivote"]
    ejes["eje_pivote"] = (d, 20.0)

    choques = sweep_collisions(
        steps, ejes, _poses(lay, [0, 180]), HUECO_MIN, _freecadcmd()
    )
    pares = {(c.angle, frozenset((c.a, c.b))) for c in choques}
    assert (180, frozenset(("biela", "eje_pivote"))) in pares
    assert not any(c.angle == 0 and {c.a, c.b} == {"biela", "eje_pivote"} for c in choques)
    choque = next(c for c in choques if c.angle == 180 and "eje_pivote" in (c.a, c.b))
    assert choque.gap_mm < HUECO_MIN
    assert "180" in choque.motivo and "eje_pivote" in choque.motivo
