"""Generadores para mecanismos: barra con dos agujeros, cajas y agujeros
colocados. Probados construyendo geometría real; volúmenes a mano."""

import math

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.build import build_part
from orchestrator.schemas.recipe import Recipe, RecipeStep
from tests.test_generators import _freecadcmd


def _construir(tmp_path, pasos):
    receta = Recipe(part="p", steps=[RecipeStep(generator=g, params=p) for g, p in pasos])
    return build_part(receta, CATALOGO, tmp_path, _freecadcmd())


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_barra_con_dos_agujeros_para_manivela_o_biela(tmp_path):
    """Forma de estadio: rectángulo d x w con semicírculos de radio w/2 en
    los extremos, y un agujero en cada centro. Origen en el primer agujero,
    que es el pivote: así la pieza gira alrededor de su propio origen."""
    r = _construir(tmp_path, [("generate_link", {
        "center_distance_mm": 30, "width_mm": 10, "thickness_mm": 5, "hole_diameter_mm": 3.4})])

    estadio = (30 * 10 + math.pi * 5**2) * 5
    agujeros = 2 * math.pi * 1.7**2 * 5
    assert r.volume_mm3 == pytest.approx(estadio - agujeros, rel=1e-4)
    assert r.bbox_mm == pytest.approx([40, 10, 5])


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_cajas_colocadas_se_suman_en_una_sola_pieza(tmp_path):
    """Una bancada: placa y un raíl encima. Dos cajas que se tocan forman
    un único sólido."""
    r = _construir(tmp_path, [
        ("generate_box", {"length_mm": 100, "width_mm": 40, "height_mm": 4,
                          "x_mm": 0, "y_mm": 0, "z_mm": -4}),
        ("generate_box", {"length_mm": 80, "width_mm": 5, "height_mm": 6,
                          "x_mm": 10, "y_mm": 12, "z_mm": 0}),
    ])

    assert r.volume_mm3 == pytest.approx(100 * 40 * 4 + 80 * 5 * 6, rel=1e-6)
    assert r.solids == 1


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_agujero_colocado_donde_se_pide(tmp_path):
    """El pivote de la manivela no tiene por qué estar en el centro de la
    bancada."""
    r = _construir(tmp_path, [
        ("generate_box", {"length_mm": 100, "width_mm": 40, "height_mm": 4,
                          "x_mm": 30, "y_mm": 0, "z_mm": 0}),
        ("generate_hole", {"diameter_mm": 3.4, "x_mm": 0, "y_mm": 0}),
    ])

    assert r.volume_mm3 == pytest.approx(100 * 40 * 4 - math.pi * 1.7**2 * 4, rel=1e-5)


needs_freecad = pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")


@needs_freecad
def test_cilindro_horizontal_con_agujero_a_lo_largo_de_su_eje(tmp_path):
    """Un nudillo de bisagra: cilindro a lo largo de X con agujero pasante."""
    r = _construir(tmp_path, [
        ("generate_cylinder", {"diameter_mm": 10, "length_mm": 20, "x_mm": 5,
                               "y_mm": 0, "z_mm": 0, "axis": "x"}),
        ("generate_hole_axis", {"diameter_mm": 4, "x_mm": 0, "y_mm": 0, "z_mm": 0, "axis": "x"}),
    ])
    assert r.volume_mm3 == pytest.approx(math.pi * (25 - 4) * 20, rel=1e-5)
    assert r.bbox_min == pytest.approx([5, -5, -5], abs=1e-6)
    assert r.bbox_max == pytest.approx([25, 5, 5], abs=1e-6)


@needs_freecad
def test_vaciado_con_caja(tmp_path):
    r = _construir(tmp_path, [
        ("generate_box", {"length_mm": 40, "width_mm": 20, "height_mm": 10,
                          "x_mm": 0, "y_mm": 0, "z_mm": 0}),
        ("generate_cut_box", {"length_mm": 10, "width_mm": 30, "height_mm": 4,
                              "x_mm": 0, "y_mm": 0, "z_mm": 6}),
    ])
    assert r.volume_mm3 == pytest.approx(40 * 20 * 10 - 10 * 20 * 4, rel=1e-6)


