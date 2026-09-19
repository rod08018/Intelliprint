"""Contrato de interfaces entre piezas.

Ver SISTEMA_MULTIAGENTE.md § 3 y DECISIONES.md ADR-001.
"""

import pytest
from pydantic import ValidationError

from orchestrator.schemas.interface import Interface


def test_interfaz_simbolica_rechaza_geometria():
    """Decomposition corre antes que Kinematics: no puede conocer el frame.

    Si el esquema permitiera esto, el modelo inventaría cotas y el gate #1
    aprobaría números que la Fase 2 cambiaría después.
    """
    with pytest.raises(ValidationError, match="simbólica"):
        Interface(
            id="IF-003",
            state="symbolic",
            type="bearing_seat",
            between=["base_giratoria", "hombro"],
            hardware_class="bearing",
            fit="press",
            frame={"origin": [0, 0, 45], "axis": [0, 0, 1]},
        )


def test_interfaz_resuelta_exige_geometria_y_hardware_concreto():
    """El contrario: una interfaz resuelta sin cotas no sirve para diseñar.

    Si esto pasara la validación, un Part Designer recibiría una interfaz
    sin frame y tendría que inventarse dónde poner la feature.
    """
    with pytest.raises(ValidationError, match="resuelta"):
        Interface(
            id="IF-003",
            state="resolved",
            type="bearing_seat",
            between=["base_giratoria", "hombro"],
            fit="press",
        )
