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


# --- las demás fichas, contra los planos que citan -----------------------------------------

def _cuerpo(id_, nombre):
    return next(c for c in cargar(id_).cuerpos if c.nombre == nombre)


def _envolvente(id_):
    ps = primitivas(cargar(id_))
    return ([min(p["min"][n] for p in ps if p["tipo"] == "caja") for n in range(3)],
            [max(p["max"][n] for p in ps if p["tipo"] == "caja") for n in range(3)])


def _dentro(punto, id_, de="cuerpos"):
    return [p["nombre"] for p in primitivas(cargar(id_), de=de) if p["tipo"] == "caja"
            and all(p["min"][n] < punto[n] < p["max"][n] for n in range(3))]


def test_raspberry_pi_4_como_su_plano_mecanico():
    """Plano de Raspberry Pi: placa de 85 × 56, agujeros de Ø2.7 a 3.5 del
    canto y a 58 × 49 entre centros, GPIO centrado a 29 + 3.5 del borde,
    alturas Z=8.5 (GPIO), 13.5 (red) y 16.0 (USB)."""
    placa = _cuerpo("raspberry-pi-4", "placa")
    assert placa.caja[:2] == [85, 56]
    f = cargar("raspberry-pi-4").fijacion
    assert {a.diametro for a in f} == {2.7}
    xs, ys = sorted({a.en[0] for a in f}), sorted({a.en[1] for a in f})
    assert xs == [3.5, 61.5] and ys == [3.5, 52.5]
    gpio = _cuerpo("raspberry-pi-4", "conector GPIO")
    assert gpio.en[0] + gpio.caja[0] / 2 == pytest.approx(32.5)
    arriba = placa.caja[2]
    assert gpio.caja[2] == 8.5 and gpio.en[2] == arriba
    assert _cuerpo("raspberry-pi-4", "conector de red").caja[2] == 13.5
    assert {c.caja[2] for c in cargar("raspberry-pi-4").cuerpos if c.nombre.startswith("USB ")} == {16}


def test_los_agujeros_de_la_pi_quedan_libres_por_debajo():
    """Se apoya en separadores en sus cuatro agujeros: lo que se deja libre
    por debajo (soldaduras, la SD) no puede tapar justo esos sitios."""
    for a in cargar("raspberry-pi-4").fijacion:
        assert not _dentro([a.en[0], a.en[1], -1], "raspberry-pi-4", de="despejar"), a.nombre
        assert _dentro([a.en[0], a.en[1], 0.7], "raspberry-pi-4") == ["placa"], a.nombre


def test_sg90_cubre_los_dos_planos():
    """TowerPro: 22.2 × 11.8, orejas de 32.2, a 16 del fondo. Luxorparts:
    22.8 × 12.4, orejas de 32.0, a 15.6. Las unidades varían de un fabricante
    a otro: la ficha toma lo mayor, para que quepa cualquiera de las dos."""
    cuerpo, orejas = _cuerpo("sg90", "cuerpo"), _cuerpo("sg90", "orejas")
    assert cuerpo.caja[:2] == [22.8, 12.4]
    assert orejas.caja[0] == 32.2
    assert orejas.en[0] + orejas.caja[0] / 2 == pytest.approx(cuerpo.caja[0] / 2)
    assert orejas.en[2] <= 15.6 and orejas.en[2] + orejas.caja[2] >= 16


