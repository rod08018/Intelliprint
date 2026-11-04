"""El programa del diseñador: `construir(kit)` en Python (F5.18 (kit)).

Sustituye a la receta para las piezas sueltas: la receta solo podía llamar
a generadores de cajas y cilindros. Ver ADR-002, enmienda.
"""

import ast

from pydantic import BaseModel, field_validator

from mech_toolkit.kit.sandbox import validar


class Programa(BaseModel):
    part: str
    codigo: str
    """El programa: una función `construir(kit)` que devuelve la pieza."""

    @field_validator("codigo")
    @classmethod
    def _seguro(cls, codigo: str) -> str:
        # En el esquema y no en el agente: así un programa que no pasa la lista
        # blanca no existe como objeto, y nadie puede llegar a construirlo.
        validar(codigo)
        return codigo

    def numeros(self) -> list[float]:
        """Las constantes numéricas del programa, para la trazabilidad
        (F1.16 (trazabilidad)): una cota de la petición tiene que aparecer
        escrita. Con variables (`SEP = 60`) aparece aunque luego se sume."""
        return [float(n.value) for n in ast.walk(ast.parse(self.codigo))
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                and not isinstance(n.value, bool)]
