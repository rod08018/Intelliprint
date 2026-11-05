"""La biblioteca de componentes (F6.11 (biblioteca)).

El soporte del HC-SR04 (2026-11-05) salió con un PCB de 43 mm y unos
transductores de Ø8 sacados de una tienda; el sensor real mide 45 y Ø16. Cada
ficha cita su fuente, y aquí se comprueba lo que el código SÍ puede ver sin
calibre: que lo simétrico sea simétrico y que las cosas estén donde caben.
Los valores esperados salen de las fuentes citadas en cada ficha, no de la
ficha misma.
"""

import pytest

from orchestrator.componentes import cargar, ids, primitivas


def test_cada_ficha_carga_y_cita_su_fuente():
    assert "hc-sr04" in ids()
    for i in ids():
        f = cargar(i)
        assert f.fuentes and all(x.url.startswith("http") and x.cita for x in f.fuentes), i
        assert f.cuerpos, i


def test_hcsr04_como_dicen_sus_fuentes():
    """Handson: «45mm x 20mm x 15mm». UPV: transductores de radio 8 en x=9.5 y
    x=35.5, a z=10. Los agujeros, a 40 x 15 entre centros."""
    f = cargar("hc-sr04")
    placa = next(c for c in f.cuerpos if c.nombre == "placa")
    assert placa.caja[0] == 45 and placa.caja[2] == 20
    t = [c for c in f.cuerpos if c.nombre.startswith("transductor")]
    assert [c.cilindro.diametro for c in t] == [16, 16]
    # Simétricos en el PCB: con 43 mm de PCB (la tienda) no lo serían.
    assert t[0].en[0] + t[1].en[0] == pytest.approx(placa.caja[0])
    # 15 mm de alto total, de la cara trasera del PCB a la punta del transductor.
    assert placa.caja[1] + t[0].cilindro.alto == pytest.approx(15)
    xs = sorted({a.en[0] for a in f.fijacion})
    zs = sorted({a.en[2] for a in f.fijacion})
    assert xs[1] - xs[0] == pytest.approx(40) and zs[1] - zs[0] == pytest.approx(15)


def test_los_agujeros_caen_dentro_del_pcb_y_fuera_de_lo_que_lleva_encima():
    f = cargar("hc-sr04")
    placa = next(c for c in f.cuerpos if c.nombre == "placa")
    for a in f.fijacion:
        assert 0 < a.en[0] < placa.caja[0] and 0 < a.en[2] < placa.caja[2], a.nombre
        for c in f.cuerpos:
            if c.cilindro:
                d = ((a.en[0] - c.en[0]) ** 2 + (a.en[2] - c.en[2]) ** 2) ** 0.5
                assert d > c.cilindro.diametro / 2 + a.diametro / 2, (a.nombre, c.nombre)


def test_colocar_y_girar_un_cuarto_de_vuelta():
    """Girado 90° alrededor de z, lo que miraba a +y mira a -x; y movido a
    (100, 0, 0), la placa va de x=100-1.6 a x=100."""
    caja = next(p for p in primitivas(cargar("hc-sr04"), en=(100, 0, 0), giros=[["z", 90]])
                if p["nombre"] == "placa")
    assert caja["min"][0] == pytest.approx(98.4) and caja["max"][0] == pytest.approx(100)
    assert caja["min"][1] == pytest.approx(0) and caja["max"][1] == pytest.approx(45)
    t = next(p for p in primitivas(cargar("hc-sr04"), giros=[["z", 90]])
             if p["nombre"] == "transductor izquierdo")
    assert t["eje"] == pytest.approx([-1, 0, 0])


def test_solo_cuartos_de_vuelta():
    with pytest.raises(ValueError, match="90"):
        primitivas(cargar("hc-sr04"), giros=[["z", 45]])
