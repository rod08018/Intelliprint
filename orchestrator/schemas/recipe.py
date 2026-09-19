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
    choice_params: dict[str, set[str]] = {}
    """Parámetros de texto y sus únicos valores válidos. Cualquier otro
    parámetro tiene que ser un número o una lista (anidada) de números."""
    description: str = ""
    """Qué construye y dónde lo coloca. La ven el Part Designer y el
    Mechanism Designer: sin ella solo tendrían la firma."""
    template: str = ""
    """Fragmento de Python con marcadores `$param` (string.Template). Lo
    escribe un humano, no un LLM: es lo que hace segura la ejecución.

    Sintaxis `$` y no `{}` porque el cuerpo es código Python real y las
    llaves de un dict o de una comprensión colisionarían."""

    @property
    def allowed_params(self) -> set[str]:
        return self.required_params | self.optional_params | set(self.choice_params)


class GeneratorCatalog:
    """Catálogo de generadores disponibles en `mech-toolkit`."""

    def __init__(self, specs: list[GeneratorSpec]) -> None:
        self._por_nombre = {spec.name: spec for spec in specs}

    def get(self, name: str) -> GeneratorSpec | None:
        return self._por_nombre.get(name)

    def describe(self) -> str:
        """Descripción para el prompt del Part Designer.

        Se deriva del catálogo en vez de escribirse a mano en el .md: si
        alguien añade un generador y la lista fuera manual, el agente
        seguiría sin conocerlo.
        """
        lineas = []
        for spec in self._por_nombre.values():
            obligatorios = sorted(spec.required_params) + [
                f"{nombre}: {' | '.join(repr(o) for o in sorted(opciones))}"
                for nombre, opciones in sorted(spec.choice_params.items())
            ]
            lineas.append(f"- `{spec.name}({', '.join(obligatorios)})`")
            if spec.description:
                lineas.append(f"    {spec.description}")
            if spec.optional_params:
                opcionales = ", ".join(sorted(spec.optional_params))
                lineas.append(f"    opcionales: {opcionales}")
        return "\n".join(lineas)


def _es_numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _es_lista_de_numeros(v) -> bool:
    return isinstance(v, list) and all(_es_numero(x) or _es_lista_de_numeros(x) for x in v)


def _validar_valor(generador: str, spec: GeneratorSpec, nombre: str, valor) -> None:
    """Los valores se pegan en el código de build.py que ejecuta FreeCAD.
    Solo números, listas de números u opciones cerradas: un texto libre
    sería código arbitrario (ADR-002)."""
    if nombre in spec.choice_params:
        if valor not in spec.choice_params[nombre]:
            raise RecipeError(
                f"{generador}: {nombre}={valor!r} no es válido. "
                f"Opciones: {sorted(spec.choice_params[nombre])}."
            )
        return
    if not (_es_numero(valor) or _es_lista_de_numeros(valor)):
        raise RecipeError(
            f"{generador}: {nombre} tiene que ser un número (en mm o grados), "
            f"no {valor!r}."
        )


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
            # Las opciones también son obligatorias: sin `axis`, el cilindro no tiene eje.
            faltantes = sorted((spec.required_params | set(spec.choice_params)) - paso.params.keys())
            if faltantes:
                raise RecipeError(
                    f"{paso.generator}: faltan parámetros obligatorios "
                    f"{faltantes}."
                )
            for nombre, valor in paso.params.items():
                _validar_valor(paso.generator, spec, nombre, valor)
            desconocidos = sorted(paso.params.keys() - spec.allowed_params)
            if desconocidos:
                raise RecipeError(
                    f"{paso.generator}: parámetros desconocidos {desconocidos}. "
                    "Ignorarlos daría una pieza con geometría incorrecta y "
                    "sin ningún error visible."
                )
