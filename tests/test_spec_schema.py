"""Especificación de un proyecto.

Ver SISTEMA_MULTIAGENTE.md § 4.2 y DECISIONES.md ADR-010.
"""

import pytest
from pydantic import ValidationError

from orchestrator.schemas.spec import Spec


def test_spec_de_robot_exige_alcance_y_carga():
    """La clase no es una etiqueta: decide qué datos son obligatorios.

    Un `robot` pasa por Kinematics, y Kinematics no puede calcular nada
    sin alcance ni carga útil. Si el esquema los deja opcionales, el
    agente se los inventa en la Fase 2 (ADR-010).
    """
    with pytest.raises(ValidationError, match="robot"):
        Spec(
            title="brazo de 3 GDL",
            description="un brazo para mover piezas pequeñas",
            product_class="robot",
            printer="prusa_mk4_petg",
            material="PETG",
        )


def test_spec_de_mecanismo_exige_carga_pero_no_alcance():
    """Una garra no tiene alcance, pero sí tiene que levantar algo.

    Actuation necesita la carga para comprobar el margen de torque; el
    alcance solo tiene sentido en una cadena cinemática.
    """
    with pytest.raises(ValidationError, match="payload_g"):
        Spec(
            title="garra para lata",
            description="garra accionada por un MG996R",
            product_class="mechanism",
            printer="prusa_mk4_petg",
            material="PETG",
        )


def test_spec_de_pieza_estatica_no_exige_nada_de_eso():
    """El soporte de vaso del carruaje: sin alcance ni carga que valgan.

    Guard del caso que va a ser mayoría: si exigiéramos datos de robot a
    una pieza estática, el usuario tendría que inventárselos.
    """
    spec = Spec(
        title="soporte de vaso para carruaje",
        description="sujeta un vaso a un tubo de 68 mm",
        product_class="static_part",
        printer="prusa_mk4_petg",
        material="PETG",
    )

    assert spec.product_class == "static_part"
    assert spec.reach_mm is None
