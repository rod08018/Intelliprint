"""Evaluador seguro de las expresiones de movimiento (F3.15 (mecanismos)).

Las fórmulas las escribe el Mechanism Designer, un LLM. No se usa eval():
se recorre el árbol sintáctico con una lista blanca de nodos, nombres y
funciones. Todo lo demás se rechaza ANTES de evaluar, con un motivo que
vuelve al agente.

Ángulos en grados, como en el resto del sistema: sin(90) = 1, asin(1) = 90.
"""

import ast
import math


class ExprError(ValueError):
    pass


def _grados(f):
    return lambda x: f(math.radians(x))


def _a_grados(f):
    return lambda *a: math.degrees(f(*a))


FUNCIONES = {
    "sin": _grados(math.sin), "cos": _grados(math.cos), "tan": _grados(math.tan),
    "asin": _a_grados(math.asin), "acos": _a_grados(math.acos),
    "atan": _a_grados(math.atan), "atan2": _a_grados(math.atan2),
    "sqrt": math.sqrt, "abs": abs, "min": min, "max": max,
    "floor": math.floor, "ceil": math.ceil, "mod": lambda a, b: a % b,
    "clamp": lambda x, lo, hi: max(lo, min(hi, x)),
}
CONSTANTES = {"pi": math.pi}

_BINARIOS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
             ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
             ast.Pow: lambda a, b: a ** b, ast.Mod: lambda a, b: a % b}
_COMPARA = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
            ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b}


def _parse(texto: str) -> ast.expr:
    try:
        return ast.parse(texto, mode="eval").body
    except SyntaxError as e:
        raise ExprError(f"{texto!r} no es una fórmula válida: {e.msg}") from None


def _nombres(nodo: ast.AST, texto: str) -> set[str]:
    usados = set()
    for n in ast.walk(nodo):
        if isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id not in FUNCIONES or n.keywords:
                raise ExprError(f"{texto!r}: solo se permiten las funciones {sorted(FUNCIONES)}")
        elif isinstance(n, ast.Name):
            if not (n.id in FUNCIONES or n.id in CONSTANTES):
                usados.add(n.id)
        elif isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float)) or isinstance(n.value, bool):
                raise ExprError(f"{texto!r}: solo números, no {n.value!r}")
        elif not isinstance(n, (ast.BinOp, ast.UnaryOp, ast.IfExp, ast.Compare, ast.Load,
                                ast.USub, ast.UAdd, *_BINARIOS, *_COMPARA)):
            raise ExprError(f"{texto!r}: {type(n).__name__} no está permitido en una fórmula")
    return usados


def check_expr(texto: str, variables: set[str]) -> None:
    """Rechaza la fórmula si usa algo fuera de la lista blanca o un nombre
    que no está definido."""
    desconocidos = _nombres(_parse(texto), texto) - set(variables)
    if desconocidos:
        raise ExprError(
            f"{texto!r} usa {sorted(desconocidos)}, que no están definidos. "
            f"Disponibles: {sorted(variables)} y las funciones {sorted(FUNCIONES)}"
        )


def evaluate(texto: str, variables: dict[str, float]) -> float:
    nodo = _parse(texto)
    check_expr(texto, set(variables))

    def ev(n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            return CONSTANTES[n.id] if n.id in CONSTANTES else variables[n.id]
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp):
            return _BINARIOS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        if isinstance(n, ast.Compare):
            izq = ev(n.left)
            for op, der in zip(n.ops, n.comparators):
                if type(op) not in _COMPARA:
                    raise ExprError(f"{texto!r}: comparación no permitida")
                d = ev(der)
                if not _COMPARA[type(op)](izq, d):
                    return False
                izq = d
            return True
        if isinstance(n, ast.Call):
            return FUNCIONES[n.func.id](*[ev(a) for a in n.args])
        raise ExprError(f"{texto!r}: {type(n).__name__} no está permitido")

    try:
        valor = ev(nodo)
    except (ValueError, ZeroDivisionError, OverflowError, TypeError) as e:
        raise ExprError(
            f"{texto!r} no se puede evaluar con {variables}: {e} "
            "(¿sqrt/asin/acos fuera de dominio o división por cero?)"
        ) from None
    if isinstance(valor, complex):
        raise ExprError(f"{texto!r} da un número complejo con {variables}")
    return float(valor)
