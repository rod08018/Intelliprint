"""El ala volante se dimensiona con lo que él compra en Amazon.

Él, el 2026-11-16: «usemos motores y bateria que pueda comprar en amazon». Y
el 2026-11-18, al ver 7 kg, pidió la lista de compras sección a sección, con
pesos de Amazon y que llegue a Guatemala, y la aprobó: «porque no una bateria
de 10Ah 6s?», «Usa 600kv y helices mas grandes» y «Con el de 660KV». La meta,
«vuelo de casi 1 hora».

Lo esperado viene de los anuncios (el peso de la batería, el empuje de la
hélice de 15″ en la tabla de banco de MAD) y de lo que él pidió, no del
dimensionado.
"""

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def r():
    return json.loads((RAIZ / "scripts" / "avion_vtol.json").read_text(encoding="utf-8"))


def test_la_bateria_es_una_lipo_6s_de_10000_mah(r):
    """22,2 V × 10 Ah = 222 Wh; pesa 1 248 g según la descripción de su
    anuncio (la ficha dice «50 g», imposible)."""
    assert r["bateria"]["serie"] == 6
    assert r["bateria"]["mAh"] == 10000
    assert r["bateria"]["Wh"] == pytest.approx(222.0, abs=0.1)
    assert r["masa_kg"]["batería LiPo 6S 10 000 mAh"] == pytest.approx(1.248, abs=0.001)


def test_vuela_casi_una_hora(r):
    """«vuelo de casi 1 hora»: 48 minutos como poco (criterio del asistente
    para «casi»)."""
    assert r["autonomia_h"] >= 0.8


def test_los_motores_de_subir_son_de_660kv_con_helice_de_15(r):
    """«Con el de 660KV», con la hélice de 15″ de la lista. Limitado al 65 %
    gira la hélice como el MAD 5005 de 440 KV a fondo: 3 024 g en la tabla
    de banco de MAD, al nivel del mar."""
    assert r["rotores"]["helice_vtol_pulg"] == 15
    assert r["vtol"]["empuje_max_por_motor_kg"] == pytest.approx(3.0)
    assert any("660KV" in c["que"] for c in r["compras"])


def test_los_cuatro_rotores_levantan_el_avion_con_margen_a_1500_m(r):
    """Cuatro hélices de 3 kg al nivel del mar empujan a 1 500 m lo que pesa
    allí el aire, 1,058 de 1,225 kg/m³ (atmósfera estándar): 1,5 veces el
    peso como poco (criterio del asistente; con menos no queda para corregir
    una ráfaga)."""
    assert 4 * r["vtol"]["empuje_max_por_motor_kg"] * 1.058 / 1.225 / r["masa_kg"]["total"] >= 1.5


def test_cada_compra_se_encuentra_en_amazon(r):
    assert r["compras"], "no hay lista de compras"
    for c in r["compras"]:
        assert c["url"].startswith("https://www.amazon.com/"), c
        assert c["cantidad"] >= 1, c


def test_ningun_tubo_de_carbono_pasa_del_metro_que_se_vende(r):
    """En Amazon los tubos de Ø16, Ø10 y Ø6 se venden de 1000 mm."""
    for nombre, largo in r["tubos_mm"].items():
        assert largo <= 1000, (nombre, largo)


def test_la_varilla_de_o2_alcanza_para_las_guias(r):
    """La varilla maciza de Ø2 se vende de 500 mm. Con la cama grande cada
    elevón es una pieza y ya no lleva varilla: solo las guías del cuerpo
    central (él: «Sí, añádelas», 2026-11-16), un trozo de 18 mm en cada una,
    tres o cuatro por corte."""
    compra = next(c for c in r["compras"] if "Ø2" in c["que"])
    largo = r["tubos_mm"]["varilla Ø2"]
    assert largo % 18 == pytest.approx(0, abs=0.01) and largo >= 3 * 18, largo
    assert largo <= compra["cantidad"] * 500, (largo, compra)
