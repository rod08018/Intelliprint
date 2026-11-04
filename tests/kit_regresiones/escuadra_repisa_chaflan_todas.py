FONDO = 200      # R1: repisa de madera de 200 mm de fondo
SEP = 60         # R5/R8: agujeros separados 60 mm
D_TORNILLO = 4.5 # R4/R7: agujeros de 4.5 mm
ANCHO = 30       # concepto: 30 mm de ancho
ALTO_PARED = 80  # concepto: 80 mm de altura de pared
ALA = 6          # concepto: alas de 6 mm
CARTELA = 6      # concepto: cartela de 6 mm
PUNTA = 20       # concepto: la cartela llega a 20 mm en la punta


def construir(kit):
    # Tumbada sobre la cartela: el perfil (L + cartela) vive en el plano xy
    # y crece ANCHO en z. La cara lateral de la cartela apoya en la cama.
    # Perfil en L: ala de pared (vertical, 80 de alto) + ala de repisa (200 de fondo).
    l = kit.extruir([(0, 0), (FONDO, 0), (FONDO, ALA), (ALA, ALA),
                     (ALA, ALTO_PARED), (0, ALTO_PARED)], ANCHO, plano="xy")
    # Cartela triangular: arranca a 80 mm en la pared y llega a 20 mm en la punta.
    # Se mete 0.5 mm en la L para solapar, no solo tocar.
    cartela = kit.extruir([(ALA - 0.5, ALA - 0.5), (FONDO, ALA - 0.5),
                           (ALA - 0.5, ALTO_PARED - 0.5)], CARTELA, plano="xy",
                          desde=(ANCHO - CARTELA) / 2)
    pieza = l + cartela

    # Agujeros del ala de pared: entran por la cara interior (x = ALA) y salen
    # por la que apoya en la pared (x = 0). Horizontales -> lagrima.
    for i, y in enumerate([(ALTO_PARED - SEP) / 2, (ALTO_PARED + SEP) / 2]):
        pieza = pieza.taladrar(f"pared_{i + 1}", D_TORNILLO,
                               en=(ALA, y, ANCHO / 2), eje="-x",
                               lagrima=True, avellanado=9)

    # Agujeros del ala de repisa: entran por la cara superior (y = ALA) y salen
    # por la que apoya en la repisa (y = 0). Horizontales -> lagrima.
    for i, x in enumerate([(FONDO - SEP) / 2, (FONDO + SEP) / 2]):
        pieza = pieza.taladrar(f"repisa_{i + 1}", D_TORNILLO,
                               en=(x, ALA, ANCHO / 2), eje="-y",
                               lagrima=True, avellanado=9)

    pieza = pieza.redondear(1, aristas="verticales")
    return pieza.achaflanar(0.5, aristas="todas")
