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
    return [falta(c) for c in componentes if c not in colocados]


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
                        f"ese eje. Sube o aleja el {s['de']} al menos {radio - libre:.1f} mm "
                        "más, sin cambiar cómo se une esta pieza a lo que tiene debajo")
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
        llega = max(_a_la_recta(q, s["punto"], s["eje"]) for q in esquinas)
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
                f"Encógela hasta que ninguna esquina pase de {radio:g} mm del eje, sin mover "
                "dónde se acopla")
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
    return [ZonaLibre(tipo="zona_libre", nombre=f"{s['de']}: {s['nombre']}",
                      punto=[float(c) for c in s["punto"]], eje=[float(c) for c in s["eje"]],
                      radio_mm=float(u.radio_libre_mm), porque=f"unión {u.id}")
            for u in giros if u.sobre == nodo for s in _salidas_del_giro(piezas, u)]


def defectos_de_la_pieza(requisitos, resultado, step, freecadcmd: str,
                         material: dict, componentes=(), pared_min_mm=None,
                         agujeros_del_perfil=None, holgura_al_moverse_mm=None) -> list[str]:
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
