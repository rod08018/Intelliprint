"""El ala volante se dimensiona con lo que él compra en Amazon.

Él, el 2026-11-16: «que tal si le apuntamos a algo de 15k mAh para tener un
poco mas de 1 hora de vuelo? o usemos 6s» y «usemos motores y bateria que
pueda comprar en amazon». Antes el dimensionado buscaba cuántas celdas 21700
hacían falta para 3 horas: con el peso real de las piezas pedía 54 y 9,3 kg
de avión. Ahora la batería y los motores son los de un anuncio, y lo que sale
es la autonomía.

Lo esperado viene de los anuncios (el peso de la batería, el empuje del
motor) y de la petición, no del dimensionado.
"""

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def r():
    return json.loads((RAIZ / "scripts" / "avion_vtol.json").read_text(encoding="utf-8"))


def test_la_bateria_es_una_lipo_6s_de_16000_mah(r):
    """22,2 V × 16 Ah = 355,2 Wh; la Tattu Plus de 16 000 mAh pesa 1,93 kg
    según su anuncio."""
    assert r["bateria"]["serie"] == 6
    assert r["bateria"]["mAh"] == 16000
    assert r["bateria"]["Wh"] == pytest.approx(355.2, abs=0.1)
    assert r["masa_kg"]["batería LiPo 6S 16 000 mAh"] == pytest.approx(1.93, abs=0.01)


def test_vuela_algo_mas_de_una_hora(r):
    assert r["autonomia_h"] >= 1.0


def test_los_rotores_son_los_del_anuncio_con_helice_de_15(r):
    """El 4312 de 400 KV da 3 kg por hélice en 6S, con hélices de 15 a 18″
    (su anuncio): con 13″ no llega."""
    assert r["rotores"]["helice_vtol_pulg"] == 15
    assert r["vtol"]["empuje_max_por_motor_kg"] == pytest.approx(3.0)


def test_los_cuatro_rotores_levantan_el_avion_con_margen(r):
    """Cuatro motores de 3 kg contra lo que pesa: 1,5 veces como poco
    (criterio del asistente; con menos no queda para corregir una ráfaga)."""
    assert 4 * r["vtol"]["empuje_max_por_motor_kg"] / r["masa_kg"]["total"] >= 1.5


def test_cada_compra_se_encuentra_en_amazon(r):
    assert r["compras"], "no hay lista de compras"
    for c in r["compras"]:
        assert c["url"].startswith("https://www.amazon.com/"), c
        assert c["cantidad"] >= 1, c


def test_ningun_tubo_de_carbono_pasa_del_metro_que_se_vende(r):
    """En Amazon los tubos de Ø16, Ø10 y Ø6 se venden de 1000 mm."""
    for nombre, largo in r["tubos_mm"].items():
        assert largo <= 1000, (nombre, largo)
