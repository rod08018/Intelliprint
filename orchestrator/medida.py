"""Requisitos medidos dentro del bucle de diseño (F6.7 (lazo)).

En el banco (2026-11-04) las piezas que se construían fallaban en lo que
pedía el usuario —el patrón de Ø2 del SG90 desviado 4.1 mm, 2 de los 4
agujeros Ø3.3 del NEMA17— y solo lo medía el banco, después. Aquí se mide
al construir, con los rasgos con nombre que registra el kit (F5.18 (kit)),
y cada defecto vuelve al diseñador con los números.

Solo los requisitos de tipo `agujero`: son los únicos cuyo rasgo se sabe
encontrar sin adivinar. Una cota de fondo no dice a qué eje va; eso queda
para F6.12 (techo).
"""

import math

TOL_DIAMETRO_MM = 0.05
"""El diámetro tiene que ser el pedido: la trazabilidad ya exige que el
número esté escrito, y aquí se exige que sea el del agujero."""
TOL_SEPARACION_MM = 0.15


def _separacion(a: dict, b: dict) -> float:
    """Distancia entre los ejes de dos agujeros paralelos: la parte de la
    distancia entre entradas que es perpendicular al eje. Dos agujeros que
    entran por caras distintas siguen estando a la misma separación."""
    e = a["eje"]
    norma = math.sqrt(sum(c * c for c in e)) or 1.0
    e = [c / norma for c in e]
    d = [bb - aa for aa, bb in zip(a["entrada"], b["entrada"])]
    a_lo_largo = sum(x * y for x, y in zip(d, e))
    perpendicular = [x - a_lo_largo * y for x, y in zip(d, e)]
    return math.sqrt(sum(c * c for c in perpendicular))


def defectos(requisitos, rasgos: list[dict]) -> list[str]:
    agujeros = [r for r in rasgos if r.get("tipo") == "agujero"]
    hay = sorted({round(a["diametro_mm"], 2) for a in agujeros})
    fallos = []
    for req in requisitos:
        if req.tipo != "agujero" or req.valor is None or req.unidad != "mm":
            continue
        iguales = [a for a in agujeros if abs(a["diametro_mm"] - req.valor) <= TOL_DIAMETRO_MM]
        pedidos = req.cantidad or 1
        if len(iguales) < pedidos:
            fallos.append(
                f"{req.id} («{req.texto}»): pide {pedidos} agujero(s) de Ø{req.valor:g} y hay "
                f"{len(iguales)}. Diámetros de agujero en la pieza: "
                f"{', '.join(f'Ø{d:g}' for d in hay) or 'ninguno'}. Hazlos con `taladrar` o "
                "`tornillo`, con nombre, y con el diámetro exacto")
            continue
        distancias = sorted({round(_separacion(a, b), 2)
                             for i, a in enumerate(iguales) for b in iguales[i + 1:]})
        for s in req.separaciones_mm:
            if not any(abs(d - s) <= TOL_SEPARACION_MM for d in distancias):
                fallos.append(
                    f"{req.id} («{req.texto}»): los agujeros de Ø{req.valor:g} tienen que "
                    f"estar a {s:g} mm entre centros, y entre los que hay las distancias son "
                    f"{', '.join(f'{d:g}' for d in distancias)} mm")
    return fallos
