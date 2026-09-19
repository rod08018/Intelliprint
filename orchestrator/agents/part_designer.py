"""Part Designer Agent (F1.10 (designer)). Ver DECISIONES.md ADR-002.

No escribe Python: emite una receta de generadores. Un error suyo es un
parámetro que el esquema rechaza antes de ejecutar nada, en vez de un
traceback después de lanzar FreeCAD.
"""

from pathlib import Path

from orchestrator.llm.structured import LlmClient, structured
from orchestrator.schemas.recipe import GeneratorCatalog, Recipe

PROMPT_PATH = Path("config/agents/part_designer.md")


class PartDesignerAgent:
    def __init__(
        self,
        client: LlmClient,
        catalog: GeneratorCatalog,
        prompt_path: Path = PROMPT_PATH,
    ) -> None:
        self._client = client
        self._catalog = catalog
        self._instrucciones = prompt_path.read_text(encoding="utf-8")

    def design(self, tarea: str, rechazo: tuple[str, str] | None = None) -> Recipe:
        """`rechazo` = (receta anterior, motivo por el que FreeCAD no pudo
        construirla). Es el segundo nivel del bucle de error (F1.11 (bucle))."""
        prompt = (
            f"{self._instrucciones}\n"
            f"## Catálogo de generadores\n\n{self._catalog.describe()}\n"
            f"## Tarea\n\n{tarea}\n"
        )
        if rechazo is not None:
            receta_previa, motivo = rechazo
            prompt += (
                "\n## Tu receta anterior NO se pudo construir\n\n"
                f"Receta:\n{receta_previa}\n\n"
                f"Motivo:\n{motivo}\n\n"
                "Corrígela. No repitas el mismo error.\n"
            )
        # El catálogo entra en el bucle de reintento: que un generador
        # exista no lo sabe el esquema, solo el catálogo. Si quedara fuera,
        # un generador inventado gastaría el intento sin corregirse.
        return structured(
            self._client,
            prompt,
            Recipe,
            extra_validation=lambda receta: receta.validate_against(self._catalog),
        )
