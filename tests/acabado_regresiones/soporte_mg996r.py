SERVO_LARGO = 40.7  # R1: cuerpo del servo mide 40.7 mm
SERVO_ANCHO = 19.7  # R1: cuerpo del servo mide 19.7 mm
M3_HOLE = 3.3  # R2: agujeros M3 de 3.3 mm
M3_PASO_X = 49.5  # R2: centros a 49.5 mm
M3_PASO_Y = 10.0  # R2: centros a 10 mm
M3_CANT = 4  # R2/R3: 4 tornillos M3
M5_HOLE = 5.5  # R4: agujeros M5 de 5.5 mm
M5_PASO = 20.0  # R4: agujeros separados 20 mm
M5_CANT = 2  # R4/R5: 2 tornillos M5
M3_METRICA = 3  # R3: tornillo M3
M5_METRICA = 5  # R5: tornillo M5
T_NUT_ANCHO = 9.5  # R6: ancho tuerca en T M5
T_NUT_ALTO = 4.5  # R7: alto tuerca en T M5
RANURA_2020 = 6.0  # R8: ranura perfil 2020
CANTO = 6.0  # sección mínima del concepto: 30 x 6 mm
ANCHO_CUELLO = 30.0  # sección mínima del concepto: 30 mm
PROFILE_Y = -30.0  # separación para que el servo cuelgue al costado del perfil
VENTANA_X = 41.4  # concepto: ventana central 41.4 mm
VENTANA_Y = 20.7  # concepto: ventana central 20.7 mm
VENTANA_R = 3.0  # concepto: esquinas redondeadas de la ventana
T = CANTO

def construir(kit):
    base = kit.caja(50, 24, T, en=(-25, -40, 0))
    cuello = kit.caja(ANCHO_CUELLO, 10, T, en=(-ANCHO_CUELLO/2, -20, 0))
    marco = kit.caja(58, 27, T, en=(-29, -13.5, 0))
    pieza = base + cuello + marco
    rib = kit.caja(6, 21.5, 12.5, en=(-3, -32, T-0.5))
    pieza = pieza + rib
    a = VENTANA_X/2
    b = VENTANA_Y/2
    r = VENTANA_R
    puntos = []
    arcos = [
        (a-r, -b+r, -90, 0),
        (a-r,  b-r,   0, 90),
        (-a+r, b-r,  90, 180),
        (-a+r, -b+r, 180, 270),
    ]
    N = 6
    for cx, cy, ang0, ang1 in arcos:
        for i in range(N+1):
            ang = radians(ang0 + (ang1-ang0)*i/N)
            puntos.append((cx + r*cos(ang), cy + r*sin(ang)))
    ventana = kit.extruir(puntos, T+2, plano='xy', desde=-1)
    pieza = pieza.quitar('ventana_servo', ventana)
    servo_z = T - 26.6
    servo = kit.componente('mg996r', en=(-SERVO_LARGO/2, -10.0, servo_z), girar=(), entra_por='+z')
    pieza = pieza.quitar('alojamiento_servo', servo.hueco(holgura='clearance'))
    perfil = kit.componente('perfil-2020', en=(0, PROFILE_Y, -10.0), girar=(), entra_por='-z')
    pieza = pieza.quitar('alojamiento_perfil', perfil.hueco(holgura='slide'))
    for i, sx in enumerate([-1, 1]):
        for j, sy in enumerate([-1, 1]):
            x = sx * M3_PASO_X / 2
            y = sy * M3_PASO_Y / 2
            pieza = pieza.tornillo(f'orejeta_{i*2+j+1}', 'M3', en=(x, y, T), eje='-z', tipo='pasante')
    for i, sx in enumerate([-1, 1]):
        x = sx * M5_PASO / 2
        y = PROFILE_Y
        pieza = pieza.taladrar(f'perfil_{i+1}', M5_HOLE, en=(x, y, T), eje='-z')
    return pieza.acabar()
