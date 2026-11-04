LARGO = 22.8      # R1: servo 22.8 mm
ANCHO = 12.2      # R2: servo 12.2 mm
D_OR = 2.0        # R4: agujeros de 2 mm para rosca directa
SEP_OR = 27.8     # R5: orejetas separadas 27.8 mm
D_M3 = 3.3        # R6: 4 agujeros de 3.3 mm
CUADRO = 20.0     # R7: cuadro de 20 mm

BASE = 4.0
ALTO = 22.5
PARED = 2.0
HOLGURA = 0.2

# Interior del collar: 23.2 x 12.6 (con holgura slide)
INT_X = LARGO + 2 * HOLGURA
INT_Y = ANCHO + 2 * HOLGURA
EXT_X = INT_X + 2 * PARED
EXT_Y = INT_Y + 2 * PARED

# Postes de orejeta: 8 x 8 mm (seccion minima del concepto)
POSTE = 8.0

# Ala de base: cubre el cuadro de 20 mm con margen
ALA_X = CUADRO + 2 * POSTE
ALA_Y = CUADRO + 2 * POSTE


def construir(kit):
    # Ala de base apoyada en la cama (z=0), collar vertical encima.
    ala = kit.caja(ALA_X, ALA_Y, BASE, en=(-ALA_X / 2, -ALA_Y / 2, 0))

    # Collar hueco: pared exterior menos interior, de z=BASE a z=BASE+ALTO.
    exterior = kit.caja(EXT_X, EXT_Y, ALTO, en=(-EXT_X / 2, -EXT_Y / 2, BASE))
    interior = kit.caja(INT_X, INT_Y, ALTO + 1, en=(-INT_X / 2, -INT_Y / 2, BASE - 0.5))
    collar = exterior.quitar("abertura_servo", interior)

    pieza = ala + collar

    # Postes de orejeta en el borde superior, a ambos lados en x.
    z_poste = BASE + ALTO
    for i, sx in enumerate([-1, 1]):
        cx = sx * SEP_OR / 2
        poste = kit.caja(POSTE, POSTE, POSTE, en=(cx - POSTE / 2, -POSTE / 2, z_poste - 0.5))
        pieza = pieza + poste

    # Cartelas a 45 grados en la union collar-base (autoportantes).
    c = 6.0
    for sx in [-1, 1]:
        x0 = sx * EXT_X / 2
        pts = [(x0, BASE), (x0 + sx * c, BASE), (x0, BASE + c)]
        cartela = kit.extruir(pts, EXT_Y, plano="xz", desde=-EXT_Y / 2)
        pieza = pieza + cartela

    # Agujeros guia de orejeta: 2 mm, verticales, en los postes.
    for i, sx in enumerate([-1, 1]):
        cx = sx * SEP_OR / 2
        pieza = pieza.taladrar(f"orejeta_{i + 1}", D_OR, en=(cx, 0, z_poste + POSTE + 1),
                               eje="-z", avellanado=D_OR + 1.5)

    # Cuatro agujeros M3 de 3.3 mm en cuadro de 20 mm, verticales.
    for i, (sx, sy) in enumerate([(-1, -1), (1, -1), (1, 1), (-1, 1)]):
        cx = sx * CUADRO / 2
        cy = sy * CUADRO / 2
        pieza = pieza.taladrar(f"placa_{i + 1}", D_M3, en=(cx, cy, BASE + 1),
                               eje="-z", avellanado=6.0)

    # Ranura de cable de 8 mm en la pared frontal del collar (y negativa).
    # Entra desde fuera (y = -EXT_Y/2 - 1) hacia +y, atravesando la pared.
    pieza = pieza.colisa("ranura_cable", 8.0,
                         desde=(0, -EXT_Y / 2 - 1, BASE + 4),
                         hasta=(0, -EXT_Y / 2 - 1, BASE + 12),
                         eje="y", profundidad=PARED + 1)

    # Acabado de producto.
    pieza = pieza.redondear(1.0, aristas="verticales")
    pieza = pieza.achaflanar(0.5, aristas="base")
    return pieza