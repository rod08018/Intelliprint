"""Cliente de DeepSeek.

Se prueba contra `httpx.MockTransport`, que ejercita el código real de
httpx (serialización, cabeceras, parseo) sin salir a la red.
"""

import json

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


def test_una_respuesta_cortada_por_max_tokens_es_un_error_y_no_un_json_invalido():
    """Fallo real: deepseek-reasoner pensó 32 768 tokens y devolvió contenido
    vacío. Tratado como JSON inválido, se gastaban los 3 reintentos (6 min)."""
    from orchestrator.llm.providers.deepseek import RespuestaCortada

    cliente = DeepSeekClient(
        api_key="k", model="deepseek-reasoner",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
            "choices": [{"finish_reason": "length", "message": {"content": ""}}]})),
    )
    with pytest.raises(RespuestaCortada, match="max_tokens=393216"):
        cliente.complete("hola")


def test_el_modelo_de_razonamiento_va_sin_modo_json_y_se_le_quita_el_bloque_de_codigo():
    enviado = {}

    def responder(request):
        enviado.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                              "message": {"content": '```json\n{"a": 1}\n```'}}]})

    cliente = DeepSeekClient(api_key="k", model="deepseek-reasoner",
                             transport=httpx.MockTransport(responder))
    assert cliente.complete("hola") == '{"a": 1}'
    assert "response_format" not in enviado


def test_una_llamada_que_no_termina_se_corta_por_plazo_total():
    """Fallo real: 54 minutos colgado. El plazo de lectura de httpx se
    reinicia con cada byte, y DeepSeek manda caracteres de mantenimiento en
    las peticiones largas, así que nunca saltaba."""
    import time

    from orchestrator.llm.providers.deepseek import TiempoAgotado

    def goteo():
        for _ in range(100):
            time.sleep(0.05)
            yield b" "          # mantenimiento: datos que no son la respuesta

    cliente = DeepSeekClient(
        api_key="k", model="deepseek-chat", deadline_s=0.3,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=goteo())),
    )

    inicio = time.time()
    with pytest.raises(TiempoAgotado, match="0.3"):
        cliente.complete("hola")
    assert time.time() - inicio < 3


def test_una_respuesta_normal_llega_entera_aunque_venga_a_trozos():
    """El plazo no puede cortar una respuesta que sí está llegando."""
    cliente = DeepSeekClient(
        api_key="k", model="deepseek-chat", deadline_s=10,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=iter([
            b'{"choices": [{"finish_reason": "stop",',
            b' "message": {"content": "{\\"a\\": 1}"}}]}',
        ]))),
    )

    assert cliente.complete("hola") == '{"a": 1}'


def test_una_conexion_que_se_corta_se_reintenta_sola():
    """Fallo real: DeepSeek cortó la respuesta a medias en la ronda 8 y tumbó
    un proyecto de media hora. Un corte de red es para reintentarlo."""
    intentos = []

    def responder(request):
        intentos.append(1)
        if len(intentos) == 1:
            raise httpx.RemoteProtocolError("peer closed connection", request=request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                              "message": {"content": '{"a": 1}'}}]})

    cliente = DeepSeekClient(api_key="k", model="deepseek-chat", espera_reintento_s=0,
                             transport=httpx.MockTransport(responder))

    assert cliente.complete("hola") == '{"a": 1}'
    assert len(intentos) == 2


def test_si_la_red_no_se_recupera_se_dice_claro():
    from orchestrator.llm.providers.deepseek import ConexionCaida

    def responder(request):
        raise httpx.RemoteProtocolError("peer closed connection", request=request)

    cliente = DeepSeekClient(api_key="k", model="deepseek-chat", espera_reintento_s=0,
                             transport=httpx.MockTransport(responder))

    with pytest.raises(ConexionCaida, match="3 veces"):
        cliente.complete("hola")


# --- El techo de salida del razonador ------------------------------------
#
# ADR-013 decía que 64K «es el techo de DeepSeek, así que no hay margen que
# subir», y con eso se aceptó que el Ginebra muriera cortado tres veces. No
# era cierto: la propia API contesta a un max_tokens mayor con
# «the valid range of max_tokens is [1, 393216]» (comprobado el 2026-09-20).
# Por decisión del usuario, el razonador pide el máximo.

MAXIMO_DE_LA_API = 393_216
VELOCIDAD_MEDIDA = 318
"""tokens/s de deepseek-reasoner (Flash con pensamiento), medidos el
2026-09-20: 20 326 tokens en 64 s."""


def _peticion_del_razonador():
    enviado = {}

    def responder(request):
        enviado.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    DeepSeekClient(api_key="k", model="deepseek-reasoner",
                   transport=httpx.MockTransport(responder)).complete("hola")
    return enviado


def test_el_razonador_pide_el_maximo_que_admite_la_api():
    assert _peticion_del_razonador()["max_tokens"] == MAXIMO_DE_LA_API


def test_el_plazo_deja_tiempo_para_generar_todo_el_techo():
    """Subir max_tokens sin subir el plazo es un techo de adorno: el corte lo
    daría nuestro reloj, no DeepSeek. Con el plazo antiguo (1200 s) y la
    velocidad medida, el techo real se quedaba en ~381 000. Margen de 2x
    porque en hora punta DeepSeek va más lento."""
    cliente = DeepSeekClient(api_key="k", model="deepseek-reasoner")
    assert cliente._deadline_s * VELOCIDAD_MEDIDA >= 2 * MAXIMO_DE_LA_API


def test_el_modelo_que_no_piensa_no_cambia():
    enviado = {}

    def responder(request):
        enviado.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    DeepSeekClient(api_key="k", model="deepseek-chat",
                   transport=httpx.MockTransport(responder)).complete("hola")
    assert enviado["max_tokens"] == 8192
