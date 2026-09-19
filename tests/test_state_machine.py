"""Máquina de estados del proyecto.

Ver SISTEMA_MULTIAGENTE.md § 4 y DECISIONES.md ADR-008.
"""

import io

import pytest

from orchestrator.human.adapters.cli import CliAdapter
from orchestrator.state_machine import (
    AprobacionRequerida,
    TransicionProhibida,
    advance,
    transition,
)


def test_no_existe_camino_de_intake_al_diseno():
    """La barrera de admisión es estructural, no una convención de prompt.

    Si esto dependiera de que el Requirements Agent se acuerde de
    preguntar, fallaría el día que el modelo tenga prisa. Como arista
    inexistente del grafo, es imposible saltárselo (ADR-008).
    """
    with pytest.raises(TransicionProhibida, match="INTAKE"):
        transition("INTAKE", "DECOMPOSED")


def test_salir_de_intake_exige_confirmacion_explicita():
    """La única salida de INTAKE existe, pero está cerrada con llave.

    "que me pregunte cosas antes de que el sistema inicie a diseñar":
    sin confirmación no se sale de la admisión.
    """
    with pytest.raises(AprobacionRequerida, match="INTAKE"):
        transition("INTAKE", "SPEC_READY")

    assert transition("INTAKE", "SPEC_READY", approved=True) == "SPEC_READY"


def test_los_dos_gates_usan_el_mismo_mecanismo_que_la_admision():
    """Un solo mecanismo para tres barreras: admisión, gate 1 y gate 2."""
    for desde, hacia in [
        ("INTERFACES_RESOLVED", "PARTS_IN_PROGRESS"),  # gate 1
        ("SLICED", "RELEASED"),  # gate 2
    ]:
        with pytest.raises(AprobacionRequerida):
            transition(desde, hacia)
        assert transition(desde, hacia, approved=True) == hacia


def test_las_transiciones_normales_no_piden_aprobacion():
    """Guard: si todo exigiera aprobación, los tests anteriores pasarían igual."""
    assert transition("SPEC_READY", "DECOMPOSED") == "DECOMPOSED"
    assert transition("PARTS_IN_PROGRESS", "ASSEMBLED") == "ASSEMBLED"


def _cli(respuesta: str) -> CliAdapter:
    return CliAdapter(entrada=io.StringIO(respuesta), salida=io.StringIO())


def test_la_admision_no_avanza_si_contestas_que_no():
    """Criterio de F1.5 (INTAKE), con la barrera conectada al canal humano real."""
    with pytest.raises(AprobacionRequerida):
        advance("INTAKE", "SPEC_READY", port=_cli("todavía no\n"))


def test_la_admision_avanza_cuando_confirmas():
    assert advance("INTAKE", "SPEC_READY", port=_cli("sí\n")) == "SPEC_READY"


def test_una_transicion_normal_no_llega_a_preguntar():
    """El canal no se usa donde no hay barrera: nada que leer de la entrada."""
    entrada_vacia = CliAdapter(entrada=io.StringIO(""), salida=io.StringIO())

    assert advance("SPEC_READY", "DECOMPOSED", port=entrada_vacia) == "DECOMPOSED"
