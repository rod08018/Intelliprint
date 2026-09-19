"""Adaptador de Telegram (F5.6 (telegram)).

Se prueba contra `httpx.MockTransport`: se ejercita el código real del
cliente, sin red y sin tocar el bot de verdad.

⚠️ El canal nace ABIERTO (ADR-012): cualquiera que escriba al bot puede
lanzar un proyecto. Cerrarlo con lista blanca es F5.10 (cerrar).
"""

import json

import httpx
import pytest

from orchestrator.human.adapters.telegram import TelegramBot, TelegramClient


def _api(respuestas, registro):
    def responder(request: httpx.Request) -> httpx.Response:
        metodo = request.url.path.rsplit("/", 1)[-1]
        cuerpo = json.loads(request.content) if request.content and not request.content.startswith(b"--") else {}
        registro.append((metodo, cuerpo))
        return httpx.Response(200, json={"ok": True, "result": respuestas.pop(0) if respuestas else []})

    return httpx.MockTransport(responder)


def _mensaje(texto, chat=7, update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "text": texto}}


def test_un_mensaje_lanza_el_trabajo_y_se_contesta_a_quien_escribio(tmp_path):
    registro = []
    gif = tmp_path / "a.gif"
    gif.write_bytes(b"GIF89a")
    hechos = []

    def trabajo(peticion, avisar):
        hechos.append(peticion)
        avisar("voy por la ronda 1")
        return {"texto": "listo: sin choques", "archivos": [gif]}

    cliente = TelegramClient("t", transport=_api([[_mensaje("una bisagra")], []], registro))
    bot = TelegramBot(cliente, trabajo, nombre="Crafty")

    assert bot.poll_once() == 1

    assert hechos == ["una bisagra"]
    enviados = [(m, c) for m, c in registro if m != "getUpdates"]
    assert all(c.get("chat_id") == 7 for _, c in enviados if c)
    textos = " ".join(json.dumps(c, ensure_ascii=False) for m, c in enviados if m == "sendMessage")
    assert "ronda 1" in textos and "sin choques" in textos
    assert any(m in ("sendAnimation", "sendDocument") for m, _ in registro)


def test_mientras_trabaja_no_acepta_otro_proyecto(tmp_path):
    registro = []

    def trabajo(peticion, avisar):
        return {"texto": "ok", "archivos": []}

    cliente = TelegramClient("t", transport=_api([[_mensaje("uno"), _mensaje("dos", update_id=2)]], registro))
    bot = TelegramBot(cliente, trabajo, nombre="Crafty")
    bot._ocupado = True  # como si ya hubiera un proyecto en marcha

    bot.poll_once()

    textos = " ".join(json.dumps(c, ensure_ascii=False) for m, c in registro if m == "sendMessage")
    assert "ocupado" in textos.lower()


def test_un_fallo_del_trabajo_se_cuenta_en_vez_de_matar_al_bot():
    registro = []

    def trabajo(peticion, avisar):
        raise RuntimeError("freecadcmd no encontrado")

    cliente = TelegramClient("t", transport=_api([[_mensaje("algo")]], registro))
    bot = TelegramBot(cliente, trabajo, nombre="Crafty")

    bot.poll_once()  # no lanza

    textos = " ".join(json.dumps(c, ensure_ascii=False) for m, c in registro if m == "sendMessage")
    assert "freecadcmd no encontrado" in textos


def test_el_offset_avanza_para_no_repetir_mensajes():
    registro = []
    cliente = TelegramClient("t", transport=_api([[_mensaje("hola", update_id=41)], []], registro))
    bot = TelegramBot(cliente, lambda p, a: {"texto": "ok", "archivos": []}, nombre="Crafty")

    bot.poll_once()
    bot.poll_once()

    offsets = [c.get("offset") for m, c in registro if m == "getUpdates"]
    assert offsets == [None, 42]


@pytest.mark.parametrize("update", [
    {"update_id": 1, "message": {"chat": {"id": 7}}},               # sin texto (una foto)
    {"update_id": 2, "edited_message": {"chat": {"id": 7}, "text": "x"}},
])
def test_lo_que_no_es_un_mensaje_de_texto_se_ignora(update):
    registro = []
    cliente = TelegramClient("t", transport=_api([[update]], registro))
    hechos = []
    bot = TelegramBot(cliente, lambda p, a: hechos.append(p), nombre="Crafty")

    bot.poll_once()

    assert hechos == []
