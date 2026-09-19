"""Instantánea del G-code de inicio de la AnkerMake M5 (F1.17 (verificación)).

Es lo primero que ejecuta la impresora. Si cambia —por editar el perfil,
actualizar PrusaSlicer o regenerar el .ini—, este test falla y obliga a
mirarlo. La instantánea dice si está verificada en la impresora real.
"""

from pathlib import Path

import pytest

from orchestrator.slicing import PERFIL_M5, prusaslicer, slice_stl
from tests.test_slicing import _cubo_stl

INSTANTANEA = Path("tests/snapshots/m5_start_gcode.txt")
LINEAS = 12


def _inicio(gcode: Path) -> list[str]:
    ordenes = [l.rstrip() for l in gcode.read_text(errors="ignore").splitlines()
               if l.strip() and not l.startswith(";")]
    return ordenes[:LINEAS]


@pytest.mark.skipif(prusaslicer() is None, reason="PrusaSlicer no disponible")
def test_el_gcode_de_inicio_no_cambia_sin_que_nadie_lo_mire(tmp_path):
    stl = tmp_path / "cubo.stl"
    _cubo_stl(stl)
    slice_stl(stl, PERFIL_M5, tmp_path / "cubo.gcode")

    esperado = [l for l in INSTANTANEA.read_text().splitlines() if not l.startswith("#")]

    assert _inicio(tmp_path / "cubo.gcode") == esperado
