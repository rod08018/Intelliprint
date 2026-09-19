"""Cliente de DeepSeek.

Se prueba contra `httpx.MockTransport`, que ejercita el código real de
httpx (serialización, cabeceras, parseo) sin salir a la red.
"""

import httpx
import pytest

from orchestrator.llm.providers.deepseek import DeepSeekClient


def test_envia_la_clave_y_el_modelo_y_devuelve_el_contenido():
    peticiones: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    cliente = DeepSeekClient(
        api_key="sk-prueba",
        model="deepseek-chat",
        transport=httpx.MockTransport(responder),
    )

    assert cliente.complete("hola") == '{"ok": true}'

    enviada = peticiones[0]
    assert enviada.headers["authorization"] == "Bearer sk-prueba"
    assert b'"deepseek-chat"' in enviada.content


def test_un_error_http_no_se_confunde_con_una_respuesta_del_modelo():
    """Un 401 o un 429 tienen que romper, no devolver texto raro que luego
    falle la validación del esquema y consuma los tres reintentos."""

    cliente = DeepSeekClient(
        api_key="sk-mala",
        model="deepseek-chat",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": "invalid key"})
        ),
    )

    with pytest.raises(httpx.HTTPStatusError):
        cliente.complete("hola")
