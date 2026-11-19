"""Una imagen de las piezas de un proyecto que no es un mecanismo
(F5.5 (web)).

Un mecanismo tiene su animación; una pieza suelta —la de calibración, un
soporte— no tenía nada que enseñar, y la web decía «3 piezas» y nada más
(2026-10-24). Se dibuja con las mallas de las STL, sin FreeCAD, con el
mismo dibujante que las animaciones.

Un invento de varias piezas (un backlog) se dibuja MONTADO: él, el
2026-11-17, «también debe mostrarse el ensamble de todo, porque del brazo y
eso no veo ensamble». La portada enseñaba sus piezas en fila, como en la cama.
"""

import json
from pathlib import Path

from mech_toolkit.geometry import Placement

from orchestrator.proyecto_3mf import leer_stl

HUECO_MM = 10.0
MARGEN_PX = 12
COLORES = ("#e8833a", "#3a7be8", "#9aa5b1", "#5bb36a", "#c94f7c", "#d6b33a")
COMPRADO = "comprado"
"""Lo comprado de un invento que no se mueve (las vigas de carbono, los
motores y las hélices del avión), en STL y ya en su sitio. Sin esto las
góndolas y las derivas salían flotando junto al ala: él, el 2026-11-17, «tiene
piezas fuera del modelo, no se entiende qué son»."""
COLOR_COMPRADO = "#33383d"


def guardar_comprado(carpeta: Path, mallas: dict[str, list]) -> list[Path]:
    """Cada malla ({nombre: [triángulo de tres puntos]}) en un STL binario de
    `comprado/`."""
    import struct
    destino = Path(carpeta) / COMPRADO
    destino.mkdir(parents=True, exist_ok=True)
    hechos = []
    for nombre, tris in mallas.items():
        ruta = destino / f"{nombre}.stl"
        datos = [bytes(80), struct.pack("<I", len(tris))]
        datos += [struct.pack("<12fH", 0, 0, 0, *(c for p in t for c in p), 0) for t in tris]
        ruta.write_bytes(b"".join(datos))
        hechos.append(ruta)
    return hechos


def dibujar_piezas(stls: list[Path], destino: Path, titulo: str = "") -> Path:
    """Las piezas en fila, como irían en la cama, en un PNG."""
    mallas, poses, colores = {}, {}, {}
    cursor = 0.0
    for i, stl in enumerate(stls):
        vertices, triangulos = leer_stl(stl)
        if not triangulos:
            continue
        xs, ys, zs = zip(*vertices)
        nombre = Path(stl).stem
        mallas[nombre] = ([list(v) for v in vertices], [list(t) for t in triangulos])
        poses[nombre] = Placement(origin=[cursor - min(xs), -(min(ys) + max(ys)) / 2, -min(zs)])
        colores[nombre] = COLORES[i % len(COLORES)]
        cursor += max(xs) - min(xs) + HUECO_MM
    return _dibujar(mallas, poses, colores, destino, titulo)


def conjunto_con_ensamble(carpeta: Path) -> str | None:
    """El último conjunto de la obra (el ensamble final) que ya dejó sus
    mallas para el visor."""
    carpeta = Path(carpeta)
    try:
        obra = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    conjuntos = [x["id"] for x in obra.get("nodos", []) if x.get("tipo") == "conjunto"]
    from orchestrator import obra as O
    try:
        orden = O.cargar_obra(carpeta).orden()
    except Exception:
        orden = conjuntos
    for i in reversed([i for i in orden if i in conjuntos]):
        if (carpeta / "nodos" / i / "ensamble.json").is_file():
            return i
    return None


