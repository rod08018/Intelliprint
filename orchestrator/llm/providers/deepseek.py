"""Cliente de DeepSeek (API compatible con OpenAI).

Perfil `dev` únicamente. Ver DECISIONES.md ADR-007b: es deuda temporal,
no el diseño objetivo.
"""

import json
import time

import httpx

BASE_URL = "https://api.deepseek.com"


def _sin_bloque_de_codigo(texto: str) -> str:
    """El JSON, aunque venga dentro de un bloque ```json ... ```."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1] if "\n" in texto else ""
        texto = texto.rsplit("```", 1)[0]
    return texto.strip()


MAX_TOKENS_RAZONADOR = 393_216
"""El límite de la API de DeepSeek para max_tokens (ver el constructor)."""

class RespuestaCortada(RuntimeError):
    pass


class ConexionCaida(RuntimeError):
    """La red se cortó a media respuesta. No es culpa del modelo ni del
    esquema: se reintenta, y si no se recupera se dice claro."""


class TiempoAgotado(RuntimeError):
    """La llamada pasó del plazo TOTAL. No vale el plazo de lectura de httpx:
    se reinicia con cada byte, y DeepSeek manda caracteres de mantenimiento
    en las peticiones largas (fallo real: 54 minutos colgado)."""


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = BASE_URL,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
        deadline_s: float | None = None,
        intentos_de_red: int = 3,
        espera_reintento_s: float = 2.0,
    ) -> None:
        self._model = model
        self.tokens = {"entrada": 0, "salida": 0}
        """Lo gastado por este cliente. El tope de gasto del proyecto sale de
        aquí (F5.12 (tope)), no de un número de rondas inventado."""
        self.llamadas: list[dict] = []
        """Una entrada por llamada, para desglosar el coste: un total no
        dice en qué se fue el dinero."""
        # El modelo de razonamiento piensa antes de responder: minutos, no
        # segundos, y su pensamiento cuenta dentro de max_tokens.
        razona = "reasoner" in model
        # Plazo total de una llamada, de principio a fin. Tiene que dejar
        # tiempo para generar TODO el techo de salida, o el techo es de adorno
        # y el corte lo da este reloj en vez de DeepSeek. Medido el
        # 2026-09-20: 318 tokens/s; los 393 216 tardan ~21 min, y en hora
        # punta más. Con 1200 s el techo real se quedaba en ~381 000. 45 min
        # es el doble de lo medido.
        self._deadline_s = deadline_s if deadline_s is not None else (2700.0 if razona else 300.0)
        self._intentos_de_red = intentos_de_red
        self._espera_reintento_s = espera_reintento_s
        # El máximo que admite la API: «the valid range of max_tokens is
        # [1, 393216]», comprobado el 2026-09-20. Su pensamiento cuenta DENTRO
        # de max_tokens y lo decide él, no el prompt.
        #
        # Historia, porque explica el número: con 32 768 la bisagra devolvía
        # la respuesta vacía; con 65 536 el Ginebra se cortó tres veces
        # seguidas y el proyecto murió sin diseño. ADR-013 dio 64K por el
        # techo de DeepSeek, y no lo era. Por decisión del usuario, se pide
        # el máximo; el tope de gasto por proyecto sigue acotando el coste
        # (una llamada llena son ~0.47 USD en hora punta).
        self._max_tokens = MAX_TOKENS_RAZONADOR if razona else 8192
        self._razona = razona
        self._cliente = httpx.Client(
            base_url=base_url,
            timeout=timeout if timeout is not None else (900.0 if razona else 120.0),
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def _pedir_con_plazo(self, cuerpo: dict) -> dict:
        """Lee la respuesta a trozos vigilando el reloj, y reintenta si la red
        se corta: un corte no puede tumbar un proyecto de media hora."""
        for intento in range(1, self._intentos_de_red + 1):
            try:
                return self._leer(cuerpo)
            except httpx.HTTPError as e:
                if isinstance(e, httpx.HTTPStatusError) or intento == self._intentos_de_red:
                    if isinstance(e, httpx.HTTPStatusError):
                        raise
                    raise ConexionCaida(
                        f"la conexión con {self._model} se cortó {intento} veces seguidas: {e}"
                    ) from None
                time.sleep(self._espera_reintento_s * intento)

    def _leer(self, cuerpo: dict) -> dict:
        limite = time.monotonic() + self._deadline_s
        trozos = []
        with self._cliente.stream("POST", "/chat/completions", json=cuerpo) as respuesta:
            # Un 401 o un 429 no pueden colarse como "respuesta del modelo": se
            # comerían los tres reintentos fallando la validación del esquema.
            if respuesta.status_code >= 400:
                respuesta.read()
                respuesta.raise_for_status()
            for trozo in respuesta.iter_bytes():
                trozos.append(trozo)
                if time.monotonic() > limite:
                    raise TiempoAgotado(
                        f"{self._model} pasó de {self._deadline_s:g} s sin terminar la "
                        "respuesta; se corta la llamada"
                    )
        return json.loads(b"".join(trozos))

    @property
    def modelo(self) -> str:
        return self._model

    def complete(self, prompt: str, *, temperature: float = 0.0,
                 imagenes: list[str] | None = None) -> str:
        # Con imágenes (referencias que mandó el usuario), el mensaje lleva
        # partes; sin ellas sigue siendo texto plano, como siempre. Flash las
        # ve: comprobado el 2026-09-21 (una imagen roja → «Rojo»).
        contenido = prompt if not imagenes else [
            {"type": "text", "text": prompt},
            *({"type": "image_url", "image_url": {"url": url}} for url in imagenes),
        ]
        cuerpo = {
            "model": self._model,
            "messages": [{"role": "user", "content": contenido}],
            "temperature": temperature,
            # Una especificación de mecanismo con sus enunciados pasa de los
            # 4K tokens por defecto; cortada, no sería JSON válido.
            "max_tokens": self._max_tokens,
            # La API garantiza JSON sintácticamente válido, pero NO que
            # cumpla nuestro esquema: la validación y el reintento con el
            # error siguen haciendo falta (F1.3 (estructurada)).
            "response_format": {"type": "json_object"},
        }
        if self._razona:
            # Con el modo JSON, deepseek-reasoner no terminaba de pensar ni con
            # 65 536 tokens; sin él respondió JSON limpio en ~30 000 (medido en
            # la bisagra). El esquema se valida igual en `structured`.
            del cuerpo["response_format"]
        cuerpo_respuesta = self._pedir_con_plazo(cuerpo)
        uso = cuerpo_respuesta.get("usage") or {}
        entrada, salida = uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0)
        self.tokens["entrada"] += entrada
        self.tokens["salida"] += salida
        self.llamadas.append({"modelo": self._model, "entrada": entrada, "salida": salida})
        eleccion = cuerpo_respuesta["choices"][0]
        if eleccion.get("finish_reason") == "length":
            # Tampoco una respuesta cortada: el reintento "corrige el JSON"
            # cuando lo que falta es sitio (fallo real con deepseek-reasoner).
            raise RespuestaCortada(
                f"{self._model} agotó max_tokens={self._max_tokens} sin terminar la respuesta"
            )
        contenido = eleccion["message"]["content"] or ""
        if self._razona:
            contenido = _sin_bloque_de_codigo(contenido)
        return contenido
