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


class RespuestaCortada(RuntimeError):
    pass


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
        # Plazo total de una llamada, de principio a fin. El de razonamiento
        # piensa varios minutos; más allá de esto, algo va mal.
        self._deadline_s = deadline_s if deadline_s is not None else (1200.0 if razona else 300.0)
        # Medido en la bisagra: ~30 000 tokens de pensamiento. Con 32 768 se
        # quedaba sin sitio y devolvía la respuesta vacía (finish_reason=length).
        self._max_tokens = 65536 if razona else 8192
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
        """Lee la respuesta a trozos vigilando el reloj: así se puede cortar
        una llamada que no avanza aunque el servidor siga mandando bytes."""
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

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        cuerpo = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
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
