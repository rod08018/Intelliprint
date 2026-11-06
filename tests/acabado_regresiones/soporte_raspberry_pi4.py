M2_5 = 2.5  # R1: cuatro agujeros para tornillos M2.5
N_M2_5 = 4  # R1: cuatro de ellos
M2_5_TORN = 2.5  # R2: tornillos M2.5
M5 = 5.0  # R3: dos tornillos M5
N_M5 = 2  # R3: dos de ellos
M5_TORN = 5.0  # R4: tornillos M5 y tuercas en T
T_NUT_STEP_W = 6.0  # R5: anchura del escalon de la tuerca en T
T_NUT_STEP_H = 1.0  # R6: altura del escalon de la tuerca en T
T_NUT_THICK = 4.5  # R7: espesor de la tuerca en T
T_NUT_LENGTH = 10.0  # R8: longitud de la tuerca en T
T_NUT_WIDTH = 9.5  # R9: anchura de la tuerca en T
T_NUT_TOTAL_H = 5.0  # R10: altura total de la tuerca en T
# R11: que se puedan enchufar todos los cables (geometria abierta)
# R12: sin soportes de impresion (imprime plano)

TRAY_T = 6.0  # concepto: bandeja de 6 mm de espesor
BAR_W = 14.0  # concepto: travesanos de 14 mm de ancho
SPINE_W = 14.0  # concepto: espina central de 14 mm
TORRETA_D = 5.5  # concepto: torretas de 5.5 mm de diametro
TORRETA_H = 6.0  # concepto: torretas de 6 mm de altura
M5_SEP = 29.0  # concepto: separacion entre M5
M5_SCREW_LEN = 12.0  # concepto: tornillos M5 avellanados de 12 mm
COUNTERSINK_D = 10.0  # concepto: rebaje a 90 grados para M5
OVERLAP = 0.5  # regla de solape entre cuerpos
PI_WIDTH = 56.0  # ficha Raspberry Pi 4: ancho de PCB
PI_HOLE_X0 = 3.5  # ficha Raspberry Pi 4
PI_HOLE_X1 = 61.5  # ficha Raspberry Pi 4
PI_HOLE_Y0 = 3.5  # ficha Raspberry Pi 4
PI_HOLE_Y1 = 52.5  # ficha Raspberry Pi 4
PI_X0 = 0.0
PI_Y0 = 0.0
PCB_Z = 12.0  # concepto: bandeja 6 + torretas 6
SD_CUT_X0 = -5.0  # ficha: tarjeta SD asoma por el canto izquierdo
SD_CUT_X1 = 0.0
SD_CUT_Y0 = 22.0
SD_CUT_Y1 = 34.0

def construir(kit):
    # Colocar el componente Raspberry Pi 4 para obtener sus agujeros
    pi = kit.componente('raspberry-pi-4', en=(PI_X0, PI_Y0, PCB_Z), girar=(), entra_por='+z', nombre='raspberry_pi_4')
    holes = pi.agujeros()
    
    # Definir el perfil en H de la bandeja
    left_x0 = PI_X0 + PI_HOLE_X0 - BAR_W / 2.0
    left_x1 = PI_X0 + PI_HOLE_X0 + BAR_W / 2.0
    right_x0 = PI_X0 + PI_HOLE_X1 - BAR_W / 2.0
    right_x1 = PI_X0 + PI_HOLE_X1 + BAR_W / 2.0
    y0 = PI_Y0
    y1 = PI_Y0 + PI_WIDTH
    spine_y0 = PI_Y0 + PI_WIDTH / 2.0 - SPINE_W / 2.0
    spine_y1 = PI_Y0 + PI_WIDTH / 2.0 + SPINE_W / 2.0
    
    puntos_h = [
        (left_x0, y0),
        (left_x1, y0),
        (left_x1, spine_y0),
        (right_x0, spine_y0),
        (right_x0, y0),
        (right_x1, y0),
        (right_x1, y1),
        (right_x0, y1),
        (right_x0, spine_y1),
        (left_x1, spine_y1),
        (left_x1, y1),
        (left_x0, y1)
    ]
    pieza = kit.extruir(puntos_h, TRAY_T, plano='xy', desde=0)
    
    # Añadir torretas en los cuatro agujeros de la Pi
    for i, h in enumerate(holes):
        c = h['en']
        torreta = kit.cilindro(TORRETA_D, TORRETA_H + OVERLAP, en=(c[0], c[1], TRAY_T - OVERLAP), eje='z')
        pieza = pieza + torreta
    
    # Colocar y restar el perfil 2020
    profile_x = (left_x1 + right_x0) / 2.0  # centro de la espina
    profile_y = (spine_y0 + spine_y1) / 2.0
    perfil = kit.componente('perfil-2020', en=(profile_x, profile_y, -10.0), girar=(), entra_por='-z', nombre='perfil_2020')
    pieza = pieza.quitar('alojamiento_perfil_2020', perfil.hueco())
    
    # Restar el hueco de la Raspberry Pi
    pieza = pieza.quitar('alojamiento_raspberry_pi_4', pi.hueco())
    
    # Muesca para la tarjeta SD
    sd_cut = kit.caja(SD_CUT_X1 - SD_CUT_X0, SD_CUT_Y1 - SD_CUT_Y0, TRAY_T + 1.0, en=(SD_CUT_X0, SD_CUT_Y0, -0.5))
    pieza = pieza.quitar('muesca_sd', sd_cut)
    
    # Taladrar los dos agujeros M5 en la espina
    m5_center_x = (left_x1 + right_x0) / 2.0
    m5_y = (spine_y0 + spine_y1) / 2.0
    for i in range(N_M5):
        x = m5_center_x - M5_SEP / 2.0 + i * M5_SEP
        pieza = pieza.taladrar(f'm5_{i+1}', M5, en=(x, m5_y, TRAY_T), eje='-z', avellanado=COUNTERSINK_D)
    
    # Taladrar los cuatro agujeros M2.5 en las torretas
    for i, h in enumerate(holes):
        c = h['en']
        pieza = pieza.taladrar(f'm2_5_{i+1}', M2_5, en=(c[0], c[1], PCB_Z), eje='-z', profundidad=TORRETA_H + OVERLAP)
    
    return pieza.acabar()