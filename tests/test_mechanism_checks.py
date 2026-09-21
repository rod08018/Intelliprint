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
            # Conducida por contacto: solo la palanca, la motriz, lleva fórmula.
            # Antes este «mecanismo sano» movía también la rueda por fórmula,
            # que es justo la trampa del trinquete del 2026-09-21.
            {"name": "rueda", "brief": "b", "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6],
             "joint": {"type": "revolute", "axis": [0, 0, 1],
                       "rest_on": {"target": "palanca", "start": "0", "toward": "increase",
                                   "limit": 40, "carry": True}}},
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

    # Lo que se prueba es que no la tome por CONSTANTE. Que haya dos motrices
    # (la palanca y este brazo) es otra regla, con su propio test abajo.
    assert not any("brazo" in p and "constante" in p for p in mechanism_problems(spec))


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

    # Tres piezas por fórmula dan también el aviso de «una sola motriz», y
    # con razón; lo que se prueba aquí es que las apoyadas se agrupen.
    problemas = [p for p in mechanism_problems(_spec(parts=piezas), min_gap_mm=0.1)
                 if "sin holgura" in p]

    assert len(problemas) == 1
    assert all(n in problemas[0] for n in ("rueda", "palanca", "pawl"))


def test_un_estiramiento_constante_no_es_un_resorte():
    """En las 19 rondas el resorte llevaba `stretch: "1"` —rígido— porque no
    podía depender de nada. Ahora puede, así que un resorte que no se
    deforma es un error."""
    spec = _spec(parts=[
        {"name": "base", "brief": "b", "bbox_min": [-50, -50, -5], "bbox_max": [50, 50, 0]},
        {"name": "muelle", "brief": "b", "bbox_min": [-4, -4, 0], "bbox_max": [4, 4, 20],
         "stretch": "1"},
        {"name": "vastago", "brief": "b", "bbox_min": [-3, -3, 0], "bbox_max": [3, 3, 40],
         "joint": {"type": "prismatic", "axis": [0, 0, 1], "value": "-t/10"}},
    ], rules=[{"a": "muelle", "b": "vastago", "kind": "contact"}])

    problemas = mechanism_problems(spec)

    assert any("muelle" in p and "no se deforma" in p for p in problemas)


def test_un_estiramiento_que_depende_de_algo_esta_bien():
    spec = _spec(parts=[
        {"name": "base", "brief": "b", "bbox_min": [-50, -50, -5], "bbox_max": [50, 50, 0]},
        {"name": "muelle", "brief": "b", "bbox_min": [-4, -4, 0], "bbox_max": [4, 4, 20],
         "stretch": "(20 + q_vastago) / 20"},
        {"name": "vastago", "brief": "b", "bbox_min": [-3, -3, 0], "bbox_max": [3, 3, 40],
         "joint": {"type": "prismatic", "axis": [0, 0, 1], "value": "-t/10"}},
    ], rules=[{"a": "muelle", "b": "vastago", "kind": "contact"}])

    assert not any("muelle" in p for p in mechanism_problems(spec))


