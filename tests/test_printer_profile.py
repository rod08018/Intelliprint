"""El perfil de impresora que se versiona en el repo debe cargar de verdad.

Guard contra la deriva entre `config/printers/*.yaml` y el código que lo
consume: es el tipo de fallo que no aparece hasta que laminas.
"""

from pathlib import Path

import pytest
import yaml

from mech_toolkit.profile import PrinterProfile

PERFIL_YAML = Path("config/printers/ankermake_m5_petg.yaml")


def _cargar() -> PrinterProfile:
    return PrinterProfile(**yaml.safe_load(PERFIL_YAML.read_text(encoding="utf-8")))


def test_el_perfil_del_repo_carga_y_tiene_lo_que_el_qa_necesita():
    perfil = _cargar()

    assert perfil.fit_mm("press") == pytest.approx(0.10)
    assert perfil.fit_mm("clearance") == pytest.approx(0.35)
    assert perfil.hole_mm("M3_through") == pytest.approx(3.3)


def test_el_perfil_del_repo_declara_que_no_esta_calibrado():
    """Los valores son defaults de boquilla 0.4, no mediciones reales.

    Mientras `calibrated` sea False, las piezas salen dimensionalmente
    correctas pero encajan mal. Que esté en el archivo evita la sorpresa.
    """
    assert _cargar().calibrated is False
