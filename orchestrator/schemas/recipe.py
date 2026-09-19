"""Receta del Part Designer. Ver SISTEMA_MULTIAGENTE.md § 6.3.

El Part Designer NO escribe Python: emite una lista de llamadas a
generadores de `mech-toolkit`. `build.py` lo compone el orquestador.
"""

from pydantic import BaseModel, model_validator


class RecipeError(ValueError):
    """La receta no es ejecutable contra el catálogo de generadores."""


class GeneratorSpec(BaseModel):
    name: str
    required_params: set[str] = set()
    optional_params: set[str] = set()

    @property
    def allowed_params(self) -> set[str]:
        return self.required_params | self.optional_params


class GeneratorCatalog:
    """Catálogo de generadores disponibles en `mech-toolkit`."""

    def __init__(self, specs: list[GeneratorSpec]) -> None:
        self._por_nombre = {spec.name: spec for spec in specs}

    def get(self, name: str) -> GeneratorSpec | None:
        return self._por_nombre.get(name)


class RecipeStep(BaseModel):
    generator: str
    params: dict = {}


class Recipe(BaseModel):
    """Validez intrínseca vía pydantic; validez contra el catálogo vía
    `validate_against`, que sí necesita saber qué generadores existen."""

    part: str
    steps: list[RecipeStep]

    @model_validator(mode="after")
    def _al_menos_un_paso(self) -> "Recipe":
        if not self.steps:
            raise ValueError(
                "una receta necesita al menos un paso: sin pasos, build.py "
                "produce una pieza vacía sin lanzar ningún error."
            )
        return self

    def validate_against(self, catalog: GeneratorCatalog) -> None:
        for paso in self.steps:
            spec = catalog.get(paso.generator)
            if spec is None:
                raise RecipeError(
                    f"generador desconocido: {paso.generator!r}. "
                    "Si la pieza lo necesita de verdad, falta escribirlo "
                    "en mech-toolkit (ADR-002)."
                )
            faltantes = sorted(spec.required_params - paso.params.keys())
            if faltantes:
                raise RecipeError(
                    f"{paso.generator}: faltan parámetros obligatorios "
                    f"{faltantes}."
                )
            desconocidos = sorted(paso.params.keys() - spec.allowed_params)
            if desconocidos:
                raise RecipeError(
                    f"{paso.generator}: parámetros desconocidos {desconocidos}. "
                    "Ignorarlos daría una pieza con geometría incorrecta y "
                    "sin ningún error visible."
                )
