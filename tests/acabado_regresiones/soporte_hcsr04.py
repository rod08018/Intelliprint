def construir(kit):
    M5 = 5.0  # R3: tornillo M5
    T_NUT_AF = 9.5  # R4: tuerca en T 2020, entrecaras
    T_NUT_ESPESOR = 4.5  # R5: tuerca en T 2020, espesor
    RANURA_2020 = 6.0  # R6: ancho de ranura del perfil 2020
    KEY_WIDTH = 5.6
    KEY_LENGTH = 8.0
    KEY_DEPTH = 4.0
    KEY_OFFSET = 18.0
    BASE_T = 5.0
    TOWER_W = 7.5
    TOWER_Y0 = 3.0
    TOWER_Y1 = 20.0
    TOWER_TOP = 30.0
    SENSOR_PCB_W = 45.0
    SENSOR_X = -SENSOR_PCB_W / 2.0
    SENSOR_Y = 10.0
    SENSOR_Z = 7.0

    base = kit.caja(60.0, 32.0, BASE_T, en=(-30.0, -12.0, 0.0))
    left = kit.caja(TOWER_W, TOWER_Y1 - TOWER_Y0, TOWER_TOP + 0.5,
                    en=(-30.0, TOWER_Y0, -0.5))
    right = kit.caja(TOWER_W, TOWER_Y1 - TOWER_Y0, TOWER_TOP + 0.5,
                     en=(SENSOR_PCB_W / 2.0, TOWER_Y0, -0.5))
    cuerpo = base + left + right
    cuerpo = cuerpo.girar(270, eje='x', centro=(0, 0, 0)).mover(0.0, 4.0, 20.0)

    perfil = kit.componente('perfil-2020', en=(0.0, -6.0, 20.0),
                            girar=[('x', 270)], entra_por='+x')
    sensor = kit.componente('hc-sr04', en=(-22.5, 11.0, 10.0),
                            girar=[('x', 270)], entra_por='+y')
    cuerpo = cuerpo.quitar('alojamiento_perfil_2020', perfil.hueco())
    cuerpo = cuerpo.quitar('alojamiento_hc_sr04', sensor.hueco())

    key = kit.caja(KEY_LENGTH, KEY_WIDTH, KEY_DEPTH + 0.5,
                   en=(KEY_OFFSET - KEY_LENGTH / 2.0, -KEY_WIDTH / 2.0, -KEY_DEPTH))
    key = key.girar(270, eje='x', centro=(0, 0, 0)).mover(0.0, 4.0, 20.0)
    cuerpo = cuerpo + key

    rail_z0 = BASE_T - 0.5
    rail_h = TOWER_TOP - rail_z0
    x_left0 = -23.0
    x_left1 = -21.2
    x_right0 = 21.2
    x_right1 = 23.0
    y_rear0 = 4.0
    y_rear1 = 9.9
    y_front0 = 11.7
    y_front1 = 18.0

    r1 = kit.caja(x_left1 - x_left0, y_rear1 - y_rear0, rail_h,
                  en=(x_left0, y_rear0, rail_z0))
    r1 = r1.girar(270, eje='x', centro=(0, 0, 0)).mover(0.0, 4.0, 20.0)
    r2 = kit.caja(x_left1 - x_left0, y_front1 - y_front0, rail_h,
                  en=(x_left0, y_front0, rail_z0))
    r2 = r2.girar(270, eje='x', centro=(0, 0, 0)).mover(0.0, 4.0, 20.0)
    r3 = kit.caja(x_right1 - x_right0, y_rear1 - y_rear0, rail_h,
                  en=(x_right0, y_rear0, rail_z0))
    r3 = r3.girar(270, eje='x', centro=(0, 0, 0)).mover(0.0, 4.0, 20.0)
    r4 = kit.caja(x_right1 - x_right0, y_front1 - y_front0, rail_h,
                  en=(x_right0, y_front0, rail_z0))
    r4 = r4.girar(270, eje='x', centro=(0, 0, 0)).mover(0.0, 4.0, 20.0)
    cuerpo = cuerpo + r1 + r2 + r3 + r4

    ledge_h = 1.9
    l1 = kit.caja(2.0, 1.8, ledge_h, en=(-23.0, y_rear1, BASE_T))
    l1 = l1.girar(270, eje='x', centro=(0, 0, 0)).mover(0.0, 4.0, 20.0)
    l2 = kit.caja(2.0, 1.8, ledge_h, en=(21.0, y_rear1, BASE_T))
    l2 = l2.girar(270, eje='x', centro=(0, 0, 0)).mover(0.0, 4.0, 20.0)
    cuerpo = cuerpo + l1 + l2

    cuerpo = cuerpo.taladrar('tornillo_m5', 5.5, en=(0.0, 9.1, 20.0),
                             eje='-y', profundidad=BASE_T + 0.5,
                             lagrima=True)
    return cuerpo.acabar(radio=0.5)
