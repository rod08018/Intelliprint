"""Receta del Part Designer: lo que el LLM produce en vez de Python.

Ver SISTEMA_MULTIAGENTE.md § 6.3 y DECISIONES.md ADR-002.
"""

import pytest
from pydantic import ValidationError

from orchestrator.schemas.recipe import (
    GeneratorCatalog,
    GeneratorSpec,
    Recipe,
    RecipeError,
    RecipeStep,
)


def _catalogo_minimo() -> GeneratorCatalog:
    return GeneratorCatalog(
        [
            GeneratorSpec(
                name="generate_bolt_pattern",
                required_params={"screw_id", "count", "pcd_mm"},
                choice_params={"screw_id": {"screw_M3x12", "screw_M3x16"}},
            )
        ]
    )


def test_receta_rechaza_generador_que_no_existe_en_el_catalogo():
    """El valor de ADR-002: un error del modelo se detecta ANTES de ejecutar.

    Si el Part Designer escribiera Python, inventarse una función sería un
    traceback tras lanzar FreeCAD. Con recetas es un rechazo de esquema.
    """
    receta = Recipe(
        part="base_servo",
        steps=[RecipeStep(generator="generate_unicornio", params={})],
    )

    with pytest.raises(RecipeError, match="generate_unicornio"):
        receta.validate_against(_catalogo_minimo())


def test_receta_rechaza_parametros_obligatorios_que_faltan():
    """Un generador existente llamado con datos incompletos tampoco vale.

    El error debe nombrar el parámetro que falta: es lo que se le devuelve
    al agente para que reintente sin lanzar FreeCAD (F1.11 (bucle), primer nivel).
    """
    receta = Recipe(
        part="base_servo",
        steps=[
            RecipeStep(
                generator="generate_bolt_pattern",
                params={"screw_id": "screw_M3x12"},
            )
        ],
    )

    with pytest.raises(RecipeError, match="pcd_mm"):
        receta.validate_against(_catalogo_minimo())


def test_receta_valida_pasa_la_validacion():
    """Sin este test, un validador que siempre lanzara error pasaría los otros."""
    receta = Recipe(
        part="base_servo",
        steps=[
            RecipeStep(
                generator="generate_bolt_pattern",
                params={"screw_id": "screw_M3x12", "count": 4, "pcd_mm": 30},
            )
        ],
    )

    receta.validate_against(_catalogo_minimo())


def test_receta_rechaza_parametros_que_el_generador_no_conoce():
    """Un parámetro inventado no puede ignorarse en silencio.

    Si el modelo escribe `pcd_diameter` en vez de `pcd_mm` y lo dejamos
    pasar, el generador usaría su valor por defecto y la pieza saldría
    con geometría incorrecta pero sin ningún error. Ese fallo silencioso
    es peor que un rechazo.
    """
    receta = Recipe(
        part="base_servo",
        steps=[
            RecipeStep(
                generator="generate_bolt_pattern",
                params={
                    "screw_id": "screw_M3x12",
                    "count": 4,
                    "pcd_mm": 30,
                    "pcd_diameter": 30,
                },
            )
        ],
    )

    with pytest.raises(RecipeError, match="pcd_diameter"):
        receta.validate_against(_catalogo_minimo())


def test_receta_sin_pasos_se_rechaza():
    """Una receta vacía compone un build.py vacío: pieza vacía, cero errores.

    Validez intrínseca, así que es ValidationError de pydantic y no
    RecipeError: no hace falta el catálogo para saber que está mal.
    """
    with pytest.raises(ValidationError, match="al menos un paso"):
        Recipe(part="base_servo", steps=[])


@pytest.mark.parametrize("valor", [
    "__import__('os').system('rm -rf ~')",
    "30); import os; os.system('x'",
    True,
    None,
    {"a": 1},
])
def test_receta_rechaza_valores_que_no_son_numeros(valor):
    """Los valores se pegan dentro de build.py, que ejecuta FreeCAD. Si un
    valor pudiera ser texto, el modelo (o una petición con texto inyectado)
    podría meter código: se acabaría la garantía de ADR-002."""
    receta = Recipe(part="p", steps=[RecipeStep(
        generator="generate_bolt_pattern",
        params={"screw_id": "screw_M3x12", "count": 4, "pcd_mm": valor})])
    with pytest.raises(RecipeError, match="pcd_mm"):
        receta.validate_against(_catalogo_minimo())


def test_un_parametro_de_opciones_solo_acepta_sus_opciones():
    receta = Recipe(part="p", steps=[RecipeStep(
        generator="generate_bolt_pattern",
        params={"screw_id": "screw_M3x12'); import os; ('", "count": 4, "pcd_mm": 30})])
    with pytest.raises(RecipeError, match="screw_id"):
        receta.validate_against(_catalogo_minimo())


def test_listas_de_numeros_se_aceptan_y_de_texto_no():
    cat = GeneratorCatalog([GeneratorSpec(name="g", required_params={"points_mm"})])
    ok = Recipe(part="p", steps=[RecipeStep(generator="g", params={"points_mm": [[0, 0], [1, 2.5]]})])
    ok.validate_against(cat)
    mal = Recipe(part="p", steps=[RecipeStep(generator="g", params={"points_mm": [[0, "os"]]})])
    with pytest.raises(RecipeError, match="points_mm"):
        mal.validate_against(cat)


def test_un_parametro_de_opciones_es_obligatorio():
    """Fallo real de DeepSeek: omitió `axis` en un cilindro y la receta pasó
    la validación; reventó después, al componer build.py."""
    receta = Recipe(part="p", steps=[RecipeStep(
        generator="generate_bolt_pattern", params={"count": 4, "pcd_mm": 30})])
    with pytest.raises(RecipeError, match="screw_id"):
        receta.validate_against(_catalogo_minimo())
