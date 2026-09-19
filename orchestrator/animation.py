"""Animación de un mecanismo: GIF de una vuelta completa.

FreeCAD (sin interfaz) solo tesela cada pieza UNA vez, en su marco local;
el movimiento se aplica aquí con las mismas poses que usa el barrido de
choques, así que lo que se ve es exactamente lo que se comprobó. Se dibuja
con matplotlib, sin abrir ninguna ventana.

Requiere el extra `render` (matplotlib y Pillow).
"""

import io
import json
import subprocess
import tempfile
from pathlib import Path

from mech_toolkit.geometry import Placement, _rotacion

PREFIJO = "INTELLIPRINT_MALLA:"

_TESELAR = '''\
import json
import Part

datos = json.load(open({entrada!r}))
formas = {{n: Part.read(p) for n, p in datos["parts"].items()}}
for n, (d, largo) in datos["pins"].items():
    formas[n] = Part.makeCylinder(d / 2, largo)
mallas = {{}}
for n, forma in formas.items():
    vertices, triangulos = forma.tessellate({tolerancia!r})
    mallas[n] = [[[v.x, v.y, v.z] for v in vertices], [list(t) for t in triangulos]]
json.dump(mallas, open({salida!r}, "w"))
print({prefijo!r} + "ok")
'''

COLORES = {
    "bancada": "#9aa5b1",
    "manivela": "#e8833a",
    "biela": "#3a7be8",
    "corredera": "#3bb273",
}
COLOR_EJE = "#444444"

Malla = tuple[list[list[float]], list[list[int]]]


def tessellate(
    parts: dict[str, Path],
    pins: dict[str, tuple[float, float]],
    freecadcmd: str,
    tolerancia: float = 0.3,
) -> dict[str, Malla]:
    with tempfile.TemporaryDirectory() as tmp:
        entrada, salida = Path(tmp) / "entrada.json", Path(tmp) / "mallas.json"
        entrada.write_text(json.dumps({
            "parts": {n: str(Path(p).resolve()) for n, p in parts.items()},
            "pins": {n: list(v) for n, v in pins.items()},
        }))
        script = Path(tmp) / "teselar.py"
        script.write_text(_TESELAR.format(
            entrada=str(entrada), salida=str(salida),
            tolerancia=tolerancia, prefijo=PREFIJO,
        ))
        proceso = subprocess.run(
            [freecadcmd, str(script)], capture_output=True, text=True, timeout=300
        )
        if PREFIJO not in proceso.stdout:
            raise RuntimeError(f"no se pudo teselar:\n{proceso.stderr[-600:]}")
        return {n: (v, t) for n, (v, t) in json.loads(salida.read_text()).items()}


def _colocar(vertices, pose: Placement):
    import numpy as np

    r = np.array(_rotacion(*pose.rotation))
    v = np.array(vertices, dtype=float)
    v[:, 2] *= pose.scale_z
    return v @ r.T + np.asarray(pose.origin)


def _subdividir(tris, max_lado: float):
    """Parte en 4 cada triángulo con algún lado mayor que `max_lado`."""
    import numpy as np

    while True:
        lados = np.linalg.norm(tris - np.roll(tris, 1, axis=1), axis=2).max(axis=1)
        grandes = lados > max_lado
        if not grandes.any():
            return tris
        a, b, c = (tris[grandes][:, i] for i in range(3))
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        nuevos = np.concatenate([
            np.stack(t, axis=1)
            for t in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))
        ])
        tris = np.concatenate([tris[~grandes], nuevos])


def render_gif(
    meshes: dict[str, Malla],
    frames,
    out: Path,
    *,
    fps: int = 12,
    title: str = "",
    colors: dict[str, str] | None = None,
    label=None,
    view: tuple[float, float] = (40, -65),
) -> Path:
    """`frames`: {t: poses} o lista de (t, poses), que admite repetir t
    (una bisagra que abre y vuelve a cerrar).
    `label(t)` pone el texto de cada fotograma (por defecto "θ = t°")."""
    frames = list(frames.items()) if isinstance(frames, dict) else list(frames)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import to_rgb
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from PIL import Image

    luz = np.array([0.3, -0.5, 0.8])
    luz /= np.linalg.norm(luz)

    todos = np.vstack([_colocar(meshes[n][0], p) for _, poses in frames for n, p in poses.items()])
    lo, hi = todos.min(axis=0), todos.max(axis=0)

    # Triángulos grandes (la cara de la base) rompen el orden por
    # profundidad de matplotlib, que usa el centro de cada triángulo:
    # se subdividen para que ninguno tape a una pieza que tiene encima.
    tris_locales = {n: _subdividir(np.asarray(v)[np.asarray(t)], 6.0)
                    for n, (v, t) in meshes.items()}
    paleta = {**COLORES, **(colors or {})}
    colores = {n: np.array(to_rgb(paleta.get(n, COLOR_EJE))) for n in meshes}
    label = label or (lambda t: f"θ = {t:g}°")

    imagenes = []
    for angulo, poses_frame in frames:
        todas, caras = [], []
        for nombre, pose in poses_frame.items():
            tris = _colocar(tris_locales[nombre].reshape(-1, 3), pose).reshape(-1, 3, 3)
            normales = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
            normales /= np.linalg.norm(normales, axis=1, keepdims=True) + 1e-12
            brillo = 0.45 + 0.55 * np.abs(normales @ luz)
            todas.append(tris)
            caras.append(np.clip(brillo[:, None] * colores[nombre], 0, 1))
        fig = plt.figure(figsize=(9, 5), dpi=110)
        ax = fig.add_subplot(projection="3d")
        # UNA colección: matplotlib solo ordena por profundidad dentro de
        # cada colección; con una por pieza, la base tapaba a todas.
        ax.add_collection3d(Poly3DCollection(
            np.concatenate(todas), facecolors=np.concatenate(caras), linewidths=0,
        ))
        for i, eje in enumerate("xyz"):
            getattr(ax, f"set_{eje}lim")(lo[i], hi[i])
        ax.set_box_aspect(tuple(np.maximum(hi - lo, 1)), zoom=1.0)
        ax.view_init(elev=view[0], azim=view[1])
        ax.set_axis_off()
        ax.set_title(f"{title}  {label(angulo)}".strip())
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        imagenes.append(Image.open(buf).convert("RGB"))

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    imagenes[0].save(
        out, save_all=True, append_images=imagenes[1:],
        duration=int(1000 / fps), loop=0,
    )
    return out
