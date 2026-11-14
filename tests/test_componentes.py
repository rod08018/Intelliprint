"""La biblioteca de componentes (F6.11 (biblioteca)).

El soporte del HC-SR04 (2026-11-05) salió con un PCB de 43 mm y unos
transductores de Ø8 sacados de una tienda; el sensor real mide 45 y Ø16. Cada
ficha cita su fuente, y aquí se comprueba lo que el código SÍ puede ver sin
calibre: que lo simétrico sea simétrico y que las cosas estén donde caben.
Los valores esperados salen de las fuentes citadas en cada ficha, no de la
ficha misma.
"""

import pytest

from orchestrator.componentes import cargar, ids, primitivas, resumen


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


def test_la_ficha_del_sg90_dice_a_que_se_atornilla_lo_que_gira_con_su_eje():
    """F9.7 (acople). Lo que gira con un servo no se atornilla al eje: se
    atornilla a su cuerno. Estaba en las notas de la ficha, en prosa, y la
    plataforma del pan-tilt 1111-1342 se sujetó con un M3 por el centro.

    Del plano TA0233, literal: «cuernos con cubo de Ø6.9 × 2.5 y brazos de
    1.5»; el de cruz (#2) mide 20.3 de punta a punta en los dos sentidos
    —cuatro brazos— y tiene agujeros de Ø1.0 a R4.3, R6.3 y R8.3."""
    [eje] = cargar("sg90").salidas
    a = eje.acople
    assert (a.cubo_diametro, a.cubo_alto, a.grosor) == (6.9, 2.5, 1.5)
    assert (a.brazos, a.de_punta_a_punta) == (4, 20.3)
    assert [(h.radio, h.diametro) for h in a.agujeros] == [(4.3, 1.0), (6.3, 1.0), (8.3, 1.0)]
    assert "agujeros de Ø1 a 4.3, 6.3 y 8.3 mm del eje" in resumen(cargar("sg90"))
    # Un rodamiento no tiene cuerno: lo que gira con él lo abraza.
    assert cargar("608zz").salidas[0].acople is None


def test_el_kit_da_el_acople_con_la_salida_ya_colocada():
    """Quien dibuja la pieza que gira lo pide donde pide el eje."""
    servo = _kit("sg90").componente("sg90", en=(10, 20, 5))
    acople = servo.salida()["acople"]
    assert [(h["radio"], h["diametro"]) for h in acople["agujeros"]] == [
        (4.3, 1.0), (6.3, 1.0), (8.3, 1.0)]
    assert (acople["cubo_diametro"], acople["brazos"]) == (6.9, 4)
    assert _kit("608zz").componente("608zz", en=(0, 0, 0)).salida()["acople"] is None


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


def test_el_resumen_dice_sobre_que_eje_gira_y_que_tornillo_lleva_cada_agujero():
    """F9.4 (canal). El ingeniero del soporte del pan-tilt (1110-0313)
    descartó las orejas del SG90 «porque el perfil no tiene agujeros M2» y lo
    sujetó con dos M3 que lo empujan: el resumen daba «Ø2.2» y callaba que
    ese tornillo viene con el servo. Tampoco decía dónde sale el eje. Las
    cifras son las de `sg90.yaml`."""
    from orchestrator.componentes import resumen
    texto = resumen(cargar("sg90"))
    assert "eje: sale en (5.8, 6.2, 27.1) hacia +z y gira de -90° a 90°" in texto
    assert "tornillo M2, viene con el componente, entra 2.9 mm" in texto
    assert "Tuerca en T M5" in resumen(cargar("perfil-2020"))
    # El aro de un rodamiento ocupa un tramo del eje: lo que gira va en él.
    assert "a lo largo de 7 mm" in resumen(cargar("608zz"))


