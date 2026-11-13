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
import re
from pathlib import Path

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


def _para_tornillo(req, del_perfil: dict) -> tuple[str, list[float]] | None:
    """Si el requisito nombra un tornillo («dos tornillos M5») y su valor es
    la métrica, el agujero es el del perfil para ese tornillo, no un Ø5.

    Proyecto del 608ZZ (2026-11-08): «M5» salió como agujero de valor 5, y
    el bucle exigía un Ø5 por el que el M5 no pasa."""
    for m in re.findall(r"\bM(\d+(?:[.,]\d+)?)\b", req.texto):
        if abs(float(m.replace(",", ".")) - req.valor) < 1e-9:
            metrica = f"M{m.replace(',', '.')}"
            validos = [float(v) for k, v in del_perfil.items()
                       if k.startswith(f"{metrica}_") and k.endswith(
                           ("_through_mm", "_selftap_mm", "_insert_mm"))]
            return metrica, sorted(validos)
    return None


def defectos(requisitos, rasgos: list[dict], agujeros_del_perfil: dict | None = None
             ) -> list[str]:
    agujeros = [r for r in rasgos if r.get("tipo") == "agujero"]
    hay = sorted({round(a["diametro_mm"], 2) for a in agujeros})
    fallos = []
    for req in requisitos:
        if req.tipo != "agujero" or req.valor is None or req.unidad != "mm":
            continue
        pedidos = req.cantidad or 1
        tornillo = _para_tornillo(req, agujeros_del_perfil or {})
        if tornillo:
            metrica, validos = tornillo
            iguales = [a for a in agujeros
                       if any(abs(a["diametro_mm"] - v) <= TOL_DIAMETRO_MM for v in validos)]
            if len(iguales) < pedidos:
                como = (f"Ø{validos[0]:g}" if len(validos) == 1
                        else " o ".join(f"Ø{v:g}" for v in validos))
                fallos.append(
                    f"{req.id} («{req.texto}»): pide {pedidos} agujero(s) para un {metrica}, "
                    f"que en esta impresora es {como if validos else '(el perfil no lo tiene)'}, "
                    f"y hay {len(iguales)}. Diámetros de agujero en la pieza: "
                    f"{', '.join(f'Ø{d:g}' for d in hay) or 'ninguno'}. Hazlos con "
                    f'`tornillo("{metrica}", ...)`, que pone el diámetro del perfil: un agujero '
                    f"de Ø{req.valor:g} es el del tornillo, y no pasa")
                continue
        else:
            iguales = [a for a in agujeros
                       if abs(a["diametro_mm"] - req.valor) <= TOL_DIAMETRO_MM]
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


CABEZA_ISO_4762_MM = {"M2": 3.8, "M2.5": 4.5, "M3": 5.5, "M4": 7.0, "M5": 8.5, "M6": 10.0,
                      "M8": 13.0}
"""Diámetro de la cabeza Allen (ISO 4762, dk máx.): lo que tiene que poder
llegar desde fuera hasta la entrada del agujero."""


def sondas_de(requisitos, rasgos=(), pared_min_mm=None) -> list:
    """Las sondas del banco (F6.12 (techo)) que se pueden pedir desde los
    requisitos. Rejuzgada con ellas, la corrida del 62 % daba 81 %, y lo que
    fallaba eran aristas vivas y ventanas de servo que el diseñador nunca
    recibía como motivo: el bucle solo medía agujeros (2026-11-04).

    El acabado se mira siempre: que se vea como un producto no lo pide nadie
    con esas palabras, pero lo espera todo el mundo.

    Y cada componente que el programa coloca con `kit.componente` se mete en
    la pieza con su ficha (F6.11 (biblioteca)): el soporte del HC-SR04 salió
    «resuelto» con un sensor que no entraba, porque aquí solo se miraban
    agujeros y aristas.

    Con `pared_min_mm` (el `walls.min_mm` del perfil), también la pared más
    fina: el soporte del MG996R del banco `1105-2120` salió con 0.15 mm y
    solo lo vio el banco."""
    from orchestrator.banco import (AccesoTornillo, AristasVivas, ParedMinima, Ventana,
                                    sondas_del_rasgo)

    sondas = [AristasVivas(tipo="aristas_vivas", max_fraccion=0.1)]
    if pared_min_mm:
        sondas.append(ParedMinima(tipo="pared_minima", min_mm=float(pared_min_mm),
                                  porque="el perfil de la impresora"))
    for r in requisitos:
        if r.tipo == "encaje" and len(r.seccion_mm) == 2:
            sondas.append(Ventana(tipo="ventana", ancho_mm=r.seccion_mm[0],
                                  alto_mm=r.seccion_mm[1], porque=f"{r.id} («{r.texto}»)"))
    for r in rasgos:
        if r.get("tipo") == "componente":
            sondas += sondas_del_rasgo(r)
        cabeza = r.get("avellanado_mm") or CABEZA_ISO_4762_MM.get(r.get("tornillo"))
        if r.get("tipo") == "agujero" and r.get("tornillo") and cabeza:
            sondas.append(AccesoTornillo(tipo="acceso_tornillo", nombre=r["nombre"],
                                         entrada=r["entrada"], eje=r["eje"],
                                         diametro_mm=float(cabeza)))
    return sondas


def _distancia_a_rasgo(p, r) -> float | None:
    """Del punto `p` a la superficie del rasgo: una caja para un hueco, un
    cilindro de eje y largo conocidos para un agujero o una tuerca (el
    hexágono, por su entrecaras: basta para saber si es él)."""
    if r.get("tipo") == "hueco":
        fuera = [max(lo - x, 0.0, x - hi) for x, lo, hi in zip(p, r["desde"], r["hasta"])]
        if any(fuera):
            return math.sqrt(sum(f * f for f in fuera))
        return min(min(x - lo, hi - x) for x, lo, hi in zip(p, r["desde"], r["hasta"]))
    if r.get("tipo") in ("agujero", "tuerca"):
        radio = (r.get("diametro_mm") or r.get("entrecaras_mm") or 0) / 2
        e = r["eje"]
        norma = math.sqrt(sum(c * c for c in e)) or 1.0
        e = [c / norma for c in e]
        d = [a - b for a, b in zip(p, r["entrada"])]
        t = sum(x * y for x, y in zip(d, e))
        radial = math.sqrt(max(sum(x * x for x in d) - t * t, 0.0))
        largo = r.get("profundidad_mm")
        axial = max(-t, 0.0, (t - largo) if largo is not None else 0.0)
        if axial:
            return math.hypot(axial, max(radial - radio, 0.0))
        return abs(radial - radio)
    return None


