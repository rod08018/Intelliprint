"""Receta → build.py. Ver DECISIONES.md ADR-002.

El LLM produce la receta; este módulo produce el Python. Las plantillas de
los generadores las escribe un humano, así que el código ejecutado nunca
sale de un modelo — esa es la propiedad que hace segura la ejecución.
"""

import json
from pathlib import Path

from orchestrator.schemas.recipe import GeneratorCatalog, Recipe

RESULT_PREFIX = "INTELLIPRINT_RESULT:"
"""Prefijo de la línea de stdout que el orquestador parsea. FreeCAD escribe
su propio banner y barras de progreso, así que el resultado va marcado."""

_PREAMBULO = '''\
# build.py — GENERADO desde recipe.json. No editar a mano:
# se regenera desde los parámetros en cada iteración (ADR-002).
import json

import FreeCAD
import Part

doc = FreeCAD.newDocument({part!r})
'''

_EPILOGO = '''
doc.recompute()

_solidos = [o for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Volume > 0]
if not _solidos:
    raise RuntimeError("la receta no produjo ningun solido")

# Convención: el último sólido es la pieza final.
_pieza = _solidos[-1]
_bb = _pieza.Shape.BoundBox

Part.export([_pieza], {stl!r})
Part.export([_pieza], {step!r})
doc.saveAs({fcstd!r})

print({prefix!r} + json.dumps({{
    "part": {part!r},
    "volume_mm3": _pieza.Shape.Volume,
    "bbox_mm": [_bb.XLength, _bb.YLength, _bb.ZLength],
    "solids": len(_solidos),
}}))
'''


def compose_build_script(
    recipe: Recipe,
    catalog: GeneratorCatalog,
    output_dir: Path | str = ".",
) -> str:
    """Compone el `build.py` de una pieza.

    Valida la receta contra el catálogo antes de componer nada: un error del
    modelo se detecta aquí, sin llegar a lanzar FreeCAD.
    """
    recipe.validate_against(catalog)

    salida = Path(output_dir)
    partes = [_PREAMBULO.format(part=recipe.part)]

    for numero, paso in enumerate(recipe.steps, start=1):
        spec = catalog.get(paso.generator)
        partes.append(f"\n# --- paso {numero}: {paso.generator} ---\n")
        partes.append(spec.template.format(**paso.params))
        partes.append("\n")

    partes.append(
        _EPILOGO.format(
            part=recipe.part,
            stl=str(salida / f"{recipe.part}.stl"),
            step=str(salida / f"{recipe.part}.step"),
            fcstd=str(salida / f"{recipe.part}.FCStd"),
            prefix=RESULT_PREFIX,
        )
    )
    return "".join(partes)