def test_el_kit_dice_donde_queda_el_eje_de_un_componente_colocado():
    """Lo que gira se acopla al eje, y el programa necesita saber dónde cae
    en la pieza, igual que `punto()` le dice dónde cae un agujero. El SG90
    tumbado del soporte del pan-tilt: (13.55, -5.6, 12.2) hacia +x, la
    cuenta a mano de `tests/test_fichar.py`."""
    from mech_toolkit.kit import Kit, KitError
    kit = Kit(fichas={"sg90": cargar("sg90").model_dump()})
    servo = kit.componente("sg90", en=(-13.55, -11.4, 6.0), girar=[("x", 90), ("z", 90)])
    s = servo.salida()
    assert s["nombre"] == "eje"
    assert s["punto"] == pytest.approx((13.55, -5.6, 12.2)) and s["eje"] == (1, 0, 0)
    assert s["recorrido"] == (-90, 90)
    assert servo.salida("eje") == s
    with pytest.raises(KitError, match="«eje»"):
        servo.salida("cuerno")


def test_el_kit_no_coloca_lo_que_ya_monta_otra_pieza_del_backlog():
    """Banco 1109-1949: la plataforma del pan-tilt colocó el SG90 que ya
    montaba el soporte de giro, y quedaron tres servos en un pan-tilt de dos."""
    from mech_toolkit.kit import Kit, KitError
    kit = Kit(fichas={"sg90": cargar("sg90").model_dump()},
              ajenos={"sg90": {"cuantos": 1, "mensaje": "el sg90 lo monta «Base»"}})
    kit.componente("sg90", nombre="propio")
    with pytest.raises(KitError, match="lo monta «Base»"):
        kit.componente("sg90", nombre="otro")


def test_el_programa_se_construye_con_lo_que_monta_otra_pieza(monkeypatch):
    from types import SimpleNamespace

    from orchestrator.recipes.compose import compose_program_script
    monkeypatch.setenv("INTELLIPRINT_AJENOS",
                       '{"sg90": {"cuantos": 0, "mensaje": "lo monta otra"}}')
    script = compose_program_script(SimpleNamespace(part="p", codigo="x"))
    assert "lo monta otra" in script and "ajenos=" in script


# --- par, velocidad y masa (F4.12 (par)) ---------------------------------------------------


def test_ningun_servo_sin_par_ni_velocidad():
    """El estudio de movimientos (F7.10 (estudio)) dice si un servo aguanta
    con su par: una ficha de servo sin él no se puede estudiar."""
    for i in ids():
        f = cargar(i)
        if "servo" in f.nombre.lower():
            assert f.par_kgf_cm and f.velocidad_s_60, i
            assert set(f.par_kgf_cm) == set(f.velocidad_s_60), i


def test_el_par_del_sg90_en_newton_metro():
    """Hoja de TowerPro: «Stall torque: 1.8 kgf·cm» a 4.8 V.
    1.8 × 9.80665 / 100 = 0.17652 N·m."""
    sg90 = cargar("sg90")
    assert sg90.par_Nm(4.8) == pytest.approx(0.17652, abs=1e-5)
    assert sg90.velocidad(4.8) == 0.1
    assert sg90.masa_g == 9


def test_el_mg996r_a_cada_tension_y_la_que_no_dice_su_hoja():
    """9.4 kgf·cm y 0.17 s/60° a 4.8 V; 11 y 0.14 a 6 V. A 5 V, que su
    hoja no da, se toma la tensión de la hoja más baja que no la pase: 4.8,
    del lado seguro."""
    mg = cargar("mg996r")
    assert mg.par_Nm(6) == pytest.approx(11 * 9.80665 / 100)
    assert mg.par_Nm(5) == pytest.approx(9.4 * 9.80665 / 100)
    assert mg.velocidad(5) == 0.17


def test_las_masas_que_dan_sus_fuentes():
    assert cargar("608zz").masa_g == 13
    assert cargar("nema17").masa_g == 275
    assert cargar("hc-sr04").masa_g == 8.5


