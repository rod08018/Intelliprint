"""El diseñador de piezas con el kit (F5.18 (kit)).

Escribe `construir(kit)` en vez de una receta de generadores: con la receta
la escuadra con nervio salía maciza y los hexágonos cuadrados. El programa
no puede salirse del kit (`mech_toolkit.kit.sandbox`), y si no pasa la
lista blanca vuelve al modelo con la línea y el motivo, dentro del mismo
bucle que un error de esquema.
"""

from pathlib import Path

import yaml

from mech_toolkit.kit import referencia
from orchestrator.llm.structured import LlmClient, structured
from orchestrator.schemas.programa import Programa

PROMPT_PATH = Path("config/agents/disenador_kit.md")

_DEL_PERFIL = ("printer", "material", "layer_height_mm", "bed_mm", "fits", "holes",
               "walls", "overhang_max_deg", "bridge_max_mm")


class DisenadorKitAgent:
    def __init__(self, client: LlmClient, activo, prompt_path: Path = PROMPT_PATH,
                 reserva: LlmClient | None = None) -> None:
        """`reserva`: el modelo sin pensamiento, por si el razonador se corta
        (ver `structured`)."""
        self._client = client
        self._reserva = reserva
        self.perfil = activo.datos
        """Lo que el kit recibe al construir: de aquí salen tornillos y holguras."""
        perfil = {k: activo.datos[k] for k in _DEL_PERFIL if k in activo.datos}
        self._instrucciones = (
            prompt_path.read_text(encoding="utf-8")
            + "\n\n## La API del kit\n\n" + referencia()
            + "\n## Perfil activo\n\n```yaml\n"
            + yaml.safe_dump(perfil, allow_unicode=True, sort_keys=False) + "```\n")

    def design(self, tarea: str, rechazo: tuple[str, str] | None = None) -> Programa:
        """`rechazo` = (programa anterior, motivo por el que no se pudo construir)."""
        prompt = f"{self._instrucciones}\n## Tarea\n\n{tarea}\n"
        if rechazo is not None:
            anterior, motivo = rechazo
            prompt += ("\n## Tu programa anterior NO se pudo construir\n\n"
                       f"```\n{anterior}\n```\n\nMotivo:\n{motivo}\n\n"
                       "Corrígelo. No repitas el mismo error.\n")
        return structured(self._client, prompt, Programa, cliente_de_reserva=self._reserva)
