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


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_pieza_que_gira_sin_agujero_en_su_eje_se_explica(tmp_path):
    """Fallo real (bisagra): la pieza giraba alrededor de su origen, pero su
    agujero estaba 30 mm más allá. El motivo tiene que decir dónde está."""
    from orchestrator.build import build_part
    from orchestrator.mechanisms.checks import joint_axis_problems
    from orchestrator.schemas.mechanism import MechanismSpec
    from orchestrator.schemas.recipe import Recipe

    receta = Recipe(part="brazo", steps=[
        {"generator": "generate_box", "params": {"length_mm": 40, "width_mm": 10, "height_mm": 5,
                                                 "x_mm": 0, "y_mm": 0, "z_mm": 0}},
        {"generator": "generate_hole", "params": {"diameter_mm": 3.35, "x_mm": -15, "y_mm": 0}}])
    build_part(receta, CATALOGO, tmp_path / "brazo", _freecadcmd())
    spec = MechanismSpec(**_spec(0.5))
    problemas = joint_axis_problems(spec, {"brazo": tmp_path / "brazo" / "brazo.step"}, _freecadcmd())
    assert len(problemas) == 1
    assert "(-15, 0," in problemas[0] and "ORIGEN LOCAL" in problemas[0]

    bien = Recipe(**RECETAS["brazo"])
    build_part(bien, CATALOGO, tmp_path / "ok", _freecadcmd())
    assert joint_axis_problems(spec, {"brazo": tmp_path / "ok" / "brazo.step"}, _freecadcmd()) == []


def _corredera_con_pared(tope):
    from orchestrator.schemas.mechanism import MechanismSpec
    return MechanismSpec(**{
        "title": "corredera", "summary": "s",
        "driver": {"unit": "mm", "start": 0, "end": 25, "step": 5},
        "parts": [
            {"name": "base", "brief": "b", "bbox_min": [-20, -10, -4], "bbox_max": [35, 10, 10]},
            {"name": "carro", "origin": [0, 0, 0.5],
             "joint": {"type": "prismatic", "axis": [1, 0, 0], "value": "t"},
             "brief": "c", "bbox_min": [-5, -5, 0], "bbox_max": [5, 5, 5]},
        ],
        "stops": [tope],
    })


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
@pytest.mark.parametrize("tope, esperado", [
    ({"a": "base", "b": "carro", "at": 25, "beyond": "above"}, None),
    ({"a": "base", "b": "carro", "at": 20, "beyond": "above"}, "no llega a tocar"),
    ({"a": "base", "b": "carro", "at": 25, "beyond": "below"}, "no bloquea"),
])
def test_un_tope_tiene_que_tocar_en_su_valor_y_bloquear_despues(tmp_path, tope, esperado):
    """Carro de 10 mm que avanza t mm hacia una pared en x = 30: su cara
    llega a la pared en t = 25 (cálculo a mano)."""
    from orchestrator.build import build_part
    from orchestrator.mechanisms.checks import stop_problems
    from orchestrator.mechanisms.spec_layout import SpecLayout
    from orchestrator.schemas.recipe import Recipe

    caja = lambda l, w, h, x, z: {"generator": "generate_box", "params": {  # noqa: E731
        "length_mm": l, "width_mm": w, "height_mm": h, "x_mm": x, "y_mm": 0, "z_mm": z}}
    build_part(Recipe(part="base", steps=[caja(55, 20, 4, 7.5, -4), caja(5, 20, 10, 32.5, 0)]),
               CATALOGO, tmp_path / "base", _freecadcmd())
    build_part(Recipe(part="carro", steps=[caja(10, 10, 5, 0, 0)]),
               CATALOGO, tmp_path / "carro", _freecadcmd())
    spec = _corredera_con_pared(tope)
    steps = {n: tmp_path / n / f"{n}.step" for n in ("base", "carro")}
    problemas = stop_problems(spec, SpecLayout(spec), steps, _freecadcmd())
    if esperado is None:
        assert problemas == []
    else:
        assert any(esperado in p for p in problemas), problemas
