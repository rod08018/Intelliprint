"""Instantánea del G-code de inicio de la AnkerMake M5 (F1.17 (verificación)).

Es lo primero que ejecuta la impresora. Si cambia —por editar el perfil,
actualizar PrusaSlicer o regenerar el .ini—, este test falla y obliga a
mirarlo. La instantánea dice si está verificada en la impresora real.
"""

from pathlib import Path

import pytest

from orchestrator.slicing import prusaslicer, slice_stl
from tests.test_slicing import PERFIL_M5, _cubo_stl

PERFILES = [
    (PERFIL_M5, Path("tests/snapshots/m5_start_gcode.txt")),
    (Path("config/slicing/m5_esun_plamas_precision.ini"),
     Path("tests/snapshots/m5_esun_plamas_start_gcode.txt")),
]
LINEAS = 12


def _inicio(gcode: Path) -> list[str]:
    ordenes = [l.rstrip() for l in gcode.read_text(errors="ignore").splitlines()
               # M73 es el aviso de tiempo restante: cambia con la estimación,
               # no con lo que hace la máquina.
               if l.strip() and not l.startswith(";") and not l.startswith("M73 ")]
    return ordenes[:LINEAS]


@pytest.mark.skipif(prusaslicer() is None, reason="PrusaSlicer no disponible")
@pytest.mark.parametrize("perfil, instantanea", PERFILES, ids=lambda x: Path(x).stem)
def test_el_gcode_de_inicio_no_cambia_sin_que_nadie_lo_mire(tmp_path, perfil, instantanea):
    stl = tmp_path / "cubo.stl"
    _cubo_stl(stl)
    slice_stl(stl, perfil, tmp_path / "cubo.gcode")

    esperado = [l for l in instantanea.read_text(encoding="utf-8").splitlines()
                if not l.startswith("#")]

    assert _inicio(tmp_path / "cubo.gcode") == esperado
