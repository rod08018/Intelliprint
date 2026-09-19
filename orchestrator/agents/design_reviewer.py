"""Design Reviewer (F3.15 (mecanismos)).

Compara la petición literal con el mecanismo diseñado y con lo que el
código MIDIÓ sobre la geometría. No aprueba nada (ADR-003): produce un
informe con un veredicto por requisito, incluido `no_verificable`, que es
el que marca lo que hoy nadie comprueba.

Cuando el perfil tenga un modelo con visión (§ 7.1, capa 3), este mismo
agente podrá mirar además los fotogramas del ensamble.
"""

from pathlib import Path

from orchestrator.llm.structured import LlmClient, structured
from orchestrator.schemas.review import ReviewReport

PROMPT_PATH = Path("config/agents/design_reviewer.md")


class DesignReviewerAgent:
    def __init__(self, client: LlmClient, prompt_path: Path = PROMPT_PATH) -> None:
        self._client = client
        self._instrucciones = prompt_path.read_text(encoding="utf-8")

    def review(self, peticion: str, spec, mediciones: list[str]) -> ReviewReport:
        piezas = "\n".join(
            f"- {p.name}: {p.brief}" for p in spec.parts
        )
        movimiento = "\n".join(
            f"- {b.name}: " + (
                f"se apoya por contacto en {b.joint.rest_on.target}"
                if b.joint and b.joint.rest_on else
                f"articulación {b.joint.type} con fórmula {b.joint.value!r}"
                if b.joint else "fija"
            ) for b in spec.bodies
        )
        prompt = (
            f"{self._instrucciones}\n"
            f"## Petición literal del usuario\n\n{peticion}\n\n"
            f"## Mecanismo diseñado: {spec.title}\n\n{spec.summary}\n\n"
            f"### Piezas y enunciados\n{piezas}\n\n"
            f"### Cómo se mueve cada pieza\n{movimiento}\n\n"
            f"### Decisiones que tomó el diseñador\n"
            + "\n".join(f"- {a}" for a in spec.assumptions)
            + "\n\n### Lo que MIDIÓ el código sobre la geometría construida\n"
            + "\n".join(f"- {m}" for m in mediciones) + "\n"
        )
        return structured(self._client, prompt, ReviewReport)
