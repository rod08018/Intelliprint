"""Lo que el agente NO puede dejar sin verificar (F3.15 (mecanismos)).

Fallo real: el trinquete quedó aprobado siendo una maqueta. El pawl tenía
articulación de valor constante (nunca se movía), el resorte estaba fijo
flotando en el aire, y no había ni una regla de contacto ni un bloqueo. Sus
dos comprobaciones las cumplían las propias fórmulas.

La lección: si las verificaciones son voluntarias, el vigilado elige si lo
vigilan. Estas son obligatorias y salen de la geometría declarada.
"""

import pytest

from orchestrator.mechanisms.checks import mechanism_problems
from orchestrator.schemas.mechanism import MechanismSpec


def _spec(**cambios):
    base = {
        "title": "t", "summary": "s", "params": {"amp": 30},
        "driver": {"start": 0, "end": 360, "step": 30},
        "parts": [
            {"name": "base", "brief": "b", "bbox_min": [-50, -50, -5], "bbox_max": [50, 50, 0]},
            {"name": "rueda", "brief": "b", "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6],
             "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "t"}},
            {"name": "palanca", "origin": [0, 0, 8], "brief": "b",
             "bbox_min": [-5, -5, 0], "bbox_max": [40, 5, 5],
             "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "amp*sin(t)"}},
        ],
        "rules": [], "checks": [],
    }
    base.update(cambios)
    return MechanismSpec(**base)


def _con(pieza, **campos):
    spec = _spec()
    partes = [p.model_dump() for p in spec.parts]
    partes.append({"name": pieza, "brief": "b", "bbox_min": [-3, -3, 0], "bbox_max": [3, 3, 10],
                   **campos})
    return _spec(parts=partes)


def test_una_articulacion_con_valor_constante_no_es_una_articulacion():
    """El pawl del trinquete: joint revolute con valor 120, fijo para siempre."""
    spec = _con("pawl", origin=[50, 0, 22],
                joint={"type": "revolute", "axis": [0, 0, 1], "value": "120"})

    problemas = mechanism_problems(spec)

    assert any("pawl" in p and "constante" in p for p in problemas)


def test_una_pieza_que_ni_se_mueve_ni_toca_a_nadie_sobra():
    """El resorte del trinquete: fijo, flotando en el aire, sin tocar nada."""
    spec = _con("resorte", origin=[50, -15, 7])

    problemas = mechanism_problems(spec)

    assert any("resorte" in p and ("no se mueve" in p or "no toca" in p) for p in problemas)


def test_una_pieza_fija_declarada_en_contacto_o_unida_esta_bien():
    spec = _spec(parts=[p.model_dump() for p in _con("tope", origin=[30, 0, 0]).parts],
                 rules=[{"a": "tope", "b": "base", "kind": "fixed"}])

    assert not any("tope" in p for p in mechanism_problems(spec))


def test_un_mecanismo_sano_no_da_problemas():
    assert mechanism_problems(_spec()) == []


@pytest.mark.parametrize("formula", ["t", "amp*sin(t)", "clamp(t/180,0,1)*amp"])
def test_las_formulas_que_dependen_del_ciclo_se_aceptan(formula):
    spec = _con("brazo", origin=[0, 0, 20],
                joint={"type": "revolute", "axis": [0, 0, 1], "value": formula})

    assert not any("brazo" in p for p in mechanism_problems(spec))


def test_una_pieza_apoyada_a_cero_milimetros_se_avisa_con_el_numero_exacto():
    """Rondas 5 y 12 del trinquete: 3 y 6 renglones de «quedan a 0.00 mm»
    porque las piezas se colocan justo sobre la cara de la base. Es
    aritmética sobre el spec: no hace falta abrir FreeCAD para verlo."""
    spec = _spec(parts=[
        {"name": "base", "brief": "b", "bbox_min": [-50, -50, 0], "bbox_max": [50, 50, 8]},
        {"name": "rueda", "origin": [0, 0, 8], "brief": "b",
         "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6],
         "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "t"}},
    ])

    problemas = mechanism_problems(spec, min_gap_mm=0.1)

    assert len(problemas) == 1
    assert "rueda" in problemas[0] and "base" in problemas[0]
    assert "0.1" in problemas[0]      # cuánto hay que subirla


def test_una_pieza_con_holgura_suficiente_no_molesta():
    spec = _spec(parts=[
        {"name": "base", "brief": "b", "bbox_min": [-50, -50, 0], "bbox_max": [50, 50, 8]},
        {"name": "rueda", "origin": [0, 0, 8.2], "brief": "b",
         "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6],
         "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "t"}},
    ])

    assert mechanism_problems(spec, min_gap_mm=0.1) == []


def test_varias_piezas_apoyadas_igual_se_agrupan_en_un_renglon():
    """La ronda 12 devolvió 6 renglones del mismo error y el agente reescribió
    el mecanismo entero en vez de subir las piezas 0.2 mm."""
    piezas = [{"name": "base", "brief": "b", "bbox_min": [-50, -50, 0], "bbox_max": [50, 50, 8]}]
    for nombre in ("rueda", "palanca", "pawl"):
        piezas.append({"name": nombre, "origin": [0, 0, 8], "brief": "b",
                       "bbox_min": [-5, -5, 0], "bbox_max": [5, 5, 4],
                       "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "t"}})

    problemas = mechanism_problems(_spec(parts=piezas), min_gap_mm=0.1)

    assert len(problemas) == 1
    assert all(n in problemas[0] for n in ("rueda", "palanca", "pawl"))
