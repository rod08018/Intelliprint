"""De aserciones derivadas a valores medidos (F2.13 (puente)).

Ciclo completo: interfaz resuelta → aserciones (F2.12 (derive_assertions)) → caras reales de
la pieza → búsqueda por contrato → valores medidos → veredicto.
"""

import math

import pytest

from mech_toolkit.assertions import derive_assertions
from mech_toolkit.geometry import Cylinder, Placement
from mech_toolkit.profile import PrinterProfile
from orchestrator.qa import measure_interfaces
from orchestrator.schemas.interface import Interface
from orchestrator.schemas.qa_report import QaReport
from tests.test_generators import _freecadcmd
from tests.test_measure_extract import _nema17

PERFIL = PrinterProfile(
    id="ankermake_m5_petg",
    fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35},
    holes={"M3_through_mm": 3.3},
)
PCD_CUADRO_31 = 31 * math.sqrt(2)


def _patron(pcd=PCD_CUADRO_31) -> Interface:
    return Interface(
        id="IF-MOTOR", state="resolved", type="bolt_pattern",
        between=["soporte", "nema17"], hardware="screw_M3x8", fit="clearance",
        nominal_mm={"d": 3, "count": 4, "pcd": pcd},
        frame={"origin": [0, 0, 0], "axis": [0, 0, 1]},
    )


def _asiento(ancho=6) -> Interface:
    return Interface(
        id="IF-PILOTO", state="resolved", type="bearing_seat",
        between=["soporte", "nema17"], hardware="nema17_pilot", fit="press",
        nominal_mm={"bore": 5, "od": 22, "width": ancho},
        frame={"origin": [0, 0, 0], "axis": [0, 0, 1]},
    )


def test_las_aserciones_llevan_el_frame_y_la_consulta_del_contrato():
    """La aserción dice DÓNDE buscar y QUÉ buscar: sin eso el QA tendría
    que pedirle al constructor que le señale qué medir (ADR-011)."""
    diametro = next(a for a in derive_assertions(_asiento(), PERFIL)
                    if a.name == "hole_diameter")

    assert diametro.frame.origin == [0, 0, 0]
    assert diametro.query == {"kind": "bore"}


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_soporte_bien_hecho_pasa_la_capa_1(tmp_path):
    step = _nema17(tmp_path)

    aserciones = measure_interfaces([_patron()], step, Placement(), PERFIL, _freecadcmd())
    informe = QaReport(part="soporte", assertions=aserciones)

    medidas = {a.name: a.measured for a in aserciones}
    assert medidas["hole_count"] == 4
    assert medidas["hole_diameter"] == pytest.approx(3.3)
    assert medidas["pcd"] == pytest.approx(PCD_CUADRO_31)
    assert informe.verdict == "PASS"


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_agujeros_en_el_sitio_equivocado_no_se_miden_se_declaran_ausentes(tmp_path):
    """Pieza construida con cuadro de 35 donde el contrato dice 31. Con
    etiquetas se habrían medido Ø3.3 correctos. Buscando por contrato:
    ningún agujero donde debe estar → FAIL con el motivo correcto."""
    step = _nema17(tmp_path, paso=35)

    aserciones = measure_interfaces([_patron()], step, Placement(), PERFIL, _freecadcmd())

    medidas = {a.name: a.measured for a in aserciones}
    assert medidas["hole_count"] == 0
    assert medidas["hole_diameter"] is None
    assert QaReport(part="soporte", assertions=aserciones).verdict == "FAIL"


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_taladro_sin_holgura_aplicada_falla_por_la_cota(tmp_path):
    """Pieza con Ø22 exacto donde el ajuste a presión exige 22.10: el
    agujero existe y se mide, pero la cota no cumple. Es lo que debe
    corregir el Tolerances Agent (F2.11 (tolerances))."""
    step = _nema17(tmp_path, taladro=22.0)

    aserciones = measure_interfaces([_asiento()], step, Placement(), PERFIL, _freecadcmd())
    diametro = next(a for a in aserciones if a.name == "hole_diameter")

    assert diametro.measured == pytest.approx(22.0)
    assert diametro.ok is False


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_pieza_desplazada_en_el_ensamble_se_mide_en_sus_coordenadas(tmp_path):
    """El frame del contrato está en coordenadas del ensamble. Si la pieza
    está 45 mm más arriba, su placement lleva el frame a coordenadas de la
    pieza y el agujero se encuentra igual."""
    step = _nema17(tmp_path)
    # model_copy(update=...) no valida: se reconstruye para que frame sea Frame
    arriba = Interface(**{**_patron().model_dump(),
                          "frame": {"origin": [0, 0, 45], "axis": [0, 0, 1]}})

    aserciones = measure_interfaces(
        [arriba], step, Placement(origin=[0, 0, 45]), PERFIL, _freecadcmd()
    )

    assert QaReport(part="soporte", assertions=aserciones).verdict == "PASS"


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_habria_detectado_el_bug_real_del_agujero_de_3_2(tmp_path):
    """El fallo real de la Fase 1: se pidió M3 a 3.3 mm, el Part Designer
    rellenó con Ø3.2 y la pieza salió "bien" sin ningún error. Con la capa
    1 del QA, ese agujero se mide contra el contrato y cae."""
    step = _nema17(tmp_path, agujero=3.2)

    aserciones = measure_interfaces([_patron()], step, Placement(), PERFIL, _freecadcmd())
    diametro = next(a for a in aserciones if a.name == "hole_diameter")

    assert diametro.measured == pytest.approx(3.2)
    assert diametro.ok is False
    assert QaReport(part="soporte", assertions=aserciones).verdict == "FAIL"