def test_sg90_con_el_eje_y_las_orejas_del_plano_ta0233():
    """Plano de AusElectronicsDirect (TA0233): cuerpo de 22.7, orejas de
    4.85 con la muesca R1.1 a 1.9 de la punta (2.95 del cuerpo), eje a 8.75
    de esa muesca (5.8 del extremo del cuerpo), centrado en el ancho; la
    carcasa llega a 27.1 y el eje a 30.7; el cubo del cuerno es de Ø6.9.
    La base del pan-tilt (2026-11-09) puso los agujeros guía en el centro de
    la oreja, a 2.35 del cuerpo: la muesca se abre hacia la punta, y un
    tornillo 0.6 más adentro choca con su fondo."""
    cuerpo = _cuerpo("sg90", "cuerpo")
    f = cargar("sg90").fijacion
    assert sorted(a.en[0] for a in f) == pytest.approx([-2.95, cuerpo.caja[0] + 2.95])
    assert {a.diametro for a in f} == {2.2}
    assert all(a.en[1] == pytest.approx(cuerpo.caja[1] / 2) for a in f)
    cubo = next(c for c in cargar("sg90").despejar if c.cilindro)
    assert cubo.en[:2] == pytest.approx([5.8, cuerpo.caja[1] / 2])
    assert cubo.cilindro.diametro == 6.9 and cubo.cilindro.eje == "+z"
    assert cubo.en[2] == 27.1 and cubo.en[2] + cubo.cilindro.alto == pytest.approx(30.7)
    assert cuerpo.caja[2] >= 27.1


def test_mg996r_como_su_plano():
    """TowerPro: orejas de 53.6, a 26.6 del fondo, 36.6 de cuerpo y 20 de ancho."""
    cuerpo, orejas = _cuerpo("mg996r", "cuerpo"), _cuerpo("mg996r", "orejas")
    assert cuerpo.caja[1:] == [20, 36.6] and orejas.caja[0] == 53.6
    assert orejas.en[2] == 26.6
    assert orejas.en[0] + orejas.caja[0] / 2 == pytest.approx(cuerpo.caja[0] / 2)


def test_nema17_como_su_plano():
    """42HD4027-01: 42.3 de lado, 39.5 de largo, 4 × M3 a 31 entre centros,
    resalte de Ø22 × 2 y eje de Ø5."""
    cuerpo = _cuerpo("nema17", "cuerpo")
    assert cuerpo.caja == [42.3, 42.3, 39.5]
    assert _cuerpo("nema17", "resalte").cilindro.diametro == 22
    assert _cuerpo("nema17", "eje").cilindro.diametro == 5
    f = cargar("nema17").fijacion
    xs, ys = sorted({a.en[0] for a in f}), sorted({a.en[1] for a in f})
    assert xs[1] - xs[0] == pytest.approx(31) and ys[1] - ys[0] == pytest.approx(31)
    # El eje y los agujeros, centrados en el cuadrado.
    assert sum(xs) == pytest.approx(0) and cuerpo.en[0] + cuerpo.caja[0] / 2 == pytest.approx(0)


def test_perfil_2020_deja_libres_sus_ranuras():
    """MISUMI HFS5-2020: 20 × 20, ranura de 6 de boca y 6 de fondo (2 de
    labio + 4 de cámara; núcleo de 8). Una lengüeta de la pieza puede entrar
    en la ranura; el resto del perfil es macizo."""
    a, b = _envolvente("perfil-2020")
    assert [b[1] - a[1], b[2] - a[2]] == [20, 20]
    for punto in ([0, 0, 9], [0, 2.9, 5], [0, 0, -9], [0, 9, 0], [0, -5, 0]):
        assert not _dentro(punto, "perfil-2020"), punto
    for punto in ([0, 3.1, 9], [0, 0, 3.9], [0, 9, 9]):
        assert _dentro(punto, "perfil-2020"), punto


def test_608_es_un_anillo():
    r = _cuerpo("608zz", "rodamiento").cilindro
    assert (r.diametro, r.interior, r.alto) == (22, 8, 7)


# --- el kit coloca componentes (F6.11 (biblioteca)) ----------------------------------------

def _kit(*ids_):
    from mech_toolkit.kit import Kit
    return Kit(fichas={i: cargar(i).model_dump() for i in ids_})


