"""Esquema y cinemática de un mecanismo declarado por el agente (F3.15 (mecanismos)).

Oráculo independiente: la biela-manivela escrita como árbol cinemático con
fórmulas tiene que dar las mismas posiciones que `sim.linkages`, que se
probó por su cuenta.
"""


import pytest

from mech_toolkit.geometry import _rotacion
from orchestrator.mechanisms.kinematics import Kinematics, euler_zyx
from orchestrator.schemas.mechanism import MechanismSpec
from sim.linkages import SliderCrank

R, L = 30.0, 90.0


def _pieza(nombre, **kw):
    return {"name": nombre, "brief": "b", "bbox_min": [-1, -1, -1], "bbox_max": [1, 1, 1], **kw}


def _biela_manivela(**cambios):
    spec = {
        "title": "biela-manivela", "summary": "s",
        "params": {"r": R, "l": L},
        "driver": {"start": 0, "end": 360, "step": 30},
        "parts": [
            _pieza("bancada"),
            _pieza("manivela", joint={"type": "revolute", "axis": [0, 0, 1], "value": "t"}),
            # La biela cuelga del muñón de la manivela y se gira para mirar a la corredera.
            _pieza("biela", parent="manivela", origin=[R, 0, 5],
                   joint={"type": "revolute", "axis": [0, 0, 1],
                          "value": "-t - asin(r*sin(t)/l)"}),
            _pieza("corredera", joint={"type": "prismatic", "axis": [1, 0, 0],
                                       "value": "r*cos(t) + sqrt(l**2 - (r*sin(t))**2)"}),
        ],
        "pins": [{"name": "eje_muñon", "parent": "manivela", "origin": [R, 0, 0],
                  "diameter_mm": 3, "length_mm": 10}],
        "checks": [{"body": "corredera", "measure": "travel", "axis": "x", "expected": 60,
                    "tolerance": 0.5, "description": "carrera de 60 mm"}],
    }
    spec.update(cambios)
    return MechanismSpec(**spec)


def test_la_biela_manivela_declarada_coincide_con_sim_linkages():
    k = Kinematics(_biela_manivela())
    oraculo = SliderCrank(R, L)
    for t in k.frames():
        pose = k.poses(t)
        esperado = oraculo.at(t)
        assert pose["corredera"].origin[0] == pytest.approx(esperado.slider_x, abs=1e-9)
        # El muñón viaja con la manivela, colgado de ella.
        assert pose["eje_muñon"].origin[:2] == pytest.approx(esperado.crank_pin, abs=1e-9)
        # El extremo de la biela cae sobre la corredera.
        r, p = k.matrices(t)["biela"]
        punta = [p[i] + L * r[i][0] for i in range(3)]
        assert punta[0] == pytest.approx(esperado.slider_x, abs=1e-9)
        assert punta[1] == pytest.approx(0, abs=1e-9)


def test_los_requisitos_se_miden_con_la_cinematica():
    Kinematics(_biela_manivela()).validate()
    corta = _biela_manivela(params={"r": 20, "l": L})
    with pytest.raises(ValueError, match="carrera de 60 mm.*40.00"):
        Kinematics(corta).validate()


def test_una_formula_fuera_de_dominio_se_explica_con_el_valor_del_parametro():
    """Biela más corta que la manivela: la corredera no llega (se bloquea)."""
    with pytest.raises(ValueError, match="t = 60"):
        Kinematics(_biela_manivela(params={"r": 30, "l": 20})).validate()


def test_la_rotacion_barrida_se_mide_alrededor_de_un_eje():
    spec = _biela_manivela(checks=[{"body": "manivela", "measure": "rotation", "axis": "z",
                                    "expected": 360, "tolerance": 1, "description": "vuelta"}])
    Kinematics(spec).validate()


@pytest.mark.parametrize("rot", [[10, 20, 30], [0, 90, 0], [45, -90, 10], [170, 5, -60]])
def test_euler_ida_y_vuelta(rot):
    r = _rotacion(*rot)
    de_vuelta = _rotacion(*euler_zyx(r))
    for i in range(3):
        assert de_vuelta[i] == pytest.approx(r[i], abs=1e-9)