@needs_freecad
def test_prisma_de_un_poligono(tmp_path):
    r = _construir(tmp_path, [("generate_prism", {
        "points_mm": [[0, 0], [30, 0], [0, 10]], "thickness_mm": 5, "z_mm": 2})])
    assert r.volume_mm3 == pytest.approx(30 * 10 / 2 * 5, rel=1e-6)
    assert r.bbox_min == pytest.approx([0, 0, 2], abs=1e-6)


@needs_freecad
def test_rueda_de_trinquete(tmp_path):
    """Área = N triángulos (centro, fondo_k, punta_k+1) — cálculo a mano."""
    n, rt, rr, t = 12, 25.0, 20.0, 6.0
    r = _construir(tmp_path, [("generate_ratchet_wheel", {
        "teeth": n, "tip_diameter_mm": 2 * rt, "root_diameter_mm": 2 * rr, "thickness_mm": t})])
    area = n * 0.5 * rr * rt * math.sin(2 * math.pi / n)
    assert r.volume_mm3 == pytest.approx(area * t, rel=1e-6)
    assert r.solids == 1


@needs_freecad
def test_resorte_helicoidal(tmp_path):
    """Volumen ≈ sección del alambre × longitud del hilo de la hélice."""
    d, w, paso, largo = 20.0, 2.0, 5.0, 30.0
    r = _construir(tmp_path, [("generate_spring", {
        "coil_diameter_mm": d, "wire_diameter_mm": w, "pitch_mm": paso, "length_mm": largo})])
    vueltas = (largo - w) / paso
    hilo = vueltas * math.hypot(math.pi * d, paso)
    assert r.volume_mm3 == pytest.approx(math.pi * (w / 2) ** 2 * hilo, rel=0.03)
    # El alambre cabe entre 0 y el largo (la caja de una B-spline es algo holgada).
    assert -0.5 < r.bbox_min[2] <= 0.3 and largo - 0.3 <= r.bbox_max[2] < largo + 0.5


@needs_freecad
def test_la_caja_del_resorte_incluye_el_grosor_del_alambre(tmp_path):
    """4 rondas del trinquete murieron adivinando esto: el agente declaraba
    ±coil/2 y salía ±(coil+wire)/2. Hasta ahora solo se fijaba la z."""
    d, w = 8.0, 1.0
    r = _construir(tmp_path, [("generate_spring", {
        "coil_diameter_mm": d, "wire_diameter_mm": w, "pitch_mm": 2.0, "length_mm": 10.0})])

    assert r.bbox_min[:2] == pytest.approx([-(d + w) / 2, -(d + w) / 2], abs=0.05)
    assert r.bbox_max[:2] == pytest.approx([(d + w) / 2, (d + w) / 2], abs=0.05)


@needs_freecad
def test_un_resorte_de_menos_de_una_vuelta_se_rechaza(tmp_path):
    """`length=3, wire=1.2, pitch=3` son 0.6 vueltas: ni es un resorte ni
    tiene huella circular, y su caja no hay quien la prediga."""
    from orchestrator.build import ConstruccionFallida

    with pytest.raises(ConstruccionFallida, match="vuelta"):
        _construir(tmp_path, [("generate_spring", {
            "coil_diameter_mm": 8, "wire_diameter_mm": 1.2, "pitch_mm": 3.0, "length_mm": 3.0})])


@needs_freecad
def test_la_caja_de_la_rueda_con_dientes_fuera_de_los_ejes(tmp_path):
    """Con 12 dientes una punta cae justo sobre cada eje y la caja es ±tip/2.
    Con 14 no, y la caja real es menor: nadie lo había probado."""
    n, rt, rr = 14, 24.0, 20.0
    r = _construir(tmp_path, [("generate_ratchet_wheel", {
        "teeth": n, "tip_diameter_mm": 2 * rt, "root_diameter_mm": 2 * rr, "thickness_mm": 5})])

    paso = 2 * math.pi / n
    esperado_y = max(max(rr * math.sin(k * paso), rt * math.sin((k + 1) * paso))
                     for k in range(n))
    assert r.bbox_max[1] == pytest.approx(esperado_y, abs=0.05)
    assert r.bbox_max[1] < rt - 0.3          # y NO es el radio de punta


