"""Verificación en la interfaz real de FreeCAD (F1.17 (verificación), marcador `gui`).

El bug del .FCStd "vacío" pasó los tests porque estos leían el zip, no lo
que ve el usuario. Este test abre el archivo en la interfaz gráfica y
pregunta a FreeCAD qué está visible. Abre una ventana unos segundos.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.test_measure_extract import _nema17

FREECAD_GUI = os.environ.get(
    "FREECAD_GUI", "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"
)


def visibilidad_en_la_interfaz(fcstd: Path, carpeta: Path) -> dict[str, bool]:
    salida = carpeta / "visibilidad.json"
    macro = carpeta / "abrir.py"
    macro.write_text(
        "import json, os, FreeCAD, FreeCADGui\n"
        f"doc = FreeCAD.openDocument({str(fcstd)!r})\n"
        "g = FreeCADGui.getDocument(doc.Name)\n"
        "res = {o.Label: g.getObject(o.Name).Visibility for o in doc.Objects}\n"
        f"open({str(salida)!r}, 'w').write(json.dumps(res))\n"
        "os._exit(0)\n"
    )
    proceso = subprocess.Popen([FREECAD_GUI, str(macro)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            if salida.exists():
                return json.loads(salida.read_text())
            time.sleep(1)
        raise TimeoutError("FreeCAD no respondió en 120 s")
    finally:
        proceso.kill()


@pytest.mark.gui
@pytest.mark.skipif(not Path(FREECAD_GUI).exists(), reason="FreeCAD con interfaz no disponible")
def test_la_pieza_se_ve_al_abrirla_en_freecad(tmp_path):
    _nema17(tmp_path)

    vis = visibilidad_en_la_interfaz(tmp_path / "pieza.FCStd", tmp_path)

    assert vis["pieza"] is True
    assert [nombre for nombre, v in vis.items() if v] == ["pieza"]


@pytest.mark.gui
@pytest.mark.skipif(not Path(FREECAD_GUI).exists(), reason="FreeCAD con interfaz no disponible")
def test_el_ensamble_del_mecanismo_se_ve_completo_en_freecad(tmp_path):
    """El ensamble es lo que el usuario abre para verificar el mecanismo:
    todas las piezas y ejes tienen que verse, no solo existir en el zip."""
    from mech_toolkit.generators import CATALOGO
    from mech_toolkit.profile import PrinterProfile
    from orchestrator.assembly import build_assembly
    from orchestrator.build import build_part
    from orchestrator.mechanisms.slider_crank import SliderCrankLayout
    from tests.test_generators import _freecadcmd

    lay = SliderCrankLayout(stroke_mm=60, profile=PrinterProfile(
        id="m5", fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35}))
    steps = {}
    for nombre, receta in lay.recipes().items():
        build_part(receta, CATALOGO, tmp_path / nombre, _freecadcmd())
        steps[nombre] = tmp_path / nombre / f"{nombre}.step"
    build_assembly(steps, lay.pins(), lay.poses(30), tmp_path / "assembly.FCStd", _freecadcmd())

    vis = visibilidad_en_la_interfaz(tmp_path / "assembly.FCStd", tmp_path)

    assert set(vis) == set(steps) | set(lay.pins())
    assert all(vis.values())
