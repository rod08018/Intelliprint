"""Encaje físico con holgura mínima (F2.20).

"Intersección = 0" contaba TOCARSE como ENCAJAR: el soporte de Ø22 contra
el saliente de Ø22 del motor pasaba, y en FDM ese motor no entra. Encajar
es tener una holgura >= la mínima del perfil de la impresora.

La referencia es el NEMA17 de obijuan (library/models/reference): un
oráculo independiente, no dibujado por el sistema.
"""

from pathlib import Path

import pytest

from mech_toolkit.fit import check_fit
from mech_toolkit.geometry import Cylinder, Frame
from mech_toolkit.measure import extract_cylinders
from mech_toolkit.profile import PrinterProfile
from tests.test_generators import _freecadcmd
from tests.test_measure_extract import _nema17

PERFIL = PrinterProfile(
    id="ankermake_m5_petg",
    fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35},
)
MOTOR = Path("library/models/reference/nema17_40mm_obijuan.step")
TALADRO = Frame(origin=[0, 0, 0], axis=[0, 0, 1])       # en el soporte
CARA_MOTOR = Frame(origin=[0, 0, 40.1], axis=[0, 0, 1])  # medida en el motor


def _encaje(tmp_path, taladro):
    soporte = extract_cylinders(_nema17(tmp_path, taladro=taladro), _freecadcmd())
    motor = extract_cylinders(MOTOR, _freecadcmd())
    return check_fit(soporte, TALADRO, motor, CARA_MOTOR, PERFIL)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_soporte_de_22_no_encaja_con_el_motor_real(tmp_path):
    """El caso de hoy: tocarse no es encajar."""
    resultado = _encaje(tmp_path, taladro=22.0)

    assert resultado.ok is False
    assert resultado.clearance_mm == pytest.approx(0.0, abs=1e-6)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_con_22_4_hay_holgura_suficiente(tmp_path):
    """0.2 mm de holgura radial frente a los 0.175 que pide el perfil."""
    resultado = _encaje(tmp_path, taladro=22.4)

    assert resultado.ok is True
    assert resultado.clearance_mm == pytest.approx(0.2)


def test_sin_agujero_donde_dice_el_contrato_no_encaja():
    saliente = Cylinder(radius=11, axis=[0, 0, 1], point=[0, 0, 0.8],
                        length=1.6, internal=False)

    resultado = check_fit([], TALADRO, [saliente], Frame(origin=[0, 0, 0], axis=[0, 0, 1]), PERFIL)

    assert resultado.ok is False
    assert "agujero" in resultado.motivo


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_motivo_dice_que_cambiar_no_solo_que_falla(tmp_path):
    """El motivo vuelve al Part Designer como defecto (F3.12, reapertura).
    "No encaja" no se puede corregir; "el taladro tiene que ser >= Ø22.35"
    sí: saliente de Ø22 + 2 x 0.175 de holgura radial."""
    resultado = _encaje(tmp_path, taladro=22.0)

    assert resultado.min_bore_mm == pytest.approx(22.35)
    assert "22.35" in resultado.motivo
