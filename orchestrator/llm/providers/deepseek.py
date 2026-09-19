"""Cliente de DeepSeek (API compatible con OpenAI).

Perfil `dev` únicamente. Ver DECISIONES.md ADR-007b: es deuda temporal,
no el diseño objetivo.
"""

import httpx

BASE_URL = "https://api.deepseek.com"


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = BASE_URL,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        # El modelo de razonamiento piensa antes de responder: minutos, no
        # segundos, y su pensamiento cuenta dentro de max_tokens.
        razona = "reasoner" in model
        self._max_tokens = 32768 if razona else 8192
        self._cliente = httpx.Client(
            base_url=base_url,
            timeout=timeout if timeout is not None else (900.0 if razona else 120.0),
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        respuesta = self._cliente.post(
            "/chat/completions",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                # Una especificación de mecanismo con sus enunciados pasa de
                # los 4K tokens por defecto; cortada, no sería JSON válido.
                "max_tokens": self._max_tokens,
                # La API garantiza JSON sintácticamente válido, pero NO que
                # cumpla nuestro esquema: la validación y el reintento con el
                # error siguen haciendo falta (F1.3 (estructurada)).
                "response_format": {"type": "json_object"},
            },
        )
        # Un 401 o un 429 no pueden colarse como "respuesta del modelo": se
        # comerían los tres reintentos fallando la validación del esquema.
        respuesta.raise_for_status()
        return respuesta.json()["choices"][0]["message"]["content"]
