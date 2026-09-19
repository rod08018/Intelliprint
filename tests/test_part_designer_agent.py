"""Part Designer Agent (F1.10 (designer)): tarea → receta.

Ver DECISIONES.md ADR-002. No escribe Python: elige generadores.
"""

import json

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.agents.part_designer import PartDesignerAgent
from orchestrator.llm.structured import SalidaInvalida


class ClienteGuionizado:
    def __init__(self, respuestas: list[str]) -> None:
        self._respuestas = list(respuestas)
        self.prompts: list[str] = []

    def complete(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        return self._respuestas.pop(0)


_RECETA_OK = json.dumps(
    {
        "part": "soporte_nema17",
        "steps": [
            {
                "generator": "generate_plate",
                "params": {"length_mm": 60, "width_mm": 60, "thickness_mm": 6},
            }
        ],
    }
)


def test_el_prompt_describe_el_catalogo_y_no_una_lista_escrita_a_mano():
    """Si la lista de generadores se escribiera en el .md, se desincronizaría
    en cuanto alguien añadiera uno. Se deriva del catálogo."""
    cliente = ClienteGuionizado([_RECETA_OK])

    PartDesignerAgent(cliente, CATALOGO).design("placa de 60x60x6")

    prompt = cliente.prompts[0]
    for spec in ["generate_plate", "generate_center_bore", "generate_square_bolt_pattern"]:
        assert spec in prompt
    assert "thickness_mm" in prompt  # parámetros obligatorios, también del catálogo


def test_un_generador_inventado_se_reintenta_con_el_error():
    """El esquema no puede saber qué generadores existen; el catálogo sí.

    Sin esto, una receta con `generate_unicornio` sería válida como JSON
    y reventaría después, fuera del bucle de reintento.
    """
    inventado = json.dumps(
        {
            "part": "soporte_nema17",
            "steps": [{"generator": "generate_unicornio", "params": {}}],
        }
    )
    cliente = ClienteGuionizado([inventado, _RECETA_OK])

    receta = PartDesignerAgent(cliente, CATALOGO).design("una placa")

    assert receta.steps[0].generator == "generate_plate"
    assert "generate_unicornio" in cliente.prompts[1]


def test_si_insiste_en_inventar_se_agotan_los_intentos():
    inventado = json.dumps(
        {"part": "x", "steps": [{"generator": "generate_unicornio", "params": {}}]}
    )
    cliente = ClienteGuionizado([inventado] * 3)

    with pytest.raises(SalidaInvalida, match="generate_unicornio"):
        PartDesignerAgent(cliente, CATALOGO).design("una placa")
