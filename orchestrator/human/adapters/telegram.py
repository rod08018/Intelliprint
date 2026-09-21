"""Adaptador de Telegram (F5.6 (telegram)).

Un proceso local que habla con la API de Telegram por sondeo largo. No
hace falta contenedor ni abrir puertos: es el bot quien pregunta.

**Solo atiende a quien está en `TELEGRAM_ALLOWED_USERS`** (F5.10 (lista)).
El canal nació abierto (ADR-012) y eso era deuda: un bot de Telegram no
es local aunque corra en el PC, porque Telegram le entrega los mensajes de
cualquiera que lo encuentre. Sin lista, el bot no arranca.

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


class ListaBlancaInvalida(ValueError):
    """TELEGRAM_ALLOWED_USERS falta o no es una lista de ids."""


def leer_lista_blanca(texto: str | None) -> frozenset[int]:
    """Los ids numéricos de Telegram de `TELEGRAM_ALLOWED_USERS`.

    Vacía NO significa «todos»: significa que nadie decidió quién. Abrir el
    canal por omisión es justo la deuda que esto salda (ADR-012), así que
    sin lista no hay canal.

    Solo ids numéricos. Un @alias se cambia cuando se quiere y lo puede
    coger otra persona; el id es de la cuenta para siempre.
    """
    partes = [p.strip() for p in (texto or "").split(",") if p.strip()]
    if not partes:
        raise ListaBlancaInvalida(
            "falta TELEGRAM_ALLOWED_USERS: sin lista de quién puede escribir, el "
            "canal no arranca. Tu id te lo dice @userinfobot en Telegram.")
    malos = [p for p in partes if not p.lstrip("-").isdigit()]
    if malos:
        raise ListaBlancaInvalida(
            f"TELEGRAM_ALLOWED_USERS solo admite ids numéricos, no {malos}: un "
            "@alias se puede cambiar y lo puede coger otro")
    return frozenset(int(p) for p in partes)


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

    def __init__(self, cliente: TelegramClient, trabajo: Trabajo, nombre: str = "Crafty",
                 *, permitidos: frozenset[int]) -> None:
        if not permitidos:
            raise ListaBlancaInvalida(
                "un bot sin lista blanca atendería a cualquiera (ADR-012): "
                "define TELEGRAM_ALLOWED_USERS")
        self._permitidos = frozenset(permitidos)
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
            # QUIÉN escribe, no dónde: en un grupo el chat es el grupo, y el
            # resto de sus miembros sigue siendo ajeno. Sin remitente (los
            # mensajes de canal no lo traen) no hay forma de comprobarlo.
            #
            # Al ajeno no se le contesta NADA, ni «no tienes permiso»:
            # contestar confirma que el bot existe y está vivo. El offset ya
            # avanzó arriba, así que tampoco se vuelve a leer.
            remitente = (mensaje.get("from") or {}).get("id")
            if remitente not in self._permitidos:
                continue
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
