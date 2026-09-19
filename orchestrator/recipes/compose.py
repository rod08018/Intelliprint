"""Receta → build.py. Ver DECISIONES.md ADR-002.

El LLM produce la receta; este módulo produce el Python. Las plantillas de
los generadores las escribe un humano, así que el código ejecutado nunca
sale de un modelo — esa es la propiedad que hace segura la ejecución.
"""

import json
from pathlib import Path
from string import Template

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
_forma = _pieza.Shape

# F1.7 (validez). Las dos comprobaciones hacen falta: una pieza partida en trozos por
# un taladro demasiado grande es isValid()=True, y una cáscara abierta tiene
# un volumen plausible. Fallar aquí, al construir, y no tres fases después.
if not _forma.isValid():
    raise RuntimeError("INTELLIPRINT_FALLO: el sólido de la pieza no es válido "
                       "(forma degenerada o cáscara abierta)")
_n_solidos = len(_forma.Solids)
if _n_solidos != 1:
    raise RuntimeError("INTELLIPRINT_FALLO: la pieza salió en %d sólidos "
                       "separados; debería ser una sola" % _n_solidos)

_bb = _forma.BoundBox

# La visibilidad que ve el usuario al abrir el .FCStd NO sale de aquí: sin
# interfaz no hay GuiDocument.xml y FreeCAD lo abre todo oculto. Eso lo
# arregla orchestrator/fcstd.py después de construir. Esto deja coherente la
# propiedad del documento y, sobre todo, pone a la pieza final su nombre
# para poder encontrarla en el árbol al ensamblar.
for _o in doc.Objects:
    _o.Visibility = _o is _pieza
_pieza.Label = {part!r}

Part.export([_pieza], {stl!r})
Part.export([_pieza], {step!r})
doc.saveAs({fcstd!r})

print({prefix!r} + json.dumps({{
    "part": {part!r},
    "volume_mm3": _forma.Volume,
    "bbox_mm": [_bb.XLength, _bb.YLength, _bb.ZLength],
    "bbox_min": [_bb.XMin, _bb.YMin, _bb.ZMin],
    "bbox_max": [_bb.XMax, _bb.YMax, _bb.ZMax],
    "solids": _n_solidos,
    "fcstd_object": _pieza.Name,
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
        # `string.Template` y no str.format: las plantillas son código Python
        # real, con dicts, listas por comprensión y bucles. Cualquier `{`
        # literal rompería format, lo que dejaría fuera a casi todo generador
        # no trivial. `substitute` además falla si falta un parámetro.
        # Los valores ya están validados (números, listas de números u
        # opciones cerradas); repr() pone las opciones entre comillas.
        valores = {k: repr(v) if isinstance(v, str) else v for k, v in paso.params.items()}
        partes.append(Template(spec.template).substitute(**valores))
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