def mensaje_de_pared(detalle: str, rasgos, pared_min_mm) -> str:
    """El defecto de pared, con los rasgos que la tocan por nombre.

    La base del pan-tilt (2026-11-09) recibía «(en 5.0, 15.2, 15.7)» y nada
    más: un punto que el diseñador tenía que casar a mano con su programa.
    La pared fina tiene un rasgo a cada lado, o la cara de la pieza en uno:
    los que quedan a menos del mínimo del punto son los que la adelgazan."""
    texto = (f"pared: {detalle} (el mínimo que imprime la impresora). Engrosa esa pared o "
             "aparta lo que la adelgaza")
    m = re.search(r"\(en (-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\)", detalle)
    cerca = []
    if m and pared_min_mm:
        p = [float(x) for x in m.groups()]
        # 0.1 de margen: el punto sale redondeado a una décima.
        cerca = [r["nombre"] for r in rasgos
                 if (dist := _distancia_a_rasgo(p, r)) is not None
                 and dist <= float(pared_min_mm) + 0.1]
    if cerca:
        return (texto + f". Está junto a {', '.join(f'«{n}»' for n in cerca)}: muévelo hacia "
                "dentro o engrosa la pared que lo rodea")
    return texto + "; suele ser un hueco o un agujero demasiado cerca de una cara"