def test_el_kit_coloca_el_componente_con_su_ficha_y_lo_registra():
    """El programa solo dice dónde va y por dónde entra; la forma y los
    agujeros salen de la ficha (plano de Raspberry Pi: agujeros a 3.5 del
    canto; los conectores asoman 2.5 por la derecha y el audio por abajo)."""
    kit = _kit("raspberry-pi-4")
    pi = kit.componente("raspberry-pi-4", en=(10, 20, 5))
    assert pi.punto("agujero abajo izquierda") == pytest.approx((13.5, 23.5, 5))
    assert len(pi.agujeros()) == 4 and {a["diametro"] for a in pi.agujeros()} == {2.7}
    minimo, maximo = pi.envolvente()
    assert minimo[1] == pytest.approx(17.5) and maximo[0] == pytest.approx(97.5)
    assert kit.rasgos() == [{"nombre": "raspberry-pi-4", "tipo": "componente",
                             "ficha": "raspberry-pi-4", "en": [10, 20, 5], "giros": [],
                             "entra_por": "+z"}]


def test_girado_un_cuarto_de_vuelta_sus_agujeros_giran_con_el():
    sensor = _kit("hc-sr04").componente("hc-sr04", girar=[("z", 90)], entra_por="-x")
    assert sensor.punto("agujero abajo derecha") == pytest.approx((0, 42.5, 2.5))


def test_un_componente_que_no_esta_en_la_biblioteca_dice_cuales_hay():
    from mech_toolkit.kit import KitError
    with pytest.raises(KitError, match="hc-sr04"):
        _kit("hc-sr04").componente("hc-sr05")
    with pytest.raises(KitError, match="90"):
        _kit("hc-sr04").componente("hc-sr04", girar=[("z", 45)])
    with pytest.raises(KitError, match="entra_por"):
        _kit("hc-sr04").componente("hc-sr04", entra_por="arriba")


# --- el ingeniero y el diseñador piensan con la ficha (F6.11 (biblioteca)) -------------

def test_se_reconocen_los_componentes_que_nombra_una_peticion():
    from orchestrator.componentes import mencionados
    assert mencionados("Soporte para un sensor ultrasónico HC-SR04 en un perfil de "
                       "aluminio 2020") == ["hc-sr04", "perfil-2020"]
    assert mencionados("Caja para una Raspberry Pi 4 y un servo SG90") == [
        "raspberry-pi-4", "sg90"]
    assert mencionados("Escuadra para un motor NEMA 17 y un rodamiento 608ZZ") == [
        "608zz", "nema17"]
    assert mencionados("Un gancho para colgar la mochila de 2 kg") == []


def test_el_resumen_dice_el_tamano_lo_que_hay_que_dejar_libre_y_que_no_esta_medido():
    """La envolvente del HC-SR04, a mano: x de 0 a 45 (placa); y de -3
    (integrados) a 15 (punta de los transductores, 1.6 + 13.4); z de -6
    (pines) a 24.5 (cristal, 16 + 8.5)."""
    from orchestrator.componentes import resumen
    r = resumen(cargar("hc-sr04"))
    assert "45 × 18 × 30.5 mm" in r
    assert "integrados de atrás" in r and "conector y cable" in r
    assert "sin verificar con calibre" in r and "handsontec.com" in r


def test_la_tuerca_en_t_es_del_perfil_y_no_algo_que_buscar():
    """Proyecto del 608ZZ (2026-11-06): el investigador buscó la «tuerca en T
    de 2020 para M5» en una tienda y sus 9.5, 4.5 y 6 mm acabaron de
    requisitos de la pieza. La tuerca va dentro de la ranura del perfil; a
    la pieza solo le toca el agujero del tornillo."""
    from orchestrator.componentes import de_la_ficha
    assert de_la_ficha("Tuerca en T de 2020 para M5") == ["perfil-2020"]
    assert de_la_ficha("T-nut M5 for 2020 extrusion") == ["perfil-2020"]
    assert de_la_ficha("rodamiento 608ZZ") == ["608zz"]
    assert de_la_ficha("tornillo M5 de 10 mm") == []


def test_el_resumen_del_608_dice_que_se_apoya_en_un_solo_aro():
    """El ingeniero y el diseñador leen la ficha por su resumen: si no dice
    que uno de los aros gira, dibujan un reborde que toca los dos (proyecto
    del 608ZZ, 2026-11-08)."""
    from orchestrator.componentes import resumen
    texto = resumen(cargar("608zz"))
    assert "aro interior" in texto and "aro exterior" in texto
    assert "uno solo" in texto
