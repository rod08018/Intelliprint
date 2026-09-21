"""La lista blanca del canal de Telegram (F5.10 (lista)): OPCIONAL.

Decisión del usuario (2026-09-21): el canal va ABIERTO. La lista se había
hecho obligatoria sin que él lo aprobara, al leer su «haz todo» como que
incluía esta tarea de la tabla de deuda. Queda como opción: vacía, el bot
atiende a cualquiera; con ids, solo a ellos.

Un bot de Telegram NO es local aunque corra en el PC: hace sondeo contra
los servidores de Telegram, que le entregan los mensajes de cualquiera que
lo encuentre. Con el canal abierto, un desconocido podía lanzar proyectos,
gastar el saldo de DeepSeek y contestar las barreras del sistema.

El criterio de aceptación del plan, literal: responde a los IDs de la
lista e IGNORA al resto; sin lista definida, el canal no arranca.
"""

import json

import httpx
import pytest

from orchestrator.human.adapters.telegram import (
    ListaBlancaInvalida, TelegramBot, TelegramClient, leer_lista_blanca)

YO = 111
AJENO = 999


def _api(respuestas, registro):
    def responder(request: httpx.Request) -> httpx.Response:
        metodo = request.url.path.rsplit("/", 1)[-1]
        cuerpo = json.loads(request.content) if request.content and not request.content.startswith(b"--") else {}
        registro.append((metodo, cuerpo))
        return httpx.Response(200, json={"ok": True, "result": respuestas.pop(0) if respuestas else []})
    return httpx.MockTransport(responder)


def _de(usuario, texto, update_id=1):
    """Un mensaje privado: en Telegram el chat privado lleva el id de la
    persona, pero se mira `from`, que es QUIÉN escribe."""
    return {"update_id": update_id,
            "message": {"chat": {"id": usuario}, "from": {"id": usuario}, "text": texto}}


def _bot(mensajes, registro, hechos):
    cliente = TelegramClient("t", transport=_api([mensajes, []], registro))
    return TelegramBot(cliente, lambda p, avisar: hechos.append(p) or {"texto": "ok"},
                       permitidos=frozenset({YO}))


# --- Leer la lista ----------------------------------------------------------


def test_la_lista_se_lee_separada_por_comas():
    assert leer_lista_blanca("111, 222,333") == frozenset({111, 222, 333})


def test_sin_lista_el_canal_esta_abierto():
    """Vacía significa «sin lista»: el canal atiende a cualquiera."""
    for vacia in ("", "   ", None, " , "):
        assert leer_lista_blanca(vacia) is None


def test_un_nombre_de_usuario_no_vale_como_id():
    """@alias se puede cambiar y lo puede coger otro. El id numérico no."""
    with pytest.raises(ListaBlancaInvalida, match="@jdr"):
        leer_lista_blanca("111,@jdr")


def test_sin_lista_el_bot_atiende_a_cualquiera():
    registro, hechos = [], []
    cliente = TelegramClient("t", transport=_api([[_de(AJENO, "una bisagra")], []], registro))
    TelegramBot(cliente, lambda p, avisar: hechos.append(p) or {"texto": "ok"},
                permitidos=None).poll_once()
    assert hechos == ["una bisagra"]


# --- Qué hace con cada mensaje -------------------------------------------------


def test_quien_esta_en_la_lista_es_atendido():
    registro, hechos = [], []
    _bot([_de(YO, "una bisagra")], registro, hechos).poll_once()
    assert hechos == ["una bisagra"]


def test_un_ajeno_no_lanza_ningun_proyecto():
    registro, hechos = [], []
    _bot([_de(AJENO, "una bisagra")], registro, hechos).poll_once()
    assert hechos == []


def test_a_un_ajeno_no_se_le_contesta_nada():
    """Ni siquiera «no tienes permiso»: contestar confirma que el bot existe
    y está vivo, y le da algo con que insistir."""
    registro, hechos = [], []
    _bot([_de(AJENO, "hola"), _de(AJENO, "/start", 2)], registro, hechos).poll_once()
    assert [m for m, _ in registro if m != "getUpdates"] == []


def test_los_mensajes_ajenos_no_se_repiten():
    """Ignorar no es dejar pendiente: el offset avanza igual, o el bot
    volvería a leerlos en cada vuelta."""
    registro, hechos = [], []
    bot = _bot([_de(AJENO, "x", update_id=41)], registro, hechos)
    bot.poll_once()
    bot.poll_once()
    offsets = [c.get("offset") for m, c in registro if m == "getUpdates"]
    assert offsets[-1] == 42


def test_un_mensaje_sin_remitente_se_ignora():
    """Los mensajes de canal no traen `from`. Sin saber quién escribe, no
    hay forma de saber si está en la lista."""
    registro, hechos = [], []
    sin_from = {"update_id": 1, "message": {"chat": {"id": YO}, "text": "una bisagra"}}
    _bot([sin_from], registro, hechos).poll_once()
    assert hechos == []


def test_en_un_grupo_cuenta_quien_escribe_no_el_grupo():
    """Si alguien de la lista mete el bot en un grupo, el resto del grupo
    sigue siendo ajeno."""
    registro, hechos = [], []
    grupo = -500
    mensajes = [
        {"update_id": 1, "message": {"chat": {"id": grupo}, "from": {"id": AJENO}, "text": "a"}},
        {"update_id": 2, "message": {"chat": {"id": grupo}, "from": {"id": YO}, "text": "b"}},
    ]
    _bot(mensajes, registro, hechos).poll_once()
    assert hechos == ["b"]
