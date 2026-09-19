"""Requirements Agent (F1.4 (requirements)). Ver SISTEMA_MULTIAGENTE.md § 4.1 y § 4.2.

Es el único agente que corre antes de tu confirmación, y el que decide
la clase de producto — que a su vez decide qué agentes correrán después
(ADR-010).
"""

from pathlib import Path

from orchestrator.llm.structured import LlmClient, structured
from orchestrator.schemas.spec import Spec

PROMPT_PATH = Path("config/agents/requirements.md")


class RequirementsAgent:
    def __init__(self, client: LlmClient, prompt_path: Path = PROMPT_PATH) -> None:
        self._client = client
        self._instrucciones = prompt_path.read_text(encoding="utf-8")

    def draft(self, peticion: str, adjuntos: list[str] | None = None) -> Spec:
        """Redacta la spec a partir de la petición.

        Si el modelo clasifica como `robot` u omite un dato obligatorio de
        la clase, el esquema lo rechaza y `structured` le devuelve el error
        exacto para que lo corrija (ADR-010 + F1.3 (estructurada)). La coherencia entre
        clase y datos no depende del prompt: la impone el esquema.
        """
        partes = [self._instrucciones, "\n## Petición\n", peticion]
        if adjuntos:
            partes.append("\n\n## Adjuntos\n")
            partes.extend(f"- {a}\n" for a in adjuntos)
        spec = structured(self._client, "".join(partes), Spec)
        # La petición literal la fija el código después de la llamada: el
        # modelo no puede perderla ni reescribirla al resumir.
        return spec.model_copy(update={"request": peticion})
