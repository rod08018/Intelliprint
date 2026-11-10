"""El dibujo de las animaciones (F7.6 (animacion)), sin FreeCAD: una malla
hecha a mano basta para ver cómo sale cada cuadro."""

import pytest

from mech_toolkit.geometry import Placement

CUBO = ([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
         [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10]],
        [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
         [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
QUIETO = {"cubo": Placement(origin=[0, 0, 0], rotation=[0, 0, 0])}


def test_un_cuadro_no_arrastra_restos_del_anterior(tmp_path):
    """El pan-tilt (2026-11-10) decía «20°°»: cada cuadro salía de un tamaño
    —el rótulo cambia de largo— y en el GIF quedaban trozos del anterior.
    Un cuadro tiene que verse igual que dibujado solo."""
    pytest.importorskip("matplotlib")
    from PIL import Image, ImageChops

    from orchestrator.animation import render_gif

    rotulos = {0: "un rótulo bastante más largo que el siguiente -90°", 1: "0°"}
    seguidos = render_gif({"cubo": CUBO}, [(0, QUIETO), (1, QUIETO)], tmp_path / "dos.gif",
                          label=rotulos.get)
    solo = render_gif({"cubo": CUBO}, [(1, QUIETO)], tmp_path / "uno.gif", label=rotulos.get)
    with Image.open(seguidos) as a, Image.open(solo) as b:
        a.seek(1)
        segundo, aparte = a.convert("RGB"), b.convert("RGB")
    assert segundo.size == aparte.size
    assert ImageChops.difference(segundo, aparte).getbbox() is None


def test_lo_que_choca_se_pinta_de_rojo_solo_en_su_cuadro(tmp_path):
    pytest.importorskip("matplotlib")
    from PIL import Image

    from orchestrator.animation import render_gif

    gif = render_gif({"cubo": CUBO}, [(0, QUIETO), (1, QUIETO)], tmp_path / "rojo.gif",
                     resaltar=lambda t: {"cubo"} if t == 1 else set())

    def rojos(imagen):
        return sum(1 for r, g, b in imagen.convert("RGB").getdata()
                   if r > 100 and g < 0.35 * r and b < 0.35 * r)

    with Image.open(gif) as img:
        assert rojos(img) == 0
        img.seek(1)
        assert rojos(img) > 100
