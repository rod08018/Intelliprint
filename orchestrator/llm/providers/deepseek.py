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
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._cliente = httpx.Client(
            base_url=base_url,
            timeout=timeout,
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
                "max_tokens": 8192,
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
