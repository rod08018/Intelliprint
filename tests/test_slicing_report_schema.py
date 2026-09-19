"""Reporte de laminado.

Ver SISTEMA_MULTIAGENTE.md § 2 (agente 11) y config/printers/*.yaml.
"""

import pytest
from pydantic import ValidationError

from orchestrator.schemas.slicing_report import SlicingReport


def test_cero_gramos_con_filamento_gastado_se_rechaza():
    """Trampa real, observada laminando un cubo con PrusaSlicer 2.9.6.

    Sin un perfil de filamento con densidad, PrusaSlicer reporta
    `total filament used [g] = 0.00` pero sí da longitud y tiempo. Si lo
    aceptáramos, el coste, la métrica de gramos y el Gate #2 saldrían a
    cero sin que nada avisara.
    """
    with pytest.raises(ValidationError, match="densidad"):
        SlicingReport(
            plate=1,
            filament_mm=2450.0,
            grams=0.0,
            time_s=834,
            needs_supports=False,
        )