# --- F12.1 (fichas): el NEMA 23 -----------------------------------------------------------
# La hoja del fabricante del SY57STH56-2804A (Changzhou Songyang), descargada
# de https://www.pololu.com/file/0J674/SY57STH56-2804A.pdf el 2026-11-14.

def test_nema23_como_su_plano():
    """El plano: 56.4 ± 1 de lado, 56 ± 1 de largo con una brida de 5, cuatro
    agujeros de Ø5 a 47.1 ± 0.2 entre centros, resalte de Ø38.1 × 1.6 y eje
    de Ø6.35 que sale 21 ± 1."""
    brida, cuerpo = _cuerpo("nema23", "brida"), _cuerpo("nema23", "cuerpo")
    assert brida.caja == [56.4, 56.4, 5]
    # Brida y cuerpo, uno detrás de otro, suman los 56 del plano.
    assert brida.caja[2] + cuerpo.caja[2] == 56 and cuerpo.en[2] == -56
    resalte = _cuerpo("nema23", "resalte").cilindro
    assert (resalte.diametro, resalte.alto) == (38.1, 1.6)
    eje = _cuerpo("nema23", "eje").cilindro
    assert (eje.diametro, eje.alto) == (6.35, 21)
    f = cargar("nema23").fijacion
    assert len(f) == 4 and all(a.diametro == 5 for a in f)
    xs, ys = sorted({a.en[0] for a in f}), sorted({a.en[1] for a in f})
    assert xs[1] - xs[0] == pytest.approx(47.1) and ys[1] - ys[0] == pytest.approx(47.1)
    assert sum(xs) == pytest.approx(0) and cuerpo.en[0] + cuerpo.caja[0] / 2 == pytest.approx(0)


def test_los_tornillos_del_nema23_cruzan_la_brida_y_llevan_tuerca():
    """Sus agujeros son pasantes, no roscados como los del NEMA 17: el
    tornillo cruza los 5 mm de la brida y agarra en una tuerca. Por un Ø5 va
    un M4 con holgura; un M5 no."""
    for a in cargar("nema23").fijacion:
        assert (a.tornillo, a.dentro_mm, a.tuerca) == ("M4", 5, "tuerca M4")
        assert not a.rosca_en_la_pieza


def test_el_nema23_da_su_par_su_masa_y_tiene_eje():
    """La hoja: «Holding Torque (N.cm) 126», 1,26 N·m. El vendedor: 0,7 kg.
    El eje sale del centro de la cara de montaje y da vueltas enteras."""
    f = cargar("nema23")
    assert f.par_motor_Nm() == pytest.approx(1.26) and f.masa_g == 700
    [eje] = f.salidas
    assert (eje.en, eje.eje, eje.recorrido, eje.largo) == ([0, 0, 0], "+z", (0, 360), 21)


def test_una_peticion_que_nombra_un_nema_23_no_recibe_el_17():
    from orchestrator.componentes import mencionados
    assert mencionados("Una base para un motor NEMA 23 con su polea") == ["nema23"]
    assert mencionados("Escuadra para un motor NEMA 17") == ["nema17"]


# --- F12.1 (fichas): los NEMA 23 con reductora planetaria comprada -------------------------
# Decidido por el usuario el 2026-11-14: las reductoras del hombro y del codo
# del brazo de 2 kg se compran («Ambas compradas»). Los planos del
# 23HS22-2804S-PG47 y del 23HS30-2804S-PG47, leídos ese día en
# https://www.oyostepper.com/images/upload/File/23HS22-2804S-PG47.pdf y
# .../23HS30-2804S-PG47.pdf.

MOTORREDUCTORES = {"nema23-pg47-56": (56, 1.25, 1600), "nema23-pg47-76": (76, 1.89, 2000)}


