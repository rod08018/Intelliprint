"""Salida estructurada con validación y reintento (F1.3 (estructurada)).

Ningún agente devuelve texto libre: todos devuelven un esquema validado.
Cuando la validación falla, se le reenvía al modelo **el error exacto**,
que es mucho más útil que repetir la misma petición.
"""

from typing import Callable, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from orchestrator.llm.providers.deepseek import (
    ConexionCaida, RespuestaCortada, TiempoAgotado)

T = TypeVar("T", bound=BaseModel)

CORTES_ANTES_DE_LA_RESERVA = 2
"""Dos cortes ya demuestran que no es mala suerte: es que no cabe."""

MAX_INTENTOS = 3


class SalidaInvalida(ValueError):
    """El modelo no produjo un esquema válido tras agotar los intentos.

    Lleva cada intento —la respuesta tal cual y por qué se rechazó— para que
    quien la capture pueda guardarlo. Fallo real: el trinquete se paró con
    tres especificaciones rechazadas y las tres se habían tirado; no había
    forma de saber si fallaba el modelo o la regla que lo rechazaba.
    """

    def __init__(self, mensaje: str, intentos: list[dict] | None = None) -> None:
        super().__init__(mensaje)
        self.intentos: list[dict] = intentos or []


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


def structured(
    client: LlmClient,
    prompt: str,
    schema: type[T],
    *,
    max_intentos: int = MAX_INTENTOS,
    extra_validation: Callable[[T], None] | None = None,
    cliente_de_reserva: LlmClient | None = None,
) -> T:
    """Pide una salida que valide contra `schema`, reintentando con el error.

    `extra_validation` cubre lo que el esquema no puede saber por sí solo
    —por ejemplo, si una receta llama a un generador que existe— y entra
    en el mismo bucle: si quedara fuera, ese fallo no tendría reintento.

    `cliente_de_reserva` es un modelo **sin pensamiento** al que se pasa la
    pelota cuando el razonador se corta dos veces. A un razonador no se le
    puede pedir que piense menos —su pensamiento cuenta dentro de
    `max_tokens` y lo decide él—, así que insistir es quemar dinero: el
    Geneva drive gastó 187.000 tokens en tres cortes seguidos sin sacar un
    diseño. Uno sin pensamiento tiene todo el presupuesto para el JSON.
    """
    peticion = prompt
    ultimo_error = ""
    cortes = 0
    intentos: list[dict] = []

    for intento in range(1, max_intentos + 1):
        try:
            se_rindio = cortes >= CORTES_ANTES_DE_LA_RESERVA and cliente_de_reserva
            respuesta = (cliente_de_reserva if se_rindio else client).complete(peticion)
        except (RespuestaCortada, TiempoAgotado, ConexionCaida) as error:
            # Se quedó sin sitio pensando: no es un JSON malo, es longitud. Se
            # reintenta pidiendo brevedad en vez de tumbar el proyecto entero
            # (fallo real: el trinquete murió aquí tras 12 minutos).
            ultimo_error = str(error)
            intentos.append({"intento": intento, "respuesta": None, "error": ultimo_error,
                             "reserva": bool(se_rindio)})
            cortes += 1
            peticion = (
                f"{prompt}\n\n--- Intento {intento} cortado ({error}) ---\n"
                "Te quedaste sin espacio antes de terminar. Razona menos y responde "
                "ya, con el JSON más corto posible: enunciados breves y solo lo "
                "imprescindible.\n"
            )
            continue
        try:
            resultado = schema.model_validate_json(respuesta)
            if extra_validation is not None:
                extra_validation(resultado)
            return resultado
        except (ValidationError, ValueError) as error:
            ultimo_error = str(error)
            intentos.append({"intento": intento, "respuesta": respuesta, "error": ultimo_error,
                             "reserva": bool(se_rindio)})
            peticion = _reintento(prompt, respuesta, ultimo_error, intento)

    raise SalidaInvalida(
        f"{schema.__name__}: {max_intentos} intentos sin salida válida. "
        f"Último error:\n{ultimo_error}",
        intentos,
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
