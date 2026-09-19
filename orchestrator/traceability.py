"""Trazabilidad petición → receta (F1.16 (trazabilidad)).

Guardia determinista: las cotas con unidad que escribió el usuario tienen
que aparecer en la receta del Part Designer. No se le pregunta a ningún
modelo si la receta respeta la petición: se comparan números.

Es una heurística, y por eso es conservadora:
- Solo cuenta como cota un número seguido de "mm" o un patrón "AxB[xC]".
  "NEMA17", "M3" o "perfil 2020" son nombres, no medidas.
- Se comprueba a la salida del Part Designer, ANTES de aplicar holguras:
  el Tolerances Agent (F2.11 (tolerances)) cambiará 22 por 22.35 a propósito.
- Si tras los reintentos una cota sigue sin aparecer, no se rompe la
  construcción: se anota para el informe (puede ser un radio que el
  generador pide como diámetro, por ejemplo).
"""

import re

from orchestrator.schemas.recipe import Recipe

_NUM = r"\d+(?:[.,]\d+)?"
_MATRIZ = re.compile(rf"({_NUM})\s*[x×]\s*({_NUM})(?:\s*[x×]\s*({_NUM}))?(?:\s*mm)?", re.I)
_CON_UNIDAD = re.compile(rf"({_NUM})\s*mm\b", re.I)


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def requested_dimensions(peticion: str) -> list[float]:
    cotas: list[float] = []
    ocupado: list[tuple[int, int]] = []
    for m in _MATRIZ.finditer(peticion):
        cotas.extend(_numero(g) for g in m.groups() if g is not None)
        ocupado.append(m.span())
    for m in _CON_UNIDAD.finditer(peticion):
        if not any(a <= m.start() < b for a, b in ocupado):
            cotas.append(_numero(m.group(1)))
    return cotas


def untraced(peticion: str, receta: Recipe, tol: float = 1e-6) -> list[float]:
    """Cotas de la petición que no aparecen en ningún parámetro de la receta."""
    valores = [
        float(v) for paso in receta.steps for v in paso.params.values()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    perdidas: list[float] = []
    for cota in requested_dimensions(peticion):
        # El signo no es parte de la cota: "4 mm por debajo" es -4 en la receta.
        if not any(abs(abs(v) - cota) <= tol for v in valores) and cota not in perdidas:
            perdidas.append(cota)
    return perdidas