@pytest.mark.parametrize("id_", MOTORREDUCTORES)
def test_el_motorreductor_como_su_plano(id_):
    """El plano: reductora de Ø56 × 72 REF, motor de 57 REF de lado y 56 o 76
    de largo detrás, resalte de Ø32 × 2, eje de Ø12 que sale 30 ± 1 y cuatro
    M5 en un círculo de Ø45 ± 0.15."""
    largo, _, _ = MOTORREDUCTORES[id_]
    reductora = _cuerpo(id_, "reductora")
    assert (reductora.cilindro.diametro, reductora.cilindro.alto) == (56, 72)
    assert reductora.en == [0, 0, -72]
    motor = _cuerpo(id_, "motor")
    # El motor empieza donde acaba la reductora, centrado en el eje.
    assert motor.caja[2] == largo and motor.en[2] == -72 - largo
    assert motor.en[0] + motor.caja[0] / 2 == pytest.approx(0)
    resalte, eje = _cuerpo(id_, "resalte").cilindro, _cuerpo(id_, "eje").cilindro
    assert (resalte.diametro, resalte.alto) == (32, 2)
    assert (eje.diametro, eje.alto) == (12, 30)
    f = cargar(id_).fijacion
    assert len(f) == 4 and all(a.tornillo == "M5" and not a.tuerca for a in f)
    for a in f:
        assert (a.en[0] ** 2 + a.en[1] ** 2) ** 0.5 == pytest.approx(22.5, abs=0.01)
    assert sum(a.en[0] for a in f) == pytest.approx(0) and sum(a.en[1] for a in f) == pytest.approx(0)
    [salida] = cargar(id_).salidas
    assert (salida.en, salida.eje, salida.recorrido, salida.largo) == ([0, 0, 0], "+z", (0, 360), 30)


@pytest.mark.parametrize("id_", MOTORREDUCTORES)
def test_un_motorreductor_da_el_par_en_su_salida(id_):
    """La hoja da el par del motor SIN la reductora («HOLDING TORQUE w/o
    GEARBOX»), la relación («46 82/125», 46,656) y el rendimiento («73.00%»).
    En el eje de salida, que es sobre el que gira la pieza, a mano:
    1,25 × 46,656 × 0,73 = 42,574 N·m; 1,89 × 46,656 × 0,73 = 64,371 N·m."""
    _, par, masa = MOTORREDUCTORES[id_]
    f = cargar(id_)
    assert f.reduccion == pytest.approx(46 + 82 / 125) and f.rendimiento == 0.73
    assert f.par_motor_Nm() == pytest.approx(par * 46.656 * 0.73)
    assert f.par_motor_Nm() == pytest.approx({1.25: 42.574, 1.89: 64.371}[par], abs=1e-3)
    assert f.da_par() and f.masa_g == masa


def test_un_motor_suelto_sigue_dando_el_par_de_su_hoja():
    """El NEMA 17 y el NEMA 23 no llevan reductora: su par es el de la hoja,
    y la relación la pone la transmisión del plan."""
    assert cargar("nema17").par_motor_Nm() == pytest.approx(0.400)
    assert cargar("nema23").par_motor_Nm() == pytest.approx(1.26)


def test_una_reductora_impresa_no_da_par_aunque_reduzca():
    """La cicloidal tiene `reduccion` y ningún motor dentro: no mueve nada
    sola, y el plan tiene que seguir pidiéndole su `movido_por`."""
    from orchestrator import modulos
    ficha = modulos.cargar("cicloidal-nema17-28").ficha
    assert ficha["reduccion"] == 28 and not ficha.get("par_retencion_mNm")


@pytest.mark.parametrize("id_", MOTORREDUCTORES)
def test_el_motorreductor_dice_donde_se_compra(id_):
    """«En los BOM agrega el link de compra de la reductora» (el usuario,
    2026-11-14). La página de la tienda donde se leyeron el precio y la hoja,
    con el número de parte del fabricante en la ficha para poder buscarlo en
    otra."""
    f = cargar(id_)
    assert f.compra_url.startswith("https://www.oyostepper.com/goods-")
    parte = {"nema23-pg47-56": "23HS22-2804S-PG47", "nema23-pg47-76": "23HS30-2804S-PG47"}[id_]
    assert parte in f.nombre and parte in f.alias


