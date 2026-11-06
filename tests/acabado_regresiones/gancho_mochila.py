CARGA_KG = 8          # R1: colgar una mochila de hasta 8 kg
TORNILLO_MM = 4       # R2: Se atornilla con 2 tornillos de 4 mm
NUM_TORNILLOS = 2     # R3: 2 de ellos
AGUJERO_MM = 4.5      # R3: agujeros de 4.5 mm
SEP_MM = 40           # R3: separados 40 mm en vertical
SALIENTE_MM = 50      # R4: el gancho sobresale 50 mm de la pared

PLACA_ANCHO = 50
PLACA_ALTO = 100
PLACA_ESPESOR = 6
BRAZO_ANCHO = 40
NERVIO_ESPESOR = 5
NERVIO_CANTO = 45
AVELLANADO_MM = 9

def construir(kit):
    placa = kit.caja(PLACA_ANCHO, PLACA_ALTO, PLACA_ESPESOR,
                     en=(-PLACA_ANCHO/2, 0, 0))
    y_min = PLACA_ALTO/2 - 5
    y_max = PLACA_ALTO/2 + 5
    lip_y = y_max + 5
    z_start = PLACA_ESPESOR - 0.5
    z_lip_start = SALIENTE_MM - 5
    z_top = SALIENTE_MM
    puntos_brazo = [
        (y_min, z_start),
        (y_max, z_start),
        (y_max, z_lip_start),
        (lip_y, z_top),
        (y_max, z_top),
        (y_min, z_top)
    ]
    brazo = kit.extruir(puntos_brazo, alto=BRAZO_ANCHO, plano="yz",
                        desde=-BRAZO_ANCHO/2)
    nervio_y_min = 10
    nervio_y_max = 55
    nervio_top_y = 50
    nervio_z_start = PLACA_ESPESOR - 0.5
    nervio_z_top = SALIENTE_MM
    puntos_nervio = [
        (nervio_y_min, nervio_z_start),
        (nervio_y_max, nervio_z_start),
        (nervio_top_y, nervio_z_top)
    ]
    nervio_der = kit.extruir(puntos_nervio, alto=NERVIO_ESPESOR + 0.5,
                             plano="yz",
                             desde=BRAZO_ANCHO/2 - 0.5)
    nervio_izq = kit.extruir(puntos_nervio, alto=NERVIO_ESPESOR + 0.5,
                             plano="yz",
                             desde=-BRAZO_ANCHO/2 - NERVIO_ESPESOR)
    pieza = placa + brazo + nervio_der + nervio_izq
    y1 = PLACA_ALTO/2 - SEP_MM/2
    y2 = PLACA_ALTO/2 + SEP_MM/2
    pieza = pieza.taladrar("agujero_inferior", AGUJERO_MM,
                           en=(0, y1, PLACA_ESPESOR),
                           eje="-z", avellanado=AVELLANADO_MM)
    pieza = pieza.taladrar("agujero_superior", AGUJERO_MM,
                           en=(0, y2, PLACA_ESPESOR),
                           eje="-z", avellanado=AVELLANADO_MM)
    return pieza.acabar()