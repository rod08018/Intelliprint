"""Qué puede hacer el programa del diseñador (F5.18 (kit)). Lista blanca.

El programa lo escribe un modelo y se ejecuta dentro de FreeCAD, que puede
leer y escribir cualquier archivo. Lo que lo hace seguro no es confiar en
el modelo, sino que aquí solo pasa:

- una función `construir(kit)` (y funciones auxiliares, y constantes);
- aritmética, bucles `for`, condiciones, listas, tuplas y diccionarios;
- los atributos de la API del kit (`mech_toolkit.kit.API`) y los métodos
  de lista y diccionario, y nada más: ningún `_algo`, ningún `__class__`,
  ningún `gi_frame`. Con atributos libres, `().__class__.__bases__` abre
  la puerta a todo Python;
- unas pocas funciones (`range`, `len`, `min`…) y las de `math`.

Sin `import`, sin `open`, sin `eval`, sin clases, sin `try` (esconde los
fallos que el diseñador tiene que ver), sin `global`. Lo que no está en la
lista no pasa, aunque parezca inofensivo: así una construcción nueva de
Python no abre un agujero sin que nadie lo decida.
"""

import ast
import math

from mech_toolkit.kit import API


class ProgramaInvalido(ValueError):
    """El programa usa algo que no está permitido. ValueError: así entra en el
    bucle de reintento de `structured` como un error de esquema más."""


FUNCIONES = {
    "range": range, "len": len, "min": min, "max": max, "abs": abs, "round": round,
    "float": float, "int": int, "list": list, "tuple": tuple, "dict": dict,
    "enumerate": enumerate, "zip": zip, "sum": sum, "sorted": sorted,
    "reversed": reversed, "bool": bool, "str": str, "isinstance": None,
}
del FUNCIONES["isinstance"]   # sin tipos a mano: no hacen falta para dibujar

MATEMATICAS = {n: getattr(math, n) for n in (
    "sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "radians",
    "degrees", "hypot", "floor", "ceil", "pi")}

NOMBRES = {"__builtins__": dict(FUNCIONES), **MATEMATICAS}
"""El entorno del programa al ejecutarse: lo único que ve."""

ATRIBUTOS = API | {"append", "extend", "insert", "pop", "index", "count",
                   "items", "keys", "values", "get"}

_NODOS = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
    ast.AugAssign, ast.AnnAssign, ast.For, ast.If, ast.Expr, ast.Pass, ast.Break,
    ast.Continue, ast.Name, ast.Load, ast.Store, ast.Constant, ast.Attribute,
    ast.Call, ast.keyword, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.IfExp, ast.Subscript, ast.Slice, ast.List, ast.Tuple, ast.Dict,
    ast.ListComp, ast.GeneratorExp, ast.DictComp, ast.comprehension,
    ast.JoinedStr, ast.FormattedValue, ast.Starred,
    ast.operator, ast.unaryop, ast.boolop, ast.cmpop,
)

_POR_NOMBRE = {
    ast.Import: "import", ast.ImportFrom: "import", ast.ClassDef: "class",
    ast.Global: "global", ast.Nonlocal: "nonlocal", ast.Try: "try",
    ast.While: "while", ast.With: "with", ast.Lambda: "lambda",
    ast.Delete: "del", ast.Raise: "raise", ast.Yield: "yield",
    ast.YieldFrom: "yield", ast.Await: "await", ast.AsyncFunctionDef: "async",
}

MAX_CARACTERES = 30_000


def _fallo(nodo, motivo: str) -> ProgramaInvalido:
    return ProgramaInvalido(f"línea {getattr(nodo, 'lineno', '?')}: {motivo}")


def validar(codigo: str) -> None:
    """Lanza `ProgramaInvalido` con la línea y el motivo si algo no pasa."""
    if len(codigo) > MAX_CARACTERES:
        raise ProgramaInvalido(f"el programa pasa de {MAX_CARACTERES} caracteres")
    try:
        arbol = ast.parse(codigo, filename="programa.py")
    except SyntaxError as e:
        raise ProgramaInvalido(f"línea {e.lineno}: error de sintaxis: {e.msg}") from None

    for nodo in ast.walk(arbol):
        prohibido = next((n for t, n in _POR_NOMBRE.items() if isinstance(nodo, t)), None)
        if prohibido:
            raise _fallo(nodo, f"`{prohibido}` no está permitido")
        if not isinstance(nodo, _NODOS):
            raise _fallo(nodo, f"`{type(nodo).__name__}` no está permitido")
        if isinstance(nodo, ast.FunctionDef) and nodo.decorator_list:
            raise _fallo(nodo, "los decoradores no están permitidos")
        if isinstance(nodo, ast.Name) and nodo.id.startswith("_"):
            raise _fallo(nodo, f"`{nodo.id}`: los nombres que empiezan por _ no están permitidos")
        if isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Load) \
                and nodo.id in _PELIGROSOS:
            raise _fallo(nodo, f"`{nodo.id}` no está permitido")
        if isinstance(nodo, ast.Attribute) and nodo.attr not in ATRIBUTOS:
            raise _fallo(nodo, f"`.{nodo.attr}` no es del kit: solo puedes usar sus "
                               "operaciones")

    for nodo in arbol.body:
        constante = (isinstance(nodo, ast.Assign)
                     and all(isinstance(t, ast.Name) for t in nodo.targets))
        if not isinstance(nodo, ast.FunctionDef) and not constante:
            raise _fallo(nodo, "en el nivel superior solo van `def` y constantes "
                               "(`SEP = 60`); el resto, dentro de `construir`")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "construir" for n in arbol.body):
        raise ProgramaInvalido("falta la función `construir(kit)`, que devuelve la pieza")


_PELIGROSOS = {"open", "eval", "exec", "compile", "getattr", "setattr", "delattr",
               "globals", "locals", "vars", "input", "breakpoint", "help", "type",
               "object", "super", "dir", "id", "memoryview", "classmethod",
               "staticmethod", "property", "print", "exit", "quit"}
"""Ya no existen en el entorno (`NOMBRES`), pero un error que diga «no está
permitido» le explica más al diseñador que un NameError al ejecutar."""
