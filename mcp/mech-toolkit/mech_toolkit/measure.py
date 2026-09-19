"""Extracción de hechos geométricos con FreeCAD (F2.13 (puente)).

Este script solo LISTA lo que hay: las caras cilíndricas de la pieza. No
decide qué cara es de qué interfaz; eso lo hace `geometry.py` buscando
donde el contrato dice que debe estar (ADR-011).
"""

import json
import subprocess
import tempfile
from pathlib import Path

from mech_toolkit.geometry import Cylinder

PREFIJO = "INTELLIPRINT_FEATURES:"

# Se lee el STEP y no el .FCStd: el STEP contiene solo la pieza final, con
# sus cilindros exactos; el .FCStd arrastra las brocas y cortes intermedios.
_EXTRACTOR = '''\
import json
import Part

forma = Part.read({step!r})
caras = []
for cara in forma.Faces:
    superficie = cara.Surface
    if superficie.__class__.__name__ != "Cylinder":
        continue
    u0, u1, v0, v1 = cara.ParameterRange
    eje = superficie.Axis
    # En un cilindro de OpenCASCADE, v es la distancia a lo largo del eje
    # desde Center: el punto medio de la cara está en Center + eje·(v0+v1)/2.
    medio = superficie.Center + eje * ((v0 + v1) / 2.0)
    # Agujero o saliente: en un agujero la normal de la cara apunta hacia el
    # eje; en un saliente, hacia fuera. normalAt ya tiene en cuenta si la
    # cara está invertida.
    u, v = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    punto = cara.valueAt(u, v)
    sobre_eje = superficie.Center + eje * (punto - superficie.Center).dot(eje)
    interior = cara.normalAt(u, v).dot(punto - sobre_eje) < 0
    caras.append({{
        "radius": superficie.Radius,
        "axis": [eje.x, eje.y, eje.z],
        "point": [medio.x, medio.y, medio.z],
        "length": abs(v1 - v0),
        "internal": bool(interior),
    }})
print({prefijo!r} + json.dumps(caras))
'''


class ExtraccionFallida(RuntimeError):
    pass


def extract_cylinders(step: Path, freecadcmd: str) -> list[Cylinder]:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "extraer.py"
        script.write_text(
            _EXTRACTOR.format(step=str(step), prefijo=PREFIJO), encoding="utf-8"
        )
        proceso = subprocess.run(
            [freecadcmd, str(script)], capture_output=True, text=True, timeout=180
        )
    for linea in proceso.stdout.splitlines():
        if linea.startswith(PREFIJO):
            return [Cylinder(**c) for c in json.loads(linea[len(PREFIJO):])]
    raise ExtraccionFallida(
        f"FreeCAD no devolvió las caras de {step}:\n{proceso.stderr[-600:]}"
    )
