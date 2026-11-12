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

SOLIDOS_FREECAD = '''\
# Lo comprado que va montado en una pieza (el cuerpo de un servo), de cajas
# y cilindros de su ficha ya colocados: se mueve con su pieza.
for n, primitivas in (datos.get("solidos") or dict()).items():
    trozos = []
    for p in primitivas:
        if p["tipo"] == "caja":
            a, b = p["min"], p["max"]
            trozos.append(Part.makeBox(b[0] - a[0], b[1] - a[1], b[2] - a[2],
                                       FreeCAD.Vector(*a)))
        else:
            base, eje = FreeCAD.Vector(*p["base"]), FreeCAD.Vector(*p["eje"])
            c = Part.makeCylinder(p["diametro"] / 2, p["alto"], base, eje)
            if p.get("interior"):
                c = c.cut(Part.makeCylinder(p["interior"] / 2, p["alto"], base, eje))
            trozos.append(c)
    forma = trozos[0]
    for t in trozos[1:]:
        forma = forma.fuse(t)
    formas[n] = forma
'''
"""Lo comparten el ensamble y la animación (`animation._TESELAR`): sin llaves,
porque los dos guiones pasan por `str.format`."""

_SCRIPT = '''\
import itertools
import json
import FreeCAD
import Part

datos = json.load(open({entrada!r}))
formas = {{n: Part.read(p) for n, p in datos["parts"].items()}}
for n, (d, largo) in datos["pins"].items():
    formas[n] = Part.makeCylinder(d / 2, largo)
''' + SOLIDOS_FREECAD + '''

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
elif datos.get("gaps"):
    # Hueco firmado (negativo = volumen común) de pares concretos, por pose.
    salida = []
    for frame in datos["frames"]:
        for a, b in datos["gaps"]:
            fa = colocar(formas[a], frame["poses"][a])
            fb = colocar(formas[b], frame["poses"][b])
            dist = fa.distToShape(fb)[0]
            if dist < 1e-4:
                comun = fa.common(fb).Volume
                dist = -comun if comun > 1e-3 else 0.0
            salida.append({{"angle": frame["angle"], "a": a, "b": b, "gap_mm": dist}})
    print({prefijo!r} + json.dumps({{"gaps": salida}}))
else:
    # La caja de cada forma en su marco: sus ocho esquinas, colocadas, dan
    # una caja que la contiene en esa pose sin tocar la geometría.
    esquinas = {{}}
    for n, f in formas.items():
        c = f.BoundBox
        esquinas[n] = [FreeCAD.Vector(x, y, z) for x in (c.XMin, c.XMax)
                       for y in (c.YMin, c.YMax) for z in (c.ZMin, c.ZMax)]

    def caja(n, pose):
        if pose.get("scale_z", 1.0) != 1.0:
            return None          # se estira: su caja no es la de sus esquinas
        x, y, z = pose["origin"]
        rx, ry, rz = pose["rotation"]
        donde = FreeCAD.Placement(FreeCAD.Vector(x, y, z), FreeCAD.Rotation(rz, ry, rx))
        puntos = [donde.multVec(v) for v in esquinas[n]]
        return ([min(p[k] for p in puntos) for k in range(3)],
                [max(p[k] for p in puntos) for k in range(3)])

    def separadas(ca, cb, mas_de):
        return any(ca[0][k] - cb[1][k] > mas_de or cb[0][k] - ca[1][k] > mas_de
                   for k in range(3))

    choques, medidos, descartados = [], 0, 0
    for frame in datos["frames"]:
        cajas = {{n: caja(n, frame["poses"][n]) for n in formas}}
        colocadas = {{}}

        def colocada(n):
            # Solo lo que se va a medir: copiar y colocar una pieza de verdad
            # en cada pose ya cuesta, y la mayoría no se mide.
            if n not in colocadas:
                colocadas[n] = colocar(formas[n], frame["poses"][n])
            return colocadas[n]

        for a, b in itertools.combinations(sorted(formas), 2):
            minimo, maximo = datos["rules"].get(a + "|" + b, (datos["min_gap"], None))
            if minimo < -1e8 and maximo is None:
                continue   # un par que no se mide: no se gasta en medirlo
            # Si sus cajas están más separadas que la holgura, no pueden
            # rozarse. Con tres giros en serie son 19³ poses y casi todas son
            # así: medirlas todas pasó de los 600 s en el banco 1112-0318.
            # Con un máximo (dos piezas que tienen que tocarse) sí se mide.
            if (maximo is None and cajas[a] is not None and cajas[b] is not None
                    and separadas(cajas[a], cajas[b], max(minimo, 0.0) + 1e-3)):
                descartados += 1
                continue
            medidos += 1
            fa, fb = colocada(a), colocada(b)
            dist = fa.distToShape(fb)[0]
            if dist < 1e-4:
                # distToShape da 0 tanto si se tocan como si se solapan:
                # el volumen común distingue un choque de verdad.
                comun = fa.common(fb).Volume
                dist = -comun if comun > 1e-3 else 0.0
            if dist < minimo - 1e-6:
                choques.append({{"angle": frame["angle"], "a": a, "b": b, "gap_mm": dist,
                                 "min_gap_mm": minimo, "kind": "choque"}})
            elif maximo is not None and dist > maximo + 1e-6:
                choques.append({{"angle": frame["angle"], "a": a, "b": b, "gap_mm": dist,
                                 "min_gap_mm": maximo, "kind": "separacion"}})
    print({prefijo!r} + json.dumps({{"collisions": choques, "medidos": medidos,
                                     "descartados": descartados}}))
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


def _datos(parts, pins, frames: dict[float, dict[str, Placement]], solidos=None) -> dict:
    return {
        "parts": {n: str(Path(p).resolve()) for n, p in parts.items()},
        "pins": {n: list(v) for n, v in pins.items()},
        "solidos": solidos or {},
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
    solidos: dict[str, list[dict]] | None = None,
) -> None:
    """Guarda el ensamble en `fcstd`, con todo visible. `solidos`: piezas
    hechas de cajas y cilindros ({min, max} o {base, eje, diametro, alto})."""
    fcstd = Path(fcstd)
    fcstd.parent.mkdir(parents=True, exist_ok=True)
    datos = _datos(parts, pins, {0: poses}, solidos)
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
    solidos: dict[str, list[dict]] | None = None,
) -> list[Collision]:
    """Pares de piezas que incumplen su regla de hueco, en cada pose."""
    datos = _datos(parts, pins, frames, solidos)
    datos["min_gap"] = min_gap_mm
    # El script recorre los pares en orden alfabético: se registran las dos claves.
    datos["rules"] = {
        f"{x}|{y}": list(regla)
        for (a, b), regla in (rules or {}).items() for x, y in ((a, b), (b, a))
    }
    return [Collision(**c) for c in _run(datos, freecadcmd)["collisions"]]


def pair_gaps(
    parts: dict[str, Path],
    pins: dict[str, tuple[float, float]],
    frames: dict[float, dict[str, Placement]],
    pares: list[tuple[str, str]],
    freecadcmd: str,
) -> list[dict]:
    """Hueco firmado de cada par en cada pose: negativo = se atraviesan (mm³)."""
    datos = _datos(parts, pins, frames)
    datos["gaps"] = [list(p) for p in pares]
    return _run(datos, freecadcmd)["gaps"]
