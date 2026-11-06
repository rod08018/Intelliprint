# R1: taladro central de 22.4 mm
D_CENTRAL = 22.4
# R2: 4 agujeros de 3.3 mm en cuadro de 31 mm
D_M3 = 3.3
CUADRO_M3 = 31
# R3: agujeros de 4.5 mm separados 30 mm
D_M4 = 4.5
SEP_M4 = 30
# R5: carga de la correa 20 N
CARGA_N = 20

# Dimensiones del concepto aprobado
ESPESOR = 5.0
ALA_MOTOR_X = 55.0
ALA_MOTOR_Y = 60.0
ALA_VERTICAL_H = 40.0
Y_CENTRO_MOTOR = 35.0

def construir(kit):
    l_puntos = [
        (0.0, 0.0),
        (ALA_MOTOR_Y, 0.0),
        (ALA_MOTOR_Y, ESPESOR),
        (ESPESOR, ESPESOR),
        (ESPESOR, ALA_VERTICAL_H),
        (0.0, ALA_VERTICAL_H),
    ]
    l = kit.extruir(l_puntos, ALA_MOTOR_X, plano='yz', desde=-ALA_MOTOR_X / 2.0)
    
    g_puntos = [(4.5, 0.0), (30.0, 0.0), (4.5, 35.0)]
    g_der = kit.extruir(g_puntos, ESPESOR, plano='yz', desde=ALA_MOTOR_X / 2.0 - ESPESOR)
    g_izq = kit.extruir(g_puntos, ESPESOR, plano='yz', desde=-ALA_MOTOR_X / 2.0)
    
    pieza = l + g_der + g_izq
    
    pieza = pieza.taladrar('taladro_central_22_4', D_CENTRAL,
                           en=(0.0, Y_CENTRO_MOTOR, ESPESOR), eje='-z')
    
    mitad_m3 = CUADRO_M3 / 2.0
    for i, dx in enumerate([-mitad_m3, mitad_m3]):
        for j, dy in enumerate([-mitad_m3, mitad_m3]):
            x = dx
            y = Y_CENTRO_MOTOR + dy
            pieza = pieza.tornillo(f'motor_M3_{i*2 + j + 1}', 'M3',
                                   en=(x, y, ESPESOR), eje='-z', tipo='pasante')
    
    for i, x in enumerate([-SEP_M4 / 2.0, SEP_M4 / 2.0]):
        pieza = pieza.taladrar(f'base_M4_{i + 1}', D_M4,
                               en=(x, ESPESOR, 20.0), eje='-y', lagrima=True)
    
    motor = kit.componente('nema17', en=(0.0, Y_CENTRO_MOTOR, 0.0),
                           girar=(), entra_por='-z')
    pieza = pieza.quitar('alojamiento_nema17', motor.hueco())
    
    return pieza.acabar()
