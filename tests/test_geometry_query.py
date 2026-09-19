"""Búsqueda de geometría por contrato (F2.13, ADR-011). Python puro.

FreeCAD solo extrae hechos (caras cilíndricas del STEP). Decidir cuál
corresponde a una interfaz se hace aquí, y por eso se prueba sin FreeCAD.
"""

import math

import pytest

from mech_toolkit.geometry import Cylinder, Frame, Placement, find_bore, find_holes_on_circle

EJE_Z = [0.0, 0.0, 1.0]


def _cil(x, y, r, largo=6.0, eje=EJE_Z):
    return Cylinder(radius=r, axis=eje, point=[x, y, 3.0], length=largo)


# --- Transformación de coordenadas ------------------------------------------


def test_la_placement_identidad_no_cambia_el_frame():
    f = Frame(origin=[1, 2, 3], axis=EJE_Z)
    assert Placement().to_local(f) == f


def test_una_pieza_desplazada_lleva_el_frame_a_sus_coordenadas():
    """El frame está en coordenadas del ensamble; la pieza se mide sola."""
    pieza = Placement(origin=[0, 0, 45])
    local = pieza.to_local(Frame(origin=[0, 0, 45], axis=EJE_Z))
    assert local.origin == pytest.approx([0, 0, 0])


def test_una_pieza_girada_90_grados_gira_tambien_el_eje():
    pieza = Placement(rotation=[0, 90, 0])  # 90° sobre Y: X -> -Z, Z -> X
    local = pieza.to_local(Frame(origin=[0, 0, 0], axis=[1, 0, 0]))
    assert local.axis == pytest.approx([0, 0, 1], abs=1e-9)


# --- Asiento centrado (bearing_seat) ----------------------------------------


def test_encuentra_el_taladro_que_pasa_por_el_frame():
    caras = [_cil(0, 0, 11.05), _cil(15.5, 15.5, 1.65)]
    taladro = find_bore(caras, Frame(origin=[0, 0, 0], axis=EJE_Z))
    assert taladro.radius == pytest.approx(11.05)


def test_entre_concentricos_elige_el_mayor():
    """Un avellanado y un agujero comparten eje: el asiento es el mayor."""
    caras = [_cil(0, 0, 4.0), _cil(0, 0, 11.05)]
    assert find_bore(caras, Frame(origin=[0, 0, 0], axis=EJE_Z)).radius == pytest.approx(11.05)


def test_un_taladro_desplazado_40mm_no_se_encuentra():
    """El ejemplo de ADR-011. Con etiquetas, el QA mediría esta cara y
    daría Ø22.10 correcto. Buscando por contrato, aquí no hay nada."""
    caras = [_cil(40, 0, 11.05)]
    assert find_bore(caras, Frame(origin=[0, 0, 0], axis=EJE_Z)) is None


def test_un_cilindro_con_otro_eje_no_cuenta():
    """Un agujero horizontal que pasa por el mismo punto no es el asiento."""
    caras = [_cil(0, 0, 11.05, eje=[1, 0, 0])]
    assert find_bore(caras, Frame(origin=[0, 0, 0], axis=EJE_Z)) is None


# --- Patrón de tornillos ----------------------------------------------------


def _cuadro(paso, r=1.65):
    s = paso / 2
    return [_cil(x, y, r) for x, y in [(s, s), (-s, s), (s, -s), (-s, -s)]]


def test_encuentra_los_agujeros_sobre_la_circunferencia_del_patron():
    """Un cuadro de 31 mm tiene sus agujeros en un círculo de 31·√2."""
    pcd = 31 * math.sqrt(2)
    agujeros = find_holes_on_circle(
        _cuadro(31) + [_cil(0, 0, 11.0)],  # el taladro central no cuenta
        Frame(origin=[0, 0, 0], axis=EJE_Z),
        pcd_mm=pcd,
    )
    assert len(agujeros) == 4


def test_un_cilindro_partido_en_dos_caras_cuenta_como_un_agujero():
    """FreeCAD a veces representa un agujero como dos medias caras."""
    s = 15.5
    doble = [_cil(s, s, 1.65), _cil(s, s, 1.65)] + _cuadro(31)[1:]
    agujeros = find_holes_on_circle(
        doble, Frame(origin=[0, 0, 0], axis=EJE_Z), pcd_mm=31 * math.sqrt(2)
    )
    assert len(agujeros) == 4


def test_un_patron_con_el_paso_equivocado_no_aporta_agujeros():
    """Cuadro de 35 donde el contrato dice 31: cero agujeros en su sitio,
    no cuatro agujeros medidos en el sitio equivocado."""
    agujeros = find_holes_on_circle(
        _cuadro(35), Frame(origin=[0, 0, 0], axis=EJE_Z), pcd_mm=31 * math.sqrt(2)
    )
    assert agujeros == []


# --- Interior (agujero) frente a exterior (saliente) ------------------------
# Fallo encontrado con el NEMA17 de referencia: find_bore elegía el cilindro
# concéntrico más grande, y el cuerpo del motor tiene esquinas redondeadas
# de Ø53.84 en el mismo eje. No distinguía un agujero de un saliente.


def test_un_alojamiento_redondo_mide_el_asiento_y_no_su_pared_exterior():
    """El caso típico: un alojamiento de rodamiento es un cilindro EXTERIOR
    alrededor del asiento INTERIOR. Elegir "el mayor" medía la pared."""
    asiento = Cylinder(radius=11.05, axis=EJE_Z, point=[0, 0, 3.5], length=7, internal=True)
    pared = Cylinder(radius=16.0, axis=EJE_Z, point=[0, 0, 3.5], length=7, internal=False)

    taladro = find_bore([asiento, pared], Frame(origin=[0, 0, 0], axis=EJE_Z))

    assert taladro.radius == pytest.approx(11.05)


def test_un_saliente_se_busca_como_saliente():
    """El saliente de centrado del NEMA17 empieza en la cara y sale hacia
    fuera; las esquinas redondeadas del cuerpo quedan detrás de la cara."""
    from mech_toolkit.geometry import find_boss

    piloto = Cylinder(radius=11.0, axis=[0, 0, -1], point=[0, 0, 0.8], length=1.6, internal=False)
    esquinas = Cylinder(radius=26.92, axis=[0, 0, -1], point=[0, 0, -3.9], length=7.75, internal=False)

    saliente = find_boss([piloto, esquinas], Frame(origin=[0, 0, 0], axis=EJE_Z))

    assert saliente.radius == pytest.approx(11.0)


def test_los_agujeros_de_un_patron_son_interiores():
    """Un patrón de pivotes (exteriores) no es un patrón de agujeros."""
    pivotes = [Cylinder(radius=1.65, axis=EJE_Z, point=[x, y, 3], length=6, internal=False)
               for x, y in [(15.5, 15.5), (-15.5, 15.5), (15.5, -15.5), (-15.5, -15.5)]]

    assert find_holes_on_circle(pivotes, Frame(origin=[0, 0, 0], axis=EJE_Z),
                                pcd_mm=31 * math.sqrt(2)) == []
