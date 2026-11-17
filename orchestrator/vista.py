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
