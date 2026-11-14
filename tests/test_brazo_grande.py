"""El brazo de seis ejes y 2 kg (F12.4 (muñeca) y F12.5 (arctos), ADR-022).

La tabla de motores y rodamientos la propuso el asistente y la aprobó el
usuario el 2026-11-14 («Sí, apruebo»), con las reductoras del hombro y del
codo compradas («Ambas compradas»). Aquí está el plan escrito a mano —el que
tendría que salir del desglosador— y sus cuentas de par, a mano y en gramos
por milímetro (1 N·m son 101 972 g·mm), con lo impreso a 0,2 g/mm como en
`dimensionar`.

Tramos: del hombro al codo 260 mm, del codo a la muñeca 240 y de la muñeca a
la brida 100. Desde la punta: el hombro a 600, el codo a 340, el giro del
antebrazo (J4) a 280, el cabeceo (J5) a 100 y el giro de la herramienta (J6)
a 40. Lo comprado que lleva cada pieza va en el eje del giro siguiente:

- brazo: el motorreductor del codo y su rodamiento, 1600 + 22 = 1622 g.
- antebrazo: lo del J4, 275 + 60 + 22 + 22 = 379 g.
- giro: lo del J5, 275 + 60 + 13 + 13 = 361 g.
- mano: lo del J6, 275 + 60 + 22 + 22 = 379 g.

Hombro (a 600): la carga, 2000 × 600 = 1 200 000; su tramo, 52 g a 130,
6 760; lo del brazo a 260, 421 720; el tramo del codo, 12 g a 290, 3 480; lo
del antebrazo a 320, 121 280; el tramo del J4, 36 g a 410, 14 760; lo del
giro a 500, 180 500; el tramo del J5, 12 g a 530, 6 360; lo de la mano a
560, 212 240; el tramo del J6, 8 g a 580, 4 640. Suma 2 171 740.

Codo (a 340): 680 000 + 12 g a 30 (360) + 379 a 60 (22 740) + 36 g a 150
(5 400) + 361 a 240 (86 640) + 12 g a 270 (3 240) + 379 a 300 (113 700) +
8 g a 320 (2 560) = 914 640.

J5 (a 100): 200 000 + 12 g a 30 (360) + 379 a 60 (22 740) + 8 g a 80 (640) =
223 740.

El J4 y el J6 giran sobre un eje que va a lo largo del brazo: con el brazo
estirado la carga está en su eje y la gravedad no les pide nada. Al J4 le
pide lo mismo que al J5 cuando la muñeca se dobla 90°: lo que cuelga queda
igual de lejos de su eje. Al J6 solo lo que se descentre la carga, que el
plan no dice.
"""

import copy

import pytest

from orchestrator.plan import validar_plan
from orchestrator.schemas.obra import Obra
from tests.test_plan_mecanico import AGUJEROS

G = 9.80665e-6
CICLOIDAL_28 = {"motor": "nema17", "tipo": "reductora", "relacion": 28}
PLAN = {
    "titulo": "Brazo de seis ejes y 2 kg", "carga_g": 2000,
    "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "se atornilla al tablero y gira el brazo",
         "compra": ["6810-2rs", "6810-2rs", "nema23"]},
        {"id": "torreta", "nombre": "Torreta", "que_hace": "gira sobre la base y aloja el hombro",
         "compra": ["nema23-pg47-76", "6806-2rs"], "depende_de": ["base"]},
        {"id": "brazo", "nombre": "Brazo", "que_hace": "del hombro al codo, 260 mm",
         "compra": ["nema23-pg47-56", "6806-2rs"], "depende_de": ["torreta"]},
        {"id": "antebrazo", "nombre": "Antebrazo", "que_hace": "sale del codo y aloja el giro",
         "compra": ["nema17", "cicloidal-nema17-28", "6806-2rs", "6806-2rs"],
         "depende_de": ["brazo"]},
        {"id": "giro", "nombre": "Giro del antebrazo", "que_hace": "gira sobre el eje del brazo",
         "compra": ["nema17", "cicloidal-nema17-28", "608zz", "608zz"],
         "depende_de": ["antebrazo"]},
        {"id": "mano", "nombre": "Mano", "que_hace": "cabecea y aloja el giro de la herramienta",
         "compra": ["nema17", "cicloidal-nema17-10", "6806-2rs", "6806-2rs"],
         "depende_de": ["giro"]},
        {"id": "brida", "nombre": "Brida", "que_hace": "donde se atornilla la herramienta",
         "depende_de": ["mano"]},
        {"id": "todo", "nombre": "El brazo", "tipo": "conjunto", "que_hace": "se mueve",
         "depende_de": ["base", "torreta", "brazo", "antebrazo", "giro", "mano", "brida"]},
    ],
    "uniones": [
        {"tipo": "fija", "id": "u1", "cabeza": "base", "agarra": "exterior", "metrica": "M4",
         "cantidad": 4},
        {"tipo": "gira", "id": "u2", "gira": "torreta", "sobre": "base", "componente": "6810-2rs",
         "recorrido_grados": 180, "eje": "vertical",
         "movido_por": {"motor": "nema23", "tipo": "correa", "relacion": 5}},
        {"tipo": "gira", "id": "u3", "gira": "brazo", "sobre": "torreta",
         "componente": "nema23-pg47-76", "recorrido_grados": 180, "radio_libre_mm": 610,
         "eje": "horizontal", "brazo_mm": 600},
        {"tipo": "gira", "id": "u4", "gira": "antebrazo", "sobre": "brazo",
         "componente": "nema23-pg47-56", "recorrido_grados": 180, "radio_libre_mm": 350,
         "eje": "horizontal", "brazo_mm": 340},
        {"tipo": "gira", "id": "u5", "gira": "giro", "sobre": "antebrazo",
         "componente": "cicloidal-nema17-28", "recorrido_grados": 180, "radio_libre_mm": 115,
         "eje": "horizontal", "brazo_mm": 280, "a_lo_largo": True, "movido_por": CICLOIDAL_28},
        {"tipo": "gira", "id": "u6", "gira": "mano", "sobre": "giro",
         "componente": "cicloidal-nema17-28", "recorrido_grados": 180, "radio_libre_mm": 110,
         "eje": "horizontal", "brazo_mm": 100, "movido_por": CICLOIDAL_28},
        {"tipo": "gira", "id": "u7", "gira": "brida", "sobre": "mano",
         "componente": "cicloidal-nema17-10", "recorrido_grados": 180, "radio_libre_mm": 45,
         "eje": "horizontal", "brazo_mm": 40, "a_lo_largo": True,
         "movido_por": {"motor": "nema17", "tipo": "reductora", "relacion": 10}},
    ],
}


