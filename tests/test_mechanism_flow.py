"""Flujo del Mechanism Designer (F3.15 (mecanismos)), con modelos guionizados.

Lo que se prueba es el bucle: una especificación que choca vuelve al
agente con el motivo concreto, la ronda siguiente se construye, y el
ensamble y la animación se guardan siempre.
"""

import json

import pytest

from mech_toolkit.generators import CATALOGO
from mech_toolkit.profile import PrinterProfile
from orchestrator.agents.mechanism_designer import MechanismDesignerAgent
from orchestrator.agents.part_designer import PartDesignerAgent
from orchestrator.mechanisms.flow import design_mechanism
from tests.test_generators import _freecadcmd

PERFIL = PrinterProfile(id="m5", fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35})


def _spec(z_brazo: float) -> dict:
    """Un brazo que gira sobre una base con un pasador vertical."""
    return {
        "title": "Brazo giratorio", "summary": "s", "assumptions": ["pasador de Ø3"],
        "driver": {"start": 0, "end": 90, "step": 45, "label": "giro"},
        "parts": [
            {"name": "base", "brief": "Pieza «base»: placa 40x20x4, cara superior en z = 0.",
             "bbox_min": [-20, -10, -4], "bbox_max": [20, 10, 0]},
            {"name": "brazo", "origin": [0, 0, z_brazo],
             "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "t"},
             "brief": "Pieza «brazo»: barra de 30 entre centros.",
             "bbox_min": [-5, -5, 0], "bbox_max": [35, 5, 5]},
        ],
        "pins": [{"name": "eje", "origin": [0, 0, -4], "diameter_mm": 3, "length_mm": 9}],
        "rules": [{"a": "base", "b": "eje", "kind": "fixed"}],
        "checks": [{"body": "brazo", "measure": "rotation", "axis": "z", "expected": 90,
                    "tolerance": 1, "description": "gira 90°"}],
    }


RECETAS = {
    "base": {"part": "base", "steps": [
        {"generator": "generate_box", "params": {"length_mm": 40, "width_mm": 20, "height_mm": 4,
                                                 "x_mm": 0, "y_mm": 0, "z_mm": -4}},
        {"generator": "generate_hole", "params": {"diameter_mm": 3, "x_mm": 0, "y_mm": 0}}]},
    "brazo": {"part": "brazo", "steps": [
        {"generator": "generate_link", "params": {"center_distance_mm": 30, "width_mm": 10,
                                                  "thickness_mm": 5, "hole_diameter_mm": 3.35}}]},
}


class Guion:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        r = self.respuestas.pop(0)
        return r(prompt) if callable(r) else r


class DisenadorDePiezas:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        tarea = prompt.split("## Tarea")[-1]
        return json.dumps(next(v for k, v in RECETAS.items() if f"«{k}»" in tarea))


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_choque_vuelve_al_agente_y_la_ronda_siguiente_lo_corrige(tmp_path):
    # Ronda 1: el brazo en z = 0 se hunde en la base. Ronda 2: z = 0.5.
    mecanico = Guion([json.dumps(_spec(0.0)), json.dumps(_spec(0.5))])
    piezas = DisenadorDePiezas()
    informe = design_mechanism(
        "un brazo que gire 90° sobre una base",
        MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(piezas, CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, animar=False,
    )
    assert len(informe.rounds) == 2
    assert "base" in informe.rounds[0].feedback and "brazo" in informe.rounds[0].feedback
    assert "Tu diseño anterior NO funciona" in mecanico.prompts[1]
    assert informe.ok
    assert (tmp_path / "assembly.FCStd").exists()
    assert (tmp_path / "rondas" / "1" / "mechanism.json").exists()
    # La base no cambió entre rondas: no se vuelve a pedir al modelo.
    assert sum("«base»" in p.split("## Tarea")[-1] for p in piezas.prompts) == 1


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_si_ninguna_ronda_funciona_el_ensamble_se_guarda_igual(tmp_path):
    mecanico = Guion([json.dumps(_spec(0.0))] * 2)
    informe = design_mechanism(
        "un brazo", MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, max_rounds=2, animar=False,
    )
    assert not informe.ok
    assert (tmp_path / "assembly.FCStd").exists()
    assert informe.final is not None and informe.final.collisions