def test_no_se_puede_bloquear_una_pieza_que_se_mueve_por_formula():
    """El trinquete resuelto declaraba que el pawl impide retroceder a la
    rueda... y a la vez le imponía el avance con una fórmula. La fórmula la
    mueve igual: el bloqueo no demuestra nada."""
    spec = _spec(parts=[
        {"name": "base", "brief": "b", "bbox_min": [-50, -50, -5], "bbox_max": [50, 50, 0]},
        {"name": "rueda", "brief": "b", "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6],
         "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "30*clamp(t/180,0,1)"}},
        {"name": "pawl", "origin": [30, 0, 0], "brief": "b",
         "bbox_min": [-6, -6, 0], "bbox_max": [20, 6, 6],
         "joint": {"type": "revolute", "axis": [0, 0, 1],
                   "rest_on": {"target": "rueda", "start": "180", "toward": "decrease",
                               "limit": 40}}},
    ], blocks=[{"body": "rueda", "against": "pawl", "at": 180, "delta": -5}])

    problemas = mechanism_problems(spec)

    assert any("rueda" in p and "carry" in p for p in problemas)


def test_una_pieza_bloqueada_que_se_mueve_por_contacto_esta_bien():
    spec = _spec(parts=[
        {"name": "base", "brief": "b", "bbox_min": [-50, -50, -5], "bbox_max": [50, 50, 0]},
        {"name": "rueda", "brief": "b", "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6],
         "joint": {"type": "revolute", "axis": [0, 0, 1],
                   "rest_on": {"target": "palanca", "start": "0", "toward": "increase",
                               "limit": 40, "carry": True}}},
        {"name": "palanca", "origin": [30, 0, 0], "brief": "b",
         "bbox_min": [-6, -6, 0], "bbox_max": [20, 6, 6],
         "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "20*sin(t)"}},
    ], blocks=[{"body": "rueda", "against": "palanca", "at": 180, "delta": -5}])

    assert not any("carry" in p for p in mechanism_problems(spec))


# --- Solo la pieza motriz se mueve por fórmula (ADR-013, enmienda) ---------
#
# El trinquete del 2026-09-21 salió «resuelto» en la ronda 12 con la rueda
# girando por fórmula —30 * min(t, 90) / 90— y las uñas siguiéndola. La regla
# de arriba (no bloquear lo que mueves por fórmula) la esquivó sin declarar
# ningún bloqueo. El GIF se veía bien; el mecanismo no demostraba nada.
#
# Solo la pieza que mueve la PERSONA puede llevar fórmula. Todo lo demás se
# mueve porque otra pieza lo empuja (`rest_on`, con `carry` si se queda donde
# lo dejan) o va unido a algo que se mueve. Decisión del usuario.


def _trinquete(rueda_joint):
    return _spec(parts=[
        {"name": "base", "brief": "b", "bbox_min": [-50, -50, -5], "bbox_max": [50, 50, 0]},
        {"name": "palanca", "origin": [30, 0, 0], "brief": "b",
         "bbox_min": [-6, -6, 0], "bbox_max": [20, 6, 6],
         "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "20*sin(t)"}},
        {"name": "rueda", "brief": "b", "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6],
         "joint": rueda_joint},
    ])


def test_dos_piezas_movidas_por_formula_no_se_aceptan():
    problemas = mechanism_problems(_trinquete(
        {"type": "revolute", "axis": [0, 0, 1], "value": "30 * min(t, 90) / 90"}))
    (p,) = [p for p in problemas if "fórmula" in p and "motriz" in p]
    # El motivo nombra a las dos y dice qué hacer en vez de eso.
    assert "«palanca»" in p and "«rueda»" in p
    assert "rest_on" in p and "carry" in p


def test_la_motriz_por_formula_y_la_conducida_por_contacto_esta_bien():
    problemas = mechanism_problems(_trinquete(
        {"type": "revolute", "axis": [0, 0, 1],
         "rest_on": {"target": "palanca", "start": "0", "toward": "increase",
                     "limit": 40, "carry": True}}))
    assert not [p for p in problemas if "motriz" in p]


def test_un_resorte_que_se_estira_no_cuenta_como_otra_motriz():
    """El estiramiento de un resorte es una fórmula, pero no mueve nada: se
    deforma según lo que hacen otras piezas."""
    spec = _trinquete({"type": "revolute", "axis": [0, 0, 1],
                       "rest_on": {"target": "palanca", "start": "0", "toward": "increase",
                                   "limit": 40, "carry": True}})
    partes = [p.model_dump() for p in spec.parts] + [
        {"name": "muelle", "brief": "b", "bbox_min": [-3, -3, 0], "bbox_max": [3, 3, 10],
         "stretch": "1 + 0.2*sin(t)"}]
    assert not [p for p in mechanism_problems(_spec(parts=partes)) if "motriz" in p]
