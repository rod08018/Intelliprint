"""Bucle de error, segundo nivel (F1.11).

Primer nivel: receta inválida → error de esquema, sin lanzar FreeCAD.
Segundo nivel: receta VÁLIDA que FreeCAD rechaza al construir → el motivo
vuelve al Part Designer para que la corrija. Máximo 3 construcciones.
"""

import json

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.agents.part_designer import PartDesignerAgent
from orchestrator.build import ConstruccionFallida, design_and_build, motivo_del_fallo
from tests.test_generators import _freecadcmd


class ClienteGuionizado:
    def __init__(self, respuestas):
        self._r = list(respuestas)
        self.prompts = []

    def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self._r.pop(0)


def _receta(diametro: float) -> str:
    return json.dumps(
        {
            "part": "placa",
            "steps": [
                {"generator": "generate_plate",
                 "params": {"length_mm": 60, "width_mm": 60, "thickness_mm": 6}},
                {"generator": "generate_center_bore",
                 "params": {"diameter_mm": diametro}},
            ],
        }
    )


def test_extrae_el_motivo_marcado_de_entre_el_ruido_de_freecad():
    salida = (
        "FreeCAD 1.1.3\nRecompute......\nTraceback (most recent call last):\n"
        '  File "build.py", line 40\n'
        "RuntimeError: INTELLIPRINT_FALLO: la pieza salió en 4 sólidos separados; "
        "debería ser una sola\n"
    )
    assert motivo_del_fallo(salida) == (
        "la pieza salió en 4 sólidos separados; debería ser una sola"
    )


def test_sin_motivo_marcado_devuelve_el_final_del_traceback():
    """Un error de FreeCAD que no provocamos nosotros también tiene que
    llegarle al agente, aunque sea en crudo."""
    salida = "Traceback (most recent call last):\nNameError: name 'x' is not defined\n"
    assert "NameError" in motivo_del_fallo(salida)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_receta_que_parte_la_pieza_se_corrige_con_el_motivo(tmp_path):
    """Taladro Ø70 en placa de 60: válida como receta, rota como pieza.
    El agente recibe "4 sólidos" y en el segundo intento pide Ø22."""
    cliente = ClienteGuionizado([_receta(70), _receta(22)])
    agente = PartDesignerAgent(cliente, CATALOGO)

    receta, resultado = design_and_build(
        agente, "placa con taladro", CATALOGO, tmp_path, freecadcmd=_freecadcmd()
    )

    assert resultado.solids == 1
    assert receta.steps[1].params["diameter_mm"] == 22
    assert "4 sólidos" in cliente.prompts[1]
    assert '"diameter_mm": 70' in cliente.prompts[1]  # ve su propia receta


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_tres_construcciones_fallidas_se_rinden_con_el_ultimo_motivo(tmp_path):
    cliente = ClienteGuionizado([_receta(70)] * 3)
    agente = PartDesignerAgent(cliente, CATALOGO)

    with pytest.raises(ConstruccionFallida, match="4 sólidos"):
        design_and_build(
            agente, "placa", CATALOGO, tmp_path, freecadcmd=_freecadcmd()
        )
    assert len(cliente.prompts) == 3