@pytest.mark.parametrize("cambio, motivo", [
    ({"parts": [_pieza("a"), _pieza("a")]}, "repetidos"),
    ({"parts": [_pieza("a", parent="fantasma"), _pieza("b")]}, "fantasma"),
    ({"parts": [_pieza("a", parent="b"), _pieza("b", parent="a")]}, "ciclo"),
    ({"parts": [_pieza("a", joint={"type": "revolute", "axis": [0, 0, 1],
                                  "value": "__import__('os')"}), _pieza("b")]}, "a.joint"),
    ({"driver": {"start": 0, "end": 360, "step": 1}}, "posiciones"),
])
def test_el_esquema_rechaza_especificaciones_incoherentes(cambio, motivo):
    with pytest.raises(ValueError, match=motivo):
        _biela_manivela(**cambio)


def _con_apoyo():
    """Un seguidor que sube porque la leva lo empuja: su carrera no se puede
    medir hasta resolver el apoyo con la geometría."""
    return MechanismSpec(**{
        "title": "leva", "summary": "s", "params": {"e": 10},
        "driver": {"start": 0, "end": 360, "step": 90},
        "parts": [
            _pieza("base"),
            _pieza("leva", joint={"type": "revolute", "axis": [0, 1, 0], "value": "t"}),
            _pieza("seguidor", joint={"type": "prismatic", "axis": [0, 0, 1],
                                      "rest_on": {"target": "leva", "start": "40",
                                                  "toward": "decrease", "limit": 40}}),
        ],
        "checks": [{"body": "seguidor", "measure": "travel", "axis": "z", "expected": 20,
                    "tolerance": 1, "description": "carrera del seguidor"}],
    })


def test_un_requisito_que_depende_de_un_apoyo_no_se_juzga_antes_de_resolverlo():
    """Fallo real: la leva murió porque su carrera medía 0 antes de resolver
    el contacto, y al agente se le pedía algo imposible."""
    k = Kinematics(_con_apoyo())

    k.validate()      # no lanza: el apoyo aún no está resuelto

    pendientes = k.checks_pendientes()
    assert [c.description for c in pendientes] == ["carrera del seguidor"]


def test_una_vez_resuelto_el_apoyo_el_requisito_si_se_juzga():
    spec = _con_apoyo()
    k = Kinematics(spec)
    # Como si el contacto hubiera dado estas alturas: recorrido de solo 5 mm.
    k.set_solved({(t, "seguidor"): v for t, v in zip(k.frames(), [0, 5, 0, 5, 0])})

    with pytest.raises(ValueError, match="carrera del seguidor"):
        k.validate()


def test_una_formula_puede_usar_el_valor_de_otra_articulacion():
    """Un resorte se comprime lo que se mueve la pieza que lo aplasta. Hasta
    ahora `stretch` solo veía el ciclo, así que el resorte tenía que ser
    rígido — y un resorte rígido no devuelve nada."""
    spec = MechanismSpec(**{
        "title": "t", "summary": "s", "params": {"l0": 20},
        "driver": {"start": 0, "end": 90, "step": 45},
        "parts": [
            _pieza("base"),
            _pieza("vastago", joint={"type": "prismatic", "axis": [0, 0, 1], "value": "-t/10"}),
            _pieza("muelle", stretch="(l0 + q_vastago) / l0"),
        ],
    })

    k = Kinematics(spec)

    assert k.poses(0)["muelle"].scale_z == pytest.approx(1.0)
    assert k.poses(90)["muelle"].scale_z == pytest.approx((20 - 9) / 20)


def test_un_nombre_de_articulacion_que_no_existe_se_rechaza():
    with pytest.raises(ValueError, match="q_fantasma"):
        MechanismSpec(**{
            "title": "t", "summary": "s",
            "driver": {"start": 0, "end": 90, "step": 45},
            "parts": [_pieza("base"), _pieza("m", stretch="q_fantasma")],
        })
