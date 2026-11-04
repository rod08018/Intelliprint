"""El diseñador que escribe programas del kit (F5.18 (kit))."""

import json
from pathlib import Path

from orchestrator.agents.disenador_kit import DisenadorKitAgent
from orchestrator.impresion import perfil_activo
from orchestrator.schemas.programa import Programa

ACTIVO = perfil_activo(Path("."))
BUENO = "def construir(kit):\n    return kit.caja(20, 10, 5)\n"


class Guion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.prompts = []

    def complete(self, prompt, **_):
        self.prompts.append(prompt)
        return self._respuestas.pop(0)


def test_devuelve_un_programa_que_pasa_la_lista_blanca():
    p = DisenadorKitAgent(Guion([json.dumps({"part": "x", "codigo": BUENO})]), ACTIVO).design("t")
    assert isinstance(p, Programa) and "kit.caja" in p.codigo


def test_un_programa_prohibido_vuelve_con_la_linea_y_el_motivo():
    malo = json.dumps({"part": "x", "codigo": "def construir(kit):\n    return open('x')"})
    guion = Guion([malo, json.dumps({"part": "x", "codigo": BUENO})])
    DisenadorKitAgent(guion, ACTIVO).design("t")
    assert "línea 2" in guion.prompts[1] and "open" in guion.prompts[1]


def test_el_prompt_lleva_la_api_del_kit_y_la_tornilleria_del_perfil():
    """La API sale de las firmas del kit: un método nuevo llega al diseñador
    sin que nadie se acuerde de documentarlo en el prompt."""
    guion = Guion([json.dumps({"part": "x", "codigo": BUENO})])
    DisenadorKitAgent(guion, ACTIVO).design("una escuadra")
    prompt = guion.prompts[0]
    assert "cuerpo.tornillo(" in prompt and "kit.extruir(" in prompt
    assert "M3_through_mm" in prompt
    assert "una escuadra" in prompt


def test_un_fallo_de_construccion_vuelve_con_el_programa_anterior():
    guion = Guion([json.dumps({"part": "x", "codigo": BUENO})])
    DisenadorKitAgent(guion, ACTIVO).design("t", rechazo=("CODIGO_VIEJO", "línea 4: radio"))
    assert "CODIGO_VIEJO" in guion.prompts[0] and "línea 4: radio" in guion.prompts[0]