def _unitario(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


def _en_caja(p, caja, margen=1e-6) -> bool:
    return all(lo + margen < x < hi - margen
               for x, lo, hi in zip(p, caja["desde"], caja["hasta"]))


def _de_caja_a_caja(a, b) -> float:
    huecos = [max(0.0, a["desde"][i] - b["hasta"][i], b["desde"][i] - a["hasta"][i])
              for i in range(3)]
    return math.sqrt(sum(h * h for h in huecos))


def _de_caja_a_agujero(caja, ag) -> float:
    """Del cilindro del agujero a la caja, muestreando su eje: basta para
    saber si se tocan."""
    e = _unitario(ag["eje"])
    largo = ag.get("profundidad_mm") or 500.0
    r = (ag.get("diametro_mm") or 0) / 2
    pasos = max(int(largo / 0.25), 1)
    mejor = math.inf
    for k in range(pasos + 1):
        p = [a + c * largo * k / pasos for a, c in zip(ag["entrada"], e)]
        fuera = [max(lo - x, 0.0, x - hi) for x, lo, hi in zip(p, caja["desde"], caja["hasta"])]
        mejor = min(mejor, math.sqrt(sum(f * f for f in fuera)))
    return max(mejor - r, 0.0)


def _a_lo_largo(rasgo, origen, e) -> tuple[float, float]:
    """Lo que ocupa un hueco o un agujero proyectado sobre la recta `origen +
    t·e`: el tramo de t que cubre."""
    def t(p):
        return sum((a - b) * c for a, b, c in zip(p, origen, e))
    if rasgo.get("tipo") == "hueco":
        ts = [t((x, y, z)) for x in (rasgo["desde"][0], rasgo["hasta"][0])
              for y in (rasgo["desde"][1], rasgo["hasta"][1])
              for z in (rasgo["desde"][2], rasgo["hasta"][2])]
        return min(ts), max(ts)
    a = _unitario(rasgo["eje"])
    largo = rasgo.get("profundidad_mm") or 500.0
    radio = (rasgo.get("diametro_mm") or 0) / 2
    coseno = sum(x * y for x, y in zip(a, e))
    ancho = radio * math.sqrt(max(1.0 - coseno * coseno, 0.0))
    t0 = t(rasgo["entrada"])
    t1 = t0 + largo * coseno
    return min(t0, t1) - ancho, max(t0, t1) + ancho


def _solapan(a, b, minimo=0.2) -> bool:
    return min(a[1], b[1]) - max(a[0], b[0]) > minimo


def bridas_que_no_aprietan(rasgos) -> list[str]:
    """Un tornillo con su tuerca dentro de la misma pieza es una brida: al
    apretarlo tiene que cerrarse una ranura, y esa ranura tiene que dar a lo
    que se sujeta. Las dos bases del pan-tilt (2026-11-09) salieron
    «resueltas» sin apretar el servo: en una, la ranura quedaba a 8 mm de él
    tras un bloque macizo; en la otra, la ranura daba al servo pero cabeza y
    tuerca quedaban del mismo lado. Se mide con los rasgos del kit, sin
    FreeCAD. Que el labio sea bastante fino para doblarse NO se mide."""
    agujeros = [r for r in rasgos if r.get("tipo") == "agujero"]
    tuercas = [r for r in rasgos if r.get("tipo") == "tuerca"]
    huecos = [r for r in rasgos if r.get("tipo") == "hueco"]
    fallos = []
    for tu in tuercas:
        et = _unitario(tu["eje"])
        for ag in agujeros:
            ea = _unitario(ag["eje"])
            if abs(sum(x * y for x, y in zip(ea, et))) < 0.99:
                continue
            d = [t - a for t, a in zip(tu["entrada"], ag["entrada"])]
            t = sum(x * y for x, y in zip(d, ea))
            if math.sqrt(max(sum(x * x for x in d) - t * t, 0.0)) > 0.5 or t <= 0:
                continue   # no es su tuerca: no está en su eje, o está detrás de la cabeza
            # De la cabeza a la cara de la tuerca más cercana, sin tocarla.
            prof = tu.get("profundidad_mm") or 0.0
            cara = min(t, t + prof * sum(x * y for x, y in zip(et, ea)))
            fin = cara - 0.1
            pasos = max(int(fin / 0.1), 1)
            puntos = [[a + c * fin * k / pasos for a, c in zip(ag["entrada"], ea)]
                      for k in range(pasos + 1)]
            cruzadas = [h for h in huecos if any(_en_caja(p, h) for p in puntos)]
            if not cruzadas:
                fallos.append(
                    f"brida: «{ag['nombre']}» y «{tu['nombre']}» aprietan material macizo; entre "
                    "la cabeza del tornillo y la tuerca no hay ninguna ranura que se cierre. El "
                    "tornillo tiene que CRUZAR la ranura de la brida, con la cabeza a un lado y "
                    "la tuerca al otro")
                continue
            for r in cruzadas:
                otros = [h for h in huecos if h is not r and _de_caja_a_caja(r, h) <= 0.2
                         and not any(_en_caja(p, h) for p in puntos)]
                otros += [a for a in agujeros if a is not ag and _de_caja_a_agujero(r, a) <= 0.2]
                otros = [o for o in otros if o is not tu]
                if not otros:
                    fallos.append(
                        f"brida: la ranura «{r['nombre']}», que cierra «{ag['nombre']}», no da a "
                        "ningún hueco ni agujero: al apretar se cierra sobre sí misma y no sujeta "
                        "nada. Tiene que abrirse al alojamiento de lo que sujeta, y dejar que la "
                        "parte que se cierra se doble")
                    continue
                # Lo que se cierra tiene que caer a la altura de lo que se
                # sujeta, medido a lo largo del tornillo: si no, la ranura se
                # cierra junto a ello y lo único que se mueve es la pared que
                # lo separa, alejándose. La tercera base del pan-tilt
                # (2026-11-09) pasó la regla anterior así: su lengüeta con la
                # tuerca se iba hacia la cabeza y abría el alojamiento.
                dentro = [k * fin / pasos for k, p in enumerate(puntos) if _en_caja(p, r)]
                cierra = (min(dentro), max(dentro))
                if not any(_solapan(cierra, _a_lo_largo(o, ag["entrada"], ea)) for o in otros):
                    nombres = ", ".join(f"«{o['nombre']}»" for o in otros)
                    fallos.append(
                        f"brida: al apretar «{ag['nombre']}», la ranura «{r['nombre']}» se cierra "
                        f"entre {cierra[0]:.1f} y {cierra[1]:.1f} mm de la cabeza, fuera de "
                        f"{nombres}: la pared que queda entre ambos se aparta de lo que sujeta "
                        "en vez de cerrarse sobre ello. La ranura tiene que cortar la pared de "
                        "lo que sujeta en la dirección del tornillo (el tornillo la cruza a la "
                        "altura del alojamiento, como una abrazadera partida)")
    return fallos


def componentes_sin_colocar(componentes, rasgos) -> list[str]:
    """Los componentes que el concepto nombra y el programa no coloca: sin
    colocarlos no se puede comprobar que quepan.

    Lo que viene montado en una pieza de la obra ya colocada cuenta como
    colocado: la plataforma del pan-tilt (2026-11-09) iba y venía entre
    colocar el SG90 del soporte y colocar el soporte, que ya lo trae."""
    from orchestrator.componentes import cargar
    colocados = {r.get("ficha") for r in rasgos if r.get("tipo") == "componente"}
    for id_ in [c for c in colocados if c and c.startswith("obra-")]:
        try:
            vecina = cargar(id_)
        except (KeyError, FileNotFoundError, ValueError):
            continue
        for cuerpo in vecina.cuerpos:
            # Las fichas de antes de `monta` llevan el componente delante del nombre.
            colocados.add(cuerpo.monta or cuerpo.nombre.split(": ", 1)[0])
    # Banco 1110-0128: a la polea del 608ZZ se le pedía colocar el 608zz (que
    # el kit le rechaza: lo monta el soporte) y quitar el hueco del soporte,
    # que no toca. Con órdenes que no se podían cumplir, salió sin colocar nada.
    import json
    import os
    ajenos = json.loads(os.environ.get("INTELLIPRINT_AJENOS") or "{}")

    def falta(c):
        if c in ajenos:
            return f"no colocaste el {c}: {ajenos[c]['mensaje']}"
        if c.startswith("obra-"):
            return (f"no colocaste la pieza {c}: ponla con `kit.componente(\"{c}\", en=..., "
                    "entra_por=...)`. Si la tuya la aloja o la toca, quita su `hueco()`; si "
                    "solo va al lado, basta colocarla: así se comprueba que no choquen")
        return (f"no colocaste el {c}: ponlo con `kit.componente(\"{c}\", en=..., "
                "entra_por=...)` y quita su `hueco()` a la pieza; sin eso no se puede "
                "comprobar que quepa ni que entre")
    lejos = {c for c, a in ajenos.items() if a.get("lejos")}
    return [falta(c) for c in componentes if c not in colocados and c not in lejos]


# --- el sitio de cada giro (F9.1 (barrido)) --------------------------------------------------

DETRAS_MM = 0.05
"""Lo que una pieza que gira puede asomar por detrás de la cara de salida
sin que cuente: ruido de coma flotante, no material."""


def _del_backlog() -> tuple[Path, str] | None:
    """(carpeta del backlog, nodo) si la pieza que se está diseñando es de
    uno: `INTELLIPRINT_UNIONES` apunta a `<backlog>/nodos/<nodo>/uniones.json`."""
    import os
    ruta = os.environ.get("INTELLIPRINT_UNIONES")
    if not ruta or not Path(ruta).is_file():
        return None
    return Path(ruta).parents[2], Path(ruta).parent.name


def _giros_de(carpeta: Path, nodo: str):
    """(obra, piezas construidas, articulaciones, uniones `gira` del nodo)."""
    from orchestrator import obra as O
    from orchestrator.conjunto import articulaciones_de, leer_piezas
    from orchestrator.schemas.obra import Gira

    obra = O.cargar_obra(carpeta)
    giros = [u for u in obra.uniones_de(nodo) if isinstance(u, Gira) and u.radio_libre_mm]
    if not giros:
        return obra, {}, {}, []
    piezas = leer_piezas(carpeta, solo_construidas=True)
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    return obra, piezas, arts, giros


def _salidas_del_giro(piezas, u) -> list[dict]:
    """Las salidas de lo que monta `u.sobre` sobre las que puede girar `u`."""
    from orchestrator.componentes import cargar
    from orchestrator.plan import salida_de
    nombre = salida_de(u, cargar(u.componente)).nombre
    return [s for s in piezas[u.sobre].salidas
            if s.get("ficha") == u.componente and s["nombre"] == nombre]


def _lo_que_llega(yo, punto, eje, esquinas) -> float:
    """Lo más lejos del eje que llega la pieza, medido en su malla. Con las
    esquinas de su caja, el brazo del banco 1113-0216 (150 mm del eje a la
    punta, con 150 de radio reservado) «llegaba» a 152,4 por su ancho y no
    podía cumplir a la vez su alcance y su radio. Sin malla, la caja."""
    from orchestrator.conjunto import _a_la_recta
    stl = next(iter(sorted(yo.step.parent.glob("*.stl"))), None)
    if stl is None:
        return max(_a_la_recta(q, punto, eje) for q in esquinas)
    import numpy as np
    from orchestrator.tornilleria import _triangulos
    r, d = yo.al_padre
    vs = _triangulos(str(stl), stl.stat().st_mtime).reshape(-1, 3) @ np.asarray(r).T + d
    e = np.asarray(_unitario(eje))
    return float(np.linalg.norm(np.cross(vs - np.asarray(punto), e), axis=1).max())


SIGUE_RECTO_MM = 5.0
"""Lo que tiene que separar dos ejes seguidos para que «seguir recto» de uno
al otro diga algo: con los dos en línea no hay hacia dónde."""


def _fuera_de_recto(piezas, arts, yo, punto, eje, esquinas):
    """(grados, hacia dónde) entre la punta de `yo` —lo suyo más lejos del eje
    sobre el que gira— y seguir recto desde el eje sobre el que gira la pieza
    que la lleva. `hacia dónde` va en el marco de `yo`. None si la de abajo
    no gira o sus dos ejes están en línea."""
    import numpy as np
    padre = piezas[yo.padre]
    a = arts.get(padre.id)
    if a is None or padre.al_padre is None:
        return None
    r, d = (np.asarray(x, dtype=float) for x in padre.al_padre)
    e = np.asarray(_unitario(eje), dtype=float)
    atras, su_eje = r.T @ (np.asarray(a.punto, dtype=float) - d), r.T @ np.asarray(
        _unitario(a.eje), dtype=float)
    recto = np.asarray(punto, dtype=float) - atras
    for v in (su_eje, e):
        recto = recto - (recto @ v) * v
    if np.linalg.norm(recto) < SIGUE_RECTO_MM:
        return None
    r_yo, d_yo = (np.asarray(x, dtype=float) for x in yo.al_padre)
    stl = next(iter(sorted(yo.step.parent.glob("*.stl"))), None)
    if stl is None:
        vs = np.asarray(esquinas, dtype=float)
    else:
        from orchestrator.tornilleria import _triangulos
        vs = _triangulos(str(stl), stl.stat().st_mtime).reshape(-1, 3) @ r_yo.T + d_yo
    radial = vs - np.asarray(punto, dtype=float)
    radial = radial - np.outer(radial @ e, e)
    punta = radial[np.linalg.norm(radial, axis=1).argmax()]
    coseno = punta @ recto / (np.linalg.norm(punta) * np.linalg.norm(recto))
    en_lo_mio = r_yo.T @ recto
    k = int(np.abs(en_lo_mio).argmax())
    return (math.degrees(math.acos(max(-1.0, min(1.0, float(coseno))))),
            ("+" if en_lo_mio[k] > 0 else "-") + "xyz"[k])


def defectos_de_giro(carpeta: Path, nodo: str) -> list[str]:
    """Lo que la pieza construida de `nodo` no cumple del sitio que el plan
    reserva a cada giro, sin FreeCAD.

    El pan-tilt del banco 1110-0313 falló solo «se mueve sin chocar», y por
    esto: su soporte dejó 12.7 mm entre el eje de inclinación y el SG90 de
    la base para una plataforma de 37.7. Se supo con las tres piezas dadas
    por buenas, y la corrección se le pidió a la plataforma. Aquí cada una
    lo sabe en su propio bucle:

    - la que MONTA el actuador: lo que tiene debajo no entra en el cilindro
      libre, en ningún ángulo (`conjunto.radio_libre`). Lo suyo propio lo
      mide la sonda `zona_libre`, con su forma real (`sondas_de_giro`);
    - la que GIRA: coloca la pieza sobre la que gira, llega al eje, va por
      delante de la cara de salida y no pasa del radio."""
    from orchestrator import obra as O
    from orchestrator.conjunto import (ALCANCE_MM, _a_la_recta, _caja_en, _esquinas, _que,
                                       _salida_a_la_caja, radio_libre)

    carpeta = Path(carpeta)
    obra, piezas, arts, giros = _giros_de(carpeta, nodo)
    if nodo not in piezas:
        return []
    yo, fallos = piezas[nodo], []
    for u in giros:
        radio = u.radio_libre_mm
        if u.sobre == nodo:
            gira = obra.nodo(u.gira).nombre
            for s in _salidas_del_giro(piezas, u):
                libre, que = radio_libre(piezas, arts, nodo, s)
                if libre < radio - 0.05:
                    fallos.append(
                        f"sitio para girar (unión {u.id}): «{gira}» necesita {radio:g} mm "
                        f"libres alrededor del eje del {s['de']} que monta esta pieza, y solo "
                        f"hay {libre:.1f} mm: {_que(piezas, que)} queda a {libre:.1f} mm de "
                        f"ese eje, por delante de la cara por donde sale. Sube el {s['de']} "
                        f"al menos {radio - libre:.1f} mm más, o sácalo hacia fuera hasta que "
                        "eso quede detrás de esa cara (lo que queda detrás no estorba), sin "
                        "cambiar cómo se une esta pieza a lo que tiene debajo")
            continue
        sobre = obra.nodo(u.sobre).nombre
        if yo.padre != u.sobre:
            fallos.append(
                f"giro (unión {u.id}): esta pieza gira sobre el {u.componente} de «{sobre}» y "
                f"no la colocaste, o colocaste antes otra pieza: pon primero `kit.componente("
                f"\"{O.id_de_ficha(u.sobre)}\", en=..., entra_por=...)` y acóplate a su "
                "`salida()`")
            continue
        candidatas = _salidas_del_giro(piezas, u)
        if not candidatas:
            continue   # «sobre» no colocó el actuador: es un defecto suyo, no de esta
        caja = _caja_en(yo.envolvente, yo.al_padre)
        lejos, s = min(((_salida_a_la_caja(s, caja), s) for s in candidatas),
                       key=lambda x: x[0])
        if lejos > ALCANCE_MM:
            fallos.append(
                f"giro (unión {u.id}): esta pieza no llega al eje del {s['de']} de «{sobre}»: "
                f"queda a {lejos:.1f} mm de la cara por donde sale. Lo que gira se acopla al "
                f"eje: tiene que empezar a menos de {ALCANCE_MM:g} mm de esa cara")
            continue
        esquinas = _esquinas(yo.envolvente, yo.al_padre)
        llega = _lo_que_llega(yo, s["punto"], s["eje"], esquinas)
        detras = max(-sum((c - p) * e for c, p, e in zip(q, s["punto"], s["eje"]))
                     for q in esquinas)
        if detras > DETRAS_MM:
            fallos.append(
                f"giro (unión {u.id}): esta pieza asoma {detras:.1f} mm por detrás de la cara "
                f"por donde sale el eje del {s['de']} de «{sobre}». El sitio que tiene "
                "reservado empieza en esa cara y va hacia fuera: detrás están el actuador y "
                "la pieza que lo sujeta. Llévala entera por delante de la cara")
        if llega > radio + 0.05:
            fallos.append(
                f"giro (unión {u.id}): esta pieza llega a {llega:.1f} mm del eje sobre el que "
                f"gira y «{sobre}» solo le deja {radio:g} mm libres: al girar chocará. "
                f"Encógela hasta que nada de ella pase de {radio:g} mm del eje, sin mover "
                "dónde se acopla")
    return fallos


def defectos_de_alcance(carpeta: Path, nodo: str) -> list[str]:
    """Si `nodo` es la pieza de la punta —gira y nada gira sobre ella— y el
    plan dice a dónde llega (`brazo_mm`): que llegue. Se le medía que no
    pasara de su radio libre y no que llegara: el brazo del banco 1113-0423
    se quedó en 149,1 mm de 150 y pasó su bucle."""
    from orchestrator import obra as O
    from orchestrator.conjunto import _esquinas, leer_piezas
    from orchestrator.schemas.obra import Gira

    carpeta = Path(carpeta)
    giros = [u for u in O.cargar_obra(carpeta).uniones if isinstance(u, Gira)]
    suyo = next((u for u in giros if u.gira == nodo and u.brazo_mm), None)
    if suyo is None or any(u.sobre == nodo for u in giros):
        return []
    piezas = leer_piezas(carpeta, solo_construidas=True)
    yo = piezas.get(nodo)
    if yo is None or yo.padre != suyo.sobre:
        return []
    fallos = []
    for s in _salidas_del_giro(piezas, suyo)[:1]:
        llega = _lo_que_llega(yo, s["punto"], s["eje"], _esquinas(yo.envolvente, yo.al_padre))
        if llega < suyo.brazo_mm - 0.05:
            fallos.append(
                f"alcance (unión {suyo.id}): esta pieza llega a {llega:.1f} mm del eje sobre "
                f"el que gira y tiene que llegar a {suyo.brazo_mm:g}: le faltan "
                f"{suyo.brazo_mm - llega:.1f} mm. Alárgala por la punta, sin mover dónde se "
                "acopla")
        # La muñeca del brazo mediano (banco 1113-1330) llegaba a 84 mm de su
        # eje, pero doblada hacia el codo, y solo gira 90° a cada lado de
        # como se dibuja: el brazo se quedó en 288 mm de 350 sin poder
        # estirarse. Un giro se barre la mitad a cada lado del dibujo.
        from orchestrator.conjunto import articulaciones_de
        arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
        fuera = _fuera_de_recto(piezas, arts, yo, s["punto"], s["eje"],
                                _esquinas(yo.envolvente, yo.al_padre))
        medio = suyo.recorrido_grados / 2
        if fuera and fuera[0] > medio + 1:
            sobre = O.cargar_obra(carpeta).nodo(suyo.sobre).nombre
            fallos.append(
                f"alcance (unión {suyo.id}): la punta de esta pieza queda a {fuera[0]:.0f}° de "
                f"seguir recto desde «{sobre}» y solo gira {medio:g}° a cada lado de como se "
                "dibuja: el brazo nunca llega a estirarse. Dibújala con la punta hacia "
                f"{fuera[1]} de tu marco, alejándose del eje sobre el que gira «{sobre}», sin "
                "mover dónde se acopla")
    return fallos


def defectos_de_orientacion(carpeta: Path, nodo: str) -> list[str]:
    """Los giros cuyo eje no mira hacia donde dice el plan, en la pieza que
    lo monta, con el invento en reposo y z hacia arriba.

    El soporte del banco 1113-0216 se dibujó tumbado: el eje, que la
    petición pedía horizontal, quedó vertical; el estudio no vio ningún par
    por gravedad y la carga la limitó el vuelco. Pasó su bucle porque nadie
    se lo midió."""
    from orchestrator import obra as O
    from orchestrator.conjunto import articulaciones_de, leer_piezas, poses
    from orchestrator.schemas.obra import Gira
    from orchestrator.tornilleria import _girar

    carpeta = Path(carpeta)
    giros = [u for u in O.cargar_obra(carpeta).uniones_de(nodo)
             if isinstance(u, Gira) and u.eje and u.sobre == nodo]
    if not giros:
        return []
    piezas = leer_piezas(carpeta, solo_construidas=True)
    if nodo not in piezas:
        return []
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    mundo = poses(piezas, arts, {})[nodo]
    fallos = []
    for u in giros:
        for s in _salidas_del_giro(piezas, u):
            eje = _unitario(_girar(mundo, s["eje"]))
            # Los umbrales con los que el banco llama a un eje vertical u horizontal.
            es = "vertical" if abs(eje[2]) > 0.99 else "horizontal" if abs(eje[2]) < 0.01 \
                else "inclinado"
            if es != u.eje:
                como = ("paralelo a la mesa" if u.eje == "horizontal" else "hacia arriba")
                fallos.append(
                    f"eje del giro (unión {u.id}): el eje del {s['de']} tiene que ir {u.eje} "
                    f"con la pieza puesta como se usa (z hacia arriba), y está {es}. Has "
                    "dibujado la pieza en otra postura, quizá como mejor se imprime: "
                    f"dibújala como va a quedar puesta, con ese eje {como}, y con lo que la "
                    "sujeta (la mesa, el tablero o la pieza de debajo) por abajo")
    return fallos


def _gira_segun_el_plan(carpeta: Path, nodo: str) -> bool:
    from orchestrator import obra as O
    from orchestrator.schemas.obra import Gira
    return any(isinstance(u, Gira) and u.gira == nodo
               for u in O.cargar_obra(Path(carpeta)).uniones)


def sondas_de_giro(carpeta: Path, nodo: str) -> list:
    """La sonda `zona_libre` de cada actuador que la pieza de `nodo` monta
    para que otra gire: su propio cuerpo no entra en el cilindro libre."""
    from orchestrator.banco import ZonaLibre

    _, piezas, _, giros = _giros_de(Path(carpeta), nodo)
    if nodo not in piezas:
        return []
    # Una salida que ocupa un tramo (el aro de un rodamiento, metido en una
    # pared) deja libre lo que hay MÁS ALLÁ de ese tramo: contado desde su
    # cara de atrás, la pared que lo sujeta estorbaba (a mano, 2026-11-12).
    return [ZonaLibre(tipo="zona_libre", nombre=f"{s['de']}: {s['nombre']}",
                      punto=[float(c + e * (s.get("largo") or 0.0))
                             for c, e in zip(s["punto"], s["eje"])],
                      eje=[float(c) for c in s["eje"]],
                      radio_mm=float(u.radio_libre_mm), porque=f"unión {u.id}")
            for u in giros if u.sobre == nodo for s in _salidas_del_giro(piezas, u)]


def uniones_sin_hacer(carpeta: Path, nodo: str) -> list[str]:
    """Los tornillos que el plan prevé y la pieza construida de `nodo` no
    lleva (F9.6 (previsto)), sin FreeCAD: los de sus uniones y los de lo
    comprado que monta.

    El pan-tilt 1111-1342 pasó el banco con el SG90 de la base sin un solo
    tornillo y el del soporte con dos agujeros de Ø2.2 para tornillos de 2.
    La lista de compras se deducía al final de lo que hubiera; nadie había
    dicho cuántos tenía que haber.

    De una unión entre dos piezas ya construidas responde la que se diseñó
    después: la otra está dada por buena y es contra ella que se taladra."""
    from orchestrator import obra as O
    from orchestrator.conjunto import leer_piezas
    from orchestrator.plan import sin_hacer
    from orchestrator.tornilleria import tornillos

    carpeta = Path(carpeta)
    obra = O.cargar_obra(carpeta)
    construidas = set(leer_piezas(carpeta, solo_construidas=True))
    if nodo not in construidas:
        return []
    orden = obra.orden()
    fichas = [O.carpeta_de_fichas(carpeta)]
    return [f.texto(obra, fichas)
            for f in sin_hacer(obra, tornillos(carpeta), construidas, fichas)
            if max(f.piezas, key=orden.index) == nodo]


FONDO_MM = 20.0
"""El fondo que se le pide libre a lo que se atornillará después, y
`DIAMETROS_ALREDEDOR` diámetros del tornillo a cada lado. Son un criterio,
no una medida: lo nuevo aún no existe y no se sabe cuánto ocupará. Bastan
para ver que un tornillo da de lleno a lo que hay debajo."""
DIAMETROS_ALREDEDOR = 2.0

LEJOS = 2.0
"""Hasta cuántas veces su radio libre se busca sitio para el eje de un giro
que monta la pieza que viene, saliendo de los agujeros. Otro criterio: la
pinza del banco 1112-1359 medía 73 mm para un dedo que pedía 40."""
CADA_MM = 10.0
CADA_GRADOS = 30.0
"""El paso de esa búsqueda. Son muchas medidas (cada punto, cinco ejes), y
con el paso del barrido un brazo de tres giros tardaría minutos; lo que se
encuentra se confirma con el paso de siempre."""


def _de_traves(e) -> tuple[list[float], list[float]]:
    """Dos direcciones perpendiculares a `e` y entre sí."""
    e = _unitario(e)
    otro = [1.0, 0.0, 0.0] if abs(e[0]) < 0.9 else [0.0, 1.0, 0.0]
    u = _unitario([otro[i] - sum(a * b for a, b in zip(otro, e)) * e[i] for i in range(3)])
    v = [e[1] * u[2] - e[2] * u[1], e[2] * u[0] - e[0] * u[2], e[0] * u[1] - e[1] * u[0]]
    return u, v


def _sitio_para_un_giro(piezas, arts, nodo: str, punto, hacia, radio: float,
                        pasillo: float) -> float:
    """El mayor radio libre que encuentra un eje puesto saliendo de `punto`
    hacia `hacia`, a menos de `LEJOS` radios: el del primer sitio donde
    caben los `radio`, o el mejor que haya si no cabe en ninguno.

    Lo que viene se atornilla en `punto` y monta el actuador más allá: se
    prueba cada `CADA_MM`, con el eje hacia fuera y de través. No se sigue
    más allá de donde el camino se estrecha por debajo de `pasillo`: la
    pieza tiene que llegar hasta ahí. Bajo la base no hay sitio: está
    aquello en lo que se apoya (`radio_libre(..., suelo=True)`)."""
    from orchestrator.conjunto import radio_libre

    hacia = _unitario(hacia)
    u, v = _de_traves(hacia)
    ejes = [hacia, u, [-c for c in u], v, [-c for c in v]]
    mejor, t = 0.0, 0.0
    while t <= LEJOS * radio + 1e-6:
        if t and radio_libre(piezas, arts, nodo, {"punto": punto, "eje": hacia},
                             paso=CADA_GRADOS, largo=t, suelo=True)[0] < pasillo - 0.05:
            break
        p = [c + e * t for c, e in zip(punto, hacia)]
        for eje in ejes:
            libre = radio_libre(piezas, arts, nodo, {"punto": p, "eje": eje},
                                paso=CADA_GRADOS, suelo=True, cara=False)[0]
            if libre >= radio - 0.05:
                libre = radio_libre(piezas, arts, nodo, {"punto": p, "eje": eje},
                                    suelo=True, cara=False)[0]
                if libre >= radio - 0.05:
                    return libre
            mejor = max(mejor, libre)
        t += CADA_MM
    return mejor


def _caras_con_sitio(piezas, arts, nodo: str, radio: float, pasillo: float) -> list[str]:
    """Las caras de la caja de `nodo` por las que sí cabe ese eje, saliendo
    de su centro: «+x», «-z»… en el marco de la pieza, que es el de quien
    la dibuja."""
    lo, hi = piezas[nodo].envolvente
    centro = [(a + b) / 2 for a, b in zip(lo, hi)]
    caras = []
    for k, nombre in enumerate("xyz"):
        for signo, borde in ((1, hi), (-1, lo)):
            punto = [borde[i] if i == k else centro[i] for i in range(3)]
            hacia = [float(signo) if i == k else 0.0 for i in range(3)]
            if _sitio_para_un_giro(piezas, arts, nodo, punto, hacia, radio,
                                   pasillo) >= radio - 0.05:
                caras.append(f"{'+' if signo > 0 else '-'}{nombre}")
    return caras


def sin_sitio_para_lo_nuevo(carpeta: Path, nodo: str, como_si_faltara=()) -> list[str]:
    """Las uniones de la pieza construida de `nodo` con una pieza que aún no
    existe y cuyos tornillos dan a un sitio ocupado, sin FreeCAD.

    En el banco 1112-1359 la plataforma del pan-tilt ganó dos M3 para la
    pinza y los puso en la cara que da al servo que la inclina. El soporte
    de la pinza se alineó con ellos y quedó construido encima de ese servo:
    ya no tenía arreglo, porque los agujeros no eran suyos. Dónde va lo
    nuevo lo decide quien taladra primero, y se puede medir ahí.

    Lo nuevo va al otro lado del tornillo: por donde sale, si esta pieza
    lleva la cabeza; delante de la boca del agujero, si es donde agarra. Se
    mide como el sitio de un giro (`conjunto.radio_libre`): contra las
    cajas de lo que hay debajo y de lo comprado que monta, con los giros de
    debajo en todos sus ángulos, pero solo en `FONDO_MM` de fondo.

    Si lo nuevo monta un actuador sobre el que girará otra pieza, eso no
    basta. Reanudada esa corrida, la plataforma pasó los M3 a su cara de
    abajo, con 12 mm libres; el dedo de la pinza pedía 40 alrededor de su
    eje y ahí quedaban 0.9. El soporte de la pinza gastó cinco intentos sin
    poder cumplir. Con un giro en lo que viene, saliendo de los agujeros
    tiene que haber dónde poner ese eje (`_sitio_para_un_giro`), y si no lo
    hay se dice por qué caras de la pieza sí.

    `como_si_faltara`: piezas construidas que se dejan fuera, para preguntar
    si a una que salió mal le habían dejado sitio (`banco.reanudar`)."""
    from orchestrator import obra as O
    from orchestrator.conjunto import _que, articulaciones_de, leer_piezas, radio_libre
    from orchestrator.schemas.obra import EXTERIOR, Fija, Gira
    from orchestrator.tornilleria import _diametro, tornillos

    carpeta = Path(carpeta)
    obra = O.cargar_obra(carpeta)
    todas = leer_piezas(carpeta, solo_construidas=True)
    piezas = {i: p for i, p in todas.items() if i not in set(como_si_faltara)}
    # Y lo que va sobre lo que falta: sin su padre no tiene dónde estar.
    while any(p.padre is not None and p.padre not in piezas for p in piezas.values()):
        piezas = {i: p for i, p in piezas.items() if p.padre is None or p.padre in piezas}
    if nodo not in piezas or piezas[nodo].padre is None:
        return []   # sin nada debajo no hay a qué dar

    def otra(u):
        return u.agarra if u.cabeza == nodo else u.cabeza

    por_firma: dict[tuple, list] = {}
    for u in obra.uniones_de(nodo):
        if isinstance(u, Fija) and u.agarra != EXTERIOR and otra(u) not in piezas:
            por_firma.setdefault((u.metrica, u.cabeza == nodo, u.agarre), []).append(u)
    if not por_firma:
        return []
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    libres = [t for t in tornillos(carpeta, sin=set(todas) - set(piezas))
              if t.piezas == [nodo] and not t.componente]
    fallos = []
    for (metrica, lleva_la_cabeza, agarre), uniones in por_firma.items():
        radio = DIAMETROS_ALREDEDOR * _diametro(metrica)
        medidos = []
        for t in libres:
            if t.metrica != metrica or (t.termina == "superficie") != lleva_la_cabeza \
                    or not (lleva_la_cabeza or t.termina == agarre):
                continue
            if lleva_la_cabeza:
                punto = [c + e * t.largo_mm for c, e in zip(t.cabeza, t.eje)]
                hacia = list(t.eje)
            else:
                punto, hacia = list(t.cabeza), [-e for e in t.eje]
            libre, que = radio_libre(piezas, arts, nodo, {"punto": punto, "eje": hacia},
                                     largo=FONDO_MM)
            medidos.append((libre, que, t))
        # Con pasantes de sobra (los de fijarse a una mesa son iguales)
        # basta con que tengan sitio tantos como pide el plan.
        hacen_falta = min(sum(u.cantidad for u in uniones), len(medidos))
        nuevas = " y ".join(dict.fromkeys(f"«{obra.nodo(otra(u)).nombre}»" for u in uniones))
        if sum(libre >= radio - 0.05 for libre, _, _ in medidos) >= hacen_falta:
            # Caben los tornillos. Si lo que viene monta un giro, además
            # tiene que caber su eje: se busca saliendo del agujero con más
            # sitio, que es donde irá.
            giros = [g for g in obra.uniones if isinstance(g, Gira) and g.radio_libre_mm
                     and g.sobre in {otra(u) for u in uniones}]
            if not giros or not medidos:
                continue
            giro = max(giros, key=lambda g: g.radio_libre_mm)
            _, _, t = max(medidos, key=lambda m: m[0])
            if lleva_la_cabeza:
                punto = [c + e * t.largo_mm for c, e in zip(t.cabeza, t.eje)]
                hacia = list(t.eje)
            else:
                punto, hacia = list(t.cabeza), [-e for e in t.eje]
            hay = _sitio_para_un_giro(piezas, arts, nodo, punto, hacia, giro.radio_libre_mm,
                                      radio)
            if hay >= giro.radio_libre_mm - 0.05:
                continue
            caras = _caras_con_sitio(piezas, arts, nodo, giro.radio_libre_mm, radio)
            agujero = t.agujeros[0].split(": ", 1)[-1]
            fallos.append(
                f"sitio para {nuevas} (unión {', '.join(u.id for u in uniones)}): sobre "
                f"{nuevas} girará «{obra.nodo(giro.gira).nombre}» (unión {giro.id}), que "
                f"necesita {giro.radio_libre_mm:g} mm libres alrededor de su eje, con los "
                f"giros de debajo en cualquier ángulo. {nuevas} va al otro lado de «{agujero}» "
                f"y, saliendo de ahí hasta {LEJOS * giro.radio_libre_mm:g} mm, no hay dónde "
                f"poner ese eje: lo más que queda libre son {hay:.1f} mm. "
                + (f"Sí lo hay saliendo por la cara {' o la '.join(caras)} de esta pieza: "
                   "lleva ahí esos agujeros, con el tornillo saliendo hacia fuera por esa cara"
                   if caras else
                   "Tal como es esta pieza no lo hay por ninguna de sus caras: alárgala hacia "
                   "donde no haya nada de las piezas sobre las que va ni de lo comprado que "
                   "montan, y pon ahí esos agujeros"))
            continue
        libre, que, t = min(medidos, key=lambda m: m[0])
        agujero = t.agujeros[0].split(": ", 1)[-1]
        fallos.append(
            f"sitio para {nuevas} (unión {', '.join(u.id for u in uniones)}): {nuevas} se "
            "diseñará después, contra esta pieza, y va al otro lado de sus tornillos "
            f"{metrica}; ahí no cabe. «{agujero}» da a {_que(piezas, que)}, que queda a "
            f"{libre:.1f} mm por ese lado, y hacen falta al menos {radio:g} mm libres "
            f"alrededor en {FONDO_MM:g} mm de fondo, con los giros de debajo en cualquier "
            "ángulo. Pon esos agujeros en otra cara de esta pieza: una que dé a un sitio "
            "sin nada de las piezas sobre las que va ni de lo comprado que montan")
    return fallos


def defectos_del_plan() -> list[str]:
    """`uniones_sin_hacer` de la pieza que se está diseñando, si es de un
    backlog."""
    backlog = _del_backlog()
    return uniones_sin_hacer(*backlog) if backlog is not None else []


def no_cabe_en_la_impresora(caja_mm, cama_mm) -> list[str]:
    """Si la caja de la pieza no entra en la impresora en ninguna postura
    derecha (`cama_mm`: ancho y fondo de la cama, y alto). La torreta del
    brazo mediano (banco 1113-1330) salió de 126 × 90 × 430 mm para una
    impresora de 250 de alto y se dio por buena: nadie lo medía. En diagonal
    sobre la cama no se prueba."""
    from itertools import permutations
    if any(all(lado <= hay + 0.05 for lado, hay in zip(p, cama_mm))
           for p in permutations(caja_mm)):
        return []
    mide = " × ".join(f"{round(v, 1):g}" for v in caja_mm)
    x, y, z = cama_mm
    return [f"no cabe en la impresora: la pieza mide {mide} mm y la impresora admite "
            f"{x:g} × {y:g} mm de cama y {z:g} de alto; no entra en ninguna postura. Hazla "
            "más pequeña. Si la altura era para dejar sitio a un giro, saca el eje hacia "
            "fuera en vez de subirlo: lo que queda detrás de la cara por donde sale no "
            "estorba"]


def defectos_de_la_pieza(requisitos, resultado, step, freecadcmd: str,
                         material: dict, componentes=(), pared_min_mm=None,
                         agujeros_del_perfil=None, holgura_al_moverse_mm=None,
                         cama_mm=None) -> list[str]:
    """Lo que la pieza construida no cumple: agujeros (con los rasgos del
    kit), componentes que no caben o no entran, y sondas sobre el STEP. Los
    de acabado van con su prefijo.

    En un backlog con plan, también el sitio de cada giro (F9.1 (barrido))
    y, si la pieza gira y está en su sitio, el choque al moverla contra lo
    ya construido (F9.5 (parcial)), con `holgura_al_moverse_mm`."""
    from orchestrator.banco import (AccesoTornillo, AristasVivas, ComponenteCabe,
                                    ComponenteEntra, ParedMinima, ZonaLibre, medir_sondas)

    fallos = defectos(requisitos, resultado.rasgos, agujeros_del_perfil)
    fallos += componentes_sin_colocar(componentes, resultado.rasgos)
    fallos += bridas_que_no_aprietan(resultado.rasgos)
    if cama_mm:
        fallos += no_cabe_en_la_impresora(resultado.bbox_mm, cama_mm)
    sondas = sondas_de(requisitos, resultado.rasgos, pared_min_mm)
    backlog = _del_backlog()
    if backlog is not None:
        # Una medida rota no es un defecto de la pieza ni un motivo para
        # perder el proyecto: se dice y se sigue, como con una sonda rota.
        try:
            del_giro = defectos_de_giro(*backlog)
            fallos += del_giro
            sondas += sondas_de_giro(*backlog)
            # Solo la pieza que gira, y solo en su sitio: fuera de él el
            # barrido repetiría, más caro, lo que ya se le dice con cifras.
            if (not del_giro and holgura_al_moverse_mm is not None
                    and _gira_segun_el_plan(*backlog)):
                from orchestrator.conjunto import mover_lo_construido
                movida = mover_lo_construido(*backlog, freecadcmd, holgura_al_moverse_mm)
                if movida["correccion"]:
                    fallos.append(movida["correccion"])
        except Exception as fallo:  # noqa: BLE001
            print(f"  sin medir el sitio de los giros: {type(fallo).__name__}: {fallo}",
                  flush=True)
        # Aparte: que falle una medida no deja sin hacer la otra.
        try:
            fallos += defectos_del_plan()
        except Exception as fallo:  # noqa: BLE001
            print(f"  sin contar los tornillos del plan: {type(fallo).__name__}: {fallo}",
                  flush=True)
        try:
            fallos += defectos_de_alcance(*backlog)
        except Exception as fallo:  # noqa: BLE001
            print(f"  sin medir a dónde llega: {type(fallo).__name__}: {fallo}", flush=True)
        try:
            fallos += defectos_de_orientacion(*backlog)
        except Exception as fallo:  # noqa: BLE001
            print(f"  sin medir hacia dónde mira el eje: {type(fallo).__name__}: {fallo}",
                  flush=True)
        try:
            from orchestrator.transmision import defectos_de_transmision
            fallos += defectos_de_transmision(*backlog)
        except Exception as fallo:  # noqa: BLE001
            print(f"  sin medir la correa: {type(fallo).__name__}: {fallo}", flush=True)
        try:
            fallos += sin_sitio_para_lo_nuevo(*backlog)
        except Exception as fallo:  # noqa: BLE001
            print(f"  sin medir el sitio para lo que se atornilla después: "
                  f"{type(fallo).__name__}: {fallo}", flush=True)
    for sonda, medida in zip(sondas, medir_sondas(step, sondas, freecadcmd, material)):
        if medida.estado != "no_cumple":
            continue   # «sin medir» (una sonda rota) no es culpa del diseñador
        if isinstance(sonda, ZonaLibre):
            fallos.append(f"sitio para girar ({sonda.porque}): {medida.detalle}. Sujeta el "
                          "actuador por detrás de esa cara y aparta de ahí lo que sobresale")
        elif isinstance(sonda, AristasVivas):
            # Antes decía `redondear(1, aristas="todas")`: redondea también los
            # rincones, y en el SG90 del banco eso cerró la ventana del servo.
            fallos.append(f"{ACABADO}: {medida.detalle}. Termina con `return pieza.acabar()`, "
                          "que redondea todas las esquinas sin rellenar los rincones; si "
                          "una pared es fina, `acabar(radio=0.5)`")
        elif isinstance(sonda, ComponenteCabe):
            fallos.append(f"{medida.detalle}. Resta a la pieza el `hueco()` del componente "
                          "(`pieza.quitar(\"...\", componente.hueco())`), y si lo que choca "
                          "es algo que la pieza necesita, muévelo o cambia por dónde entra")
        elif isinstance(sonda, ParedMinima):
            fallos.append(mensaje_de_pared(medida.detalle, resultado.rasgos, pared_min_mm))
        elif isinstance(sonda, AccesoTornillo):
            fallos.append(f"{medida.detalle}. Mueve el tornillo a donde se llegue desde "
                          "fuera, aparta lo que tapa su camino, o atorníllalo desde el otro "
                          "lado (la `en` del agujero es donde va la cabeza)")
        elif isinstance(sonda, ComponenteEntra):
            fallos.append(f"{medida.detalle}. El camino de entrada tiene que quedar abierto: "
                          "el `hueco()` lo abre, o cambia `entra_por` a un lado sin pared")
        else:
            fallos.append(f"{sonda.porque}: {medida.detalle}. La abertura tiene que atravesar "
                          "la pieza entera, no ser un rebaje, y llevar holgura")
    return fallos
