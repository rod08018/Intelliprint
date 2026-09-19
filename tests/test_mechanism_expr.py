"""Expresiones del movimiento de un mecanismo (F3.15 (mecanismos)).

Las escribe el Mechanism Designer (un LLM) y las evalúa el código. Por eso
no se usa eval(): un evaluador con lista blanca de nodos, nombres y
funciones. Ángulos en grados, como en todo el sistema.
"""

import math

import pytest

from orchestrator.mechanisms.expr import ExprError, check_expr, evaluate


def test_aritmetica_y_trigonometria_en_grados():
    assert evaluate("2 * sin(t) + 1", {"t": 90}) == pytest.approx(3)
    assert evaluate("asin(0.5)", {}) == pytest.approx(30)
    assert evaluate("atan2(1, 1)", {}) == pytest.approx(45)
    assert evaluate("sqrt(L**2 - 9)", {"L": 5}) == pytest.approx(4)


def test_la_biela_manivela_se_escribe_como_expresion():
    r, l, t = 30, 90, 40
    esperado = r * math.cos(math.radians(t)) + math.sqrt(l**2 - (r * math.sin(math.radians(t)))**2)
    assert evaluate("r*cos(t) + sqrt(l**2 - (r*sin(t))**2)", {"r": r, "l": l, "t": t}) == pytest.approx(esperado)


def test_funciones_por_tramos():
    assert evaluate("min(t, 10)", {"t": 30}) == 10
    assert evaluate("mod(t, 30)", {"t": 70}) == pytest.approx(10)
    assert evaluate("floor(t / 30)", {"t": 70}) == 2
    assert evaluate("clamp(t, 0, 5)", {"t": 9}) == 5
    assert evaluate("t if t < 10 else 20 - t", {"t": 15}) == 5


@pytest.mark.parametrize("peligrosa", [
    "__import__('os').system('ls')",
    "t.__class__",
    "open('x')",
    "[x for x in (1,2)]",
    "lambda: 1",
    "t; 1",
])
def test_rechaza_todo_lo_que_no_sea_una_formula(peligrosa):
    with pytest.raises(ExprError):
        check_expr(peligrosa, {"t"})


def test_un_nombre_desconocido_se_rechaza_antes_de_evaluar():
    with pytest.raises(ExprError, match="radio"):
        check_expr("radio * cos(t)", {"t"})


def test_fuera_de_dominio_da_un_error_legible():
    with pytest.raises(ExprError, match="sqrt"):
        evaluate("sqrt(1 - 2)", {})
