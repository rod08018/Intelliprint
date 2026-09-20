"""Parte de bloqueo con evidencias (F3.15 (mecanismos)).

Cuando el sistema se detiene —atascado o sin presupuesto— no basta con
decir "no pude". Hay que enseñar QUÉ falla, DÓNDE falla y cómo fue
evolucionando, para que la persona decida con datos y no a ciegas.
"""

import math

from PIL import Image

from orchestrator.mechanisms.evidence import escribir_bloqueo, render_frame


def _malla_caja(ancho=10.0, alto=4.0):
    """Una caja, sin pasar por FreeCAD: esto prueba el dibujo, no la geometría."""
    v = [[x, y, z] for x in (0, ancho) for y in (0, ancho) for z in (0, alto)]
    caras = [[0, 1, 2], [1, 3, 2], [4, 6, 5], [5, 6, 7], [0, 4, 1], [1, 4, 5],
             [2, 3, 6], [3, 7, 6], [0, 2, 4], [2, 6, 4], [1, 5, 3], [3, 5, 7]]
    return v, caras


def test_una_pose_se_dibuja_como_imagen_para_poder_mirarla(tmp_path):
    from mech_toolkit.geometry import Placement

    salida = render_frame(
        {"base": _malla_caja(), "brazo": _malla_caja(6, 2)},
        {"base": Placement(), "brazo": Placement(origin=[0, 0, 6], rotation=[0, 0, 30])},
        tmp_path / "fallo.png", title="choque a t = 180", resaltar={"brazo"},
    )

    with Image.open(salida) as img:
        assert img.size[0] > 200 and img.size[1] > 150


def test_el_parte_de_bloqueo_cuenta_que_paso_y_como_fue_evolucionando(tmp_path):
    rondas = [
        {"number": 1, "title": "Trinquete", "feedback": "- «pawl» no llega a apoyarse: 9.38 mm"},
        {"number": 2, "title": "Trinquete", "feedback": "- «pawl» no llega a apoyarse: 4.75 mm"},
        {"number": 3, "title": "Trinquete", "feedback": "- «pawl» no llega a apoyarse: 0.32 mm"},
    ]

    ruta = escribir_bloqueo(tmp_path, titulo="Trinquete y rueda", parada="atascado",
                            rondas=rondas, gasto_usd=0.41, imagenes=["fallo_t180.png"],
                            peticion="un trinquete que solo gire en un sentido")

    texto = ruta.read_text(encoding="utf-8").lower()
    crudo = ruta.read_text(encoding="utf-8")
    assert "atascado" in texto
    assert "9.38" in texto and "0.32" in texto          # la evolución, no solo el último
    assert "3 rondas" in texto and "0.41" in texto
    assert "fallo_t180.png" in texto
    assert "«pawl»" in texto
    # Y opciones concretas para que la persona elija:
    assert "Qué puedes hacer" in crudo


def test_si_el_fallo_no_mejora_el_parte_lo_dice(tmp_path):
    rondas = [{"number": i, "title": "t", "feedback": "- se solapan 12.5 mm³"} for i in (1, 2, 3)]

    texto = escribir_bloqueo(tmp_path, titulo="t", parada="atascado", rondas=rondas,
                             gasto_usd=0.2, imagenes=[], peticion="x").read_text(encoding="utf-8")

    assert "no mejoró" in texto or "sin avanzar" in texto


def test_el_parte_por_presupuesto_habla_de_dinero_y_no_de_atasco(tmp_path):
    texto = escribir_bloqueo(tmp_path, titulo="t", parada="presupuesto",
                             rondas=[{"number": 1, "title": "t", "feedback": "- algo"}],
                             gasto_usd=2.0, imagenes=[], peticion="x").read_text(
                                 encoding="utf-8").lower()

    assert "presupuesto" in texto and "2.00" in texto
    assert "subir el tope" in texto


def test_la_evolucion_se_saca_de_los_numeros_del_fallo():
    from orchestrator.mechanisms.evidence import evolucion

    valores = evolucion([
        {"feedback": "- se queda a 9.38 mm"},
        {"feedback": "- se queda a 4.75 mm"},
        {"feedback": "- se queda a 0.32 mm"},
    ])

    assert valores == [9.38, 4.75, 0.32]
    assert math.isclose(valores[-1], 0.32)
