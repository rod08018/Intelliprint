"""Salida estructurada: validar y reintentar con el error (F1.2).

Es la base de los once agentes: ninguno devuelve texto libre, todos
devuelven un esquema validado.
"""

import pytest
from pydantic import BaseModel

from orchestrator.llm.structured import SalidaInvalida, structured


class Pieza(BaseModel):
    nombre: str
    alto_mm: float


class ClienteGuionizado:
    """Cliente con respuestas predefinidas.

    No es un mock de la lógica que probamos: sustituye la frontera de red,
    que es lo único que no podemos ejercitar en un test rápido. Registra
    los prompts para poder comprobar QUÉ se le reenvía al reintentar.
    """

    def __init__(self, respuestas: list[str]) -> None:
        self._respuestas = list(respuestas)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._respuestas.pop(0)


def test_reintenta_cuando_la_respuesta_no_valida_y_acaba_devolviendo_el_modelo():
    cliente = ClienteGuionizado(
        [
            '{"nombre": "dedo_der"}',  # falta alto_mm
            '{"nombre": "dedo_der", "alto_mm": 12.5}',
        ]
    )

    pieza = structured(cliente, "diseña un dedo", Pieza)

    assert pieza.alto_mm == 12.5
    assert len(cliente.prompts) == 2


def test_el_reintento_incluye_el_error_exacto_y_no_solo_otra_vez():
    """El valor está en el contenido del reintento, no en que haya reintento.

    Un modelo que ve `alto_mm / Field required` corrige ese campo. Si solo
    le repites la petición, suele repetir el mismo fallo.
    """
    cliente = ClienteGuionizado(
        ['{"nombre": "dedo_der"}', '{"nombre": "dedo_der", "alto_mm": 12.5}']
    )

    structured(cliente, "diseña un dedo", Pieza)

    reintento = cliente.prompts[1]
    assert "alto_mm" in reintento
    assert "Field required" in reintento
    assert '{"nombre": "dedo_der"}' in reintento  # su propia respuesta
    assert "diseña un dedo" in reintento  # y la petición original


def test_agotar_los_intentos_falla_con_el_ultimo_error():
    """No se devuelve un objeto a medias ni se inventa un valor por defecto."""
    cliente = ClienteGuionizado(['{"nombre": "x"}'] * 3)

    with pytest.raises(SalidaInvalida, match="alto_mm"):
        structured(cliente, "diseña un dedo", Pieza)

    assert len(cliente.prompts) == 3


def test_una_respuesta_que_no_es_json_tambien_reintenta():
    """Los modelos envuelven el JSON en prosa o en ```json con frecuencia."""
    cliente = ClienteGuionizado(
        [
            "Claro, aquí tienes la pieza que pides:",
            '{"nombre": "dedo_der", "alto_mm": 12.5}',
        ]
    )

    assert structured(cliente, "diseña un dedo", Pieza).alto_mm == 12.5
