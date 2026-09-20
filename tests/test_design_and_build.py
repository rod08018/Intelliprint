"""Bucle de error, segundo nivel (F1.11 (bucle)).

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


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_la_construccion_informa_de_donde_queda_la_pieza(tmp_path):
    """El tamaño no basta para ensamblar: una placa de 60 mm centrada en el
    origen y otra que empieza en el origen miden lo mismo."""
    from orchestrator.build import build_part
    from orchestrator.schemas.recipe import Recipe

    r = build_part(Recipe.model_validate_json(_receta(8)), CATALOGO, tmp_path, _freecadcmd())
    assert r.bbox_min == pytest.approx([-30, -30, 0], abs=1e-6)
    assert r.bbox_max == pytest.approx([30, 30, 6], abs=1e-6)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_comprobacion_fallida_tras_construir_vuelve_al_agente(tmp_path):
    """Una pieza construible pero mal colocada es un rechazo más: su motivo
    llega al agente igual que un fallo de FreeCAD."""
    cliente = ClienteGuionizado([_receta(8), _receta(10)])
    agente = PartDesignerAgent(cliente, CATALOGO)

    def comprobar(resultado):
        return None if resultado.volume_mm3 < 60 * 60 * 6 - 400 else "el taladro central tiene que ser mayor"

    _, resultado = design_and_build(
        agente, "placa", CATALOGO, tmp_path, freecadcmd=_freecadcmd(), check=comprobar)
    assert len(cliente.prompts) == 2
    assert "el taladro central tiene que ser mayor" in cliente.prompts[1]
    assert resultado.volume_mm3 < 60 * 60 * 6 - 400


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_caja_que_no_cuadra_no_quema_los_tres_intentos(tmp_path):
    """4 rondas del trinquete se fueron así: la pieza estaba bien dibujada y
    era la caja DECLARADA la que no cuadraba, pero se le pedía al Part
    Designer que arreglara un desacuerdo que no era suyo."""
    cliente = ClienteGuionizado([_receta(8)] * 3)
    agente = PartDesignerAgent(cliente, CATALOGO)

    with pytest.raises(ConstruccionFallida, match="caja"):
        design_and_build(agente, "placa", CATALOGO, tmp_path, freecadcmd=_freecadcmd(),
                         check=lambda r: "la pieza ocupa x de -30 a 30; se necesita de 0 a 60",
                         check_es_de_la_caja=True)

    assert len(cliente.prompts) == 2      # un intento y una corrección, no tres
