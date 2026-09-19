"""Ensamble de un mecanismo en FreeCAD y barrido de choques.

`build_assembly` guarda un .FCStd con cada pieza (importada de su STEP) y
cada eje en su sitio, todo visible: es lo que el usuario abre para
verificar el mecanismo con sus propios ojos.

`sweep_collisions` mueve el mecanismo por una lista de poses y mide la
distancia mínima entre cada par de sólidos. Un choque que solo ocurre a
cierto ángulo no se ve en una pose guardada; aquí sí. El criterio es
físico (F2.20 (encaje)): tocarse NO es funcionar; entre dos piezas tiene
que quedar al menos `min_gap_mm`.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

from mech_toolkit.geometry import Placement
from orchestrator.fcstd import mostrar

PREFIJO = "INTELLIPRINT_ENSAMBLE:"

_SCRIPT = '''\
import itertools
import json
import FreeCAD
import Part

datos = json.load(open({entrada!r}))
formas = {{n: Part.read(p) for n, p in datos["parts"].items()}}
for n, (d, largo) in datos["pins"].items():
    formas[n] = Part.makeCylinder(d / 2, largo)


def colocar(forma, pose):
    x, y, z = pose["origin"]
    rx, ry, rz = pose["rotation"]
    copia = forma.copy()
    if pose.get("scale_z", 1.0) != 1.0:
        m = FreeCAD.Matrix()
        m.scale(1, 1, pose["scale_z"])
        copia = copia.transformGeometry(m)
    # Rotation(yaw, pitch, roll) = Rz·Ry·Rx, igual que mech_toolkit.geometry.
    copia.Placement = FreeCAD.Placement(
        FreeCAD.Vector(x, y, z), FreeCAD.Rotation(rz, ry, rx))
    return copia


if datos.get("fcstd"):
    doc = FreeCAD.newDocument("assembly")
    pose = datos["frames"][0]["poses"]
    for n, forma in formas.items():
        obj = doc.addObject("Part::Feature", n)
        obj.Shape = colocar(forma, pose[n])
        obj.Label = n
    doc.recompute()
    doc.saveAs(datos["fcstd"])
    print({prefijo!r} + json.dumps({{"objects": [o.Name for o in doc.Objects]}}))
else:
    choques = []
    for frame in datos["frames"]:
        colocadas = {{n: colocar(f, frame["poses"][n]) for n, f in formas.items()}}
        for a, b in itertools.combinations(sorted(colocadas), 2):
            fa, fb = colocadas[a], colocadas[b]
            dist = fa.distToShape(fb)[0]
            if dist < 1e-4:
                # distToShape da 0 tanto si se tocan como si se solapan:
                # el volumen común distingue un choque de verdad.
                comun = fa.common(fb).Volume
                dist = -comun if comun > 1e-3 else 0.0
            minimo, maximo = datos["rules"].get(a + "|" + b, (datos["min_gap"], None))
            if dist < minimo - 1e-6:
                choques.append({{"angle": frame["angle"], "a": a, "b": b, "gap_mm": dist,
                                 "min_gap_mm": minimo, "kind": "choque"}})
            elif maximo is not None and dist > maximo + 1e-6:
                choques.append({{"angle": frame["angle"], "a": a, "b": b, "gap_mm": dist,
                                 "min_gap_mm": maximo, "kind": "separacion"}})
    print({prefijo!r} + json.dumps({{"collisions": choques}}))
'''


PairRule = tuple[float, float | None]
"""(hueco mínimo, hueco máximo o None) para un par de piezas. Por defecto
el mínimo es la holgura del perfil y no hay máximo. Un par que TIENE que
tocarse (seguidor y leva) lleva (0, 0.05); uno fijo entre sí (leva y eje
con ajuste a presión) lleva (0, None): tocarse sí, atravesarse no."""


class Collision(BaseModel):
    angle: float
    a: str
    b: str
    gap_mm: float
    """Distancia mínima entre las dos piezas. Negativa = se solapan, y su
    valor absoluto es el volumen común en mm³."""
    min_gap_mm: float
    """El límite incumplido: el mínimo si es un choque, el máximo si se separan."""
    kind: str = "choque"

    @property
    def motivo(self) -> str:
        if self.kind == "separacion":
            return (
                f"con t = {self.angle:g}, {self.a} y {self.b} se separan {self.gap_mm:.2f} mm; "
                f"tienen que seguir en contacto (máximo {self.min_gap_mm:g} mm)"
            )
        if self.gap_mm < 0:
            que = f"se solapan ({-self.gap_mm:.1f} mm³ en común)"
        else:
            que = f"quedan a {self.gap_mm:.2f} mm"
        return (
            f"con t = {self.angle:g}, {self.a} y {self.b} {que}; "
            f"hace falta al menos {self.min_gap_mm:g} mm para que no rocen"
        )


def _run(datos: dict, freecadcmd: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / "entrada.json"
        entrada.write_text(json.dumps(datos), encoding="utf-8")
        script = Path(tmp) / "ensamble.py"
        script.write_text(
            _SCRIPT.format(entrada=str(entrada), prefijo=PREFIJO), encoding="utf-8"
        )
        proceso = subprocess.run(
            [freecadcmd, str(script)], capture_output=True, text=True, timeout=600
        )
    for linea in proceso.stdout.splitlines():
        if linea.startswith(PREFIJO):
            return json.loads(linea[len(PREFIJO):])
    raise RuntimeError(f"el ensamble falló:\n{(proceso.stdout + proceso.stderr)[-800:]}")


def _datos(parts, pins, frames: dict[float, dict[str, Placement]]) -> dict:
    return {
        "parts": {n: str(Path(p).resolve()) for n, p in parts.items()},
        "pins": {n: list(v) for n, v in pins.items()},
        "frames": [
            {"angle": a, "poses": {n: p.model_dump() for n, p in poses.items()}}
            for a, poses in frames.items()
        ],
    }


def build_assembly(
    parts: dict[str, Path],
    pins: dict[str, tuple[float, float]],
    poses: dict[str, Placement],
    fcstd: Path,
    freecadcmd: str,
) -> None:
    """Guarda el ensamble en `fcstd`, con todo visible."""
    fcstd = Path(fcstd)
    fcstd.parent.mkdir(parents=True, exist_ok=True)
    datos = _datos(parts, pins, {0: poses})
    datos["fcstd"] = str(fcstd.resolve())
    objetos = _run(datos, freecadcmd)["objects"]
    # Sin esto FreeCAD lo abre todo oculto (orchestrator/fcstd.py).
    mostrar(fcstd, set(objetos))


def sweep_collisions(
    parts: dict[str, Path],
    pins: dict[str, tuple[float, float]],
    frames: dict[float, dict[str, Placement]],
    min_gap_mm: float,
    freecadcmd: str,
    rules: dict[tuple[str, str], PairRule] | None = None,
) -> list[Collision]:
    """Pares de piezas que incumplen su regla de hueco, en cada pose."""
    datos = _datos(parts, pins, frames)
    datos["min_gap"] = min_gap_mm
    # El script recorre los pares en orden alfabético: se registran las dos claves.
    datos["rules"] = {
        f"{x}|{y}": list(regla)
        for (a, b), regla in (rules or {}).items() for x, y in ((a, b), (b, a))
    }
    return [Collision(**c) for c in _run(datos, freecadcmd)["collisions"]]