def montado(carpeta: Path) -> tuple[dict, dict]:
    """({nombre: (vértices, triángulos)}, {nombre: color}) del invento
    montado, cada malla ya en su sitio.

    Con un conjunto que ya se movió, las mallas de su verificación (lo
    comprado incluido) en la postura de reposo, con la misma cinemática que
    el visor. Sin él —el avión no se mueve—, cada pieza donde se dibujó."""
    carpeta = Path(carpeta)
    conjunto = conjunto_con_ensamble(carpeta)
    mallas, colores = {}, {}
    if conjunto and (carpeta / "nodos" / conjunto / "verificacion.json").is_file():
        from orchestrator.conjunto import pose_para_el_visor
        datos = json.loads((carpeta / "nodos" / conjunto / "ensamble.json")
                           .read_text(encoding="utf-8"))
        poses = pose_para_el_visor(carpeta, conjunto, {})["poses"]
        for s, x in datos["solidos"].items():
            m = poses.get(x["pieza"], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
            v = x["v"]
            vertices = [[m[4 * f] * v[k] + m[4 * f + 1] * v[k + 1] + m[4 * f + 2] * v[k + 2]
                         + m[4 * f + 3] for f in range(3)] for k in range(0, len(v), 3)]
            t = x["t"]
            mallas[s] = (vertices, [t[k:k + 3] for k in range(0, len(t), 3)])
            colores[s] = x.get("color") or COLORES[len(colores) % len(COLORES)]
        return mallas, colores
    from orchestrator.web.versiones import piezas_de
    for i, stl in enumerate(piezas_de(carpeta)):
        vertices, triangulos = leer_stl(stl)
        if triangulos:
            mallas[stl.stem] = ([list(p) for p in vertices], [list(t) for t in triangulos])
            colores[stl.stem] = COLORES[i % len(COLORES)]
    for stl in sorted((carpeta / COMPRADO).glob("*.stl")):
        vertices, triangulos = leer_stl(stl)
        if triangulos:
            mallas[stl.stem] = ([list(p) for p in vertices], [list(t) for t in triangulos])
            colores[stl.stem] = COLOR_COMPRADO
    return mallas, colores


ENSAMBLE = "ensamble.FCStd"
"""El invento montado para abrirlo en el FreeCAD del PC (F13.14 (ensamble)).
Él, el 2026-11-18: «darle click en algún lado de la app y ver el avión
ensamblado»; en FreeCAD solo se podía abrir pieza a pieza."""
DENTRO = "dentro"
"""Lo que va dentro del avión (batería, electrónica, servos): no se ve en la
foto, pero en FreeCAD se puede esconder la piel y mirarlo."""
_FUENTES_ENSAMBLE = ("parts/*/*.stl", "nodos/*/parts/*/*.stl", "modulos/*/*/*.stl",
                     "nodos/*/ensamble.json", f"{COMPRADO}/*.stl", f"{DENTRO}/*/*.stl")
_ESCRIBIR_FCSTD = r'''
import json, os, FreeCAD, Mesh
datos = json.load(open(os.environ["INTELLIPRINT_ENSAMBLE"], encoding="utf-8"))
doc = FreeCAD.newDocument("Ensamble")
grupos = {}
for i, p in enumerate(datos["mallas"]):
    if p["grupo"] not in grupos:
        grupos[p["grupo"]] = doc.addObject("App::DocumentObjectGroup", p["grupo"])
    o = doc.addObject("Mesh::Feature", "Malla%03d" % i)
    o.Label = p["nombre"]
    o.Mesh = Mesh.Mesh(p["stl"])
    o.addProperty("App::PropertyColor", "Color", "Intelliprint",
                  "El color de la foto; lo pinta la macro del puente al abrirlo")
    o.Color = tuple(p["color"])
    grupos[p["grupo"]].addObject(o)
# Sin ventana, FreeCAD los guardaba ocultos y al abrirlos no se veía nada
# (2026-11-19).
for o in doc.Objects:
    o.Visibility = True
doc.recompute()
doc.saveAs(datos["destino"])
'''


def _firma_ensamble(carpeta: Path) -> list:
    return [[r.relative_to(carpeta).as_posix(), r.stat().st_mtime_ns, r.stat().st_size]
            for patron in _FUENTES_ENSAMBLE for r in sorted(carpeta.glob(patron))]


def _color(hexa: str) -> list[float]:
    return [int(hexa[k:k + 2], 16) / 255 for k in (1, 3, 5)]


def _escribir_stl(ruta: Path, vertices, triangulos) -> None:
    import struct
    datos = [bytes(80), struct.pack("<I", len(triangulos))]
    datos += [struct.pack("<12fH", 0, 0, 0, *(c for k in t for c in vertices[k]), 0)
              for t in triangulos]
    ruta.write_bytes(b"".join(datos))


def ensamble_fcstd(carpeta: Path, freecadcmd: str | None = None) -> Path:
    """`vistas/ensamble.FCStd`: cada pieza del invento montado
    (`montado`, las mismas mallas que la foto) en el grupo «Impreso» o
    «Comprado», y lo de `dentro/` en «Dentro». Solo se rehace si cambió algo
    de lo que sale (`vistas/ensamble.json` guarda la firma).

    Mallas y no los .step: el brazo se monta en reposo moviendo mallas
    (`pose_para_el_visor`), y así lo que se ve en FreeCAD es lo de la foto."""
    import os
    import subprocess
    import tempfile
    carpeta = Path(carpeta)
    destino = carpeta / "vistas" / ENSAMBLE
    guardada = carpeta / "vistas" / "ensamble.json"
    firma = _firma_ensamble(carpeta)
    try:
        if destino.is_file() and json.loads(guardada.read_text(encoding="utf-8")) == firma:
            return destino
    except (OSError, ValueError):
        pass
    mallas, colores = montado(carpeta)
    if not mallas:
        raise ValueError("este invento no tiene ninguna pieza con triángulos")
    freecadcmd = freecadcmd or os.environ.get("FREECADCMD")
    if not freecadcmd:
        raise ValueError("no hay FreeCAD con el que escribir el ensamble (define FREECADCMD)")
    destino.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        lista = []
        for i, (nombre, (vertices, triangulos)) in enumerate(mallas.items()):
            stl = tmp / f"{i:03d}.stl"
            _escribir_stl(stl, vertices, triangulos)
            lista.append({"nombre": nombre, "stl": str(stl), "color": _color(colores[nombre]),
                          "grupo": "Comprado" if colores[nombre] == COLOR_COMPRADO else "Impreso"})
        for i, stl in enumerate(sorted(carpeta.glob(f"{DENTRO}/*/*.stl"))):
            lista.append({"nombre": stl.stem, "stl": str(stl),
                          "color": _color(COLORES[i % len(COLORES)]), "grupo": "Dentro"})
        temporal = destino.with_suffix(".tmp.FCStd")
        (tmp / "datos.json").write_text(json.dumps({"mallas": lista, "destino": str(temporal)}),
                                        encoding="utf-8")
        (tmp / "escribir.py").write_text(_ESCRIBIR_FCSTD, encoding="utf-8")
        proceso = subprocess.run([freecadcmd, str(tmp / "escribir.py")], capture_output=True,
                                 text=True, timeout=900,
                                 env={**os.environ, "INTELLIPRINT_ENSAMBLE": str(tmp / "datos.json")})
        # freecadcmd sale con 0 aunque el guion falle: lo que dice si se hizo
        # es el archivo.
        if not temporal.is_file():
            raise ValueError(f"FreeCAD no escribió el ensamble: {proceso.stdout[-500:]}"
                             f"{proceso.stderr[-500:]}")
        temporal.replace(destino)
    guardada.write_text(json.dumps(firma), encoding="utf-8")
    return destino


def dibujar_montado(carpeta: Path, destino: Path, titulo: str = "") -> Path:
    """El invento montado (`montado`), en un PNG."""
    mallas, colores = montado(carpeta)
    return _dibujar(mallas, {n: Placement() for n in mallas}, colores, destino, titulo)


def _dibujar(mallas: dict, poses: dict, colores: dict, destino: Path, titulo: str) -> Path:
    from PIL import Image

    from orchestrator.animation import render_gif

    if not mallas:
        raise ValueError("ninguna pieza tiene triángulos")
    destino = Path(destino)
    gif = render_gif(mallas, [(0, poses)], destino.with_suffix(".tmp.gif"), title=titulo,
                     colors=colores, label=lambda t: "", view=(35, -60))
    with Image.open(gif) as imagen:
        imagen = imagen.convert("RGB")
    # Recortada a lo dibujado: los cuadros de la animación tienen tamaño fijo
    # (F7.6 (animacion)) y las piezas quedaban pequeñas en un lienzo blanco.
    caja = imagen.convert("L").point(lambda v: 255 if v < 240 else 0).getbbox()
    if caja:
        m = MARGEN_PX
        imagen = imagen.crop((max(caja[0] - m, 0), max(caja[1] - m, 0),
                              min(caja[2] + m, imagen.width), min(caja[3] + m, imagen.height)))
    imagen.save(destino, "PNG")
    Path(gif).unlink(missing_ok=True)
    return destino