def test_el_plan_del_brazo_de_2_kg_escrito_a_mano_vale():
    errores, _ = validar_plan(Obra(**PLAN), AGUJEROS)
    assert errores == []


def test_cada_motor_que_levanta_puede_con_lo_suyo():
    """Lo que da cada uno, pidiéndole la mitad de su par: el motorreductor
    de 76 mm del hombro, 1,89 × 46,656 × 0,73 / 2 = 32,186 N·m; el de 56 del
    codo, 1,25 × 46,656 × 0,73 / 2 = 21,287; las cicloidales 28:1 del J4 y
    del J5, 0,400 × 28 × 0,65 / 2 = 3,64. La base, de eje vertical, no carga
    peso y no sale; el J6 tampoco, porque el plan no dice cuánto se
    descentra la carga."""
    from orchestrator.dimensionar import pares
    hombro, codo, j4, j5 = pares(Obra(**PLAN))
    assert [p["union"] for p in (hombro, codo, j4, j5)] == ["u3", "u4", "u5", "u6"]
    assert hombro["pide_Nm"] == pytest.approx(2171740 * G) == pytest.approx(21.297, abs=1e-3)
    assert hombro["da_Nm"] == pytest.approx(32.186, abs=1e-3)
    assert codo["pide_Nm"] == pytest.approx(914640 * G) == pytest.approx(8.970, abs=1e-3)
    assert codo["da_Nm"] == pytest.approx(21.287, abs=1e-3)
    assert j5["pide_Nm"] == pytest.approx(223740 * G) == pytest.approx(2.194, abs=1e-3)
    assert j5["da_Nm"] == pytest.approx(3.64)


def test_un_giro_a_lo_largo_del_brazo_pide_lo_que_la_muneca_doblada():
    """El J4 gira el antebrazo sobre su propio eje. Con la muñeca doblada
    90°, la carga queda a los 100 mm del J5 del eje del J4, y todo lo que
    cuelga del J5 igual de lejos que del suyo: pide lo que el J5, 223 740
    g·mm. Contado como un giro que levanta, a 280 mm de la punta, serían más
    de 560 000 (5,5 N·m) y la cicloidal de 28:1 (3,64) no alcanzaría."""
    from orchestrator.dimensionar import errores, pares
    j4 = pares(Obra(**PLAN))[2]
    assert j4["union"] == "u5" and j4["pide_Nm"] == pytest.approx(223740 * G)
    assert j4["da_Nm"] == pytest.approx(3.64) and j4["brazo_mm"] == 100
    assert errores(Obra(**PLAN)) == []
    sin_decirlo = copy.deepcopy(PLAN)
    del sin_decirlo["uniones"][4]["a_lo_largo"]
    [error] = errores(Obra(**sin_decirlo))
    assert "u5" in error


def test_si_la_muneca_no_puede_doblada_lo_dice_el_giro_del_antebrazo():
    """Con una cicloidal de 10:1 en el J4 (0,400 × 10 × 0,65 / 2 = 1,30 N·m)
    no puede con los 2,194 que le pide la muñeca doblada, y el error dice
    con qué giro doblado."""
    from orchestrator.dimensionar import errores
    plan = copy.deepcopy(PLAN)
    plan["nodos"][3]["compra"][1] = "cicloidal-nema17-10"
    plan["uniones"][4].update(componente="cicloidal-nema17-10",
                              movido_por={"motor": "nema17", "tipo": "reductora", "relacion": 10})
    [error] = errores(Obra(**plan))
    assert "u5" in error and "u6" in error and "doblad" in error
    assert "2.194" in error and "1.300" in error and "100 mm" in error


def test_el_sitio_de_un_giro_a_lo_largo_no_es_lo_que_mide_el_brazo():
    """El radio libre de un giro es lo que barre la pieza alrededor de su
    eje. La que cabecea llega a 100 mm de su eje y necesita más de eso; la
    que gira a lo largo tiene la punta a 280 mm, pero sobre su eje: con la
    muñeca doblada barre los 100 del J5 y poco más (115), no 285."""
    errores, _ = validar_plan(Obra(**PLAN), AGUJEROS)
    assert errores == []
    plan = copy.deepcopy(PLAN)
    plan["uniones"][5]["radio_libre_mm"] = 90          # el J5, que sí levanta
    errores, _ = validar_plan(Obra(**plan), AGUJEROS)
    assert any("u6" in e and "radio libre" in e for e in errores)
