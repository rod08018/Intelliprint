"""Modelos de referencia de la librería (F2.3).

Los modelos de hardware comercial NO los dibuja el sistema: se descargan de
fuentes independientes (library/models/reference/, con autor y licencia).
Si el sistema diseñara la pieza y también su referencia con los mismos
números, que encajen no probaría nada — es circular, el mismo fallo que
ADR-011. Una referencia dibujada por otra persona a partir del objeto real
sí puede contradecirnos, y eso es lo que la hace útil.

Aquí solo se IMPORTAN: el STEP original no se toca, y se genera un .FCStd
porque "Insert Component" de FreeCAD no acepta STEP.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

PREFIJO = "INTELLIPRINT_MODELO:"

_IMPORTAR = '''\
import json
import FreeCAD
import Part

forma = Part.read({step!r})
forma.translate(FreeCAD.Vector(0, 0, {dz!r}))
doc = FreeCAD.newDocument({nombre!r})
obj = doc.addObject("Part::Feature", {nombre!r})
obj.Shape = forma
obj.Label = {nombre!r}
doc.recompute()
doc.saveAs({fcstd!r})
bb = forma.BoundBox
print({prefijo!r} + json.dumps({{
    "bbox_mm": [bb.XLength, bb.YLength, bb.ZLength],
    "zmin": bb.ZMin, "zmax": bb.ZMax,
    "solids": len(forma.Solids), "valid": forma.isValid(),
    "fcstd_object": obj.Name,
}}))
'''


class ModeloImportado(BaseModel):
    bbox_mm: list[float]
    zmin: float
    zmax: float
    solids: int
    valid: bool
    fcstd_object: str


def import_reference(
    step: Path, fcstd: Path, freecadcmd: str, dz: float = 0.0
) -> ModeloImportado:
    """STEP de referencia → .FCStd listo para "Insert Component".

    `dz` desplaza el modelo para dejarlo en posición de montaje. Ese valor
    se MIDE en la geometría del propio modelo (p. ej. dónde está su cara
    frontal), no se toma de nuestras cotas: si no, volveríamos a la
    referencia circular.
    """
    from orchestrator.fcstd import mostrar_solo

    fcstd = Path(fcstd)
    fcstd.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "importar.py"
        script.write_text(
            _IMPORTAR.format(
                step=str(Path(step).resolve()), fcstd=str(fcstd.resolve()),
                nombre=fcstd.stem, dz=float(dz), prefijo=PREFIJO,
            ),
            encoding="utf-8",
        )
        proceso = subprocess.run(
            [freecadcmd, str(script)], capture_output=True, text=True, timeout=180
        )
    for linea in proceso.stdout.splitlines():
        if linea.startswith(PREFIJO):
            modelo = ModeloImportado(**json.loads(linea[len(PREFIJO):]))
            # Sin esto FreeCAD abre el .FCStd con todo oculto (orchestrator/fcstd.py).
            mostrar_solo(fcstd, modelo.fcstd_object)
            return modelo
    raise RuntimeError(f"no se pudo importar {step}:\n{proceso.stderr[-600:]}")
