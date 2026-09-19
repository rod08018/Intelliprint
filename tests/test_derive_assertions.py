"""Capa 1 del QA: las aserciones se derivan del contrato de interfaces.

Ver SISTEMA_MULTIAGENTE.md § 3.3 y § 7.1, y DECISIONES.md ADR-003.
"""

import pytest

from mech_toolkit.assertions import SinReglaDeDerivacion, derive_assertions
from mech_toolkit.profile import PrinterProfile
from orchestrator.schemas.interface import Interface

PERFIL = PrinterProfile(
    id="prusa_mk4_petg",
    fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35},
    holes={"M3_through_mm": 3.3},
    assertion_tol_mm=0.05,
)


def _asiento_608zz() -> Interface:
    return Interface(
        id="IF-003",
        state="resolved",
        type="bearing_seat",
        between=["base_giratoria", "hombro"],
        hardware="bearing_608zz",
        fit="press",
        nominal_mm={"bore": 8, "od": 22, "width": 7},
        frame={"origin": [0, 0, 45], "axis": [0, 0, 1]},
    )


def test_un_asiento_a_presion_exige_el_diametro_exterior_mas_la_holgura():
    """Ø22 nominal + 0.10 de press fit = Ø22.10. Aritmética, no criterio.

    Este número no lo decide ningún modelo: sale del `od` de la librería
    de hardware y del perfil de la impresora.
    """
    aserciones = derive_assertions(_asiento_608zz(), PERFIL)

    diametro = next(a for a in aserciones if a.name == "hole_diameter")
    assert diametro.expected == pytest.approx(22.10)
    assert diametro.tol == pytest.approx(0.05)
    assert diametro.unit == "mm"
    assert diametro.interface == "IF-003"


def test_un_tipo_sin_regla_falla_en_vez_de_devolver_lista_vacia():
    """Cero aserciones significaría que la capa 1 aprueba cualquier cosa.

    Es el fallo silencioso más peligroso del QA: al añadir un tipo de
    interfaz nuevo sin escribir su derivación, esa interfaz quedaría sin
    verificar y la pieza pasaría por el hueco. Mejor romper ruidosamente.
    """
    cable = Interface(
        id="IF-009",
        state="resolved",
        type="cable_pass",
        between=["base", "hombro"],
        hardware="cable_2x22awg",
        fit="clearance",
        nominal_mm={"d": 6},
        frame={"origin": [0, 0, 10], "axis": [0, 0, 1]},
    )

    with pytest.raises(SinReglaDeDerivacion, match="cable_pass"):
        derive_assertions(cable, PERFIL)


def _patron_m3() -> Interface:
    return Interface(
        id="IF-004",
        state="resolved",
        type="bolt_pattern",
        between=["hombro", "eslabon_1"],
        hardware="screw_M3x12",
        fit="clearance",
        nominal_mm={"d": 3, "count": 4, "pcd": 30},
        frame={"origin": [0, 0, 60], "axis": [0, 0, 1]},
    )


def test_un_patron_de_tornillos_usa_la_tabla_de_agujeros_y_no_el_calculo():
    """Distinción que importa: 3.3 tabulado, no 3 + 0.35 calculado.

    Para tornillería, el diámetro de paso es un valor de tabla del perfil
    (§ 7), afinado con impresiones reales. Calcularlo como nominal+holgura
    daría 3.35 y sería *más* holgado de lo que la práctica recomienda.
    Cuando hay dato tabulado, gana al cálculo.
    """
    aserciones = derive_assertions(_patron_m3(), PERFIL)
    por_nombre = {a.name: a for a in aserciones}

    assert por_nombre["hole_diameter"].expected == pytest.approx(3.3)
    assert por_nombre["hole_count"].expected == 4
    assert por_nombre["hole_count"].unit == "count"
    assert por_nombre["pcd"].expected == pytest.approx(30)
