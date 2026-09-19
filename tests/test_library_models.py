"""Modelos de hardware comercial de la librería (F2.3).

Los escribe un humano con las cotas de la hoja del fabricante: ningún
modelo debe inventar las medidas de un NEMA17 (§ 10).
"""

import pytest

from mech_toolkit.library_models import build_nema17
from orchestrator.fcstd import mostrar_solo  # noqa: F401  (usado por build_nema17)
from tests.test_fcstd_output import _visibilidad_gui
from tests.test_generators import _freecadcmd


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_nema17_tiene_las_cotas_de_la_hoja(tmp_path):
    """Cuerpo 42.3 x 42.3 x 40, más 24 mm de eje: 64 mm de alto total."""
    resultado = build_nema17(tmp_path, _freecadcmd())

    assert resultado.bbox_mm == pytest.approx([42.3, 42.3, 64.0])
    assert resultado.solids == 1


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_nema17_esta_en_posicion_de_montaje(tmp_path):
    """Cara del motor en z=0 y cuerpo hacia abajo: en las mismas coordenadas
    que el soporte (placa de z=0 hacia arriba, centrada en el origen). Al
    insertar los dos en un ensamblaje quedan montados sin uniones."""
    resultado = build_nema17(tmp_path, _freecadcmd())

    assert resultado.zmin == pytest.approx(-40.0)
    assert resultado.zmax == pytest.approx(24.0)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_fcstd_del_motor_se_ve_al_abrirlo(tmp_path):
    build_nema17(tmp_path, _freecadcmd())

    gui = _visibilidad_gui(tmp_path / "nema17_42x40.FCStd")

    assert list(gui.values()) == [True]
    assert (tmp_path / "nema17_42x40.step").exists()
