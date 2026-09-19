"""Adaptador de Telegram (F5.6 (telegram)).

Un proceso local que habla con la API de Telegram por sondeo largo. No
hace falta contenedor ni abrir puertos: es el bot quien pregunta.

⚠️ **El canal nace ABIERTO** (ADR-012): cualquiera que escriba al bot
puede lanzar un proyecto y gastar modelo. Es deuda declarada; cerrarlo
con `TELEGRAM_ALLOWED_USERS` es F5.10 (cerrar). Mientras tanto, el bot
avisa de ello al arrancar.

Lo que entra por aquí es **dato, nunca instrucción para el sistema**: el
texto se pasa como petición al flujo de diseño y nada más.
"""

import time
from pathlib import Path
from typing import Callable

import httpx

API = "https://api.telegram.org"

Trabajo = Callable[[str, Callable[[str], None]], dict]
"""(petición, avisar) → {"texto": resumen, "archivos": [rutas]}."""


class TelegramClient:
    def __init__(self, token: str, base_url: str = API, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._cliente = httpx.Client(base_url=f"{base_url}/bot{token}",
                                     timeout=timeout, transport=transport)

    def _pedir(self, metodo: str, **datos):
        r = self._cliente.post(f"/{metodo}", json=datos)
        r.raise_for_status()
        return r.json().get("result")

    def get_updates(self, offset: int | None, espera: int = 25) -> list[dict]:
        return self._pedir("getUpdates", offset=offset, timeout=espera) or []

    def send_message(self, chat_id: int, texto: str) -> None:
        # Telegram corta en 4096 caracteres; un informe de choques pasa de ahí.
        for trozo in [texto[i:i + 3500] for i in range(0, len(texto), 3500)] or [""]:
            self._pedir("sendMessage", chat_id=chat_id, text=trozo)

    def send_file(self, chat_id: int, ruta: Path) -> None:
        ruta = Path(ruta)
        metodo, campo = ("sendAnimation", "animation") if ruta.suffix == ".gif" else \
                        ("sendDocument", "document")
        with ruta.open("rb") as f:
            r = self._cliente.post(f"/{metodo}", data={"chat_id": chat_id},
                                   files={campo: (ruta.name, f)})
        r.raise_for_status()


class TelegramBot:
    """Sondea mensajes y ejecuta UN proyecto a la vez (regla 9 de § 4: dos
    proyectos a la vez se pelean por FreeCAD y por el modelo)."""

    def __init__(self, cliente: TelegramClient, trabajo: Trabajo, nombre: str = "Crafty") -> None:
        self._cliente = cliente
        self._trabajo = trabajo
        self._nombre = nombre
        self._offset: int | None = None
        self._ocupado = False

    def poll_once(self, espera: int = 25) -> int:
        """Procesa los mensajes pendientes. Devuelve cuántos atendió."""
        atendidos = 0
        for update in self._cliente.get_updates(self._offset, espera):
            self._offset = update["update_id"] + 1
            mensaje = update.get("message") or {}
            texto = (mensaje.get("text") or "").strip()
            chat = (mensaje.get("chat") or {}).get("id")
            if not texto or chat is None:
                continue  # fotos, ediciones y otros: todavía no (F5.2 (adjuntos))
            atendidos += 1
            if texto.startswith("/"):
                self._cliente.send_message(chat, self._ayuda())
                continue
            if self._ocupado:
                self._cliente.send_message(
                    chat, f"[{self._nombre}] Ahora mismo estoy ocupado con otro proyecto. "
                          "Escríbeme cuando termine.")
                continue
            self._atender(chat, texto)
        return atendidos

    def _atender(self, chat: int, peticion: str) -> None:
        self._ocupado = True
        self._cliente.send_message(
            chat, f"[{self._nombre}] Recibido. Voy a diseñarlo; cada ronda tarda unos minutos.")
        try:
            resultado = self._trabajo(peticion, lambda t: self._cliente.send_message(chat, t)) or {}
            self._cliente.send_message(chat, resultado.get("texto", "listo"))
            for ruta in resultado.get("archivos", []):
                self._cliente.send_file(chat, ruta)
        except Exception as e:  # el bot sigue vivo: el fallo es del proyecto
            self._cliente.send_message(chat, f"[{self._nombre}] No pude terminarlo: {e}")
        finally:
            self._ocupado = False

    def _ayuda(self) -> str:
        return (
            f"[{self._nombre}] Escríbeme el mecanismo que quieres y lo diseño: "
            "piezas, ensamble en FreeCAD, animación del movimiento y una revisión "
            "de si cumple lo que pediste.\n\n"
            "Ejemplo: «una bisagra de dos hojas con pasador y un tope que limite la apertura».\n"
            "Puedes mandarme el enunciado completo en un mensaje largo."
        )

    def run(self) -> None:
        while True:
            try:
                self.poll_once()
            except httpx.HTTPError as e:
                print(f"[{self._nombre}] error de red con Telegram: {e}; reintento en 5 s")
                time.sleep(5)
