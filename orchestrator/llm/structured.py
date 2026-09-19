"""Salida estructurada con validación y reintento (F1.2).

Ningún agente devuelve texto libre: todos devuelven un esquema validado.
Cuando la validación falla, se le reenvía al modelo **el error exacto**,
que es mucho más útil que repetir la misma petición.
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

MAX_INTENTOS = 3


class SalidaInvalida(ValueError):
    """El modelo no produjo un esquema válido tras agotar los intentos."""


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


def structured(
    client: LlmClient,
    prompt: str,
    schema: type[T],
    *,
    max_intentos: int = MAX_INTENTOS,
) -> T:
    peticion = prompt
    ultimo_error = ""

    for intento in range(1, max_intentos + 1):
        respuesta = client.complete(peticion)
        try:
            return schema.model_validate_json(respuesta)
        except ValidationError as error:
            ultimo_error = str(error)
            peticion = _reintento(prompt, respuesta, ultimo_error, intento)

    raise SalidaInvalida(
        f"{schema.__name__}: {max_intentos} intentos sin salida válida. "
        f"Último error:\n{ultimo_error}"
    )


def _reintento(prompt: str, respuesta: str, error: str, intento: int) -> str:
    """Reenvía el error exacto, no solo 'inténtalo otra vez'.

    Un modelo que ve `alto_mm: Field required` corrige el campo concreto.
    Repetirle la misma petición suele producir el mismo fallo."""
    return (
        f"{prompt}\n\n"
        f"--- Intento {intento} rechazado ---\n"
        f"Tu respuesta:\n{respuesta}\n\n"
        f"No valida contra el esquema:\n{error}\n\n"
        "Devuelve SOLO el JSON corregido, sin texto alrededor."
    )
