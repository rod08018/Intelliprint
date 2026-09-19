"""Mechanism Designer (F3.15 (mecanismos)).

De la petición en texto a un `MechanismSpec`. Lo que se puede comprobar
sin geometría (fórmulas evaluables en todo el recorrido, requisitos
medibles) entra en el bucle de reintento de `structured`; lo que necesita
geometría (choques, contactos, piezas que no cuadran) vuelve en la ronda
siguiente como `rechazo`.
"""

from pathlib import Path

from mech_toolkit.profile import PrinterProfile
from orchestrator.llm.structured import LlmClient, structured
from orchestrator.mechanisms.kinematics import Kinematics
from orchestrator.schemas.mechanism import MechanismSpec
from orchestrator.schemas.recipe import GeneratorCatalog

PROMPT_PATH = Path("config/agents/mechanism_designer.md")


class MechanismDesignerAgent:
    def __init__(self, client: LlmClient, catalog: GeneratorCatalog, profile: PrinterProfile,
                 bed_mm: tuple[float, float, float], min_gap_mm: float,
                 prompt_path: Path = PROMPT_PATH) -> None:
        self._client = client
        self._instrucciones = prompt_path.read_text(encoding="utf-8").format(
            min_gap=f"{min_gap_mm:g}", bed=" × ".join(f"{v:g}" for v in bed_mm),
            profile_id=profile.id, clearance=f"{profile.fit_mm('clearance'):g}",
            slide=f"{profile.fit_mm('slide'):g}", press=f"{profile.fit_mm('press'):g}",
            catalog=catalog.describe(),
        )

    def design(self, peticion: str, rechazo: tuple[str, str] | None = None) -> MechanismSpec:
        """`rechazo` = (especificación anterior, qué falló al construirla)."""
        prompt = f"{self._instrucciones}\n## Petición del usuario\n\n{peticion}\n"
        if rechazo is not None:
            anterior, motivo = rechazo
            prompt += (
                "\n## Tu diseño anterior NO funciona\n\n"
                f"Diseño:\n{anterior}\n\n"
                f"Lo que falló al construirlo y moverlo:\n{motivo}\n\n"
                "Corrígelo. Cambia lo necesario (medidas, posiciones, holguras, "
                "fórmulas) sin dejar de cumplir la petición.\n"
            )
        return structured(
            self._client, prompt, MechanismSpec,
            extra_validation=lambda spec: Kinematics(spec).validate(),
        )
