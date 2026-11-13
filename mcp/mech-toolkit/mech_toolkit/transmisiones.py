"""Las cuentas de una correa dentada GT2 de 2 mm (F10.3 (correa), ADR-021).

Aquí no hay geometría de FreeCAD: solo las medidas que hacen falta para
dibujar una polea y para saber a qué distancia van dos ejes. Lo importan el
kit (que dibuja) y el orquestador (que mide y elige la correa).

De dónde sale cada cifra:

- Manual técnico de SDP/SI (sdp-si.com, D820 «Technical Section»). Figura
  19g, «2 mm Pitch GT3»: paso 2 mm, diente de 0,76 mm de alto, correa de
  1,52 mm de grueso. Tabla de «Distance from Pitch Line to Belt Tooth
  Bottom "U"»: 2 mm GT3, .010 inches; «O.D. = pd − 2U». Tabla 26, altura
  nominal de pestaña para 2 mm GT: 1,50 mm. Tabla 27, lo que la cara de la
  polea mide de más sobre la correa: 3,00 mm sin pestañas y 1,00 con ellas.
  Sección 22, la geometría de la correa (ecuaciones 22-1 y 22-2).
- Tabla «2mm - PowerGrip GT / 2MR» de Pfeifer Industries: de 12 dientes
  para arriba; 20 dientes, 12,73 y 12,22 mm.

**La forma de la ranura es una aproximación.** Ninguna de las dos fuentes
publica los radios del perfil GT2. La ranura de aquí es un semicírculo con
el centro en el diámetro exterior y el radio del alto del diente de la
correa: tiene su profundidad y deja 0,4 mm de cresta. Si la correa asienta
lo dice una pieza impresa (F10.8 (calibrar)), no este archivo.
"""

import math

PASO = 2.0
ALTO_DEL_DIENTE = 0.76
"""También el radio de la ranura. Sin holgura de impresión: sumarle la
deslizante del perfil (0,2 mm en diámetro) deja 0,2 mm de cresta entre
ranuras en una polea de 20 dientes, menos que un hilo de la boquilla."""
U = 0.254
"""De la línea primitiva (donde va el cordón de la correa) al fondo de su
diente: .010 pulgadas. El diámetro exterior de la polea es el primitivo
menos dos veces esto."""
PESTANA = 1.5
SOBRA_CON_PESTANAS, SOBRA_SIN_PESTANAS = 1.0, 3.0
MINIMO_DE_DIENTES = 12
DIENTES_DEL_MOTOR = 20
"""La polea que se compra para el eje de 5 mm de un NEMA 17."""


def diametro_primitivo(dientes: int) -> float:
    return dientes * PASO / math.pi


def diametro_exterior(dientes: int) -> float:
    return diametro_primitivo(dientes) - 2 * U


def ancho_de_la_cara(correa_mm: float, pestanas: bool) -> float:
    return correa_mm + (SOBRA_CON_PESTANAS if pestanas else SOBRA_SIN_PESTANAS)


def dientes_de_la_conducida(del_motor: int, relacion: float) -> int:
    """Los dientes de la polea grande para esa relación, o ValueError si no
    salen enteros."""
    exactos = del_motor * relacion
    if abs(exactos - round(exactos)) > 1e-6:
        raise ValueError(
            f"una relación de {relacion:g}:1 con una polea de {del_motor} dientes pide "
            f"{exactos:g} dientes, y tienen que ser enteros: prueba con "
            f"{math.floor(exactos) / del_motor:g} o {math.ceil(exactos) / del_motor:g}")
    return round(exactos)


def largo_de_correa(z1: int, z2: int, entre_ejes: float) -> float:
    """Los milímetros de correa, por su línea primitiva, que abrazan dos
    poleas de `z1` y `z2` dientes con los ejes a `entre_ejes`: dos tramos
    rectos y un arco en cada polea (SDP/SI, ecuaciones 22-1 y 22-2)."""
    grande, chica = max(z1, z2) * PASO / (2 * math.pi), min(z1, z2) * PASO / (2 * math.pi)
    if entre_ejes <= grande - chica:
        raise ValueError("una polea queda dentro de la otra")
    phi = math.acos((grande - chica) / entre_ejes)
    return (2 * entre_ejes * math.sin(phi) + math.pi * (grande + chica)
            + (math.pi - 2 * phi) * (grande - chica))


def distancia_entre_ejes(z1: int, z2: int, dientes_de_la_correa: int) -> float | None:
    """A qué distancia van los ejes para que una correa cerrada de esos
    dientes quede justa, o None si no llega a abrazar las dos poleas sin que
    se toquen. El largo crece con la distancia: se busca por bisección."""
    largo = dientes_de_la_correa * PASO
    lo = (z1 + z2) * PASO / (2 * math.pi)        # las dos primitivas tocándose
    if largo_de_correa(z1, z2, lo) >= largo:
        return None
    hi = largo                                    # de sobra: 2C ya pasa del largo
    for _ in range(80):
        medio = (lo + hi) / 2
        lo, hi = (medio, hi) if largo_de_correa(z1, z2, medio) < largo else (lo, medio)
    return (lo + hi) / 2


def correa_para(z1: int, z2: int, entre_ejes: float, ajuste: float) -> dict | None:
    """La correa cerrada que cabe con los ejes a `entre_ejes` ± `ajuste` (lo
    que da la colisa del motor): {"dientes", "largo_mm", "entre_ejes_mm"}.
    De las que caben, la que pide la distancia más cercana a la dibujada.
    None si ninguna cae en el ajuste."""
    justa = largo_de_correa(z1, z2, entre_ejes) / PASO
    mejor = None
    for n in (math.floor(justa) - 1, math.floor(justa), math.ceil(justa), math.ceil(justa) + 1):
        c = distancia_entre_ejes(z1, z2, n)
        if c is None or abs(c - entre_ejes) > ajuste + 1e-9:
            continue
        if mejor is None or abs(c - entre_ejes) < abs(mejor["entre_ejes_mm"] - entre_ejes):
            mejor = {"dientes": n, "largo_mm": n * PASO, "entre_ejes_mm": c}
    return mejor
