"""Laminado con PrusaSlicer (F1.12 (laminado) + F1.13 (slicing)).

Ver PLAN_PROYECTO.md: el perfil de laminado es distinto del de holguras,
y sin densidad de filamento PrusaSlicer reporta 0 g (lo vimos con el cubo).
"""

import shutil
import struct
from pathlib import Path

import pytest

from orchestrator.slicing import (
    PERFIL_M5,
    parse_tiempo,
    prusaslicer,
    slice_stl,
)


def test_parsea_los_formatos_de_tiempo_de_prusaslicer():
    assert parse_tiempo("13m 54s") == 834
    assert parse_tiempo("1h 2m 3s") == 3723
    assert parse_tiempo("1d 0h 0m 1s") == 86401
    assert parse_tiempo("45s") == 45


def _cubo_stl(ruta: Path, lado: float = 20.0) -> None:
    v = [(0, 0, 0), (lado, 0, 0), (lado, lado, 0), (0, lado, 0),
         (0, 0, lado), (lado, 0, lado), (lado, lado, lado), (0, lado, lado)]
    caras = [(0, 3, 2), (0, 2, 1), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    with ruta.open("wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(caras)))
        for a, b, c in caras:
            f.write(struct.pack("<3f", 0, 0, 0))
            for i in (a, b, c):
                f.write(struct.pack("<3f", *v[i]))
            f.write(struct.pack("<H", 0))


@pytest.mark.skipif(prusaslicer() is None, reason="PrusaSlicer no disponible")
def test_el_perfil_de_la_m5_da_gramos_reales(tmp_path):
    """Criterio de F1.12 (laminado). Sin densidad en el perfil saldría 0 g, y
    SlicingReport lo rechazaría (es la trampa que vimos con el cubo).

    Un cubo de 20 mm son 8 cm³; con relleno parcial el peso real tiene
    que quedar por debajo de 8 cm³ × 1.27 g/cm³ de PETG macizo.
    """
    stl = tmp_path / "cubo.stl"
    _cubo_stl(stl)

    informe = slice_stl(stl, PERFIL_M5, tmp_path / "cubo.gcode")

    assert 0 < informe.grams < 8 * 1.27
    assert informe.filament_mm > 0
    assert informe.time_s > 0
    assert (tmp_path / "cubo.gcode").exists()


@pytest.mark.skipif(prusaslicer() is None, reason="PrusaSlicer no disponible")
def test_el_gcode_sale_para_la_cama_de_la_m5(tmp_path):
    """Si el perfil no se aplicara, PrusaSlicer usaría su máquina por
    defecto y el G-code no sería para la M5."""
    stl = tmp_path / "cubo.stl"
    _cubo_stl(stl)

    slice_stl(stl, PERFIL_M5, tmp_path / "cubo.gcode")

    gcode = (tmp_path / "cubo.gcode").read_text(errors="ignore")
    assert "bed_shape = 0x0,235x0,235x235,0x235" in gcode
    assert "filament_density = 1.27" in gcode
