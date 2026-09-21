"""Cada ronda, guardada como DATO y en el momento (F5.5 (web)).

La interfaz enseña en qué ronda va un proyecto, qué falló, qué dijo el
diseñador que iba a cambiar y cuánto se acercó a lo pedido. Hasta ahora
nada de eso existía mientras el trabajo corría: rounds.json se escribía al
terminar, y las mediciones acababan convertidas en frases para el revisor.

Lo que se mide aquí es aritmética del código, no un juicio (ADR-003).
"""

import pytest

from orchestrator.assembly import Collision
from orchestrator.mechanisms.resumen import resumen_de_ronda
from orchestrator.mechanisms.run import MechanismReport
from orchestrator.mechanisms.spec_layout import SpecLayout
from orchestrator.schemas.mechanism import MechanismSpec
from tests.test_mechanism_flow import _correccion, _spec


def _informe(choques=()):
    return MechanismReport(parts={}, assembly="assembly.FCStd", animation=None,
                           angles=[0, 45, 90], min_gap_mm=0.1, collisions=list(choques))


def _resumen(spec_dict, choques=(), feedback=""):
    spec = MechanismSpec(**spec_dict)
    return resumen_de_ronda(1, spec, SpecLayout(spec), _informe(choques), feedback)


def test_un_requisito_medido_lleva_esperado_tolerancia_medido_y_desviacion():
    """Oráculo a mano: el brazo gira de 0 a 90 y se pide 90 ± 1."""
    (req,) = _resumen(_spec(0.5))["requisitos"]
    assert req["descripcion"] == "gira 90°"
    assert req["esperado"] == 90 and req["tolerancia"] == 1
    assert req["medido"] == pytest.approx(90.0, abs=1e-6)
    assert req["desviacion"] == pytest.approx(0.0, abs=1e-6)
    assert req["cumple"] is True


def test_un_requisito_fuera_de_tolerancia_no_cumple():
    s = _spec(0.5)
    s["checks"][0]["expected"] = 120   # gira 90, se piden 120 ± 1
    (req,) = _resumen(s)["requisitos"]
    assert req["cumple"] is False
    assert req["desviacion"] == pytest.approx(-30.0, abs=1e-6)


def test_el_barrido_cuenta_choques_y_da_el_peor_hueco():
    choques = [Collision(angle=0, a="base", b="brazo", gap_mm=-3.5, min_gap_mm=0.1),
               Collision(angle=45, a="base", b="brazo", gap_mm=-1.0, min_gap_mm=0.1)]
    barrido = _resumen(_spec(-2.0), choques)["barrido"]
    assert barrido == {"posiciones": 3, "hueco_minimo_mm": 0.1, "choques": 2,
                       "peor_hueco_mm": -3.5, "pares": [["base", "brazo"]]}


def test_sin_choques_el_barrido_esta_limpio():
    barrido = _resumen(_spec(0.5))["barrido"]
    assert barrido["choques"] == 0 and barrido["peor_hueco_mm"] is None


def test_el_plan_del_disenador_y_lo_que_volvio_quedan_juntos():
    """Es la historia de la ronda: qué dijo que iba a cambiar, y qué pasó."""
    r = _resumen(_correccion(0.5), feedback="- base / brazo: chocan")
    assert r["plan"]["cambio"] == "ajusto la altura"
    assert r["feedback"] == "- base / brazo: chocan"
    assert r["resuelta"] is False


def test_una_ronda_sin_fallos_esta_resuelta():
    assert _resumen(_spec(0.5))["resuelta"] is True


def test_lo_que_se_mueve_por_formula_se_distingue_de_lo_verificado():
    """El brazo se mueve porque su fórmula lo dice: nadie comprueba que lo
    cause el mecanismo. La interfaz tiene que poder decirlo."""
    r = _resumen(_spec(0.5))
    assert r["impuesto_por_formula"] == ["brazo"]
    assert r["verificado"] == {"contactos": 0, "topes": 0, "bloqueos": 0, "apoyos": 0}


def test_una_ronda_que_no_llego_al_barrido_no_hereda_el_de_otra():
    """Si una pieza no se pudo dibujar, esa ronda no montó nada. Enseñar el
    barrido de la ronda anterior como si fuera suyo sería mentir."""
    spec = MechanismSpec(**_spec(0.5))
    r = resumen_de_ronda(2, spec, SpecLayout(spec), None, "- la pieza «brazo» no se pudo dibujar")
    assert r["barrido"] is None
    assert r["resuelta"] is False


def test_un_requisito_que_no_se_puede_medir_lo_dice_en_vez_de_romper():
    class LayoutQueNoMide:
        def frames(self):
            return [0, 90]

        class kin:
            @staticmethod
            def measure(check, frames):
                raise ValueError("«brazo» se apoya en «base» y el apoyo no está resuelto")

    spec = MechanismSpec(**_spec(0.5))
    (req,) = resumen_de_ronda(1, spec, LayoutQueNoMide(), _informe(), "x")["requisitos"]
    assert req["medido"] is None and req["cumple"] is None
    assert "apoyo no está resuelto" in req["nota"]
