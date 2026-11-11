"""Trazabilidad petición → receta (F1.16 (trazabilidad)).

El bug real: se pidió "agujeros de 3.3 mm", el resumen perdió la cota y
el diseñador puso Ø3.2 sacado de lo que sabe de un NEMA17. La pieza
salió bien construida, con un valor que contradecía la petición, y
ningún test lo vio. Esta guardia es determinista: no pregunta a ningún
modelo si la receta respeta la petición, compara números.
"""

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.build import design_and_build
from orchestrator.schemas.recipe import Recipe, RecipeStep
from orchestrator.traceability import requested_dimensions, untraced
from tests.test_generators import _freecadcmd

PETICION = "placa de 60x60x6 mm con taladro central de 22 mm y agujeros de 3.3 mm en cuadro de 31 mm"


def _receta(agujero: float) -> Recipe:
    return Recipe(part="p", steps=[
        RecipeStep(generator="generate_plate",
                   params={"length_mm": 60, "width_mm": 60, "thickness_mm": 6}),
        RecipeStep(generator="generate_center_bore", params={"diameter_mm": 22}),
        RecipeStep(generator="generate_square_bolt_pattern",
                   params={"hole_diameter_mm": agujero, "pitch_mm": 31}),
    ])


def test_extrae_las_cotas_con_unidad_de_la_peticion():
    assert sorted(requested_dimensions(PETICION)) == sorted([60, 60, 6, 22, 3.3, 31])


def test_no_confunde_designaciones_con_cotas():
    """NEMA17, M3 y perfil 2020 son nombres, no medidas."""
    assert requested_dimensions("soporte NEMA17 con tornillos M3 para perfil 2020") == []


def test_acepta_coma_decimal():
    assert requested_dimensions("agujero de 3,3 mm") == [3.3]


def test_detecta_la_cota_que_la_receta_perdio():
    """El Ø3.2 de hoy."""
    assert untraced(PETICION, _receta(3.2)) == [3.3]
    assert untraced(PETICION, _receta(3.3)) == []


class DisenadorGuionizado:
    """Un diseñador con las recetas escritas: lo que se prueba es qué le
    devuelve el bucle de construcción (`rechazos`), no un agente."""

    def __init__(self, recetas):
        self._r = list(recetas)
        self.rechazos = []

    def design(self, tarea, rechazo=None):
        self.rechazos.append(rechazo)
        return self._r.pop(0)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_cota_perdida_vuelve_al_disenador_con_el_valor(tmp_path):
    agente = DisenadorGuionizado([_receta(3.2), _receta(3.3)])

    receta, resultado = design_and_build(
        agente, "brief", CATALOGO, tmp_path, freecadcmd=_freecadcmd(), request=PETICION,
    )

    assert receta.steps[2].params["hole_diameter_mm"] == 3.3
    assert "3.3 mm" in agente.rechazos[1][1]
    assert resultado.untraced_mm == []


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_si_insiste_se_construye_pero_queda_anotado(tmp_path):
    """La guardia es heurística: si la cota sigue sin aparecer tras los
    reintentos, no rompe la construcción. Queda anotada para el informe."""
    _, resultado = design_and_build(
        DisenadorGuionizado([_receta(3.2)] * 3), "brief", CATALOGO, tmp_path,
        freecadcmd=_freecadcmd(), request=PETICION,
    )

    assert resultado.untraced_mm == [3.3]