def test_el_enlace_de_compra_es_una_direccion_web():
    """Se pinta como enlace en la web: nada que no sea http(s)."""
    from pydantic import ValidationError

    from orchestrator.componentes import Ficha
    datos = cargar("608zz").model_dump()
    assert Ficha(**{**datos, "compra_url": "https://tienda.example/608"}).compra_url
    with pytest.raises(ValidationError):
        Ficha(**{**datos, "compra_url": "javascript:alert(1)"})


# --- F12.1 (fichas): los rodamientos grandes del brazo de 2 kg -----------------------------
# Las páginas de SKF 61806-2RS1 y 61810-2RS1 en coolenbearings.com, leídas el
# 2026-11-14: (d, D, B, masa en g, lo más que sube el apoyo del eje, D2).

RODAMIENTOS = {"6806-2rs": (30, 42, 7, 22, 32.5, 39.4), "6810-2rs": (50, 65, 7, 47.2, 55.0, 61.55)}


@pytest.mark.parametrize("id_", RODAMIENTOS)
def test_un_rodamiento_grande_es_un_anillo_con_las_cotas_de_su_hoja(id_):
    d, D, B, masa, _, _ = RODAMIENTOS[id_]
    r = _cuerpo(id_, "rodamiento").cilindro
    assert (r.interior, r.diametro, r.alto) == (d, D, B)
    f = cargar(id_)
    assert f.masa_g == masa and not f.da_par()
    [aro] = f.salidas
    assert (aro.nombre, aro.eje, aro.recorrido, aro.largo) == ("aro interior", "+z", (0, 360), B)


@pytest.mark.parametrize("id_", RODAMIENTOS)
def test_en_un_rodamiento_grande_se_apoya_en_un_solo_aro(id_):
    """Como en el 608ZZ: lo que toque la cara de un aro gira con él, y una
    pieza no puede apoyar en los dos. La zona del aro interior llega al
    menos hasta donde la hoja deja subir el apoyo del eje (da max), y la del
    exterior empieza como muy tarde en su rebaje (D2); entre las dos queda
    el sello, que no es de ninguno."""
    d, D, B, _, da_max, D2 = RODAMIENTOS[id_]
    zonas = cargar(id_).despejar
    interior = [z for z in zonas if z.gira_con == "aro interior"]
    exterior = [z for z in zonas if z.gira_con == "aro exterior"]
    assert len(interior) == len(exterior) == 2 and len(zonas) == 4
    for z in interior:
        assert z.cilindro.interior == d and da_max <= z.cilindro.diametro < D2
    for z in exterior:
        assert z.cilindro.diametro == D and da_max < z.cilindro.interior <= D2
    assert max(z.cilindro.diametro for z in interior) < min(z.cilindro.interior for z in exterior)
    # Una cara a cada lado del rodamiento.
    assert sorted(z.en[2] for z in interior) == sorted(z.en[2] for z in exterior) == [-0.5, B]


def test_cada_rodamiento_se_reconoce_por_su_nombre_y_no_por_el_de_otro():
    from orchestrator.componentes import mencionados
    assert mencionados("El hombro apoya en un rodamiento 6806-2RS") == ["6806-2rs"]
    assert mencionados("La base gira sobre dos SKF 61810-2RS1") == ["6810-2rs"]
    assert mencionados("Una polea para un rodamiento 608ZZ") == ["608zz"]


def test_una_peticion_que_nombra_el_motorreductor_por_su_numero_de_parte():
    from orchestrator.componentes import mencionados
    assert mencionados("El hombro, sobre un 23HS30-2804S-PG47") == ["nema23-pg47-76"]
    # Y quien pide un NEMA 23 a secas no recibe uno con reductora.
    assert mencionados("Una base para un motor NEMA 23") == ["nema23"]
