"""Requirements Agent: texto libre → Spec clasificada (F1.3).

Ver SISTEMA_MULTIAGENTE.md § 4.1 y § 4.2.
"""

import json

from orchestrator.agents.requirements import RequirementsAgent


class ClienteGuionizado:
    def __init__(self, respuestas: list[str]) -> None:
        self._respuestas = list(respuestas)
        self.prompts: list[str] = []

    def complete(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        return self._respuestas.pop(0)


_SOPORTE = json.dumps(
    {
        "title": "soporte de vaso para carruaje",
        "description": "sujeta un vaso a un tubo de 68 mm",
        "product_class": "static_part",
        "printer": "ankermake_m5_petg",
        "material": "PETG",
        "payload_g": None,
        "reach_mm": None,
    }
)


def test_convierte_texto_libre_en_una_spec_clasificada():
    cliente = ClienteGuionizado([_SOPORTE])

    spec = RequirementsAgent(cliente).draft(
        "algo que sujete un vaso en el carruaje de mi hijo, tubo de 68 mm"
    )

    assert spec.product_class == "static_part"
    assert spec.material == "PETG"


def test_el_prompt_incluye_las_instrucciones_del_agente_y_la_peticion():
    """El prompt vive en config/agents/, no incrustado en el código:
    afinarlo es la tarea F6.3 y no debería requerir tocar Python."""
    cliente = ClienteGuionizado([_SOPORTE])

    RequirementsAgent(cliente).draft("sujeta un vaso")

    prompt = cliente.prompts[0]
    assert "Requirements Agent" in prompt  # viene del .md
    assert "static_part" in prompt
    assert "sujeta un vaso" in prompt  # la petición


def test_un_robot_sin_alcance_se_corrige_solo_en_el_reintento():
    """La coherencia entre clase y datos no depende del prompt.

    Guard de integración entre ADR-010 y F1.2: si el modelo dice `robot`
    y olvida el alcance, lo rechaza el ESQUEMA y el error exacto vuelve
    al modelo. Aunque el prompt estuviera mal escrito, o el modelo lo
    ignorase, no puede colarse una spec de robot sin alcance.
    """
    incompleta = json.dumps(
        {
            "title": "brazo de 3 GDL",
            "description": "brazo para mover piezas pequeñas",
            "product_class": "robot",
            "printer": "ankermake_m5_petg",
            "material": "PETG",
        }
    )
    completa = json.dumps(
        {
            "title": "brazo de 3 GDL",
            "description": "brazo para mover piezas pequeñas",
            "product_class": "robot",
            "printer": "ankermake_m5_petg",
            "material": "PETG",
            "payload_g": 500,
            "reach_mm": 400,
        }
    )
    cliente = ClienteGuionizado([incompleta, completa])

    spec = RequirementsAgent(cliente).draft("un brazo de 3 ejes, alcance 40 cm")

    assert spec.reach_mm == 400
    assert "reach_mm" in cliente.prompts[1]  # el error le dijo qué faltaba
