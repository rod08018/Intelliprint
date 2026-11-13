"""Laminado con PrusaSlicer (F1.12 (laminado) + F1.13 (slicing)).

Ver PLAN_PROYECTO.md: el perfil de laminado es distinto del de holguras,
y sin densidad de filamento PrusaSlicer reporta 0 g (lo vimos con el cubo).
"""

import shutil
import struct
from pathlib import Path

import pytest

from orchestrator.slicing import (
    parse_tiempo,
    prusaslicer,
    slice_stl,
)

PERFIL_M5 = Path("config/slicing/ankermake_m5_petg.ini")
"""El de PETG: sigue en el catálogo como alternativa al perfil activo."""


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


# --- «pide soportes» lo dice PrusaSlicer, y la postura se elige al laminar (2026-11-13) ----

AVISO = """65 => Searching support spots
69 => Alert if supports needed
print warning: Detected print stability issues:

muneca.stl
Floating bridge anchors, Loose extrusions, Long bridging extrusions

Consider enabling supports.
88 => Estimating curled extrusions
"""
"""Lo que escribió PrusaSlicer al laminar tumbada la muñeca del brazo mediano
(banco 1113-1330), tal cual salió."""


def test_el_aviso_de_prusaslicer_es_lo_que_dice_si_pide_soportes():
    """Hasta el 2026-11-13 «pide soportes» era el ajuste `support_material`
    del perfil, que vale 0: toda pieza que se laminaba salía «sin soportes»,
    en todos los encargos del banco. PrusaSlicer sí lo dice, en lo que
    escribe al laminar, y nadie lo leía."""
    from orchestrator.slicing import avisos_de_soportes
    assert avisos_de_soportes(AVISO, "muneca.stl") == [
        "Floating bridge anchors", "Loose extrusions", "Long bridging extrusions"]
    sin_aviso = "65 => Searching support spots\n69 => Alert if supports needed\n"
    assert avisos_de_soportes(sin_aviso, "muneca.stl") == []
    # Que le falte agarre a la cama no es pedir soportes: se arregla con un borde.
    con_borde = AVISO.replace("Consider enabling supports.", "Consider enabling brim.")
    assert avisos_de_soportes(con_borde, "muneca.stl") == []


def _mesa_stl(ruta: Path) -> None:
    """Una mesa de una pata: un tablero de 40 × 40 × 2 a 20 mm de alto sobre
    un poste de 6 × 6. De pie, el tablero vuela 17 mm por cada lado; boca
    abajo, apoyada en el tablero, no vuela nada."""
    from tests.test_tornilleria import _caja_stl
    ruta.write_text("solid mesa\n" + _caja_stl((17, 17, 0), (23, 23, 20))
                    + _caja_stl((0, 0, 20), (40, 40, 22)) + "endsolid mesa\n", encoding="utf-8")


@pytest.mark.skipif(prusaslicer() is None, reason="PrusaSlicer no disponible")
def test_una_mesa_de_pie_pide_soportes_y_boca_abajo_no(tmp_path):
    stl = tmp_path / "mesa.stl"
    _mesa_stl(stl)
    perfil = Path("config/slicing/m5_esun_plamas_precision.ini")

    de_pie = slice_stl(stl, perfil, tmp_path / "mesa.gcode")
    assert de_pie.needs_supports and de_pie.avisos and de_pie.postura == "-z"

    boca_abajo = slice_stl(stl, perfil, tmp_path / "mesa.gcode", postura="+z")
    assert not boca_abajo.needs_supports and boca_abajo.postura == "+z"
    assert boca_abajo.avisos == []


@pytest.mark.skipif(prusaslicer() is None, reason="PrusaSlicer no disponible")
def test_la_postura_dice_que_cara_va_a_la_cama(tmp_path):
    """Un poste de 6 × 6 que sale en +x de un tablero de 40 × 40 puesto en
    x = 0. Apoyada en su cara -x (el tablero) no vuela nada; en la +x se
    apoya en la punta del poste y el tablero queda en el aire."""
    from tests.test_tornilleria import _caja_stl
    stl = tmp_path / "seta.stl"
    stl.write_text("solid seta\n" + _caja_stl((0, 0, 0), (2, 40, 40))
                   + _caja_stl((2, 17, 17), (22, 23, 23)) + "endsolid seta\n", encoding="utf-8")
    perfil = Path("config/slicing/m5_esun_plamas_precision.ini")
    assert not slice_stl(stl, perfil, tmp_path / "s.gcode", postura="-x").needs_supports
    assert slice_stl(stl, perfil, tmp_path / "s.gcode", postura="+x").needs_supports
