"""Generadores de la rueda de Ginebra y su disco de bloqueo (F3.15 (mecanismos)).

Fallo real, el Ginebra del 2026-09-21: en 5 de 10 rondas el Part Designer no
consiguió dibujar la rueda componiendo cilindros y cajas (salía en 5 trozos,
o no cabía en su caja), y el diseñador fue probando radios de bloqueo a ojo:
41.4, 17.57, 34.5… Una Ginebra externa queda determinada por cuatro números
—ranuras N, distancia entre centros C, diámetro del pasador y holgura— y el
resto sale de fórmulas estándar. Rueda y bloqueo salen de las MISMAS
fórmulas, así que encajan por construcción.

Oráculos: medidas calculadas a mano, y lo que importa de verdad, la
cinemática: en reposo el bloqueo se aloja en el arco de la rueda sin
tocarla; con el pasador en el fondo de la ranura, no toca la rueda.
"""

import math

import pytest

from mech_toolkit.generators import CATALOGO
from mech_toolkit.geometry import Placement
from orchestrator.assembly import pair_gaps
from orchestrator.build import build_part
from orchestrator.schemas.recipe import Recipe, RecipeStep
from tests.test_generators import _freecadcmd

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")

N, C, PASADOR, ESPESOR, HOLGURA = 4, 60.0, 8.0, 6.0, 0.25
A = C * math.sin(math.pi / N)             # radio de manivela: 42.43
B = C * math.cos(math.pi / N)             # radio de entrada:  42.43
ANCHO = PASADOR + 2 * HOLGURA             # 8.5
R_RUEDA = math.hypot(B, ANCHO / 2)        # 42.64
R_BLOQUEO = A - ANCHO / 2 - HOLGURA - 1   # 36.93: el arco a 1 mm de la boca de la ranura
COMUNES = {"slots": N, "center_distance_mm": C, "pin_diameter_mm": PASADOR,
           "thickness_mm": ESPESOR, "clearance_mm": HOLGURA}


@pytest.fixture(scope="module")
def piezas(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("ginebra")
    hechas = {}
    for nombre, generador in (("rueda", "generate_geneva_wheel"), ("bloqueo", "generate_geneva_lock")):
        receta = Recipe(part=nombre, steps=[RecipeStep(generator=generador, params=COMUNES)])
        hechas[nombre] = build_part(receta, CATALOGO, carpeta / nombre, _freecadcmd())
    return carpeta, hechas


def test_la_rueda_sale_en_una_sola_pieza_con_su_caja(piezas):
    _, hechas = piezas
    rueda = hechas["rueda"]
    assert rueda.solids == 1
    # Con N múltiplo de 4 las ranuras caen en los ejes: lo más lejano en X e
    # Y es la esquina de la ranura, a b del centro.
    assert rueda.bbox_mm[0] == pytest.approx(2 * B, abs=0.05)
    assert rueda.bbox_mm[1] == pytest.approx(2 * B, abs=0.05)
    assert rueda.bbox_mm[2] == pytest.approx(ESPESOR, abs=0.01)


def test_el_bloqueo_sale_en_una_sola_pieza_con_su_caja(piezas):
    _, hechas = piezas
    bloqueo = hechas["bloqueo"]
    assert bloqueo.solids == 1
    # Disco de radio R_BLOQUEO con el alivio del lado +X (hacia el pasador).
    # En X llega hasta donde se cruzan los dos círculos —las puntas de la
    # media luna—, no hasta donde el alivio corta el eje:
    #   x² + y² = r²  y  (x - C)² + y² = (R + h)²  →  x = (C² + r² - (R+h)²) / 2C
    punta = (C**2 + R_BLOQUEO**2 - (R_RUEDA + HOLGURA) ** 2) / (2 * C)
    assert bloqueo.bbox_mm[0] == pytest.approx(R_BLOQUEO + punta, abs=0.05)
    assert bloqueo.bbox_mm[1] == pytest.approx(2 * R_BLOQUEO, abs=0.05)


def _pasos(carpeta):
    return {n: carpeta / n / f"{n}.step" for n in ("rueda", "bloqueo")}


def test_en_reposo_el_bloqueo_se_aloja_en_el_arco_sin_tocar_la_rueda(piezas):
    """Reposo: el pasador está en el lado OPUESTO a la rueda. La rueda queda
    en -X respecto al eje conductor, así que el pasador —y el alivio, que
    mira hacia él— van en +X: el bloqueo sin girar. Y un arco cóncavo de la
    rueda mira al eje conductor. Los arcos están a (k+½)·360/N: girando la rueda -45°, el
    arco de 45° queda en +X, frente al conductor en (C, 0)."""
    carpeta, _ = piezas
    poses = {0: {"rueda": Placement(rotation=[0, 0, -180.0 / N]),
                 "bloqueo": Placement(origin=[C, 0, 0])}}
    (hueco,) = pair_gaps(_pasos(carpeta), {}, poses, [("rueda", "bloqueo")], _freecadcmd())
    assert 0 <= hueco["gap_mm"] <= 2 * HOLGURA + 0.05


def test_con_el_pasador_en_el_fondo_de_la_ranura_no_toca_la_rueda(piezas, tmp_path):
    """Con el pasador lo más dentro posible —en (C - a, 0), sobre el eje de
    la ranura 0— tiene que caber en ella con holgura."""
    carpeta, _ = piezas
    pasador = Recipe(part="pasador", steps=[RecipeStep(generator="generate_cylinder", params={
        "diameter_mm": PASADOR, "length_mm": ESPESOR, "x_mm": 0, "y_mm": 0, "z_mm": 0,
        "axis": "z"})])
    build_part(pasador, CATALOGO, tmp_path / "pasador", _freecadcmd())
    pasos = {"rueda": carpeta / "rueda" / "rueda.step",
             "pasador": tmp_path / "pasador" / "pasador.step"}
    poses = {0: {"rueda": Placement(), "pasador": Placement(origin=[C - A, 0, 0])}}
    (hueco,) = pair_gaps(pasos, {}, poses, [("rueda", "pasador")], _freecadcmd())
    assert hueco["gap_mm"] >= HOLGURA - 0.05
