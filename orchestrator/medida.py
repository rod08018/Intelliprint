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


# --- sondas dentro del bucle -----------------------------------------------------------

ACABADO = "acabado"
"""Prefijo de los defectos de estética: el mejor intento (F6.8 (mejor))
cuenta antes los de función. Una pieza bien acabada donde el servo no
entra es peor que una con aristas vivas donde sí."""


def sondas_de(requisitos) -> list:
    """Las sondas del banco (F6.12 (techo)) que se pueden pedir desde los
    requisitos. Rejuzgada con ellas, la corrida del 62 % daba 81 %, y lo que
    fallaba eran aristas vivas y ventanas de servo que el diseñador nunca
    recibía como motivo: el bucle solo medía agujeros (2026-11-04).

    El acabado se mira siempre: que se vea como un producto no lo pide nadie
    con esas palabras, pero lo espera todo el mundo."""
    from orchestrator.banco import AristasVivas, Ventana

    sondas = [AristasVivas(tipo="aristas_vivas", max_fraccion=0.1)]
    for r in requisitos:
        if r.tipo == "encaje" and len(r.seccion_mm) == 2:
            sondas.append(Ventana(tipo="ventana", ancho_mm=r.seccion_mm[0],
                                  alto_mm=r.seccion_mm[1], porque=f"{r.id} («{r.texto}»)"))
    return sondas


def defectos_de_la_pieza(requisitos, resultado, step, freecadcmd: str,
                         material: dict) -> list[str]:
    """Lo que la pieza construida no cumple: agujeros (con los rasgos del
    kit) y sondas sobre el STEP. Los de acabado van con su prefijo."""
    from orchestrator.banco import AristasVivas, medir_sondas

    fallos = defectos(requisitos, resultado.rasgos)
    sondas = sondas_de(requisitos)
    for sonda, medida in zip(sondas, medir_sondas(step, sondas, freecadcmd, material)):
        if medida.estado != "no_cumple":
            continue   # «sin medir» (una sonda rota) no es culpa del diseñador
        if isinstance(sonda, AristasVivas):
            # Antes decía `redondear(1, aristas="todas")`: redondea también los
            # rincones, y en el SG90 del banco eso cerró la ventana del servo.
            fallos.append(f"{ACABADO}: {medida.detalle}. Termina con `return pieza.acabar()`, "
                          "que redondea todas las esquinas sin rellenar los rincones; si "
                          "una pared es fina, `acabar(radio=0.5)`")
        else:
            fallos.append(f"{sonda.porque}: {medida.detalle}. La abertura tiene que atravesar "
                          "la pieza entera, no ser un rebaje, y llevar holgura")
    return fallos
