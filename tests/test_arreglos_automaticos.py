"""Los arreglos exactos los aplica el código, no el modelo (F3.15 (mecanismos)).

El validador ya calculaba «súbelas 0.10 mm» y aun así devolvía el problema
al modelo, que gastaba un intento —o una ronda entera— en sumar 0.10 a una
coordenada. Tumbó la ronda 1 del segundo trinquete del 2026-09-20 y las
rondas 7 y 10 del cuarto. Si el arreglo es exacto y no depende de ninguna
decisión de diseño, lo hace el código y lo deja anotado.
"""

import json

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.agents.mechanism_designer import MechanismDesignerAgent
from orchestrator.mechanisms.checks import _apoyadas_a_cero, levantar_apoyadas
from orchestrator.schemas.mechanism import MechanismSpec
from tests.test_mechanism_flow import PERFIL, Guion, _spec


def test_una_pieza_apoyada_a_cero_se_levanta_justo_la_holgura():
    spec = MechanismSpec(**_spec(0.0))          # brazo en z = 0, base hasta z = 0
    notas = levantar_apoyadas(spec, 0.1)

    brazo = next(p for p in spec.parts if p.name == "brazo")
    assert brazo.origin[2] == pytest.approx(0.1, abs=0.002)
    assert _apoyadas_a_cero(spec, 0.1) == []
    assert notas and "«brazo»" in notas[0] and "0.10" in notas[0]


def test_una_pieza_con_holgura_no_se_toca():
    spec = MechanismSpec(**_spec(0.5))
    assert levantar_apoyadas(spec, 0.1) == []
    assert next(p for p in spec.parts if p.name == "brazo").origin[2] == 0.5


def test_el_agente_entrega_la_especificacion_ya_arreglada_en_un_solo_intento():
    """Sin el arreglo automático, esta respuesta se rechazaba y el modelo
    tenía que volver a escribirla entera para sumar 0.1."""
    modelo = Guion([json.dumps(_spec(0.0))])
    agente = MechanismDesignerAgent(modelo, CATALOGO, PERFIL, (235, 235, 250), 0.1)

    spec = agente.design("un brazo")

    assert len(modelo.prompts) == 1
    assert next(p for p in spec.parts if p.name == "brazo").origin[2] == pytest.approx(0.1, abs=0.002)
    assert any("brazo" in n for n in agente.ajustes)
