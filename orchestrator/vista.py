"""Una imagen de las piezas de un proyecto que no es un mecanismo
(F5.5 (web)).

Un mecanismo tiene su animación; una pieza suelta —la de calibración, un
soporte— no tenía nada que enseñar, y la web decía «3 piezas» y nada más
(2026-10-24). Se dibuja con las mallas de las STL, sin FreeCAD, con el
mismo dibujante que las animaciones.
"""

from pathlib import Path

from mech_toolkit.geometry import Placement

from orchestrator.proyecto_3mf import leer_stl

HUECO_MM = 10.0
COLORES = ("#e8833a", "#3a7be8", "#9aa5b1", "#5bb36a", "#c94f7c", "#d6b33a")


def dibujar_piezas(stls: list[Path], destino: Path, titulo: str = "") -> Path:
    """Las piezas en fila, como irían en la cama, en un PNG."""
    from PIL import Image

    from orchestrator.animation import render_gif

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
    if not mallas:
        raise ValueError("ninguna pieza tiene triángulos")
    destino = Path(destino)
    gif = render_gif(mallas, [(0, poses)], destino.with_suffix(".tmp.gif"), title=titulo,
                     colors=colores, label=lambda t: "", view=(35, -60))
    with Image.open(gif) as imagen:
        imagen.convert("RGB").save(destino, "PNG")
    Path(gif).unlink(missing_ok=True)
    return destino