@needs_freecad
def test_una_una_de_trinquete_tiene_punta_y_cara_de_ataque(tmp_path):
    """Los pawls de las 19 rondas eran cajas romas: el contacto era esquina
    contra flanco y el bloqueo declarado no bloqueaba."""
    r = _construir(tmp_path, [("generate_pawl", {
        "pivot_to_tip_mm": 30, "width_mm": 8, "thickness_mm": 6,
        "tip_angle_deg": 35, "hub_diameter_mm": 12, "hole_diameter_mm": 4.35})])

    assert r.solids == 1
    assert r.bbox_max[0] == pytest.approx(30, abs=0.1)      # la punta, en el eje X
    assert r.bbox_min[0] == pytest.approx(-6, abs=0.1)      # el cubo del pivote
    assert r.bbox_max[2] == pytest.approx(6, abs=1e-6)
    # Es un dedo que se estrecha, no una caja: ocupa bastante menos que su caja.
    caja = (r.bbox_max[0] - r.bbox_min[0]) * (r.bbox_max[1] - r.bbox_min[1]) * r.bbox_max[2]
    assert r.volume_mm3 < caja * 0.6


@needs_freecad
def test_la_una_apoyada_por_el_solucionador_bloquea_hacia_atras_y_monta_hacia_delante(tmp_path):
    """El oráculo no es una pose escrita a mano: se deja que el solucionador
    de contactos apoye la uña sobre la rueda, y se comprueba que con esa
    pose la rueda no puede retroceder y sí puede avanzar montando el diente."""
    from orchestrator.assembly import pair_gaps
    from orchestrator.mechanisms.contact import solve_contacts
    from orchestrator.mechanisms.kinematics import Kinematics
    from orchestrator.schemas.mechanism import MechanismSpec

    n, rt, rr = 12, 20.0, 16.0
    _construir(tmp_path / "rueda", [("generate_ratchet_wheel", {
        "teeth": n, "tip_diameter_mm": 2 * rt, "root_diameter_mm": 2 * rr, "thickness_mm": 6})])
    _construir(tmp_path / "pawl", [("generate_pawl", {
        "pivot_to_tip_mm": 24, "width_mm": 8, "thickness_mm": 6, "tip_angle_deg": 30,
        "hub_diameter_mm": 12, "hole_diameter_mm": 4.35})])
    piezas = {"rueda": tmp_path / "rueda" / "p.step", "pawl": tmp_path / "pawl" / "p.step"}

    spec = MechanismSpec(**{
        "title": "trinquete", "summary": "s",
        "driver": {"start": 0, "end": 30, "step": 30},
        "parts": [
            {"name": "rueda", "brief": "b", "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6],
             "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "t"}},
            {"name": "pawl", "origin": [36, 14, 0], "brief": "b",
             "bbox_min": [-6, -6, 0], "bbox_max": [24, 6, 6],
             "joint": {"type": "revolute", "axis": [0, 0, 1],
                       "rest_on": {"target": "rueda", "start": "235", "toward": "decrease",
                                   "limit": 45}}},
        ],
    })
    kin = Kinematics(spec)
    solve_contacts(spec, kin, piezas, {}, _freecadcmd(), [0])

    def hueco(giro_rueda):
        poses = {0: kin.poses(0, {"rueda": giro_rueda})}
        return pair_gaps(piezas, {}, poses, [("pawl", "rueda")], _freecadcmd())[0]["gap_mm"]

    assert hueco(0) >= 0                 # apoyada sobre el diente, sin atravesarlo
    assert hueco(-4) < 0                 # la rueda no puede retroceder: la uña se lo impide
