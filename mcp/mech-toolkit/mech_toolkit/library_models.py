"""Modelos de hardware comercial para la librería (F2.3).

Geometría escrita por un humano con las cotas de la hoja del fabricante:
ningún modelo de lenguaje debe inventar las medidas de un NEMA17 (§ 10).

Posición de montaje: los modelos se construyen en las MISMAS coordenadas
que las piezas que los alojan (centrados en el origen, con la cara de
montaje en z=0). Así, al insertar soporte y motor en un ensamblaje de
FreeCAD quedan montados sin tener que crear uniones.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

PREFIJO = "INTELLIPRINT_MODELO:"

# NEMA17 42x40 simplificado: cuerpo, saliente de centrado, eje y los
# cuatro M3 roscados de la brida. Suficiente para comprobar encaje; no
# modela los chaflanes del cuerpo ni el plano del eje.
_NEMA17 = '''\
import json
import FreeCAD
import Part

V = FreeCAD.Vector
L, H = 42.3, 40.0           # lado y largo del cuerpo
PILOTO_D, PILOTO_H = 22.0, 2.0
EJE_D, EJE_L = 5.0, 24.0
M3_D, M3_PROF, CUADRO = 3.0, 4.5, 31.0

cuerpo = Part.makeBox(L, L, H, V(-L / 2, -L / 2, -H))      # cara en z=0, hacia abajo
piloto = Part.makeCylinder(PILOTO_D / 2, PILOTO_H, V(0, 0, 0))
eje = Part.makeCylinder(EJE_D / 2, EJE_L, V(0, 0, 0))
motor = cuerpo.fuse(piloto).fuse(eje)
s = CUADRO / 2
for x, y in [(s, s), (-s, s), (s, -s), (-s, -s)]:
    motor = motor.cut(Part.makeCylinder(M3_D / 2, M3_PROF, V(x, y, -M3_PROF)))
motor = motor.removeSplitter()

doc = FreeCAD.newDocument("nema17_42x40")
obj = doc.addObject("Part::Feature", "nema17_42x40")
obj.Shape = motor
obj.Label = "nema17_42x40"
doc.recompute()
Part.export([obj], {step!r})
doc.saveAs({fcstd!r})
bb = motor.BoundBox
print({prefijo!r} + json.dumps({{
    "bbox_mm": [bb.XLength, bb.YLength, bb.ZLength],
    "zmin": bb.ZMin, "zmax": bb.ZMax,
    "solids": len(motor.Solids), "valid": motor.isValid(),
    "fcstd_object": obj.Name,
}}))
'''


class ModeloConstruido(BaseModel):
    bbox_mm: list[float]
    zmin: float
    zmax: float
    solids: int
    valid: bool
    fcstd_object: str


def build_nema17(salida: Path, freecadcmd: str) -> ModeloConstruido:
    from orchestrator.fcstd import mostrar_solo

    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    fcstd, step = salida / "nema17_42x40.FCStd", salida / "nema17_42x40.step"
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "nema17.py"
        script.write_text(
            _NEMA17.format(step=str(step), fcstd=str(fcstd), prefijo=PREFIJO),
            encoding="utf-8",
        )
        proceso = subprocess.run(
            [freecadcmd, str(script)], capture_output=True, text=True, timeout=180
        )
    for linea in proceso.stdout.splitlines():
        if linea.startswith(PREFIJO):
            modelo = ModeloConstruido(**json.loads(linea[len(PREFIJO):]))
            # Sin esto FreeCAD abre el .FCStd con todo oculto (orchestrator/fcstd.py).
            mostrar_solo(fcstd, modelo.fcstd_object)
            return modelo
    raise RuntimeError(f"no se pudo construir el NEMA17:\n{proceso.stderr[-600:]}")
