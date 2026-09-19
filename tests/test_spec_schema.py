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
            printer="ankermake_m5_petg",
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
            printer="ankermake_m5_petg",
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
        printer="ankermake_m5_petg",
        material="PETG",
    )

    assert spec.product_class == "static_part"
    assert spec.reach_mm is None


# --- Procedencia de los datos (F1.2) ----------------------------------------


def _mecanismo(**extra) -> Spec:
    return Spec(
        title="bisagra del gallinero",
        description="bisagra motorizada para la puerta",
        product_class="mechanism",
        printer="ankermake_m5_petg",
        material="PETG",
        payload_g=1500,
        **extra,
    )


def test_la_spec_distingue_lo_que_dijo_el_usuario_de_lo_que_estimo_el_modelo():
    """El payload_g=1500 de la bisagra se lo inventó el modelo. Sin marca,
    es indistinguible de un dato del usuario."""
    spec = _mecanismo(estimated=["payload_g"])

    assert "payload_g" in spec.estimated


def test_no_se_puede_marcar_como_estimado_un_campo_que_no_existe():
    with pytest.raises(ValidationError, match="peso_kg"):
        _mecanismo(estimated=["peso_kg"])


def test_los_estimados_criticos_son_los_que_la_clase_exige():
    """Lo que la admisión debe preguntar: un dato inventado del que depende
    una fase posterior. Una bisagra dimensionada para 1.5 kg con una puerta
    de 4 kg da un servo que no puede con ella."""
    spec = _mecanismo(estimated=["payload_g", "material"])

    assert spec.estimated_critical == ["payload_g"]


def test_una_pieza_estatica_con_material_supuesto_no_tiene_criticos():
    """Suponer PETG no rompe nada que dependa de ello: no hay que preguntar."""
    spec = Spec(
        title="soporte",
        description="soporte de vaso",
        product_class="static_part",
        printer="ankermake_m5_petg",
        material="PETG",
        estimated=["material"],
    )

    assert spec.estimated_critical == []
